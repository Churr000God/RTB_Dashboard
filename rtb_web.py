#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""App local para validar la descarga de datos RTB via n8n."""

from datetime import datetime, timezone
import json
import os
import shutil
from pathlib import Path
from time import sleep as sleep_seconds
from html import escape
from typing import Callable
from uuid import uuid4
from zoneinfo import ZoneInfo

import requests
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from rtb_analisis import build_facturacion_dashboard, build_ventas_dashboard, find_latest_csv, load_cotizaciones, read_csv


WEBHOOK_URLS = {
    "test": os.getenv("RTB_WEBHOOK_TEST_URL", ""),
    "prod": os.getenv("RTB_WEBHOOK_PROD_URL", ""),
}

HTTP_TIMEOUT_SECONDS = 900
SALES_SNAPSHOT_FILENAME = "ventas_latest.json"
FACTURACION_SNAPSHOT_FILENAME = "facturacion_latest.json"
LOCAL_TIMEZONE = ZoneInfo("America/Mexico_City")
CSV_WAIT_ATTEMPTS = int(os.getenv("RTB_CSV_WAIT_ATTEMPTS", "300"))
CSV_WAIT_DELAY_SECONDS = float(os.getenv("RTB_CSV_WAIT_DELAY_SECONDS", "1.0"))


def atomic_write_json(path, payload) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)
        fh.write("\n")
    os.replace(temporary, path)


class UpdateRequest(BaseModel):
    ambiente: str
    fecha_desde: str
    fecha_hasta: str


def build_payload(fecha_desde: str, fecha_hasta: str) -> list[dict[str, str]]:
    return [{"after": fecha_desde}, {"before": fecha_hasta}]


def parse_iso_date(value: str, label: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"{label} debe venir en formato YYYY-MM-DD") from exc


def resolve_webhook_url(ambiente: str) -> str:
    normalized = ambiente.strip().lower()
    if normalized not in WEBHOOK_URLS:
        raise ValueError("ambiente invalido; usa test o prod")
    url = WEBHOOK_URLS[normalized]
    if not url:
        raise ValueError(
            f"webhook url no configurada para '{normalized}'; "
            f"define RTB_WEBHOOK_{normalized.upper()}_URL en el entorno"
        )
    return url


def validate_request(ambiente: str, fecha_desde: str, fecha_hasta: str) -> tuple[str, datetime, datetime]:
    normalized = ambiente.strip().lower()
    resolve_webhook_url(normalized)
    start = parse_iso_date(fecha_desde, "fecha_desde")
    end = parse_iso_date(fecha_hasta, "fecha_hasta")
    if end < start:
        raise ValueError("fecha_hasta no puede ser menor que fecha_desde")
    return normalized, start, end


def parse_response_body(response: requests.Response):
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type.lower():
        return response.json()
    try:
        return response.json()
    except ValueError:
        return response.text


def call_webhook(
    ambiente: str,
    fecha_desde: str,
    fecha_hasta: str,
    http_post: Callable[..., requests.Response] | None = None,
) -> dict:
    normalized, _, _ = validate_request(ambiente, fecha_desde, fecha_hasta)
    url = resolve_webhook_url(normalized)
    payload = build_payload(fecha_desde, fecha_hasta)
    post = http_post or requests.post

    response = post(url, json=payload, timeout=HTTP_TIMEOUT_SECONDS)
    body = parse_response_body(response)

    return {
        "ambiente": normalized,
        "url": url,
        "payload": payload,
        "status_code": response.status_code,
        "response": body,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


class WebhookResponseError(RuntimeError):
    pass


def snapshot_cotizaciones(data_dir: str | Path) -> dict[str, tuple[int, int]]:
    root = Path(data_dir)
    if not root.exists():
        return {}
    return {
        path.name: (path.stat().st_mtime_ns, path.stat().st_size)
        for path in root.glob("Cotizaciones*.csv")
        if path.is_file()
    }


def snapshot_facturas(data_dir: str | Path) -> dict[str, tuple[int, int]]:
    root = Path(data_dir)
    if not root.exists():
        return {}
    return {
        path.name: (path.stat().st_mtime_ns, path.stat().st_size)
        for path in root.glob("Facturas*.csv")
        if path.is_file()
    }


def wait_for_changed_facturas(
    data_dir: str | Path,
    before: dict[str, tuple[int, int]],
    sleep: Callable[[float], None] = sleep_seconds,
    attempts: int = CSV_WAIT_ATTEMPTS,
    delay_seconds: float = CSV_WAIT_DELAY_SECONDS,
    quiesce_seconds: float = 8.0,
) -> None:
    """Espera hasta que los archivos de Facturas en data/ se estabilicen.

    Primero espera a que al menos un archivo cambie vs. `before`.
    Luego espera `quiesce_seconds` adicionales sin nuevos cambios para
    asegurarse de que n8n terminó de descargar todos los archivos.
    """
    root = Path(data_dir)
    # Fase 1: esperar el primer cambio
    for attempt in range(attempts):
        after = snapshot_facturas(root)
        if any(before.get(name) != fp for name, fp in after.items()):
            break
        if attempt == attempts - 1:
            return  # best-effort
        sleep(delay_seconds)
    # Fase 2: estabilización — esperar hasta que no lleguen archivos nuevos
    quiesce_attempts = max(1, int(quiesce_seconds / delay_seconds))
    stable_count = 0
    prev = snapshot_facturas(root)
    for _ in range(quiesce_attempts * 3):
        sleep(delay_seconds)
        curr = snapshot_facturas(root)
        if curr == prev:
            stable_count += 1
            if stable_count >= quiesce_attempts:
                return
        else:
            stable_count = 0
            prev = curr


def find_changed_cotizaciones(data_dir: str | Path, before: dict[str, tuple[int, int]]) -> Path:
    root = Path(data_dir)
    after = snapshot_cotizaciones(root)
    changed = [root / name for name, fingerprint in after.items() if before.get(name) != fingerprint]
    if not changed:
        raise ValueError("No se encontro un CSV nuevo o actualizado de Cotizaciones despues del webhook")
    return max(changed, key=lambda path: (path.stat().st_mtime_ns, path.name))


def wait_for_changed_cotizaciones(
    data_dir: str | Path,
    before: dict[str, tuple[int, int]],
    sleep: Callable[[float], None] = sleep_seconds,
    attempts: int = CSV_WAIT_ATTEMPTS,
    delay_seconds: float = CSV_WAIT_DELAY_SECONDS,
) -> Path:
    for attempt in range(attempts):
        try:
            return find_changed_cotizaciones(data_dir, before)
        except ValueError:
            if attempt == attempts - 1:
                raise
            sleep(delay_seconds)
    raise RuntimeError("No se pudo verificar el CSV de Cotizaciones")


def archive_ventas_csv(
    csv_path: str | Path, processed_dir: str | Path, archived_at: datetime | None = None
) -> Path:
    source = Path(csv_path)
    root = Path(processed_dir)
    archive_time = archived_at or datetime.now(LOCAL_TIMEZONE)
    timestamp = archive_time.strftime("%Y-%m-%d_%H-%M-%S")
    destination_dir = root / f"{timestamp}_ventas"
    suffix = 1
    while destination_dir.exists():
        destination_dir = root / f"{timestamp}_ventas_{suffix}"
        suffix += 1
    destination_dir.mkdir(parents=True)
    destination = destination_dir / source.name
    shutil.move(str(source), str(destination))
    return destination


def archive_data_dir(
    data_dir: str | Path,
    processed_dir: str | Path,
    archived_at: datetime | None = None,
) -> list[str]:
    """Mueve TODOS los CSV de data/ a una sola subcarpeta en data_procesada/.

    Devuelve la lista de nombres de archivos archivados.
    """
    root = Path(data_dir)
    proc = Path(processed_dir)
    archive_time = archived_at or datetime.now(LOCAL_TIMEZONE)
    timestamp = archive_time.strftime("%Y-%m-%d_%H-%M-%S")
    candidates = [p for p in root.glob("*.csv") if p.is_file()]
    if not candidates:
        return []
    destination_dir = proc / f"{timestamp}_datos"
    suffix = 1
    while destination_dir.exists():
        destination_dir = proc / f"{timestamp}_datos_{suffix}"
        suffix += 1
    destination_dir.mkdir(parents=True)
    archived = []
    for src in sorted(candidates, key=lambda p: p.name):
        shutil.move(str(src), str(destination_dir / src.name))
        archived.append(src.name)
    return archived


def publish_ventas_snapshot(
    data_dir: str | Path,
    dashboard_dir: str | Path,
    before: dict[str, tuple[int, int]],
    fecha_desde: str,
    fecha_hasta: str,
    csv_path: str | Path | None = None,
) -> dict:
    csv_path = Path(csv_path) if csv_path else wait_for_changed_cotizaciones(data_dir, before)
    period_label = f"{fecha_desde} a {fecha_hasta}"
    ventas = build_ventas_dashboard(
        read_csv(csv_path), period_label=period_label, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta
    )
    snapshot = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": {"start": fecha_desde, "end": fecha_hasta, "label": period_label},
        "file": csv_path.name,
        "dashboard": {"ventas": ventas},
    }
    atomic_write_json(Path(dashboard_dir) / SALES_SNAPSHOT_FILENAME, snapshot)
    return snapshot


def validate_webhook_success(webhook: dict) -> None:
    if not 200 <= webhook["status_code"] < 300:
        raise WebhookResponseError(f"n8n respondio HTTP {webhook['status_code']}")
    if not isinstance(webhook["response"], dict) or webhook["response"].get("ok") is not True:
        raise WebhookResponseError("n8n no confirmo la actualizacion con {\"ok\": true}")


def load_dashboard_payload(data_dir: str = "data", dashboard_dir: str = "dashboard_data") -> dict:
    sales_snapshot = Path(dashboard_dir) / SALES_SNAPSHOT_FILENAME
    if sales_snapshot.exists():
        return json.loads(sales_snapshot.read_text(encoding="utf-8"))["dashboard"]["ventas"]
    rows = load_cotizaciones(data_dir)
    dates = [row.get("Fecha_creacion", "")[:10] for row in rows if row.get("Fecha_creacion")]
    period_label = "Periodo actual"
    if dates:
        period_label = f"{min(dates)} a {max(dates)}"
    return build_ventas_dashboard(
        rows, period_label=period_label, fecha_desde=min(dates) if dates else None, fecha_hasta=max(dates) if dates else None
    )



def find_latest_facturacion_csv(data_dir: str | Path, prefix: str) -> Path:
    root = Path(data_dir)
    matches = [
        path for path in root.glob(f"{prefix}*.csv")
        if path.is_file() and not (prefix == "Facturas_" and path.name.startswith("Facturas_Secundarias_"))
    ]
    if not matches:
        raise FileNotFoundError(f"No se encontro {prefix}*.csv en la carpeta de datos: {root.resolve()}")
    return max(matches, key=lambda path: (path.stat().st_mtime_ns, path.name))


def load_facturacion_exports(data_dir: str | Path) -> tuple[Path, Path, Path]:
    return (
        Path(find_latest_csv(data_dir, "Cotizaciones")),
        find_latest_facturacion_csv(data_dir, "Facturas_"),
        find_latest_facturacion_csv(data_dir, "Facturas_Secundarias_"),
    )


def publish_facturacion_snapshot(
    data_dir: str | Path,
    dashboard_dir: str | Path,
    fecha_desde: str,
    fecha_hasta: str,
    cot_path: str | Path | None = None,
) -> dict:
    default_cot_path, principales_path, secundarias_path = load_facturacion_exports(data_dir)
    cot_path = Path(cot_path) if cot_path else default_cot_path
    period_label = f"{fecha_desde} a {fecha_hasta}"
    facturacion = build_facturacion_dashboard(
        read_csv(cot_path),
        read_csv(principales_path),
        read_csv(secundarias_path),
        period_label=period_label,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )
    snapshot = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": {"start": fecha_desde, "end": fecha_hasta, "label": period_label},
        "files": {
            "cotizaciones": cot_path.name,
            "principales": principales_path.name,
            "secundarias": secundarias_path.name,
        },
        "dashboard": {"facturacion": facturacion},
    }
    atomic_write_json(Path(dashboard_dir) / FACTURACION_SNAPSHOT_FILENAME, snapshot)
    return snapshot


def load_facturacion_payload(data_dir: str = "data", dashboard_dir: str = "dashboard_data") -> dict:
    snapshot_path = Path(dashboard_dir) / FACTURACION_SNAPSHOT_FILENAME
    if snapshot_path.exists():
        return json.loads(snapshot_path.read_text(encoding="utf-8"))["dashboard"]["facturacion"]
    cot_path, principales_path, secundarias_path = load_facturacion_exports(data_dir)
    return build_facturacion_dashboard(read_csv(cot_path), read_csv(principales_path), read_csv(secundarias_path))


def render_index() -> str:
    today = datetime.now()
    _end = today.strftime("%Y-%m-%d")
    _sm, _sy = today.month - 2, today.year
    if _sm <= 0:
        _sm += 12; _sy -= 1
    _start = f"{_sy}-{_sm:02d}-01"
    test_payload = build_payload(_start, _end)
    payload_text = escape(_json_preview(test_payload))
    return """<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RTB Command Center</title>
  <style>
    :root {
      color-scheme: dark;
      --app-bg: #f4f7f9;
      --sidebar: #276f86;
      --sidebar-2: #225e73;
      --sidebar-3: #1d5368;
      --primary: #159895;
      --primary-2: #57c5b6;
      --accent: #d0b56b;
      --accent-2: #c6ad6a;
      --text: #f4f7f9;
      --text-2: rgba(255,255,255,0.72);
      --text-3: rgba(255,255,255,0.50);
      --border: rgba(173,149,81,0.28);
      --border-soft: rgba(173,149,81,0.14);
      --alert: #d96058;
      --good: #57c5b6;
      --paper: #ffffff;
      --ink: #111827;
      --muted: #5b6673;
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; min-height: 100%; background: var(--app-bg); color: var(--ink); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; font-size: 14px; line-height: 1.45; }
    .app { min-height: 100vh; display: grid; grid-template-columns: 320px minmax(0, 1fr); }
    .sidebar { min-height: 100vh; background: var(--sidebar); color: var(--text); border-right: 1px solid var(--border); display: flex; flex-direction: column; }
    .brand { padding: 22px 22px 18px; border-bottom: 1px solid var(--border-soft); }
    .eyebrow { margin: 0 0 8px; color: var(--primary-2); font-size: 10px; font-weight: 700; letter-spacing: 1.4px; text-transform: uppercase; }
    h1 { margin: 0; font-size: 21px; line-height: 1.14; font-weight: 760; letter-spacing: 0; }
    .subtitle { margin: 8px 0 0; color: var(--text-2); font-size: 12.5px; }
    .control-panel { padding: 18px 18px 16px; display: grid; gap: 14px; }
    .group { display: grid; gap: 8px; }
    label { color: var(--text-2); font-size: 11px; font-weight: 720; letter-spacing: .8px; text-transform: uppercase; }
    input, select, button { width: 100%; min-height: 38px; border-radius: 7px; font: inherit; outline: none; }
    input, select { border: 1px solid var(--border-soft); background: var(--sidebar-3); color: var(--text); padding: 8px 10px; }
    input:focus, select:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(208,181,107,.16); }
    button { border: 1px solid var(--accent); background: var(--accent); color: #142b36; font-weight: 800; cursor: pointer; transition: background 150ms ease-out, opacity 150ms ease-out; }
    button:hover { background: var(--accent-2); }
    button:disabled { opacity: .62; cursor: wait; }
    .status-card { margin: 2px 18px 18px; border: 1px solid var(--border-soft); border-radius: 8px; background: var(--sidebar-2); padding: 13px; }
    .status-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
    .status-label { color: var(--text-2); font-size: 11px; font-weight: 720; letter-spacing: .8px; text-transform: uppercase; }
    .pill { display: inline-flex; align-items: center; min-height: 24px; border-radius: 999px; padding: 2px 8px; border: 1px solid var(--border-soft); color: var(--text-2); font-size: 11px; font-weight: 750; }
    .pill.success { color: var(--good); background: rgba(87,197,182,.12); border-color: rgba(87,197,182,.36); }
    .pill.error { color: #ffaca6; background: rgba(217,96,88,.12); border-color: rgba(217,96,88,.4); }
    .status-detail { margin: 11px 0 0; color: var(--text-3); font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; overflow-wrap: anywhere; }
    .payload { margin-top: auto; padding: 14px 18px 18px; border-top: 1px solid var(--border-soft); color: var(--text-3); }
    .payload b { display: block; color: var(--text-2); font-size: 11px; letter-spacing: .8px; text-transform: uppercase; margin-bottom: 6px; }
    code { font: 11px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; color: var(--accent); overflow-wrap: anywhere; }
    .main { min-width: 0; padding: 18px; display: grid; grid-template-rows: auto minmax(0, 1fr); gap: 12px; }
    .module-bar { min-width: 0; min-height: 56px; border: 1px solid #d6e1e8; border-radius: 9px; background: #fbfcfd; display: flex; align-items: center; gap: 8px; padding: 9px; overflow-x: auto; box-shadow: 0 10px 28px rgba(34,94,115,.08); }
    .module-tab { width: auto; min-width: max-content; min-height: 36px; border: 1px solid #d6e1e8; border-radius: 7px; background: #eef5f7; color: var(--sidebar-2); padding: 0 13px; font-size: 12px; font-weight: 820; letter-spacing: 0; cursor: pointer; transition: background 150ms ease-out, border-color 150ms ease-out, color 150ms ease-out, box-shadow 150ms ease-out; }
    .module-tab:hover { border-color: rgba(21,152,149,.45); background: #e7f3f3; }
    .module-tab:focus-visible { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(208,181,107,.22); }
    .module-tab.active { border-color: var(--sidebar); background: var(--sidebar); color: var(--text); box-shadow: inset 0 -2px 0 var(--accent); }
    .canvas { min-height: calc(100vh - 104px); border: 1px dashed #c8d2dc; border-radius: 10px; background: var(--paper); padding: 16px; }
    .ventas-panel[hidden], .facturacion-panel[hidden] { display: none; }
    .kpi-grid { display: grid; grid-template-columns: repeat(3, minmax(240px, 1fr)); gap: 12px; align-items: stretch; }
    .kpi-card { position: relative; isolation: isolate; overflow: hidden; min-height: 146px; border: 1px solid #d8e3ea; border-radius: 8px; background: #fbfcfd; padding: 14px; display: grid; gap: 12px; box-shadow: 0 8px 22px rgba(34,94,115,.06); transition: transform 180ms ease-out, box-shadow 180ms ease-out, border-color 180ms ease-out; }
    .kpi-card:hover { transform: translateY(-2px); border-color: rgba(21,152,149,.38); box-shadow: 0 14px 34px rgba(34,94,115,.13); }
    .kpi-bg { position: absolute; inset: 0; width: 100%; height: 100%; z-index: 0; opacity: .62; pointer-events: none; }
    .kpi-card > :not(.kpi-bg) { position: relative; z-index: 1; }
    .kpi-card h2 { margin: 0; color: var(--sidebar-2); font-size: 12px; line-height: 1.2; font-weight: 820; letter-spacing: .5px; text-transform: uppercase; }
    .kpi-pair { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    .kpi-metric { min-width: 0; display: grid; gap: 4px; }
    .kpi-label { color: var(--muted); font-size: 11px; font-weight: 740; letter-spacing: 0; }
    .kpi-value { color: var(--ink); font-size: 24px; line-height: 1.05; font-weight: 820; letter-spacing: 0; overflow-wrap: anywhere; }
    .kpi-note { color: #65717e; font-size: 12px; }
    .kpi-delta { border-top: 1px solid #e0e8ee; padding-top: 10px; display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
    .kpi-delta .kpi-label { text-transform: uppercase; letter-spacing: .45px; }
    .kpi-delta .kpi-value { font-size: 20px; }
    .kpi-card.primary { border-color: rgba(21,152,149,.38); background: #f0faf9; }
    .kpi-card.accent { border-color: rgba(208,181,107,.45); background: #fffaf0; }
    .kpi-card.warning .kpi-delta .kpi-value { color: #a45131; }
    .kpi-card.warning { border-color: rgba(217,96,88,.35); background: #fff5f4; }
    .facturacion-kpi-grid { grid-template-columns: repeat(6, minmax(0, 1fr)); }
    .facturacion-kpi-grid > .kpi-card { grid-column: span 2; }
    .facturacion-kpi-grid > .kpi-card:nth-child(4) { grid-column: 2 / span 2; }
    .facturacion-kpi-grid > .kpi-card:nth-child(5) { grid-column: 4 / span 2; }
    @media (max-width: 1180px) {
      .facturacion-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .facturacion-kpi-grid > .kpi-card,
      .facturacion-kpi-grid > .kpi-card:nth-child(4),
      .facturacion-kpi-grid > .kpi-card:nth-child(5) { grid-column: auto; }
    }
    @media (max-width: 920px) {
      .facturacion-kpi-grid { grid-template-columns: 1fr; }
    }
    .ventas-panel, .facturacion-panel { display: grid; gap: 14px; }
    .facturacion-alerts { display: flex; flex-wrap: wrap; gap: 8px; }
    .facturacion-alert { border: 1px solid #ead7a2; border-radius: 999px; background: #fff8e6; color: #7a5c00; padding: 5px 9px; font-size: 12px; font-weight: 720; }
    .ciclo-chart-wrap { min-width: 0; height: 220px; }
    .status-section { border: 1px solid #d8e3ea; border-radius: 8px; background: #fbfcfd; padding: 14px; box-shadow: 0 8px 22px rgba(34,94,115,.06); }
    .section-title { margin: 0 0 8px; color: var(--sidebar-2); font-size: 13px; line-height: 1.2; font-weight: 840; letter-spacing: .45px; text-transform: uppercase; }
    .section-subtitle { margin: 0 0 12px; color: var(--muted); font-size: 12px; }
    .status-layout { display: grid; grid-template-columns: minmax(0, 1.45fr) minmax(260px, .75fr); gap: 16px; align-items: center; }
    .table-wrap { min-width: 0; overflow-x: auto; }
    .status-table { width: 100%; border-collapse: collapse; min-width: 560px; font-size: 13px; }
    .status-table th { color: var(--muted); font-size: 11px; font-weight: 820; letter-spacing: .45px; text-transform: uppercase; text-align: right; border-bottom: 1px solid #d8e3ea; padding: 9px 8px; white-space: nowrap; }
    .status-table th:first-child, .status-table td:first-child { text-align: left; }
    .status-table td { border-bottom: 1px solid #e6edf2; padding: 10px 8px; text-align: right; white-space: nowrap; }
    .status-table tbody tr:last-child td { border-bottom: 0; }
    .status-table tbody tr { cursor: pointer; transition: background 150ms ease-out; }
    .status-table tbody tr:hover, .status-table tbody tr.active { background: #eef5f7; }
    .status-name { display: inline-flex; align-items: center; gap: 8px; font-weight: 780; color: var(--ink); }
    .status-dot { width: 9px; height: 9px; border-radius: 999px; background: var(--status-color); flex: 0 0 auto; }
    .pie-panel { position: relative; display: grid; justify-items: center; gap: 12px; min-width: 0; }
    .pie-canvas-wrap { position: relative; width: min(260px, 100%); aspect-ratio: 1; }
    .pie-chart { width: 100%; height: 100%; display: block; cursor: pointer; }
    .pie-center { position: absolute; inset: 50% auto auto 50%; transform: translate(-50%, -50%); display: grid; justify-items: center; gap: 2px; pointer-events: none; }
    .pie-center strong { color: var(--sidebar-2); font-size: 20px; line-height: 1; }
    .pie-center span { color: var(--muted); font-size: 11px; font-weight: 760; letter-spacing: .4px; text-transform: uppercase; }
    .chart-tooltip { position: fixed; z-index: 20; min-width: 180px; border: 1px solid #d8e3ea; border-radius: 8px; background: #fbfcfd; color: var(--ink); padding: 10px 11px; box-shadow: 0 14px 32px rgba(34,94,115,.20); pointer-events: none; }
    .chart-tooltip[hidden] { display: none; }
    .chart-tooltip b { display: block; margin-bottom: 6px; color: var(--sidebar-2); font-size: 12px; }
    .chart-tooltip div { display: flex; justify-content: space-between; gap: 18px; color: #4c5966; font-size: 12px; }
    .chart-tooltip strong { color: var(--ink); }
    .weekly-layout { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(360px, .95fr); gap: 16px; align-items: center; }
    .weekly-chart-wrap { position: relative; min-width: 0; height: 320px; }
    .weekly-chart { width: 100%; height: 100%; display: block; cursor: pointer; }
    .chart-view-toggle { display: flex; gap: 4px; margin-bottom: 8px; }
    .chart-view-btn { padding: 4px 14px; border-radius: 999px; border: 1.5px solid #ccd8df; background: transparent; color: #4c5966; font-size: 12px; font-weight: 600; cursor: pointer; transition: background 150ms, border-color 150ms, color 150ms; }
    .chart-view-btn:hover { background: #eef5f7; border-color: #a8c0cc; }
    .chart-view-btn.active { background: #276f86; border-color: #276f86; color: #fff; }
    .chart-legend { display: flex; flex-wrap: wrap; gap: 10px 14px; align-items: center; color: #4c5966; font-size: 12px; margin-top: 10px; }
    .legend-chip { display: inline-flex; align-items: center; gap: 6px; }
    .legend-line { width: 18px; height: 3px; border-radius: 999px; background: var(--status-color); }
    .pie-legend { width: 100%; display: grid; gap: 7px; }
    .legend-item { border: 1px solid transparent; border-radius: 7px; background: transparent; display: grid; grid-template-columns: auto 1fr auto; gap: 8px; align-items: center; color: #4c5966; font-size: 12px; padding: 5px 7px; cursor: pointer; transition: background 150ms ease-out, border-color 150ms ease-out; }
    .legend-item:hover, .legend-item.active { background: #eef5f7; border-color: #d8e3ea; }
    .legend-swatch { width: 9px; height: 9px; border-radius: 999px; background: var(--status-color); }
    .panel-state { color: var(--muted); font-size: 13px; padding: 4px 2px; }
    @media (max-width: 1180px) { .kpi-grid { grid-template-columns: repeat(2, minmax(220px, 1fr)); } }
    @media (max-width: 920px) { .kpi-grid { grid-template-columns: 1fr; } .status-layout, .weekly-layout { grid-template-columns: 1fr; } .pie-canvas-wrap { width: min(240px, 80vw); } .weekly-chart-wrap { height: 280px; } }
    @media (max-width: 760px) { .app { grid-template-columns: 1fr; } .sidebar { min-height: auto; } .main { padding: 12px; gap: 10px; } .module-bar { border-radius: 8px; } .canvas { min-height: 45vh; padding: 12px; } .kpi-card { min-height: 0; } .kpi-pair { grid-template-columns: 1fr; } }
    .top-charts-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
    .top-chart-title { margin: 0 0 12px; font-size: 13px; font-weight: 720; color: #3a4a56; letter-spacing: .3px; }
    .hbar-chart { display: grid; gap: 7px; }
    .hbar-row { display: grid; grid-template-columns: 76px 1fr; gap: 10px; align-items: center; cursor: default; }
    .hbar-label { font-size: 11.5px; font-weight: 600; color: #65717e; text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .hbar-track { position: relative; height: 24px; background: #e5edf2; border-radius: 5px; overflow: hidden; }
    .hbar-fill { height: 100%; border-radius: 5px; display: flex; align-items: center; justify-content: flex-end; padding-right: 7px; transition: opacity 130ms ease-out; min-width: 6px; }
    .hbar-fill-value { font-size: 10.5px; font-weight: 700; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: calc(100% - 4px); }
    .hbar-row:hover .hbar-fill { opacity: .82; }
    @media (max-width: 920px) { .top-charts-grid { grid-template-columns: 1fr; } }
    .tipo-badge { display: inline-block; font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 999px; letter-spacing: .3px; white-space: nowrap; }
    .tipo-badge-max { background: #d4edda; color: #1a5e30; }
    .tipo-badge-min { background: #ffeeba; color: #7a5c00; }
    .tiempos-stats-row { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 20px; }
    .tiempos-kpi { background: #fff; border: 1.5px solid #d8e8ee; border-left: 4px solid #276f86; border-radius: 8px; padding: 10px 18px; min-width: 120px; }
    .tiempos-kpi strong { display: block; font-size: 22px; color: #276f86; font-weight: 800; line-height: 1.15; }
    .tiempos-kpi span { font-size: 11px; color: #5b6673; text-transform: uppercase; letter-spacing: .5px; }
    .tiempos-alerta { background: #fff8e6; border: 1px solid #f0c040; border-radius: 8px; padding: 10px 14px; color: #7a5c00; font-size: 13px; margin-bottom: 16px; }
    .tiempos-layout { display: grid; grid-template-columns: minmax(260px, 340px) 1fr; gap: 28px; align-items: start; }
    .tiempos-charts-col { display: flex; flex-direction: column; gap: 20px; }
    .tiempos-canvas-wrap { position: relative; height: 185px; }
    .tiempos-canvas-wrap canvas { width: 100%; height: 100%; display: block; }
    .tiempos-pct-bar { display: inline-block; vertical-align: middle; width: 56px; height: 6px; background: #e5edf2; border-radius: 999px; margin-right: 6px; overflow: hidden; }
    .tiempos-pct-bar-fill { height: 100%; border-radius: 999px; }
    @media (max-width: 960px) { .tiempos-layout { grid-template-columns: 1fr; } }
    .download-overlay { position: fixed; inset: 0; z-index: 100; display: grid; place-items: center; padding: 20px; background: rgba(244,247,249,.94); }
    .download-overlay[hidden] { display: none; }
    .download-panel { width: min(520px, 100%); border: 1px solid #cbd9e1; border-radius: 12px; background: #fbfcfd; padding: 26px; box-shadow: 0 24px 64px rgba(34,94,115,.18); }
    .download-eyebrow { margin: 0 0 8px; color: var(--primary); font-size: 11px; font-weight: 820; letter-spacing: 1.1px; text-transform: uppercase; }
    .download-title { margin: 0; color: var(--sidebar-2); font-size: 24px; line-height: 1.16; font-weight: 820; }
    .download-copy { margin: 10px 0 0; max-width: 52ch; color: var(--muted); font-size: 14px; }
    .download-progress { height: 5px; margin-top: 22px; overflow: hidden; border-radius: 999px; background: #e2ebef; }
    .download-progress span { display: block; width: 42%; height: 100%; border-radius: inherit; background: var(--primary); animation: download-progress 1.35s ease-in-out infinite alternate; }
    .download-steps { display: grid; gap: 9px; margin: 20px 0 0; padding: 0; list-style: none; }
    .download-step { display: flex; align-items: center; gap: 10px; color: #52616e; font-size: 13px; }
    .download-step::before { content: ''; width: 8px; height: 8px; flex: 0 0 auto; border-radius: 50%; background: var(--primary-2); box-shadow: 0 0 0 4px rgba(87,197,182,.14); }
    .download-note { margin: 18px 0 0; color: #71808d; font-size: 12px; }
    @keyframes download-progress { from { transform: translateX(-8%); } to { transform: translateX(146%); } }
    @media (prefers-reduced-motion: reduce) { .download-progress span { animation: none; width: 100%; } }
  </style>
</head>
<body>
  <section class="download-overlay" id="downloadOverlay" role="status" aria-live="polite" aria-busy="true" hidden>
    <div class="download-panel">
      <p class="download-eyebrow">Actualizacion en curso</p>
      <h2 class="download-title">Descargando datos de ventas</h2>
      <p class="download-copy">Estamos solicitando las cotizaciones a n8n y preparando el dashboard. La pantalla se recargara automaticamente al terminar.</p>
      <div class="download-progress" aria-hidden="true"><span></span></div>
      <ol class="download-steps">
        <li class="download-step">Solicitando datos por rango de fechas</li>
        <li class="download-step">Descargando y sincronizando el CSV</li>
        <li class="download-step">Publicando metricas actualizadas</li>
      </ol>
      <p class="download-note">Mantén esta pagina abierta durante el proceso.</p>
    </div>
  </section>
  <main class="app">
    <aside class="sidebar">
      <div class="brand">
        <p class="eyebrow">Refacciones Tomas Badillo</p>
        <h1>RTB Command Center</h1>
        <p class="subtitle">Control para activar la descarga de datos desde n8n por rango de fechas.</p>
      </div>

      <form id="updateForm" class="control-panel">
        <div class="group">
          <label for="fecha_desde">Fecha inicio</label>
          <input id="fecha_desde" name="fecha_desde" type="date" required>
        </div>
        <div class="group">
          <label for="fecha_hasta">Fecha fin</label>
          <input id="fecha_hasta" name="fecha_hasta" type="date" required>
        </div>
        <div class="group">
          <label for="ambiente">Entorno</label>
          <select id="ambiente" name="ambiente">
            <option value="test">Pruebas</option>
            <option value="prod">Produccion</option>
          </select>
        </div>
        <button id="submitButton" type="submit">Activar webhook</button>
        <button id="regenerarButton" type="button" style="margin-top:8px;width:100%;background:#159895;border:none;color:#fff;border-radius:6px;padding:8px 12px;cursor:pointer;font-size:.85rem;font-weight:600;opacity:.9;" title="Regenera los snapshots con los archivos ya descargados en data/, sin llamar a n8n. Útil cuando el webhook falla pero los archivos sí llegaron.">Regenerar con archivos actuales</button>
      </form>

      <section class="status-card" aria-live="polite">
        <div class="status-row">
          <span class="status-label">Estado de envio</span>
          <span class="pill" id="statusBadge">Pendiente</span>
        </div>
        <p class="status-detail" id="statusDetail">Sin envio. Selecciona fechas y entorno para llamar n8n.</p>
      </section>

      <div class="payload">
        <b>Payload</b>
        <code id="payloadPreview">PAYLOAD_TEXT</code>
      </div>
    </aside>

    <section class="main">
      <nav class="module-bar" aria-label="Modulos del dashboard">
        <button class="module-tab active" type="button" data-module="ventas" aria-current="page">Ventas</button>
        <button class="module-tab" type="button" data-module="facturacion">Facturación</button>
        <button class="module-tab" type="button" data-module="operacion">Operacion</button>
        <button class="module-tab" type="button" data-module="compras">Compras</button>
        <button class="module-tab" type="button" data-module="inventario">Inventario</button>
        <button class="module-tab" type="button" data-module="finanzas">Finanzas</button>
        <button class="module-tab" type="button" data-module="pnl">P&amp;L</button>
      </nav>
      <div class="canvas" data-module="ventas" aria-label="Area de trabajo">
        <section id="ventasPanel" class="ventas-panel" aria-label="KPIs de ventas">
          <div class="kpi-grid" id="kpiGrid">
            <p class="panel-state">Cargando ventas...</p>
          </div>
          <section class="status-section" id="estadoSection" hidden>
            <h2 class="section-title">Estado de cotizacion</h2>
            <div class="status-layout">
              <div class="table-wrap">
                <table class="status-table">
                  <thead>
                    <tr>
                      <th>Estado</th>
                      <th>Qty</th>
                      <th>Monto c/IVA</th>
                      <th>% qty</th>
                      <th>% monto</th>
                    </tr>
                  </thead>
                  <tbody id="estadoRows"></tbody>
                </table>
              </div>
              <div class="pie-panel">
                <div class="pie-canvas-wrap">
                  <canvas class="pie-chart" id="estadoPie" width="520" height="520" aria-label="Grafica de dona por monto y estado de cotizacion"></canvas>
                  <div class="pie-center" id="estadoPieCenter"><strong>100%</strong><span>Monto</span></div>
                </div>
                <div class="chart-tooltip" id="estadoTooltip" hidden></div>
                <div class="pie-legend" id="estadoLegend"></div>
              </div>
            </div>
          </section>
          <section class="status-section" id="semanaSection" hidden>
            <h2 class="section-title" id="temporalSectionTitle">1.2 Comportamiento semanal</h2>
            <p class="section-subtitle" id="temporalSectionSubtitle">S1=1-7 · S2=8-14 · S3=15-21 · S4=22-28 · S5=29-fin de mes</p>
            <div class="weekly-layout">
              <div class="table-wrap">
                <table class="status-table">
                  <thead>
                    <tr>
                      <th id="temporalTableHeading">Sem</th>
                      <th>Cot.</th>
                      <th>Monto cot.</th>
                      <th>Apr.</th>
                      <th>Monto apr.</th>
                      <th>Conv.qty</th>
                      <th>Conv.monto</th>
                    </tr>
                  </thead>
                  <tbody id="semanaRows"></tbody>
                </table>
              </div>
              <div>
                <div class="weekly-chart-wrap">
                  <div class="chart-view-toggle">
                    <button class="chart-view-btn active" id="semanaVistaMonto" type="button">Monto</button>
                    <button class="chart-view-btn" id="semanaVistaCantidad" type="button">Cantidad</button>
                  </div>
                  <canvas class="weekly-chart" id="semanaChart" width="760" height="420" aria-label="Grafica de barras y lineas de tendencia de cotizado contra aprobado por semana"></canvas>
                  <div class="chart-tooltip" id="semanaTooltip" hidden></div>
                </div>
                <div class="chart-legend">
                  <span class="legend-chip"><span class="legend-swatch" style="--status-color:#276f86"></span><span id="semanaLegendBar1">Monto cotizado</span></span>
                  <span class="legend-chip"><span class="legend-swatch" style="--status-color:#d0b56b"></span><span id="semanaLegendBar2">Monto aprobado</span></span>
                  <span class="legend-chip"><span class="legend-line" style="--status-color:#276f86"></span><span id="semanaLegendTend1">Tend. cotizado</span></span>
                  <span class="legend-chip"><span class="legend-line" style="--status-color:#d0b56b"></span><span id="semanaLegendTend2">Tend. aprobado</span></span>
                  <span class="legend-chip"><span class="legend-line" style="--status-color:#6b46c1"></span>Tend. conv. qty</span>
                </div>
              </div>
            </div>
          </section>
          <section class="status-section" id="topClientesSection" hidden>
            <h2 class="section-title">1.3 &amp; 1.4 Top 10 clientes</h2>
            <p class="section-subtitle">Ranking por monto del periodo seleccionado</p>
            <div class="top-charts-grid">
              <div>
                <p class="top-chart-title">1.3 Más cotizan — monto cotizado c/IVA</p>
                <div class="hbar-chart" id="topCotizanChart"></div>
                <div class="chart-tooltip" id="topCotizanTooltip" hidden></div>
              </div>
              <div>
                <p class="top-chart-title">1.4 Más compran — monto aprobado c/IVA</p>
                <div class="hbar-chart" id="topApruebanyChart"></div>
                <div class="chart-tooltip" id="topApruebanyTooltip" hidden></div>
              </div>
            </div>
          </section>
          <section class="status-section" id="tipoPagoSection" hidden>
            <h2 class="section-title">1.5 Tipos de pago en cotizaciones</h2>
            <div class="status-layout">
              <div class="table-wrap">
                <table class="status-table">
                  <thead>
                    <tr>
                      <th>Tipo pago</th>
                      <th>Qty</th>
                      <th>Monto c/IVA</th>
                      <th>% monto</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody id="tipoPagoRows"></tbody>
                </table>
              </div>
              <div class="pie-panel">
                <div class="pie-canvas-wrap">
                  <canvas class="pie-chart" id="tipoPie" width="520" height="520" aria-label="Grafica de dona por cantidad de cotizaciones segun tipo de pago"></canvas>
                  <div class="pie-center" id="tipoPieCenter"><strong id="tipoPieCenterVal"></strong><span>Cot.</span></div>
                </div>
                <div class="chart-tooltip" id="tipoPagoTooltip" hidden></div>
                <div class="pie-legend" id="tipoPagoLegend"></div>
              </div>
            </div>
          </section>
          <section class="status-section" id="tiemposAprSection" hidden>
            <h2 class="section-title">1.6 Tiempos de aprobación</h2>
            <p class="section-subtitle">Solo cotizaciones aprobadas con ambas fechas registradas</p>
            <div id="tiemposAprAlerta" class="tiempos-alerta" hidden></div>
            <div class="tiempos-stats-row" id="tiemposAprKpis"></div>
            <div class="tiempos-layout">
              <div>
                <p class="top-chart-title">Distribución por rango</p>
                <table class="status-table">
                  <thead>
                    <tr>
                      <th>Rango</th>
                      <th style="text-align:right">Cot.</th>
                      <th style="text-align:right">%</th>
                    </tr>
                  </thead>
                  <tbody id="tiemposAprRangos"></tbody>
                </table>
              </div>
              <div class="tiempos-charts-col">
                <div>
                  <p class="top-chart-title" id="tiemposTemporalTitle">Promedio de días por semana</p>
                  <div class="tiempos-canvas-wrap">
                    <canvas id="tiemposSemanCanvas" aria-label="Grafica de barras de dias promedio de aprobacion por semana"></canvas>
                    <div class="chart-tooltip" id="tiemposSemanTooltip" hidden></div>
                  </div>
                  <div class="chart-legend" style="margin-top:6px">
                    <span class="legend-chip"><span class="legend-swatch" style="--status-color:#159895"></span>Días prom.</span>
                    <span class="legend-chip"><span class="legend-line" style="--status-color:#276f86;border-top:2px dashed #276f86;background:none"></span>Promedio global</span>
                    <span class="legend-chip"><span class="legend-line" style="--status-color:#d0b56b;border-top:2px dashed #d0b56b;background:none"></span>Tendencia</span>
                  </div>
                </div>
                <div>
                  <p class="top-chart-title">Distribución por días exactos</p>
                  <div class="tiempos-canvas-wrap">
                    <canvas id="tiemposHistCanvas" aria-label="Histograma de cantidad de aprobaciones por dias exactos"></canvas>
                    <div class="chart-tooltip" id="tiemposHistTooltip" hidden></div>
                  </div>
                </div>
              </div>
            </div>
          </section>
        </section>
        <section id="facturacionPanel" class="facturacion-panel" aria-label="KPIs de facturación" hidden>
          <div class="kpi-grid facturacion-kpi-grid" id="facturacionKpiGrid">
            <p class="panel-state">Cargando facturación...</p>
          </div>
          <section class="status-section" id="facturacionEstadoSection">
            <h2 class="section-title">Estado de facturación</h2>
            <p class="section-subtitle">Facturas vigentes del periodo, sin duplicar registros secundarios repetidos.</p>
            <div class="status-layout">
              <div class="table-wrap">
                <table class="status-table">
                  <thead><tr><th>Estado</th><th>Qty</th><th>Monto</th><th>% qty</th><th>% monto</th></tr></thead>
                  <tbody id="facturacionEstadoRows"></tbody>
                </table>
              </div>
              <div class="pie-panel">
                <div class="pie-canvas-wrap">
                  <canvas class="pie-chart" id="facturacionEstadoPie" width="520" height="520" aria-label="Gráfica de dona por monto y estado de factura"></canvas>
                  <div class="pie-center" id="facturacionEstadoPieCenter"><strong>100%</strong><span>Monto</span></div>
                </div>
                <div class="chart-tooltip" id="facturacionEstadoTooltip" hidden></div>
                <div class="pie-legend" id="facturacionEstadoLegend"></div>
              </div>
            </div>
          </section>
          <section class="status-section">
            <h2 class="section-title">Comportamiento temporal</h2>
            <p class="section-subtitle">Facturas vigentes por fecha de facturación.</p>
            <div class="weekly-layout">
              <div class="table-wrap">
                <table class="status-table">
                  <thead><tr><th>Periodo</th><th>Qty</th><th>Monto facturado</th></tr></thead>
                  <tbody id="facturacionTemporalRows"></tbody>
                  <tfoot id="facturacionTemporalTotals"></tfoot>
                </table>
              </div>
              <div>
                <div class="weekly-chart-wrap">
                  <div class="chart-view-toggle">
                    <button class="chart-view-btn active" id="factTemporalVistaMonto" type="button">Monto</button>
                    <button class="chart-view-btn" id="factTemporalVistaCantidad" type="button">Cantidad</button>
                  </div>
                  <canvas class="weekly-chart" id="facturacionTemporalChart" width="760" height="420" aria-label="Gráfica de barras y tendencia de facturas vigentes por periodo"></canvas>
                  <div class="chart-tooltip" id="facturacionTemporalTooltip" hidden></div>
                </div>
                <div class="chart-legend">
                  <span class="legend-chip"><span class="legend-swatch" style="--status-color:#159895"></span><span id="factTemporalLegendBar">Monto facturado</span></span>
                  <span class="legend-chip"><span class="legend-line" style="--status-color:#159895"></span><span id="factTemporalLegendTend">Tendencia monto</span></span>
                </div>
              </div>
            </div>
          </section>
          <section class="status-section" id="cicloSection">
            <h2 class="section-title">Ciclo de Facturación Completo</h2>
            <p class="section-subtitle">Días promedio por etapa: Pedido aprobado → Factura emitida → Validada por cliente → Asociada al complemento de pago SAT.</p>
            <div class="status-layout">
              <div class="table-wrap">
                <table class="status-table">
                  <thead><tr><th>Etapa</th><th>Promedio</th><th>Mediana</th><th>Máximo</th><th>N</th></tr></thead>
                  <tbody id="cicloEtapasRows"></tbody>
                </table>
              </div>
              <div class="ciclo-chart-wrap">
                <canvas class="weekly-chart" id="cicloEtapasChart" width="560" height="280" aria-label="Gráfica de barras de días promedio por etapa del ciclo de facturación"></canvas>
                <div class="chart-tooltip" id="cicloEtapasTooltip" hidden></div>
              </div>
            </div>
            <p class="section-subtitle" style="margin-top:14px">Evolución del ciclo total promedio por periodo.</p>
            <div class="weekly-layout">
              <div class="table-wrap">
                <table class="status-table">
                  <thead><tr><th>Periodo</th><th>Ciclo total (días)</th></tr></thead>
                  <tbody id="cicloTemporalRows"></tbody>
                </table>
              </div>
              <div class="weekly-chart-wrap">
                <canvas class="weekly-chart" id="cicloTemporalChart" width="760" height="320" aria-label="Gráfica de evolución del ciclo total por periodo"></canvas>
                <div class="chart-tooltip" id="cicloTemporalTooltip" hidden></div>
              </div>
            </div>
          </section>
          <section class="status-section">
            <h2 class="section-title">Alertas operativas</h2>
            <div class="facturacion-alerts" id="facturacionAlerts"></div>
          </section>
        </section>
      </div>
    </section>
  </main>

  <script>
    const form = document.querySelector('#updateForm');
    const submitButton = document.querySelector('#submitButton');
    const regenerarButton = document.querySelector('#regenerarButton');
    const downloadOverlay = document.querySelector('#downloadOverlay');
    const statusBadge = document.querySelector('#statusBadge');
    const statusDetail = document.querySelector('#statusDetail');
    const payloadPreview = document.querySelector('#payloadPreview');
    const moduleTabs = document.querySelectorAll('.module-tab');
    const canvas = document.querySelector('.canvas');
    const ventasPanel = document.querySelector('#ventasPanel');
    const facturacionPanel = document.querySelector('#facturacionPanel');
    const facturacionKpiGrid = document.querySelector('#facturacionKpiGrid');
    const facturacionEstadoSection = document.querySelector('#facturacionEstadoSection');
    const facturacionEstadoRows = document.querySelector('#facturacionEstadoRows');
    const facturacionEstadoPie = document.querySelector('#facturacionEstadoPie');
    const facturacionEstadoPieCenter = document.querySelector('#facturacionEstadoPieCenter');
    const facturacionEstadoTooltip = document.querySelector('#facturacionEstadoTooltip');
    const facturacionEstadoLegend = document.querySelector('#facturacionEstadoLegend');
    const facturacionTemporalRows = document.querySelector('#facturacionTemporalRows');
    const facturacionTemporalChart = document.querySelector('#facturacionTemporalChart');
    const facturacionTemporalTooltip = document.querySelector('#facturacionTemporalTooltip');
    const facturacionTemporalTotals = document.querySelector('#facturacionTemporalTotals');
    const factTemporalVistaMonto = document.querySelector('#factTemporalVistaMonto');
    const factTemporalVistaCantidad = document.querySelector('#factTemporalVistaCantidad');
    const factTemporalLegendBar = document.querySelector('#factTemporalLegendBar');
    const factTemporalLegendTend = document.querySelector('#factTemporalLegendTend');
    const cicloSection = document.querySelector('#cicloSection');
    const cicloEtapasRows = document.querySelector('#cicloEtapasRows');
    const cicloEtapasChart = document.querySelector('#cicloEtapasChart');
    const cicloEtapasTooltip = document.querySelector('#cicloEtapasTooltip');
    const cicloTemporalRows = document.querySelector('#cicloTemporalRows');
    const cicloTemporalChart = document.querySelector('#cicloTemporalChart');
    const cicloTemporalTooltip = document.querySelector('#cicloTemporalTooltip');
    const facturacionAlerts = document.querySelector('#facturacionAlerts');
    const kpiGrid = document.querySelector('#kpiGrid');
    const estadoSection = document.querySelector('#estadoSection');
    const estadoRows = document.querySelector('#estadoRows');
    const estadoPie = document.querySelector('#estadoPie');
    const estadoPieCenter = document.querySelector('#estadoPieCenter');
    const estadoTooltip = document.querySelector('#estadoTooltip');
    const estadoLegend = document.querySelector('#estadoLegend');
    const semanaSection = document.querySelector('#semanaSection');
    const semanaRows = document.querySelector('#semanaRows');
    const temporalSectionTitle = document.querySelector('#temporalSectionTitle');
    const temporalSectionSubtitle = document.querySelector('#temporalSectionSubtitle');
    const temporalTableHeading = document.querySelector('#temporalTableHeading');
    const tiemposTemporalTitle = document.querySelector('#tiemposTemporalTitle');
    const semanaChart = document.querySelector('#semanaChart');
    const semanaTooltip = document.querySelector('#semanaTooltip');
    const semanaVistaMonto = document.querySelector('#semanaVistaMonto');
    const semanaVistaCantidad = document.querySelector('#semanaVistaCantidad');
    const semanaLegendBar1 = document.querySelector('#semanaLegendBar1');
    const semanaLegendBar2 = document.querySelector('#semanaLegendBar2');
    const semanaLegendTend1 = document.querySelector('#semanaLegendTend1');
    const semanaLegendTend2 = document.querySelector('#semanaLegendTend2');
    const topClientesSection = document.querySelector('#topClientesSection');
    const topCotizanChart = document.querySelector('#topCotizanChart');
    const topCotizanTooltip = document.querySelector('#topCotizanTooltip');
    const topApruebanyChart = document.querySelector('#topApruebanyChart');
    const topApruebanyTooltip = document.querySelector('#topApruebanyTooltip');
    const tipoPagoSection = document.querySelector('#tipoPagoSection');
    const tipoPagoRows = document.querySelector('#tipoPagoRows');
    const tipoPie = document.querySelector('#tipoPie');
    const tipoPieCenter = document.querySelector('#tipoPieCenterVal');
    const tipoPagoTooltip = document.querySelector('#tipoPagoTooltip');
    const tipoPagoLegend = document.querySelector('#tipoPagoLegend');
    const tiemposAprSection = document.querySelector('#tiemposAprSection');
    const tiemposAprAlerta = document.querySelector('#tiemposAprAlerta');
    const tiemposAprKpis = document.querySelector('#tiemposAprKpis');
    const tiemposAprRangos = document.querySelector('#tiemposAprRangos');
    const tiemposSemanCanvas = document.querySelector('#tiemposSemanCanvas');
    const tiemposSemanTooltip = document.querySelector('#tiemposSemanTooltip');
    const tiemposHistCanvas = document.querySelector('#tiemposHistCanvas');
    const tiemposHistTooltip = document.querySelector('#tiemposHistTooltip');
    const statusColors = ['#276f86', '#d0b56b', '#d96058', '#57c5b6', '#8a6f35', '#5b6673'];
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let ventasLoaded = false;
    let facturacionLoaded = false;
    let estadoChart = { slices: [], activeIndex: null };
    let facturacionEstadoChart = { slices: [], activeIndex: null };
    let facturacionTemporalState = { rows: [], activeIndex: null, points: [], tendencias: null, vista: 'monto' };
    let cicloEtapasState = { rows: [], activeIndex: null, points: [] };
    let cicloTemporalState = { rows: [], activeIndex: null, points: [] };
    let tipoPagoChart = { slices: [], activeIndex: null };
    let semanaChartState = { rows: [], activeIndex: null, points: [], trends: null, vista: 'monto' };
    let kpiCanvasStates = [];
    let kpiAnimationFrame = null;

    function currentPayload() {
      return [{ after: form.fecha_desde.value }, { before: form.fecha_hasta.value }];
    }

    function refreshPayload() {
      payloadPreview.textContent = JSON.stringify(currentPayload());
    }

    function setStatus(label, kind, detail) {
      statusBadge.textContent = label;
      statusBadge.className = kind ? `pill ${kind}` : 'pill';
      statusDetail.textContent = detail;
    }

    function showDownloadOverlay() {
      downloadOverlay.hidden = false;
      document.body.setAttribute('aria-busy', 'true');
    }

    function hideDownloadOverlay() {
      downloadOverlay.hidden = true;
      document.body.removeAttribute('aria-busy');
    }

    function formatMoney(value) {
      return new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN', maximumFractionDigits: 0 }).format(Number(value || 0));
    }

    function formatPercent(value) {
      return new Intl.NumberFormat('es-MX', { style: 'percent', minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(Number(value || 0));
    }

    function formatNumber(value) {
      return new Intl.NumberFormat('es-MX', { maximumFractionDigits: 0 }).format(Number(value || 0));
    }

    function kpiValue(kpis, key, type) {
      const value = kpis[key];
      if (type === 'money') return formatMoney(value);
      if (type === 'percent') return formatPercent(value);
      if (type === 'pp') return `${Number((value || 0) * 100).toFixed(1)} pp`;
      return formatNumber(value);
    }

    function metric(label, value, note) {
      return `
        <div class="kpi-metric">
          <div class="kpi-label">${label}</div>
          <div class="kpi-value">${value}</div>
          <div class="kpi-note">${note}</div>
        </div>
      `;
    }

    function delta(label, value, note) {
      return `
        <div class="kpi-delta">
          <div>
            <div class="kpi-label">${label}</div>
            <div class="kpi-note">${note}</div>
          </div>
          <div class="kpi-value">${value}</div>
        </div>
      `;
    }

    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
    }

    function renderEstadoChart(activeIndex = null) {
      const ctx = estadoPie.getContext('2d');
      const rect = estadoPie.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      estadoPie.width = Math.max(1, Math.round(rect.width * dpr));
      estadoPie.height = Math.max(1, Math.round(rect.height * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, rect.width, rect.height);

      const cx = rect.width / 2;
      const cy = rect.height / 2;
      const radius = Math.min(rect.width, rect.height) * 0.43;
      const innerRadius = radius * 0.58;
      estadoChart.slices.forEach((slice, index) => {
        const isActive = index === activeIndex;
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.arc(cx, cy, radius + (isActive ? 8 : 0), slice.start, slice.end);
        ctx.closePath();
        ctx.fillStyle = slice.color;
        ctx.globalAlpha = activeIndex === null || isActive ? 1 : 0.42;
        ctx.fill();
        ctx.globalAlpha = 1;
        ctx.lineWidth = isActive ? 4 : 2;
        ctx.strokeStyle = '#fbfcfd';
        ctx.stroke();
      });

      ctx.globalCompositeOperation = 'destination-out';
      ctx.beginPath();
      ctx.arc(cx, cy, innerRadius, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalCompositeOperation = 'source-over';
      ctx.beginPath();
      ctx.arc(cx, cy, innerRadius, 0, Math.PI * 2);
      ctx.fillStyle = '#fbfcfd';
      ctx.fill();
      ctx.strokeStyle = '#e0e8ee';
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    function sliceAtEvent(event) {
      const rect = estadoPie.getBoundingClientRect();
      const x = event.clientX - rect.left - rect.width / 2;
      const y = event.clientY - rect.top - rect.height / 2;
      const distance = Math.hypot(x, y);
      const outer = Math.min(rect.width, rect.height) * 0.47;
      const inner = outer * 0.52;
      if (distance < inner || distance > outer) return null;
      let angle = Math.atan2(y, x);
      if (angle < -Math.PI / 2) angle += Math.PI * 2;
      return estadoChart.slices.findIndex((slice) => angle >= slice.start && angle <= slice.end);
    }

    function setActiveEstado(index, event) {
      estadoChart.activeIndex = index >= 0 ? index : null;
      renderEstadoChart(estadoChart.activeIndex);
      estadoLegend.querySelectorAll('.legend-item').forEach((item, itemIndex) => item.classList.toggle('active', itemIndex === estadoChart.activeIndex));
      estadoRows.querySelectorAll('tr').forEach((row, rowIndex) => row.classList.toggle('active', rowIndex === estadoChart.activeIndex));
      if (estadoChart.activeIndex === null) {
        estadoTooltip.hidden = true;
        estadoPieCenter.innerHTML = '<strong>100%</strong><span>Monto</span>';
        return;
      }
      const slice = estadoChart.slices[estadoChart.activeIndex];
      estadoPieCenter.innerHTML = `<strong>${formatPercent(slice.montoPct)}</strong><span>${escapeHtml(slice.estado)}</span>`;
      if (event) { placeTooltipNear(estadoTooltip, event.clientX, event.clientY); }
      estadoTooltip.innerHTML = `
        <b>${escapeHtml(slice.estado)}</b>
        <div><span>Monto</span><strong>${formatMoney(slice.monto)}</strong></div>
        <div><span>Qty</span><strong>${formatNumber(slice.qty)}</strong></div>
        <div><span>% monto</span><strong>${formatPercent(slice.montoPct)}</strong></div>
        <div><span>% qty</span><strong>${formatPercent(slice.qtyPct)}</strong></div>
      `;
      estadoTooltip.hidden = false;
    }

    function renderEstados(estados) {
      const rows = [...(estados || [])].sort((a, b) => Number(b.m || 0) - Number(a.m || 0));
      const totalQty = rows.reduce((sum, row) => sum + Number(row.n || 0), 0);
      const totalMonto = rows.reduce((sum, row) => sum + Number(row.m || 0), 0);
      if (!rows.length || !totalMonto) {
        estadoSection.hidden = true;
        semanaSection.hidden = true;
        return;
      }

      estadoRows.innerHTML = rows.map((row, index) => {
        const color = statusColors[index % statusColors.length];
        const qtyPct = totalQty ? Number(row.n || 0) / totalQty : 0;
        const montoPct = totalMonto ? Number(row.m || 0) / totalMonto : 0;
        return `
          <tr data-index="${index}">
            <td><span class="status-name" style="--status-color: ${color}"><span class="status-dot"></span>${escapeHtml(row.estado)}</span></td>
            <td>${formatNumber(row.n)}</td>
            <td>${formatMoney(row.m)}</td>
            <td>${formatPercent(qtyPct)}</td>
            <td>${formatPercent(montoPct)}</td>
          </tr>
        `;
      }).join('');

      let current = -Math.PI / 2;
      estadoChart.slices = rows.map((row, index) => {
        const value = Number(row.m || 0);
        const span = totalMonto ? (value / totalMonto) * Math.PI * 2 : 0;
        const slice = {
          estado: row.estado,
          qty: Number(row.n || 0),
          monto: value,
          qtyPct: totalQty ? Number(row.n || 0) / totalQty : 0,
          montoPct: totalMonto ? value / totalMonto : 0,
          color: statusColors[index % statusColors.length],
          start: current,
          end: current + span,
        };
        current += span;
        return slice;
      });

      estadoLegend.innerHTML = estadoChart.slices.map((slice, index) => `
        <button class="legend-item" type="button" style="--status-color: ${slice.color}" data-index="${index}">
          <span class="legend-swatch"></span>
          <span>${escapeHtml(slice.estado)}</span>
          <strong>${formatPercent(slice.montoPct)}</strong>
        </button>
      `).join('');
      estadoSection.hidden = false;
      setActiveEstado(null);
    }

    estadoPie.addEventListener('mousemove', (event) => {
      const index = sliceAtEvent(event);
      if (index >= 0) setActiveEstado(index, event);
      else setActiveEstado(null);
    });
    estadoPie.addEventListener('mouseleave', () => setActiveEstado(null));
    estadoLegend.addEventListener('mousemove', (event) => {
      const item = event.target.closest('.legend-item');
      if (!item) return;
      setActiveEstado(Number(item.dataset.index), event);
    });
    estadoLegend.addEventListener('mouseleave', () => setActiveEstado(null));
    estadoRows.addEventListener('mousemove', (event) => {
      const row = event.target.closest('tr');
      if (!row) return;
      setActiveEstado(Number(row.dataset.index), event);
    });
    estadoRows.addEventListener('mouseleave', () => setActiveEstado(null));

    function renderFacturacionEstadoChart(activeIndex = null) {
      const ctx = facturacionEstadoPie.getContext('2d');
      const rect = facturacionEstadoPie.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      facturacionEstadoPie.width = Math.max(1, Math.round(rect.width * dpr));
      facturacionEstadoPie.height = Math.max(1, Math.round(rect.height * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, rect.width, rect.height);
      const cx = rect.width / 2;
      const cy = rect.height / 2;
      const radius = Math.min(rect.width, rect.height) * 0.43;
      const innerRadius = radius * 0.58;
      facturacionEstadoChart.slices.forEach((slice, index) => {
        const isActive = index === activeIndex;
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.arc(cx, cy, radius + (isActive ? 8 : 0), slice.start, slice.end);
        ctx.closePath();
        ctx.fillStyle = slice.color;
        ctx.globalAlpha = activeIndex === null || isActive ? 1 : 0.42;
        ctx.fill();
        ctx.globalAlpha = 1;
        ctx.lineWidth = isActive ? 4 : 2;
        ctx.strokeStyle = '#fbfcfd';
        ctx.stroke();
      });
      ctx.globalCompositeOperation = 'destination-out';
      ctx.beginPath();
      ctx.arc(cx, cy, innerRadius, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalCompositeOperation = 'source-over';
      ctx.beginPath();
      ctx.arc(cx, cy, innerRadius, 0, Math.PI * 2);
      ctx.fillStyle = '#fbfcfd';
      ctx.fill();
      ctx.strokeStyle = '#e0e8ee';
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    function facturacionSliceAtEvent(event) {
      const rect = facturacionEstadoPie.getBoundingClientRect();
      const x = event.clientX - rect.left - rect.width / 2;
      const y = event.clientY - rect.top - rect.height / 2;
      const distance = Math.hypot(x, y);
      const outer = Math.min(rect.width, rect.height) * 0.47;
      const inner = outer * 0.52;
      if (distance < inner || distance > outer) return null;
      let angle = Math.atan2(y, x);
      if (angle < -Math.PI / 2) angle += Math.PI * 2;
      return facturacionEstadoChart.slices.findIndex((slice) => angle >= slice.start && angle <= slice.end);
    }

    function setActiveFacturacionEstado(index, event) {
      facturacionEstadoChart.activeIndex = index >= 0 ? index : null;
      renderFacturacionEstadoChart(facturacionEstadoChart.activeIndex);
      facturacionEstadoLegend.querySelectorAll('.legend-item').forEach((item, i) => item.classList.toggle('active', i === facturacionEstadoChart.activeIndex));
      facturacionEstadoRows.querySelectorAll('tr').forEach((row, i) => row.classList.toggle('active', i === facturacionEstadoChart.activeIndex));
      if (facturacionEstadoChart.activeIndex === null) {
        facturacionEstadoTooltip.hidden = true;
        facturacionEstadoPieCenter.innerHTML = '<strong>100%</strong><span>Monto</span>';
        return;
      }
      const slice = facturacionEstadoChart.slices[facturacionEstadoChart.activeIndex];
      facturacionEstadoPieCenter.innerHTML = `<strong>${formatPercent(slice.montoPct)}</strong><span>${escapeHtml(slice.estado)}</span>`;
      if (event) { placeTooltipNear(facturacionEstadoTooltip, event.clientX, event.clientY); }
      facturacionEstadoTooltip.innerHTML = `
        <b>${escapeHtml(slice.estado)}</b>
        <div><span>Monto</span><strong>${formatMoney(slice.monto)}</strong></div>
        <div><span>Qty</span><strong>${formatNumber(slice.qty)}</strong></div>
        <div><span>% monto</span><strong>${formatPercent(slice.montoPct)}</strong></div>
        <div><span>% qty</span><strong>${formatPercent(slice.qtyPct)}</strong></div>
      `;
      facturacionEstadoTooltip.hidden = false;
    }

    function renderFacturacionEstados(estados) {
      const rows = [...(estados || [])].sort((a, b) => Number(b.m || 0) - Number(a.m || 0));
      const totalQty = rows.reduce((sum, row) => sum + Number(row.n || 0), 0);
      const totalMonto = rows.reduce((sum, row) => sum + Number(row.m || 0), 0);
      facturacionEstadoRows.innerHTML = rows.map((row, index) => {
        const color = statusColors[index % statusColors.length];
        const qtyPct = totalQty ? Number(row.n || 0) / totalQty : 0;
        const montoPct = totalMonto ? Number(row.m || 0) / totalMonto : 0;
        return `<tr data-index="${index}">
          <td><span class="status-name" style="--status-color: ${color}"><span class="status-dot"></span>${escapeHtml(row.estado)}</span></td>
          <td>${formatNumber(row.n)}</td>
          <td>${formatMoney(row.m)}</td>
          <td>${formatPercent(qtyPct)}</td>
          <td>${formatPercent(montoPct)}</td>
        </tr>`;
      }).join('') || '<tr><td colspan="5">Sin facturas vigentes en el periodo.</td></tr>';
      let current = -Math.PI / 2;
      facturacionEstadoChart.slices = rows.map((row, index) => {
        const value = Number(row.m || 0);
        const span = totalMonto ? (value / totalMonto) * Math.PI * 2 : 0;
        const slice = {
          estado: row.estado,
          qty: Number(row.n || 0),
          monto: value,
          qtyPct: totalQty ? Number(row.n || 0) / totalQty : 0,
          montoPct: totalMonto ? value / totalMonto : 0,
          color: statusColors[index % statusColors.length],
          start: current,
          end: current + span,
        };
        current += span;
        return slice;
      });
      facturacionEstadoLegend.innerHTML = facturacionEstadoChart.slices.map((slice, index) => `
        <button class="legend-item" type="button" style="--status-color: ${slice.color}" data-index="${index}">
          <span class="legend-swatch"></span>
          <span>${escapeHtml(slice.estado)}</span>
          <strong>${formatPercent(slice.montoPct)}</strong>
        </button>
      `).join('');
      setActiveFacturacionEstado(null);
    }

    facturacionEstadoPie.addEventListener('mousemove', (event) => {
      const index = facturacionSliceAtEvent(event);
      if (index >= 0) setActiveFacturacionEstado(index, event);
      else setActiveFacturacionEstado(null);
    });
    facturacionEstadoPie.addEventListener('mouseleave', () => setActiveFacturacionEstado(null));
    facturacionEstadoLegend.addEventListener('mousemove', (event) => {
      const item = event.target.closest('.legend-item');
      if (!item) return;
      setActiveFacturacionEstado(Number(item.dataset.index), event);
    });
    facturacionEstadoLegend.addEventListener('mouseleave', () => setActiveFacturacionEstado(null));
    facturacionEstadoRows.addEventListener('mousemove', (event) => {
      const row = event.target.closest('tr');
      if (!row) return;
      setActiveFacturacionEstado(Number(row.dataset.index), event);
    });
    facturacionEstadoRows.addEventListener('mouseleave', () => setActiveFacturacionEstado(null));

    function drawFacturacionTemporalChart(activeIndex = null) {
      const ctx = facturacionTemporalChart.getContext('2d');
      const rect = resizeCanvasToDisplay(facturacionTemporalChart, ctx);
      const width = rect.width;
      const height = rect.height;
      ctx.clearRect(0, 0, width, height);
      const rows = facturacionTemporalState.rows;
      if (!rows.length) return;

      const esCantidad = facturacionTemporalState.vista === 'cantidad';
      const val = (row) => esCantidad ? row.cantidad : row.monto;
      const barColor = esCantidad ? '#57c5b6' : '#159895';
      const fmtY = esCantidad
        ? (v) => formatNumber(Math.round(v))
        : (v) => formatMoney(v).replace('MXN', '').trim();

      const pad = { left: 64, right: 24, top: 26, bottom: 46 };
      const plotW = width - pad.left - pad.right;
      const plotH = height - pad.top - pad.bottom;
      const maxVal = Math.max(...rows.map(val), 1);
      const maxY = maxVal * 1.12;
      const slot = plotW / rows.length;
      const barW = Math.min(48, slot * 0.55);
      facturacionTemporalState.points = [];

      ctx.fillStyle = '#fbfcfd';
      ctx.fillRect(0, 0, width, height);
      ctx.font = '11px -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif';

      for (let i = 0; i <= 4; i++) {
        const y = pad.top + plotH * (i / 4);
        ctx.strokeStyle = '#e5edf2';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(pad.left, y);
        ctx.lineTo(width - pad.right, y);
        ctx.stroke();
        ctx.textAlign = 'right';
        ctx.textBaseline = 'middle';
        ctx.fillStyle = '#65717e';
        ctx.fillText(fmtY(maxY * (1 - i / 4)), pad.left - 8, y);
      }

      rows.forEach((row, index) => {
        const centerX = pad.left + slot * index + slot / 2;
        const h = (val(row) / maxY) * plotH;
        const x = centerX - barW / 2;
        const y = pad.top + plotH - h;
        const isActive = activeIndex === index;

        ctx.globalAlpha = activeIndex === null || isActive ? 1 : 0.35;
        drawRoundRect(ctx, x, y, barW, h, 5);
        ctx.fillStyle = barColor;
        ctx.fill();
        ctx.globalAlpha = 1;

        ctx.fillStyle = isActive ? '#225e73' : '#65717e';
        ctx.font = `${isActive ? 800 : 700} 12px -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.fillText(row.etiqueta, centerX, pad.top + plotH + 14);
        facturacionTemporalState.points.push({ x: centerX, y, row });
      });

      const tendencias = facturacionTemporalState.tendencias;
      if (tendencias) {
        const trendKey = esCantidad ? 'cantidad' : 'monto';
        const trend = tendencias[trendKey];
        if (trend && rows.length > 1) {
          const n = rows.length;
          const x0 = pad.left + slot / 2;
          const xN = pad.left + slot * (n - 1) + slot / 2;
          const yFromVal = (v) => pad.top + plotH - (v / maxY) * plotH;
          ctx.setLineDash([6, 4]);
          ctx.beginPath();
          ctx.moveTo(x0, yFromVal(trend.start));
          ctx.lineTo(xN, yFromVal(trend.end));
          ctx.strokeStyle = barColor;
          ctx.lineWidth = 2.5;
          ctx.lineJoin = 'round';
          ctx.lineCap = 'round';
          ctx.stroke();
          ctx.setLineDash([]);
        }
      }

      rows.forEach((row, index) => {
        const point = facturacionTemporalState.points[index];
        const isActive = activeIndex === index;
        ctx.beginPath();
        ctx.arc(point.x, point.y, isActive ? 5 : 3.5, 0, Math.PI * 2);
        ctx.fillStyle = '#fbfcfd';
        ctx.fill();
        ctx.lineWidth = isActive ? 4 : 2.5;
        ctx.strokeStyle = barColor;
        ctx.stroke();
      });

      if (activeIndex !== null) {
        const point = facturacionTemporalState.points[activeIndex];
        ctx.beginPath();
        ctx.arc(point.x, point.y, 13, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(21,152,149,.22)';
        ctx.lineWidth = 6;
        ctx.stroke();
      }

      ctx.fillStyle = '#65717e';
      ctx.font = '11px -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'top';
      ctx.fillText(esCantidad ? 'Barras: cantidad · Línea: tendencia' : 'Barras: monto facturado · Línea: tendencia', pad.left, 8);
    }

    function setActiveFacturacionTemporal(index, event) {
      facturacionTemporalState.activeIndex = index >= 0 ? index : null;
      drawFacturacionTemporalChart(facturacionTemporalState.activeIndex);
      facturacionTemporalRows.querySelectorAll('tr').forEach((row, i) => row.classList.toggle('active', i === facturacionTemporalState.activeIndex));
      if (facturacionTemporalState.activeIndex === null) {
        facturacionTemporalTooltip.hidden = true;
        return;
      }
      const row = facturacionTemporalState.rows[facturacionTemporalState.activeIndex];
      if (event) { placeTooltipNear(facturacionTemporalTooltip, event.clientX, event.clientY); }
      facturacionTemporalTooltip.innerHTML = `
        <b>${escapeHtml(row.etiqueta)}</b>
        <div><span>Qty</span><strong>${formatNumber(row.cantidad)}</strong></div>
        <div><span>Monto</span><strong>${formatMoney(row.monto)}</strong></div>
      `;
      facturacionTemporalTooltip.hidden = false;
    }

    function renderFacturacionTemporal(temporal) {
      const periodos = temporal?.periodos || [];
      const rows = periodos.map((row) => ({
        etiqueta: row.etiqueta || '',
        cantidad: Number(row.cantidad || 0),
        monto: Number(row.monto || 0),
      }));
      if (!rows.length) return;
      facturacionTemporalState.rows = rows;
      facturacionTemporalState.tendencias = temporal?.tendencias || null;
      facturacionTemporalRows.innerHTML = rows.map((row, index) => `
        <tr data-index="${index}">
          <td><strong>${escapeHtml(row.etiqueta)}</strong></td>
          <td>${formatNumber(row.cantidad)}</td>
          <td>${formatMoney(row.monto)}</td>
        </tr>
      `).join('');
      const totalQty = rows.reduce((s, r) => s + r.cantidad, 0);
      const totalMonto = rows.reduce((s, r) => s + r.monto, 0);
      facturacionTemporalTotals.innerHTML = `<tr><td><strong>Total</strong></td><td>${formatNumber(totalQty)}</td><td>${formatMoney(totalMonto)}</td></tr>`;
      setActiveFacturacionTemporal(null);
    }

    function setFacturacionTemporalVista(vista) {
      facturacionTemporalState.vista = vista;
      factTemporalVistaMonto.classList.toggle('active', vista === 'monto');
      factTemporalVistaCantidad.classList.toggle('active', vista === 'cantidad');
      factTemporalLegendBar.textContent = vista === 'cantidad' ? 'Qty facturas' : 'Monto facturado';
      factTemporalLegendTend.textContent = vista === 'cantidad' ? 'Tendencia qty' : 'Tendencia monto';
      drawFacturacionTemporalChart(facturacionTemporalState.activeIndex);
    }
    factTemporalVistaMonto.addEventListener('click', () => setFacturacionTemporalVista('monto'));
    factTemporalVistaCantidad.addEventListener('click', () => setFacturacionTemporalVista('cantidad'));

    facturacionTemporalChart.addEventListener('mousemove', (event) => {
      const rect = facturacionTemporalChart.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const nearest = facturacionTemporalState.points.reduce((best, point, index) => {
        const distance = Math.abs(point.x - x);
        return distance < best.distance ? { index, distance } : best;
      }, { index: -1, distance: Infinity });
      if (nearest.distance <= Math.max(42, rect.width / Math.max(facturacionTemporalState.rows.length * 2, 1))) setActiveFacturacionTemporal(nearest.index, event);
      else setActiveFacturacionTemporal(null);
    });
    facturacionTemporalChart.addEventListener('mouseleave', () => setActiveFacturacionTemporal(null));
    facturacionTemporalRows.addEventListener('mousemove', (event) => {
      const row = event.target.closest('tr');
      if (!row) return;
      setActiveFacturacionTemporal(Number(row.dataset.index), event);
    });
    facturacionTemporalRows.addEventListener('mouseleave', () => setActiveFacturacionTemporal(null));

    const CICLO_COLORS = ['#276f86', '#57c5b6', '#d0b56b', '#d96058'];
    const CICLO_LABELS = ['Ped.→Fact.', 'Fact.→Val.', 'Val.→Asoc.', 'Ciclo total'];

    function drawCicloEtapasChart(activeIndex = null) {
      const ctx = cicloEtapasChart.getContext('2d');
      const rect = resizeCanvasToDisplay(cicloEtapasChart, ctx);
      const width = rect.width;
      const height = rect.height;
      ctx.clearRect(0, 0, width, height);
      const rows = cicloEtapasState.rows;
      if (!rows.length) return;

      const pad = { left: 38, right: 16, top: 20, bottom: 44 };
      const plotW = width - pad.left - pad.right;
      const plotH = height - pad.top - pad.bottom;
      const maxVal = Math.max(...rows.map((r) => r.avg || 0), 1);
      const maxY = maxVal * 1.2;
      const slot = plotW / rows.length;
      const barW = Math.min(56, slot * 0.55);
      cicloEtapasState.points = [];

      ctx.fillStyle = '#fbfcfd';
      ctx.fillRect(0, 0, width, height);
      ctx.font = '11px -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif';
      for (let i = 0; i <= 4; i++) {
        const y = pad.top + plotH * (i / 4);
        ctx.strokeStyle = '#e5edf2'; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(width - pad.right, y); ctx.stroke();
        ctx.textAlign = 'right'; ctx.textBaseline = 'middle'; ctx.fillStyle = '#65717e';
        ctx.fillText(`${Math.round(maxY * (1 - i / 4))}d`, pad.left - 5, y);
      }

      rows.forEach((row, index) => {
        const avg = row.avg || 0;
        const centerX = pad.left + slot * index + slot / 2;
        const h = (avg / maxY) * plotH;
        const x = centerX - barW / 2;
        const y = pad.top + plotH - h;
        const isActive = activeIndex === index;
        ctx.globalAlpha = activeIndex === null || isActive ? 1 : 0.35;
        drawRoundRect(ctx, x, y, barW, h, 5);
        ctx.fillStyle = CICLO_COLORS[index % CICLO_COLORS.length];
        ctx.fill();
        ctx.globalAlpha = 1;

        if (row.med !== null && row.med !== undefined) {
          const medY = pad.top + plotH - (row.med / maxY) * plotH;
          ctx.strokeStyle = '#fbfcfd'; ctx.lineWidth = 2.5;
          ctx.beginPath(); ctx.moveTo(x - 4, medY); ctx.lineTo(x + barW + 4, medY); ctx.stroke();
        }

        ctx.fillStyle = isActive ? '#225e73' : '#65717e';
        ctx.font = `${isActive ? 800 : 700} 11px -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif`;
        ctx.textAlign = 'center'; ctx.textBaseline = 'top';
        ctx.fillText(CICLO_LABELS[index] || row.etapa, centerX, pad.top + plotH + 10);
        cicloEtapasState.points.push({ x: centerX, y, row });
      });
    }

    function setActiveCicloEtapa(index, event) {
      cicloEtapasState.activeIndex = index >= 0 ? index : null;
      drawCicloEtapasChart(cicloEtapasState.activeIndex);
      cicloEtapasRows.querySelectorAll('tr').forEach((row, i) => row.classList.toggle('active', i === cicloEtapasState.activeIndex));
      if (cicloEtapasState.activeIndex === null) { cicloEtapasTooltip.hidden = true; return; }
      const row = cicloEtapasState.rows[cicloEtapasState.activeIndex];
      if (event) { placeTooltipNear(cicloEtapasTooltip, event.clientX, event.clientY); }
      cicloEtapasTooltip.innerHTML = `
        <b>${escapeHtml(row.etapa)}</b>
        <div><span>Promedio</span><strong>${row.avg !== null ? row.avg + ' días' : '—'}</strong></div>
        <div><span>Mediana</span><strong>${row.med !== null ? row.med + ' días' : '—'}</strong></div>
        <div><span>Máximo</span><strong>${row.max !== null ? row.max + ' días' : '—'}</strong></div>
        <div><span>N</span><strong>${row.n}</strong></div>
      `;
      cicloEtapasTooltip.hidden = false;
    }

    function drawCicloTemporalChart(activeIndex = null) {
      const ctx = cicloTemporalChart.getContext('2d');
      const rect = resizeCanvasToDisplay(cicloTemporalChart, ctx);
      const width = rect.width; const height = rect.height;
      ctx.clearRect(0, 0, width, height);
      const rows = cicloTemporalState.rows.filter((r) => r.avg_tot !== null);
      if (!rows.length) return;

      const pad = { left: 42, right: 16, top: 20, bottom: 40 };
      const plotW = width - pad.left - pad.right;
      const plotH = height - pad.top - pad.bottom;
      const maxVal = Math.max(...rows.map((r) => r.avg_tot), 1);
      const maxY = maxVal * 1.2;
      const allRows = cicloTemporalState.rows;
      const slot = plotW / allRows.length;
      cicloTemporalState.points = [];

      ctx.fillStyle = '#fbfcfd'; ctx.fillRect(0, 0, width, height);
      ctx.font = '11px -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif';
      for (let i = 0; i <= 4; i++) {
        const y = pad.top + plotH * (i / 4);
        ctx.strokeStyle = '#e5edf2'; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(width - pad.right, y); ctx.stroke();
        ctx.textAlign = 'right'; ctx.textBaseline = 'middle'; ctx.fillStyle = '#65717e';
        ctx.fillText(`${Math.round(maxY * (1 - i / 4))}d`, pad.left - 5, y);
      }

      allRows.forEach((row, index) => {
        const centerX = pad.left + slot * index + slot / 2;
        const val = row.avg_tot;
        const y = val !== null ? pad.top + plotH - (val / maxY) * plotH : null;
        const isActive = activeIndex === index;

        ctx.fillStyle = isActive ? '#225e73' : '#65717e';
        ctx.font = `${isActive ? 800 : 700} 11px -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif`;
        ctx.textAlign = 'center'; ctx.textBaseline = 'top';
        ctx.fillText(row.etiqueta, centerX, pad.top + plotH + 10);

        if (y !== null) {
          const barW = Math.min(40, slot * 0.5);
          const barH = (val / maxY) * plotH;
          ctx.globalAlpha = activeIndex === null || isActive ? 1 : 0.4;
          drawRoundRect(ctx, centerX - barW / 2, y, barW, barH, 4);
          ctx.fillStyle = '#d96058'; ctx.fill();
          ctx.globalAlpha = 1;
          cicloTemporalState.points.push({ x: centerX, y, row, index });
        }
      });

      const validPoints = cicloTemporalState.points;
      if (validPoints.length > 1) {
        ctx.beginPath();
        validPoints.forEach((p, i) => { if (i === 0) ctx.moveTo(p.x, p.y); else ctx.lineTo(p.x, p.y); });
        ctx.strokeStyle = '#d96058'; ctx.lineWidth = 2; ctx.setLineDash([5, 4]);
        ctx.lineJoin = 'round'; ctx.stroke(); ctx.setLineDash([]);
      }

      validPoints.forEach((p) => {
        const isActive = activeIndex === p.index;
        ctx.beginPath(); ctx.arc(p.x, p.y, isActive ? 5 : 3.5, 0, Math.PI * 2);
        ctx.fillStyle = '#fbfcfd'; ctx.fill();
        ctx.lineWidth = isActive ? 4 : 2.5; ctx.strokeStyle = '#d96058'; ctx.stroke();
      });
    }

    function setActiveCicloTemporal(index, event) {
      cicloTemporalState.activeIndex = index >= 0 ? index : null;
      drawCicloTemporalChart(cicloTemporalState.activeIndex);
      cicloTemporalRows.querySelectorAll('tr').forEach((row, i) => row.classList.toggle('active', i === cicloTemporalState.activeIndex));
      if (cicloTemporalState.activeIndex === null) { cicloTemporalTooltip.hidden = true; return; }
      const row = cicloTemporalState.rows[cicloTemporalState.activeIndex];
      if (event) { placeTooltipNear(cicloTemporalTooltip, event.clientX, event.clientY); }
      cicloTemporalTooltip.innerHTML = `
        <b>${escapeHtml(row.etiqueta)}</b>
        <div><span>Ciclo total prom.</span><strong>${row.avg_tot !== null ? row.avg_tot + ' días' : '—'}</strong></div>
      `;
      cicloTemporalTooltip.hidden = false;
    }

    function renderCicloFacturacion(ciclo) {
      if (!ciclo) return;
      const etapas = ciclo.etapas || [];
      cicloEtapasState.rows = etapas;
      cicloEtapasRows.innerHTML = etapas.map((e, index) => `
        <tr data-index="${index}">
          <td><span class="status-name" style="--status-color:${CICLO_COLORS[index % CICLO_COLORS.length]}"><span class="status-dot"></span>${escapeHtml(e.etapa)}</span></td>
          <td>${e.avg !== null ? e.avg + ' días' : '—'}</td>
          <td>${e.med !== null ? e.med + ' días' : '—'}</td>
          <td>${e.max !== null ? e.max + ' días' : '—'}</td>
          <td>${e.n}</td>
        </tr>
      `).join('');
      setActiveCicloEtapa(null);

      const temporal = ciclo.temporal || [];
      cicloTemporalState.rows = temporal;
      cicloTemporalRows.innerHTML = temporal.map((p, index) => `
        <tr data-index="${index}">
          <td><strong>${escapeHtml(p.etiqueta)}</strong></td>
          <td>${p.avg_tot !== null ? p.avg_tot + ' días' : '—'}</td>
        </tr>
      `).join('');
      setActiveCicloTemporal(null);
    }

    cicloEtapasChart.addEventListener('mousemove', (event) => {
      const rect = cicloEtapasChart.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const nearest = cicloEtapasState.points.reduce((best, point, index) => {
        const distance = Math.abs(point.x - x);
        return distance < best.distance ? { index, distance } : best;
      }, { index: -1, distance: Infinity });
      if (nearest.distance <= 60) setActiveCicloEtapa(nearest.index, event);
      else setActiveCicloEtapa(null);
    });
    cicloEtapasChart.addEventListener('mouseleave', () => setActiveCicloEtapa(null));
    cicloEtapasRows.addEventListener('mousemove', (event) => {
      const row = event.target.closest('tr');
      if (!row) return;
      setActiveCicloEtapa(Number(row.dataset.index), event);
    });
    cicloEtapasRows.addEventListener('mouseleave', () => setActiveCicloEtapa(null));

    cicloTemporalChart.addEventListener('mousemove', (event) => {
      const rect = cicloTemporalChart.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const nearest = cicloTemporalState.points.reduce((best, point) => {
        const distance = Math.abs(point.x - x);
        return distance < best.distance ? { index: point.index, distance } : best;
      }, { index: -1, distance: Infinity });
      if (nearest.distance <= Math.max(42, rect.width / Math.max(cicloTemporalState.rows.length * 2, 1))) setActiveCicloTemporal(nearest.index, event);
      else setActiveCicloTemporal(null);
    });
    cicloTemporalChart.addEventListener('mouseleave', () => setActiveCicloTemporal(null));
    cicloTemporalRows.addEventListener('mousemove', (event) => {
      const row = event.target.closest('tr');
      if (!row) return;
      setActiveCicloTemporal(Number(row.dataset.index), event);
    });
    cicloTemporalRows.addEventListener('mouseleave', () => setActiveCicloTemporal(null));

    window.addEventListener('resize', () => {
      renderEstadoChart(estadoChart.activeIndex);
      renderFacturacionEstadoChart(facturacionEstadoChart.activeIndex);
      drawFacturacionTemporalChart(facturacionTemporalState.activeIndex);
      drawCicloEtapasChart(cicloEtapasState.activeIndex);
      drawCicloTemporalChart(cicloTemporalState.activeIndex);
      drawSemanaChart(semanaChartState.activeIndex);
      if (!tiemposAprSection.hidden) renderTiemposApr(window._lastTiemposApr);
    });

    function resizeCanvasToDisplay(canvas, ctx) {
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const width = Math.max(1, Math.round(rect.width * dpr));
      const height = Math.max(1, Math.round(rect.height * dpr));
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      return rect;
    }

    function drawRoundRect(ctx, x, y, width, height, radius) {
      const r = Math.min(radius, Math.abs(width) / 2, Math.abs(height) / 2);
      ctx.beginPath();
      ctx.moveTo(x + r, y);
      ctx.arcTo(x + width, y, x + width, y + height, r);
      ctx.arcTo(x + width, y + height, x, y + height, r);
      ctx.arcTo(x, y + height, x, y, r);
      ctx.arcTo(x, y, x + width, y, r);
      ctx.closePath();
    }

    function drawSemanaChart(activeIndex = null) {
      const ctx = semanaChart.getContext('2d');
      const rect = resizeCanvasToDisplay(semanaChart, ctx);
      const width = rect.width;
      const height = rect.height;
      ctx.clearRect(0, 0, width, height);
      const rows = semanaChartState.rows;
      if (!rows.length) return;

      const esCantidad = semanaChartState.vista === 'cantidad';
      const valA = (row) => esCantidad ? row.cotizaciones : row.cotizado;
      const valB = (row) => esCantidad ? row.aprobadas : row.aprobado;
      const trendKeyA = esCantidad ? 'cotizaciones' : 'cotizado';
      const trendKeyB = esCantidad ? 'aprobadas' : 'aprobado';
      const fmtY = esCantidad ? (v) => formatNumber(Math.round(v)) : (v) => formatMoney(v).replace('MXN', '').trim();

      const pad = { left: 58, right: 46, top: 26, bottom: 46 };
      const plotW = width - pad.left - pad.right;
      const plotH = height - pad.top - pad.bottom;
      const maxVal = Math.max(...rows.map((row) => Math.max(valA(row), valB(row))), 1);
      const maxY = maxVal * 1.12;
      const slot = plotW / rows.length;
      const barW = Math.min(28, slot * .22);
      semanaChartState.points = [];

      ctx.fillStyle = '#fbfcfd';
      ctx.fillRect(0, 0, width, height);
      ctx.strokeStyle = '#e5edf2';
      ctx.lineWidth = 1;
      ctx.font = '11px -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif';
      ctx.textBaseline = 'middle';
      for (let i = 0; i <= 4; i += 1) {
        const y = pad.top + plotH * (i / 4);
        const value = maxY * (1 - i / 4);
        ctx.beginPath();
        ctx.moveTo(pad.left, y);
        ctx.lineTo(width - pad.right, y);
        ctx.stroke();
        ctx.textAlign = 'right';
        ctx.fillStyle = '#65717e';
        ctx.fillText(fmtY(value), pad.left - 8, y);
        ctx.textAlign = 'left';
        ctx.fillStyle = '#6b46c1';
        ctx.fillText(`${Math.round((1 - i / 4) * 100)}%`, width - pad.right + 6, y);
      }

      rows.forEach((row, index) => {
        const centerX = pad.left + slot * index + slot / 2;
        const aH = (valA(row) / maxY) * plotH;
        const bH = (valB(row) / maxY) * plotH;
        const aX = centerX - barW - 3;
        const bX = centerX + 3;
        const aY = pad.top + plotH - aH;
        const bY = pad.top + plotH - bH;
        const isActive = activeIndex === index;

        ctx.globalAlpha = activeIndex === null || isActive ? 1 : .35;
        drawRoundRect(ctx, aX, aY, barW, aH, 5);
        ctx.fillStyle = '#276f86';
        ctx.fill();
        drawRoundRect(ctx, bX, bY, barW, bH, 5);
        ctx.fillStyle = '#d0b56b';
        ctx.fill();
        ctx.globalAlpha = 1;

        ctx.fillStyle = isActive ? '#225e73' : '#65717e';
        ctx.font = `${isActive ? 800 : 700} 12px -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.fillText(row.semana, centerX, pad.top + plotH + 14);

        const convY = pad.top + plotH - (row.convMonto * plotH);
        semanaChartState.points.push({ x: centerX, y: convY, row });
      });

      const aPoints = rows.map((row, index) => ({
        x: pad.left + slot * index + slot / 2,
        y: pad.top + plotH - (valA(row) / maxY) * plotH,
      }));
      const bPoints = rows.map((row, index) => ({
        x: pad.left + slot * index + slot / 2,
        y: pad.top + plotH - (valB(row) / maxY) * plotH,
      }));
      const trends = semanaChartState.trends;
      const n = rows.length;
      const x0 = pad.left + slot / 2;
      const xN = pad.left + slot * (n - 1) + slot / 2;

      function drawTrendLine(y0, yN, color, dash) {
        ctx.setLineDash(dash || []);
        ctx.beginPath();
        ctx.moveTo(x0, y0);
        ctx.lineTo(xN, yN);
        ctx.strokeStyle = color;
        ctx.lineWidth = 2.5;
        ctx.lineJoin = 'round';
        ctx.lineCap = 'round';
        ctx.stroke();
        ctx.setLineDash([]);
      }

      if (trends) {
        const yFromVal = (v) => pad.top + plotH - (v / maxY) * plotH;
        const yFromConv = (c) => pad.top + plotH * (1 - c);
        drawTrendLine(yFromVal(trends[trendKeyA].start), yFromVal(trends[trendKeyA].end), '#276f86');
        drawTrendLine(yFromVal(trends[trendKeyB].start), yFromVal(trends[trendKeyB].end), '#d0b56b');
        drawTrendLine(yFromConv(trends.conv_qty.start), yFromConv(trends.conv_qty.end), '#6b46c1', [6, 4]);
      }

      [aPoints, bPoints].forEach((points, seriesIndex) => {
        points.forEach((point, index) => {
          const isActive = activeIndex === index;
          ctx.beginPath();
          ctx.arc(point.x, point.y, isActive ? 5 : 3.5, 0, Math.PI * 2);
          ctx.fillStyle = '#fbfcfd';
          ctx.fill();
          ctx.lineWidth = isActive ? 4 : 2.5;
          ctx.strokeStyle = seriesIndex === 0 ? '#276f86' : '#d0b56b';
          ctx.stroke();
        });
      });

      if (activeIndex !== null) {
        const point = semanaChartState.points[activeIndex];
        ctx.beginPath();
        ctx.arc(point.x, point.y, 13, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(21,152,149,.22)';
        ctx.lineWidth = 6;
        ctx.stroke();
      }

      ctx.fillStyle = '#65717e';
      ctx.font = '11px -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'top';
      const footerLabel = esCantidad
        ? 'Barras: cantidad de cot. y apr. · Lineas: tendencias de cotizaciones, aprobadas y conv. qty'
        : 'Barras: monto c/IVA · Lineas: tendencias de cotizado, aprobado y conv. qty';
      ctx.fillText(footerLabel, pad.left, 8);
    }

    function setActiveSemana(index, event) {
      semanaChartState.activeIndex = index >= 0 ? index : null;
      drawSemanaChart(semanaChartState.activeIndex);
      semanaRows.querySelectorAll('tr').forEach((row, rowIndex) => row.classList.toggle('active', rowIndex === semanaChartState.activeIndex));
      if (semanaChartState.activeIndex === null) {
        semanaTooltip.hidden = true;
        return;
      }
      const row = semanaChartState.rows[semanaChartState.activeIndex];
      if (event) { placeTooltipNear(semanaTooltip, event.clientX, event.clientY); }
      semanaTooltip.innerHTML = `
        <b>${escapeHtml(row.semana)}</b>
        <div><span>Cotizado</span><strong>${formatMoney(row.cotizado)}</strong></div>
        <div><span>Aprobado</span><strong>${formatMoney(row.aprobado)}</strong></div>
        <div><span>Cot.</span><strong>${formatNumber(row.cotizaciones)}</strong></div>
        <div><span>Apr.</span><strong>${formatNumber(row.aprobadas)}</strong></div>
        <div><span>Conv.qty</span><strong>${formatPercent(row.convQty)}</strong></div>
        <div><span>Conv.monto</span><strong>${formatPercent(row.convMonto)}</strong></div>
      `;
      semanaTooltip.hidden = false;
    }

    function renderTipoPagoChart(activeIndex = null) {
      const ctx = tipoPie.getContext('2d');
      const rect = tipoPie.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      tipoPie.width = Math.max(1, Math.round(rect.width * dpr));
      tipoPie.height = Math.max(1, Math.round(rect.height * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, rect.width, rect.height);
      const cx = rect.width / 2;
      const cy = rect.height / 2;
      const radius = Math.min(rect.width, rect.height) * 0.43;
      const innerRadius = radius * 0.58;
      tipoPagoChart.slices.forEach((slice, index) => {
        const isActive = index === activeIndex;
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.arc(cx, cy, radius + (isActive ? 8 : 0), slice.start, slice.end);
        ctx.closePath();
        ctx.fillStyle = slice.color;
        ctx.globalAlpha = activeIndex === null || isActive ? 1 : 0.42;
        ctx.fill();
        ctx.globalAlpha = 1;
        ctx.lineWidth = isActive ? 4 : 2;
        ctx.strokeStyle = '#fbfcfd';
        ctx.stroke();
      });
      ctx.globalCompositeOperation = 'destination-out';
      ctx.beginPath();
      ctx.arc(cx, cy, innerRadius, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalCompositeOperation = 'source-over';
      ctx.beginPath();
      ctx.arc(cx, cy, innerRadius, 0, Math.PI * 2);
      ctx.fillStyle = '#fbfcfd';
      ctx.fill();
      ctx.strokeStyle = '#e0e8ee';
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    function tipoPagoSliceAtEvent(event) {
      const rect = tipoPie.getBoundingClientRect();
      const x = event.clientX - rect.left - rect.width / 2;
      const y = event.clientY - rect.top - rect.height / 2;
      const distance = Math.hypot(x, y);
      const outer = Math.min(rect.width, rect.height) * 0.47;
      const inner = outer * 0.52;
      if (distance < inner || distance > outer) return null;
      let angle = Math.atan2(y, x);
      if (angle < -Math.PI / 2) angle += Math.PI * 2;
      return tipoPagoChart.slices.findIndex((slice) => angle >= slice.start && angle <= slice.end);
    }

    function setActiveTipoPago(index, event) {
      tipoPagoChart.activeIndex = index >= 0 ? index : null;
      renderTipoPagoChart(tipoPagoChart.activeIndex);
      tipoPagoLegend.querySelectorAll('.legend-item').forEach((item, i) => item.classList.toggle('active', i === tipoPagoChart.activeIndex));
      tipoPagoRows.querySelectorAll('tr').forEach((row, i) => row.classList.toggle('active', i === tipoPagoChart.activeIndex));
      if (tipoPagoChart.activeIndex === null) {
        tipoPagoTooltip.hidden = true;
        const total = tipoPagoChart.slices.reduce((s, sl) => s + sl.qty, 0);
        tipoPieCenter.textContent = formatNumber(total);
        return;
      }
      const slice = tipoPagoChart.slices[tipoPagoChart.activeIndex];
      tipoPieCenter.textContent = `${formatPercent(slice.qtyPct)}`;
      if (event) positionTooltip(tipoPagoTooltip, event);
      tipoPagoTooltip.innerHTML = `
        <b>${escapeHtml(slice.tipo)}</b>
        <div><span>Cotizaciones</span><strong>${formatNumber(slice.qty)}</strong></div>
        <div><span>% qty</span><strong>${formatPercent(slice.qtyPct)}</strong></div>
        <div><span>Monto</span><strong>${formatMoney(slice.monto)}</strong></div>
        <div><span>% monto</span><strong>${formatPercent(slice.montoPct)}</strong></div>
      `;
      tipoPagoTooltip.hidden = false;
    }

    function renderTipoPago(tipos) {
      if (!tipos?.length) { tipoPagoSection.hidden = true; return; }
      const rows = [...tipos].sort((a, b) => Number(b.n || 0) - Number(a.n || 0));
      const totalQty = rows.reduce((s, r) => s + Number(r.n || 0), 0);
      const totalMonto = rows.reduce((s, r) => s + Number(r.m || 0), 0);
      if (!totalQty) { tipoPagoSection.hidden = true; return; }
      const maxQty = Math.max(...rows.map((r) => Number(r.n || 0)));
      const minQty = Math.min(...rows.map((r) => Number(r.n || 0)));

      tipoPagoRows.innerHTML = rows.map((row, index) => {
        const color = statusColors[index % statusColors.length];
        const qty = Number(row.n || 0);
        const monto = Number(row.m || 0);
        const montoPct = totalMonto ? monto / totalMonto : 0;
        const isMax = qty === maxQty;
        const isMin = qty === minQty && qty !== maxQty;
        const badge = isMax
          ? `<span class="tipo-badge tipo-badge-max">Más usado</span>`
          : isMin
          ? `<span class="tipo-badge tipo-badge-min">Menos usado</span>`
          : '';
        return `<tr data-index="${index}">
          <td><span class="status-name" style="--status-color:${color}"><span class="status-dot"></span>${escapeHtml(row.tipo)}</span></td>
          <td>${formatNumber(qty)}</td>
          <td>${formatMoney(monto)}</td>
          <td>${formatPercent(montoPct)}</td>
          <td>${badge}</td>
        </tr>`;
      }).join('');

      let current = -Math.PI / 2;
      tipoPagoChart.slices = rows.map((row, index) => {
        const qty = Number(row.n || 0);
        const monto = Number(row.m || 0);
        const span = totalQty ? (qty / totalQty) * Math.PI * 2 : 0;
        const slice = {
          tipo: row.tipo,
          qty,
          monto,
          qtyPct: totalQty ? qty / totalQty : 0,
          montoPct: totalMonto ? monto / totalMonto : 0,
          color: statusColors[index % statusColors.length],
          start: current,
          end: current + span,
        };
        current += span;
        return slice;
      });

      tipoPagoLegend.innerHTML = tipoPagoChart.slices.map((slice, index) => `
        <button class="legend-item" type="button" style="--status-color:${slice.color}" data-index="${index}">
          <span class="legend-swatch"></span>
          <span>${escapeHtml(slice.tipo)}</span>
          <strong>${formatPercent(slice.qtyPct)}</strong>
        </button>
      `).join('');

      tipoPagoSection.hidden = false;
      tipoPieCenter.textContent = formatNumber(totalQty);
      setActiveTipoPago(null);
    }

    tipoPie.addEventListener('mousemove', (event) => {
      const index = tipoPagoSliceAtEvent(event);
      if (index >= 0) setActiveTipoPago(index, event);
      else setActiveTipoPago(null);
    });
    tipoPie.addEventListener('mouseleave', () => setActiveTipoPago(null));
    tipoPagoLegend.addEventListener('mousemove', (event) => {
      const item = event.target.closest('.legend-item');
      if (!item) return;
      setActiveTipoPago(Number(item.dataset.index), event);
    });
    tipoPagoLegend.addEventListener('mouseleave', () => setActiveTipoPago(null));
    tipoPagoRows.addEventListener('mousemove', (event) => {
      const row = event.target.closest('tr');
      if (!row) return;
      setActiveTipoPago(Number(row.dataset.index));
    });
    tipoPagoRows.addEventListener('mouseleave', () => setActiveTipoPago(null));

    function drawBarChart(canvas, tooltip, bars, opts) {
      const dpr = window.devicePixelRatio || 1;
      const rect = canvas.getBoundingClientRect();
      canvas.width = Math.max(1, Math.round(rect.width * dpr));
      canvas.height = Math.max(1, Math.round(rect.height * dpr));
      const ctx = canvas.getContext('2d');
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const w = rect.width, h = rect.height;
      ctx.clearRect(0, 0, w, h);
      if (!bars.length) return;

      const pad = { left: 46, right: 10, top: 20, bottom: 32 };
      const plotW = w - pad.left - pad.right;
      const plotH = h - pad.top - pad.bottom;
      const maxVal = Math.max(...bars.map((b) => b.value), 1);
      const maxY = maxVal * 1.15;
      const slot = plotW / bars.length;
      const barW = Math.min(32, slot * 0.55);

      ctx.fillStyle = '#fbfcfd';
      ctx.fillRect(0, 0, w, h);
      ctx.font = '10px -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif';
      ctx.strokeStyle = '#e5edf2';
      ctx.lineWidth = 1;
      for (let i = 0; i <= 4; i++) {
        const y = pad.top + plotH * (i / 4);
        const val = maxY * (1 - i / 4);
        ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(w - pad.right, y); ctx.stroke();
        ctx.textAlign = 'right'; ctx.fillStyle = '#65717e'; ctx.textBaseline = 'middle';
        ctx.fillText(opts.fmtY ? opts.fmtY(val) : Math.round(val), pad.left - 4, y);
      }

      if (opts.refLine != null) {
        const ry = pad.top + plotH - (opts.refLine / maxY) * plotH;
        ctx.setLineDash([5, 3]);
        ctx.strokeStyle = opts.refColor || '#276f86';
        ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.moveTo(pad.left, ry); ctx.lineTo(w - pad.right, ry); ctx.stroke();
        ctx.setLineDash([]);
      }

      const hitZones = [];
      bars.forEach((bar, i) => {
        const cx = pad.left + slot * i + slot / 2;
        const bh = (bar.value / maxY) * plotH;
        const bx = cx - barW / 2;
        const by = pad.top + plotH - bh;
        drawRoundRect(ctx, bx, by, barW, bh, 4);
        ctx.fillStyle = bar.color || opts.color || '#276f86';
        ctx.fill();
        ctx.textAlign = 'center'; ctx.textBaseline = 'top'; ctx.fillStyle = '#65717e';
        ctx.font = '10px -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif';
        ctx.fillText(bar.label, cx, pad.top + plotH + 5);
        hitZones.push({ cx, bar });
      });

      if (opts.trendLine && bars.length >= 2) {
        const tl = opts.trendLine;
        const y0 = pad.top + plotH - Math.max(0, Math.min(tl.start, maxY)) / maxY * plotH;
        const yN = pad.top + plotH - Math.max(0, Math.min(tl.end, maxY)) / maxY * plotH;
        const tx0 = pad.left + slot / 2;
        const txN = pad.left + slot * (bars.length - 1) + slot / 2;
        ctx.save();
        ctx.setLineDash([6, 4]);
        ctx.strokeStyle = opts.trendColor || '#d0b56b';
        ctx.lineWidth = 2;
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(tx0, y0);
        ctx.lineTo(txN, yN);
        ctx.stroke();
        ctx.restore();
      }

      canvas._hitZones = hitZones;
      canvas._slotW = slot;
    }

    function attachBarTooltip(canvas, tooltip, fmtTooltip) {
      canvas.addEventListener('mousemove', (e) => {
        if (!canvas._hitZones) return;
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const best = canvas._hitZones.reduce((b, z) => {
          const d = Math.abs(z.cx - mx);
          return d < b.d ? { d, z } : b;
        }, { d: Infinity, z: null });
        if (best.z && best.d <= (canvas._slotW || 40) / 2 + 8) {
          tooltip.innerHTML = fmtTooltip(best.z.bar);
          tooltip.hidden = false;
          placeTooltipNear(tooltip, e.clientX, e.clientY);
        } else { tooltip.hidden = true; }
      });
      canvas.addEventListener('mouseleave', () => { tooltip.hidden = true; });
    }

    function configureTemporalLabels(granularidad) {
      const mensual = granularidad === 'mes';
      temporalSectionTitle.textContent = mensual ? '1.2 Comportamiento mensual' : '1.2 Comportamiento semanal';
      temporalSectionSubtitle.textContent = mensual ? 'Agrupado por mes calendario del periodo seleccionado' : 'S1=1-7 · S2=8-14 · S3=15-21 · S4=22-28 · S5=29-fin de mes';
      temporalTableHeading.textContent = mensual ? 'Mes' : 'Sem';
      tiemposTemporalTitle.textContent = mensual ? 'Promedio de días por mes' : 'Promedio de días por semana';
      semanaChart.setAttribute('aria-label', mensual ? 'Grafica de barras y lineas de tendencia de cotizado contra aprobado por mes' : 'Grafica de barras y lineas de tendencia de cotizado contra aprobado por semana');
      tiemposSemanCanvas.setAttribute('aria-label', mensual ? 'Grafica de barras de dias promedio de aprobacion por mes' : 'Grafica de barras de dias promedio de aprobacion por semana');
    }

    function renderTiemposApr(ta) {
      window._lastTiemposApr = ta;
      if (!ta || !ta.stats) { tiemposAprSection.hidden = true; return; }
      const { stats, rangos, semanal, periodos, granularidad, histograma } = ta;
      configureTemporalLabels(granularidad || 'semana');
      if (!stats.n_con_datos && !stats.n_sin_fechas) { tiemposAprSection.hidden = true; return; }

      if (stats.n_sin_fechas > 0) {
        tiemposAprAlerta.textContent = `⚠️ ${stats.n_sin_fechas} cotización${stats.n_sin_fechas > 1 ? 'es aprobadas no tienen' : ' aprobada no tiene'} fecha de aprobación registrada — excluida${stats.n_sin_fechas > 1 ? 's' : ''} del análisis.`;
        tiemposAprAlerta.hidden = false;
      } else { tiemposAprAlerta.hidden = true; }

      tiemposAprKpis.innerHTML = [
        { label: 'Promedio',      value: `${stats.promedio} días`,            color: '#276f86' },
        { label: 'Mediana',       value: `${stats.mediana} días`,             color: '#159895' },
        { label: 'Máximo',        value: `${stats.maximo} días`,              color: '#d96058' },
        { label: 'Con datos',     value: formatNumber(stats.n_con_datos),     color: '#5b6673' },
      ].map((k) => `<div class="tiempos-kpi" style="border-left-color:${k.color}"><strong style="color:${k.color}">${escapeHtml(k.value)}</strong><span>${escapeHtml(k.label)}</span></div>`).join('');

      const rangoColors = { 'Mismo día': '#57c5b6', '1-3 días': '#159895', '4-7 días': '#d0b56b', '>7 días': '#d96058' };
      const totalRangos = rangos.reduce((s, r) => s + Number(r.n || 0), 0);
      tiemposAprRangos.innerHTML = rangos.map((r) => {
        const pct = totalRangos ? r.n / totalRangos : 0;
        const color = rangoColors[r.rango] || '#276f86';
        const barPct = Math.max(2, Math.round(pct * 100));
        return `<tr>
          <td><span class="status-dot" style="background:${color};display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;vertical-align:middle;"></span>${escapeHtml(r.rango)}</td>
          <td style="text-align:right;font-variant-numeric:tabular-nums">${formatNumber(r.n)}</td>
          <td style="text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap">
            <span class="tiempos-pct-bar"><span class="tiempos-pct-bar-fill" style="width:${barPct}%;background:${color}"></span></span>${formatPercent(pct)}
          </td>
        </tr>`;
      }).join('');

      tiemposAprSection.hidden = false;

      const semBars = (periodos || semanal).map((s) => ({
        label: s.etiqueta || s.semana, value: s.avg, n: s.n, med: s.med,
        color: s.n > 0 ? '#159895' : '#dde5ea',
      }));
      const histColors = (d) => {
        if (d === '0') return '#57c5b6';
        if (d === '1' || d === '2' || d === '3') return '#159895';
        if (d === '4' || d === '5' || d === '6' || d === '7') return '#d0b56b';
        return '#d96058';
      };
      const histBars = histograma.map((h) => ({
        label: h.dias === '8+' ? '8+d' : `${h.dias}d`,
        value: h.n, dias: h.dias, color: histColors(h.dias),
      }));
      const totalHist = histBars.reduce((s, b) => s + b.value, 0);

      requestAnimationFrame(() => {
        drawBarChart(tiemposSemanCanvas, tiemposSemanTooltip, semBars, {
          fmtY: (v) => `${v.toFixed(1)}d`,
          refLine: stats.promedio,
          refColor: '#276f86',
          color: '#159895',
          trendLine: ta.semanal_tendencia || null,
          trendColor: '#d0b56b',
        });
        attachBarTooltip(tiemposSemanCanvas, tiemposSemanTooltip, (bar) =>
          bar.n === 0
            ? `<b>${bar.label}</b><div><span>Sin datos</span></div>`
            : `<b>${bar.label}</b><div><span>Promedio</span><strong>${bar.value.toFixed(1)} días</strong></div><div><span>Mediana</span><strong>${bar.med.toFixed(1)} días</strong></div><div><span>Cotizaciones</span><strong>${formatNumber(bar.n)}</strong></div>`
        );
        drawBarChart(tiemposHistCanvas, tiemposHistTooltip, histBars, { color: '#159895' });
        attachBarTooltip(tiemposHistCanvas, tiemposHistTooltip, (bar) =>
          `<b>${bar.label === '8+d' ? 'Más de 7 días' : `${bar.dias} día${bar.dias === '1' ? '' : 's'}`}</b><div><span>Cotizaciones</span><strong>${formatNumber(bar.value)}</strong></div><div><span>%</span><strong>${formatPercent(totalHist ? bar.value / totalHist : 0)}</strong></div>`
        );
      });
    }

    function renderTopChart(container, tooltip, data, opts) {
      if (!data || !data.length) { container.closest('section')?.hidden === false && (container.innerHTML = ''); return; }
      const maxM = Math.max(...data.map((d) => d[opts.barField]), 1);
      container.innerHTML = data.map((d, i) => {
        const pct = Math.max(2, Math.round((d[opts.barField] / maxM) * 100));
        return `<div class="hbar-row" data-index="${i}" title="${escapeHtml(d.cliente)}">
          <span class="hbar-label">${escapeHtml(d.cliente)}</span>
          <div class="hbar-track">
            <div class="hbar-fill" style="width:${pct}%;background:${opts.color}">
              <span class="hbar-fill-value">${formatMoney(d[opts.barField])}</span>
            </div>
          </div>
        </div>`;
      }).join('');
      container.querySelectorAll('.hbar-row').forEach((row) => {
        row.addEventListener('mouseenter', (e) => {
          const d = data[Number(row.dataset.index)];
          tooltip.innerHTML = opts.tooltipFn(d);
          positionTooltip(tooltip, e);
          tooltip.hidden = false;
        });
        row.addEventListener('mousemove', (e) => positionTooltip(tooltip, e));
        row.addEventListener('mouseleave', () => { tooltip.hidden = true; });
      });
    }

    function positionTooltip(tooltip, e) {
      placeTooltipNear(tooltip, e.clientX, e.clientY);
    }

    function placeTooltipNear(tooltip, x, y) {
      const GAP = 12;
      tooltip.style.left = '0px';
      tooltip.style.top = '0px';
      const rect = tooltip.getBoundingClientRect();
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      let left = x + GAP;
      if (left + rect.width > vw - 4) left = Math.max(4, x - GAP - rect.width);
      let top = y + GAP;
      if (top + rect.height > vh - 4) top = Math.max(4, y - GAP - rect.height);
      tooltip.style.left = `${left}px`;
      tooltip.style.top = `${top}px`;
    }

    function renderTopClientes(cotizan, aprueban) {
      if (!cotizan?.length && !aprueban?.length) { topClientesSection.hidden = true; return; }
      renderTopChart(topCotizanChart, topCotizanTooltip, cotizan, {
        barField: 'm',
        color: '#276f86',
        tooltipFn: (d) => {
          const convQ = d.n ? d.na / d.n : 0;
          const convM = d.m ? d.ma / d.m : 0;
          return `<b>${escapeHtml(d.cliente)}</b>
            <div><span>Cotizaciones</span><strong>${formatNumber(d.n)}</strong></div>
            <div><span>Monto cotizado</span><strong>${formatMoney(d.m)}</strong></div>
            <div><span>Aprobadas</span><strong>${formatNumber(d.na)}</strong></div>
            <div><span>Monto aprobado</span><strong>${formatMoney(d.ma)}</strong></div>
            <div><span>Conv. qty</span><strong>${formatPercent(convQ)}</strong></div>
            <div><span>Conv. monto</span><strong>${formatPercent(convM)}</strong></div>`;
        },
      });
      renderTopChart(topApruebanyChart, topApruebanyTooltip, aprueban, {
        barField: 'm',
        color: '#d0b56b',
        tooltipFn: (d) => {
          const convQ = d.n_cot ? d.n / d.n_cot : 0;
          const convM = d.m_cot ? d.m / d.m_cot : 0;
          return `<b>${escapeHtml(d.cliente)}</b>
            <div><span>Aprobadas</span><strong>${formatNumber(d.n)}</strong></div>
            <div><span>Monto aprobado</span><strong>${formatMoney(d.m)}</strong></div>
            <div><span>Cotizaciones</span><strong>${formatNumber(d.n_cot)}</strong></div>
            <div><span>Monto cotizado</span><strong>${formatMoney(d.m_cot)}</strong></div>
            <div><span>Conv. qty</span><strong>${formatPercent(convQ)}</strong></div>
            <div><span>Conv. monto</span><strong>${formatPercent(convM)}</strong></div>`;
        },
      });
      topClientesSection.hidden = false;
    }

    function renderSemanas(semanas, tendencias, granularidad = 'semana') {
      configureTemporalLabels(granularidad);
      const rows = [...(semanas || [])]
        .map((row) => ({
          semana: row.etiqueta || row.semana,
          cotizaciones: Number(row.cotizaciones || 0),
          cotizado: Number(row.cotizado || 0),
          aprobadas: Number(row.aprobadas || 0),
          aprobado: Number(row.aprobado || 0),
          convQty: Number(row.cotizaciones || 0) ? Number(row.aprobadas || 0) / Number(row.cotizaciones || 0) : 0,
          convMonto: Number(row.cotizado || 0) ? Number(row.aprobado || 0) / Number(row.cotizado || 0) : 0,
        }));
      if (!rows.length) {
        semanaSection.hidden = true;
        return;
      }
      semanaChartState.rows = rows;
      semanaChartState.trends = tendencias || null;
      semanaRows.innerHTML = rows.map((row, index) => `
        <tr data-index="${index}">
          <td><strong>${escapeHtml(row.semana)}</strong></td>
          <td>${formatNumber(row.cotizaciones)}</td>
          <td>${formatMoney(row.cotizado)}</td>
          <td>${formatNumber(row.aprobadas)}</td>
          <td>${formatMoney(row.aprobado)}</td>
          <td>${formatPercent(row.convQty)}</td>
          <td>${formatPercent(row.convMonto)}</td>
        </tr>
      `).join('');
      semanaSection.hidden = false;
      setActiveSemana(null);
    }

    function setSemanaVista(vista) {
      semanaChartState.vista = vista;
      semanaVistaMonto.classList.toggle('active', vista === 'monto');
      semanaVistaCantidad.classList.toggle('active', vista === 'cantidad');
      const esCantidad = vista === 'cantidad';
      semanaLegendBar1.textContent = esCantidad ? 'Cotizaciones' : 'Monto cotizado';
      semanaLegendBar2.textContent = esCantidad ? 'Aprobadas' : 'Monto aprobado';
      semanaLegendTend1.textContent = esCantidad ? 'Tend. cotizaciones' : 'Tend. cotizado';
      semanaLegendTend2.textContent = esCantidad ? 'Tend. aprobadas' : 'Tend. aprobado';
      drawSemanaChart(semanaChartState.activeIndex);
    }
    semanaVistaMonto.addEventListener('click', () => setSemanaVista('monto'));
    semanaVistaCantidad.addEventListener('click', () => setSemanaVista('cantidad'));

    semanaChart.addEventListener('mousemove', (event) => {
      const rect = semanaChart.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const nearest = semanaChartState.points.reduce((best, point, index) => {
        const distance = Math.abs(point.x - x);
        return distance < best.distance ? { index, distance } : best;
      }, { index: -1, distance: Infinity });
      if (nearest.distance <= Math.max(42, rect.width / Math.max(semanaChartState.rows.length * 2, 1))) setActiveSemana(nearest.index, event);
      else setActiveSemana(null);
    });
    semanaChart.addEventListener('mouseleave', () => setActiveSemana(null));
    semanaRows.addEventListener('mousemove', (event) => {
      const row = event.target.closest('tr');
      if (!row) return;
      setActiveSemana(Number(row.dataset.index), event);
    });
    semanaRows.addEventListener('mouseleave', () => setActiveSemana(null));

    function resizeCanvasToCard(canvas, ctx) {
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const width = Math.max(1, Math.round(rect.width * dpr));
      const height = Math.max(1, Math.round(rect.height * dpr));
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      return rect;
    }

    function drawKpiCanvas(state, time) {
      const { canvas, ctx, card, index } = state;
      const rect = resizeCanvasToCard(canvas, ctx);
      const width = rect.width;
      const height = rect.height;
      ctx.clearRect(0, 0, width, height);
      const tone = card.classList.contains('accent') ? '#d0b56b' : card.classList.contains('warning') ? '#d96058' : '#159895';
      const secondary = card.classList.contains('primary') ? '#57c5b6' : '#276f86';
      const speed = reduceMotion ? 0 : time * 0.001;
      const hoverPower = state.hover ? 1 : 0;

      const gradient = ctx.createLinearGradient(0, 0, width, height);
      gradient.addColorStop(0, `${tone}18`);
      gradient.addColorStop(1, `${secondary}08`);
      ctx.fillStyle = gradient;
      ctx.fillRect(0, 0, width, height);

      ctx.lineWidth = 1;
      for (let i = 0; i < 4; i += 1) {
        const yBase = height * (0.34 + i * 0.14);
        ctx.beginPath();
        for (let x = -12; x <= width + 12; x += 10) {
          const y = yBase + Math.sin((x * 0.024) + speed * (1.2 + i * .22) + index) * (5 + i * 1.6);
          if (x === -12) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.strokeStyle = i % 2 ? `${secondary}24` : `${tone}2c`;
        ctx.stroke();
      }

      const pulse = (Math.sin(speed * 1.8 + index) + 1) / 2;
      ctx.beginPath();
      ctx.arc(width * .86, height * .18, 18 + pulse * 12 + hoverPower * 8, 0, Math.PI * 2);
      ctx.strokeStyle = `${tone}${state.hover ? '55' : '30'}`;
      ctx.lineWidth = 2;
      ctx.stroke();

      ctx.beginPath();
      ctx.arc(width * .08, height * .82, 28 + pulse * 7, 0, Math.PI * 2);
      ctx.fillStyle = `${secondary}12`;
      ctx.fill();

      if (state.hover) {
        const halo = ctx.createRadialGradient(state.x, state.y, 0, state.x, state.y, Math.max(width, height) * .55);
        halo.addColorStop(0, `${tone}34`);
        halo.addColorStop(.35, `${secondary}16`);
        halo.addColorStop(1, 'rgba(255,255,255,0)');
        ctx.fillStyle = halo;
        ctx.fillRect(0, 0, width, height);

        ctx.beginPath();
        ctx.arc(state.x, state.y, 4, 0, Math.PI * 2);
        ctx.fillStyle = tone;
        ctx.fill();
      }
    }

    function animateKpiCanvases(time) {
      kpiCanvasStates.forEach((state) => drawKpiCanvas(state, time));
      if (!reduceMotion) kpiAnimationFrame = requestAnimationFrame(animateKpiCanvases);
    }

    function attachKpiCanvases() {
      if (kpiAnimationFrame) {
        cancelAnimationFrame(kpiAnimationFrame);
        kpiAnimationFrame = null;
      }
      const grids = [kpiGrid, facturacionKpiGrid].filter(Boolean);
      const cards = grids.flatMap(g => [...g.querySelectorAll('.kpi-card')]);
      kpiCanvasStates = cards.map((card, index) => {
        let canvas = card.querySelector(':scope > canvas.kpi-bg');
        if (!canvas) {
          canvas = document.createElement('canvas');
          canvas.className = 'kpi-bg';
          card.prepend(canvas);
        }
        const state = { card, canvas, ctx: canvas.getContext('2d'), index, hover: false, x: 0, y: 0 };
        card.addEventListener('mousemove', (event) => {
          const rect = card.getBoundingClientRect();
          state.hover = true;
          state.x = event.clientX - rect.left;
          state.y = event.clientY - rect.top;
        });
        card.addEventListener('mouseenter', () => { state.hover = true; });
        card.addEventListener('mouseleave', () => { state.hover = false; });
        return state;
      });
      animateKpiCanvases(performance.now());
    }

    function renderKpis(kpis) {
      const aprobacionWarning = Number(kpis.diferencia_aprobacion_pct || 0) < 0 ? 'warning' : '';
      const aribaConvWarning = Number(kpis.diferencia_ariba_conv || 0) < 0 ? 'warning' : '';
      const cards = [
        `
        <article class="kpi-card primary">
          <h2>Cotizaciones</h2>
          <div class="kpi-pair">
            ${metric('Total cotizaciones', kpiValue(kpis, 'total_cotizaciones', 'number'), 'Registros del periodo')}
            ${metric('Total cotizado c/IVA', kpiValue(kpis, 'total_cotizado_iva', 'money'), 'Base comercial total')}
          </div>
          ${metric('Ticket prom. cotizado', kpiValue(kpis, 'ticket_promedio_cotizado', 'money'), 'Total / cotizaciones')}
        </article>`,
        `
        <article class="kpi-card accent">
          <h2>Aprobadas</h2>
          <div class="kpi-pair">
            ${metric('Cotizaciones aprobadas', kpiValue(kpis, 'cotizaciones_aprobadas', 'number'), 'Cantidad convertida')}
            ${metric('Monto aprobado c/IVA', kpiValue(kpis, 'monto_aprobado_iva', 'money'), 'Valor convertido')}
          </div>
          ${metric('Ticket prom. aprobado', kpiValue(kpis, 'ticket_promedio_aprobado', 'money'), 'Aprobado / aprobadas')}
        </article>`,
        `
        <article class="kpi-card ${aprobacionWarning}">
          <h2>Conversion</h2>
          <div class="kpi-pair">
            ${metric('Aprobacion por monto', kpiValue(kpis, 'aprobacion_monto_pct', 'percent'), 'Aprobado / cotizado')}
            ${metric('Aprobacion por cantidad', kpiValue(kpis, 'aprobacion_cantidad_pct', 'percent'), 'Aprobadas / cotizaciones')}
          </div>
          ${delta('Diferencia aprobacion', kpiValue(kpis, 'diferencia_aprobacion_pct', 'pp'), 'Monto menos cantidad')}
        </article>`,
        `
        <article class="kpi-card primary">
          <h2>Ariba cotizado</h2>
          <div class="kpi-pair">
            ${metric('Cot. Ariba totales', kpiValue(kpis, 'ariba_cotizadas', 'number'), 'Cotizaciones con Ariba')}
            ${metric('Monto Ariba cotizado', kpiValue(kpis, 'monto_ariba_cotizado', 'money'), 'Total Ariba cotizado')}
          </div>
          ${metric('Ticket prom. Ariba', kpiValue(kpis, 'ticket_ariba_cotizado', 'money'), 'Monto / cotizaciones Ariba')}
        </article>`,
        `
        <article class="kpi-card accent">
          <h2>Ariba aprobado</h2>
          <div class="kpi-pair">
            ${metric('Cot. Ariba aprobadas', kpiValue(kpis, 'ariba_aprobadas', 'number'), 'Ariba con estado aprobado')}
            ${metric('Monto Ariba aprobado', kpiValue(kpis, 'monto_ariba_aprobado', 'money'), 'Total Ariba aprobado')}
          </div>
          ${metric('Ariba % cantidad', kpiValue(kpis, 'ariba_aprobadas_pct_cantidad', 'percent'), 'Ariba aprobadas / total cotizaciones')}
        </article>`,
        `
        <article class="kpi-card ${aribaConvWarning}">
          <h2>Ariba conversion</h2>
          <div class="kpi-pair">
            ${metric('Aprobacion por monto', kpiValue(kpis, 'ariba_conv_m', 'percent'), 'Ariba aprobado / Ariba cotizado')}
            ${metric('Aprobacion por cantidad', kpiValue(kpis, 'ariba_conv_q', 'percent'), 'Ariba aprobadas / Ariba cotizadas')}
          </div>
          ${delta('Diferencia Ariba', kpiValue(kpis, 'diferencia_ariba_conv', 'pp'), 'Monto menos cantidad')}
        </article>`,
      ];
      kpiGrid.innerHTML = cards.join('');
      attachKpiCanvases();
    }

    function renderFacturacion(body) {
      const kpis = body.kpis || {};
      const vigentes = Number(kpis.facturas_vigentes || 0);
      const canceladas = Number(kpis.facturas_canceladas || 0);
      const principales = Number(kpis.facturas_principales || 0);
      const secundarias = Number(kpis.facturas_secundarias || 0);
      const rezagoMonto = Number(kpis.rezago_estimado_monto || 0);
      const montoFacturado = Number(kpis.monto_facturado_vigente || 0);
      const valPct = Number(kpis.cobertura_validacion_pct || 0);
      const asPct = Number(kpis.cobertura_asociacion_pct || 0);

      const pctSecundarias = (principales + secundarias) > 0 ? secundarias / (principales + secundarias) : 0;
      const pctCanceladas = (vigentes + canceladas) > 0 ? canceladas / (vigentes + canceladas) : 0;
      const pctRezago = montoFacturado > 0 ? rezagoMonto / montoFacturado : 0;
      const difCobertura = ((valPct - asPct) * 100).toFixed(1) + ' pp';

      const coberturaWarning = (valPct < 0.8 || asPct < 0.8) ? 'warning' : '';
      const cancelacionesWarning = Number(kpis.monto_cancelado || 0) > 0 ? 'warning' : '';
      const rezagoWarning = rezagoMonto > 0 ? 'warning' : '';

      const cards = [
        `<article class="kpi-card primary">
          <h2>Facturas vigentes</h2>
          <div class="kpi-pair">
            ${metric('Facturas', kpiValue(kpis, 'facturas_vigentes', 'number'), 'Principales y secundarias sin duplicar')}
            ${metric('Monto facturado', kpiValue(kpis, 'monto_facturado_vigente', 'money'), 'Monto vigente del periodo')}
          </div>
          ${metric('Ticket promedio', kpiValue(kpis, 'ticket_promedio_facturado', 'money'), 'Monto / facturas vigentes')}
        </article>`,
        `<article class="kpi-card accent">
          <h2>Origen de factura</h2>
          <div class="kpi-pair">
            ${metric('Principales', kpiValue(kpis, 'facturas_principales', 'number'), 'Primer registro de factura')}
            ${metric('Secundarias', kpiValue(kpis, 'facturas_secundarias', 'number'), 'Facturas adicionales')}
          </div>
          ${metric('% secundarias', formatPercent(pctSecundarias), 'Participación de facturas adicionales')}
        </article>`,
        `<article class="kpi-card ${coberturaWarning}">
          <h2>Cobertura documental</h2>
          <div class="kpi-pair">
            ${metric('Validación', kpiValue(kpis, 'cobertura_validacion_pct', 'percent'), 'Facturas con fecha de validación')}
            ${metric('Asociación', kpiValue(kpis, 'cobertura_asociacion_pct', 'percent'), 'Facturas asociadas a OC')}
          </div>
          ${delta('Diferencia', difCobertura, 'Validación menos asociación')}
        </article>`,
        `<article class="kpi-card ${cancelacionesWarning}">
          <h2>Cancelaciones</h2>
          <div class="kpi-pair">
            ${metric('Canceladas', kpiValue(kpis, 'facturas_canceladas', 'number'), 'Excluidas del monto vigente')}
            ${metric('Monto cancelado', kpiValue(kpis, 'monto_cancelado', 'money'), 'Monto fuera de vigencia')}
          </div>
          ${metric('% sobre emitidas', formatPercent(pctCanceladas), 'Canceladas / (vigentes + canceladas)')}
        </article>`,
        `<article class="kpi-card ${rezagoWarning}">
          <h2>Rezago estimado</h2>
          <div class="kpi-pair">
            ${metric('Cotizaciones', kpiValue(kpis, 'rezago_estimado_cantidad', 'number'), 'Aprobadas sin factura vigente')}
            ${metric('Monto', kpiValue(kpis, 'rezago_estimado_monto', 'money'), 'Pendiente estimado')}
          </div>
          ${metric('% del facturado', formatPercent(pctRezago), 'Rezago / monto facturado')}
        </article>`,
      ];
      facturacionKpiGrid.innerHTML = cards.join('');
      attachKpiCanvases();

      renderFacturacionEstados(body.series?.estados || []);

      renderFacturacionTemporal(body.series?.temporal);
      renderCicloFacturacion(body.ciclo);
      const signals = body.signals || [];
      facturacionAlerts.innerHTML = signals.map((signal) => `<span class="facturacion-alert">${escapeHtml(signal.titulo)}: ${formatNumber(signal.metricas?.cantidad || 0)}</span>`).join('') || '<span class="panel-state">Sin alertas operativas.</span>';
    }

    async function loadFacturacion() {
      if (facturacionLoaded) return;
      try {
        const response = await fetch('/api/dashboard/facturacion');
        const body = await response.json();
        if (!response.ok) throw new Error(body.detail || 'No se pudieron cargar los KPIs de facturación.');
        renderFacturacion(body);
        facturacionLoaded = true;
      } catch (error) {
        facturacionKpiGrid.innerHTML = `<p class="panel-state">${escapeHtml(error.message)}</p>`;
      }
    }

    async function loadVentasKpis() {
      if (ventasLoaded) return;
      try {
        const response = await fetch('/api/dashboard/ventas');
        const body = await response.json();
        if (!response.ok) throw new Error(body.detail || 'No se pudieron cargar los KPIs de ventas.');
        renderKpis(body.kpis || {});
        renderEstados(body.series?.estados || []);
        const temporal = body.series?.temporal;
        renderSemanas(temporal?.periodos || body.series?.semanas || [], temporal?.tendencias || body.series?.tendencias || null, temporal?.granularidad || 'semana');
        renderTopClientes(body.tables?.top_clientes_cotizan || [], body.tables?.top_clientes_aprueban || []);
        renderTipoPago(body.tables?.tipos_pago || []);
        renderTiemposApr(body.series?.tiempos_aprobacion || null);
        ventasLoaded = true;
      } catch (error) {
        kpiGrid.innerHTML = `<p class="panel-state">${error.message}</p>`;
        estadoSection.hidden = true;
        semanaSection.hidden = true;
        tiemposAprSection.hidden = true;
      }
    }

    function setActiveModule(moduleName) {
      canvas.dataset.module = moduleName;
      ventasPanel.hidden = moduleName !== 'ventas';
      facturacionPanel.hidden = moduleName !== 'facturacion';
      if (moduleName === 'ventas') loadVentasKpis();
      if (moduleName === 'facturacion') loadFacturacion();
    }

    form.addEventListener('input', refreshPayload);
    form.addEventListener('change', refreshPayload);

    moduleTabs.forEach((tab) => {
      tab.addEventListener('click', () => {
        moduleTabs.forEach((item) => {
          item.classList.remove('active');
          item.removeAttribute('aria-current');
        });
        tab.classList.add('active');
        tab.setAttribute('aria-current', 'page');
        setActiveModule(tab.dataset.module);
      });
    });

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      refreshPayload();
      if (!form.fecha_desde.value || !form.fecha_hasta.value) {
        setStatus('Error', 'error', 'Falta fecha inicio o fecha fin.');
        return;
      }
      if (form.fecha_hasta.value < form.fecha_desde.value) {
        setStatus('Error', 'error', 'Fecha fin no puede ser menor que fecha inicio.');
        return;
      }

      submitButton.disabled = true;
      showDownloadOverlay();
      setStatus('Enviando', '', 'Llamando webhook n8n...');
      try {
        const response = await fetch('/api/actualizar-datos', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            ambiente: form.ambiente.value,
            fecha_desde: form.fecha_desde.value,
            fecha_hasta: form.fecha_hasta.value
          })
        });
        const body = await response.json();
        if (!response.ok) throw new Error(body.detail || 'La llamada no pudo completarse.');
        setStatus('Completado', 'success', `Archivos procesados: ${body.files?.length || 0}`);
        window.location.reload();
      } catch (error) {
        hideDownloadOverlay();
        setStatus('Error', 'error', error.message);
      } finally {
        submitButton.disabled = false;
      }
    });

    regenerarButton.addEventListener('click', async () => {
      if (!form.fecha_desde.value || !form.fecha_hasta.value) {
        setStatus('Error', 'error', 'Falta fecha inicio o fecha fin.');
        return;
      }
      regenerarButton.disabled = true;
      submitButton.disabled = true;
      setStatus('Regenerando', '', 'Regenerando snapshots con archivos actuales...');
      try {
        const response = await fetch('/api/regenerar-snapshot', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ fecha_desde: form.fecha_desde.value, fecha_hasta: form.fecha_hasta.value })
        });
        const body = await response.json();
        if (!response.ok) throw new Error(body.detail || 'No se pudo regenerar.');
        const archivados = body.archived?.length || 0;
        setStatus('Regenerado', 'success', `Snapshots actualizados. ${archivados} archivo${archivados !== 1 ? 's' : ''} archivado${archivados !== 1 ? 's' : ''}.`);
        window.location.reload();
      } catch (error) {
        setStatus('Error', 'error', error.message);
      } finally {
        regenerarButton.disabled = false;
        submitButton.disabled = false;
      }
    });

    refreshPayload();
    loadVentasKpis();
  </script>
</body>
</html>""".replace("PAYLOAD_TEXT", payload_text)

def _json_preview(payload: list[dict[str, str]]) -> str:
    import json

    return json.dumps(payload, indent=2, ensure_ascii=False)


def create_app(
    http_post: Callable[..., requests.Response] | None = None,
    data_dir: str = "data",
    processed_dir: str = "data_procesada",
    dashboard_dir: str = "dashboard_data",
) -> FastAPI:
    app = FastAPI(title="Dashboard RTB", version="0.3.0")
    app.state.http_post = http_post
    app.state.data_dir = data_dir
    app.state.dashboard_dir = dashboard_dir
    app.state.processed_dir = processed_dir

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse(render_index())

    @app.get("/api/dashboard/ventas")
    def dashboard_ventas(request: Request) -> dict:
        try:
            return load_dashboard_payload(
                request.app.state.data_dir, request.app.state.dashboard_dir
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=422, detail=f"Falta columna requerida en Cotizaciones: {exc}") from exc

    @app.get("/api/dashboard/facturacion")
    def dashboard_facturacion(request: Request) -> dict:
        try:
            return load_facturacion_payload(
                request.app.state.data_dir, request.app.state.dashboard_dir
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/actualizar-datos", status_code=status.HTTP_202_ACCEPTED)
    def actualizar_datos(payload: UpdateRequest, request: Request) -> dict:
        try:
            validate_request(payload.ambiente, payload.fecha_desde, payload.fecha_hasta)
            before = snapshot_cotizaciones(request.app.state.data_dir)
            before_facturas = snapshot_facturas(request.app.state.data_dir)
            webhook = call_webhook(
                payload.ambiente,
                payload.fecha_desde,
                payload.fecha_hasta,
                http_post=request.app.state.http_post,
            )
            try:
                validate_webhook_success(webhook)
            except WebhookResponseError:
                # 502/524: proxy o Cloudflare cortó la conexión antes de que n8n respondiera,
                # pero n8n sigue corriendo y depositará los archivos. Continuamos esperándolos.
                if webhook["status_code"] not in (502, 524):
                    raise
            csv_path = wait_for_changed_cotizaciones(request.app.state.data_dir, before)
            wait_for_changed_facturas(request.app.state.data_dir, before_facturas)
            try:
                publish_facturacion_snapshot(
                    request.app.state.data_dir,
                    request.app.state.dashboard_dir,
                    payload.fecha_desde,
                    payload.fecha_hasta,
                    cot_path=csv_path,
                )
            except FileNotFoundError:
                pass
            snapshot = publish_ventas_snapshot(
                request.app.state.data_dir,
                request.app.state.dashboard_dir,
                before,
                payload.fecha_desde,
                payload.fecha_hasta,
                csv_path=csv_path,
            )
            archived = archive_data_dir(
                request.app.state.data_dir,
                request.app.state.processed_dir,
            )
            return {**webhook, "status": "completada", "files": [snapshot["file"]], "archived": archived}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except WebhookResponseError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except requests.RequestException as exc:
            raise HTTPException(status_code=502, detail=f"Error llamando webhook n8n: {exc}") from exc

    class RegenerarRequest(BaseModel):
        fecha_desde: str
        fecha_hasta: str

    @app.post("/api/regenerar-snapshot", status_code=status.HTTP_200_OK)
    def regenerar_snapshot(payload: RegenerarRequest, request: Request) -> dict:
        """Regenera los snapshots de ventas y facturación con los archivos actuales en data/.
        Útil cuando el webhook falla (502) pero los CSV ya se descargaron.
        No mueve archivos ni llama a n8n."""
        try:
            fecha_desde = parse_iso_date(payload.fecha_desde, "fecha_desde").strftime("%Y-%m-%d")
            fecha_hasta = parse_iso_date(payload.fecha_hasta, "fecha_hasta").strftime("%Y-%m-%d")
            if fecha_hasta < fecha_desde:
                raise ValueError("fecha_hasta no puede ser menor que fecha_desde")
            try:
                publish_facturacion_snapshot(
                    request.app.state.data_dir,
                    request.app.state.dashboard_dir,
                    fecha_desde,
                    fecha_hasta,
                )
            except FileNotFoundError:
                pass
            files_regenerated = []
            cot_candidates = sorted(
                Path(request.app.state.data_dir).glob("Cotizaciones*.csv"),
                key=lambda p: (p.stat().st_mtime_ns, p.name),
            )
            if cot_candidates:
                cot_path = cot_candidates[-1]
                snapshot = publish_ventas_snapshot(
                    request.app.state.data_dir,
                    request.app.state.dashboard_dir,
                    {},
                    fecha_desde,
                    fecha_hasta,
                    csv_path=cot_path,
                )
                files_regenerated = [snapshot["file"]]
            archived = archive_data_dir(
                request.app.state.data_dir,
                request.app.state.processed_dir,
            )
            return {"status": "regenerado", "files": files_regenerated, "archived": archived}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app


app = create_app()

