# Parche aplicado sobre tu proyecto actual

Base revisada:
- Proyecto real inspeccionado desde el zip `llm_corp-main.zip`
- Ruta objetivo en tu equipo: `/Users/soporte/Documents/proyectos_llm/qwen_corp/llm_corp`

## Archivos incluidos en este parche

- `api/app/services/answer_service.py`
- `api/app/services/query_service.py`
- `api/app/services/auth_service.py`
- `api/app/utils/filters.py`
- `etl/run_all.py`
- `config/sqlserver_queries/movements.sql`

## Qué corrige

1. **Prompt del LLM mucho más grounded**
   - ahora sí recibe incidencias foco, archivos foco, movimientos recientes, movimientos de mayor importe, reglas, snippets de conocimiento y resultados web
   - mejora respuestas como “dime el primer descuadre crítico”

2. **Detección de intención más útil**
   - agrega prioridad para `primer`, `primera`, `detalle`, `desglosa`

3. **Movimientos más útiles para el chat**
   - `query_service.py` soporta `sort_mode="recent"` y `sort_mode="amount"`

4. **Evidencia real en incidencias**
   - `STATEMENT_BALANCE_MISMATCH` guarda saldos y diferencia calculada
   - `HEADER_WITHOUT_MOVEMENTS` guarda cuántos movimientos quedaron ligados al estado

5. **Se deja de perder `evidence` al insertar**
   - había un bug que siempre convertía `evidence` a `NULL`

6. **Bootstrap de admin consistente**
   - al reiniciar la API, el usuario admin de `.env` vuelve a quedar activo y con password sincronizado con `.env`

7. **Query de movimientos más robusta**
   - amplía inferencia de banco
   - mejora extracción de cuenta
   - intenta match por cuenta y por CLABE final

## Importante

La mejora de `movements.sql` está construida **con base en las columnas reales que sí vi en tu proyecto**. No pude ejecutarla contra tu SQL Server real desde aquí, así que esa parte está preparada y consistente con tu código, pero la validación final depende de correr el ETL en tu ambiente.

---

# Pasos exactos para aplicar en tu Mac

## 1) Colócate en tu proyecto real

```bash
cd /Users/soporte/Documents/proyectos_llm/qwen_corp/llm_corp
pwd
```

Debe imprimir:

```bash
/Users/soporte/Documents/proyectos_llm/qwen_corp/llm_corp
```

## 2) Haz respaldo de los archivos que vas a reemplazar

```bash
mkdir -p backup_pre_patch_2026_04_23/api/app/services
mkdir -p backup_pre_patch_2026_04_23/api/app/utils
mkdir -p backup_pre_patch_2026_04_23/etl
mkdir -p backup_pre_patch_2026_04_23/config/sqlserver_queries

cp api/app/services/answer_service.py backup_pre_patch_2026_04_23/api/app/services/
cp api/app/services/query_service.py backup_pre_patch_2026_04_23/api/app/services/
cp api/app/services/auth_service.py backup_pre_patch_2026_04_23/api/app/services/
cp api/app/utils/filters.py backup_pre_patch_2026_04_23/api/app/utils/
cp etl/run_all.py backup_pre_patch_2026_04_23/etl/
cp config/sqlserver_queries/movements.sql backup_pre_patch_2026_04_23/config/sqlserver_queries/
```

## 3) Descomprime este parche en una carpeta temporal

Supongamos que descargaste el zip del parche a `~/Downloads/llm_corp_patch.zip`.

```bash
mkdir -p ~/Downloads/llm_corp_patch_unzip
unzip -o ~/Downloads/llm_corp_patch.zip -d ~/Downloads/llm_corp_patch_unzip
```

## 4) Copia encima los archivos corregidos

```bash
cp ~/Downloads/llm_corp_patch_unzip/llm_corp_patch/api/app/services/answer_service.py api/app/services/answer_service.py
cp ~/Downloads/llm_corp_patch_unzip/llm_corp_patch/api/app/services/query_service.py api/app/services/query_service.py
cp ~/Downloads/llm_corp_patch_unzip/llm_corp_patch/api/app/services/auth_service.py api/app/services/auth_service.py
cp ~/Downloads/llm_corp_patch_unzip/llm_corp_patch/api/app/utils/filters.py api/app/utils/filters.py
cp ~/Downloads/llm_corp_patch_unzip/llm_corp_patch/etl/run_all.py etl/run_all.py
cp ~/Downloads/llm_corp_patch_unzip/llm_corp_patch/config/sqlserver_queries/movements.sql config/sqlserver_queries/movements.sql
```

## 5) Valida sintaxis Python antes de reconstruir

```bash
python3 -m py_compile api/app/services/answer_service.py
python3 -m py_compile api/app/services/query_service.py
python3 -m py_compile api/app/services/auth_service.py
python3 -m py_compile api/app/utils/filters.py
python3 -m py_compile etl/run_all.py
```

## 6) Reconstruye y reinicia la API

```bash
docker compose build api
docker compose up -d api
```

Si quieres reiniciar también UI, gateway y Open WebUI para dejar todo alineado:

```bash
docker compose up -d api ui open-webui gateway searxng
```

## 7) Reingesta datos para regenerar incidencias con `evidence`

```bash
bash ./scripts/ingest.sh
```

## 8) Revisa salud general

```bash
bash ./scripts/test-stack.sh
curl -fsS http://localhost:3300/api/health
```

## 9) Verifica que el admin del `.env` ya pueda autenticarse

```bash
curl -sS -X POST http://localhost:3300/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}'
```

Si devuelve `access_token`, ya quedó resuelto el 401 por bootstrap desalineado.

## 10) Verifica que ya exista evidencia en incidencias críticas

Primero toma token:

```bash
TOKEN=$(curl -sS -X POST http://localhost:3300/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}' | python3 -c 'import sys, json; print(json.load(sys.stdin)["access_token"])')
```

Luego consulta incidencias detalladas:

```bash
curl -sS "http://localhost:3300/api/incidents?aggregated=false&limit=5" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

Ahí debes ver `evidence` poblado al menos para:
- `STATEMENT_BALANCE_MISMATCH`
- `HEADER_WITHOUT_MOVEMENTS`

## 11) Verifica que el chat ya traiga más contexto real

```bash
curl -sS -X POST http://localhost:3300/api/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"question":"dime la informacion del primer descuadre critico que identificas","use_web":false}' | python3 -m json.tool
```

Y para híbrido:

```bash
curl -sS -X POST http://localhost:3300/api/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"question":"que herramientas o procesos existen para automatizar la deteccion de STATEMENT_BALANCE_MISMATCH en futuros periodos","use_web":true}' | python3 -m json.tool
```

---

# Si algo falla y quieres revertir rápido

Desde la raíz del proyecto:

```bash
cp backup_pre_patch_2026_04_23/api/app/services/answer_service.py api/app/services/answer_service.py
cp backup_pre_patch_2026_04_23/api/app/services/query_service.py api/app/services/query_service.py
cp backup_pre_patch_2026_04_23/api/app/services/auth_service.py api/app/services/auth_service.py
cp backup_pre_patch_2026_04_23/api/app/utils/filters.py api/app/utils/filters.py
cp backup_pre_patch_2026_04_23/etl/run_all.py etl/run_all.py
cp backup_pre_patch_2026_04_23/config/sqlserver_queries/movements.sql config/sqlserver_queries/movements.sql

docker compose build api
docker compose up -d api
bash ./scripts/ingest.sh
```

---

# Pipe de Open WebUI

Con este parche **no necesitas cambiar forzosamente la pipe** para que mejore la calidad de la respuesta. La pipe ya estaba reenviando la pregunta a `/chat`; el problema principal era el armado del contexto y el ETL de incidencias.

Solo verifica dentro de Open WebUI que la pipe siga apuntando a:
- `API_BASE_URL = http://api:8000`
- `API_USERNAME = admin`
- `API_PASSWORD = admin123`

Después del reinicio de API, ese login debe volver a funcionar si tu `.env` sigue con esos valores.
