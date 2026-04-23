# qwen_secure_enterprise_stack_sqlserver_gateway

## Descripción general

Stack dockerizado para consultas corporativas con **Open WebUI** como punto principal de entrada, **Caddy** como gateway único, una **API interna** para orquestación y políticas, una **UI segura** publicada bajo `/secure`, y un flujo de **ETL** orientado a consumir información operativa desde **SQL Server** o, en escenarios de prueba, desde archivos CSV/PDF.

El objetivo del repositorio es centralizar:

* acceso conversacional a un LLM desde Open WebUI;
* consulta de datos corporativos estructurados;
* ingestión de conocimiento documental;
* control de exposición web mediante políticas;
* despliegue reproducible en entornos Ubuntu y macOS.

---

## Alcance funcional

El repositorio incorpora los siguientes bloques funcionales:

* **Open WebUI** como interfaz principal para usuarios finales.
* **Gateway Caddy** para exponer una única entrada pública y enrutar componentes internos.
* **API propia** para autenticación, políticas, consultas, orquestación de respuestas y búsqueda web.
* **UI segura** separada del front principal y servida detrás de `/secure`.
* **PostgreSQL** como base interna del stack.
* **SearXNG** como motor de búsqueda web configurable por política.
* **ETL** para extracción, normalización y carga de conocimiento.
* **Integración con SQL Server** mediante consultas versionadas en `config/sqlserver_queries/`.
* **Soporte de insumos estáticos** en CSV/PDF para escenarios de prueba o bootstrap.

---

## Arquitectura

### Vista lógica

```text
Usuario
  │
  ▼
Caddy Gateway (:PUBLIC_PORT)
  ├── /              -> Open WebUI
  ├── /api           -> Open WebUI API
  ├── /corp-api      -> API interna
  └── /secure        -> UI segura
                           │
                           └── servicios internos / consultas controladas

API interna
  ├── autenticación y dependencias
  ├── políticas de acceso
  ├── consultas al origen corporativo
  ├── composición de respuestas
  └── búsqueda web controlada

Orígenes de datos
  ├── SQL Server
  ├── CSV
  └── PDF / conocimiento cargado por ETL

Persistencia local
  ├── PostgreSQL
  └── almacenamiento de runtime de Open WebUI
```

### Enrutamiento esperado

Con base en la configuración compartida del gateway, el comportamiento esperado de rutas es:

* `/corp-api` → `api:8000`
* `/secure` → `ui:8501`
* `/api` → `open-webui:8080`
* `/` → `open-webui:8080`

Esto define un **gateway único** con Open WebUI como entrada principal del sistema.

---

## Componentes principales

| Componente | Ruta | Función |
|---|---|---|
| Gateway | `gateway/` | Publicación del stack y reverse proxy con Caddy |
| API interna | `api/` | Políticas, autenticación, orquestación, consultas y web search |
| UI segura | `ui/` | Interfaz publicada detrás de `/secure` |
| ETL | `etl/` | Extracción, normalización, plantillas y carga de conocimiento |
| SQL versionado | `config/sqlserver_queries/` | Consultas SQL para movimientos y estados |
| Base interna | `db/init/` | Esquema y seguridad de PostgreSQL |
| Branding | `branding/` | Personalización visual y loader |
| SearXNG | `searxng/` | Configuración del motor de búsqueda web |
| Scripts operativos | `scripts/` | Bootstrap, arranque, pruebas, ingestión y utilidades |

---

## Estructura del repositorio

```text
.
├── api/
├── branding/
├── config/
│   └── sqlserver_queries/
├── data/
│   └── input/
├── db/
│   └── init/
├── docs/
├── etl/
├── gateway/
├── scripts/
├── searxng/
├── ui/
├── docker-compose.yml
├── Makefile
└── .env.example
```

---

## Prerrequisitos

### Ubuntu

* Docker Engine
* Docker Compose Plugin
* Git
* Bash
* Acceso de red a los servicios requeridos:
  - SQL Server
  - endpoints del modelo, si aplican
  - SearXNG o internet controlado, si la política lo permite

### macOS

* Docker Desktop
* Git
* Bash / zsh
* permisos para ejecutar scripts `.command` cuando se utilicen los accesos directos del repositorio

---

## Configuración

### Archivo de entorno

El repositorio debe operar a partir de un archivo `.env` local, derivado de `.env.example`.

```bash
cp .env.example .env
```

### Variables relevantes

| Variable | Obligatoria | Descripción |
|---|---:|---|
| `COMPOSE_PROJECT_NAME` | Sí | Nombre lógico del proyecto Docker |
| `POSTGRES_DB` | Sí | Base de datos interna del stack |
| `POSTGRES_USER` | Sí | Usuario de PostgreSQL |
| `POSTGRES_PASSWORD` | Sí | Contraseña de PostgreSQL |
| `POSTGRES_HOST` | Sí | Host de PostgreSQL |
| `POSTGRES_PORT` | Sí | Puerto de PostgreSQL |
| `APP_HOST` | Sí | Host de exposición de la API |
| `APP_PORT` | Sí | Puerto de la API interna |
| `API_BASE_URL` | Sí | URL base interna de la API |
| `PUBLIC_PORT` | Sí | Puerto público del gateway |
| `OPEN_WEBUI_URL` | Sí | URL pública esperada de Open WebUI |
| `OPEN_WEBUI_PORT` | Sí | Puerto público asociado a Open WebUI |
| `WEBUI_URL` | Sí | URL base de la interfaz principal |
| `WEBUI_SECRET_KEY` | Sí | Clave secreta de Open WebUI |
| `SECURE_UI_BASE_PATH` | Sí | Base path pública de la UI segura |
| `STREAMLIT_BASE_PATH` | Sí | Base path utilizada por la UI segura |
| `STREAMLIT_PORT` | Sí | Puerto interno de la UI segura |
| `SEARXNG_PORT` | Condicional | Puerto del servicio SearXNG |
| `SEARXNG_BASE_URL` | Condicional | URL base de SearXNG |
| `SEARXNG_QUERY_URL` | Condicional | Endpoint de consulta web |
| `WEB_SEARCH_RESULT_COUNT` | No | Número de resultados por consulta web |
| `WEB_LOADER_TIMEOUT` | No | Timeout de carga web |
| `WEB_DOMAIN_ALLOWLIST` | No | Restricción opcional de dominios permitidos |
| `DATA_SOURCE_MODE` | Sí | Modo de origen de datos (`csv`, `sqlserver` u otro definido por el proyecto) |
| `CSV_SOURCE_PATH` | Condicional | Ruta al CSV de prueba, si se trabaja en modo archivo |

> Las credenciales reales, secretos y endpoints privados no deben versionarse.

---

## Puesta en marcha rápida

## Ubuntu

### 1. Clonar el repositorio

```bash
git clone <URL_DEL_REPOSITORIO>
cd qwen_secure_enterprise_stack_sqlserver_gateway
```

### 2. Preparar entorno

```bash
cp .env.example .env
nano .env
```

### 3. Ejecutar bootstrap inicial

```bash
chmod +x scripts/*.sh scripts/ubuntu/*.sh scripts/host/*.sh
./scripts/setup_ubuntu.sh
./scripts/bootstrap.sh
```

### 4. Levantar el stack

```bash
./scripts/start-stack.sh
```

### 5. Validar servicios

```bash
./scripts/test-stack.sh
docker compose ps
```

### 6. Acceder a la plataforma

* Open WebUI: `http://localhost:${PUBLIC_PORT}`
* UI segura: `http://localhost:${PUBLIC_PORT}/secure`
* API interna vía gateway: `http://localhost:${PUBLIC_PORT}/corp-api`

---

## macOS

### 1. Clonar el repositorio

```bash
git clone <URL_DEL_REPOSITORIO>
cd qwen_secure_enterprise_stack_sqlserver_gateway
```

### 2. Preparar entorno

```bash
cp .env.example .env
nano .env
chmod +x scripts/*.sh scripts/host/*.sh
```

### 3. Bootstrap inicial

```bash
./scripts/bootstrap.sh
```

### 4. Arranque

Puede utilizarse la terminal:

```bash
./scripts/start-stack.sh
```

o bien, si se desea el flujo simplificado del repositorio:

```bash
open scripts/mac/01_primer_inicio.command
```

### 5. Verificación

```bash
./scripts/test-stack.sh
docker compose ps
```

---

## Operación diaria

### Arranque

```bash
./scripts/start-stack.sh
```

### Detención

```bash
./scripts/stop-stack.sh
```

### Verificación funcional

```bash
./scripts/test-stack.sh
```

### Descarga o preparación de modelo

```bash
./scripts/pull-model.sh
# o, según el flujo definido en el entorno:
./scripts/download_model.sh
```

---

## ETL e ingestión de conocimiento

El directorio `etl/` contiene utilidades para preparar datos y conocimiento del dominio.

### Scripts relevantes

| Script | Función |
|---|---|
| `etl/sqlserver_probe.py` | Prueba conectividad y acceso al origen SQL Server |
| `etl/extract_sqlserver.py` | Extrae información desde SQL Server |
| `etl/normalize_movements.py` | Normaliza movimientos para análisis o ingestión |
| `etl/load_knowledge.py` | Carga conocimiento derivado al stack |
| `etl/catalogs.py` | Manejo de catálogos y estructuras auxiliares |
| `etl/run_all.py` | Orquestación completa del pipeline |
| `etl/generate_assignments_template.py` | Generación de plantillas auxiliares |

### Ejecución recomendada

#### Probar conectividad a SQL Server

```bash
./scripts/probe-sqlserver.sh
```

#### Ingestión estándar

```bash
./scripts/ingest.sh
```

#### Orquestación completa por Python

```bash
python etl/run_all.py
```

---

## Integración con SQL Server

El repositorio está orientado a operar con un origen corporativo en SQL Server cuando exista conectividad y permisos adecuados.

### Consultas versionadas

Las consultas operativas residen en:

```text
config/sqlserver_queries/
├── movements.sql
└── statements.sql
```

### Ruta recomendada de uso

1. Configurar variables del origen SQL Server en `.env`.
2. Validar conectividad.
3. Ejecutar extracción.
4. Normalizar información.
5. Cargar conocimiento o datasets derivados al stack.

### Modos de operación

| Modo | Uso recomendado |
|---|---|
| `csv` | Pruebas locales, demos o bootstrap con insumos estáticos |
| `sqlserver` | Integración preferente con fuente corporativa vigente |

---

## Acceso web y políticas

La solución contempla control de acceso a búsqueda web mediante la API y la integración con SearXNG.

### Consideraciones operativas

* La búsqueda web debe habilitarse conforme a la política definida por el entorno.
* El allowlist de dominios puede restringirse mediante `WEB_DOMAIN_ALLOWLIST`.
* Los timeouts y el número de resultados deben ajustarse según capacidad y riesgo operativo.
* La exposición efectiva a internet depende de la configuración del gateway, los scripts de guardia de red y la política del servicio.

### Scripts relacionados

```bash
scripts/host/run-network-guard-mac.sh
scripts/host/run-network-guard-ubuntu.sh
```

---

## Seguridad y separación de funciones

El repositorio incluye elementos para endurecimiento operativo y separación funcional:

* gateway único como punto de exposición;
* UI segura bajo base path independiente;
* política de acceso web centralizada;
* inicialización de seguridad en base de datos;
* soporte para roles y restricciones a nivel de aplicación, sujeto a la configuración efectiva del despliegue.

### Artefactos relevantes

* `db/init/002_security.sql`
* `api/app/services/auth_service.py`
* `api/app/services/policy_service.py`
* `scripts/host/network_guard.py`

---

## Branding y personalización

La personalización visual reside en `branding/` y contempla, al menos, los siguientes artefactos:

* `branding/custom.css`
* `branding/loader.js`
* `branding/open-webui/patch_brand.py`

### Estado observado

En el escenario compartido durante la validación:

* la personalización por **CSS** carga correctamente;
* la personalización mediante **`loader.js`** presenta fallas cuando la UI segura opera detrás de `/secure`.

Por lo tanto, para despliegues donde `/secure` deba permanecer estable, la ruta más segura actualmente es mantener branding por CSS hasta corregir el manejo de rutas base del loader.

---

## Limitaciones conocidas

* La UI segura bajo `/secure` depende de una configuración consistente entre Caddy, la aplicación servida en `ui/` y el base path efectivo.
* La personalización por `branding/loader.js` no se comporta de forma estable en el escenario validado detrás de `/secure`.
* Los artefactos locales de Open WebUI, cachés de embeddings, backups y bases SQLite no deben formar parte del repositorio.
* El uso de fuentes CSV debe considerarse transitorio cuando exista integración operativa con SQL Server.
* La política de acceso web debe revisarse por entorno antes de habilitar navegación externa.

---

## Troubleshooting

### La ruta `/secure` no carga correctamente

Verificar:

1. `SECURE_UI_BASE_PATH`
2. `STREAMLIT_BASE_PATH`
3. reglas de `uri strip_prefix /secure` en `gateway/Caddyfile`
4. compatibilidad de assets estáticos con ejecución detrás de subruta
5. deshabilitación temporal de `branding/loader.js`

### Open WebUI responde, pero la UI segura falla

Escenario observado: con `custom.css` la personalización no rompe la carga; con `loader.js` sí se presentan fallas.  
Acción recomendada: aislar la validación sin loader y confirmar primero el comportamiento base de `/secure`.

### La conectividad a SQL Server falla

Validar:

```bash
./scripts/probe-sqlserver.sh
```

Revisar además:

* host, puerto y credenciales;
* reachability desde el contenedor o host;
* permisos sobre las tablas consultadas;
* consultas en `config/sqlserver_queries/`.

### El stack levanta, pero no responde el gateway

Validar:

```bash
docker compose ps
docker compose logs gateway
```

Revisar:

* puerto público configurado en `.env`;
* colisión con otros servicios locales;
* resolución correcta de nombres internos (`api`, `ui`, `open-webui`).

---

## Documentación complementaria

El repositorio incluye documentación adicional en `docs/`, entre ella:

* despliegue en macOS;
* despliegue en Ubuntu;
* seguridad y roles;
* comandos operativos;
* arquitectura final;
* origen SQL Server;
* reglas de catálogo;
* preguntas demo.

---

## Buenas prácticas de versionado

No deben versionarse:

* `.env`
* volúmenes y bases locales
* backups de Open WebUI
* cachés de modelos/embeddings
* archivos temporales de sistema
* metadatos `Zone.Identifier`

El repositorio debe publicar únicamente código, configuración versionable, documentación y ejemplos que no contengan credenciales ni runtime state.

---

## Estado recomendado del README del repositorio

Este README está orientado a acompañar el repositorio principal.  
El detalle operativo ampliado puede mantenerse en:

* `PROJECT_STATUS.md` para estado actual y limitaciones,
* `docs/` para despliegue y operación detallada,
* `.env.example` para referencia de configuración.

