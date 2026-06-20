from __future__ import annotations

import hashlib
from pathlib import Path

from playwright.sync_api import sync_playwright

CACHE_DIR = Path("data/ingestion_cache/html")


class PlaywrightFetcher:
    """Fetch rendered pages with Playwright and cache the HTML locally."""

    def __init__(self, cache_dir: Path = CACHE_DIR, refresh: bool = False) -> None:
        self.cache_dir = cache_dir
        self.refresh = refresh
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def cache_path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
        return self.cache_dir / f"{digest}.html"

    def fetch(self, url: str) -> str:
        path = self.cache_path(url)
        if path.exists() and not self.refresh:
            return path.read_text(encoding="utf-8")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=60_000)
            page.wait_for_load_state("domcontentloaded")
            html = page.content()
            browser.close()

        path.write_text(html, encoding="utf-8")
        return html
