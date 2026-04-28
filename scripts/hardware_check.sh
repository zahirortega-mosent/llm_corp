#!/usr/bin/env bash
set -euo pipefail

echo "== CPU =="
lscpu | egrep 'Model name|CPU\(s\)|Core|Thread|Socket' || true

echo "== RAM =="
free -h || true

echo "== PCI GPU =="
GPU_LINES="$(lspci | grep -Ei 'vga|3d|display' || true)"
printf '%s\n' "$GPU_LINES"

echo "== NVIDIA =="
NVIDIA_FOUND=false
if command -v nvidia-smi >/dev/null 2>&1; then
  NVIDIA_FOUND=true
  nvidia-smi || true
fi

echo "== AMD ROCm =="
ROCM_FOUND=false
if command -v rocminfo >/dev/null 2>&1; then
  ROCM_FOUND=true
  rocminfo | head -80 || true
fi
if command -v rocm-smi >/dev/null 2>&1; then
  ROCM_FOUND=true
  rocm-smi || true
fi

echo "== Vulkan =="
VULKAN_FOUND=false
if command -v vulkaninfo >/dev/null 2>&1; then
  VULKAN_FOUND=true
  vulkaninfo --summary || true
fi

echo "== Ollama =="
ollama ps || true
journalctl -u ollama -n 120 --no-pager || true

GPU_DEDICATED_FOUND=false
GPU_BACKEND=cpu
if [ "$NVIDIA_FOUND" = "true" ]; then
  GPU_DEDICATED_FOUND=true
  GPU_BACKEND=cuda
elif [ "$ROCM_FOUND" = "true" ]; then
  GPU_DEDICATED_FOUND=true
  GPU_BACKEND=rocm
elif [ "$VULKAN_FOUND" = "true" ]; then
  GPU_BACKEND=vulkan
fi

OLLAMA_PROCESSOR=CPU
if journalctl -u ollama -n 200 --no-pager 2>/dev/null | grep -Eiq 'processor.*gpu|offloaded [1-9][0-9]*/|compute.*gpu'; then
  OLLAMA_PROCESSOR=mixed
fi
if journalctl -u ollama -n 200 --no-pager 2>/dev/null | grep -Eiq 'compute.*gpu'; then
  OLLAMA_PROCESSOR=GPU
fi

echo "== Conclusion operacional =="
echo "GPU_DEDICATED_FOUND=$GPU_DEDICATED_FOUND"
echo "GPU_BACKEND=$GPU_BACKEND"
echo "OLLAMA_PROCESSOR=$OLLAMA_PROCESSOR"
