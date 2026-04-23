#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"
require_cmd curl
log "Validando gateway / Open WebUI"
curl -fsS "http://localhost:${PUBLIC_PORT}" >/dev/null
echo "OK - Open WebUI responde en http://localhost:${PUBLIC_PORT}"
log "Validando portal seguro"
curl -fsS "http://localhost:${PUBLIC_PORT}/${SECURE_UI_BASE_PATH}" >/dev/null
echo "OK - Portal seguro responde en http://localhost:${PUBLIC_PORT}/${SECURE_UI_BASE_PATH}"
log "Validando API vía gateway"
curl -fsS "http://localhost:${PUBLIC_PORT}/api/health" | grep -qi 'status'
echo "OK - API responde en http://localhost:${PUBLIC_PORT}/api/health"
