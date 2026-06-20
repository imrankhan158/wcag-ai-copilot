"""Async-friendly S3 client wrapper configured using BaseServiceSettings."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import boto3
from botocore.config import Config as BotoConfig
from wcag_common.config.settings import BaseServiceSettings

logger = logging.getLogger(__name__)


class S3ClientWrapper:
    """Helper wrapper for async S3 bucket interaction using boto3."""

    def __init__(self, settings: BaseServiceSettings) -> None:
        self.settings = settings
        self.client: Any = boto3.client(
            "s3",
            endpoint_url=self.settings.aws_endpoint_url,
            region_name=self.settings.aws_region,
            aws_access_key_id=self.settings.aws_access_key_id,
            aws_secret_access_key=self.settings.aws_secret_access_key,
            config=BotoConfig(
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=5,
                read_timeout=30,
            ),
        )

    async def verify_bucket(self, bucket_name: str) -> None:
        """Ensure the bucket exists, creating it if necessary."""
        try:
            await asyncio.to_thread(self.client.head_bucket, Bucket=bucket_name)
        except Exception:
            logger.info("Bucket '%s' not found – creating it", bucket_name)
            try:
                await asyncio.to_thread(
                    self.client.create_bucket,
                    Bucket=bucket_name,
                )
            except Exception:
                logger.error("Failed to create bucket '%s'", bucket_name, exc_info=True)

    async def upload_content(self, bucket_name: str, key: str, content: str, content_type: str = "text/html") -> bool:
        """Upload string content to an S3 bucket."""
        await self.verify_bucket(bucket_name)
        try:
            await asyncio.to_thread(
                self.client.put_object,
                Bucket=bucket_name,
                Key=key,
                Body=content.encode("utf-8"),
                ContentType=content_type,
            )
            logger.info("Uploaded content to S3: %s/%s", bucket_name, key)
            return True
        except Exception:
            logger.error("Failed to upload to S3: %s/%s", bucket_name, key, exc_info=True)
            return False

    async def download_content(self, bucket_name: str, key: str) -> str | None:
        """Download string content from an S3 bucket."""
        try:
            resp = await asyncio.to_thread(
                self.client.get_object,
                Bucket=bucket_name,
                Key=key,
            )
            body = resp["Body"].read()
            return body.decode("utf-8")
        except Exception:
            logger.error("Failed to download from S3: %s/%s", bucket_name, key, exc_info=True)
            return None
