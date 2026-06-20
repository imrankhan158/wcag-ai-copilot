from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import boto3
from botocore.config import Config as BotoConfig

logger = logging.getLogger("audit-service.s3")

AWS_ENDPOINT_URL: str = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
AWS_REGION: str = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "test")
AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "test")
SCRAPER_CACHE_BUCKET: str = os.getenv("SCRAPER_CACHE_BUCKET", "wcag-scraper-cache")


def _build_sync_client() -> Any:
    return boto3.client(
        "s3",
        endpoint_url=AWS_ENDPOINT_URL,
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        config=BotoConfig(
            retries={"max_attempts": 3, "mode": "standard"},
            connect_timeout=5,
            read_timeout=30,
        ),
    )


_s3_client: Any | None = None


def get_s3_client() -> Any:
    global _s3_client
    if _s3_client is None:
        _s3_client = _build_sync_client()
        logger.info(
            "S3 client initialised (endpoint=%s, region=%s)",
            AWS_ENDPOINT_URL,
            AWS_REGION,
        )
    return _s3_client


async def download_html(s3_key: str) -> str | None:
    client = get_s3_client()
    try:
        resp = await asyncio.to_thread(
            client.get_object,
            Bucket=SCRAPER_CACHE_BUCKET,
            Key=s3_key,
        )
        body = resp["Body"].read()
        return body.decode("utf-8")
    except Exception:
        logger.error("Failed to download HTML from S3 key %s", s3_key, exc_info=True)
        return None
