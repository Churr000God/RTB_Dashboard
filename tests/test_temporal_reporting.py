import unittest


class TemporalReportingTests(unittest.TestCase):
    def test_temporal_axis_uses_calendar_months_when_period_crosses_month_boundary(self):
        from rtb_analisis import temporal_axis

        axis = temporal_axis("2026-04-01", "2026-06-30")

        self.assertEqual(axis["granularidad"], "mes")
        self.assertEqual(axis["keys"], ["2026-04", "2026-05", "2026-06"])
        self.assertEqual(axis["labels"], ["Abr 2026", "May 2026", "Jun 2026"])
        self.assertEqual(axis["table_heading"], "Mes")

    def test_temporal_axis_keeps_weeks_when_period_stays_in_one_month(self):
        from rtb_analisis import temporal_axis

        axis = temporal_axis("2026-04-01", "2026-04-30")

        self.assertEqual(axis["granularidad"], "semana")
        self.assertEqual(axis["keys"], ["S1", "S2", "S3", "S4", "S5"])
        self.assertEqual(axis["labels"], ["S1", "S2", "S3", "S4", "S5"])
        self.assertEqual(axis["table_heading"], "Semana")

    def test_aggregate_temporal_accepts_arbitrary_metrics_for_future_modules(self):
        from rtb_analisis import aggregate_temporal

        rows = [
            {"fecha": "2026-04-15", "total": "100", "estado": "Aprobada"},
            {"fecha": "2026-05-02", "total": "250", "estado": "Pendiente"},
        ]
        result = aggregate_temporal(
            rows,
            date_getter=lambda row: row["fecha"],
            metric_getters={
                "registros": lambda row: 1,
                "monto": lambda row: float(row["total"]),
                "aprobadas": lambda row: 1 if row["estado"] == "Aprobada" else 0,
            },
            fecha_desde="2026-04-01",
            fecha_hasta="2026-05-31",
        )

        self.assertEqual(result["granularidad"], "mes")
        self.assertEqual(result["periodos"], [
            {"key": "2026-04", "etiqueta": "Abr 2026", "registros": 1.0, "monto": 100.0, "aprobadas": 1.0},
            {"key": "2026-05", "etiqueta": "May 2026", "registros": 1.0, "monto": 250.0, "aprobadas": 0.0},
        ])

    def test_compute_exposes_shared_temporal_axis_for_all_time_based_modules(self):
        from rtb_analisis import compute

        data = {key: [] for key in ("cot", "crec", "fc", "fcp", "gas", "inv", "ms", "ped", "env", "fac", "facs", "pag", "pent")}
        period = {"start": "2026-04-01", "end": "2026-05-31"}

        result = compute(data, period=period)

        self.assertEqual(result["temporal"]["labels"], ["Abr 2026", "May 2026"])
        self.assertEqual(result["m1"]["temporal_cot"]["labels"], result["temporal"]["labels"])
        self.assertEqual(result["m2a"]["temporal_ped"]["labels"], result["temporal"]["labels"])
        self.assertEqual(result["m3"]["temporal_fc"]["labels"], result["temporal"]["labels"])
        self.assertEqual(result["m5"]["temporal_gas"]["labels"], result["temporal"]["labels"])


if __name__ == "__main__":
    unittest.main()
