#!/usr/bin/env bash
# Deploy full DataSentinel stack to AWS: foundation → ECR images → ECS services
set -euo pipefail

ENV="${ENV:-dev}"
AWS_REGION="${AWS_REGION:-eu-west-1}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TAG="${TAG:-$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo latest)}"
SKIP_FOUNDATION="${SKIP_FOUNDATION:-false}"

export AWS_REGION

echo "=== DataSentinel AWS deploy (env=${ENV}, region=${AWS_REGION}, tag=${TAG}) ==="

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
ECR_BASE="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo "Account: ${ACCOUNT_ID}"

if [ "${SKIP_FOUNDATION}" != "true" ]; then
  echo ""
  echo "=== Step 1/3: Foundation stack (VPC, RDS, SQS, S3, ECR, ECS cluster) ==="
  echo "This takes ~15–20 minutes (RDS provisioning)."
  "${ROOT}/scripts/cfn-deploy.sh" \
    "datasentinel-${ENV}-foundation" \
    "${ROOT}/datasentinel-infra/cloudformation/00-foundation/foundation-main.yaml" \
    "${ENV}"
else
  echo ""
  echo "=== Skipping foundation (SKIP_FOUNDATION=true) ==="
fi

echo ""
echo "=== Step 2/3: Build and push Docker images to ECR ==="
aws ecr get-login-password --region "${AWS_REGION}" | \
  docker login --username AWS --password-stdin "${ECR_BASE}"

build_push() {
  local svc="$1"
  local dockerfile="$2"
  local image="${ECR_BASE}/datasentinel-${svc}:${TAG}"
  echo "Building ${svc} → ${image}" >&2
  docker build --platform linux/amd64 -f "${ROOT}/${dockerfile}" -t "${image}" "${ROOT}" >&2
  docker push "${image}" >&2
  echo "${image}"
}

IMAGE_PLATFORM_API="$(build_push platform-api datasentinel-platform-api/Dockerfile)"
IMAGE_DQA="$(build_push dqa-engine datasentinel-dqa-engine/Dockerfile)"
IMAGE_CORRECTION="$(build_push correction-engine datasentinel-correction-engine/Dockerfile)"
IMAGE_AI="$(build_push ai-engine datasentinel-ai-engine/Dockerfile)"

echo ""
echo "=== Step 3/3: ECS service stacks ==="

deploy_service_stack() {
  local svc="$1"
  local template="$2"
  local image="$3"
  local stack="datasentinel-${ENV}-${svc}"
  echo "Deploying ${stack}..."
  "${ROOT}/scripts/cfn-deploy.sh" \
    "${stack}" \
    "${ROOT}/datasentinel-infra/cloudformation/01-services/${template}" \
    "${ENV}" \
    "${image}"
}

deploy_service_stack platform-api platform-api.yaml "${IMAGE_PLATFORM_API}"
deploy_service_stack dqa-engine dqa-engine.yaml "${IMAGE_DQA}"
deploy_service_stack correction-engine correction-engine.yaml "${IMAGE_CORRECTION}"
deploy_service_stack ai-engine ai-engine.yaml "${IMAGE_AI}"

echo ""
echo "=== Deploy complete ==="
ALB_DNS="$(aws cloudformation describe-stacks \
  --stack-name "datasentinel-${ENV}-platform-api" \
  --query "Stacks[0].Outputs[?OutputKey=='LoadBalancerDns'].OutputValue" \
  --output text 2>/dev/null || echo "")"

if [ -n "${ALB_DNS}" ] && [ "${ALB_DNS}" != "None" ]; then
  echo ""
  echo "Platform API:  http://${ALB_DNS}/api/docs"
  echo "Health check:  http://${ALB_DNS}/api/health"
  echo "Login:         POST http://${ALB_DNS}/api/v1/auth/token"
  echo "               user: admin@datasentinel.io  password: admin123"
fi

echo ""
echo "Useful commands:"
echo "  aws logs tail /ecs/datasentinel-platform-api-${ENV} --follow"
echo "  aws ecs list-services --cluster datasentinel-${ENV}"
