import hashlib
import zipfile
from pathlib import Path
from typing import Iterable, List

from pypdf import PdfReader


ALLOWED_SUFFIXES = {'.py', '.php', '.js', '.ts', '.tsx', '.jsx', '.md', '.json', '.yml', '.yaml', '.sql'}
INCLUDE_MARKERS = ('app/Http/Controllers', 'app/Services', 'app/Models', 'database/migrations', 'routes', 'README', 'src', 'backend', 'api', 'etl')


def _chunk_text(text: str, chunk_size: int = 1800, overlap: int = 200) -> List[str]:
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, 0)
    return [chunk for chunk in chunks if chunk]


def _make_uid(*parts: str) -> str:
    material = '|'.join(parts)
    return hashlib.sha256(material.encode('utf-8')).hexdigest()


def load_pdf_snippets(pdf_path: str | Path) -> List[dict]:
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        return []
    reader = PdfReader(str(pdf_path))
    snippets = []
    for index, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or '').strip()
        if not text:
            continue
        snippets.append({'snippet_uid': _make_uid('pdf', str(pdf_path), str(index)), 'source_type': 'pdf', 'source_name': pdf_path.name, 'source_path': str(pdf_path), 'page_number': index, 'title': f'{pdf_path.name} - página {index}', 'content': text, 'tags': ['conciliador', 'pdf', f'pagina_{index}']})
    return snippets


def _ensure_source_tree(source_path: str | Path, extraction_dir: str | Path) -> Path | None:
    source_path = Path(source_path)
    extraction_dir = Path(extraction_dir)
    if source_path.exists() and source_path.is_dir():
        return source_path
    if source_path.exists() and source_path.suffix.lower() == '.zip':
        extraction_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(source_path, 'r') as zf:
            zf.extractall(extraction_dir)
        folders = [p for p in extraction_dir.iterdir() if p.is_dir()]
        return folders[0] if folders else extraction_dir
    return None


def iter_code_roots(source_locations: Iterable[str | Path], extraction_root: str | Path) -> list[Path]:
    extraction_root = Path(extraction_root)
    roots = []
    for raw in source_locations:
        path = Path(raw)
        if not path.exists():
            continue
        if path.is_dir() and path.name == 'codebases':
            for child in path.iterdir():
                if child.is_dir() or child.suffix.lower() == '.zip':
                    resolved = _ensure_source_tree(child, extraction_root / child.stem)
                    if resolved is not None:
                        roots.append(resolved)
        else:
            resolved = _ensure_source_tree(path, extraction_root / path.stem)
            if resolved is not None:
                roots.append(resolved)
    return roots


def load_code_snippets(source_locations: Iterable[str | Path], extraction_dir: str | Path) -> List[dict]:
    roots = iter_code_roots(source_locations, extraction_dir)
    snippets: List[dict] = []
    for root in roots:
        for path in root.rglob('*'):
            if not path.is_file() or path.suffix.lower() not in ALLOWED_SUFFIXES:
                continue
            posix = path.as_posix()
            if not any(marker.lower() in posix.lower() for marker in INCLUDE_MARKERS):
                continue
            try:
                content = path.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                try:
                    content = path.read_text(encoding='latin-1')
                except Exception:
                    continue
            for idx, chunk in enumerate(_chunk_text(content), start=1):
                tags = [tag for tag in path.parts if tag not in {root.name, '.'}]
                snippets.append({'snippet_uid': _make_uid('code', posix, str(idx)), 'source_type': 'code', 'source_name': path.name, 'source_path': posix, 'page_number': None, 'title': f'{path.name} #{idx}', 'content': chunk, 'tags': tags[:10]})
    return snippets


def load_all_knowledge(pdf_path: str | Path, source_code_locations: Iterable[str | Path], extraction_dir: str | Path) -> List[dict]:
    snippets = []
    snippets.extend(load_pdf_snippets(pdf_path))
    snippets.extend(load_code_snippets(source_code_locations, extraction_dir))
    return snippets
