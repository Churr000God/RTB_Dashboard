"""Tests para el modulo rtb_pdf (generacion de PDF y ZIP).

Patron: sin FastAPI, importa rtb_pdf directamente.
Todos los tests son rapidos (generacion en memoria, sin disco).
"""
import io
import unittest
import zipfile

import rtb_pdf

# ---------------------------------------------------------------------------
# Payloads de prueba
# ---------------------------------------------------------------------------

def _sample_ventas_payload():
    return {
        "periodo": "2026-05-01 a 2026-05-31",
        "kpis": {
            "cotizaciones": 45,
            "aprobadas": 28,
            "total_cotizado": 1_250_000.50,
            "monto_aprobado": 780_000.00,
            "conversion_qty": 0.622,
            "ticket_promedio": 27_777.78,
        },
        "series": {
            "temporal": {
                "granularidad": "semana",
                "keys": ["S1", "S2", "S3", "S4", "S5"],
                "labels": ["S1", "S2", "S3", "S4", "S5"],
                "periodos": [
                    {"key": "S1", "etiqueta": "S1", "cotizaciones": 10, "monto": 300_000},
                    {"key": "S2", "etiqueta": "S2", "cotizaciones": 8,  "monto": 220_000},
                    {"key": "S3", "etiqueta": "S3", "cotizaciones": 12, "monto": 350_000},
                    {"key": "S4", "etiqueta": "S4", "cotizaciones": 9,  "monto": 250_000},
                    {"key": "S5", "etiqueta": "S5", "cotizaciones": 6,  "monto": 130_000},
                ],
            },
            "estados": [
                {"estado": "Aprobada",   "n": 28, "monto": 780_000, "color": "#276f86"},
                {"estado": "Pendiente",  "n": 12, "monto": 350_000, "color": "#d0b56b"},
                {"estado": "Rechazada",  "n": 5,  "monto": 120_000, "color": "#d96058"},
            ],
        },
        "tables": {
            "top_clientes_cotizan": [
                {"cliente": "Cliente A", "n": 8,  "monto": 400_000},
                {"cliente": "Cliente B", "n": 5,  "monto": 280_000},
                {"cliente": "Cliente C", "n": 3,  "monto": 150_000},
            ],
        },
        "signals": [
            {"tipo": "baja_conversion", "mensaje": "Conversion de monto inferior al 60%"},
        ],
    }


def _sample_facturacion_payload():
    return {
        "periodo": "2026-05-01 a 2026-05-31",
        "kpis": {
            "facturas_vigentes": 32,
            "monto_facturado_vigente": 920_000.00,
            "facturas_canceladas": 2,
        },
        "series": {
            "temporal": {
                "granularidad": "semana",
                "keys": ["S1", "S2", "S3", "S4", "S5"],
                "labels": ["S1", "S2", "S3", "S4", "S5"],
                "periodos": [
                    {"key": "S1", "etiqueta": "S1", "monto": 180_000, "cantidad": 7},
                    {"key": "S2", "etiqueta": "S2", "monto": 210_000, "cantidad": 8},
                    {"key": "S3", "etiqueta": "S3", "monto": 250_000, "cantidad": 9},
                    {"key": "S4", "etiqueta": "S4", "monto": 180_000, "cantidad": 6},
                    {"key": "S5", "etiqueta": "S5", "monto": 100_000, "cantidad": 2},
                ],
            },
        },
        "tables": {
            "facturas": [
                {"factura": "F001", "fecha": "2026-05-03", "monto": 55_000, "estado": "Aprobada"},
                {"factura": "F002", "fecha": "2026-05-10", "monto": 120_000, "estado": "Aprobada"},
            ],
        },
        "signals": [],
    }


def _empty_payload():
    return {
        "periodo": "2026-05-01 a 2026-05-31",
        "kpis": {},
        "series": {},
        "tables": {},
        "signals": [],
    }


def _minimal_payload():
    """Payload sin llaves opcionales (como si el snapshot estuviera incompleto)."""
    return {"periodo": "2026-05-01 a 2026-05-31"}


# ---------------------------------------------------------------------------
# Tests de prettify_label
# ---------------------------------------------------------------------------

class TestPrettifyLabel(unittest.TestCase):

    def test_underscore_to_space(self):
        self.assertEqual(rtb_pdf.prettify_label("monto_facturado_vigente"),
                         "Monto facturado vigente")

    def test_single_word(self):
        self.assertEqual(rtb_pdf.prettify_label("cotizaciones"), "Cotizaciones")

    def test_already_spaced(self):
        self.assertEqual(rtb_pdf.prettify_label("ticket promedio"), "Ticket promedio")

    def test_empty_string(self):
        self.assertEqual(rtb_pdf.prettify_label(""), "")

    def test_hyphen_separator(self):
        self.assertEqual(rtb_pdf.prettify_label("fecha-inicio"), "Fecha inicio")


# ---------------------------------------------------------------------------
# Tests de _slug
# ---------------------------------------------------------------------------

class TestSlug(unittest.TestCase):

    def test_basic(self):
        self.assertEqual(rtb_pdf._slug("Ventas"), "ventas")

    def test_spaces(self):
        self.assertEqual(rtb_pdf._slug("Pagos Proveedores"), "pagos_proveedores")

    def test_ampersand(self):
        self.assertEqual(rtb_pdf._slug("P&L"), "p_l")


# ---------------------------------------------------------------------------
# Tests de build_module_pdf
# ---------------------------------------------------------------------------

class TestBuildModulePdf(unittest.TestCase):

    def _assert_valid_pdf(self, data: bytes):
        self.assertIsInstance(data, bytes)
        self.assertGreater(len(data), 0)
        self.assertTrue(data.startswith(b"%PDF"), f"No empieza con %PDF: {data[:8]!r}")

    def test_ventas_payload(self):
        payload = _sample_ventas_payload()
        pdf = rtb_pdf.build_module_pdf("Ventas", payload)
        self._assert_valid_pdf(pdf)

    def test_facturacion_payload(self):
        payload = _sample_facturacion_payload()
        pdf = rtb_pdf.build_module_pdf("Facturacion", payload)
        self._assert_valid_pdf(pdf)

    def test_empty_payload_no_crash(self):
        """Un payload sin KPIs/series/tables no debe lanzar excepcion."""
        pdf = rtb_pdf.build_module_pdf("Modulo Vacio", _empty_payload())
        self._assert_valid_pdf(pdf)

    def test_minimal_payload_no_crash(self):
        """Payload sin llaves opcionales no debe lanzar excepcion."""
        pdf = rtb_pdf.build_module_pdf("Minimal", _minimal_payload())
        self._assert_valid_pdf(pdf)

    def test_pdf_not_empty_for_rich_payload(self):
        """Un payload con datos debe producir un PDF mas grande que uno vacio."""
        pdf_rich  = rtb_pdf.build_module_pdf("Ventas",        _sample_ventas_payload())
        pdf_empty = rtb_pdf.build_module_pdf("Modulo Vacio",  _empty_payload())
        self.assertGreater(len(pdf_rich), len(pdf_empty))

    def test_signals_rendered(self):
        """PDF con senales debe ser generado sin error."""
        payload = _sample_ventas_payload()
        payload["signals"] = [
            {"tipo": "baja_conversion", "mensaje": "Conversion de monto inferior al 60%"},
            {"tipo": "factura_pendiente", "mensaje": "3 facturas sin validar"},
        ]
        pdf = rtb_pdf.build_module_pdf("Con senales", payload)
        self._assert_valid_pdf(pdf)

    def test_tables_with_many_rows_truncated(self):
        """Tablas con mas de MAX_TABLE_ROWS filas no deben lanzar excepcion."""
        rows = [{"factura": f"F{i:03d}", "monto": i * 1000, "estado": "Aprobada"}
                for i in range(50)]
        payload = {
            "periodo": "2026-05",
            "kpis": {"facturas": 50},
            "series": {},
            "tables": {"facturas": rows},
            "signals": [],
        }
        pdf = rtb_pdf.build_module_pdf("Facturacion", payload)
        self._assert_valid_pdf(pdf)

    def test_series_list_of_dicts_estado(self):
        """Serie de estados renderiza sin crash."""
        payload = {
            "periodo": "2026-05",
            "kpis": {},
            "series": {
                "estados": [
                    {"estado": "Aprobada", "n": 10, "monto": 500_000},
                    {"estado": "Pendiente", "n": 5,  "monto": 200_000},
                ]
            },
            "tables": {},
            "signals": [],
        }
        pdf = rtb_pdf.build_module_pdf("Ventas", payload)
        self._assert_valid_pdf(pdf)

    def test_series_temporal_with_periodos(self):
        """Serie temporal con periodos renderiza barras sin crash."""
        payload = {
            "periodo": "2026-05",
            "kpis": {},
            "series": {
                "temporal": {
                    "granularidad": "mes",
                    "keys": ["2026-04", "2026-05"],
                    "labels": ["Abril", "Mayo"],
                    "periodos": [
                        {"key": "2026-04", "etiqueta": "Abril", "monto": 400_000},
                        {"key": "2026-05", "etiqueta": "Mayo",  "monto": 600_000},
                    ],
                }
            },
            "tables": {},
            "signals": [],
        }
        pdf = rtb_pdf.build_module_pdf("Facturacion", payload)
        self._assert_valid_pdf(pdf)


# ---------------------------------------------------------------------------
# Tests de build_combined_pdf
# ---------------------------------------------------------------------------

class TestBuildCombinedPdf(unittest.TestCase):

    def _assert_valid_pdf(self, data: bytes):
        self.assertIsInstance(data, bytes)
        self.assertGreater(len(data), 0)
        self.assertTrue(data.startswith(b"%PDF"))

    def test_two_modules(self):
        modules = [
            ("Ventas",       _sample_ventas_payload()),
            ("Facturacion",  _sample_facturacion_payload()),
        ]
        pdf = rtb_pdf.build_combined_pdf(modules)
        self._assert_valid_pdf(pdf)

    def test_single_module(self):
        modules = [("Ventas", _sample_ventas_payload())]
        pdf = rtb_pdf.build_combined_pdf(modules)
        self._assert_valid_pdf(pdf)

    def test_empty_list_returns_empty(self):
        result = rtb_pdf.build_combined_pdf([])
        self.assertEqual(result, b"")

    def test_combined_larger_than_single(self):
        single = rtb_pdf.build_module_pdf("Ventas", _sample_ventas_payload())
        combined = rtb_pdf.build_combined_pdf([
            ("Ventas",       _sample_ventas_payload()),
            ("Facturacion",  _sample_facturacion_payload()),
        ])
        self.assertGreater(len(combined), len(single))


# ---------------------------------------------------------------------------
# Tests de build_reports_zip
# ---------------------------------------------------------------------------

class TestBuildReportsZip(unittest.TestCase):

    def _load_zip(self, data: bytes) -> zipfile.ZipFile:
        buf = io.BytesIO(data)
        self.assertTrue(zipfile.is_zipfile(buf), "Los bytes no son un ZIP valido")
        buf.seek(0)
        return zipfile.ZipFile(buf)

    def test_zip_is_valid(self):
        modules = [
            ("Ventas",       _sample_ventas_payload()),
            ("Facturacion",  _sample_facturacion_payload()),
        ]
        zip_bytes = rtb_pdf.build_reports_zip(modules)
        buf = io.BytesIO(zip_bytes)
        self.assertTrue(zipfile.is_zipfile(buf))

    def test_zip_contains_combined(self):
        modules = [("Ventas", _sample_ventas_payload())]
        zf = self._load_zip(rtb_pdf.build_reports_zip(modules))
        names = zf.namelist()
        self.assertIn("_reporte_completo.pdf", names)

    def test_zip_contains_individual_pdfs(self):
        modules = [
            ("Ventas",       _sample_ventas_payload()),
            ("Facturacion",  _sample_facturacion_payload()),
        ]
        zf = self._load_zip(rtb_pdf.build_reports_zip(modules))
        names = zf.namelist()
        self.assertIn("ventas.pdf", names)
        self.assertIn("facturacion.pdf", names)

    def test_zip_individual_pdf_count(self):
        modules = [
            ("Ventas",      _sample_ventas_payload()),
            ("Facturacion", _sample_facturacion_payload()),
            ("Compras",     _empty_payload()),
        ]
        zf = self._load_zip(rtb_pdf.build_reports_zip(modules))
        individual = [n for n in zf.namelist() if n != "_reporte_completo.pdf"]
        self.assertEqual(len(individual), 3)

    def test_individual_pdfs_are_valid(self):
        modules = [("Ventas", _sample_ventas_payload())]
        zf = self._load_zip(rtb_pdf.build_reports_zip(modules))
        pdf_bytes = zf.read("ventas.pdf")
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_combined_pdf_in_zip_is_valid(self):
        modules = [("Ventas", _sample_ventas_payload())]
        zf = self._load_zip(rtb_pdf.build_reports_zip(modules))
        pdf_bytes = zf.read("_reporte_completo.pdf")
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_slug_ampersand(self):
        """El slug de 'P&L' no debe contener caracteres invalidos en nombre de archivo."""
        modules = [("P&L", _empty_payload())]
        zf = self._load_zip(rtb_pdf.build_reports_zip(modules))
        self.assertIn("p_l.pdf", zf.namelist())

    def test_spaces_in_label_become_underscore_slug(self):
        modules = [("Pagos Proveedores", _empty_payload())]
        zf = self._load_zip(rtb_pdf.build_reports_zip(modules))
        self.assertIn("pagos_proveedores.pdf", zf.namelist())


if __name__ == "__main__":
    unittest.main()
