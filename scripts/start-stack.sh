#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"
require_cmd curl
require_cmd docker
mkdir -p data/open-webui data/searxng data/input data/input/codebases data/output pgdata control/commands/pending control/commands/done
log "Levantando DB, API, UI segura interna, SearXNG, Open WebUI y gateway"
compose_cmd up --build -d
log "Esperando gateway"
wait_for_url "http://localhost:${PUBLIC_PORT}" 180 2
log "Esperando portal seguro"
wait_for_url "http://localhost:${PUBLIC_PORT}/${SECURE_UI_BASE_PATH}" 180 2
log "Esperando API vía gateway"
wait_for_url "http://localhost:${PUBLIC_PORT}/api/health" 180 2
log "Servicios arriba"
compose_cmd ps
