#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RTB Cierre Mensual — Módulo de análisis. Devuelve dict R con todas las métricas."""

import csv, json, os, re
from datetime import datetime, timezone
from collections import defaultdict

# ─── Utils ──────────────────────────────────────────────────────────────────
def f(v):
    try: return float(str(v).replace(",","").strip()) if str(v).strip() else 0.0
    except: return 0.0

def parse_date(s):
    if not s: return None
    s = str(s).strip()
    if s.startswith("{"):
        try: s = json.loads(s).get("start","") or ""
        except: return None
    s = s.replace("Z", "")
    s = re.sub(r'([+-]\d{2}:\d{2})$','',s)
    # Longitudes reales del string de fecha, NO len(fmt) que da tamaño del formato
    for fmt, n in [("%Y-%m-%dT%H:%M:%S.%f",26),("%Y-%m-%dT%H:%M:%S",19),
                   ("%Y-%m-%dT%H:%M",16),("%Y-%m-%d",10)]:
        try: return datetime.strptime(s[:n], fmt)
        except: pass
    return None

def week(dt):
    if not dt: return None
    d = dt.day
    return "S1" if d<=7 else "S2" if d<=14 else "S3" if d<=21 else "S4" if d<=28 else "S5"

def avg(lst): return sum(lst)/len(lst) if lst else 0.0
def med(lst):
    if not lst: return 0.0
    s=sorted(lst); n=len(s)
    return float(s[n//2]) if n%2 else (s[n//2-1]+s[n//2])/2

def days_diff(a, b):
    if a and b:
        try: return abs((b-a).days)
        except: pass
    return None

def parse_tp(s):
    s=(s or "").strip()
    if s.startswith("["):
        try: lst=json.loads(s); return lst[0] if lst else "Sin tipo"
        except: pass
    return s or "Sin tipo"

def histog(values, bins):
    """bins: list of (label, lo, hi) — hi=None means open-ended"""
    counts = {lbl:0 for lbl,_,_ in bins}
    for v in values:
        for lbl,lo,hi in bins:
            if hi is None:
                if v >= lo: counts[lbl]+=1; break
            elif lo <= v < hi: counts[lbl]+=1; break
    return counts

def read_csv(path):
    with open(path, newline='', encoding='utf-8-sig') as fh:
        return list(csv.DictReader(fh))

def prov_name(name):
    return re.sub(r'\s*[-–]\s*[FMA]\s*\d+.*$','',str(name)).strip()


def find_latest_csv(data_dir, prefix):
    data_dir = os.path.abspath(data_dir)
    matches = [
        os.path.join(data_dir, name)
        for name in os.listdir(data_dir)
        if name.startswith(prefix) and name.lower().endswith(".csv")
        and not (prefix == "Facturas_" and name.startswith("Facturas_Secundarias_"))
    ]
    if not matches:
        existing = sorted(name for name in os.listdir(data_dir) if name.lower().endswith(".csv"))
        existing_lines = "\n".join(f"  - {name}" for name in existing) or "  - Ninguno"
        raise FileNotFoundError(
            f"No se encontro {prefix}*.csv en la carpeta de datos.\n"
            f"Carpeta revisada: {data_dir}\n"
            "CSVs encontrados:\n"
            f"{existing_lines}"
        )
    return sorted(matches, key=lambda path: (os.path.getmtime(path), path))[-1]

def load_cotizaciones(data_dir="data"):
    return read_csv(find_latest_csv(data_dir, "Cotizaciones"))

def truthy(value):
    return str(value or "").strip().lower() in ("true", "1", "si", "sí", "yes")

def cot_has_pedido(row):
    return bool((row.get("Pedidos_Asociados.0") or "").strip() or (row.get("Pedidos_Asociados.1") or "").strip())

def compute_ventas(cot):
    SEMS = ["S1", "S2", "S3", "S4", "S5"]
    n_cot = len(cot)
    tot_cot = sum(f(r.get("Total")) for r in cot)
    sub_cot = sum(f(r.get("Subtotal_con_envio_venta")) for r in cot)
    aprobadas = [r for r in cot if (r.get("Estado_cotizacion") or "").strip() == "Aprobada"]
    n_apr = len(aprobadas)
    mon_apr = sum(f(r.get("Total")) for r in aprobadas)

    est_cot = defaultdict(lambda: {"n": 0, "m": 0.0})
    for r in cot:
        e = (r.get("Estado_cotizacion") or "Sin estado").strip() or "Sin estado"
        est_cot[e]["n"] += 1
        est_cot[e]["m"] += f(r.get("Total"))

    sem_cot = {s: {"n": 0, "m": 0.0, "na": 0, "ma": 0.0} for s in SEMS}
    for r in cot:
        dt = parse_date(r.get("Fecha_creacion"))
        s = week(dt)
        if not s:
            continue
        amount = f(r.get("Total"))
        sem_cot[s]["n"] += 1
        sem_cot[s]["m"] += amount
        if (r.get("Estado_cotizacion") or "").strip() == "Aprobada":
            sem_cot[s]["na"] += 1
            sem_cot[s]["ma"] += amount

    cli_cot = defaultdict(lambda: {"n": 0, "m": 0.0})
    cli_apr = defaultdict(lambda: {"n": 0, "m": 0.0})
    for r in cot:
        c = (r.get("Cliente") or "?").strip() or "?"
        amount = f(r.get("Total"))
        cli_cot[c]["n"] += 1
        cli_cot[c]["m"] += amount
        if (r.get("Estado_cotizacion") or "").strip() == "Aprobada":
            cli_apr[c]["n"] += 1
            cli_apr[c]["m"] += amount

    tip_cot = defaultdict(lambda: {"n": 0, "m": 0.0})
    for r in aprobadas:
        tp = (r.get("Tipo_pago.0") or r.get("Tipo_pago.1") or "Sin definir").strip() or "Sin definir"
        tip_cot[tp]["n"] += 1
        tip_cot[tp]["m"] += f(r.get("Total"))

    t_apr = []
    rangos_apr = {"Mismo día": 0, "1-3 días": 0, "4-7 días": 0, ">7 días": 0}
    hist_apr = defaultdict(int)
    sem_apr_times = defaultdict(list)
    n_apr_sin_fechas = 0
    for r in aprobadas:
        created = parse_date(r.get("Fecha_creacion"))
        approved = parse_date(r.get("Fecha_aprobacion"))
        delta = days_diff(created, approved)
        if delta is None:
            n_apr_sin_fechas += 1
            continue
        t_apr.append(float(delta))
        d = int(delta)
        bucket = str(d) if d <= 7 else "8+"
        hist_apr[bucket] += 1
        s = week(created)
        if s:
            sem_apr_times[s].append(float(delta))
        if delta == 0:
            rangos_apr["Mismo día"] += 1
        elif delta <= 3:
            rangos_apr["1-3 días"] += 1
        elif delta <= 7:
            rangos_apr["4-7 días"] += 1
        else:
            rangos_apr[">7 días"] += 1
    sem_apr = {s: {"avg": avg(sem_apr_times[s]), "med": med(sem_apr_times[s]), "n": len(sem_apr_times[s])} for s in ["S1", "S2", "S3", "S4", "S5"]}

    rol_cot = defaultdict(lambda: {"n": 0, "m": 0.0, "na": 0, "ma": 0.0})
    for r in cot:
        rol = (r.get("Localidad") or "Sin rol").strip() or "Sin rol"
        amount = f(r.get("Total"))
        rol_cot[rol]["n"] += 1
        rol_cot[rol]["m"] += amount
        if (r.get("Estado_cotizacion") or "").strip() == "Aprobada":
            rol_cot[rol]["na"] += 1
            rol_cot[rol]["ma"] += amount

    ariba_rows = [r for r in cot if truthy(r.get("Ariba"))]
    ariba_apr_rows = [r for r in ariba_rows if (r.get("Estado_cotizacion") or "").strip() == "Aprobada"]
    n_ariba = len(ariba_rows)
    m_ariba_cot = sum(f(r.get("Total")) for r in ariba_rows)
    n_ariba_apr = len(ariba_apr_rows)
    m_ariba_apr = sum(f(r.get("Total")) for r in ariba_apr_rows)
    ariba_conv_q = n_ariba_apr / n_ariba if n_ariba else 0
    ariba_conv_m = m_ariba_apr / m_ariba_cot if m_ariba_cot else 0
    ticket_ariba_cot = m_ariba_cot / n_ariba if n_ariba else 0
    return {
        "n_cot": n_cot, "tot_cot": tot_cot, "sub_cot": sub_cot,
        "n_apr": n_apr, "mon_apr": mon_apr,
        "conv_q": n_apr / n_cot if n_cot else 0,
        "conv_m": mon_apr / tot_cot if tot_cot else 0,
        "ticket_cot": tot_cot / n_cot if n_cot else 0,
        "ticket_apr": mon_apr / n_apr if n_apr else 0,
        "est_cot": dict(est_cot),
        "sem_cot": sem_cot,
        "top_cli_cot": sorted(
            [(k, {"n": v["n"], "m": v["m"], "na": cli_apr[k]["n"], "ma": cli_apr[k]["m"]}) for k, v in cli_cot.items()],
            key=lambda x: -x[1]["m"],
        )[:10],
        "top_cli_apr": sorted(
            [(k, {"n": v["n"], "m": v["m"], "n_cot": cli_cot[k]["n"], "m_cot": cli_cot[k]["m"]}) for k, v in cli_apr.items()],
            key=lambda x: -x[1]["m"],
        )[:10],
        "tip_cot": dict(tip_cot),
        "rangos_apr": rangos_apr,
        "t_apr_avg": avg(t_apr), "t_apr_med": med(t_apr), "t_apr_max": max(t_apr) if t_apr else 0,
        "n_apr_sin_fechas": n_apr_sin_fechas, "hist_apr": dict(hist_apr), "sem_apr": sem_apr,
        "rol_cot": dict(rol_cot),
        "n_ariba": n_ariba, "m_ariba": m_ariba_cot,
        "ticket_ariba_cot": ticket_ariba_cot,
        "n_ariba_apr": n_ariba_apr, "m_ariba_apr": m_ariba_apr,
        "ariba_apr_conv_q": n_ariba_apr / n_cot if n_cot else 0,
        "ariba_apr_conv_m": m_ariba_apr / tot_cot if tot_cot else 0,
        "ariba_conv_q": ariba_conv_q, "ariba_conv_m": ariba_conv_m,
    }

def signal_record(row):
    return {
        "cotizacion_id": row.get("Cotizacion_id", ""),
        "cotizacion": row.get("Cotizacion_nombre", ""),
        "cliente": row.get("Cliente", ""),
        "estado": row.get("Estado_cotizacion", ""),
        "total": f(row.get("Total")),
    }

def make_signal(tipo, severidad, titulo, descripcion, periodo, metricas=None, registros=None, accion=""):
    return {
        "id": f"{tipo}:{periodo}".replace(" ", "_"),
        "tipo": tipo,
        "severidad": severidad,
        "titulo": titulo,
        "descripcion": descripcion,
        "modulo": "ventas",
        "periodo": periodo,
        "metricas": metricas or {},
        "registros": registros or [],
        "accion_sugerida": accion,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

def build_ventas_signals(cot, m1, period_label="Periodo actual"):
    signals = []
    sin_tipo = [r for r in cot if not (r.get("Tipo_pago.0") or r.get("Tipo_pago.1") or "").strip()]
    if m1["n_cot"] and len(sin_tipo) / m1["n_cot"] > 0.5:
        signals.append(make_signal(
            "tipo_pago_sin_definir", "riesgo", "Tipo de pago sin definir",
            "Mas de la mitad de las cotizaciones no tienen tipo de pago capturado.",
            period_label,
            {"cantidad": len(sin_tipo), "porcentaje": len(sin_tipo) / m1["n_cot"]},
            [signal_record(r) for r in sin_tipo[:10]],
            "Completar tipo de pago antes de convertir cotizaciones a pedido.",
        ))

    aprobadas_sin_pedido = [r for r in cot if (r.get("Estado_cotizacion") or "").strip() == "Aprobada" and not cot_has_pedido(r)]
    if aprobadas_sin_pedido:
        signals.append(make_signal(
            "aprobada_sin_pedido", "atencion", "Aprobadas sin pedido asociado",
            "Hay cotizaciones aprobadas sin trazabilidad a pedido.",
            period_label,
            {"cantidad": len(aprobadas_sin_pedido), "monto": sum(f(r.get("Total")) for r in aprobadas_sin_pedido)},
            [signal_record(r) for r in aprobadas_sin_pedido[:10]],
            "Revisar si falta crear o asociar el pedido en Notion.",
        ))

    ariba_aprobada = [r for r in cot if truthy(r.get("Ariba")) and (r.get("Estado_cotizacion") or "").strip() == "Aprobada"]
    if ariba_aprobada:
        signals.append(make_signal(
            "ariba_aprobada", "atencion", "Cotizaciones Ariba aprobadas",
            "Las cotizaciones Ariba aprobadas requieren seguimiento operativo y documental.",
            period_label,
            {"cantidad": len(ariba_aprobada), "monto": sum(f(r.get("Total")) for r in ariba_aprobada)},
            [signal_record(r) for r in ariba_aprobada[:10]],
            "Confirmar PO, pedido asociado y siguiente paso de cobranza.",
        ))

    exp_altas = [r for r in cot if (r.get("Estado_cotizacion") or "").strip() == "Expirada" and f(r.get("Total")) >= m1["ticket_cot"]]
    if exp_altas:
        signals.append(make_signal(
            "expirada_monto_alto", "riesgo", "Cotizaciones altas expiradas",
            "Hay cotizaciones expiradas por arriba del ticket promedio.",
            period_label,
            {"cantidad": len(exp_altas), "monto": sum(f(r.get("Total")) for r in exp_altas), "ticket_promedio": m1["ticket_cot"]},
            [signal_record(r) for r in exp_altas[:10]],
            "Priorizar seguimiento comercial con clientes de alto monto.",
        ))

    avg_week_amount = sum(d["m"] for d in m1["sem_cot"].values()) / 5 if m1["sem_cot"] else 0
    low_weeks = []
    for name, data in m1["sem_cot"].items():
        conv = data["ma"] / data["m"] if data["m"] else 0
        if data["m"] >= avg_week_amount and conv < m1["conv_m"]:
            low_weeks.append({"semana": name, "monto": data["m"], "conversion_monto": conv})
    if low_weeks:
        signals.append(make_signal(
            "semana_baja_conversion", "atencion", "Semana con baja conversion",
            "Una semana con monto relevante convirtio por debajo del promedio del periodo.",
            period_label,
            {"semanas": low_weeks, "conversion_promedio": m1["conv_m"]},
            [],
            "Revisar cotizaciones abiertas o expiradas de la semana marcada.",
        ))
    return signals


def linear_trend(values):
    n = len(values)
    if n == 0:
        return {"m": 0.0, "b": 0.0, "start": 0.0, "end": 0.0}
    if n == 1:
        v = float(values[0])
        return {"m": 0.0, "b": v, "start": v, "end": v}
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(values) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values))
    den = sum((x - mean_x) ** 2 for x in xs)
    m = num / den if den != 0 else 0.0
    b = mean_y - m * mean_x
    return {"m": m, "b": b, "start": m * 0 + b, "end": m * (n - 1) + b}


MONTH_LABELS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
TEMPORAL_WEEKS = ["S1", "S2", "S3", "S4", "S5"]

def month_key(dt):
    return f"{dt.year:04d}-{dt.month:02d}" if dt else None

def month_label(key):
    year, month = (int(part) for part in key.split("-"))
    return f"{MONTH_LABELS[month - 1]} {year}"

def calendar_months(start, end):
    keys = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        keys.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return keys

def temporal_axis(fecha_desde=None, fecha_hasta=None, dates=None):
    parsed_dates = [parse_date(value) for value in (dates or [])]
    parsed_dates = [dt for dt in parsed_dates if dt]
    start = parse_date(fecha_desde) or (min(parsed_dates) if parsed_dates else None)
    end = parse_date(fecha_hasta) or (max(parsed_dates) if parsed_dates else None)
    monthly = bool(start and end and (start.year, start.month) != (end.year, end.month))
    keys = calendar_months(start, end) if monthly else list(TEMPORAL_WEEKS)
    return {
        "granularidad": "mes" if monthly else "semana",
        "keys": keys,
        "labels": [month_label(key) for key in keys] if monthly else list(keys),
        "table_heading": "Mes" if monthly else "Semana",
        "behavior_title": "Comportamiento mensual" if monthly else "Comportamiento semanal",
        "chart_suffix": "por mes" if monthly else "por semana",
        "hint": "Agrupado por mes calendario del periodo seleccionado" if monthly else "S1=1-7 · S2=8-14 · S3=15-21 · S4=22-28 · S5=29-fin de mes",
    }

def temporal_key(dt, granularidad):
    return month_key(dt) if granularidad == "mes" else week(dt)

def aggregate_temporal(rows, date_getter, metric_getters, fecha_desde=None, fecha_hasta=None, axis=None):
    axis = axis or temporal_axis(fecha_desde, fecha_hasta, dates=[date_getter(row) for row in rows])
    start_d = parse_date(fecha_desde).date() if parse_date(fecha_desde) else None
    end_d = parse_date(fecha_hasta).date() if parse_date(fecha_hasta) else None
    buckets = {key: {metric: 0.0 for metric in metric_getters} for key in axis["keys"]}
    for row in rows:
        dt = parse_date(date_getter(row))
        if dt is None:
            continue
        d = dt.date()
        if (start_d and d < start_d) or (end_d and d > end_d):
            continue
        key = temporal_key(dt, axis["granularidad"])
        if key not in buckets:
            continue
        for metric, getter in metric_getters.items():
            buckets[key][metric] += getter(row)
    return {
        **axis,
        "periodos": [
            {"key": key, "etiqueta": label, **buckets[key]}
            for key, label in zip(axis["keys"], axis["labels"])
        ],
    }

def build_temporal_series(cot, fecha_desde=None, fecha_hasta=None):
    aggregated = aggregate_temporal(
        cot,
        date_getter=lambda row: row.get("Fecha_creacion"),
        metric_getters={
            "cotizaciones": lambda row: 1,
            "cotizado": lambda row: f(row.get("Total")),
            "aprobadas": lambda row: 1 if (row.get("Estado_cotizacion") or "").strip() == "Aprobada" else 0,
            "aprobado": lambda row: f(row.get("Total")) if (row.get("Estado_cotizacion") or "").strip() == "Aprobada" else 0.0,
        },
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )
    approval_times = defaultdict(list)
    for row in cot:
        if (row.get("Estado_cotizacion") or "").strip() != "Aprobada":
            continue
        created = parse_date(row.get("Fecha_creacion"))
        key = temporal_key(created, aggregated["granularidad"])
        delta = days_diff(created, parse_date(row.get("Fecha_aprobacion")))
        if key in aggregated["keys"] and delta is not None:
            approval_times[key].append(float(delta))
    approval_periods = [
        {"etiqueta": label, "avg": avg(approval_times[key]), "med": med(approval_times[key]), "n": len(approval_times[key])}
        for key, label in zip(aggregated["keys"], aggregated["labels"])
    ]
    periods = aggregated["periodos"]
    return {
        **aggregated,
        "tiempos_aprobacion": approval_periods,
        "tendencias": {
            "cotizado": linear_trend([data["cotizado"] for data in periods]),
            "aprobado": linear_trend([data["aprobado"] for data in periods]),
            "conv_qty": linear_trend([data["aprobadas"] / data["cotizaciones"] if data["cotizaciones"] else 0.0 for data in periods]),
            "cotizaciones": linear_trend([data["cotizaciones"] for data in periods]),
            "aprobadas": linear_trend([data["aprobadas"] for data in periods]),
        },
    }

def factura_record(row, tipo):
    return {
        "factura_id": row.get("Factura_id", ""),
        "factura": row.get("#_Factura", ""),
        "cotizacion_id": row.get("Factura_cotizacion", ""),
        "cliente": row.get("Factura_Cliente", ""),
        "estado": (row.get("Estado_Factura") or "Sin estado").strip() or "Sin estado",
        "tipo": tipo,
    }

def make_facturacion_signal(tipo, severidad, titulo, descripcion, periodo, metricas=None, registros=None, accion=""):
    return {
        "id": f"{tipo}:{periodo}".replace(" ", "_"),
        "tipo": tipo,
        "severidad": severidad,
        "titulo": titulo,
        "descripcion": descripcion,
        "modulo": "facturacion",
        "periodo": periodo,
        "metricas": metricas or {},
        "registros": registros or [],
        "accion_sugerida": accion,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

def build_facturacion_dashboard(cot, principales, secundarias, period_label="Periodo actual", fecha_desde=None, fecha_hasta=None):
    _s = parse_date(fecha_desde)
    _e = parse_date(fecha_hasta)
    start_d = _s.date() if _s else None
    end_d = _e.date() if _e else None

    cot_aprobacion = {
        (r.get("Cotizacion_id") or "").strip(): parse_date(r.get("Fecha_aprobacion"))
        for r in cot
        if (r.get("Cotizacion_id") or "").strip()
    }

    def normalized(row, tipo):
        date_key = "Fecha_Facturacion" if tipo == "principal" else "Fecha_Facturacion_Secundaria"
        validation_key = "Fecha_Validacion" if tipo == "principal" else "Fecha_Validacion_Secundaria"
        association_key = "Fecha_Asociacion" if tipo == "principal" else "Fecha_Asociacion_Secundaria"
        partial_key = "Monto_primer_factura" if tipo == "principal" else "Monto_segunda_factura"
        date = parse_date(row.get(date_key))
        raw_partial = row.get(partial_key)
        partial = round(f(raw_partial), 2) if (raw_partial is not None and str(raw_partial).strip() != "") else None
        total_amount = round(f(row.get("Total")), 2)
        cid = (row.get("Factura_cotizacion") or "").strip()
        estado_aprob = (row.get("Factura_Estado_Aprobacion") or "").strip().lower()
        raw_folio = (row.get("#_Factura") or "").strip()
        m_folio = re.match(r"^(C\d+)", raw_folio)
        folio = m_folio.group(1) if m_folio else raw_folio
        return {
            "row": row,
            "tipo": tipo,
            "fecha": date,
            "fecha_validacion": parse_date(row.get(validation_key)),
            "fecha_asociacion": parse_date(row.get(association_key)),
            "fecha_aprobacion": cot_aprobacion.get(cid),
            "partial": partial,
            "total_amount": total_amount,
            "monto": partial if partial is not None else total_amount,
            "cancelada": estado_aprob in ("cancelada", "cancelado"),
            "aprobada": estado_aprob == "aprobada",
            "folio": folio,
            "folio_dirty": bool(m_folio) and folio != raw_folio,
            "cotizacion_id": cid,
            "factura_id": (row.get("Factura_id") or "").strip(),
        }

    rows = [normalized(row, "principal") for row in principales]
    rows.extend(normalized(row, "secundaria") for row in secundarias)

    def in_period(item):
        if not item["fecha"]:
            return False
        d = item["fecha"].date()
        return (not start_d or d >= start_d) and (not end_d or d <= end_d)

    canceladas = [item for item in rows if item["cancelada"] and in_period(item)]
    incompletas = [
        item for item in rows
        if item["aprobada"] and not item["cancelada"] and (not item["folio"] or not item["fecha"])
    ]
    candidates = [
        item for item in rows
        if item["aprobada"] and not item["cancelada"] and item["folio"] and in_period(item)
    ]
    vigentes = []
    duplicate_rows = []
    seen = set()
    for item in candidates:
        identity = item["factura_id"] or item["folio"] or item["cotizacion_id"]
        if identity in seen:
            duplicate_rows.append(item)
            continue
        seen.add(identity)
        vigentes.append(item)
    # Suprimir falsos positivos: mismo factura_id en principal y secundaria es el mismo
    # registro de Notion exportado en ambos CSVs (anomalía de export, no error de captura).
    # Solo reportar duplicados cuya identidad no sea el factura_id (colisión de folio/cot).
    duplicate_rows = [item for item in duplicate_rows if not item["factura_id"]]

    cot_aprobadas = [
        row for row in cot
        if (row.get("Estado_cotizacion") or "").strip() == "Aprobada"
    ]
    cotizaciones_facturadas = {item["cotizacion_id"] for item in vigentes if item["cotizacion_id"]}
    rezago = [
        row for row in cot_aprobadas
        if (row.get("Cotizacion_id") or "").strip() not in cotizaciones_facturadas
    ]

    estados = defaultdict(lambda: {"n": 0, "m": 0.0})
    for item in vigentes:
        estado = (item["row"].get("Estado_Factura") or "Sin estado").strip() or "Sin estado"
        estados[estado]["n"] += 1
        estados[estado]["m"] += item["monto"]

    temporal = aggregate_temporal(
        vigentes,
        date_getter=lambda item: item["fecha"],
        metric_getters={
            "cantidad": lambda item: 1,
            "monto": lambda item: item["monto"],
        },
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )
    periods = temporal["periodos"]
    temporal["tendencias"] = {
        "cantidad": linear_trend([row["cantidad"] for row in periods]),
        "monto": linear_trend([row["monto"] for row in periods]),
    }

    def _safe_diff(a, b, max_days):
        d = days_diff(a, b)
        return d if d is not None and d <= max_days else None

    def _cycle_stats(vals):
        valid = sorted(v for v in vals if v is not None)
        n = len(valid)
        if not n:
            return {"avg": None, "med": None, "max": None, "n": 0}
        avg_v = round(sum(valid) / n, 1)
        med_v = round(valid[n // 2] if n % 2 else (valid[n // 2 - 1] + valid[n // 2]) / 2, 1)
        return {"avg": avg_v, "med": med_v, "max": max(valid), "n": n}

    for item in vigentes:
        item["_pf"] = _safe_diff(item["fecha_aprobacion"], item["fecha"], 180)
        item["_fv"] = _safe_diff(item["fecha"], item["fecha_validacion"], 90)
        item["_va"] = _safe_diff(item["fecha_validacion"], item["fecha_asociacion"], 180)
        item["_tot"] = _safe_diff(item["fecha_aprobacion"], item["fecha_asociacion"], 365)

    ciclo_temp = aggregate_temporal(
        vigentes,
        date_getter=lambda item: item["fecha"],
        metric_getters={
            "sum_tot": lambda item: item["_tot"] or 0,
            "cnt_tot": lambda item: 1 if item["_tot"] is not None else 0,
        },
        axis=temporal,
    )
    for p in ciclo_temp["periodos"]:
        p["avg_tot"] = round(p["sum_tot"] / p["cnt_tot"], 1) if p["cnt_tot"] else None

    ciclo = {
        "etapas": [
            {"etapa": "Pedido → Facturado", **_cycle_stats([item["_pf"] for item in vigentes])},
            {"etapa": "Facturado → Validado", **_cycle_stats([item["_fv"] for item in vigentes])},
            {"etapa": "Validado → Asociado", **_cycle_stats([item["_va"] for item in vigentes])},
            {"etapa": "Ciclo total", **_cycle_stats([item["_tot"] for item in vigentes])},
        ],
        "temporal": [
            {"etiqueta": p["etiqueta"], "avg_tot": p["avg_tot"]}
            for p in ciclo_temp["periodos"]
        ],
    }
    for item in vigentes:
        del item["_pf"], item["_fv"], item["_va"], item["_tot"]

    signals = []
    if incompletas:
        signals.append(make_facturacion_signal(
            "factura_captura_incompleta", "riesgo", "Facturas con captura incompleta",
            "Hay facturas aprobadas sin folio o sin fecha de facturacion.",
            period_label,
            {"cantidad": len(incompletas)},
            [factura_record(item["row"], item["tipo"]) for item in incompletas[:10]],
            "Completar folio y fecha de facturacion en Notion.",
        ))
    if duplicate_rows:
        signals.append(make_facturacion_signal(
            "factura_duplicada", "atencion", "Facturas duplicadas",
            "Hay registros repetidos entre facturas principales y secundarias.",
            period_label,
            {"cantidad": len(duplicate_rows)},
            [factura_record(item["row"], item["tipo"]) for item in duplicate_rows[:10]],
            "Revisar la asociacion para evitar doble conteo.",
        ))
    if rezago:
        signals.append(make_facturacion_signal(
            "rezago_facturacion_estimado", "riesgo", "Rezago estimado de facturacion",
            "Hay cotizaciones aprobadas sin una factura vigente asociada.",
            period_label,
            {"cantidad": len(rezago), "monto": sum(f(row.get("Total")) for row in rezago)},
            [signal_record(row) for row in rezago[:10]],
            "Revisar cotizaciones aprobadas pendientes de facturar.",
        ))

    folios_sucios = [item for item in vigentes if item["folio_dirty"]]
    if folios_sucios:
        signals.append(make_facturacion_signal(
            "factura_folio_captura_sucia", "atencion",
            "Folios con notas embebidas en #_Factura",
            "El campo #_Factura contiene texto extra; se extrajo el codigo Cxxxx para conteo.",
            period_label,
            {"cantidad": len(folios_sucios)},
            [factura_record(item["row"], item["tipo"]) for item in folios_sucios[:10]],
            "Limpiar el campo en Notion dejando solo el folio.",
        ))

    cot_con_secundaria = {
        (s.get("Factura_cotizacion") or "").strip()
        for s in secundarias
        if (s.get("Factura_cotizacion") or "").strip()
    }
    pendientes_segunda = [
        item for item in vigentes
        if item["tipo"] == "principal" and item["partial"] is not None
        and item["cotizacion_id"] and item["cotizacion_id"] not in cot_con_secundaria
    ]
    if pendientes_segunda:
        monto_pendiente_total = round(sum(item["total_amount"] - item["partial"] for item in pendientes_segunda), 2)
        signals.append(make_facturacion_signal(
            "segunda_factura_pendiente", "atencion",
            "Segunda factura pendiente de emision",
            "Cotizaciones con primera factura emitida y segunda aun sin emitirse.",
            period_label,
            {"cantidad": len(pendientes_segunda), "monto_pendiente": monto_pendiente_total},
            [factura_record(item["row"], item["tipo"]) for item in pendientes_segunda[:10]],
            "Verificar emision de la segunda factura para cerrar la cotizacion.",
        ))

    def _sec_monto(s):
        raw = s.get("Monto_segunda_factura")
        if raw is not None and str(raw).strip():
            return round(f(raw), 2)
        return round(f(s.get("Total")), 2)

    sec_by_cot = defaultdict(list)
    for s in secundarias:
        cid = (s.get("Factura_cotizacion") or "").strip()
        if cid:
            sec_by_cot[cid].append(s)
    desbalanceadas = []
    for item in vigentes:
        if item["tipo"] != "principal" or item["partial"] is None:
            continue
        secs = sec_by_cot.get(item["cotizacion_id"], [])
        if not secs:
            continue
        suma = round(item["partial"] + sum(_sec_monto(s) for s in secs), 2)
        if abs(suma - item["total_amount"]) > 0.05:
            desbalanceadas.append((item, suma))
    if desbalanceadas:
        signals.append(make_facturacion_signal(
            "factura_partidas_desbalanceadas", "riesgo",
            "Primer + segunda factura no cuadran con Total",
            "Diferencia mayor a $0.05 entre la suma de partidas y el Total de la cotizacion.",
            period_label,
            {"cantidad": len(desbalanceadas)},
            [factura_record(item["row"], item["tipo"]) for item, _ in desbalanceadas[:10]],
            "Revisar captura de Monto_primer_factura / Monto_segunda_factura en Notion.",
        ))

    monto_vigente = round(sum(item["monto"] for item in vigentes), 2)
    return {
        "periodo": period_label,
        "kpis": {
            "facturas_vigentes": len(vigentes),
            "monto_facturado_vigente": monto_vigente,
            "ticket_promedio_facturado": monto_vigente / len(vigentes) if vigentes else 0.0,
            "facturas_principales": sum(1 for item in vigentes if item["tipo"] == "principal"),
            "facturas_secundarias": sum(1 for item in vigentes if item["tipo"] == "secundaria"),
            "facturas_canceladas": len(canceladas),
            "monto_cancelado": round(sum(item["monto"] for item in canceladas), 2),
            "rezago_estimado_cantidad": len(rezago),
            "rezago_estimado_monto": round(sum(f(row.get("Total")) for row in rezago), 2),
            "cobertura_validacion_pct": sum(1 for item in vigentes if item["fecha_validacion"]) / len(vigentes) if vigentes else 0.0,
            "cobertura_asociacion_pct": sum(1 for item in vigentes if item["fecha_asociacion"]) / len(vigentes) if vigentes else 0.0,
            "senales": len(signals),
        },
        "series": {
            "temporal": temporal,
            "estados": [{"estado": key, **value} for key, value in estados.items()],
        },
        "ciclo": ciclo,
        "tables": {
            "facturas": [
                {
                    **factura_record(item["row"], item["tipo"]),
                    "factura": item["folio"],
                    "fecha": item["fecha"].strftime("%Y-%m-%d"),
                    "monto": item["monto"],
                    "validada": bool(item["fecha_validacion"]),
                    "asociada": bool(item["fecha_asociacion"]),
                }
                for item in vigentes
            ],
        },
        "signals": signals,
    }

def build_ventas_dashboard(cot, period_label="Periodo actual", fecha_desde=None, fecha_hasta=None):
    m1 = compute_ventas(cot)
    temporal = build_temporal_series(cot, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta)
    signals = build_ventas_signals(cot, m1, period_label)
    return {
        "periodo": period_label,
        "kpis": {
            "cotizaciones": m1["n_cot"],
            "aprobadas": m1["n_apr"],
            "total_cotizado": m1["tot_cot"],
            "monto_aprobado": m1["mon_apr"],
            "conversion_qty": m1["conv_q"],
            "conversion_monto": m1["conv_m"],
            "ticket_promedio": m1["ticket_cot"],
            "ariba": m1["n_ariba"],
            "senales": len(signals),
            "total_cotizaciones": m1["n_cot"],
            "total_cotizado_iva": m1["tot_cot"],
            "cotizaciones_aprobadas": m1["n_apr"],
            "monto_aprobado_iva": m1["mon_apr"],
            "aprobacion_cantidad_pct": m1["conv_q"],
            "aprobacion_monto_pct": m1["conv_m"],
            "diferencia_aprobacion_pct": m1["conv_m"] - m1["conv_q"],
            "ticket_promedio_cotizado": m1["ticket_cot"],
            "ticket_promedio_aprobado": m1["ticket_apr"],
            "ariba_aprobadas": m1["n_ariba_apr"],
            "monto_ariba_aprobado": m1["m_ariba_apr"],
            "ariba_aprobadas_pct_cantidad": m1["ariba_apr_conv_q"],
            "ariba_aprobadas_pct_monto": m1["ariba_apr_conv_m"],
            "diferencia_ariba_aprobada_pct": m1["ariba_apr_conv_m"] - m1["ariba_apr_conv_q"],
            "ariba_cotizadas": m1["n_ariba"],
            "monto_ariba_cotizado": m1["m_ariba"],
            "ticket_ariba_cotizado": m1["ticket_ariba_cot"],
            "ariba_conv_q": m1["ariba_conv_q"],
            "ariba_conv_m": m1["ariba_conv_m"],
            "diferencia_ariba_conv": m1["ariba_conv_m"] - m1["ariba_conv_q"],
        },
        "m1": m1,
        "series": {
            "temporal": temporal,
            "semanas": [{"semana": k, "cotizado": v["m"], "aprobado": v["ma"], "cotizaciones": v["n"], "aprobadas": v["na"]} for k, v in m1["sem_cot"].items()],
            "estados": [{"estado": k, **v} for k, v in m1["est_cot"].items()],
            "roles": [{"rol": k, **v} for k, v in m1["rol_cot"].items()],
            "tiempos_aprobacion": {
                "stats": {
                    "promedio": round(m1["t_apr_avg"], 1),
                    "mediana": round(m1["t_apr_med"], 1),
                    "maximo": int(m1["t_apr_max"]),
                    "n_con_datos": sum(m1["hist_apr"].values()),
                    "n_sin_fechas": m1["n_apr_sin_fechas"],
                    "n_no_aprobadas": m1["n_cot"] - m1["n_apr"],
                },
                "rangos": [
                    {"rango": k, "n": v, "pct": v / sum(m1["rangos_apr"].values()) if sum(m1["rangos_apr"].values()) else 0}
                    for k, v in m1["rangos_apr"].items()
                ],
                "semanal": [{"semana": s, **m1["sem_apr"][s]} for s in ["S1", "S2", "S3", "S4", "S5"]],
                "periodos": temporal["tiempos_aprobacion"],
                "granularidad": temporal["granularidad"],
                "semanal_tendencia": linear_trend([p["avg"] for p in temporal["tiempos_aprobacion"]]),
                "histograma": sorted(
                    [{"dias": k, "n": v} for k, v in m1["hist_apr"].items()],
                    key=lambda x: 99 if x["dias"] == "8+" else int(x["dias"]),
                ),
            },
            "tendencias": {
                "cotizado": linear_trend([m1["sem_cot"][s]["m"] for s in ["S1", "S2", "S3", "S4", "S5"]]),
                "aprobado": linear_trend([m1["sem_cot"][s]["ma"] for s in ["S1", "S2", "S3", "S4", "S5"]]),
                "conv_qty": linear_trend([
                    m1["sem_cot"][s]["na"] / m1["sem_cot"][s]["n"] if m1["sem_cot"][s]["n"] else 0.0
                    for s in ["S1", "S2", "S3", "S4", "S5"]
                ]),
                "cotizaciones": linear_trend([m1["sem_cot"][s]["n"] for s in ["S1", "S2", "S3", "S4", "S5"]]),
                "aprobadas": linear_trend([m1["sem_cot"][s]["na"] for s in ["S1", "S2", "S3", "S4", "S5"]]),
            },
        },
        "tables": {
            "top_clientes_cotizan": [{"cliente": k, **v} for k, v in m1["top_cli_cot"]],
            "top_clientes_aprueban": [{"cliente": k, **v} for k, v in m1["top_cli_apr"]],
            "tipos_pago": [{"tipo": k, **v} for k, v in m1["tip_cot"].items()],
            "cotizaciones": [
                {
                    "id": r.get("Cotizacion_id", ""),
                    "cotizacion": r.get("Cotizacion_nombre", ""),
                    "cliente": r.get("Cliente", ""),
                    "estado": (r.get("Estado_cotizacion") or "Sin estado").strip() or "Sin estado",
                    "localidad": (r.get("Localidad") or "Sin rol").strip() or "Sin rol",
                    "tipo_pago": (r.get("Tipo_pago.0") or r.get("Tipo_pago.1") or "Sin definir").strip() or "Sin definir",
                    "fecha": (r.get("Fecha_creacion") or "")[:10],
                    "total": f(r.get("Total")),
                    "subtotal": f(r.get("Subtotal_con_envio_venta")),
                    "ariba": truthy(r.get("Ariba")),
                    "pedido_asociado": cot_has_pedido(r),
                }
                for r in sorted(cot, key=lambda row: f(row.get("Total")), reverse=True)
            ],
        },
        "signals": signals,
    }

def _norm_fc_row(row):
    """Normaliza una fila de Facturas_Compras a estructura unificada.
    Soporta el formato antiguo (property_*) y el nuevo (Factura_compra_*)."""
    if "Factura_compra_subtotal" in row:
        sub = f(row.get("Factura_compra_subtotal", 0))
        iva = f(row.get("Fcatura_compra_iva", 0))       # typo en export n8n
        env = f(row.get("Factura_compra_envio", 0))
        tot = f(row.get("Factura_compra_total", 0)) or sub + iva + env
        return {
            "nombre": row.get("Factura_compra_nombre", ""),
            "sub": sub, "iva": iva, "env": env, "tot": tot,
            "fecha": row.get("Facatura_compra_fecha_factura", ""),  # typo en export n8n
            "tipo_pago": parse_tp(row.get("Factura_compra_tipo", "")),
            "cfdi": (row.get("Factura_compra_uso_cfdi", "") or "Sin CFDI").strip() or "Sin CFDI",
            "status_pago": (row.get("Factura_compra_estatus_factura", "") or "Sin status").strip() or "Sin status",
            "fecha_pago": "",
        }
    sub = f(row.get("property_subtotal_f", 0))
    iva = f(row.get("property_iva_16", 0))
    env = f(row.get("property_costo_de_envio", 0))
    return {
        "nombre": row.get("name", ""),
        "sub": sub, "iva": iva, "env": env, "tot": sub + iva + env,
        "fecha": row.get("property_fecha_de_factura.start", ""),
        "tipo_pago": parse_tp(row.get("property_tipo_de_pago.0", "")),
        "cfdi": (row.get("property_uso_cfdi", "") or "Sin CFDI").strip() or "Sin CFDI",
        "status_pago": (row.get("property_status_de_pago", "") or "Sin status").strip() or "Sin status",
        "fecha_pago": row.get("property_fecha_de_pago", ""),
    }


def build_compras_dashboard(fc, fcp, period_label="Periodo actual", fecha_desde=None, fecha_hasta=None):
    _s = parse_date(fecha_desde)
    _e = parse_date(fecha_hasta)
    start_d = _s.date() if _s else None
    end_d = _e.date() if _e else None

    def in_period_d(fecha_str):
        dt = parse_date(fecha_str)
        if not dt: return False
        d = dt.date()
        return (not start_d or d >= start_d) and (not end_d or d <= end_d)

    fc_norm  = [_norm_fc_row(r) for r in fc  if in_period_d(_norm_fc_row(r)["fecha"])]
    fcp_norm = [_norm_fc_row(r) for r in fcp if in_period_d(_norm_fc_row(r)["fecha"])]

    # Totales facturas compras
    n_fc   = len(fc_norm)
    sub_fc = round(sum(r["sub"] for r in fc_norm), 2)
    iva_fc = round(sum(r["iva"] for r in fc_norm), 2)
    tot_fc = round(sum(r["tot"] for r in fc_norm), 2)

    # Totales pagadas
    n_fcp   = len(fcp_norm)
    sub_fcp = round(sum(r["sub"] for r in fcp_norm), 2)
    tot_fcp = round(sum(r["tot"] for r in fcp_norm), 2)

    # Status de pago
    sp_fc = defaultdict(lambda: {"n": 0, "m": 0.0})
    for r in fc_norm:
        sp_fc[r["status_pago"]]["n"] += 1
        sp_fc[r["status_pago"]]["m"] += r["tot"]

    no_pag   = [r for r in fc_norm if r["status_pago"] == "No Pagado"]
    n_no_pag = len(no_pag)
    cxp      = round(sp_fc.get("No Pagado", {"m": 0.0})["m"], 2)

    # Tipo de pago
    tp_fc = defaultdict(lambda: {"n": 0, "m": 0.0})
    for r in fc_norm:
        tp_fc[r["tipo_pago"] or "Sin tipo"]["n"] += 1
        tp_fc[r["tipo_pago"] or "Sin tipo"]["m"] += r["tot"]

    # Top 10 proveedores
    prov_fc = defaultdict(lambda: {"n": 0, "sub": 0.0, "tot": 0.0})
    for r in fc_norm:
        p = prov_name(r["nombre"])
        prov_fc[p]["n"] += 1
        prov_fc[p]["sub"] += r["sub"]
        prov_fc[p]["tot"] += r["tot"]
    top_prov = sorted(prov_fc.items(), key=lambda x: -x[1]["tot"])[:10]

    # Crédito vivo
    cred_vivo_acc = defaultdict(lambda: {"n": 0, "m": 0.0})
    for r in no_pag:
        p = prov_name(r["nombre"])
        cred_vivo_acc[p]["n"] += 1
        cred_vivo_acc[p]["m"] += r["tot"]
    cred_vivo = sorted(cred_vivo_acc.items(), key=lambda x: -x[1]["m"])[:10]

    # Top 10 proveedores pagados
    prov_fcp = defaultdict(lambda: {"n": 0, "m": 0.0})
    for r in fcp_norm:
        p = prov_name(r["nombre"])
        prov_fcp[p]["n"] += 1
        prov_fcp[p]["m"] += r["tot"]
    top_prov_pag = sorted(prov_fcp.items(), key=lambda x: -x[1]["m"])[:10]

    # Días factura→pago (solo si el row tiene fecha_pago, formato antiguo)
    t_fc_pago = []
    for r in fcp_norm:
        if not r["fecha_pago"]: continue
        df = parse_date(r["fecha"])
        dp = parse_date(r["fecha_pago"])
        d = days_diff(df, dp)
        if d is not None and d < 365:
            t_fc_pago.append(d)

    # Temporal — usa filas originales para que aggregate_temporal maneje el date_getter
    temporal = aggregate_temporal(
        fc_norm,
        date_getter=lambda row: row["fecha"],
        metric_getters={
            "n":   lambda row: 1,
            "sub": lambda row: row["sub"],
            "tot": lambda row: row["tot"],
        },
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )
    periods = temporal["periodos"]
    temporal["tendencias"] = {
        "n":   linear_trend([p["n"]   for p in periods]),
        "sub": linear_trend([p["sub"] for p in periods]),
        "tot": linear_trend([p["tot"] for p in periods]),
    }

    return {
        "periodo": period_label,
        "kpis": {
            "n_fc": n_fc,
            "sub_fc": sub_fc,
            "iva_fc": iva_fc,
            "tot_fc": tot_fc,
            "n_fcp": n_fcp,
            "sub_fcp": sub_fcp,
            "tot_fcp": tot_fcp,
            "cxp": cxp,
            "n_no_pag": n_no_pag,
            "t_pago_avg": round(avg(t_fc_pago), 1),
            "t_pago_med": round(med(t_fc_pago), 1),
            "t_pago_max": max(t_fc_pago) if t_fc_pago else 0,
            "pct_pagado": round(tot_fcp / tot_fc, 4) if tot_fc else 0,
        },
        "series": {
            "temporal": temporal,
            "status_pago": [{"status": k, **v} for k, v in sp_fc.items()],
            "tipo_pago": [{"tipo": k, **v} for k, v in tp_fc.items()],
        },
        "tables": {
            "top_proveedores": [{"proveedor": k, **v} for k, v in top_prov],
            "credito_vivo": [{"proveedor": k, **v} for k, v in cred_vivo],
            "top_proveedores_pag": [{"proveedor": k, **v} for k, v in top_prov_pag],
        },
    }

# ─── Lectura ────────────────────────────────────────────────────────────────
def load_all(data_dir="data", allowed_files=None):
    prefixes = {
        "cot":  "Cotizaciones",
        "crec": "CRECIMIENTO_INVENTARIO",
        "fc":   "FACTURAS_COMPRAS",
        "fcp":  "FACTURAS_COMPRAS_PAGADAS",
        "gas":  "GASTOS_OPERATIVOS",
        "inv":  "INVENTARIO_REAL_ACTUAL",
        "ms":   "MATERIALES_SALIDA",
        "ped":  "PEDIDOS_CLIENTES",
        "env":  "PEDIDOS_CLIENTES_ENVIADOS",
        "fac":  "PEDIDOS_CLIENTES_FACTURADOS",
        "facs": "PEDIDOS_CLIENTES_FACTURADOS_SECUNDARIA",
        "pag":  "PEDIDOS_CLIENTES_PAGADOS",
        "pent": "PRODUCTOS_ENTRADA",
    }
    optional_prefixes = {
        "gas": "No se encontro GASTOS_OPERATIVOS*.csv; los gastos operativos se toman como $0.00 y el reporte queda incompleto en OPEX."
    }
    data_dir = os.path.abspath(data_dir)
    if not os.path.isdir(data_dir):
        raise FileNotFoundError(f"No existe la carpeta de datos: {data_dir}")

    allowed_files = set(allowed_files) if allowed_files is not None else None
    files = {}
    all_prefixes = list(prefixes.values())
    missing = []
    for key, prefix in prefixes.items():
        matches = [
            os.path.join(data_dir, name)
            for name in os.listdir(data_dir)
            if name.startswith(prefix) and name.lower().endswith(".csv")
            and (allowed_files is None or name in allowed_files)
            and not any(
                other != prefix
                and other.startswith(prefix + "_")
                and name.startswith(other + "_")
                for other in all_prefixes
            )
        ]
        if not matches:
            if key not in optional_prefixes:
                missing.append((key, prefix))
            continue
        files[key] = sorted(matches, key=lambda p: (os.path.getmtime(p), p))[-1]

    if missing:
        existing = sorted(name for name in os.listdir(data_dir) if name.lower().endswith(".csv"))
        missing_lines = "\n".join(f"  - {key}: {prefix}*.csv" for key, prefix in missing)
        existing_lines = "\n".join(f"  - {name}" for name in existing) or "  - Ninguno"
        raise FileNotFoundError(
            "Faltan CSVs obligatorios en la carpeta de datos:\n"
            f"{missing_lines}\n\n"
            f"Carpeta revisada: {data_dir}\n"
            "CSVs encontrados:\n"
            f"{existing_lines}"
        )

    D = {k: read_csv(v) for k, v in files.items()}
    warnings = []
    for key, message in optional_prefixes.items():
        if key not in D:
            D[key] = []
            warnings.append(message)
    D["_files"] = files
    D["_data_dir"] = data_dir
    D["_warnings"] = warnings
    return D

# ─── Análisis ───────────────────────────────────────────────────────────────
def compute(D, period=None):
    period = period or {}
    shared_temporal_axis = temporal_axis(period.get("start"), period.get("end"))
    R = {"warnings": list(D.get("_warnings", [])), "temporal": shared_temporal_axis}
    cot=D["cot"]; crec=D["crec"]; fc=D["fc"]; fcp=D["fcp"]
    gas=D["gas"]; inv=D["inv"]; ms=D["ms"]; ped=D["ped"]
    env=D["env"]; fac=D["fac"]; facs=D["facs"]; pag=D["pag"]; pent=D["pent"]

    SEMS = ["S1","S2","S3","S4","S5"]
    def sem_dict(): return {s:{"n":0,"m":0.0} for s in SEMS}

    # ── MOD 1: COTIZACIONES ────────────────────────────────────────────────
    R["m1"] = compute_ventas(cot)
    R["m1"]["temporal_cot"] = aggregate_temporal(
        cot, lambda row: row.get("Fecha_creacion"),
        {"n": lambda row: 1, "m": lambda row: f(row.get("Total")),
         "na": lambda row: 1 if (row.get("Estado_cotizacion") or "").strip() == "Aprobada" else 0,
         "ma": lambda row: f(row.get("Total")) if (row.get("Estado_cotizacion") or "").strip() == "Aprobada" else 0.0},
        axis=shared_temporal_axis,
    )

    # ── MOD 2A: PEDIDOS CREADOS ────────────────────────────────────────────
    n_ped=len(ped)
    sub_ped=sum(f(r["Subtotal con Envio"]) for r in ped)
    tot_ped=sum(f(r["property_total_formula"]) for r in ped)
    n_falt=sum(1 for r in ped if r.get("tiene_faltante","").upper() in("TRUE","1"))

    rol_ped=defaultdict(lambda:{"n":0,"sub":0.0,"tot":0.0})
    for r in ped:
        rol=(r.get("rol","") or "Sin rol").strip()
        rol_ped[rol]["n"]+=1; rol_ped[rol]["sub"]+=f(r["Subtotal con Envio"]); rol_ped[rol]["tot"]+=f(r["property_total_formula"])

    est_ped=defaultdict(lambda:{"n":0,"m":0.0})
    for r in ped:
        e=(r.get("estado_pedido","") or "Sin estado").strip()
        est_ped[e]["n"]+=1; est_ped[e]["m"]+=f(r["property_total_formula"])

    est_fac=defaultdict(lambda:{"n":0,"m":0.0})
    for r in ped:
        e=(r.get("estado_factura","") or "Sin estado").strip()
        est_fac[e]["n"]+=1; est_fac[e]["m"]+=f(r["property_total_formula"])

    stat_fac=defaultdict(lambda:{"n":0,"m":0.0})
    for r in ped:
        e=(r.get("status_factura","") or "Sin status").strip()
        stat_fac[e]["n"]+=1; stat_fac[e]["m"]+=f(r["property_total_formula"])

    sem_ped={s:{"n":0,"m":0.0} for s in SEMS}
    for r in ped:
        dt=parse_date(r["fecha_pedido"]); s=week(dt)
        if not s: continue
        sem_ped[s]["n"]+=1; sem_ped[s]["m"]+=f(r["property_total_formula"])

    cli_ped=defaultdict(lambda:{"n":0,"m":0.0})
    for r in ped:
        c=(r.get("cliente","") or "?").strip()
        cli_ped[c]["n"]+=1; cli_ped[c]["m"]+=f(r["property_total_formula"])

    # Tiempos preparación
    t_prep=[f(r["dias_preparacion"]) for r in ped if r.get("dias_preparacion","").strip()]
    prep_bins=[("0-1 días",0,2),("2-3 días",2,4),("4-7 días",4,8),("8-14 días",8,15),(">14 días",15,None)]
    rangos_prep=histog(t_prep, prep_bins)

    # Tiempos entrega
    t_ent=[f(r["dias_entrega"]) for r in ped if r.get("dias_entrega","").strip()]
    ent_bins=[("Mismo día",0,1),("1-2 días",1,3),("3-5 días",3,6),("6-10 días",6,11),(">10 días",11,None)]
    rangos_ent=histog(t_ent, ent_bins)
    n_ent_2=sum(1 for v in t_ent if v<=2)
    n_ent_5=sum(1 for v in t_ent if v<=5)
    n_ent_7=sum(1 for v in t_ent if v<=7)

    # Ciclo de facturación (desde PEDIDOS_CLIENTES)
    ciclo_pf=[]; ciclo_fv=[]; ciclo_va=[]; ciclo_total=[]
    for r in ped:
        dp=parse_date(r.get("fecha_pedido",""))
        df=parse_date(r.get("fecha_facturacion",""))
        dv=parse_date(r.get("fecha_validacion",""))
        da=parse_date(r.get("fecha_de_asociacion",""))
        pf=days_diff(dp,df); fv=days_diff(df,dv); va=days_diff(dv,da)
        if pf is not None and pf<180: ciclo_pf.append(pf)
        if fv is not None and fv<90: ciclo_fv.append(fv)
        if va is not None and va<180: ciclo_va.append(va)
        if pf is not None and va is not None and (pf+fv+va)<365:
            try: ciclo_total.append(pf+(fv or 0)+(va or 0))
            except: pass

    # Pedidos entregados con NR pero sin factura
    sin_factura=[r for r in ped if r.get("estado_pedido","").strip()=="Entregado" and r.get("estado_factura","").strip()=="En espera"]
    # Pedidos facturados sin entregar
    sin_entregar=[r for r in ped if r.get("estado_factura","").strip()=="Factura enviada" and r.get("estado_pedido","").strip() not in ("Entregado","")]

    R["m2a"]={
        "n_ped":n_ped,"sub_ped":sub_ped,"tot_ped":tot_ped,"n_falt":n_falt,
        "rol_ped":dict(rol_ped),"est_ped":dict(est_ped),"est_fac":dict(est_fac),"stat_fac":dict(stat_fac),
        "sem_ped":sem_ped,
        "temporal_ped":aggregate_temporal(
            ped, lambda row: row.get("fecha_pedido"),
            {"n": lambda row: 1, "m": lambda row: f(row.get("property_total_formula"))},
            axis=shared_temporal_axis,
        ),
        "top_cli_ped":sorted(cli_ped.items(),key=lambda x:-x[1]["m"])[:10],
        "t_prep_avg":avg(t_prep),"t_prep_med":med(t_prep),"t_prep_max":max(t_prep) if t_prep else 0,
        "rangos_prep":rangos_prep,
        "t_ent_avg":avg(t_ent),"t_ent_med":med(t_ent),"t_ent_max":max(t_ent) if t_ent else 0,
        "rangos_ent":rangos_ent,"n_ent_2":n_ent_2,"n_ent_5":n_ent_5,"n_ent_7":n_ent_7,
        "ciclo_pf_avg":avg(ciclo_pf),"ciclo_pf_med":med(ciclo_pf),"ciclo_pf_max":max(ciclo_pf) if ciclo_pf else 0,
        "ciclo_fv_avg":avg(ciclo_fv),"ciclo_fv_med":med(ciclo_fv),"ciclo_fv_max":max(ciclo_fv) if ciclo_fv else 0,
        "ciclo_va_avg":avg(ciclo_va),"ciclo_va_med":med(ciclo_va),"ciclo_va_max":max(ciclo_va) if ciclo_va else 0,
        "ciclo_tot_avg":avg(ciclo_total),"ciclo_tot_med":med(ciclo_total),"ciclo_tot_max":max(ciclo_total) if ciclo_total else 0,
        "sin_factura":sin_factura,"sin_entregar":sin_entregar,
        "n_ciclo_pf":len(ciclo_pf),"n_ciclo_fv":len(ciclo_fv),"n_ciclo_va":len(ciclo_va),"n_ciclo_tot":len(ciclo_total),
    }

    # ── MOD 2B: ENVIADOS ──────────────────────────────────────────────────
    n_env=len(env); tot_env=sum(f(r["property_total_formula"]) for r in env)
    sub_env=sum(f(r["property_sub_total_formula"]) for r in env)
    n_env_falt=sum(1 for r in env if r.get("property_tiene_faltante","").upper() in("TRUE","1"))

    t_env=[f(r["property_tiempo_de_entrega"]) for r in env if r.get("property_tiempo_de_entrega","").strip()]
    rol_env=defaultdict(lambda:{"n":0,"m":0.0})
    for r in env:
        rol=(r.get("property_rol.0","") or "Sin rol").strip()
        rol_env[rol]["n"]+=1; rol_env[rol]["m"]+=f(r["property_total_formula"])

    cli_env=defaultdict(lambda:{"n":0,"m":0.0})
    for r in env:
        # Extract client from name: PP-FARF*300-820 → FARF
        m=re.search(r'PP-([A-Z0-9]+)\*',r.get("name",""))
        c=m.group(1) if m else "?"
        cli_env[c]["n"]+=1; cli_env[c]["m"]+=f(r["property_total_formula"])

    porc=[f(r.get("property_de_pedido","0").replace("%","")) for r in env]
    n_100=sum(1 for p in porc if p>=100)

    R["m2b"]={
        "n_env":n_env,"tot_env":tot_env,"sub_env":sub_env,"n_env_falt":n_env_falt,
        "t_env_avg":avg(t_env),"t_env_med":med(t_env),"t_env_max":max(t_env) if t_env else 0,
        "rol_env":dict(rol_env),
        "top_cli_env":sorted(cli_env.items(),key=lambda x:-x[1]["m"])[:10],
        "n_100":n_100,"n_parcial":len(env)-n_100,
    }

    # ── MOD 2C: FACTURADOS ────────────────────────────────────────────────
    n_fac=len(fac); tot_fac=sum(f(r["property_total_formula"]) for r in fac)
    sub_fac=sum(f(r["Subtotal con Envio"]) for r in fac)
    mon_1era=sum(f(r.get("property_monto_1er_factura","0")) for r in fac)
    n_facs=len(facs); mon_2da=sum(f(r.get("property_monto_2da_factura","0")) for r in facs)
    R["m2c"]={
        "n_fac":n_fac,"tot_fac":tot_fac,"sub_fac":sub_fac,"mon_1era":mon_1era,
        "n_facs":n_facs,"mon_2da":mon_2da,"tot_facturacion":tot_fac+mon_2da,
        "detalle_sec":[{
            "nombre":r.get("nombre",""),
            "factura":r.get("num_factura",""),
            "cliente":r.get("cliente",""),
            "mon2":f(r.get("property_monto_2da_factura","0")),
        } for r in facs],
    }

    # ── MOD 2D: PAGADOS ───────────────────────────────────────────────────
    n_pag=len(pag); tot_pag=sum(f(r["property_total_formula"]) for r in pag)
    sub_pag=sum(f(r["property_sub_total_formula"]) for r in pag)

    tp_pag=defaultdict(lambda:{"n":0,"m":0.0})
    for r in pag:
        tp=(r.get("property_tipo_de_pago","") or "Sin tipo").strip() or "Sin tipo"
        tp_pag[tp]["n"]+=1; tp_pag[tp]["m"]+=f(r["property_total_formula"])

    rol_pag=defaultdict(lambda:{"n":0,"m":0.0})
    for r in pag:
        rol=(r.get("property_rol.0","") or "Sin rol").strip() or "Sin rol"
        rol_pag[rol]["n"]+=1; rol_pag[rol]["m"]+=f(r["property_total_formula"])

    cli_pag=defaultdict(lambda:{"n":0,"m":0.0})
    for r in pag:
        c=(r.get("property_cliente_f","") or "?").strip()
        cli_pag[c]["n"]+=1; cli_pag[c]["m"]+=f(r["property_total_formula"])

    t_pago=[f(r["property_tiempos_de_pago"]) for r in pag if r.get("property_tiempos_de_pago","").strip()]
    pago_bins=[("0-15 días",0,16),("16-30 días",16,31),("31-60 días",31,61),("61-90 días",61,91),(">90 días",91,None)]
    rangos_pago=histog(t_pago, pago_bins)

    # CxC estimado
    cxc_est = max(0, tot_fac - tot_pag)

    R["m2d"]={
        "n_pag":n_pag,"tot_pag":tot_pag,"sub_pag":sub_pag,
        "tp_pag":dict(tp_pag),"rol_pag":dict(rol_pag),
        "top_cli_pag":sorted(cli_pag.items(),key=lambda x:-x[1]["m"])[:10],
        "t_pago_avg":avg(t_pago),"t_pago_med":med(t_pago),"t_pago_max":max(t_pago) if t_pago else 0,
        "rangos_pago":rangos_pago,"cxc_est":cxc_est,
    }

    # ── MOD 3: COMPRAS ────────────────────────────────────────────────────
    n_fc=len(fc)
    sub_fc=sum(f(r["property_subtotal_f"]) for r in fc)
    iva_fc=sum(f(r["property_iva_16"]) for r in fc)
    env_fc=sum(f(r["property_costo_de_envio"]) for r in fc)
    tot_fc=sub_fc+iva_fc+env_fc

    sem_fc={s:{"n":0,"sub":0.0,"tot":0.0} for s in SEMS}
    for r in fc:
        dt=parse_date(r.get("property_fecha_de_factura.start",""))
        s=week(dt)
        if not s: continue
        row_tot=f(r["property_subtotal_f"])+f(r["property_iva_16"])
        sem_fc[s]["n"]+=1; sem_fc[s]["sub"]+=f(r["property_subtotal_f"]); sem_fc[s]["tot"]+=row_tot

    sp_fc=defaultdict(lambda:{"n":0,"m":0.0})
    for r in fc:
        sp=(r.get("property_status_de_pago","") or "Sin status").strip() or "Sin status"
        sp_fc[sp]["n"]+=1; sp_fc[sp]["m"]+=f(r["property_subtotal_f"])+f(r["property_iva_16"])

    tp_fc=defaultdict(lambda:{"n":0,"m":0.0})
    for r in fc:
        tp=parse_tp(r.get("property_tipo_de_pago.0",""))
        tp_fc[tp]["n"]+=1; tp_fc[tp]["m"]+=f(r["property_subtotal_f"])+f(r["property_iva_16"])

    prov_fc=defaultdict(lambda:{"n":0,"sub":0.0,"tot":0.0})
    for r in fc:
        p=prov_name(r.get("name",""))
        row_tot=f(r["property_subtotal_f"])+f(r["property_iva_16"])
        prov_fc[p]["n"]+=1; prov_fc[p]["sub"]+=f(r["property_subtotal_f"]); prov_fc[p]["tot"]+=row_tot

    cfdi_fc=defaultdict(lambda:{"n":0,"m":0.0})
    for r in fc:
        c=(r.get("property_uso_cfdi","") or "Sin CFDI").strip() or "Sin CFDI"
        cfdi_fc[c]["n"]+=1; cfdi_fc[c]["m"]+=f(r["property_subtotal_f"])+f(r["property_iva_16"])

    # Crédito vivo (no pagadas)
    no_pag=[r for r in fc if r.get("property_status_de_pago","").strip()=="No Pagado"]
    cred_vivo=defaultdict(lambda:{"n":0,"m":0.0})
    for r in no_pag:
        p=prov_name(r.get("name",""))
        cred_vivo[p]["n"]+=1; cred_vivo[p]["m"]+=f(r["property_subtotal_f"])+f(r["property_iva_16"])

    # Pagos a proveedores
    n_fcp=len(fcp)
    sub_fcp=sum(f(r["property_subtotal_f"]) for r in fcp)
    iva_fcp=sum(f(r["property_iva_16"]) for r in fcp)
    env_fcp=sum(f(r["property_costo_de_envio"]) for r in fcp)
    tot_fcp=sub_fcp+iva_fcp+env_fcp

    tp_fcp=defaultdict(lambda:{"n":0,"m":0.0})
    for r in fcp:
        tp=parse_tp(r.get("property_tipo_de_pago.0",""))
        tp_fcp[tp]["n"]+=1; tp_fcp[tp]["m"]+=f(r["property_subtotal_f"])+f(r["property_iva_16"])

    prov_fcp=defaultdict(lambda:{"n":0,"m":0.0})
    for r in fcp:
        p=prov_name(r.get("name",""))
        prov_fcp[p]["n"]+=1; prov_fcp[p]["m"]+=f(r["property_subtotal_f"])+f(r["property_iva_16"])

    # Días factura→pago para compras
    t_fc_pago=[]
    for r in fcp:
        df=parse_date(r.get("property_fecha_de_factura.start",""))
        dp_raw=r.get("property_fecha_de_pago","")
        if dp_raw.startswith("{"):
            try: dp_raw=json.loads(dp_raw).get("start","")
            except: dp_raw=""
        dp=parse_date(dp_raw)
        d=days_diff(df,dp)
        if d is not None and d<365: t_fc_pago.append(d)

    R["m3"]={
        "n_fc":n_fc,"sub_fc":sub_fc,"iva_fc":iva_fc,"env_fc":env_fc,"tot_fc":tot_fc,
        "sem_fc":sem_fc,
        "temporal_fc":aggregate_temporal(
            fc, lambda row: row.get("property_fecha_de_factura.start"),
            {"n": lambda row: 1, "sub": lambda row: f(row.get("property_subtotal_f")),
             "tot": lambda row: f(row.get("property_subtotal_f")) + f(row.get("property_iva_16"))},
            axis=shared_temporal_axis,
        ),
        "sp_fc":dict(sp_fc),"tp_fc":dict(tp_fc),
        "top_prov":sorted(prov_fc.items(),key=lambda x:-x[1]["tot"])[:10],
        "cfdi_fc":dict(cfdi_fc),
        "n_no_pag":len(no_pag),"cxp":sum(d["m"] for d in sp_fc.get("No Pagado",{"m":0.0}) and [sp_fc.get("No Pagado",{"m":0.0})] or [{"m":0.0}]),
        "cred_vivo":sorted(cred_vivo.items(),key=lambda x:-x[1]["m"])[:10],
        "n_fcp":n_fcp,"sub_fcp":sub_fcp,"iva_fcp":iva_fcp,"env_fcp":env_fcp,"tot_fcp":tot_fcp,
        "tp_fcp":dict(tp_fcp),
        "top_prov_pag":sorted(prov_fcp.items(),key=lambda x:-x[1]["m"])[:10],
        "t_fc_pago_avg":avg(t_fc_pago),"t_fc_pago_med":med(t_fc_pago),"t_fc_pago_max":max(t_fc_pago) if t_fc_pago else 0,
    }
    # Fix cxp
    R["m3"]["cxp"]=sp_fc.get("No Pagado",{"m":0.0})["m"]

    # ── MOD 4: INVENTARIO ────────────────────────────────────────────────
    inv_total=sum(f(r["property_costo_total_en_stock"]) for r in inv)
    inv_en=[r for r in inv if r.get("property_estado_real","").strip()=="En stock"]
    inv_sin=[r for r in inv if r.get("property_estado_real","").strip()!="En stock"]
    val_en=sum(f(r["property_costo_total_en_stock"]) for r in inv_en)

    # Snapshots
    snaps={"Febrero":{},"Marzo":{},"Abril":{},"Mayo":{}}
    mes_map={"febrero":"Febrero","marzo":"Marzo","abril":"Abril","mayo":"Mayo"}
    for r in crec:
        nom=(r.get("property_nombre","") or r.get("name","")).lower()
        tipo=r.get("property_tipo","").strip()
        monto=f(r.get("property_monto","0"))
        for k,v in mes_map.items():
            if k in nom:
                if tipo=="Inventario": snaps[v]["total"]=monto
                elif tipo=="Productos sin movimiento": snaps[v]["inmov"]=monto
    for mes,d in snaps.items():
        d["total"]=d.get("total",0); d["inmov"]=d.get("inmov",0)
        d["activo"]=d["total"]-d["inmov"]
        d["pct_inmov"]=d["inmov"]/d["total"] if d["total"] else 0

    # Salidas
    total_sal_piezas=sum(f(r["property_salida_real_final"]) for r in ms)
    top_sal=sorted(ms,key=lambda r:-f(r["property_salida_real_final"]))[:10]

    # Unir con costo de inventario para calcular valor de salida
    inv_by_sku={r.get("property_sku_f",""):r for r in inv}
    salidas_valor=[]
    for r in top_sal:
        sku=r.get("property_sku","") or r.get("property_codigo_interno.0","")
        qty=f(r["property_salida_real_final"])
        inv_r=inv_by_sku.get(sku)
        if inv_r:
            cant_inv=max(f(inv_r.get("property_cantidad_real_en_inventario","1")),1)
            cost_unit=f(inv_r["property_costo_total_en_stock"])/cant_inv
        else: cost_unit=0
        salidas_valor.append({"sku":sku,"qty":qty,"cost_unit":cost_unit,"valor":qty*cost_unit})

    # Entradas
    total_ent_piezas=sum(f(r["property_erf"]) for r in pent)
    top_ent=sorted(pent,key=lambda r:-f(r["property_erf"]))[:10]

    # Top SKUs por valor
    top_inv=sorted(inv,key=lambda r:-f(r["property_costo_total_en_stock"]))[:10]

    R["m4"]={
        "inv_total":inv_total,"n_skus":len(inv),"n_en":len(inv_en),"n_sin":len(inv_sin),"val_en":val_en,
        "snaps":snaps,
        "var_mar_abr":snaps["Abril"]["total"]-snaps["Marzo"]["total"],
        "var_pct_mar_abr":(snaps["Abril"]["total"]-snaps["Marzo"]["total"])/snaps["Marzo"]["total"]*100 if snaps["Marzo"]["total"] else 0,
        "total_sal_piezas":total_sal_piezas,"n_skus_sal":len(ms),
        "top_sal":top_sal,"salidas_valor":salidas_valor,
        "total_ent_piezas":total_ent_piezas,"n_skus_ent":len(pent),
        "top_ent":top_ent,"top_inv":top_inv,
    }

    # ── MOD 5: GASTOS ─────────────────────────────────────────────────────
    gas_real=[r for r in gas if r.get("property_estado","").strip()=="Realizado"]
    gas_pend=[r for r in gas if r.get("property_estado","").strip()!="Realizado"]
    tot_gas=sum(f(r["property_total"]) for r in gas_real)
    sub_gas=sum(f(r["property_subtotal"]) for r in gas_real)

    ded=sum(f(r["property_total"]) for r in gas_real if r.get("property_deducible","").upper() in("TRUE","1"))
    no_ded=tot_gas-ded

    mp_gas=defaultdict(lambda:{"n":0,"m":0.0})
    for r in gas_real:
        mp=(r.get("property_m_todo_de_pago","") or "Sin método").strip() or "Sin método"
        mp_gas[mp]["n"]+=1; mp_gas[mp]["m"]+=f(r["property_total"])

    cat_gas=defaultdict(lambda:{"n":0,"m":0.0})
    for r in gas_real:
        cat=(r.get("property_categor_a","") or "Sin categoría").strip() or "Sin categoría"
        cat_gas[cat]["n"]+=1; cat_gas[cat]["m"]+=f(r["property_total"])

    # Identificar carga fiscal dentro de "Otros" / sin categoría
    fiscal_kw=["DECLARAC","ISR","IVA","SIPARE","INTERESE","FISCAL","IMSS","INFONAVIT"]
    carga_fiscal=[]
    for r in gas_real:
        conc=(r.get("property_concepto_descripci_n","") or r.get("name","")).upper()
        if any(kw in conc for kw in fiscal_kw):
            carga_fiscal.append({"concepto":r.get("property_concepto_descripci_n","") or r.get("name",""),
                                  "total":f(r["property_total"]),
                                  "folio":r.get("property_folio_factura","")})
    tot_fiscal=sum(x["total"] for x in carga_fiscal)
    sub_gas_recur=sub_gas-(tot_fiscal/1.16 if tot_fiscal else 0)

    sem_gas={s:{"n":0,"m":0.0} for s in SEMS}
    for r in gas_real:
        dt=parse_date(r.get("property_fecha.start",""))
        s=week(dt)
        if not s: continue
        sem_gas[s]["n"]+=1; sem_gas[s]["m"]+=f(r["property_total"])

    con_folio=sum(1 for r in gas_real if r.get("property_folio_factura","").strip())
    sin_folio=len(gas_real)-con_folio
    mon_con_folio=sum(f(r["property_total"]) for r in gas_real if r.get("property_folio_factura","").strip())
    mon_sin_folio=tot_gas-mon_con_folio

    conc_gas=defaultdict(lambda:{"n":0,"m":0.0})
    for r in gas_real:
        conc=(r.get("property_concepto_descripci_n","") or r.get("name","")).strip()[:60]
        conc_gas[conc]["n"]+=1; conc_gas[conc]["m"]+=f(r["property_total"])

    resp_gas=defaultdict(lambda:{"n":0,"m":0.0})
    for r in gas_real:
        resp=(r.get("property_responsable.0","") or "Sin responsable").strip() or "Sin responsable"
        resp_gas[resp]["n"]+=1; resp_gas[resp]["m"]+=f(r["property_total"])

    R["m5"]={
        "n_real":len(gas_real),"n_pend":len(gas_pend),
        "tot_gas":tot_gas,"sub_gas":sub_gas,"iva_gas":tot_gas-sub_gas,
        "ded":ded,"no_ded":no_ded,"pct_ded":ded/tot_gas if tot_gas else 0,
        "mp_gas":dict(mp_gas),"cat_gas":dict(cat_gas),
        "carga_fiscal":sorted(carga_fiscal,key=lambda x:-x["total"]),"tot_fiscal":tot_fiscal,
        "sub_gas_recur":max(0,sub_gas_recur),
        "sem_gas":sem_gas,
        "temporal_gas":aggregate_temporal(
            gas_real, lambda row: row.get("property_fecha.start"),
            {"n": lambda row: 1, "m": lambda row: f(row.get("property_total"))},
            axis=shared_temporal_axis,
        ),
        "con_folio":con_folio,"sin_folio":sin_folio,"mon_con_folio":mon_con_folio,"mon_sin_folio":mon_sin_folio,
        "top_conc":sorted(conc_gas.items(),key=lambda x:-x[1]["m"])[:10],
        "resp_gas":sorted(resp_gas.items(),key=lambda x:-x[1]["m"]),
    }

    # ── P&L ───────────────────────────────────────────────────────────────
    ing_sub=R["m2d"]["sub_pag"]
    comp_sub=sub_fc
    margen=ing_sub-comp_sub
    opex_sub=sub_gas
    utilidad=margen-opex_sub
    utilidad_adj=margen-R["m5"]["sub_gas_recur"]
    flujo_neto=tot_pag-tot_fcp-tot_gas
    cxc_total=max(0,R["m2c"]["tot_fac"]-tot_pag)
    cxp_total=R["m3"]["cxp"]

    R["pl"]={
        "ing_sub":ing_sub,"comp_sub":comp_sub,"margen":margen,
        "pct_margen":margen/ing_sub if ing_sub else 0,
        "opex_sub":opex_sub,"utilidad":utilidad,
        "pct_utilidad":utilidad/ing_sub if ing_sub else 0,
        "tot_fiscal":tot_fiscal,
        "opex_recur":R["m5"]["sub_gas_recur"],
        "utilidad_adj":utilidad_adj,
        "pct_utilidad_adj":utilidad_adj/ing_sub if ing_sub else 0,
        "flujo_cobrado":tot_pag,"flujo_pagado_prov":tot_fcp,"flujo_opex":tot_gas,
        "flujo_neto":flujo_neto,
        "cxc_total":cxc_total,"cxp_total":cxp_total,"pos_neta":cxc_total-cxp_total,
    }

    # ── KPIs HERO ─────────────────────────────────────────────────────────
    R["hero"]={
        "n_cot":R["m1"]["n_cot"],"tot_cot":R["m1"]["tot_cot"],
        "conv_q":R["m1"]["conv_q"],"conv_m":R["m1"]["conv_m"],
        "n_ped":n_ped,"tot_ped":tot_ped,
        "n_env":n_env,"tot_env":tot_env,
        "tot_facturacion":R["m2c"]["tot_facturacion"],
        "tot_pag":tot_pag,"sub_pag":sub_pag,
        "margen":margen,"pct_margen":margen/ing_sub if ing_sub else 0,
        "snap_abr_total":snaps["Abril"]["total"],
        "snap_abr_inmov":snaps["Abril"]["inmov"],
        "pct_inmov":snaps["Abril"]["pct_inmov"],
    }

    return R
