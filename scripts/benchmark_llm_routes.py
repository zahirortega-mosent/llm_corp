#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
import urllib.error
import urllib.request
from typing import Any

DEFAULT_QUESTIONS = [
    "cuantos movimientos hubo en enero 2026",
    "periodos disponibles",
    "movimientos por banco en enero 2026",
    "cuentas sugeridas a revisar en enero 2026",
    "resume riesgos principales de enero 2026",
]


def post_json(url: str, token: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=240) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark simple de rutas /chat para Bloque 1/2")
    parser.add_argument("--base-url", default=os.getenv("API_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--token", default=os.getenv("API_TOKEN"))
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--question", action="append")
    args = parser.parse_args()
    if not args.token:
        raise SystemExit("Falta API_TOKEN o --token")
    questions = args.question or DEFAULT_QUESTIONS
    rows = []
    for question in questions:
        latencies = []
        last_payload = None
        for _ in range(args.repeat):
            started = time.perf_counter()
            payload = post_json(
                f"{args.base_url.rstrip('/')}/chat",
                args.token,
                {"question": question, "use_web": False, "options": {"debug": False, "max_rows": 10}},
            )
            elapsed_ms = (time.perf_counter() - started) * 1000
            latencies.append(elapsed_ms)
            last_payload = payload
        rows.append({
            "question": question,
            "latency_ms_avg": round(statistics.mean(latencies), 1),
            "route": (last_payload or {}).get("route"),
            "used_llm": (last_payload or {}).get("used_llm"),
            "model_used": (last_payload or {}).get("model_used"),
        })
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
