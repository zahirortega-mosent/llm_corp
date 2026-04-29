# Aplicar parche Bloque 3 - Conversacion robusta y follow-ups

## 1. Copiar ZIP a Descargas

El archivo generado por ChatGPT debe quedar en:

```bash
~/Descargas/llm_corp_bloque3_conversacion_followups_patch.zip
```

## 2. Aplicar desde la raiz del proyecto

```bash
cd ~/proyectos_llm/llm_corp
cp -a api/app/services/answer_service.py api/app/services/answer_service.py.bak_pre_bloque3_$(date +%Y%m%d_%H%M%S)
unzip -o ~/Descargas/llm_corp_bloque3_conversacion_followups_patch.zip -d .
```

## 3. Activar variable en `.env`

```bash
grep -q '^ENABLE_CONTEXT_RESOLVER=' .env \
  && sed -i 's/^ENABLE_CONTEXT_RESOLVER=.*/ENABLE_CONTEXT_RESOLVER=true/' .env \
  || echo 'ENABLE_CONTEXT_RESOLVER=true' >> .env
```

## 4. Aplicar migracion en PostgreSQL existente

```bash
docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" < db/migrations/005_conversation_state.sql
```

Si las variables no estan exportadas en tu shell, usa los valores de `.env`:

```bash
docker compose exec -T db psql -U conciliador -d conciliador_mvp < db/migrations/005_conversation_state.sql
```

## 5. Reconstruir y levantar API

```bash
docker compose build api
docker compose up -d db api ui open-webui gateway searxng
```

## 6. Probar tests dentro del contenedor API

```bash
docker compose exec api bash -lc 'PYTHONPATH=/app python -m pytest /app/tests/test_filters_dates.py /app/tests/test_router_direct.py /app/tests/test_query_routes.py /app/tests/test_followups.py -q'
```

## 7. Smoke test de chat con conversation_id

```bash
TOKEN=$(curl -s http://localhost:3300/corp-api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"Admin123!"}' | jq -r .access_token)

curl -s http://localhost:3300/corp-api/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"question":"movimientos por banco en enero 2026","conversation_id":"smoke-bloque3","options":{"max_rows":5}}' | jq .

curl -s http://localhost:3300/corp-api/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"question":"y por filial?","conversation_id":"smoke-bloque3","options":{"max_rows":5,"debug":true}}' | jq .
```

En la segunda respuesta, `metadata.filter_resolution.inherits_previous_context` debe aparecer en `true` y la ruta debe mantenerse SQL directa.
