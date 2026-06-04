# Dashboard RTB - Contexto y diccionario

Documento de referencia: que datos consume el dashboard, que KPIs muestra, y donde se calcula cada uno. Fuente unica de verdad: `rtb_analisis.py`. Si la UI muestra algo distinto a este doc, el codigo gana - actualiza el doc.

## Dominio

RTB (Recursos Tecnologicos del Bajio) genera cotizaciones desde Notion. Cada cotizacion tiene un estado, un total con IVA, una localidad/rol comercial, un tipo de pago y opcionalmente un flag `Ariba` (cuando el cliente es Grupo Posadas y compra via SAP Ariba). El dashboard resume cada periodo con KPIs de volumen, conversion, tiempos y desglose por tipo de pago / cliente.

## CSV de entrada

n8n exporta cotizaciones desde Notion y deposita el CSV como `data/Cotizaciones_<timestamp>.csv` (via Nextcloud sync). El dashboard lo consume con `read_csv` (`rtb_analisis.py`) cuando se completa el flujo de `publish_ventas_snapshot`.

### Columnas criticas

| Columna | Uso | Notas |
|---|---|---|
| `Cotizacion_id` | Identificador, signals | Texto |
| `Cotizacion_nombre` | Etiqueta en tablas/signals | Texto |
| `Cliente` | Top clientes, signals | Texto |
| `Estado_cotizacion` | Conversion, filtros | Valores: `Aprobada`, `Expirada`, otros |
| `Total` | Todos los montos | Numerico; helper `f()` parsea (acepta strings con comas) |
| `Ariba` | Filtro Ariba | Truthy si valor es `true`/`TRUE`/`1`/etc (helper `truthy()`) |
| `Fecha_creacion` | Tiempos, semanas/meses | ISO `YYYY-MM-DD` |
| `Fecha_aprobacion` | Tiempos de aprobacion | Puede venir vacia (cuenta como "Sin fechas") |
| `Tipo_pago.0`, `Tipo_pago.1` | Mix de pago | Multi-select de Notion aplanado |
| `Localidad` | Rol comercial | Texto; default `Sin rol` |

Columnas no listadas son ignoradas. Si Notion agrega/renombra una columna critica, el cambio se hace en `rtb_analisis.py`.

## KPIs visibles

Calculados en `rtb_analisis.compute_ventas` y expuestos por `build_ventas_dashboard` (dict bajo `kpis`). La UI los consume desde `kpis[<clave>]` en `renderKpis` (`rtb_web.py`).

### Grupo Cotizaciones

| Clave | Definicion |
|---|---|
| `total_cotizaciones` | Cuenta de filas del CSV |
| `total_cotizado_iva` | Suma de `Total` de todas las cotizaciones |
| `ticket_promedio_cotizado` | `total_cotizado / total_cotizaciones` |

### Grupo Aprobadas

| Clave | Definicion |
|---|---|
| `cotizaciones_aprobadas` | Cuenta de filas con `Estado_cotizacion == "Aprobada"` |
| `monto_aprobado_iva` | Suma de `Total` de las aprobadas |
| `ticket_promedio_aprobado` | `monto_aprobado / cotizaciones_aprobadas` |

### Grupo Conversion

| Clave | Definicion |
|---|---|
| `aprobacion_cantidad_pct` | `aprobadas / cotizaciones` |
| `aprobacion_monto_pct` | `monto_aprobado / total_cotizado` |
| `diferencia_aprobacion_pct` | `aprobacion_monto_pct - aprobacion_cantidad_pct` (en pp; negativo = aprobamos cotizaciones de ticket bajo) |

### Grupo Ariba cotizado

Subset filtrado por `truthy(Ariba)`. **Las aprobadas Ariba son siempre subset de las cotizadas Ariba** - es matematicamente imposible tener mas aprobadas que cotizadas.

| Clave | Definicion |
|---|---|
| `ariba_cotizadas` | Filas Ariba totales |
| `monto_ariba_cotizado` | Suma de `Total` de Ariba |
| `ticket_ariba_cotizado` | `monto_ariba_cotizado / ariba_cotizadas` |

### Grupo Ariba aprobado

| Clave | Definicion |
|---|---|
| `ariba_aprobadas` | Filas Ariba con `Estado_cotizacion == "Aprobada"` |
| `monto_ariba_aprobado` | Suma de `Total` de Ariba aprobadas |
| `ariba_aprobadas_pct_cantidad` | `ariba_aprobadas / total_cotizaciones` (% sobre TODO el universo, no solo Ariba) |
| `ariba_aprobadas_pct_monto` | `monto_ariba_aprobado / total_cotizado` |
| `diferencia_ariba_aprobada_pct` | Diferencia entre las dos anteriores |

### Grupo Ariba conversion

Conversion **interna** de Ariba (aprobado / cotizado dentro del subset Ariba, no contra el universo completo).

| Clave | Definicion |
|---|---|
| `ariba_conv_q` | `ariba_aprobadas / ariba_cotizadas` |
| `ariba_conv_m` | `monto_ariba_aprobado / monto_ariba_cotizado` |
| `diferencia_ariba_conv` | `ariba_conv_m - ariba_conv_q` |

### Tiempos de aprobacion

Solo cotizaciones con `Estado_cotizacion == "Aprobada"` se evaluan. Para cada una se calcula `Fecha_aprobacion - Fecha_creacion` en dias.

| Clave (`series.tiempos_aprobacion.stats`) | Definicion |
|---|---|
| `promedio`, `mediana`, `maximo` | Estadisticas en dias sobre filas con ambas fechas |
| `n_con_datos` | Aprobadas con ambas fechas validas |
| `n_sin_fechas` | Aprobadas sin `Fecha_aprobacion` (excluidas del calculo, pero contadas en la tarjeta) |
| `n_no_aprobadas` | `total_cotizaciones - cotizaciones_aprobadas` (NO se muestra en UI, queda en payload por compatibilidad) |

Histograma: buckets `0..7` y `8+` dias. Rangos: `Mismo dia`, `1-3 dias`, `4-7 dias`, `>7 dias`.

## Series temporales

`build_temporal_series` (`rtb_analisis.py`) genera buckets semanales o mensuales segun el rango:

- Si periodo cae dentro de un solo mes -> buckets semanales `S1..S5` (S1=1-7, S2=8-14, S3=15-21, S4=22-28, S5=29-fin).
- Si periodo cruza meses -> buckets mensuales (`YYYY-MM`).

Cada bucket trae: `cotizaciones`, `aprobadas`, `cotizado`, `aprobado`, y `tiempo_promedio_aprobacion`.

## Signals / alertas

`build_ventas_signals` produce alertas operativas (visibles eventualmente como notificaciones / panel). Tipos actuales:

- `tipo_pago_sin_definir`: >50% de cotizaciones sin `Tipo_pago`. Riesgo.
- `aprobada_sin_pedido`: aprobadas sin pedido asociado. Atencion.
- `ariba_aprobada`: cotizaciones Ariba aprobadas (requieren seguimiento PO). Atencion.
- `expirada_monto_alto`: expiradas con `Total >= ticket_promedio`. Riesgo.
- `semana_baja_conversion`: semana con monto relevante pero conversion < promedio del periodo. Atencion.

## Flujo de la snapshot

`dashboard_data/ventas_latest.json` es el archivo que sirve la API:

```
{
  "generated_at": "<ISO UTC>",
  "period": {"start": "...", "end": "...", "label": "..."},
  "file": "Cotizaciones_<ts>.csv",
  "processed_file": "data_procesada/<ts>_ventas/<file>",
  "dashboard": {
    "ventas": {
      "periodo": "...",
      "kpis": { ... },           # las claves de arriba
      "m1": { ... },             # output interno de compute_ventas
      "series": { ... },         # temporal, semanas, estados, roles, tiempos_aprobacion, tendencias
      "tables": { ... },         # top_clientes_cotizan, top_clientes_aprueban, tipos_pago, cotizaciones
      "signals": [ ... ]
    }
  }
}
```

Si agregas una clave nueva en `kpis`, **debes regenerar la snapshot** (re-correr el flujo con el ultimo CSV en `data_procesada/`). Si no, la UI mostrara `0`/`$0`/`0.0%` para esa clave (helper `kpiValue` devuelve esos defaults para claves ausentes).

## Cosas que se ven raras pero no son bug

- **Ariba conversion = 100%**: pasa cuando todas las filas con flag Ariba estan en estado Aprobada. Es realista si el operador solo marca el flag al recibir la PO. Verificar en `data_procesada/` el ultimo CSV.
- **Cotizaciones por encima del ticket promedio expiradas**: aparecen como signal de riesgo aunque sea normal en periodos cortos. Filtrar visualmente si distraen.
- **Snapshot desfasada**: si `dashboard_data/ventas_latest.json` no se actualiza despues de disparar el formulario, el problema es timeout del wait (`RTB_CSV_WAIT_ATTEMPTS`) o un CSV nuevo aterrizando despues del cierre del request. Procesarlo manualmente con el script de `publish_ventas_snapshot`.


## Modulo Facturacion

La pestaña `Facturación` consume tres exports de n8n: `Cotizaciones_*.csv`,
`Facturas_*.csv` y `Facturas_Secundarias_*.csv`. La fuente de verdad es
`build_facturacion_dashboard` en `rtb_analisis.py`; la API sirve el snapshot
independiente `dashboard_data/facturacion_latest.json`.

### Columnas criticas de facturacion

| Columna | Uso |
|---|---|
| `Factura_id` | Identificador para deduplicar principal y secundaria |
| `Factura_cotizacion` | Relacion con `Cotizacion_id` para estimar rezago |
| `Factura_Estado_Aprobacion` | Solo `Aprobada` puede ser factura vigente |
| `Estado_Factura` | Desglose operativo por estado |
| `Fecha_Facturacion` / `Fecha_Facturacion_Secundaria` | Filtro temporal y serie semanal o mensual |
| `#_Factura` | Folio requerido para considerar vigente el registro; se extrae `Cxxxx` si hay notas embebidas |
| `Factura_Cancelada` | **Informativo**: guarda el folio anterior sustituido. NO determina cancelacion |
| `Monto_primer_factura` / `Monto_segunda_factura` | Si NO es nulo (ni cadena vacia) sustituye a `Total`; cero literal cuenta como valor valido |
| `Fecha_Validacion` / `Fecha_Validacion_Secundaria` | Cobertura documental de validacion |
| `Fecha_Asociacion` / `Fecha_Asociacion_Secundaria` | Cobertura documental de asociacion |

### KPIs visibles de facturacion

| Clave | Definicion |
|---|---|
| `facturas_vigentes` | Facturas con `Factura_Estado_Aprobacion == Aprobada`, folio, fecha, sin cancelar y sin duplicar |
| `monto_facturado_vigente` | Suma de `round(Monto_primer/segunda_factura, 2)` si no nulo, else `round(Total, 2)`; resultado final redondeado a 2 dec |
| `ticket_promedio_facturado` | `monto_facturado_vigente / facturas_vigentes` |
| `facturas_principales` | Vigentes provenientes de `Facturas_*.csv` |
| `facturas_secundarias` | Vigentes adicionales provenientes de `Facturas_Secundarias_*.csv` |
| `facturas_canceladas` / `monto_cancelado` | Registros con `Factura_Estado_Aprobacion ∈ {Cancelada, Cancelado}` del periodo |
| `rezago_estimado_cantidad` / `rezago_estimado_monto` | Cotizaciones aprobadas sin factura vigente asociada |
| `cobertura_validacion_pct` | Vigentes con fecha de validacion / vigentes |
| `cobertura_asociacion_pct` | Vigentes con fecha de asociacion / vigentes |

### Signals de facturacion

- `factura_captura_incompleta`: aprobada sin folio o fecha de facturacion.
- `factura_duplicada`: mismo identificador presente mas de una vez entre exports.
- `rezago_facturacion_estimado`: cotizacion aprobada sin factura vigente asociada.
- `factura_folio_captura_sucia`: campo `#_Factura` contiene notas extra ademas del codigo `Cxxxx`; el folio se normaliza automaticamente pero hay que corregir en Notion.
- `segunda_factura_pendiente`: `Monto_primer_factura` esta lleno pero no hay entrada en `Facturas_Secundarias_*.csv` — la segunda parte aun no se ha emitido. `metricas.monto_pendiente = Total − primer`.
- `factura_partidas_desbalanceadas`: cuando ambas partes existen, `Monto_primer_factura + Monto_segunda_factura` difiere mas de $0.05 del `Total` — indica error de captura en Notion.


## Modulo Compras

La pestaña `Compras` consume un solo export de n8n: `Facturas_Compras_*.csv`.
**No maneja pagos, CxP ni cobranza.** El modulo muestra exclusivamente el lado
de facturacion recibida (IVA acreditable). La fuente de verdad es
`build_compras_dashboard` en `rtb_analisis.py`; la API sirve el snapshot
`dashboard_data/compras_latest.json`.

El CSV `Facturas_Compras_Pagadas_*.csv` puede seguir llegando via n8n pero no
se consume en este modulo.

### Columnas criticas de compras

| Columna | Uso |
|---|---|
| `Factura_compra_nombre` | Nombre/ID del proveedor |
| `Factura_compra_subtotal` | Subtotal sin IVA ni envio |
| `Fcatura_compra_iva` | IVA 16% (typo en export n8n, sin corregir) |
| `Factura_compra_envio` | Costo de envio |
| `Factura_compra_total` | Total con IVA; si es 0 se recalcula como sub+iva+env |
| `Facatura_compra_fecha_factura` | Fecha del CFDI (typo en export n8n, sin corregir) |
| `Factura_compra_tipo` | Tipo de pago |
| `Factura_compra_uso_cfdi` | Clave de uso CFDI (G01, G03, etc.) |
| `Factura_compra_estatus_factura` | Estado del CFDI: `Facturada`, `Factura Cancelada`, `Sin status` |

### Regla de canceladas

Las facturas con `Factura_compra_estatus_factura == "Factura Cancelada"` se
**excluyen de todos los totales** (`n_fc`, `sub_fc`, `iva_fc`, `tot_fc`).
Se reportan como metricas separadas `n_canc` y `tot_canc` y aparecen en el
desglose "Estado de la factura" para visibilidad.

### KPIs y series del modulo

| Campo | Descripcion |
|---|---|
| `kpis.n_fc` | Facturas recibidas (excluye canceladas) |
| `kpis.sub_fc` | Subtotal del periodo |
| `kpis.iva_fc` | IVA acreditable del periodo |
| `kpis.tot_fc` | Total c/IVA del periodo |
| `kpis.n_canc` | Facturas canceladas |
| `kpis.tot_canc` | Monto cancelado |
| `series.estado_factura` | Desglose por estado del CFDI (incluye canceladas) |
| `series.tipo_pago` | Desglose por tipo de pago (excluye canceladas) |
| `series.uso_cfdi` | Desglose por uso de CFDI (excluye canceladas) |
| `series.temporal` | Comportamiento temporal (excluye canceladas) |
| `tables.top_proveedores` | Top 10 proveedores por monto (excluye canceladas) |
