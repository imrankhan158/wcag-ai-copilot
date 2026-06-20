"""Async-friendly SQS client wrapper configured using BaseServiceSettings."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import boto3
from botocore.config import Config as BotoConfig
from wcag_common.config.settings import BaseServiceSettings

logger = logging.getLogger(__name__)


class SQSClientWrapper:
    """Helper wrapper for async SQS queue interaction using boto3."""

    def __init__(self, settings: BaseServiceSettings) -> None:
        self.settings = settings
        self.client: Any = boto3.client(
            "sqs",
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

    async def get_queue_url(self, queue_name: str) -> str:
        """Resolve a queue name to its URL, creating it if necessary."""
        try:
            resp = await asyncio.to_thread(self.client.get_queue_url, QueueName=queue_name)
            return resp["QueueUrl"]
        except self.client.exceptions.QueueDoesNotExist:
            logger.info("Queue '%s' not found – creating it", queue_name)
            resp = await asyncio.to_thread(
                self.client.create_queue,
                QueueName=queue_name,
                Attributes={"VisibilityTimeout": "30"},
            )
            return resp["QueueUrl"]

    async def publish_message(self, queue_name: str, body: str, delay_seconds: int = 0, attributes: dict | None = None) -> str | None:
        """Publish a message to the SQS queue."""
        try:
            queue_url = await self.get_queue_url(queue_name)
            kwargs: dict[str, Any] = {
                "QueueUrl": queue_url,
                "MessageBody": body,
                "DelaySeconds": min(delay_seconds, 900),
            }
            if attributes:
                kwargs["MessageAttributes"] = attributes

            resp = await asyncio.to_thread(self.client.send_message, **kwargs)
            return resp.get("MessageId")
        except Exception:
            logger.error("Failed to publish message to SQS queue '%s'", queue_name, exc_info=True)
            return None

    async def receive_messages(
        self, queue_name: str, max_messages: int = 10, wait_time_seconds: int = 20, visibility_timeout: int = 30
    ) -> list[dict]:
        """Poll and receive messages from the SQS queue."""
        try:
            queue_url = await self.get_queue_url(queue_name)
            resp = await asyncio.to_thread(
                self.client.receive_message,
                QueueUrl=queue_url,
                MaxNumberOfMessages=max_messages,
                WaitTimeSeconds=wait_time_seconds,
                VisibilityTimeout=visibility_timeout,
                MessageAttributeNames=["All"],
            )
            return resp.get("Messages", [])
        except Exception:
            logger.error("Failed to receive messages from SQS queue '%s'", queue_name, exc_info=True)
            return []

    async def delete_message(self, queue_name: str, receipt_handle: str) -> bool:
        """Delete/Acknowledge a message from the SQS queue."""
        try:
            queue_url = await self.get_queue_url(queue_name)
            await asyncio.to_thread(
                self.client.delete_message,
                QueueUrl=queue_url,
                ReceiptHandle=receipt_handle,
            )
            return True
        except Exception:
            logger.error("Failed to delete message from SQS queue '%s'", queue_name, exc_info=True)
            return False
