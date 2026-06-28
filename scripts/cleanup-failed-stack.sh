#!/usr/bin/env bash
# Remove a stuck CloudFormation stack (e.g. ROLLBACK_FAILED after IAM errors)
set -euo pipefail

STACK_NAME="${1:-datasentinel-dev-foundation}"
AWS_REGION="${AWS_REGION:-eu-west-1}"
export AWS_REGION

echo "Cleaning up stack: ${STACK_NAME} (region=${AWS_REGION})"

STATUS="$(aws cloudformation describe-stacks --stack-name "${STACK_NAME}" \
  --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo NOT_FOUND)"

if [ "${STATUS}" = "NOT_FOUND" ]; then
  echo "Stack not found — nothing to do."
  exit 0
fi

echo "Current status: ${STATUS}"

if [ "${STATUS}" = "ROLLBACK_FAILED" ]; then
  echo "Attempting to skip stuck resources and complete rollback..."
  aws cloudformation continue-update-rollback \
    --stack-name "${STACK_NAME}" \
    --resources-to-skip InternetGateway VPC 2>/dev/null || true
  sleep 5
fi

echo "Deleting stack..."
aws cloudformation delete-stack --stack-name "${STACK_NAME}" 2>/dev/null || true

echo "Waiting for delete (may fail if IAM still lacks ec2:DeleteVpc)..."
if aws cloudformation wait stack-delete-complete --stack-name "${STACK_NAME}" 2>/dev/null; then
  echo "Stack deleted."
  exit 0
fi

echo ""
echo "Delete did not complete. Orphan resources may remain:"
aws cloudformation describe-stack-resources --stack-name "${STACK_NAME}" \
  --query 'StackResources[?ResourceStatus!=`DELETE_COMPLETE`].[LogicalResourceId,PhysicalResourceId,ResourceStatus]' \
  --output table 2>/dev/null || true

echo ""
echo "Manual cleanup (requires ec2:DeleteVpc / ec2:DeleteInternetGateway):"
echo "  1. Detach and delete Internet Gateway from the VPC"
echo "  2. Delete the VPC"
echo "  3. Re-run: aws cloudformation delete-stack --stack-name ${STACK_NAME}"
echo ""
echo "Or attach datasentinel-infra/iam/datasentinel-deploy-policy.json and retry delete."
