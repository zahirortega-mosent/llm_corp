#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"
log "Ejecutando probe de SQL Server"
compose_cmd exec api python /app/etl/sqlserver_probe.py
