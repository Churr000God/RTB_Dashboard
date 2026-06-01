import tempfile
import unittest
from pathlib import Path


class FakeCoordinator:
    def __init__(self):
        self.created = []
        self.finalized = []
        self.runs = {}
        self.callback_token = "secret"

    def create_run(self, fecha_desde, fecha_hasta):
        run = {
            "run_id": "run-123",
            "status": "solicitada",
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta,
        }
        self.created.append((fecha_desde, fecha_hasta))
        self.runs[run["run_id"]] = run
        return run

    def get_run(self, run_id):
        return self.runs[run_id]

    def finalize_run(self, run_id, archivos):
        self.finalized.append((run_id, archivos))
        run = {**self.runs[run_id], "status": "completada", "files": archivos}
        self.runs[run_id] = run
        return run

    def mark_start_failed(self, run_id, error):
        self.runs[run_id]["status"] = "fallida_inicio"

    def load_latest(self):
        return {"dashboard": {"ventas": {"kpis": {"cotizaciones": 99}}}}


class ActualizacionApiTests(unittest.TestCase):
    def test_start_returns_202_and_sends_filters_to_n8n(self):
        from fastapi.testclient import TestClient
        import rtb_web

        sent = {}
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        data_dir = root / "data"
        data_dir.mkdir()

        class FakeResponse:
            status_code = 200
            headers = {"content-type": "application/json"}

            def json(self):
                return {"ok": True}

        def fake_post(url, json, timeout):
            sent.update({"url": url, "json": json, "timeout": timeout})
            (data_dir / "Cotizaciones_2026-05.csv").write_text(
                "Cotizacion_id,Fecha_creacion,Estado_cotizacion,Total,Subtotal_con_envio_venta\n"
                "COT-1,2026-05-01,Aprobada,116,100\n",
                encoding="utf-8",
            )
            return FakeResponse()

        app = rtb_web.create_app(
            http_post=fake_post,
            data_dir=str(data_dir),
            dashboard_dir=str(root / "dashboard"),
        )
        response = TestClient(app).post(
            "/api/actualizar-datos",
            json={"ambiente": "test", "fecha_desde": "2026-05-01", "fecha_hasta": "2026-05-31"},
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "completada")
        self.assertEqual(
            sent["json"],
            [{"after": "2026-05-01"}, {"before": "2026-05-31"}],
        )
        self.assertEqual(sent["timeout"], 900)

    def test_callback_rejects_invalid_token(self):
        from fastapi.testclient import TestClient
        import rtb_web

        coordinator = FakeCoordinator()
        coordinator.create_run("2026-05-01", "2026-05-31")
        client = TestClient(rtb_web.create_app(coordinator=coordinator))

        response = client.post(
            "/api/actualizaciones/finalizar",
            headers={"X-RTB-Webhook-Token": "wrong"},
            json={"run_id": "run-123", "archivos": ["Cotizaciones.csv"]},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(coordinator.finalized, [])

    def test_callback_finalizes_run_and_status_endpoint_exposes_result(self):
        from fastapi.testclient import TestClient
        import rtb_web

        coordinator = FakeCoordinator()
        coordinator.create_run("2026-05-01", "2026-05-31")
        client = TestClient(rtb_web.create_app(coordinator=coordinator))

        callback = client.post(
            "/api/actualizaciones/finalizar",
            headers={"X-RTB-Webhook-Token": "secret"},
            json={"run_id": "run-123", "archivos": ["Cotizaciones.csv"]},
        )
        status = client.get("/api/actualizaciones/run-123")

        self.assertEqual(callback.status_code, 200)
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["status"], "completada")

    def test_dashboard_reads_latest_snapshot_when_available(self):
        from fastapi.testclient import TestClient
        import rtb_web

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        response = TestClient(
            rtb_web.create_app(coordinator=FakeCoordinator(), dashboard_dir=tmp.name)
        ).get("/api/dashboard/ventas")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["kpis"]["cotizaciones"], 99)


if __name__ == "__main__":
    unittest.main()
