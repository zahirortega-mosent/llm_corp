#!/usr/bin/env python3
import json
import os
import platform
import subprocess
import time
from pathlib import Path
from urllib import request

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PENDING_DIR = PROJECT_ROOT / "control" / "commands" / "pending"
DONE_DIR = PROJECT_ROOT / "control" / "commands" / "done"
DONE_DIR.mkdir(parents=True, exist_ok=True)


def load_env() -> dict[str, str]:
    env = {}
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.strip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    return env


def mac_wifi_device() -> str:
    output = subprocess.check_output(["networksetup", "-listallhardwareports"], text=True)
    current_device = None
    is_wifi = False
    for line in output.splitlines():
        if line.startswith("Hardware Port:"):
            is_wifi = "Wi-Fi" in line or "AirPort" in line
        elif line.startswith("Device:") and is_wifi:
            current_device = line.split(":", 1)[1].strip()
            break
    if not current_device:
        raise RuntimeError("No se encontró dispositivo Wi-Fi en macOS")
    return current_device


def execute_wifi_power(state: str) -> str:
    system = platform.system().lower()
    state = state.lower()
    if state not in {"on", "off"}:
        raise RuntimeError(f"Estado Wi-Fi no soportado: {state}")
    if "darwin" in system:
        device = mac_wifi_device()
        subprocess.check_call(["networksetup", "-setairportpower", device, state])
        return f"Wi-Fi macOS {state} en {device}"
    if "linux" in system:
        subprocess.check_call(["nmcli", "radio", "wifi", state])
        return f"Wi-Fi Linux {state}"
    raise RuntimeError(f"Sistema operativo no soportado: {system}")


def report_status(env: dict[str, str], command_pk: int, status: str, message: str) -> None:
    api_url = env.get("API_BASE_URL", "http://localhost:8000").replace("http://api:8000", "http://localhost:8000")
    secret = env.get("HOST_AGENT_SECRET_KEY", "")
    if not secret:
        return
    payload = json.dumps({"status": status, "result_message": message, "executor_host": platform.node()}).encode("utf-8")
    req = request.Request(
        f"{api_url}/agent/host-commands/{command_pk}/complete",
        data=payload,
        headers={"Content-Type": "application/json", "X-Agent-Key": secret},
        method="POST",
    )
    request.urlopen(req, timeout=15).read()


def main() -> None:
    env = load_env()
    print("[guard] leyendo cola:", PENDING_DIR)
    while True:
        for path in sorted(PENDING_DIR.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                command_pk = int(payload["command_pk"])
                command_type = payload["command_type"]
                command_payload = payload.get("command_payload") or {}
                if command_type == "wifi_power":
                    result = execute_wifi_power(str(command_payload.get("state", "off")))
                else:
                    raise RuntimeError(f"Tipo de comando no soportado: {command_type}")
                payload["execution_status"] = "done"
                payload["result_message"] = result
                report_status(env, command_pk, "done", result)
            except Exception as exc:
                payload = locals().get("payload", {})
                payload["execution_status"] = "error"
                payload["result_message"] = str(exc)
                try:
                    report_status(env, int(payload.get("command_pk", 0)), "error", str(exc))
                except Exception:
                    pass
            finally:
                destination = DONE_DIR / path.name
                destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                path.unlink(missing_ok=True)
        time.sleep(3)


if __name__ == "__main__":
    main()
