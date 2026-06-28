import os
import io
import json
from urllib.parse import urlparse

import pandas as pd


def _s3():
    import boto3

    return boto3.client("s3", region_name=os.environ.get("AWS_REGION", "eu-west-1"))


def load_df(uri: str) -> pd.DataFrame:
    parsed = urlparse(uri)
    body = _s3().get_object(Bucket=parsed.netloc, Key=parsed.path.lstrip("/"))["Body"].read()
    ext = os.path.splitext(parsed.path)[1].lower()
    buf = io.BytesIO(body)
    return pd.read_csv(buf) if ext == ".csv" else pd.read_excel(buf)


def load_json(uri: str) -> dict:
    parsed = urlparse(uri)
    body = _s3().get_object(Bucket=parsed.netloc, Key=parsed.path.lstrip("/"))["Body"].read()
    return json.loads(body.decode("utf-8"))


def save_json(uri: str, payload: dict) -> None:
    parsed = urlparse(uri)
    _s3().put_object(
        Bucket=parsed.netloc,
        Key=parsed.path.lstrip("/"),
        Body=json.dumps(payload).encode("utf-8"),
        ContentType="application/json",
    )


def suggestions_uri(tenant_id: str, job_id: str) -> str:
    bucket = os.environ["S3_DATASETS_BUCKET"]
    return f"s3://{bucket}/tenants/{tenant_id}/corrections/{job_id}/suggestions.json"
