#!/usr/bin/env bash
# Verify AWS credentials and minimum IAM permissions before deploy-aws
set -euo pipefail

AWS_REGION="${AWS_REGION:-eu-west-1}"
export AWS_REGION

echo "=== DataSentinel AWS preflight (region=${AWS_REGION}) ==="

ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
ARN="$(aws sts get-caller-identity --query Arn --output text)"
echo "Account: ${ACCOUNT}"
echo "Identity: ${ARN}"
echo ""

FAIL=0

check() {
  local name="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    echo "  OK   ${name}"
  else
    echo "  FAIL ${name}"
    FAIL=1
  fi
}

echo "Permission checks (dry-run / read-only where possible):"

# SQS — the failure you hit
check "sqs:CreateQueue" \
  aws sqs create-queue --queue-name "datasentinel-preflight-$$" --attributes VisibilityTimeout=30

if aws sqs get-queue-url --queue-name "datasentinel-preflight-$$" >/dev/null 2>&1; then
  QURL="$(aws sqs get-queue-url --queue-name "datasentinel-preflight-$$" --query QueueUrl --output text)"
  aws sqs delete-queue --queue-url "${QURL}" >/dev/null 2>&1 || true
fi

# ECR
check "ecr:CreateRepository" \
  aws ecr create-repository --repository-name "datasentinel-preflight-$$" --image-scanning-configuration scanOnPush=false

aws ecr delete-repository --repository-name "datasentinel-preflight-$$" --force >/dev/null 2>&1 || true

# CloudFormation (template must include at least one resource)
check "cloudformation:ValidateTemplate" \
  aws cloudformation validate-template --template-body '{"AWSTemplateFormatVersion":"2010-09-09","Resources":{"PreflightProbe":{"Type":"AWS::CloudFormation::WaitConditionHandle"}}}'

# EC2 (VPC create is heavy; check describe only)
check "ec2:DescribeVpcs" aws ec2 describe-vpcs --max-results 5

# Secrets Manager
check "secretsmanager:CreateSecret" \
  aws secretsmanager create-secret --name "datasentinel/preflight/$$" --secret-string "test"

aws secretsmanager delete-secret --secret-id "datasentinel/preflight/$$" --force-delete-without-recovery >/dev/null 2>&1 || true

echo ""
if [ "${FAIL}" -ne 0 ]; then
  echo "Preflight FAILED — your IAM user/role is missing permissions."
  echo ""
  echo "Attach the policy in datasentinel-infra/iam/datasentinel-deploy-policy.json"
  echo "to your user (or ask your AWS admin), then re-run:"
  echo "  make deploy-aws ENV=dev"
  echo ""
  echo "If a previous stack is stuck in ROLLBACK_FAILED, clean up first:"
  echo "  ./scripts/cleanup-failed-stack.sh datasentinel-dev-foundation"
  exit 1
fi

echo "Preflight passed. Safe to run: make deploy-aws ENV=dev"
