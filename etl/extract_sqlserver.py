from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd
import pymssql


REQUIRED_STATEMENT_COLUMNS = {
    "source_statement_id", "statement_uid", "source_hash", "source_filename", "account_number",
    "clabe", "entity_name", "filial", "bank", "currency", "period", "period_start", "period_end",
    "opening_balance", "closing_balance", "total_deposits", "total_withdrawals",
    "reconciled_deposit_balance", "reconciled_withdrawal_balance", "statement_balance_ok",
    "created_at_source", "updated_at_source",
}

REQUIRED_MOVEMENT_COLUMNS = {
    "source_movement_id", "source_statement_id", "statement_uid", "bank_transaction_id", "bank", "filial",
    "account_number", "clabe", "entity_name", "period", "movement_date", "settlement_date", "reference",
    "folio", "description", "concept", "movement_type", "amount", "deposit", "withdrawal", "balance",
    "liquidation_balance", "currency", "reconciled", "source_filename", "source_hash", "source_group",
    "created_at_source", "updated_at_source",
}


class SourceConfigError(RuntimeError):
    pass


def _query_text(path: str | Path, required: bool = True) -> str:
    path = Path(path)
    if not path.exists():
        if required:
            raise SourceConfigError(f"No existe el archivo de query: {path}")
        return ""
    query = path.read_text(encoding="utf-8").strip()
    if not query and required:
        raise SourceConfigError(f"La query está vacía: {path}")
    return query


def _ensure_columns(frame: pd.DataFrame, required_columns: Iterable[str], label: str) -> None:
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise SourceConfigError(f"La query de {label} no devolvió todas las columnas requeridas. Faltan: {', '.join(missing)}")


def _connect(settings) -> pymssql.Connection:
    if not getattr(settings, 'sqlserver_password', ''):
        raise SourceConfigError('Falta SQLSERVER_PASSWORD en .env. No lo inferí porque no venía visible en los archivos compartidos.')
    server = settings.sqlserver_server
    if getattr(settings, 'sqlserver_port', None):
        server = f"{server}:{settings.sqlserver_port}"
    return pymssql.connect(
        server=server,
        user=settings.sqlserver_username,
        password=settings.sqlserver_password,
        database=settings.sqlserver_database,
        login_timeout=int(settings.sqlserver_login_timeout_seconds),
        timeout=int(settings.sqlserver_timeout_seconds),
        charset='UTF-8',
    )


def read_normalized_frames(settings) -> tuple[pd.DataFrame, pd.DataFrame]:
    statements_query = _query_text(settings.sqlserver_statements_query_file, required=True)
    movements_query = _query_text(settings.sqlserver_movements_query_file, required=True)
    if 'SELECT' not in movements_query.upper():
        raise SourceConfigError('SQLSERVER_MOVEMENTS_QUERY_FILE todavía no contiene la query real de movimientos.')
    with _connect(settings) as connection:
        statements = pd.read_sql(statements_query, connection)
        movements = pd.read_sql(movements_query, connection)
    _ensure_columns(statements, REQUIRED_STATEMENT_COLUMNS, 'estados de cuenta')
    _ensure_columns(movements, REQUIRED_MOVEMENT_COLUMNS, 'movimientos')
    return statements, movements
