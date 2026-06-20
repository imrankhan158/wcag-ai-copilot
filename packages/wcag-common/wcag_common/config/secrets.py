from __future__ import annotations

import json
import os
import logging
import boto3

logger = logging.getLogger("wcag_common.config.secrets")


def fetch_aws_secrets(secret_id: str, region_name: str = "us-east-1") -> dict[str, str]:
    """Retrieves secret variables dynamically from AWS Secrets Manager."""
    provider = os.getenv("SECRETS_PROVIDER")
    if provider != "aws":
        return {}

    logger.info(f"Fetching configuration secrets from AWS Secrets Manager: {secret_id}")
    try:
        # Use credentials from IAM instance profile / task role if keys not set in env
        session = boto3.session.Session()
        client = session.client(
            service_name="secretsmanager",
            region_name=os.getenv("AWS_DEFAULT_REGION", region_name),
            endpoint_url=os.getenv("AWS_ENDPOINT_URL")  # Support local stack testing
        )
        
        response = client.get_secret_value(SecretId=secret_id)
        if "SecretString" in response:
            return json.loads(response["SecretString"])
        else:
            logger.warning("SecretString payload not found in AWS Secrets Manager response.")
    except Exception as e:
        logger.error(f"Failed to fetch secrets from AWS Secrets Manager: {e}", exc_info=True)
        
    return {}
