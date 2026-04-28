#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import urllib.request
from typing import Any


def post_json(url: str, token: str, payload: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.getenv("API_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--token", default=os.getenv("API_TOKEN"))
    args = parser.parse_args()
    if not args.token:
        raise SystemExit("Falta API_TOKEN o --token")
    checks = [
        ("cuantos movimientos hubo en enero 2025", False),
        ("cuantos movimientos hubo en enero 2026", False),
        ("periodos disponibles", False),
        ("movimientos por banco en enero 2026", False),
    ]
    for question, expected_llm in checks:
        payload = post_json(f"{args.base_url.rstrip('/')}/chat", args.token, {"question": question, "use_web": False, "options": {"debug": False}})
        print(json.dumps({"question": question, "route": payload.get("route"), "used_llm": payload.get("used_llm"), "answer": payload.get("answer")}, ensure_ascii=False))
        if payload.get("used_llm") != expected_llm:
            raise SystemExit(f"Ruta inesperada para {question!r}: used_llm={payload.get('used_llm')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
