import ast
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _class_method(path, class_name, method_name):
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == method_name:
                    return item
    raise AssertionError(f"{class_name}.{method_name} was not found in {path}")


class StartupCompletionContractTests(unittest.TestCase):
    def test_monitor_stops_before_sending_synchronous_completion(self):
        path = (
            PROJECT_ROOT
            / "Service"
            / "UFC_UGC_ZOS_Service"
            / "index"
            / "UFC_UGC_ZOS_index.py"
        )
        method = _class_method(path, "Monitor_start_state_Thread", "dosomething")
        source = ast.get_source_segment(path.read_text(encoding="utf-8-sig"), method)

        self.assertLess(source.index("self.stop()"), source.index(".send()"))

    def test_completion_callback_never_waits_for_monitor_thread_deletion(self):
        path = (
            PROJECT_ROOT
            / "Service"
            / "UFC_UGC_ZOS_Service"
            / "index"
            / "UFC_UGC_ZOS_index.py"
        )
        method = _class_method(path, "UFC_UGC_ZOS_index", "update_start_state")
        source = ast.get_source_segment(path.read_text(encoding="utf-8-sig"), method)

        self.assertNotIn("deleteLater", source)
        self.assertIn("更新启动完成状态", source)

    def test_gui_success_handler_cancels_the_failure_timer(self):
        path = PROJECT_ROOT / "index" / "MainWindow_index.py"
        method = _class_method(path, "MainWindow_Index", "_on_gas_path_start_success")
        source = ast.get_source_segment(path.read_text(encoding="utf-8-sig"), method)

        self.assertIn("_gas_path_success = True", source)
        self.assertIn("_gas_path_timeout_timer.stop()", source)
        self.assertIn("气路启动成功", source)

    def test_gui_timeout_does_not_report_a_confirmed_failure(self):
        path = PROJECT_ROOT / "index" / "MainWindow_index.py"
        method = _class_method(path, "MainWindow_Index", "_on_gas_path_final_timeout")
        source = ast.get_source_segment(path.read_text(encoding="utf-8-sig"), method)

        self.assertNotIn("气路初始化失败", source)
        self.assertIn("气路启动等待超时", source)

    def test_calibration_stop_events_report_completed_statuses(self):
        path = PROJECT_ROOT / "index" / "MainWindow_index.py"
        method = _class_method(path, "read_queue_data_Thread", "dosomething")
        source = ast.get_source_segment(path.read_text(encoding="utf-8-sig"), method)

        self.assertIn('calibration_detail_status_text = "零点标定完成"', source)
        self.assertIn('calibration_detail_status_text = "量程标定完成"', source)
        self.assertIn('calibration_detail_status_text = "Air空气校准完成"', source)
        self.assertIn("updateAirEndTime", source)

    def test_air_calibration_uses_its_own_ui_log_methods(self):
        path = (
            PROJECT_ROOT
            / "public"
            / "component"
            / "dialog"
            / "custom"
            / "calibration_detail_Dialog.py"
        )
        start_method = _class_method(path, "CalibrationDialog", "updateAirStartTime")
        end_method = _class_method(path, "CalibrationDialog", "updateAirEndTime")
        text = path.read_text(encoding="utf-8-sig")
        start_source = ast.get_source_segment(text, start_method)
        end_source = ast.get_source_segment(text, end_method)

        self.assertIn("Air空气校准开始", start_source)
        self.assertIn("Air空气校准完成", end_source)
        self.assertNotIn("零点标定", start_source + end_source)


if __name__ == "__main__":
    unittest.main()
