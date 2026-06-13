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

### Logística (pedidos aprobados / enviados / entregados — 8º tab)
- `Pedidos_Aprbados_En_El_Periodo_YYYY-MM-DD_HH-MM.csv` *(typo "Aprbados")* — aprobados. Regex: `^Pedidos_Aprbados_En_El_Periodo_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\.csv$`
- `Pedidos_Enviados_En_El_Periodo_YYYY-MM-DD_HH-MM.csv` — enviados. Regex: `^Pedidos_Enviados_En_El_Periodo_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\.csv$`
- `Pedidos_Entregados_En_El_Periodo_YYYY-MM-DD_HH-MM.csv` — entregados, **fuente principal de lead times**. Regex: `^Pedidos_Entregados_En_El_Periodo_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\.csv$`
- `Segimiento_pedidos_entregados_incompletos_YYYY-MM-DD_HH-MM.csv` *(typo "Segimiento")* — backlog incompletos (opcional). Regex: `^Segimiento_pedidos_entregados_incompletos_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\.csv$`
- Selección: `find_latest_logistica_csvs(data_dir)` en `rtb_analisis.py` — devuelve `(ap, en, et, seg|None)` con fallback a `data_procesada/`
- Función: `build_logistica_dashboard(aprobados, enviados, entregados, seguimiento, period_label, fecha_desde, fecha_hasta)`
- Snapshot: `dashboard_data/logistica_latest.json`
- Endpoint: `GET /api/dashboard/logistica`

### Gastos Operativos (gastos administrativos categorizados)
- `Gastos_Operativos_YYYY-MM-DD_HH-MM.csv` — gastos con categoría, tarjeta, deducible/no deducible. Regex: `^Gastos_Operativos_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\.csv$`
- Selección: `find_latest_gastos_operativos_csv(data_dir)` en `rtb_analisis.py`
- Función: `build_gastos_operativos_dashboard(rows, period_label, fecha_desde, fecha_hasta)`
- Snapshot: `dashboard_data/gastos_operativos_latest.json`
- Endpoint: `GET /api/dashboard/gastos_operativos`

### Inventario (9º tab — stock + margen bruto)
- `Crecimineto_inventario_YYYY-MM-DD_HH-MM.csv` *(typo "Crecimineto")* — snapshots de valor de inventario. Regex: `^Crecimineto_inventario_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\.csv$`
- `Partidas_facturas_ventas_YYYY-MM-DD_HH-MM.csv` — partidas de facturas de venta (surtido + margen). Regex: `^Partidas_facturas_ventas_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\.csv$`
- Seleccion: `find_latest_inventario_csv(data_dir)`, `find_latest_partidas_ventas_csv(data_dir)` en `rtb_analisis.py`
- Funcion: `build_inventario_dashboard(inventario_rows, ventas_rows, period_label, fecha_desde, fecha_hasta)`
- Snapshot: `dashboard_data/inventario_latest.json`
- Endpoint: `GET /api/dashboard/inventario`
- **Margen bruto** = `subtotal − costo_unitario_de_compra_formula × cantidad_solicitada` por partida. `subtotal = costo_unitario_v × cantidad_solicitada` (100% verificado).
- **Inventario snapshot**: filas con `tipo ∈ {Inventario, Productos sin movimiento}` agrupadas por `name` (ej. "Inventario Mayo - 2026"). Snapshot mas reciente = alphabetically last `name`.
- NO entra al consolidado Finanzas (el valor de ventas ya esta en Cobranza/Facturacion).

### Almacen (tab "Almacen" — reutiliza placeholder "Operacion", 3er tab visible)
- `Partidas_facturas_ventas_*.csv` — mismo CSV que Inventario (surtido/picking, campo `estado ∈ {Empacado, Pendiente, Faltante}`).
- `Partidas_facturas_compras_YYYY-MM-DD_HH-MM.csv` — partidas de facturas de compra (recepcion de proveedores). Regex: `^Partidas_facturas_compras_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\.csv$`
- Seleccion: `find_latest_partidas_compras_csv(data_dir)` en `rtb_analisis.py`
- Funcion: `build_almacen_dashboard(compras_rows, ventas_rows, period_label, fecha_desde, fecha_hasta, cotizaciones=None, facturas_compras=None)`
- Snapshot: `dashboard_data/almacen_latest.json`
- Endpoint: `GET /api/dashboard/almacen`
- **Fill rate** = `cantidad_llegada / cantidad_solicitada` — `cantidad_llegada` vacio (string "") = pendiente (None).
- **Validacion fisica**: `partida_validacion_fisica` es string `"TRUE"` / `"FALSE"`.
- Columnas del CSV compras tienen prefijo `partida_` (sin prefijo timestamp; no cambiar).
- **Nombre de cotizacion en faltantes**: `cotizaciones_a_clientes.0` (UUID) se resuelve a `Cotizacion_nombre` via lookup `{Cotizacion_id → Cotizacion_nombre}` del CSV de cotizaciones. Fallback al UUID si no se pasa `cotizaciones`.
- **Nombre de factura de compra en pendientes**: `partida_cotizacion.0` (UUID que apunta a `Factura_compra_id`) se resuelve a `Factura_compra_nombre` (ej. "PROVEEDOR SA - 42") via lookup del CSV `Facturas_Compras_*.csv`. Helper `_load_facturas_compras_rows(data_dir)` en `rtb_web.py` con fallback a `data_procesada/`.
- **Estado de surtido** (dona): patron identico a ventas — `renderAlmacenSurtidoChart` / `almacenSurtidoSliceAtEvent` / `setActiveAlmacenSurtido`. Canvas DPR-aware con `getBoundingClientRect` + `setTransform`. Slice activo +8px / opacidad 0.42 inactivos. Filas con `status-name`+`status-dot`+`--status-color`. Leyenda con `.legend-item`+`.legend-swatch`+`data-index`. Interaccion `mousemove`/`mouseleave`.
- **Recepcion de compras** (dona): `series.recepcion` — 3 estados: `100% recibido` (#57c5b6), `Parcial` (#d0b56b), `Pendiente` (#5b6673). Mismo patron de funciones: `renderAlmacenRecepcionChart` / `almacenRecepcionSliceAtEvent` / `setActiveAlmacenRecepcion`.

### Finanzas (consolidado — 7º tab, independiente de Logística)
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
| Canvas muestra `For&#225;neo` o `Aprob.&#8594;Envio` en lugar del texto real | Entidades HTML numéricas en `ctx.fillText()` — canvas NO las decodifica | Usar solo texto plano ASCII/Unicode directo. Al escribir regex JS dentro de strings Python usar `\\d` (no `\d`) |
| Dashboard no procesa datos aunque n8n terminó | `CSV_WAIT_ATTEMPTS` agotado (timeout de espera de CSVs) | Valor actual: 13200 s (220 min). Ajustar env var `RTB_CSV_WAIT_ATTEMPTS` sin rebuild |
| Gráfica "Distribucion ciclo total" en Logística muestra `$12`, `$6`... | `renderHBarCanvas` usaba `formatMoney` hardcoded para el texto de las barras | Pasar `valueFmt: (v) => v + ' ped.'` en la llamada del histograma |
| IVA por pagar en Finanzas muestra $0 o valor negativo confuso | Cuando `iva_trasladado = 0` (sin cobros en el periodo) el resultado es negativo — indica saldo a favor, no deuda | `renderFinanzasIva` ahora muestra "Saldo a favor" con valor absoluto cuando `iva_por_pagar < 0` |
| `levantar_dashboard.sh` falla en el último test del webhook (tarda 220 min) | `wait_for_changed_facturas` usa `sleep` real con 13200 intentos; el test no inyectaba sleep | `create_app` acepta `sleep=` injectable; test usa `sleep=lambda _t: None` |
| Tests de facturación en `test_webhook_app.py` fallan con `FileNotFoundError` en `find_latest_facturacion_csv` | Nombres de CSV en tests usaban formato `Facturas_2026-06.csv` — no pasan el regex allowlist que requiere `YYYY-MM-DD_HH-MM` | Renombrar a `Facturas_2026-06-02_10-00.csv` en los tests |
| Puerto 8000 ocupado por otro servicio local | Docker Compose concatena `ports` de base + override, por eso no basta con el override para cambiar el puerto | `docker-compose.override.yml` (`.gitignore`) sobreescribe el mapeo; usar `RTB_BASE_URL=http://localhost:8001` para el script |

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
python -m unittest tests/test_logistica_dashboard.py -v                # 44 tests
python -m unittest tests/test_inventario_dashboard.py -v               # 33 tests
python -m unittest tests/test_almacen_dashboard.py -v                  # 48 tests
# Suite completa sin FastAPI (328 tests):
python -m unittest tests/test_facturacion_dashboard.py tests/test_compras_dashboard.py tests/test_cobranza_dashboard.py tests/test_pagos_proveedores_dashboard.py tests/test_gastos_operativos_dashboard.py tests/test_finanzas_dashboard.py tests/test_logistica_dashboard.py tests/test_inventario_dashboard.py tests/test_almacen_dashboard.py -v
# Suite completa incluyendo tests de integracion FastAPI (369 tests):
python -m unittest discover -s tests -v
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
| 2026-06-08 | Nuevo módulo Logística (8º tab): 4 CSVs (aprobados/enviados/entregados/seguimiento_incompletos). Lead times calculados solo del CSV entregados vía `days_diff`. Las 3 vistas de n8n tienen ventanas de periodo independientes — NO son subconjuntos anidados; no usar ratio directo "entregados÷aprobados". `tiene_faltante` tiene typo "Aprbados" y "Segimiento" en prefijos. Campo `fecha_del_pedido` en seguimiento tiene clave malformada por n8n (prefijo duplicado sin separador) — se busca con `"fecha_del_pedido" in k`. No entra al consolidado Finanzas (montos ya están en ventas/cobranza). 44 tests nuevos. Suite total: 247 tests. |
| 2026-06-08 | Eliminados todos los acentos (tildes/enie) de `rtb_web.py`, `rtb_analisis.py` y `tests/`. Excepción: `"sí"` en `as_bool()` (linea ~122 de `rtb_analisis.py`) se preserva para parseo de valores booleanos de CSV. Entidades HTML numéricas (`&#225;`, `&#237;`, `&#8594;` etc.) también reemplazadas — el canvas NO las decodifica, muestra el literal. Al escribir JS/HTML dentro de strings Python, usar solo ASCII/Unicode directo en textos visibles. |
| 2026-06-08 | Sección "Estado de pedidos aprobados" en Logística rediseñada con el patrón visual de "Distribución por categoría" (Gastos Operativos): leyenda HTML `<div class="pie-legend">` con `<button class="legend-item">`, `status-name`+`status-dot` en tabla, interactividad bidireccional dona↔leyenda↔tabla. Helpers separados: `renderLogisticaEstadoPieChart`, `logisticaEstadoSliceAtEvent`, `setActiveLogisticaEstado`. |
| 2026-06-08 | Command Center: nuevo endpoint `GET /api/data-files` + indicador "Archivos en data/" en el sidebar (badge verde/gris con conteo y lista de nombres). Se refresca automáticamente al cargar y después de cada operación. |
| 2026-06-08 | `CSV_WAIT_ATTEMPTS` aumentado de 600 a 13200 (220 min × 60 s). Evita que el dashboard deje de esperar cuando n8n tarda más de 10 min en descargar todos los CSVs. |
| 2026-06-12 | `renderHBarCanvas` ahora acepta `opts.valueFmt` para formatear el texto de las barras. Antes era `formatMoney` hardcoded. El histograma de ciclo total en Logística usa `valueFmt: (v) => v + ' ped.'`. |
| 2026-06-12 | IVA estimado en Finanzas: `renderFinanzasIva` reescrito — usa `renderHBarCanvas` (una barra por concepto, valores absolutos) en lugar de `drawGroupedBarChart` con dos series idénticas. Cuando `iva_por_pagar < 0` muestra "Saldo a favor" en teal. El IVA trasladado es base caja (sobre cobros); si no hay cobros en el periodo = $0 es correcto. |
| 2026-06-12 | `create_app` acepta `sleep: Callable` injectable para tests. `actualizar_datos` pasa `app.state.sleep` a `wait_for_changed_cotizaciones` y `wait_for_changed_facturas`. `levantar_dashboard.sh`: `BASE_URL` configurable via `${RTB_BASE_URL:-http://localhost:8000}`. Suite total: 298 tests. |
| 2026-06-13 | Nuevos modulos Inventario (tab "Inventario") y Almacen (tab "Almacen", reutiliza placeholder "Operacion"). CSVs: `Crecimineto_inventario_*.csv`, `Partidas_facturas_ventas_*.csv`, `Partidas_facturas_compras_*.csv`. Backend: `build_inventario_dashboard` (stock snapshot + margen bruto por SKU/pedido), `build_almacen_dashboard` (surtido Empacado/Pendiente/Faltante + fill rate recepcion + validacion fisica). Margen = `subtotal - costo_unitario_de_compra_formula * cantidad_solicitada`. `cantidad_llegada` vacio = pendiente (None). Columnas compras con prefijo `partida_` (sin timestamp). Endpoints `/api/dashboard/inventario` y `/api/dashboard/almacen`. Wired en ambos bloques publish (webhook + regenerar-snapshot). Frontend con dona surtido (patron Logistica), HBar fill rate, tablas HTML (no canvas — evita crash SIGILL en grid). 71 tests nuevos (33 + 38). Suite sin FastAPI: 318 tests. |
| 2026-06-13 | Almacen — Estado de surtido rediseñado con patron identico a ventas: `renderAlmacenSurtidoChart` / `almacenSurtidoSliceAtEvent` / `setActiveAlmacenSurtido`. Canvas DPR-aware (`getBoundingClientRect` + `setTransform`), slice activo +8px, opacidad 0.42 para inactivos, tooltip `placeTooltipNear`, filas con `status-name`+`status-dot`, leyenda con `.legend-item`+`.legend-swatch`+`data-index`, interaccion `mousemove`/`mouseleave`. Columna `% monto` agregada al thead. |
| 2026-06-13 | Almacen — "Partidas con material faltante": campo `cotizacion` resuelve UUID (`cotizaciones_a_clientes.0`) a `Cotizacion_nombre` via lookup del CSV de cotizaciones pasado como `cotizaciones=` a `build_almacen_dashboard`. Fallback al UUID si no se pasa. |
| 2026-06-13 | Almacen — "Recepcion de compras" sustituye el HBar de fill rate por dona con patron Estado de surtido. Backend: `series.recepcion` = `[{estado, n, color}]` con 3 estados: `100% recibido` (#57c5b6), `Parcial` (#d0b56b), `Pendiente` (#5b6673). Frontend: `renderAlmacenRecepcionChart` / `almacenRecepcionSliceAtEvent` / `setActiveAlmacenRecepcion`. |
| 2026-06-13 | Almacen — "Partidas pendientes de recepcion": campo `Fact. compra` resuelve UUID (`partida_cotizacion.0`) a `Factura_compra_nombre` (ej. "PROVEEDOR SA - 42") via lookup del CSV `Facturas_Compras_*.csv`, pasado como `facturas_compras=` a `build_almacen_dashboard`. Helper `_load_facturas_compras_rows(data_dir)` en `rtb_web.py` con fallback a `data_procesada/`. Suite sin FastAPI: 328 tests. |
| 2026-06-05 | Nuevo módulo Finanzas (7º tab): consolidación pura de los 5 módulos financieros. `build_finanzas_dashboard` recibe los 5 sub-dicts ya construidos (no CSVs). Dos lentes paralelas: Devengado (facturación vs compras+gastos) y Caja (cobranza vs pagos+gastos). Gastos en ambas bases. IVA trasladado derivado de lo cobrado (`cobrado − cobrado/1.16`). Snapshot `finanzas_latest.json`. 58 tests nuevos. Suite completa: 188 tests. |
| 2026-06-13 | Inventario — "Valor de inventario" rediseñado: dona (patron identico a "Estado de cotizacion" en Ventas) con 2 rebanadas: `Con movimiento` (inv_activo) y `Sin movimiento` (inv_sin_mov). Centro muestra valor total (`inv_total`) en reposo; al hover muestra % de la rebanada. Reemplaza el HBar de snapshots mensuales. Funciones: `renderInvValorChart` / `invValorSliceAtEvent` / `setActiveInvValor` / `renderInvValor`. Interactividad dona↔leyenda↔tabla. |
| 2026-06-13 | Inventario — "Margen bruto por periodo" rediseñado: `weekly-layout` (tabla + canvas), inspirado en "Comportamiento semanal" de Ventas. 3 lineas (Venta `#276f86`, Costo `#d96058`, Margen `#57c5b6`) + tendencias punteadas (Venta y Margen). Dots + halos en puntos activos. Hover sincroniza canvas↔tabla. Leyenda `chart-legend` con `legend-chip`/`legend-line`. Estado: `inventarioMargenState`. Tabla: Periodo / Venta / Costo / Margen / % Margen. |
| 2026-06-13 | Inventario — "Top pedidos por margen": `build_inventario_dashboard` ahora acepta `cotizaciones=None`. Construye lookup `Cotizacion_id → Cotizacion_nombre` y resuelve los UUIDs de `cotizaciones_a_clientes.0` a nombres legibles. `publish_inventario_snapshot` carga cotizaciones con `load_cotizaciones(data_dir)` (con fallback a `data_procesada/`). |

---

## Nota de despliegue — git push

**Excluir siempre de commits/push:** `docker-compose.yml` — los volúmenes usan rutas absolutas de la máquina local (`/home/dhguilleng/Nextcloud/Sistemas/REPORTES/Dashboard_interactivo_reportes/{data,data_procesada,dashboard_data}`) que no aplican en otros entornos. El archivo en el repo mantiene rutas relativas (`./data`, `./data_procesada`, `./dashboard_data`).

Todo lo demás (`rtb_web.py`, `rtb_analisis.py`, `tests/`, `CLAUDE.md`, etc.) se sube normalmente.
