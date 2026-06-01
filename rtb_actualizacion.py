#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Coordina actualizaciones asíncronas del dashboard RTB."""

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from rtb_analisis import build_ventas_dashboard, compute, load_all


ACTIVE_STATUSES = {"solicitada", "procesando", "archivando"}


class ActiveRunError(RuntimeError):
    pass


class InvalidRunError(ValueError):
    pass


class RunNotFoundError(LookupError):
    pass


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)
        fh.write("\n")
    os.replace(temporary, path)


class UpdateCoordinator:
    def __init__(self, data_dir, processed_dir, dashboard_dir, callback_token=""):
        self.data_dir = Path(data_dir)
        self.processed_dir = Path(processed_dir)
        self.dashboard_dir = Path(dashboard_dir)
        self.runs_dir = self.dashboard_dir / "runs"
        self.snapshots_dir = self.dashboard_dir / "snapshots"
        self.callback_token = callback_token

    def _run_path(self, run_id):
        if not re.fullmatch(r"[a-f0-9]{32}", str(run_id)):
            raise RunNotFoundError(f"Identificador de corrida invalido: {run_id}")
        return self.runs_dir / f"{run_id}.json"

    def _save_run(self, run):
        run["updated_at"] = utc_now()
        atomic_write_json(self._run_path(run["run_id"]), run)
        return run

    def _iter_runs(self):
        if not self.runs_dir.exists():
            return []
        runs = []
        for path in self.runs_dir.glob("*.json"):
            try:
                runs.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return runs

    def create_run(self, fecha_desde, fecha_hasta):
        for run in self._iter_runs():
            if run.get("status") in ACTIVE_STATUSES:
                raise ActiveRunError(f"Ya existe una corrida activa: {run['run_id']}")
        run = {
            "run_id": uuid4().hex,
            "status": "solicitada",
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta,
            "created_at": utc_now(),
            "files": [],
            "error": None,
        }
        return self._save_run(run)

    def get_run(self, run_id):
        path = self._run_path(run_id)
        if not path.exists():
            raise RunNotFoundError(f"No existe la corrida: {run_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def mark_start_failed(self, run_id, error):
        run = self.get_run(run_id)
        run["status"] = "fallida_inicio"
        run["error"] = str(error)
        return self._save_run(run)

    def _validate_files(self, filenames):
        if not filenames:
            raise InvalidRunError("El callback no incluye archivos CSV")
        clean = []
        seen = set()
        for filename in filenames:
            if not isinstance(filename, str):
                raise InvalidRunError("Cada nombre de archivo debe ser texto")
            if filename != os.path.basename(filename) or filename in (".", ".."):
                raise InvalidRunError(f"nombre de archivo inseguro: {filename}")
            if not filename.lower().endswith(".csv"):
                raise InvalidRunError(f"El archivo no es CSV: {filename}")
            if filename in seen:
                raise InvalidRunError(f"Archivo duplicado: {filename}")
            path = self.data_dir / filename
            if not path.is_file():
                raise InvalidRunError(f"No existe el archivo declarado: {filename}")
            seen.add(filename)
            clean.append(filename)
        return clean

    def _archive_files(self, run):
        destination_dir = self.processed_dir / run["archive_slug"]
        destination_dir.mkdir(parents=True, exist_ok=True)
        moved = []
        pending = []
        for filename in run["files"]:
            source = self.data_dir / filename
            destination = destination_dir / filename
            if source.exists():
                if destination.exists():
                    pending.append(filename)
                    continue
                shutil.move(str(source), str(destination))
            if destination.exists():
                moved.append(filename)
            else:
                pending.append(filename)
        run["processed_dir"] = str(destination_dir)
        run["moved_files"] = moved
        run["pending_files"] = pending
        if pending:
            raise OSError(f"No se pudieron archivar: {', '.join(pending)}")
        return run

    def finalize_run(self, run_id, filenames):
        run = self.get_run(run_id)
        if run["status"] == "completada":
            return run
        if run["status"] in {"archivando", "fallida_archivado"}:
            return self._retry_archive(run)

        try:
            clean_files = self._validate_files(filenames)
        except Exception as exc:
            run["status"] = "fallida_validacion"
            run["error"] = str(exc)
            self._save_run(run)
            raise

        run["status"] = "procesando"
        run["files"] = clean_files
        run["error"] = None
        self._save_run(run)

        try:
            data = load_all(self.data_dir, allowed_files=clean_files)
            period_label = f"{run['fecha_desde']} a {run['fecha_hasta']}"
            period = {
                "start": run["fecha_desde"],
                "end": run["fecha_hasta"],
                "label": period_label,
                "range_label": period_label,
            }
            metrics = compute(data, period=period)
            metrics["period"] = {
                "start": run["fecha_desde"],
                "end": run["fecha_hasta"],
                "label": period_label,
                "range_label": period_label,
            }
            ventas = build_ventas_dashboard(
                data["cot"], period_label=period_label,
                fecha_desde=run["fecha_desde"], fecha_hasta=run["fecha_hasta"],
            )
        except Exception as exc:
            run["status"] = "fallida_calculo"
            run["error"] = str(exc)
            self._save_run(run)
            raise

        archive_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        run["archive_slug"] = f"{archive_time}_{run_id}"
        snapshot = {
            "run_id": run_id,
            "generated_at": utc_now(),
            "period": {
                "start": run["fecha_desde"],
                "end": run["fecha_hasta"],
                "label": period_label,
            },
            "files": clean_files,
            "metrics": metrics,
            "dashboard": {"ventas": ventas},
        }
        history_path = self.snapshots_dir / f"{archive_time}_{run_id}.json"
        try:
            atomic_write_json(history_path, snapshot)
            atomic_write_json(self.dashboard_dir / "latest.json", snapshot)
        except Exception as exc:
            run["status"] = "fallida_publicacion"
            run["error"] = str(exc)
            self._save_run(run)
            raise
        run["snapshot_path"] = str(history_path)
        run["status"] = "archivando"
        self._save_run(run)

        try:
            self._archive_files(run)
        except Exception as exc:
            run["status"] = "fallida_archivado"
            run["error"] = str(exc)
            self._save_run(run)
            raise

        run["status"] = "completada"
        run["error"] = None
        return self._save_run(run)

    def _retry_archive(self, run):
        try:
            self._archive_files(run)
        except Exception as exc:
            run["error"] = str(exc)
            self._save_run(run)
            raise
        run["status"] = "completada"
        run["error"] = None
        return self._save_run(run)

    def load_latest(self):
        path = self.dashboard_dir / "latest.json"
        if not path.exists():
            raise FileNotFoundError(f"No existe snapshot vigente: {path}")
        return json.loads(path.read_text(encoding="utf-8"))
