#!/usr/bin/env python3
"""Export the Platform API OpenAPI spec to docs/openapi/."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLATFORM_API = ROOT / "datasentinel-platform-api"
CONTRACTS = ROOT / "datasentinel-contracts"
OUT_DIR = ROOT.parent / "docs" / "openapi"
OUT_FILE = OUT_DIR / "datasentinel-platform-api.openapi.json"


def main() -> int:
    os.environ.setdefault("UPLOAD_DIR", str(ROOT / "uploads"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (ROOT / "uploads").mkdir(exist_ok=True)

    sys.path[:0] = [str(PLATFORM_API), str(CONTRACTS)]

    from app.main import app  # noqa: E402

    spec = app.openapi()
    spec["info"]["contact"] = {
        "name": "DataSentinel Platform API",
    }
    spec["info"]["description"] = (
        "Public REST API for data quality assessment, violation review, "
        "corrections, and partner integrations. Authenticate with Bearer JWT "
        "from /api/v1/auth/token (users) or /api/v1/auth/client-token (M2M)."
    )
    spec["externalDocs"] = {
        "description": "Partner integration guide",
        "url": "../PARTNER_API_GUIDE.md",
    }
    spec["servers"] = [
        {"url": "http://localhost:8000", "description": "Local development"},
        {
            "url": "https://{host}",
            "description": "Deployed environment (ALB DNS or custom domain)",
            "variables": {"host": {"default": "api.example.com"}},
        },
    ]

    OUT_FILE.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    print(f"Exported {len(spec.get('paths', {}))} paths → {OUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
