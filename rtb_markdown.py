#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RTB Cierre — Generador de Markdown."""

from datetime import datetime

def p(v): return f"${v:,.2f}"
def pct(a,b): return f"{a/b*100:.1f}%" if b else "0.0%"

def tabla(headers, rows, align=None):
    if not rows: return "| " + " | ".join(headers) + " |\n|" + "|".join(["---"]*len(headers)) + "|"
    widths=[max(len(str(h)),max(len(str(c)) for c in col)) for h,col in zip(headers,zip(*rows))]
    def row_str(r): return "| " + " | ".join(str(c).ljust(w) for c,w in zip(r,widths)) + " |"
    sep = "|" + "|".join("-"*(w+2) for w in widths) + "|"
    return "\n".join([row_str(headers), sep] + [row_str(r) for r in rows])

def render(R):
    m1=R["m1"]; m2a=R["m2a"]; m2b=R["m2b"]; m2c=R["m2c"]; m2d=R["m2d"]
    m3=R["m3"]; m4=R["m4"]; m5=R["m5"]; pl=R["pl"]; hero=R["hero"]
    now=datetime.now().strftime("%Y-%m-%d %H:%M")
    period=R.get("period",{})
    period_label=period.get("label","Abril 2026")
    period_range=period.get("range_label","1–30 de Abril 2026")
    period_month=period.get("month_label","abril")
    export_date=period.get("export_date","23-may-2026")
    warnings=R.get("warnings",[])
    temporal=R.get("temporal", {})
    temporal_behavior=temporal.get("behavior_title", "Comportamiento semanal")
    temporal_heading=temporal.get("table_heading", "Semana")

    lines=[]
    A=lines.append

    A(f"# 📊 Cierre Mensual RTB — {period_label}")
    A(f"\n**RFC:** RTB181127HC7 · **Generado:** {now} · **Encargado TI:** Diego Guillén García\n")
    A(f"**Período:** {period_range} · **Fuente:** Notion (CSVs exportados {export_date})\n")
    for warning in warnings:
        A(f"> ⚠️ **Dato faltante:** {warning}")
    if warnings:
        A("")

    A("---")
    A("## KPIs Ejecutivos\n")
    A(tabla(["Indicador","Valor","Notas"],[
        ["Cotizaciones creadas", str(hero["n_cot"]), p(hero["tot_cot"])+" c/IVA"],
        ["Tasa de conversión qty/monto", f"{hero['conv_q']:.1%} / {hero['conv_m']:.1%}", "Aprobadas"],
        ["Pedidos del mes", str(hero["n_ped"]), p(hero["tot_ped"])+" c/IVA"],
        ["Pedidos entregados", str(hero["n_env"]), p(hero["tot_env"])],
        ["Facturación total (prim+sec)", p(hero["tot_facturacion"]), f"Fecha en {period_month}"],
        ["Ingresos cobrados", p(hero["tot_pag"]), p(hero["sub_pag"])+" sub"],
        ["Margen bruto", p(hero["margen"]), f"{hero['pct_margen']:.1%} s/ingresos"],
        ["Stock total (cierre abril)", p(hero["snap_abr_total"]), f"{hero['pct_inmov']:.1%} inmovilizado"],
    ]))
    A("")

    # ── MÓDULO 1 ──────────────────────────────────────────────────────────
    A("---\n## 🟢 Módulo 1 · Ventas / Cotizaciones\n")
    A(f"- **Total cotizaciones:** {m1['n_cot']} · **Total c/IVA:** {p(m1['tot_cot'])} · **Subtotal:** {p(m1['sub_cot'])}")
    A(f"- **Aprobadas:** {m1['n_apr']} ({m1['conv_q']:.1%} en qty, {m1['conv_m']:.1%} en monto) · **Monto aprobado:** {p(m1['mon_apr'])}")
    A(f"- **Ticket promedio cotizado:** {p(m1['ticket_cot'])} · **Ticket promedio aprobado:** {p(m1['ticket_apr'])}")
    A(f"- **Ariba (Grupo Posadas):** {m1['n_ariba']} cotizaciones ({m1['n_ariba']/m1['n_cot']:.1%}) · {p(m1['m_ariba'])}\n")

    A("### 1.1 Por estado")
    rows=[[e,str(d["n"]),p(d["m"]),pct(d["n"],m1["n_cot"]),pct(d["m"],m1["tot_cot"])]
          for e,d in sorted(m1["est_cot"].items(),key=lambda x:-x[1]["m"])]
    A(tabla(["Estado","Qty","Monto c/IVA","% qty","% monto"],rows)); A("")

    A(f"### 1.2 {temporal_behavior}")
    srows=[[d["etiqueta"],str(int(d["n"])),p(d["m"]),str(int(d["na"])),p(d["ma"]),
            f"{d['na']/d['n']:.1%}" if d["n"] else "0%",
            f"{d['ma']/d['m']:.1%}" if d["m"] else "0%"]
           for d in m1["temporal_cot"]["periodos"]]
    A(tabla([temporal_heading,"Cot.","Monto cot.","Apr.","Monto apr.","Conv. qty","Conv. monto"],srows)); A("")

    A("### 1.3 Top 10 clientes (cotizan / compran)")
    r1=[[c,str(d["n"]),p(d["m"])] for c,d in m1["top_cli_cot"]]
    r2=[[c,str(d["n"]),p(d["m"])] for c,d in m1["top_cli_apr"]]
    A("**Cotizan:**"); A(tabla(["Cliente","Cot.","Monto"],r1)); A("")
    A("**Aprobadas:**"); A(tabla(["Cliente","Apr.","Monto"],r2)); A("")

    A("### 1.4 Tipos de pago en cotizaciones")
    rows=[[tp,str(d["n"]),p(d["m"]),pct(d["m"],m1["tot_cot"])]
          for tp,d in sorted(m1["tip_cot"].items(),key=lambda x:-x[1]["m"])]
    A(tabla(["Tipo pago","Qty","Monto","% monto"],rows)); A("")
    if m1["tip_cot"].get("Sin definir",{}).get("n",0)/m1["n_cot"]>0.5:
        A("> ⚠️ Más del 50% de las cotizaciones tienen tipo de pago en blanco — ver Hallazgos.\n")

    A("### 1.5 Tiempos de aprobación (cotizaciones aprobadas)")
    A(f"- **Promedio:** {m1['t_apr_avg']:.1f} días · **Mediana:** {m1['t_apr_med']:.0f} días · **Máximo:** {m1['t_apr_max']:.0f} días")
    rows=[[r,str(c)] for r,c in m1["rangos_apr"].items()]
    A(tabla(["Rango","Cantidad"],rows)); A("")

    A("### 1.6 Local vs Foráneo")
    rows=[[rol,str(d["n"]),p(d["m"]),str(d["na"]),p(d["ma"]),
           f"{d['ma']/d['m']:.1%}" if d["m"] else "0%"]
          for rol,d in sorted(m1["rol_cot"].items(),key=lambda x:-x[1]["m"])]
    A(tabla(["Rol","Cot.","Monto cot.","Apr.","Monto apr.","Conv. monto"],rows)); A("")

    # ── MÓDULO 2 ──────────────────────────────────────────────────────────
    A("---\n## 🟡 Módulo 2 · Almacén / Logística / Facturación / Cobranza\n")

    A("### 2.A Pedidos creados en el mes")
    A(f"- **Total:** {m2a['n_ped']} pedidos · **Subtotal:** {p(m2a['sub_ped'])} · **Total c/IVA:** {p(m2a['tot_ped'])}")
    A(f"- **Con faltante:** {m2a['n_falt']} ({pct(m2a['n_falt'],m2a['n_ped'])})")
    A(f"- **Sin factura (NR sin facturar):** {len(m2a['sin_factura'])} pedidos")
    A(f"- **Facturados sin entregar:** {len(m2a['sin_entregar'])} pedidos\n")

    A("**Local vs Foráneo:**")
    rows=[[rol,str(d["n"]),p(d["sub"]),p(d["tot"])] for rol,d in sorted(m2a["rol_ped"].items(),key=lambda x:-x[1]["tot"])]
    A(tabla(["Rol","Pedidos","Subtotal","Total c/IVA"],rows)); A("")

    A("**Estado de pedido:**")
    rows=[[e,str(d["n"]),p(d["m"])] for e,d in sorted(m2a["est_ped"].items(),key=lambda x:-x[1]["m"])]
    A(tabla(["Estado","Qty","Monto"],rows)); A("")

    A("**Estado de factura:**")
    rows=[[e,str(d["n"]),p(d["m"])] for e,d in sorted(m2a["est_fac"].items(),key=lambda x:-x[1]["m"])]
    A(tabla(["Estado","Qty","Monto"],rows)); A("")

    A(f"**{temporal_behavior}:**")
    rows=[[d["etiqueta"],str(int(d["n"])),p(d["m"])] for d in m2a["temporal_ped"]["periodos"]]
    A(tabla([temporal_heading,"Pedidos","Monto"],rows)); A("")

    A("**Top 10 clientes (monto pedido):**")
    rows=[[c,str(d["n"]),p(d["m"])] for c,d in m2a["top_cli_ped"]]
    A(tabla(["Cliente","Pedidos","Monto"],rows)); A("")

    A("### 2.B Tiempos de preparación de pedidos")
    A(f"> **¿Qué es?** Los días que tarda el equipo desde que se crea el pedido hasta que queda listo para envío/entrega.\n")
    A(f"- **Promedio:** {m2a['t_prep_avg']:.1f} días · **Mediana:** {m2a['t_prep_med']:.0f} días · **Máximo:** {m2a['t_prep_max']:.0f} días")
    rows=[[r,str(c)] for r,c in m2a["rangos_prep"].items()]
    A(tabla(["Rango preparación","Pedidos"],rows)); A("")

    A("### 2.C Tiempos de entrega al cliente")
    A(f"> **¿Qué es?** Días desde que el pedido está listo hasta que el cliente lo recibe (incluye tránsito para foráneos).\n")
    A(f"- **Promedio:** {m2a['t_ent_avg']:.1f} días · **Mediana:** {m2a['t_ent_med']:.0f} días · **Máximo:** {m2a['t_ent_max']:.0f} días")
    A(f"- Entregados ≤2 días: {m2a['n_ent_2']} | ≤5 días: {m2a['n_ent_5']} | ≤7 días: {m2a['n_ent_7']}")
    rows=[[r,str(c)] for r,c in m2a["rangos_ent"].items()]
    A(tabla(["Rango entrega","Pedidos"],rows)); A("")

    A("### 2.D Ciclo de facturación completo")
    A("> **¿Qué es?** El ciclo de vida de una venta: desde pedido → emisión de factura (CFDI) → validación del cliente → asociación al complemento de pago.\n")
    A(tabla(["Etapa","Promedio","Mediana","Máximo","N"],[
        ["Pedido → Facturado",f"{m2a['ciclo_pf_avg']:.1f}d",f"{m2a['ciclo_pf_med']:.0f}d",f"{m2a['ciclo_pf_max']:.0f}d",str(m2a["n_ciclo_pf"])],
        ["Facturado → Validado",f"{m2a['ciclo_fv_avg']:.1f}d",f"{m2a['ciclo_fv_med']:.0f}d",f"{m2a['ciclo_fv_max']:.0f}d",str(m2a["n_ciclo_fv"])],
        ["Validado → Asociado",f"{m2a['ciclo_va_avg']:.1f}d",f"{m2a['ciclo_va_med']:.0f}d",f"{m2a['ciclo_va_max']:.0f}d",str(m2a["n_ciclo_va"])],
        ["Ciclo total",f"{m2a['ciclo_tot_avg']:.1f}d",f"{m2a['ciclo_tot_med']:.0f}d",f"{m2a['ciclo_tot_max']:.0f}d",str(m2a["n_ciclo_tot"])],
    ])); A("")

    A("### 2.E Pedidos enviados/entregados en el mes (cualquier origen)")
    A(f"- **Total entregados:** {m2b['n_env']} · **Total c/IVA:** {p(m2b['tot_env'])}")
    A(f"- **Con faltante:** {m2b['n_env_falt']} ({pct(m2b['n_env_falt'],m2b['n_env'])})")
    A(f"- **Completados 100%:** {m2b['n_100']} | **Parciales:** {m2b['n_parcial']}")
    A(f"- **Tiempo entrega promedio:** {m2b['t_env_avg']:.1f} días (med: {m2b['t_env_med']:.0f}, máx: {m2b['t_env_max']:.0f})")
    A("\n**Top 10 clientes (entregas):**")
    rows=[[c,str(d["n"]),p(d["m"])] for c,d in m2b["top_cli_env"]]
    A(tabla(["Cliente","Entregas","Monto"],rows)); A("")

    A(f"### 2.F Facturación (Fecha primaria {period_label})")
    A(f"- **Pedidos facturados:** {m2c['n_fac']} · **Total c/IVA:** {p(m2c['tot_fac'])} · **1ra factura:** {p(m2c['mon_1era'])}")
    if m2c["n_facs"]:
        A(f"- **Facturación secundaria:** {m2c['n_facs']} registro(s) · {p(m2c['mon_2da'])}")
    A(f"- **Total facturado {period_month} (prim+sec):** {p(m2c['tot_facturacion'])}\n")

    A("### 2.G Ingresos cobrados y tiempos de pago")
    A(f"> **¿Qué es tiempo de pago?** Días desde la emisión de la factura hasta que el cliente realiza el pago.\n")
    A(f"- **Pedidos pagados:** {m2d['n_pag']} · **Subtotal:** {p(m2d['sub_pag'])} · **Total c/IVA:** {p(m2d['tot_pag'])}")
    A(f"- **CxC estimada (facturado−cobrado):** {p(m2d['cxc_est'])}")
    A(f"- **Promedio días pago:** {m2d['t_pago_avg']:.1f} · Mediana: {m2d['t_pago_med']:.0f} · Máximo: {m2d['t_pago_max']:.0f}")
    rows=[[r,str(c)] for r,c in m2d["rangos_pago"].items()]
    A(tabla(["Rango días pago","Pedidos"],rows)); A("")
    A("**Por tipo de pago:**")
    rows=[[tp,str(d["n"]),p(d["m"]),pct(d["m"],m2d["tot_pag"])]
          for tp,d in sorted(m2d["tp_pag"].items(),key=lambda x:-x[1]["m"])]
    A(tabla(["Tipo","Pedidos","Monto","% del total"],rows)); A("")
    A("**Top 10 clientes que pagaron:**")
    rows=[[c,str(d["n"]),p(d["m"])] for c,d in m2d["top_cli_pag"]]
    A(tabla(["Cliente","Pagos","Monto"],rows)); A("")

    # ── MÓDULO 3 ──────────────────────────────────────────────────────────
    A("---\n## 🔵 Módulo 3 · Compras\n")
    A(f"- **Facturas:** {m3['n_fc']} · **Subtotal:** {p(m3['sub_fc'])} · **IVA:** {p(m3['iva_fc'])} · **Total c/IVA:** {p(m3['tot_fc'])}")
    A(f"- **Costo de envío:** {p(m3['env_fc'])}\n")

    A(f"**{temporal_behavior}:**")
    rows=[[d["etiqueta"],str(int(d["n"])),p(d["sub"]),p(d["tot"])] for d in m3["temporal_fc"]["periodos"]]
    A(tabla([temporal_heading,"Facturas","Subtotal","Total c/IVA"],rows)); A("")

    A("**Status de pago:**")
    rows=[[sp,str(d["n"]),p(d["m"]),pct(d["m"],m3["tot_fc"])]
          for sp,d in sorted(m3["sp_fc"].items(),key=lambda x:-x[1]["m"])]
    A(tabla(["Status","Qty","Monto","% total"],rows)); A("")

    A("**Tipos de pago:**")
    rows=[[tp,str(d["n"]),p(d["m"]),pct(d["m"],m3["tot_fc"])]
          for tp,d in sorted(m3["tp_fc"].items(),key=lambda x:-x[1]["m"])]
    A(tabla(["Tipo pago","Qty","Monto","% total"],rows)); A("")

    A("**Top 10 proveedores:**")
    rows=[[pv,str(d["n"]),p(d["sub"]),p(d["tot"])] for pv,d in m3["top_prov"]]
    A(tabla(["Proveedor","Facturas","Subtotal","Total c/IVA"],rows)); A("")

    A(f"**Crédito vivo (no pagadas):** {m3['n_no_pag']} facturas · {p(m3['cxp'])}")
    rows=[[pv,str(d["n"]),p(d["m"])] for pv,d in m3["cred_vivo"]]
    A(tabla(["Proveedor","Facturas","Monto adeudado"],rows)); A("")

    A("**Pagos efectivos a proveedores (PAGADAS):**")
    A(f"- **Facturas:** {m3['n_fcp']} · **Total:** {p(m3['tot_fcp'])} · **Prom días pago:** {m3['t_fc_pago_avg']:.1f}")
    rows=[[pv,str(d["n"]),p(d["m"])] for pv,d in m3["top_prov_pag"]]
    A(tabla(["Proveedor","Pagos","Monto"],rows)); A("")

    A("**Uso CFDI:**")
    A("> **¿Qué es CFDI?** Comprobante Fiscal Digital por Internet — la factura electrónica del SAT. G01 = adquisición de mercancías, G03 = gastos en general.")
    rows=[[c,str(d["n"]),p(d["m"])] for c,d in sorted(m3["cfdi_fc"].items(),key=lambda x:-x[1]["m"])]
    A(tabla(["Uso CFDI","Qty","Monto"],rows)); A("")

    # ── MÓDULO 4 ──────────────────────────────────────────────────────────
    A("---\n## 🟣 Módulo 4 · Inventario\n")
    A("> **Regla de lectura:** El inmovilizado es un *subconjunto* del stock total, no una métrica paralela.")
    A("> Si stock=$X e inmovilizado=$Y → $X−$Y rotó (tuvo salidas) · $Y no tuvo ninguna salida en el mes.\n")

    snaps=m4["snaps"]
    A("**Snapshot oficial Abril 2026:**")
    sa=snaps["Abril"]
    A(f"- Stock total: {p(sa['total'])} | Con rotación: {p(sa['activo'])} | Inmovilizado: {p(sa['inmov'])} ({sa['pct_inmov']:.1%})\n")

    A("**Comparativa histórica:**")
    rows=[]
    prev=None
    for mes in ["Febrero","Marzo","Abril","Mayo"]:
        d=snaps[mes]
        delta=f"{(d['total']-prev)/prev*100:+.1f}%" if prev else "—"
        rows.append([mes,p(d["total"]),p(d["inmov"]),f"{d['pct_inmov']:.1%}",delta])
        prev=d["total"]
    A(tabla(["Mes","Stock total","Inmovilizado","% inmov","Δ vs anterior"],rows)); A("")
    A(f"**Variación Marzo→Abril:** {p(m4['var_mar_abr'])} ({m4['var_pct_mar_abr']:+.1f}%)\n")

    A("**Movimientos del mes:**")
    A(f"- Salidas: {m4['total_sal_piezas']:.0f} piezas en {m4['n_skus_sal']} SKUs")
    A(f"- Entradas: {m4['total_ent_piezas']:.0f} piezas en {m4['n_skus_ent']} SKUs")
    A(f"- SKUs en stock: {m4['n_en']} · SKUs sin stock: {m4['n_sin']}\n")

    A("**Top 10 SKUs con más salidas (cantidad):**")
    rows=[[r.get("property_sku","?"),str(int(float(r.get("property_salida_real_final","0")))),
           r.get("name","")[:40]] for r in m4["top_sal"]]
    A(tabla(["SKU","Piezas","Nombre"],rows)); A("")

    A("**Top 10 SKUs con más entradas:**")
    rows=[[r.get("property_sku.0","?"),str(int(float(r.get("property_erf","0")))),
           r.get("name","")[:40]] for r in m4["top_ent"]]
    A(tabla(["SKU","Piezas","Nombre"],rows)); A("")

    A("**Top 10 SKUs por valor de stock:**")
    rows=[[r.get("property_sku_f","?"),r.get("property_cantidad_real_en_inventario",""),
           p(float(r.get("property_costo_total_en_stock","0") or 0)),
           r.get("name","")[:40]] for r in m4["top_inv"]]
    A(tabla(["SKU","Cant","Valor","Nombre"],rows)); A("")

    # ── MÓDULO 5 ──────────────────────────────────────────────────────────
    A("---\n## ⚪ Módulo 5 · Gastos Operativos\n")
    for warning in warnings:
        if "GASTOS_OPERATIVOS" in warning:
            A(f"> ⚠️ **Dato faltante:** {warning}\n")
    A(f"- **Realizados:** {m5['n_real']} · **Total:** {p(m5['tot_gas'])} · **Subtotal:** {p(m5['sub_gas'])}")
    A(f"- **Pendientes:** {m5['n_pend']} registros")
    A(f"- **Deducibles:** {p(m5['ded'])} ({m5['pct_ded']:.1%}) · **No deducibles:** {p(m5['no_ded'])}\n")

    A("**Por categoría:**")
    rows=[[cat,str(d["n"]),p(d["m"]),pct(d["m"],m5["tot_gas"])]
          for cat,d in sorted(m5["cat_gas"].items(),key=lambda x:-x[1]["m"])]
    A(tabla(["Categoría","Qty","Monto","% total"],rows)); A("")

    A("**Por método de pago:**")
    rows=[[mp,str(d["n"]),p(d["m"]),pct(d["m"],m5["tot_gas"])]
          for mp,d in sorted(m5["mp_gas"].items(),key=lambda x:-x[1]["m"])]
    A(tabla(["Método","Qty","Monto","% total"],rows)); A("")

    A(f"**Carga fiscal identificada:** {p(m5['tot_fiscal'])} en {len(m5['carga_fiscal'])} registros")
    rows=[[x["concepto"][:50],p(x["total"]),x.get("folio","")] for x in m5["carga_fiscal"]]
    if rows: A(tabla(["Concepto","Total","Folio"],rows)); A("")

    A(f"**{temporal_behavior}:**")
    rows=[[d["etiqueta"],str(int(d["n"])),p(d["m"]),pct(d["m"],m5["tot_gas"])] for d in m5["temporal_gas"]["periodos"]]
    A(tabla([temporal_heading,"Qty","Monto","% total"],rows)); A("")

    A(f"**Con comprobante fiscal:** {m5['con_folio']} registros · {p(m5['mon_con_folio'])} | **Sin folio:** {m5['sin_folio']} · {p(m5['mon_sin_folio'])}\n")

    A("**Top 10 conceptos:**")
    rows=[[conc[:50],str(d["n"]),p(d["m"])] for conc,d in m5["top_conc"]]
    A(tabla(["Concepto","Qty","Monto"],rows)); A("")

    A("**Por responsable:**")
    rows=[[resp[:40],str(d["n"]),p(d["m"]),pct(d["m"],m5["tot_gas"])] for resp,d in m5["resp_gas"]]
    A(tabla(["Responsable","Qty","Monto","% total"],rows)); A("")

    # ── P&L ───────────────────────────────────────────────────────────────
    A("---\n## 📈 Estado de Resultados y Flujo de Caja\n")
    A("```")
    A(f"  (+) Ingresos cobrados (subtotal)       {p(pl['ing_sub']):>16}")
    A(f"  (−) Costo de compras (subtotal)        {p(pl['comp_sub']):>16}")
    A(f"  ─────────────────────────────────────────────────────")
    A(f"  MARGEN BRUTO                           {p(pl['margen']):>16}   ({pl['pct_margen']:.1%})")
    A(f"  (−) OPEX (subtotal)                    {p(pl['opex_sub']):>16}")
    A(f"  ─────────────────────────────────────────────────────")
    A(f"  UTILIDAD TEÓRICA                       {p(pl['utilidad']):>16}   ({pl['pct_utilidad']:.1%})")
    A(f"")
    A(f"  — Ajustado (sin carga fiscal {p(pl['tot_fiscal'])}) —")
    A(f"  OPEX recurrente                        {p(pl['opex_recur']):>16}")
    A(f"  UTILIDAD AJUSTADA                      {p(pl['utilidad_adj']):>16}   ({pl['pct_utilidad_adj']:.1%})")
    A("```\n")
    A("```")
    A(f"  FLUJO DE CAJA REAL (c/IVA)")
    A(f"  (+) Cobrado a clientes                 {p(pl['flujo_cobrado']):>16}")
    A(f"  (−) Pagado a proveedores               {p(pl['flujo_pagado_prov']):>16}")
    A(f"  (−) OPEX pagado                        {p(pl['flujo_opex']):>16}")
    A(f"  ─────────────────────────────────────────────────────")
    A(f"  FLUJO NETO DEL MES                     {p(pl['flujo_neto']):>16}")
    A("```\n")
    A(f"**Posición de cartera:** CxC {p(pl['cxc_total'])} − CxP {p(pl['cxp_total'])} = **{p(pl['pos_neta'])}**\n")

    # ── HALLAZGOS ─────────────────────────────────────────────────────────
    A("---\n## 🔍 Hallazgos Críticos\n")
    h=[]
    h.extend(f"⚠️ **Dato faltante:** {warning}" for warning in warnings)
    pct_fiscal=m5["tot_fiscal"]/m5["tot_gas"] if m5["tot_gas"] else 0
    if pct_fiscal>0.5:
        h.append(f"🚨 **Carga fiscal extraordinaria** representa el {pct_fiscal:.1%} del OPEX ({p(m5['tot_fiscal'])}): declaraciones acumuladas que distorsionan el mes. Sin este cargo, utilidad ajustada sería **{p(pl['utilidad_adj'])} ({pl['pct_utilidad_adj']:.1%})**.")
    pct_inmov=snaps["Abril"]["pct_inmov"]
    if pct_inmov>0.4:
        h.append(f"🚨 **Inventario inmovilizado {pct_inmov:.1%}** del stock total ({p(snaps['Abril']['inmov'])} de {p(snaps['Abril']['total'])}). Creció {snaps['Marzo']['inmov']:.0f} → {snaps['Abril']['inmov']:.0f} (Marzo→Abril). Revisar SKUs sin rotación.")
    if m2d["t_pago_med"]>60:
        h.append(f"⚠️ **Mediana de días de cobro {m2d['t_pago_med']:.0f} días** — muy alta. CxC estimada: {p(m2d['cxc_est'])}. Riesgo de flujo en mayo.")
    top_pv,top_pv_d=m3["top_prov"][0] if m3["top_prov"] else ("?",{"tot":0})
    if top_pv_d["tot"]/m3["tot_fc"]>0.4:
        h.append(f"⚠️ **Concentración de proveedor:** {top_pv} representa {pct(top_pv_d['tot'],m3['tot_fc'])} de las compras ({p(top_pv_d['tot'])}). Riesgo operativo si falla suministro.")
    por_definir=m3["tp_fc"].get("99 por definir",{"m":0})["m"]
    if por_definir/m3["tot_fc"]>0.1:
        h.append(f"⚠️ **{pct(por_definir,m3['tot_fc'])} de compras sin tipo de pago definido** (\"99 por definir\" = {p(por_definir)}). Degrada trazabilidad de tesorería.")
    sin_def_cot=m1["tip_cot"].get("Sin definir",{"n":0})["n"]
    if sin_def_cot/m1["n_cot"]>0.5:
        h.append(f"⚠️ **{pct(sin_def_cot,m1['n_cot'])} cotizaciones sin tipo de pago definido** ({sin_def_cot}/{m1['n_cot']}). Sin este dato no se puede analizar el mix comercial real.")
    if len(m2a["sin_entregar"])>3:
        h.append(f"⚠️ **{len(m2a['sin_entregar'])} pedidos facturados sin entregar** — riesgo de incidencia con cliente y desfase contable.")
    otros_pct=m5["cat_gas"].get("Otros",{"m":0})["m"]/m5["tot_gas"] if m5["tot_gas"] else 0
    if otros_pct>0.4:
        h.append(f"⚠️ **Categoría 'Otros' representa {otros_pct:.1%} del OPEX** — la taxonomía de Notion está rota. Se recomienda crear categorías 'Impuestos/SAT', 'Seguridad Social', 'Intereses Financieros'.")
    h.append(f"ℹ️ **Flujo neto del mes: {p(pl['flujo_neto'])}** — equilibrio casi perfecto pero cualquier descalce en cobranza generará déficit en mayo.")
    for i,item in enumerate(h,1):
        A(f"{i}. {item}")
    A("")

    # ── GLOSARIO ──────────────────────────────────────────────────────────
    A("---\n## 📚 Glosario de Terminología\n")
    glosario=[
        ("Cotización","Propuesta de precio enviada al cliente. No es una venta confirmada. Caduca si no se aprueba en el plazo acordado."),
        ("Pedido","Cotización aprobada por el cliente. Entra al flujo de preparación, entrega y facturación."),
        ("NR (Nota de Remisión)","Guía de entrega física que acompaña la mercancía antes de emitir la factura CFDI formal. Sirve como resguardo temporal."),
        ("CFDI","Comprobante Fiscal Digital por Internet — la factura electrónica validada por el SAT. G01 = adquisición de mercancías. G03 = gastos en general."),
        ("Ariba","Plataforma SAP que usa Grupo Posadas (hoteles) para gestionar sus órdenes de compra con proveedores B2B. Impone proceso más largo pero asegura el pago."),
        ("Foráneo / Local","Foráneo = cliente fuera de CDMX o con entrega en otro estado (requiere envío). Local = cliente en CDMX/área metro (entrega directa)."),
        ("Inmovilizado","Inventario que NO tuvo ninguna salida durante el mes. Es un subconjunto del stock total — no se suma, se resta para conocer el activo con movimiento."),
        ("Margen Bruto","Ingresos de ventas menos el costo directo de los productos comprados. No incluye gastos operativos (salarios, renta, servicios)."),
        ("EBITDA / Utilidad estimada","Margen bruto menos gastos operativos. Aproxima la rentabilidad del negocio antes de impuestos, depreciación e intereses. No es la utilidad fiscal."),
        ("CxC (Cuentas por Cobrar)","Dinero que los clientes nos deben por facturas emitidas pero aún no pagadas."),
        ("CxP (Cuentas por Pagar)","Dinero que debemos a proveedores por facturas recibidas pero aún no pagadas."),
        ("Tipo de pago '99 por definir'","Marca interna de Notion cuando el tipo de pago no fue especificado al registrar la factura. Debe resolverse antes de cierre."),
        ("Validación de factura","Confirmación interna de que la factura emitida es correcta en datos, monto y concepto. Paso previo a enviarla al cliente."),
        ("Asociación al pago","Proceso de vincular el pago recibido del cliente con la factura correspondiente — necesario para emitir el complemento de pago al SAT."),
        ("Ciclo de facturación","Tiempo total desde que se crea el pedido hasta que la factura queda asociada al pago. Incluye: preparación → emisión → validación → asociación."),
        ("Carga fiscal extraordinaria","Pagos al SAT / IMSS que cayeron en el mes pero corresponden a períodos anteriores (declaraciones atrasadas, pagos acumulados). Distorsionan el OPEX del mes corriente."),
        ("Status 'Impresa' vs 'Entregada'","Impresa = factura generada en sistema pero no entregada físicamente/digitalmente al cliente. Entregada = el cliente la recibió. Mientras está en 'Impresa', el ciclo no avanza."),
        ("Complemento de pago","Documento CFDI adicional que se emite cuando el cliente paga una factura a crédito. Cierra el ciclo fiscal ante el SAT."),
        ("SIPARE","Sistema de Pago Referenciado del IMSS/INFONAVIT. El pago mensual de las cuotas de seguridad social de los empleados."),
    ]
    A(tabla(["Término","Explicación"],glosario)); A("")

    A("---")
    A(f"*Generado automáticamente — RTB Cierre Mensual v4 · Fuente: CSVs Notion exportados {export_date}*")
    return "\n".join(lines)
