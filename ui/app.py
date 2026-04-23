import json
import os
from typing import Any

import pandas as pd
import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
OPEN_WEBUI_URL = os.getenv("OPEN_WEBUI_URL", "http://localhost:3000")


def auth_headers() -> dict[str, str]:
    token = st.session_state.get("token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def api_request(method: str, path: str, json: dict | None = None, params: dict | None = None, auth: bool = True) -> Any:
    headers = auth_headers() if auth else {}
    response = requests.request(method, f"{API_BASE_URL}{path}", json=json, params=params, headers=headers, timeout=180)
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail")
        except Exception:
            detail = response.text
        raise RuntimeError(f"{response.status_code}: {detail}")
    return response.json()


def safe_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def login_view() -> None:
    st.title("Qwen Secure Enterprise Stack")
    st.caption("Datos corporativos blindados + benchmark publico controlado.")
    with st.form("login"):
        username = st.text_input("Usuario")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Entrar", type="primary")
    if submitted:
        try:
            payload = api_request("POST", "/auth/login", json={"username": username, "password": password}, auth=False)
            st.session_state["token"] = payload["access_token"]
            st.session_state["me"] = payload["user"]
            st.rerun()
        except Exception as exc:
            st.error(str(exc))


def refresh_me() -> dict:
    me = api_request("GET", "/auth/me")
    st.session_state["me"] = me
    return me


def current_user() -> dict:
    return st.session_state.get("me") or refresh_me()


def render_sidebar(me: dict) -> None:
    st.sidebar.title("Sesion")
    st.sidebar.write(f"**Usuario:** {me.get('username')}")
    st.sidebar.write(f"**Nombre:** {me.get('full_name') or '-'}")
    st.sidebar.write(f"**Roles:** {', '.join(me.get('roles') or [])}")
    st.sidebar.write(f"**Permisos:** {', '.join(me.get('permissions') or [])}")
    st.sidebar.write(f"**Web por usuario:** {'SI' if me.get('web_access_enabled') else 'NO'}")
    if st.sidebar.button("Cerrar sesion"):
        st.session_state.clear()
        st.rerun()


def render_filters(me: dict) -> dict[str, Any]:
    filters = {"period": None, "bank": None, "filial": None, "account_number": None}
    if "view_summary" not in set(me.get("permissions") or []):
        return filters
    try:
        metadata = api_request("GET", "/metadata")
    except Exception as exc:
        st.sidebar.error(str(exc))
        return filters
    periods = [""] + list(metadata.get("periods") or [])
    banks = [""] + list(metadata.get("banks") or [])
    filiales = [""] + list(metadata.get("filiales") or [])
    st.sidebar.title("Filtros")
    filters["period"] = st.sidebar.selectbox("Periodo", periods, index=0) or None
    filters["bank"] = st.sidebar.selectbox("Banco", banks, index=0) or None
    filters["filial"] = st.sidebar.selectbox("Filial", filiales, index=0) or None
    filters["account_number"] = st.sidebar.text_input("Cuenta").strip() or None
    return filters


def render_dashboard(filters: dict[str, Any], me: dict) -> None:
    st.subheader("Panel corporativo")
    if "view_summary" not in set(me.get("permissions") or []):
        st.info("Tu rol no tiene acceso al panel ejecutivo.")
        return
    try:
        summary = api_request("GET", "/summary", params=filters)
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Movimientos", f"{int(summary.get('movements', 0)):,}")
        col2.metric("Depositos", f"${float(summary.get('total_deposits', 0)):,.2f}")
        col3.metric("Retiros", f"${float(summary.get('total_withdrawals', 0)):,.2f}")
        col4.metric("Incidencias", f"{int(summary.get('incidents', 0)):,}")
        col5, col6, col7, col8 = st.columns(4)
        col5.metric("Estados de cuenta", f"{int(summary.get('statements', 0)):,}")
        col6.metric("No conciliados", f"{int(summary.get('unreconciled_movements', 0)):,}")
        col7.metric("Descuadre saldo", f"{int(summary.get('statement_balance_mismatch', 0)):,}")
        col8.metric("Archivos", f"{int(summary.get('files', 0)):,}")
    except Exception as exc:
        st.error(str(exc))
        return

    left, right = st.columns(2)
    if "view_incidents" in set(me.get("permissions") or []):
        with left:
            st.markdown("#### Incidencias agregadas")
            try:
                incidents = api_request("GET", "/incidents", params={**filters, "aggregated": True, "limit": 20})
                frame = safe_df(incidents)
                if not frame.empty:
                    st.dataframe(frame, use_container_width=True, hide_index=True)
                else:
                    st.info("Sin incidencias con los filtros actuales.")
            except Exception as exc:
                st.error(str(exc))
    if "view_movements" in set(me.get("permissions") or []):
        with right:
            st.markdown("#### Movimientos relevantes")
            try:
                movements = api_request("GET", "/movements", params={**filters, "limit": 20})
                frame = safe_df(movements)
                if not frame.empty:
                    st.dataframe(frame, use_container_width=True, hide_index=True)
                else:
                    st.info("Sin movimientos con los filtros actuales.")
            except Exception as exc:
                st.error(str(exc))


def render_chat(filters: dict[str, Any], me: dict) -> None:
    st.subheader("Chat protegido")
    st.caption("Comandos soportados: /internet on|off, /allow-web usuario, /deny-web usuario, /wifi on|off, /roles usuario rol1,rol2")
    permissions = set(me.get("permissions") or [])
    allow_web_checkbox = "ask_hybrid" in permissions and me.get("web_access_enabled")
    use_web = st.checkbox("Usar benchmark publico controlado", value=False, disabled=not allow_web_checkbox)
    prompt = st.text_area(
        "Pregunta o comando",
        value="¿Qué movimientos de febrero en Santander requieren revisión y qué conceptos públicos aplican sin alterar nuestros datos internos?",
        height=140,
    )
    if st.button("Enviar al chat", type="primary"):
        try:
            result = api_request("POST", "/chat", json={"question": prompt, "use_web": use_web, **filters})
            if "answer" in result:
                st.markdown("### Respuesta")
                st.markdown(result["answer"])
                with st.expander("Contexto usado"):
                    st.json({
                        "filters": result.get("filters"),
                        "web_allowed": result.get("web_allowed"),
                        "web_used": result.get("web_used"),
                        "web_query": result.get("web_query"),
                        "summary": result.get("context", {}).get("summary"),
                        "incident_summary": result.get("context", {}).get("incident_summary"),
                        "rules": result.get("context", {}).get("rules"),
                        "knowledge": result.get("context", {}).get("knowledge"),
                        "web_results": result.get("context", {}).get("web_results"),
                    })
            else:
                st.success(result.get("message", "Comando ejecutado"))
                if result.get("user"):
                    st.json(result["user"])
                if result.get("policies"):
                    st.json(result["policies"])
                if result.get("command"):
                    st.json(result["command"])
                refresh_me()
        except Exception as exc:
            st.error(str(exc))


def render_admin(me: dict) -> None:
    permissions = set(me.get("permissions") or [])
    if not ({"manage_users", "manage_roles", "manage_policies", "host_network_control"} & permissions):
        st.info("Tu rol no tiene acceso al panel de administración.")
        return

    st.subheader("Administración de seguridad")

    if "manage_policies" in permissions:
        with st.expander("Políticas globales", expanded=True):
            try:
                policies = api_request("GET", "/admin/policies")
                st.json(policies)
                with st.form("internet_policy"):
                    global_internet_enabled = st.toggle("Internet global habilitado", value=bool(policies.get("global_internet_enabled")))
                    submitted = st.form_submit_button("Guardar política")
                if submitted:
                    api_request("PUT", "/admin/policies/internet", json={"global_internet_enabled": global_internet_enabled})
                    st.success("Política actualizada")
                    st.rerun()
            except Exception as exc:
                st.error(str(exc))

    if "manage_users" in permissions:
        with st.expander("Usuarios y asignación web", expanded=True):
            try:
                users = api_request("GET", "/admin/users")
                st.dataframe(safe_df(users), use_container_width=True, hide_index=True)
            except Exception as exc:
                st.error(str(exc))
                users = []

            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("##### Crear usuario")
                with st.form("create_user"):
                    username = st.text_input("Nuevo usuario")
                    full_name = st.text_input("Nombre completo")
                    email = st.text_input("Correo")
                    password = st.text_input("Password inicial", type="password")
                    role_names = st.text_input("Roles (coma separados)", value="viewer")
                    web_access_enabled = st.checkbox("Habilitar web para este usuario")
                    submitted = st.form_submit_button("Crear usuario")
                if submitted:
                    try:
                        api_request("POST", "/admin/users", json={
                            "username": username,
                            "password": password,
                            "full_name": full_name,
                            "email": email or None,
                            "role_names": [item.strip() for item in role_names.split(",") if item.strip()],
                            "web_access_enabled": web_access_enabled,
                            "is_active": True,
                        })
                        st.success("Usuario creado")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
            with col_b:
                st.markdown("##### Cambiar roles o web")
                with st.form("update_user"):
                    selected_username = st.text_input("Usuario a modificar")
                    new_roles = st.text_input("Roles nuevos (coma separados)")
                    new_web = st.selectbox("Acceso web", ["sin cambio", "habilitar", "bloquear"], index=0)
                    submitted = st.form_submit_button("Aplicar cambios")
                if submitted:
                    try:
                        if new_roles.strip():
                            api_request("PUT", f"/admin/users/{selected_username}/roles", json={"role_names": [item.strip() for item in new_roles.split(",") if item.strip()]})
                        if new_web != "sin cambio":
                            api_request("PUT", f"/admin/users/{selected_username}/web-access", json={"web_access_enabled": new_web == 'habilitar'})
                        st.success("Usuario actualizado")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))

    if "manage_roles" in permissions:
        with st.expander("Roles y acceso por tablas", expanded=False):
            try:
                roles = api_request("GET", "/admin/roles")
                all_permissions = api_request("GET", "/admin/permissions").get("permissions", [])
                st.dataframe(safe_df(roles), use_container_width=True, hide_index=True)
            except Exception as exc:
                st.error(str(exc))
                roles = []
                all_permissions = []
            with st.form("create_role"):
                role_name = st.text_input("Nombre del rol")
                description = st.text_input("Descripción")
                permission_codes = st.multiselect("Permisos", options=all_permissions)
                table_access_text = st.text_area(
                    "Acceso por tablas JSON",
                    value='{"bank_movements": true, "bank_statements": true, "incidents": true, "knowledge_snippets": false, "business_rules": true, "assignments": false}',
                    height=120,
                )
                submitted = st.form_submit_button("Crear rol")
            if submitted:
                try:
                    table_access = json.loads(table_access_text)
                    api_request("POST", "/admin/roles", json={
                        "role_name": role_name,
                        "description": description,
                        "permission_codes": permission_codes,
                        "table_access": table_access,
                    })
                    st.success("Rol creado")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    if "host_network_control" in permissions:
        with st.expander("Control de red del host", expanded=False):
            st.warning("Para Wi‑Fi por chat debes correr también el host agent en macOS o Ubuntu.")
            with st.form("host_commands"):
                command = st.selectbox("Comando", ["wifi_power"])
                state = st.selectbox("Estado", ["off", "on"])
                submitted = st.form_submit_button("Encolar comando")
            if submitted:
                try:
                    api_request("POST", "/admin/host-commands", json={"command_type": command, "command_payload": {"state": state}})
                    st.success("Comando encolado")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
            try:
                commands = api_request("GET", "/admin/host-commands")
                st.dataframe(safe_df(commands), use_container_width=True, hide_index=True)
            except Exception as exc:
                st.error(str(exc))


def render_webui_tab() -> None:
    st.subheader("Open WebUI aislado")
    st.write(
        "Esta UI sirve como chat local general con búsqueda web, pero no toca la base financiera. "
        "El acceso corporativo seguro queda en las pestañas anteriores."
    )
    st.markdown(f"Abrir Open WebUI: [Ir a {OPEN_WEBUI_URL}]({OPEN_WEBUI_URL})")


def main() -> None:
    st.set_page_config(page_title="Qwen Secure Enterprise Stack", layout="wide")
    if "token" not in st.session_state:
        login_view()
        return
    me = current_user()
    render_sidebar(me)
    filters = render_filters(me)
    tabs = st.tabs(["Panel", "Chat protegido", "Administración", "Open WebUI"])
    with tabs[0]:
        render_dashboard(filters, me)
    with tabs[1]:
        render_chat(filters, me)
    with tabs[2]:
        render_admin(me)
    with tabs[3]:
        render_webui_tab()


if __name__ == "__main__":
    main()
