# Mapa del proyecto

## Entradas

- `data/`: carpeta esperada para CSVs nuevos. Actualmente esta vacia.
- `data_procesada/YYYY-MM-DD_HH-MM/`: CSVs usados en corridas anteriores. Abril 2026 tiene varias copias historicas.

## Codigo

- `generar_reporte.py`
  - CLI principal.
  - Resuelve periodo con `--start` y `--end`, por nombres de archivo o por fechas dentro de filas.
  - Llama `load_all()`, `compute()`, `render_md()`, `render_html()`.
  - Escribe salidas en `reportes/<periodo>/`.
  - Mueve CSVs procesados.

- `rtb_analisis.py`
  - Utilidades: `f`, `parse_date`, `week`, `avg`, `med`, `days_diff`, `parse_tp`, `histog`, `read_csv`, `prov_name`.
  - `load_all(data_dir)`: localiza CSVs por prefijo.
  - `compute(D)`: calcula todos los modulos.

- `rtb_html.py`
  - Embebe `chart.umd.min.js`.
  - Define CSS, helpers de tabla/KPI/insight/chart.
  - Renderiza secciones HTML y JS de graficas.

- `rtb_markdown.py`
  - Renderiza reporte textual para auditoria y comparacion rapida.

- `01_analizar.py`
  - Script exploratorio/historico. No parece ser la entrada principal.

## Salidas

- `reportes/<periodo>/RTB_Cierre_<periodo>.html`
- `reportes/<periodo>/RTB_Cierre_<periodo>.md`

## Contrato de datos interno

`compute(D)` devuelve:

- `R["m1"]`: Ventas/cotizaciones.
- `R["m2a"]`: Pedidos creados, estados, tiempos y riesgos.
- `R["m2b"]`: Pedidos enviados/entregados.
- `R["m2c"]`: Facturacion primaria/secundaria.
- `R["m2d"]`: Cobranza e ingresos.
- `R["m3"]`: Compras/proveedores.
- `R["m4"]`: Inventario, entradas, salidas, snapshots.
- `R["m5"]`: Gastos operativos.
- `R["pl"]`: P&L operativo y flujo.
- `R["hero"]`: KPIs ejecutivos.

## Puntos sensibles

- Cualquier cambio en `rtb_analisis.py` puede modificar Markdown y HTML.
- `rtb_html.py` contiene mucho HTML como strings; editar con cuidado y validar sintaxis Python.
- `generar_reporte.py` mueve CSVs de `data/`; para pruebas usa copia temporal o datos ya procesados.
- Las fechas vienen en formatos variados, incluyendo JSON con `start`; usa `parse_date()`.
- Algunos nombres de columnas tienen acentos normalizados o caracteres escapados desde Notion.

## Contrato temporal compartido

Toda grafica o modulo nuevo que agrupe datos por fecha debe usar `temporal_axis()` y `aggregate_temporal()` de `rtb_analisis.py`. No agregues agrupaciones semanales locales nuevas.

Regla unica:

- Si `start` y `end` pertenecen al mismo mes, el eje usa `S1` a `S5`.
- Si el periodo cruza un limite mensual, el eje usa meses calendario (`Abr 2026`, `May 2026`, etc.).
- `compute(D, period=period)` publica el eje comun en `R["temporal"]`.
- Ventas, pedidos, compras y OPEX exponen sus series en `temporal_cot`, `temporal_ped`, `temporal_fc` y `temporal_gas`.
- Las claves historicas `sem_*` se conservan solo por compatibilidad con calculos existentes. HTML, Markdown y superficies nuevas deben consumir `temporal_*`.
