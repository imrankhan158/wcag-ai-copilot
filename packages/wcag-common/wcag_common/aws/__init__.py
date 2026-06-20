"""Shared AWS utilities (S3 and SQS client wrappers)."""

from wcag_common.aws.s3_client import S3ClientWrapper
from wcag_common.aws.sqs_client import SQSClientWrapper

__all__ = [
    "S3ClientWrapper",
    "SQSClientWrapper",
]
