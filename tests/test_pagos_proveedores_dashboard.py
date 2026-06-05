import unittest
from rtb_analisis import build_pagos_proveedores_dashboard, find_latest_pagos_proveedores_csvs, _RE_PAGOS_FC, _RE_NOTAS_CREDITO

PERIODO = {"fecha_desde": "2026-05-01", "fecha_hasta": "2026-05-31"}


def _pago(**kw):
    """Factory para fila de Pagos_Facturas_Compras."""
    base = {
        "Pagos_Facturas_Compras_id": "pfc-test",
        "Pagos_Facturas_Compras_nombre": "PROV TEST - FAC001",
        "Pagos_Facturas_Compras_fecha_pago": '{"start":"2026-05-15","end":null,"time_zone":null}',
        "Pagos_Facturas_Compras_numero_factura": "FAC001",
        "Pagos_Facturas_Compras_tipo_compra": "Comercial",
        "Pagos_Facturas_Compras_tipo_pago": "3 Tranferencia",
        "Pagos_Facturas_Compras_estatus_pago": "Pagado",
        "Pagos_Facturas_Compras_nota_credito": "[]",
        "Pagos_Facturas_Compras_cantidad_pagada": "1000.00",
        "Pagos_Facturas_Compras_Nombre_proveedor": "PROVEEDOR A",
        "Pagos_Facturas_Compras_id_provedor": "PROV-F-1",
    }
    base.update(kw)
    return base


def _nc(**kw):
    """Factory para fila de Pago_Facturas_Nostas_Credito."""
    base = {
        "Pago_Facturas_Nostas_Credito_id": "nc-test",
        "Pago_Facturas_Nostas_Credito_nombre": "PROV NC - NCE001",
        "Pago_Facturas_Nostas_Credito_estado_pago": "Pagada",
        "Pago_Facturas_Nostas_Credito_proveedor_siglas": "PROV-F-10",
        "Pago_Facturas_Nostas_Credito_numero_documento": "NCE001",
        "Pago_Facturas_Nostas_Credito_proveedor_nombre": '["Grupo Test"]',
        "Pago_Facturas_Nostas_Credito_fecha_pago": '{"start":"2026-05-20","end":null,"time_zone":null}',
        "Pago_Facturas_Nostas_Credito_tipo_documeto": "Nota de Crédito",
        "Pago_Facturas_Nostas_Credito_tipo_pago": "Tarjeta de Debito",
        "Pago_Facturas_Nostas_Credito_factura_asociada": "pfc-otro",
        "Pago_Facturas_Nostas_Credito_tipo_cfdi": "G01",
        "Pago_Facturas_Nostas_Credito_total_pagado": "500.00",
    }
    base.update(kw)
    return base


class TestAllowlistRegex(unittest.TestCase):

    def test_acepta_pagos_fc_valido(self):
        self.assertTrue(_RE_PAGOS_FC.match("Pagos_Facturas_Compras_2026-05-15_09-30.csv"))

    def test_rechaza_pagos_fc_sin_timestamp(self):
        self.assertIsNone(_RE_PAGOS_FC.match("Pagos_Facturas_Compras.csv"))

    def test_rechaza_gastos_operativos_en_pagos_fc(self):
        self.assertIsNone(_RE_PAGOS_FC.match("Gastos_Operativos_2026-05-15_09-30.csv"))

    def test_acepta_notas_credito_valido(self):
        self.assertTrue(_RE_NOTAS_CREDITO.match("Pago_Facturas_Nostas_Credito_2026-06-05_10-39.csv"))

    def test_rechaza_notas_credito_sin_timestamp(self):
        self.assertIsNone(_RE_NOTAS_CREDITO.match("Pago_Facturas_Nostas_Credito.csv"))

    def test_rechaza_pagos_fc_en_notas_credito(self):
        self.assertIsNone(_RE_NOTAS_CREDITO.match("Pagos_Facturas_Compras_2026-05-15_09-30.csv"))


class TestKpisBasicos(unittest.TestCase):

    def setUp(self):
        pagos = [
            _pago(Pagos_Facturas_Compras_id="a", Pagos_Facturas_Compras_cantidad_pagada="2000"),
            _pago(Pagos_Facturas_Compras_id="b", Pagos_Facturas_Compras_cantidad_pagada="3000"),
        ]
        nc = [_nc(Pago_Facturas_Nostas_Credito_total_pagado="500")]
        self.result = build_pagos_proveedores_dashboard(pagos, nc, period_label="mayo 2026", **PERIODO)
        self.kpis = self.result["kpis"]

    def test_monto_fc(self):
        self.assertAlmostEqual(self.kpis["monto_fc"], 5000.0, places=2)

    def test_monto_nc(self):
        self.assertAlmostEqual(self.kpis["monto_nc"], 500.0, places=2)

    def test_monto_total(self):
        self.assertAlmostEqual(self.kpis["monto_total"], 5500.0, places=2)

    def test_n_pagados(self):
        self.assertEqual(self.kpis["n_pagados"], 2)

    def test_n_nc(self):
        self.assertEqual(self.kpis["n_nc"], 1)

    def test_n_pendientes_cero(self):
        self.assertEqual(self.kpis["n_pendientes"], 0)


class TestFiltradoPeriodo(unittest.TestCase):

    def test_excluye_fuera_de_rango(self):
        pagos = [
            _pago(Pagos_Facturas_Compras_id="dentro",
                  Pagos_Facturas_Compras_fecha_pago='{"start":"2026-05-15","end":null,"time_zone":null}',
                  Pagos_Facturas_Compras_cantidad_pagada="1000"),
            _pago(Pagos_Facturas_Compras_id="fuera",
                  Pagos_Facturas_Compras_fecha_pago='{"start":"2026-04-10","end":null,"time_zone":null}',
                  Pagos_Facturas_Compras_cantidad_pagada="9999"),
        ]
        result = build_pagos_proveedores_dashboard(pagos, [], **PERIODO)
        self.assertEqual(result["kpis"]["n_pagados"], 1)
        self.assertAlmostEqual(result["kpis"]["monto_fc"], 1000.0, places=2)


class TestNormalizacionTipoPago(unittest.TestCase):

    def test_transferencia(self):
        pagos = [_pago(Pagos_Facturas_Compras_tipo_pago="3 Tranferencia")]
        result = build_pagos_proveedores_dashboard(pagos, [], **PERIODO)
        tipos = {t["tipo"] for t in result["series"]["tipo_pago"]}
        self.assertIn("Transferencia", tipos)

    def test_tarjeta_debito(self):
        pagos = [_pago(Pagos_Facturas_Compras_tipo_pago="28 Tarjeta de debito")]
        result = build_pagos_proveedores_dashboard(pagos, [], **PERIODO)
        tipos = {t["tipo"] for t in result["series"]["tipo_pago"]}
        self.assertIn("Tarjeta de débito", tipos)

    def test_efectivo(self):
        pagos = [_pago(Pagos_Facturas_Compras_tipo_pago="1 Efectivo")]
        result = build_pagos_proveedores_dashboard(pagos, [], **PERIODO)
        tipos = {t["tipo"] for t in result["series"]["tipo_pago"]}
        self.assertIn("Efectivo", tipos)

    def test_por_definir(self):
        pagos = [_pago(Pagos_Facturas_Compras_tipo_pago="99 por definir")]
        result = build_pagos_proveedores_dashboard(pagos, [], **PERIODO)
        kpis = result["kpis"]
        self.assertEqual(kpis["n_por_definir"], 1)
        self.assertAlmostEqual(kpis["pct_por_definir"], 1.0, places=4)


class TestMontoNegativo(unittest.TestCase):
    """NC aplicada puede dar cantidad_pagada negativa o ~0."""

    def test_monto_negativo_suma_correctamente(self):
        # El código redondea cada monto a 2 decimales antes de sumar.
        # round(-0.0008, 2) = 0.0, así que monto_fc = 1000.0 + 0.0 = 1000.0
        pagos = [
            _pago(Pagos_Facturas_Compras_id="a", Pagos_Facturas_Compras_cantidad_pagada="1000"),
            _pago(Pagos_Facturas_Compras_id="b", Pagos_Facturas_Compras_cantidad_pagada="-0.0008",
                  Pagos_Facturas_Compras_nota_credito='["nc-001"]'),
        ]
        result = build_pagos_proveedores_dashboard(pagos, [], **PERIODO)
        self.assertAlmostEqual(result["kpis"]["monto_fc"], 1000.0, places=2)

    def test_nc_aplicada_genera_senal(self):
        pagos = [
            _pago(Pagos_Facturas_Compras_id="a", Pagos_Facturas_Compras_nota_credito='["nc-001"]'),
        ]
        result = build_pagos_proveedores_dashboard(pagos, [], **PERIODO)
        tipos_signal = [s["tipo"] for s in result["signals"]]
        self.assertIn("nc_aplicada", tipos_signal)


class TestPagoPendiente(unittest.TestCase):

    def test_pago_no_pagado_no_suma_al_total(self):
        pagos = [
            _pago(Pagos_Facturas_Compras_id="pag", Pagos_Facturas_Compras_cantidad_pagada="1000",
                  Pagos_Facturas_Compras_estatus_pago="Pagado"),
            _pago(Pagos_Facturas_Compras_id="pend", Pagos_Facturas_Compras_cantidad_pagada="9999",
                  Pagos_Facturas_Compras_estatus_pago="No Pagado"),
        ]
        result = build_pagos_proveedores_dashboard(pagos, [], **PERIODO)
        self.assertAlmostEqual(result["kpis"]["monto_fc"], 1000.0, places=2)
        self.assertEqual(result["kpis"]["n_pendientes"], 1)

    def test_pago_pendiente_genera_senal(self):
        pagos = [_pago(Pagos_Facturas_Compras_estatus_pago="No Pagado")]
        result = build_pagos_proveedores_dashboard(pagos, [], **PERIODO)
        tipos_signal = [s["tipo"] for s in result["signals"]]
        self.assertIn("pago_pendiente", tipos_signal)


class TestTablaNotasAnticipios(unittest.TestCase):

    def test_tabla_notas_contiene_todos_los_registros(self):
        nc = [_nc(), _nc(Pago_Facturas_Nostas_Credito_id="nc-2", Pago_Facturas_Nostas_Credito_total_pagado="300")]
        result = build_pagos_proveedores_dashboard([], nc, **PERIODO)
        self.assertEqual(len(result["tables"]["notas_anticipos"]), 2)

    def test_campos_de_nota(self):
        nc = [_nc()]
        result = build_pagos_proveedores_dashboard([], nc, **PERIODO)
        row = result["tables"]["notas_anticipos"][0]
        self.assertIn("tipo_doc", row)
        self.assertIn("monto", row)
        self.assertIn("factura_asociada", row)


if __name__ == "__main__":
    unittest.main()
