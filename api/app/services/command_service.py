import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import text

from app.config import get_settings
from app.db import get_engine
from app.services.auth_service import AuthService
from app.services.policy_service import PolicyService


class CommandService:
    def __init__(self) -> None:
        self.engine = get_engine()
        self.settings = get_settings()
        self.auth_service = AuthService()
        self.policy_service = PolicyService()

    def queue_host_command(self, command_type: str, command_payload: dict[str, Any], requested_by: str) -> dict[str, Any]:
        self.policy_service.require_host_network_control_enabled()
        with self.engine.begin() as conn:
            result = conn.execute(
                text(
                    """
                    INSERT INTO host_command_queue(command_type, command_payload, requested_by)
                    VALUES (:command_type, CAST(:command_payload AS jsonb), :requested_by)
                    RETURNING command_pk, command_type, command_payload, status, requested_by, created_at
                    """
                ),
                {
                    "command_type": command_type,
                    "command_payload": json.dumps(command_payload, ensure_ascii=False),
                    "requested_by": requested_by,
                },
            ).mappings().first()
        payload = dict(result)
        queue_dir = self.settings.host_command_queue_path
        queue_dir.mkdir(parents=True, exist_ok=True)
        filename = queue_dir / f"{payload['command_pk']:06d}_{command_type}.json"
        filename.write_text(json.dumps(payload, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
        return payload

    def list_host_commands(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT command_pk, command_type, command_payload, status, requested_by,
                           result_message, created_at, executed_at, executor_host
                    FROM host_command_queue
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            ).mappings().all()
        return [dict(row) for row in rows]


    def complete_host_command(self, command_pk: int, command_status: str, result_message: str, executor_host: str | None = None) -> dict[str, Any]:
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    UPDATE host_command_queue
                    SET status = :command_status, result_message = :result_message, executed_at = NOW(), executor_host = :executor_host
                    WHERE command_pk = :command_pk
                    RETURNING command_pk, command_type, command_payload, status, requested_by, result_message, created_at, executed_at, executor_host
                    """
                ),
                {
                    "command_pk": command_pk,
                    "command_status": command_status,
                    "result_message": result_message,
                    "executor_host": executor_host,
                },
            ).mappings().first()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comando no encontrado")
        return dict(row)

    def handle_chat_command(self, user: dict[str, Any], command: str) -> dict[str, Any]:
        raw = command.strip()
        lowered = raw.lower()
        permissions = set(user.get("permissions") or [])
        if lowered in {"/help", "/ayuda"}:
            return {
                "message": (
                    "Comandos: /internet on|off, /allow-web usuario, /deny-web usuario, /wifi on|off, "
                    "/roles usuario rol1,rol2"
                )
            }
        if lowered in {"/internet on", "/internet off"}:
            if "manage_policies" not in permissions:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No puedes cambiar politicas")
            enabled = lowered.endswith("on")
            policies = self.policy_service.set_global_internet_enabled(enabled, requested_by=user["username"])
            return {"message": f"Internet global {'habilitado' if enabled else 'bloqueado'}", "policies": policies}
        if lowered.startswith("/allow-web ") or lowered.startswith("/deny-web "):
            if "manage_policies" not in permissions:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No puedes cambiar politicas")
            target = raw.split(maxsplit=1)[1].strip()
            enabled = lowered.startswith("/allow-web ")
            updated = self.auth_service.set_user_web_access(target, enabled)
            return {"message": f"Acceso web {'habilitado' if enabled else 'bloqueado'} para {target}", "user": updated}
        if lowered.startswith("/roles "):
            if "manage_roles" not in permissions and "manage_users" not in permissions:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No puedes cambiar roles")
            _, username, roles_csv = raw.split(maxsplit=2)
            role_names = [role.strip() for role in roles_csv.split(",") if role.strip()]
            updated = self.auth_service.set_user_roles(username, role_names)
            return {"message": f"Roles actualizados para {username}", "user": updated}
        if lowered in {"/wifi on", "/wifi off"}:
            if "host_network_control" not in permissions:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No puedes controlar la red del host")
            queued = self.queue_host_command(
                command_type="wifi_power",
                command_payload={"state": "on" if lowered.endswith("on") else "off", "requested_at": datetime.utcnow().isoformat()},
                requested_by=user["username"],
            )
            return {"message": f"Comando de Wi-Fi encolado: {queued['command_type']} #{queued['command_pk']}", "command": queued}
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Comando no reconocido")
