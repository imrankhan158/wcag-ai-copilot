from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid

from bs4 import BeautifulSoup
from wcag_common.models import ScrapeRequest
from scraper_s3 import download_html

logger = logging.getLogger("audit-service.scraper")


async def resolve_input(
    user_input: str,
    user_id: str | None = None,
    redis=None,
    sqs_client=None,
    queue_url: str | None = None,
) -> str:
    """Resolve user input: if it's a URL, scrape it via SQS/S3 pipeline. Otherwise return as-is."""
    input_stripped = user_input.strip()
    if not re.match(r"^https?://", input_stripped):
        return user_input

    try:
        job_id = str(uuid.uuid4())
        job_key = f"job:{job_id}"

        # 1. Set pending status in Redis
        if redis is not None:
            await redis.set(
                job_key,
                json.dumps({"status": "pending", "url": input_stripped}),
                ex=3600,
            )

        # 2. Publish scrape request to SQS
        if sqs_client and queue_url:
            task = ScrapeRequest(
                job_id=job_id,
                url=input_stripped,
                user_id=user_id or "anonymous",
            )
            await asyncio.to_thread(
                sqs_client.send_message,
                QueueUrl=queue_url,
                MessageBody=task.model_dump_json(),
            )
        else:
            logger.warning("SQS client or queue_url not configured — cannot scrape URL")
            return f"Failed to crawl URL {input_stripped}: SQS not configured"

        # 3. Poll Redis for result
        max_attempts = 120
        html = None
        for _ in range(max_attempts):
            await asyncio.sleep(0.5)
            if redis is None:
                continue
            status_raw = await redis.get(job_key)
            if status_raw:
                job_state = json.loads(status_raw)
                if job_state["status"] == "success":
                    s3_key = job_state["s3_key"]
                    # Download HTML from S3
                    html = await download_html(s3_key)
                    break
                elif job_state["status"] == "error":
                    raise Exception(job_state.get("error_message") or "Scraping failed")

        if not html:
            raise Exception("Timeout waiting for scraper worker response.")

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "meta", "link", "svg", "noscript"]):
            tag.decompose()
        body = soup.body
        content = str(body) if body else html
        if len(content) > 15000:
            content = content[:15000] + "\n... [HTML truncated for length] ..."
        return f"CRAWLED URL: {input_stripped}\n\nHTML CONTENT:\n```html\n{content}\n```"

    except Exception as e:
        logger.error(f"resolve_input error: {e}")
        return f"Failed to crawl URL {input_stripped}: {str(e)}"
