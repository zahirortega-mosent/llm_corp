import json
import re
from typing import Any

import pandas as pd
from fastapi import HTTPException, status
from sqlalchemy import text

from app.db import get_engine
from app.utils.filters import normalize_text


def _serialize_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return frame.where(pd.notnull(frame), None).to_dict(orient="records")


class QueryService:
    def __init__(self) -> None:
        self.engine = get_engine()

    def _normalize_period(self, period: str | None) -> str | None:
        if not period:
            return None
        cleaned = str(period).strip()
        if re.fullmatch(r"\d{4}-\d{2}", cleaned):
            return f"{cleaned}-01"
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", cleaned):
            return f"{cleaned[:7]}-01"
        return cleaned

    def ensure_table_access(self, user: dict[str, Any], table_names: list[str]) -> None:
        table_access = user.get("table_access") or {}
        missing = [table for table in table_names if not table_access.get(table, False)]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso denegado a tablas: {', '.join(sorted(missing))}",
            )

    def get_metadata(self, user: dict[str, Any]) -> dict[str, Any]:
        self.ensure_table_access(user, ["bank_movements"])
        with self.engine.connect() as conn:
            periods = pd.read_sql(text("SELECT DISTINCT period FROM bank_movements WHERE period IS NOT NULL ORDER BY period"), conn)
            banks = pd.read_sql(text("SELECT DISTINCT bank FROM bank_movements WHERE bank IS NOT NULL ORDER BY bank"), conn)
            filiales = pd.read_sql(text("SELECT DISTINCT filial FROM bank_movements WHERE filial IS NOT NULL ORDER BY filial"), conn)
        return {
            "periods": [str(v)[:10] for v in periods["period"].tolist()],
            "banks": banks["bank"].tolist(),
            "filiales": filiales["filial"].tolist(),
        }

    def build_where(self, filters: dict[str, Any], table_alias: str = "") -> tuple[str, dict[str, Any]]:
        prefix = f"{table_alias}." if table_alias else ""
        conditions = []
        params: dict[str, Any] = {}
        period = self._normalize_period(filters.get("period"))
        if period:
            conditions.append(f"{prefix}period = :period")
            params["period"] = period
        bank = filters.get("bank")
        if bank:
            conditions.append(f"UPPER({prefix}bank) = :bank")
            params["bank"] = str(bank).upper()
        filial = filters.get("filial")
        if filial:
            conditions.append(f"{prefix}filial = :filial")
            params["filial"] = filial
        account_number = filters.get("account_number")
        if account_number:
            conditions.append(f"{prefix}account_number = :account_number")
            params["account_number"] = str(account_number)
        severity = filters.get("severity")
        if severity:
            conditions.append(f"{prefix}severity = :severity")
            params["severity"] = severity
        rule_code = filters.get("rule_code")
        if rule_code:
            conditions.append(f"{prefix}rule_code = :rule_code")
            params["rule_code"] = rule_code
        return ("WHERE " + " AND ".join(conditions)) if conditions else "", params

    def get_summary(self, user: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        self.ensure_table_access(user, ["bank_movements", "bank_statements", "incidents"])
        mov_where, mov_params = self.build_where(filters)
        stmt_where, stmt_params = self.build_where(filters)
        inc_where, inc_params = self.build_where(filters)
        movements_sql = text(
            f"""
            SELECT COUNT(*) AS movements,
                   COALESCE(SUM(deposit), 0) AS total_deposits,
                   COALESCE(SUM(withdrawal), 0) AS total_withdrawals,
                   COUNT(DISTINCT bank) AS banks,
                   COUNT(DISTINCT filial) AS filiales,
                   COUNT(DISTINCT account_number) AS accounts,
                   COUNT(*) FILTER (WHERE reconciled IS TRUE) AS reconciled_movements,
                   COUNT(*) FILTER (WHERE reconciled IS FALSE OR reconciled IS NULL) AS unreconciled_movements
            FROM bank_movements {mov_where}
            """
        )
        statements_sql = text(
            f"""
            SELECT COUNT(*) AS statements,
                   COUNT(*) AS files,
                   COUNT(*) FILTER (WHERE statement_balance_ok IS FALSE) AS statement_balance_mismatch,
                   COUNT(*) FILTER (WHERE header_only IS TRUE) AS header_only_statements
            FROM bank_statements {stmt_where}
            """
        )
        incidents_sql = text(
            f"""
            SELECT COUNT(*) AS incidents,
                   COUNT(*) FILTER (WHERE severity = 'critica') AS critical_incidents,
                   COUNT(*) FILTER (WHERE severity = 'alta') AS high_incidents,
                   COUNT(*) FILTER (WHERE severity = 'media') AS medium_incidents,
                   COUNT(*) FILTER (WHERE severity = 'baja') AS low_incidents
            FROM incidents {inc_where}
            """
        )
        with self.engine.connect() as conn:
            movements = pd.read_sql(movements_sql, conn, params=mov_params).iloc[0].to_dict()
            statements = pd.read_sql(statements_sql, conn, params=stmt_params).iloc[0].to_dict()
            incidents = pd.read_sql(incidents_sql, conn, params=inc_params).iloc[0].to_dict()
        result = {**movements, **statements, **incidents}
        serialized: dict[str, Any] = {}
        for key, value in result.items():
            serialized[key] = value.item() if hasattr(value, "item") else value
        return serialized

    def get_movements(
        self,
        user: dict[str, Any],
        filters: dict[str, Any],
        limit: int = 50,
        offset: int = 0,
        sort_mode: str = "recent",
    ) -> list[dict[str, Any]]:
        self.ensure_table_access(user, ["bank_movements"])
        where, params = self.build_where(filters)
        params.update({"limit": limit, "offset": offset})

        if sort_mode == "amount":
            order_by = "ORDER BY ABS(COALESCE(amount, 0)) DESC, movement_date DESC NULLS LAST"
        else:
            order_by = "ORDER BY movement_date DESC NULLS LAST, ABS(COALESCE(amount, 0)) DESC"

        sql = text(
            f"""
            SELECT movement_uid, bank, filial, account_number, period, movement_date, settlement_date,
                   reference, folio, description, concept, movement_type, amount, deposit, withdrawal,
                   balance, reconciled, source_filename, source_hash
            FROM bank_movements {where}
            {order_by}
            LIMIT :limit OFFSET :offset
            """
        )
        with self.engine.connect() as conn:
            frame = pd.read_sql(sql, conn, params=params)
        return _serialize_records(frame)

    def get_files(self, user: dict[str, Any], filters: dict[str, Any], limit: int = 25) -> list[dict[str, Any]]:
        self.ensure_table_access(user, ["bank_statements"])
        where, params = self.build_where(filters)
        params["limit"] = limit
        sql = text(
            f"""
            SELECT statement_uid, source_filename, source_hash, bank, filial, account_number, period,
                   period_start, period_end, opening_balance, closing_balance, total_deposits,
                   total_withdrawals, statement_balance_ok, header_only
            FROM bank_statements {where}
            ORDER BY period DESC NULLS LAST, bank, filial, account_number
            LIMIT :limit
            """
        )
        with self.engine.connect() as conn:
            frame = pd.read_sql(sql, conn, params=params)
        return _serialize_records(frame)

    def get_incidents(self, user: dict[str, Any], filters: dict[str, Any], limit: int = 100, aggregated: bool = False) -> list[dict[str, Any]]:
        self.ensure_table_access(user, ["incidents"])
        where, params = self.build_where(filters)
        params["limit"] = limit
        if aggregated:
            sql = text(
                f"""
                SELECT rule_code, title, severity, COUNT(*) AS total
                FROM incidents {where}
                GROUP BY rule_code, title, severity
                ORDER BY CASE severity WHEN 'critica' THEN 1 WHEN 'alta' THEN 2 WHEN 'media' THEN 3 ELSE 4 END,
                         COUNT(*) DESC
                LIMIT :limit
                """
            )
        else:
            sql = text(
                f"""
                SELECT incident_uid, rule_code, period, bank, filial, account_number, severity, title,
                       description, source_filename, suggested_owner, evidence
                FROM incidents {where}
                ORDER BY CASE severity WHEN 'critica' THEN 1 WHEN 'alta' THEN 2 WHEN 'media' THEN 3 ELSE 4 END,
                         detected_at DESC
                LIMIT :limit
                """
            )
        with self.engine.connect() as conn:
            frame = pd.read_sql(sql, conn, params=params)
        return _serialize_records(frame)

    def get_top_accounts_by_incidents(self, user: dict[str, Any], filters: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
        self.ensure_table_access(user, ["incidents"])
        where, params = self.build_where(filters)
        params["limit"] = limit
        sql = text(
            f"""
            SELECT bank, filial, account_number, COUNT(*) AS incidents
            FROM incidents {where}
            GROUP BY bank, filial, account_number
            ORDER BY COUNT(*) DESC, bank, filial, account_number
            LIMIT :limit
            """
        )
        with self.engine.connect() as conn:
            frame = pd.read_sql(sql, conn, params=params)
        return _serialize_records(frame)

    def get_top_movement_entities(self, user: dict[str, Any], filters: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
        self.ensure_table_access(user, ["bank_movements"])
        where, params = self.build_where(filters)
        params["limit"] = limit
        sql = text(
            f"""
            SELECT bank, filial, account_number, COUNT(*) AS movements,
                   COALESCE(SUM(deposit), 0) AS total_deposits,
                   COALESCE(SUM(withdrawal), 0) AS total_withdrawals
            FROM bank_movements {where}
            GROUP BY bank, filial, account_number
            ORDER BY COUNT(*) DESC, COALESCE(SUM(deposit), 0) + COALESCE(SUM(withdrawal), 0) DESC
            LIMIT :limit
            """
        )
        with self.engine.connect() as conn:
            frame = pd.read_sql(sql, conn, params=params)
        return _serialize_records(frame)

    def get_relevant_rules(self, user: dict[str, Any], question: str, related_rule_codes: list[str] | None = None, limit: int = 10) -> list[dict[str, Any]]:
        self.ensure_table_access(user, ["business_rules"])
        related_rule_codes = related_rule_codes or []
        with self.engine.connect() as conn:
            frame = pd.read_sql(text("SELECT * FROM business_rules ORDER BY title"), conn)
        if frame.empty:
            return []
        normalized_question = normalize_text(question)
        tokens = [token for token in re.findall(r"[a-zA-Z0-9_]+", normalized_question) if len(token) > 2]

        def score_row(row: pd.Series) -> int:
            score = 0
            if row["rule_code"] in related_rule_codes:
                score += 10
            blob = normalize_text(" ".join([
                str(row.get("title") or ""),
                str(row.get("description") or ""),
                str(row.get("origin") or ""),
                str(row.get("normative_basis") or ""),
                " ".join(row.get("keywords") or []),
            ]))
            for token in tokens:
                if token in blob:
                    score += 1
            return score

        frame["score"] = frame.apply(score_row, axis=1)
        ranked = frame.sort_values(["score", "auto_detectable", "severity", "title"], ascending=[False, False, True, True])
        ranked = ranked[ranked["score"] > 0].head(limit)
        if ranked.empty:
            ranked = frame.sort_values(["auto_detectable", "title"], ascending=[False, True]).head(limit)
        return _serialize_records(ranked)

    def search_knowledge(self, user: dict[str, Any], question: str, limit: int = 8) -> list[dict[str, Any]]:
        self.ensure_table_access(user, ["knowledge_snippets"])
        cleaned = " ".join([token for token in re.findall(r"[a-zA-Z0-9_]+", normalize_text(question)) if len(token) > 2])
        if not cleaned:
            return []
        sql = text(
            """
            SELECT snippet_uid, source_type, source_name, source_path, page_number, title, content, tags,
                   ts_rank_cd(content_tsv, plainto_tsquery('simple', :q)) AS rank
            FROM knowledge_snippets
            WHERE content_tsv @@ plainto_tsquery('simple', :q)
            ORDER BY rank DESC, source_type, source_name
            LIMIT :limit
            """
        )
        with self.engine.connect() as conn:
            frame = pd.read_sql(sql, conn, params={"q": cleaned, "limit": limit})
        if frame.empty:
            fallback_sql = text(
                """
                SELECT snippet_uid, source_type, source_name, source_path, page_number, title, content, tags, 0 AS rank
                FROM knowledge_snippets
                WHERE content ILIKE :pattern OR title ILIKE :pattern
                ORDER BY source_type, source_name
                LIMIT :limit
                """
            )
            with self.engine.connect() as conn:
                frame = pd.read_sql(fallback_sql, conn, params={"pattern": f"%{cleaned}%", "limit": limit})
        return _serialize_records(frame)

    def get_assignment_for(self, user: dict[str, Any], bank: str | None, filial: str | None, account_number: str | None) -> dict[str, Any] | None:
        self.ensure_table_access(user, ["assignments"])
        if not account_number or not bank or not filial:
            return None
        sql = text(
            """
            SELECT filial, bank, account_number, owner_name, area, email
            FROM assignments
            WHERE filial = :filial AND bank = :bank AND account_number = :account_number AND active IS TRUE
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            frame = pd.read_sql(sql, conn, params={"filial": filial, "bank": bank, "account_number": account_number})
        return _serialize_records(frame)[0] if not frame.empty else None

    def write_audit(self, question: str, parsed_filters: dict[str, Any], used_fallback: bool, response: str) -> None:
        sql = text(
            """
            INSERT INTO prompt_audit(question, parsed_filters, used_fallback, response)
            VALUES (:question, CAST(:parsed_filters AS jsonb), :used_fallback, :response)
            """
        )
        with self.engine.begin() as conn:
            conn.execute(
                sql,
                {
                    "question": question,
                    "parsed_filters": json.dumps(parsed_filters, ensure_ascii=False, default=str),
                    "used_fallback": used_fallback,
                    "response": response,
                },
            )
