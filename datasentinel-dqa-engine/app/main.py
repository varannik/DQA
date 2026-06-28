import logging
import os
import time

import boto3

from app.consumer import process_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dqa-engine.main")


def poll_loop():
    queue_url = os.environ["SQS_REQUEST_URL"]
    sqs = boto3.client("sqs", region_name=os.environ.get("AWS_REGION", "eu-west-1"))
    logger.info("DQA worker polling %s", queue_url)
    while True:
        resp = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=20,
            VisibilityTimeout=int(os.environ.get("VISIBILITY_TIMEOUT", "900")),
        )
        for msg in resp.get("Messages", []):
            try:
                process_message(msg["Body"])
                sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=msg["ReceiptHandle"])
            except Exception:
                logger.exception("Failed to process DQA job")


if __name__ == "__main__":
    poll_loop()
