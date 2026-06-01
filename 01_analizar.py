#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parte 1: Lee CSVs, computa todas las métricas y guarda en JSON."""

import csv, json, re, os
from datetime import datetime, date
from collections import defaultdict

DIR = "/home/dhguilleng/Proyectos/Generador_de_reportes/Abril_csv_2026/"
OUT = "/home/dhguilleng/Proyectos/Generador_de_reportes/"
ANIO = 2026
MES_NUM = 4

# ─── Utils ─────────────────────────────────────
def f(v):
    try:
        s = str(v).replace(",","").strip()
        return float(s) if s else 0.0
    except: return 0.0

def parse_date(s):
    if not s: return None
    s = str(s).strip()
    if s.startswith("{"):
        try:
            d = json.loads(s); s = d.get("start","") or ""
        except: return None
    s = re.sub(r'([+-]\d{2}:\d{2})$', '', s)
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f","%Y-%m-%dT%H:%M:%S","%Y-%m-%dT%H:%M","%Y-%m-%d"):
        try:
            return datetime.strptime(s[:26], fmt[:26])
        except: pass
    try: return datetime.strptime(s[:10], "%Y-%m-%d")
    except: return None

def read_csv(fname):
    with open(DIR + fname, newline='', encoding='utf-8-sig') as fh:
        return list(csv.DictReader(fh))

def semana(dt):
    """Devuelve S1-S5 dentro del mes de abril."""
    if not dt: return None
    d = dt.day
    if d <= 7: return "S1"
    if d <= 14: return "S2"
    if d <= 21: return "S3"
    if d <= 28: return "S4"
    return "S5"

def avg(lst): return sum(lst)/len(lst) if lst else 0
def med(lst):
    if not lst: return 0
    s = sorted(lst); n = len(s)
    return s[n//2] if n%2 else (s[n//2-1]+s[n//2])/2

def parse_pct(s):
    try: return float(str(s).replace("%","").strip())
    except: return 0

def parse_tipo_pago_json(s):
    """['3 Tranferencia'] -> '3 Tranferencia'"""
    s = (s or "").strip()
    if s.startswith("["):
        try:
            lst = json.loads(s)
            return lst[0] if lst else "Sin tipo"
        except: pass
    return s or "Sin tipo"

# ─── 1. Lectura ─────────────────────────────────
print("Leyendo CSVs...")
cot   = read_csv("COTIZACIONES_CLIENTES_Abril_Final_2026-05-23_14-43.csv")
crec  = read_csv("CRECIMIENTO_INVENTARIO_Abril_Final_2026-05-23_14-48.csv")
fc    = read_csv("FACTURAS_COMPRAS_Abril_Final_2026-05-23_14-46.csv")
fcp   = read_csv("FACTURAS_COMPRAS_PAGADAS_Abril_Final_2026-05-23_14-46.csv")
gas   = read_csv("GASTOS_OPERATIVOS_Abril_Final_2026-05-23_14-48.csv")
inv   = read_csv("INVENTARIO_REAL_ACTUAL_Abril_Final_2026-05-23_14-47.csv")
ms    = read_csv("MATERIALES_SALIDA_Abril_Final_2026-05-23_14-47.csv")
ped   = read_csv("PEDIDOS_CLIENTES_Abril_Final_2026-05-23_14-44.csv")
env   = read_csv("PEDIDOS_CLIENTES_ENVIADOS_Abril_Final_2026-05-23_14-45.csv")
fac   = read_csv("PEDIDOS_CLIENTES_FACTURADOS_Abril_Final_2026-05-23_14-45.csv")
facs  = read_csv("PEDIDOS_CLIENTES_FACTURADOS_SECUNDARIA_Abril_Final_2026-05-23_14-48.csv")
pag   = read_csv("PEDIDOS_CLIENTES_PAGADOS_Abril_Final_2026-05-23_14-46.csv")
pent  = read_csv("PRODUCTOS_ENTRADA_Abril_Final_2026-05-23_14-47.csv")
vap   = read_csv("VERIFICADOR_FECHAS_APROBACION_Abril_Final_2026-05-23_14-42.csv")
vnap  = read_csv("VERIFICADOR_FECHAS_NO_APROBACION_Abril_Final_2026-05-23_14-44.csv")

print(f"  Cotizaciones={len(cot)} | Pedidos={len(ped)} | Enviados={len(env)} | Facturados={len(fac)}+{len(facs)} | Pagados={len(pag)}")
print(f"  Compras={len(fc)} | CompPag={len(fcp)} | Gastos={len(gas)} | Inv={len(inv)} | Mov={len(ms)}/{len(pent)}")

R = {}  # resultado a guardar

# ─── 2. MÓDULO 1: COTIZACIONES ──────────────────
print("\nMod 1: Cotizaciones...")

# Stats globales
n_cot = len(cot)
sub_cot   = sum(f(r["property_subtotal_con_envio"]) for r in cot)
tot_cot   = sum(f(r["property_total"]) for r in cot)
n_apr     = sum(1 for r in cot if r["property_estado"].strip()=="Aprobada")
mon_apr   = sum(f(r["property_total"]) for r in cot if r["property_estado"].strip()=="Aprobada")
conv_q    = n_apr/n_cot if n_cot else 0
conv_m    = mon_apr/tot_cot if tot_cot else 0

# Por estado
est_cot = defaultdict(lambda: {"n":0,"m":0.0})
for r in cot:
    e = r["property_estado"].strip() or "Sin estado"
    est_cot[e]["n"] += 1
    est_cot[e]["m"] += f(r["property_total"])

# Por semana
sem_cot = {s: {"n":0,"m":0.0,"napr":0,"mapr":0.0} for s in ["S1","S2","S3","S4","S5"]}
for r in cot:
    d = parse_date(r["property_fecha_de_creaci_n"])
    s = semana(d)
    if not s: continue
    sem_cot[s]["n"] += 1
    sem_cot[s]["m"] += f(r["property_total"])
    if r["property_estado"].strip() == "Aprobada":
        sem_cot[s]["napr"] += 1
        sem_cot[s]["mapr"] += f(r["property_total"])

# Top clientes (cotizan)
cli_cot = defaultdict(lambda: {"n":0,"m":0.0})
for r in cot:
    c = (r.get("property_id_f","") or "Sin cliente").strip()
    cli_cot[c]["n"] += 1
    cli_cot[c]["m"] += f(r["property_total"])
top_cli_cot = sorted(cli_cot.items(), key=lambda x: x[1]["m"], reverse=True)[:10]

# Top clientes (aprobadas)
cli_apr = defaultdict(lambda: {"n":0,"m":0.0})
for r in cot:
    if r["property_estado"].strip() != "Aprobada": continue
    c = (r.get("property_id_f","") or "Sin cliente").strip()
    cli_apr[c]["n"] += 1
    cli_apr[c]["m"] += f(r["property_total"])
top_cli_apr = sorted(cli_apr.items(), key=lambda x: x[1]["m"], reverse=True)[:10]

# Tipos de pago en cotización
tip_cot = defaultdict(lambda: {"n":0,"m":0.0})
for r in cot:
    tp = (r.get("property_tip_p","") or "Sin definir").strip() or "Sin definir"
    tip_cot[tp]["n"] += 1
    tip_cot[tp]["m"] += f(r["property_total"])

# Tiempos de aprobación
t_apr_list = []
for r in cot:
    if r["property_estado"].strip() != "Aprobada": continue
    t = r.get("property_tiempo_de_aprobacion","").strip()
    if t:
        try: t_apr_list.append(float(t))
        except: pass

rangos_apr = {"Mismo día (0 días)":0, "1-3 días":0, "4-7 días":0, ">7 días":0}
for t in t_apr_list:
    if t == 0: rangos_apr["Mismo día (0 días)"] += 1
    elif t <= 3: rangos_apr["1-3 días"] += 1
    elif t <= 7: rangos_apr["4-7 días"] += 1
    else: rangos_apr[">7 días"] += 1

# Local vs Foráneo
rol_cot = defaultdict(lambda: {"n":0,"m":0.0,"napr":0,"mapr":0.0})
for r in cot:
    rol = (r.get("property_rol.0","") or "Sin rol").strip() or "Sin rol"
    rol_cot[rol]["n"] += 1
    rol_cot[rol]["m"] += f(r["property_total"])
    if r["property_estado"].strip() == "Aprobada":
        rol_cot[rol]["napr"] += 1
        rol_cot[rol]["mapr"] += f(r["property_total"])

# Ariba
n_ariba = sum(1 for r in cot if r.get("property_ariba","").upper() == "TRUE")
m_ariba = sum(f(r["property_total"]) for r in cot if r.get("property_ariba","").upper() == "TRUE")

R["mod1"] = {
    "n_cot": n_cot, "sub_cot": sub_cot, "tot_cot": tot_cot,
    "n_apr": n_apr, "mon_apr": mon_apr, "conv_q": conv_q, "conv_m": conv_m,
    "ticket_prom_cot": tot_cot/n_cot if n_cot else 0,
    "ticket_prom_apr": mon_apr/n_apr if n_apr else 0,
    "est_cot": dict(est_cot),
    "sem_cot": sem_cot,
    "top_cli_cot": top_cli_cot, "top_cli_apr": top_cli_apr,
    "tip_cot": dict(tip_cot),
    "rangos_apr": rangos_apr,
    "tiempo_apr_avg": avg(t_apr_list),
    "tiempo_apr_med": med(t_apr_list),
    "tiempo_apr_max": max(t_apr_list) if t_apr_list else 0,
    "rol_cot": dict(rol_cot),
    "n_ariba": n_ariba, "m_ariba": m_ariba,
}

print(f"  N={n_cot} Aprobadas={n_apr} ({conv_q:.1%}) MontoApr={mon_apr:,.2f}")
print(f"  Ariba={n_ariba} ({n_ariba/n_cot:.1%})")

print("Mod 1 OK. Guardando estado parcial...")
with open(OUT + "metrics_data.json", "w", encoding="utf-8") as fh:
    json.dump(R, fh, ensure_ascii=False, indent=2, default=str)
print("Guardado.")
