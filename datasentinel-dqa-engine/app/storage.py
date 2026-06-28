import os
import io
import json
import logging
from urllib.parse import urlparse

import pandas as pd

logger = logging.getLogger("dqa-engine.storage")


def _client():
    import boto3

    return boto3.client("s3", region_name=os.environ.get("AWS_REGION", "eu-west-1"))


def parse_s3(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    return parsed.netloc, parsed.path.lstrip("/")


def load_df(uri: str) -> pd.DataFrame:
    bucket, key = parse_s3(uri)
    body = _client().get_object(Bucket=bucket, Key=key)["Body"].read()
    ext = os.path.splitext(key)[1].lower()
    buf = io.BytesIO(body)
    if ext == ".csv":
        return pd.read_csv(buf)
    return pd.read_excel(buf)


def save_json(uri: str, payload: dict) -> None:
    bucket, key = parse_s3(uri)
    _client().put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(payload).encode("utf-8"),
        ContentType="application/json",
    )


def violations_uri(tenant_id: str, run_id: str) -> str:
    bucket = os.environ["S3_DATASETS_BUCKET"]
    return f"s3://{bucket}/tenants/{tenant_id}/runs/{run_id}/violations.json"
