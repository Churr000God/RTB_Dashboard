# Dashboard RTB

Dashboard web interactivo para visualizar cierres mensuales RTB a partir de cotizaciones exportadas desde Notion. Reemplaza al flujo anterior de reportes estaticos HTML/Markdown.

## Stack

- Python 3.12 + FastAPI + uvicorn
- HTML/CSS/JS inline en `rtb_web.py` (canvas custom, sin librerias de charting)
- Docker + docker-compose
- Sincronizacion de CSVs via Nextcloud (drop-in en `data/`)

## Como correr

```bash
docker compose up -d --build
```

Acceso: <http://localhost:8000>.

Variables de entorno (ver `.env.example`; cargar via `.env` o exportar):

| Variable | Default | Para que sirve |
|---|---|---|
| `RTB_WEBHOOK_TEST_URL` | (vacio) | Webhook de n8n para ambiente `test` (la UI lo elige desde el dropdown) |
| `RTB_WEBHOOK_PROD_URL` | (vacio) | Webhook de n8n para ambiente `prod` |
| `RTB_CSV_WAIT_ATTEMPTS` | `300` | Cuantos intentos espera el dashboard al CSV nuevo despues del `ok` de n8n |
| `RTB_CSV_WAIT_DELAY_SECONDS` | `1.0` | Segundos entre intento e intento |

Sin las dos primeras, el endpoint `/api/actualizar-datos` devuelve `400` con un mensaje claro. `RTB_CSV_WAIT_ATTEMPTS * RTB_CSV_WAIT_DELAY_SECONDS = espera total` (default 5 min). Subir si Nextcloud sincroniza lento.

## Arquitectura runtime

```
docker compose
  └─ dashboard-rtb (uvicorn rtb_web:app :8000)
       ├─ rtb_web.py     - FastAPI app + UI (HTML/JS inline) + endpoints + flujo sync de webhook
       └─ rtb_analisis.py - Fuente de verdad de KPIs (parseo CSV + agregaciones)
```

Volumenes montados desde el host:

- `./data` -> `/app/data` (drop-in de CSVs nuevos)
- `./data_procesada` -> `/app/data_procesada` (archivo historico de CSVs ya consumidos)
- `./dashboard_data` -> `/app/dashboard_data` (snapshot `ventas_latest.json` que sirve la API)

## Flujo de actualizacion

Disparado desde el formulario del dashboard (`POST /api/actualizar-datos`):

1. Validacion de fechas + ambiente (test/prod).
2. `call_webhook` -> POST sincrono al webhook de n8n cloud.
3. `validate_webhook_success` exige HTTP 2xx y body `{"ok": true}`.
4. `publish_ventas_snapshot` (`rtb_web.py:180`) espera hasta `RTB_CSV_WAIT_ATTEMPTS` segundos a que aparezca un `Cotizaciones_*.csv` nuevo en `data/` (lo deja Nextcloud).
5. `build_ventas_dashboard` (`rtb_analisis.py`) calcula KPIs.
6. CSV se mueve a `data_procesada/<timestamp>_ventas/`.
7. Snapshot se escribe atomicamente en `dashboard_data/ventas_latest.json`.

El frontend recarga y consume `GET /api/dashboard/ventas`.

## KPIs principales

Calculados en `rtb_analisis.compute_ventas` y servidos por `build_ventas_dashboard`. Ver `contexto/RTB_REPORTE_ACTUAL.md` para el catalogo completo.

Grupos visibles en la UI:

- Cotizaciones / Aprobadas / Conversion (cantidad y monto)
- Ariba cotizado / Ariba aprobado / Ariba conversion (subset filtrado por flag `Ariba`)
- Tiempos de aprobacion (promedio, mediana, maximo, histograma 0-7+ dias)
- Comportamiento temporal (semanal o mensual segun rango)
- Top clientes cotizan / aprueban
- Tipos de pago

## Tests

Unitarios (corren contra el contenedor):

```bash
docker compose exec -T dashboard-rtb python3 -m unittest discover tests/
```

Smoke test end-to-end (levanta docker, compila modulos, valida endpoints):

```bash
bash scripts/levantar_dashboard.sh
```

## Estructura del repo

```
.
├── rtb_web.py            # FastAPI app + UI + flujo sync de webhook
├── rtb_analisis.py       # Calculos
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── scripts/
│   └── levantar_dashboard.sh
├── tests/
│   ├── test_temporal_reporting.py
│   ├── test_ventas_dashboard.py
│   ├── test_webhook_app.py
│   └── test_levantar_dashboard.sh
├── contexto/
│   └── RTB_REPORTE_ACTUAL.md   # Diccionario de KPIs y columnas del CSV
├── AGENTS.md                   # Guia para agentes / IA
└── README.md
```

Las carpetas `data/`, `data_procesada/`, `reportes/` y `dashboard_data/` viven en el host pero estan ignoradas en git (contienen datos de negocio).

## Historial de limpieza

- Eliminado el flujo CLI viejo (`01_analizar.py`, `generar_reporte.py`, `rtb_html.py`, `rtb_markdown.py`, `chart.umd.min.js`) y los docs que lo describian (`diseno_paginas/`, `estructura_proyecto/`).
- Eliminado el flujo async de coordinator (`rtb_actualizacion.py`, endpoints `/api/actualizaciones/*`, vars `RTB_CALLBACK_URL`/`RTB_CALLBACK_TOKEN`). El dashboard ahora solo usa el flujo sincrono `POST /api/actualizar-datos`.
- URLs de webhook movidas de codigo a env vars (`RTB_WEBHOOK_TEST_URL`, `RTB_WEBHOOK_PROD_URL`).
