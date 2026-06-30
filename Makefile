ENV ?= dev
AWS_REGION ?= eu-west-1
TAG ?= latest
STACK_PREFIX = datasentinel-$(ENV)
SERVICES = platform-api dqa-engine correction-engine ai-engine

.PHONY: help test build deploy-infra deploy-services deploy-aws deploy-admin-ui preflight cleanup-stack destroy-aws export-openapi

help:
	@echo "DataSentinel Platform — AWS deployment"
	@echo ""
	@echo "  make preflight ENV=dev       Check AWS credentials + IAM permissions"
	@echo "  make deploy-aws ENV=dev     Full stack: foundation + images + ECS services"
	@echo "  make deploy-admin-ui ENV=dev  Deploy admin UI (requires platform-api stack)"
	@echo "  make deploy-infra ENV=dev   Foundation only (VPC, RDS, SQS, S3, ECR)"
	@echo "  make deploy-services ENV=dev  ECS services only (requires images in ECR)"
	@echo "  make cleanup-stack ENV=dev   Remove failed/stuck foundation stack"
	@echo "  make build ENV=dev TAG=abc  Build Docker images locally"
	@echo "  make test                   Run contract unit tests"
	@echo "  make export-openapi         Regenerate docs/openapi/*.openapi.json"
	@echo ""
	@echo "Prerequisites: AWS CLI configured, Docker running, IAM policy attached (see datasentinel-infra/iam/)"

preflight:
	@./scripts/aws-preflight.sh

cleanup-stack:
	@./scripts/cleanup-failed-stack.sh datasentinel-$(ENV)-foundation

test:
	@cd datasentinel-contracts && python3 -m pip install . pytest pydantic -q && python3 -m pytest -q

export-openapi:
	@python3 scripts/export-openapi.py

build:
	@for s in $(SERVICES); do \
	  echo "Building datasentinel-$$s:$(TAG)..."; \
	  docker build --platform linux/amd64 -f datasentinel-$$s/Dockerfile -t datasentinel-$$s:$(TAG) . ; \
	done

deploy-infra:
	@./scripts/cfn-deploy.sh $(STACK_PREFIX)-foundation \
	  datasentinel-infra/cloudformation/00-foundation/foundation-main.yaml $(ENV)

deploy-services:
	@SKIP_FOUNDATION=true ENV=$(ENV) AWS_REGION=$(AWS_REGION) TAG=$(TAG) ./scripts/deploy-aws.sh

deploy-aws:
	@ENV=$(ENV) AWS_REGION=$(AWS_REGION) TAG=$(TAG) ./scripts/deploy-aws.sh

deploy-admin-ui:
	@ENV=$(ENV) AWS_REGION=$(AWS_REGION) TAG=$(TAG) $(MAKE) -C ../datasentinel-admin-ui deploy-aws
