# Aplicar Bloque 4 - Memoria institucional

Desde la raiz del proyecto:

```bash
cd ~/proyectos_llm/llm_corp
```

## 1. Backup recomendado

```bash
mkdir -p ~/Respaldos/llm_corp
BACKUP_DIR=~/Respaldos/llm_corp/backup_pre_bloque4_$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"
cp -a api db etl docs scripts tests .env .env.example "$BACKUP_DIR" 2>/dev/null || true
```

## 2. Aplicar ZIP

```bash
unzip -o ~/Descargas/llm_corp_bloque4_memoria_patch.zip -d .
```

## 3. Migracion SQL

Con Docker Compose:

```bash
docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" < db/migrations/004_institutional_memory.sql
```

Si tus variables no estan exportadas:

```bash
docker compose exec -T db psql -U conciliador -d conciliador_mvp < db/migrations/004_institutional_memory.sql
```

## 4. Build/restart

```bash
docker compose build api
docker compose up -d db api ui open-webui gateway searxng
```

Si algun servicio no existe en tu `docker-compose.yml`, levanta los que si existan:

```bash
docker compose up -d db api
```

## 5. Dependencias

No se agregan dependencias pesadas nuevas. Reinstala si tu ambiente lo requiere:

```bash
python -m pip install -r api/requirements.txt
python -m pip install -r api/requirements-dev.txt
```

## 6. Tests minimos

```bash
PYTHONPATH=api python -m pytest \
  tests/test_filters_dates.py \
  tests/test_router_direct.py \
  tests/test_query_routes.py \
  tests/test_followups.py \
  tests/test_knowledge_search.py \
  -q
```

## 7. Smoke test de `/chat`

```bash
python scripts/smoke_test_chat.py \
  --base-url http://localhost:8000 \
  --username admin \
  --password 'Admin123!' \
  --question '¿Cuál es el proceso para escalar una incidencia de conciliación?'
```

## 8. Ingesta de documento real

```bash
mkdir -p data/knowledge
PYTHONPATH=api python etl/knowledge_ingest.py \
  --input data/knowledge/TU_DOCUMENTO_REAL.md \
  --title "TITULO_REAL_DEL_DOCUMENTO" \
  --owner-area "AREA_REAL" \
  --tags tag_real_1 tag_real_2 \
  --allowed-groups grupo_real_1 grupo_real_2 \
  --status draft
```

Para cargar ya aprobado, usa `--status approved` solo si realmente corresponde.

## 9. Verificacion SQL

```bash
docker compose exec -T db psql -U conciliador -d conciliador_mvp -c "
SELECT d.document_id, d.title, d.status, d.owner_area, count(c.chunk_id) AS chunks
FROM institutional_documents d
LEFT JOIN institutional_chunks c ON c.document_id = d.document_id
GROUP BY d.document_id, d.title, d.status, d.owner_area
ORDER BY d.document_id DESC;
"
```

## 10. Activar/desactivar memoria

En `.env`:

```env
ENABLE_INSTITUTIONAL_MEMORY=true
INSTITUTIONAL_MEMORY_REQUIRE_APPROVED=true
INSTITUTIONAL_MEMORY_ENABLE_VECTOR=false
```

Desactivar:

```env
ENABLE_INSTITUTIONAL_MEMORY=false
```

Reinicia API:

```bash
docker compose up -d api
```
