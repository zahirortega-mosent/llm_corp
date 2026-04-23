#!/usr/bin/env sh
set -eu
BASE_PATH="${STREAMLIT_BASE_PATH:-secure}"
exec streamlit run /app/app.py   --server.address=0.0.0.0   --server.port=8501   --server.baseUrlPath="$BASE_PATH"   --browser.gatherUsageStats=false
