from __future__ import annotations

import json
import re
from typing import Any

import pandas as pd
from fastapi import HTTPException, status
from sqlalchemy import text

from app.db import get_engine
from app.utils.filters import normalize_period, normalize_text


def _serialize_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return frame.where(pd.notnull(frame), None).to_dict(orient="records")


def _scalar(value: Any) -> Any:
    return value.item() if hasattr(value, "item") else value


class QueryService:
    def __init__(self) -> None:
        self.engine = get_engine()

    def _normalize_period(self, period: str | None) -> str | None:
        return normalize_period(period)

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
            accounts = pd.read_sql(text("SELECT DISTINCT account_number FROM bank_movements WHERE account_number IS NOT NULL ORDER BY account_number LIMIT 5000"), conn)
        return {
            "periods": [str(v)[:10] for v in periods["period"].tolist()],
            "banks": banks["bank"].tolist(),
            "filiales": filiales["filial"].tolist(),
            "accounts_sample": accounts["account_number"].tolist(),
        }

    def get_available_periods_summary(self, user: dict[str, Any], scope: dict[str, Any] | None = None) -> dict[str, Any]:
        self.ensure_table_access(user, ["bank_movements"])
        sql = text(
            """
            SELECT period,
                   COUNT(*) AS movements,
                   COUNT(DISTINCT bank) AS banks,
                   COUNT(DISTINCT filial) AS filiales,
                   COUNT(DISTINCT account_number) AS accounts,
                   MIN(movement_date) AS min_movement_date,
                   MAX(movement_date) AS max_movement_date
            FROM bank_movements
            WHERE period IS NOT NULL
            GROUP BY period
            ORDER BY period
            """
        )
        with self.engine.connect() as conn:
            frame = pd.read_sql(sql, conn)
        rows = _serialize_records(frame)
        return {
            "periods": [str(row.get("period"))[:10] for row in rows],
            "rows": rows,
        }

    def build_where(self, filters: dict[str, Any], table_alias: str = "") -> tuple[str, dict[str, Any]]:
        prefix = f"{table_alias}." if table_alias else ""
        conditions = []
        params: dict[str, Any] = {}
        period = self._normalize_period(filters.get("period"))
        if period:
            conditions.append(f"{prefix}period = :period")
            params["period"] = period
        periods = [self._normalize_period(item) for item in filters.get("periods", []) if self._normalize_period(item)]
        if periods and not period:
            conditions.append(f"{prefix}period = ANY(:periods)")
            params["periods"] = periods
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

    def get_summary(self, user: dict[str, Any], filters: dict[str, Any], scope: dict[str, Any] | None = None) -> dict[str, Any]:
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
        return {key: _scalar(value) for key, value in {**movements, **statements, **incidents}.items()}

    def get_movements(
        self,
        user: dict[str, Any],
        filters: dict[str, Any],
        scope: dict[str, Any] | None = None,
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

    def search_movements_text(self, user: dict[str, Any], filters: dict[str, Any], query: str, scope: dict[str, Any] | None = None, limit: int = 50) -> list[dict[str, Any]]:
        self.ensure_table_access(user, ["bank_movements"])
        where, params = self.build_where(filters)
        cleaned = " ".join(token for token in re.findall(r"[a-zA-Z0-9_]+", normalize_text(query)) if len(token) > 1)
        if not cleaned:
            return []
        extra = " AND " if where else "WHERE "
        params.update({"q": cleaned, "pattern": f"%{cleaned}%", "limit": limit})
        sql = text(
            f"""
            SELECT movement_uid, bank, filial, account_number, period, movement_date, settlement_date,
                   reference, folio, description, concept, movement_type, amount, deposit, withdrawal,
                   balance, reconciled, source_filename, source_hash,
                   ts_rank_cd(
                       to_tsvector('spanish', coalesce(description,'') || ' ' || coalesce(concept,'') || ' ' || coalesce(reference,'')),
                       plainto_tsquery('spanish', :q)
                   ) AS rank
            FROM bank_movements {where}
            {extra}(
                to_tsvector('spanish', coalesce(description,'') || ' ' || coalesce(concept,'') || ' ' || coalesce(reference,'')) @@ plainto_tsquery('spanish', :q)
                OR description ILIKE :pattern
                OR concept ILIKE :pattern
                OR reference ILIKE :pattern
            )
            ORDER BY rank DESC, movement_date DESC NULLS LAST
            LIMIT :limit
            """
        )
        with self.engine.connect() as conn:
            frame = pd.read_sql(sql, conn, params=params)
        return _serialize_records(frame)

    def get_movements_breakdown(self, user: dict[str, Any], filters: dict[str, Any], group_by: str, scope: dict[str, Any] | None = None, limit: int = 25) -> list[dict[str, Any]]:
        self.ensure_table_access(user, ["bank_movements"])
        allowed = {"bank", "filial", "account_number", "period"}
        if group_by not in allowed:
            raise ValueError(f"group_by no permitido para movimientos: {group_by}")
        where, params = self.build_where(filters)
        params["limit"] = limit
        sql = text(
            f"""
            SELECT {group_by},
                   COUNT(*) AS movements,
                   COALESCE(SUM(deposit), 0) AS total_deposits,
                   COALESCE(SUM(withdrawal), 0) AS total_withdrawals,
                   COUNT(*) FILTER (WHERE reconciled IS TRUE) AS reconciled_movements,
                   COUNT(*) FILTER (WHERE reconciled IS FALSE OR reconciled IS NULL) AS unreconciled_movements,
                   COUNT(DISTINCT account_number) AS accounts
            FROM bank_movements {where}
            GROUP BY {group_by}
            ORDER BY COUNT(*) DESC, COALESCE(SUM(deposit), 0) + COALESCE(SUM(withdrawal), 0) DESC, {group_by}
            LIMIT :limit
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

    def get_files_for_statement_uids(self, user: dict[str, Any], statement_uids: list[str], scope: dict[str, Any] | None = None, limit: int = 25) -> list[dict[str, Any]]:
        self.ensure_table_access(user, ["bank_statements"])
        if not statement_uids:
            return []
        sql = text(
            """
            SELECT statement_uid, source_filename, source_hash, bank, filial, account_number, period,
                   period_start, period_end, opening_balance, closing_balance, total_deposits,
                   total_withdrawals, statement_balance_ok, header_only
            FROM bank_statements
            WHERE statement_uid = ANY(:statement_uids)
            ORDER BY period DESC NULLS LAST, bank, filial, account_number
            LIMIT :limit
            """
        )
        with self.engine.connect() as conn:
            frame = pd.read_sql(sql, conn, params={"statement_uids": statement_uids, "limit": limit})
        return _serialize_records(frame)

    def get_incidents(self, user: dict[str, Any], filters: dict[str, Any], limit: int = 100, aggregated: bool = False, scope: dict[str, Any] | None = None) -> list[dict[str, Any]]:
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

    def get_incidents_breakdown(self, user: dict[str, Any], filters: dict[str, Any], group_by: str, scope: dict[str, Any] | None = None, limit: int = 25) -> list[dict[str, Any]]:
        self.ensure_table_access(user, ["incidents"])
        allowed = {"bank", "filial", "account_number", "period", "rule_code", "severity"}
        if group_by not in allowed:
            raise ValueError(f"group_by no permitido para incidencias: {group_by}")
        where, params = self.build_where(filters)
        params["limit"] = limit
        sql = text(
            f"""
            SELECT {group_by},
                   COUNT(*) AS incidents,
                   COUNT(*) FILTER (WHERE severity = 'critica') AS critical_incidents,
                   COUNT(*) FILTER (WHERE severity = 'alta') AS high_incidents,
                   COUNT(*) FILTER (WHERE severity = 'media') AS medium_incidents,
                   COUNT(*) FILTER (WHERE severity = 'baja') AS low_incidents
            FROM incidents {where}
            GROUP BY {group_by}
            ORDER BY COUNT(*) DESC, {group_by}
            LIMIT :limit
            """
        )
        with self.engine.connect() as conn:
            frame = pd.read_sql(sql, conn, params=params)
        return _serialize_records(frame)

    def get_incidents_for_movements(self, user: dict[str, Any], movement_uids: list[str], scope: dict[str, Any] | None = None, limit: int = 100) -> list[dict[str, Any]]:
        self.ensure_table_access(user, ["incidents"])
        if not movement_uids:
            return []
        sql = text(
            """
            SELECT incident_uid, rule_code, period, bank, filial, account_number, severity, title,
                   description, source_filename, suggested_owner, evidence
            FROM incidents
            WHERE evidence::text ILIKE ANY(:patterns)
            ORDER BY CASE severity WHEN 'critica' THEN 1 WHEN 'alta' THEN 2 WHEN 'media' THEN 3 ELSE 4 END,
                     detected_at DESC
            LIMIT :limit
            """
        )
        patterns = [f"%{uid}%" for uid in movement_uids]
        with self.engine.connect() as conn:
            frame = pd.read_sql(sql, conn, params={"patterns": patterns, "limit": limit})
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

    def get_review_candidates(self, user: dict[str, Any], filters: dict[str, Any], scope: dict[str, Any] | None = None, limit: int = 10) -> list[dict[str, Any]]:
        self.ensure_table_access(user, ["bank_movements", "bank_statements", "incidents"])
        mov_where, mov_params = self.build_where(filters, "m")
        inc_where, inc_params = self.build_where(filters, "i")
        stmt_where, stmt_params = self.build_where(filters, "s")
        params = {**{f"m_{k}": v for k, v in mov_params.items()}, **{f"i_{k}": v for k, v in inc_params.items()}, **{f"s_{k}": v for k, v in stmt_params.items()}, "limit": limit}
        # Reescribe nombres de parametros por alias para evitar colisiones entre CTEs.
        for original, prefixed in [(mov_params, "m"), (inc_params, "i"), (stmt_params, "s")]:
            pass
        mov_where = self._prefix_params(mov_where, "m", mov_params)
        inc_where = self._prefix_params(inc_where, "i", inc_params)
        stmt_where = self._prefix_params(stmt_where, "s", stmt_params)
        sql = text(
            f"""
            WITH movement_scores AS (
                SELECT m.bank, m.filial, m.account_number,
                       COUNT(*) AS movements,
                       COUNT(*) FILTER (WHERE m.reconciled IS FALSE OR m.reconciled IS NULL) AS unreconciled_movements,
                       COALESCE(SUM(ABS(COALESCE(m.amount, COALESCE(m.deposit,0) - COALESCE(m.withdrawal,0)))), 0) AS movement_amount
                FROM bank_movements m {mov_where}
                GROUP BY m.bank, m.filial, m.account_number
            ), incident_scores AS (
                SELECT i.bank, i.filial, i.account_number,
                       COUNT(*) AS incidents,
                       COUNT(*) FILTER (WHERE i.severity = 'critica') AS critical_incidents,
                       COUNT(*) FILTER (WHERE i.severity = 'alta') AS high_incidents,
                       COUNT(*) FILTER (WHERE i.severity = 'media') AS medium_incidents
                FROM incidents i {inc_where}
                GROUP BY i.bank, i.filial, i.account_number
            ), statement_scores AS (
                SELECT s.bank, s.filial, s.account_number,
                       COUNT(*) FILTER (WHERE s.statement_balance_ok IS FALSE) AS balance_mismatches
                FROM bank_statements s {stmt_where}
                GROUP BY s.bank, s.filial, s.account_number
            )
            SELECT COALESCE(m.bank, i.bank, s.bank) AS bank,
                   COALESCE(m.filial, i.filial, s.filial) AS filial,
                   COALESCE(m.account_number, i.account_number, s.account_number) AS account_number,
                   COALESCE(m.movements, 0) AS movements,
                   COALESCE(i.incidents, 0) AS incidents,
                   COALESCE(i.critical_incidents, 0) AS critical_incidents,
                   COALESCE(i.high_incidents, 0) AS high_incidents,
                   COALESCE(i.medium_incidents, 0) AS medium_incidents,
                   COALESCE(m.unreconciled_movements, 0) AS unreconciled_movements,
                   COALESCE(s.balance_mismatches, 0) AS balance_mismatches,
                   COALESCE(m.movement_amount, 0) AS amount_at_risk,
                   (
                       COALESCE(i.critical_incidents, 0) * 100
                     + COALESCE(i.high_incidents, 0) * 50
                     + COALESCE(i.medium_incidents, 0) * 15
                     + COALESCE(m.unreconciled_movements, 0) * 10
                     + COALESCE(s.balance_mismatches, 0) * 40
                     + LN(1 + COALESCE(m.movement_amount, 0)) * 5
                   )::numeric(18,2) AS review_score
            FROM movement_scores m
            FULL OUTER JOIN incident_scores i
              ON i.bank = m.bank AND i.filial = m.filial AND i.account_number = m.account_number
            FULL OUTER JOIN statement_scores s
              ON s.bank = COALESCE(m.bank, i.bank)
             AND s.filial = COALESCE(m.filial, i.filial)
             AND s.account_number = COALESCE(m.account_number, i.account_number)
            ORDER BY review_score DESC, critical_incidents DESC, high_incidents DESC
            LIMIT :limit
            """
        )
        with self.engine.connect() as conn:
            frame = pd.read_sql(sql, conn, params=params)
        return _serialize_records(frame)

    def _prefix_params(self, where_sql: str, prefix: str, params: dict[str, Any]) -> str:
        for key in sorted(params.keys(), key=len, reverse=True):
            where_sql = where_sql.replace(f":{key}", f":{prefix}_{key}")
        return where_sql

    def get_account_profile(self, user: dict[str, Any], filters: dict[str, Any], scope: dict[str, Any] | None = None, limit: int = 10) -> dict[str, Any]:
        account_number = filters.get("account_number")
        if not account_number:
            return {"profile": None, "recent_movements": [], "incidents": []}
        scoped_filters = dict(filters)
        scoped_filters["account_number"] = str(account_number)
        summary = self.get_summary(user, scoped_filters)
        recent_movements = self.get_movements(user, scoped_filters, limit=limit, sort_mode="recent")
        incident_summary = self.get_incidents(user, scoped_filters, limit=limit, aggregated=True)
        metadata_where, params = self.build_where(scoped_filters)
        sql = text(
            f"""
            SELECT MIN(bank) AS bank,
                   MIN(filial) AS filial,
                   account_number,
                   string_agg(DISTINCT to_char(period, 'YYYY-MM'), ', ' ORDER BY to_char(period, 'YYYY-MM')) AS periods
            FROM bank_movements {metadata_where}
            GROUP BY account_number
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            frame = pd.read_sql(sql, conn, params=params)
        profile = _serialize_records(frame)[0] if not frame.empty else {"account_number": account_number}
        profile.update(summary)
        profile["amount_at_risk"] = abs(float(summary.get("total_deposits") or 0)) + abs(float(summary.get("total_withdrawals") or 0))
        return {"profile": profile, "recent_movements": recent_movements, "incidents": incident_summary}

    def get_relevant_rules(self, user: dict[str, Any], question: str, scope: dict[str, Any] | None = None, rule_codes: list[str] | None = None, related_rule_codes: list[str] | None = None, limit: int = 10) -> list[dict[str, Any]]:
        self.ensure_table_access(user, ["business_rules"])
        related_rule_codes = related_rule_codes or rule_codes or []
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

    def write_audit(
        self,
        question: str,
        parsed_filters: dict[str, Any],
        used_fallback: bool,
        response: str,
        route: dict[str, Any] | None = None,
        tools_used: list[str] | None = None,
        model_used: str | None = None,
    ) -> None:
        sql = text(
            """
            INSERT INTO prompt_audit(question, parsed_filters, used_fallback, response)
            VALUES (:question, CAST(:parsed_filters AS jsonb), :used_fallback, :response)
            """
        )
        audit_filters = dict(parsed_filters or {})
        if route:
            audit_filters["route"] = route
        if tools_used:
            audit_filters["tools_used"] = tools_used
        if model_used:
            audit_filters["model_used"] = model_used
        with self.engine.begin() as conn:
            conn.execute(
                sql,
                {
                    "question": question,
                    "parsed_filters": json.dumps(audit_filters, ensure_ascii=False, default=str),
                    "used_fallback": used_fallback,
                    "response": response,
                },
            )
