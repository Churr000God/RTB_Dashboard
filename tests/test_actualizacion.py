import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class ActualizacionCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data_dir = self.root / "data"
        self.processed_dir = self.root / "data_procesada"
        self.dashboard_dir = self.root / "dashboard_data"
        self.data_dir.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def coordinator(self):
        from rtb_actualizacion import UpdateCoordinator

        return UpdateCoordinator(
            data_dir=self.data_dir,
            processed_dir=self.processed_dir,
            dashboard_dir=self.dashboard_dir,
            callback_token="secret",
        )

    def write_csv(self, name, text="columna\nvalor\n"):
        path = self.data_dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_rejects_second_active_run(self):
        from rtb_actualizacion import ActiveRunError

        coordinator = self.coordinator()
        coordinator.create_run("2026-05-01", "2026-05-31")

        with self.assertRaises(ActiveRunError):
            coordinator.create_run("2026-06-01", "2026-06-30")

    def test_rejects_unsafe_callback_filename(self):
        from rtb_actualizacion import InvalidRunError

        coordinator = self.coordinator()
        run = coordinator.create_run("2026-05-01", "2026-05-31")

        with self.assertRaisesRegex(InvalidRunError, "nombre de archivo"):
            coordinator.finalize_run(run["run_id"], ["../fuera.csv"])

    @patch("rtb_actualizacion.build_ventas_dashboard")
    @patch("rtb_actualizacion.compute")
    @patch("rtb_actualizacion.load_all")
    def test_publishes_snapshot_and_archives_only_declared_files(self, load_all, compute, build_ventas):
        declared = self.write_csv("Cotizaciones_run.csv")
        extra = self.write_csv("ARCHIVO_NUEVO_run.csv")
        untouched = self.write_csv("sobrante.csv")
        load_all.return_value = {"cot": [{"Cotizacion_id": "cot-1"}], "_files": {"cot": str(declared)}}
        compute.return_value = {"hero": {"cotizaciones": 1}}
        build_ventas.return_value = {"kpis": {"cotizaciones": 1}}
        coordinator = self.coordinator()
        run = coordinator.create_run("2026-05-01", "2026-05-31")

        result = coordinator.finalize_run(run["run_id"], [declared.name, extra.name])

        latest = json.loads((self.dashboard_dir / "latest.json").read_text(encoding="utf-8"))
        history = list((self.dashboard_dir / "snapshots").glob("*.json"))
        archived = sorted(path.name for path in Path(result["processed_dir"]).iterdir())
        self.assertEqual(latest["run_id"], run["run_id"])
        self.assertEqual(latest["metrics"]["hero"]["cotizaciones"], 1)
        self.assertEqual(latest["dashboard"]["ventas"]["kpis"]["cotizaciones"], 1)
        self.assertEqual(len(history), 1)
        self.assertEqual(archived, sorted([declared.name, extra.name]))
        self.assertTrue(untouched.exists())
        load_all.assert_called_once_with(self.data_dir, allowed_files=[declared.name, extra.name])
        compute.assert_called_once_with(
            load_all.return_value,
            period={
                "start": "2026-05-01",
                "end": "2026-05-31",
                "label": "2026-05-01 a 2026-05-31",
                "range_label": "2026-05-01 a 2026-05-31",
            },
        )
        build_ventas.assert_called_once_with(
            load_all.return_value["cot"], period_label="2026-05-01 a 2026-05-31",
            fecha_desde="2026-05-01", fecha_hasta="2026-05-31",
        )

    @patch("rtb_actualizacion.compute", side_effect=RuntimeError("calculo roto"))
    @patch("rtb_actualizacion.load_all")
    def test_keeps_previous_snapshot_and_files_when_calculation_fails(self, load_all, compute):
        csv_path = self.write_csv("Cotizaciones_run.csv")
        self.dashboard_dir.mkdir()
        previous = {"run_id": "anterior"}
        (self.dashboard_dir / "latest.json").write_text(json.dumps(previous), encoding="utf-8")
        load_all.return_value = {"cot": [], "_files": {"cot": str(csv_path)}}
        coordinator = self.coordinator()
        run = coordinator.create_run("2026-05-01", "2026-05-31")

        with self.assertRaisesRegex(RuntimeError, "calculo roto"):
            coordinator.finalize_run(run["run_id"], [csv_path.name])

        latest = json.loads((self.dashboard_dir / "latest.json").read_text(encoding="utf-8"))
        status = coordinator.get_run(run["run_id"])
        self.assertEqual(latest, previous)
        self.assertTrue(csv_path.exists())
        self.assertEqual(status["status"], "fallida_calculo")

    @patch("rtb_actualizacion.build_ventas_dashboard", return_value={"kpis": {}})
    @patch("rtb_actualizacion.compute", return_value={"hero": {}})
    @patch("rtb_actualizacion.load_all")
    def test_completed_callback_is_idempotent(self, load_all, compute, build_ventas):
        csv_path = self.write_csv("Cotizaciones_run.csv")
        load_all.return_value = {"cot": [], "_files": {"cot": str(csv_path)}}
        coordinator = self.coordinator()
        run = coordinator.create_run("2026-05-01", "2026-05-31")

        first = coordinator.finalize_run(run["run_id"], [csv_path.name])
        second = coordinator.finalize_run(run["run_id"], [csv_path.name])

        self.assertEqual(second, first)
        compute.assert_called_once()


    def test_load_all_uses_only_allowed_files(self):
        from rtb_analisis import load_all

        prefixes = [
            "Cotizaciones",
            "CRECIMIENTO_INVENTARIO",
            "FACTURAS_COMPRAS",
            "FACTURAS_COMPRAS_PAGADAS",
            "INVENTARIO_REAL_ACTUAL",
            "MATERIALES_SALIDA",
            "PEDIDOS_CLIENTES",
            "PEDIDOS_CLIENTES_ENVIADOS",
            "PEDIDOS_CLIENTES_FACTURADOS",
            "PEDIDOS_CLIENTES_FACTURADOS_SECUNDARIA",
            "PEDIDOS_CLIENTES_PAGADOS",
            "PRODUCTOS_ENTRADA",
        ]
        allowed = []
        for prefix in prefixes:
            filename = f"{prefix}_declarado.csv"
            self.write_csv(filename)
            allowed.append(filename)
        self.write_csv("Cotizaciones_sobrante.csv")

        data = load_all(self.data_dir, allowed_files=allowed)

        self.assertEqual(Path(data["_files"]["cot"]).name, "Cotizaciones_declarado.csv")

    @patch("rtb_actualizacion.build_ventas_dashboard", return_value={"kpis": {}})
    @patch("rtb_actualizacion.compute", return_value={"hero": {}})
    @patch("rtb_actualizacion.load_all")
    def test_retries_partial_archiving_without_recalculating(self, load_all, compute, build_ventas):
        first = self.write_csv("Cotizaciones_run.csv")
        second = self.write_csv("ARCHIVO_NUEVO_run.csv")
        load_all.return_value = {"cot": [], "_files": {"cot": str(first)}}
        coordinator = self.coordinator()
        run = coordinator.create_run("2026-05-01", "2026-05-31")
        real_move = shutil.move
        attempts = {"count": 0}

        def fail_second_move(source, destination):
            attempts["count"] += 1
            if attempts["count"] == 2:
                raise OSError("disco ocupado")
            return real_move(source, destination)

        with patch("rtb_actualizacion.shutil.move", side_effect=fail_second_move):
            with self.assertRaisesRegex(OSError, "disco ocupado"):
                coordinator.finalize_run(run["run_id"], [first.name, second.name])

        result = coordinator.finalize_run(run["run_id"], [first.name, second.name])

        self.assertEqual(result["status"], "completada")
        self.assertEqual(sorted(result["moved_files"]), sorted([first.name, second.name]))
        compute.assert_called_once()


    def test_compute_builds_hero_from_empty_datasets(self):
        from rtb_analisis import compute

        data = {key: [] for key in ("cot", "crec", "fc", "fcp", "gas", "inv", "ms", "ped", "env", "fac", "facs", "pag", "pent")}

        result = compute(data)

        self.assertEqual(result["hero"]["n_cot"], 0)
        self.assertEqual(result["hero"]["conv_q"], 0)


if __name__ == "__main__":
    unittest.main()
