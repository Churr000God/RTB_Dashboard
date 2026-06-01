import json
from datetime import datetime
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


class WebhookContractTests(unittest.TestCase):
    def test_build_payload_uses_expected_after_before_array(self):
        from rtb_web import build_payload

        self.assertEqual(
            build_payload("2026-04-01", "2026-04-30"),
            [{"after": "2026-04-01"}, {"before": "2026-04-30"}],
        )

    def test_rejects_end_date_before_start_date(self):
        from rtb_web import validate_request

        with self.assertRaisesRegex(ValueError, "fecha_hasta no puede ser menor"):
            validate_request("test", "2026-04-30", "2026-04-01")

    def test_rejects_unknown_environment(self):
        from rtb_web import validate_request

        with self.assertRaisesRegex(ValueError, "ambiente invalido"):
            validate_request("staging", "2026-04-01", "2026-04-30")

    def test_selects_test_webhook_url(self):
        from rtb_web import resolve_webhook_url

        self.assertEqual(
            resolve_webhook_url("test"),
            "https://sistemas-rtb.app.n8n.cloud/webhook-test/0003d589-aa54-49f3-b7de-65f675685fc0",
        )

    def test_selects_production_webhook_url(self):
        from rtb_web import resolve_webhook_url

        self.assertEqual(
            resolve_webhook_url("prod"),
            "https://sistemas-rtb.app.n8n.cloud/webhook/0003d589-aa54-49f3-b7de-65f675685fc0",
        )

    @patch("rtb_web.requests.post")
    def test_post_update_calls_requests_with_selected_url_and_payload(self, post):
        from rtb_web import call_webhook

        post.return_value.status_code = 200
        post.return_value.text = '{"ok": true}'
        post.return_value.headers = {"content-type": "application/json"}
        post.return_value.json.return_value = {"ok": True}

        result = call_webhook("test", "2026-04-01", "2026-04-30")

        post.assert_called_once_with(
            "https://sistemas-rtb.app.n8n.cloud/webhook-test/0003d589-aa54-49f3-b7de-65f675685fc0",
            json=[{"after": "2026-04-01"}, {"before": "2026-04-30"}],
            timeout=900,
        )
        self.assertEqual(result["status_code"], 200)
        self.assertEqual(result["response"], {"ok": True})
        self.assertEqual(
            result["payload"],
            [{"after": "2026-04-01"}, {"before": "2026-04-30"}],
        )

    def test_detects_new_cotizaciones_file_after_webhook_ok(self):
        import rtb_web

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        data_dir = Path(tmp.name)
        before = rtb_web.snapshot_cotizaciones(data_dir)
        (data_dir / "Cotizaciones_2026-06-01.csv").write_text("Cotizacion_id\nCOT-1\n", encoding="utf-8")

        self.assertEqual(
            rtb_web.find_changed_cotizaciones(data_dir, before).name,
            "Cotizaciones_2026-06-01.csv",
        )

    def test_detects_overwritten_cotizaciones_file_after_webhook_ok(self):
        import rtb_web

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        data_dir = Path(tmp.name)
        path = data_dir / "Cotizaciones.csv"
        path.write_text("Cotizacion_id\nCOT-1\n", encoding="utf-8")
        before = rtb_web.snapshot_cotizaciones(data_dir)
        time.sleep(0.001)
        path.write_text("Cotizacion_id\nCOT-1\nCOT-2\n", encoding="utf-8")
        os.utime(path, None)

        self.assertEqual(rtb_web.find_changed_cotizaciones(data_dir, before), path)

    def test_rejects_webhook_ok_without_updated_cotizaciones_file(self):
        import rtb_web

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)

        with self.assertRaisesRegex(ValueError, "No se encontro un CSV nuevo o actualizado"):
            rtb_web.find_changed_cotizaciones(Path(tmp.name), {})

    def test_waits_for_cotizaciones_file_that_arrives_after_webhook_ok(self):
        import rtb_web

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        data_dir = Path(tmp.name)
        attempts = []

        def fake_sleep(seconds):
            attempts.append(seconds)
            (data_dir / "Cotizaciones_sincronizada.csv").write_text("Cotizacion_id\nCOT-1\n", encoding="utf-8")

        changed = rtb_web.wait_for_changed_cotizaciones(data_dir, {}, sleep=fake_sleep, attempts=2, delay_seconds=0.25)

        self.assertEqual(changed.name, "Cotizaciones_sincronizada.csv")
        self.assertEqual(attempts, [0.25])

    def test_archive_ventas_uses_supplied_local_timestamp(self):
        import rtb_web

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        source = root / "Cotizaciones.csv"
        source.write_text("Cotizacion_id\nCOT-1\n", encoding="utf-8")

        archived = rtb_web.archive_ventas_csv(source, root / "procesada", archived_at=datetime(2026, 6, 1, 13, 33, 51))

        self.assertEqual(archived.parent.name, "2026-06-01_13-33-51_ventas")

    def test_ignores_previous_cotizaciones_and_unrelated_new_files(self):
        import rtb_web

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        data_dir = Path(tmp.name)
        previous = data_dir / "Cotizaciones_anterior.csv"
        previous.write_text("Cotizacion_id\nCOT-1\n", encoding="utf-8")
        before = rtb_web.snapshot_cotizaciones(data_dir)
        (data_dir / "PEDIDOS_CLIENTES.csv").write_text("id\nPED-1\n", encoding="utf-8")
        current = data_dir / "Cotizaciones_actual.csv"
        current.write_text("Cotizacion_id\nCOT-2\n", encoding="utf-8")

        self.assertEqual(rtb_web.find_changed_cotizaciones(data_dir, before), current)

    def test_app_endpoint_rejects_non_success_webhook_status(self):
        from fastapi.testclient import TestClient
        import rtb_web

        class FakeResponse:
            status_code = 500
            headers = {"content-type": "application/json"}

            def json(self):
                return {"ok": False}

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "data").mkdir()
        client = TestClient(rtb_web.create_app(http_post=lambda *args, **kwargs: FakeResponse(), data_dir=str(root / "data")))

        response = client.post(
            "/api/actualizar-datos",
            json={"ambiente": "test", "fecha_desde": "2026-04-01", "fecha_hasta": "2026-04-30"},
        )

        self.assertEqual(response.status_code, 502)
        self.assertIn("HTTP 500", response.json()["detail"])

    def test_app_endpoint_reports_webhook_timeout(self):
        from fastapi.testclient import TestClient
        import requests
        import rtb_web

        def fake_post(*args, **kwargs):
            raise requests.Timeout("n8n excedio el limite")

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "data").mkdir()
        client = TestClient(rtb_web.create_app(http_post=fake_post, data_dir=str(root / "data")))

        response = client.post(
            "/api/actualizar-datos",
            json={"ambiente": "test", "fecha_desde": "2026-04-01", "fecha_hasta": "2026-04-30"},
        )

        self.assertEqual(response.status_code, 502)
        self.assertIn("Error llamando webhook n8n", response.json()["detail"])

    def test_app_endpoint_processes_new_cotizaciones_after_webhook_ok(self):
        from fastapi.testclient import TestClient
        import rtb_web

        class FakeResponse:
            status_code = 200
            text = json.dumps({"ok": True})
            headers = {"content-type": "application/json"}

            def json(self):
                return {"ok": True}

        def fake_post(url, json, timeout):
            (data_dir / "Cotizaciones_2026-06-01.csv").write_text(
                "Cotizacion_id,Cotizacion_nombre,Fecha_creacion,Estado_cotizacion,Total,Subtotal_con_envio_venta\n"
                "COT-1,Cotizacion 1,2026-06-01,Aprobada,116,100\n",
                encoding="utf-8",
            )
            return FakeResponse()

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        data_dir = root / "data"
        data_dir.mkdir()
        client = TestClient(
            rtb_web.create_app(
                http_post=fake_post,
                data_dir=str(data_dir),
                processed_dir=str(root / "procesada"),
                dashboard_dir=str(root / "dashboard"),
            )
        )
        response = client.post(
            "/api/actualizar-datos",
            json={
                "ambiente": "test",
                "fecha_desde": "2026-04-01",
                "fecha_hasta": "2026-04-30",
            },
        )

        self.assertEqual(response.status_code, 202)
        body = response.json()
        self.assertEqual(body["status_code"], 200)
        self.assertEqual(body["response"], {"ok": True})
        self.assertEqual(body["ambiente"], "test")
        self.assertEqual(body["status"], "completada")
        self.assertEqual(body["files"], ["Cotizaciones_2026-06-01.csv"])
        self.assertEqual(list(data_dir.glob("*.csv")), [])
        archived = list((root / "procesada").glob("*_ventas/Cotizaciones_2026-06-01.csv"))
        self.assertEqual(len(archived), 1)
        dashboard = client.get("/api/dashboard/ventas").json()
        self.assertEqual(dashboard["kpis"]["total_cotizaciones"], 1)

    def test_ui_reloads_page_without_polling_run_status(self):
        from rtb_web import render_index

        html = render_index()

        self.assertNotIn("pollRun(", html)
        self.assertIn("window.location.reload();", html)

    def test_ui_shows_download_overlay_and_reloads_after_success(self):
        from rtb_web import render_index

        html = render_index()

        self.assertIn('id="downloadOverlay"', html)
        self.assertIn('role="status"', html)
        self.assertIn('aria-live="polite"', html)
        self.assertIn("function showDownloadOverlay()", html)
        self.assertIn("function hideDownloadOverlay()", html)
        self.assertIn("showDownloadOverlay();", html)
        self.assertIn("window.location.reload();", html)
        self.assertIn("hideDownloadOverlay();", html)
        self.assertIn("@media (prefers-reduced-motion: reduce)", html)
        self.assertNotIn("await loadVentasKpis();", html[html.index("form.addEventListener('submit'"):])

    def test_ui_has_dynamic_temporal_labels_for_monthly_periods(self):
        from rtb_web import render_index

        html = render_index()

        self.assertIn('id="temporalSectionTitle"', html)
        self.assertIn('id="temporalSectionSubtitle"', html)
        self.assertIn('id="temporalTableHeading"', html)
        self.assertIn('id="tiemposTemporalTitle"', html)
        self.assertIn('function configureTemporalLabels(granularidad)', html)
        self.assertIn("body.series?.temporal", html)

    def test_app_endpoint_rejects_webhook_response_without_ok(self):
        from fastapi.testclient import TestClient
        import rtb_web

        class FakeResponse:
            status_code = 200
            headers = {"content-type": "application/json"}

            def json(self):
                return {"ok": False}

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        data_dir = root / "data"
        data_dir.mkdir()
        client = TestClient(
            rtb_web.create_app(http_post=lambda *args, **kwargs: FakeResponse(), data_dir=str(data_dir))
        )

        response = client.post(
            "/api/actualizar-datos",
            json={"ambiente": "test", "fecha_desde": "2026-04-01", "fecha_hasta": "2026-04-30"},
        )

        self.assertEqual(response.status_code, 502)
        self.assertIn("no confirmo", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
