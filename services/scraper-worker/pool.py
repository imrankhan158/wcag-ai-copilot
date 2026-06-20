"""Playwright Browser Context Pool manager.

Reuses a single Chromium browser instance and manages pre-warmed/reused
isolated browser contexts, recycling them to prevent memory leaks.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from playwright.async_api import async_playwright

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Playwright

logger = logging.getLogger(__name__)


class BrowserContextPool:
    """Manages a pool of Playwright browser contexts from a single browser instance."""

    def __init__(self, max_contexts: int = 5, recycle_limit: int = 50) -> None:
        self.max_contexts = max_contexts
        self.recycle_limit = recycle_limit

        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._active_contexts: dict[BrowserContext, int] = {}
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Start Playwright and launch the headless Chromium instance."""
        async with self._lock:
            if self._browser is not None:
                return

            logger.info("Starting Playwright and launching Chromium...")
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )
            logger.info("Chromium launched successfully.")

    async def get_context(self) -> BrowserContext:
        """Get an isolated browser context, creating one if needed."""
        await self.start()
        async with self._lock:
            # Clean up closed or dead contexts
            for ctx in list(self._active_contexts.keys()):
                # Context has no native way to check if dead, but we can verify if it works
                # or if we have exceeded the use limit, recycle it.
                if self._active_contexts[ctx] >= self.recycle_limit:
                    logger.info("Recycling browser context (reached reuse limit %d)", self.recycle_limit)
                    try:
                        await ctx.close()
                    except Exception:
                        pass
                    self._active_contexts.pop(ctx, None)

            # Check if we can create a new context
            if len(self._active_contexts) < self.max_contexts:
                assert self._browser is not None
                context = await self._browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                )
                self._active_contexts[context] = 1
                logger.info("Created new isolated browser context. Active: %d", len(self._active_contexts))
                return context

            # Re-use the least used active context
            best_context = min(self._active_contexts, key=self._active_contexts.get)
            self._active_contexts[best_context] += 1
            logger.debug("Reusing browser context (usage count: %d)", self._active_contexts[best_context])
            return best_context

    async def release_context(self, context: BrowserContext) -> None:
        """Release context or close it if it's exceeded the reuse limit."""
        async with self._lock:
            if context in self._active_contexts:
                if self._active_contexts[context] >= self.recycle_limit:
                    logger.info("Closing context on release (reached reuse limit %d)", self.recycle_limit)
                    try:
                        await context.close()
                    except Exception:
                        pass
                    self._active_contexts.pop(context, None)

    async def check_health(self) -> bool:
        """Verify that the browser is alive and responsive."""
        if self._browser is None:
            return False
        try:
            # Try launching a quick test context to check responsiveness
            ctx = await self._browser.new_context()
            await ctx.close()
            return True
        except Exception:
            logger.error("Browser pool health check failed", exc_info=True)
            return False

    async def stop(self) -> None:
        """Close all contexts and terminate the browser instance."""
        async with self._lock:
            logger.info("Stopping browser pool...")
            for ctx in list(self._active_contexts.keys()):
                try:
                    await ctx.close()
                except Exception:
                    pass
            self._active_contexts.clear()

            if self._browser:
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None

            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
                self._playwright = None
            logger.info("Browser pool stopped.")
