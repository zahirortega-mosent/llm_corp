# Preguntas test para evitar rutas heuristicas peligrosas

Estas preguntas separan rutas exactas de SQL directo contra preguntas ambiguas o institucionales. La idea no es meter mas `if` sueltos, sino validar que el router solo toma SQL directo cuando hay metrica clara, entidad/ruta clara y confianza suficiente.

| Pregunta | Resultado esperado | Motivo |
|---|---|---|
| `cuantos movimientos hubo en enero 2026` | `movement_count`, SQL directo, `used_llm=false` | conteo exacto con periodo explicito |
| `cuantos movimientos hubo en enero 2025` | `movement_count`, SQL directo, 0 + periodos disponibles | respeta ano explicito no disponible |
| `periodos disponibles` | `available_periods`, SQL directo | catalogo exacto |
| `movimientos por banco en enero 2026` | `movement_breakdown`, `group_by=bank`, SQL directo | metrica + agrupacion + periodo |
| `incidencias por filial en enero 2026` | `incident_breakdown`, `group_by=filial`, SQL directo | metrica de incidencias + agrupacion |
| `cuentas sugeridas a revisar en enero 2026` | `review_candidates`, SQL directo | ranking deterministico de cuentas |
| `banco` | `summary`/aclaracion, no SQL directo | palabra suelta no debe traer todos los bancos |
| `por filial` | `summary`/aclaracion, no SQL directo | agrupacion sin metrica no debe consultar todo |
| `revisa esto` | `summary`/aclaracion, no `review_candidates` | no hay cuenta, periodo ni evidencia referenciada |
| `cual es el proceso por banco para autorizar la conciliacion` | `institutional_knowledge`, no SQL directo | menciona proceso/autorizacion; no es desglose financiero |
| `como se autoriza una cuenta bancaria en el proceso interno` | `institutional_knowledge`, no `account_profile` | la palabra cuenta no basta sin numero de cuenta |
| `quien es responsable del proceso de conciliacion` | `institutional_knowledge`, no SQL directo | pregunta de memoria institucional |

Comando automatizado:

```bash
docker compose exec api sh -lc 'cd /app && PYTHONPATH=/app python scripts/smoke_test_router_questions.py'
```
