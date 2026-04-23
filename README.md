# Qwen Secure Enterprise Stack - SQL Server + gateway 3000

Este ZIP deja el proyecto orientado a tu variante objetivo:

**SQL Server local -> normalización directa a `bank_statements` y `bank_movements` -> PostgreSQL -> FastAPI segura -> entrada pública por puerto 3000**.

## Cambios incluidos

- un solo puerto público: `3000`
- gateway con rutas:
  - `/` -> Open WebUI
  - `/secure` -> portal seguro corporativo
  - `/api` -> API segura
- ETL con `DATA_SOURCE_MODE=sqlserver`
- query de estados basada en `dbo.ConciliacionBancaria`
- probe para cerrar la fuente real de movimientos sin inventarla
- soporte para múltiples codebases en `data/input/codebases/`

## Valores reales fijados con base en lo que compartiste

- `SQLSERVER_SERVER=192.168.0.10\POWERBI`
- `SQLSERVER_DATABASE=DataLake`
- `SQLSERVER_USERNAME=sa`
- `SQLSERVER_STATEMENTS_QUERY_FILE=/app/config/sqlserver_queries/statements.sql`

## Lo pendiente y no inferido

- `SQLSERVER_PASSWORD`
- la query final de `config/sqlserver_queries/movements.sql`

## Flujo rápido

```bash
cp .env.example .env
# llena SQLSERVER_PASSWORD
# completa config/sqlserver_queries/movements.sql
./scripts/start-stack.sh
./scripts/pull-model.sh
./scripts/probe-sqlserver.sh
./scripts/ingest.sh
./scripts/test-stack.sh
```

## URLs finales

- `http://localhost:3000/`
- `http://localhost:3000/secure`
- `http://localhost:3000/api/health`
