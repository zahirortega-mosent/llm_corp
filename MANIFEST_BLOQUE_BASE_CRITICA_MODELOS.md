# Parche Bloque base critica + rendimiento/modelos

Fecha: 2026-04-28

Este parche esta preparado para descomprimirse desde la raiz del proyecto `llm_corp` y sobrescribir solo archivos necesarios. No elimina funcionalidades existentes.

## Reglas de negocio tomadas como obligatorias

- SQL directo para hechos exactos: conteos, listados, desgloses, busquedas textuales simples, rankings y perfil basico de cuenta.
- Fechas explicitas se respetan; `enero 2025` nunca debe convertirse en `enero 2026`.
- Mes sin anio solo se infiere si hay un unico periodo disponible para ese mes.
- Si el mes sin anio es ambiguo, se pide aclaracion.
- Si el mes sin anio no existe en metadata, se responde sin consultar todo el dataset.
- Rutas directas no usan LLM.
- Rutas analiticas usan evidencia compactada y selector de modelo.
- `context` completo solo debe exponerse con `options.debug=true`.

## Cambios aplicados

### Base critica

- Reforzado `api/app/utils/filters.py`:
  - parseo explicito de `enero 2025`, `enero 2026`, `octubre 2025`;
  - listas como `enero y febrero 2026`;
  - trimestres `Q1 2026`;
  - metadata de resolucion de filtros.
- Reforzado `api/app/router/deterministic_parser.py`:
  - aliases de `group_by` mas acotados para no confundir `banco BANBAJIO` con `por banco`.
- Reforzado `api/app/services/answer_service.py`:
  - no consulta SQL cuando mes sin anio requiere aclaracion;
  - no consulta todo el dataset si el mes sin anio no existe;
  - mantiene rutas directas con `used_llm=false`.
- Reforzado `api/app/services/answer_composer.py`:
  - etiquetas para periodos multiples;
  - respuestas de aclaracion y mes no disponible.
- Creado `db/init/003_indexes.sql`.
- Agregados tests de fechas, router directo y presencia de rutas SQL.

### Rendimiento/modelos

- Creado `api/app/services/model_selector.py`.
- Creado `api/app/services/context_builder.py`.
- Creado `api/app/router/llm_classifier.py`.
- Reforzado `api/app/services/llm_service.py` para permitir:
  - modelo por llamada;
  - timeout por llamada;
  - temperatura por llamada;
  - schema JSON opcional para clasificacion.
- Agregados prompts base:
  - `api/app/prompts/classify_intent.md`
  - `api/app/prompts/analyst_system.md`
- Agregados scripts:
  - `scripts/hardware_check.sh`
  - `scripts/configure_ollama_bloque2.sh`
  - `scripts/pull-model.sh`
  - `scripts/benchmark_llm_routes.py`
  - `scripts/smoke_test_chat.py`
  - `scripts/test-stack.sh`

## Comandos recomendados

Desde la raiz del proyecto:

```bash
unzip -o llm_corp_bloque_base_critica_modelos_patch.zip -d .

# Verificar sintaxis local dentro del contenedor API o ambiente con dependencias
PYTHONPATH=api python -m pytest tests/test_filters_dates.py tests/test_router_direct.py tests/test_query_routes.py -q

# Reconstruir API si usas Docker Compose
docker compose build api
docker compose up -d db api ui open-webui gateway searxng

# Aplicar indices a una DB existente
docker compose exec -T db psql -U conciliador -d conciliador_mvp < db/init/003_indexes.sql

# Ver logs de API
docker compose logs -f --tail=200 api
```

## Comandos Ollama host

Estos comandos se ejecutan en el host, no dentro del contenedor API:

```bash
bash scripts/hardware_check.sh
bash scripts/configure_ollama_bloque2.sh
bash scripts/pull-model.sh
ollama ps
```

## Smoke test API

Primero obtiene token con tu login actual:

```bash
TOKEN=$(curl -s http://localhost:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"Admin123!"}' | jq -r .access_token)

API_TOKEN="$TOKEN" python scripts/smoke_test_chat.py --base-url http://localhost:8000
API_TOKEN="$TOKEN" python scripts/benchmark_llm_routes.py --base-url http://localhost:8000 --repeat 3
```

## Preguntas de prueba para UI

- `cuantos movimientos hubo en enero 2025`
- `cuantos movimientos hubo en enero 2026`
- `periodos disponibles`
- `movimientos por banco en enero 2026`
- `cuentas sugeridas a revisar en enero 2026`
- `cuantos movimientos hubo en octubre`
- `muestra movimientos del banco BANBAJIO en enero 2026`

Esperado: las primeras rutas exactas deben responder con `used_llm=false` en debug/API.
