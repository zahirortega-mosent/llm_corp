# Despliegue en macOS

1. `cp .env.example .env`
2. llena `SQLSERVER_PASSWORD`
3. completa `config/sqlserver_queries/movements.sql`
4. `./scripts/start-stack.sh`
5. `./scripts/pull-model.sh`
6. `./scripts/probe-sqlserver.sh`
7. `./scripts/ingest.sh`
