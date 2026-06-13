import os
import tempfile
import unittest

from rtb_analisis import (
    _RE_INVENTARIO,
    _RE_PART_VENTAS,
    build_inventario_dashboard,
    find_latest_inventario_csv,
    find_latest_partidas_ventas_csv,
)

PERIODO = {"fecha_desde": "2026-05-01", "fecha_hasta": "2026-05-31"}
PFX_INV = "Crecimineto_inventario_"
PFX_VTA = "Partidas_facturas_ventas_"


# ─── Factories de filas CSV ───────────────────────────────────────────────────

def _inv_row(**kw):
    base = {
        PFX_INV + "id":   "uuid-inv-001",
        PFX_INV + "name": "Inventario Mayo - 2026",
        PFX_INV + "tipo": "Inventario",
        PFX_INV + "monto": "500000.00",
        PFX_INV + "fecha_de_registro.start": "2026-05-31T00:00:00.000Z",
    }
    base.update(kw)
    return base


def _inv_sin_mov(**kw):
    base = {
        PFX_INV + "id":   "uuid-inv-002",
        PFX_INV + "name": "Inventario Mayo - 2026",
        PFX_INV + "tipo": "Productos sin movimiento",
        PFX_INV + "monto": "100000.00",
        PFX_INV + "fecha_de_registro.start": "2026-05-31T00:00:00.000Z",
    }
    base.update(kw)
    return base


def _vta(**kw):
    base = {
        PFX_VTA + "id":              "uuid-vta-001",
        PFX_VTA + "name":            "partida 1",
        PFX_VTA + "categoria_de_ganancias": "Materiales",
        PFX_VTA + "producto_sku":    "RTB-SKU-001",
        PFX_VTA + "subtotal":        "10000.00",
        PFX_VTA + "estado":          "Empacado",
        PFX_VTA + "cantidad_faltante": "0",
        PFX_VTA + "cantidad_solicitada": "10.0",
        PFX_VTA + "cotizaciones_a_clientes.0": "COT-001",
        PFX_VTA + "fecha_de_creaci_n": "2026-05-15T10:00:00.000Z",
        PFX_VTA + "costo_unitario_de_compra_formula": "750.00",
        PFX_VTA + "costo_unitario_v": "1000.00",
    }
    base.update(kw)
    return base


# ─── Regex allowlist ──────────────────────────────────────────────────────────

class TestInventarioRegex(unittest.TestCase):

    def test_inventario_acepta_patron_correcto(self):
        self.assertIsNotNone(_RE_INVENTARIO.match(
            "Crecimineto_inventario_2026-05-31_10-00.csv"
        ))

    def test_inventario_rechaza_sin_timestamp(self):
        self.assertIsNone(_RE_INVENTARIO.match("Crecimineto_inventario_2026-05.csv"))

    def test_inventario_rechaza_prefijo_diferente(self):
        self.assertIsNone(_RE_INVENTARIO.match("Inventario_2026-05-31_10-00.csv"))

    def test_part_ventas_acepta_patron_correcto(self):
        self.assertIsNotNone(_RE_PART_VENTAS.match(
            "Partidas_facturas_ventas_2026-05-31_10-00.csv"
        ))

    def test_part_ventas_rechaza_compras(self):
        self.assertIsNone(_RE_PART_VENTAS.match(
            "Partidas_facturas_compras_2026-05-31_10-00.csv"
        ))


class TestFindLatestInventario(unittest.TestCase):

    def test_encuentra_el_mas_reciente(self):
        with tempfile.TemporaryDirectory() as tmp:
            older = os.path.join(tmp, "Crecimineto_inventario_2026-04-30_08-00.csv")
            newer = os.path.join(tmp, "Crecimineto_inventario_2026-05-31_10-00.csv")
            for f in (older, newer):
                open(f, "w").close()
            p = find_latest_inventario_csv(tmp)
            self.assertEqual(p.name, "Crecimineto_inventario_2026-05-31_10-00.csv")

    def test_rechaza_nombre_invalido(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = os.path.join(tmp, "Crecimineto_inventario_2026-05.csv")
            open(bad, "w").close()
            with self.assertRaises(FileNotFoundError):
                find_latest_inventario_csv(tmp)

    def test_lanza_si_directorio_vacio(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                find_latest_inventario_csv(tmp)

    def test_find_partidas_ventas_encuentra(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = os.path.join(tmp, "Partidas_facturas_ventas_2026-05-31_10-00.csv")
            open(f, "w").close()
            p = find_latest_partidas_ventas_csv(tmp)
            self.assertEqual(p.name, "Partidas_facturas_ventas_2026-05-31_10-00.csv")


# ─── KPIs de snapshot de inventario ──────────────────────────────────────────

class TestInventarioKPIsSnapshot(unittest.TestCase):

    def setUp(self):
        self.inv = [_inv_row(), _inv_sin_mov()]
        self.vtas = [_vta()]

    def test_inv_total(self):
        r = build_inventario_dashboard(self.inv, self.vtas, **PERIODO)
        self.assertAlmostEqual(r["kpis"]["inv_total"], 500_000.0)

    def test_inv_sin_mov(self):
        r = build_inventario_dashboard(self.inv, self.vtas, **PERIODO)
        self.assertAlmostEqual(r["kpis"]["inv_sin_mov"], 100_000.0)

    def test_inv_activo(self):
        r = build_inventario_dashboard(self.inv, self.vtas, **PERIODO)
        self.assertAlmostEqual(r["kpis"]["inv_activo"], 400_000.0)

    def test_pct_inmov(self):
        r = build_inventario_dashboard(self.inv, self.vtas, **PERIODO)
        self.assertAlmostEqual(r["kpis"]["pct_inmov"], 0.20)

    def test_nombre_snapshot(self):
        r = build_inventario_dashboard(self.inv, self.vtas, **PERIODO)
        self.assertEqual(r["kpis"]["inv_nombre"], "Inventario Mayo - 2026")

    def test_n_snapshots(self):
        r = build_inventario_dashboard(self.inv, self.vtas, **PERIODO)
        self.assertEqual(r["kpis"]["n_snapshots"], 1)

    def test_sin_inventario_pct_cero(self):
        r = build_inventario_dashboard([], self.vtas, **PERIODO)
        self.assertEqual(r["kpis"]["pct_inmov"], 0.0)
        self.assertEqual(r["kpis"]["inv_total"], 0.0)


# ─── Margen bruto ─────────────────────────────────────────────────────────────
# margen = subtotal − costo_unitario_de_compra_formula × cantidad_solicitada
# = 10000 − 750 × 10 = 2500

class TestInventarioMargen(unittest.TestCase):

    def setUp(self):
        self.inv = [_inv_row(), _inv_sin_mov()]

    def test_margen_total(self):
        vtas = [_vta()]
        r = build_inventario_dashboard(self.inv, vtas, **PERIODO)
        self.assertAlmostEqual(r["kpis"]["margen_total"], 2500.0)

    def test_venta_total(self):
        vtas = [_vta()]
        r = build_inventario_dashboard(self.inv, vtas, **PERIODO)
        self.assertAlmostEqual(r["kpis"]["venta_total"], 10_000.0)

    def test_pct_margen(self):
        vtas = [_vta()]
        r = build_inventario_dashboard(self.inv, vtas, **PERIODO)
        self.assertAlmostEqual(r["kpis"]["pct_margen"], 0.25)

    def test_dos_partidas_acumulan(self):
        vtas = [_vta(), _vta(**{PFX_VTA + "producto_sku": "RTB-SKU-002",
                                PFX_VTA + "subtotal": "5000.00",
                                PFX_VTA + "cantidad_solicitada": "5.0",
                                PFX_VTA + "costo_unitario_de_compra_formula": "600.00"})]
        r = build_inventario_dashboard(self.inv, vtas, **PERIODO)
        # margen1=2500, margen2=5000-3000=2000 → 4500
        self.assertAlmostEqual(r["kpis"]["margen_total"], 4500.0)

    def test_top_margen_tabla(self):
        vtas = [_vta(), _vta(**{PFX_VTA + "producto_sku": "RTB-SKU-002",
                                PFX_VTA + "subtotal": "20000.00",
                                PFX_VTA + "cantidad_solicitada": "20.0",
                                PFX_VTA + "costo_unitario_de_compra_formula": "500.00"})]
        r = build_inventario_dashboard(self.inv, vtas, **PERIODO)
        top = r["tables"]["top_margen"]
        # SKU-002 tiene margen 20000 - 10000 = 10000 → primero
        self.assertEqual(top[0]["sku"], "RTB-SKU-002")
        self.assertAlmostEqual(top[0]["margen"], 10_000.0)

    def test_top_pedidos_margen(self):
        vtas = [_vta(), _vta(**{PFX_VTA + "cotizaciones_a_clientes.0": "COT-002",
                                PFX_VTA + "subtotal": "50000.00",
                                PFX_VTA + "cantidad_solicitada": "50.0",
                                PFX_VTA + "costo_unitario_de_compra_formula": "600.00"})]
        r = build_inventario_dashboard(self.inv, vtas, **PERIODO)
        top = r["tables"]["top_pedidos_margen"]
        self.assertEqual(top[0]["cotizacion"], "COT-002")


# ─── Filtro de periodo ────────────────────────────────────────────────────────

class TestInventarioPeriodo(unittest.TestCase):

    def setUp(self):
        self.inv = [_inv_row(), _inv_sin_mov()]

    def test_excluye_fuera_de_periodo(self):
        vtas_fuera = [_vta(**{PFX_VTA + "fecha_de_creaci_n": "2026-07-01T10:00:00.000Z"})]
        r = build_inventario_dashboard(self.inv, vtas_fuera, **PERIODO)
        self.assertEqual(r["kpis"]["n_partidas"], 0)
        self.assertAlmostEqual(r["kpis"]["venta_total"], 0.0)

    def test_incluye_dia_inicio(self):
        vtas = [_vta(**{PFX_VTA + "fecha_de_creaci_n": "2026-05-01T00:00:00.000Z"})]
        r = build_inventario_dashboard(self.inv, vtas, **PERIODO)
        self.assertEqual(r["kpis"]["n_partidas"], 1)

    def test_incluye_dia_fin(self):
        vtas = [_vta(**{PFX_VTA + "fecha_de_creaci_n": "2026-05-31T23:59:59.000Z"})]
        r = build_inventario_dashboard(self.inv, vtas, **PERIODO)
        self.assertEqual(r["kpis"]["n_partidas"], 1)


# ─── Señales ──────────────────────────────────────────────────────────────────

class TestInventarioSenales(unittest.TestCase):

    def setUp(self):
        self.vtas = [_vta()]

    def test_senal_inmovilizado_alto_al_superar_30pct(self):
        # sin_mov / total = 160000/500000 = 32% > 30%
        inv = [_inv_row(), _inv_sin_mov(**{PFX_INV + "monto": "160000.00"})]
        r = build_inventario_dashboard(inv, self.vtas, **PERIODO)
        tipos = [s["tipo"] for s in r["signals"]]
        self.assertIn("inventario_alto_inmovilizado", tipos)

    def test_sin_senal_inmovilizado_bajo_30pct(self):
        inv = [_inv_row(), _inv_sin_mov()]   # 20% < 30%
        r = build_inventario_dashboard(inv, self.vtas, **PERIODO)
        tipos = [s["tipo"] for s in r["signals"]]
        self.assertNotIn("inventario_alto_inmovilizado", tipos)

    def test_senal_costo_compra_cero(self):
        # costo_unitario_de_compra_formula = 0 y subtotal > 0
        vtas = [_vta(**{PFX_VTA + "costo_unitario_de_compra_formula": "0"})]
        inv = [_inv_row(), _inv_sin_mov()]
        r = build_inventario_dashboard(inv, vtas, **PERIODO)
        tipos = [s["tipo"] for s in r["signals"]]
        self.assertIn("costo_compra_cero", tipos)

    def test_senal_margen_negativo(self):
        # costo 1200 * 10 = 12000 > subtotal 10000 → margen −2000
        vtas = [_vta(**{PFX_VTA + "costo_unitario_de_compra_formula": "1200.00"})]
        inv = [_inv_row(), _inv_sin_mov()]
        r = build_inventario_dashboard(inv, vtas, **PERIODO)
        tipos = [s["tipo"] for s in r["signals"]]
        self.assertIn("margen_negativo", tipos)

    def test_no_senal_si_datos_limpios(self):
        inv = [_inv_row(), _inv_sin_mov()]  # 20% inmovilizado
        r = build_inventario_dashboard(inv, self.vtas, **PERIODO)
        # sin_costo=0, sin margen_neg, sin inmov>30%
        self.assertEqual(r["kpis"]["n_sin_costo"], 0)
        self.assertEqual(r["kpis"]["n_margen_neg"], 0)


# ─── Series temporales ────────────────────────────────────────────────────────

class TestInventarioSeries(unittest.TestCase):

    def test_serie_inventario_mensual_existe(self):
        inv = [_inv_row(), _inv_sin_mov()]
        vtas = [_vta()]
        r = build_inventario_dashboard(inv, vtas, **PERIODO)
        series_inv = r["series"]["inventario_mensual"]
        self.assertGreaterEqual(len(series_inv), 1)
        self.assertIn("total", series_inv[0])
        self.assertIn("sin_mov", series_inv[0])
        self.assertIn("activo", series_inv[0])

    def test_tendencias_calculadas(self):
        inv = [_inv_row(), _inv_sin_mov()]
        vtas = [_vta()]
        r = build_inventario_dashboard(inv, vtas, **PERIODO)
        tend = r["series"]["temporal_margen"]["tendencias"]
        self.assertIn("margen", tend)
        self.assertIn("venta", tend)

    def test_dos_snapshots_producen_dos_puntos(self):
        inv = [
            _inv_row(**{PFX_INV + "name": "Inventario Abril - 2026"}),
            _inv_sin_mov(**{PFX_INV + "name": "Inventario Abril - 2026",
                            PFX_INV + "monto": "80000.00"}),
            _inv_row(**{PFX_INV + "name": "Inventario Mayo - 2026",
                        PFX_INV + "monto": "550000.00"}),
            _inv_sin_mov(**{PFX_INV + "name": "Inventario Mayo - 2026",
                            PFX_INV + "monto": "110000.00"}),
        ]
        vtas = [_vta()]
        r = build_inventario_dashboard(inv, vtas, **PERIODO)
        self.assertEqual(len(r["series"]["inventario_mensual"]), 2)


if __name__ == "__main__":
    unittest.main()
