#!/usr/bin/env bash
# Run the cloud sender once now instead of waiting for the schedule, and print its result.
set -euo pipefail
name=$(aws cloudformation describe-stacks --stack-name colder-mailer \
  --query "Stacks[0].Outputs[?OutputKey=='SenderFunctionName'].OutputValue" --output text)
aws lambda invoke --function-name "$name" /dev/stdout --query StatusCode --output text
