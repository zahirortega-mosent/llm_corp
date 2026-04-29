#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import html.parser
import os
import re
from pathlib import Path
from typing import Iterable

from sqlalchemy import create_engine, text


SUPPORTED_SIMPLE = {".md", ".markdown", ".txt", ".csv", ".html", ".htm"}
SOURCE_TYPE_BY_EXT = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "txt",
    ".csv": "csv",
    ".html": "html",
    ".htm": "html",
    ".pdf": "pdf",
    ".docx": "docx",
}


class HTMLTextExtractor(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = data.strip()
        if value:
            self.parts.append(value)

    def text(self) -> str:
        return "\n".join(self.parts)


def database_url() -> str:
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "conciliador_mvp")
    user = os.getenv("POSTGRES_USER", "conciliador")
    password = os.getenv("POSTGRES_PASSWORD", "conciliador_local_2026")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def read_csv_text(path: Path) -> str:
    rows: list[str] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            rows.append(" | ".join(cell.strip() for cell in row if cell is not None))
    return "\n".join(rows)


def read_html_text(path: Path) -> str:
    parser = HTMLTextExtractor()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    return parser.text()


def read_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except Exception as exc:  # pragma: no cover - depends on optional runtime package
        raise RuntimeError("PDF requiere pypdf instalado. El api/requirements.txt actual ya lo incluye; reinstala dependencias si falta.") from exc
    reader = PdfReader(str(path))
    pages: list[str] = []
    for index, page in enumerate(reader.pages, start=1):
        text_value = page.extract_text() or ""
        if text_value.strip():
            pages.append(f"[pagina {index}]\n{text_value}")
    return "\n\n".join(pages)


def extract_text(path: Path) -> tuple[str, str]:
    ext = path.suffix.lower()
    source_type = SOURCE_TYPE_BY_EXT.get(ext, "other")
    if ext in {".md", ".markdown", ".txt"}:
        return normalize_text(path.read_text(encoding="utf-8", errors="replace")), source_type
    if ext == ".csv":
        return normalize_text(read_csv_text(path)), source_type
    if ext in {".html", ".htm"}:
        return normalize_text(read_html_text(path)), source_type
    if ext == ".pdf":
        return normalize_text(read_pdf_text(path)), source_type
    if ext == ".docx":
        raise RuntimeError("DOCX requiere dependencia extra (python-docx) no incluida por default para no hacer pesada la instalacion.")
    raise RuntimeError(f"Formato no soportado para extraccion simple: {ext or 'sin extension'}")


def chunk_text(text_value: str, chunk_size: int, overlap: int) -> list[str]:
    text_value = normalize_text(text_value)
    if not text_value:
        return []
    if chunk_size <= 0:
        raise ValueError("chunk_size debe ser mayor a cero")
    overlap = max(0, min(overlap, chunk_size - 1))
    chunks: list[str] = []
    start = 0
    while start < len(text_value):
        end = min(len(text_value), start + chunk_size)
        chunk = text_value[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text_value):
            break
        start = end - overlap
    return chunks


def iter_input_files(input_path: Path) -> Iterable[Path]:
    if input_path.is_file():
        yield input_path
        return
    for path in sorted(input_path.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_SIMPLE.union({".pdf"}):
            yield path


def insert_document(
    *,
    engine,
    path: Path,
    title: str,
    owner_area: str | None,
    tags: list[str],
    allowed_groups: list[str],
    status: str,
    created_by: str | None,
    version: str | None,
    chunk_size: int,
    chunk_overlap: int,
) -> tuple[int, int, str]:
    checksum = sha256_file(path)
    content, source_type = extract_text(path)
    chunks = chunk_text(content, chunk_size=chunk_size, overlap=chunk_overlap)
    if not chunks:
        raise RuntimeError(f"No se extrajo texto util de {path}")

    with engine.begin() as conn:
        document_id = conn.execute(
            text(
                """
                INSERT INTO institutional_documents (
                    title, source_type, source_path, owner_area, status, version,
                    checksum, tags, allowed_groups, created_by, approved_by, approved_at
                ) VALUES (
                    :title, :source_type, :source_path, :owner_area, :status, :version,
                    :checksum, :tags, :allowed_groups, :created_by,
                    CASE WHEN :status = 'approved' THEN :created_by ELSE NULL END,
                    CASE WHEN :status = 'approved' THEN now() ELSE NULL END
                )
                RETURNING document_id
                """
            ),
            {
                "title": title,
                "source_type": source_type,
                "source_path": str(path),
                "owner_area": owner_area,
                "status": status,
                "version": version,
                "checksum": checksum,
                "tags": tags,
                "allowed_groups": allowed_groups,
                "created_by": created_by,
            },
        ).scalar_one()

        for idx, chunk in enumerate(chunks):
            conn.execute(
                text(
                    """
                    INSERT INTO institutional_chunks (
                        document_id, chunk_index, content, tags, area, allowed_groups, active
                    ) VALUES (
                        :document_id, :chunk_index, :content, :tags, :area, :allowed_groups, true
                    )
                    """
                ),
                {
                    "document_id": document_id,
                    "chunk_index": idx,
                    "content": chunk,
                    "tags": tags,
                    "area": owner_area,
                    "allowed_groups": allowed_groups,
                },
            )
    return int(document_id), len(chunks), checksum


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingesta real de documentos para memoria institucional")
    parser.add_argument("--input", required=True, help="Archivo o carpeta local a ingerir")
    parser.add_argument("--title", required=True, help="Titulo real del documento")
    parser.add_argument("--owner-area", default=None, help="Area propietaria real del documento")
    parser.add_argument("--tags", nargs="*", default=[], help="Tags reales, separados por espacios")
    parser.add_argument("--allowed-groups", nargs="*", default=[], help="Grupos autorizados reales, separados por espacios")
    parser.add_argument("--status", choices=["draft", "approved", "archived"], default="draft")
    parser.add_argument("--created-by", default=os.getenv("USER") or "etl")
    parser.add_argument("--version", default=None)
    parser.add_argument("--chunk-size", type=int, default=int(os.getenv("INSTITUTIONAL_MEMORY_CHUNK_SIZE", "1200")))
    parser.add_argument("--chunk-overlap", type=int, default=int(os.getenv("INSTITUTIONAL_MEMORY_CHUNK_OVERLAP", "150")))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        raise SystemExit(f"No existe la ruta de entrada: {input_path}")
    engine = create_engine(database_url(), pool_pre_ping=True, future=True)

    files = list(iter_input_files(input_path))
    if not files:
        raise SystemExit("No hay archivos soportados para ingestar en la ruta indicada.")

    for path in files:
        title = args.title if input_path.is_file() else f"{args.title} - {path.name}"
        document_id, chunk_count, checksum = insert_document(
            engine=engine,
            path=path,
            title=title,
            owner_area=args.owner_area,
            tags=args.tags,
            allowed_groups=args.allowed_groups,
            status=args.status,
            created_by=args.created_by,
            version=args.version,
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
        )
        print(f"document_id={document_id} chunks={chunk_count} status={args.status} checksum={checksum} path={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
