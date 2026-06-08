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
        import rtb_web

        with patch.dict(rtb_web.WEBHOOK_URLS, {"test": "https://stub.example/webhook-test"}):
            self.assertEqual(rtb_web.resolve_webhook_url("test"), "https://stub.example/webhook-test")

    def test_selects_production_webhook_url(self):
        import rtb_web

        with patch.dict(rtb_web.WEBHOOK_URLS, {"prod": "https://stub.example/webhook"}):
            self.assertEqual(rtb_web.resolve_webhook_url("prod"), "https://stub.example/webhook")

    def test_rejects_when_webhook_url_not_configured(self):
        import rtb_web

        with patch.dict(rtb_web.WEBHOOK_URLS, {"test": ""}):
            with self.assertRaisesRegex(ValueError, "webhook url no configurada"):
                rtb_web.resolve_webhook_url("test")

    @patch("rtb_web.requests.post")
    def test_post_update_calls_requests_with_selected_url_and_payload(self, post):
        import rtb_web

        post.return_value.status_code = 200
        post.return_value.text = '{"ok": true}'
        post.return_value.headers = {"content-type": "application/json"}
        post.return_value.json.return_value = {"ok": True}

        with patch.dict(rtb_web.WEBHOOK_URLS, {"test": "https://stub.example/webhook-test"}):
            result = rtb_web.call_webhook("test", "2026-04-01", "2026-04-30")

        post.assert_called_once_with(
            "https://stub.example/webhook-test",
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
        archived = list((root / "procesada").glob("*_datos/Cotizaciones_2026-06-01.csv"))
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


    def test_facturacion_endpoint_loads_current_exports(self):
        from fastapi.testclient import TestClient
        import rtb_web

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        data_dir = root / "data"
        data_dir.mkdir()
        (data_dir / "Cotizaciones_2026-06.csv").write_text(
            "Cotizacion_id,Estado_cotizacion,Total\nCOT-1,Aprobada,116\n",
            encoding="utf-8",
        )
        (data_dir / "Facturas_2026-06.csv").write_text(
            "Factura_id,Factura_cotizacion,Factura_Estado_Aprobacion,Estado_Factura,Fecha_Facturacion,#_Factura,Total\n"
            "FAC-1,COT-1,Aprobada,Factura enviada,2026-06-02,F-1,116\n",
            encoding="utf-8",
        )
        (data_dir / "Facturas_Secundarias_2026-06.csv").write_text(
            "Factura_id,Factura_cotizacion,Factura_Estado_Aprobacion,Estado_Factura,Fecha_Facturacion_Secundaria,#_Factura,Total\n",
            encoding="utf-8",
        )
        client = TestClient(rtb_web.create_app(data_dir=str(data_dir), dashboard_dir=str(root / "dashboard")))

        response = client.get("/api/dashboard/facturacion")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["kpis"]["facturas_vigentes"], 1)

    def test_publish_facturacion_snapshot_writes_dashboard_payload(self):
        import rtb_web

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        data_dir = root / "data"
        data_dir.mkdir()
        (data_dir / "Cotizaciones_2026-06.csv").write_text(
            "Cotizacion_id,Estado_cotizacion,Total\nCOT-1,Aprobada,116\n",
            encoding="utf-8",
        )
        (data_dir / "Facturas_2026-06.csv").write_text(
            "Factura_id,Factura_cotizacion,Factura_Estado_Aprobacion,Estado_Factura,Fecha_Facturacion,#_Factura,Total\n"
            "FAC-1,COT-1,Aprobada,Factura enviada,2026-06-02,F-1,116\n",
            encoding="utf-8",
        )
        (data_dir / "Facturas_Secundarias_2026-06.csv").write_text(
            "Factura_id,Factura_cotizacion,Factura_Estado_Aprobacion,Estado_Factura,Fecha_Facturacion_Secundaria,#_Factura,Total\n",
            encoding="utf-8",
        )

        snapshot = rtb_web.publish_facturacion_snapshot(data_dir, root / "dashboard", "2026-06-01", "2026-06-30")

        self.assertEqual(snapshot["dashboard"]["facturacion"]["kpis"]["facturas_vigentes"], 1)
        written = json.loads((root / "dashboard" / "facturacion_latest.json").read_text(encoding="utf-8"))
        self.assertEqual(written["files"]["principales"], "Facturas_2026-06.csv")

    def test_publish_facturacion_snapshot_uses_supplied_cotizaciones_path(self):
        import rtb_web

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        data_dir = root / "data"
        data_dir.mkdir()
        stale = data_dir / "Cotizaciones_stale.csv"
        stale.write_text("Cotizacion_id,Estado_cotizacion,Total\nCOT-OLD,Aprobada,999\n", encoding="utf-8")
        fresh = root / "Cotizaciones_fresh.csv"
        fresh.write_text("Cotizacion_id,Estado_cotizacion,Total\nCOT-1,Aprobada,116\n", encoding="utf-8")
        (data_dir / "Facturas_2026-06.csv").write_text(
            "Factura_id,Factura_cotizacion,Factura_Estado_Aprobacion,Estado_Factura,Fecha_Facturacion,#_Factura,Total\n"
            "FAC-1,COT-1,Aprobada,Factura enviada,2026-06-02,F-1,116\n",
            encoding="utf-8",
        )
        (data_dir / "Facturas_Secundarias_2026-06.csv").write_text(
            "Factura_id,Factura_cotizacion,Factura_Estado_Aprobacion,Estado_Factura,Fecha_Facturacion_Secundaria,#_Factura,Total\n",
            encoding="utf-8",
        )

        snapshot = rtb_web.publish_facturacion_snapshot(
            data_dir, root / "dashboard", "2026-06-01", "2026-06-30", cot_path=fresh
        )

        self.assertEqual(snapshot["dashboard"]["facturacion"]["kpis"]["rezago_estimado_cantidad"], 0)

    def test_ui_exposes_facturacion_tab_and_loader(self):
        from rtb_web import render_index

        html = render_index()

        self.assertIn('data-module="facturacion"', html)
        self.assertIn('id="facturacionPanel"', html)
        self.assertIn("fetch('/api/dashboard/facturacion')", html)


    def test_ui_compras_tiene_jerarquia_gerencial(self):
        html = (Path(__file__).resolve().parents[1] / "rtb_web.py").read_text(encoding="utf-8")

        self.assertIn("id=\"comprasRiskStrip\"", html)
        self.assertIn("id=\"comprasTipoBars\"", html)
        self.assertIn("id=\"comprasCfdiBars\"", html)
        self.assertIn("Compras documentadas", html)
        self.assertIn("Concentracion", html)
        self.assertIn("Periodo parcial", html)
        self.assertIn("kpis.iva_alerta", html)
        self.assertIn("management?.comparison", html)
        self.assertIn("management?.concentration", html)
        self.assertIn("Estado de facturas de compra", html)


class ComprasAnticiposSnapshotTests(unittest.TestCase):
    FC_HEADER = (
        "Factura_compra_id,Factura_compra_nombre,Factura_compra_envio,"
        "Factura_compra_subtotal,Factura_compra_seguro_envio,Fcatura_compra_iva,"
        "Factura_compra_total,#_Factura_compra,Factura_compra_tipo,"
        "Factura_compra_uso_cfdi,Factura_compra_estatus_factura,"
        "Facatura_compra_fecha_factura,Factura_compra_rfc_proveedor,"
        "Factura_Anticipo_Asociada\n"
    )
    ANT_HEADER = (
        "Factura_anticipo_id,Factura_anticipo_nombre,Factura_anticipo_Proveedor_Siglas,"
        "Factura_anticipo_Proveedor_nombre,Factura_anticipo_numero_documento,"
        "Factura_anticipo_fecha_emision,Factura_anticipo_estado,Factura_anticipo_monto,"
        "Factura_anticipo_tipo_documento,Factura_anticipo_uso_CFDI\n"
    )

    def _setup_dirs(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        data = root / "data"
        dashboard = root / "dashboard"
        data.mkdir()
        dashboard.mkdir()
        return data, dashboard

    def test_publish_compras_snapshot_carga_anticipos(self):
        import rtb_web

        data, dashboard = self._setup_dirs()
        (data / "Facturas_Compras_2026-06-04_14-29.csv").write_text(
            self.FC_HEADER
            + 'id-1,PRV - F1,0,1000,0,160,1160,F1,,G03,Facturada,2026-05-10,RFC1,[]\n'
            + 'id-2,VAT - V 2185,0,3468.22,0,554.91,4023.13,V 2185,,G01,Facturada,2026-06-01,RFC2,"[""ant-vatreni""]"\n',
            encoding="utf-8",
        )
        (data / "Facturas_Anticipo_2026-06-04_14-29.csv").write_text(
            self.ANT_HEADER
            + 'ant-vatreni,VAT - V 656,PROV-V,VATRENI,V 656,'
            + '"{""start"":""2026-05-27"",""end"":null,""time_zone"":null}",Procesada,4023.14,Factura de Anticipo,G01\n'
            + 'ant-dolsa,DOL - M 3564,PROV-D,DOLSA,M 3564,'
            + '"{""start"":""2026-05-12"",""end"":null,""time_zone"":null}",Procesada,8332.5,Factura de Anticipo,G01\n',
            encoding="utf-8",
        )

        snap = rtb_web.publish_compras_snapshot(data, dashboard, "2026-05-01", "2026-06-30")

        self.assertEqual(snap["files"]["anticipos"], "Facturas_Anticipo_2026-06-04_14-29.csv")
        kpis = snap["dashboard"]["compras"]["anticipos"]["kpis"]
        self.assertEqual(kpis["n_ant"], 2)
        self.assertEqual(kpis["n_ant_pendientes"], 1)
        self.assertEqual(kpis["n_ant_regularizados"], 1)
        self.assertAlmostEqual(kpis["monto_pendientes"], 8332.5, places=1)

    def test_publish_compras_snapshot_sin_csv_anticipos(self):
        import rtb_web

        data, dashboard = self._setup_dirs()
        (data / "Facturas_Compras_2026-06-04_14-29.csv").write_text(
            self.FC_HEADER
            + 'id-1,PRV - F1,0,1000,0,160,1160,F1,,G03,Facturada,2026-05-10,RFC1,[]\n',
            encoding="utf-8",
        )

        snap = rtb_web.publish_compras_snapshot(data, dashboard, "2026-05-01", "2026-06-30")

        self.assertNotIn("anticipos", snap["files"])
        kpis = snap["dashboard"]["compras"]["anticipos"]["kpis"]
        self.assertEqual(kpis["n_ant"], 0)


if __name__ == "__main__":
    unittest.main()
