import base64
import hashlib
import hmac
import os
import secrets
from typing import Any

from fastapi import HTTPException, status
from itsdangerous import BadSignature, BadTimeSignature, URLSafeTimedSerializer
from sqlalchemy import text

from app.config import get_settings
from app.db import get_engine


DEFAULT_ROLE_PERMISSIONS = {
    "admin": [
        "view_summary",
        "view_movements",
        "view_incidents",
        "view_knowledge",
        "view_rules",
        "ask_internal",
        "ask_hybrid",
        "manage_users",
        "manage_roles",
        "manage_policies",
        "host_network_control",
    ],
    "analyst": [
        "view_summary",
        "view_movements",
        "view_incidents",
        "view_knowledge",
        "view_rules",
        "ask_internal",
    ],
    "auditor": [
        "view_summary",
        "view_movements",
        "view_incidents",
        "view_knowledge",
        "view_rules",
        "ask_internal",
        "ask_hybrid",
    ],
    "viewer": ["view_summary"],
}

DEFAULT_ROLE_TABLE_ACCESS = {
    "admin": {
        "bank_movements": True,
        "bank_statements": True,
        "incidents": True,
        "knowledge_snippets": True,
        "business_rules": True,
        "assignments": True,
        "prompt_audit": True,
        "policy_audit": True,
    },
    "analyst": {
        "bank_movements": True,
        "bank_statements": True,
        "incidents": True,
        "knowledge_snippets": True,
        "business_rules": True,
        "assignments": True,
    },
    "auditor": {
        "bank_movements": True,
        "bank_statements": True,
        "incidents": True,
        "knowledge_snippets": True,
        "business_rules": True,
        "assignments": False,
    },
    "viewer": {
        "bank_movements": True,
        "bank_statements": True,
        "incidents": True,
        "knowledge_snippets": False,
        "business_rules": False,
        "assignments": False,
    },
}


class AuthService:
    def __init__(self) -> None:
        self.engine = get_engine()
        settings = get_settings()
        self.serializer = URLSafeTimedSerializer(settings.auth_secret_key, salt="secure-enterprise-auth")

    def _hash_password(self, password: str, salt: str | None = None) -> str:
        salt = salt or secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000)
        encoded = base64.b64encode(digest).decode("utf-8")
        return f"pbkdf2_sha256${salt}${encoded}"

    def verify_password(self, password: str, password_hash: str) -> bool:
        try:
            _, salt, expected = password_hash.split("$", maxsplit=2)
        except ValueError:
            return False
        candidate = self._hash_password(password, salt)
        return hmac.compare_digest(candidate, f"pbkdf2_sha256${salt}${expected}")

    def create_token(self, username: str) -> str:
        return self.serializer.dumps({"username": username})

    def decode_token(self, token: str) -> str:
        settings = get_settings()
        try:
            payload = self.serializer.loads(token, max_age=settings.auth_token_max_age_seconds)
        except (BadSignature, BadTimeSignature):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalido o expirado")
        username = payload.get("username")
        if not username:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token sin usuario")
        return username

    def bootstrap_security(self) -> None:
        settings = get_settings()
        with self.engine.begin() as conn:
            permissions = conn.execute(text("SELECT permission_code FROM permissions")).scalars().all()
            roles = conn.execute(text("SELECT role_name FROM roles")).scalars().all()
            for role_name, permission_codes in DEFAULT_ROLE_PERMISSIONS.items():
                if role_name not in roles:
                    conn.execute(
                        text("INSERT INTO roles(role_name, description, is_system) VALUES (:role_name, :description, TRUE)"),
                        {"role_name": role_name, "description": f"Rol del sistema: {role_name}"},
                    )
            for role_name, permission_codes in DEFAULT_ROLE_PERMISSIONS.items():
                for permission_code in permission_codes:
                    if permission_code not in permissions:
                        conn.execute(
                            text("INSERT INTO permissions(permission_code, description) VALUES (:code, :description)"),
                            {"code": permission_code, "description": permission_code},
                        )
                    conn.execute(
                        text(
                            """
                            INSERT INTO role_permissions(role_pk, permission_pk)
                            SELECT r.role_pk, p.permission_pk
                            FROM roles r JOIN permissions p ON p.permission_code = :permission_code
                            WHERE r.role_name = :role_name
                            ON CONFLICT DO NOTHING
                            """
                        ),
                        {"role_name": role_name, "permission_code": permission_code},
                    )
                for table_name, can_read in DEFAULT_ROLE_TABLE_ACCESS.get(role_name, {}).items():
                    conn.execute(
                        text(
                            """
                            INSERT INTO role_table_access(role_pk, table_name, can_read)
                            SELECT r.role_pk, :table_name, :can_read
                            FROM roles r
                            WHERE r.role_name = :role_name
                            ON CONFLICT (role_pk, table_name)
                            DO UPDATE SET can_read = EXCLUDED.can_read, updated_at = NOW()
                            """
                        ),
                        {"role_name": role_name, "table_name": table_name, "can_read": can_read},
                    )

            admin_row = conn.execute(
                text("SELECT user_pk FROM app_users WHERE username = :username LIMIT 1"),
                {"username": settings.admin_username},
            ).mappings().first()
            if not admin_row:
                conn.execute(
                    text(
                        """
                        INSERT INTO app_users(username, full_name, email, password_hash, is_active, web_access_enabled)
                        VALUES (:username, :full_name, :email, :password_hash, TRUE, TRUE)
                        """
                    ),
                    {
                        "username": settings.admin_username,
                        "full_name": settings.admin_full_name,
                        "email": settings.admin_email,
                        "password_hash": self._hash_password(settings.admin_password),
                    },
                )
            else:
                conn.execute(
                    text(
                        """
                        UPDATE app_users
                        SET full_name = :full_name,
                            email = :email,
                            password_hash = :password_hash,
                            is_active = TRUE,
                            web_access_enabled = TRUE,
                            updated_at = NOW()
                        WHERE username = :username
                        """
                    ),
                    {
                        "username": settings.admin_username,
                        "full_name": settings.admin_full_name,
                        "email": settings.admin_email,
                        "password_hash": self._hash_password(settings.admin_password),
                    },
                )
            conn.execute(
                text(
                    """
                    INSERT INTO user_roles(user_pk, role_pk)
                    SELECT u.user_pk, r.role_pk
                    FROM app_users u JOIN roles r ON r.role_name = 'admin'
                    WHERE u.username = :username
                    ON CONFLICT DO NOTHING
                    """
                ),
                {"username": settings.admin_username},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO app_settings(setting_key, setting_value)
                    VALUES ('global_internet_enabled', CAST(:value AS jsonb))
                    ON CONFLICT (setting_key)
                    DO UPDATE SET setting_value = EXCLUDED.setting_value, updated_at = NOW()
                    """
                ),
                {"value": "true" if settings.global_internet_enabled else "false"},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO app_settings(setting_key, setting_value)
                    VALUES ('enable_host_network_control', CAST(:value AS jsonb))
                    ON CONFLICT (setting_key)
                    DO UPDATE SET setting_value = EXCLUDED.setting_value, updated_at = NOW()
                    """
                ),
                {"value": "true" if settings.enable_host_network_control else "false"},
            )

    def login(self, username: str, password: str) -> dict[str, Any]:
        user = self._get_user_row(username)
        if not user or not user.get("is_active"):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales invalidas")
        if not self.verify_password(password, user["password_hash"]):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales invalidas")
        hydrated = self.get_user(username)
        return {
            "access_token": self.create_token(username),
            "token_type": "bearer",
            "user": hydrated,
        }

    def _get_user_row(self, username: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT username, full_name, email, password_hash, is_active, web_access_enabled
                    FROM app_users
                    WHERE username = :username
                    LIMIT 1
                    """
                ),
                {"username": username},
            ).mappings().first()
        return dict(row) if row else None

    def get_user(self, username: str) -> dict[str, Any] | None:
        user = self._get_user_row(username)
        if not user:
            return None
        with self.engine.connect() as conn:
            roles = conn.execute(
                text(
                    """
                    SELECT r.role_name
                    FROM roles r
                    JOIN user_roles ur ON ur.role_pk = r.role_pk
                    JOIN app_users u ON u.user_pk = ur.user_pk
                    WHERE u.username = :username
                    ORDER BY r.role_name
                    """
                ),
                {"username": username},
            ).scalars().all()
            permissions = conn.execute(
                text(
                    """
                    SELECT DISTINCT p.permission_code
                    FROM permissions p
                    JOIN role_permissions rp ON rp.permission_pk = p.permission_pk
                    JOIN roles r ON r.role_pk = rp.role_pk
                    JOIN user_roles ur ON ur.role_pk = r.role_pk
                    JOIN app_users u ON u.user_pk = ur.user_pk
                    WHERE u.username = :username
                    ORDER BY p.permission_code
                    """
                ),
                {"username": username},
            ).scalars().all()
            table_rows = conn.execute(
                text(
                    """
                    SELECT rta.table_name, bool_or(rta.can_read) AS can_read
                    FROM role_table_access rta
                    JOIN roles r ON r.role_pk = rta.role_pk
                    JOIN user_roles ur ON ur.role_pk = r.role_pk
                    JOIN app_users u ON u.user_pk = ur.user_pk
                    WHERE u.username = :username
                    GROUP BY rta.table_name
                    ORDER BY rta.table_name
                    """
                ),
                {"username": username},
            ).mappings().all()
        table_access = {row["table_name"]: bool(row["can_read"]) for row in table_rows}
        user.update(
            {
                "roles": roles,
                "permissions": permissions,
                "table_access": table_access,
            }
        )
        return user

    def list_users(self) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT username, full_name, email, is_active, web_access_enabled, created_at
                    FROM app_users
                    ORDER BY username
                    """
                )
            ).mappings().all()
        users = []
        for row in rows:
            item = dict(row)
            hydrated = self.get_user(item["username"])
            item["roles"] = hydrated.get("roles", []) if hydrated else []
            users.append(item)
        return users

    def list_roles(self) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT role_name, description, is_system
                    FROM roles
                    ORDER BY role_name
                    """
                )
            ).mappings().all()
        result = []
        for row in rows:
            role_name = row["role_name"]
            result.append(
                {
                    **dict(row),
                    "permission_codes": self.get_role_permissions(role_name),
                    "table_access": self.get_role_table_access(role_name),
                }
            )
        return result

    def get_role_permissions(self, role_name: str) -> list[str]:
        with self.engine.connect() as conn:
            return conn.execute(
                text(
                    """
                    SELECT p.permission_code
                    FROM permissions p
                    JOIN role_permissions rp ON rp.permission_pk = p.permission_pk
                    JOIN roles r ON r.role_pk = rp.role_pk
                    WHERE r.role_name = :role_name
                    ORDER BY p.permission_code
                    """
                ),
                {"role_name": role_name},
            ).scalars().all()

    def get_role_table_access(self, role_name: str) -> dict[str, bool]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT rta.table_name, rta.can_read
                    FROM role_table_access rta
                    JOIN roles r ON r.role_pk = rta.role_pk
                    WHERE r.role_name = :role_name
                    ORDER BY rta.table_name
                    """
                ),
                {"role_name": role_name},
            ).mappings().all()
        return {row["table_name"]: bool(row["can_read"]) for row in rows}

    def create_user(
        self,
        username: str,
        password: str,
        full_name: str,
        email: str | None,
        role_names: list[str],
        web_access_enabled: bool,
        is_active: bool,
    ) -> dict[str, Any]:
        if self._get_user_row(username):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El usuario ya existe")
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO app_users(username, full_name, email, password_hash, is_active, web_access_enabled)
                    VALUES (:username, :full_name, :email, :password_hash, :is_active, :web_access_enabled)
                    """
                ),
                {
                    "username": username,
                    "full_name": full_name,
                    "email": email,
                    "password_hash": self._hash_password(password),
                    "is_active": is_active,
                    "web_access_enabled": web_access_enabled,
                },
            )
        self.set_user_roles(username, role_names or ["viewer"])
        return self.get_user(username) or {}

    def set_user_roles(self, username: str, role_names: list[str]) -> dict[str, Any]:
        role_names = sorted(set(role_names))
        with self.engine.begin() as conn:
            user_pk = conn.execute(text("SELECT user_pk FROM app_users WHERE username = :username"), {"username": username}).scalar()
            if not user_pk:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
            available_roles = set(conn.execute(text("SELECT role_name FROM roles")).scalars().all())
            unknown_roles = [role for role in role_names if role not in available_roles]
            if unknown_roles:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Roles inexistentes: {', '.join(unknown_roles)}")
            conn.execute(text("DELETE FROM user_roles WHERE user_pk = :user_pk"), {"user_pk": user_pk})
            for role_name in role_names:
                conn.execute(
                    text(
                        """
                        INSERT INTO user_roles(user_pk, role_pk)
                        SELECT :user_pk, role_pk FROM roles WHERE role_name = :role_name
                        ON CONFLICT DO NOTHING
                        """
                    ),
                    {"user_pk": user_pk, "role_name": role_name},
                )
        return self.get_user(username) or {}

    def set_user_web_access(self, username: str, enabled: bool) -> dict[str, Any]:
        with self.engine.begin() as conn:
            updated = conn.execute(
                text(
                    """
                    UPDATE app_users
                    SET web_access_enabled = :enabled, updated_at = NOW()
                    WHERE username = :username
                    """
                ),
                {"username": username, "enabled": enabled},
            ).rowcount
        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
        return self.get_user(username) or {}

    def create_role(self, role_name: str, description: str | None, permission_codes: list[str], table_access: dict[str, bool]) -> dict[str, Any]:
        with self.engine.begin() as conn:
            if conn.execute(text("SELECT 1 FROM roles WHERE role_name = :role_name"), {"role_name": role_name}).scalar():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El rol ya existe")
            conn.execute(
                text("INSERT INTO roles(role_name, description, is_system) VALUES (:role_name, :description, FALSE)"),
                {"role_name": role_name, "description": description},
            )
        self.update_role_permissions(role_name, permission_codes)
        self.update_role_table_access(role_name, table_access)
        return next((role for role in self.list_roles() if role["role_name"] == role_name), {})

    def update_role_permissions(self, role_name: str, permission_codes: list[str]) -> None:
        permission_codes = sorted(set(permission_codes))
        with self.engine.begin() as conn:
            role_pk = conn.execute(text("SELECT role_pk FROM roles WHERE role_name = :role_name"), {"role_name": role_name}).scalar()
            if not role_pk:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rol no encontrado")
            available = set(conn.execute(text("SELECT permission_code FROM permissions")).scalars().all())
            unknown = [code for code in permission_codes if code not in available]
            if unknown:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Permisos inexistentes: {', '.join(unknown)}")
            conn.execute(text("DELETE FROM role_permissions WHERE role_pk = :role_pk"), {"role_pk": role_pk})
            for permission_code in permission_codes:
                conn.execute(
                    text(
                        """
                        INSERT INTO role_permissions(role_pk, permission_pk)
                        SELECT :role_pk, permission_pk FROM permissions WHERE permission_code = :permission_code
                        ON CONFLICT DO NOTHING
                        """
                    ),
                    {"role_pk": role_pk, "permission_code": permission_code},
                )

    def update_role_table_access(self, role_name: str, table_access: dict[str, bool]) -> None:
        table_access = table_access or {}
        with self.engine.begin() as conn:
            role_pk = conn.execute(text("SELECT role_pk FROM roles WHERE role_name = :role_name"), {"role_name": role_name}).scalar()
            if not role_pk:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rol no encontrado")
            for table_name, can_read in table_access.items():
                conn.execute(
                    text(
                        """
                        INSERT INTO role_table_access(role_pk, table_name, can_read)
                        VALUES (:role_pk, :table_name, :can_read)
                        ON CONFLICT (role_pk, table_name)
                        DO UPDATE SET can_read = EXCLUDED.can_read, updated_at = NOW()
                        """
                    ),
                    {"role_pk": role_pk, "table_name": table_name, "can_read": bool(can_read)},
                )

    def list_permissions(self) -> list[str]:
        with self.engine.connect() as conn:
            return conn.execute(text("SELECT permission_code FROM permissions ORDER BY permission_code")).scalars().all()
