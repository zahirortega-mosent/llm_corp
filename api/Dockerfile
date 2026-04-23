FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends     build-essential     curl     git     && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY api/requirements.txt /app/requirements.txt
RUN pip install --upgrade pip setuptools wheel && pip install -r /app/requirements.txt

COPY api/app /app/app
COPY etl /app/etl
COPY db /app/db
COPY docs /app/docs
COPY config /app/config

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
