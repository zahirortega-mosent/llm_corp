#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"
require_cmd ollama
MODEL="${1:-$(ollama_model_from_env)}"
log "Descargando modelo ${MODEL} en Ollama"
ollama pull "$MODEL"
