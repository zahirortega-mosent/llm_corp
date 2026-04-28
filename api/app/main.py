from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from sqlalchemy import text

from app.config import get_settings
from app.db import get_engine
from app.dependencies import get_current_user, require_permission
from app.schemas import (
    AskRequest,
    ChatCommandRequest,
    HostCommandRequest,
    InternetPolicyUpdateRequest,
    LoginRequest,
    LoginResponse,
    RoleCreateRequest,
    TableAccessUpdateRequest,
    UserCreateRequest,
    UserRolesRequest,
    UserWebAccessRequest,
)
from app.services.answer_service import AnswerService
from app.services.auth_service import AuthService
from app.services.command_service import CommandService
from app.services.policy_service import PolicyService
from app.services.query_service import QueryService

query_service = QueryService()
answer_service = AnswerService()
auth_service = AuthService()
policy_service = PolicyService()
command_service = CommandService()


@asynccontextmanager
async def lifespan(_: FastAPI):
    auth_service.bootstrap_security()
    yield


app = FastAPI(
    title="Qwen Secure Enterprise Stack",
    version="2.0.0",
    description="Consulta segura de datos corporativos con comparacion controlada contra conceptos publicos.",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    engine = get_engine()
    with engine.connect() as conn:
        movements = conn.execute(text("SELECT COUNT(*) FROM bank_movements")).scalar_one()
        statements = conn.execute(text("SELECT COUNT(*) FROM bank_statements")).scalar_one()
        incidents = conn.execute(text("SELECT COUNT(*) FROM incidents")).scalar_one()
        snippets = conn.execute(text("SELECT COUNT(*) FROM knowledge_snippets")).scalar_one()
    return {
        "status": "ok",
        "database": settings.database_url.rsplit("@", maxsplit=1)[-1],
        "llm_enabled": settings.llm_enabled,
        "ollama_base_url": settings.ollama_base_url,
        "open_webui_port": settings.open_webui_port,
        "streamlit_port": settings.streamlit_port,
        "movements": movements,
        "statements": statements,
        "incidents": incidents,
        "knowledge_snippets": snippets,
        "policies": policy_service.get_policies(),
    }


@app.post("/auth/login", response_model=LoginResponse)
def login(request: LoginRequest) -> dict:
    return auth_service.login(request.username, request.password)


@app.get("/auth/me")
def me(user: dict = Depends(get_current_user)) -> dict:
    return user


@app.get("/metadata")
def metadata(user: dict = Depends(require_permission("view_summary"))) -> dict:
    return query_service.get_metadata(user)


@app.get("/summary")
def summary(
    period: str | None = Query(default=None),
    bank: str | None = Query(default=None),
    filial: str | None = Query(default=None),
    account_number: str | None = Query(default=None),
    user: dict = Depends(require_permission("view_summary")),
) -> dict:
    return query_service.get_summary(user, {"period": period, "bank": bank, "filial": filial, "account_number": account_number})


@app.get("/movements")
def movements(
    period: str | None = Query(default=None),
    bank: str | None = Query(default=None),
    filial: str | None = Query(default=None),
    account_number: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(require_permission("view_movements")),
) -> list[dict]:
    return query_service.get_movements(user, {"period": period, "bank": bank, "filial": filial, "account_number": account_number}, limit=limit, offset=offset)


@app.get("/incidents")
def incidents(
    period: str | None = Query(default=None),
    bank: str | None = Query(default=None),
    filial: str | None = Query(default=None),
    account_number: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    rule_code: str | None = Query(default=None),
    aggregated: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=500),
    user: dict = Depends(require_permission("view_incidents")),
) -> list[dict]:
    return query_service.get_incidents(user, {"period": period, "bank": bank, "filial": filial, "account_number": account_number, "severity": severity, "rule_code": rule_code}, limit=limit, aggregated=aggregated)


@app.get("/rules")
def rules(question: str = Query(default="incidencias de conciliacion"), limit: int = Query(default=20, ge=1, le=100), user: dict = Depends(require_permission("view_rules"))) -> list[dict]:
    return query_service.get_relevant_rules(user, question=question, related_rule_codes=None, limit=limit)


@app.get("/knowledge")
def knowledge(question: str = Query(..., min_length=3), limit: int = Query(default=10, ge=1, le=50), user: dict = Depends(require_permission("view_knowledge"))) -> list[dict]:
    return query_service.search_knowledge(user, question=question, limit=limit)


@app.post("/ask")
def ask(request: AskRequest, user: dict = Depends(require_permission("ask_internal"))) -> dict:
    explicit_filters = {"period": request.period, "bank": request.bank, "filial": request.filial, "account_number": request.account_number}
    return answer_service.answer(request.question, user=user, explicit_filters=explicit_filters, use_web=False, conversation_id=request.conversation_id, options=request.options)


@app.post("/ask/hybrid")
def ask_hybrid(request: AskRequest, user: dict = Depends(require_permission("ask_hybrid"))) -> dict:
    explicit_filters = {"period": request.period, "bank": request.bank, "filial": request.filial, "account_number": request.account_number}
    return answer_service.answer(request.question, user=user, explicit_filters=explicit_filters, use_web=bool(request.use_web), conversation_id=request.conversation_id, options=request.options)


@app.post("/chat")
def chat(request: AskRequest, user: dict = Depends(get_current_user)) -> dict:
    if request.question.strip().startswith("/"):
        return command_service.handle_chat_command(user, request.question)
    explicit_filters = {"period": request.period, "bank": request.bank, "filial": request.filial, "account_number": request.account_number}
    can_hybrid = "ask_hybrid" in set(user.get("permissions") or [])
    use_web = bool(request.use_web and can_hybrid)
    return answer_service.answer(request.question, user=user, explicit_filters=explicit_filters, use_web=use_web, conversation_id=request.conversation_id, options=request.options)


@app.get("/admin/users")
def admin_users(_: dict = Depends(require_permission("manage_users"))) -> list[dict]:
    return auth_service.list_users()


@app.post("/admin/users")
def create_admin_user(request: UserCreateRequest, _: dict = Depends(require_permission("manage_users"))) -> dict:
    return auth_service.create_user(
        username=request.username,
        password=request.password,
        full_name=request.full_name,
        email=request.email,
        role_names=request.role_names,
        web_access_enabled=request.web_access_enabled,
        is_active=request.is_active,
    )


@app.put("/admin/users/{username}/roles")
def update_user_roles(username: str, request: UserRolesRequest, _: dict = Depends(require_permission("manage_users"))) -> dict:
    return auth_service.set_user_roles(username, request.role_names)


@app.put("/admin/users/{username}/web-access")
def update_user_web_access(username: str, request: UserWebAccessRequest, _: dict = Depends(require_permission("manage_policies"))) -> dict:
    return auth_service.set_user_web_access(username, request.web_access_enabled)


@app.get("/admin/roles")
def admin_roles(_: dict = Depends(require_permission("manage_roles"))) -> list[dict]:
    return auth_service.list_roles()


@app.get("/admin/permissions")
def admin_permissions(_: dict = Depends(require_permission("manage_roles"))) -> dict:
    return {"permissions": auth_service.list_permissions()}


@app.post("/admin/roles")
def create_role(request: RoleCreateRequest, _: dict = Depends(require_permission("manage_roles"))) -> dict:
    return auth_service.create_role(
        role_name=request.role_name,
        description=request.description,
        permission_codes=request.permission_codes,
        table_access=request.table_access,
    )


@app.put("/admin/roles/table-access")
def update_table_access(request: TableAccessUpdateRequest, _: dict = Depends(require_permission("manage_roles"))) -> dict:
    auth_service.update_role_table_access(request.role_name, request.table_access)
    return {"role_name": request.role_name, "table_access": auth_service.get_role_table_access(request.role_name)}


@app.get("/admin/policies")
def admin_policies(_: dict = Depends(require_permission("manage_policies"))) -> dict:
    return policy_service.get_policies()


@app.put("/admin/policies/internet")
def admin_policy_internet(request: InternetPolicyUpdateRequest, user: dict = Depends(require_permission("manage_policies"))) -> dict:
    return policy_service.set_global_internet_enabled(request.global_internet_enabled, requested_by=user["username"])


@app.get("/admin/host-commands")
def host_commands(_: dict = Depends(require_permission("host_network_control"))) -> list[dict]:
    return command_service.list_host_commands()


@app.post("/admin/host-commands")
def create_host_command(request: HostCommandRequest, user: dict = Depends(require_permission("host_network_control"))) -> dict:
    return command_service.queue_host_command(request.command_type, request.command_payload, requested_by=user["username"])


@app.post("/admin/chat-command")
def admin_chat_command(request: ChatCommandRequest, user: dict = Depends(get_current_user)) -> dict:
    return command_service.handle_chat_command(user, request.command)


@app.post("/agent/host-commands/{command_pk}/complete")
def complete_host_command_agent(
    command_pk: int,
    payload: dict,
    x_agent_key: str | None = Header(default=None),
) -> dict:
    settings = get_settings()
    if not x_agent_key or x_agent_key != settings.host_agent_secret_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Agent key invalida")
    return command_service.complete_host_command(
        command_pk=command_pk,
        command_status=str(payload.get("status", "done")),
        result_message=str(payload.get("result_message", "")),
        executor_host=payload.get("executor_host"),
    )
