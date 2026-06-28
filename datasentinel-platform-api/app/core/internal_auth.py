"""Internal message signing for service-to-service job envelopes."""
from __future__ import annotations

from datasentinel_contracts.events.signing import attach_signature, verify_payload

from app.core.config import settings


def sign_envelope(envelope: dict) -> dict:
    return attach_signature(envelope, settings.INTERNAL_MESSAGE_SIGNING_KEY)


def verify_envelope(envelope: dict) -> bool:
    signature = envelope.get("signature")
    if not signature:
        return False
    payload = {k: v for k, v in envelope.items() if k != "signature"}
    return verify_payload(payload, signature, settings.INTERNAL_MESSAGE_SIGNING_KEY)
