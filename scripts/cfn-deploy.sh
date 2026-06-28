#!/usr/bin/env bash
set -euo pipefail

STACK_NAME="$1"
TEMPLATE_FILE="$2"
ENV="$3"
IMAGE_URI="${4:-}"

echo "Deploying stack: ${STACK_NAME}"

aws cloudformation validate-template --template-body "file://${TEMPLATE_FILE}" > /dev/null

PARAMS=(ParameterKey=Environment,ParameterValue="${ENV}")
if [ -n "${IMAGE_URI}" ]; then
  PARAMS+=(ParameterKey=ImageUri,ParameterValue="${IMAGE_URI}")
fi

STACK_EXISTS=true
aws cloudformation describe-stacks --stack-name "${STACK_NAME}" >/dev/null 2>&1 || STACK_EXISTS=false

if [ "${STACK_EXISTS}" = "false" ]; then
  echo "Creating stack ${STACK_NAME}..."
  aws cloudformation create-stack \
    --stack-name "${STACK_NAME}" \
    --template-body "file://${TEMPLATE_FILE}" \
    --parameters "${PARAMS[@]}" \
    --capabilities CAPABILITY_NAMED_IAM
  aws cloudformation wait stack-create-complete --stack-name "${STACK_NAME}"
else
  CHANGE_SET="cs-$(date +%s)"
  aws cloudformation create-change-set \
    --stack-name "${STACK_NAME}" \
    --template-body "file://${TEMPLATE_FILE}" \
    --parameters "${PARAMS[@]}" \
    --capabilities CAPABILITY_NAMED_IAM \
    --change-set-name "${CHANGE_SET}"
  aws cloudformation wait change-set-create-complete --stack-name "${STACK_NAME}" --change-set-name "${CHANGE_SET}"
  CHANGES=$(aws cloudformation describe-change-set \
    --stack-name "${STACK_NAME}" \
    --change-set-name "${CHANGE_SET}" \
    --query "Changes" --output json)
  if [ "${CHANGES}" = "[]" ] || [ "${CHANGES}" = "null" ]; then
    aws cloudformation delete-change-set --stack-name "${STACK_NAME}" --change-set-name "${CHANGE_SET}"
    echo "Stack up-to-date: ${STACK_NAME}"
  else
    aws cloudformation execute-change-set --stack-name "${STACK_NAME}" --change-set-name "${CHANGE_SET}"
    aws cloudformation wait stack-update-complete --stack-name "${STACK_NAME}"
    echo "Stack updated: ${STACK_NAME}"
  fi
fi

echo "Done: ${STACK_NAME}"
