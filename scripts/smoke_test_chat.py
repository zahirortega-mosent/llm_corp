#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys

import requests


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test de /auth/login y /chat")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--question", required=True)
    args = parser.parse_args()

    login = requests.post(
        f"{args.base_url.rstrip('/')}/auth/login",
        json={"username": args.username, "password": args.password},
        timeout=30,
    )
    login.raise_for_status()
    token = login.json()["access_token"]
    chat = requests.post(
        f"{args.base_url.rstrip('/')}/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": args.question, "conversation_id": "smoke-bloque4", "options": {"debug": False}},
        timeout=120,
    )
    chat.raise_for_status()
    payload = chat.json()
    print(json.dumps({"route": payload.get("route"), "used_memory": payload.get("used_memory"), "answer": payload.get("answer")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
