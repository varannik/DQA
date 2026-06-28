import logging
import os
import boto3
from app.consumer import process_message

logging.basicConfig(level=logging.INFO)


def poll_queues():
    sqs = boto3.client("sqs", region_name=os.environ.get("AWS_REGION", "eu-west-1"))
    queues = [os.environ.get("SQS_PREDICT_URL", ""), os.environ.get("SQS_TRAINING_URL", "")]
    while True:
        for queue_url in filter(None, queues):
            resp = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=20, VisibilityTimeout=900)
            for msg in resp.get("Messages", []):
                try:
                    process_message(msg["Body"])
                    sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=msg["ReceiptHandle"])
                except Exception:
                    logging.exception("AI job failed")


if __name__ == "__main__":
    poll_queues()
