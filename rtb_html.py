#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RTB Cierre — Generador de HTML dashboard."""

import html, json, os, re
from datetime import datetime

# Lee Chart.js desde el archivo local para embeberlo inline
def _load_chartjs():
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "chart.umd.min.js")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return ""  # fallback vacío — el usuario verá error en consola

CHARTJS_INLINE = _load_chartjs()

def p(v):
    try: return f"${float(v):,.2f}"
    except: return "$0.00"
def pct(a,b): return f"{a/b*100:.1f}%" if b else "0.0%"
def jv(x): return json.dumps(round(float(x),2))
def ja(lst): return json.dumps([round(float(v),2) for v in lst])

CSS = """
:root{--bg:#ffffff;--surface:#276f86;--surface-2:#225e73;--primary:#159895;--primary-2:#7dd7cd;--accent:#d0b56b;--accent-2:#c6ad6a;--text:#f4f7f9;--text-2:rgba(255,255,255,0.72);--text-3:rgba(255,255,255,0.5);--border:rgba(173,149,81,0.24);--border-soft:rgba(173,149,81,0.12);--row-alt:rgba(255,255,255,0.05);--warn:#d4a93b;--alert:#d96058;--good:#57c5b6;}
*{box-sizing:border-box;}
html,body{background:var(--bg);color:var(--text);font-family:'Inter Tight',sans-serif;margin:0;padding:0;-webkit-font-smoothing:antialiased;}
.container{width:100%;max-width:1400px;margin:0 auto;padding:48px 32px;overflow-x:hidden;}
.hero{border-bottom:1px solid #d1d5db;padding-bottom:32px;margin-bottom:32px;color:#111827;}
.hero-eyebrow{font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#0f766e;font-weight:500;}
.hero-title{font-family:'Fraunces',serif;font-weight:500;font-size:56px;line-height:1.05;margin:12px 0 16px;color:#111827;letter-spacing:-0.02em;}
.hero-mes{color:var(--accent);font-style:italic;}
.hero-meta{font-size:13px;color:#374151;display:flex;gap:12px;flex-wrap:wrap;}
.hero-meta .dot{color:#9ca3af;}
.kpi-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin-bottom:48px;}
.kpi{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:20px 22px;display:flex;flex-direction:column;gap:6px;min-height:110px;}
.kpi-label{font-size:11px;letter-spacing:1.5px;text-transform:uppercase;color:var(--primary-2);font-weight:500;}
.kpi-value{font-family:'JetBrains Mono',monospace;font-size:26px;font-weight:600;color:var(--accent);line-height:1.1;margin-top:2px;}
.kpi-sub{font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--text-2);margin-top:auto;}
.sec{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:28px 32px;margin-bottom:24px;min-width:0;overflow:visible;}
.sec-title{font-family:'Fraunces',serif;font-size:26px;font-weight:500;color:var(--text);margin:0 0 24px;padding-bottom:12px;border-bottom:1px solid var(--border-soft);letter-spacing:-0.01em;}
.sub{font-family:'Fraunces',serif;font-size:18px;font-weight:500;color:var(--primary-2);margin:24px 0 12px;letter-spacing:-0.005em;}
.sub-sm{font-family:'Inter Tight',sans-serif;font-size:13px;font-weight:600;letter-spacing:0.5px;text-transform:uppercase;color:var(--primary-2);margin:20px 0 10px;}
.section-intro{color:var(--text-2);font-size:14px;line-height:1.6;margin:0 0 20px;}
table.t{width:100%;max-width:100%;border-collapse:collapse;margin:12px 0;font-size:13px;border:1px solid var(--border-soft);border-radius:6px;overflow:hidden;table-layout:fixed;}
table.t thead th{background:var(--surface-2);color:var(--primary-2);font-weight:600;font-size:11px;letter-spacing:1px;text-transform:uppercase;padding:12px 14px;border-bottom:1px solid var(--border);text-align:left;}
table.t thead th:not(:first-child),table.t tbody td:not(:first-child){text-align:right;}
table.t tbody td{padding:10px 14px;border-bottom:1px solid var(--border-soft);color:var(--text);text-align:left;overflow-wrap:anywhere;}
table.t tbody tr:nth-child(even) td{background:var(--row-alt);}
table.t tbody tr:last-child td{border-bottom:none;}
table.t tbody td:not(:first-child){font-family:'JetBrains Mono',monospace;font-size:12.5px;}
table.t b{color:var(--accent);}
.kpi-mini-row{display:flex;gap:12px;flex-wrap:wrap;margin:12px 0 16px;}
.kpi-mini{background:var(--surface-2);border:1px solid var(--border-soft);border-radius:8px;padding:12px 16px;flex:1 1 180px;min-width:160px;display:flex;flex-direction:column;gap:4px;}
.kpi-mini span{font-size:10px;letter-spacing:1px;text-transform:uppercase;color:var(--primary-2);font-weight:500;}
.kpi-mini b{font-family:'JetBrains Mono',monospace;font-size:15px;font-weight:500;color:var(--accent);}
.insight{display:flex;gap:14px;padding:14px 18px;margin:16px 0;border-radius:6px;background:rgba(255,255,255,0.04);border-left:3px solid var(--accent);font-size:13.5px;line-height:1.55;color:var(--text);}
.insight-icon{font-size:18px;line-height:1.2;flex-shrink:0;}
.insight-warn{border-left-color:var(--warn);}
.insight-alert{border-left-color:var(--alert);}
.insight-info{border-left-color:var(--primary);}
.insight-ok{border-left-color:var(--good);}
.insight b{color:var(--accent);}
.insight code{font-family:'JetBrains Mono',monospace;background:rgba(0,0,0,0.3);padding:1px 6px;border-radius:3px;font-size:12px;}
.callout{background:rgba(173,149,81,0.08);border:1px solid var(--border);border-radius:6px;padding:14px 18px;margin:16px 0 20px;font-size:14px;line-height:1.6;}
.callout b{color:var(--accent);}
.grid-2{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:24px;margin:16px 0;}
.grid-2>*{min-width:0;}
.chart-box{background:var(--surface-2);border:1px solid var(--border-soft);border-radius:6px;padding:16px;margin:10px 0;position:relative;min-width:0;max-width:100%;overflow:hidden;}
.chart-box canvas{display:block;max-width:100%!important;}
.chart-title{font-size:11px;letter-spacing:1px;text-transform:uppercase;color:var(--text-2);margin-bottom:10px;font-weight:600;}
.exec-summary p{font-size:15px;line-height:1.7;color:var(--text);margin:0 0 14px;}
.exec-summary b{color:var(--text);font-weight:600;}
.hl{color:var(--accent)!important;font-weight:600;}
.hl-good{color:var(--good)!important;font-weight:600;}
.hl-bad{color:var(--alert)!important;font-weight:600;}
.hl-num{color:var(--accent)!important;font-family:'JetBrains Mono',monospace;}
.gloss-term{position:relative;display:inline-block;background:rgba(208,181,107,0.22);border:1px solid var(--accent);border-radius:3px;color:#fff;font-family:'JetBrains Mono',monospace;font-size:0.92em;font-weight:500;line-height:1.15;padding:1px 5px;cursor:help;vertical-align:baseline;}
.gloss-term::after{content:attr(data-gloss);position:absolute;left:0;bottom:calc(100% + 8px);z-index:20;width:max-content;max-width:320px;background:#0a1e2e;color:#e8edf2;border:1px solid var(--accent);border-radius:6px;padding:10px 12px;font-family:'Inter Tight',sans-serif;font-size:12px;font-weight:400;line-height:1.45;text-transform:none;letter-spacing:0;box-shadow:0 12px 30px rgba(0,0,0,0.25);opacity:0;pointer-events:none;transform:translateY(4px);transition:opacity .15s ease,transform .15s ease;white-space:normal;text-align:left;}
.gloss-term::before{content:"";position:absolute;left:12px;bottom:calc(100% + 3px);z-index:21;border:5px solid transparent;border-top-color:var(--accent);opacity:0;pointer-events:none;transition:opacity .15s ease;}
.gloss-term:hover::after,.gloss-term:focus::after,.gloss-term:hover::before,.gloss-term:focus::before{opacity:1;transform:translateY(0);}
ol.findings{padding-left:0;list-style:none;counter-reset:f;}
ol.findings li{counter-increment:f;padding:14px 18px 14px 52px;background:var(--surface-2);border:1px solid var(--border-soft);border-left:3px solid var(--accent);border-radius:6px;margin-bottom:10px;position:relative;font-size:14px;line-height:1.6;}
ol.findings li::before{content:counter(f);position:absolute;left:16px;top:14px;font-family:'JetBrains Mono',monospace;font-size:16px;font-weight:600;color:var(--accent);background:var(--surface);width:26px;height:26px;display:flex;align-items:center;justify-content:center;border-radius:4px;border:1px solid var(--border);}
ol.findings.recs li{border-left-color:var(--primary);}
ol.findings.recs li::before{color:var(--primary-2);}
ol.findings code{font-family:'JetBrains Mono',monospace;background:rgba(0,0,0,0.3);padding:1px 6px;border-radius:3px;font-size:12px;}
.hint{font-size:12.5px;color:var(--text-2);margin:8px 0;line-height:1.5;}
.hint code{font-family:'JetBrains Mono',monospace;background:rgba(0,0,0,0.3);padding:1px 6px;border-radius:3px;font-size:11.5px;}
.glosario-table{width:100%;border-collapse:collapse;font-size:13px;}
.glosario-table th{background:var(--surface-2);color:var(--primary-2);font-size:11px;letter-spacing:1px;text-transform:uppercase;padding:10px 14px;border-bottom:1px solid var(--border);text-align:left;}
.glosario-table td{padding:10px 14px;border-bottom:1px solid var(--border-soft);vertical-align:top;}
.glosario-table td:first-child{font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--accent);white-space:nowrap;width:200px;}
.glosario-table tr:nth-child(even) td{background:var(--row-alt);}
.glosario-table tr{scroll-margin-top:16px;}
footer{margin-top:32px;padding-top:24px;border-top:1px solid var(--border-soft);color:var(--text-3);font-size:12px;text-align:center;}
@media(max-width:980px){.container{padding:24px 16px;}.hero-title{font-size:36px;}.kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr));}.grid-2{grid-template-columns:minmax(0,1fr);}.sec{padding:20px 18px;}table.t thead th,table.t tbody td{padding:8px 10px;font-size:12px;}}
@media(max-width:640px){.container{padding:18px 10px;}.kpi-grid{grid-template-columns:minmax(0,1fr);}.sec{padding:16px 10px;border-radius:8px;}table.t{font-size:11px;}table.t thead th,table.t tbody td{padding:7px 6px;}.chart-box{padding:10px;}}
"""

JS_BASE = """
const C={primary:'#159895',primary2:'#57c5b6',accent:'#ad9551',accent2:'#c6ad6a',text2:'rgba(255,255,255,0.6)',grid:'rgba(255,255,255,0.08)'};
Chart.defaults.font.family="'Inter Tight',sans-serif";Chart.defaults.color=C.text2;Chart.defaults.borderColor=C.grid;
const mf=v=>'$'+Math.round(v).toLocaleString('en-US');
const nf=v=>Math.round(v).toLocaleString('en-US');
const df=v=>Number(v).toFixed(1).replace(/\\.0$/,'')+' días';
const bs={x:{grid:{color:C.grid,drawBorder:false},ticks:{color:C.text2,font:{size:11}}},y:{grid:{color:C.grid,drawBorder:false},ticks:{color:C.text2,font:{size:11},callback:v=>mf(v)}}};
const countScales={x:{grid:{color:C.grid},ticks:{color:C.text2}},y:{grid:{color:C.grid},ticks:{color:C.text2,callback:v=>nf(v)}}};
const daysXScales={x:{grid:{color:C.grid},ticks:{color:C.text2,callback:v=>df(v)}},y:{grid:{display:false},ticks:{color:C.text2,font:{size:11}}}};
const tt={backgroundColor:'#0a1e2e',titleColor:'#e8edf2',bodyColor:'#e8edf2',borderColor:C.accent,borderWidth:1,padding:10,cornerRadius:4,callbacks:{label:ctx=>{const l=ctx.dataset.label||'',p=ctx.parsed,v=typeof p==='object'?(ctx.chart.options.indexAxis==='y'?p.x:p.y):p;if(typeof v!=='number')return l+': '+v;if(ctx.dataset.format==='count')return l+': '+nf(v);if(ctx.dataset.format==='days')return l+': '+df(v);if(ctx.dataset.format==='percent')return l+': '+v.toFixed(1)+'%';return l+': '+mf(v);}}};
function bar(id,labels,datasets,opts={}){new Chart(document.getElementById(id),{type:'bar',data:{labels,datasets},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{color:C.text2}},...(opts.nolegend?{legend:{display:false}}:{}),tooltip:tt},scales:opts.scales||bs,...opts}});}
function dough(id,labels,data,colors){new Chart(document.getElementById(id),{type:'doughnut',data:{labels,datasets:[{data,backgroundColor:colors,borderColor:'#154d62',borderWidth:2}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'right',labels:{color:C.text2,font:{size:11}}},tooltip:tt},cutout:'60%'}});}
function line(id,labels,datasets){new Chart(document.getElementById(id),{type:'line',data:{labels,datasets},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{color:C.text2}},tooltip:tt},scales:bs}});}
function hbar(id,labels,data,color,label='Monto',format='money',scales=null){new Chart(document.getElementById(id),{type:'bar',data:{labels,datasets:[{label,data,format,backgroundColor:color,borderRadius:4}]},options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:tt},scales:scales||{x:{grid:{color:C.grid},ticks:{color:C.text2,callback:v=>mf(v)}},y:{grid:{display:false},ticks:{color:C.text2,font:{size:11}}}}}});}
"""

def trow(cells, bold_idx=None):
    tds="".join(f"<td>{c}</td>" if i!=(bold_idx or -1) else f"<td><b>{c}</b></td>" for i,c in enumerate(cells))
    return f"<tr>{tds}</tr>"

def thead(headers):
    return "<thead><tr>"+"".join(f"<th>{h}</th>" for h in headers)+"</tr></thead>"

def build_table(headers, rows, bold_col=None):
    ths=thead(headers)
    trs="".join(f"<tr>{''.join(f'<td><b>{c}</b></td>' if i==bold_col else f'<td>{c}</td>' for i,c in enumerate(r))}</tr>" for r in rows)
    return f'<table class="t">{ths}<tbody>{trs}</tbody></table>'

def kpi(label, value, sub=""):
    return f'<div class="kpi"><div class="kpi-label">{label}</div><div class="kpi-value">{value}</div><div class="kpi-sub">{sub}</div></div>'

def mini(label, value):
    return f'<div class="kpi-mini"><span>{label}</span><b>{value}</b></div>'

def insight(icon, cls, html):
    return f'<div class="insight {cls}"><span class="insight-icon">{icon}</span><div>{html}</div></div>'

def chart_box(canvas_id, title="", height=200):
    t=f'<div class="chart-title">{title}</div>' if title else ""
    return f'<div class="chart-box">{t}<div style="position:relative;height:{height}px"><canvas id="{canvas_id}"></canvas></div></div>'

def link_first_glossary_terms(fragment, glossary_variants):
    parts = re.split(r"(<[^>]+>)", fragment)
    for variants, description in glossary_variants:
        pattern = re.compile(r"(?<![\wÁÉÍÓÚÜÑáéíóúüñ])(" + "|".join(re.escape(v) for v in variants) + r")(?![\wÁÉÍÓÚÜÑáéíóúüñ])")
        for i, part in enumerate(parts):
            if part.startswith("<"):
                continue
            if pattern.search(part):
                gloss_text = html.escape(description, quote=True)
                parts[i] = pattern.sub(
                    lambda m: f'<span class="gloss-term" tabindex="0" data-gloss="{gloss_text}">{m.group(1)}</span>',
                    part,
                    count=1,
                )
                parts = re.split(r"(<[^>]+>)", "".join(parts))
                break
    return "".join(parts)

def render(R):
    m1=R["m1"]; m2a=R["m2a"]; m2b=R["m2b"]; m2c=R["m2c"]; m2d=R["m2d"]
    m3=R["m3"]; m4=R["m4"]; m5=R["m5"]; pl=R["pl"]; hero=R["hero"]
    snaps=m4["snaps"]; now=datetime.now().strftime("%d-%b-%Y")
    period=R.get("period",{})
    period_label=period.get("label","Abril 2026")
    period_range=period.get("range_label","1 – 30 de abril, 2026")
    period_month=period.get("month_label","abril")
    next_month=period.get("next_month_label","mayo")
    export_date=period.get("export_date","23-may-2026")
    warnings=R.get("warnings",[])
    temporal=R.get("temporal", {})
    temporal_behavior=temporal.get("behavior_title", "Comportamiento semanal")
    temporal_heading=temporal.get("table_heading", "Semana")
    temporal_suffix=temporal.get("chart_suffix", "por semana")
    temporal_hint=temporal.get("hint", "S1=1-7 · S2=8-14 · S3=15-21 · S4=22-28 · S5=29-fin de mes")
    data_warnings_html="".join(
        insight("⚠️","insight-warn",f'<b>Dato faltante:</b> {warning}')
        for warning in warnings
    )

    # ── Sección 1: Cotizaciones ──────────────────────────────────────────
    temporal_cot=m1.get("temporal_cot", {})
    temporal_cot_periods=temporal_cot.get("periodos", [])
    sem_rows="".join(f"<tr><td>{d['etiqueta']}</td><td>{int(d['n'])}</td><td>{p(d['m'])}</td><td>{int(d['na'])}</td><td>{p(d['ma'])}</td><td>{d['na']/d['n']:.1%}</td><td>{d['ma']/d['m']:.1%}</td></tr>" if d["n"] and d["m"] else f"<tr><td>{d['etiqueta']}</td><td>0</td><td>$0</td><td>0</td><td>$0</td><td>0%</td><td>0%</td></tr>" for d in temporal_cot_periods)
    est_rows="".join(f"<tr><td>{e}</td><td>{d['n']}</td><td>{p(d['m'])}</td><td>{pct(d['n'],m1['n_cot'])}</td><td>{pct(d['m'],m1['tot_cot'])}</td></tr>" for e,d in sorted(m1["est_cot"].items(),key=lambda x:-x[1]["m"]))
    cli_cot_rows="".join(f"<tr><td>{c}</td><td>{d['n']}</td><td>{p(d['m'])}</td></tr>" for c,d in m1["top_cli_cot"])
    cli_apr_rows="".join(f"<tr><td>{c}</td><td>{d['n']}</td><td>{p(d['m'])}</td></tr>" for c,d in m1["top_cli_apr"])
    tip_rows="".join(f"<tr><td>{tp}</td><td>{d['n']}</td><td>{p(d['m'])}</td><td>{pct(d['m'],m1['tot_cot'])}</td></tr>" for tp,d in sorted(m1["tip_cot"].items(),key=lambda x:-x[1]["m"]))
    apr_rng_rows="".join(f"<tr><td>{r}</td><td>{c}</td><td>{pct(c,m1['n_apr'])}</td></tr>" for r,c in m1["rangos_apr"].items())
    rol_rows="".join(f"<tr><td>{rol}</td><td>{d['n']}</td><td>{p(d['m'])}</td><td>{d['na']}</td><td>{p(d['ma'])}</td><td>{pct(d['ma'],d['m']) if d['m'] else '0%'}</td></tr>" for rol,d in sorted(m1["rol_cot"].items(),key=lambda x:-x[1]["m"]))

    sindefi=m1["tip_cot"].get("Sin definir",{"n":0,"m":0})
    warn_tip=insight("⚠️","insight-warn",f'El <b>{pct(sindefi["n"],m1["n_cot"])}</b> de las cotizaciones no tiene tipo de pago marcado — sin este dato no se puede analizar el mix comercial real.') if sindefi["n"]/m1["n_cot"]>0.5 else ""

    sec1=f"""
<section class="sec">
<h2 class="sec-title">🟢 Módulo 1 · Ventas (Cotizaciones)</h2>
<p class="section-intro">Una <b>cotización</b> es la propuesta de precio que RTB envía al cliente antes de confirmar la venta. Solo cuando el cliente la aprueba se convierte en pedido. El análisis aquí cubre las cotizaciones <em>creadas</em> en {period_month} — su monto cotizado, cuántas se aprobaron y a qué velocidad.</p>
<div class="kpi-mini-row">
{mini("Total cotizaciones",str(m1["n_cot"]))}
{mini("Total cotizado c/IVA",p(m1["tot_cot"]))}
{mini("Aprobadas (qty)",f"{m1['n_apr']} ({m1['conv_q']:.1%})")}
{mini("Monto aprobado c/IVA",p(m1["mon_apr"]))}
{mini("Conv. en monto",f"{m1['conv_m']:.1%}")}
{mini("Ticket prom. cotizado",p(m1["ticket_cot"]))}
{mini("Ticket prom. aprobado",p(m1["ticket_apr"]))}
{mini("Ariba (Posadas)",f"{m1['n_ariba']} · {pct(m1['n_ariba'],m1['n_cot'])}")}
</div>
<div class="grid-2">
<div>
<h3 class="sub">1.1 Por estado</h3>
<p class="hint">Estado final de la cotización al exportar. <b>Aprobada</b> = cliente confirmó. <b>Expirada</b> = se venció el plazo sin respuesta. <b>Cancelada/Rechazada</b> = descartada explícitamente.</p>
<table class="t"><thead><tr><th>Estado</th><th>Qty</th><th>Monto c/IVA</th><th>% qty</th><th>% monto</th></tr></thead><tbody>{est_rows}</tbody></table>
{chart_box("chart_estados","Distribución por monto",140)}
</div>
<div>
<h3 class="sub">1.2 {temporal_behavior}</h3>
<p class="hint">{temporal_hint}</p>
{chart_box("chart_cot_sem",f"Cotizado vs Aprobado {temporal_suffix}",160)}
<table class="t"><thead><tr><th>{temporal_heading}</th><th>Cot.</th><th>Monto cot.</th><th>Apr.</th><th>Monto apr.</th><th>Conv.qty</th><th>Conv.monto</th></tr></thead><tbody>{sem_rows}</tbody></table>
</div>
</div>
<div class="grid-2">
<div>
<h3 class="sub">1.3 Top 10 — más cotizan</h3>
<table class="t"><thead><tr><th>Cliente</th><th>Cot.</th><th>Monto c/IVA</th></tr></thead><tbody>{cli_cot_rows}</tbody></table>
</div>
<div>
<h3 class="sub">1.4 Top 10 — más compran (aprobadas)</h3>
<table class="t"><thead><tr><th>Cliente</th><th>Apr.</th><th>Monto c/IVA</th></tr></thead><tbody>{cli_apr_rows}</tbody></table>
</div>
</div>
<div class="grid-2">
<div>
<h3 class="sub">1.5 Tipos de pago en cotizaciones</h3>
<p class="hint">"Sin definir" significa que el campo quedó vacío al crear la cotización en Notion.</p>
<table class="t"><thead><tr><th>Tipo pago</th><th>Qty</th><th>Monto</th><th>% monto</th></tr></thead><tbody>{tip_rows}</tbody></table>
{warn_tip}
</div>
<div>
<h3 class="sub">1.6 Tiempos de aprobación</h3>
<p class="hint">Días desde que se envía la cotización hasta que el cliente la aprueba. Solo aplica a cotizaciones aprobadas ({m1['n_apr']}).</p>
<div class="kpi-mini-row">{mini("Promedio",f"{m1['t_apr_avg']:.1f} días")}{mini("Mediana",f"{m1['t_apr_med']:.0f} días")}{mini("Máximo",f"{m1['t_apr_max']:.0f} días")}</div>
<table class="t"><thead><tr><th>Rango</th><th>Cantidad</th><th>%</th></tr></thead><tbody>{apr_rng_rows}</tbody></table>
{chart_box("chart_apr_rng","Distribución tiempos de aprobación",120)}
</div>
</div>
<h3 class="sub">1.7 Local vs Foráneo</h3>
<p class="hint"><b>Local</b> = CDMX / zona metro. <b>Foráneo</b> = otro estado — implica envío y más días de entrega.</p>
<table class="t"><thead><tr><th>Rol</th><th>Cot.</th><th>Monto cot.</th><th>Apr.</th><th>Monto apr.</th><th>Conv. monto</th></tr></thead><tbody>{rol_rows}</tbody></table>
<h3 class="sub">1.8 Ariba (Grupo Posadas vía SAP Ariba)</h3>
<p class="hint"><b>Ariba</b> es la plataforma de compras corporativas de Grupo Posadas (hoteles Fiesta Americana, Live Aqua, etc.). Las órdenes generadas en Ariba tienen proceso más largo pero garantizan el pago mediante PO formal.</p>
<div class="kpi-mini-row">{mini("Cotizaciones Ariba",f"{m1['n_ariba']} ({pct(m1['n_ariba'],m1['n_cot'])})")}{mini("Monto Ariba",f"{p(m1['m_ariba'])} ({pct(m1['m_ariba'],m1['tot_cot'])})")}</div>
</section>
"""

    # ── Sección 2: Pedidos/Almacén ────────────────────────────────────────
    rol_ped=m2a["rol_ped"]
    rol_rows2="".join(f"<tr><td>{rol}</td><td>{d['n']}</td><td>{p(d['sub'])}</td><td>{p(d['tot'])}</td></tr>" for rol,d in sorted(rol_ped.items(),key=lambda x:-x[1]["tot"]))
    est_ped_rows="".join(f"<tr><td>{e}</td><td>{d['n']}</td><td>{p(d['m'])}</td></tr>" for e,d in sorted(m2a["est_ped"].items(),key=lambda x:-x[1]["m"]))
    est_fac_rows="".join(f"<tr><td>{e}</td><td>{d['n']}</td><td>{p(d['m'])}</td></tr>" for e,d in sorted(m2a["est_fac"].items(),key=lambda x:-x[1]["m"]))
    stat_fac_rows="".join(f"<tr><td>{e}</td><td>{d['n']}</td><td>{p(d['m'])}</td></tr>" for e,d in sorted(m2a["stat_fac"].items(),key=lambda x:-x[1]["m"]))
    temporal_ped_periods=m2a.get("temporal_ped", {}).get("periodos", [])
    sem_ped_rows="".join(f"<tr><td>{d['etiqueta']}</td><td>{int(d['n'])}</td><td>{p(d['m'])}</td></tr>" for d in temporal_ped_periods)
    cli_ped_rows="".join(f"<tr><td>{c}</td><td>{d['n']}</td><td>{p(d['m'])}</td></tr>" for c,d in m2a["top_cli_ped"])
    prep_rows="".join(f"<tr><td>{r}</td><td>{c}</td><td>{pct(c,len([v for v in [m2a['t_prep_avg']] if v]))}</td></tr>" for r,c in m2a["rangos_prep"].items())
    rng_prep="".join(f"<tr><td>{r}</td><td>{c}</td></tr>" for r,c in m2a["rangos_prep"].items())
    rng_ent="".join(f"<tr><td>{r}</td><td>{c}</td></tr>" for r,c in m2a["rangos_ent"].items())
    cli_env_rows="".join(f"<tr><td>{c}</td><td>{d['n']}</td><td>{p(d['m'])}</td></tr>" for c,d in m2b["top_cli_env"])
    tp_pag_rows="".join(f"<tr><td>{tp}</td><td>{d['n']}</td><td>{p(d['m'])}</td><td>{pct(d['m'],m2d['tot_pag'])}</td></tr>" for tp,d in sorted(m2d["tp_pag"].items(),key=lambda x:-x[1]["m"]))
    cli_pag_rows="".join(f"<tr><td>{c}</td><td>{d['n']}</td><td>{p(d['m'])}</td></tr>" for c,d in m2d["top_cli_pag"])
    pago_rng_rows="".join(f"<tr><td>{r}</td><td>{c}</td></tr>" for r,c in m2d["rangos_pago"].items())

    sin_fac=m2a["sin_factura"]; sin_ent=m2a["sin_entregar"]
    sin_fac_rows="".join(f"<tr><td>{r.get('nombre','?')[:35]}</td><td>{r.get('cliente','?')}</td><td>{p(f(r.get('property_total_formula','0')))}</td></tr>" for r in sin_fac[:5]) if sin_fac else "<tr><td colspan='3'>Ninguno</td></tr>"
    sin_ent_rows="".join(f"<tr><td>{r.get('nombre','?')[:35]}</td><td>{r.get('cliente','?')}</td><td>{r.get('estado_pedido','?')}</td><td>{p(f(r.get('property_total_formula','0')))}</td></tr>" for r in sin_ent[:8]) if sin_ent else "<tr><td colspan='4'>Ninguno</td></tr>"

    eff_ent=m2b["n_100"]/m2b["n_env"]*100 if m2b["n_env"] else 0
    pct_2=m2a["n_ent_2"]/len([1 for _ in [m2a["t_ent_avg"]] if True]) if True else 0

    sec2=f"""
<section class="sec">
<h2 class="sec-title">🟡 Módulo 2 · Almacén / Logística / Facturación / Cobros</h2>
<h3 class="sub">2.A Pedidos creados en el mes</h3>
<p class="hint">Pedidos cuya <b>fecha de creación</b> cae en {period_label}. Un pedido es una cotización aprobada que ya entró al proceso de preparación y entrega.</p>
<div class="kpi-mini-row">
{mini("Pedidos",str(m2a["n_ped"]))}{mini("Subtotal",p(m2a["sub_ped"]))}{mini("Total c/IVA",p(m2a["tot_ped"]))}{mini("Con faltante",f"{m2a['n_falt']} ({pct(m2a['n_falt'],m2a['n_ped'])})")}{mini("Sin factura (NR sin facturar)",str(len(sin_fac)))}{mini("Facturados sin entregar",str(len(sin_ent)))}
</div>
<div class="grid-2">
<div><h4 class="sub-sm">Local vs Foráneo</h4><table class="t"><thead><tr><th>Rol</th><th>Pedidos</th><th>Subtotal</th><th>Total c/IVA</th></tr></thead><tbody>{rol_rows2}</tbody></table></div>
<div>
<h4 class="sub-sm">Estado del pedido</h4>
<table class="t"><thead><tr><th>Estado</th><th>Qty</th><th>Monto</th></tr></thead><tbody>{est_ped_rows}</tbody></table>
</div>
</div>
<div class="grid-2">
<div><h4 class="sub-sm">Estado de factura</h4><table class="t"><thead><tr><th>Estado</th><th>Qty</th><th>Monto</th></tr></thead><tbody>{est_fac_rows}</tbody></table></div>
<div><h4 class="sub-sm">Status de factura</h4>
<p class="hint"><b>Impresa</b> = factura generada pero no enviada al cliente. <b>Entregada</b> = el cliente la recibió físicamente/digital.</p>
<table class="t"><thead><tr><th>Status</th><th>Qty</th><th>Monto</th></tr></thead><tbody>{stat_fac_rows}</tbody></table></div>
</div>
<h4 class="sub-sm">{temporal_behavior}</h4>
{chart_box("chart_ped_sem",f"Pedidos creados {temporal_suffix}",100)}
<table class="t"><thead><tr><th>{temporal_heading}</th><th>Pedidos</th><th>Monto</th></tr></thead><tbody>{sem_ped_rows}</tbody></table>
<h4 class="sub-sm">Top 10 clientes (pedidos creados)</h4>
<table class="t"><thead><tr><th>Cliente</th><th>Pedidos</th><th>Monto c/IVA</th></tr></thead><tbody>{cli_ped_rows}</tbody></table>

<h3 class="sub">2.B Tiempos de Preparación</h3>
<p class="hint">Días desde que se crea el pedido hasta que el equipo de almacén lo deja listo para salida. <b>Incluye:</b> surtido de piezas, empaque, generación de NR (Nota de Remisión). <b>Meta sugerida:</b> ≤3 días para locales, ≤5 para foráneos.</p>
<div class="kpi-mini-row">{mini("Promedio",f"{m2a['t_prep_avg']:.1f} días")}{mini("Mediana",f"{m2a['t_prep_med']:.0f} días")}{mini("Máximo",f"{m2a['t_prep_max']:.0f} días")}</div>
<div class="grid-2">
<div>
{chart_box("chart_dias_prep","Distribución días de preparación",140)}
</div>
<div>
<table class="t"><thead><tr><th>Rango preparación</th><th>Pedidos</th></tr></thead><tbody>{rng_prep}</tbody></table>
</div>
</div>

<h3 class="sub">2.C Tiempos de Entrega</h3>
<p class="hint">Días desde que el pedido sale del almacén hasta que llega al cliente. Para <b>foráneos</b> incluye el tiempo de tránsito de la paquetería. Para <b>locales</b> suele ser el mismo día o al siguiente.</p>
<div class="kpi-mini-row">{mini("Promedio",f"{m2a['t_ent_avg']:.1f} días")}{mini("Mediana",f"{m2a['t_ent_med']:.0f} días")}{mini("Máximo",f"{m2a['t_ent_max']:.0f} días")}{mini("Entregados ≤2 días",str(m2a["n_ent_2"]))}{mini("Entregados ≤5 días",str(m2a["n_ent_5"]))}{mini("Entregados ≤7 días",str(m2a["n_ent_7"]))}</div>
<div class="grid-2">
<div>{chart_box("chart_dias_ent","Distribución días de entrega",140)}</div>
<div><table class="t"><thead><tr><th>Rango entrega</th><th>Pedidos</th></tr></thead><tbody>{rng_ent}</tbody></table></div>
</div>

<h3 class="sub">2.D Ciclo de Facturación Completo</h3>
<p class="hint">El ciclo de vida de una venta inicia cuando se crea el pedido y termina cuando el pago queda asociado formalmente al CFDI. <b>Pedido→Facturado</b>: tiempo de preparación hasta emitir la factura. <b>Facturado→Validado</b>: el cliente revisa y confirma la factura. <b>Validado→Asociado</b>: se vincula el pago con el complemento de pago SAT.</p>
{chart_box("chart_ciclo","Promedio de días por etapa del ciclo",100)}
<table class="t"><thead><tr><th>Etapa</th><th>Promedio</th><th>Mediana</th><th>Máximo</th><th>N</th></tr></thead><tbody>
<tr><td>Pedido → Facturado</td><td>{m2a['ciclo_pf_avg']:.1f} días</td><td>{m2a['ciclo_pf_med']:.0f} días</td><td>{m2a['ciclo_pf_max']:.0f} días</td><td>{m2a['n_ciclo_pf']}</td></tr>
<tr><td>Facturado → Validado</td><td>{m2a['ciclo_fv_avg']:.1f} días</td><td>{m2a['ciclo_fv_med']:.0f} días</td><td>{m2a['ciclo_fv_max']:.0f} días</td><td>{m2a['n_ciclo_fv']}</td></tr>
<tr><td>Validado → Asociado</td><td>{m2a['ciclo_va_avg']:.1f} días</td><td>{m2a['ciclo_va_med']:.0f} días</td><td>{m2a['ciclo_va_max']:.0f} días</td><td>{m2a['n_ciclo_va']}</td></tr>
<tr><td><b>Ciclo total</b></td><td><b>{m2a['ciclo_tot_avg']:.1f} días</b></td><td>{m2a['ciclo_tot_med']:.0f} días</td><td>{m2a['ciclo_tot_max']:.0f} días</td><td>{m2a['n_ciclo_tot']}</td></tr>
</tbody></table>

<div class="grid-2">
<div>
<h4 class="sub-sm">Pedidos entregados con NR pero sin factura</h4>
<p class="hint">Pedidos físicamente entregados (con Nota de Remisión) pero que aún no tienen CFDI emitido — estado "En espera" de factura.</p>
<div class="kpi-mini-row">{mini("Pendientes",f"{len(sin_fac)} pedidos")}</div>
<table class="t"><thead><tr><th>Pedido</th><th>Cliente</th><th>Monto</th></tr></thead><tbody>{sin_fac_rows}</tbody></table>
</div>
<div>
<h4 class="sub-sm">Pedidos facturados pero NO entregados</h4>
<p class="hint">Se emitió el CFDI pero la mercancía aún no salió del almacén. Riesgo: el cliente podría reclamar que facturamos algo no entregado.</p>
<div class="kpi-mini-row">{mini("En riesgo",f"{len(sin_ent)} pedidos · {p(sum(f(r.get('property_total_formula','0')) for r in sin_ent))}")}</div>
<table class="t"><thead><tr><th>Pedido</th><th>Cliente</th><th>Estado</th><th>Monto</th></tr></thead><tbody>{sin_ent_rows}</tbody></table>
</div>
</div>

<h3 class="sub">2.E Pedidos entregados en el mes (cualquier origen)</h3>
<p class="hint">Incluye pedidos creados en meses anteriores que se entregaron en {period_month}. Por eso puede ser mayor al número de pedidos creados en el mes.</p>
<div class="kpi-mini-row">{mini("Total entregados",str(m2b["n_env"]))}{mini("Monto entregado",p(m2b["tot_env"]))}{mini("Con faltante",f"{m2b['n_env_falt']} ({pct(m2b['n_env_falt'],m2b['n_env'])})")}{mini("Completados 100%",str(m2b["n_100"]))}{mini("Tiempo entrega prom.",f"{m2b['t_env_avg']:.1f} días")}</div>
<h4 class="sub-sm">Top 10 clientes con entregas</h4>
<table class="t"><thead><tr><th>Cliente</th><th>Entregas</th><th>Monto</th></tr></thead><tbody>{cli_env_rows}</tbody></table>

<h3 class="sub">2.F Facturación del mes</h3>
<div class="kpi-mini-row">{mini(f"Primaria (fecha en {period_month})",f"{m2c['n_fac']} · {p(m2c['tot_fac'])}")}{mini("Secundaria (refacturaciones)",f"{m2c['n_facs']} · {p(m2c['mon_2da'])}")}{mini(f"TOTAL facturado {period_month}",p(m2c["tot_facturacion"]))}</div>
{insight("📌","insight-info","Sin archivo Excel maestro (VENTAS_2026.xlsx) en esta corrida — no se ejecutó el módulo de cruce Excel ↔ Notion. Para activarlo adjunta el Excel en la próxima corrida.")}

<h3 class="sub">2.G Ingresos cobrados y tiempos de pago</h3>
<p class="hint"><b>Tiempo de pago:</b> días desde que se emite la factura hasta que el cliente realiza el pago. Un tiempo alto indica clientes que pagan a crédito largo o retraso en cobranza activa.</p>
<div class="kpi-mini-row">{mini("Pedidos cobrados",str(m2d["n_pag"]))}{mini("Subtotal cobrado",p(m2d["sub_pag"]))}{mini("Total c/IVA cobrado",p(m2d["tot_pag"]))}{mini("Prom. días pago",f"{m2d['t_pago_avg']:.1f}")}{mini("Mediana días pago",f"{m2d['t_pago_med']:.0f}")}{mini("CxC estimada",p(m2d["cxc_est"]))}</div>
<div class="grid-2">
<div>
{chart_box("chart_dias_pago","Distribución días factura→pago",140)}
<table class="t"><thead><tr><th>Rango días pago</th><th>Pedidos</th></tr></thead><tbody>{pago_rng_rows}</tbody></table>
</div>
<div>
<h4 class="sub-sm">Tipos de pago utilizados</h4>
<table class="t"><thead><tr><th>Tipo</th><th>Pedidos</th><th>Monto c/IVA</th><th>%</th></tr></thead><tbody>{tp_pag_rows}</tbody></table>
{chart_box("chart_tp_pag","Ingresos por tipo de pago",120)}
</div>
</div>
<h4 class="sub-sm">Top 10 clientes que pagaron</h4>
<table class="t"><thead><tr><th>Cliente</th><th>Pagos</th><th>Monto</th></tr></thead><tbody>{cli_pag_rows}</tbody></table>
</section>
"""

    # ── Sección 3: Compras ────────────────────────────────────────────────
    sp_rows="".join(f"<tr><td>{sp}</td><td>{d['n']}</td><td>{p(d['m'])}</td><td>{pct(d['m'],m3['tot_fc'])}</td></tr>" for sp,d in sorted(m3["sp_fc"].items(),key=lambda x:-x[1]["m"]))
    tp_fc_rows="".join(f"<tr><td>{tp}</td><td>{d['n']}</td><td>{p(d['m'])}</td><td>{pct(d['n'],m3['n_fc'])}</td><td>{pct(d['m'],m3['tot_fc'])}</td></tr>" for tp,d in sorted(m3["tp_fc"].items(),key=lambda x:-x[1]["m"]))
    prov_rows="".join(f"<tr><td>{pv}</td><td>{d['n']}</td><td>{p(d['sub'])}</td><td>{p(d['tot'])}</td></tr>" for pv,d in m3["top_prov"])
    cred_rows="".join(f"<tr><td>{pv}</td><td>{d['n']}</td><td>{p(d['m'])}</td></tr>" for pv,d in m3["cred_vivo"])
    tp_fcp_rows="".join(f"<tr><td>{tp}</td><td>{d['n']}</td><td>{p(d['m'])}</td></tr>" for tp,d in sorted(m3["tp_fcp"].items(),key=lambda x:-x[1]["m"]))
    prov_pag_rows="".join(f"<tr><td>{pv}</td><td>{d['n']}</td><td>{p(d['m'])}</td></tr>" for pv,d in m3["top_prov_pag"])
    cfdi_rows="".join(f"<tr><td>{c}</td><td>{d['n']}</td><td>{p(d['m'])}</td></tr>" for c,d in sorted(m3["cfdi_fc"].items(),key=lambda x:-x[1]["m"]))
    temporal_fc_periods=m3.get("temporal_fc", {}).get("periodos", [])
    sem_fc_rows="".join(f"<tr><td>{d['etiqueta']}</td><td>{int(d['n'])}</td><td>{p(d['sub'])}</td><td>{p(d['tot'])}</td></tr>" for d in temporal_fc_periods)

    por_def=m3["tp_fc"].get("99 por definir",{"m":0,"n":0})
    warn_99=insight("⚠️","insight-warn",f'{por_def["n"]} facturas ({pct(por_def["n"],m3["n_fc"])} qty, <b>{pct(por_def["m"],m3["tot_fc"])}</b> monto) con tipo de pago <code>99 por definir</code>. Cerrar antes del siguiente cierre.') if por_def["m"]/m3["tot_fc"]>0.05 else ""

    sec3=f"""
<section class="sec">
<h2 class="sec-title">🔵 Módulo 3 · Compras</h2>
<p class="section-intro">Análisis de las facturas de compra a proveedores cuya <b>fecha de factura</b> cae en {period_label}, y de los pagos efectivamente realizados a proveedores durante el mes (que pueden incluir facturas de meses anteriores).</p>
<div class="kpi-mini-row">{mini("Facturas activas",str(m3["n_fc"]))}{mini("Subtotal",p(m3["sub_fc"]))}{mini("IVA 16%",p(m3["iva_fc"]))}{mini("Total c/IVA",p(m3["tot_fc"]))}{mini("Costo envío",p(m3["env_fc"]))}</div>
<h3 class="sub">3.1 {temporal_behavior}</h3>
{chart_box("chart_compras_sem",f"Compras {temporal_suffix}",100)}
<table class="t"><thead><tr><th>{temporal_heading}</th><th>Facturas</th><th>Subtotal</th><th>Total c/IVA</th></tr></thead><tbody>{sem_fc_rows}</tbody></table>
<div class="grid-2">
<div>
<h3 class="sub">3.2 Status de pago</h3>
<table class="t"><thead><tr><th>Status</th><th>Facturas</th><th>Monto</th><th>%</th></tr></thead><tbody>{sp_rows}</tbody></table>
{chart_box("chart_sp","Status de pago (monto)",140)}
</div>
<div>
<h3 class="sub">3.3 Tipos de pago</h3>
<p class="hint"><b>99 por definir</b> = tipo de pago no especificado. <b>3 Transferencia</b> = SPEI. <b>28 Tarjeta de débito</b> = pago con tarjeta física.</p>
<table class="t"><thead><tr><th>Tipo pago</th><th>Qty</th><th>Monto</th><th>% qty</th><th>% monto</th></tr></thead><tbody>{tp_fc_rows}</tbody></table>
{warn_99}
</div>
</div>
<h3 class="sub">3.4 Top 10 proveedores</h3>
<table class="t"><thead><tr><th>Proveedor</th><th>Facturas</th><th>Subtotal</th><th>Total c/IVA</th></tr></thead><tbody>{prov_rows}</tbody></table>
<div class="grid-2">
<div>
<h3 class="sub">3.5 Crédito vivo con proveedores</h3>
<p class="hint">Facturas del mes con status "No Pagado" — lo que RTB aún debe a proveedores al cierre de {period_month}.</p>
<div class="kpi-mini-row">{mini("Facturas pendientes",str(m3["n_no_pag"]))}{mini("Monto adeudado",p(m3["cxp"]))}</div>
<table class="t"><thead><tr><th>Proveedor</th><th>Facturas</th><th>Monto adeudado</th></tr></thead><tbody>{cred_rows}</tbody></table>
</div>
<div>
<h3 class="sub">3.6 Pagos efectivos a proveedores</h3>
<p class="hint">Facturas en FACTURAS_COMPRAS_PAGADAS — pueden incluir facturas de meses anteriores pagadas en {period_month}.</p>
<div class="kpi-mini-row">{mini("Total pagado",p(m3["tot_fcp"]))}{mini("Facturas",str(m3["n_fcp"]))}{mini("Prom días pago",f"{m3['t_fc_pago_avg']:.1f}")}</div>
<table class="t"><thead><tr><th>Tipo pago</th><th>Facturas</th><th>Monto</th></tr></thead><tbody>{tp_fcp_rows}</tbody></table>
</div>
</div>
<h3 class="sub">3.7 Top 10 proveedores pagados</h3>
<table class="t"><thead><tr><th>Proveedor</th><th>Pagos</th><th>Monto</th></tr></thead><tbody>{prov_pag_rows}</tbody></table>
<h3 class="sub">3.8 Uso CFDI</h3>
<p class="hint"><b>CFDI (Comprobante Fiscal Digital por Internet)</b> es la factura electrónica del SAT. El uso indica la naturaleza del gasto. <b>G01</b> = adquisición de mercancías (inventario). <b>G03</b> = gastos en general. El SAT los usa para clasificar deducciones.</p>
<table class="t"><thead><tr><th>Uso CFDI</th><th>Facturas</th><th>Monto</th></tr></thead><tbody>{cfdi_rows}</tbody></table>
</section>
"""

    # ── Sección 4: Inventario ─────────────────────────────────────────────
    snap_rows=""; prev_tot=None
    for mes in ["Febrero","Marzo","Abril","Mayo"]:
        d=snaps[mes]
        delta=f"{(d['total']-prev_tot)/prev_tot*100:+.1f}%" if prev_tot else "—"
        bold="" if mes!="Abril" else "style='font-weight:700;color:var(--accent)'"
        snap_rows+=f"<tr {bold}><td>{mes} 2026</td><td>{p(d['total'])}</td><td>{p(d['inmov'])}</td><td>{pct(d['inmov'],d['total'])}</td><td>{p(d['activo'])}</td><td>{delta}</td></tr>"
        prev_tot=d["total"]

    top_sal_rows="".join(f"<tr><td>{r.get('property_sku','?')}</td><td>{int(float(r.get('property_salida_real_final','0')))}</td><td>{r.get('name','')[:35]}</td></tr>" for r in m4["top_sal"])
    sal_val_rows="".join(f"<tr><td>{sv['sku']}</td><td>{int(sv['qty'])}</td><td>{p(sv['cost_unit'])}</td><td>{p(sv['valor'])}</td></tr>" for sv in m4["salidas_valor"])
    top_ent_rows="".join(f"<tr><td>{r.get('property_sku.0','?')}</td><td>{int(float(r.get('property_erf','0')))}</td><td>{r.get('name','')[:35]}</td></tr>" for r in m4["top_ent"])
    top_inv_rows="".join(f"<tr><td>{r.get('property_sku_f','?')}</td><td>{r.get('property_cantidad_real_en_inventario','')}</td><td>{p(float(r.get('property_costo_total_en_stock','0') or 0))}</td><td>{r.get('name','')[:40]}</td></tr>" for r in m4["top_inv"])
    sa=snaps["Abril"]

    sec4=f"""
<section class="sec">
<h2 class="sec-title">🟣 Módulo 4 · Inventario</h2>
<div class="callout"><b>Regla de lectura aplicada:</b> El "inmovilizado" es un <b>subconjunto</b> del inventario total, no una métrica paralela. Si stock=$X e inmovilizado=$Y → $X−$Y <em>rotó</em> (tuvo al menos una salida en el mes) · $Y no tuvo ninguna salida. <b>No se suman.</b></div>
<div class="grid-2">
<div>
<h3 class="sub">4.1 Snapshot oficial Abril 2026</h3>
<p class="hint">Cifras del registro "Inventario Abril 2026" en CRECIMIENTO_INVENTARIO — snapshot tomado al 30-abr-2026 23:02h.</p>
<table class="t"><thead><tr><th>Métrica</th><th>Valor</th><th>% del stock</th></tr></thead><tbody>
<tr><td><b>Stock total vigente</b></td><td><b>{p(sa["total"])}</b></td><td>100.0%</td></tr>
<tr><td>Con rotación en el mes</td><td>{p(sa["activo"])}</td><td>{pct(sa["activo"],sa["total"])}</td></tr>
<tr><td><b>Inmovilizado (sin movimiento)</b></td><td><b>{p(sa["inmov"])}</b></td><td><b>{pct(sa["inmov"],sa["total"])}</b></td></tr>
</tbody></table>
</div>
<div>{chart_box("chart_inv_donut","Stock vigente Abril 2026",200)}</div>
</div>
<h3 class="sub">4.2 Comparativa histórica</h3>
{chart_box("chart_inv_hist","Evolución inventario total vs inmovilizado",100)}
<table class="t"><thead><tr><th>Mes</th><th>Stock total</th><th>Inmovilizado</th><th>% inmov.</th><th>Activo</th><th>Δ stock vs anterior</th></tr></thead><tbody>{snap_rows}</tbody></table>
{insight("🚨","insight-alert",f'El inventario inmovilizado pasó de <b>{p(snaps["Marzo"]["inmov"])} ({pct(snaps["Marzo"]["inmov"],snaps["Marzo"]["total"])} en marzo)</b> a <b>{p(sa["inmov"])} ({sa["pct_inmov"]:.1%} en abril)</b> — crecimiento de <b>{sa["inmov"]/snaps["Marzo"]["inmov"]:.1f}x</b> en un solo mes. El stock total bajó −51.8% pero el remanente sin rotar se volvió dominante.')}

<h3 class="sub">4.3 Movimientos del mes</h3>
<div class="kpi-mini-row">{mini("Salidas totales",f"{m4['total_sal_piezas']:.0f} piezas en {m4['n_skus_sal']} SKUs")}{mini("Entradas totales",f"{m4['total_ent_piezas']:.0f} piezas")}{mini("SKUs en stock",str(m4["n_en"]))}{mini("SKUs sin stock (agotados)",str(m4["n_sin"]))}</div>
<div class="grid-2">
<div>
<h3 class="sub">4.4 Top 10 salidas — cantidad</h3>
<table class="t"><thead><tr><th>SKU</th><th>Piezas</th><th>Nombre</th></tr></thead><tbody>{top_sal_rows}</tbody></table>
</div>
<div>
<h3 class="sub">4.5 Top 10 salidas — valor estimado</h3>
<p class="hint">Valor = piezas × costo unitario del inventario actual. Algunos SKUs muestran $0 si no tienen costo registrado en INVENTARIO_REAL_ACTUAL.</p>
<table class="t"><thead><tr><th>SKU</th><th>Piezas</th><th>Costo unit.</th><th>Valor salida</th></tr></thead><tbody>{sal_val_rows}</tbody></table>
</div>
</div>
<div class="grid-2">
<div>
<h3 class="sub">4.6 Top 10 entradas — cantidad</h3>
<table class="t"><thead><tr><th>SKU</th><th>Piezas</th><th>Nombre</th></tr></thead><tbody>{top_ent_rows}</tbody></table>
</div>
<div>
<h3 class="sub">4.7 Top 10 SKUs por valor de stock</h3>
<table class="t"><thead><tr><th>SKU</th><th>Cant.</th><th>Valor</th><th>Nombre</th></tr></thead><tbody>{top_inv_rows}</tbody></table>
</div>
</div>
</section>
"""

    # ── Sección 5: Gastos ─────────────────────────────────────────────────
    cat_rows="".join(f"<tr><td>{cat}</td><td>{d['n']}</td><td>{p(d['m'])}</td><td>{pct(d['m'],m5['tot_gas'])}</td></tr>" for cat,d in sorted(m5["cat_gas"].items(),key=lambda x:-x[1]["m"]))
    mp_rows="".join(f"<tr><td>{mp}</td><td>{d['n']}</td><td>{p(d['m'])}</td><td>{pct(d['m'],m5['tot_gas'])}</td></tr>" for mp,d in sorted(m5["mp_gas"].items(),key=lambda x:-x[1]["m"]))
    temporal_gas_periods=m5.get("temporal_gas", {}).get("periodos", [])
    sem_gas_rows="".join(f"<tr><td>{d['etiqueta']}</td><td>{int(d['n'])}</td><td>{p(d['m'])}</td><td>{pct(d['m'],m5['tot_gas'])}</td></tr>" for d in temporal_gas_periods)
    fiscal_rows="".join(f"<tr><td>{x['concepto'][:50]}</td><td>{p(x['total'])}</td><td>{x.get('folio','')}</td></tr>" for x in m5["carga_fiscal"])
    conc_rows="".join(f"<tr><td>{conc}</td><td>{d['n']}</td><td>{p(d['m'])}</td></tr>" for conc,d in m5["top_conc"])
    resp_rows="".join(f"<tr><td>{resp}</td><td>{d['n']}</td><td>{p(d['m'])}</td><td>{pct(d['m'],m5['tot_gas'])}</td></tr>" for resp,d in m5["resp_gas"])

    otros_pct=m5["cat_gas"].get("Otros",{"m":0})["m"]/m5["tot_gas"] if m5["tot_gas"] else 0
    warn_otros=insight("🚨","insight-alert",f'La categoría <b>"Otros" representa el {otros_pct:.1%} del OPEX</b> (umbral de alerta: 40%). <b>{p(m5["tot_fiscal"])}</b> corresponden a <b>cargas fiscales acumuladas</b> que deberían tener categoría propia en Notion: <code>Impuestos / SAT</code>, <code>Seguridad Social</code>, <code>Intereses Financieros</code>.') if otros_pct>0.4 else ""
    warn_gas_missing="".join(
        insight("⚠️","insight-warn",f'<b>Dato faltante:</b> {warning}')
        for warning in warnings
        if "GASTOS_OPERATIVOS" in warning
    )

    sec5=f"""
<section class="sec">
<h2 class="sec-title">⚪ Módulo 5 · Gastos Operativos</h2>
<p class="section-intro">Gastos con <b>fecha en {period_label}</b> en estado "Realizado". El OPEX (<em>Operating Expenses</em>) son los costos de operar el negocio, distintos al costo directo de la mercancía vendida.</p>
{warn_gas_missing}
<div class="kpi-mini-row">{mini("OPEX total (Realizado)",p(m5["tot_gas"]))}{mini("Subtotal sin IVA",p(m5["sub_gas"]))}{mini("Registros realizados",str(m5["n_real"]))}{mini("Pendientes",str(m5["n_pend"]))}{mini("Deducibles",f"{p(m5['ded'])} ({m5['pct_ded']:.1%})")}{mini("No deducibles",p(m5["no_ded"]))}</div>
<div class="grid-2">
<div>
<h3 class="sub">5.1 Deducible vs No deducible</h3>
<p class="hint"><b>Deducible</b> = el SAT permite restarle el IVA o registrarlo como gasto fiscal. <b>No deducible</b> = no tiene beneficio fiscal (consumos sin factura, propinas, etc.).</p>
<table class="t"><thead><tr><th>Tipo</th><th>Qty</th><th>Monto</th><th>%</th></tr></thead><tbody>
<tr><td>Deducible</td><td>{m5["n_real"]-sum(1 for r in range(1) if True)}</td><td>{p(m5["ded"])}</td><td>{m5["pct_ded"]:.1%}</td></tr>
<tr><td>No deducible</td><td>—</td><td>{p(m5["no_ded"])}</td><td>{(1-m5["pct_ded"]):.1%}</td></tr>
</tbody></table>
<h3 class="sub">Por método de pago</h3>
<table class="t"><thead><tr><th>Método</th><th>Qty</th><th>Monto</th><th>%</th></tr></thead><tbody>{mp_rows}</tbody></table>
{chart_box("chart_mp","Métodos de pago OPEX",160)}
</div>
<div>
<h3 class="sub">5.2 Por categoría</h3>
{chart_box("chart_cat","OPEX por categoría",200)}
<table class="t"><thead><tr><th>Categoría</th><th>Qty</th><th>Monto</th><th>%</th></tr></thead><tbody>{cat_rows}</tbody></table>
{warn_otros}
</div>
</div>
{f'<h3 class="sub">5.3 Desglose de carga fiscal identificada — {p(m5["tot_fiscal"])}</h3><p class="hint">Gastos con palabras clave [DECLARACION, ISR, IVA, SIPARE, INTERESES] que corresponden a obligaciones fiscales de meses anteriores procesadas en {period_month}. Deberían tener categoría <code>Impuestos / SAT</code> en Notion.</p><table class="t"><thead><tr><th>Concepto</th><th>Total</th><th>Folio</th></tr></thead><tbody>{fiscal_rows}</tbody></table>' if m5["carga_fiscal"] else ""}
<h3 class="sub">5.4 {temporal_behavior}</h3>
{chart_box("chart_opex_sem",f"OPEX {temporal_suffix}",100)}
<table class="t"><thead><tr><th>{temporal_heading}</th><th>Registros</th><th>Monto</th><th>% total</th></tr></thead><tbody>{sem_gas_rows}</tbody></table>
{insight("⚠️","insight-warn",f'Si el último periodo concentra más del 40% del OPEX, revisar si hay cargas extraordinarias (declaraciones, pagos acumulados) que distorsionan el análisis.')}
<h3 class="sub">5.5 Con vs sin comprobante fiscal</h3>
<table class="t"><thead><tr><th>Tipo</th><th>Registros</th><th>Monto</th><th>%</th></tr></thead><tbody>
<tr><td>Con folio (comprobante fiscal)</td><td>{m5["con_folio"]}</td><td>{p(m5["mon_con_folio"])}</td><td>{pct(m5["mon_con_folio"],m5["tot_gas"])}</td></tr>
<tr><td>Sin folio (efectivo/sin factura)</td><td>{m5["sin_folio"]}</td><td>{p(m5["mon_sin_folio"])}</td><td>{pct(m5["mon_sin_folio"],m5["tot_gas"])}</td></tr>
</tbody></table>
<div class="grid-2">
<div><h3 class="sub">5.6 Top 10 conceptos</h3><table class="t"><thead><tr><th>Concepto</th><th>Qty</th><th>Monto</th></tr></thead><tbody>{conc_rows}</tbody></table></div>
<div><h3 class="sub">5.7 OPEX por responsable</h3><table class="t"><thead><tr><th>Responsable</th><th>Qty</th><th>Monto</th><th>%</th></tr></thead><tbody>{resp_rows}</tbody></table></div>
</div>
</section>
"""

    # ── Sección P&L ───────────────────────────────────────────────────────
    sec_pl=f"""
<section class="sec">
<h2 class="sec-title">📈 Dashboard Ejecutivo · P&amp;L y Flujo de Caja</h2>
<p class="section-intro"><b>P&amp;L (Profit & Loss)</b> = Estado de Resultados — muestra si el negocio generó utilidad. <b>Flujo de caja</b> = cuánto dinero realmente entró y salió del banco este mes, independientemente de cuándo se facturó.</p>
<div class="grid-2">
<div>
<h3 class="sub">P&amp;L Teórico (sin IVA)</h3>
<table class="t"><thead><tr><th>Línea</th><th>Monto</th><th>% vs ingresos</th></tr></thead><tbody>
<tr><td>(+) Ingresos cobrados (sub)</td><td><b>{p(pl["ing_sub"])}</b></td><td>100.0%</td></tr>
<tr><td>(−) Costo de compras (sub)</td><td>{p(pl["comp_sub"])}</td><td>{pct(pl["comp_sub"],pl["ing_sub"])}</td></tr>
<tr><td><b>= Margen bruto</b></td><td><b class="hl-good">{p(pl["margen"])}</b></td><td><b class="hl-good">+{pl["pct_margen"]:.1%}</b></td></tr>
<tr><td>(−) OPEX total (sub)</td><td>{p(pl["opex_sub"])}</td><td>{pct(pl["opex_sub"],pl["ing_sub"])}</td></tr>
<tr><td><b>= Utilidad teórica</b></td><td><b class="{'hl-good' if pl['utilidad']>=0 else 'hl-bad'}">{p(pl["utilidad"])}</b></td><td><b class="{'hl-good' if pl['utilidad']>=0 else 'hl-bad'}">{pl["pct_utilidad"]:+.1%}</b></td></tr>
</tbody></table>
</div>
<div>
<h3 class="sub">P&amp;L Ajustado (sin carga fiscal extraordinaria)</h3>
<p class="hint">Excluye las declaraciones acumuladas ({p(pl["tot_fiscal"])}) que son obligaciones de meses anteriores, no costos recurrentes de {period_label}.</p>
<table class="t"><thead><tr><th>Línea</th><th>Monto</th><th>%</th></tr></thead><tbody>
<tr><td>Margen bruto</td><td>{p(pl["margen"])}</td><td>+{pl["pct_margen"]:.1%}</td></tr>
<tr><td>OPEX recurrente (sin fiscal)</td><td>{p(pl["opex_recur"])}</td><td>{pct(pl["opex_recur"],pl["ing_sub"])}</td></tr>
<tr><td><b>Utilidad ajustada</b></td><td><b class="hl-good">{p(pl["utilidad_adj"])}</b></td><td><b class="hl-good">+{pl["pct_utilidad_adj"]:.1%}</b></td></tr>
</tbody></table>
</div>
</div>
<div class="grid-2">
<div>
<h3 class="sub">Flujo de Caja Real (c/IVA)</h3>
<table class="t"><thead><tr><th>Línea</th><th>Monto</th></tr></thead><tbody>
<tr><td>(+) Cobrado a clientes</td><td><b>{p(pl["flujo_cobrado"])}</b></td></tr>
<tr><td>(−) Pagado a proveedores</td><td>{p(pl["flujo_pagado_prov"])}</td></tr>
<tr><td>(−) OPEX pagado</td><td>{p(pl["flujo_opex"])}</td></tr>
<tr><td><b>= Flujo neto del mes</b></td><td><b class="hl-num">{p(pl["flujo_neto"])}</b></td></tr>
</tbody></table>
</div>
<div>
<h3 class="sub">Posición de Cartera al cierre</h3>
<table class="t"><thead><tr><th>Línea</th><th>Monto</th></tr></thead><tbody>
<tr><td>CxC — facturado no cobrado</td><td><b>{p(pl["cxc_total"])}</b></td></tr>
<tr><td>CxP — comprado no pagado</td><td>{p(pl["cxp_total"])}</td></tr>
<tr><td><b>Posición neta (CxC − CxP)</b></td><td><b class="hl-num">{p(pl["pos_neta"])}</b></td></tr>
</tbody></table>
</div>
</div>
{chart_box("chart_pl","P&L — Comparativa de líneas principales",100)}
</section>
"""

    # ── Hallazgos ─────────────────────────────────────────────────────────
    hallazgos=[]
    hallazgos.extend(f'<b>Dato faltante:</b> {warning}' for warning in warnings)
    pct_fiscal=m5["tot_fiscal"]/m5["tot_gas"] if m5["tot_gas"] else 0
    if pct_fiscal>0.5:
        hallazgos.append(f'<b>Carga fiscal extraordinaria distorsionó el OPEX:</b> {p(m5["tot_fiscal"])} ({pct_fiscal:.1%} del OPEX) corresponden a declaraciones acumuladas Dic 2025/Ene-Feb 2026. Sin este cargo, utilidad ajustada sería <b class="hl-good">{p(pl["utilidad_adj"])} (+{pl["pct_utilidad_adj"]:.1%})</b>.')
    sa=snaps["Abril"]; sm=snaps["Marzo"]
    if sa["pct_inmov"]>0.4:
        ratio=sa["inmov"]/sm["inmov"] if sm["inmov"] else 0
        hallazgos.append(f'<b>Inventario inmovilizado creció {ratio:.1f}x en un mes:</b> de {p(sm["inmov"])} ({sm["pct_inmov"]:.1%} en Marzo) a <b>{p(sa["inmov"])} ({sa["pct_inmov"]:.1%} en Abril)</b>. Aunque el stock total bajó −51.8%, el remanente sin rotar se volvió dominante.')
    if m2d["t_pago_med"]>60:
        hallazgos.append(f'<b>Cartera por cobrar abultada:</b> mediana de días pago = <b>{m2d["t_pago_med"]:.0f} días</b>. CxC estimada: <b>{p(m2d["cxc_est"])}</b>. Compromete el flujo del siguiente mes.')
    top_pv=m3["top_prov"][0] if m3["top_prov"] else ("?",{"tot":0,"n":0})
    if top_pv[1]["tot"]/m3["tot_fc"]>0.4:
        hallazgos.append(f'<b>Concentración en {top_pv[0]}:</b> {pct(top_pv[1]["tot"],m3["tot_fc"])} de las compras del mes provienen de un solo proveedor ({p(top_pv[1]["tot"])}). Además {m3["cred_vivo"][0][1]["n"] if m3["cred_vivo"] else 0} de sus facturas están sin pagar al cierre.')
    por_def=m3["tp_fc"].get("99 por definir",{"m":0})
    if por_def["m"]/m3["tot_fc"]>0.1:
        hallazgos.append(f'<b>Tipos de pago sin definir en compras:</b> <code>99 por definir</code> = {pct(por_def["m"],m3["tot_fc"])} del monto ({p(por_def["m"])}). Degrada la trazabilidad de tesorería.')
    sindefi=m1["tip_cot"].get("Sin definir",{"n":0})
    if sindefi["n"]/m1["n_cot"]>0.5:
        hallazgos.append(f'<b>Tipos de pago en blanco en cotizaciones:</b> <b>{pct(sindefi["n"],m1["n_cot"])}</b> de las cotizaciones ({sindefi["n"]}/{m1["n_cot"]}) no tienen tipo de pago. Imposible analizar el mix contado vs crédito vs Ariba al cotizar.')
    if len(m2a["sin_entregar"])>3:
        tot_se=sum(f(r.get("property_total_formula","0")) for r in m2a["sin_entregar"])
        hallazgos.append(f'<b>{len(m2a["sin_entregar"])} pedidos facturados sin entregar</b> — {p(tot_se)} en facturas emitidas cuya mercancía aún no salió del almacén. Riesgo de reclamación del cliente y desfase contable.')
    if otros_pct>0.4:
        hallazgos.append(f'<b>Categoría "Otros" = {otros_pct:.1%} del OPEX</b> — la taxonomía en Notion está rota. Crear <code>Impuestos/SAT</code>, <code>Seguridad Social</code>, <code>Intereses Financieros</code>, <code>Profesionalización</code>.')
    hallazgos.append(f'<b>Flujo neto del mes: {p(pl["flujo_neto"])}</b> — prácticamente cero. El negocio está en equilibrio real pero sin margen de error. Cualquier descalce en cobranza generará déficit en mayo.')
    hallazgos.append(f'<b>Ciclo de facturación largo:</b> promedio {m2a["ciclo_tot_avg"]:.1f} días de pedido a asociación de pago (máx {m2a["ciclo_tot_max"]:.0f} días). La etapa Validado→Asociado ({m2a["ciclo_va_avg"]:.1f} días prom) es el cuello de botella principal.')

    recs=[
        'Crear categoría <code>Impuestos / SAT</code> en Notion para aislar cargas fiscales del OPEX recurrente. Sin esto el dashboard seguirá mostrando una imagen distorsionada mes a mes.',
        f'<b>Plan de liquidación de inmovilizado ({p(sa["inmov"])}):</b> identificar los SKUs con mayor antigüedad y valor (top 10 del stock) y lanzar campaña de descuento/cross-sell con clientes hoteleros.',
        f'<b>Acelerar cobranza (mediana {m2d["t_pago_med"]:.0f} días):</b> crear flujo automatizado en n8n con recordatorio a 30/45/60 días desde fecha de facturación. Priorizar clientes con CxC mayor a $20K.',
        'Cerrar el campo <code>99 por definir</code> en compras: añadir validación en Notion que pida tipo de pago antes de marcar factura como revisada.',
        'Hacer obligatorio el tipo de pago en cotizaciones: configurar vista de Notion que filtre cotizaciones sin tipo de pago y bloquear conversión a pedido hasta llenarlo.',
        f'Conciliar los {len(m2a["sin_entregar"])} pedidos facturados-sin-entregar: asignar dueño y fecha compromiso de salida en Notion antes del 5 de mayo.',
        f'Diversificar proveedores: la dependencia de {top_pv[0]} ({pct(top_pv[1]["tot"],m3["tot_fc"])}) es un riesgo operativo. Mapear 2-3 alternativas por línea de producto crítica.',
        f'Reducir la etapa Validado→Asociado ({m2a["ciclo_va_avg"]:.1f} días prom) creando un recordatorio automático para emitir el complemento de pago SAT el mismo día que el cliente confirma pago.',
    ]

    h_items="".join(f"<li>{h}</li>" for h in hallazgos)
    r_items="".join(f"<li>{r}</li>" for r in recs)

    sec_hall=f"""
<section class="sec">
<h2 class="sec-title">🎯 Hallazgos Críticos</h2>
<ol class="findings">{h_items}</ol>
</section>
<section class="sec">
<h2 class="sec-title">✅ Recomendaciones Accionables — {next_month.capitalize()} {period_label[-4:]}</h2>
<ol class="findings recs">{r_items}</ol>
</section>
"""

    # ── Glosario ──────────────────────────────────────────────────────────
    glosario_items=[
        ("Cotización","Propuesta de precio enviada al cliente antes de confirmar la venta. Caduca si no se aprueba en el plazo acordado. No genera movimiento contable."),
        ("Pedido","Cotización aprobada por el cliente. Entra al flujo de preparación, entrega y facturación. SÍ genera obligación de entrega."),
        ("NR — Nota de Remisión","Guía de entrega física que acompaña la mercancía antes de emitir la factura CFDI. Sirve como resguardo temporal y da fe de la entrega."),
        ("CFDI","Comprobante Fiscal Digital por Internet — la factura electrónica validada por el SAT. G01 = adquisición de mercancías (inventario). G03 = gastos en general."),
        ("Complemento de pago","Documento CFDI adicional que se emite cuando el cliente paga una factura a crédito. Cierra el ciclo fiscal ante el SAT y es obligatorio para deducir el IVA."),
        ("Ariba (SAP Ariba)","Plataforma de compras corporativas de Grupo Posadas (hoteles Fiesta Americana, Live Aqua, etc.). Las órdenes Ariba tienen un proceso más largo pero garantizan el pago mediante PO formal."),
        ("Foráneo / Local","Local = cliente en CDMX/área metropolitana (entrega directa, mismo día o siguiente). Foráneo = cliente en otro estado (requiere paquetería, 1-5 días extra)."),
        ("Inmovilizado","Inventario que NO tuvo ninguna salida durante el mes analizado. Es un SUBCONJUNTO del stock total — no se suma, se resta para conocer el inventario activo."),
        ("Inventario activo","Stock total menos el inmovilizado. Representa la mercancía que sí rotó (tuvo al menos una salida) durante el mes."),
        ("Margen Bruto","Ingresos de ventas menos el costo directo de los productos comprados. No incluye gastos operativos. Un margen saludable para RTB debería ser >30%."),
        ("EBITDA / Utilidad estimada","Earnings Before Interest, Taxes, Depreciation and Amortization. Aquí se aproxima como Margen Bruto menos OPEX. No es la utilidad fiscal formal."),
        ("CxC — Cuentas por Cobrar","Dinero que los clientes nos deben por facturas emitidas pero aún no pagadas. Un CxC alto implica que vendimos pero no hemos cobrado."),
        ("CxP — Cuentas por Pagar","Dinero que RTB debe a proveedores por facturas recibidas pero aún no pagadas. Un CxP alto puede generar problemas de relación con proveedores."),
        ("Tipo de pago '99 por definir'","Marca interna de Notion cuando el tipo de pago no fue especificado al registrar la factura. Debe resolverse antes del cierre mensual."),
        ("Validación de factura","Confirmación interna de que la factura emitida es correcta en datos, monto y concepto. Paso previo a enviarla formalmente al cliente."),
        ("Asociación al pago","Proceso de vincular el pago recibido del cliente con la factura correspondiente — necesario para emitir el complemento de pago al SAT."),
        ("Ciclo de facturación","Tiempo total desde creación del pedido hasta que la factura queda asociada al pago. Etapas: preparación → emisión CFDI → validación → asociación."),
        ("Carga fiscal extraordinaria","Pagos al SAT/IMSS que cayeron en el mes pero corresponden a períodos anteriores (declaraciones atrasadas o acumuladas). Distorsionan el OPEX del mes corriente."),
        ("Status 'Impresa' vs 'Entregada'","Impresa = factura generada en el sistema pero no entregada físicamente/digitalmente al cliente. Entregada = el cliente la recibió."),
        ("SIPARE","Sistema de Pago Referenciado del IMSS/INFONAVIT. El pago mensual de las cuotas patronales y obreras de seguridad social."),
        ("OPEX","Operating Expenses — gastos de operación del negocio (renta, combustible, alimentación, servicios, etc.). Distintos al costo directo de la mercancía."),
    ]
    glosario_ids={term:f"glos-{i:02d}" for i,(term,_) in enumerate(glosario_items,1)}
    glosario_desc={term:desc for term,desc in glosario_items}
    glos_rows="".join(f'<tr id="{glosario_ids[t]}"><td>{t}</td><td>{d}</td></tr>' for t,d in glosario_items)
    glossary_variants=[
        (["Cotizaciones","Cotización","cotizaciones","cotización"],glosario_desc["Cotización"]),
        (["Pedidos","Pedido","pedidos","pedido"],glosario_desc["Pedido"]),
        (["Nota de Remisión","NR"],glosario_desc["NR — Nota de Remisión"]),
        (["CFDI"],glosario_desc["CFDI"]),
        (["Complemento de pago","complemento de pago"],glosario_desc["Complemento de pago"]),
        (["SAP Ariba","Ariba"],glosario_desc["Ariba (SAP Ariba)"]),
        (["Foráneo","foráneo","Local","local"],glosario_desc["Foráneo / Local"]),
        (["Inmovilizado","inmovilizado"],glosario_desc["Inmovilizado"]),
        (["Inventario activo","inventario activo"],glosario_desc["Inventario activo"]),
        (["Margen Bruto","Margen bruto","margen bruto"],glosario_desc["Margen Bruto"]),
        (["EBITDA","Utilidad estimada","utilidad estimada"],glosario_desc["EBITDA / Utilidad estimada"]),
        (["Cuentas por Cobrar","CxC"],glosario_desc["CxC — Cuentas por Cobrar"]),
        (["Cuentas por Pagar","CxP"],glosario_desc["CxP — Cuentas por Pagar"]),
        (["99 por definir"],glosario_desc["Tipo de pago '99 por definir'"]),
        (["Validación de factura","validación de factura"],glosario_desc["Validación de factura"]),
        (["Asociación al pago","asociación al pago"],glosario_desc["Asociación al pago"]),
        (["Ciclo de facturación","ciclo de facturación"],glosario_desc["Ciclo de facturación"]),
        (["Carga fiscal extraordinaria","carga fiscal extraordinaria"],glosario_desc["Carga fiscal extraordinaria"]),
        (["Impresa","Entregada"],glosario_desc["Status 'Impresa' vs 'Entregada'"]),
        (["SIPARE"],glosario_desc["SIPARE"]),
        (["OPEX"],glosario_desc["OPEX"]),
    ]

    sec_glos=f"""
<section class="sec">
<h2 class="sec-title">📚 Glosario — Terminología del Reporte</h2>
<p class="section-intro">Definiciones en lenguaje llano de los términos técnicos usados en este reporte. Consultar antes de presentar a áreas no-financieras.</p>
<table class="glosario-table"><thead><tr><th>Término</th><th>Explicación</th></tr></thead><tbody>{glos_rows}</tbody></table>
</section>
"""

    # ── JavaScript ────────────────────────────────────────────────────────
    # Build JS data object
    def jl(lst): return json.dumps([str(x) for x in lst])

    sem_labels=temporal_cot.get("labels", [])
    sem_cot_vals=[d["m"] for d in temporal_cot_periods]
    sem_apr_vals=[d["ma"] for d in temporal_cot_periods]
    ped_labels=m2a.get("temporal_ped", {}).get("labels", [])
    compras_labels=m3.get("temporal_fc", {}).get("labels", [])
    gas_labels=m5.get("temporal_gas", {}).get("labels", [])

    est_labels=list(m1["est_cot"].keys())
    est_data=[m1["est_cot"][e]["m"] for e in est_labels]

    prep_labels=list(m2a["rangos_prep"].keys())
    prep_data=list(m2a["rangos_prep"].values())

    ent_labels=list(m2a["rangos_ent"].keys())
    ent_data=list(m2a["rangos_ent"].values())

    pago_labels=list(m2d["rangos_pago"].keys())
    pago_data=list(m2d["rangos_pago"].values())

    ciclo_labels=["Pedido→Facturado","Facturado→Validado","Validado→Asociado","Ciclo total"]
    ciclo_data=[m2a["ciclo_pf_avg"],m2a["ciclo_fv_avg"],m2a["ciclo_va_avg"],m2a["ciclo_tot_avg"]]

    tp_pag_labels=list(m2d["tp_pag"].keys())
    tp_pag_data=[m2d["tp_pag"][k]["m"] for k in tp_pag_labels]

    sp_labels=list(m3["sp_fc"].keys())
    sp_data=[m3["sp_fc"][k]["m"] for k in sp_labels]

    prov5=[pv for pv,_ in m3["top_prov"][:5]]
    prov5_data=[m3["top_prov"][i][1]["tot"] for i in range(min(5,len(m3["top_prov"])))]

    inv_hist_labels=["Feb 2026","Mar 2026","Abr 2026","May 2026"]
    inv_hist_tot=[snaps[k]["total"] for k in ["Febrero","Marzo","Abril","Mayo"]]
    inv_hist_inmov=[snaps[k]["inmov"] for k in ["Febrero","Marzo","Abril","Mayo"]]

    cat_labels_sorted=sorted(m5["cat_gas"].keys(),key=lambda k:-m5["cat_gas"][k]["m"])
    cat_data_sorted=[m5["cat_gas"][k]["m"] for k in cat_labels_sorted]

    mp_labels=list(m5["mp_gas"].keys())
    mp_data=[m5["mp_gas"][k]["m"] for k in mp_labels]

    sem_gas_data=[d["m"] for d in temporal_gas_periods]
    max_gas=max(sem_gas_data) if sem_gas_data else 1
    gas_colors=json.dumps(["#d96058" if v==max_gas else "#159895" for v in sem_gas_data])

    pl_labels=["Ingresos (sub)","Compras (sub)","Margen bruto","OPEX (sub)","Util. teórica","Util. ajustada"]
    pl_data=[pl["ing_sub"],pl["comp_sub"],pl["margen"],pl["opex_sub"],pl["utilidad"],pl["utilidad_adj"]]
    pl_colors=json.dumps(["#159895","#7a8c95","#57c5b6","#7a8c95","#d96058" if pl["utilidad"]<0 else "#57c5b6","#ad9551"])

    apr_labels=list(m1["rangos_apr"].keys())
    apr_data=list(m1["rangos_apr"].values())

    JS_CHARTS=f"""
const D={{
  cot_sem: {{labels:{jl(sem_labels)},cotizado:{ja(sem_cot_vals)},aprobado:{ja(sem_apr_vals)}}},
  estados: {{labels:{jl(est_labels)},data:{ja(est_data)}}},
  apr_rng: {{labels:{jl(apr_labels)},data:{ja(apr_data)}}},
  dias_prep: {{labels:{jl(prep_labels)},data:{ja(prep_data)}}},
  dias_ent: {{labels:{jl(ent_labels)},data:{ja(ent_data)}}},
  dias_pago: {{labels:{jl(pago_labels)},data:{ja(pago_data)}}},
  ciclo: {{labels:{jl(ciclo_labels)},data:{ja(ciclo_data)}}},
  tp_pag: {{labels:{jl(tp_pag_labels)},data:{ja(tp_pag_data)}}},
  sp_fc: {{labels:{jl(sp_labels)},data:{ja(sp_data)}}},
  inv_hist: {{labels:{jl(inv_hist_labels)},total:{ja(inv_hist_tot)},inmov:{ja(inv_hist_inmov)}}},
  inv_donut: {{labels:["Con rotación","Inmovilizado"],data:{ja([sa["activo"],sa["inmov"]])}}},
  cat: {{labels:{jl(cat_labels_sorted)},data:{ja(cat_data_sorted)}}},
  mp: {{labels:{jl(mp_labels)},data:{ja(mp_data)}}},
  opex_sem: {{labels:{jl(gas_labels)},data:{ja(sem_gas_data)},colors:{gas_colors}}},
  pl: {{labels:{jl(pl_labels)},data:{ja(pl_data)},colors:{pl_colors}}},
  ped_sem: {{labels:{jl(ped_labels)},data:{ja([d["m"] for d in temporal_ped_periods])}}},
  compras_sem: {{labels:{jl(compras_labels)},data:{ja([d["tot"] for d in temporal_fc_periods])}}},
}};
// Charts
line('chart_cot_sem',D.cot_sem.labels,[
  {{label:'Cotizado',data:D.cot_sem.cotizado,borderColor:C.primary,backgroundColor:'rgba(21,152,149,0.15)',tension:0.3,fill:true,borderWidth:2}},
  {{label:'Aprobado',data:D.cot_sem.aprobado,borderColor:C.accent,backgroundColor:'rgba(173,149,81,0.10)',tension:0.3,fill:true,borderWidth:2}}
]);
dough('chart_estados',D.estados.labels,D.estados.data,[C.primary,C.accent,'#d96058',C.primary2,'#7a8c95']);
bar('chart_apr_rng',D.apr_rng.labels,[{{label:'Cotizaciones',data:D.apr_rng.data,format:'count',backgroundColor:C.primary2,borderRadius:4}}],{{nolegend:true,scales:countScales}});
bar('chart_ped_sem',D.ped_sem.labels,[{{label:'Monto',data:D.ped_sem.data,backgroundColor:C.primary,borderRadius:4}}],{{nolegend:true}});
bar('chart_dias_prep',D.dias_prep.labels,[{{label:'Pedidos',data:D.dias_prep.data,format:'count',backgroundColor:C.primary2,borderRadius:4}}],{{nolegend:true,scales:countScales}});
bar('chart_dias_ent',D.dias_ent.labels,[{{label:'Pedidos',data:D.dias_ent.data,format:'count',backgroundColor:C.accent,borderRadius:4}}],{{nolegend:true,scales:countScales}});
bar('chart_dias_pago',D.dias_pago.labels,[{{label:'Pedidos',data:D.dias_pago.data,format:'count',backgroundColor:C.accent2,borderRadius:4}}],{{nolegend:true,scales:countScales}});
hbar('chart_ciclo',D.ciclo.labels,D.ciclo.data,C.primary,'Días','days',daysXScales);
dough('chart_tp_pag',D.tp_pag.labels,D.tp_pag.data,[C.accent,C.primary,C.primary2,'#7a8c95']);
bar('chart_compras_sem',D.compras_sem.labels,[{{label:'Total c/IVA',data:D.compras_sem.data,backgroundColor:C.primary,borderRadius:4}}],{{nolegend:true}});
dough('chart_sp',D.sp_fc.labels,D.sp_fc.data,[C.primary,C.accent,'#d96058']);
new Chart(document.getElementById('chart_inv_hist'),{{type:'bar',data:{{labels:D.inv_hist.labels,datasets:[{{label:'Total',data:D.inv_hist.total,backgroundColor:C.primary,borderRadius:4}},{{label:'Inmovilizado',data:D.inv_hist.inmov,backgroundColor:C.accent,borderRadius:4}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{labels:{{color:C.text2}}}},tooltip:tt}},scales:bs}}}});
dough('chart_inv_donut',D.inv_donut.labels,D.inv_donut.data,[C.primary,C.accent]);
hbar('chart_cat',D.cat.labels,D.cat.data,C.accent,'Gasto','money');
dough('chart_mp',D.mp.labels,D.mp.data,[C.primary,C.accent,C.primary2,'#7a8c95']);
new Chart(document.getElementById('chart_opex_sem'),{{type:'bar',data:{{labels:D.opex_sem.labels,datasets:[{{label:'OPEX',data:D.opex_sem.data,backgroundColor:D.opex_sem.colors,borderRadius:4}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}},tooltip:tt}},scales:bs}}}});
new Chart(document.getElementById('chart_pl'),{{type:'bar',data:{{labels:D.pl.labels,datasets:[{{label:'Monto',data:D.pl.data,backgroundColor:D.pl.colors,borderRadius:4}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}},tooltip:tt}},scales:bs}}}});
"""

    # ── Resumen ejecutivo ─────────────────────────────────────────────────
    sec_exec=f"""
<section class="sec">
<h2 class="sec-title">Resumen Ejecutivo</h2>
<div class="exec-summary">
<p>{period_label} cerró con <b>{m1['n_cot']} cotizaciones</b> ({p(m1['tot_cot'])} c/IVA), tasa de conversión <b class="hl">{m1['conv_q']:.1%}</b> en cantidad y <b class="hl">{m1['conv_m']:.1%}</b> en monto, y <b>{m2a['n_ped']} pedidos creados</b> por <b>{p(m2a['tot_ped'])}</b>. Se entregaron <b>{m2b['n_env']} pedidos</b> ({p(m2b['tot_env'])}). La facturación total del mes fue <b class="hl">{p(m2c['tot_facturacion'])}</b> y los ingresos efectivamente cobrados ascendieron a <b class="hl">{p(m2d['tot_pag'])}</b> c/IVA.</p>
<p>El <b>margen bruto fue {pl['pct_margen']:.1%}</b> ({p(pl['margen'])}), saludable para el perfil de RTB. Sin embargo, la utilidad teórica fue <b class="hl-bad">{p(pl['utilidad'])} ({pl['pct_utilidad']:+.1%})</b> porque el OPEX del mes incluyó <b>{p(m5['tot_fiscal'])}</b> en cargas fiscales acumuladas (declaraciones Dic 2025, Ene y Feb 2026). Excluyendo ese cargo extraordinario, la <b>utilidad ajustada habría sido <span class="hl-good">{p(pl['utilidad_adj'])} (+{pl['pct_utilidad_adj']:.1%})</span></b>. El flujo de caja neto fue prácticamente cero ({p(pl['flujo_neto'])}).</p>
<p>El <b>inventario inmovilizado ({sa['pct_inmov']:.1%} del stock)</b> creció de {p(sm['inmov'])} en marzo a {p(sa['inmov'])} en {period_month} — el remanente sin rotar se volvió dominante a pesar de que el stock total bajó −51.8%. La <b>mediana de días de cobro</b> de {m2d['t_pago_med']:.0f} días requiere atención inmediata para proteger el flujo de {next_month}.</p>
</div>
</section>
"""

    # ── Hero ──────────────────────────────────────────────────────────────
    kpis="".join([
        kpi("Cotizaciones creadas",str(hero["n_cot"]),f"{p(hero['tot_cot'])} c/IVA"),
        kpi("Conversión a pedido",f"{hero['conv_q']:.1%}",f"{hero['conv_m']:.1%} en monto"),
        kpi("Pedidos creados",str(hero["n_ped"]),f"{p(hero['tot_ped'])} c/IVA"),
        kpi("Entregados",str(hero["n_env"]),p(hero["tot_env"])),
        kpi("Facturado total",p(hero["tot_facturacion"]),"Primaria + Secundaria"),
        kpi("Ingresos cobrados",p(hero["tot_pag"]),f"{p(hero['sub_pag'])} sub"),
        kpi("Margen bruto",p(hero["margen"]),f"{hero['pct_margen']:.1%} s/ingresos"),
        kpi("Stock total",p(hero["snap_abr_total"]),f"{hero['pct_inmov']:.1%} inmovilizado"),
    ])
    content_before_glossary=link_first_glossary_terms(f"""
<div class="kpi-grid">{kpis}</div>
{data_warnings_html}

{sec_exec}
{sec1}
{sec2}
{sec3}
{sec4}
{sec5}
{sec_pl}
{sec_hall}
""", glossary_variants)

    # ── Ensamble final ────────────────────────────────────────────────────
    html=f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>RTB · Cierre {period_label} · Dashboard Ejecutivo</title>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600;9..144,700&family=Inter+Tight:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<script>{CHARTJS_INLINE}</script>
<style>{CSS}</style>
</head>
<body>
<div class="container">

<div class="hero">
<div class="hero-eyebrow">Refacciones Tomás Badillo S.A. de C.V. · RFC RTB181127HC7</div>
<h1 class="hero-title">Cierre Mensual <span class="hero-mes">{period_label}</span></h1>
<div class="hero-meta">
<span>Periodo: {period_range}</span>
<span class="dot">•</span>
<span>Generado {now}</span>
<span class="dot">•</span>
<span>Encargado de Tecnología: Diego Guillén García</span>
</div>
</div>

{content_before_glossary}
{sec_glos}

<footer>Generado automáticamente por el flujo de cierre mensual RTB v4 · CSVs exportados de Notion al {export_date} · Diego Guillén García</footer>
</div>

<script>
{JS_BASE}
{JS_CHARTS}
</script>
</body>
</html>"""
    return html

def f(v):
    try: return float(str(v).replace(",","").strip()) if str(v).strip() else 0.0
    except: return 0.0
