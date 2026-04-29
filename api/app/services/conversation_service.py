from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db import get_engine


def _as_json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, default=str)


def _as_json_list(value: Any) -> str:
    return json.dumps(value if value is not None else [], ensure_ascii=False, default=str)


class ConversationService:
    """Persisted conversation state for robust follow-ups.

    This service stores only compact structured state. It does not store the
    full chat transcript and it is safe with multiple API workers because
    PostgreSQL is the source of truth.
    """

    def __init__(self) -> None:
        self.engine = get_engine()

    def get_state(self, username: str, conversation_id: str | None) -> dict[str, Any] | None:
        if not conversation_id:
            return None
        sql = text(
            """
            SELECT conversation_id, username, last_question, last_intent,
                   last_filters, last_entities, last_route, last_result_refs,
                   last_answer_summary, updated_at
            FROM conversation_state
            WHERE conversation_id = :conversation_id AND username = :username
            LIMIT 1
            """
        )
        try:
            with self.engine.connect() as conn:
                row = conn.execute(sql, {"conversation_id": conversation_id, "username": username}).mappings().first()
        except SQLAlchemyError:
            # Existing databases need db/migrations/005_conversation_state.sql.
            # Do not break /chat if the migration has not been applied yet.
            return None
        if not row:
            return None
        state = dict(row)
        for key in ["last_filters", "last_entities", "last_route"]:
            if state.get(key) is None:
                state[key] = {}
        if state.get("last_result_refs") is None:
            state["last_result_refs"] = []
        return state

    def save_state(
        self,
        *,
        username: str,
        conversation_id: str | None,
        last_question: str,
        last_intent: str | None,
        last_filters: dict[str, Any] | None,
        last_entities: dict[str, Any] | None,
        last_route: dict[str, Any] | None,
        last_result_refs: list[dict[str, Any]] | None,
        last_answer_summary: str | None,
    ) -> None:
        if not conversation_id:
            return
        sql = text(
            """
            INSERT INTO conversation_state (
                conversation_id, username, last_question, last_intent,
                last_filters, last_entities, last_route, last_result_refs,
                last_answer_summary, updated_at
            ) VALUES (
                :conversation_id, :username, :last_question, :last_intent,
                CAST(:last_filters AS jsonb), CAST(:last_entities AS jsonb),
                CAST(:last_route AS jsonb), CAST(:last_result_refs AS jsonb),
                :last_answer_summary, :updated_at
            )
            ON CONFLICT (conversation_id, username) DO UPDATE SET
                last_question = EXCLUDED.last_question,
                last_intent = EXCLUDED.last_intent,
                last_filters = EXCLUDED.last_filters,
                last_entities = EXCLUDED.last_entities,
                last_route = EXCLUDED.last_route,
                last_result_refs = EXCLUDED.last_result_refs,
                last_answer_summary = EXCLUDED.last_answer_summary,
                updated_at = EXCLUDED.updated_at
            """
        )
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    sql,
                    {
                        "conversation_id": conversation_id,
                        "username": username,
                        "last_question": last_question,
                        "last_intent": last_intent,
                        "last_filters": _as_json(last_filters),
                        "last_entities": _as_json(last_entities),
                        "last_route": _as_json(last_route),
                        "last_result_refs": _as_json_list(last_result_refs),
                        "last_answer_summary": (last_answer_summary or "")[:1000],
                        "updated_at": datetime.now(timezone.utc),
                    },
                )
        except SQLAlchemyError:
            return
