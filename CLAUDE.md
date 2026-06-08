# CLAUDE.md — Dashboard RTB: guía de orientación rápida

Actualizar este archivo con cada cambio importante de arquitectura, semántica o decisión de diseño.

---

## Qué es este proyecto

Dashboard web interactivo de reportes para Vatreni Ingeniería. Muestra KPIs de **ventas** (cotizaciones), **facturación** (facturas emitidas) y **compras** (facturas recibidas de proveedores). La fuente de verdad es **Notion**; los datos llegan como CSVs vía **n8n**.

---

## Stack

| Capa | Tecnología |
|---|---|
| Backend | Python 3 + FastAPI + Uvicorn |
| Contenedor | Docker (`docker-compose.yml` + `docker-compose.override.yml`) |
| Frontend | HTML/CSS/JS vanilla (todo en `rtb_web.py` como string Python) |
| Orquestador | n8n — descarga CSVs de Notion y dispara webhook al dashboard |
| Datos | Notion → n8n → CSVs en `data/` → snapshot JSON en `dashboard_data/` |

El override monta el código local (`.:/app`) — cambios en `.py` se reflejan sin rebuild; solo `docker compose up -d` una vez.

---

## Archivos clave

| Archivo | Rol |
|---|---|
| `rtb_analisis.py` | Toda la lógica de cálculo. Funciones `build_*_dashboard()` |
| `rtb_web.py` | API FastAPI + HTML/CSS/JS del frontend completo |
| `dashboard_data/*_latest.json` | Snapshots cacheados que sirve la API |
| `data/` | CSVs activos que lee el servidor |
| `data_procesada/YYYY-MM-DD_HH-MM-SS_datos/` | Histórico de cada corrida de n8n |
| `contexto/RTB_REPORTE_ACTUAL.md` | Reglas de negocio (mantener actualizada) |
| `tests/test_facturacion_dashboard.py` | Suite facturación |
| `tests/test_compras_dashboard.py` | Suite compras (22 tests) |
| `tests/test_cobranza_dashboard.py` | Suite cobranza (39 tests) |

---

## Flujo de datos

```
n8n deposita CSVs → ./data/
      ↓  webhook → publish_*_snapshot()
      ↓  lee CSVs más recientes con read_csv() (utf-8-sig para manejar BOM)
      ↓  corre build_*_dashboard(...)
      ↓  escribe JSON atómico
./dashboard_data/*_latest.json
      ↓
GET /api/dashboard/*  →  sirve el JSON
```

**Si el código del backend cambia, el snapshot NO se regenera solo.** Hay que disparar el webhook o llamar `POST /api/regenerar-snapshot` con `{"fecha_desde":"...", "fecha_hasta":"..."}`.

---

## Módulos y sus CSVs

### Ventas (cotizaciones)
- `Cotizaciones_*.csv`

### Facturación (facturas emitidas)
- `Cotizaciones_*.csv`
- `Facturas_*.csv` — **solo** `Facturas_YYYY-MM-DD_HH-MM.csv` (allowlist regex; rechaza `Anticipo_`, `Compras_`, `Secundarias_` y cualquier sufijo futuro)
- `Facturas_Secundarias_*.csv` — igual, solo el patrón `Facturas_Secundarias_YYYY-MM-DD_HH-MM.csv`
- Selección de archivo: `find_latest_facturacion_csv()` en `rtb_analisis.py` (testeable sin FastAPI)
- Función: `build_facturacion_dashboard()`
- Snapshot: `dashboard_data/facturacion_latest.json`

### Compras (facturas recibidas)
- `Facturas_Compras_*.csv`
- `Facturas_Anticipo_*.csv` — **tiene BOM UTF-8**, siempre leer con `read_csv()` de `rtb_analisis`
- Función: `build_compras_dashboard(fc, anticipos=...)`
- Snapshot: `dashboard_data/compras_latest.json`

### Cobranza (cobros de pedidos de ventas)
- `Pagos_Principlaes_Facturas_Ventas_YYYY-MM-DD_HH-MM.csv` — **nótese el typo "Principlaes"**, viene así de n8n. Regex allowlist: `^Pagos_Principlaes_Facturas_Ventas_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\.csv$`
- `Pagos_Secundarias_Facturas_Ventas_YYYY-MM-DD_HH-MM.csv` — regex: `^Pagos_Secundarias_Facturas_Ventas_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\.csv$`
- Selección: `find_latest_cobranza_csvs()` en `rtb_web.py` — busca en `data/` primero; cae a `data_procesada/` cuando `data/` está vacío (post-archivo n8n)
- `Cotizaciones_*.csv` también se carga con fallback a `data_procesada/` vía `load_cotizaciones()`
- Función: `build_cobranza_dashboard(principales, secundarias, ..., cotizaciones=None)`
- Snapshot: `dashboard_data/cobranza_latest.json`
- Campo nuevo `Pedido Pago Cotizacion` (UUID): vincula cada cobro a su `Cotizacion_id` — 100 % poblado

### Pagos a Proveedores (pagos de facturas de compra)
- `Pagos_Facturas_Compras_YYYY-MM-DD_HH-MM.csv` — pagos de facturas de materiales. Regex: `^Pagos_Facturas_Compras_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\.csv$`
- `Pago_Facturas_Nostas_Credito_YYYY-MM-DD_HH-MM.csv` — notas de crédito y anticipos. Regex: `^Pago_Facturas_Nostas_Credito_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\.csv$` (**"Nostas"** es el typo de n8n, igual que "Principlaes")
- Selección: `find_latest_pagos_proveedores_csvs(data_dir)` en `rtb_analisis.py` usando `_find_csv_with_fallback()` (busca `data/` primero, luego `data_procesada/`). NC puede ser `None` si no existe el CSV.
- Función: `build_pagos_proveedores_dashboard(pagos_fc, notas_credito, period_label, fecha_desde, fecha_hasta)`
- Snapshot: `dashboard_data/pagos_proveedores_latest.json`
- Endpoint: `GET /api/dashboard/pagos_proveedores`

### Gastos Operativos (gastos administrativos categorizados)
- `Gastos_Operativos_YYYY-MM-DD_HH-MM.csv` — gastos con categoría, tarjeta, deducible/no deducible. Regex: `^Gastos_Operativos_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\.csv$`
- Selección: `find_latest_gastos_operativos_csv(data_dir)` en `rtb_analisis.py`
- Función: `build_gastos_operativos_dashboard(rows, period_label, fecha_desde, fecha_hasta)`
- Snapshot: `dashboard_data/gastos_operativos_latest.json`
- Endpoint: `GET /api/dashboard/gastos_operativos`

### Finanzas (consolidado — 7º tab)
- **No lee CSVs**: `build_finanzas_dashboard` recibe los 5 sub-dicts ya construidos (consolidador puro).
- **Dos lentes**:
  - Devengado: `facturacion.kpis.monto_facturado_vigente` vs `compras.kpis.tot_fc + gastos.kpis.total_total`
  - Caja: `cobranza.kpis.monto_cobrado_total` vs `pagos_proveedores.kpis.monto_total + gastos.kpis.total_total`
- **Gastos en ambas bases**: desembolso inmediato, mismo valor en devengado y caja.
- **IVA trasladado** = `ingreso_caja − ingreso_caja/1.16` (sobre lo cobrado).
- **IVA acreditable** = `compras.iva_fc + gastos.iva_acreditable`.
- Las series temporales se alinean por `key` (robusto ante ejes desalineados).
- Función: `build_finanzas_dashboard(facturacion, cobranza, compras, pagos_proveedores, gastos_operativos, ...)`
- `publish_finanzas_snapshot` llama a los 5 `load_*_payload` con `_safe()` — si falta un sub-snapshot su aporte es 0.
- Snapshot: `dashboard_data/finanzas_latest.json`
- Endpoint: `GET /api/dashboard/finanzas`

---

## Reglas de negocio críticas

### Cancelación (facturación)
- **Cancelada real:** `Factura_Estado_Aprobacion ∈ {Cancelada, Cancelado}` (case-insensitive)
- **`Factura_Cancelada`:** NO es flag booleano — guarda el folio sustituido (ej. "C5878"). Ignorar para determinar cancelación.

### Monto facturado (facturación)
```python
raw = row.get("Monto_primer_factura")
partial = round(f(raw), 2) if (raw is not None and str(raw).strip() != "") else None
monto = partial if partial is not None else round(f(row.get("Total")), 2)
# "0" literal cuenta como valor válido, no como nulo
```

### Compras — canceladas excluidas
Facturas con `estado_factura == "Factura Cancelada"` se excluyen de todos los totales. Se reportan por separado como `n_canc / tot_canc`.

### Compras — IVA acreditable
- `iva_fc` = IVA **recibido** = `tot − sub − env` (derivado del total reportado en Notion)
- `iva_real_fc` = IVA **teórico** = `sub × 0.16`
- La diferencia refleja errores de captura en Notion, NO un bug del dashboard

### Compras — anticipos (Facturas de Anticipo)
Un anticipo es **Regularizado** (vinculado) cuando existe una factura de compras activa que en su campo `Factura_Anticipo_Asociada` contiene el UUID del anticipo. Esto se verifica contra **todo el CSV** (sin filtro de periodo), así un anticipo de mayo regularizado por una factura de julio igual aparece como vinculado.

**Semántica de la gráfica de anticipos:** barras agrupadas por **mes de emisión del anticipo**.
- Rojo = `monto_pendiente` (sin factura definitiva)
- Azul = `monto_regularizado` (vinculado a factura definitiva)
- Ambas barras usan la fecha del anticipo, NO la fecha de la factura definitiva.

### Cobranza — monto cobrado
- `Pedido Pago Total` (c/IVA) es el monto cobrado. El campo `Pedido Pago Monto pagado` viene vacío en todos los registros actuales — ignorarlo.
- `Pedido Estatus de pago` siempre llega como `"Pagada Total"`. El CSV contiene solo cobros completados.
- **Eje temporal: `Fecha de pago`** (siempre poblada), no la fecha de asociación.

### Cobranza — secundarias NO suman al ingreso
Un cobro "secundaria" es el **segundo cobro del mismo pedido** facturado en dos partes. Su `Total` es el total del pedido completo, **no** el monto del segundo cobro. Por ello:
- `monto_cobrado_total` = suma de `Total` de **principales únicamente**.
- `monto_secundarias_referencial` = suma de `Total` de secundarias (referencia, no ingreso).
- El monto real del 2º cobro no está capturado en Notion (`Monto pagado Secundaria` está vacío) — se reporta señal `monto_secundaria_no_capturado`.

### Cobranza — días de cobranza
`days_diff(fecha_asociacion, fecha_pago)` — lag entre cuándo se asoció la factura y cuándo se recibió el pago. Solo calculable cuando `Fecha de Asociacion` está poblada (≈79 % de los registros actuales).

### Cobranza — pendientes por cobrar
Cotizaciones aprobadas (`Estado_cotizacion == "Aprobada"`) cuyo `Cotizacion_id` **no** aparece en ningún registro del CSV de principales.
- `n_pendientes_cobro` / `monto_pendiente_cobro` = backlog completo (sin filtro de periodo).
- Cruce usa **todos** los pagos del CSV, no solo los del periodo — un cobro fuera del rango aún marca la cotización como cobrada.
- `series.pendientes_temporal` = distribución por `Fecha_aprobacion` (rango auto-detectado).
- `tables.pendientes` = top-20 por monto desc.

### Pagos a Proveedores — reglas clave
- `cantidad_pagada` puede ser **negativo o ~0** cuando hay nota de crédito aplicada. Se suma tal cual (los negativos restan — correcto contablemente).
- `tipo_pago` viene con prefijo numérico (`"3 Tranferencia"`, `"28 Tarjeta de debito"`, `"99 por definir"`). Normalizar con `_normalizar_tipo_pago_fc()` usando `_TP_MAP = {"1":"Efectivo","3":"Transferencia","28":"Tarjeta de débito","99":"Por definir"}`.
- **"Tranferencia"** (sic, sin 's') — respetar el typo del CSV en el código de matching.
- `nota_credito` en `Pagos_Facturas_Compras` es lista JSON de UUIDs — si no está vacía, se emite señal `nc_aplicada`.
- `estatus_pago = "No Pagado"` → se cuenta en `n_pendientes` y se emite `pago_pendiente`; **no suma** a `monto_fc`.
- Cruce NC ↔ Factura: campo `nota_credito` apunta a UUIDs del CSV `Pago_Facturas_Nostas_Credito`.

### Gastos Operativos — reglas clave
- `Deducible` viene como string `"TRUE"` / `"FALSE"` (no booleano Python). Usar `.upper() == "TRUE"`.
- `IVA acreditable` = suma de `Gasto Operativo Iva` donde `Deducible == "TRUE"` y `Estado == "Realizado"`.
- `Total` se toma directamente del campo (`Subtotal + IVA` no siempre cierra exacto por redondeos en Notion).
- `Estado = "Rechazado"` **no cuenta** en totales pero se reporta señal `gasto_rechazado`.
- `Gasto Operativo Tarjeta ` y `Gasto Operativo Fecha ` tienen **espacio al final del nombre** — respetar en `.get()`.
- `Tarjeta` vacía → grupo `"Sin tarjeta"` en la agrupación por tarjeta.
- `Categoria` vacía → grupo `"Sin categoría"`.

---

## Granularidad temporal

```python
# temporal_axis() en rtb_analisis.py
monthly = (start.year, start.month) != (end.year, end.month)
# mismo mes → granularidad='semana', keys=['S1'..'S5']
# meses distintos → granularidad='mes', keys=['2026-05', '2026-06', ...]
```

Comparar fechas siempre con `.date()` para ignorar hora (evita corte de registros del día final).

---

## Gotchas frecuentes

| Síntoma | Causa probable | Solución |
|---|---|---|
| KPIs muestran $0 o valores viejos tras cambio de backend | Snapshot no regenerado | Disparar webhook o `POST /api/regenerar-snapshot` |
| Barras de anticipos muestran $0 aunque hay datos en tabla | Snapshot tiene `monto_anticipado` (clave vieja) en lugar de `monto_pendiente` | Regenerar snapshot con nueva versión del código |
| Compras muestra solo 1 mes en lugar del rango | n8n devolvió CSV incompleto (bug intermitente) | Verificar CSV en `data_procesada/`, pedir al usuario reejecutar webhook |
| Badge "Regularizado/Pendiente" se sale de la celda | Columna Estado sin `min-width` | `<th style="min-width:110px">Estado</th>` |
| Leyenda de gráfica desborda la sección | `pie-legend` dentro de `weekly-chart-wrap` (altura fija) | Mover `pie-legend` fuera del `weekly-chart-wrap` |
| `Factura_anticipo_id` llega vacío al normalizar | CSV leído con `encoding='utf-8'` en lugar de `'utf-8-sig'` | Siempre usar `read_csv()` de `rtb_analisis` |
| Facturación muestra 3 facturas / $180k aunque CSV tiene 273 filas | `Facturas_Anticipo_*.csv` seleccionado como "principales" por tener mtime mayor | Ya corregido con allowlist regex en `find_latest_facturacion_csv`; si reaparece, verificar que la función no fue revertida a denylist |
| Cobranza: `n_pendientes_cobro = 0` aunque hay cotizaciones aprobadas | `data/` vacío → `load_cotizaciones` falla silenciosamente → `cotizaciones=None` | Ambas funciones tienen fallback a `data_procesada/`; si sigue vacío verificar que el CSV de cotizaciones existe ahí |
| `regenerar-snapshot` silencioso para Cobranza | Pagos CSVs archivados en `data_procesada/` antes del restart; `find_latest_cobranza_csvs` ya tiene fallback automático | Verificar que exista al menos un `Pagos_Principlaes_*.csv` en `data_procesada/` |
| Pagos Proveedores muestra $0 / sin datos | CSV `Pagos_Facturas_Compras_*.csv` no encontrado en `data/` ni `data_procesada/` | Verificar que n8n haya depositado el archivo; endpoint devuelve HTTP 404 si falta |
| `Pago_Facturas_Nostas_Credito` no carga | CSV opcional — si no existe, `find_latest_pagos_proveedores_csvs` devuelve `(path_fc, None)` sin error | `build_pagos_proveedores_dashboard` acepta `notas_credito=[]` correctamente |
| Gastos Operativos: campo `Fecha` no parsea | Nombre de campo tiene espacio final: `"Gasto Operativo Fecha "` — la coma extra en el header del CSV | Usar exactamente ese nombre (con espacio) en `.get()` |
| `_find_csv_with_fallback` devuelve CSV de otro módulo | El glob prefix no es suficientemente específico si hay archivos con nombres similares | El regex es el filtro real; el prefix solo acelera el glob |

---

## Calidad de datos conocida

- **`Factura_compra_total`** mal capturado en Notion para ~17 facturas (abr-jun 2026). Diferencia acumulada ≈ −$41,784. Aparece en tarjeta "Diferencia IVA". No es bug del dashboard.
- **n8n filtra solo 1 mes** en Facturas_Compras de forma intermitente. Si hay discrepancia de datos, primero revisar el CSV antes de tocar código.
- **Facturas con folio sucio** (`#_Factura = "C5888 / PEND 50%..."`): regex `^(C\d+)` extrae el código; se emite señal `factura_folio_captura_sucia`.

---

## Tests

```bash
python -m unittest tests/test_facturacion_dashboard.py -v
python -m unittest tests/test_compras_dashboard.py -v                  # 22 tests
python -m unittest tests/test_cobranza_dashboard.py -v                 # 44 tests
python -m unittest tests/test_pagos_proveedores_dashboard.py -v        # 23 tests
python -m unittest tests/test_gastos_operativos_dashboard.py -v        # 26 tests (+ 15 de regex/tarjeta/categoría)
python -m unittest tests/test_finanzas_dashboard.py -v                 # 58 tests
# Suite completa sin FastAPI (188 tests):
python -m unittest tests/test_facturacion_dashboard.py tests/test_compras_dashboard.py tests/test_cobranza_dashboard.py tests/test_pagos_proveedores_dashboard.py tests/test_gastos_operativos_dashboard.py tests/test_finanzas_dashboard.py -v
```

Correr siempre antes de hacer commit en `rtb_analisis.py`.

---

## Señales activas (facturación)

| Señal | Condición |
|---|---|
| `factura_captura_incompleta` | Aprobada sin folio o fecha |
| `factura_duplicada` | Mismo folio/cotizacion_id con distinto `Factura_id` |
| `rezago_facturacion_estimado` | Cotización aprobada sin factura vigente |
| `factura_folio_captura_sucia` | `#_Factura` contiene notas extra |
| `segunda_factura_pendiente` | `Monto_primer_factura` lleno, sin secundaria |
| `factura_partidas_desbalanceadas` | primer + segunda difiere >$0.05 de Total |

---

## Historial de decisiones importantes

| Fecha | Decisión |
|---|---|
| 2026-06-03 | Módulo Compras: eliminar toda la lógica de pagos (CxP, fechas de pago, % pagado). Solo facturación recibida. |
| 2026-06-03 | `Factura_Cancelada` no es booleano — es el folio sustituido. Cancelación real = `Factura_Estado_Aprobacion`. |
| 2026-06-04 | IVA compras: `iva_fc = tot−sub−env` (recibido), `iva_real = sub×0.16` (teórico). |
| 2026-06-04 | Gráfica anticipos: barras agrupadas (rojo=pendiente, azul=vinculado) por mes de **emisión del anticipo**. El mes de la factura definitiva ya no determina la posición en la gráfica. |
| 2026-06-04 | Columna Estado de anticipos: solo badge, sin texto "Procesada" del CSV. |
| 2026-06-04 | `find_latest_facturacion_csv` migrada de denylist a allowlist regex `^<prefix>\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\.csv$`. Movida a `rtb_analisis.py` para ser testeable sin FastAPI. 4 tests de regresión agregados a `test_facturacion_dashboard.py`. |
| 2026-06-04 | Compras: nueva tarjeta KPI "Total del periodo" — `n_fc + n_ant_pendientes` y `tot_fc + monto_pendientes`. Calculada en JS puro en `renderCompras()`, sin cambio de backend ni snapshot. |
| 2026-06-04 | Nuevo módulo Cobranza (4º tab). Monto cobrado = `Total` de principales únicamente. Secundarias = 2º cobro del mismo pedido; su `Total` NO se suma al ingreso. Días de cobranza = `days_diff(fecha_asociacion, fecha_pago)`. CSV prefix tiene typo "Principlaes" de n8n — respetado en código. |
| 2026-06-05 | Cobranza: análisis de pendientes por cobrar vía campo `Pedido Pago Cotizacion`. Cruce usa todos los pagos (sin filtro periodo). `find_latest_cobranza_csvs` y `load_cotizaciones` caen a `data_procesada/` como fallback post-archivo. |
| 2026-06-05 | Cobranza: sección "Días de cobranza" rediseñada — pie chart donut (paleta azules/dorados del tema), stats con tarjetas `.tiempos-kpi` con color de acento. |
| 2026-06-05 | Cobranza: nueva sección "Top 10 clientes con crédito activo" — barras horizontales (rojo), ordenadas por monto pendiente desc. Backend: `tables.top_clientes_pendientes` en `build_cobranza_dashboard`, agrupando `pendientes_cot` completo (no el top-20 truncado). 5 tests nuevos. |
| 2026-06-05 | Nuevos módulos "Pagos a Proveedores" y "Gastos Operativos" (5º y 6º tabs). Backend: `build_pagos_proveedores_dashboard`, `build_gastos_operativos_dashboard`, `_find_csv_with_fallback` (genérico, compartido). Reglas clave: `cantidad_pagada` puede ser negativo (NC aplicada), `tipo_pago` viene con prefijo numérico, `Deducible` es string "TRUE"/"FALSE", campos de Gastos tienen espacios en el nombre. 49 tests nuevos (23 + 26). Suite completa: 130 tests. |
| 2026-06-05 | Gastos Operativos: refactor visual completo — todas las tablas y leyendas migradas a `<canvas>`. 4 helpers canvas nuevos en `rtb_web.py`: `drawTableCanvas`, `drawGroupedBarChart`, `drawKpiCardsCanvas`, `drawPieLegendCanvas`. Centro de la dona dibujado en canvas (eliminado `div.pie-center`). Interactividad tabla↔gráfica bidireccional en Comportamiento semanal y Distribución por categoría. Análisis fiscal: tarjetas `.tiempos-kpi` HTML + gráfica de barras agrupadas canvas (Monto `#276f86` / IVA `#d0b56b`). Tabla de detalle eliminada. `GASTOS_CAT_COLORS` y colores de gráficas alineados a la paleta principal del tema. Bug resuelto: usar `renderVal` (no `valueOf`) en columnas de `drawTableCanvas` — `valueOf` es método nativo de Object.prototype y causa `[object Object]` en todas las celdas. |
| 2026-06-05 | Nuevo módulo Finanzas (7º tab): consolidación pura de los 5 módulos financieros. `build_finanzas_dashboard` recibe los 5 sub-dicts ya construidos (no CSVs). Dos lentes paralelas: Devengado (facturación vs compras+gastos) y Caja (cobranza vs pagos+gastos). Gastos en ambas bases. IVA trasladado derivado de lo cobrado (`cobrado − cobrado/1.16`). Snapshot `finanzas_latest.json`. 58 tests nuevos. Suite completa: 188 tests. |

---

## Nota de despliegue — git push

**Excluir siempre de commits/push:** `docker-compose.yml` — los volúmenes usan rutas absolutas de la máquina local (`/home/dhguilleng/Nextcloud/Sistemas/REPORTES/Dashboard_interactivo_reportes/{data,data_procesada,dashboard_data}`) que no aplican en otros entornos. El archivo en el repo mantiene rutas relativas (`./data`, `./data_procesada`, `./dashboard_data`).

Todo lo demás (`rtb_web.py`, `rtb_analisis.py`, `tests/`, `CLAUDE.md`, etc.) se sube normalmente.
