#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"
log "Ejecutando ETL e ingestión"
compose_cmd exec api python /app/etl/run_all.py
log "Ingestión terminada"
