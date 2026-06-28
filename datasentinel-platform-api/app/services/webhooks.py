import hashlib
import hmac
import json
import logging
from typing import Any, Dict

import httpx

from app.core.config import settings
from app.models import Webhook

logger = logging.getLogger("datasentinel.webhooks")


def sign_webhook_payload(payload: dict, secret: str) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def dispatch_webhooks(db, tenant_id, event: str, payload: Dict[str, Any]) -> None:
    hooks = (
        db.query(Webhook)
        .filter(Webhook.tenant_id == tenant_id, Webhook.is_active == True)
        .all()
    )
    for hook in hooks:
        if event not in (hook.events or []):
            continue
        signature = sign_webhook_payload(payload, hook.secret)
        try:
            httpx.post(
                hook.url,
                json=payload,
                headers={"X-DataSentinel-Signature": f"sha256={signature}"},
                timeout=10.0,
            )
        except Exception:
            logger.exception("Webhook delivery failed for %s", hook.url)
