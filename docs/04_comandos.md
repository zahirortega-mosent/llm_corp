# Comandos y rutas

## Shell

```bash
./scripts/start-stack.sh
./scripts/stop-stack.sh
./scripts/pull-model.sh
./scripts/ingest.sh
./scripts/test-stack.sh
make logs
```

## Chat administrativo

```text
/internet on
/internet off
/allow-web analista1
/deny-web analista1
/roles analista1 analyst,auditor
/wifi off
/wifi on
/help
```

## Rutas

- cola pendiente: `control/commands/pending/`
- cola ejecutada: `control/commands/done/`
- datos Open WebUI: `data/open-webui/`
- caché SearXNG: `data/searxng/`
- insumos ETL: `data/input/`
- salidas ETL: `data/output/`
