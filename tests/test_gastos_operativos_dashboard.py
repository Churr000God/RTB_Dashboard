import unittest
from rtb_analisis import build_gastos_operativos_dashboard, find_latest_gastos_operativos_csv, _RE_GASTOS_OP

PERIODO = {"fecha_desde": "2026-05-01", "fecha_hasta": "2026-05-31"}


def _gasto(**kw):
    """Factory para fila de Gastos_Operativos."""
    base = {
        "Gasto Operativo id": "go-test",
        "Gasto Operativo name": "GASTO TEST",
        "Gasto Operativo Subtotal": "862.069",
        "Gasto Operativo Iva": "137.931",
        "Gasto Operativo Total": "1000.00",
        "Gasto Operativo Fecha ": '{"start":"2026-05-15","end":null,"time_zone":null}',
        "Gasto Operativo Estado": "Realizado",
        "Gasto Operativo Factura": "FACT001",
        "Gasto Operativo Proveedor Nombre": "PROVEEDOR TEST",
        "Gasto Operativo Proveedor ID": "PROV-F-1",
        "Gasto Operativo Tipo de Pago": "Tarjeta",
        "Gasto Operativo Categoria": "Software",
        "Gasto Operativo Tarjeta ": "5218",
        "Gasto Operativo Deducible": "TRUE",
    }
    base.update(kw)
    return base


class TestAllowlistRegex(unittest.TestCase):

    def test_acepta_formato_valido(self):
        self.assertTrue(_RE_GASTOS_OP.match("Gastos_Operativos_2026-06-05_09-23.csv"))

    def test_rechaza_sin_timestamp(self):
        self.assertIsNone(_RE_GASTOS_OP.match("Gastos_Operativos.csv"))

    def test_rechaza_pagos_fc(self):
        self.assertIsNone(_RE_GASTOS_OP.match("Pagos_Facturas_Compras_2026-05-15_09-30.csv"))

    def test_rechaza_prefijo_similar(self):
        self.assertIsNone(_RE_GASTOS_OP.match("Gastos_2026-05-15_09-30.csv"))


class TestKpisBasicos(unittest.TestCase):

    def setUp(self):
        rows = [
            _gasto(**{"Gasto Operativo id": "a", "Gasto Operativo Total": "1000",
                      "Gasto Operativo Subtotal": "862.07", "Gasto Operativo Iva": "137.93",
                      "Gasto Operativo Deducible": "TRUE"}),
            _gasto(**{"Gasto Operativo id": "b", "Gasto Operativo Total": "500",
                      "Gasto Operativo Subtotal": "431.03", "Gasto Operativo Iva": "68.97",
                      "Gasto Operativo Deducible": "FALSE"}),
        ]
        self.result = build_gastos_operativos_dashboard(rows, period_label="mayo 2026", **PERIODO)
        self.kpis = self.result["kpis"]

    def test_total_total(self):
        self.assertAlmostEqual(self.kpis["total_total"], 1500.0, places=1)

    def test_monto_deducible(self):
        self.assertAlmostEqual(self.kpis["monto_deducible"], 1000.0, places=1)

    def test_monto_no_deducible(self):
        self.assertAlmostEqual(self.kpis["monto_no_deducible"], 500.0, places=1)

    def test_iva_acreditable(self):
        self.assertAlmostEqual(self.kpis["iva_acreditable"], 137.93, places=2)

    def test_iva_no_acreditable(self):
        self.assertAlmostEqual(self.kpis["iva_no_acreditable"], 68.97, places=2)

    def test_pct_deducible(self):
        self.assertAlmostEqual(self.kpis["pct_deducible"], 1000.0 / 1500.0, places=3)

    def test_n_gastos(self):
        self.assertEqual(self.kpis["n_gastos"], 2)

    def test_n_deducibles(self):
        self.assertEqual(self.kpis["n_deducibles"], 1)

    def test_n_no_deducibles(self):
        self.assertEqual(self.kpis["n_no_deducibles"], 1)


class TestRechazadosNoSumanTotales(unittest.TestCase):

    def test_rechazado_excluido_del_total(self):
        rows = [
            _gasto(**{"Gasto Operativo id": "ok", "Gasto Operativo Total": "1000",
                      "Gasto Operativo Estado": "Realizado"}),
            _gasto(**{"Gasto Operativo id": "bad", "Gasto Operativo Total": "9999",
                      "Gasto Operativo Estado": "Rechazado"}),
        ]
        result = build_gastos_operativos_dashboard(rows, **PERIODO)
        self.assertAlmostEqual(result["kpis"]["total_total"], 1000.0, places=1)
        self.assertEqual(result["kpis"]["n_rechazados"], 1)

    def test_rechazado_genera_senal(self):
        rows = [_gasto(**{"Gasto Operativo Estado": "Rechazado"})]
        result = build_gastos_operativos_dashboard(rows, **PERIODO)
        tipos = [s["tipo"] for s in result["signals"]]
        self.assertIn("gasto_rechazado", tipos)


class TestFiltradoPeriodo(unittest.TestCase):

    def test_excluye_fecha_fuera_de_rango(self):
        rows = [
            _gasto(**{"Gasto Operativo id": "dentro", "Gasto Operativo Total": "1000",
                      "Gasto Operativo Fecha ": '{"start":"2026-05-15","end":null,"time_zone":null}'}),
            _gasto(**{"Gasto Operativo id": "fuera", "Gasto Operativo Total": "9999",
                      "Gasto Operativo Fecha ": '{"start":"2026-04-01","end":null,"time_zone":null}'}),
        ]
        result = build_gastos_operativos_dashboard(rows, **PERIODO)
        self.assertEqual(result["kpis"]["n_gastos"], 1)
        self.assertAlmostEqual(result["kpis"]["total_total"], 1000.0, places=1)


class TestCategorizacion(unittest.TestCase):

    def test_categoria_en_series(self):
        rows = [
            _gasto(**{"Gasto Operativo Categoria": "Software", "Gasto Operativo Total": "500"}),
            _gasto(**{"Gasto Operativo Categoria": "Transporte / Combustible", "Gasto Operativo Total": "300"}),
            _gasto(**{"Gasto Operativo Categoria": "Software", "Gasto Operativo Total": "200"}),
        ]
        result = build_gastos_operativos_dashboard(rows, **PERIODO)
        cats = {s["categoria"]: s["m"] for s in result["series"]["categoria"]}
        self.assertAlmostEqual(cats["Software"], 700.0, places=1)
        self.assertAlmostEqual(cats["Transporte / Combustible"], 300.0, places=1)

    def test_categoria_vacia_se_llama_sin_categoria(self):
        rows = [_gasto(**{"Gasto Operativo Categoria": ""})]
        result = build_gastos_operativos_dashboard(rows, **PERIODO)
        cats = {s["categoria"] for s in result["series"]["categoria"]}
        self.assertIn("Sin categoria", cats)


class TestAgrupacionPorTarjeta(unittest.TestCase):

    def test_tarjeta_en_series(self):
        rows = [
            _gasto(**{"Gasto Operativo Tarjeta ": "5218", "Gasto Operativo Total": "400"}),
            _gasto(**{"Gasto Operativo Tarjeta ": "0079", "Gasto Operativo Total": "300"}),
            _gasto(**{"Gasto Operativo Tarjeta ": "5218", "Gasto Operativo Total": "100"}),
        ]
        result = build_gastos_operativos_dashboard(rows, **PERIODO)
        tar = {s["tarjeta"]: s["m"] for s in result["series"]["tarjeta"]}
        self.assertAlmostEqual(tar["5218"], 500.0, places=1)
        self.assertAlmostEqual(tar["0079"], 300.0, places=1)

    def test_tarjeta_vacia_se_llama_sin_tarjeta(self):
        rows = [_gasto(**{"Gasto Operativo Tarjeta ": ""})]
        result = build_gastos_operativos_dashboard(rows, **PERIODO)
        tars = {s["tarjeta"] for s in result["series"]["tarjeta"]}
        self.assertIn("Sin tarjeta", tars)


class TestSenalesCalidadCaptura(unittest.TestCase):

    def test_sin_factura_genera_senal(self):
        rows = [_gasto(**{"Gasto Operativo Factura": ""})]
        result = build_gastos_operativos_dashboard(rows, **PERIODO)
        tipos = [s["tipo"] for s in result["signals"]]
        self.assertIn("gasto_sin_factura", tipos)

    def test_sin_proveedor_genera_senal(self):
        rows = [_gasto(**{"Gasto Operativo Proveedor Nombre": ""})]
        result = build_gastos_operativos_dashboard(rows, **PERIODO)
        tipos = [s["tipo"] for s in result["signals"]]
        self.assertIn("gasto_sin_proveedor", tipos)

    def test_con_factura_no_genera_senal(self):
        rows = [_gasto()]  # tiene FACT001 por defecto
        result = build_gastos_operativos_dashboard(rows, **PERIODO)
        tipos = [s["tipo"] for s in result["signals"]]
        self.assertNotIn("gasto_sin_factura", tipos)


class TestDeducibleStringBoolean(unittest.TestCase):

    def test_true_string_reconocido(self):
        rows = [_gasto(**{"Gasto Operativo Deducible": "TRUE", "Gasto Operativo Total": "1000"})]
        result = build_gastos_operativos_dashboard(rows, **PERIODO)
        self.assertEqual(result["kpis"]["n_deducibles"], 1)
        self.assertEqual(result["kpis"]["n_no_deducibles"], 0)

    def test_false_string_reconocido(self):
        rows = [_gasto(**{"Gasto Operativo Deducible": "FALSE", "Gasto Operativo Total": "1000"})]
        result = build_gastos_operativos_dashboard(rows, **PERIODO)
        self.assertEqual(result["kpis"]["n_deducibles"], 0)
        self.assertEqual(result["kpis"]["n_no_deducibles"], 1)


class TestTablaDeduciblesSplit(unittest.TestCase):

    def test_split_tiene_dos_entradas(self):
        rows = [
            _gasto(**{"Gasto Operativo Deducible": "TRUE", "Gasto Operativo Total": "1000"}),
            _gasto(**{"Gasto Operativo Deducible": "FALSE", "Gasto Operativo Total": "500"}),
        ]
        result = build_gastos_operativos_dashboard(rows, **PERIODO)
        split = result["tables"]["deducibles_split"]
        self.assertEqual(len(split), 2)
        tipos = {row["tipo"] for row in split}
        self.assertIn("Deducible", tipos)
        self.assertIn("No deducible", tipos)


if __name__ == "__main__":
    unittest.main()
