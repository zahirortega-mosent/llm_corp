#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../.."
echo "Ejecuta este agente con permisos de administrador cuando quieras aceptar comandos /wifi on|off desde el panel."
sudo python3 ./scripts/host/network_guard.py
