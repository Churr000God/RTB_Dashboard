#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RTB — Generador de reportes mensuales.

Uso:
  python3 generar_reporte.py
  python3 generar_reporte.py --data-dir data
  python3 generar_reporte.py --start 2026-04-01 --end 2026-04-30

Genera los archivos dentro de:
  reportes/YYYY-MM-DD_a_YYYY-MM-DD_HH-MM/

Después de generar el reporte, mueve los CSV procesados a:
  data_procesada/YYYY-MM-DD_HH-MM/
"""

import argparse
import calendar
import os
import re
import shutil
import sys
from datetime import datetime

from rtb_analisis import load_all, compute, parse_date
from rtb_markdown import render as render_md
from rtb_html import render as render_html

BASE = os.path.dirname(os.path.abspath(__file__))

MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

MONTH_LABELS = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}

DATE_FIELDS = (
    "property_fecha_de_creaci_n",
    "fecha_pedido",
    "fecha_facturacion",
    "property_fecha_de_factura.start",
    "property_fecha_de_pago",
    "property_fecha.start",
)


def mxn(v):
    return f"${v:,.2f}"


def parse_cli_date(value, label):
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise SystemExit(f"[ERROR] {label} debe venir en formato YYYY-MM-DD: {value}")


def format_period(start, end):
    same_month = start.year == end.year and start.month == end.month
    if same_month:
        label = f"{MONTH_LABELS[start.month].capitalize()} {start.year}"
        range_label = f"{start.day} – {end.day} de {MONTH_LABELS[start.month]}, {start.year}"
    else:
        label = f"{start.date()} a {end.date()}"
        range_label = f"{start.day} de {MONTH_LABELS[start.month]} {start.year} – {end.day} de {MONTH_LABELS[end.month]} {end.year}"
    slug = f"{start:%Y-%m-%d}_a_{end:%Y-%m-%d}"
    return {
        "start": start.strftime("%Y-%m-%d"),
        "end": end.strftime("%Y-%m-%d"),
        "label": label,
        "range_label": range_label,
        "month_label": MONTH_LABELS[start.month],
        "next_month_label": MONTH_LABELS[1 if start.month == 12 else start.month + 1],
        "slug": slug,
    }


def detect_export_date(files):
    dates = []
    for path in files.values():
        match = re.search(r"(20\d{2}-\d{2}-\d{2})", os.path.basename(path))
        if match:
            dates.append(match.group(1))
    if not dates:
        return "fecha no detectada"
    return max(dates)


def detect_period_from_filenames(files):
    found = []
    for path in files.values():
        name = os.path.basename(path).lower()
        year_match = re.search(r"(20\d{2})", name)
        if not year_match:
            continue
        for month_name, month_num in MONTHS.items():
            if month_name in name:
                found.append((int(year_match.group(1)), month_num))
                break
    if not found:
        return None
    year, month = max(set(found), key=found.count)
    start = datetime(year, month, 1)
    end = datetime(year, month, calendar.monthrange(year, month)[1])
    return start, end


def detect_period_from_rows(D):
    dates = []
    for key, rows in D.items():
        if key.startswith("_") or not isinstance(rows, list):
            continue
        for row in rows:
            for field in DATE_FIELDS:
                dt = parse_date(row.get(field, ""))
                if dt:
                    dates.append(dt)
    if not dates:
        raise SystemExit("[ERROR] No pude detectar fechas en los CSVs. Usa --start YYYY-MM-DD --end YYYY-MM-DD.")
    return min(dates), max(dates)


def unique_destination(path):
    if not os.path.exists(path):
        return path

    folder, name = os.path.split(path)
    base, ext = os.path.splitext(name)
    counter = 1
    while True:
        candidate = os.path.join(folder, f"{base}_{counter}{ext}")
        if not os.path.exists(candidate):
            return candidate
        counter += 1


def move_processed_files(data_dir, loaded_files, processed_base):
    process_date = datetime.now().strftime("%Y-%m-%d_%H-%M")
    processed_dir = os.path.join(os.path.abspath(processed_base), process_date)
    os.makedirs(processed_dir, exist_ok=True)

    moved = []
    seen = set()
    csv_files = [
        os.path.join(os.path.abspath(data_dir), name)
        for name in os.listdir(data_dir)
        if name.lower().endswith(".csv")
    ]
    paths = list(loaded_files.values()) + sorted(csv_files)

    for path in paths:
        source = os.path.abspath(path)
        if source in seen or not os.path.exists(source):
            continue
        seen.add(source)

        destination = unique_destination(os.path.join(processed_dir, os.path.basename(source)))
        shutil.move(source, destination)
        moved.append(destination)

    return processed_dir, moved


def resolve_period(D, start_arg=None, end_arg=None):
    if start_arg or end_arg:
        if not start_arg or not end_arg:
            raise SystemExit("[ERROR] Usa --start y --end juntos.")
        start = parse_cli_date(start_arg, "--start")
        end = parse_cli_date(end_arg, "--end")
        if end < start:
            raise SystemExit("[ERROR] --end no puede ser menor que --start.")
    else:
        detected = detect_period_from_filenames(D.get("_files", {}))
        start, end = detected if detected else detect_period_from_rows(D)

    period = format_period(start, end)
    period["export_date"] = detect_export_date(D.get("_files", {}))
    return period


def parse_args():
    parser = argparse.ArgumentParser(description="Genera el reporte mensual RTB desde CSVs en data/.")
    parser.add_argument("--data-dir", default=os.path.join(BASE, "data"), help="Carpeta con CSVs exportados de Notion. Default: ./data")
    parser.add_argument("--out-dir", default=os.path.join(BASE, "reportes"), help="Carpeta base para reportes. Default: ./reportes")
    parser.add_argument("--processed-dir", default=os.path.join(BASE, "data_procesada"), help="Carpeta base para archivar CSVs procesados. Default: ./data_procesada")
    parser.add_argument("--start", help="Fecha inicial del reporte en formato YYYY-MM-DD.")
    parser.add_argument("--end", help="Fecha final del reporte en formato YYYY-MM-DD.")
    return parser.parse_args()


def main():
    args = parse_args()

    print("=" * 60)
    print("  RTB — Generador de Reportes")
    print("=" * 60)
    print()

    print("[1/5] Cargando datos...")
    try:
        D = load_all(args.data_dir)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        print("Coloca los CSVs exportados de Notion en la carpeta data/ o usa --data-dir.")
        return 1

    period = resolve_period(D, args.start, args.end)
    print(f"      Periodo: {period['range_label']}")
    print(f"      Datos:   {os.path.abspath(args.data_dir)}")
    for warning in D.get("_warnings", []):
        print(f"      ADVERTENCIA: {warning}")

    print("[2/5] Computando métricas...")
    try:
        R = compute(D, period=period)
        R["period"] = period
    except Exception as e:
        print(f"[ERROR] Al computar métricas: {e}")
        raise

    h = R.get("hero", {})
    m1 = R.get("m1", {})
    m2a = R.get("m2a", {})
    m2b = R.get("m2b", {})
    m2c = R.get("m2c", {})
    m5 = R.get("m5", {})
    pl = R.get("pl", {})
    snaps = R.get("m4", {}).get("snaps", {})
    snap = snaps.get("Abril", {}) or {}

    print()
    print("── RESUMEN EJECUTIVO ────────────────────────────────────")
    print(f"  Periodo       : {period['range_label']}")
    print(f"  Cotizaciones  : {m1.get('n_cot', 0):>4}   Aprobadas: {m1.get('n_apr', 0)} ({m1.get('conv_q', 0):.1%})")
    print(f"  Monto cotizado: {mxn(m1.get('tot_cot', 0))}")
    print(f"  Monto aprobado: {mxn(m1.get('mon_apr', 0))}")
    print()
    print(f"  Pedidos       : {m2a.get('n_ped', 0):>4}   Entregados: {m2b.get('n_env', 0)}")
    print(f"  Subtotal ped  : {mxn(m2a.get('sub_ped', 0))}")
    print(f"  Facturado     : {mxn(m2c.get('tot_fac', 0))}")
    print()
    print(f"  Cobrado (sub) : {mxn(pl.get('ing_sub', 0))}")
    print(f"  Compras (sub) : {mxn(pl.get('comp_sub', 0))}")
    print(f"  Margen bruto  : {mxn(pl.get('margen', 0))}")
    print(f"  OPEX          : {mxn(pl.get('opex_sub', 0))}")
    print(f"  Utilidad teór.: {mxn(pl.get('utilidad', 0))}")
    print(f"  Flujo neto    : {mxn(pl.get('flujo_neto', 0))}")
    print()
    if snap.get("total"):
        print(f"  Inventario    : {mxn(snap.get('total', 0))}")
        print(f"  Inmovilizado  : {mxn(snap.get('inmov', 0))}  ({snap.get('pct_inmov', 0):.1%} del total)")
    else:
        print("  Inventario    : n/d")
    print(f"  OPEX total    : {mxn(m5.get('tot_gas', 0))}  (carga fiscal: {mxn(m5.get('tot_fiscal', 0))})")
    for warning in R.get("warnings", []):
        print(f"  Advertencia   : {warning}")
    print("─" * 60)
    print()

    report_timestamp = datetime.now().strftime("%H-%M")
    report_slug = f"{period['slug']}_{report_timestamp}"
    report_dir = os.path.join(os.path.abspath(args.out_dir), report_slug)
    os.makedirs(report_dir, exist_ok=True)
    base_name = f"RTB_Cierre_{period['slug']}"

    print("[3/5] Generando Markdown...")
    try:
        md_text = render_md(R)
        md_path = os.path.join(report_dir, base_name + ".md")
        with open(md_path, "w", encoding="utf-8") as fh:
            fh.write(md_text)
        print(f"      ✓ {md_path}  ({len(md_text):,} chars)")
    except Exception as e:
        print(f"[ERROR] Al generar Markdown: {e}")
        raise

    print("[4/5] Generando HTML...")
    try:
        html_text = render_html(R)
        html_path = os.path.join(report_dir, base_name + ".html")
        with open(html_path, "w", encoding="utf-8") as fh:
            fh.write(html_text)
        print(f"      ✓ {html_path}  ({len(html_text):,} chars)")
    except Exception as e:
        print(f"[ERROR] Al generar HTML: {e}")
        raise

    print("[5/5] Archivando datos procesados...")
    try:
        processed_dir, moved_files = move_processed_files(args.data_dir, D.get("_files", {}), args.processed_dir)
        print(f"      ✓ {processed_dir}")
        print(f"      CSVs movidos: {len(moved_files)}")
    except Exception as e:
        print(f"[ERROR] Al mover datos procesados: {e}")
        raise

    print()
    print("=" * 60)
    print("  Reporte generado correctamente.")
    print("=" * 60)
    print()
    print("Archivos generados:")
    print(f"  • {md_path}")
    print(f"  • {html_path}")
    print()
    print("Datos procesados:")
    print(f"  • {processed_dir}")
    print()
    print("Abrir el dashboard:")
    print(f"  xdg-open {html_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
