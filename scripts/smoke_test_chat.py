#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys

import requests


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test contra /auth/login y /chat")
    parser.add_argument("--base-url", default=os.getenv("CORP_API_URL", "http://localhost:8000"))
    parser.add_argument("--username", default=os.getenv("ADMIN_USERNAME", "admin"))
    parser.add_argument("--password", default=os.getenv("ADMIN_PASSWORD", "Admin123!"))
    parser.add_argument("--question", default="cuantos movimientos hubo en enero 2025")
    parser.add_argument("--debug", action="store_true", help="Envia options.debug=true y espera context en la respuesta")
    parser.add_argument("--assert-no-context", action="store_true", help="Falla si /chat publica context sin debug")
    args = parser.parse_args()

    login = requests.post(
        f"{args.base_url.rstrip('/')}/auth/login",
        json={"username": args.username, "password": args.password},
        timeout=20,
    )
    login.raise_for_status()
    token = login.json()["access_token"]

    options = {"max_rows": 10}
    if args.debug:
        options["debug"] = True

    chat = requests.post(
        f"{args.base_url.rstrip('/')}/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": args.question, "conversation_id": "smoke-bloque-1-cleanup", "options": options},
        timeout=60,
    )
    chat.raise_for_status()
    payload = chat.json()
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))

    question_norm = args.question.lower()
    if payload.get("used_llm") is True and "cuantos movimientos" in question_norm:
        print("ERROR: una pregunta de conteo exacto uso LLM", file=sys.stderr)
        return 2
    if args.assert_no_context and "context" in payload:
        print("ERROR: /chat publico context sin debug=true", file=sys.stderr)
        return 3
    if args.debug and "context" not in payload:
        print("ERROR: /chat no publico context con debug=true", file=sys.stderr)
        return 4
    if "accounts_sample" in json.dumps(payload.get("metadata", {}), ensure_ascii=False):
        print("ERROR: metadata publica contiene accounts_sample", file=sys.stderr)
        return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
