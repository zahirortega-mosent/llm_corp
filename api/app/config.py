from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    postgres_db: str = "conciliador_mvp"
    postgres_user: str = "conciliador"
    postgres_password: str = "conciliador_local_2026"
    postgres_host: str = "db"
    postgres_port: int = 5432

    app_host: str = "0.0.0.0"
    app_port: int = 8000
    api_base_url: str = "http://api:8000"

    public_port: int = 3000
    secure_ui_base_path: str = "secure"
    streamlit_base_path: str = "secure"

    data_source_mode: str = "sqlserver"
    csv_source_path: str = "/data/input/conciliador_movimientos_pdf_enero_febrero.csv"
    sqlserver_server: str = r"192.168.0.10\POWERBI"
    sqlserver_database: str = "DataLake"
    sqlserver_username: str = "sa"
    sqlserver_password: str = ""
    sqlserver_port: int | None = None
    sqlserver_statements_query_file: str = "/app/config/sqlserver_queries/statements.sql"
    sqlserver_movements_query_file: str = "/app/config/sqlserver_queries/movements.sql"
    sqlserver_login_timeout_seconds: int = 15
    sqlserver_timeout_seconds: int = 120

    pdf_source_path: str = "/data/input/Conciliador_zahir_1.1.pdf"
    source_code_path: str = "/data/input/conciliacion_mosent-main"
    source_code_paths: str = "/data/input/codebases"
    assignments_path: str = "/data/input/assignments.csv"
    etl_output_dir: str = "/data/output"

    llm_enabled: bool = True
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "qwen3:8b"
    ollama_timeout_seconds: int = 180
    llm_max_tokens: int = 900
    llm_temperature: float = 0.1

    enable_new_router: bool = True
    enable_llm_classifier: bool = False
    enable_institutional_memory: bool = False
    enable_scope_enforcement: bool = False
    enable_context_resolver: bool = False

    llm_fast_model: str = "qwen3:4b"
    llm_analyst_model: str = "qwen3:14b"
    llm_classifier_model: str = "qwen3:4b"
    llm_embedding_model: str = "qwen3-embedding:0.6b"
    llm_default_context: int = 8192
    llm_long_context: int = 16384
    llm_classifier_timeout_seconds: int = 30
    llm_analyst_timeout_seconds: int = 180
    llm_allow_thinking: bool = False

    searxng_base_url: str = "http://localhost:8080/"
    searxng_query_url: str = "http://searxng:8080/search?q=<query>&format=json"
    web_search_result_count: int = 5
    web_loader_timeout: int = 15
    web_domain_allowlist: str = ""
    outbound_terms_blocklist: str = "mosent,pabs,netpay,odoo,nextcloud,zahir,stp,ecobro"
    outbound_default_concepts_query: str = "conciliacion bancaria mejores practicas controles financieros segregacion funciones"

    auth_secret_key: str = "change-me-in-env"
    host_agent_secret_key: str = "change-agent-key"
    auth_token_max_age_seconds: int = 28800
    admin_username: str = "admin"
    admin_password: str = "Admin123!"
    admin_full_name: str = "Administrador Local"
    admin_email: str = "admin@local"

    global_internet_enabled: bool = False
    internet_allowed_users: str = "admin"
    enable_host_network_control: bool = False
    host_command_queue_dir: str = "/control/commands/pending"

    open_webui_port: int = 3000
    streamlit_port: int = 8501

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def host_command_queue_path(self) -> Path:
        return Path(self.host_command_queue_dir)

    @property
    def domain_allowlist(self) -> list[str]:
        return [item.strip().lower() for item in self.web_domain_allowlist.split(",") if item.strip()]

    @property
    def outbound_blocklist(self) -> list[str]:
        return [item.strip().lower() for item in self.outbound_terms_blocklist.split(",") if item.strip()]

    @property
    def env_internet_allowed_users(self) -> list[str]:
        return [item.strip() for item in self.internet_allowed_users.split(",") if item.strip()]

    @property
    def source_code_locations(self) -> list[str]:
        locations = [item.strip() for item in self.source_code_paths.split(",") if item.strip()]
        if self.source_code_path and self.source_code_path not in locations:
            locations.append(self.source_code_path)
        return locations


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
