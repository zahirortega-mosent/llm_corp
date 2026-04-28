FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ARG INSTALL_DEV=false
COPY api/requirements.txt /app/requirements.txt
COPY api/requirements-dev.txt /app/requirements-dev.txt
RUN pip install --upgrade pip setuptools wheel \
    && if [ "$INSTALL_DEV" = "true" ]; then \
        pip install -r /app/requirements-dev.txt; \
    else \
        pip install -r /app/requirements.txt; \
    fi

COPY api/app /app/app
COPY etl /app/etl
COPY db /app/db
COPY docs /app/docs
COPY config /app/config
COPY scripts /app/scripts
COPY tests /app/tests

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
