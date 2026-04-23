import re
from typing import Any
from urllib.parse import quote_plus, urlparse

import requests
from sqlalchemy import text

from app.config import get_settings
from app.db import get_engine
from app.utils.filters import normalize_text

STOPWORDS = {
    "como", "para", "donde", "cuando", "desde", "hasta", "sobre", "segun", "nuestro", "nuestra",
    "datos", "internos", "empresa", "corporativo", "banco", "cuenta", "cuentas", "monto", "montos",
    "movimiento", "movimientos", "filial", "periodo", "periodos", "enero", "febrero", "marzo", "abril",
    "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
}


class WebSearchService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.engine = get_engine()

    def sanitize_query(self, question: str) -> str:
        normalized = normalize_text(question)
        normalized = re.sub(r"\b\d[\d\-\./,:]*\b", " ", normalized)
        normalized = re.sub(r"\b[a-z]{0,2}\d+[a-z\d]*\b", " ", normalized)
        tokens = [token for token in re.findall(r"[a-záéíóúñ]{3,}", normalized) if token not in STOPWORDS]
        tokens = [token for token in tokens if token not in set(self.settings.outbound_blocklist)]
        if not tokens:
            return self.settings.outbound_default_concepts_query
        query = " ".join(tokens[:8])
        return query.strip() or self.settings.outbound_default_concepts_query

    def search_concepts(self, question: str, username: str, limit: int | None = None) -> tuple[str, list[dict[str, Any]]]:
        limit = limit or self.settings.web_search_result_count
        query = self.sanitize_query(question)
        url = self.settings.searxng_query_url.replace("<query>", quote_plus(query))
        response = requests.get(url, timeout=self.settings.web_loader_timeout)
        response.raise_for_status()
        payload = response.json()
        results = []
        allowlist = set(self.settings.domain_allowlist)
        for item in payload.get("results", []):
            link = item.get("url") or item.get("link")
            domain = urlparse(link).netloc.lower() if link else ""
            if allowlist and domain not in allowlist:
                continue
            results.append(
                {
                    "title": item.get("title"),
                    "url": link,
                    "domain": domain,
                    "content": item.get("content") or item.get("snippet") or "",
                    "engine": item.get("engine"),
                }
            )
            if len(results) >= limit:
                break
        self.audit_search(username=username, original_question=question, sanitized_query=query, result_count=len(results))
        return query, results

    def audit_search(self, username: str, original_question: str, sanitized_query: str, result_count: int) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO web_search_audit(username, original_question, sanitized_query, result_count)
                    VALUES (:username, :original_question, :sanitized_query, :result_count)
                    """
                ),
                {
                    "username": username,
                    "original_question": original_question,
                    "sanitized_query": sanitized_query,
                    "result_count": result_count,
                },
            )
