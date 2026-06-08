import unittest
from rtb_analisis import (
    build_logistica_dashboard,
    find_latest_logistica_csvs,
    _RE_PED_APROBADOS,
    _RE_PED_ENVIADOS,
    _RE_PED_ENTREGADOS,
    _RE_SEG_INCOMPLETOS,
)

PERIODO = {"fecha_desde": "2026-05-01", "fecha_hasta": "2026-05-31"}


# ─── Factories de filas CSV ───────────────────────────────────────────────────

def _pedido_aprobado(**kw):
    base = {
        "Pedidos_Aprbados_En_El_Periodo_id":                       "uuid-ap-001",
        "Pedidos_Aprbados_En_El_Periodo_nombre":                   "PP-CLIENTE*001",
        "Pedidos_Aprbados_En_El_Periodo_total":                    "5000.00",
        "Pedidos_Aprbados_En_El_Periodo_potcentaje_pedido_empacado": "100%",
        "Pedidos_Aprbados_En_El_Periodo_#_factura":                "C5900",
        "Pedidos_Aprbados_En_El_Periodo_fecha_envio":              '{"start":"2026-05-10","end":null,"time_zone":null}',
        "Pedidos_Aprbados_En_El_Periodo_tipo_envio":               "Local",
        "Pedidos_Aprbados_En_El_Periodo_estado_pedido":            "Entregado",
        "Pedidos_Aprbados_En_El_Periodo_tiene_faltante":           "false",
        "Pedidos_Aprbados_En_El_Periodo_cliente":                  "CLIENTE A",
        "Pedidos_Aprbados_En_El_Periodo_fecha_entrega":            '{"start":"2026-05-12","end":null,"time_zone":null}',
        "Pedidos_Aprbados_En_El_Periodo_fecha_de_aprobacion.start": "2026-05-08T10:00:00.000-06:00",
        "Pedidos_Aprbados_En_El_Periodo_fecha_de_aprobacion.end":  None,
        "Pedidos_Aprbados_En_El_Periodo_fecha_de_aprobacion.time_zone": None,
        "Pedidos_Aprbados_En_El_Periodo_cotizacion.0":             "uuid-cot-001",
        "Pedidos_Aprbados_En_El_Periodo_#_nr":                     "N.R. 42",
        "Pedidos_Aprbados_En_El_Periodo_direccion_de_entrega.0":   "@Hotel Ejemplo",
    }
    base.update(kw)
    return base


def _pedido_enviado(**kw):
    base = {
        "Pedidos_Enviados_En_El_Periodo_id":                       "uuid-en-001",
        "Pedidos_Enviados_En_El_Periodo_nombre":                   "PP-CLIENTE*001",
        "Pedidos_Enviados_En_El_Periodo_total":                    "5000.00",
        "Pedidos_Enviados_En_El_Periodo_potcentaje_pedido_empacado": "100%",
        "Pedidos_Enviados_En_El_Periodo_#_factura":                "C5900",
        "Pedidos_Enviados_En_El_Periodo_fecha_envio":              '{"start":"2026-05-10","end":null,"time_zone":null}',
        "Pedidos_Enviados_En_El_Periodo_tipo_envio":               "Local",
        "Pedidos_Enviados_En_El_Periodo_estado_pedido":            "Entregado",
        "Pedidos_Enviados_En_El_Periodo_tiene_faltante":           "false",
        "Pedidos_Enviados_En_El_Periodo_cliente":                  "CLIENTE A",
        "Pedidos_Enviados_En_El_Periodo_fecha_entrega":            '{"start":"2026-05-12","end":null,"time_zone":null}',
        "Pedidos_Enviados_En_El_Periodo_fecha_de_aprobacion.start": "2026-05-08T10:00:00.000-06:00",
        "Pedidos_Enviados_En_El_Periodo_fecha_de_aprobacion.end":  None,
        "Pedidos_Enviados_En_El_Periodo_fecha_de_aprobacion.time_zone": None,
        "Pedidos_Enviados_En_El_Periodo_cotizacion.0":             "uuid-cot-001",
        "Pedidos_Enviados_En_El_Periodo_#_nr":                     "N.R. 42",
        "Pedidos_Enviados_En_El_Periodo_direccion_de_entrega.0":   "@Hotel Ejemplo",
        "Pedidos_Enviados_En_El_Periodo_fecha_de_aprobacion":      "2026-05-08T10:00:00.000-06:00",
    }
    base.update(kw)
    return base


def _pedido_entregado(**kw):
    base = {
        "Pedidos_Entregados_En_El_Periodo_id":                       "uuid-et-001",
        "Pedidos_Entregados_En_El_Periodo_nombre":                   "PP-CLIENTE*001",
        "Pedidos_Entregados_En_El_Periodo_total":                    "5000.00",
        "Pedidos_Entregados_En_El_Periodo_potcentaje_pedido_empacado": "100%",
        "Pedidos_Entregados_En_El_Periodo_#_factura":                "C5900",
        "Pedidos_Entregados_En_El_Periodo_fecha_envio":              '{"start":"2026-05-10","end":null,"time_zone":null}',
        "Pedidos_Entregados_En_El_Periodo_tipo_envio":               "Local",
        "Pedidos_Entregados_En_El_Periodo_estado_pedido":            "Entregado",
        "Pedidos_Entregados_En_El_Periodo_tiene_faltante":           "false",
        "Pedidos_Entregados_En_El_Periodo_cliente":                  "CLIENTE A",
        "Pedidos_Entregados_En_El_Periodo_fecha_entrega":            "2026-05-12T15:00:00.000-06:00",
        "Pedidos_Entregados_En_El_Periodo_fecha_de_aprobacion.start": "2026-05-08T10:00:00.000-06:00",
        "Pedidos_Entregados_En_El_Periodo_fecha_de_aprobacion.end":  None,
        "Pedidos_Entregados_En_El_Periodo_fecha_de_aprobacion.time_zone": None,
        "Pedidos_Entregados_En_El_Periodo_cotizacion.0":             "uuid-cot-001",
        "Pedidos_Entregados_En_El_Periodo_#_nr":                     "N.R. 42",
        "Pedidos_Entregados_En_El_Periodo_direccion_de_entrega.0":   "@Hotel Ejemplo",
        "Pedidos_Entregados_En_El_Periodo_fecha_de_aprobacion":      "2026-05-08T10:00:00.000-06:00",
    }
    base.update(kw)
    return base


def _seg(**kw):
    base = {
        "Segimiento_pedidos_entregados_incompletos_id":    "uuid-seg-001",
        "Segimiento_pedidos_entregados_incompletos_name":  "PP-FIAPT*001",
        # Campo con clave malformada (prefijo duplicado sin separador — bug de n8n)
        "Segimiento_pedidos_entregados_incompletosSegimiento_pedidos_entregados_incompletos_fecha_del_pedido":
            "2026-05-10T00:00:00.000Z",
        "Segimiento_pedidos_entregados_incompletos_notas_adicionales":       "",
        "Segimiento_pedidos_entregados_incompletos_prioridad":               "",
        "Segimiento_pedidos_entregados_incompletos_cliente":                 "FIAPT",
        "Segimiento_pedidos_entregados_incompletos_estado":                  "Pendiente",
        "Segimiento_pedidos_entregados_incompletos_cotizacion.0":            "uuid-cot-001",
        "Segimiento_pedidos_entregados_incompletos_fecha_estimada_de_resoluci_n": "",
        "Segimiento_pedidos_entregados_incompletos_fecha_de_creaci_n":       "2026-05-10T01:09:00.000Z",
        "Segimiento_pedidos_entregados_incompletos_productos_faltantes.0":   "REGULADOR FLUJO 1.5 GPM",
        "Segimiento_pedidos_entregados_incompletos_pedido_faltante.0":       "uuid-ped-001",
        "Segimiento_pedidos_entregados_incompletos_motivo_de_incompletitud": "",
    }
    base.update(kw)
    return base


# ─── Allowlist regex ──────────────────────────────────────────────────────────

class TestAllowlistRegex(unittest.TestCase):

    def test_aprobados_valido(self):
        self.assertTrue(_RE_PED_APROBADOS.match("Pedidos_Aprbados_En_El_Periodo_2026-05-15_09-30.csv"))

    def test_aprobados_sin_timestamp(self):
        self.assertIsNone(_RE_PED_APROBADOS.match("Pedidos_Aprbados_En_El_Periodo_.csv"))

    def test_aprobados_otro_prefijo(self):
        self.assertIsNone(_RE_PED_APROBADOS.match("Pedidos_Entregados_En_El_Periodo_2026-05-15_09-30.csv"))

    def test_aprobados_prefijo_similar(self):
        self.assertIsNone(_RE_PED_APROBADOS.match("Pedidos_Aprobados_En_El_Periodo_2026-05-15_09-30.csv"))

    def test_enviados_valido(self):
        self.assertTrue(_RE_PED_ENVIADOS.match("Pedidos_Enviados_En_El_Periodo_2026-06-08_11-40.csv"))

    def test_enviados_rechaza_aprobados(self):
        self.assertIsNone(_RE_PED_ENVIADOS.match("Pedidos_Aprbados_En_El_Periodo_2026-06-08_11-30.csv"))

    def test_entregados_valido(self):
        self.assertTrue(_RE_PED_ENTREGADOS.match("Pedidos_Entregados_En_El_Periodo_2026-06-08_11-43.csv"))

    def test_entregados_rechaza_enviados(self):
        self.assertIsNone(_RE_PED_ENTREGADOS.match("Pedidos_Enviados_En_El_Periodo_2026-06-08_11-40.csv"))

    def test_seguimiento_valido(self):
        self.assertTrue(_RE_SEG_INCOMPLETOS.match("Segimiento_pedidos_entregados_incompletos_2026-06-08_11-46.csv"))

    def test_seguimiento_sin_timestamp(self):
        self.assertIsNone(_RE_SEG_INCOMPLETOS.match("Segimiento_pedidos_entregados_incompletos_.csv"))

    def test_seguimiento_rechaza_entregados(self):
        self.assertIsNone(_RE_SEG_INCOMPLETOS.match("Pedidos_Entregados_En_El_Periodo_2026-06-08_11-43.csv"))


# ─── KPIs basicos ─────────────────────────────────────────────────────────────

class TestKpisBasicos(unittest.TestCase):

    def setUp(self):
        self.ap = [
            _pedido_aprobado(),
            _pedido_aprobado(**{"Pedidos_Aprbados_En_El_Periodo_id": "uuid-ap-002",
                                "Pedidos_Aprbados_En_El_Periodo_total": "3000.00",
                                "Pedidos_Aprbados_En_El_Periodo_estado_pedido": "Preparado"}),
        ]
        self.en = [_pedido_enviado()]
        self.et = [
            _pedido_entregado(),
            _pedido_entregado(**{"Pedidos_Entregados_En_El_Periodo_id": "uuid-et-002",
                                 "Pedidos_Entregados_En_El_Periodo_total": "2000.00",
                                 "Pedidos_Entregados_En_El_Periodo_potcentaje_pedido_empacado": "80%",
                                 "Pedidos_Entregados_En_El_Periodo_tiene_faltante": "true"}),
        ]
        self.result = build_logistica_dashboard(
            self.ap, self.en, self.et, [],
            period_label="mayo 2026", **PERIODO,
        )
        self.kpis = self.result["kpis"]

    def test_n_aprobados(self):
        self.assertEqual(self.kpis["n_aprobados"], 2)

    def test_n_enviados(self):
        self.assertEqual(self.kpis["n_enviados"], 1)

    def test_n_entregados(self):
        self.assertEqual(self.kpis["n_entregados"], 2)

    def test_monto_entregado(self):
        self.assertAlmostEqual(self.kpis["monto_entregado"], 7000.00, places=1)

    def test_n_con_faltante(self):
        self.assertEqual(self.kpis["n_con_faltante"], 1)

    def test_pct_faltante(self):
        self.assertAlmostEqual(self.kpis["pct_faltante"], 0.5, places=3)

    def test_pct_empacado_prom(self):
        # (100 + 80) / 2 = 90
        self.assertAlmostEqual(self.kpis["pct_empacado_prom"], 90.0, places=1)

    def test_estructura_retorno(self):
        for clave in ("periodo", "kpis", "series", "tables", "signals"):
            self.assertIn(clave, self.result)

    def test_series_claves(self):
        for clave in ("temporal", "estado", "tipo_envio", "lead_hist"):
            self.assertIn(clave, self.result["series"])

    def test_tables_claves(self):
        for clave in ("top_clientes", "pedidos_lentos", "incompletos"):
            self.assertIn(clave, self.result["tables"])


# ─── Lead times ───────────────────────────────────────────────────────────────

class TestLeadTimes(unittest.TestCase):

    def test_ciclo_calculado_correctamente(self):
        """aprob 2026-05-08, entrega 2026-05-12 → ciclo = 4 dias"""
        et = [_pedido_entregado()]
        r = build_logistica_dashboard([], [], et, [], **PERIODO)
        self.assertEqual(r["kpis"]["n_con_lead"], 1)
        self.assertGreater(r["kpis"]["ciclo_total_med"], 0)

    def test_ciclo_total_es_4_dias(self):
        et = [_pedido_entregado()]
        r = build_logistica_dashboard([], [], et, [], **PERIODO)
        # aprob 2026-05-08, entrega 2026-05-12 → abs = 4
        self.assertEqual(r["kpis"]["ciclo_total_med"], 4.0)

    def test_sin_fecha_aprob_no_cuenta_ciclo(self):
        et = [_pedido_entregado(**{
            "Pedidos_Entregados_En_El_Periodo_fecha_de_aprobacion.start": "",
        })]
        r = build_logistica_dashboard([], [], et, [], **PERIODO)
        self.assertEqual(r["kpis"]["n_con_lead"], 0)
        self.assertEqual(r["kpis"]["ciclo_total_med"], 0.0)

    def test_lead_ap_en_positivo(self):
        et = [_pedido_entregado()]
        r = build_logistica_dashboard([], [], et, [], **PERIODO)
        # aprob 2026-05-08 10am → envio 2026-05-10 00:00 → .days = 1 (timedelta floor)
        self.assertGreater(r["kpis"]["lead_aprob_envio_med"], 0)

    def test_lead_en_et_positivo(self):
        et = [_pedido_entregado()]
        r = build_logistica_dashboard([], [], et, [], **PERIODO)
        # envio 2026-05-10, entrega 2026-05-12 → 2 dias
        self.assertEqual(r["kpis"]["lead_envio_entrega_med"], 2.0)

    def test_sin_fecha_envio_cuenta_n_sin_fecha(self):
        et = [_pedido_entregado(**{
            "Pedidos_Entregados_En_El_Periodo_fecha_envio": "",
        })]
        r = build_logistica_dashboard([], [], et, [], **PERIODO)
        self.assertEqual(r["kpis"]["n_sin_fecha"], 1)


# ─── Filtrado de periodo ──────────────────────────────────────────────────────

class TestFiltradoPeriodo(unittest.TestCase):

    def test_entregado_fuera_de_rango_excluido(self):
        et_dentro  = _pedido_entregado()  # fecha_entrega 2026-05-12 ✓
        et_fuera   = _pedido_entregado(**{
            "Pedidos_Entregados_En_El_Periodo_id": "uuid-et-002",
            "Pedidos_Entregados_En_El_Periodo_fecha_entrega": "2026-06-15T10:00:00.000-06:00",
        })
        r = build_logistica_dashboard([], [], [et_dentro, et_fuera], [], **PERIODO)
        self.assertEqual(r["kpis"]["n_entregados"], 1)

    def test_aprobado_fuera_de_rango_excluido(self):
        ap_dentro = _pedido_aprobado()   # fecha_aprob 2026-05-08 ✓
        ap_fuera  = _pedido_aprobado(**{
            "Pedidos_Aprbados_En_El_Periodo_id": "uuid-ap-002",
            "Pedidos_Aprbados_En_El_Periodo_fecha_de_aprobacion.start": "2026-06-15T10:00:00.000-06:00",
        })
        r = build_logistica_dashboard([ap_dentro, ap_fuera], [], [], [], **PERIODO)
        self.assertEqual(r["kpis"]["n_aprobados"], 1)

    def test_sin_rango_incluye_todos(self):
        et = [
            _pedido_entregado(),
            _pedido_entregado(**{"Pedidos_Entregados_En_El_Periodo_id": "uuid-et-002",
                                 "Pedidos_Entregados_En_El_Periodo_fecha_entrega": "2026-03-01T10:00:00.000-06:00"}),
        ]
        r = build_logistica_dashboard([], [], et, [])
        # sin filtro → ambos incluidos (tienen fecha_entrega → in_period retorna True)
        self.assertEqual(r["kpis"]["n_entregados"], 2)


# ─── Series y tablas ──────────────────────────────────────────────────────────

class TestSeriesTablas(unittest.TestCase):

    def test_tipo_envio_local_en_series(self):
        et = [_pedido_entregado()]  # tipo_envio=Local
        r = build_logistica_dashboard([], [], et, [], **PERIODO)
        tipos = {t["tipo"] for t in r["series"]["tipo_envio"]}
        self.assertIn("Local", tipos)

    def test_tipo_envio_ciclo_med_calculado(self):
        et = [_pedido_entregado()]
        r = build_logistica_dashboard([], [], et, [], **PERIODO)
        local = next(t for t in r["series"]["tipo_envio"] if t["tipo"] == "Local")
        self.assertIsNotNone(local["ciclo_med"])
        self.assertGreater(local["ciclo_med"], 0)

    def test_estado_en_series(self):
        ap = [_pedido_aprobado()]   # estado=Entregado
        r = build_logistica_dashboard(ap, [], [], [], **PERIODO)
        estados = {e["estado"] for e in r["series"]["estado"]}
        self.assertIn("Entregado", estados)

    def test_top_clientes_en_tabla(self):
        et = [_pedido_entregado()]
        r = build_logistica_dashboard([], [], et, [], **PERIODO)
        self.assertGreater(len(r["tables"]["top_clientes"]), 0)
        self.assertIn("cliente", r["tables"]["top_clientes"][0])

    def test_lead_hist_6_bins(self):
        et = [_pedido_entregado()]
        r = build_logistica_dashboard([], [], et, [], **PERIODO)
        self.assertEqual(len(r["series"]["lead_hist"]), 6)

    def test_lead_hist_ciclo_4_en_bin_correcto(self):
        """ciclo 4 dias → bin '4–7 d'"""
        et = [_pedido_entregado()]
        r = build_logistica_dashboard([], [], et, [], **PERIODO)
        bins = {b["rango"]: b["n"] for b in r["series"]["lead_hist"]}
        self.assertEqual(bins.get("4–7 d"), 1)
        self.assertEqual(bins.get("0–3 d"), 0)

    def test_incompletos_pendientes_primero(self):
        seg_rows = [
            _seg(**{"Segimiento_pedidos_entregados_incompletos_estado": "Completado",
                    "Segimiento_pedidos_entregados_incompletos_id": "uuid-seg-002"}),
            _seg(),  # Pendiente
        ]
        r = build_logistica_dashboard([], [], [], seg_rows)
        tabla = r["tables"]["incompletos"]
        self.assertEqual(len(tabla), 2)
        self.assertEqual(tabla[0]["estado"], "Pendiente")
        self.assertEqual(tabla[1]["estado"], "Completado")


# ─── Senales ──────────────────────────────────────────────────────────────────

class TestSenales(unittest.TestCase):

    def test_incompletos_pendientes_genera_senal(self):
        seg_rows = [_seg()]  # estado=Pendiente
        r = build_logistica_dashboard([], [], [], seg_rows)
        tipos = [s["tipo"] for s in r["signals"]]
        self.assertIn("incompletos_pendientes", tipos)

    def test_sin_incompletos_no_genera_senal(self):
        seg_rows = [_seg(**{"Segimiento_pedidos_entregados_incompletos_estado": "Completado"})]
        r = build_logistica_dashboard([], [], [], seg_rows)
        tipos = [s["tipo"] for s in r["signals"]]
        self.assertNotIn("incompletos_pendientes", tipos)

    def test_captura_fecha_incompleta_genera_senal(self):
        et = [_pedido_entregado(**{"Pedidos_Entregados_En_El_Periodo_fecha_envio": ""})]
        r = build_logistica_dashboard([], [], et, [], **PERIODO)
        tipos = [s["tipo"] for s in r["signals"]]
        self.assertIn("captura_fecha_incompleta", tipos)

    def test_entrega_lenta_genera_senal(self):
        """Ciclo > 10 dias con 3+ pedidos → senal entrega_lenta"""
        def _et_lento(i, dias):
            return _pedido_entregado(**{
                "Pedidos_Entregados_En_El_Periodo_id": f"uuid-et-{i}",
                "Pedidos_Entregados_En_El_Periodo_fecha_de_aprobacion.start": "2026-05-01T08:00:00.000-06:00",
                "Pedidos_Entregados_En_El_Periodo_fecha_envio": '{"start":"2026-05-05","end":null,"time_zone":null}',
                "Pedidos_Entregados_En_El_Periodo_fecha_entrega": f"2026-05-{1+dias:02d}T15:00:00.000-06:00",
            })
        et = [_et_lento(i, 15) for i in range(3)]  # ciclo 15 dias cada uno
        r = build_logistica_dashboard([], [], et, [], **PERIODO)
        tipos = [s["tipo"] for s in r["signals"]]
        self.assertIn("entrega_lenta", tipos)

    def test_ciclo_corto_no_genera_senal_lenta(self):
        et = [_pedido_entregado()]  # ciclo 4 dias
        r = build_logistica_dashboard([], [], et, [], **PERIODO)
        tipos = [s["tipo"] for s in r["signals"]]
        self.assertNotIn("entrega_lenta", tipos)

    def test_pct_faltante_alto_genera_senal(self):
        et = [
            _pedido_entregado(**{"Pedidos_Entregados_En_El_Periodo_id": f"uuid-et-{i}",
                                 "Pedidos_Entregados_En_El_Periodo_tiene_faltante": "true"})
            for i in range(6)
        ]
        r = build_logistica_dashboard([], [], et, [], **PERIODO)
        tipos = [s["tipo"] for s in r["signals"]]
        self.assertIn("pedido_con_faltante", tipos)

    def test_senales_reflejadas_en_kpis_senales(self):
        seg_rows = [_seg()]
        r = build_logistica_dashboard([], [], [], seg_rows)
        self.assertEqual(r["kpis"]["senales"], len(r["signals"]))


if __name__ == "__main__":
    unittest.main()
