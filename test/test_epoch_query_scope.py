import datetime
import os
import tempfile
import unittest

from public.dao.SQLite.Monitor_Datas_Handle import Monitor_Datas_Handle
from public.dao.SQLite.SQliteManager import SQLiteManager


class EpochQueryScopeTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.manager = SQLiteManager(os.path.join(self.temp_dir.name, "epoch_scope.db"))
        self.handle = Monitor_Datas_Handle.__new__(Monitor_Datas_Handle)
        self.handle.sqlite_manager = self.manager

        self.manager.create_table(
            "UFC_monitor_data_cage_1",
            {
                "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
                "flow_num": "INTEGER",
                "unused_sensor_field": "TEXT",
                "remarks": "TEXT",
                "time": "TIMESTAMP",
            },
        )
        self.manager.create_table(
            "MouseInfrared_data_cage_1",
            {
                "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
                "tmp_hs_mean": "REAL",
                "time": "TIMESTAMP",
            },
        )
        self.manager.create_table(
            "DetectionResults_data_cage_1",
            {
                "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
                "center_x": "REAL",
                "time": "TIMESTAMP",
            },
        )

    def tearDown(self):
        self.manager.close()
        self.temp_dir.cleanup()

    @staticmethod
    def _format_time(timestamp):
        return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    def test_epoch_query_excludes_unrelated_tables_and_columns(self):
        start_time = 1_800_000_000.0
        self.manager.insert(
            "UFC_monitor_data_cage_1",
            flow_num=120,
            unused_sensor_field="not needed",
            remarks="ufc ok",
            time=self._format_time(start_time + 1),
        )
        for offset, temperature in ((2, 31.5), (3, 32.0)):
            self.manager.insert(
                "MouseInfrared_data_cage_1",
                tmp_hs_mean=temperature,
                time=self._format_time(start_time + offset),
            )
        self.manager.insert(
            "DetectionResults_data_cage_1",
            center_x=999.0,
            time=self._format_time(start_time + 9),
        )

        query_plan = self.handle.get_epoch_query_plan(1)
        results, columns = self.handle.query_data_in_line_with_epoch_data(
            start_time,
            start_time + 10,
            start_exclusive=True,
            table_columns=query_plan,
        )

        self.assertEqual(results["UFC_monitor_data_cage_1__flow_num"], 120)
        self.assertEqual(results["UFC_monitor_data_cage_1__remarks"], "ufc ok")
        self.assertEqual(
            results["MouseInfrared_data_cage_1__tmp_hs_mean"],
            [31.5, 32.0],
        )
        self.assertNotIn("UFC_monitor_data_cage_1__unused_sensor_field", results)
        self.assertFalse(any("DetectionResults" in key for key in results))
        self.assertFalse(any("DetectionResults" in column for column in columns))

    def test_epoch_end_time_ignores_later_trajectory_frame(self):
        start_time = 1_800_000_000.0
        self.manager.insert(
            "UFC_monitor_data_cage_1",
            flow_num=120,
            unused_sensor_field=None,
            remarks=None,
            time=self._format_time(start_time + 1),
        )
        self.manager.insert(
            "DetectionResults_data_cage_1",
            center_x=999.0,
            time=self._format_time(start_time + 9),
        )

        actual_end_time = self.handle.query_epoch_actual_end_time(
            start_time,
            start_time + 10,
            table_names=self.handle.get_epoch_query_plan(1),
        )

        self.assertAlmostEqual(actual_end_time, start_time + 1, places=3)


if __name__ == "__main__":
    unittest.main()
