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
        "Pedido Pago Cotizacion": "",
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
    """La clave del modulo: secundarias NO se suman al ingreso."""

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


def _cot(**kw):
    """Factory para fila de cotizacion."""
    base = {
        "Cotizacion_id": "cot-test-1",
        "Cotizacion_nombre": "COT-TEST",
        "Cliente": "CLIENTE_X",
        "Total": "5000",
        "Subtotal_con_envio_venta": "4310",
        "Estado_cotizacion": "Aprobada",
        "Estado_pago": '["No pagada"]',
        "Fecha_aprobacion": '{"start":"2026-05-10","end":null,"time_zone":null}',
        "Fecha_creacion": "2026-05-05",
        "PO": "",
    }
    base.update(kw)
    return base


class TestPendientesCobro(unittest.TestCase):

    def _build_with_cots(self, pp_ids, cot_ids, cot_pagada_ids=None):
        """pp_ids = IDs de cotizacion ya cobrados; cot_ids = todos los IDs de cotizacion en CSV."""
        pp = [_pp(**{"Pedido Pago ID": f"pp-{i}", "Pedido Pago Cotizacion": pid,
                     "Pedido Pago Total": "1000"})
              for i, pid in enumerate(pp_ids)]
        cots = [_cot(**{"Cotizacion_id": cid, "Total": "2000"}) for cid in cot_ids]
        if cot_pagada_ids:
            for c in cots:
                if c["Cotizacion_id"] in cot_pagada_ids:
                    c["Estado_pago"] = '["Pagada Total"]'
        return build_cobranza_dashboard(pp, [], cotizaciones=cots, **PERIODO)

    def test_kpi_pendientes_count(self):
        r = self._build_with_cots(["cot-A"], ["cot-A", "cot-B", "cot-C"])
        self.assertEqual(r["kpis"]["n_pendientes_cobro"], 2)

    def test_kpi_pendientes_monto(self):
        r = self._build_with_cots(["cot-A"], ["cot-A", "cot-B", "cot-C"])
        self.assertAlmostEqual(r["kpis"]["monto_pendiente_cobro"], 4000.0, places=2)

    def test_sin_cotizaciones_pendientes_cero(self):
        r = build_cobranza_dashboard([_pp()], [], **PERIODO)
        self.assertEqual(r["kpis"]["n_pendientes_cobro"], 0)
        self.assertAlmostEqual(r["kpis"]["monto_pendiente_cobro"], 0.0, places=2)

    def test_todas_cobradas_pendientes_cero(self):
        r = self._build_with_cots(["cot-A", "cot-B"], ["cot-A", "cot-B"])
        self.assertEqual(r["kpis"]["n_pendientes_cobro"], 0)

    def test_cotizacion_no_aprobada_excluida(self):
        pp = []
        cots = [
            _cot(**{"Cotizacion_id": "cot-APR", "Estado_cotizacion": "Aprobada"}),
            _cot(**{"Cotizacion_id": "cot-EXP", "Estado_cotizacion": "Expirada"}),
            _cot(**{"Cotizacion_id": "cot-COT", "Estado_cotizacion": "En Cotizacion"}),
        ]
        r = build_cobranza_dashboard(pp, [], cotizaciones=cots, **PERIODO)
        # Solo la Aprobada cuenta como pendiente
        self.assertEqual(r["kpis"]["n_pendientes_cobro"], 1)

    def test_tabla_pendientes_en_resultado(self):
        r = self._build_with_cots(["cot-A"], ["cot-A", "cot-B"])
        self.assertIn("pendientes", r["tables"])
        self.assertEqual(len(r["tables"]["pendientes"]), 1)
        self.assertEqual(r["tables"]["pendientes"][0]["cotizacion_id"], "cot-B")

    def test_tabla_pendientes_orden_monto_desc(self):
        pp = []
        cots = [
            _cot(**{"Cotizacion_id": "cot-1", "Total": "1000"}),
            _cot(**{"Cotizacion_id": "cot-2", "Total": "9000"}),
            _cot(**{"Cotizacion_id": "cot-3", "Total": "3000"}),
        ]
        r = build_cobranza_dashboard(pp, [], cotizaciones=cots, **PERIODO)
        montos = [x["monto"] for x in r["tables"]["pendientes"]]
        self.assertEqual(montos, sorted(montos, reverse=True))

    def test_pendientes_temporal_presente(self):
        r = self._build_with_cots([], ["cot-A", "cot-B"])
        self.assertIsNotNone(r["series"]["pendientes_temporal"])
        self.assertIn("granularidad", r["series"]["pendientes_temporal"])

    def test_pendientes_temporal_none_sin_cotizaciones(self):
        r = build_cobranza_dashboard([_pp()], [], **PERIODO)
        self.assertIsNone(r["series"]["pendientes_temporal"])

    def test_pagos_fuera_de_periodo_aun_marcan_cobrada(self):
        """Un cobro fuera del periodo analizado igual marca la cotizacion como cobrada."""
        pp = [_pp(**{
            "Pedido Pago Cotizacion": "cot-A",
            "Pedido Pago Fecha de pago ": "2026-04-01",  # fuera de PERIODO (mayo)
            "Pedido Pago Total": "5000",
        })]
        cots = [_cot(**{"Cotizacion_id": "cot-A"}), _cot(**{"Cotizacion_id": "cot-B"})]
        r = build_cobranza_dashboard(pp, [], cotizaciones=cots, **PERIODO)
        # cot-A esta pagada (aunque el cobro este fuera de periodo), cot-B pendiente
        self.assertEqual(r["kpis"]["n_pendientes_cobro"], 1)

    def test_pago_posterior_al_cierre_no_elimina_cartera_historica(self):
        pp = [_pp(**{
            "Pedido Pago Cotizacion": "cot-A",
            "Pedido Pago Fecha de pago ": "2026-06-10",
        })]
        cots = [_cot(**{"Cotizacion_id": "cot-A", "Fecha_aprobacion": "2026-05-10"})]
        r = build_cobranza_dashboard(pp, [], cotizaciones=cots, **PERIODO)
        self.assertEqual(r["kpis"]["n_pendientes_cobro"], 1)

    def test_aprobacion_posterior_al_cierre_no_entra_en_cartera(self):
        cots = [
            _cot(**{"Cotizacion_id": "cot-mayo", "Fecha_aprobacion": "2026-05-31"}),
            _cot(**{"Cotizacion_id": "cot-junio", "Fecha_aprobacion": "2026-06-01"}),
        ]
        r = build_cobranza_dashboard([], [], cotizaciones=cots, **PERIODO)
        self.assertEqual(r["kpis"]["n_pendientes_cobro"], 1)
        self.assertEqual(r["tables"]["pendientes"][0]["cotizacion_id"], "cot-mayo")

    def test_antiguedad_cartera_usa_fecha_de_cierre(self):
        cots = [
            _cot(**{"Cotizacion_id": "d30", "Fecha_aprobacion": "2026-05-01", "Total": "100"}),
            _cot(**{"Cotizacion_id": "d31", "Fecha_aprobacion": "2026-04-30", "Total": "200"}),
            _cot(**{"Cotizacion_id": "d60", "Fecha_aprobacion": "2026-04-01", "Total": "300"}),
            _cot(**{"Cotizacion_id": "d61", "Fecha_aprobacion": "2026-03-31", "Total": "400"}),
            _cot(**{"Cotizacion_id": "d90", "Fecha_aprobacion": "2026-03-02", "Total": "500"}),
            _cot(**{"Cotizacion_id": "d91", "Fecha_aprobacion": "2026-03-01", "Total": "600"}),
        ]
        r = build_cobranza_dashboard([], [], cotizaciones=cots, **PERIODO)
        buckets = {x["rango"]: x for x in r["series"]["cartera_antiguedad"]}
        self.assertEqual(buckets["0-30 dias"]["n"], 1)
        self.assertEqual(buckets["31-60 dias"]["n"], 2)
        self.assertEqual(buckets["61-90 dias"]["n"], 2)
        self.assertEqual(buckets[">90 dias"]["n"], 1)
        self.assertAlmostEqual(buckets[">90 dias"]["monto"], 600.0, places=2)

    def test_pendientes_ordenan_por_antiguedad_y_monto(self):
        cots = [
            _cot(**{"Cotizacion_id": "reciente", "Fecha_aprobacion": "2026-05-25", "Total": "9000"}),
            _cot(**{"Cotizacion_id": "viejo-menor", "Fecha_aprobacion": "2026-03-01", "Total": "1000"}),
            _cot(**{"Cotizacion_id": "viejo-mayor", "Fecha_aprobacion": "2026-03-01", "Total": "3000"}),
        ]
        r = build_cobranza_dashboard([], [], cotizaciones=cots, **PERIODO)
        self.assertEqual(
            [x["cotizacion_id"] for x in r["tables"]["pendientes"]],
            ["viejo-mayor", "viejo-menor", "reciente"],
        )
        self.assertEqual(r["tables"]["pendientes"][0]["rango_antiguedad"], ">90 dias")

    def test_cobertura_y_porcentaje_mayor_30_dias(self):
        pp = [
            _pp(**{"Pedido Pago ID": "rapido", "Pedido Pago Fecha de Asociacion": "2026-05-01", "Pedido Pago Fecha de pago ": "2026-05-11"}),
            _pp(**{"Pedido Pago ID": "lento", "Pedido Pago Fecha de Asociacion": "2026-03-01", "Pedido Pago Fecha de pago ": "2026-05-11"}),
            _pp(**{"Pedido Pago ID": "sin-fecha", "Pedido Pago Fecha de Asociacion": "", "Pedido Pago Fecha de pago ": "2026-05-11"}),
        ]
        r = build_cobranza_dashboard(pp, [], **PERIODO)
        self.assertAlmostEqual(r["kpis"]["cobertura_dias_cobro_pct"], 2 / 3, places=4)
        self.assertAlmostEqual(r["kpis"]["cobros_mayor_30_pct"], 1 / 2, places=4)

    def test_exposicion_cartera_sobre_cobrado(self):
        pp = [_pp(**{"Pedido Pago Cotizacion": "pagada", "Pedido Pago Total": "1000"})]
        cots = [_cot(**{"Cotizacion_id": "pendiente", "Total": "2500"})]
        r = build_cobranza_dashboard(pp, [], cotizaciones=cots, **PERIODO)
        self.assertAlmostEqual(r["kpis"]["exposicion_cartera_sobre_cobrado"], 2.5, places=4)

    def test_top_clientes_pendientes_presente(self):
        r = self._build_with_cots([], ["cot-A", "cot-B"])
        self.assertIn("top_clientes_pendientes", r["tables"])
        self.assertIsInstance(r["tables"]["top_clientes_pendientes"], list)

    def test_top_clientes_pendientes_agrega_por_cliente(self):
        pp = []
        cots = [
            _cot(**{"Cotizacion_id": "cot-1", "Cliente": "ACME", "Total": "3000"}),
            _cot(**{"Cotizacion_id": "cot-2", "Cliente": "ACME", "Total": "7000"}),
            _cot(**{"Cotizacion_id": "cot-3", "Cliente": "BETA", "Total": "1000"}),
        ]
        r = build_cobranza_dashboard(pp, [], cotizaciones=cots, **PERIODO)
        top = {d["cliente"]: d for d in r["tables"]["top_clientes_pendientes"]}
        self.assertAlmostEqual(top["ACME"]["m"], 10000.0, places=2)
        self.assertEqual(top["ACME"]["n"], 2)
        self.assertAlmostEqual(top["BETA"]["m"], 1000.0, places=2)

    def test_top_clientes_pendientes_orden_monto_desc(self):
        pp = []
        cots = [
            _cot(**{"Cotizacion_id": "cot-1", "Cliente": "C1", "Total": "500"}),
            _cot(**{"Cotizacion_id": "cot-2", "Cliente": "C2", "Total": "9000"}),
            _cot(**{"Cotizacion_id": "cot-3", "Cliente": "C3", "Total": "3000"}),
        ]
        r = build_cobranza_dashboard(pp, [], cotizaciones=cots, **PERIODO)
        montos = [d["m"] for d in r["tables"]["top_clientes_pendientes"]]
        self.assertEqual(montos, sorted(montos, reverse=True))

    def test_top_clientes_pendientes_trunca_a_10(self):
        pp = []
        cots = [
            _cot(**{"Cotizacion_id": f"cot-{i}", "Cliente": f"CLI_{i}", "Total": str(1000 + i)})
            for i in range(15)
        ]
        r = build_cobranza_dashboard(pp, [], cotizaciones=cots, **PERIODO)
        self.assertEqual(len(r["tables"]["top_clientes_pendientes"]), 10)

    def test_top_clientes_pendientes_vacio_sin_cotizaciones(self):
        r = build_cobranza_dashboard([_pp()], [], **PERIODO)
        self.assertEqual(r["tables"]["top_clientes_pendientes"], [])


if __name__ == "__main__":
    unittest.main()
