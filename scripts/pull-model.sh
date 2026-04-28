#!/usr/bin/env bash
set -euo pipefail

ollama pull qwen3:4b
ollama pull qwen3:14b
ollama pull qwen3-embedding:0.6b
ollama list
