import hmac
import hashlib
import json
from typing import Any


def canonical_json(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def sign_payload(payload: dict, secret: str) -> str:
    body = canonical_json(payload).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def verify_payload(payload: dict, signature: str, secret: str) -> bool:
    expected = sign_payload(payload, secret)
    return hmac.compare_digest(expected, signature)


def attach_signature(envelope: dict, secret: str) -> dict:
    payload = {k: v for k, v in envelope.items() if k != "signature"}
    envelope = dict(envelope)
    envelope["signature"] = sign_payload(payload, secret)
    return envelope
