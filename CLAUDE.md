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
| `tests/test_cobranza_dashboard.py` | Suite cobranza (29 tests) |

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
- Selección: `find_latest_cobranza_csvs()` en `rtb_web.py`
- Función: `build_cobranza_dashboard(principales, secundarias, ...)`
- Snapshot: `dashboard_data/cobranza_latest.json`

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

---

## Calidad de datos conocida

- **`Factura_compra_total`** mal capturado en Notion para ~17 facturas (abr-jun 2026). Diferencia acumulada ≈ −$41,784. Aparece en tarjeta "Diferencia IVA". No es bug del dashboard.
- **n8n filtra solo 1 mes** en Facturas_Compras de forma intermitente. Si hay discrepancia de datos, primero revisar el CSV antes de tocar código.
- **Facturas con folio sucio** (`#_Factura = "C5888 / PEND 50%..."`): regex `^(C\d+)` extrae el código; se emite señal `factura_folio_captura_sucia`.

---

## Tests

```bash
python -m unittest tests/test_facturacion_dashboard.py -v
python -m unittest tests/test_compras_dashboard.py -v   # 22 tests
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
