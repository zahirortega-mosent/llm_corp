#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys

import requests


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test del Bloque 1 contra /auth/login y /chat")
    parser.add_argument("--base-url", default=os.getenv("CORP_API_URL", "http://localhost:8000"))
    parser.add_argument("--username", default=os.getenv("ADMIN_USERNAME", "admin"))
    parser.add_argument("--password", default=os.getenv("ADMIN_PASSWORD", "Admin123!"))
    parser.add_argument("--question", default="cuantos movimientos hubo en enero 2025")
    args = parser.parse_args()

    login = requests.post(
        f"{args.base_url.rstrip('/')}/auth/login",
        json={"username": args.username, "password": args.password},
        timeout=20,
    )
    login.raise_for_status()
    token = login.json()["access_token"]

    chat = requests.post(
        f"{args.base_url.rstrip('/')}/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": args.question, "conversation_id": "smoke-bloque-1", "options": {"max_rows": 10}},
        timeout=60,
    )
    chat.raise_for_status()
    payload = chat.json()
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))

    if payload.get("used_llm") is True and "cuantos movimientos" in args.question.lower():
        print("ERROR: una pregunta de conteo exacto uso LLM", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
