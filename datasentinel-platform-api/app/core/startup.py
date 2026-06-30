import time
import logging
from sqlalchemy.orm import Session
logger = logging.getLogger("datasentinel.startup")
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.core.tenancy import DEFAULT_TENANT_ID, get_or_create_default_tenant

def create_default_admin():
    # Retry a few times in case DB isn't ready
    for attempt in range(5):
        db = None
        try:
            from app.core.migrations import run_migrations

            run_migrations()

            db = SessionLocal()
            from app.models import User, Project

            tenant = get_or_create_default_tenant(db)

            existing = db.query(User).filter(User.email == "admin@datasentinel.io").first()
            if not existing:
                admin = User(
                    email="admin@datasentinel.io",
                    full_name="System Admin",
                    hashed_password=hash_password("admin123"),
                    role="admin",
                    is_active=True,
                )
                db.add(admin)
                db.commit()
                logger.info("Admin user created: admin@datasentinel.io")
            else:
                existing.hashed_password = hash_password("admin123")
                db.commit()
                logger.info("Admin password reset on startup")

            proj = db.query(Project).first()
            if not proj:
                p = Project(
                    tenant_id=tenant.id,
                    name="CO₂ Sequestration — Stream 1",
                    description="Fabric-Native Platform DQA — DQA-STR1-TDD-001",
                    domain="co2_sequestration",
                    config={
                        "batch_frequency_minutes": 120,
                        "expected_rows_per_batch": 60,
                        "sla_threshold_seconds": 300,
                        "min_data_coverage": 0.85,
                        "dimension_weights": {
                            "completeness": 0.15, "integrity": 0.20,
                            "timeliness": 0.10, "uniqueness": 0.10,
                            "accuracy": 0.20, "consistency": 0.15, "relevance": 0.10
                        }
                    }
                )
                db.add(p)
                db.commit()
                logger.info("Demo project created")
            elif proj.tenant_id is None:
                proj.tenant_id = DEFAULT_TENANT_ID
                db.commit()
                logger.info("Backfilled demo project tenant_id")

            db.close()
            return  # success

        except Exception as e:
            logger.warning("Startup attempt %s failed: %s", attempt + 1, e, exc_info=True)
            if db is not None:
                try:
                    db.close()
                except Exception:
                    pass
            time.sleep(2)

    logger.error("Could not initialise default admin after 5 attempts")
