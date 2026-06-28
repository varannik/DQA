"""Dataset storage — local filesystem or S3."""
from __future__ import annotations

import io
import os
from typing import Optional, Protocol
from urllib.parse import urlparse

import pandas as pd

from app.core.config import settings


class DatasetStore(Protocol):
    def load_df(self, uri: str) -> pd.DataFrame: ...
    def save_bytes(self, uri: str, data: bytes) -> None: ...
    def resolve_uri(self, dataset) -> str: ...
    def build_dataset_uri(self, tenant_id: str, dataset_id: str, ext: str) -> str: ...


class LocalDatasetStore:
    def load_df(self, uri: str) -> pd.DataFrame:
        if not uri or not os.path.exists(uri):
            raise FileNotFoundError(f"File not found: {uri}")
        ext = os.path.splitext(uri)[1].lower()
        if ext == ".csv":
            return pd.read_csv(uri)
        return pd.read_excel(uri)

    def save_bytes(self, uri: str, data: bytes) -> None:
        directory = os.path.dirname(uri)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(uri, "wb") as f:
            f.write(data)

    def resolve_uri(self, dataset) -> str:
        return getattr(dataset, "s3_uri", None) or dataset.storage_path

    def build_dataset_uri(self, tenant_id: str, dataset_id: str, ext: str) -> str:
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        return os.path.join(settings.UPLOAD_DIR, f"{dataset_id}{ext}")


class S3DatasetStore:
    def __init__(self, bucket: str, region: str):
        import boto3

        self.bucket = bucket
        self._client = boto3.client("s3", region_name=region)

    def _parse_s3(self, uri: str) -> tuple[str, str]:
        parsed = urlparse(uri)
        if parsed.scheme != "s3":
            raise ValueError(f"Expected s3:// URI, got {uri}")
        return parsed.netloc, parsed.path.lstrip("/")

    def load_df(self, uri: str) -> pd.DataFrame:
        bucket, key = self._parse_s3(uri)
        obj = self._client.get_object(Bucket=bucket, Key=key)
        body = obj["Body"].read()
        ext = os.path.splitext(key)[1].lower()
        buf = io.BytesIO(body)
        if ext == ".csv":
            return pd.read_csv(buf)
        return pd.read_excel(buf)

    def save_bytes(self, uri: str, data: bytes) -> None:
        bucket, key = self._parse_s3(uri)
        self._client.put_object(Bucket=bucket, Key=key, Body=data)

    def resolve_uri(self, dataset) -> str:
        return getattr(dataset, "s3_uri", None) or dataset.storage_path

    def build_dataset_uri(self, tenant_id: str, dataset_id: str, ext: str) -> str:
        key = f"tenants/{tenant_id}/datasets/{dataset_id}/original{ext}"
        return f"s3://{self.bucket}/{key}"

    def load_json(self, uri: str) -> dict:
        import json

        bucket, key = self._parse_s3(uri)
        obj = self._client.get_object(Bucket=bucket, Key=key)
        return json.loads(obj["Body"].read().decode("utf-8"))

    def save_json(self, uri: str, payload: dict) -> None:
        import json

        bucket, key = self._parse_s3(uri)
        self._client.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(payload).encode("utf-8"),
            ContentType="application/json",
        )


_store: Optional[DatasetStore] = None


def get_dataset_store() -> DatasetStore:
    global _store
    if _store is None:
        if settings.S3_DATASETS_BUCKET:
            _store = S3DatasetStore(settings.S3_DATASETS_BUCKET, settings.AWS_REGION)
        else:
            _store = LocalDatasetStore()
    return _store
