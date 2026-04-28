#!/usr/bin/env bash
set -euo pipefail

python -m pytest tests/test_filters_dates.py tests/test_router_direct.py tests/test_query_routes.py -q
