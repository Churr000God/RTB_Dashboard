import os
import tempfile
import unittest

from rtb_analisis import (
    _RE_PART_COMPRAS,
    build_almacen_dashboard,
    find_latest_partidas_compras_csv,
)

PERIODO = {"fecha_desde": "2026-05-01", "fecha_hasta": "2026-05-31"}
VFX = "Partidas_facturas_ventas_"
CFX = "partida_"


# ─── Factories de filas CSV ───────────────────────────────────────────────────

def _vta(**kw):
    base = {
        VFX + "id":              "uuid-vta-001",
        VFX + "name":            "partida 1",
        VFX + "categoria_de_ganancias": "Materiales",
        VFX + "producto_sku":    "RTB-SKU-001",
        VFX + "subtotal":        "10000.00",
        VFX + "estado":          "Empacado",
        VFX + "cantidad_faltante": "0",
        VFX + "cantidad_solicitada": "10.0",
        VFX + "cotizaciones_a_clientes.0": "COT-001",
        VFX + "fecha_de_creaci_n": "2026-05-15T10:00:00.000Z",
        VFX + "costo_unitario_de_compra_formula": "750.00",
        VFX + "costo_unitario_v": "1000.00",
    }
    base.update(kw)
    return base


def _cmp(**kw):
    base = {
        CFX + "id":                    "uuid-cmp-001",
        CFX + "name":                  "1",
        CFX + "fecha_creacion":        "2026-05-10T00:00:00.000Z",
        CFX + "validacion_fisica":     "TRUE",
        CFX + "id_producto.0":         "uuid-prod-001",
        CFX + "cantidad_llegada":      "10",
        CFX + "codigo_producto.0":     "RTB-SKU-001",
        CFX + "cantidad_solicitada":   "10",
        CFX + "cotizacion.0":          "uuid-fc-001",
        CFX + "producto_codigo_gestion_inventario.0": "uuid-gi-001",
    }
    base.update(kw)
    return base


# ─── Regex allowlist ──────────────────────────────────────────────────────────

class TestPartComprasRegex(unittest.TestCase):

    def test_acepta_patron_correcto(self):
        self.assertIsNotNone(_RE_PART_COMPRAS.match(
            "Partidas_facturas_compras_2026-05-31_10-00.csv"
        ))

    def test_rechaza_sin_timestamp(self):
        self.assertIsNone(_RE_PART_COMPRAS.match("Partidas_facturas_compras_2026-05.csv"))

    def test_rechaza_ventas(self):
        self.assertIsNone(_RE_PART_COMPRAS.match(
            "Partidas_facturas_ventas_2026-05-31_10-00.csv"
        ))

    def test_rechaza_prefijo_libre(self):
        self.assertIsNone(_RE_PART_COMPRAS.match("compras_2026-05-31_10-00.csv"))


class TestFindLatestPartCompras(unittest.TestCase):

    def test_encuentra_el_mas_reciente(self):
        with tempfile.TemporaryDirectory() as tmp:
            older = os.path.join(tmp, "Partidas_facturas_compras_2026-04-30_08-00.csv")
            newer = os.path.join(tmp, "Partidas_facturas_compras_2026-05-31_10-00.csv")
            for f in (older, newer):
                open(f, "w").close()
            p = find_latest_partidas_compras_csv(tmp)
            self.assertEqual(p.name, "Partidas_facturas_compras_2026-05-31_10-00.csv")

    def test_lanza_si_no_hay_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                find_latest_partidas_compras_csv(tmp)

    def test_rechaza_nombre_invalido(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = os.path.join(tmp, "Partidas_facturas_compras_2026-05.csv")
            open(bad, "w").close()
            with self.assertRaises(FileNotFoundError):
                find_latest_partidas_compras_csv(tmp)


# ─── KPIs de surtido de ventas ───────────────────────────────────────────────

class TestAlmacenSurtidoKPIs(unittest.TestCase):

    def setUp(self):
        self.cmp = [_cmp()]

    def test_n_empacado(self):
        vtas = [_vta(), _vta(**{VFX + "estado": "Empacado", VFX + "id": "u2"})]
        r = build_almacen_dashboard(self.cmp, vtas, **PERIODO)
        self.assertEqual(r["kpis"]["n_empacado"], 2)

    def test_n_pendiente(self):
        vtas = [_vta(**{VFX + "estado": "Pendiente"})]
        r = build_almacen_dashboard(self.cmp, vtas, **PERIODO)
        self.assertEqual(r["kpis"]["n_pendiente"], 1)
        self.assertEqual(r["kpis"]["n_empacado"], 0)

    def test_n_faltante(self):
        vtas = [_vta(**{VFX + "estado": "Faltante",
                        VFX + "cantidad_faltante": "3"})]
        r = build_almacen_dashboard(self.cmp, vtas, **PERIODO)
        self.assertEqual(r["kpis"]["n_faltante"], 1)

    def test_sub_empacado(self):
        vtas = [_vta(), _vta(**{VFX + "id": "u2", VFX + "subtotal": "5000.00"})]
        r = build_almacen_dashboard(self.cmp, vtas, **PERIODO)
        self.assertAlmostEqual(r["kpis"]["sub_empacado"], 15_000.0)

    def test_pct_empacado(self):
        vtas = [_vta(), _vta(**{VFX + "estado": "Pendiente", VFX + "id": "u2"})]
        r = build_almacen_dashboard(self.cmp, vtas, **PERIODO)
        # 1 empacado de 2 = 50%
        self.assertAlmostEqual(r["kpis"]["pct_empacado"], 0.50)

    def test_sub_total_vta(self):
        vtas = [_vta(), _vta(**{VFX + "estado": "Faltante", VFX + "id": "u2",
                                VFX + "subtotal": "3000.00"})]
        r = build_almacen_dashboard(self.cmp, vtas, **PERIODO)
        self.assertAlmostEqual(r["kpis"]["sub_total_vta"], 13_000.0)

    def test_sin_partidas_todo_cero(self):
        r = build_almacen_dashboard(self.cmp, [], **PERIODO)
        self.assertEqual(r["kpis"]["n_partidas_vta"], 0)
        self.assertAlmostEqual(r["kpis"]["pct_empacado"], 0.0)


# ─── Filtro de periodo surtido ────────────────────────────────────────────────

class TestAlmacenPeriodoSurtido(unittest.TestCase):

    def setUp(self):
        self.cmp = [_cmp()]

    def test_excluye_ventas_fuera_periodo(self):
        vtas = [_vta(**{VFX + "fecha_de_creaci_n": "2026-07-01T00:00:00.000Z"})]
        r = build_almacen_dashboard(self.cmp, vtas, **PERIODO)
        self.assertEqual(r["kpis"]["n_partidas_vta"], 0)

    def test_incluye_ventas_dia_inicio(self):
        vtas = [_vta(**{VFX + "fecha_de_creaci_n": "2026-05-01T00:00:00.000Z"})]
        r = build_almacen_dashboard(self.cmp, vtas, **PERIODO)
        self.assertEqual(r["kpis"]["n_partidas_vta"], 1)

    def test_incluye_ventas_dia_fin(self):
        vtas = [_vta(**{VFX + "fecha_de_creaci_n": "2026-05-31T23:59:59.000Z"})]
        r = build_almacen_dashboard(self.cmp, vtas, **PERIODO)
        self.assertEqual(r["kpis"]["n_partidas_vta"], 1)


# ─── Recepcion de compras / fill rate ────────────────────────────────────────

class TestAlmacenRecepcion(unittest.TestCase):

    def setUp(self):
        self.vtas = [_vta()]

    def test_fill_rate_completo(self):
        # 10 solicitadas, 10 llegadas → 100%
        r = build_almacen_dashboard([_cmp()], self.vtas, **PERIODO)
        self.assertAlmostEqual(r["kpis"]["fill_rate"], 1.0)

    def test_fill_rate_parcial(self):
        # 10 solicitadas, 6 llegadas → 60%
        r = build_almacen_dashboard(
            [_cmp(**{CFX + "cantidad_llegada": "6"})], self.vtas, **PERIODO
        )
        self.assertAlmostEqual(r["kpis"]["fill_rate"], 0.60)

    def test_pendiente_sin_llegada(self):
        # cantidad_llegada vacío → pendiente
        r = build_almacen_dashboard(
            [_cmp(**{CFX + "cantidad_llegada": ""})], self.vtas, **PERIODO
        )
        self.assertEqual(r["kpis"]["n_pendientes_rcep"], 1)
        self.assertEqual(r["kpis"]["n_completos_rcep"], 0)

    def test_tres_estados_conteo(self):
        cmp_rows = [
            _cmp(**{CFX + "id": "a", CFX + "cantidad_llegada": "10",
                    CFX + "cantidad_solicitada": "10"}),  # completo
            _cmp(**{CFX + "id": "b", CFX + "cantidad_llegada": "5",
                    CFX + "cantidad_solicitada": "10"}),  # parcial
            _cmp(**{CFX + "id": "c", CFX + "cantidad_llegada": ""}),   # pendiente
        ]
        r = build_almacen_dashboard(cmp_rows, self.vtas, **PERIODO)
        self.assertEqual(r["kpis"]["n_completos_rcep"],  1)
        self.assertEqual(r["kpis"]["n_parciales_rcep"],  1)
        self.assertEqual(r["kpis"]["n_pendientes_rcep"], 1)

    def test_fill_rate_cero_sin_llegadas(self):
        r = build_almacen_dashboard(
            [_cmp(**{CFX + "cantidad_llegada": ""})], self.vtas, **PERIODO
        )
        # sol=10, lleg=0 → fill_rate=0
        self.assertAlmostEqual(r["kpis"]["fill_rate"], 0.0)

    def test_fill_por_fc_en_series(self):
        r = build_almacen_dashboard([_cmp()], self.vtas, **PERIODO)
        self.assertGreaterEqual(len(r["series"]["fill_por_fc"]), 1)
        fc = r["series"]["fill_por_fc"][0]
        self.assertIn("pct", fc)

    def test_tabla_pendientes_rcep_sin_llegada(self):
        cmp_rows = [_cmp(**{CFX + "cantidad_llegada": ""})]
        r = build_almacen_dashboard(cmp_rows, self.vtas, **PERIODO)
        self.assertEqual(len(r["tables"]["pendientes_rcep"]), 1)

    def test_tabla_pendientes_rcep_completa_no_aparece(self):
        cmp_rows = [_cmp()]   # cantidad_llegada=10 == solicitada=10 → completo
        r = build_almacen_dashboard(cmp_rows, self.vtas, **PERIODO)
        self.assertEqual(len(r["tables"]["pendientes_rcep"]), 0)


# ─── Filtro de periodo recepcion ──────────────────────────────────────────────

class TestAlmacenPeriodoRecepcion(unittest.TestCase):

    def setUp(self):
        self.vtas = [_vta()]

    def test_excluye_compras_fuera_de_periodo(self):
        cmp_rows = [_cmp(**{CFX + "fecha_creacion": "2026-07-01T00:00:00.000Z"})]
        r = build_almacen_dashboard(cmp_rows, self.vtas, **PERIODO)
        self.assertEqual(r["kpis"]["n_partidas_cmp"], 0)

    def test_incluye_compras_dia_inicio(self):
        cmp_rows = [_cmp(**{CFX + "fecha_creacion": "2026-05-01T00:00:00.000Z"})]
        r = build_almacen_dashboard(cmp_rows, self.vtas, **PERIODO)
        self.assertEqual(r["kpis"]["n_partidas_cmp"], 1)


# ─── Validacion fisica ────────────────────────────────────────────────────────

class TestAlmacenValidacionFisica(unittest.TestCase):

    def setUp(self):
        self.vtas = [_vta()]

    def test_valida_true_suma(self):
        cmp_rows = [_cmp(**{CFX + "validacion_fisica": "TRUE"})]
        r = build_almacen_dashboard(cmp_rows, self.vtas, **PERIODO)
        self.assertEqual(r["kpis"]["n_validadas"], 1)
        self.assertAlmostEqual(r["kpis"]["pct_validado"], 1.0)

    def test_valida_false_no_suma(self):
        cmp_rows = [_cmp(**{CFX + "validacion_fisica": "FALSE"})]
        r = build_almacen_dashboard(cmp_rows, self.vtas, **PERIODO)
        self.assertEqual(r["kpis"]["n_validadas"], 0)
        self.assertAlmostEqual(r["kpis"]["pct_validado"], 0.0)

    def test_mix_50pct(self):
        cmp_rows = [
            _cmp(**{CFX + "id": "a", CFX + "validacion_fisica": "TRUE"}),
            _cmp(**{CFX + "id": "b", CFX + "validacion_fisica": "FALSE"}),
        ]
        r = build_almacen_dashboard(cmp_rows, self.vtas, **PERIODO)
        self.assertAlmostEqual(r["kpis"]["pct_validado"], 0.50)


# ─── Señales ──────────────────────────────────────────────────────────────────

class TestAlmacenSenales(unittest.TestCase):

    def test_senal_partidas_faltantes(self):
        vtas = [_vta(**{VFX + "estado": "Faltante", VFX + "cantidad_faltante": "5"})]
        r = build_almacen_dashboard([_cmp()], vtas, **PERIODO)
        tipos = [s["tipo"] for s in r["signals"]]
        self.assertIn("partidas_faltantes", tipos)

    def test_sin_senal_si_no_hay_faltantes(self):
        vtas = [_vta()]   # estado=Empacado, cantidad_faltante=0
        r = build_almacen_dashboard([_cmp()], vtas, **PERIODO)
        tipos = [s["tipo"] for s in r["signals"]]
        self.assertNotIn("partidas_faltantes", tipos)

    def test_senal_validacion_fisica_baja(self):
        # menos del 50% validados con >=5 partidas
        cmp_rows = [
            _cmp(**{CFX + "id": f"c{i}", CFX + "validacion_fisica": "FALSE"}) for i in range(5)
        ]
        r = build_almacen_dashboard(cmp_rows, [_vta()], **PERIODO)
        tipos = [s["tipo"] for s in r["signals"]]
        self.assertIn("validacion_fisica_baja", tipos)

    def test_sin_senal_validacion_fisica_si_menos_de_5(self):
        # solo 4 partidas con 0% validado → no dispara (min_partidas=5)
        cmp_rows = [
            _cmp(**{CFX + "id": f"c{i}", CFX + "validacion_fisica": "FALSE"}) for i in range(4)
        ]
        r = build_almacen_dashboard(cmp_rows, [_vta()], **PERIODO)
        tipos = [s["tipo"] for s in r["signals"]]
        self.assertNotIn("validacion_fisica_baja", tipos)


# ─── Series y estructura de respuesta ────────────────────────────────────────

class TestAlmacenEstructura(unittest.TestCase):

    def test_estructura_completa(self):
        r = build_almacen_dashboard([_cmp()], [_vta()], **PERIODO)
        self.assertIn("kpis", r)
        self.assertIn("series", r)
        self.assertIn("tables", r)
        self.assertIn("signals", r)

    def test_serie_surtido_tres_estados(self):
        r = build_almacen_dashboard([_cmp()], [_vta()], **PERIODO)
        estados = {s["estado"] for s in r["series"]["surtido"]}
        self.assertSetEqual(estados, {"Empacado", "Pendiente", "Faltante"})

    def test_tabla_faltantes_con_cantidad_faltante(self):
        vtas = [_vta(**{VFX + "cantidad_faltante": "5", VFX + "estado": "Faltante"})]
        r = build_almacen_dashboard([_cmp()], vtas, **PERIODO)
        self.assertGreaterEqual(len(r["tables"]["faltantes"]), 1)

    def test_tabla_faltantes_vacia_sin_faltantes(self):
        # cantidad_faltante=0 en todo
        vtas = [_vta()]
        r = build_almacen_dashboard([_cmp()], vtas, **PERIODO)
        self.assertEqual(len(r["tables"]["faltantes"]), 0)


if __name__ == "__main__":
    unittest.main()
