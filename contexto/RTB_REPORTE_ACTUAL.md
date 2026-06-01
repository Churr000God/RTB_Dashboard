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
