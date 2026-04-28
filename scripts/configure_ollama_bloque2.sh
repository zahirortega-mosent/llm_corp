#!/usr/bin/env bash
set -euo pipefail

DROPIN_DIR=/etc/systemd/system/ollama.service.d
DROPIN_FILE="$DROPIN_DIR/10-llm-corp-bloque2.conf"

sudo mkdir -p "$DROPIN_DIR"
sudo tee "$DROPIN_FILE" >/dev/null <<'EOF'
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
Environment="OLLAMA_NUM_PARALLEL=2"
Environment="OLLAMA_MAX_LOADED_MODELS=2"
Environment="OLLAMA_CONTEXT_LENGTH=8192"
Environment="OLLAMA_KEEP_ALIVE=30m"
Environment="OLLAMA_FLASH_ATTENTION=1"
EOF

sudo systemctl daemon-reload
sudo systemctl restart ollama
systemctl show ollama --property=Environment --no-pager
