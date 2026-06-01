# Instrucciones para IA - Dashboard RTB

Este proyecto es el **dashboard web interactivo** que muestra cierres mensuales RTB calculados a partir de cotizaciones exportadas desde Notion. No es Nexus Ops RTB y no genera reportes HTML estaticos (ese flujo se elimino). Antes de cambiar codigo, lee el `README.md` y entiende los KPIs documentados en `contexto/RTB_REPORTE_ACTUAL.md`.

## Orden de entendimiento

1. `README.md` - stack, flujo y como correrlo.
2. `contexto/RTB_REPORTE_ACTUAL.md` - diccionario de KPIs, columnas criticas del CSV.
3. `rtb_analisis.py` - fuente de verdad de toda agregacion. Si el numero esta mal, esta aqui.
4. `rtb_web.py` - endpoints HTTP + render de UI inline (HTML/CSS/JS embebidos). Las tarjetas KPI estan en `renderKpis`.
5. `rtb_actualizacion.py` - coordinator del flujo async con callback de n8n.

## Modulos activos

| Archivo | Responsabilidad | Importado por |
|---|---|---|
| `rtb_web.py` | FastAPI app, endpoints, UI completa (HTML/JS inline), orquestacion sincrona del webhook | uvicorn (entry point) |
| `rtb_actualizacion.py` | Coordinator de runs async, valida tokens de callback, gestiona estado de actualizaciones | `rtb_web.py` |
| `rtb_analisis.py` | Parsing de CSV, KPIs, agregaciones temporales, signals/alertas | `rtb_web.py`, `rtb_actualizacion.py`, tests |

No hay otros modulos Python a nivel raiz. Si encuentras referencias a `generar_reporte.py`, `rtb_html.py`, `rtb_markdown.py`, `chart.umd.min.js`, `01_analizar.py`, `diseno_paginas/`, `estructura_proyecto/` u "HTML estatico" en docs o comentarios, son rezagos del flujo viejo - borralos o reescribelos.

## Reglas de implementacion

- **No introduzcas dependencias de charting** (Chart.js, D3, ECharts). El dashboard usa canvas 2D custom en `rtb_web.py`. Mantener.
- **Nombres de dominio inalterables**: cotizacion, pedido, aprobada, expirada, Ariba, ticket promedio, CFDI, complemento de pago, Tipo_pago, Localidad.
- **Calculos nuevos van en `rtb_analisis.py`** como funciones puras. Agrega test unitario en `tests/test_ventas_dashboard.py` o `tests/test_temporal_reporting.py` antes de tocar la UI.
- **KPIs nuevos en la UI**: agregar la clave en el dict que retorna `build_ventas_dashboard` (`rtb_analisis.py`), luego consumirla en `renderKpis` (`rtb_web.py`). Recuerda regenerar `dashboard_data/ventas_latest.json` (se queda viejo si no se reprocesa el ultimo CSV).
- **Cambios en CSS/JS del HTML inline**: el contenedor Docker NO monta el codigo fuente. Cualquier edit en `rtb_web.py` requiere `docker compose up -d --build`. Sin rebuild, el usuario ve la version vieja en cache.
- **Datos sensibles** (montos, clientes, fechas) viven en `data/`, `data_procesada/`, `dashboard_data/`. Estan en `.gitignore`. Nunca subir, nunca pegar en commits.

## Verificacion antes de cerrar

1. Tipos / compile:
   ```bash
   docker compose exec -T dashboard-rtb python3 -m py_compile rtb_web.py rtb_analisis.py rtb_actualizacion.py
   ```
2. Tests:
   ```bash
   docker compose exec -T dashboard-rtb python3 -m unittest discover tests/
   ```
3. Smoke end-to-end de endpoints:
   ```bash
   curl -s http://localhost:8000/ | grep -q "Dashboard"
   curl -s http://localhost:8000/api/dashboard/ventas | head -c 200
   ```
4. Si cambiaste UI: abrir <http://localhost:8000> con Ctrl+Shift+R, validar que la tarjeta/grafica afectada renderiza con datos actuales y los tooltips no se cortan.
5. Si cambiaste calculos: comparar contra un CSV real conocido y reportar la diferencia esperada en el PR/commit.

## Skills sugeridos

- `test-driven-development` antes de tocar parseo, agregaciones, conversion, ticket promedio, signals.
- `verification-before-completion` antes de decir "listo": correr los 5 pasos de arriba.
- `code-review` para cambios que toquen mas de un modulo o que afecten KPIs visibles.
