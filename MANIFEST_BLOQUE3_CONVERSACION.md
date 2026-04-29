# Bloque 3 - Conversacion robusta y follow-ups

Este parche implementa estado conversacional persistente en PostgreSQL y un resolver deterministico de follow-ups antes del router final.

## Archivos nuevos

- `db/init/005_conversation_state.sql`
- `db/migrations/005_conversation_state.sql`
- `api/app/services/conversation_service.py`
- `api/app/services/context_resolver.py`
- `tests/test_followups.py`
- `open_webui_functions/corp_pipe_bloque3.py`
- `docs/09_bloque3_conversacion_followups.md`

## Archivos modificados

- `.env.example`
- `api/app/config.py`
- `api/app/services/answer_service.py`
- `api/app/services/query_service.py`
- `tests/test_query_routes.py`

## Reglas aplicadas

- El estado no vive en variables de proceso.
- El backend resuelve follow-ups con estado estructurado.
- El Pipe queda delgado y solo reenvia `conversation_id`.
- No se manda todo el historial al LLM.
- Follow-ups resolubles no usan LLM.
- La evidencia referenciable se guarda compacta en `last_result_refs`.

## Casos cubiertos

- `movimientos de enero por banco` -> `y por filial?`
- `top cuentas a revisar` -> `revisa la primera`
- `cuantos movimientos en enero 2026` -> `y febrero?`

## Migracion requerida para bases existentes

```bash
docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" < db/migrations/005_conversation_state.sql
```
