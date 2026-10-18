#!/usr/bin/env bash
# Package the backend for Lambda into infra/.build/lambda: app code plus
# Linux (manylinux x86_64, Python 3.12) wheels of the production dependencies.
set -euo pipefail
cd "$(dirname "$0")/.."
out=infra/.build/lambda
rm -rf "$out" && mkdir -p "$out"

(cd backend && uv export --no-dev --no-hashes --no-emit-project --frozen) > infra/.build/requirements.txt
uv pip install --quiet --requirement infra/.build/requirements.txt --target "$out" \
  --python-platform x86_64-manylinux2014 --python-version 3.12 --only-binary :all:

rsync -a --exclude __pycache__ backend/app "$out/"
echo "Built $out ($(du -sh "$out" | cut -f1))"
