import json
import unittest
from rtb_analisis import build_cobranza_dashboard

PERIODO = {"fecha_desde": "2026-05-01", "fecha_hasta": "2026-05-31"}


def _pp(**kw):
    """Factory para fila de Pagos_Principlaes_Facturas_Ventas."""
    base = {
        "Pedido Pago ID": "pp-test",
        "Pedido Pago Nombre": "PP-TEST-1",
        "Pedido Pago Subtotal": "1000",
        "Pedido Pago Total": "1160",
        "Pedido Estatus de pago": "Pagada Total",
        "Pedido Pago Fecha de Asociacion": "",
        "Pedido Pago # de Factura": "C5000",
        "Pedido Pago Estado de pedido": "Aprobada",
        "Pedido Pago Fecha de pago ": '{"start":"2026-05-15","end":null,"time_zone":null}',
        "Pedido Pago Monto pagado ": "",
        "Pedido Pago Cliente": "CLIENTE_A",
        "Pedido Pago Complemento de pago": "",
        "Pedido Pago PO": "",
        "Pedido Pago Fecha de aprobacion": "",
        "Pedido Pago Tipo de pago": "Transferencia",
    }
    base.update(kw)
    return base


def _ps(**kw):
    """Factory para fila de Pagos_Secundarias_Facturas_Ventas."""
    base = {
        "Pedido Pago ID": "ps-test",
        "Pedido Pago Nombre": "PP-TEST-SEC",
        "Pedido Pago Subtotal": "1000",
        "Pedido Pago Total": "1160",
        "Pedido Estatus de pago": "Pagada Total",
        "Pedido Pago Fecha de Asociacion": "",
        "Pedido Pago # de Factura": "C5000 / C5001",
        "Pedido Pago Estado de pedido": "Aprobada",
        "Pedido Pago Fecha de pago Secundaria": '{"start":"2026-05-20","end":null,"time_zone":null}',
        "Pedido Pago Monto pagado Secundaria": "",
        "Pedido Pago Cliente": "CLIENTE_B",
        "Pedido Pago Complemento de pago": "",
        "Pedido Pago PO": "",
        "Pedido Pago Fecha de aprobacion": "",
        "Pedido Pago Tipo de pago": "Credito",
    }
    base.update(kw)
    return base


class TestBuildCobranzaKpisBasicos(unittest.TestCase):

    def setUp(self):
        pp = [
            _pp(**{"Pedido Pago ID": "a", "Pedido Pago Total": "1000"}),
            _pp(**{"Pedido Pago ID": "b", "Pedido Pago Total": "2000"}),
            _pp(**{"Pedido Pago ID": "c", "Pedido Pago Total": "500"}),
        ]
        self.result = build_cobranza_dashboard(pp, [], **PERIODO)
        self.kpis = self.result["kpis"]

    def test_cobros_principales(self):
        self.assertEqual(self.kpis["cobros_principales"], 3)

    def test_monto_cobrado_total(self):
        self.assertAlmostEqual(self.kpis["monto_cobrado_total"], 3500.0, places=2)

    def test_cobros_secundarias_cero(self):
        self.assertEqual(self.kpis["cobros_secundarias"], 0)

    def test_cobros_total(self):
        self.assertEqual(self.kpis["cobros_total"], 3)

    def test_ticket_promedio(self):
        self.assertAlmostEqual(self.kpis["ticket_promedio"], 3500.0 / 3, places=1)


class TestSecundariasNoSumanMonto(unittest.TestCase):
    """La clave del módulo: secundarias NO se suman al ingreso."""

    def setUp(self):
        pp = [_pp(**{"Pedido Pago Total": "1000"})]
        ps = [_ps(**{"Pedido Pago Total": "5000"})]
        self.result = build_cobranza_dashboard(pp, ps, **PERIODO)
        self.kpis = self.result["kpis"]

    def test_monto_solo_principales(self):
        self.assertAlmostEqual(self.kpis["monto_cobrado_total"], 1000.0, places=2)

    def test_secundaria_referencial(self):
        self.assertAlmostEqual(self.kpis["monto_secundarias_referencial"], 5000.0, places=2)

    def test_cobros_total_incluye_secundaria(self):
        self.assertEqual(self.kpis["cobros_total"], 2)

    def test_cobros_secundarias_count(self):
        self.assertEqual(self.kpis["cobros_secundarias"], 1)


class TestFechasParseo(unittest.TestCase):

    def test_fecha_json_notion_parseada(self):
        """parse_date maneja el JSON de Notion en Fecha de pago."""
        pp = [_pp(**{"Pedido Pago Fecha de pago ": '{"start":"2026-05-26","end":null,"time_zone":null}'})]
        r = build_cobranza_dashboard(pp, [], **PERIODO)
        self.assertEqual(r["kpis"]["cobros_principales"], 1)
        cobro = r["tables"]["cobros"][0]
        self.assertEqual(cobro["fecha_pago"], "2026-05-26")

    def test_fecha_iso_directa_parseada(self):
        pp = [_pp(**{"Pedido Pago Fecha de pago ": "2026-05-10"})]
        r = build_cobranza_dashboard(pp, [], **PERIODO)
        self.assertEqual(r["kpis"]["cobros_principales"], 1)


class TestFiltroPeriodo(unittest.TestCase):

    def test_pago_fuera_de_periodo_excluido(self):
        pp = [
            _pp(**{"Pedido Pago Total": "1000", "Pedido Pago Fecha de pago ": "2026-04-15"}),
            _pp(**{"Pedido Pago Total": "500", "Pedido Pago Fecha de pago ": "2026-05-10"}),
        ]
        r = build_cobranza_dashboard(pp, [], **PERIODO)
        self.assertEqual(r["kpis"]["cobros_principales"], 1)
        self.assertAlmostEqual(r["kpis"]["monto_cobrado_total"], 500.0, places=2)

    def test_secundaria_fuera_de_periodo_excluida(self):
        ps = [_ps(**{"Pedido Pago Fecha de pago Secundaria": "2026-04-01"})]
        r = build_cobranza_dashboard([], ps, **PERIODO)
        self.assertEqual(r["kpis"]["cobros_secundarias"], 0)


class TestDiasCobranza(unittest.TestCase):

    def test_lag_calculado_correctamente(self):
        pp = [_pp(**{
            "Pedido Pago Fecha de Asociacion": '{"start":"2026-02-25","end":null,"time_zone":null}',
            "Pedido Pago Fecha de pago ": '{"start":"2026-05-26","end":null,"time_zone":null}',
        })]
        r = build_cobranza_dashboard(pp, [], **PERIODO)
        self.assertEqual(r["kpis"]["n_con_lag"], 1)
        cobro = r["tables"]["cobros"][0]
        self.assertGreater(cobro["dias_cobro"], 85)

    def test_sin_fecha_asociacion_no_cuenta_lag(self):
        pp = [_pp(**{"Pedido Pago Fecha de Asociacion": ""})]
        r = build_cobranza_dashboard(pp, [], **PERIODO)
        self.assertEqual(r["kpis"]["n_con_lag"], 0)
        self.assertEqual(r["kpis"]["dias_cobro_promedio"], 0.0)


class TestTopClientes(unittest.TestCase):

    def test_top_clientes_solo_principales(self):
        """Secundarias no deben inflar el ranking de clientes."""
        pp = [
            _pp(**{"Pedido Pago Cliente": "ALFA", "Pedido Pago Total": "3000"}),
            _pp(**{"Pedido Pago Cliente": "ALFA", "Pedido Pago Total": "2000"}),
            _pp(**{"Pedido Pago Cliente": "BETA", "Pedido Pago Total": "1000"}),
        ]
        ps = [_ps(**{"Pedido Pago Cliente": "ALFA", "Pedido Pago Total": "9999"})]
        r = build_cobranza_dashboard(pp, ps, **PERIODO)
        cli = {c["cliente"]: c["m"] for c in r["tables"]["top_clientes"]}
        self.assertAlmostEqual(cli["ALFA"], 5000.0, places=2)
        self.assertAlmostEqual(cli["BETA"], 1000.0, places=2)

    def test_top_clientes_orden_descendente(self):
        pp = [
            _pp(**{"Pedido Pago Cliente": "CHICO", "Pedido Pago Total": "100"}),
            _pp(**{"Pedido Pago Cliente": "GRANDE", "Pedido Pago Total": "9000"}),
        ]
        r = build_cobranza_dashboard(pp, [], **PERIODO)
        self.assertEqual(r["tables"]["top_clientes"][0]["cliente"], "GRANDE")


class TestTipoPago(unittest.TestCase):

    def test_distribucion_tipo_pago(self):
        pp = [
            _pp(**{"Pedido Pago Tipo de pago": "Transferencia", "Pedido Pago Total": "2000"}),
            _pp(**{"Pedido Pago Tipo de pago": "Transferencia", "Pedido Pago Total": "3000"}),
            _pp(**{"Pedido Pago Tipo de pago": "Efectivo", "Pedido Pago Total": "500"}),
        ]
        r = build_cobranza_dashboard(pp, [], **PERIODO)
        tp = {x["tipo"]: x for x in r["series"]["tipo_pago"]}
        self.assertEqual(tp["Transferencia"]["n"], 2)
        self.assertAlmostEqual(tp["Transferencia"]["m"], 5000.0, places=2)
        self.assertEqual(tp["Efectivo"]["n"], 1)
        self.assertAlmostEqual(tp["Efectivo"]["m"], 500.0, places=2)


class TestSenales(unittest.TestCase):

    def test_senal_cobro_sin_cliente(self):
        pp = [_pp(**{"Pedido Pago Cliente": ""})]
        r = build_cobranza_dashboard(pp, [], **PERIODO)
        tipos = [s["tipo"] for s in r["signals"]]
        self.assertIn("cobro_sin_cliente", tipos)
        self.assertEqual(r["kpis"]["cobros_sin_cliente"], 1)

    def test_senal_folio_sucio(self):
        pp = [_pp(**{"Pedido Pago # de Factura": "C5533 / C5633"})]
        r = build_cobranza_dashboard(pp, [], **PERIODO)
        tipos = [s["tipo"] for s in r["signals"]]
        self.assertIn("factura_folio_sucio", tipos)
        cobro = r["tables"]["cobros"][0]
        self.assertEqual(cobro["factura"], "C5533")

    def test_senal_cobro_sin_fecha_asociacion(self):
        pp = [_pp(**{"Pedido Pago Fecha de Asociacion": ""})]
        r = build_cobranza_dashboard(pp, [], **PERIODO)
        tipos = [s["tipo"] for s in r["signals"]]
        self.assertIn("cobro_sin_fecha_asociacion", tipos)
        self.assertEqual(r["kpis"]["cobros_sin_fecha_asociacion"], 1)

    def test_senal_monto_secundaria_no_capturado(self):
        ps = [_ps(**{"Pedido Pago Monto pagado Secundaria": ""})]
        r = build_cobranza_dashboard([], ps, **PERIODO)
        tipos = [s["tipo"] for s in r["signals"]]
        self.assertIn("monto_secundaria_no_capturado", tipos)

    def test_senal_cobranza_lenta_si_mediana_mayor_30(self):
        # Forzar lag alto con fecha_asociacion muy anterior
        pp = [
            _pp(**{
                "Pedido Pago Fecha de Asociacion": "2026-01-01",
                "Pedido Pago Fecha de pago ": "2026-05-15",
            })
        ]
        r = build_cobranza_dashboard(pp, [], **PERIODO)
        tipos = [s["tipo"] for s in r["signals"]]
        self.assertIn("cobranza_lenta", tipos)

    def test_no_senal_folio_limpio(self):
        pp = [_pp(**{"Pedido Pago # de Factura": "C5100"})]
        r = build_cobranza_dashboard(pp, [], **PERIODO)
        tipos = [s["tipo"] for s in r["signals"]]
        self.assertNotIn("factura_folio_sucio", tipos)


class TestGranularidadTemporal(unittest.TestCase):

    def test_cross_month_produces_granularidad_mes(self):
        pp = [
            _pp(**{"Pedido Pago Fecha de pago ": "2026-04-15", "Pedido Pago Total": "1000"}),
            _pp(**{"Pedido Pago Fecha de pago ": "2026-05-10", "Pedido Pago Total": "2000"}),
        ]
        r = build_cobranza_dashboard(pp, [], fecha_desde="2026-04-01", fecha_hasta="2026-05-31")
        self.assertEqual(r["series"]["temporal"]["granularidad"], "mes")

    def test_same_month_produces_granularidad_semana(self):
        pp = [_pp(**{"Pedido Pago Fecha de pago ": "2026-05-10"})]
        r = build_cobranza_dashboard(pp, [], **PERIODO)
        self.assertEqual(r["series"]["temporal"]["granularidad"], "semana")


class TestInvariantes(unittest.TestCase):

    def test_monto_total_es_suma_de_principales(self):
        pp = [
            _pp(**{"Pedido Pago Total": "1000"}),
            _pp(**{"Pedido Pago Total": "2000"}),
            _pp(**{"Pedido Pago Total": "3000"}),
        ]
        ps = [_ps(**{"Pedido Pago Total": "9999"})]
        r = build_cobranza_dashboard(pp, ps, **PERIODO)
        # Solo los cobros principales tienen monto != None
        esperado = sum(c["monto"] for c in r["tables"]["cobros"] if c["tipo"] == "principal")
        self.assertAlmostEqual(r["kpis"]["monto_cobrado_total"], esperado, places=2)

    def test_secundarias_vacias_no_rompe(self):
        pp = [_pp()]
        r = build_cobranza_dashboard(pp, [], **PERIODO)
        self.assertIn("kpis", r)
        self.assertEqual(r["kpis"]["cobros_secundarias"], 0)

    def test_ambas_listas_vacias(self):
        r = build_cobranza_dashboard([], [], **PERIODO)
        self.assertEqual(r["kpis"]["cobros_total"], 0)
        self.assertAlmostEqual(r["kpis"]["monto_cobrado_total"], 0.0, places=2)


if __name__ == "__main__":
    unittest.main()
