#!/usr/bin/env bash
# Build and deploy both Lambdas and the 15-minute schedule (CloudFormation stack "colder-mailer").
set -euo pipefail
cd "$(dirname "$0")"
./build.sh
sam deploy \
  --template-file template.yaml \
  --stack-name colder-mailer \
  --resolve-s3 \
  --capabilities CAPABILITY_IAM \
  --no-fail-on-empty-changeset \
  "$@"
