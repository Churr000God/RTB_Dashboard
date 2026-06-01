import csv
import tempfile
import unittest
from pathlib import Path


def write_csv(path, rows):
    fieldnames = [
        "Cotizacion_id",
        "Cotizacion_nombre",
        "Cliente",
        "Subtotal_venta",
        "Envio",
        "Subtotal_con_envio_venta",
        "Total",
        "Fecha_creacion",
        "Fecha_aprobacion",
        "PO",
        "PR",
        "Status_pedido",
        "Estado_pago",
        "Localidad",
        "Estado_cotizacion",
        "Aprobado_por",
        "Ariba",
        "Pedidos_Asociados.0",
        "Tipo_pago.0",
        "Pedidos_Asociados.1",
        "Tipo_pago.1",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class VentasDashboardTests(unittest.TestCase):
    def sample_rows(self):
        return [
            {
                "Cotizacion_id": "cot-1",
                "Cotizacion_nombre": "ACME*001",
                "Cliente": "ACME",
                "Subtotal_venta": "1000",
                "Subtotal_con_envio_venta": "1000",
                "Total": "1160",
                "Fecha_creacion": "2026-04-02T10:00:00.000Z",
                "Fecha_aprobacion": '{"start":"2026-04-02T12:00:00.000-06:00","end":null,"time_zone":null}',
                "Status_pedido": "Pendiente",
                "Estado_pago": '["No pagada"]',
                "Localidad": "Local",
                "Estado_cotizacion": "Aprobada",
                "Aprobado_por": '["ventas@rtb.com"]',
                "Ariba": "true",
                "Pedidos_Asociados.0": "ped-1",
                "Tipo_pago.0": "Transferencia",
            },
            {
                "Cotizacion_id": "cot-2",
                "Cotizacion_nombre": "BETA*002",
                "Cliente": "BETA",
                "Subtotal_venta": "2000",
                "Subtotal_con_envio_venta": "2000",
                "Total": "2320",
                "Fecha_creacion": "2026-04-17T10:00:00.000Z",
                "Status_pedido": "Pendiente",
                "Estado_pago": "[]",
                "Localidad": "Foraneo",
                "Estado_cotizacion": "Expirada",
                "Aprobado_por": "[]",
                "Ariba": "false",
                "Tipo_pago.0": "",
            },
            {
                "Cotizacion_id": "cot-3",
                "Cotizacion_nombre": "GAMMA*003",
                "Cliente": "GAMMA",
                "Subtotal_venta": "500",
                "Subtotal_con_envio_venta": "500",
                "Total": "580",
                "Fecha_creacion": "2026-04-30T10:00:00.000Z",
                "Fecha_aprobacion": "2026-05-02T10:00:00.000Z",
                "Status_pedido": "Pendiente",
                "Estado_pago": '["No pagada"]',
                "Localidad": "Foraneo",
                "Estado_cotizacion": "Aprobada",
                "Aprobado_por": '["ventas@rtb.com"]',
                "Ariba": "false",
                "Tipo_pago.0": "",
            },
        ]

    def test_load_cotizaciones_accepts_only_new_prefix(self):
        from rtb_analisis import load_cotizaciones

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_csv(root / "Cotizaciones_2026-05-29_08-46.csv", self.sample_rows())
            rows = load_cotizaciones(root)

        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["Cotizacion_id"], "cot-1")

    def test_load_cotizaciones_rejects_legacy_prefix(self):
        from rtb_analisis import load_cotizaciones

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_csv(root / "COTIZACIONES_CLIENTES_legacy.csv", self.sample_rows())

            with self.assertRaisesRegex(FileNotFoundError, "Cotizaciones"):
                load_cotizaciones(root)

    def test_compute_ventas_uses_total_as_amount_with_iva(self):
        from rtb_analisis import compute_ventas

        result = compute_ventas(self.sample_rows())

        self.assertEqual(result["n_cot"], 3)
        self.assertEqual(result["n_apr"], 2)
        self.assertEqual(result["tot_cot"], 4060)
        self.assertEqual(result["sub_cot"], 3500)
        self.assertEqual(result["mon_apr"], 1740)
        self.assertAlmostEqual(result["conv_q"], 2 / 3)
        self.assertAlmostEqual(result["conv_m"], 1740 / 4060)
        self.assertEqual(result["sem_cot"]["S1"]["m"], 1160)
        self.assertEqual(result["sem_cot"]["S3"]["m"], 2320)
        self.assertEqual(result["sem_cot"]["S5"]["ma"], 580)
        self.assertEqual(result["n_ariba"], 1)
        self.assertEqual(result["m_ariba"], 1160)

    def test_build_ventas_dashboard_generates_v1_signals(self):
        from rtb_analisis import build_ventas_dashboard

        dashboard = build_ventas_dashboard(self.sample_rows(), period_label="Abril 2026")
        signal_types = {signal["tipo"] for signal in dashboard["signals"]}

        self.assertIn("tipo_pago_sin_definir", signal_types)
        self.assertIn("aprobada_sin_pedido", signal_types)
        self.assertIn("ariba_aprobada", signal_types)
        self.assertIn("expirada_monto_alto", signal_types)
        self.assertIn("semana_baja_conversion", signal_types)
        self.assertEqual(dashboard["kpis"]["total_cotizado"], 4060)

    def test_build_ventas_dashboard_exposes_requested_general_kpis(self):
        from rtb_analisis import build_ventas_dashboard

        rows = self.sample_rows() + [
            {
                "Cotizacion_id": "cot-4",
                "Cotizacion_nombre": "DELTA*004",
                "Cliente": "DELTA",
                "Subtotal_venta": "1000",
                "Subtotal_con_envio_venta": "1000",
                "Total": "1160",
                "Fecha_creacion": "2026-04-10T10:00:00.000Z",
                "Localidad": "Local",
                "Estado_cotizacion": "Expirada",
                "Ariba": "true",
                "Tipo_pago.0": "Credito",
            }
        ]

        dashboard = build_ventas_dashboard(rows, period_label="Abril 2026")
        kpis = dashboard["kpis"]

        self.assertEqual(kpis["total_cotizaciones"], 4)
        self.assertEqual(kpis["total_cotizado_iva"], 5220)
        self.assertEqual(kpis["cotizaciones_aprobadas"], 2)
        self.assertEqual(kpis["monto_aprobado_iva"], 1740)
        self.assertAlmostEqual(kpis["aprobacion_cantidad_pct"], 2 / 4)
        self.assertAlmostEqual(kpis["aprobacion_monto_pct"], 1740 / 5220)
        self.assertAlmostEqual(kpis["diferencia_aprobacion_pct"], (1740 / 5220) - (2 / 4))
        self.assertEqual(kpis["ticket_promedio_cotizado"], 5220 / 4)
        self.assertEqual(kpis["ticket_promedio_aprobado"], 1740 / 2)
        self.assertEqual(kpis["ariba_aprobadas"], 1)
        self.assertEqual(kpis["monto_ariba_aprobado"], 1160)
        self.assertAlmostEqual(kpis["ariba_aprobadas_pct_cantidad"], 1 / 4)
        self.assertAlmostEqual(kpis["ariba_aprobadas_pct_monto"], 1160 / 5220)
        self.assertAlmostEqual(kpis["diferencia_ariba_aprobada_pct"], (1160 / 5220) - (1 / 4))
        # Ariba cotizado (new)
        self.assertEqual(kpis["ariba_cotizadas"], 2)            # cot-1 + cot-4
        self.assertEqual(kpis["monto_ariba_cotizado"], 2320)    # 1160 + 1160
        self.assertAlmostEqual(kpis["ticket_ariba_cotizado"], 1160.0)
        # Ariba conversión interna (aprobado/cotizado dentro de Ariba)
        self.assertAlmostEqual(kpis["ariba_conv_q"], 1 / 2)     # 1 apr / 2 cot Ariba
        self.assertAlmostEqual(kpis["ariba_conv_m"], 1160 / 2320)
        self.assertAlmostEqual(kpis["diferencia_ariba_conv"], (1160 / 2320) - (1 / 2))

    def test_signals_are_dashboard_only_not_a_webhook_endpoint(self):
        from fastapi.testclient import TestClient
        import rtb_web

        client = TestClient(rtb_web.create_app())
        response = client.post(
            "/api/senales/enviar",
            json={"ambiente": "test", "signals": [{"id": "sig-1", "tipo": "ariba_aprobada"}]},
        )

        self.assertEqual(response.status_code, 404)


class TopClientesEnrichmentTests(unittest.TestCase):
    def sample_rows(self):
        return VentasDashboardTests().sample_rows()

    def test_top_cli_cot_includes_approved_amounts(self):
        from rtb_analisis import compute_ventas

        result = compute_ventas(self.sample_rows())
        top = dict(result["top_cli_cot"])

        # ACME: cotizó 1, monto 1160, aprobada 1, ma 1160
        self.assertIn("ACME", top)
        self.assertEqual(top["ACME"]["na"], 1)
        self.assertAlmostEqual(top["ACME"]["ma"], 1160.0)

        # BETA: cotizó 1, monto 2320, NO aprobada
        self.assertIn("BETA", top)
        self.assertEqual(top["BETA"]["na"], 0)
        self.assertAlmostEqual(top["BETA"]["ma"], 0.0)

    def test_top_cli_apr_includes_quoted_amounts(self):
        from rtb_analisis import compute_ventas

        result = compute_ventas(self.sample_rows())
        top = dict(result["top_cli_apr"])

        # ACME: aprobada 1 (ma 1160), cotizó 1 (m_cot 1160)
        self.assertIn("ACME", top)
        self.assertEqual(top["ACME"]["n_cot"], 1)
        self.assertAlmostEqual(top["ACME"]["m_cot"], 1160.0)


class LinearTrendTests(unittest.TestCase):
    def test_linear_trend_returns_zero_slope_for_flat_series(self):
        from rtb_analisis import linear_trend

        result = linear_trend([100, 100, 100, 100, 100])

        self.assertAlmostEqual(result["m"], 0.0)
        self.assertAlmostEqual(result["start"], 100.0)
        self.assertAlmostEqual(result["end"], 100.0)

    def test_linear_trend_returns_positive_slope_for_increasing_series(self):
        from rtb_analisis import linear_trend

        result = linear_trend([10, 20, 30, 40, 50])

        self.assertAlmostEqual(result["m"], 10.0)
        self.assertAlmostEqual(result["start"], 10.0)
        self.assertAlmostEqual(result["end"], 50.0)

    def test_linear_trend_returns_negative_slope_for_decreasing_series(self):
        from rtb_analisis import linear_trend

        result = linear_trend([50, 40, 30, 20, 10])

        self.assertAlmostEqual(result["m"], -10.0)
        self.assertAlmostEqual(result["start"], 50.0)
        self.assertAlmostEqual(result["end"], 10.0)

    def test_linear_trend_handles_empty_and_single_value(self):
        from rtb_analisis import linear_trend

        empty = linear_trend([])
        self.assertEqual(empty["m"], 0.0)
        self.assertEqual(empty["start"], 0.0)
        self.assertEqual(empty["end"], 0.0)

        single = linear_trend([42])
        self.assertAlmostEqual(single["m"], 0.0)
        self.assertAlmostEqual(single["start"], 42.0)
        self.assertAlmostEqual(single["end"], 42.0)

    def test_build_ventas_dashboard_exposes_weekly_trends(self):
        from rtb_analisis import build_ventas_dashboard

        dashboard = build_ventas_dashboard(
            VentasDashboardTests().sample_rows(), period_label="Abril 2026"
        )
        tendencias = dashboard["series"]["tendencias"]

        for key in ("cotizado", "aprobado", "conv_qty", "cotizaciones", "aprobadas"):
            self.assertIn(key, tendencias, f"falta clave '{key}' en tendencias")
            for field in ("m", "b", "start", "end"):
                self.assertIn(field, tendencias[key], f"falta campo '{field}' en tendencias.{key}")

    def test_build_ventas_dashboard_groups_multi_month_period_by_calendar_month(self):
        from rtb_analisis import build_ventas_dashboard

        dashboard = build_ventas_dashboard(
            VentasDashboardTests().sample_rows(), period_label="2026-04-01 a 2026-05-31",
            fecha_desde="2026-04-01", fecha_hasta="2026-05-31",
        )
        temporal = dashboard["series"]["temporal"]

        self.assertEqual(temporal["granularidad"], "mes")
        self.assertEqual([item["etiqueta"] for item in temporal["periodos"]], ["Abr 2026", "May 2026"])
        self.assertEqual(temporal["periodos"][0]["cotizaciones"], 3)
        self.assertEqual(temporal["periodos"][0]["aprobadas"], 2)
        self.assertEqual(temporal["periodos"][1]["cotizaciones"], 0)
        self.assertEqual([item["etiqueta"] for item in temporal["tiempos_aprobacion"]], ["Abr 2026", "May 2026"])
        self.assertEqual(temporal["tiempos_aprobacion"][0]["n"], 2)

    def test_build_ventas_dashboard_keeps_weekly_periods_for_single_month(self):
        from rtb_analisis import build_ventas_dashboard

        dashboard = build_ventas_dashboard(
            VentasDashboardTests().sample_rows(), period_label="2026-04-01 a 2026-04-30",
            fecha_desde="2026-04-01", fecha_hasta="2026-04-30",
        )
        temporal = dashboard["series"]["temporal"]

        self.assertEqual(temporal["granularidad"], "semana")
        self.assertEqual([item["etiqueta"] for item in temporal["periodos"]], ["S1", "S2", "S3", "S4", "S5"])

    def test_build_ventas_dashboard_weekly_trends_cantidad_values(self):
        from rtb_analisis import build_ventas_dashboard

        dashboard = build_ventas_dashboard(
            VentasDashboardTests().sample_rows(), period_label="Abril 2026"
        )
        tendencias = dashboard["series"]["tendencias"]

        # cot-1 en S1: n=1, na=1 | cot-2 en S3: n=1, na=0 | cot-3 en S5: n=1, na=1
        # cotizaciones trend: start y end deben ser >= 0
        self.assertGreaterEqual(tendencias["cotizaciones"]["start"], 0)
        self.assertGreaterEqual(tendencias["aprobadas"]["start"], 0)


class TiemposAprobacionTests(unittest.TestCase):
    def sample_rows(self):
        return VentasDashboardTests().sample_rows()

    def sample_rows_con_sin_fecha(self):
        rows = self.sample_rows()
        rows.append({
            "Cotizacion_id": "cot-nofecha",
            "Cotizacion_nombre": "NODATES*999",
            "Cliente": "NODATES",
            "Subtotal_venta": "100",
            "Subtotal_con_envio_venta": "100",
            "Total": "116",
            "Fecha_creacion": "2026-04-10T10:00:00.000Z",
            "Estado_cotizacion": "Aprobada",
            "Aprobado_por": '["ventas@rtb.com"]',
            "Ariba": "false",
            "Tipo_pago.0": "",
        })
        return rows

    def test_compute_ventas_cuenta_sin_fechas(self):
        from rtb_analisis import compute_ventas

        result = compute_ventas(self.sample_rows_con_sin_fecha())
        # cot-nofecha es aprobada pero sin Fecha_aprobacion
        self.assertEqual(result["n_apr_sin_fechas"], 1)

    def test_compute_ventas_histograma_dias(self):
        from rtb_analisis import compute_ventas

        result = compute_ventas(self.sample_rows())
        hist = result["hist_apr"]
        # cot-1: delta=0 (mismo día) → bucket "0"
        self.assertIn("0", hist)
        self.assertEqual(hist["0"], 1)
        # cot-3: created 2026-04-30, approved 2026-05-02 → delta=2 → bucket "2"
        self.assertIn("2", hist)
        self.assertEqual(hist["2"], 1)

    def test_compute_ventas_sem_apr_por_semana(self):
        from rtb_analisis import compute_ventas

        result = compute_ventas(self.sample_rows())
        sem = result["sem_apr"]
        # cot-1 en S1: delta=0 → avg=0.0, n=1
        self.assertIn("S1", sem)
        self.assertAlmostEqual(sem["S1"]["avg"], 0.0)
        self.assertEqual(sem["S1"]["n"], 1)
        # cot-3 en S5: delta=2 → avg=2.0, n=1
        self.assertIn("S5", sem)
        self.assertAlmostEqual(sem["S5"]["avg"], 2.0)
        self.assertEqual(sem["S5"]["n"], 1)

    def test_build_ventas_dashboard_exposes_tiempos_aprobacion(self):
        from rtb_analisis import build_ventas_dashboard

        dashboard = build_ventas_dashboard(self.sample_rows(), period_label="Abril 2026")
        ta = dashboard["series"].get("tiempos_aprobacion")
        self.assertIsNotNone(ta, "falta series.tiempos_aprobacion")

        stats = ta["stats"]
        for key in ("promedio", "mediana", "maximo", "n_con_datos", "n_sin_fechas"):
            self.assertIn(key, stats, f"falta stats.{key}")
        # cot-1 delta=0, cot-3 delta=2 → avg=1.0, med=1.0, max=2
        self.assertAlmostEqual(stats["promedio"], 1.0)
        self.assertAlmostEqual(stats["mediana"], 1.0)
        self.assertEqual(stats["maximo"], 2)
        self.assertEqual(stats["n_con_datos"], 2)
        self.assertEqual(stats["n_sin_fechas"], 0)

        rangos = ta["rangos"]
        self.assertIsInstance(rangos, list)
        self.assertTrue(any(r["rango"] == "Mismo día" for r in rangos))

        self.assertIn("semanal", ta)
        self.assertIn("histograma", ta)
        # tendencia semanal: clave y campos m/b/start/end
        self.assertIn("semanal_tendencia", ta, "falta semanal_tendencia")
        for field in ("m", "b", "start", "end"):
            self.assertIn(field, ta["semanal_tendencia"], f"falta semanal_tendencia.{field}")
        # cot-1 S1 avg=0, cot-3 S5 avg=2 → pendiente positiva
        self.assertGreater(ta["semanal_tendencia"]["m"], 0)


if __name__ == "__main__":
    unittest.main()
