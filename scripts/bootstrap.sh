#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="${1:-$(pwd)}"
cd "$PROJECT_DIR"
chmod +x scripts/*.sh scripts/common.sh scripts/host/*.sh || true
bash ./scripts/start-stack.sh
bash ./scripts/pull-model.sh
bash ./scripts/ingest.sh
bash ./scripts/test-stack.sh
