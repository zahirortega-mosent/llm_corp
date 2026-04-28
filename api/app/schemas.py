from typing import Any, Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3)
    password: str = Field(..., min_length=6)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict[str, Any]


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3)
    period: Optional[str] = None
    bank: Optional[str] = None
    filial: Optional[str] = None
    account_number: Optional[str] = None
    conversation_id: Optional[str] = None
    use_web: bool = False
    options: dict[str, Any] = Field(default_factory=dict)


class AskResponse(BaseModel):
    question: str
    filters: dict[str, Any]
    filter_resolution: dict[str, Any] = Field(default_factory=dict)
    route: Optional[str] = None
    intent: Optional[str] = None
    confidence: Optional[float] = None
    used_llm: bool = False
    model_used: Optional[str] = None
    used_memory: bool = False
    used_fallback: bool
    web_used: bool
    web_allowed: bool
    web_query: Optional[str] = None
    answer: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    context: Optional[dict[str, Any]] = None


class UserCreateRequest(BaseModel):
    username: str = Field(..., min_length=3)
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=2)
    email: Optional[str] = None
    role_names: list[str] = Field(default_factory=list)
    web_access_enabled: bool = False
    is_active: bool = True


class UserRolesRequest(BaseModel):
    role_names: list[str] = Field(default_factory=list)


class UserWebAccessRequest(BaseModel):
    web_access_enabled: bool


class RoleCreateRequest(BaseModel):
    role_name: str = Field(..., min_length=3)
    description: Optional[str] = None
    permission_codes: list[str] = Field(default_factory=list)
    table_access: dict[str, bool] = Field(default_factory=dict)


class TableAccessUpdateRequest(BaseModel):
    role_name: str = Field(..., min_length=3)
    table_access: dict[str, bool] = Field(default_factory=dict)


class InternetPolicyUpdateRequest(BaseModel):
    global_internet_enabled: bool


class HostCommandRequest(BaseModel):
    command_type: str = Field(..., min_length=3)
    command_payload: dict[str, Any] = Field(default_factory=dict)


class ChatCommandRequest(BaseModel):
    command: str = Field(..., min_length=2)
