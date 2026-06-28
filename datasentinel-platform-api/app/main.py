import logging
from fastapi import FastAPI
from app.core.logging_config import setup_logging, logger
setup_logging()
from fastapi.middleware.cors import CORSMiddleware
import os

from app.api.v1 import (
    auth, projects, datasets, rules, runs, violations, corrections, ai_engine, audit, webhooks
)

from app.core.config import settings

app = FastAPI(
    title="DataSentinel Platform API",
    description="Data Quality Assessment & Error Correction Platform API",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

@app.on_event("startup")
def on_startup():
    logger.info("DataSentinel Platform API starting up")
    from app.core.startup import create_default_admin
    create_default_admin()
    from app.workers.result_worker import start_result_worker
    start_result_worker()
    logger.info("Startup complete")

app.include_router(auth.router,        prefix="/api/v1/auth",        tags=["Auth"])
app.include_router(projects.router,    prefix="/api/v1/projects",    tags=["Projects"])
app.include_router(datasets.router,    prefix="/api/v1/datasets",    tags=["Datasets"])
app.include_router(rules.router,       prefix="/api/v1/rules",       tags=["Rules"])
app.include_router(runs.router,        prefix="/api/v1/runs",        tags=["Runs"])
app.include_router(violations.router,  prefix="/api/v1/violations",  tags=["Violations"])
app.include_router(corrections.router, prefix="/api/v1/corrections", tags=["Corrections"])
app.include_router(ai_engine.router,   prefix="/api/v1/ai",          tags=["AI Engine"])
app.include_router(audit.router,       prefix="/api/v1/audit",       tags=["Audit"])
app.include_router(webhooks.router,    prefix="/api/v1/webhooks",    tags=["Webhooks"])

@app.get("/api/health")
def health():
    from app.core.config import settings
    return {
        "status": "ok",
        "service": "DataSentinel Platform API",
        "environment": settings.ENVIRONMENT,
        "dqa_execution_mode": settings.DQA_EXECUTION_MODE,
    }
