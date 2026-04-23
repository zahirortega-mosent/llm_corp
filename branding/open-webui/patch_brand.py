from pathlib import Path
import os

BRAND = os.environ.get("BRAND_NAME", "Mosent Group")

ROOTS = [
    Path("/app/backend/open_webui"),
    Path("/app/backend/open_webui/static"),
]

EXTENSIONS = {".js", ".html", ".css", ".json", ".svg", ".txt", ".map"}

REPLACEMENTS = [
    (f"{BRAND} (Open WebUI)", BRAND),
    ("Open WebUI", BRAND),
]

patched = []

for root in ROOTS:
    if not root.exists():
        continue

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in EXTENSIONS:
            continue

        try:
            original = path.read_text(encoding="utf-8")
        except Exception:
            continue

        updated = original
        for old, new in REPLACEMENTS:
            updated = updated.replace(old, new)

        if updated != original:
            path.write_text(updated, encoding="utf-8")
            patched.append(str(path))

print(f"[OK] patched {len(patched)} files")
for p in patched[:50]:
    print(p)
