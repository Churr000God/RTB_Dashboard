import unittest
from rtb_analisis import build_compras_dashboard

FC_BASE = [
    {"Factura_compra_subtotal": "1000", "Fcatura_compra_iva": "160",
     "Factura_compra_envio": "0", "Factura_compra_total": "1160",
     "Facatura_compra_fecha_factura": "2026-05-10",
     "Factura_compra_nombre": "PROA", "Factura_compra_tipo": "",
     "Factura_compra_uso_cfdi": "G03", "Factura_compra_estatus_factura": "Facturada"},
    {"Factura_compra_subtotal": "2000", "Fcatura_compra_iva": "320",
     "Factura_compra_envio": "0", "Factura_compra_total": "2320",
     "Facatura_compra_fecha_factura": "2026-05-15",
     "Factura_compra_nombre": "PROB", "Factura_compra_tipo": "",
     "Factura_compra_uso_cfdi": "G03", "Factura_compra_estatus_factura": "Sin status"},
    {"Factura_compra_subtotal": "500", "Fcatura_compra_iva": "80",
     "Factura_compra_envio": "0", "Factura_compra_total": "580",
     "Facatura_compra_fecha_factura": "2026-05-20",
     "Factura_compra_nombre": "PROC", "Factura_compra_tipo": "",
     "Factura_compra_uso_cfdi": "G01", "Factura_compra_estatus_factura": "Facturada"},
    {"Factura_compra_subtotal": "300", "Fcatura_compra_iva": "48",
     "Factura_compra_envio": "0", "Factura_compra_total": "348",
     "Facatura_compra_fecha_factura": "2026-05-25",
     "Factura_compra_nombre": "PROC", "Factura_compra_tipo": "",
     "Factura_compra_uso_cfdi": "G01", "Factura_compra_estatus_factura": "Factura Cancelada"},
]


class TestBuildComprasDashboard(unittest.TestCase):

    def setUp(self):
        self.result = build_compras_dashboard(
            FC_BASE,
            period_label="Test",
            fecha_desde="2026-05-01",
            fecha_hasta="2026-05-31",
        )
        self.kpis = self.result["kpis"]
        self.series = self.result["series"]
        self.tables = self.result["tables"]

    def test_firma_sin_fcp(self):
        """La función acepta solo fc sin parámetro fcp."""
        r = build_compras_dashboard(FC_BASE)
        self.assertIn("kpis", r)

    def test_exclusion_canceladas_en_totales(self):
        # Activas: row1 (sub=1000) + row2 (sub=2000) + row3 (sub=500) = 3500
        self.assertEqual(self.kpis["n_fc"], 3)
        self.assertAlmostEqual(self.kpis["sub_fc"], 3500.0, places=1)
        self.assertAlmostEqual(self.kpis["iva_fc"], 560.0, places=1)
        self.assertAlmostEqual(self.kpis["tot_fc"], 4060.0, places=1)

    def test_iva_real_y_diferencia(self):
        # Subtotal 3500 × 16% = 560; IVA recibido 560 → diff 0, pct 0
        self.assertAlmostEqual(self.kpis["iva_real_fc"], 560.0, places=1)
        self.assertAlmostEqual(self.kpis["iva_diff_fc"], 0.0, places=1)
        self.assertAlmostEqual(self.kpis["iva_diff_pct_fc"], 0.0, places=4)

    def test_kpis_canceladas(self):
        self.assertEqual(self.kpis["n_canc"], 1)
        self.assertAlmostEqual(self.kpis["tot_canc"], 348.0, places=1)

    def test_estado_factura_incluye_canceladas(self):
        estados = {e["estado"]: e["n"] for e in self.series["estado_factura"]}
        self.assertIn("Factura Cancelada", estados)
        self.assertEqual(estados["Factura Cancelada"], 1)
        self.assertIn("Facturada", estados)
        self.assertEqual(estados["Facturada"], 2)
        self.assertIn("Sin status", estados)
        self.assertEqual(estados["Sin status"], 1)

    def test_top_proveedores_excluye_canceladas(self):
        prov = {p["proveedor"]: p["n"] for p in self.tables["top_proveedores"]}
        # PROC tiene 1 Facturada y 1 Cancelada; solo debe contar 1
        self.assertEqual(prov.get("PROC", 0), 1)

    def test_uso_cfdi_excluye_canceladas(self):
        cfdi = {c["cfdi"]: c["n"] for c in self.series["uso_cfdi"]}
        # G01 tiene 1 Facturada y 1 Cancelada; solo debe contar 1
        self.assertEqual(cfdi.get("G03", 0), 2)
        self.assertEqual(cfdi.get("G01", 0), 1)

    def test_temporal_excluye_canceladas(self):
        total_n = sum(p["n"] for p in self.series["temporal"]["periodos"])
        self.assertEqual(total_n, 3)

    def test_payload_sin_claves_obsoletas(self):
        claves_obsoletas = [
            "cxp", "n_no_pag", "t_pago_avg", "t_pago_med", "t_pago_max",
            "pct_pagado", "n_fcp", "sub_fcp", "tot_fcp",
        ]
        for c in claves_obsoletas:
            self.assertNotIn(c, self.kpis, f"Clave obsoleta encontrada en kpis: {c}")
        self.assertNotIn("credito_vivo", self.tables)
        self.assertNotIn("top_proveedores_pag", self.tables)
        self.assertNotIn("status_pago", self.series)
        self.assertNotIn("tipo_pago", self.series)

    def test_tipo_compra_default_productos_vendibles(self):
        tipos = {t["tipo"]: t["n"] for t in self.series["tipo_compra"]}
        self.assertIn("Productos vendibles", tipos)

    def test_tipo_compra_excluye_canceladas(self):
        total_tp = sum(t["n"] for t in self.series["tipo_compra"])
        self.assertEqual(total_tp, 3)


    def test_alerta_iva_exige_monto_y_porcentaje_material(self):
        leve = build_compras_dashboard([
            _fc("F1", 1160.50, "2026-05-10", subtotal=1000, iva=160.50),
        ], fecha_desde="2026-05-01", fecha_hasta="2026-05-31")
        material = build_compras_dashboard([
            _fc("F1", 1261, "2026-05-10", subtotal=1000, iva=261),
        ], fecha_desde="2026-05-01", fecha_hasta="2026-05-31")
        self.assertFalse(leve["kpis"]["iva_alerta"])
        self.assertTrue(material["kpis"]["iva_alerta"])


class TestComprasGerencial(unittest.TestCase):
    def test_periodos_fuera_de_cobertura_no_participan_en_tendencia(self):
        rows = [_fc("M1", 1160, "2026-05-10"), _fc("M2", 2320, "2026-06-03")]
        result = build_compras_dashboard(rows, fecha_desde="2026-01-01", fecha_hasta="2026-12-31")
        periods = {p["key"]: p for p in result["series"]["temporal"]["periodos"]}
        self.assertEqual(periods["2026-04"]["coverage"], "sin_cobertura")
        self.assertEqual(periods["2026-05"]["coverage"], "completo")
        self.assertEqual(periods["2026-06"]["coverage"], "parcial")
        self.assertEqual(periods["2026-07"]["coverage"], "sin_cobertura")
        self.assertEqual(result["series"]["temporal"]["tendencias"], {})

    def test_cero_entre_periodos_con_datos_es_cero_real(self):
        rows = [_fc("A1", 1160, "2026-04-10"), _fc("C1", 3480, "2026-06-10")]
        result = build_compras_dashboard(rows, fecha_desde="2026-04-01", fecha_hasta="2026-06-30")
        periods = {p["key"]: p for p in result["series"]["temporal"]["periodos"]}
        self.assertEqual(periods["2026-05"]["coverage"], "completo")
        self.assertEqual(periods["2026-05"]["tot"], 0)

    def test_compara_los_dos_ultimos_periodos_completos(self):
        rows = [
            _fc("A1", 1160, "2026-04-10"),
            _fc("B1", 1740, "2026-05-10"),
            _fc("B2", 1740, "2026-05-20"),
            _fc("C1", 9999, "2026-06-03"),
        ]
        result = build_compras_dashboard(rows, fecha_desde="2026-04-01", fecha_hasta="2026-06-30")
        comparison = result["management"]["comparison"]
        self.assertEqual(comparison["previous_key"], "2026-04")
        self.assertEqual(comparison["current_key"], "2026-05")
        self.assertAlmostEqual(comparison["amount_change_pct"], 2.0, places=4)
        self.assertAlmostEqual(comparison["quantity_change_pct"], 1.0, places=4)

    def test_consolida_proveedor_por_numero_factura_y_uuid(self):
        rows = [
            _fc("F 100", 1160, "2026-05-10"),
            _fc("7CFD9F18-1234-5678-9012-123456789ABC", 2320, "2026-05-11"),
        ]
        rows[0]["Factura_compra_nombre"] = "PROVEEDOR UNO - F 100"
        rows[1]["Factura_compra_nombre"] = "PROVEEDOR UNO - 7CFD9F18-1234-5678-9012-123456789ABC"
        result = build_compras_dashboard(rows, fecha_desde="2026-05-01", fecha_hasta="2026-05-31")
        self.assertEqual(result["tables"]["top_proveedores"][0]["proveedor"], "PROVEEDOR UNO")
        self.assertEqual(result["tables"]["top_proveedores"][0]["n"], 2)

    def test_concentracion_expone_top_uno_y_top_cinco(self):
        rows = [_fc("A", 5000, "2026-05-10"), _fc("B", 3000, "2026-05-11"), _fc("C", 2000, "2026-05-12")]
        for row, provider in zip(rows, ["Proveedor A", "Proveedor B", "Proveedor C"]):
            row["Factura_compra_nombre"] = provider
        result = build_compras_dashboard(rows, fecha_desde="2026-05-01", fecha_hasta="2026-05-31")
        concentration = result["management"]["concentration"]
        self.assertEqual(concentration["top_provider"], "Proveedor A")
        self.assertAlmostEqual(concentration["top1_pct"], 0.5, places=4)
        self.assertAlmostEqual(concentration["top5_pct"], 1.0, places=4)
        self.assertAlmostEqual(result["tables"]["top_proveedores"][0]["pct"], 0.5, places=4)


def _fc(numero, total, fecha, estado="Facturada", anticipos="[]", subtotal=None, iva=None):
    sub = total / 1.16 if subtotal is None else subtotal
    iv = total - sub if iva is None else iva
    return {
        "Factura_compra_subtotal": str(sub),
        "Fcatura_compra_iva": str(iv),
        "Factura_compra_envio": "0",
        "Factura_compra_total": str(total),
        "Facatura_compra_fecha_factura": fecha,
        "Factura_compra_nombre": f"PRV - {numero}",
        "#_Factura_compra": numero,
        "Factura_compra_tipo": "",
        "Factura_compra_uso_cfdi": "G03",
        "Factura_compra_estatus_factura": estado,
        "Factura_Anticipo_Asociada": anticipos,
    }


def _ant(aid, monto, fecha, estado="Procesada", numero="DOC-1"):
    return {
        "Factura_anticipo_id": aid,
        "Factura_anticipo_nombre": f"PRV - {numero}",
        "Factura_anticipo_Proveedor_Siglas": "PRV-X",
        "Factura_anticipo_Proveedor_nombre": "Proveedor X",
        "Factura_anticipo_numero_documento": numero,
        "Factura_anticipo_fecha_emision": fecha,
        "Factura_anticipo_estado": estado,
        "Factura_anticipo_monto": str(monto),
        "Factura_anticipo_tipo_documento": "Factura de Anticipo",
        "Factura_anticipo_uso_CFDI": "G01",
    }


class TestAnticiposEnCompras(unittest.TestCase):
    PERIODO = dict(fecha_desde="2026-05-01", fecha_hasta="2026-06-30")

    def test_anticipo_pendiente_sin_factura(self):
        fc = [_fc("F1", 1160, "2026-05-10")]
        ant = [_ant("A1", 5800, "2026-05-15")]
        r = build_compras_dashboard(fc, anticipos=ant, **self.PERIODO)
        self.assertEqual(r["anticipos"]["kpis"]["n_ant_pendientes"], 1)
        self.assertEqual(r["anticipos"]["kpis"]["n_ant_regularizados"], 0)
        self.assertAlmostEqual(r["anticipos"]["kpis"]["monto_pendientes"], 5800.0, places=1)

    def test_anticipo_regularizado_por_factura(self):
        fc = [_fc("F1", 1160, "2026-06-01", anticipos='["A1"]')]
        ant = [_ant("A1", 1160, "2026-05-15")]
        r = build_compras_dashboard(fc, anticipos=ant, **self.PERIODO)
        self.assertEqual(r["anticipos"]["kpis"]["n_ant_regularizados"], 1)
        self.assertEqual(r["anticipos"]["kpis"]["n_ant_pendientes"], 0)

    def test_factura_array_vacio_no_afecta(self):
        fc = [_fc("F1", 1160, "2026-05-10", anticipos="[]")]
        ant = [_ant("A1", 5800, "2026-05-15")]
        r = build_compras_dashboard(fc, anticipos=ant, **self.PERIODO)
        self.assertEqual(r["anticipos"]["kpis"]["n_ant_pendientes"], 1)

    def test_factura_con_dos_anticipos(self):
        fc = [_fc("F1", 2320, "2026-06-01", anticipos='["A1","A2"]')]
        ant = [_ant("A1", 1160, "2026-05-15"), _ant("A2", 1160, "2026-05-20")]
        r = build_compras_dashboard(fc, anticipos=ant, **self.PERIODO)
        self.assertEqual(r["anticipos"]["kpis"]["n_ant_regularizados"], 2)
        self.assertEqual(r["anticipos"]["kpis"]["n_ant_pendientes"], 0)

    def test_anticipo_fuera_de_periodo_excluido(self):
        fc = [_fc("F1", 1160, "2026-05-10")]
        ant = [_ant("A1", 5800, "2026-04-15")]  # fuera del periodo (mayo-jun)
        r = build_compras_dashboard(fc, anticipos=ant, **self.PERIODO)
        self.assertEqual(r["anticipos"]["kpis"]["n_ant"], 0)

    def test_compatibilidad_sin_anticipos(self):
        fc = [_fc("F1", 1160, "2026-05-10")]
        r = build_compras_dashboard(fc, **self.PERIODO)
        self.assertEqual(r["anticipos"]["kpis"]["n_ant"], 0)
        self.assertEqual(r["anticipos"]["temporal"]["periodos"], [])

    def test_factura_cancelada_no_regulariza(self):
        fc = [_fc("F1", 1160, "2026-06-01", estado="Factura Cancelada", anticipos='["A1"]')]
        ant = [_ant("A1", 1160, "2026-05-15")]
        r = build_compras_dashboard(fc, anticipos=ant, **self.PERIODO)
        self.assertEqual(r["anticipos"]["kpis"]["n_ant_pendientes"], 1)
        self.assertEqual(r["anticipos"]["kpis"]["n_ant_regularizados"], 0)

    def test_serie_temporal_apilada_por_mes_de_emision(self):
        # Anticipo emitido en mayo regularizado por factura de junio → aparece en mayo.
        fc = [_fc("F1", 4023.14, "2026-06-01", anticipos='["A1"]')]
        ant = [_ant("A1", 4023.14, "2026-05-27")]
        r = build_compras_dashboard(fc, anticipos=ant, **self.PERIODO)
        periodos = {p["key"]: p for p in r["anticipos"]["temporal"]["periodos"]}
        self.assertAlmostEqual(periodos["2026-05"]["monto_pendiente"], 0.0, places=1)
        self.assertAlmostEqual(periodos["2026-05"]["monto_regularizado"], 4023.14, places=1)
        # Junio está en el eje pero sin anticipos emitidos → todo cero.
        self.assertAlmostEqual(periodos["2026-06"]["monto_pendiente"], 0.0, places=1)
        self.assertAlmostEqual(periodos["2026-06"]["monto_regularizado"], 0.0, places=1)

    def test_factura_fuera_de_periodo_aun_regulariza(self):
        # La factura definitiva cae en julio (fuera del rango may-jun), el anticipo en mayo.
        # El anticipo NO debe contarse como pendiente: referenced_ids usa TODO el CSV.
        fc = [_fc("F1", 1160, "2026-07-15", anticipos='["A1"]')]
        ant = [_ant("A1", 1160, "2026-05-15")]
        r = build_compras_dashboard(fc, anticipos=ant, **self.PERIODO)
        self.assertEqual(r["anticipos"]["kpis"]["n_ant_pendientes"], 0)
        self.assertEqual(r["anticipos"]["kpis"]["n_ant_regularizados"], 1)

    def test_json_malformado_en_anticipo_asociado(self):
        fc = [_fc("F1", 1160, "2026-05-10", anticipos='no es JSON')]
        ant = [_ant("A1", 5800, "2026-05-15")]
        r = build_compras_dashboard(fc, anticipos=ant, **self.PERIODO)
        # JSON malformado → tratado como sin anticipos; A1 queda pendiente.
        self.assertEqual(r["anticipos"]["kpis"]["n_ant_pendientes"], 1)

    def test_tabla_anticipos_expone_factura_asociada(self):
        fc = [_fc("F1", 1160, "2026-06-01", anticipos='["A1"]')]
        ant = [_ant("A1", 1160, "2026-05-15", numero="ANT-99")]
        r = build_compras_dashboard(fc, anticipos=ant, **self.PERIODO)
        tabla = r["anticipos"]["tabla"]
        self.assertEqual(len(tabla), 1)
        self.assertEqual(tabla[0]["numero_documento"], "ANT-99")
        self.assertTrue(tabla[0]["regularizado"])
        self.assertEqual(tabla[0]["factura_asociada_numero"], "F1")


if __name__ == "__main__":
    unittest.main()
