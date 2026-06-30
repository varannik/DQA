# DataSentinel Platform (monorepo)

Implementation of [PLATFORM_MIGRATION_GUIDE.md](./PLATFORM_MIGRATION_GUIDE.md).

## Deploy to AWS (recommended)

```bash
# Requires: AWS CLI, Docker, configured credentials
make deploy-aws ENV=dev AWS_REGION=eu-west-1
```

See [datasentinel-infra/README.md](./datasentinel-infra/README.md) for full details, cost estimates, and operations.

## Layout

| Directory | Role |
|-----------|------|
| `datasentinel-contracts/` | Shared event/schema package |
| `datasentinel-platform-api/` | Public REST API + orchestration |
| `datasentinel-dqa-engine/` | DQA SQS worker |
| `datasentinel-correction-engine/` | Rule-based correction worker |
| `datasentinel-ai-engine/` | ML worker (S3 model registry) |
| `datasentinel-infra/` | CloudFormation (VPC, RDS, ECS, ALB, SQS, S3) |
| `scripts/deploy-aws.sh` | Full-stack deploy orchestration |

Legacy monolith (Phase 0): `../backend/`

## Local development

```bash
cd datasentinel-platform-api
cp .env.example .env
pip install -r requirements.txt ../datasentinel-contracts
uvicorn app.main:app --reload --port 8000
```

Set `DQA_EXECUTION_MODE=sqs` and configure SQS/S3 URLs to use distributed workers locally (e.g. LocalStack).

## Partner API documentation

Share these with integrators:

| Document | Purpose |
|----------|---------|
| [`../docs/PARTNER_API_GUIDE.md`](../docs/PARTNER_API_GUIDE.md) | Integration guide (auth, webhooks, workflows) |
| [`../docs/ADMIN_UI_MIGRATION.md`](../docs/ADMIN_UI_MIGRATION.md) | Legacy admin UI → DQA platform API |
| [`../datasentinel-admin-ui/`](../datasentinel-admin-ui/) | **Admin UI** (production-ready, AWS deploy) |
| [`../docs/DATASENTINEL_INTEGRATION.md`](../docs/DATASENTINEL_INTEGRATION.md) | Full UI integration pack (partner UIs) |
| [`../docs/partner-api-guide.adoc`](../docs/partner-api-guide.adoc) | AsciiDoc version (export to PDF/HTML) |
| [`../docs/openapi/datasentinel-platform-api.openapi.json`](../docs/openapi/datasentinel-platform-api.openapi.json) | OpenAPI 3.1 contract |

Regenerate the OpenAPI file after API changes:

```bash
make export-openapi
```

Live interactive docs when the API is running: `/api/docs`, `/api/redoc`, `/openapi.json`.

## Makefile targets

| Command | Description |
|---------|-------------|
| `make deploy-aws` | Full AWS stack (foundation + ECR + ECS) |
| `make deploy-infra` | Foundation stack only |
| `make build` | Build Docker images locally |
| `make test` | Run contract unit tests |
| `make export-openapi` | Regenerate OpenAPI spec in `docs/openapi/` |
