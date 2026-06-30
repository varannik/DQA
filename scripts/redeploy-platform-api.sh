#!/usr/bin/env bash
# Rebuild and redeploy platform-api only (e.g. after migration/startup fix)
set -euo pipefail

ENV="${ENV:-dev}"
AWS_REGION="${AWS_REGION:-eu-west-1}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TAG="${TAG:-$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo latest)}"

export AWS_REGION
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
ECR_BASE="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE="${ECR_BASE}/datasentinel-platform-api:${TAG}"

echo "=== Redeploy platform-api (env=${ENV}, tag=${TAG}) ==="

aws ecr get-login-password --region "${AWS_REGION}" | \
  docker login --username AWS --password-stdin "${ECR_BASE}"

docker build --platform linux/amd64 -f "${ROOT}/datasentinel-platform-api/Dockerfile" -t "${IMAGE}" "${ROOT}"
docker push "${IMAGE}"

"${ROOT}/scripts/cfn-deploy.sh" \
  "datasentinel-${ENV}-platform-api" \
  "${ROOT}/datasentinel-infra/cloudformation/01-services/platform-api.yaml" \
  "${ENV}" \
  "${IMAGE}"

aws ecs update-service \
  --cluster "datasentinel-${ENV}" \
  --service "platform-api-${ENV}" \
  --force-new-deployment \
  --region "${AWS_REGION}" >/dev/null

echo "Waiting for service stable..."
aws ecs wait services-stable \
  --cluster "datasentinel-${ENV}" \
  --services "platform-api-${ENV}" \
  --region "${AWS_REGION}"

ALB_DNS="$(aws cloudformation describe-stacks \
  --stack-name "datasentinel-${ENV}-platform-api" \
  --query "Stacks[0].Outputs[?OutputKey=='LoadBalancerDns'].OutputValue" \
  --output text)"

echo ""
echo "Platform API: http://${ALB_DNS}/api/docs"
echo "Test login:"
echo "  curl -X POST http://${ALB_DNS}/api/v1/auth/token -d 'username=admin@datasentinel.io&password=admin123'"
