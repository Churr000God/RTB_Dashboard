import unittest
from rtb_analisis import build_pnl_dashboard

PERIODO = {"fecha_desde": "2026-05-01", "fecha_hasta": "2026-05-31"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _periodos_inv(*keys):
    """Periodos stub para inventario.temporal_margen (campos venta/costo/margen)."""
    return [
        {"key": k, "etiqueta": k, "venta": 0, "costo": 0, "margen": 0}
        for k in keys
    ]


def _periodos_gas(*keys):
    """Periodos stub para gastos.temporal (campo monto = total con IVA)."""
    return [
        {"key": k, "etiqueta": k, "monto": 0, "gastos": 0}
        for k in keys
    ]


def _temporal_inv(periodos, kv_override=None):
    """temporal_margen stub de Inventario con eje minimal."""
    rows = []
    for p in periodos:
        row = dict(p)
        if kv_override and p["key"] in kv_override:
            row.update(kv_override[p["key"]])
        rows.append(row)
    keys = [p["key"] for p in periodos]
    return {
        "granularidad": "semana",
        "keys": keys,
        "labels": keys,
        "table_heading": "Semana",
        "behavior_title": "Comportamiento semanal",
        "chart_suffix": "por semana",
        "hint": "",
        "periodos": rows,
        "tendencias": {},
    }


def _temporal_gas(periodos, kv_override=None):
    """temporal stub de Gastos."""
    rows = []
    for p in periodos:
        row = dict(p)
        if kv_override and p["key"] in kv_override:
            row.update(kv_override[p["key"]])
        rows.append(row)
    keys = [p["key"] for p in periodos]
    return {
        "granularidad": "semana",
        "keys": keys,
        "labels": keys,
        "table_heading": "Semana",
        "behavior_title": "Comportamiento semanal",
        "chart_suffix": "por semana",
        "hint": "",
        "periodos": rows,
        "tendencias": {},
    }


def _inv(venta=0, costo=0, margen=None, n_sin_costo=0, n_margen_neg=0,
         temporal_kv=None, periodos=None, top_pedidos=None):
    p = periodos or _periodos_inv("S1", "S2", "S3")
    m = margen if margen is not None else (venta - costo)
    pct = round(m / venta, 4) if venta else 0.0
    return {
        "kpis": {
            "venta_total":  venta,
            "costo_total":  costo,
            "margen_total": m,
            "pct_margen":   pct,
            "n_sin_costo":  n_sin_costo,
            "n_margen_neg": n_margen_neg,
            "inv_total":    0,
            "n_partidas":   0,
        },
        "series": {"temporal_margen": _temporal_inv(p, temporal_kv)},
        "tables": {"top_pedidos_margen": top_pedidos or []},
        "signals": [],
    }


def _gas(total_subtotal=0, total_total=None, iva_acreditable=0,
         temporal_kv=None, periodos=None):
    p = periodos or _periodos_gas("S1", "S2", "S3")
    tt = total_total if total_total is not None else total_subtotal
    return {
        "kpis": {
            "total_subtotal":  total_subtotal,
            "total_total":     tt,
            "total_iva":       round(tt - total_subtotal, 2),
            "iva_acreditable": iva_acreditable,
            "n_gastos":        0,
        },
        "series": {"temporal": _temporal_gas(p, temporal_kv)},
        "signals": [],
    }


def _fac(monto_vigente=0):
    return {
        "kpis": {"monto_facturado_vigente": monto_vigente},
        "series": {},
        "signals": [],
    }


def _build(**kw):
    defaults = dict(
        inventario=_inv(),
        gastos_operativos=_gas(),
        facturacion=None,
        period_label="mayo 2026",
        **PERIODO,
    )
    defaults.update(kw)
    return build_pnl_dashboard(**defaults)


# ── TestEstructura ─────────────────────────────────────────────────────────────

class TestEstructura(unittest.TestCase):
    def setUp(self):
        self.result = _build()

    def test_claves_top(self):
        self.assertEqual(set(self.result.keys()), {"periodo", "kpis", "series", "tables", "signals"})

    def test_periodo_label(self):
        self.assertEqual(self.result["periodo"], "mayo 2026")

    def test_kpis_claves(self):
        esperadas = {
            "ingresos", "costo_ventas", "utilidad_bruta", "margen_bruto",
            "gastos_operativos", "utilidad_operativa", "margen_operativo",
            "ingresos_facturados", "n_sin_costo", "n_margen_neg", "n_signals",
        }
        self.assertTrue(esperadas.issubset(set(self.result["kpis"].keys())))

    def test_series_tiene_temporal(self):
        self.assertIn("temporal", self.result["series"])

    def test_tables_claves(self):
        esperadas = {"estado_resultados", "margen_por_periodo", "top_pedidos"}
        self.assertTrue(esperadas.issubset(set(self.result["tables"].keys())))

    def test_signals_es_lista(self):
        self.assertIsInstance(self.result["signals"], list)

    def test_estado_resultados_5_filas(self):
        er = self.result["tables"]["estado_resultados"]
        self.assertEqual(len(er), 5)

    def test_estado_resultados_tipos(self):
        er = self.result["tables"]["estado_resultados"]
        tipos = {r["tipo"] for r in er}
        self.assertEqual(tipos, {"ingreso", "costo", "utilidad_bruta", "gasto", "utilidad_operativa"})


# ── TestKpis ───────────────────────────────────────────────────────────────────

class TestKpis(unittest.TestCase):
    def setUp(self):
        self.result = _build(
            inventario=_inv(venta=1_000_000, costo=600_000),
            gastos_operativos=_gas(total_subtotal=150_000, total_total=174_000),
        )
        self.kpis = self.result["kpis"]

    def test_ingresos(self):
        self.assertAlmostEqual(self.kpis["ingresos"], 1_000_000.0, places=1)

    def test_costo_ventas(self):
        self.assertAlmostEqual(self.kpis["costo_ventas"], 600_000.0, places=1)

    def test_utilidad_bruta(self):
        self.assertAlmostEqual(self.kpis["utilidad_bruta"], 400_000.0, places=1)

    def test_margen_bruto(self):
        self.assertAlmostEqual(self.kpis["margen_bruto"], 0.4, places=4)

    def test_gastos_operativos_usa_subtotal_sin_iva(self):
        # Debe usar total_subtotal (150k), no total_total (174k)
        self.assertAlmostEqual(self.kpis["gastos_operativos"], 150_000.0, places=1)

    def test_utilidad_operativa(self):
        # 400_000 - 150_000 = 250_000
        self.assertAlmostEqual(self.kpis["utilidad_operativa"], 250_000.0, places=1)

    def test_margen_operativo(self):
        self.assertAlmostEqual(self.kpis["margen_operativo"], 0.25, places=4)


# ── TestOpexSinIVA ─────────────────────────────────────────────────────────────

class TestOpexSinIVA(unittest.TestCase):
    """OPEX del KPI = total_subtotal, no total_total."""

    def test_kpi_usa_subtotal(self):
        r = _build(gastos_operativos=_gas(total_subtotal=10_000, total_total=11_600))
        self.assertAlmostEqual(r["kpis"]["gastos_operativos"], 10_000.0, places=1)

    def test_kpi_no_usa_total_con_iva(self):
        r = _build(gastos_operativos=_gas(total_subtotal=10_000, total_total=11_600))
        self.assertNotAlmostEqual(r["kpis"]["gastos_operativos"], 11_600.0, places=0)

    def test_temporal_opex_escalado(self):
        """Gastos temporales se escalan por total_subtotal/total_total."""
        p_gas = _periodos_gas("S1")
        # monto (con IVA) = 11_600; razon = 10000/11600; opex_s1 = 11600 * (10000/11600) = 10000
        result = _build(
            inventario=_inv(periodos=_periodos_inv("S1")),
            gastos_operativos=_gas(
                total_subtotal=10_000, total_total=11_600,
                temporal_kv={"S1": {"monto": 11_600}},
                periodos=p_gas,
            ),
        )
        per = result["series"]["temporal"].get("periodos") or []
        if per:
            self.assertAlmostEqual(per[0]["gastos"], 10_000.0, places=1)

    def test_temporal_opex_cero_si_no_hay_total(self):
        """Si total_total == 0, opex temporal = 0 (no ZeroDivisionError)."""
        p_gas = _periodos_gas("S1")
        try:
            result = _build(
                inventario=_inv(periodos=_periodos_inv("S1")),
                gastos_operativos=_gas(
                    total_subtotal=0, total_total=0,
                    temporal_kv={"S1": {"monto": 100}},
                    periodos=p_gas,
                ),
            )
        except ZeroDivisionError:
            self.fail("Lanzo ZeroDivisionError cuando total_total == 0")
        per = result["series"]["temporal"].get("periodos") or []
        if per:
            self.assertAlmostEqual(per[0]["gastos"], 0.0, places=1)


# ── TestCascada ────────────────────────────────────────────────────────────────

class TestCascada(unittest.TestCase):
    def setUp(self):
        self.r = _build(
            inventario=_inv(venta=500_000, costo=300_000),
            gastos_operativos=_gas(total_subtotal=80_000),
        )
        self.er = {row["tipo"]: row for row in self.r["tables"]["estado_resultados"]}

    def test_ingreso_positivo(self):
        self.assertGreater(self.er["ingreso"]["monto"], 0)

    def test_costo_negativo_en_cascada(self):
        # Costo aparece negativo en la tabla (resta)
        self.assertLess(self.er["costo"]["monto"], 0)

    def test_gasto_negativo_en_cascada(self):
        self.assertLess(self.er["gasto"]["monto"], 0)

    def test_utilidad_bruta_coherente(self):
        # Ingresos + costo_fila = utilidad_bruta (costo_fila es negativo)
        esperada = self.er["ingreso"]["monto"] + self.er["costo"]["monto"]
        self.assertAlmostEqual(self.er["utilidad_bruta"]["monto"], esperada, places=1)

    def test_utilidad_operativa_coherente(self):
        esperada = self.er["utilidad_bruta"]["monto"] + self.er["gasto"]["monto"]
        self.assertAlmostEqual(self.er["utilidad_operativa"]["monto"], esperada, places=1)

    def test_pct_ingreso_es_100(self):
        self.assertAlmostEqual(self.er["ingreso"]["pct"], 1.0, places=4)


# ── TestAlineacionTemporal ─────────────────────────────────────────────────────

class TestAlineacionTemporal(unittest.TestCase):
    def setUp(self):
        p_inv = _periodos_inv("S1", "S2", "S3")
        p_gas = _periodos_gas("S1", "S2", "S3")
        self.result = _build(
            inventario=_inv(
                venta=300_000, costo=200_000,
                temporal_kv={"S1": {"venta": 100_000, "costo": 60_000, "margen": 40_000},
                             "S2": {"venta": 200_000, "costo": 140_000, "margen": 60_000}},
                periodos=p_inv,
            ),
            gastos_operativos=_gas(
                total_subtotal=10_000, total_total=11_600,
                temporal_kv={"S1": {"monto": 5_800}},  # => 5_000 pre-IVA
                periodos=p_gas,
            ),
        )
        self.periodos = self.result["series"]["temporal"].get("periodos") or []

    def test_tiene_3_periodos(self):
        self.assertEqual(len(self.periodos), 3)

    def test_ingresos_S1(self):
        s1 = self.periodos[0]
        self.assertAlmostEqual(s1["ingresos"], 100_000.0, places=1)

    def test_costo_S1(self):
        s1 = self.periodos[0]
        self.assertAlmostEqual(s1["costo"], 60_000.0, places=1)

    def test_utilidad_bruta_S1(self):
        s1 = self.periodos[0]
        self.assertAlmostEqual(s1["utilidad_bruta"], 40_000.0, places=1)

    def test_gastos_S1_escalados(self):
        # monto_s1 = 5800; razon = 10000/11600; opex = 5800 * (10000/11600) = 5000
        s1 = self.periodos[0]
        self.assertAlmostEqual(s1["gastos"], 5_000.0, places=1)

    def test_utilidad_operativa_S1(self):
        s1 = self.periodos[0]
        self.assertAlmostEqual(s1["utilidad_operativa"], 35_000.0, places=1)  # 40000 - 5000

    def test_S3_cero_sin_datos(self):
        s3 = self.periodos[2]
        self.assertAlmostEqual(s3["ingresos"], 0.0, places=1)
        self.assertAlmostEqual(s3["gastos"], 0.0, places=1)
        self.assertAlmostEqual(s3["utilidad_operativa"], 0.0, places=1)

    def test_tendencias_presentes(self):
        t = self.result["series"]["temporal"].get("tendencias") or {}
        self.assertIn("utilidad_bruta", t)
        self.assertIn("utilidad_operativa", t)

    def test_margen_por_periodo_coherente(self):
        mp = self.result["tables"]["margen_por_periodo"]
        self.assertEqual(len(mp), len(self.periodos))
        mp0 = mp[0]
        self.assertAlmostEqual(mp0["ingresos"], self.periodos[0]["ingresos"], places=1)
        self.assertAlmostEqual(mp0["utilidad_operativa"], self.periodos[0]["utilidad_operativa"], places=1)


# ── TestEjeDesalineado ─────────────────────────────────────────────────────────

class TestEjeDesalineado(unittest.TestCase):
    """Inventario con S1/S2/S3, gastos solo con S2."""

    def setUp(self):
        p_inv = _periodos_inv("S1", "S2", "S3")
        p_gas = _periodos_gas("S2")
        self.result = _build(
            inventario=_inv(
                temporal_kv={"S1": {"venta": 100, "costo": 60, "margen": 40}},
                periodos=p_inv,
            ),
            gastos_operativos=_gas(
                total_subtotal=10, total_total=10,
                temporal_kv={"S2": {"monto": 10}},
                periodos=p_gas,
            ),
        )
        self.periodos = self.result["series"]["temporal"].get("periodos") or []

    def test_no_lanza(self):
        self.assertIsNotNone(self.periodos)

    def test_referencia_es_inventario(self):
        # Eje tomado de inventario: 3 periodos
        self.assertEqual(len(self.periodos), 3)

    def test_S1_gastos_cero_no_en_gastos(self):
        s1 = self.periodos[0]
        self.assertAlmostEqual(s1["gastos"], 0.0, places=1)

    def test_S2_gastos_presentes(self):
        s2 = self.periodos[1]
        self.assertAlmostEqual(s2["gastos"], 10.0, places=1)


# ── TestSubDashboardVacio ─────────────────────────────────────────────────────

class TestSubDashboardVacio(unittest.TestCase):
    def test_None_no_lanza(self):
        try:
            r = build_pnl_dashboard(None, None, None, **PERIODO)
        except Exception as exc:
            self.fail(f"Lanzo excepcion con sub-dashboards None: {exc}")
        self.assertAlmostEqual(r["kpis"]["utilidad_operativa"], 0.0, places=1)

    def test_dicts_vacios_no_lanzan(self):
        r = build_pnl_dashboard({}, {}, {}, **PERIODO)
        self.assertAlmostEqual(r["kpis"]["ingresos"], 0.0, places=1)

    def test_parcialmente_vacio(self):
        r = _build(gastos_operativos={})
        self.assertAlmostEqual(r["kpis"]["gastos_operativos"], 0.0, places=1)

    def test_temporal_vacio_cuando_inv_sin_serie(self):
        inv_sin_temporal = {"kpis": {}, "series": {}, "tables": {}, "signals": []}
        r = build_pnl_dashboard(inv_sin_temporal, {}, {}, **PERIODO)
        self.assertFalse(r["series"]["temporal"])

    def test_margen_bruto_cero_cuando_ingresos_cero(self):
        r = build_pnl_dashboard(None, None, None, **PERIODO)
        self.assertEqual(r["kpis"]["margen_bruto"], 0.0)

    def test_margen_operativo_cero_cuando_ingresos_cero(self):
        r = build_pnl_dashboard(None, None, None, **PERIODO)
        self.assertEqual(r["kpis"]["margen_operativo"], 0.0)


# ── TestSignals ────────────────────────────────────────────────────────────────

class TestSignals(unittest.TestCase):
    def test_senales_de_inventario_presentes(self):
        inv = _inv()
        inv["signals"] = [{"tipo": "inv_test", "msg": "test"}]
        r = _build(inventario=inv)
        tipos = [s["tipo"] for s in r["signals"]]
        self.assertIn("inv_test", tipos)

    def test_senales_de_gastos_presentes(self):
        gas = _gas()
        gas["signals"] = [{"tipo": "gasto_test", "msg": "test"}]
        r = _build(gastos_operativos=gas)
        tipos = [s["tipo"] for s in r["signals"]]
        self.assertIn("gasto_test", tipos)

    def test_senal_costo_incompleto_cuando_n_sin_costo(self):
        r = _build(inventario=_inv(n_sin_costo=5))
        tipos = [s["tipo"] for s in r["signals"]]
        self.assertIn("pnl_costo_incompleto", tipos)

    def test_senal_costo_incompleto_cuando_margen_neg(self):
        r = _build(inventario=_inv(n_margen_neg=2))
        tipos = [s["tipo"] for s in r["signals"]]
        self.assertIn("pnl_costo_incompleto", tipos)

    def test_sin_senal_costo_incompleto_si_datos_ok(self):
        r = _build(inventario=_inv(n_sin_costo=0, n_margen_neg=0))
        tipos = [s["tipo"] for s in r["signals"]]
        self.assertNotIn("pnl_costo_incompleto", tipos)

    def test_n_signals_coherente(self):
        r = _build(inventario=_inv(n_sin_costo=1))
        self.assertEqual(r["kpis"]["n_signals"], len(r["signals"]))


# ── TestTablas ─────────────────────────────────────────────────────────────────

class TestTablas(unittest.TestCase):
    def setUp(self):
        top = [
            {"cotizacion": "COT-001", "venta": 100_000, "costo": 60_000, "margen": 40_000, "n": 5, "pct": 0.4},
            {"cotizacion": "COT-002", "venta": 80_000, "costo": 50_000, "margen": 30_000, "n": 3, "pct": 0.375},
        ]
        self.r = _build(
            inventario=_inv(venta=500_000, costo=300_000, top_pedidos=top),
            gastos_operativos=_gas(total_subtotal=80_000),
        )

    def test_estado_resultados_orden(self):
        tipos_ordenados = [r["tipo"] for r in self.r["tables"]["estado_resultados"]]
        self.assertEqual(tipos_ordenados,
                         ["ingreso", "costo", "utilidad_bruta", "gasto", "utilidad_operativa"])

    def test_top_pedidos_passthrough(self):
        top = self.r["tables"]["top_pedidos"]
        self.assertEqual(len(top), 2)
        self.assertEqual(top[0]["cotizacion"], "COT-001")

    def test_top_pedidos_max_10(self):
        pedidos_grandes = [{"cotizacion": f"C{i}", "venta": 1000, "costo": 500, "margen": 500, "n": 1, "pct": 0.5}
                           for i in range(15)]
        r = _build(inventario=_inv(top_pedidos=pedidos_grandes))
        self.assertEqual(len(r["tables"]["top_pedidos"]), 10)

    def test_margen_por_periodo_campos(self):
        mp = self.r["tables"]["margen_por_periodo"]
        if mp:
            expected_fields = {"key", "etiqueta", "ingresos", "costo", "utilidad_bruta",
                               "margen_bruto_pct", "gastos", "utilidad_operativa"}
            self.assertTrue(expected_fields.issubset(set(mp[0].keys())))

    def test_costo_negativo_en_estado_resultados(self):
        fila_costo = next(r for r in self.r["tables"]["estado_resultados"] if r["tipo"] == "costo")
        self.assertLessEqual(fila_costo["monto"], 0)

    def test_gasto_negativo_en_estado_resultados(self):
        fila_gasto = next(r for r in self.r["tables"]["estado_resultados"] if r["tipo"] == "gasto")
        self.assertLessEqual(fila_gasto["monto"], 0)


# ── TestFacturacionMemo ────────────────────────────────────────────────────────

class TestFacturacionMemo(unittest.TestCase):
    """facturacion es solo referencia, no afecta la cascada."""

    def test_ingresos_facturados_presente(self):
        r = _build(facturacion=_fac(monto_vigente=500_000))
        self.assertAlmostEqual(r["kpis"]["ingresos_facturados"], 500_000.0, places=1)

    def test_facturacion_no_afecta_ingresos(self):
        r1 = _build(inventario=_inv(venta=300_000), facturacion=_fac(monto_vigente=400_000))
        r2 = _build(inventario=_inv(venta=300_000), facturacion=_fac(monto_vigente=999_999))
        self.assertAlmostEqual(r1["kpis"]["ingresos"], r2["kpis"]["ingresos"], places=1)

    def test_facturacion_no_afecta_utilidad(self):
        r1 = _build(inventario=_inv(venta=300_000, costo=200_000), facturacion=_fac(monto_vigente=0))
        r2 = _build(inventario=_inv(venta=300_000, costo=200_000), facturacion=_fac(monto_vigente=999_999))
        self.assertAlmostEqual(r1["kpis"]["utilidad_bruta"], r2["kpis"]["utilidad_bruta"], places=1)


# ── TestDatosReales ────────────────────────────────────────────────────────────

class TestDatosReales(unittest.TestCase):
    """Regresion contra cifras reales de mayo 2026 (snapshots regenerados 2026-06-13).

    Ingresos:        308,366.71
    Costo:           202,735.01
    Utilidad bruta:  105,631.70   (34.26%)
    OPEX (sin IVA):   27,061.45
    Utilidad op.:     78,570.25   (25.48%)
    """

    def setUp(self):
        self.r = _build(
            inventario=_inv(venta=308_366.714264, costo=202_735.01076529,
                            margen=105_631.70349871),
            gastos_operativos=_gas(total_subtotal=27_061.45, total_total=31_391.30),
        )
        self.kpis = self.r["kpis"]

    def test_ingresos(self):
        self.assertAlmostEqual(self.kpis["ingresos"], 308_366.71, places=0)

    def test_costo_ventas(self):
        self.assertAlmostEqual(self.kpis["costo_ventas"], 202_735.01, places=0)

    def test_utilidad_bruta(self):
        self.assertAlmostEqual(self.kpis["utilidad_bruta"], 105_631.70, places=0)

    def test_margen_bruto(self):
        self.assertAlmostEqual(self.kpis["margen_bruto"], 0.3426, places=2)

    def test_gastos_operativos(self):
        self.assertAlmostEqual(self.kpis["gastos_operativos"], 27_061.45, places=0)

    def test_utilidad_operativa(self):
        self.assertAlmostEqual(self.kpis["utilidad_operativa"], 78_570.25, places=0)

    def test_margen_operativo(self):
        self.assertAlmostEqual(self.kpis["margen_operativo"], 0.2548, places=2)


if __name__ == "__main__":
    unittest.main()
