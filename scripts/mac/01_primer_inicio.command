#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker Desktop no esta instalado o docker no esta disponible."
  exit 1
fi
if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama no esta instalado."
  exit 1
fi

open -a Docker || true
launchctl setenv OLLAMA_HOST "0.0.0.0:11434"
open -a Ollama || true
chmod +x ./scripts/*.sh ./scripts/common.sh ./scripts/mac/*.command ./scripts/host/*.sh || true
./scripts/start-stack.sh
./scripts/pull-model.sh

echo "Completa .env (SQLSERVER_PASSWORD) y config/sqlserver_queries/movements.sql antes de correr ./scripts/ingest.sh"
open "http://localhost:3000"
open "http://localhost:3000/secure"
