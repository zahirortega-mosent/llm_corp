from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.services.auth_service import AuthService

security = HTTPBearer(auto_error=False)

auth_service = AuthService()


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Falta token de acceso")
    username = auth_service.decode_token(credentials.credentials)
    user = auth_service.get_user(username)
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no valido")
    return user


def require_permission(permission_code: str) -> Callable:
    def dependency(user: dict = Depends(get_current_user)) -> dict:
        if permission_code not in set(user.get("permissions") or []):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permiso insuficiente: {permission_code}",
            )
        return user

    return dependency
