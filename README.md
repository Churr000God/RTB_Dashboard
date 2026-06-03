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
- `./dashboard_data` -> `/app/dashboard_data` (snapshots `ventas_latest.json` y `facturacion_latest.json` que sirven las APIs)

### Rutas locales en produccion

`docker-compose.yml` se mantiene versionado sin cambios locales. Si el servidor
de produccion usa rutas absolutas distintas, crear un
`docker-compose.override.yml` local a partir del ejemplo:

```bash
cp docker-compose.override.example.yml docker-compose.override.yml
```

Editar solamente los tres paths del lado izquierdo de cada volumen. El archivo
real esta ignorado por Git y Docker Compose lo carga automaticamente, por lo que
los comandos normales siguen funcionando:

```bash
docker compose config
docker compose up -d --build
```

Antes de actualizar un servidor que todavia tenga rutas locales editadas
directamente en `docker-compose.yml`, respaldar ese archivo fuera del repo,
pasar las rutas al override y restaurar la version del repositorio:

```bash
cp docker-compose.yml /tmp/docker-compose.yml.backup
cp docker-compose.override.example.yml docker-compose.override.yml
# Editar docker-compose.override.yml con las rutas del backup
git restore docker-compose.yml
git pull --ff-only origin main
docker compose config
docker compose up -d --build
```

Revisar la salida de `docker compose config` antes del rebuild: los `source` de
los tres volumes deben apuntar a las rutas reales del servidor.

## Flujo de actualizacion

Disparado desde el formulario del dashboard (`POST /api/actualizar-datos`):

1. Validacion de fechas + ambiente (test/prod).
2. `call_webhook` -> POST sincrono al webhook de n8n cloud.
3. `validate_webhook_success` exige HTTP 2xx y body `{"ok": true}`.
4. `publish_ventas_snapshot` (`rtb_web.py:180`) espera hasta `RTB_CSV_WAIT_ATTEMPTS` segundos a que aparezca un `Cotizaciones_*.csv` nuevo en `data/` (lo deja Nextcloud).
5. Si existen los tres exports requeridos, `build_facturacion_dashboard` calcula y publica `dashboard_data/facturacion_latest.json`.
6. `build_ventas_dashboard` (`rtb_analisis.py`) calcula KPIs comerciales.
7. CSV de cotizaciones se mueve a `data_procesada/<timestamp>_ventas/`.
8. Snapshot comercial se escribe atomicamente en `dashboard_data/ventas_latest.json`.

El frontend recarga y consume `GET /api/dashboard/ventas` y `GET /api/dashboard/facturacion`.

## KPIs principales

Calculados en `rtb_analisis.compute_ventas` y servidos por `build_ventas_dashboard`. Ver `contexto/RTB_REPORTE_ACTUAL.md` para el catalogo completo.

Grupos visibles en la UI:

- Cotizaciones / Aprobadas / Conversion (cantidad y monto)
- Ariba cotizado / Ariba aprobado / Ariba conversion (subset filtrado por flag `Ariba`)
- Tiempos de aprobacion (promedio, mediana, maximo, histograma 0-7+ dias)
- Comportamiento temporal (semanal o mensual segun rango; ver regla abajo)
- Top clientes cotizan / aprueban
- Tipos de pago

## Granularidad temporal automatica

La funcion `temporal_axis` (`rtb_analisis.py`) detecta automaticamente si mostrar semanas o meses:

- `fecha_desde` y `fecha_hasta` en el **mismo mes** → `granularidad=semana` (S1 1-7, S2 8-14, S3 15-21, S4 22-28, S5 29-fin)
- `fecha_desde` y `fecha_hasta` en **meses distintos** → `granularidad=mes` (una barra por mes calendario)

`aggregate_temporal` filtra los registros al rango exacto antes de asignarlos al bucket, usando comparacion de fecha sin hora (`.date()`). Esto garantiza que:

1. Un CSV con datos de 3 meses consultado en modo semanal (un solo mes) no mezcla registros de otros meses en S1-S5.
2. Registros creados a las 23:59 del ultimo dia del rango no quedan excluidos por la comparacion datetime vs medianoche.

## Facturacion

La pestaña `Facturación` combina tres exports: `Cotizaciones_*.csv`,
`Facturas_*.csv` y `Facturas_Secundarias_*.csv`. El snapshot independiente
`dashboard_data/facturacion_latest.json` evita acoplar la vista a Ventas.

Reglas principales:

- Una factura vigente requiere aprobación, folio y fecha de facturación.
- Las canceladas se excluyen del monto vigente y se muestran aparte.
- `Monto_primer_factura` o `Monto_segunda_factura` sustituyen a `Total` cuando tienen valor.
- Un mismo `Factura_id` no se duplica entre exports principal y secundario.
- El rezago estimado suma cotizaciones aprobadas sin factura vigente asociada.

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

## Historial de correcciones

### 2026-06-03 — Granularidad y filtrado de fechas (`rtb_analisis.py`)

**`aggregate_temporal` no filtraba por rango en modo semanal.** Con granularidad `semana`, S1-S5 no codifican el mes. Si el CSV contiene datos de varios meses pero el rango pedido es un solo mes, los registros de los otros meses caian en los mismos buckets. Fix: filtrar por `dt.date()` antes de asignar al bucket.

**Corte por hora en `fecha_hasta`.** `parse_date('2026-06-03')` devuelve medianoche; registros con hora `2026-06-03T21:14Z` eran mayores y quedaban excluidos. Fix: comparar `.date()` en ambos lados en `aggregate_temporal` e `in_period`.

**Facturación solo procesaba un mes cuando el CSV tenia varios.** Causa: el snapshot se habia generado con `fecha_hasta` incorrecto (fin de mes en lugar de fecha real). Fix: regenerar via `POST /api/regenerar-snapshot` con las fechas correctas copiando los CSVs de `data_procesada/` de vuelta a `data/`.

**`render_index` tenia payload de ejemplo hardcodeado a abril 2026.** Fix: calcula dinamicamente `hoy` y `primer dia de hace 2 meses`.

---

## Historial de limpieza

- Eliminado el flujo CLI viejo (`01_analizar.py`, `generar_reporte.py`, `rtb_html.py`, `rtb_markdown.py`, `chart.umd.min.js`) y los docs que lo describian (`diseno_paginas/`, `estructura_proyecto/`).
- Eliminado el flujo async de coordinator (`rtb_actualizacion.py`, endpoints `/api/actualizaciones/*`, vars `RTB_CALLBACK_URL`/`RTB_CALLBACK_TOKEN`). El dashboard ahora solo usa el flujo sincrono `POST /api/actualizar-datos`.
- URLs de webhook movidas de codigo a env vars (`RTB_WEBHOOK_TEST_URL`, `RTB_WEBHOOK_PROD_URL`).
