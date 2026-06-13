#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RTB Cierre Mensual — Modulo de analisis. Devuelve dict R con todas las metricas."""

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
    # Longitudes reales del string de fecha, NO len(fmt) que da tamano del formato
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

def prov_name(name, invoice_number=""):
    value = str(name or "").strip()
    invoice = str(invoice_number or "").strip()
    if invoice:
        value = re.sub(r"\s*[-–]\s*" + re.escape(invoice) + r"\s*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*[-–]\s*[0-9A-F]{8}(?:-[0-9A-F]{4}){3}-[0-9A-F]{12}\s*$", "", value, flags=re.IGNORECASE)
    return re.sub(r"\s*[-–]\s*[FMA]\s*\d+.*$", "", value).strip()


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

def find_latest_facturacion_csv(data_dir, prefix):
    from pathlib import Path
    root = Path(data_dir)
    pattern = re.compile(rf"^{re.escape(prefix)}\d{{4}}-\d{{2}}-\d{{2}}_\d{{2}}-\d{{2}}\.csv$")
    matches = [p for p in root.glob(f"{prefix}*.csv") if p.is_file() and pattern.match(p.name)]
    if not matches:
        raise FileNotFoundError(f"No se encontro {prefix}*.csv en la carpeta de datos: {root.resolve()}")
    return max(matches, key=lambda p: (p.stat().st_mtime_ns, p.name))

def load_cotizaciones(data_dir="data"):
    try:
        return read_csv(find_latest_csv(data_dir, "Cotizaciones"))
    except FileNotFoundError:
        # Fallback: buscar en data_procesada/ cuando data/ esta vacio (post-archivo de n8n)
        archive = os.path.join(os.path.dirname(os.path.abspath(data_dir)), "data_procesada")
        if os.path.isdir(archive):
            matches = []
            for root, _dirs, files in os.walk(archive):
                for name in files:
                    if name.startswith("Cotizaciones") and name.lower().endswith(".csv"):
                        matches.append(os.path.join(root, name))
            if matches:
                latest = max(matches, key=lambda p: (os.path.getmtime(p), p))
                return read_csv(latest)
        raise

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
    rangos_apr = {"Mismo dia": 0, "1-3 dias": 0, "4-7 dias": 0, ">7 dias": 0}
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
            rangos_apr["Mismo dia"] += 1
        elif delta <= 3:
            rangos_apr["1-3 dias"] += 1
        elif delta <= 7:
            rangos_apr["4-7 dias"] += 1
        else:
            rangos_apr[">7 dias"] += 1
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
    # registro de Notion exportado en ambos CSVs (anomalia de export, no error de captura).
    # Solo reportar duplicados cuya identidad no sea el factura_id (colision de folio/cot).
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

def _parse_anticipos_ids(raw):
    """Parsea la columna Factura_Anticipo_Asociada (string JSON con array de UUIDs)."""
    s = str(raw or "").strip()
    if not s:
        return []
    try:
        lst = json.loads(s)
    except Exception:
        return []
    if not isinstance(lst, list):
        return []
    return [str(x).strip() for x in lst if str(x).strip()]


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
            "numero": (row.get("#_Factura_compra", "") or "").strip(),
            "sub": sub, "iva": iva, "env": env, "tot": tot,
            "fecha": row.get("Facatura_compra_fecha_factura", ""),  # typo en export n8n
            "tipo_pago": parse_tp(row.get("Factura_compra_tipo", "")),
            "cfdi": (row.get("Factura_compra_uso_cfdi", "") or "Sin CFDI").strip() or "Sin CFDI",
            "estado_factura": (row.get("Factura_compra_estatus_factura", "") or "Sin status").strip() or "Sin status",
            "fecha_pago": "",
            "anticipos_ids": _parse_anticipos_ids(row.get("Factura_Anticipo_Asociada", "")),
        }
    sub = f(row.get("property_subtotal_f", 0))
    iva = f(row.get("property_iva_16", 0))
    env = f(row.get("property_costo_de_envio", 0))
    return {
        "nombre": row.get("name", ""),
        "numero": (row.get("property_numero_factura", "") or "").strip(),
        "sub": sub, "iva": iva, "env": env, "tot": sub + iva + env,
        "fecha": row.get("property_fecha_de_factura.start", ""),
        "tipo_pago": parse_tp(row.get("property_tipo_de_pago.0", "")),
        "cfdi": (row.get("property_uso_cfdi", "") or "Sin CFDI").strip() or "Sin CFDI",
        "estado_factura": (row.get("property_status_de_pago", "") or "Sin status").strip() or "Sin status",
        "fecha_pago": row.get("property_fecha_de_pago", ""),
        "anticipos_ids": [],
    }


def _norm_anticipo_row(row):
    """Normaliza una fila de Facturas_Anticipo a estructura unificada."""
    return {
        "id": (row.get("Factura_anticipo_id", "") or "").strip(),
        "nombre": row.get("Factura_anticipo_nombre", "") or "",
        "prov_siglas": (row.get("Factura_anticipo_Proveedor_Siglas", "") or "").strip(),
        "prov_nombre": (row.get("Factura_anticipo_Proveedor_nombre", "") or "").strip(),
        "numero": (row.get("Factura_anticipo_numero_documento", "") or "").strip(),
        "fecha": row.get("Factura_anticipo_fecha_emision", "") or "",
        "estado": (row.get("Factura_anticipo_estado", "") or "Sin estado").strip() or "Sin estado",
        "monto": f(row.get("Factura_anticipo_monto", 0)),
        "tipo_documento": (row.get("Factura_anticipo_tipo_documento", "") or "").strip(),
        "uso_cfdi": (row.get("Factura_anticipo_uso_CFDI", "") or "Sin CFDI").strip() or "Sin CFDI",
    }


def _decorate_compras_temporal(temporal, rows, fecha_hasta=None):
    parsed = sorted(dt for dt in (parse_date(row.get("fecha")) for row in rows) if dt)
    periods = temporal.get("periodos", [])
    if not parsed or not periods:
        for period in periods:
            period["coverage"] = "sin_cobertura"
        temporal["tendencias"] = {}
        temporal["trend_keys"] = []
        return {}

    granularity = temporal.get("granularidad", "semana")
    first_key = temporal_key(parsed[0], granularity)
    last_key = temporal_key(parsed[-1], granularity)
    keys = temporal.get("keys", [])
    first_index = keys.index(first_key) if first_key in keys else 0
    last_index = keys.index(last_key) if last_key in keys else len(keys) - 1
    requested_end = parse_date(fecha_hasta)
    last_is_partial = bool(requested_end and parsed[-1].date() < requested_end.date())

    for index, period in enumerate(periods):
        if index < first_index or index > last_index:
            period["coverage"] = "sin_cobertura"
        elif index == last_index and last_is_partial:
            period["coverage"] = "parcial"
        else:
            period["coverage"] = "completo"

    complete = [period for period in periods if period["coverage"] == "completo"]
    temporal["trend_keys"] = [period["key"] for period in complete]
    temporal["tendencias"] = ({
        "n": linear_trend([period["n"] for period in complete]),
        "sub": linear_trend([period["sub"] for period in complete]),
        "tot": linear_trend([period["tot"] for period in complete]),
    } if len(complete) >= 2 else {})
    if len(complete) < 2:
        return {}

    previous, current = complete[-2:]
    amount_change = ((current["tot"] - previous["tot"]) / previous["tot"]
                     if previous["tot"] else None)
    quantity_change = ((current["n"] - previous["n"]) / previous["n"]
                       if previous["n"] else None)
    return {
        "previous_key": previous["key"],
        "previous_label": previous["etiqueta"],
        "current_key": current["key"],
        "current_label": current["etiqueta"],
        "previous_amount": previous["tot"],
        "current_amount": current["tot"],
        "amount_change_pct": amount_change,
        "previous_quantity": previous["n"],
        "current_quantity": current["n"],
        "quantity_change_pct": quantity_change,
    }


def build_compras_dashboard(fc, anticipos=None, period_label="Periodo actual", fecha_desde=None, fecha_hasta=None):
    _s = parse_date(fecha_desde)
    _e = parse_date(fecha_hasta)
    start_d = _s.date() if _s else None
    end_d = _e.date() if _e else None

    def in_period_d(fecha_str):
        dt = parse_date(fecha_str)
        if not dt: return False
        d = dt.date()
        return (not start_d or d >= start_d) and (not end_d or d <= end_d)

    # Normalizar TODAS las filas primero para resolver anticipos referenciados
    # incluso por facturas fuera del rango de fechas seleccionado.
    fc_all_norm   = [_norm_fc_row(r) for r in fc]
    fc_all_active = [r for r in fc_all_norm if r["estado_factura"] != "Factura Cancelada"]
    # Set de UUIDs de anticipos consumidos por alguna factura ACTIVA (cualquier periodo).
    # Una factura cancelada NO regulariza al anticipo: vuelve a pendiente automaticamente.
    referenced_ids = set()
    for r in fc_all_active:
        referenced_ids.update(r.get("anticipos_ids", []))

    # KPIs y series de facturas: solo periodo seleccionado.
    fc_norm   = [r for r in fc_all_norm if in_period_d(r["fecha"])]
    fc_active = [r for r in fc_norm if r["estado_factura"] != "Factura Cancelada"]
    fc_canc   = [r for r in fc_norm if r["estado_factura"] == "Factura Cancelada"]

    # Totales (excluyen canceladas)
    n_fc   = len(fc_active)
    sub_fc = round(sum(r["sub"] for r in fc_active), 2)
    env_fc = round(sum(r["env"] for r in fc_active), 2)
    tot_fc = round(sum(r["tot"] for r in fc_active), 2)
    # IVA recibido: derivado del total realmente reportado en las facturas
    iva_fc = round(tot_fc - sub_fc - env_fc, 2)
    # IVA acreditable teorico al 16%
    iva_real_fc = round(sub_fc * 0.16, 2)
    iva_diff_fc = round(iva_fc - iva_real_fc, 2)
    iva_diff_pct_fc = (iva_diff_fc / iva_real_fc) if iva_real_fc else 0
    iva_alerta = abs(iva_diff_fc) > 100 and abs(iva_diff_pct_fc) > 0.02

    # Canceladas (metrica de control de calidad)
    n_canc   = len(fc_canc)
    tot_canc = round(sum(r["tot"] for r in fc_canc), 2)

    # Estado de la factura (sobre fc_norm completo para visibilidad de canceladas)
    ef_fc = defaultdict(lambda: {"n": 0, "m": 0.0})
    for r in fc_norm:
        ef_fc[r["estado_factura"]]["n"] += 1
        ef_fc[r["estado_factura"]]["m"] += r["tot"]

    # Tipo de compra (solo facturas activas; campo vacio/Sin tipo → "Productos vendibles")
    tp_fc = defaultdict(lambda: {"n": 0, "m": 0.0})
    for r in fc_active:
        tipo = r["tipo_pago"] if r["tipo_pago"] and r["tipo_pago"] != "Sin tipo" else "Productos vendibles"
        tp_fc[tipo]["n"] += 1
        tp_fc[tipo]["m"] += r["tot"]

    # Top 10 proveedores (solo facturas activas)
    prov_fc = defaultdict(lambda: {"n": 0, "sub": 0.0, "tot": 0.0})
    for r in fc_active:
        p = prov_name(r["nombre"], r.get("numero", ""))
        prov_fc[p]["n"] += 1
        prov_fc[p]["sub"] += r["sub"]
        prov_fc[p]["tot"] += r["tot"]
    top_prov = sorted(prov_fc.items(), key=lambda x: -x[1]["tot"])[:10]
    top_prov_rows = [
        {"proveedor": name, **values, "pct": values["tot"] / tot_fc if tot_fc else 0}
        for name, values in top_prov
    ]
    concentration = {
        "top_provider": top_prov_rows[0]["proveedor"] if top_prov_rows else "",
        "top1_pct": top_prov_rows[0]["pct"] if top_prov_rows else 0,
        "top5_pct": sum(row["tot"] for row in top_prov_rows[:5]) / tot_fc if tot_fc else 0,
    }

    # Uso de CFDI (solo facturas activas)
    cfdi_fc = defaultdict(lambda: {"n": 0, "m": 0.0})
    for r in fc_active:
        cfdi_fc[r["cfdi"] or "Sin CFDI"]["n"] += 1
        cfdi_fc[r["cfdi"] or "Sin CFDI"]["m"] += r["tot"]

    # Temporal (solo facturas activas)
    temporal = aggregate_temporal(
        fc_active,
        date_getter=lambda row: row["fecha"],
        metric_getters={
            "n":   lambda row: 1,
            "sub": lambda row: row["sub"],
            "tot": lambda row: row["tot"],
        },
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )
    comparison = _decorate_compras_temporal(temporal, fc_active, fecha_hasta)

    # ─── Anticipos ──────────────────────────────────────────────────────────
    ant_all_norm = [_norm_anticipo_row(r) for r in (anticipos or [])]
    ant_in_period = [a for a in ant_all_norm if in_period_d(a["fecha"])]

    # Index: anticipo_id -> primera factura activa (cualquier periodo) que lo regulariza.
    ant_to_factura = {}
    for r in fc_all_active:
        for aid in r.get("anticipos_ids", []):
            ant_to_factura.setdefault(aid, r)

    for a in ant_in_period:
        regulariza = ant_to_factura.get(a["id"])
        a["regularizado"] = regulariza is not None
        a["factura_asociada_numero"] = (regulariza.get("numero") if regulariza else "") or ""
        a["factura_asociada_nombre"] = (regulariza.get("nombre") if regulariza else "") or ""

    pendientes = [a for a in ant_in_period if not a["regularizado"]]
    regularizados = [a for a in ant_in_period if a["regularizado"]]

    n_ant = len(ant_in_period)
    monto_ant = round(sum(a["monto"] for a in ant_in_period), 2)
    n_ant_pendientes = len(pendientes)
    monto_pendientes = round(sum(a["monto"] for a in pendientes), 2)
    n_ant_regularizados = len(regularizados)
    monto_regularizados = round(sum(a["monto"] for a in regularizados), 2)

    # Serie temporal apilada: ambas series usan la fecha de emision del anticipo.
    # Rojo = pendientes, verde = regularizados, apilados en el mes de emision.
    if ant_in_period:
        ant_axis = temporal_axis(
            fecha_desde,
            fecha_hasta,
            dates=[a["fecha"] for a in ant_in_period],
        )
        ant_series = aggregate_temporal(
            ant_in_period,
            date_getter=lambda row: row["fecha"],
            metric_getters={
                "monto_pendiente": lambda row: row["monto"] if not row["regularizado"] else 0,
                "monto_regularizado": lambda row: row["monto"] if row["regularizado"] else 0,
                "n_anticipos": lambda row: 1,
            },
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            axis=ant_axis,
        )
        ant_temporal = {
            **ant_axis,
            "periodos": [
                {
                    **p,
                    "monto_pendiente": round(p["monto_pendiente"], 2),
                    "monto_regularizado": round(p["monto_regularizado"], 2),
                }
                for p in ant_series["periodos"]
            ],
        }
    else:
        ant_temporal = {"granularidad": "mes", "keys": [], "labels": [], "periodos": []}

    def _iso_date(s):
        dt = parse_date(s)
        return dt.date().isoformat() if dt else ""

    ant_tabla = sorted(
        [
            {
                "id": a["id"],
                "proveedor": a["prov_nombre"] or a["prov_siglas"] or prov_name(a["nombre"]),
                "numero_documento": a["numero"],
                "fecha": _iso_date(a["fecha"]),
                "monto": round(a["monto"], 2),
                "estado": a["estado"],
                "uso_cfdi": a["uso_cfdi"],
                "regularizado": a["regularizado"],
                "factura_asociada_numero": a["factura_asociada_numero"],
                "factura_asociada_nombre": a["factura_asociada_nombre"],
            }
            for a in ant_in_period
        ],
        key=lambda x: (x["fecha"] or "", -x["monto"]),
        reverse=True,
    )

    return {
        "periodo": period_label,
        "kpis": {
            "n_fc": n_fc,
            "sub_fc": sub_fc,
            "iva_fc": iva_fc,
            "iva_real_fc": iva_real_fc,
            "iva_diff_fc": iva_diff_fc,
            "iva_diff_pct_fc": iva_diff_pct_fc,
            "iva_alerta": iva_alerta,
            "tot_fc": tot_fc,
            "n_canc": n_canc,
            "tot_canc": tot_canc,
        },
        "management": {
            "documented": {
                "count": n_fc + n_ant_pendientes,
                "amount": round(tot_fc + monto_pendientes, 2),
                "invoice_count": n_fc,
                "invoice_amount": tot_fc,
                "pending_advance_count": n_ant_pendientes,
                "pending_advance_amount": monto_pendientes,
            },
            "comparison": comparison,
            "concentration": concentration,
        },
        "series": {
            "temporal": temporal,
            "estado_factura": [{"estado": k, **v} for k, v in ef_fc.items()],
            "tipo_compra": [{"tipo": k, **v} for k, v in tp_fc.items()],
            "uso_cfdi": sorted(
                [{"cfdi": k, **v} for k, v in cfdi_fc.items()],
                key=lambda x: -x["m"],
            ),
        },
        "tables": {
            "top_proveedores": top_prov_rows,
        },
        "anticipos": {
            "kpis": {
                "n_ant": n_ant,
                "monto_ant": monto_ant,
                "n_ant_pendientes": n_ant_pendientes,
                "monto_pendientes": monto_pendientes,
                "n_ant_regularizados": n_ant_regularizados,
                "monto_regularizados": monto_regularizados,
            },
            "tabla": ant_tabla,
            "temporal": ant_temporal,
        },
    }


# ─── Cobranza (cobros de pedidos de ventas) ──────────────────────────────────

_FACTURA_CLEAN_RE = re.compile(r'^C\d+$')
_FOLIO_EXTRACT_RE = re.compile(r'(C\d+)')


def _norm_cobro(row, tipo="principal"):
    if tipo == "principal":
        fecha_pago_raw = row.get("Pedido Pago Fecha de pago ", "") or row.get("Pedido Pago Fecha de pago", "")
    else:
        fecha_pago_raw = row.get("Pedido Pago Fecha de pago Secundaria", "")
    factura_raw = (row.get("Pedido Pago # de Factura") or "").strip()
    m = _FOLIO_EXTRACT_RE.search(factura_raw)
    factura_clean = m.group(1) if m else ""
    factura_dirty = bool(factura_raw and not _FACTURA_CLEAN_RE.fullmatch(factura_raw))
    return {
        "row": row, "tipo": tipo,
        "pedido_id": (row.get("Pedido Pago ID") or "").strip(),
        "nombre": (row.get("Pedido Pago Nombre") or "").strip(),
        "fecha_pago": parse_date(fecha_pago_raw),
        "fecha_asociacion": parse_date(row.get("Pedido Pago Fecha de Asociacion", "")),
        "fecha_aprobacion": parse_date(row.get("Pedido Pago Fecha de aprobacion", "")),
        "factura": factura_clean,
        "factura_raw": factura_raw,
        "factura_dirty": factura_dirty,
        "cliente": (row.get("Pedido Pago Cliente") or "").strip(),
        "tipo_pago": (row.get("Pedido Pago Tipo de pago") or "Sin tipo").strip() or "Sin tipo",
        "monto": round(f(row.get("Pedido Pago Total", 0)), 2),
        "subtotal": round(f(row.get("Pedido Pago Subtotal", 0)), 2),
        "po": (row.get("Pedido Pago PO") or "").strip(),
        "complemento": (row.get("Pedido Pago Complemento de pago") or "").strip(),
        "cotizacion_id": (row.get("Pedido Pago Cotizacion") or "").strip(),
    }


def make_cobranza_signal(tipo, severidad, titulo, descripcion, periodo, metricas=None, registros=None, accion=""):
    s = make_signal(tipo, severidad, titulo, descripcion, periodo, metricas, registros, accion)
    s["modulo"] = "cobranza"
    return s


def build_cobranza_signals(rows, kpis, period_label="Periodo actual"):
    signals = []

    sin_factura = [r for r in rows if r["tipo"] == "principal" and not r["factura"]]
    if sin_factura:
        signals.append(make_cobranza_signal(
            "cobro_sin_factura", "riesgo", "Cobros sin folio de factura",
            f"{len(sin_factura)} cobro(s) con campo '# de Factura' vacio o no parseable.",
            period_label,
            {"cantidad": len(sin_factura), "monto": round(sum(r["monto"] for r in sin_factura), 2)},
            [{"pedido_id": r["pedido_id"], "nombre": r["nombre"], "cliente": r["cliente"],
              "factura_raw": r["factura_raw"], "monto": r["monto"]} for r in sin_factura[:10]],
            "Corregir el campo '# de Factura' en Notion para estos pedidos.",
        ))

    folio_sucios = [r for r in rows if r["tipo"] == "principal" and r["factura_dirty"]]
    if folio_sucios:
        signals.append(make_cobranza_signal(
            "factura_folio_sucio", "atencion", "Folios de factura con notas extra",
            f"{len(folio_sucios)} cobro(s) tienen notas o multiples folios en '# de Factura'. Se extrae el primero.",
            period_label,
            {"cantidad": len(folio_sucios)},
            [{"pedido_id": r["pedido_id"], "nombre": r["nombre"], "cliente": r["cliente"],
              "factura_raw": r["factura_raw"], "folio_extraido": r["factura"]} for r in folio_sucios[:10]],
            "Capturar solo el folio en el campo '# de Factura'; mover notas a otro campo.",
        ))

    sin_cliente = [r for r in rows if r["tipo"] == "principal" and not r["cliente"]]
    if sin_cliente:
        signals.append(make_cobranza_signal(
            "cobro_sin_cliente", "riesgo", "Cobros sin cliente asignado",
            f"{len(sin_cliente)} cobro(s) sin campo 'Cliente' capturado en Notion.",
            period_label,
            {"cantidad": len(sin_cliente), "monto": round(sum(r["monto"] for r in sin_cliente), 2)},
            [{"pedido_id": r["pedido_id"], "nombre": r["nombre"], "monto": r["monto"]} for r in sin_cliente[:10]],
            "Asignar el cliente en Notion para poder hacer analisis por cliente.",
        ))

    sin_asoc = [r for r in rows if r["tipo"] == "principal" and not r["fecha_asociacion"]]
    if sin_asoc:
        signals.append(make_cobranza_signal(
            "cobro_sin_fecha_asociacion", "atencion", "Cobros sin fecha de asociacion a factura",
            f"{len(sin_asoc)} cobro(s) no tienen 'Fecha de Asociacion' en Notion. No es posible calcular el lag.",
            period_label,
            {"cantidad": len(sin_asoc), "monto": round(sum(r["monto"] for r in sin_asoc), 2)},
            [{"pedido_id": r["pedido_id"], "nombre": r["nombre"], "cliente": r["cliente"],
              "monto": r["monto"]} for r in sin_asoc[:10]],
            "Registrar la fecha en que se asocio el pago a la factura en Notion.",
        ))

    sec_sin_monto = [r for r in rows if r["tipo"] == "secundaria"]
    if sec_sin_monto:
        signals.append(make_cobranza_signal(
            "monto_secundaria_no_capturado", "atencion", "Segundo cobro sin monto capturado",
            f"{len(sec_sin_monto)} cobro(s) secundario(s). El campo 'Monto pagado Secundaria' esta vacio en Notion.",
            period_label,
            {"cantidad": len(sec_sin_monto)},
            [{"pedido_id": r["pedido_id"], "nombre": r["nombre"], "cliente": r["cliente"]} for r in sec_sin_monto[:10]],
            "Capturar 'Monto pagado Secundaria' en Notion para reportar el monto exacto del segundo cobro.",
        ))

    if kpis.get("dias_cobro_mediana", 0) > 30:
        signals.append(make_cobranza_signal(
            "cobranza_lenta", "riesgo", "Cobranza con lag alto",
            f"La mediana de dias de cobranza es {kpis['dias_cobro_mediana']:.0f} dias (umbral: 30).",
            period_label,
            {"dias_cobro_mediana": kpis["dias_cobro_mediana"],
             "dias_cobro_promedio": kpis.get("dias_cobro_promedio", 0)},
            [],
            "Revisar procesos de seguimiento de cobranza con clientes.",
        ))

    return signals


def build_cobranza_dashboard(principales, secundarias, period_label="Periodo actual", fecha_desde=None, fecha_hasta=None, cotizaciones=None):
    _s = parse_date(fecha_desde)
    _e = parse_date(fecha_hasta)
    start_d = _s.date() if _s else None
    end_d = _e.date() if _e else None

    def in_period(dt):
        if not dt: return False
        d = dt.date()
        return (not start_d or d >= start_d) and (not end_d or d <= end_d)

    pp_norm = [_norm_cobro(r, "principal") for r in (principales or [])]
    ps_norm = [_norm_cobro(r, "secundaria") for r in (secundarias or [])]
    pp_periodo = [r for r in pp_norm if in_period(r["fecha_pago"])]
    ps_periodo = [r for r in ps_norm if in_period(r["fecha_pago"])]
    all_rows = pp_periodo + ps_periodo

    # ─── KPIs ─────────────────────────────────────────────────────────────────
    cobros_principales = len(pp_periodo)
    cobros_secundarias = len(ps_periodo)
    cobros_total = cobros_principales + cobros_secundarias
    monto_cobrado_total = round(sum(r["monto"] for r in pp_periodo), 2)
    monto_secundarias_referencial = round(sum(r["monto"] for r in ps_periodo), 2)
    ticket_promedio = round(monto_cobrado_total / cobros_principales, 2) if cobros_principales else 0.0

    # ─── Dias de cobranza ─────────────────────────────────────────────────────
    lags = []
    for r in pp_periodo:
        d = days_diff(r["fecha_asociacion"], r["fecha_pago"])
        if d is not None:
            lags.append(d)
    dias_cobro_promedio = round(avg(lags), 1) if lags else 0.0
    dias_cobro_mediana = round(med(lags), 1) if lags else 0.0
    dias_cobro_max = max(lags) if lags else 0
    cobertura_dias_cobro_pct = len(lags) / cobros_principales if cobros_principales else 0.0
    cobros_mayor_30_pct = sum(1 for dias in lags if dias > 30) / len(lags) if lags else 0.0

    rangos_bins = [
        ("Mismo dia", 0, 1), ("1-3 d", 1, 4), ("4-7 d", 4, 8),
        ("8-15 d", 8, 16), ("16-30 d", 16, 31), (">30 d", 31, None),
    ]
    rangos_counts = histog(lags, rangos_bins)
    rangos = [
        {"rango": rango, "n": rangos_counts[rango],
         "pct": round(rangos_counts[rango] / len(lags), 4) if lags else 0.0}
        for rango, _, _ in rangos_bins
    ]

    # ─── Calidad de captura ────────────────────────────────────────────────────
    cobros_sin_factura = sum(1 for r in pp_periodo if not r["factura"])
    cobros_sin_cliente = sum(1 for r in pp_periodo if not r["cliente"])
    cobros_sin_fecha_asociacion = sum(1 for r in pp_periodo if not r["fecha_asociacion"])

    # ─── Pendientes por cobrar ─────────────────────────────────────────────────
    # La cartera se reconstruye a la fecha de cierre. Pagos posteriores no alteran cierres historicos.
    paid_cot_ids = {
        r["cotizacion_id"] for r in pp_norm
        if r["cotizacion_id"] and r["fecha_pago"] and (not end_d or r["fecha_pago"].date() <= end_d)
    }

    n_pendientes_cobro = 0
    monto_pendiente_cobro = 0.0
    tabla_pendientes = []
    top_clientes_pendientes = []
    pendientes_temporal = None
    cartera_antiguedad = [
        {"rango": "0-30 dias", "n": 0, "monto": 0.0},
        {"rango": "31-60 dias", "n": 0, "monto": 0.0},
        {"rango": "61-90 dias", "n": 0, "monto": 0.0},
        {"rango": ">90 dias", "n": 0, "monto": 0.0},
    ]

    if cotizaciones:
        _iso_date = lambda dt: dt.date().isoformat() if dt else ""
        aprobadas_cot = []
        for r in cotizaciones:
            if (r.get("Estado_cotizacion") or "").strip() != "Aprobada":
                continue
            fecha_aprobacion = parse_date(r.get("Fecha_aprobacion", ""))
            if end_d and fecha_aprobacion and fecha_aprobacion.date() > end_d:
                continue
            aprobadas_cot.append(r)
        pendientes_cot = [r for r in aprobadas_cot if r.get("Cotizacion_id", "").strip() not in paid_cot_ids]

        n_pendientes_cobro = len(pendientes_cot)
        monto_pendiente_cobro = round(sum(f(r.get("Total", 0)) for r in pendientes_cot), 2)

        def _rango_antiguedad(dias):
            if dias is None or dias <= 30:
                return "0-30 dias"
            if dias <= 60:
                return "31-60 dias"
            if dias <= 90:
                return "61-90 dias"
            return ">90 dias"

        def _norm_pend(r):
            fap = parse_date(r.get("Fecha_aprobacion", ""))
            dias_pendiente = max(0, (end_d - fap.date()).days) if end_d and fap else None
            return {
                "cotizacion_id": r.get("Cotizacion_id", "").strip(),
                "nombre": (r.get("Cotizacion_nombre") or "").strip(),
                "cliente": (r.get("Cliente") or "").strip(),
                "monto": round(f(r.get("Total", 0)), 2),
                "fecha_aprobacion": _iso_date(fap),
                "dias_pendiente": dias_pendiente,
                "rango_antiguedad": _rango_antiguedad(dias_pendiente),
                "estado_pago": (r.get("Estado_pago") or "").strip(),
                "po": (r.get("PO") or "").strip(),
            }

        pendientes_norm = [_norm_pend(r) for r in pendientes_cot]
        tabla_pendientes = sorted(
            pendientes_norm,
            key=lambda x: (-(x["dias_pendiente"] if x["dias_pendiente"] is not None else -1), -x["monto"]),
        )[:20]
        antiguedad_index = {item["rango"]: item for item in cartera_antiguedad}
        for item in pendientes_norm:
            if item["dias_pendiente"] is None:
                continue
            bucket = antiguedad_index[item["rango_antiguedad"]]
            bucket["n"] += 1
            bucket["monto"] = round(bucket["monto"] + item["monto"], 2)

        # Top 10 clientes por monto pendiente
        _cli_pend = defaultdict(lambda: {"n": 0, "m": 0.0})
        for r in pendientes_cot:
            c = (r.get("Cliente") or "").strip() or "(sin cliente)"
            _cli_pend[c]["n"] += 1
            _cli_pend[c]["m"] += f(r.get("Total", 0))
        top_clientes_pendientes = [
            {"cliente": c, "n": v["n"], "m": round(v["m"], 2)}
            for c, v in sorted(_cli_pend.items(), key=lambda x: -x[1]["m"])[:10]
        ]

        # Serie temporal de pendientes por Fecha_aprobacion
        # Detectar rango automaticamente para mostrar distribucion de antiguedad
        pend_fechas = [parse_date(r.get("Fecha_aprobacion", "")) for r in pendientes_cot]
        pend_fechas = [d for d in pend_fechas if d]
        if pend_fechas:
            pend_fmin = min(pend_fechas).date().isoformat()
            pend_fmax = max(pend_fechas).date().isoformat()
        else:
            pend_fmin = fecha_desde
            pend_fmax = fecha_hasta

        def _fap_getter(r):
            dt = parse_date(r.get("Fecha_aprobacion", ""))
            return dt.isoformat() if dt else ""

        pendientes_temporal = aggregate_temporal(
            [{"_r": r, "monto": round(f(r.get("Total", 0)), 2)} for r in pendientes_cot],
            date_getter=lambda x: _fap_getter(x["_r"]),
            metric_getters={
                "n": lambda x: 1,
                "monto": lambda x: x["monto"],
            },
            fecha_desde=pend_fmin,
            fecha_hasta=pend_fmax,
        )

    # ─── Senales ───────────────────────────────────────────────────────────────
    kpis_pre = {"dias_cobro_mediana": dias_cobro_mediana, "dias_cobro_promedio": dias_cobro_promedio}
    signals = build_cobranza_signals(all_rows, kpis_pre, period_label)

    # ─── Tipos de pago ────────────────────────────────────────────────────────
    tipo_pago_data = defaultdict(lambda: {"n": 0, "m": 0.0})
    for r in pp_periodo:
        tp = r["tipo_pago"] if r["tipo_pago"] != "Sin tipo" else "Sin tipo"
        tipo_pago_data[tp]["n"] += 1
        tipo_pago_data[tp]["m"] += r["monto"]

    # ─── Top clientes ─────────────────────────────────────────────────────────
    cli_data = defaultdict(lambda: {"n": 0, "m": 0.0})
    for r in pp_periodo:
        c = r["cliente"] or "(sin cliente)"
        cli_data[c]["n"] += 1
        cli_data[c]["m"] += r["monto"]
    top_clientes = [
        {"cliente": c, "n": v["n"], "m": round(v["m"], 2)}
        for c, v in sorted(cli_data.items(), key=lambda x: -x[1]["m"])[:10]
    ]

    # ─── Serie temporal ───────────────────────────────────────────────────────
    def _fp(row):
        return row["fecha_pago"].isoformat() if row["fecha_pago"] else ""

    temporal = aggregate_temporal(
        all_rows,
        date_getter=_fp,
        metric_getters={
            "cobros":      lambda row: 1 if row["tipo"] == "principal" else 0,
            "monto":       lambda row: row["monto"] if row["tipo"] == "principal" else 0.0,
            "secundarias": lambda row: 1 if row["tipo"] == "secundaria" else 0,
        },
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )
    periods = temporal["periodos"]
    temporal["tendencias"] = {
        "cobros": linear_trend([p["cobros"] for p in periods]),
        "monto":  linear_trend([p["monto"]  for p in periods]),
    }

    # ─── Tabla cobros ─────────────────────────────────────────────────────────
    def _iso(dt):
        return dt.date().isoformat() if dt else ""

    tabla_cobros = sorted(
        [
            {
                "pedido_id": r["pedido_id"],
                "nombre": r["nombre"],
                "tipo": r["tipo"],
                "cliente": r["cliente"],
                "factura": r["factura"],
                "factura_raw": r["factura_raw"] if r["factura_dirty"] else "",
                "tipo_pago": r["tipo_pago"],
                "monto": r["monto"] if r["tipo"] == "principal" else None,
                "po": r["po"],
                "complemento": r["complemento"],
                "fecha_pago": _iso(r["fecha_pago"]),
                "fecha_asociacion": _iso(r["fecha_asociacion"]),
                "dias_cobro": days_diff(r["fecha_asociacion"], r["fecha_pago"]),
            }
            for r in all_rows
        ],
        key=lambda x: (x["fecha_pago"] or ""), reverse=True,
    )

    return {
        "periodo": period_label,
        "kpis": {
            "cobros_total": cobros_total,
            "cobros_principales": cobros_principales,
            "cobros_secundarias": cobros_secundarias,
            "monto_cobrado_total": monto_cobrado_total,
            "monto_secundarias_referencial": monto_secundarias_referencial,
            "ticket_promedio": ticket_promedio,
            "dias_cobro_promedio": dias_cobro_promedio,
            "dias_cobro_mediana": dias_cobro_mediana,
            "dias_cobro_max": dias_cobro_max,
            "n_con_lag": len(lags),
            "cobros_sin_factura": cobros_sin_factura,
            "cobros_sin_cliente": cobros_sin_cliente,
            "cobros_sin_fecha_asociacion": cobros_sin_fecha_asociacion,
            "n_pendientes_cobro": n_pendientes_cobro,
            "monto_pendiente_cobro": monto_pendiente_cobro,
            "cobertura_dias_cobro_pct": cobertura_dias_cobro_pct,
            "cobros_mayor_30_pct": cobros_mayor_30_pct,
            "exposicion_cartera_sobre_cobrado": monto_pendiente_cobro / monto_cobrado_total if monto_cobrado_total else 0.0,
            "senales": len(signals),
        },
        "series": {
            "temporal": temporal,
            "tipo_pago": [{"tipo": k, **v} for k, v in sorted(tipo_pago_data.items(), key=lambda x: -x[1]["m"])],
            "dias_cobro": {
                "stats": {
                    "avg": dias_cobro_promedio, "med": dias_cobro_mediana,
                    "max": dias_cobro_max, "n": len(lags),
                },
                "rangos": rangos,
            },
            "pendientes_temporal": pendientes_temporal,
            "cartera_antiguedad": cartera_antiguedad,
        },
        "tables": {
            "top_clientes": top_clientes,
            "top_clientes_pendientes": top_clientes_pendientes,
            "cobros": tabla_cobros,
            "pendientes": tabla_pendientes,
        },
        "signals": signals,
    }


# ─── Modulo Pagos a Proveedores ─────────────────────────────────────────────
_RE_PAGOS_FC = re.compile(r"^Pagos_Facturas_Compras_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\.csv$")
_RE_NOTAS_CREDITO = re.compile(r"^Pago_Facturas_Nostas_Credito_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\.csv$")

def _find_csv_with_fallback(root_dir, compiled_re, glob_prefix):
    from pathlib import Path
    root = Path(root_dir)
    matches = [p for p in root.glob(f"{glob_prefix}*.csv") if p.is_file() and compiled_re.match(p.name)]
    if not matches:
        archive = root.parent / "data_procesada"
        if archive.is_dir():
            matches = [p for p in archive.rglob(f"{glob_prefix}*.csv") if compiled_re.match(p.name)]
    if not matches:
        return None
    return max(matches, key=lambda p: (p.stat().st_mtime_ns, p.name))

def find_latest_pagos_proveedores_csvs(data_dir="data"):
    p_fc = _find_csv_with_fallback(data_dir, _RE_PAGOS_FC, "Pagos_Facturas_Compras_")
    p_nc = _find_csv_with_fallback(data_dir, _RE_NOTAS_CREDITO, "Pago_Facturas_Nostas_Credito_")
    if p_fc is None:
        raise FileNotFoundError(f"No se encontro Pagos_Facturas_Compras_*.csv en {data_dir} ni en data_procesada/")
    return p_fc, p_nc  # p_nc puede ser None si no existe aun


_RE_GASTOS_OP = re.compile(r"^Gastos_Operativos_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\.csv$")

def find_latest_gastos_operativos_csv(data_dir="data"):
    p = _find_csv_with_fallback(data_dir, _RE_GASTOS_OP, "Gastos_Operativos_")
    if p is None:
        raise FileNotFoundError(f"No se encontro Gastos_Operativos_*.csv en {data_dir} ni en data_procesada/")
    return p


# ─── Modulo Logistica ────────────────────────────────────────────────────────
_RE_PED_APROBADOS   = re.compile(r"^Pedidos_Aprbados_En_El_Periodo_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\.csv$")
_RE_PED_ENVIADOS    = re.compile(r"^Pedidos_Enviados_En_El_Periodo_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\.csv$")
_RE_PED_ENTREGADOS  = re.compile(r"^Pedidos_Entregados_En_El_Periodo_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\.csv$")
_RE_SEG_INCOMPLETOS = re.compile(r"^Segimiento_pedidos_entregados_incompletos_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\.csv$")

# ─── Modulo Inventario y Almacen ────────────────────────────────────────────
_RE_INVENTARIO   = re.compile(r"^Crecimineto_inventario_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\.csv$")
_RE_PART_VENTAS  = re.compile(r"^Partidas_facturas_ventas_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\.csv$")
_RE_PART_COMPRAS = re.compile(r"^Partidas_facturas_compras_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\.csv$")


def find_latest_inventario_csv(data_dir="data"):
    p = _find_csv_with_fallback(data_dir, _RE_INVENTARIO, "Crecimineto_inventario_")
    if p is None:
        raise FileNotFoundError(
            f"No se encontro Crecimineto_inventario_*.csv en {data_dir} ni en data_procesada/"
        )
    return p


def find_latest_partidas_ventas_csv(data_dir="data"):
    p = _find_csv_with_fallback(data_dir, _RE_PART_VENTAS, "Partidas_facturas_ventas_")
    if p is None:
        raise FileNotFoundError(
            f"No se encontro Partidas_facturas_ventas_*.csv en {data_dir} ni en data_procesada/"
        )
    return p


def find_latest_partidas_compras_csv(data_dir="data"):
    p = _find_csv_with_fallback(data_dir, _RE_PART_COMPRAS, "Partidas_facturas_compras_")
    if p is None:
        raise FileNotFoundError(
            f"No se encontro Partidas_facturas_compras_*.csv en {data_dir} ni en data_procesada/"
        )
    return p


# ─── Modulo Logistica ────────────────────────────────────────────────────────
def find_latest_logistica_csvs(data_dir="data"):
    """Devuelve (ap, en, et, seg) — ap/en/et obligatorios, seg puede ser None."""
    p_ap  = _find_csv_with_fallback(data_dir, _RE_PED_APROBADOS,   "Pedidos_Aprbados_En_El_Periodo_")
    p_en  = _find_csv_with_fallback(data_dir, _RE_PED_ENVIADOS,    "Pedidos_Enviados_En_El_Periodo_")
    p_et  = _find_csv_with_fallback(data_dir, _RE_PED_ENTREGADOS,  "Pedidos_Entregados_En_El_Periodo_")
    p_seg = _find_csv_with_fallback(data_dir, _RE_SEG_INCOMPLETOS, "Segimiento_pedidos_entregados_incompletos_")
    if p_et is None:
        raise FileNotFoundError(
            f"No se encontro Pedidos_Entregados_En_El_Periodo_*.csv en {data_dir} ni en data_procesada/"
        )
    if p_ap is None:
        raise FileNotFoundError(
            f"No se encontro Pedidos_Aprbados_En_El_Periodo_*.csv en {data_dir} ni en data_procesada/"
        )
    if p_en is None:
        raise FileNotFoundError(
            f"No se encontro Pedidos_Enviados_En_El_Periodo_*.csv en {data_dir} ni en data_procesada/"
        )
    return p_ap, p_en, p_et, p_seg  # p_seg puede ser None si no existe todavia


# Normalizacion del tipo de pago de Pagos_Facturas_Compras
_TP_MAP = {
    "1": "Efectivo",
    "3": "Transferencia",
    "28": "Tarjeta de debito",
    "99": "Por definir",
}

def _normalizar_tipo_pago_fc(raw):
    raw = (raw or "").strip()
    code = raw.split()[0] if raw else ""
    return _TP_MAP.get(code, raw or "Sin tipo")


def build_pagos_proveedores_dashboard(pagos_fc, notas_credito, period_label="Periodo actual", fecha_desde=None, fecha_hasta=None):
    _s = parse_date(fecha_desde)
    _e = parse_date(fecha_hasta)
    start_d = _s.date() if _s else None
    end_d = _e.date() if _e else None

    def in_period(dt):
        if not dt: return False
        d = dt.date()
        return (not start_d or d >= start_d) and (not end_d or d <= end_d)

    # Construir lista de IDs de notas de credito para cruce
    nc_ids = {str(r.get("Pago_Facturas_Nostas_Credito_id", "")).strip() for r in (notas_credito or [])}

    def _norm_pago(r):
        tp_raw = (r.get("Pagos_Facturas_Compras_tipo_pago") or "").strip()
        nc_raw = (r.get("Pagos_Facturas_Compras_nota_credito") or "[]").strip()
        try:
            nc_list = json.loads(nc_raw) if nc_raw.startswith("[") else []
        except Exception:
            nc_list = []
        return {
            "id": (r.get("Pagos_Facturas_Compras_id") or "").strip(),
            "nombre": (r.get("Pagos_Facturas_Compras_nombre") or "").strip(),
            "fecha_pago": parse_date(r.get("Pagos_Facturas_Compras_fecha_pago")),
            "numero_factura": (r.get("Pagos_Facturas_Compras_numero_factura") or "").strip(),
            "tipo_compra": (r.get("Pagos_Facturas_Compras_tipo_compra") or "").strip() or "Sin clasificar",
            "tipo_pago": _normalizar_tipo_pago_fc(tp_raw),
            "tipo_pago_raw": tp_raw,
            "estatus": (r.get("Pagos_Facturas_Compras_estatus_pago") or "").strip(),
            "nc_list": nc_list,
            "monto": round(f(r.get("Pagos_Facturas_Compras_cantidad_pagada")), 2),
            "proveedor": (r.get("Pagos_Facturas_Compras_Nombre_proveedor") or "").strip(),
            "proveedor_id": (r.get("Pagos_Facturas_Compras_id_provedor") or "").strip(),
        }

    def _norm_nc(r):
        return {
            "id": (r.get("Pago_Facturas_Nostas_Credito_id") or "").strip(),
            "nombre": (r.get("Pago_Facturas_Nostas_Credito_nombre") or "").strip(),
            "proveedor": str(r.get("Pago_Facturas_Nostas_Credito_proveedor_nombre") or "").strip().strip("[]\"'"),
            "proveedor_id": (r.get("Pago_Facturas_Nostas_Credito_proveedor_siglas") or "").strip(),
            "numero_doc": (r.get("Pago_Facturas_Nostas_Credito_numero_documento") or "").strip(),
            "tipo_doc": (r.get("Pago_Facturas_Nostas_Credito_tipo_documeto") or "").strip(),
            "tipo_pago": (r.get("Pago_Facturas_Nostas_Credito_tipo_pago") or "").strip(),
            "factura_asociada": (r.get("Pago_Facturas_Nostas_Credito_factura_asociada") or "").strip(),
            "monto": round(f(r.get("Pago_Facturas_Nostas_Credito_total_pagado")), 2),
            "estado": (r.get("Pago_Facturas_Nostas_Credito_estado_pago") or "").strip(),
            "fecha_pago": parse_date(r.get("Pago_Facturas_Nostas_Credito_fecha_pago")),
        }

    pagos_norm = [_norm_pago(r) for r in (pagos_fc or [])]
    nc_norm = [_norm_nc(r) for r in (notas_credito or [])]

    pagos_periodo = [r for r in pagos_norm if in_period(r["fecha_pago"])]
    pagos_pagados = [r for r in pagos_periodo if r["estatus"] == "Pagado"]
    pagos_pendientes = [r for r in pagos_periodo if r["estatus"] != "Pagado"]

    monto_fc = round(sum(r["monto"] for r in pagos_pagados), 2)
    monto_nc = round(sum(r["monto"] for r in nc_norm), 2)
    monto_total = round(monto_fc + monto_nc, 2)

    n_pagados = len(pagos_pagados)
    n_pendientes = len(pagos_pendientes)
    n_nc = len(nc_norm)

    # Distribucion tipo de pago
    tp_data = defaultdict(lambda: {"n": 0, "m": 0.0})
    for r in pagos_pagados:
        tp = r["tipo_pago"]
        tp_data[tp]["n"] += 1
        tp_data[tp]["m"] += r["monto"]

    n_por_definir = sum(1 for r in pagos_pagados if r["tipo_pago"] == "Por definir")
    pct_por_definir = round(n_por_definir / n_pagados, 4) if n_pagados else 0.0

    # Top proveedores (por monto absoluto, ya que algunos montos son negativos por NC)
    prov_data = defaultdict(lambda: {"n": 0, "m": 0.0})
    for r in pagos_pagados:
        p = r["proveedor"] or "(sin proveedor)"
        prov_data[p]["n"] += 1
        prov_data[p]["m"] += r["monto"]
    top_proveedores = [
        {"proveedor": k, "n": v["n"], "m": round(v["m"], 2)}
        for k, v in sorted(prov_data.items(), key=lambda x: -x[1]["m"])[:15]
    ]

    # Serie temporal
    def _fp(row):
        return row["fecha_pago"].isoformat() if row["fecha_pago"] else ""

    temporal = aggregate_temporal(
        pagos_pagados,
        date_getter=_fp,
        metric_getters={
            "pagos": lambda row: 1,
            "monto": lambda row: row["monto"],
        },
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )
    periods = temporal["periodos"]
    temporal["tendencias"] = {
        "pagos": linear_trend([p["pagos"] for p in periods]),
        "monto": linear_trend([p["monto"] for p in periods]),
    }

    # Tabla de detalle
    def _iso(dt):
        return dt.date().isoformat() if dt else ""

    tabla_pagos = sorted(
        [
            {
                "id": r["id"],
                "proveedor": r["proveedor"],
                "numero_factura": r["numero_factura"],
                "tipo_compra": r["tipo_compra"],
                "tipo_pago": r["tipo_pago"],
                "estatus": r["estatus"],
                "monto": r["monto"],
                "nc_aplicada": len(r["nc_list"]) > 0,
                "fecha_pago": _iso(r["fecha_pago"]),
            }
            for r in pagos_pagados
        ],
        key=lambda x: -x["monto"],
    )[:50]

    # Senales
    signals = []
    if n_por_definir:
        signals.append(make_signal(
            "pago_tipo_por_definir", "atencion", "Pagos sin tipo de pago definido",
            f"{n_por_definir} registro(s) con tipo de pago '99 por definir'. Completar en Notion.",
            period_label,
            {"cantidad": n_por_definir, "porcentaje": pct_por_definir},
            [],
            "Actualizar el tipo de pago en la base de datos de Notion.",
        ))
    if n_pendientes:
        signals.append(make_signal(
            "pago_pendiente", "riesgo", "Pagos registrados sin liquidar",
            f"{n_pendientes} pago(s) con estatus 'No Pagado' en el periodo.",
            period_label,
            {"cantidad": n_pendientes, "monto": round(sum(r["monto"] for r in pagos_pendientes), 2)},
            [{"nombre": r["nombre"], "monto": r["monto"]} for r in pagos_pendientes[:10]],
            "Verificar y liquidar los pagos pendientes.",
        ))
    nc_aplicadas = [r for r in pagos_pagados if len(r["nc_list"]) > 0]
    if nc_aplicadas:
        signals.append(make_signal(
            "nc_aplicada", "info", "Notas de credito aplicadas",
            f"{len(nc_aplicadas)} factura(s) con nota de credito aplicada en el periodo.",
            period_label,
            {"cantidad": len(nc_aplicadas)},
            [],
            "",
        ))

    return {
        "periodo": period_label,
        "kpis": {
            "monto_total": monto_total,
            "monto_fc": monto_fc,
            "monto_nc": monto_nc,
            "n_pagados": n_pagados,
            "n_pendientes": n_pendientes,
            "n_nc": n_nc,
            "n_por_definir": n_por_definir,
            "pct_por_definir": pct_por_definir,
            "senales": len(signals),
        },
        "series": {
            "temporal": temporal,
            "tipo_pago": [{"tipo": k, **v} for k, v in sorted(tp_data.items(), key=lambda x: -x[1]["m"])],
        },
        "tables": {
            "top_proveedores": top_proveedores,
            "pagos_detalle": tabla_pagos,
            "notas_anticipos": [
                {
                    "nombre": r["nombre"],
                    "proveedor": r["proveedor"],
                    "tipo_doc": r["tipo_doc"],
                    "numero_doc": r["numero_doc"],
                    "tipo_pago": r["tipo_pago"],
                    "factura_asociada": r["factura_asociada"],
                    "monto": r["monto"],
                    "estado": r["estado"],
                    "fecha_pago": _iso(r["fecha_pago"]),
                }
                for r in nc_norm
            ],
        },
        "signals": signals,
    }


# ─── Modulo Gastos Operativos ────────────────────────────────────────────────
def build_gastos_operativos_dashboard(rows, period_label="Periodo actual", fecha_desde=None, fecha_hasta=None):
    _s = parse_date(fecha_desde)
    _e = parse_date(fecha_hasta)
    start_d = _s.date() if _s else None
    end_d = _e.date() if _e else None

    def in_period(dt):
        if not dt: return False
        d = dt.date()
        return (not start_d or d >= start_d) and (not end_d or d <= end_d)

    def _norm_gasto(r):
        return {
            "id": (r.get("Gasto Operativo id") or "").strip(),
            "nombre": (r.get("Gasto Operativo name") or "").strip(),
            "subtotal": round(f(r.get("Gasto Operativo Subtotal")), 2),
            "iva": round(f(r.get("Gasto Operativo Iva")), 2),
            "total": round(f(r.get("Gasto Operativo Total")), 2),
            "fecha": parse_date(r.get("Gasto Operativo Fecha ")),  # nota: campo tiene espacio al final
            "estado": (r.get("Gasto Operativo Estado") or "").strip(),
            "factura": (r.get("Gasto Operativo Factura") or "").strip(),
            "proveedor": (r.get("Gasto Operativo Proveedor Nombre") or "").strip(),
            "proveedor_id": (r.get("Gasto Operativo Proveedor ID") or "").strip(),
            "tipo_pago": (r.get("Gasto Operativo Tipo de Pago") or "").strip(),
            "categoria": (r.get("Gasto Operativo Categoria") or "").strip() or "Sin categoria",
            "tarjeta": (r.get("Gasto Operativo Tarjeta ") or "").strip() or "Sin tarjeta",  # campo tiene espacio
            "deducible": str(r.get("Gasto Operativo Deducible") or "").strip().upper() == "TRUE",
        }

    gastos_norm = [_norm_gasto(r) for r in (rows or [])]
    realizados = [r for r in gastos_norm if r["estado"] == "Realizado"]
    rechazados = [r for r in gastos_norm if r["estado"] == "Rechazado"]
    periodo = [r for r in realizados if in_period(r["fecha"])]

    total_subtotal = round(sum(r["subtotal"] for r in periodo), 2)
    total_iva = round(sum(r["iva"] for r in periodo), 2)
    total_total = round(sum(r["total"] for r in periodo), 2)

    deducibles = [r for r in periodo if r["deducible"]]
    no_deducibles = [r for r in periodo if not r["deducible"]]

    monto_deducible = round(sum(r["total"] for r in deducibles), 2)
    monto_no_deducible = round(sum(r["total"] for r in no_deducibles), 2)
    iva_acreditable = round(sum(r["iva"] for r in deducibles), 2)
    iva_no_acreditable = round(sum(r["iva"] for r in no_deducibles), 2)

    pct_deducible = round(monto_deducible / total_total, 4) if total_total else 0.0

    n_rechazados = len(rechazados)
    monto_rechazado = round(sum(r["total"] for r in rechazados), 2)

    # Distribucion por categoria
    cat_data = defaultdict(lambda: {"n": 0, "m": 0.0})
    for r in periodo:
        cat_data[r["categoria"]]["n"] += 1
        cat_data[r["categoria"]]["m"] += r["total"]
    series_categoria = [
        {"categoria": k, "n": v["n"], "m": round(v["m"], 2)}
        for k, v in sorted(cat_data.items(), key=lambda x: -x[1]["m"])
    ]

    # Distribucion por tarjeta
    tar_data = defaultdict(lambda: {"n": 0, "m": 0.0})
    for r in periodo:
        tar_data[r["tarjeta"]]["n"] += 1
        tar_data[r["tarjeta"]]["m"] += r["total"]
    series_tarjeta = [
        {"tarjeta": k, "n": v["n"], "m": round(v["m"], 2)}
        for k, v in sorted(tar_data.items(), key=lambda x: -x[1]["m"])
    ]

    # Top proveedores
    prov_data = defaultdict(lambda: {"n": 0, "m": 0.0})
    for r in periodo:
        p = r["proveedor"] or "(sin proveedor)"
        prov_data[p]["n"] += 1
        prov_data[p]["m"] += r["total"]
    top_proveedores = [
        {"proveedor": k, "n": v["n"], "m": round(v["m"], 2)}
        for k, v in sorted(prov_data.items(), key=lambda x: -x[1]["m"])[:10]
    ]

    # Serie temporal
    def _fg(row):
        return row["fecha"].isoformat() if row["fecha"] else ""

    temporal = aggregate_temporal(
        periodo,
        date_getter=_fg,
        metric_getters={
            "gastos": lambda row: 1,
            "monto": lambda row: row["total"],
        },
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )
    periods = temporal["periodos"]
    temporal["tendencias"] = {
        "gastos": linear_trend([p["gastos"] for p in periods]),
        "monto": linear_trend([p["monto"] for p in periods]),
    }

    # Tabla detalle
    def _iso(dt):
        return dt.date().isoformat() if dt else ""

    tabla_gastos = sorted(
        [
            {
                "nombre": r["nombre"],
                "categoria": r["categoria"],
                "proveedor": r["proveedor"],
                "tipo_pago": r["tipo_pago"],
                "tarjeta": r["tarjeta"],
                "subtotal": r["subtotal"],
                "iva": r["iva"],
                "total": r["total"],
                "deducible": r["deducible"],
                "factura": r["factura"],
                "estado": r["estado"],
                "fecha": _iso(r["fecha"]),
            }
            for r in periodo
        ],
        key=lambda x: -x["total"],
    )[:50]

    # Senales
    signals = []
    n_sin_factura = sum(1 for r in periodo if not r["factura"])
    n_sin_proveedor = sum(1 for r in periodo if not r["proveedor"])
    monto_sin_factura = round(sum(r["total"] for r in periodo if not r["factura"]), 2)

    if n_rechazados:
        signals.append(make_signal(
            "gasto_rechazado", "riesgo", "Gastos rechazados",
            f"{n_rechazados} gasto(s) con estado 'Rechazado' (no incluidos en totales).",
            period_label,
            {"cantidad": n_rechazados, "monto": monto_rechazado},
            [{"nombre": r["nombre"], "total": r["total"]} for r in rechazados[:10]],
            "Verificar si deben eliminarse o corregirse en Notion.",
        ))
    if n_sin_factura:
        signals.append(make_signal(
            "gasto_sin_factura", "info", "Gastos sin numero de factura",
            f"{n_sin_factura} gasto(s) sin numero de factura capturado (monto total: ${monto_sin_factura:,.2f}).",
            period_label,
            {"cantidad": n_sin_factura, "monto": monto_sin_factura},
            [],
            "Comun en efectivo / pasajes, pero verificar que esten respaldados.",
        ))
    if n_sin_proveedor:
        signals.append(make_signal(
            "gasto_sin_proveedor", "info", "Gastos sin proveedor",
            f"{n_sin_proveedor} gasto(s) sin proveedor capturado.",
            period_label,
            {"cantidad": n_sin_proveedor},
            [],
            "Completar el proveedor en Notion para mejorar la trazabilidad.",
        ))

    return {
        "periodo": period_label,
        "kpis": {
            "total_subtotal": total_subtotal,
            "total_iva": total_iva,
            "total_total": total_total,
            "iva_acreditable": iva_acreditable,
            "iva_no_acreditable": iva_no_acreditable,
            "monto_deducible": monto_deducible,
            "monto_no_deducible": monto_no_deducible,
            "pct_deducible": pct_deducible,
            "n_gastos": len(periodo),
            "n_deducibles": len(deducibles),
            "n_no_deducibles": len(no_deducibles),
            "n_rechazados": n_rechazados,
            "monto_rechazado": monto_rechazado,
            "n_sin_factura": n_sin_factura,
            "n_sin_proveedor": n_sin_proveedor,
            "senales": len(signals),
        },
        "series": {
            "temporal": temporal,
            "categoria": series_categoria,
            "tarjeta": series_tarjeta,
        },
        "tables": {
            "top_proveedores": top_proveedores,
            "gastos_detalle": tabla_gastos,
            "deducibles_split": [
                {"tipo": "Deducible", "n": len(deducibles), "m": monto_deducible, "iva": iva_acreditable},
                {"tipo": "No deducible", "n": len(no_deducibles), "m": monto_no_deducible, "iva": iva_no_acreditable},
            ],
        },
        "signals": signals,
    }


def build_logistica_dashboard(
    aprobados, enviados, entregados, seguimiento,
    period_label="Periodo actual", fecha_desde=None, fecha_hasta=None,
):
    _s = parse_date(fecha_desde)
    _e = parse_date(fecha_hasta)
    start_d = _s.date() if _s else None
    end_d   = _e.date() if _e else None

    def in_period(dt):
        if not dt: return False
        d = dt.date()
        return (not start_d or d >= start_d) and (not end_d or d <= end_d)

    # Derivar prefijo del primer row de cada lista (columna que termina en _id)
    def _prefix_of(rows):
        if not rows: return ""
        id_keys = [k for k in rows[0].keys() if k.endswith("_id")]
        return id_keys[0][:-3] if id_keys else ""  # quita "_id"

    def _norm_pedido(r, pre):
        emp_raw = (r.get(pre + "_potcentaje_pedido_empacado") or "").replace("%", "").strip()
        try:
            emp = int(float(emp_raw))
        except (ValueError, TypeError):
            emp = 0
        return {
            "id":            (r.get(pre + "_id") or "").strip(),
            "nombre":        (r.get(pre + "_nombre") or "").strip(),
            "total":         round(f(r.get(pre + "_total")), 2),
            "empacado":      emp,
            "factura":       (r.get(pre + "_#_factura") or "").strip(),
            "fecha_envio":   parse_date(r.get(pre + "_fecha_envio")),
            "tipo_envio":    (r.get(pre + "_tipo_envio") or "").strip() or "Sin tipo",
            "estado":        (r.get(pre + "_estado_pedido") or "").strip(),
            "faltante":      str(r.get(pre + "_tiene_faltante") or "").strip().lower() == "true",
            "cliente":       (r.get(pre + "_cliente") or "").strip() or "(sin cliente)",
            "fecha_entrega": parse_date(r.get(pre + "_fecha_entrega")),
            "fecha_aprob":   parse_date(r.get(pre + "_fecha_de_aprobacion.start")),
        }

    def _norm_seg(r):
        pre = "Segimiento_pedidos_entregados_incompletos"
        # fecha_del_pedido tiene clave malformada en n8n (prefijo duplicado sin separador)
        fecha_pedido = None
        for k in r:
            if "fecha_del_pedido" in k:
                fecha_pedido = parse_date(r[k])
                break
        return {
            "id":                  (r.get(pre + "_id") or "").strip(),
            "nombre":              (r.get(pre + "_name") or "").strip(),
            "cliente":             (r.get(pre + "_cliente") or "").strip() or "(sin cliente)",
            "estado":              (r.get(pre + "_estado") or "").strip(),
            "motivo":              (r.get(pre + "_motivo_de_incompletitud") or "").strip(),
            "prioridad":           (r.get(pre + "_prioridad") or "").strip() or "Sin prioridad",
            "productos_faltantes": (r.get(pre + "_productos_faltantes.0") or "").strip(),
            "fecha_creacion":      parse_date(r.get(pre + "_fecha_de_creaci_n")),
            "fecha_est_res":       parse_date(r.get(pre + "_fecha_estimada_de_resoluci_n")),
            "notas":               (r.get(pre + "_notas_adicionales") or "").strip(),
        }

    # ── Normalizar ────────────────────────────────────────────────────────────
    pre_ap = _prefix_of(aprobados)
    pre_en = _prefix_of(enviados)
    pre_et = _prefix_of(entregados)

    ap_norm  = [_norm_pedido(r, pre_ap) for r in (aprobados   or [])]
    en_norm  = [_norm_pedido(r, pre_en) for r in (enviados    or [])]
    et_norm  = [_norm_pedido(r, pre_et) for r in (entregados  or [])]
    seg_norm = [_norm_seg(r)            for r in (seguimiento or [])]

    # ── Filtrar por periodo (fecha natural de cada CSV) ───────────────────────
    ap_periodo = [r for r in ap_norm if in_period(r["fecha_aprob"])]
    en_periodo = [r for r in en_norm if in_period(r["fecha_envio"])]
    et_periodo = [r for r in et_norm if in_period(r["fecha_entrega"])]

    # ── KPIs basicos ──────────────────────────────────────────────────────────
    n_aprobados  = len(ap_periodo)
    n_enviados   = len(en_periodo)
    n_entregados = len(et_periodo)
    monto_entregado = round(sum(r["total"] for r in et_periodo), 2)

    n_con_faltante    = sum(1 for r in et_periodo if r["faltante"])
    pct_faltante      = round(n_con_faltante / n_entregados, 4) if n_entregados else 0.0
    pct_empacado_prom = round(sum(r["empacado"] for r in et_periodo) / n_entregados, 1) if n_entregados else 0.0
    n_sin_fecha       = sum(1 for r in et_periodo if not r["fecha_envio"] or not r["fecha_entrega"])

    # ── Lead times (solo entregados, requieren ambas fechas) ──────────────────
    leads_ap_en = []
    leads_en_et = []
    leads_ciclo = []

    for r in et_periodo:
        if r["fecha_aprob"] and r["fecha_envio"]:
            d = days_diff(r["fecha_aprob"], r["fecha_envio"])
            if d is not None:
                leads_ap_en.append(d)
        if r["fecha_envio"] and r["fecha_entrega"]:
            d = days_diff(r["fecha_envio"], r["fecha_entrega"])
            if d is not None:
                leads_en_et.append(d)
        if r["fecha_aprob"] and r["fecha_entrega"]:
            d = days_diff(r["fecha_aprob"], r["fecha_entrega"])
            if d is not None:
                leads_ciclo.append(d)

    n_con_lead       = len(leads_ciclo)
    ciclo_prom       = round(avg(leads_ciclo), 1)  if leads_ciclo else 0.0
    ciclo_med        = round(med(leads_ciclo), 1)  if leads_ciclo else 0.0
    lead_ap_en_prom  = round(avg(leads_ap_en), 1)  if leads_ap_en  else 0.0
    lead_ap_en_med   = round(med(leads_ap_en), 1)  if leads_ap_en  else 0.0
    lead_en_et_prom  = round(avg(leads_en_et), 1)  if leads_en_et  else 0.0
    lead_en_et_med   = round(med(leads_en_et), 1)  if leads_en_et  else 0.0

    # ── Seguimiento de incompletos ────────────────────────────────────────────
    pendientes  = [r for r in seg_norm if (r["estado"] or "").lower() != "completado"]
    completados = [r for r in seg_norm if (r["estado"] or "").lower() == "completado"]
    n_pend = len(pendientes)

    # ── series.estado (distribucion de estado_pedido en aprobados) ────────────
    estado_data = defaultdict(int)
    for r in ap_norm:
        estado_data[r["estado"] or "Sin estado"] += 1
    series_estado = [
        {"estado": k, "n": v}
        for k, v in sorted(estado_data.items(), key=lambda x: -x[1])
    ]

    # ── series.tipo_envio (Local vs Foraneo en entregados) ───────────────────
    tipo_data = defaultdict(lambda: {"n": 0, "m": 0.0, "ciclos": []})
    for r in et_periodo:
        t = r["tipo_envio"]
        tipo_data[t]["n"] += 1
        tipo_data[t]["m"] += r["total"]
        if r["fecha_aprob"] and r["fecha_entrega"]:
            d = days_diff(r["fecha_aprob"], r["fecha_entrega"])
            if d is not None:
                tipo_data[t]["ciclos"].append(d)
    series_tipo_envio = [
        {
            "tipo":       k,
            "n":          v["n"],
            "m":          round(v["m"], 2),
            "ciclo_med":  round(med(v["ciclos"]), 1) if v["ciclos"] else None,
            "ciclo_prom": round(avg(v["ciclos"]), 1) if v["ciclos"] else None,
        }
        for k, v in sorted(tipo_data.items(), key=lambda x: -x[1]["m"])
    ]

    # ── Serie temporal (por fecha_entrega) ────────────────────────────────────
    def _fg_et(row):
        return row["fecha_entrega"].isoformat() if row["fecha_entrega"] else ""

    temporal = aggregate_temporal(
        et_periodo,
        date_getter=_fg_et,
        metric_getters={
            "entregados":    lambda row: 1,
            "monto":         lambda row: row["total"],
            "monto_local":   lambda row: row["total"] if row["tipo_envio"] == "Local"   else 0,
            "monto_foraneo": lambda row: row["total"] if row["tipo_envio"] == "Foraneo" else 0,
        },
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )
    periods = temporal["periodos"]
    temporal["tendencias"] = {
        "entregados": linear_trend([p["entregados"] for p in periods]),
        "monto":      linear_trend([p["monto"]      for p in periods]),
    }

    # ── Tables ────────────────────────────────────────────────────────────────
    cli_data = defaultdict(lambda: {"n": 0, "m": 0.0})
    for r in et_periodo:
        c = r["cliente"]
        cli_data[c]["n"] += 1
        cli_data[c]["m"] += r["total"]
    top_clientes = [
        {"cliente": k, "n": v["n"], "m": round(v["m"], 2)}
        for k, v in sorted(cli_data.items(), key=lambda x: -x[1]["m"])[:10]
    ]

    # Pedidos lentos: ciclo > mediana×2 (minimo 14 dias)
    umbral_lento = max(ciclo_med * 2, 14.0) if ciclo_med > 0 else 14.0
    pedidos_lentos = []
    for r in et_periodo:
        if r["fecha_aprob"] and r["fecha_entrega"]:
            d = days_diff(r["fecha_aprob"], r["fecha_entrega"])
            if d is not None and d >= umbral_lento:
                pedidos_lentos.append({
                    "nombre":        r["nombre"],
                    "cliente":       r["cliente"],
                    "tipo_envio":    r["tipo_envio"],
                    "total":         r["total"],
                    "ciclo_dias":    d,
                    "fecha_entrega": r["fecha_entrega"].date().isoformat() if r["fecha_entrega"] else "",
                })
    pedidos_lentos = sorted(pedidos_lentos, key=lambda x: -x["ciclo_dias"])[:20]

    def _iso(dt):
        return dt.date().isoformat() if dt else ""

    tabla_incompletos = [
        {
            "nombre":              r["nombre"],
            "cliente":             r["cliente"],
            "estado":              r["estado"],
            "motivo":              r["motivo"],
            "prioridad":           r["prioridad"],
            "productos_faltantes": r["productos_faltantes"],
            "fecha_creacion":      _iso(r["fecha_creacion"]),
            "notas":               r["notas"],
        }
        for r in (pendientes + completados)
    ]

    # Histograma de ciclo total
    LEAD_BINS = [
        ("0–3 d",   0,  4),
        ("4–7 d",   4,  8),
        ("8–14 d",  8, 15),
        ("15–21 d", 15, 22),
        ("22–30 d", 22, 31),
        ("31+ d",   31, None),
    ]
    hist_counts = histog(leads_ciclo, LEAD_BINS)
    lead_hist = [{"rango": lbl, "n": hist_counts[lbl]} for lbl, _, _ in LEAD_BINS]

    # ── Senales ───────────────────────────────────────────────────────────────
    signals = []
    UMBRAL_DIAS_LENTO = 10

    if ciclo_med > UMBRAL_DIAS_LENTO and n_con_lead >= 3:
        signals.append(make_signal(
            "entrega_lenta", "atencion", "Tiempos de entrega elevados",
            f"La mediana del ciclo aprobacion→entrega es {ciclo_med:.0f} dias (umbral: {UMBRAL_DIAS_LENTO} dias).",
            period_label,
            {"ciclo_mediana": ciclo_med, "n_pedidos": n_con_lead, "umbral": UMBRAL_DIAS_LENTO},
            pedidos_lentos[:5],
            "Revisar pedidos lentos — pueden tener problemas de abastecimiento o logistica.",
        ))
    if n_pend:
        signals.append(make_signal(
            "incompletos_pendientes", "riesgo", "Pedidos incompletos sin resolver",
            f"{n_pend} pedido(s) entregado(s) con faltante pendiente de resolucion.",
            period_label,
            {"cantidad": n_pend},
            [{"nombre": r["nombre"], "cliente": r["cliente"], "motivo": r["motivo"]} for r in pendientes[:5]],
            "Completar la entrega o actualizar el estado en Notion.",
        ))
    if n_sin_fecha:
        signals.append(make_signal(
            "captura_fecha_incompleta", "info", "Pedidos sin fechas completas",
            f"{n_sin_fecha} pedido(s) entregado(s) sin fecha de envio o entrega — lead time incalculable.",
            period_label,
            {"cantidad": n_sin_fecha},
            [],
            "Capturar las fechas en Notion para completar el analisis de tiempos.",
        ))
    if pct_faltante > 0.5 and n_entregados >= 5:
        signals.append(make_signal(
            "pedido_con_faltante", "atencion", "Alto porcentaje de pedidos con faltante",
            f"{n_con_faltante} de {n_entregados} pedidos ({pct_faltante * 100:.0f}%) tienen faltante marcado.",
            period_label,
            {"pct_faltante": pct_faltante, "n_con_faltante": n_con_faltante},
            [],
            "Revisar gestion de inventario y proceso de preparacion.",
        ))

    return {
        "periodo": period_label,
        "kpis": {
            "n_aprobados":              n_aprobados,
            "n_enviados":               n_enviados,
            "n_entregados":             n_entregados,
            "monto_entregado":          monto_entregado,
            "n_con_faltante":           n_con_faltante,
            "pct_faltante":             pct_faltante,
            "pct_empacado_prom":        pct_empacado_prom,
            "lead_aprob_envio_prom":    lead_ap_en_prom,
            "lead_aprob_envio_med":     lead_ap_en_med,
            "lead_envio_entrega_prom":  lead_en_et_prom,
            "lead_envio_entrega_med":   lead_en_et_med,
            "ciclo_total_prom":         ciclo_prom,
            "ciclo_total_med":          ciclo_med,
            "n_con_lead":               n_con_lead,
            "n_incompletos_pendientes": n_pend,
            "n_incompletos_total":      len(seg_norm),
            "n_sin_fecha":              n_sin_fecha,
            "senales":                  len(signals),
        },
        "series": {
            "temporal":   temporal,
            "estado":     series_estado,
            "tipo_envio": series_tipo_envio,
            "lead_hist":  lead_hist,
        },
        "tables": {
            "top_clientes":   top_clientes,
            "pedidos_lentos": pedidos_lentos,
            "incompletos":    tabla_incompletos,
        },
        "signals": signals,
    }


# ─── Modulo Inventario ───────────────────────────────────────────────────────

def _margen_linea_ventas(row, pfx="Partidas_facturas_ventas_"):
    """Margen bruto de una fila de partidas ventas.

    subtotal == costo_unitario_v * cantidad_solicitada (100 % verificado).
    Margen = venta - costo_compra * cantidad.
    Devuelve (venta, costo_compra, margen).  Costo puede ser 0 (dato faltante).
    """
    sol  = f(row.get(pfx + "cantidad_solicitada"))
    sub  = f(row.get(pfx + "subtotal"))
    cc   = f(row.get(pfx + "costo_unitario_de_compra_formula"))
    costo = cc * sol
    return sub, costo, sub - costo


def build_inventario_dashboard(inventario_rows, ventas_rows,
                               period_label="Periodo actual",
                               fecha_desde=None, fecha_hasta=None,
                               cotizaciones=None):
    """Tab Inventario: valor de stock + % inmovilizado + margen bruto por periodo.

    inventario_rows: filas de Crecimineto_inventario_*.csv
                     tipos: 'Inventario' (total) y 'Productos sin movimiento'.
    ventas_rows:     filas de Partidas_facturas_ventas_*.csv
                     Surtido de ventas con costo_unitario_de_compra_formula.
    """
    _s = parse_date(fecha_desde)
    _e = parse_date(fecha_hasta)
    start_d = _s.date() if _s else None
    end_d   = _e.date() if _e else None

    def in_period(dt):
        if not dt: return False
        d = dt.date()
        return (not start_d or d >= start_d) and (not end_d or d <= end_d)

    signals = []
    PFX = "Crecimineto_inventario_"
    VFX = "Partidas_facturas_ventas_"

    # ── Inventario snapshot: agrupa por nombre de snapshot (mes) ─────────────
    snap_por_mes = defaultdict(lambda: {"total": 0.0, "sin_mov": 0.0})
    for row in inventario_rows:
        nombre = (row.get(PFX + "name") or "").strip()
        tipo   = (row.get(PFX + "tipo") or "").strip()
        monto  = f(row.get(PFX + "monto"))
        if tipo == "Inventario":
            snap_por_mes[nombre]["total"] = monto
        elif tipo == "Productos sin movimiento":
            snap_por_mes[nombre]["sin_mov"] = monto

    # Snapshot mas reciente (alphabetically por nombre — "Inventario Mayo - 2026" etc.)
    ultimo_snap = {}
    if snap_por_mes:
        ultimo_nombre = sorted(snap_por_mes.keys())[-1]
        d = snap_por_mes[ultimo_nombre]
        pct_inmov = d["sin_mov"] / d["total"] if d["total"] else 0.0
        ultimo_snap = {
            "nombre":    ultimo_nombre,
            "total":     d["total"],
            "sin_mov":   d["sin_mov"],
            "activo":    d["total"] - d["sin_mov"],
            "pct_inmov": pct_inmov,
        }

    # Tendencia mensual de inventario (todos los snapshots)
    series_inv = sorted([
        {
            "key":     nombre,
            "total":   v["total"],
            "sin_mov": v["sin_mov"],
            "activo":  v["total"] - v["sin_mov"],
        }
        for nombre, v in snap_por_mes.items()
    ], key=lambda x: x["key"])

    if ultimo_snap.get("pct_inmov", 0) > 0.30:
        signals.append(make_signal(
            "inventario_alto_inmovilizado", "atencion",
            "Inventario inmovilizado elevado",
            f"El {ultimo_snap['pct_inmov']*100:.1f}% del inventario no tuvo movimiento en el periodo.",
            period_label,
            {"pct_inmov": ultimo_snap["pct_inmov"],
             "sin_mov": ultimo_snap["sin_mov"],
             "total": ultimo_snap["total"]},
            accion="Revisar productos sin movimiento y considerar liquidacion o devolucion.",
        ))

    # ── Margen bruto: partidas de ventas ─────────────────────────────────────
    def _norm_vta(row):
        fecha = parse_date(row.get(VFX + "fecha_de_creaci_n"))
        sol   = f(row.get(VFX + "cantidad_solicitada"))
        sub, costo, margen = _margen_linea_ventas(row, VFX)
        cc    = f(row.get(VFX + "costo_unitario_de_compra_formula"))
        return {
            "fecha":       fecha,
            "sku":         (row.get(VFX + "producto_sku") or "").strip(),
            "descripcion": (row.get(VFX + "categoria_de_ganancias") or "").strip(),
            "cotizacion":  (row.get(VFX + "cotizaciones_a_clientes.0") or "").strip(),
            "estado":      (row.get(VFX + "estado") or "").strip(),
            "cantidad":    sol,
            "subtotal":    sub,
            "costo_cc":    costo,
            "margen":      margen,
            "cc_unitario": cc,
        }

    vtas_norm = [_norm_vta(r) for r in ventas_rows]
    periodo_vtas = [v for v in vtas_norm if in_period(v["fecha"])]

    venta_total  = sum(v["subtotal"] for v in periodo_vtas)
    costo_total  = sum(v["costo_cc"] for v in periodo_vtas)
    margen_total = sum(v["margen"]   for v in periodo_vtas)
    pct_margen   = margen_total / venta_total if venta_total else 0.0

    # Alertas de calidad de datos
    sin_costo = [v for v in periodo_vtas if v["cc_unitario"] == 0.0 and v["subtotal"] > 0]
    margen_neg = [v for v in periodo_vtas if v["margen"] < 0]
    if sin_costo:
        skus = sorted(set(v["sku"] for v in sin_costo))
        signals.append(make_signal(
            "costo_compra_cero", "atencion",
            "Partidas sin costo de compra",
            f"SKU(s) con costo de compra = $0: {', '.join(skus[:5])}. El margen calculado no es confiable.",
            period_label,
            {"n": len(sin_costo), "skus": skus},
            accion="Capturar costo de compra en Notion para estos productos.",
        ))
    if margen_neg:
        skus = sorted(set(v["sku"] for v in margen_neg))
        signals.append(make_signal(
            "margen_negativo", "riesgo",
            "Productos con margen negativo",
            f"Se vende por debajo del costo de compra: {', '.join(skus[:5])}.",
            period_label,
            {"n": len(margen_neg), "monto": sum(abs(v["margen"]) for v in margen_neg), "skus": skus},
            accion="Revisar precio de venta o costo de compra capturado.",
        ))

    # Top productos por margen (agrupado por SKU)
    por_sku = defaultdict(lambda: {"descripcion": "", "venta": 0.0, "costo": 0.0, "margen": 0.0, "n": 0})
    for v in periodo_vtas:
        d = por_sku[v["sku"]]
        if not d["descripcion"]:
            d["descripcion"] = v["descripcion"]
        d["venta"]  += v["subtotal"]
        d["costo"]  += v["costo_cc"]
        d["margen"] += v["margen"]
        d["n"]      += 1
    top_margen = sorted(
        [{"sku": k, **v, "pct": v["margen"]/v["venta"] if v["venta"] else 0.0} for k, v in por_sku.items()],
        key=lambda x: -x["margen"]
    )[:15]
    bottom_margen = sorted(
        [{"sku": k, **v, "pct": v["margen"]/v["venta"] if v["venta"] else 0.0} for k, v in por_sku.items()],
        key=lambda x: x["margen"]
    )[:10]

    # Lookup UUID → nombre de cotizacion
    _cot_nombre = {}
    if cotizaciones:
        for r in cotizaciones:
            cid = (r.get("Cotizacion_id") or "").strip()
            nom = (r.get("Cotizacion_nombre") or "").strip()
            if cid:
                _cot_nombre[cid] = nom or cid

    # Top pedidos por margen
    por_cot = defaultdict(lambda: {"venta": 0.0, "costo": 0.0, "margen": 0.0, "n": 0})
    for v in periodo_vtas:
        d = por_cot[v["cotizacion"]]
        d["venta"]  += v["subtotal"]
        d["costo"]  += v["costo_cc"]
        d["margen"] += v["margen"]
        d["n"]      += 1
    top_pedidos_margen = sorted(
        [{"cotizacion": _cot_nombre.get(k, k), **v, "pct": v["margen"]/v["venta"] if v["venta"] else 0.0}
         for k, v in por_cot.items()],
        key=lambda x: -x["margen"]
    )[:15]

    # Serie temporal de margen (por periodo del filtro)
    temporal_margen = aggregate_temporal(
        periodo_vtas,
        date_getter=lambda v: v["fecha"].isoformat() if v["fecha"] else "",
        metric_getters={
            "venta":  lambda v: v["subtotal"],
            "costo":  lambda v: v["costo_cc"],
            "margen": lambda v: v["margen"],
        },
        fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
    )
    periodos = temporal_margen["periodos"]
    temporal_margen["tendencias"] = {
        "margen": linear_trend([p["margen"] for p in periodos]),
        "venta":  linear_trend([p["venta"]  for p in periodos]),
    }

    return {
        "periodo": period_label,
        "kpis": {
            "inv_total":      ultimo_snap.get("total", 0.0),
            "inv_sin_mov":    ultimo_snap.get("sin_mov", 0.0),
            "inv_activo":     ultimo_snap.get("activo", 0.0),
            "pct_inmov":      ultimo_snap.get("pct_inmov", 0.0),
            "inv_nombre":     ultimo_snap.get("nombre", ""),
            "n_snapshots":    len(snap_por_mes),
            "venta_total":    venta_total,
            "costo_total":    costo_total,
            "margen_total":   margen_total,
            "pct_margen":     pct_margen,
            "n_sin_costo":    len(sin_costo),
            "n_margen_neg":   len(margen_neg),
            "n_partidas":     len(periodo_vtas),
            "senales":        len(signals),
        },
        "series": {
            "inventario_mensual": series_inv,
            "temporal_margen":    temporal_margen,
        },
        "tables": {
            "top_margen":         top_margen,
            "bottom_margen":      bottom_margen,
            "top_pedidos_margen": top_pedidos_margen,
        },
        "signals": signals,
    }


# ─── Modulo Almacen ──────────────────────────────────────────────────────────

def build_almacen_dashboard(compras_rows, ventas_rows,
                            period_label="Periodo actual",
                            fecha_desde=None, fecha_hasta=None,
                            cotizaciones=None,
                            facturas_compras=None):
    """Tab Almacen: surtido de ventas + recepcion de compras + validacion fisica.

    compras_rows: filas de Partidas_facturas_compras_*.csv
                  (partida_* cols — recepcion de proveedores).
    ventas_rows:  filas de Partidas_facturas_ventas_*.csv
                  (surtido / picking de pedidos de cliente).
    """
    _s = parse_date(fecha_desde)
    _e = parse_date(fecha_hasta)
    start_d = _s.date() if _s else None
    end_d   = _e.date() if _e else None

    def in_period(dt):
        if not dt: return False
        d = dt.date()
        return (not start_d or d >= start_d) and (not end_d or d <= end_d)

    signals = []
    VFX = "Partidas_facturas_ventas_"

    # Lookup UUID → nombre de cotizacion
    _cot_nombre = {}
    if cotizaciones:
        for r in cotizaciones:
            cid  = (r.get("Cotizacion_id") or "").strip()
            nom  = (r.get("Cotizacion_nombre") or "").strip()
            if cid:
                _cot_nombre[cid] = nom or cid

    # Lookup UUID → nombre de factura de compra
    _fc_nombre = {}
    if facturas_compras:
        for r in facturas_compras:
            fid  = (r.get("Factura_compra_id") or "").strip()
            nom  = (r.get("Factura_compra_nombre") or "").strip()
            if fid:
                _fc_nombre[fid] = nom or fid

    # ── Surtido de ventas ─────────────────────────────────────────────────────
    def _norm_vta(row):
        fecha   = parse_date(row.get(VFX + "fecha_de_creaci_n"))
        sku     = (row.get(VFX + "producto_sku") or "").strip()
        desc    = (row.get(VFX + "categoria_de_ganancias") or "").strip()
        estado  = (row.get(VFX + "estado") or "").strip()
        sol     = f(row.get(VFX + "cantidad_solicitada"))
        falt    = f(row.get(VFX + "cantidad_faltante"))
        sub     = f(row.get(VFX + "subtotal"))
        cot_id  = (row.get(VFX + "cotizaciones_a_clientes.0") or "").strip()
        return {
            "fecha": fecha, "sku": sku, "descripcion": desc,
            "estado": estado, "cantidad_solicitada": sol,
            "cantidad_faltante": falt, "subtotal": sub,
            "cotizacion": _cot_nombre.get(cot_id, cot_id),
        }

    vtas_norm = [_norm_vta(r) for r in ventas_rows]
    periodo_vtas = [v for v in vtas_norm if in_period(v["fecha"])]

    # KPIs de surtido
    n_total_vta  = len(periodo_vtas)
    n_empacado   = sum(1 for v in periodo_vtas if v["estado"] == "Empacado")
    n_pendiente  = sum(1 for v in periodo_vtas if v["estado"] == "Pendiente")
    n_faltante   = sum(1 for v in periodo_vtas if v["estado"] == "Faltante")
    sub_empacado = sum(v["subtotal"] for v in periodo_vtas if v["estado"] == "Empacado")
    sub_pendiente= sum(v["subtotal"] for v in periodo_vtas if v["estado"] == "Pendiente")
    sub_faltante = sum(v["subtotal"] for v in periodo_vtas if v["estado"] == "Faltante")
    sub_total_vta= sum(v["subtotal"] for v in periodo_vtas)

    pct_empacado = n_empacado / n_total_vta if n_total_vta else 0.0

    # Series de estado para dona
    SURTIDO_COLORS = ["#276f86", "#d0b56b", "#d96058"]
    series_surtido = [
        {"estado": "Empacado",  "n": n_empacado,  "monto": sub_empacado,  "color": SURTIDO_COLORS[0]},
        {"estado": "Pendiente", "n": n_pendiente, "monto": sub_pendiente, "color": SURTIDO_COLORS[1]},
        {"estado": "Faltante",  "n": n_faltante,  "monto": sub_faltante,  "color": SURTIDO_COLORS[2]},
    ]

    # Tabla de faltantes
    tabla_faltantes = sorted(
        [v for v in periodo_vtas if v["cantidad_faltante"] > 0],
        key=lambda x: -x["subtotal"]
    )[:30]

    if n_faltante > 0:
        signals.append(make_signal(
            "partidas_faltantes", "riesgo",
            "Partidas con material faltante",
            f"{n_faltante} partidas no se pudieron surtir por falta de material (${sub_faltante:,.0f}).",
            period_label,
            {"n": n_faltante, "monto": sub_faltante},
            accion="Revisar reposicion de inventario para los SKUs faltantes.",
        ))

    # Serie temporal de surtido
    temporal_surtido = aggregate_temporal(
        periodo_vtas,
        date_getter=lambda v: v["fecha"].isoformat() if v["fecha"] else "",
        metric_getters={
            "n_empacado":  lambda v: 1 if v["estado"] == "Empacado"  else 0,
            "n_pendiente": lambda v: 1 if v["estado"] == "Pendiente" else 0,
            "n_faltante":  lambda v: 1 if v["estado"] == "Faltante"  else 0,
            "monto":       lambda v: v["subtotal"],
        },
        fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
    )

    # ── Recepcion de compras ──────────────────────────────────────────────────
    def _norm_cmp(row):
        fecha    = parse_date(row.get("partida_fecha_creacion"))
        sku      = (row.get("partida_codigo_producto.0") or "").strip()
        sol      = f(row.get("partida_cantidad_solicitada"))
        raw_lleg = (row.get("partida_cantidad_llegada") or "").strip()
        lleg     = f(raw_lleg) if raw_lleg else None   # None = aun no llego
        fc_id    = (row.get("partida_cotizacion.0") or "").strip()  # Factura_compra_id UUID
        valida   = str(row.get("partida_validacion_fisica") or "").strip().upper() == "TRUE"
        return {
            "fecha": fecha, "sku": sku, "cantidad_solicitada": sol,
            "cantidad_llegada": lleg, "validada": valida,
            "factura_compra_id":     fc_id,
            "factura_compra_nombre": _fc_nombre.get(fc_id, fc_id),
        }

    cmp_norm = [_norm_cmp(r) for r in compras_rows]
    periodo_cmp = [c for c in cmp_norm if in_period(c["fecha"])]

    sol_total  = sum(c["cantidad_solicitada"] for c in periodo_cmp)
    cmp_con_llegada = [c for c in periodo_cmp if c["cantidad_llegada"] is not None]
    lleg_total = sum(c["cantidad_llegada"] for c in cmp_con_llegada)
    fill_rate  = lleg_total / sol_total if sol_total else 0.0

    n_pendientes_rcep = sum(1 for c in periodo_cmp if c["cantidad_llegada"] is None)
    n_parciales_rcep  = sum(1 for c in cmp_con_llegada
                            if c["cantidad_llegada"] < c["cantidad_solicitada"])
    n_completos_rcep  = sum(1 for c in cmp_con_llegada
                            if c["cantidad_llegada"] >= c["cantidad_solicitada"])

    # Fill rate por factura de compra
    por_fc = defaultdict(lambda: {"sol": 0.0, "lleg": 0.0, "n_part": 0, "n_pendiente": 0})
    for c in periodo_cmp:
        d = por_fc[c["factura_compra_id"]]
        d["sol"] += c["cantidad_solicitada"]
        d["n_part"] += 1
        if c["cantidad_llegada"] is not None:
            d["lleg"] += c["cantidad_llegada"]
        else:
            d["n_pendiente"] += 1
    fill_por_fc = sorted(
        [
            {"fc_id": k[:8], "sol": v["sol"], "lleg": v["lleg"],
             "n_part": v["n_part"], "n_pendiente": v["n_pendiente"],
             "pct": v["lleg"] / v["sol"] if v["sol"] else 0.0}
            for k, v in por_fc.items()
        ],
        key=lambda x: x["pct"]
    )[:20]

    # Validacion fisica
    n_validadas = sum(1 for c in periodo_cmp if c["validada"])
    pct_validado = n_validadas / len(periodo_cmp) if periodo_cmp else 0.0

    if pct_validado < 0.5 and len(periodo_cmp) >= 5:
        signals.append(make_signal(
            "validacion_fisica_baja", "atencion",
            "Validacion fisica pendiente",
            f"Solo el {pct_validado*100:.1f}% de partidas recibidas han sido validadas fisicamente ({n_validadas}/{len(periodo_cmp)}).",
            period_label,
            {"pct_validado": pct_validado, "n_validadas": n_validadas, "n_total": len(periodo_cmp)},
            accion="Revisar proceso de validacion fisica en almacen.",
        ))

    # Partidas pendientes de recepcion (sin llegada)
    tabla_pendientes_rcep = sorted(
        [c for c in periodo_cmp if c["cantidad_llegada"] is None],
        key=lambda x: -x["cantidad_solicitada"]
    )[:20]

    RCEP_COLORS = ["#57c5b6", "#d0b56b", "#5b6673"]
    series_recepcion = [
        {"estado": "100% recibido", "n": n_completos_rcep,  "color": RCEP_COLORS[0]},
        {"estado": "Parcial",       "n": n_parciales_rcep,  "color": RCEP_COLORS[1]},
        {"estado": "Pendiente",     "n": n_pendientes_rcep, "color": RCEP_COLORS[2]},
    ]

    return {
        "periodo": period_label,
        "kpis": {
            "n_partidas_vta":   n_total_vta,
            "n_empacado":       n_empacado,
            "n_pendiente":      n_pendiente,
            "n_faltante":       n_faltante,
            "sub_empacado":     sub_empacado,
            "sub_pendiente":    sub_pendiente,
            "sub_faltante":     sub_faltante,
            "sub_total_vta":    sub_total_vta,
            "pct_empacado":     pct_empacado,
            "sol_total":        sol_total,
            "lleg_total":       lleg_total,
            "fill_rate":        fill_rate,
            "n_pendientes_rcep":n_pendientes_rcep,
            "n_parciales_rcep": n_parciales_rcep,
            "n_completos_rcep": n_completos_rcep,
            "n_validadas":      n_validadas,
            "pct_validado":     pct_validado,
            "n_partidas_cmp":   len(periodo_cmp),
            "senales":          len(signals),
        },
        "series": {
            "surtido":      series_surtido,
            "recepcion":    series_recepcion,
            "temporal":     temporal_surtido,
            "fill_por_fc":  fill_por_fc,
        },
        "tables": {
            "faltantes":          tabla_faltantes,
            "pendientes_rcep":    tabla_pendientes_rcep,
        },
        "signals": signals,
    }


def build_finanzas_dashboard(
    facturacion, cobranza, compras, pagos_proveedores, gastos_operativos,
    period_label="Periodo actual", fecha_desde=None, fecha_hasta=None,
):
    """Consolida los 5 sub-dashboards en una vista de ingresos vs egresos.

    Recibe dicts ya construidos (no rows). Cualquier sub-dashboard puede ser {}
    o None si su CSV no estaba disponible — se trata su aporte como 0.
    NO lee CSVs, NO re-filtra por fecha; toda cifra deriva de los sub-dashboards.

    Dos bases paralelas:
    - DEVENGADO:  ingreso = facturacion,  egreso = compras + gastos.
    - CAJA:       ingreso = cobranza,     egreso = pagos_proveedores + gastos.
    Gastos Operativos suma en AMBAS bases (desembolso generalmente inmediato).
    NUNCA se suman compras + pagos juntos — miden el mismo egreso en momentos distintos.

    IVA trasladado se deriva de lo COBRADO (base caja):
        iva_trasladado = ingreso_caja − ingreso_caja / 1.16
    """
    fac = facturacion or {}
    cob = cobranza or {}
    com = compras or {}
    pag = pagos_proveedores or {}
    gas = gastos_operativos or {}

    fac_kpis = fac.get("kpis") or {}
    cob_kpis = cob.get("kpis") or {}
    com_kpis = com.get("kpis") or {}
    pag_kpis = pag.get("kpis") or {}
    gas_kpis = gas.get("kpis") or {}

    # ── KPIs escalares ────────────────────────────────────────────────────────
    ingreso_devengado  = float(fac_kpis.get("monto_facturado_vigente") or 0)
    egreso_dev_compras = float(com_kpis.get("tot_fc") or 0)
    egreso_dev_gastos  = float(gas_kpis.get("total_total") or 0)
    egreso_devengado   = round(egreso_dev_compras + egreso_dev_gastos, 2)
    utilidad_devengada = round(ingreso_devengado - egreso_devengado, 2)
    margen_devengado   = round(utilidad_devengada / ingreso_devengado, 4) if ingreso_devengado else 0.0

    ingreso_caja      = float(cob_kpis.get("monto_cobrado_total") or 0)
    egreso_caja_pagos = float(pag_kpis.get("monto_total") or 0)
    egreso_caja_gastos = egreso_dev_gastos  # gastos = desembolso inmediato, mismo valor
    egreso_caja       = round(egreso_caja_pagos + egreso_caja_gastos, 2)
    flujo_caja_neto   = round(ingreso_caja - egreso_caja, 2)
    margen_caja       = round(flujo_caja_neto / ingreso_caja, 4) if ingreso_caja else 0.0

    pendiente_cobro   = float(cob_kpis.get("monto_pendiente_cobro") or 0)
    n_pendientes_cobro = int(cob_kpis.get("n_pendientes_cobro") or 0)
    pendiente_pago    = int(pag_kpis.get("n_pendientes") or 0)

    # IVA trasladado: derivado de lo cobrado — ingreso_caja incluye IVA
    # iva_trasladado = cobrado - cobrado/1.16  (i.e. la parte que es IVA)
    iva_trasladado  = round(ingreso_caja - ingreso_caja / 1.16, 2) if ingreso_caja else 0.0
    iva_acreditable = round(
        float(com_kpis.get("iva_fc") or 0) + float(gas_kpis.get("iva_acreditable") or 0), 2
    )
    iva_por_pagar = round(iva_trasladado - iva_acreditable, 2)

    # Senales consolidadas (los 4 modulos que exponen lista signals)
    all_signals = []
    for sub in [fac, cob, pag, gas]:
        all_signals.extend(sub.get("signals") or [])

    # ── Series temporales consolidadas ────────────────────────────────────────
    def _temporal(sub):
        return (sub.get("series") or {}).get("temporal") or {}

    def _by_key(temporal):
        return {p["key"]: p for p in (temporal.get("periodos") or [])}

    # Eje de referencia: primer sub-dashboard que tenga series temporales
    ref_temporal = None
    for sub in [fac, cob, com, pag, gas]:
        t = _temporal(sub)
        if t.get("keys"):
            ref_temporal = t
            break

    if ref_temporal:
        fac_bk = _by_key(_temporal(fac))
        cob_bk = _by_key(_temporal(cob))
        com_bk = _by_key(_temporal(com))
        pag_bk = _by_key(_temporal(pag))
        gas_bk = _by_key(_temporal(gas))

        periodos_consolidados = []
        for key, label in zip(ref_temporal["keys"], ref_temporal["labels"]):
            fac_p = fac_bk.get(key) or {}
            cob_p = cob_bk.get(key) or {}
            com_p = com_bk.get(key) or {}
            pag_p = pag_bk.get(key) or {}
            gas_p = gas_bk.get(key) or {}

            i_dev   = float(fac_p.get("monto") or 0)
            e_dev_c = float(com_p.get("tot") or 0)
            e_dev_g = float(gas_p.get("monto") or 0)
            e_dev   = round(e_dev_c + e_dev_g, 2)
            u_dev   = round(i_dev - e_dev, 2)

            i_caja  = float(cob_p.get("monto") or 0)
            e_pag   = float(pag_p.get("monto") or 0)
            e_caja  = round(e_pag + e_dev_g, 2)
            f_caja  = round(i_caja - e_caja, 2)

            periodos_consolidados.append({
                "key": key,
                "etiqueta": label,
                "ingreso_dev": i_dev,
                "egreso_dev": e_dev,
                "utilidad_dev": u_dev,
                "ingreso_caja": i_caja,
                "egreso_caja": e_caja,
                "flujo_caja": f_caja,
            })

        util_vals = [p["utilidad_dev"] for p in periodos_consolidados]
        caja_vals = [p["flujo_caja"]    for p in periodos_consolidados]
        tendencias = {
            "utilidad_dev": linear_trend(util_vals),
            "flujo_caja":   linear_trend(caja_vals),
        }
        temporal = {
            "granularidad":   ref_temporal.get("granularidad"),
            "keys":           ref_temporal["keys"],
            "labels":         ref_temporal["labels"],
            "table_heading":  ref_temporal.get("table_heading"),
            "behavior_title": ref_temporal.get("behavior_title"),
            "chart_suffix":   ref_temporal.get("chart_suffix"),
            "hint":           ref_temporal.get("hint"),
            "periodos":       periodos_consolidados,
            "tendencias":     tendencias,
        }
    else:
        temporal = {}

    # ── Tablas ────────────────────────────────────────────────────────────────
    comparativo = [
        {"concepto": "Ingreso",   "devengado": round(ingreso_devengado, 2),  "caja": round(ingreso_caja, 2)},
        {"concepto": "Egreso",    "devengado": egreso_devengado,              "caja": egreso_caja},
        {"concepto": "Resultado", "devengado": utilidad_devengada,            "caja": flujo_caja_neto},
    ]
    waterfall_devengado = [
        {"concepto": "Facturacion", "monto": round(ingreso_devengado, 2),   "tipo": "ingreso"},
        {"concepto": "Compras",     "monto": round(-egreso_dev_compras, 2), "tipo": "egreso"},
        {"concepto": "Gastos op.",  "monto": round(-egreso_dev_gastos, 2),  "tipo": "egreso"},
        {"concepto": "Utilidad",    "monto": utilidad_devengada,            "tipo": "total"},
    ]
    waterfall_caja = [
        {"concepto": "Cobranza",    "monto": round(ingreso_caja, 2),        "tipo": "ingreso"},
        {"concepto": "Pagos prov.", "monto": round(-egreso_caja_pagos, 2),  "tipo": "egreso"},
        {"concepto": "Gastos op.",  "monto": round(-egreso_caja_gastos, 2), "tipo": "egreso"},
        {"concepto": "Flujo neto",  "monto": flujo_caja_neto,               "tipo": "total"},
    ]
    iva_split = [
        {"tipo": "Trasladado",  "m": iva_trasladado},
        {"tipo": "Acreditable", "m": iva_acreditable},
        {"tipo": "Por pagar",   "m": iva_por_pagar},
    ]

    return {
        "periodo": period_label,
        "kpis": {
            "ingreso_devengado":        round(ingreso_devengado, 2),
            "egreso_devengado":         egreso_devengado,
            "egreso_devengado_compras": round(egreso_dev_compras, 2),
            "egreso_devengado_gastos":  round(egreso_dev_gastos, 2),
            "utilidad_devengada":       utilidad_devengada,
            "margen_devengado":         margen_devengado,
            "ingreso_caja":             round(ingreso_caja, 2),
            "egreso_caja":              egreso_caja,
            "egreso_caja_pagos":        round(egreso_caja_pagos, 2),
            "egreso_caja_gastos":       round(egreso_caja_gastos, 2),
            "flujo_caja_neto":          flujo_caja_neto,
            "margen_caja":              margen_caja,
            "pendiente_cobro":          round(pendiente_cobro, 2),
            "n_pendientes_cobro":       n_pendientes_cobro,
            "pendiente_pago":           pendiente_pago,
            "iva_trasladado":           iva_trasladado,
            "iva_acreditable":          iva_acreditable,
            "iva_por_pagar":            iva_por_pagar,
            "n_signals":                len(all_signals),
        },
        "series": {
            "temporal": temporal,
        },
        "tables": {
            "comparativo":         comparativo,
            "waterfall_devengado": waterfall_devengado,
            "waterfall_caja":      waterfall_caja,
            "iva_split":           iva_split,
        },
        "signals": all_signals,
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

# ─── Analisis ───────────────────────────────────────────────────────────────
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

    # Tiempos preparacion
    t_prep=[f(r["dias_preparacion"]) for r in ped if r.get("dias_preparacion","").strip()]
    prep_bins=[("0-1 dias",0,2),("2-3 dias",2,4),("4-7 dias",4,8),("8-14 dias",8,15),(">14 dias",15,None)]
    rangos_prep=histog(t_prep, prep_bins)

    # Tiempos entrega
    t_ent=[f(r["dias_entrega"]) for r in ped if r.get("dias_entrega","").strip()]
    ent_bins=[("Mismo dia",0,1),("1-2 dias",1,3),("3-5 dias",3,6),("6-10 dias",6,11),(">10 dias",11,None)]
    rangos_ent=histog(t_ent, ent_bins)
    n_ent_2=sum(1 for v in t_ent if v<=2)
    n_ent_5=sum(1 for v in t_ent if v<=5)
    n_ent_7=sum(1 for v in t_ent if v<=7)

    # Ciclo de facturacion (desde PEDIDOS_CLIENTES)
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
    pago_bins=[("0-15 dias",0,16),("16-30 dias",16,31),("31-60 dias",31,61),("61-90 dias",61,91),(">90 dias",91,None)]
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

    # Credito vivo (no pagadas)
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

    # Dias factura→pago para compras
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
        mp=(r.get("property_m_todo_de_pago","") or "Sin metodo").strip() or "Sin metodo"
        mp_gas[mp]["n"]+=1; mp_gas[mp]["m"]+=f(r["property_total"])

    cat_gas=defaultdict(lambda:{"n":0,"m":0.0})
    for r in gas_real:
        cat=(r.get("property_categor_a","") or "Sin categoria").strip() or "Sin categoria"
        cat_gas[cat]["n"]+=1; cat_gas[cat]["m"]+=f(r["property_total"])

    # Identificar carga fiscal dentro de "Otros" / sin categoria
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
