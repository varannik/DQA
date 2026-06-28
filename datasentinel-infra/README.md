# DataSentinel — AWS Infrastructure

Production-ready CloudFormation for the full platform stack.

## What gets deployed

| Stack | Resources |
|-------|-----------|
| `datasentinel-{env}-foundation` | VPC (2 AZ), NAT, S3 gateway endpoint, RDS PostgreSQL 15, S3 buckets, SQS queues + DLQs, Secrets Manager, ECR repos, ECS cluster |
| `datasentinel-{env}-platform-api` | ALB (HTTP:80), ECS Fargate service, IAM roles |
| `datasentinel-{env}-dqa-engine` | DQA worker (SQS consumer) |
| `datasentinel-{env}-correction-engine` | Correction worker |
| `datasentinel-{env}-ai-engine` | AI worker |

Estimated **dev** cost: ~$45–70/month (RDS db.t3.micro, NAT gateway, Fargate tasks).

## Prerequisites

1. **AWS CLI** configured (`aws sts get-caller-identity` works)
2. **Docker** running locally (images built and pushed to ECR)
3. **IAM permissions** — your user/role must allow CloudFormation, EC2, RDS, S3, **SQS**, **ECR**, ECS, ELB, Secrets Manager, Logs, and IAM role creation.

Your deploy failed if you see errors like:
```
not authorized to perform: sqs:CreateQueue
not authorized to perform: ecr:CreateRepository
```

**Fix:** attach the policy in [`iam/datasentinel-deploy-policy.json`](./iam/datasentinel-deploy-policy.json) to your IAM user (or ask your AWS admin):

```bash
# As admin — create and attach policy (once)
aws iam create-policy \
  --policy-name DataSentinelDeploy \
  --policy-document file://datasentinel-infra/iam/datasentinel-deploy-policy.json

aws iam attach-user-policy \
  --user-name YOUR_USER \
  --policy-arn arn:aws:iam::625239230739:policy/DataSentinelDeploy
```

Verify before deploying:

```bash
make preflight ENV=dev
```

### Clean up a failed stack

If a deploy rolled back and the stack is stuck in `ROLLBACK_FAILED`:

```bash
make cleanup-stack ENV=dev
# attach IAM policy if delete fails, then retry cleanup-stack
```

## One-command deploy

From the `DQA/` monorepo root:

```bash
make deploy-aws ENV=dev AWS_REGION=eu-west-1
```

This runs `scripts/deploy-aws.sh` which:

1. Deploys the foundation stack (~15–20 min for RDS)
2. Builds and pushes all four service images to ECR
3. Deploys ECS service stacks with the ALB

When complete, the script prints the Platform API URL:

```
Platform API:  http://ds-api-dev-XXXX.eu-west-1.elb.amazonaws.com/api/docs
```

Default login: `admin@datasentinel.io` / `admin123`

## Step-by-step (manual)

```bash
# 1. Foundation only
make deploy-infra ENV=dev

# 2. Full deploy (foundation + services)
make deploy-aws ENV=dev
```

## Configuration

| Parameter | dev default | prod recommendation |
|-----------|-------------|----------------------|
| `DbInstanceClass` | db.t3.micro | db.t3.small+ |
| `EnableMultiAz` | false | true |
| ECS `DesiredCount` | 1 per service | 2+ for platform-api |

Override foundation parameters:

```bash
./scripts/cfn-deploy.sh datasentinel-dev-foundation \
  datasentinel-infra/cloudformation/00-foundation/foundation-main.yaml dev \
  "ParameterKey=DbInstanceClass,ParameterValue=db.t3.small"
```

## Operations

```bash
# Tail Platform API logs
aws logs tail /ecs/datasentinel-platform-api-dev --follow

# Force new deployment after code change
TAG=$(git rev-parse --short HEAD) make deploy-aws ENV=dev

# List running services
aws ecs list-services --cluster datasentinel-dev
```

## Stack layout

```
cloudformation/
├── 00-foundation/
│   └── foundation-main.yaml    # Single deployable template (no S3 nested stacks)
├── 01-services/
│   ├── platform-api.yaml
│   ├── dqa-engine.yaml
│   ├── correction-engine.yaml
│   └── ai-engine.yaml
└── parameters/
    └── dev.json
```

## Notes

- Platform API runs with `DQA_EXECUTION_MODE=sqs` and `CORRECTION_EXECUTION_MODE=sqs` in AWS.
- DB migrations run automatically on platform-api startup (`app/core/migrations.py`).
- Secrets (JWT, signing key, DB password) are auto-generated in Secrets Manager.
- HTTPS: add an ACM certificate and HTTPS listener to `platform-api.yaml` for production.
