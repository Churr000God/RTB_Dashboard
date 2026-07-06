#!/usr/bin/env python3
"""Generador de PDF y ZIP para los reportes del dashboard RTB.

Diseño:
- Completamente independiente de FastAPI (testeable sin servidor).
- Un PDF por modulo + un PDF combinado empaquetados en un ZIP.
- Renderizador generico que recorre la estructura uniforme de cada
  payload: periodo / kpis / series / tables / signals.
- ASCII-only en strings del PDF (sin tildes ni enies) — regla del repo.
"""

import io
import re
import zipfile
from datetime import datetime
from typing import Any

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ---------------------------------------------------------------------------
# Paleta de colores (alineada al tema del dashboard)
# ---------------------------------------------------------------------------
_C_PRIMARY   = colors.HexColor("#276f86")   # azul principal
_C_TEAL      = colors.HexColor("#57c5b6")   # teal / acento
_C_GOLD      = colors.HexColor("#d0b56b")   # dorado
_C_RED       = colors.HexColor("#d96058")   # rojo
_C_DARK      = colors.HexColor("#1c3f4e")   # texto oscuro
_C_MUTED     = colors.HexColor("#6e8fa0")   # gris mutado
_C_BG        = colors.HexColor("#eef5f7")   # fondo claro
_C_WHITE     = colors.white
_C_BLACK     = colors.black

# Colores rotativos para graficas de barras / pie
_CHART_COLORS = [
    _C_PRIMARY, _C_TEAL, _C_GOLD, _C_RED,
    colors.HexColor("#5b6673"), colors.HexColor("#2d7d9a"),
    colors.HexColor("#a5c8d8"), colors.HexColor("#e8b87b"),
]

_PAGE_W, _PAGE_H = A4
_MARGIN = 1.8 * cm
_CONTENT_W = _PAGE_W - 2 * _MARGIN

# Limite de filas en tablas para no inflar el PDF
_MAX_TABLE_ROWS = 25

# ---------------------------------------------------------------------------
# Estilos
# ---------------------------------------------------------------------------

def _styles():
    base = getSampleStyleSheet()
    normal = base["Normal"]
    return {
        "title":   ParagraphStyle("title",   parent=normal, fontSize=22, textColor=_C_DARK,
                                  fontName="Helvetica-Bold", spaceAfter=4),
        "subtitle":ParagraphStyle("subtitle",parent=normal, fontSize=11, textColor=_C_MUTED,
                                  fontName="Helvetica", spaceAfter=12),
        "h2":      ParagraphStyle("h2",      parent=normal, fontSize=13, textColor=_C_PRIMARY,
                                  fontName="Helvetica-Bold", spaceBefore=10, spaceAfter=4),
        "h3":      ParagraphStyle("h3",      parent=normal, fontSize=11, textColor=_C_DARK,
                                  fontName="Helvetica-Bold", spaceBefore=6, spaceAfter=3),
        "body":    ParagraphStyle("body",    parent=normal, fontSize=9,  textColor=_C_DARK,
                                  fontName="Helvetica"),
        "bullet":  ParagraphStyle("bullet",  parent=normal, fontSize=8,  textColor=_C_MUTED,
                                  fontName="Helvetica", leftIndent=12, spaceAfter=2),
        "cover_title": ParagraphStyle("cover_title", parent=normal, fontSize=28, textColor=_C_WHITE,
                                      fontName="Helvetica-Bold", alignment=TA_CENTER, spaceAfter=8),
        "cover_sub":   ParagraphStyle("cover_sub",   parent=normal, fontSize=13, textColor=_C_BG,
                                      fontName="Helvetica", alignment=TA_CENTER),
        "toc_item":    ParagraphStyle("toc_item",    parent=normal, fontSize=10, textColor=_C_DARK,
                                      fontName="Helvetica", spaceAfter=3),
        "cell_right":  ParagraphStyle("cell_right",  parent=normal, fontSize=8, alignment=TA_RIGHT,
                                      fontName="Helvetica"),
        "cell_left":   ParagraphStyle("cell_left",   parent=normal, fontSize=8, alignment=TA_LEFT,
                                      fontName="Helvetica"),
    }


# ---------------------------------------------------------------------------
# Utilitarios
# ---------------------------------------------------------------------------

def prettify_label(key: str) -> str:
    """Convierte clave_maquina -> 'Clave maquina' (sin tildes/enies)."""
    s = re.sub(r"[_\-]+", " ", str(key)).strip()
    return s[:1].upper() + s[1:] if s else ""


def _slug(label: str) -> str:
    """Convierte 'Pagos Proveedores' -> 'pagos_proveedores' para nombre de archivo."""
    s = re.sub(r"[^a-zA-Z0-9]+", "_", label.lower()).strip("_")
    return s or "modulo"


def _fmt_value(v: Any) -> str:
    """Formatea un valor para mostrarlo en tabla KPI."""
    if isinstance(v, bool):
        return "Si" if v else "No"
    if isinstance(v, float):
        if v != v:          # NaN
            return "-"
        if abs(v) >= 1000:
            return f"{v:,.2f}"
        if v == int(v) and abs(v) < 1e9:
            return f"{int(v):,}"
        return f"{v:.4f}".rstrip("0").rstrip(".")
    if isinstance(v, int):
        return f"{v:,}"
    if v is None:
        return "-"
    return str(v)


def _is_money_key(key: str) -> bool:
    """Heuristica: la clave contiene 'monto', 'total', 'costo', 'venta', 'cobr', 'pago'."""
    k = key.lower()
    return any(t in k for t in ("monto", "total", "costo", "venta", "cobr", "pago", "precio", "ingreso", "egreso"))


def _table_style_header():
    return TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), _C_PRIMARY),
        ("TEXTCOLOR",    (0, 0), (-1, 0), _C_WHITE),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [_C_WHITE, colors.HexColor("#f0f6f8")]),
        ("GRID",         (0, 0), (-1, -1), 0.3, colors.HexColor("#d8e3ea")),
        ("TOPPADDING",   (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
        ("LEFTPADDING",  (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("ALIGN",        (0, 0), (-1, 0),  "CENTER"),
    ])


# ---------------------------------------------------------------------------
# Construccion de graficas
# ---------------------------------------------------------------------------

def _make_bar_chart(labels: list[str], values: list[float], title: str = "", width: float = _CONTENT_W, height: float = 5 * cm) -> Drawing | None:
    """Genera un VerticalBarChart de reportlab."""
    if not values or all(v == 0 for v in values):
        return None
    d = Drawing(width, height + 1.2 * cm)
    bc = VerticalBarChart()
    bc.x = 40
    bc.y = 30
    bc.width = width - 60
    bc.height = height - 10
    bc.data = [values]
    bc.bars[0].fillColor = _C_PRIMARY
    bc.categoryAxis.categoryNames = [str(l)[:12] for l in labels]
    bc.categoryAxis.labels.fontSize = 7
    bc.categoryAxis.labels.angle = 20 if len(labels) > 6 else 0
    bc.categoryAxis.labels.dy = -6
    bc.valueAxis.labels.fontSize = 7
    bc.valueAxis.forceZero = True
    if title:
        d.add(String(width / 2, height + 1.0 * cm, title,
                     fontSize=9, fillColor=_C_DARK, textAnchor="middle"))
    d.add(bc)
    return d


def _make_pie_chart(labels: list[str], values: list[float], title: str = "", width: float = 8 * cm, height: float = 6 * cm) -> Drawing | None:
    """Genera un Pie chart de reportlab."""
    values = [max(v, 0) for v in values]
    if not values or sum(values) == 0:
        return None
    d = Drawing(width, height + 1.0 * cm)
    pie = Pie()
    pie.x = width / 2 - 2.5 * cm
    pie.y = 0.8 * cm
    pie.width = 5 * cm
    pie.height = 5 * cm
    pie.data = values
    pie.labels = [str(l)[:16] for l in labels]
    pie.sideLabels = True
    pie.sideLabelsOffset = 0.04
    for i in range(len(values)):
        pie.slices[i].fillColor = _CHART_COLORS[i % len(_CHART_COLORS)]
        pie.slices[i].strokeColor = _C_WHITE
        pie.slices[i].strokeWidth = 0.5
    pie.slices.fontSize = 7
    if title:
        d.add(String(width / 2, height + 0.8 * cm, title,
                     fontSize=9, fillColor=_C_DARK, textAnchor="middle"))
    d.add(pie)
    return d


# ---------------------------------------------------------------------------
# Renderizadores de secciones del payload
# ---------------------------------------------------------------------------

def _render_kpis(kpis: dict, styles: dict) -> list:
    """Renderiza el dict kpis como una tabla de 2 columnas (Label | Valor)."""
    if not kpis:
        return []
    flowables = [Paragraph("KPIs del periodo", styles["h2"])]
    # Filtrar claves internas / listas / dicts anidados
    rows = []
    for k, v in kpis.items():
        if isinstance(v, (dict, list)):
            continue
        rows.append([Paragraph(prettify_label(k), styles["cell_left"]),
                     Paragraph(_fmt_value(v),     styles["cell_right"])])
    if not rows:
        return []
    col_w = [_CONTENT_W * 0.68, _CONTENT_W * 0.32]
    t = Table(rows, colWidths=col_w)
    t.setStyle(TableStyle([
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS",(0, 0), (-1, -1), [_C_WHITE, colors.HexColor("#f0f6f8")]),
        ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#d8e3ea")),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("ALIGN",         (1, 0), (1, -1),  "RIGHT"),
    ]))
    flowables.append(t)
    return flowables


def _render_series(series: dict, styles: dict) -> list:
    """Renderiza series temporales (periodos) y de estado (pie) con graficas y tablas."""
    flowables = []
    if not series:
        return flowables

    for serie_key, serie_val in series.items():
        label = prettify_label(serie_key)

        # ---- Serie temporal: dict con clave "periodos" (lista de periodos) ----
        if isinstance(serie_val, dict) and "periodos" in serie_val:
            periodos = serie_val["periodos"]
            if not periodos:
                continue
            # Detectar metricas numericas (excluir 'key', 'etiqueta', 'granularidad')
            sample = periodos[0]
            metric_keys = [k for k, v in sample.items()
                           if k not in ("key", "etiqueta", "granularidad") and isinstance(v, (int, float))]
            if not metric_keys:
                continue
            period_labels = [p.get("etiqueta", p.get("key", "")) for p in periodos]
            # Una grafica por metrica (max 3 metricas para no sobrecargar)
            flowables.append(Paragraph(label, styles["h2"]))
            for mk in metric_keys[:3]:
                vals = [p.get(mk, 0) for p in periodos]
                chart = _make_bar_chart(period_labels, vals,
                                        title=prettify_label(mk),
                                        width=_CONTENT_W, height=4.5 * cm)
                if chart:
                    flowables.append(chart)
                    flowables.append(Spacer(1, 3 * mm))
            # Tabla resumen de periodos (todas las metricas)
            header = ["Periodo"] + [prettify_label(mk) for mk in metric_keys[:6]]
            t_rows = [[p.get("etiqueta", p.get("key", ""))] + [_fmt_value(p.get(mk, 0)) for mk in metric_keys[:6]]
                      for p in periodos]
            col_w = [_CONTENT_W * 0.22] + [(_CONTENT_W * 0.78) / min(len(metric_keys), 6)] * min(len(metric_keys), 6)
            _render_simple_table(flowables, styles, header, t_rows, col_w)
            continue

        # ---- Serie de estados: lista de dicts con "estado" + numeros ----
        if isinstance(serie_val, list) and serie_val and isinstance(serie_val[0], dict):
            sample = serie_val[0]
            # Detectar campo de etiqueta (estado, tipo, rango, rol, semana, etc.)
            label_field = None
            for candidate in ("estado", "tipo", "rango", "rol", "semana", "categoria", "key"):
                if candidate in sample:
                    label_field = candidate
                    break
            if label_field is None:
                continue
            # Detectar primera metrica numerica
            num_fields = [k for k, v in sample.items()
                          if k != label_field and isinstance(v, (int, float))]
            if not num_fields:
                continue
            pie_field = next((f for f in num_fields if f in ("n", "cantidad", "count")), num_fields[0])
            lbls = [str(item.get(label_field, ""))[:20] for item in serie_val]
            vals = [float(item.get(pie_field, 0)) for item in serie_val]
            flowables.append(Paragraph(label, styles["h2"]))
            chart = _make_pie_chart(lbls, vals, title="", width=_CONTENT_W * 0.5, height=5 * cm)
            if chart:
                flowables.append(chart)
                flowables.append(Spacer(1, 3 * mm))
            # Tabla de estados
            header = [prettify_label(label_field)] + [prettify_label(f) for f in num_fields[:4]]
            t_rows = [[str(item.get(label_field, ""))] + [_fmt_value(item.get(f, 0)) for f in num_fields[:4]]
                      for item in serie_val[:_MAX_TABLE_ROWS]]
            col_w = [_CONTENT_W * 0.35] + [(_CONTENT_W * 0.65) / min(len(num_fields), 4)] * min(len(num_fields), 4)
            _render_simple_table(flowables, styles, header, t_rows, col_w)
            continue

        # ---- Serie de estadisticas anidadas (dict sin "periodos") ----
        if isinstance(serie_val, dict):
            flat_kpis = {k: v for k, v in serie_val.items() if isinstance(v, (int, float, str, bool, type(None)))}
            if flat_kpis:
                flowables.append(Paragraph(label, styles["h2"]))
                inner = _render_kpis(flat_kpis, styles)
                flowables.extend(inner[1:])  # omitir heading redundante

    return flowables


def _render_simple_table(flowables: list, styles: dict, header: list[str], rows: list[list], col_w: list[float]) -> None:
    """Helper: agrega una tabla con encabezado a flowables."""
    if not rows:
        return
    header_row = [Paragraph(h, ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=8,
                                               textColor=_C_WHITE)) for h in header]
    data = [header_row] + [[Paragraph(str(cell), ParagraphStyle("td", fontName="Helvetica",
                                                                  fontSize=7, textColor=_C_DARK))
                             for cell in row] for row in rows]
    t = Table(data, colWidths=col_w, repeatRows=1)
    t.setStyle(_table_style_header())
    flowables.append(t)
    flowables.append(Spacer(1, 3 * mm))


def _render_tables(tables: dict, styles: dict) -> list:
    """Renderiza el dict tables como tablas HTML (top-N filas)."""
    flowables = []
    if not tables:
        return flowables
    flowables.append(Paragraph("Detalle", styles["h2"]))
    for table_key, rows in tables.items():
        if not isinstance(rows, list) or not rows:
            continue
        # Permitir solo listas de dicts
        if not isinstance(rows[0], dict):
            continue
        flowables.append(Paragraph(prettify_label(table_key), styles["h3"]))
        # Encabezados: claves del primer registro (excluir claves de ID largas)
        all_keys = list(rows[0].keys())
        skip = {"id", "uuid", "Cotizacion_id", "Factura_id"}
        display_keys = [k for k in all_keys if k not in skip][:8]
        if not display_keys:
            continue
        header = [prettify_label(k) for k in display_keys]
        data_rows = []
        for r in rows[:_MAX_TABLE_ROWS]:
            data_rows.append([_fmt_value(r.get(k)) for k in display_keys])
        # Calcular anchos: primera col mas ancha si es texto
        n_cols = len(display_keys)
        if n_cols == 1:
            col_w = [_CONTENT_W]
        else:
            first_w = min(0.35, 10 / (n_cols * 10 + 10)) + 0.15  # heuristica
            rest_w = (_CONTENT_W * (1 - first_w)) / (n_cols - 1)
            col_w = [_CONTENT_W * first_w] + [rest_w] * (n_cols - 1)
        _render_simple_table(flowables, styles, header, data_rows, col_w)
        if len(rows) > _MAX_TABLE_ROWS:
            flowables.append(Paragraph(
                f"... ({len(rows) - _MAX_TABLE_ROWS} registros adicionales omitidos en PDF)",
                styles["bullet"],
            ))
    return flowables


def _render_signals(signals: list, styles: dict) -> list:
    """Renderiza la lista de senales como bullets."""
    if not signals:
        return []
    flowables = [Paragraph("Senales", styles["h2"])]
    for s in signals:
        if isinstance(s, dict):
            msg = s.get("mensaje") or s.get("message") or s.get("tipo") or str(s)
        else:
            msg = str(s)
        flowables.append(Paragraph(f"• {msg}", styles["bullet"]))
    return flowables


# ---------------------------------------------------------------------------
# Flowables de un modulo (helper compartido por build_module_pdf y combined)
# ---------------------------------------------------------------------------

def _module_flowables(label: str, payload: dict) -> list:
    """Construye la lista de flowables para un modulo a partir de su payload."""
    styles = _styles()
    flowables: list = []
    periodo = payload.get("periodo") or "Sin periodo"

    # Encabezado del modulo
    flowables.append(Paragraph(label, styles["title"]))
    flowables.append(Paragraph(f"Periodo: {periodo}", styles["subtitle"]))
    flowables.append(HRFlowable(width=_CONTENT_W, thickness=1.5, color=_C_PRIMARY))
    flowables.append(Spacer(1, 5 * mm))

    # KPIs
    kpis = payload.get("kpis")
    if kpis and isinstance(kpis, dict):
        flowables.extend(_render_kpis(kpis, styles))
        flowables.append(Spacer(1, 5 * mm))

    # Series (graficas + tablas de serie)
    series = payload.get("series")
    if series and isinstance(series, dict):
        flowables.extend(_render_series(series, styles))
        flowables.append(Spacer(1, 3 * mm))

    # Tablas de detalle
    tables = payload.get("tables")
    if tables and isinstance(tables, dict):
        flowables.extend(_render_tables(tables, styles))

    # Senales
    signals = payload.get("signals")
    if signals:
        flowables.extend(_render_signals(signals, styles))

    return flowables


# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------

def build_module_pdf(module_label: str, payload: dict) -> bytes:
    """Genera el PDF de un unico modulo. Devuelve bytes del PDF."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=_MARGIN, rightMargin=_MARGIN,
        topMargin=_MARGIN, bottomMargin=_MARGIN,
        title=f"Reporte {module_label}",
        author="RTB Dashboard",
    )
    flowables = _module_flowables(module_label, payload)
    doc.build(flowables)
    return buf.getvalue()


def build_combined_pdf(modules: list[tuple[str, dict]]) -> bytes:
    """Genera un PDF con todos los modulos (portada + indice + secciones).

    Args:
        modules: lista de tuplas (label, payload) en el orden de renderizado.

    Returns:
        bytes del PDF combinado.
    """
    if not modules:
        return b""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=_MARGIN, rightMargin=_MARGIN,
        topMargin=_MARGIN, bottomMargin=_MARGIN,
        title="Reporte Completo RTB",
        author="RTB Dashboard",
    )
    styles = _styles()
    flowables: list = []

    # --- Portada -----------------------------------------------------------
    # Fondo de color: tabla de 1 celda con fondo primario
    cover_data = [[Paragraph("Reporte Completo RTB", styles["cover_title"])],
                  [Paragraph(f"Generado el {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles["cover_sub"])],
                  [Paragraph(f"{len(modules)} modulos incluidos", styles["cover_sub"])]]
    cover_table = Table(cover_data, colWidths=[_CONTENT_W])
    cover_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), _C_PRIMARY),
        ("TOPPADDING",    (0, 0), (-1, -1), 18),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 18),
        ("LEFTPADDING",   (0, 0), (-1, -1), 20),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 20),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    flowables.append(Spacer(1, 5 * cm))
    flowables.append(cover_table)
    flowables.append(Spacer(1, 1 * cm))

    # --- Indice -----------------------------------------------------------
    flowables.append(Paragraph("Indice de modulos", styles["h2"]))
    for i, (lbl, _) in enumerate(modules, 1):
        flowables.append(Paragraph(f"{i}. {lbl}", styles["toc_item"]))
    flowables.append(PageBreak())

    # --- Secciones por modulo --------------------------------------------
    for i, (lbl, payload) in enumerate(modules):
        flowables.extend(_module_flowables(lbl, payload))
        if i < len(modules) - 1:
            flowables.append(PageBreak())

    doc.build(flowables)
    return buf.getvalue()


def build_reports_zip(modules: list[tuple[str, dict]]) -> bytes:
    """Genera un ZIP con _reporte_completo.pdf + un PDF por modulo.

    Args:
        modules: lista de tuplas (label, payload).

    Returns:
        bytes del ZIP.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        # PDF combinado
        combined = build_combined_pdf(modules)
        zf.writestr("_reporte_completo.pdf", combined)
        # PDF por modulo
        for label, payload in modules:
            slug = _slug(label)
            pdf_bytes = build_module_pdf(label, payload)
            zf.writestr(f"{slug}.pdf", pdf_bytes)
    return buf.getvalue()
