from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import boto3
from botocore.config import Config as BotoConfig

logger = logging.getLogger("audit-service.sqs")

AWS_ENDPOINT_URL: str = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
AWS_REGION: str = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "test")
AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "test")


def _build_sync_client() -> Any:
    return boto3.client(
        "sqs",
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


_sqs_client: Any | None = None


def get_sqs_client() -> Any:
    global _sqs_client
    if _sqs_client is None:
        _sqs_client = _build_sync_client()
        logger.info(
            "SQS client initialised (endpoint=%s, region=%s)",
            AWS_ENDPOINT_URL,
            AWS_REGION,
        )
    return _sqs_client


async def get_queue_url(queue_name: str) -> str:
    client = get_sqs_client()
    try:
        resp = await asyncio.to_thread(client.get_queue_url, QueueName=queue_name)
        return resp["QueueUrl"]
    except client.exceptions.QueueDoesNotExist:
        logger.info("Queue '%s' not found – creating it", queue_name)
        resp = await asyncio.to_thread(
            client.create_queue,
            QueueName=queue_name,
            Attributes={"VisibilityTimeout": "30"},
        )
        return resp["QueueUrl"]
