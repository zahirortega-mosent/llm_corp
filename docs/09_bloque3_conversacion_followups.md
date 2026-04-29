# Bloque 3 - Conversacion robusta y follow-ups

## Objetivo

Permitir preguntas cortas como `y por filial?`, `revisa la primera` y `y febrero?` sin depender de memoria local del proceso ni de prompts grandes.

## Flujo implementado

```text
/chat
  -> QueryService.get_metadata
  -> ConversationService.get_state(conversation_id, username)
  -> ContextResolver.resolve(...)
  -> IntentRouter o route_override deterministico
  -> SQL/LLM segun ruta
  -> ConversationService.save_state(...)
```

## Estado persistido

La tabla `conversation_state` guarda:

- ultima pregunta
- ultima intencion
- ultimos filtros
- ultima ruta
- referencias compactas de resultados
- resumen corto de la ultima respuesta

No guarda todo el historial del chat.

## Referencias compactas

`last_result_refs` guarda como maximo 10 elementos con campos utiles para follow-ups:

- banco
- filial
- cuenta
- periodo
- movement_uid / incident_uid / statement_uid cuando existan
- metricas principales como movimientos, incidencias y score

## Pipe de Open WebUI

El archivo `open_webui_functions/corp_pipe_bloque3.py` es una version delgada del Pipe. Su responsabilidad es enviar al backend:

```json
{
  "question": "...",
  "conversation_id": "...",
  "use_web": false,
  "options": {"debug": false, "max_rows": 10}
}
```

El backend conserva la responsabilidad de resolver contexto, permisos, rutas, SQL y composicion.

## Validaciones rapidas

```bash
PYTHONPATH=api python -m pytest tests/test_followups.py -q
PYTHONPATH=api python -m pytest tests/test_filters_dates.py tests/test_router_direct.py tests/test_query_routes.py -q
```
