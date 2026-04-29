# Bloque 4 - Memoria institucional hibrida

Este bloque agrega una memoria institucional formal para responder sobre procesos, responsables, politicas, procedimientos, reglas internas, areas, escalamiento, manuales, glosarios y FAQs internas.

La memoria institucional queda separada de los datos financieros transaccionales. Las preguntas exactas de conteos, rankings, movimientos, incidencias, bancos, filiales, cuentas y periodos siguen resolviendose por SQL directo.

## Archivos creados

- `db/init/003_indexes.sql`
- `db/migrations/003_indexes.sql`
- `db/init/004_institutional_memory.sql`
- `db/migrations/004_institutional_memory.sql`
- `db/init/005_conversation_state.sql`
- `db/migrations/005_conversation_state.sql`
- `api/app/services/knowledge_service.py`
- `api/app/prompts/institutional_answer.md`
- `etl/knowledge_ingest.py`
- `docs/10_bloque4_memoria_institucional.md`
- `APLICAR_BLOQUE4_MEMORIA.md`
- `MANIFEST_BLOQUE4_MEMORIA.md`
- `tests/test_knowledge_search.py`
- `tests/test_router_direct.py`
- `tests/test_filters_dates.py`
- `tests/test_query_routes.py`
- `tests/test_followups.py`
- `scripts/smoke_test_chat.py`

## Archivos modificados

- `.env.example`
- `api/app/config.py`
- `api/app/router/deterministic_parser.py`
- `api/app/services/answer_service.py`
- `api/app/services/answer_composer.py`
- `api/app/services/context_builder.py`

## Modelo de datos

La migracion crea las tablas:

- `institutional_documents`
- `institutional_chunks`
- `institutional_entities`
- `institutional_facts`

Los documentos se cargan como `draft` por defecto. Las respuestas normales usan solo documentos `approved` cuando `INSTITUTIONAL_MEMORY_REQUIRE_APPROVED=true`.

## pgvector

La migracion intenta ejecutar `CREATE EXTENSION IF NOT EXISTS vector`, pero no falla si la imagen actual de PostgreSQL no tiene pgvector. En ese caso:

- la memoria funciona con busqueda lexical/full-text;
- la columna `embedding_vector` no se crea;
- `INSTITUTIONAL_MEMORY_ENABLE_VECTOR=false` debe mantenerse.

Para habilitar busqueda vectorial despues, usa una imagen PostgreSQL con pgvector instalado, aplica la migracion y activa:

```env
INSTITUTIONAL_MEMORY_ENABLE_VECTOR=true
```

## Ingesta de documentos reales

Ejemplo:

```bash
PYTHONPATH=api python etl/knowledge_ingest.py \
  --input data/knowledge/manual_tesoreria.md \
  --title "Manual de Tesoreria" \
  --owner-area "Tesoreria" \
  --tags conciliacion tesoreria bancos \
  --allowed-groups tesoreria auditoria \
  --status draft
```

Formatos simples soportados por default: Markdown, TXT, CSV y HTML simple. PDF se soporta si `pypdf` esta instalado. DOCX requiere dependencia extra (`python-docx`) y no se agrega por default para no hacer pesada la instalacion.

## Aprobar/publicar memoria

Para publicar un documento cargado como `draft`:

```sql
UPDATE institutional_documents
SET status = 'approved', approved_by = 'admin', approved_at = now(), updated_at = now()
WHERE document_id = 1;
```

Usa el `document_id` real devuelto por el ETL.

## Preguntas de prueba

Institucionales:

```text
¿Cual es el proceso para escalar una incidencia de conciliacion?
¿Quien autoriza excepciones de conciliacion?
¿Que politica interna aplica para movimientos no conciliados?
```

Transaccionales, deben seguir por SQL directo sin memoria:

```text
¿Cuantos movimientos hubo en enero 2026?
Movimientos por banco en enero 2026
Top cuentas con incidencias en febrero 2026
```

## Desactivar memoria

En `.env`:

```env
ENABLE_INSTITUTIONAL_MEMORY=false
```

Reinicia `api` despues del cambio.
