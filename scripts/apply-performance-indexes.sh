#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose exec -T db psql -U "${POSTGRES_USER:-conciliador}" -d "${POSTGRES_DB:-conciliador_mvp}" < db/migrations/003_performance_indexes.sql
