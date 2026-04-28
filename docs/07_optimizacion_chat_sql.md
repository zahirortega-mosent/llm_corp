# Optimización de respuestas SQL directas

## Objetivo

El chat debe contestar en segundos cuando la pregunta pide datos exactos de la base: conteos, periodos, movimientos por banco/filial/cuenta, incidencias por regla/severidad y perfil de una cuenta.

La regla de arquitectura queda así:

1. SQL directo para hechos y métricas.
2. SQL + ranking determinístico para cuentas sugeridas a revisar.
3. LLM solo para redacción analítica cuando la pregunta pide explicación, causa probable o resumen ejecutivo.

## Cambios aplicados

### 1. Parser de fechas

Archivo: `api/app/utils/filters.py`

Ahora reconoce correctamente:

- `enero 2025`
- `enero de 2025`
- `2025 enero`
- `2025-01`
- `2025/01`

Si el usuario solo dice `enero` y existen varios años, toma el periodo más reciente disponible y avisa que hubo ambigüedad.

### 2. Router determinístico de respuestas

Archivo: `api/app/services/answer_service.py`

Antes casi todo terminaba armando contexto y llamando a Ollama. Ahora se responde sin LLM para:

- `cuántos movimientos hubo en enero 2025`
- `movimientos por banco en febrero 2026`
- `incidencias por regla`
- `qué periodos hay cargados`
- `la cuenta 123456 pertenece a qué filial`
- `qué cuentas sugieres revisar`
- búsquedas por referencia, folio, descripción o concepto

El JSON de salida agrega `used_llm: false` y `context.direct_route` cuando respondió por SQL directo.

### 3. Nuevas consultas SQL de negocio

Archivo: `api/app/services/query_service.py`

Métodos nuevos:

- `get_available_periods_summary()`
- `get_movements_breakdown()`
- `get_incidents_breakdown()`
- `get_review_candidates()`
- `get_account_profile()`
- `search_movements_text()`

### 4. Endpoints nuevos para pruebas rápidas

Archivo: `api/app/main.py`

- `GET /periods`
- `GET /accounts/{account_number}/profile`
- `GET /review-candidates`

### 5. Performance en Postgres

Archivos:

- `db/init/001_schema.sql`
- `db/migrations/003_performance_indexes.sql`
- `scripts/apply-performance-indexes.sh`

Se agregaron índices compuestos para filtros frecuentes por `period`, `bank`, `filial`, `account_number`, severidad, reglas y búsqueda textual.

Para una base ya existente, ejecutar:

```bash
bash scripts/apply-performance-indexes.sh
```

### 6. Corrección de `statement_uid`

Archivos:

- `config/sqlserver_queries/movements.sql`
- `etl/normalize_movements.py`
- `etl/run_all.py`

Antes, algunos movimientos podían quedar con `statement_uid` vacío si `hash_archivo` venía nulo. Eso rompía trazabilidad contra `bank_statements` y podía afectar incidencias. Ahora se genera el mismo hash alternativo que ya usaba `statements.sql`.

## Después de aplicar

Recrear o actualizar la base:

```bash
bash scripts/ingest.sh
bash scripts/apply-performance-indexes.sh
```

Probar desde Open WebUI o desde API:

```text
qué periodos hay cargados
cuantos movimientos hubo en enero 2025
cuantos movimientos por banco en enero 2025
incidencias por regla en enero 2025
qué cuentas sugieres revisar en enero 2025
la cuenta 01002614979 pertenece a qué filial y qué movimientos tiene
busca movimientos proveedor global en enero 2025
```
