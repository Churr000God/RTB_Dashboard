import unittest
from rtb_analisis import build_finanzas_dashboard

PERIODO = {"fecha_desde": "2026-05-01", "fecha_hasta": "2026-05-31"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _periodos(*keys):
    """Genera lista de periodos temporales stub con todas las métricas en 0."""
    return [
        {"key": k, "etiqueta": k, "monto": 0, "tot": 0, "pagos": 0, "cobros": 0, "gastos": 0}
        for k in keys
    ]


def _temporal_stub(periodos, kv_override=None):
    """temporal con eje mínimo; permite sobreescribir métricas por key."""
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


def _fac(monto_vigente=0, temporal_kv=None, periodos=None):
    p = periodos or _periodos("S1", "S2", "S3")
    return {
        "kpis": {"monto_facturado_vigente": monto_vigente},
        "series": {"temporal": _temporal_stub(p, temporal_kv)},
        "signals": [],
    }


def _cob(monto_cobrado=0, pendiente=0, n_pendientes=0, temporal_kv=None, periodos=None):
    p = periodos or _periodos("S1", "S2", "S3")
    return {
        "kpis": {
            "monto_cobrado_total": monto_cobrado,
            "monto_pendiente_cobro": pendiente,
            "n_pendientes_cobro": n_pendientes,
        },
        "series": {"temporal": _temporal_stub(p, temporal_kv)},
        "signals": [],
    }


def _com(tot_fc=0, iva_fc=0, temporal_kv=None, periodos=None):
    p = periodos or _periodos("S1", "S2", "S3")
    return {
        "kpis": {"tot_fc": tot_fc, "iva_fc": iva_fc},
        "series": {"temporal": _temporal_stub(p, temporal_kv)},
    }


def _pag(monto_total=0, n_pendientes=0, temporal_kv=None, periodos=None):
    p = periodos or _periodos("S1", "S2", "S3")
    return {
        "kpis": {"monto_total": monto_total, "n_pendientes": n_pendientes},
        "series": {"temporal": _temporal_stub(p, temporal_kv)},
        "signals": [],
    }


def _gas(total_total=0, iva_acreditable=0, temporal_kv=None, periodos=None):
    p = periodos or _periodos("S1", "S2", "S3")
    return {
        "kpis": {"total_total": total_total, "iva_acreditable": iva_acreditable},
        "series": {"temporal": _temporal_stub(p, temporal_kv)},
        "signals": [],
    }


def _build(**kw):
    defaults = dict(
        facturacion=_fac(), cobranza=_cob(), compras=_com(),
        pagos_proveedores=_pag(), gastos_operativos=_gas(),
        period_label="mayo 2026", **PERIODO,
    )
    defaults.update(kw)
    return build_finanzas_dashboard(**defaults)


# ── TestEstructura ─────────────────────────────────────────────────────────

class TestEstructura(unittest.TestCase):
    def setUp(self):
        self.result = _build()

    def test_top_level_keys(self):
        for k in ("periodo", "kpis", "series", "tables", "signals"):
            self.assertIn(k, self.result, f"Falta clave top-level '{k}'")

    def test_tables_keys(self):
        t = self.result["tables"]
        for k in ("comparativo", "waterfall_devengado", "iva_split"):
            self.assertIn(k, t, f"Falta tabla '{k}'")

    def test_kpis_completos(self):
        kpis = self.result["kpis"]
        esperados = [
            "ingreso_devengado", "egreso_devengado", "egreso_devengado_compras",
            "egreso_devengado_gastos", "utilidad_devengada", "margen_devengado",
            "ingreso_caja", "egreso_caja", "egreso_caja_pagos", "egreso_caja_gastos",
            "flujo_caja_neto", "margen_caja", "pendiente_cobro", "n_pendientes_cobro",
            "pendiente_pago", "iva_trasladado", "iva_acreditable", "iva_por_pagar",
            "n_signals",
        ]
        for k in esperados:
            self.assertIn(k, kpis, f"Falta KPI '{k}'")

    def test_periodo(self):
        self.assertEqual(self.result["periodo"], "mayo 2026")


# ── TestKpisDevengado ──────────────────────────────────────────────────────

class TestKpisDevengado(unittest.TestCase):
    def setUp(self):
        self.result = _build(
            facturacion=_fac(monto_vigente=1_000_000),
            compras=_com(tot_fc=600_000),
            gastos_operativos=_gas(total_total=200_000),
        )
        self.kpis = self.result["kpis"]

    def test_ingreso_devengado(self):
        self.assertAlmostEqual(self.kpis["ingreso_devengado"], 1_000_000.0, places=1)

    def test_egreso_devengado_compras(self):
        self.assertAlmostEqual(self.kpis["egreso_devengado_compras"], 600_000.0, places=1)

    def test_egreso_devengado_gastos(self):
        self.assertAlmostEqual(self.kpis["egreso_devengado_gastos"], 200_000.0, places=1)

    def test_egreso_devengado_suma(self):
        self.assertAlmostEqual(self.kpis["egreso_devengado"], 800_000.0, places=1)

    def test_utilidad_devengada(self):
        self.assertAlmostEqual(self.kpis["utilidad_devengada"], 200_000.0, places=1)

    def test_margen_devengado(self):
        self.assertAlmostEqual(self.kpis["margen_devengado"], 0.2, places=4)

    def test_margen_cero_cuando_ingreso_cero(self):
        r = _build(facturacion=_fac(monto_vigente=0))
        self.assertEqual(r["kpis"]["margen_devengado"], 0.0)


# ── TestKpisCaja ──────────────────────────────────────────────────────────

class TestKpisCaja(unittest.TestCase):
    def setUp(self):
        self.result = _build(
            cobranza=_cob(monto_cobrado=735_727.62),
            pagos_proveedores=_pag(monto_total=610_376.88),
            gastos_operativos=_gas(total_total=197_626.14),
        )
        self.kpis = self.result["kpis"]

    def test_ingreso_caja(self):
        self.assertAlmostEqual(self.kpis["ingreso_caja"], 735_727.62, places=1)

    def test_egreso_caja_pagos(self):
        self.assertAlmostEqual(self.kpis["egreso_caja_pagos"], 610_376.88, places=1)

    def test_egreso_caja_gastos(self):
        self.assertAlmostEqual(self.kpis["egreso_caja_gastos"], 197_626.14, places=1)

    def test_egreso_caja_suma(self):
        # 610,376.88 + 197,626.14 = 808,003.02
        self.assertAlmostEqual(self.kpis["egreso_caja"], 808_003.02, places=1)

    def test_flujo_caja_neto_negativo(self):
        # 735,727.62 - 808,003.02 = -72,275.40
        self.assertAlmostEqual(self.kpis["flujo_caja_neto"], -72_275.40, places=0)

    def test_margen_caja_cero_cuando_ingreso_cero(self):
        r = _build(cobranza=_cob(monto_cobrado=0))
        self.assertEqual(r["kpis"]["margen_caja"], 0.0)


# ── TestNoDobleConteo ─────────────────────────────────────────────────────

class TestNoDobleConteo(unittest.TestCase):
    """Compras y pagos_proveedores NO deben sumarse juntos en ninguna base."""

    def setUp(self):
        self.result = _build(
            compras=_com(tot_fc=1000),
            pagos_proveedores=_pag(monto_total=300),
            gastos_operativos=_gas(total_total=100),
        )
        self.kpis = self.result["kpis"]

    def test_egreso_devengado_no_incluye_pagos(self):
        # egreso_devengado = compras(1000) + gastos(100) = 1100, NO 1400
        self.assertAlmostEqual(self.kpis["egreso_devengado"], 1100.0, places=1)

    def test_egreso_caja_no_incluye_compras(self):
        # egreso_caja = pagos(300) + gastos(100) = 400, NO 1400
        self.assertAlmostEqual(self.kpis["egreso_caja"], 400.0, places=1)

    def test_no_suman_compras_y_pagos(self):
        compras_mas_pagos = self.kpis["egreso_devengado_compras"] + self.kpis["egreso_caja_pagos"]
        self.assertNotAlmostEqual(self.kpis["egreso_devengado"], compras_mas_pagos, places=1)
        self.assertNotAlmostEqual(self.kpis["egreso_caja"],      compras_mas_pagos, places=1)


# ── TestGastosEnAmbasBases ────────────────────────────────────────────────

class TestGastosEnAmbasBases(unittest.TestCase):
    """Gastos operativos aparecen tanto en egreso_devengado como en egreso_caja."""

    def setUp(self):
        self.result = _build(
            compras=_com(tot_fc=500),
            pagos_proveedores=_pag(monto_total=300),
            gastos_operativos=_gas(total_total=200),
        )
        self.kpis = self.result["kpis"]

    def test_gastos_en_devengado(self):
        self.assertAlmostEqual(self.kpis["egreso_devengado_gastos"], 200.0, places=1)
        self.assertAlmostEqual(self.kpis["egreso_devengado"], 700.0, places=1)  # 500+200

    def test_gastos_en_caja(self):
        self.assertAlmostEqual(self.kpis["egreso_caja_gastos"], 200.0, places=1)
        self.assertAlmostEqual(self.kpis["egreso_caja"], 500.0, places=1)  # 300+200


# ── TestAlineacionTemporal ────────────────────────────────────────────────

class TestAlineacionTemporal(unittest.TestCase):
    def setUp(self):
        p = _periodos("S1", "S2", "S3")
        self.result = _build(
            facturacion=_fac(temporal_kv={"S1": {"monto": 100}, "S2": {"monto": 200}}, periodos=p),
            compras=_com(temporal_kv={"S1": {"tot": 60}, "S2": {"tot": 80}}, periodos=p),
            gastos_operativos=_gas(temporal_kv={"S1": {"monto": 20}, "S2": {"monto": 30}}, periodos=p),
            cobranza=_cob(temporal_kv={"S1": {"monto": 90}, "S2": {"monto": 150}}, periodos=p),
            pagos_proveedores=_pag(temporal_kv={"S1": {"monto": 50}, "S2": {"monto": 70}}, periodos=p),
        )
        self.periodos = self.result["series"]["temporal"]["periodos"]

    def test_longitud_eje(self):
        self.assertEqual(len(self.periodos), 3)

    def test_ingreso_dev_S1(self):
        s1 = self.periodos[0]
        self.assertAlmostEqual(s1["ingreso_dev"], 100.0, places=1)

    def test_egreso_dev_S1(self):
        s1 = self.periodos[0]
        self.assertAlmostEqual(s1["egreso_dev"], 80.0, places=1)  # 60+20

    def test_utilidad_dev_S1(self):
        s1 = self.periodos[0]
        self.assertAlmostEqual(s1["utilidad_dev"], 20.0, places=1)  # 100-80

    def test_ingreso_caja_S2(self):
        s2 = self.periodos[1]
        self.assertAlmostEqual(s2["ingreso_caja"], 150.0, places=1)

    def test_egreso_caja_S2(self):
        s2 = self.periodos[1]
        self.assertAlmostEqual(s2["egreso_caja"], 100.0, places=1)  # 70+30

    def test_flujo_caja_S3_cero_sin_datos(self):
        s3 = self.periodos[2]
        self.assertAlmostEqual(s3["flujo_caja"], 0.0, places=1)


# ── TestEjeDesalineado ────────────────────────────────────────────────────

class TestEjeDesalineado(unittest.TestCase):
    """Módulo con menos keys que el eje de referencia — las keys faltantes aportan 0."""

    def setUp(self):
        # Facturación tiene S1, S2, S3; compras solo tiene S2
        p_full = _periodos("S1", "S2", "S3")
        p_partial = _periodos("S2")
        self.result = _build(
            facturacion=_fac(temporal_kv={"S1": {"monto": 100}}, periodos=p_full),
            compras=_com(temporal_kv={"S2": {"tot": 60}}, periodos=p_partial),
            gastos_operativos=_gas(periodos=p_full),
        )
        self.periodos = self.result["series"]["temporal"]["periodos"]

    def test_no_lanza(self):
        # Solo verificar que llega aquí sin excepción
        self.assertEqual(len(self.periodos), 3)

    def test_S1_compras_cero(self):
        # compras no tiene S1 → su aporte es 0
        s1 = self.periodos[0]
        self.assertAlmostEqual(s1["egreso_dev"], 0.0, places=1)

    def test_S2_compras_presente(self):
        s2 = self.periodos[1]
        self.assertAlmostEqual(s2["egreso_dev"], 60.0, places=1)


# ── TestIVA ───────────────────────────────────────────────────────────────

class TestIVA(unittest.TestCase):
    def setUp(self):
        self.result = _build(
            cobranza=_cob(monto_cobrado=116_000),   # IVA trasladado = 116000 - 116000/1.16 ≈ 16000
            compras=_com(iva_fc=9_000),
            gastos_operativos=_gas(iva_acreditable=3_000),
        )
        self.kpis = self.result["kpis"]

    def test_iva_trasladado(self):
        esperado = 116_000 - 116_000 / 1.16
        self.assertAlmostEqual(self.kpis["iva_trasladado"], round(esperado, 2), places=1)

    def test_iva_acreditable(self):
        self.assertAlmostEqual(self.kpis["iva_acreditable"], 12_000.0, places=1)  # 9000+3000

    def test_iva_por_pagar(self):
        esperado = round(116_000 - 116_000 / 1.16, 2) - 12_000
        self.assertAlmostEqual(self.kpis["iva_por_pagar"], round(esperado, 2), places=1)

    def test_iva_trasladado_cero_si_no_hay_cobros(self):
        r = _build(cobranza=_cob(monto_cobrado=0))
        self.assertEqual(r["kpis"]["iva_trasladado"], 0.0)


# ── TestPendientes ────────────────────────────────────────────────────────

class TestPendientes(unittest.TestCase):
    def setUp(self):
        self.result = _build(
            cobranza=_cob(pendiente=500_000, n_pendientes=25),
            pagos_proveedores=_pag(n_pendientes=3),
        )
        self.kpis = self.result["kpis"]

    def test_pendiente_cobro(self):
        self.assertAlmostEqual(self.kpis["pendiente_cobro"], 500_000.0, places=1)

    def test_n_pendientes_cobro(self):
        self.assertEqual(self.kpis["n_pendientes_cobro"], 25)

    def test_pendiente_pago(self):
        self.assertEqual(self.kpis["pendiente_pago"], 3)


# ── TestSubDashboardVacio ─────────────────────────────────────────────────

class TestSubDashboardVacio(unittest.TestCase):
    """Sub-dashboards vacíos ({} o None) no lanzan excepción; aporte = 0."""

    def test_None_no_lanza(self):
        try:
            r = build_finanzas_dashboard(None, None, None, None, None, **PERIODO)
        except Exception as exc:
            self.fail(f"Lanzó excepción con sub-dashboards None: {exc}")
        self.assertAlmostEqual(r["kpis"]["utilidad_devengada"], 0.0, places=1)

    def test_dict_vacio_no_lanza(self):
        try:
            r = build_finanzas_dashboard({}, {}, {}, {}, {}, **PERIODO)
        except Exception as exc:
            self.fail(f"Lanzó excepción con dicts vacíos: {exc}")
        self.assertAlmostEqual(r["kpis"]["flujo_caja_neto"], 0.0, places=1)

    def test_parcialmente_vacio(self):
        r = _build(compras={}, pagos_proveedores={})
        # Sin compras ni pagos → egresos provienen solo de gastos
        self.assertAlmostEqual(r["kpis"]["egreso_devengado_compras"], 0.0, places=1)
        self.assertAlmostEqual(r["kpis"]["egreso_caja_pagos"], 0.0, places=1)

    def test_temporal_vacio_devuelve_dict_vacio(self):
        r = build_finanzas_dashboard({}, {}, {}, {}, {}, **PERIODO)
        self.assertFalse(r["series"]["temporal"])  # {} es falsy


# ── TestSignalsConsolidadas ───────────────────────────────────────────────

class TestSignalsConsolidadas(unittest.TestCase):
    def test_signals_concatenadas(self):
        sig_fac = [{"id": "f1", "tipo": "factura_duplicada"}]
        sig_cob = [{"id": "c1", "tipo": "cobro_sin_factura"}, {"id": "c2", "tipo": "cobranza_lenta"}]
        sig_pag = [{"id": "p1", "tipo": "pago_pendiente"}]
        r = _build(
            facturacion={**_fac(), "signals": sig_fac},
            cobranza={**_cob(), "signals": sig_cob},
            pagos_proveedores={**_pag(), "signals": sig_pag},
        )
        self.assertEqual(r["kpis"]["n_signals"], 4)
        self.assertEqual(len(r["signals"]), 4)

    def test_signals_vacias(self):
        r = _build()
        self.assertEqual(r["kpis"]["n_signals"], 0)
        self.assertEqual(r["signals"], [])


# ── TestTablas ────────────────────────────────────────────────────────────

class TestTablas(unittest.TestCase):
    def setUp(self):
        self.result = _build(
            facturacion=_fac(monto_vigente=1000),
            compras=_com(tot_fc=600),
            gastos_operativos=_gas(total_total=200),
            cobranza=_cob(monto_cobrado=700),
            pagos_proveedores=_pag(monto_total=400),
        )
        self.tables = self.result["tables"]

    def test_comparativo_tiene_3_filas(self):
        self.assertEqual(len(self.tables["comparativo"]), 3)

    def test_comparativo_resultado_devengado(self):
        resultado = next(r for r in self.tables["comparativo"] if r["concepto"] == "Resultado")
        self.assertAlmostEqual(resultado["devengado"], 200.0, places=1)  # 1000-800

    def test_comparativo_resultado_caja(self):
        resultado = next(r for r in self.tables["comparativo"] if r["concepto"] == "Resultado")
        self.assertAlmostEqual(resultado["caja"], 100.0, places=1)  # 700-600

    def test_waterfall_devengado_tiene_4_filas(self):
        self.assertEqual(len(self.tables["waterfall_devengado"]), 4)

    def test_waterfall_utilidad_es_total(self):
        utilidad = next(r for r in self.tables["waterfall_devengado"] if r["tipo"] == "total")
        self.assertAlmostEqual(utilidad["monto"], 200.0, places=1)

    def test_waterfall_egresos_negativos(self):
        for row in self.tables["waterfall_devengado"]:
            if row["tipo"] == "egreso":
                self.assertLessEqual(row["monto"], 0, f"'{row['concepto']}' debería ser negativo")

    def test_waterfall_caja_tiene_4_filas(self):
        self.assertEqual(len(self.tables["waterfall_caja"]), 4)

    def test_waterfall_caja_flujo_es_total(self):
        flujo = next(r for r in self.tables["waterfall_caja"] if r["tipo"] == "total")
        self.assertAlmostEqual(flujo["monto"], self.result["kpis"]["flujo_caja_neto"], places=1)

    def test_waterfall_caja_egresos_negativos(self):
        for row in self.tables["waterfall_caja"]:
            if row["tipo"] == "egreso":
                self.assertLessEqual(row["monto"], 0, f"'{row['concepto']}' debería ser negativo")

    def test_iva_split_tiene_3_filas(self):
        self.assertEqual(len(self.tables["iva_split"]), 3)

    def test_iva_split_tipos(self):
        tipos = {r["tipo"] for r in self.tables["iva_split"]}
        self.assertEqual(tipos, {"Trasladado", "Acreditable", "Por pagar"})


# ── TestDatosReales ───────────────────────────────────────────────────────

class TestDatosReales(unittest.TestCase):
    """Verifica coherencia con los datos reales de mayo 2026 de los snapshots."""

    def setUp(self):
        self.result = _build(
            facturacion=_fac(monto_vigente=1_164_587.51),
            cobranza=_cob(monto_cobrado=735_727.62, pendiente=954_180.48, n_pendientes=115),
            compras=_com(tot_fc=642_953.04, iva_fc=69_121.47),
            pagos_proveedores=_pag(monto_total=610_376.88, n_pendientes=1),
            gastos_operativos=_gas(total_total=197_626.14, iva_acreditable=19_065.59),
        )
        self.kpis = self.result["kpis"]

    def test_utilidad_devengada(self):
        # 1,164,587.51 - (642,953.04 + 197,626.14)
        self.assertAlmostEqual(self.kpis["utilidad_devengada"], 324_008.33, places=0)

    def test_flujo_caja_neto(self):
        # 735,727.62 - (610,376.88 + 197,626.14)
        self.assertAlmostEqual(self.kpis["flujo_caja_neto"], -72_275.40, places=0)

    def test_pendiente_cobro(self):
        self.assertAlmostEqual(self.kpis["pendiente_cobro"], 954_180.48, places=0)

    def test_iva_acreditable_compras_mas_gastos(self):
        self.assertAlmostEqual(self.kpis["iva_acreditable"], 88_187.06, places=0)

    def test_iva_trasladado_positivo(self):
        self.assertGreater(self.kpis["iva_trasladado"], 0)


if __name__ == "__main__":
    unittest.main()
