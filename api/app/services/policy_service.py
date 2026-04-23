import json
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import text

from app.config import get_settings
from app.db import get_engine


class PolicyService:
    def __init__(self) -> None:
        self.engine = get_engine()
        self.settings = get_settings()

    def _get_setting(self, key: str, default: Any) -> Any:
        with self.engine.connect() as conn:
            value = conn.execute(
                text("SELECT setting_value FROM app_settings WHERE setting_key = :key"),
                {"key": key},
            ).scalar()
        if value is None:
            return default
        return value

    def get_policies(self) -> dict[str, Any]:
        return {
            "global_internet_enabled": bool(self._get_setting("global_internet_enabled", self.settings.global_internet_enabled)),
            "enable_host_network_control": bool(
                self._get_setting("enable_host_network_control", self.settings.enable_host_network_control)
            ),
            "internet_allowed_users_env": self.settings.env_internet_allowed_users,
            "domain_allowlist": self.settings.domain_allowlist,
        }

    def set_global_internet_enabled(self, enabled: bool, requested_by: str) -> dict[str, Any]:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO app_settings(setting_key, setting_value)
                    VALUES ('global_internet_enabled', CAST(:value AS jsonb))
                    ON CONFLICT (setting_key)
                    DO UPDATE SET setting_value = EXCLUDED.setting_value, updated_at = NOW()
                    """
                ),
                {"value": "true" if enabled else "false"},
            )
            conn.execute(
                text(
                    "INSERT INTO policy_audit(policy_type, action, payload, requested_by) VALUES (:policy_type, :action, CAST(:payload AS jsonb), :requested_by)"
                ),
                {
                    "policy_type": "internet",
                    "action": "global_toggle",
                    "payload": json.dumps({"global_internet_enabled": enabled}),
                    "requested_by": requested_by,
                },
            )
        return self.get_policies()

    def is_user_allowed_web(self, user: dict[str, Any]) -> bool:
        policies = self.get_policies()
        if not policies["global_internet_enabled"]:
            return False
        if "ask_hybrid" not in set(user.get("permissions") or []):
            return False
        if not user.get("web_access_enabled"):
            return False
        env_users = set(policies.get("internet_allowed_users_env") or [])
        return "*" in env_users or user.get("username") in env_users

    def require_host_network_control_enabled(self) -> None:
        if not self.get_policies().get("enable_host_network_control"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El control de red en host esta deshabilitado por politica",
            )
