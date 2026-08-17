import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook, load_workbook

from public.function.weight.weight_postprocessor import (
    CAGE_HEADER,
    WEIGHT_HEADER,
    WeightPostprocessConfig,
    create_fitted_workbook,
    fit_weight_series,
)


class WeightPostprocessorTest(unittest.TestCase):
    def test_fit_uses_stable_upper_minus_lower_and_rejects_outlier_plateau(self):
        values = [
            0.0, 0.1, -0.1,
            25.0, 25.2, 24.9,
            0.1, 0.0, -0.1,
            40.0, 40.1, 39.9,
            0.0, 0.1, -0.1,
            25.1, 25.0, 25.2,
            0.0, -0.1, 0.1,
        ]
        fitted, event_count = fit_weight_series(
            values,
            WeightPostprocessConfig(
                outlier_ratio=0.20,
                reference_history=3,
            ),
        )

        self.assertGreaterEqual(event_count, 2)
        self.assertTrue(all(value is not None for value in fitted))
        self.assertTrue(all(24.0 <= value <= 26.0 for value in fitted))
        self.assertNotIn(40.0, fitted)

    def test_workbook_postprocess_keeps_raw_file_and_replaces_only_epoch_weight(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            raw_path = Path(temp_dir) / "experiment.xlsx"
            fitted_path = Path(temp_dir) / "experiment_称重拟合.xlsx"
            workbook = Workbook()
            epoch_sheet = workbook.active
            epoch_sheet.title = "每轮数据监控数据"
            epoch_sheet.append(["序号", CAGE_HEADER, WEIGHT_HEADER, "备注"])

            cage_one_values = [
                0.0, 0.1, -0.1,
                25.0, 25.2, 24.9,
                0.1, 0.0, -0.1,
                75.0,
                0.0, 0.1, -0.1,
                25.1, 25.0, 25.2,
                0.0, -0.1, 0.1,
            ]
            for index, value in enumerate(cage_one_values, start=1):
                epoch_sheet.append([index, 1, value, f"原备注{index}"])
            epoch_sheet.append([100, 2, 1.0, "笼2"])
            epoch_sheet.append([101, 2, "None", "笼2"])
            epoch_sheet.append([102, 2, 1.2, "笼2"])
            epoch_sheet.append([103, "参考笼", "None", "参考"])

            raw_weight_sheet = workbook.create_sheet("称重模块监控数据_通道1")
            raw_weight_sheet.append(["序号", "重量测量值(g)", "备注"])
            raw_weight_sheet.append([1, 75.0, "原始异常值"])
            workbook.save(raw_path)

            result = create_fitted_workbook(raw_path, output_path=fitted_path)

            self.assertTrue(result.success, result.error)
            self.assertEqual(str(fitted_path), result.output_path)
            self.assertTrue(raw_path.exists())
            self.assertTrue(fitted_path.exists())

            raw_workbook = load_workbook(raw_path, data_only=True)
            fitted_workbook = load_workbook(fitted_path, data_only=True)
            raw_epoch = raw_workbook["每轮数据监控数据"]
            fitted_epoch = fitted_workbook["每轮数据监控数据"]

            raw_values = [raw_epoch.cell(row, 3).value for row in range(2, 21)]
            fitted_values = [fitted_epoch.cell(row, 3).value for row in range(2, 21)]
            self.assertIn(75.0, raw_values)
            self.assertNotIn(75.0, fitted_values)
            self.assertTrue(all(isinstance(value, (int, float)) for value in fitted_values))
            self.assertTrue(all(24.0 <= value <= 26.0 for value in fitted_values))

            fitted_cage_two = [fitted_epoch.cell(row, 3).value for row in range(21, 24)]
            self.assertEqual([1.0, 1.0, 1.2], fitted_cage_two)
            self.assertIsNone(fitted_epoch.cell(24, 3).value)
            self.assertEqual(4, fitted_epoch.max_column)
            self.assertEqual("原备注1", fitted_epoch.cell(2, 4).value)
            self.assertEqual(
                75.0,
                fitted_workbook["称重模块监控数据_通道1"].cell(2, 2).value,
            )

    def test_no_weight_data_is_not_reported_as_export_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            raw_path = Path(temp_dir) / "empty_weight.xlsx"
            fitted_path = Path(temp_dir) / "empty_weight_称重拟合.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.append([CAGE_HEADER, WEIGHT_HEADER])
            sheet.append([1, "None"])
            workbook.save(raw_path)

            result = create_fitted_workbook(raw_path, output_path=fitted_path)

            self.assertTrue(result.success)
            self.assertIsNone(result.output_path)
            self.assertFalse(fitted_path.exists())
            self.assertTrue(raw_path.exists())


if __name__ == "__main__":
    unittest.main()
