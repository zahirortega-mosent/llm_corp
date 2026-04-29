from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.engine import Engine

from app.config import get_settings
from app.db import get_engine
from app.utils.filters import normalize_text


_QUERY_STOPWORDS = {
    "a", "al", "algo", "ante", "aprobada", "aprobado", "bajo", "como", "con", "cual", "cuales",
    "cuando", "de", "del", "desde", "donde", "el", "ella", "ellos", "en", "entre", "es", "esta",
    "este", "esto", "estos", "fue", "ha", "hasta", "hay", "la", "las", "le", "lo", "los", "mas",
    "memoria", "mi", "no", "o", "para", "por", "que", "quien", "quienes", "se", "segun", "si",
    "sobre", "su", "sus", "tu", "un", "una", "y", "ya"
}


@dataclass(slots=True)
class InstitutionalEvidence:
    chunk_id: int
    document_id: int
    chunk_index: int
    title: str
    content: str
    source_type: str | None = None
    source_path: str | None = None
    owner_area: str | None = None
    status: str | None = None
    version: str | None = None
    checksum: str | None = None
    tags: list[str] | None = None
    allowed_groups: list[str] | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    rank: float = 0.0
    search_mode: str = "lexical"

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "chunk_index": self.chunk_index,
            "title": self.title,
            "content": self.content,
            "source_type": self.source_type,
            "source_path": self.source_path,
            "owner_area": self.owner_area,
            "status": self.status,
            "version": self.version,
            "checksum": self.checksum,
            "tags": self.tags or [],
            "allowed_groups": self.allowed_groups or [],
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "rank": self.rank,
            "search_mode": self.search_mode,
        }


class KnowledgeService:
    """Busqueda institucional hibrida.

    Reglas de seguridad del Bloque 4:
    - Por defecto solo devuelve documentos approved y chunks active.
    - No devuelve drafts en respuestas normales si REQUIRE_APPROVED=true.
    - Si pgvector no esta disponible o no esta habilitado, usa solo full-text.
    - Nunca inventa fuentes: si no hay evidencia, devuelve lista vacia.
    """

    def __init__(self, engine: Engine | None = None) -> None:
        self.engine = engine or get_engine()
        self.settings = get_settings()

    def search(
        self,
        question: str,
        user: dict[str, Any] | None = None,
        *,
        limit: int | None = None,
        owner_area: str | None = None,
        tags: list[str] | None = None,
        allowed_groups: list[str] | None = None,
        query_embedding: list[float] | None = None,
        require_approved: bool | None = None,
    ) -> list[dict[str, Any]]:
        if not self.settings.enable_institutional_memory:
            return []
        limit = int(limit or self.settings.institutional_memory_top_k)
        require_approved = self.settings.institutional_memory_require_approved if require_approved is None else require_approved

        groups = self._resolve_groups(user, allowed_groups)
        lexical = self.lexical_search(
            question,
            limit=max(limit * 4, 10),
            owner_area=owner_area,
            tags=tags,
            groups=groups,
            require_approved=require_approved,
        )
        # Fallback amplio: preguntas naturales traen palabras como "segun", "quien"
        # o "hasta cuando" que pueden hacer demasiado restrictivo plainto_tsquery.
        # Esta busqueda OR sigue filtrando approved/active/vigencia/permisos.
        lexical.extend(self.keyword_search(
            question,
            limit=max(limit * 4, 10),
            owner_area=owner_area,
            tags=tags,
            groups=groups,
            require_approved=require_approved,
        ))
        semantic = self.semantic_search(
            query_embedding,
            limit=max(limit * 4, 10),
            owner_area=owner_area,
            tags=tags,
            groups=groups,
            require_approved=require_approved,
        )
        return [item.to_dict() for item in self.merge_dedupe(lexical, semantic)[:limit]]

    def lexical_search(
        self,
        question: str,
        *,
        limit: int,
        owner_area: str | None,
        tags: list[str] | None,
        groups: list[str],
        require_approved: bool,
    ) -> list[InstitutionalEvidence]:
        cleaned = self._clean_query(question)
        if not cleaned:
            return []
        params = self._base_params(limit=limit, owner_area=owner_area, tags=tags, groups=groups, require_approved=require_approved)
        params.update({"q": cleaned, "pattern": f"%{cleaned}%"})
        sql = text(
            f"""
            SELECT c.chunk_id, c.document_id, c.chunk_index, c.content,
                   d.title, d.source_type, d.source_path, d.owner_area,
                   d.status, d.version, d.checksum,
                   COALESCE(c.tags, d.tags, '{{}}'::text[]) AS tags,
                   COALESCE(NULLIF(c.allowed_groups, '{{}}'::text[]), d.allowed_groups, '{{}}'::text[]) AS allowed_groups,
                   c.valid_from::text AS valid_from,
                   c.valid_to::text AS valid_to,
                   ts_rank_cd(c.content_tsv, plainto_tsquery('spanish', :q)) AS rank
            FROM institutional_chunks c
            JOIN institutional_documents d ON d.document_id = c.document_id
            WHERE {self._where_clause()}
              AND (
                c.content_tsv @@ plainto_tsquery('spanish', :q)
                OR c.content ILIKE :pattern
                OR d.title ILIKE :pattern
              )
            ORDER BY rank DESC, d.status, d.updated_at DESC, c.chunk_index ASC
            LIMIT :limit
            """
        )
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(sql, params).mappings().all()
        except SQLAlchemyError:
            # Migrations not applied or FTS objects missing: fail closed, not invented.
            return []
        return [self._row_to_evidence(row, search_mode="lexical") for row in rows]

    def keyword_search(
        self,
        question: str,
        *,
        limit: int,
        owner_area: str | None,
        tags: list[str] | None,
        groups: list[str],
        require_approved: bool,
    ) -> list[InstitutionalEvidence]:
        tokens = self._query_tokens(question)
        if not tokens:
            return []
        ts_query = " | ".join(tokens[:12])
        params = self._base_params(limit=limit, owner_area=owner_area, tags=tags, groups=groups, require_approved=require_approved)
        params.update({"q_or": ts_query, "title_pattern": "%" + "%".join(tokens[:4]) + "%"})
        sql = text(
            f"""
            SELECT c.chunk_id, c.document_id, c.chunk_index, c.content,
                   d.title, d.source_type, d.source_path, d.owner_area,
                   d.status, d.version, d.checksum,
                   COALESCE(c.tags, d.tags, '{{}}'::text[]) AS tags,
                   COALESCE(NULLIF(c.allowed_groups, '{{}}'::text[]), d.allowed_groups, '{{}}'::text[]) AS allowed_groups,
                   c.valid_from::text AS valid_from,
                   c.valid_to::text AS valid_to,
                   ts_rank_cd(c.content_tsv, to_tsquery('spanish', :q_or)) AS rank
            FROM institutional_chunks c
            JOIN institutional_documents d ON d.document_id = c.document_id
            WHERE {self._where_clause()}
              AND (
                c.content_tsv @@ to_tsquery('spanish', :q_or)
                OR lower(d.title) LIKE lower(:title_pattern)
              )
            ORDER BY rank DESC, d.status, d.updated_at DESC, c.chunk_index ASC
            LIMIT :limit
            """
        )
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(sql, params).mappings().all()
        except SQLAlchemyError:
            return []
        return [self._row_to_evidence(row, search_mode="lexical_keyword") for row in rows]

    def semantic_search(
        self,
        query_embedding: list[float] | None,
        *,
        limit: int,
        owner_area: str | None,
        tags: list[str] | None,
        groups: list[str],
        require_approved: bool,
    ) -> list[InstitutionalEvidence]:
        if not query_embedding or not self.settings.institutional_memory_enable_vector:
            return []
        if not self._vector_available():
            return []
        params = self._base_params(limit=limit, owner_area=owner_area, tags=tags, groups=groups, require_approved=require_approved)
        params["embedding"] = "[" + ",".join(str(float(value)) for value in query_embedding) + "]"
        sql = text(
            f"""
            SELECT c.chunk_id, c.document_id, c.chunk_index, c.content,
                   d.title, d.source_type, d.source_path, d.owner_area,
                   d.status, d.version, d.checksum,
                   COALESCE(c.tags, d.tags, '{{}}'::text[]) AS tags,
                   COALESCE(NULLIF(c.allowed_groups, '{{}}'::text[]), d.allowed_groups, '{{}}'::text[]) AS allowed_groups,
                   c.valid_from::text AS valid_from,
                   c.valid_to::text AS valid_to,
                   (1 - (c.embedding_vector <=> CAST(:embedding AS vector))) AS rank
            FROM institutional_chunks c
            JOIN institutional_documents d ON d.document_id = c.document_id
            WHERE {self._where_clause()}
              AND c.embedding_vector IS NOT NULL
            ORDER BY c.embedding_vector <=> CAST(:embedding AS vector)
            LIMIT :limit
            """
        )
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(sql, params).mappings().all()
        except SQLAlchemyError:
            return []
        return [self._row_to_evidence(row, search_mode="semantic") for row in rows]

    def merge_dedupe(
        self,
        lexical: Iterable[InstitutionalEvidence],
        semantic: Iterable[InstitutionalEvidence],
    ) -> list[InstitutionalEvidence]:
        merged: dict[int, InstitutionalEvidence] = {}
        for item in list(lexical) + list(semantic):
            current = merged.get(item.chunk_id)
            if current is None:
                merged[item.chunk_id] = item
                continue
            combined = max(float(current.rank or 0), float(item.rank or 0)) + 0.15
            current.rank = combined
            current.search_mode = "hybrid"
        return sorted(merged.values(), key=lambda row: (row.rank, row.status == "approved"), reverse=True)

    def _query_tokens(self, value: str) -> list[str]:
        normalized = normalize_text(value)
        tokens = []
        for token in re.findall(r"[a-zA-Z0-9]+", normalized):
            if len(token) <= 1 or token in _QUERY_STOPWORDS:
                continue
            # to_tsquery requiere tokens simples; regex ya evita operadores como :, &, |.
            tokens.append(token)
        seen: set[str] = set()
        unique: list[str] = []
        for token in tokens:
            if token not in seen:
                seen.add(token)
                unique.append(token)
        return unique

    def _clean_query(self, value: str) -> str:
        return " ".join(self._query_tokens(value)[:24])

    def _resolve_groups(self, user: dict[str, Any] | None, explicit_groups: list[str] | None) -> list[str]:
        values: list[str] = []
        for source in [explicit_groups, (user or {}).get("groups"), (user or {}).get("role_names"), (user or {}).get("roles")]:
            if not source:
                continue
            if isinstance(source, str):
                values.extend([part.strip() for part in source.split(",") if part.strip()])
            elif isinstance(source, list):
                for item in source:
                    if isinstance(item, dict):
                        name = item.get("group_name") or item.get("role_name") or item.get("name")
                    else:
                        name = item
                    if name:
                        values.append(str(name).strip())
        return sorted({item for item in values if item})

    def _base_params(
        self,
        *,
        limit: int,
        owner_area: str | None,
        tags: list[str] | None,
        groups: list[str],
        require_approved: bool,
    ) -> dict[str, Any]:
        return {
            "limit": limit,
            "owner_area": owner_area,
            "has_owner_area": bool(owner_area),
            "tags": tags or [],
            "has_tags": bool(tags),
            "groups": groups or [],
            "has_groups": bool(groups),
            "require_approved": bool(require_approved),
        }

    def _where_clause(self) -> str:
        return """
            c.active IS TRUE
            AND (:require_approved IS FALSE OR d.status = 'approved')
            AND (c.valid_from IS NULL OR c.valid_from <= CURRENT_DATE)
            AND (c.valid_to IS NULL OR c.valid_to >= CURRENT_DATE)
            AND (:has_owner_area IS FALSE OR c.area = :owner_area OR d.owner_area = :owner_area)
            AND (:has_tags IS FALSE OR c.tags && CAST(:tags AS text[]) OR d.tags && CAST(:tags AS text[]))
            AND (
                :has_groups IS FALSE
                OR COALESCE(cardinality(c.allowed_groups), 0) = 0
                OR c.allowed_groups && CAST(:groups AS text[])
                OR d.allowed_groups && CAST(:groups AS text[])
            )
        """

    def _row_to_evidence(self, row: Any, *, search_mode: str) -> InstitutionalEvidence:
        mapping = dict(row)
        return InstitutionalEvidence(
            chunk_id=int(mapping.get("chunk_id")),
            document_id=int(mapping.get("document_id")),
            chunk_index=int(mapping.get("chunk_index") or 0),
            title=str(mapping.get("title") or "Documento institucional"),
            content=str(mapping.get("content") or ""),
            source_type=mapping.get("source_type"),
            source_path=mapping.get("source_path"),
            owner_area=mapping.get("owner_area"),
            status=mapping.get("status"),
            version=mapping.get("version"),
            checksum=mapping.get("checksum"),
            tags=list(mapping.get("tags") or []),
            allowed_groups=list(mapping.get("allowed_groups") or []),
            valid_from=mapping.get("valid_from"),
            valid_to=mapping.get("valid_to"),
            rank=float(mapping.get("rank") or 0.0),
            search_mode=search_mode,
        )

    def _vector_available(self) -> bool:
        try:
            with self.engine.connect() as conn:
                exists = conn.execute(
                    text(
                        """
                        SELECT EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_name = 'institutional_chunks'
                              AND column_name = 'embedding_vector'
                        )
                        """
                    )
                ).scalar_one()
            return bool(exists)
        except SQLAlchemyError:
            return False
