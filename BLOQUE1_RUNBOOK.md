# Runbook Bloque 1 - router minimo, fechas precisas y SQL directo

Este ZIP esta preparado como overlay desde la raiz del proyecto. Descomprimirlo en `/home/user/proyectos_llm/llm_corp` sobrescribe solo los archivos modificados y crea los nuevos.

## 1. Aplicar overlay

```bash
cd /home/user/proyectos_llm/llm_corp
cp /ruta/llm_corp_bloque1_router_sql_overlay.zip .
unzip -o llm_corp_bloque1_router_sql_overlay.zip
```

## 2. Reconstruir API y levantar contenedores

```bash
docker compose build api
docker compose up -d db api open-webui caddy searxng
```

Si tu `docker-compose.yml` usa otros nombres, verlos con:

```bash
docker compose config --services
```

## 3. Aplicar indices SQL del Bloque 1

```bash
docker compose cp db/init/003_indexes.sql db:/tmp/003_indexes.sql
docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /tmp/003_indexes.sql
```

Alternativa si las variables no estan dentro del shell:

```bash
docker compose exec db psql -U conciliador -d conciliador_mvp -f /tmp/003_indexes.sql
```

## 4. Ejecutar pruebas unitarias dentro del contenedor API

```bash
docker compose exec api sh -lc 'cd /app && PYTHONPATH=/app pytest tests/test_filters_dates.py tests/test_router_direct.py tests/test_query_routes.py -q'
```

Si pytest no esta instalado en la imagen:

```bash
docker compose exec api sh -lc 'pip install pytest && cd /app && PYTHONPATH=/app pytest tests/test_filters_dates.py tests/test_router_direct.py tests/test_query_routes.py -q'
```

## 5. Probar rutas criticas por API

```bash
docker compose exec api sh -lc 'python scripts/smoke_test_chat.py --base-url http://localhost:8000 --question "cuantos movimientos hubo en enero 2025"'
docker compose exec api sh -lc 'python scripts/smoke_test_chat.py --base-url http://localhost:8000 --question "cuantos movimientos hubo en enero 2026"'
docker compose exec api sh -lc 'python scripts/smoke_test_chat.py --base-url http://localhost:8000 --question "periodos disponibles"'
docker compose exec api sh -lc 'python scripts/smoke_test_chat.py --base-url http://localhost:8000 --question "movimientos por banco en enero 2026"'
docker compose exec api sh -lc 'python scripts/smoke_test_chat.py --base-url http://localhost:8000 --question "cuentas sugeridas a revisar en enero 2026"'
```

## 6. Logs y verificacion

```bash
docker compose logs -f --tail=200 api
docker compose ps
curl -s http://localhost:8000/health | jq .
```

## Criterios esperados

- `enero 2025` se mantiene como `2025-01-01`; no se cambia a 2026.
- Conteos exactos devuelven `used_llm=false`.
- `periodos disponibles` devuelve los periodos cargados.
- Desgloses y cuentas sugeridas salen por SQL directo.
