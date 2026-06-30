"""Apply SQL migrations from migrations/ on startup (RDS first boot)."""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import text

from app.core.database import engine

logger = logging.getLogger("datasentinel.migrations")

MIGRATION_FILES = [
    "init.sql",
    "002_tenant.sql",
    "003_api_clients_webhooks.sql",
]


def run_migrations() -> None:
    migrations_dir = Path(__file__).resolve().parents[2] / "migrations"
    if not migrations_dir.exists():
        logger.warning("Migrations directory not found: %s", migrations_dir)
        return

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename VARCHAR(255) PRIMARY KEY,
                    applied_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            )
        )
        for name in MIGRATION_FILES:
            path = migrations_dir / name
            if not path.exists():
                continue
            applied = conn.execute(
                text("SELECT 1 FROM schema_migrations WHERE filename = :name"),
                {"name": name},
            ).first()
            if applied:
                logger.info("Skipping migration %s (already applied)", name)
                continue
            sql = path.read_text(encoding="utf-8")
            logger.info("Applying migration %s", name)
            for statement in _split_statements(sql):
                if statement.strip():
                    conn.execute(text(statement))
            conn.execute(
                text("INSERT INTO schema_migrations (filename) VALUES (:name)"),
                {"name": name},
            )
    logger.info("Database migrations complete")


def _split_statements(sql: str) -> list[str]:
    statements = []
    current = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        current.append(line)
        if stripped.endswith(";"):
            statements.append("\n".join(current))
            current = []
    if current:
        statements.append("\n".join(current))
    return statements
