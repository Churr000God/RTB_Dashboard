import os
import tempfile
import time
import unittest


class FacturacionDashboardTests(unittest.TestCase):
    def principales(self):
        return [
            {"Factura_id": "FAC-1", "Factura_nombre": "Factura 1", "Factura_cotizacion": "COT-1", "Factura_Estado_Aprobacion": "Aprobada", "Estado_Factura": "Factura enviada", "Fecha_Facturacion": '{"start":"2026-05-06"}', "Fecha_Validacion": '{"start":"2026-05-07"}', "Fecha_Asociacion": '{"start":"2026-05-08"}', "#_Factura": "F-1", "Subtotal": "100", "Total": "116", "Monto_primer_factura": ""},
            {"Factura_id": "FAC-2", "Factura_nombre": "Factura 2", "Factura_cotizacion": "COT-2", "Factura_Estado_Aprobacion": "Aprobada", "Estado_Factura": "Facturando", "Fecha_Facturacion": '{"start":"2026-05-15"}', "Fecha_Validacion": "", "Fecha_Asociacion": "", "#_Factura": "F-2", "Subtotal": "200", "Total": "232", "Monto_primer_factura": "80"},
            {"Factura_id": "FAC-CANCEL", "Factura_cotizacion": "COT-3", "Factura_Estado_Aprobacion": "Cancelada", "Estado_Factura": "Factura enviada", "Fecha_Facturacion": '{"start":"2026-05-20"}', "#_Factura": "F-C", "Total": "58"},
            {"Factura_id": "FAC-INCOMPLETE", "Factura_cotizacion": "COT-4", "Factura_Estado_Aprobacion": "Aprobada", "Estado_Factura": "Factura enviada", "Fecha_Facturacion": "", "#_Factura": "", "Total": "464"},
        ]

    def secundarias(self):
        return [
            {"Factura_id": "FAC-1", "Factura_cotizacion": "COT-1", "Factura_Estado_Aprobacion": "Aprobada", "Estado_Factura": "Factura enviada", "Fecha_Facturacion_Secundaria": '{"start":"2026-05-06"}', "Fecha_Validacion_Secundaria": '{"start":"2026-05-07"}', "Fecha_Asociacion_Secundaria": '{"start":"2026-05-08"}', "#_Factura": "F-1", "Total": "116", "Monto_segunda_factura": ""},
            {"Factura_id": "FAC-3", "Factura_cotizacion": "COT-3", "Factura_Estado_Aprobacion": "Aprobada", "Estado_Factura": "Factura enviada", "Fecha_Facturacion_Secundaria": '{"start":"2026-05-21"}', "Fecha_Validacion_Secundaria": '{"start":"2026-05-22"}', "Fecha_Asociacion_Secundaria": "", "#_Factura": "F-3", "Total": "174", "Monto_segunda_factura": "60"},
        ]

    def cotizaciones(self):
        return [
            {"Cotizacion_id": "COT-1", "Estado_cotizacion": "Aprobada", "Total": "116", "Fecha_aprobacion": "2026-05-05"},
            {"Cotizacion_id": "COT-2", "Estado_cotizacion": "Aprobada", "Total": "232", "Fecha_aprobacion": "2026-05-14"},
            {"Cotizacion_id": "COT-4", "Estado_cotizacion": "Aprobada", "Total": "464", "Fecha_aprobacion": "2026-04-01"},
            {"Cotizacion_id": "COT-X", "Estado_cotizacion": "Expirada", "Total": "999"},
        ]

    def test_build_facturacion_dashboard_applies_validity_amount_and_dedupe_rules(self):
        from rtb_analisis import build_facturacion_dashboard
        dashboard = build_facturacion_dashboard(self.cotizaciones(), self.principales(), self.secundarias(), period_label="Mayo 2026", fecha_desde="2026-05-01", fecha_hasta="2026-05-31")
        kpis = dashboard["kpis"]
        self.assertEqual(kpis["facturas_vigentes"], 3)
        self.assertEqual(kpis["monto_facturado_vigente"], 256)
        self.assertEqual(kpis["ticket_promedio_facturado"], 256 / 3)
        self.assertEqual(kpis["facturas_principales"], 2)
        self.assertEqual(kpis["facturas_secundarias"], 1)
        self.assertEqual(kpis["facturas_canceladas"], 1)
        self.assertEqual(kpis["monto_cancelado"], 58)
        self.assertEqual(kpis["rezago_estimado_cantidad"], 1)
        self.assertEqual(kpis["rezago_estimado_monto"], 464)
        self.assertEqual(kpis["cobertura_validacion_pct"], 2 / 3)
        self.assertEqual(kpis["cobertura_asociacion_pct"], 1 / 3)

    def test_build_facturacion_dashboard_exposes_temporal_status_and_alerts(self):
        from rtb_analisis import build_facturacion_dashboard
        dashboard = build_facturacion_dashboard(self.cotizaciones(), self.principales(), self.secundarias(), period_label="Mayo 2026", fecha_desde="2026-05-01", fecha_hasta="2026-05-31")
        temporal = dashboard["series"]["temporal"]
        self.assertEqual(temporal["granularidad"], "semana")
        self.assertEqual(sum(row["cantidad"] for row in temporal["periodos"]), 3)
        self.assertEqual(sum(row["monto"] for row in temporal["periodos"]), 256)
        estados = {row["estado"]: row["n"] for row in dashboard["series"]["estados"]}
        self.assertEqual(estados, {"Factura enviada": 2, "Facturando": 1})
        tipos = {signal["tipo"] for signal in dashboard["signals"]}
        self.assertIn("factura_captura_incompleta", tipos)
        # FAC-1 aparece en principales y secundarias con el mismo factura_id →
        # es el mismo registro exportado dos veces, no un duplicado real → no dispara señal
        self.assertNotIn("factura_duplicada", tipos)
        self.assertIn("rezago_facturacion_estimado", tipos)

    def test_build_facturacion_dashboard_excludes_rows_outside_selected_period(self):
        from rtb_analisis import build_facturacion_dashboard
        rows = self.principales()
        rows[0]["Fecha_Facturacion"] = '{"start":"2026-04-30"}'
        dashboard = build_facturacion_dashboard(self.cotizaciones(), rows, [], fecha_desde="2026-05-01", fecha_hasta="2026-05-31")
        self.assertEqual(dashboard["kpis"]["facturas_vigentes"], 1)
        self.assertEqual(dashboard["kpis"]["monto_facturado_vigente"], 80)


    def test_build_facturacion_dashboard_computes_ciclo_etapas(self):
        from rtb_analisis import build_facturacion_dashboard
        dashboard = build_facturacion_dashboard(self.cotizaciones(), self.principales(), self.secundarias(), period_label="Mayo 2026", fecha_desde="2026-05-01", fecha_hasta="2026-05-31")
        ciclo = dashboard["ciclo"]
        etapas = {e["etapa"]: e for e in ciclo["etapas"]}

        # FAC-1: aprobada 2026-05-05, facturada 2026-05-06 -> pf=1
        # FAC-2: aprobada 2026-05-14, facturada 2026-05-15 -> pf=1
        # FAC-3 (secundaria, COT-3 no esta en cotizaciones) -> pf=None
        pf = etapas["Pedido → Facturado"]
        self.assertEqual(pf["n"], 2)
        self.assertEqual(pf["avg"], 1.0)

        # FAC-1: facturada 2026-05-06, validada 2026-05-07 -> fv=1
        # FAC-2: sin validacion -> fv=None
        # FAC-3: facturada 2026-05-21, validada 2026-05-22 -> fv=1
        fv = etapas["Facturado → Validado"]
        self.assertEqual(fv["n"], 2)
        self.assertEqual(fv["avg"], 1.0)

        # FAC-1: validada 2026-05-07, asociada 2026-05-08 -> va=1
        # FAC-2, FAC-3: sin asociacion -> va=None
        va = etapas["Validado → Asociado"]
        self.assertEqual(va["n"], 1)
        self.assertEqual(va["avg"], 1.0)

        # FAC-1: aprobada 2026-05-05, asociada 2026-05-08 -> tot=3
        # FAC-2: sin asociacion. FAC-3: sin fecha_aprobacion.
        tot = etapas["Ciclo total"]
        self.assertEqual(tot["n"], 1)
        self.assertEqual(tot["avg"], 3.0)

        self.assertIn("temporal", ciclo)
        self.assertTrue(any(p["avg_tot"] is not None for p in ciclo["temporal"]))


    def test_duplicate_signal_fires_only_for_folio_collision_not_same_factura_id(self):
        """Duplicado por mismo factura_id (export Notion) no dispara señal; colisión de folio sí."""
        from rtb_analisis import build_facturacion_dashboard
        # Caso 1: mismo factura_id en principal y secundaria → NO señal
        pri = [{"Factura_id": "FAC-X", "Factura_cotizacion": "COT-X", "Factura_Estado_Aprobacion": "Aprobada",
                "Estado_Factura": "Factura enviada", "Fecha_Facturacion": '{"start":"2026-05-10"}',
                "#_Factura": "FX", "Total": "100", "Monto_primer_factura": ""}]
        sec = [{"Factura_id": "FAC-X", "Factura_cotizacion": "COT-X", "Factura_Estado_Aprobacion": "Aprobada",
                "Estado_Factura": "Factura enviada", "Fecha_Facturacion_Secundaria": '{"start":"2026-05-10"}',
                "#_Factura": "FX", "Total": "100", "Monto_segunda_factura": ""}]
        d = build_facturacion_dashboard([], pri, sec, fecha_desde="2026-05-01", fecha_hasta="2026-05-31")
        tipos = {s["tipo"] for s in d["signals"]}
        self.assertNotIn("factura_duplicada", tipos)
        # Caso 2: distinto factura_id pero mismo folio → SÍ señal (verdadero duplicado)
        pri2 = [
            {"Factura_id": "", "Factura_cotizacion": "COT-A", "Factura_Estado_Aprobacion": "Aprobada",
             "Estado_Factura": "Factura enviada", "Fecha_Facturacion": '{"start":"2026-05-10"}',
             "#_Factura": "FOLIO-REP", "Total": "200", "Monto_primer_factura": ""},
            {"Factura_id": "", "Factura_cotizacion": "COT-B", "Factura_Estado_Aprobacion": "Aprobada",
             "Estado_Factura": "Factura enviada", "Fecha_Facturacion": '{"start":"2026-05-11"}',
             "#_Factura": "FOLIO-REP", "Total": "300", "Monto_primer_factura": ""},
        ]
        d2 = build_facturacion_dashboard([], pri2, [], fecha_desde="2026-05-01", fecha_hasta="2026-05-31")
        tipos2 = {s["tipo"] for s in d2["signals"]}
        self.assertIn("factura_duplicada", tipos2)

    def test_factura_cancelada_field_does_not_mark_factura_as_cancelled(self):
        """Factura_Cancelada guarda el folio sustituido; la cancelacion real es por Estado_Aprobacion."""
        from rtb_analisis import build_facturacion_dashboard
        principales = [
            {"Factura_id": "FAC-R", "Factura_cotizacion": "COT-R", "Factura_Estado_Aprobacion": "Aprobada",
             "Estado_Factura": "Factura enviada", "Fecha_Facturacion": '{"start":"2026-05-10"}',
             "#_Factura": "F-R", "Total": "200", "Monto_primer_factura": "",
             "Factura_Cancelada": "F-ANTERIOR"},  # folio sustituido — no es cancelacion
        ]
        dashboard = build_facturacion_dashboard([], principales, [], fecha_desde="2026-05-01", fecha_hasta="2026-05-31")
        kpis = dashboard["kpis"]
        self.assertEqual(kpis["facturas_vigentes"], 1)
        self.assertEqual(kpis["monto_facturado_vigente"], 200.0)
        self.assertEqual(kpis["facturas_canceladas"], 0)

    def test_monto_primer_factura_zero_is_used_not_total(self):
        """Monto_primer_factura='0' no es nulo: monto debe ser 0.0, no Total."""
        from rtb_analisis import build_facturacion_dashboard
        principales = [
            {"Factura_id": "FAC-Z", "Factura_cotizacion": "COT-Z", "Factura_Estado_Aprobacion": "Aprobada",
             "Estado_Factura": "Factura enviada", "Fecha_Facturacion": '{"start":"2026-05-05"}',
             "#_Factura": "F-Z", "Total": "500", "Monto_primer_factura": "0"},
        ]
        dashboard = build_facturacion_dashboard([], principales, [], fecha_desde="2026-05-01", fecha_hasta="2026-05-31")
        self.assertEqual(dashboard["kpis"]["monto_facturado_vigente"], 0.0)

    def test_dirty_folio_triggers_signal_and_normalizes_folio(self):
        """Folio con notas embebidas ('C5888 / nota') emite señal y se normaliza a 'C5888'."""
        from rtb_analisis import build_facturacion_dashboard
        principales = [
            {"Factura_id": "FAC-D", "Factura_cotizacion": "COT-D", "Factura_Estado_Aprobacion": "Aprobada",
             "Estado_Factura": "Facturando", "Fecha_Facturacion": '{"start":"2026-05-15"}',
             "#_Factura": "C9001 / nota pendiente 50%", "Total": "300", "Monto_primer_factura": "150"},
        ]
        dashboard = build_facturacion_dashboard([], principales, [], fecha_desde="2026-05-01", fecha_hasta="2026-05-31")
        tipos = {s["tipo"] for s in dashboard["signals"]}
        self.assertIn("factura_folio_captura_sucia", tipos)
        folio_en_tabla = dashboard["tables"]["facturas"][0]["factura"]
        self.assertEqual(folio_en_tabla, "C9001")

    def test_segunda_factura_pendiente_signal(self):
        """Cuando Monto_primer_factura esta lleno y no hay secundaria, se emite segunda_factura_pendiente."""
        from rtb_analisis import build_facturacion_dashboard
        principales = [
            {"Factura_id": "FAC-P", "Factura_cotizacion": "COT-P", "Factura_Estado_Aprobacion": "Aprobada",
             "Estado_Factura": "Facturando", "Fecha_Facturacion": '{"start":"2026-05-20"}',
             "#_Factura": "C9002", "Total": "1000", "Monto_primer_factura": "400"},
        ]
        dashboard = build_facturacion_dashboard([], principales, [], fecha_desde="2026-05-01", fecha_hasta="2026-05-31")
        tipos = {s["tipo"] for s in dashboard["signals"]}
        self.assertIn("segunda_factura_pendiente", tipos)
        signal = next(s for s in dashboard["signals"] if s["tipo"] == "segunda_factura_pendiente")
        self.assertEqual(signal["metricas"]["cantidad"], 1)
        self.assertAlmostEqual(signal["metricas"]["monto_pendiente"], 600.0, places=2)
        self.assertEqual(dashboard["kpis"]["monto_facturado_vigente"], 400.0)

    def test_partidas_desbalanceadas_signal(self):
        """Cuando primer + segunda != Total (tol $0.05) se emite factura_partidas_desbalanceadas."""
        from rtb_analisis import build_facturacion_dashboard
        principales = [
            {"Factura_id": "FAC-B", "Factura_cotizacion": "COT-B", "Factura_Estado_Aprobacion": "Aprobada",
             "Estado_Factura": "Factura enviada", "Fecha_Facturacion": '{"start":"2026-05-10"}',
             "#_Factura": "C9003", "Total": "1000", "Monto_primer_factura": "400"},
        ]
        secundarias = [
            {"Factura_id": "FAC-B-S", "Factura_cotizacion": "COT-B", "Factura_Estado_Aprobacion": "Aprobada",
             "Estado_Factura": "Factura enviada", "Fecha_Facturacion_Secundaria": '{"start":"2026-05-15"}',
             "#_Factura": "C9004", "Total": "1000", "Monto_segunda_factura": "500"},  # 400+500=900 != 1000
        ]
        dashboard = build_facturacion_dashboard([], principales, secundarias, fecha_desde="2026-05-01", fecha_hasta="2026-05-31")
        tipos = {s["tipo"] for s in dashboard["signals"]}
        self.assertIn("factura_partidas_desbalanceadas", tipos)

    def test_monto_kpis_rounded_to_2_decimals(self):
        """monto_facturado_vigente y monto_cancelado se devuelven redondeados a 2 decimales."""
        from rtb_analisis import build_facturacion_dashboard
        principales = [
            {"Factura_id": "FAC-F", "Factura_cotizacion": "COT-F", "Factura_Estado_Aprobacion": "Aprobada",
             "Estado_Factura": "Factura enviada", "Fecha_Facturacion": '{"start":"2026-05-05"}',
             "#_Factura": "F-F", "Total": "100.123456789", "Monto_primer_factura": ""},
            {"Factura_id": "FAC-G", "Factura_cotizacion": "COT-G", "Factura_Estado_Aprobacion": "Cancelado",
             "Estado_Factura": "Cancelada", "Fecha_Facturacion": '{"start":"2026-05-06"}',
             "#_Factura": "F-G", "Total": "50.987654321", "Monto_primer_factura": ""},
        ]
        dashboard = build_facturacion_dashboard([], principales, [], fecha_desde="2026-05-01", fecha_hasta="2026-05-31")
        kpis = dashboard["kpis"]
        self.assertEqual(kpis["monto_facturado_vigente"], round(100.123456789, 2))
        self.assertEqual(kpis["monto_cancelado"], round(50.987654321, 2))
        self.assertEqual(kpis["facturas_canceladas"], 1)


class FindLatestFacturacionCsvTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _touch(self, name, delay=0):
        path = os.path.join(self.tmp, name)
        open(path, "w").close()
        if delay:
            time.sleep(delay)
        return path

    def test_ignora_anticipo_aunque_sea_mas_nuevo(self):
        """El archivo de anticipos tiene mtime mayor al principal — no debe ganar."""
        from rtb_analisis import find_latest_facturacion_csv
        self._touch("Facturas_2026-06-04_17-18.csv")
        time.sleep(0.05)
        self._touch("Facturas_Anticipo_2026-06-04_17-18.csv")
        result = find_latest_facturacion_csv(self.tmp, "Facturas_")
        self.assertEqual(result.name, "Facturas_2026-06-04_17-18.csv")

    def test_ignora_compras_y_secundarias(self):
        from rtb_analisis import find_latest_facturacion_csv
        self._touch("Facturas_2026-06-04_17-18.csv")
        time.sleep(0.05)
        self._touch("Facturas_Compras_2026-06-04_17-18.csv")
        self._touch("Facturas_Secundarias_2026-06-04_17-18.csv")
        result = find_latest_facturacion_csv(self.tmp, "Facturas_")
        self.assertEqual(result.name, "Facturas_2026-06-04_17-18.csv")

    def test_prefijo_secundarias_acepta_su_propio_patron(self):
        from rtb_analisis import find_latest_facturacion_csv
        self._touch("Facturas_Secundarias_2026-06-04_17-18.csv")
        result = find_latest_facturacion_csv(self.tmp, "Facturas_Secundarias_")
        self.assertEqual(result.name, "Facturas_Secundarias_2026-06-04_17-18.csv")

    def test_sin_archivo_lanza_error(self):
        from rtb_analisis import find_latest_facturacion_csv
        with self.assertRaises(FileNotFoundError):
            find_latest_facturacion_csv(self.tmp, "Facturas_")


if __name__ == "__main__":
    unittest.main()
