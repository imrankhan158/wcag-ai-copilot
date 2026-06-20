#!/usr/bin/env sh
# =============================================================================
# init-aws.sh — Bootstrap local AWS resources via floci (LocalStack)
#
# Creates SQS queues and S3 buckets needed by the WCAG AI Copilot.
# Runs as a one-shot container in docker-compose.
# =============================================================================
set -e

ENDPOINT="http://floci:4566"

echo "==> Waiting for floci to be ready..."
until aws --endpoint-url "$ENDPOINT" sqs list-queues 2>/dev/null; do
    echo "    floci not ready yet, retrying in 2s..."
    sleep 2
done
echo "==> floci is ready!"

# ---------------------------------------------------------------------------
# SQS Queues
# ---------------------------------------------------------------------------
echo "==> Creating SQS dead-letter queues..."
aws --endpoint-url "$ENDPOINT" sqs create-queue --queue-name scrape-requests-dlq   || true
aws --endpoint-url "$ENDPOINT" sqs create-queue --queue-name audit-requests-dlq    || true

echo "==> Creating SQS queues..."
aws --endpoint-url "$ENDPOINT" sqs create-queue --queue-name scrape-requests \
    --attributes '{
        "RedrivePolicy": "{\"deadLetterTargetArn\":\"arn:aws:sqs:us-east-1:000000000000:scrape-requests-dlq\",\"maxReceiveCount\":\"3\"}"
    }' || true

aws --endpoint-url "$ENDPOINT" sqs create-queue --queue-name scrape-results        || true

aws --endpoint-url "$ENDPOINT" sqs create-queue --queue-name audit-requests \
    --attributes '{
        "RedrivePolicy": "{\"deadLetterTargetArn\":\"arn:aws:sqs:us-east-1:000000000000:audit-requests-dlq\",\"maxReceiveCount\":\"3\"}"
    }' || true

aws --endpoint-url "$ENDPOINT" sqs create-queue --queue-name audit-results         || true
aws --endpoint-url "$ENDPOINT" sqs create-queue --queue-name notification-send     || true

# ---------------------------------------------------------------------------
# S3 Buckets
# ---------------------------------------------------------------------------
echo "==> Creating S3 buckets..."
aws --endpoint-url "$ENDPOINT" s3 mb s3://wcag-scraper-cache || true

echo "==> AWS resource initialization complete!"
aws --endpoint-url "$ENDPOINT" sqs list-queues
aws --endpoint-url "$ENDPOINT" s3 ls
