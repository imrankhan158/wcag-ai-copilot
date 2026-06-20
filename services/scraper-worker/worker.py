"""Scraper Worker main service process.

Consumes scrape requests from SQS, executes Playwright headless crawls,
uploads HTML to S3, and updates Redis job state.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
from datetime import datetime, timezone

import redis.asyncio as aioredis
from wcag_common import BaseServiceSettings, S3ClientWrapper, SQSClientWrapper
from wcag_common.models.queue import ScrapeRequest, ScrapeResult

from pool import BrowserContextPool
from wcag_common.observability.logging import setup_json_logging

# Setup logging
setup_json_logging("scraper-worker")
logger = logging.getLogger("scraper-worker")

# Setup Settings
class ScraperSettings(BaseServiceSettings):
    service_name: str = "scraper-worker"
    max_concurrent_scrapes: int = 5
    visibility_timeout_seconds: int = 60
    scraper_cache_bucket: str = "wcag-scraper-cache"
    queue_requests: str = "scrape-requests"
    queue_results: str = "scrape-results"


settings = ScraperSettings()
browser_pool = BrowserContextPool(max_contexts=settings.max_concurrent_scrapes)
redis_client: aioredis.Redis | None = None
sqs_wrapper = SQSClientWrapper(settings)
s3_wrapper = S3ClientWrapper(settings)

# Global run loop control
_running = True


async def init_services() -> None:
    """Initialize Redis and Playwright services."""
    global redis_client
    logger.info("Initializing services...")
    redis_client = aioredis.from_url(
        settings.redis_url,
        decode_responses=True,
    )
    await redis_client.ping()
    logger.info("Connected to Redis at %s", settings.redis_url)

    await s3_wrapper.verify_bucket(settings.scraper_cache_bucket)
    await browser_pool.start()
    logger.info("Browser pool pre-warmed.")


async def close_services() -> None:
    """Shutdown Redis and Playwright services."""
    logger.info("Closing services...")
    if redis_client:
        await redis_client.aclose()
    await browser_pool.stop()
    logger.info("All services shut down.")


async def process_scrape_task(request_data: dict) -> None:
    """Run a single Playwright scrape task and publish results."""
    try:
        # Validate task payload with Pydantic schema
        task = ScrapeRequest(**request_data)
    except Exception as exc:
        logger.error("Failed to parse scrape request: %s", request_data, exc_info=True)
        return

    job_id = task.job_id
    url = task.url
    user_id = task.user_id

    # 1. Update job status to "scraping" in Redis
    job_key = f"job:{job_id}"
    await redis_client.set(
        job_key,
        json.dumps({"status": "scraping", "url": url, "updated_at": datetime.now(timezone.utc).isoformat()}),
        ex=3600,
    )

    logger.info("Starting crawl for job %s, URL: %s", job_id, url)
    context = await browser_pool.get_context()
    page = None
    html_content = ""
    status = "success"
    error_msg = None

    try:
        page = await context.new_page()
        # Enforce 30s timeout on navigation
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_load_state("domcontentloaded")
        html_content = await page.content()
    except Exception as e:
        logger.warning("Crawl failed for job %s: %s", job_id, str(e))
        status = "error"
        error_msg = str(e)
    finally:
        if page:
            await page.close()
        await browser_pool.release_context(context)

    s3_key = f"html/{job_id}.html"

    if status == "success":
        # 2. Upload to S3
        upload_ok = await s3_wrapper.upload_content(
            settings.scraper_cache_bucket,
            s3_key,
            html_content,
        )
        if not upload_ok:
            status = "error"
            error_msg = "S3 upload failed"

    # 3. Update job status in Redis
    if status == "success":
        await redis_client.set(
            job_key,
            json.dumps({
                "status": "success",
                "s3_key": s3_key,
                "url": url,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }),
            ex=3600,
        )
    else:
        await redis_client.set(
            job_key,
            json.dumps({
                "status": "error",
                "error_message": error_msg,
                "url": url,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }),
            ex=3600,
        )

    # 4. Publish results message to SQS `scrape-results`
    result = ScrapeResult(
        job_id=job_id,
        url=url,
        s3_key=s3_key if status == "success" else None,
        status=status,
        error_message=error_msg,
        scraped_at=datetime.now(timezone.utc),
    )
    attributes = {
        "timestamp": {
            "DataType": "String",
            "StringValue": datetime.now(timezone.utc).isoformat(),
        },
        "source_service": {
            "DataType": "String",
            "StringValue": settings.service_name,
        },
    }
    await sqs_wrapper.publish_message(
        settings.queue_results,
        result.model_dump_json(),
        attributes=attributes,
    )
    logger.info("Completed crawl job %s with status: %s", job_id, status)


async def main() -> None:
    """Worker main loop polling SQS."""
    global _running
    await init_services()

    # Graceful shutdown handlers
    loop = asyncio.get_running_loop()

    def handle_shutdown():
        global _running
        logger.info("Received shutdown signal. Stopping worker loop...")
        _running = False

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_shutdown)

    logger.info("Scraper worker polling SQS queue '%s'...", settings.queue_requests)
    
    # Track concurrent tasks
    active_tasks = set()

    while _running:
        try:
            # SQS long-polling (max 10 messages, 10s wait to allow quick check of _running)
            messages = await sqs_wrapper.receive_messages(
                settings.queue_requests,
                max_messages=settings.max_concurrent_scrapes - len(active_tasks),
                wait_time_seconds=10,
                visibility_timeout=settings.visibility_timeout_seconds,
            )

            for message in messages:
                receipt_handle = message["ReceiptHandle"]
                try:
                    payload = json.loads(message["Body"])
                except Exception:
                    logger.error("Failed to decode message JSON: %s", message["Body"])
                    await sqs_wrapper.delete_message(settings.queue_requests, receipt_handle)
                    continue

                # Run process in background to handle concurrently
                task = asyncio.create_task(process_scrape_task(payload))
                active_tasks.add(task)
                
                # Delete message from SQS on completion ONLY if it succeeded without unhandled exceptions
                def make_done_callback(h):
                    def callback(t: asyncio.Task):
                        active_tasks.discard(t)
                        try:
                            exc = t.exception()
                            if exc is not None:
                                logger.error("Scrape task failed with unhandled exception, leaving message on queue", exc_info=exc)
                                return
                        except asyncio.CancelledError:
                            logger.warning("Scrape task was cancelled, leaving message on queue")
                            return
                        # Message successfully processed, delete from SQS
                        asyncio.create_task(sqs_wrapper.delete_message(settings.queue_requests, h))
                    return callback
                task.add_done_callback(make_done_callback(receipt_handle))

            # Small backoff sleep if no messages or wait for active tasks
            if not messages:
                await asyncio.sleep(0.5)
            else:
                # Limit concurrency
                while len(active_tasks) >= settings.max_concurrent_scrapes:
                    await asyncio.sleep(0.1)

        except Exception as e:
            logger.error("Error in worker polling loop", exc_info=True)
            await asyncio.sleep(5)

    # Wait for remaining active tasks to finish on shutdown
    if active_tasks:
        logger.info("Waiting for %d active scrapes to complete...", len(active_tasks))
        await asyncio.gather(*active_tasks, return_exceptions=True)

    await close_services()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker stopped.")
