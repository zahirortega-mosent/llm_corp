#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

chmod +x ./scripts/*.sh ./scripts/common.sh ./scripts/host/*.sh || true
./scripts/start-stack.sh
./scripts/pull-model.sh

echo "Completa .env (SQLSERVER_PASSWORD) y config/sqlserver_queries/movements.sql antes de correr ./scripts/ingest.sh"
echo "Open WebUI: http://localhost:3000 | Portal seguro: http://localhost:3000/secure"
