# Balance LLM + SQL directo

Este parche corrige el comportamiento donde demasiadas preguntas se iban por respuestas directas deterministicas.

## Objetivo

- Usar Postgres como fuente exacta de datos.
- Usar el LLM para redactar, comparar, priorizar y explicar la mayoria de preguntas.
- Responder directo desde SQL solo cuando la pregunta sea claramente obvia y numerica, por ejemplo:
  - cuantos movimientos hubo en enero 2026
  - cuantas incidencias criticas hay
  - que periodos hay cargados

## Cambios principales

1. `answer_service.py`
   - Vuelve a un flujo LLM-first.
   - Conserva respuestas directas solo para conteos y catalogo de periodos.
   - Agrega memoria corta por usuario para follow-ups como "estos movimientos" o "abre el folio".
   - Envia al LLM contexto mas rico: movimientos a revisar, incidencias ligadas, archivos/estados, perfil de cuenta, reglas y distribuciones.

2. `query_service.py`
   - Agrega consultas auxiliares sin romper endpoints existentes.
   - Permite ordenar movimientos por prioridad de revision.
   - Agrega busqueda de movimientos por folio, referencia, concepto o descripcion.
   - Agrega candidatos de revision y perfil de cuenta.

3. `filters.py`
   - Mejora deteccion de fechas, banco, filial, cuenta, limite y follow-ups.
   - Respeta anio explicito en preguntas como "enero 2025".

## No cambia

- No toca Docker Compose.
- No toca ingestion.
- No borra datos.
- No modifica roles ni seguridad.
- No quita acceso a internet configurado por roles.
