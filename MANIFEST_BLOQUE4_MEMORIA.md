# Manifest Bloque 4 - Memoria institucional

## Objetivo

Implementar memoria institucional formal, hibrida y segura para responder con evidencia sobre procesos, responsables, flujos internos, politicas, reglas internas, procedimientos, areas, escalamiento, manuales, glosarios y FAQs internas.

## Decisiones de seguridad

- `ENABLE_INSTITUTIONAL_MEMORY=false` por default.
- `INSTITUTIONAL_MEMORY_REQUIRE_APPROVED=true` por default.
- `INSTITUTIONAL_MEMORY_ENABLE_VECTOR=false` por default.
- No se insertan documentos ficticios ni contenido dummy.
- La migracion no rompe si pgvector no existe.
- El ETL guarda documentos como `draft` por default.
- Las preguntas financieras exactas siguen por SQL directo.

## Archivos incluidos

```text
.env.example
api/app/config.py
api/app/router/deterministic_parser.py
api/app/services/answer_service.py
api/app/services/answer_composer.py
api/app/services/context_builder.py
api/app/services/knowledge_service.py
api/app/prompts/institutional_answer.md
db/init/003_indexes.sql
db/migrations/003_indexes.sql
db/init/004_institutional_memory.sql
db/migrations/004_institutional_memory.sql
db/init/005_conversation_state.sql
db/migrations/005_conversation_state.sql
etl/knowledge_ingest.py
docs/10_bloque4_memoria_institucional.md
APLICAR_BLOQUE4_MEMORIA.md
MANIFEST_BLOQUE4_MEMORIA.md
tests/test_knowledge_search.py
tests/test_router_direct.py
tests/test_filters_dates.py
tests/test_query_routes.py
tests/test_followups.py
scripts/smoke_test_chat.py
```

## No incluido deliberadamente

- No se cambia `docker-compose.yml` porque no venia en el ZIP base analizado.
- No se activa pgvector por default.
- No se agregan dependencias pesadas de extraccion DOCX/PDF avanzada.
- No se crean documentos de ejemplo.
