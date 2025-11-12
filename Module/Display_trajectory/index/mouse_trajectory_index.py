# from PyQt6.QtCore import pyqtSlot, QThread, pyqtSignal, Qt
# from PyQt6.QtWidgets import QTableWidgetItem
# # 核心继承：ThemedWindow → BaseWindow → ThemedWidget（和user_monitor完全一致）
# from theme.ThemeQt6 import ThemedWindow
# from .display_trajectory_ui import DisplayTrajectoryUI
# # 项目公共模块（和user_monitor导入一致）
# from public.config_class.global_setting import global_setting
# from your_project.utils import calculate_distance
# from loguru import logger
# from datetime import datetime
#
#
# class TrajectoryDataThread(QThread):
#     """数据线程（和user_monitor的线程结构、命名一致）"""
#     update_signal = pyqtSignal(list)  # 发送轨迹点列表：[(x1,y1), (x2,y2), ...]
#
#     def __init__(self, parent, cage_number):
#         super().__init__(parent)
#         self.parent = parent
#         self.cage_number = cage_number
#         self.is_running = False  # 和user_monitor的线程状态变量命名一致
#         self.trajectory_points = []
#
#     def run(self):
#         """线程运行逻辑（模仿user_monitor）"""
#         self.is_running = True
#         logger.info(f"轨迹数据线程启动（鼠笼：{self.cage_number + 1}）")
#         while self.is_running:
#             try:
#                 new_points = self._fetch_trajectory_data()
#                 self.update_signal.emit(new_points)
#                 # 按速度调节刷新频率（和user_monitor一致）
#                 refresh_interval = int(200 / self.parent.ui.speed_slider.value())
#                 self.msleep(refresh_interval)
#             except Exception as e:
#                 logger.error(f"轨迹线程异常：{str(e)}")
#                 self.msleep(1000)
#
#     def _fetch_trajectory_data(self):
#         """获取轨迹数据（模仿user_monitor：模拟/数据库/传感器，实际项目替换）"""
#         import random
#         # 初始化初始位置（复用已有组件的鼠笼尺寸，避免硬编码）
#         cage_width = self.parent.ui.trajectory_widget.get_cage_width()
#         cage_height = self.parent.ui.trajectory_widget.get_cage_height()
#
#         if not hasattr(self, "last_x"):
#             self.last_x = random.randint(50, cage_width - 50)
#             self.last_y = random.randint(50, cage_height - 50)
#
#         # 模拟老鼠随机游走（实际项目替换为真实数据读取）
#         offset_x = random.randint(-5, 5)
#         offset_y = random.randint(-5, 5)
#         new_x = self.last_x + offset_x
#         new_y = self.last_y + offset_y
#
#         # 限制在鼠笼内（复用已有组件的方法，和user_monitor的数据校验一致）
#         new_x, new_y = self.parent.ui.trajectory_widget.clamp_point((new_x, new_y))
#         self.last_x, self.last_y = new_x, new_y
#
#         # 缓存最近100个点（和user_monitor的缓存策略一致）
#         self.trajectory_points.append((new_x, new_y))
#         return self.trajectory_points[-100:]
#
#     def stop(self):
#         """停止线程（统一接口，和user_monitor一致）"""
#         self.is_running = False
#         self.wait()
#         logger.info(f"轨迹线程停止（鼠笼：{self.cage_number + 1}）")
#
#
# class DisplayTrajectoryIndex(ThemedWindow):
#     """核心业务类（继承链、结构和user_monitor完全一致）"""
#
#     def __init__(self, parent=None):
#         # 唯一继承：初始化ThemedWindow（自动调用BaseWindow和ThemedWidget构造）
#         super().__init__(parent)
#         # 初始化流程和user_monitor完全一致：窗口→主题→UI→业务
#         self._init_window()
#         self._init_theme()
#         self._init_ui()
#         self._init_business()
#         logger.info("DisplayTrajectory模块初始化完成（无widgets文件夹，继承项目已有组件）")
#
#     def _init_window(self):
#         """窗口初始化（模仿user_monitor：调用BaseWindow的统一方法）"""
#         self.setWindowTitle("老鼠轨迹监控")
#         self.setMinimumSize(1200, 600)
#         # 复用BaseWindow的统一功能（和user_monitor一致）
#         self.set_window_icon(global_setting.get_setting("app_icon_path"))
#         self.center_window()  # BaseWindow的居中方法
#
#     def _init_theme(self):
#         """主题初始化（模仿user_monitor：继承ThemedWidget的方法）"""
#         self.load_theme_config()  # ThemedWidget的统一方法（加载主题配置）
#         self.apply_theme_to_window()  # 应用主题到窗口
#
#     def _init_ui(self):
#         """UI初始化（模仿user_monitor：组合UI类，挂载到窗口）"""
#         # 初始化UI类，传递主题（和user_monitor的UI初始化一致）
#         self.ui = DisplayTrajectoryUI(theme=self.theme)
#         # 挂载UI到ThemedWindow的中央容器（和user_monitor的挂载方式一致）
#         self.setCentralWidget(self.ui)
#
#     def _init_business(self):
#         """业务初始化（和user_monitor的结构一致：变量→信号→线程）"""
#         self.trajectory_thread = None
#         self.current_cage = global_setting.get_setting("tab2_select_mouse_cage", 0)
#         self.ui.cage_combo.setCurrentIndex(self.current_cage)
#         self._bind_signals()
#         self._init_thread()
#
#     def _bind_signals(self):
#         """信号绑定（模仿user_monitor：集中绑定，命名规范一致）"""
#         # UI按钮信号
#         self.ui.play_btn.clicked.connect(self._on_play_btn_click)
#         self.ui.clear_btn.clicked.connect(self._on_clear_btn_click)
#         self.ui.grid_btn.clicked.connect(self._on_grid_btn_click)
#         self.ui.color_btn.clicked.connect(self._on_color_btn_click)
#         # 下拉框切换信号
#         self.ui.cage_combo.currentIndexChanged.connect(self._on_cage_changed)
#         # 主题切换信号（继承ThemedWidget，和user_monitor一致）
#         self.theme_changed_signal.connect(self._on_theme_changed)
#
#     def _init_thread(self):
#         """初始化线程（和user_monitor的线程管理一致）"""
#         if self.trajectory_thread:
#             self.trajectory_thread.stop()
#         self.trajectory_thread = TrajectoryDataThread(self, self.current_cage)
#         # 绑定线程信号（QueuedConnection避免线程安全问题，和user_monitor一致）
#         self.trajectory_thread.update_signal.connect(self._on_trajectory_updated, Qt.ConnectionType.QueuedConnection)
#
#     # ---------------------- 信号响应方法（和user_monitor的命名规范一致：_on_xxx）----------------------
#     @pyqtSlot()
#     def _on_play_btn_click(self):
#         """开始/暂停（模仿user_monitor的按钮响应逻辑）"""
#         if not self.trajectory_thread.is_running:
#             self.trajectory_thread.start()
#             self.ui.play_btn.setText("暂停")
#             logger.info("轨迹监控开始")
#         else:
#             self.trajectory_thread.is_running = False
#             self.ui.play_btn.setText("开始")
#             logger.info("轨迹监控暂停")
#
#     @pyqtSlot()
#     def _on_clear_btn_click(self):
#         """清空轨迹（模仿user_monitor的清理逻辑）"""
#         self.ui.trajectory_widget.clear_trajectory()  # 调用已有组件方法
#         self.ui.trajectory_table.setRowCount(0)
#         # 重置统计标签
#         self.ui.coord_label.setText("当前坐标：(0.0, 0.0)")
#         self.ui.distance_label.setText("总距离：0.0 cm")
#         self.ui.speed_label.setText("当前速度：0.0 cm/s")
#         logger.info("轨迹数据清空")
#
#     @pyqtSlot()
#     def _on_grid_btn_click(self):
#         """显示/隐藏网格（模仿user_monitor：调用已有组件方法）"""
#         if self.ui.grid_btn.isChecked():
#             self.ui.trajectory_widget.show_grid()
#         else:
#             self.ui.trajectory_widget.hide_grid()
#
#     @pyqtSlot()
#     def _on_color_btn_click(self):
#         """切换轨迹颜色（模仿user_monitor：从主题获取颜色）"""
#         color_list = [self.theme.primary_color, self.theme.secondary_color, self.theme.success_color]
#         current_color = self.ui.trajectory_widget.get_trajectory_color()
#         current_idx = color_list.index(current_color) if current_color in color_list else 0
#         new_color = color_list[(current_idx + 1) % len(color_list)]
#         self.ui.trajectory_widget.set_trajectory_color(new_color)
#         logger.info(f"轨迹颜色切换为：{new_color.name()}")
#
#     @pyqtSlot(int)
#     def _on_cage_changed(self, cage_idx):
#         """切换鼠笼（模仿user_monitor的下拉框响应）"""
#         self.current_cage = cage_idx
#         global_setting.set_setting("tab2_select_mouse_cage", cage_idx)
#         self._init_thread()
#         self._on_clear_btn_click()
#         logger.info(f"切换至鼠笼：{cage_idx + 1}")
#
#     @pyqtSlot(list)
#     def _on_trajectory_updated(self, new_points):
#         """更新轨迹和统计（模仿user_monitor的数据处理逻辑）"""
#         self.ui.trajectory_widget.update_trajectory(new_points)  # 调用已有组件方法
#         if len(new_points) >= 2:
#             self._calculate_stats(new_points)
#             self._update_table(new_points[-1])
#
#     @pyqtSlot()
#     def _on_theme_changed(self):
#         """主题切换响应（模仿user_monitor：全UI主题更新）"""
#         self.ui.theme = self.theme
#         self.ui._load_style_sheet()
#         self.ui._apply_label_theme(
#             [self.ui.coord_label, self.ui.distance_label, self.ui.speed_label, self.ui.table_label])
#         self.ui._apply_table_theme()
#         # 组件主题更新（调用已有组件的主题方法）
#         self.ui.trajectory_widget.apply_theme(self.theme)
#         logger.info("轨迹模块主题已更新")
#
#     # ---------------------- 业务辅助方法（和user_monitor的命名一致）----------------------
#     def _calculate_stats(self, points_list):
#         """计算统计数据（复用项目工具类，和user_monitor一致）"""
#         last_x, last_y = points_list[-1]
#         self.ui.coord_label.setText(f"当前坐标：({last_x:.1f}, {last_y:.1f})")
#
#         # 总距离
#         total_distance = 0.0
#         for i in range(len(points_list) - 1):
#             total_distance += calculate_distance(points_list[i], points_list[i + 1])
#         self.ui.distance_label.setText(f"总距离：{total_distance:.1f} cm")
#
#         # 当前速度
#         refresh_interval = 200 / self.ui.speed_slider.value() / 1000  # 秒
#         last_two_dist = calculate_distance(points_list[-2], points_list[-1])
#         current_speed = last_two_dist / refresh_interval if refresh_interval != 0 else 0.0
#         self.ui.speed_label.setText(f"当前速度：{current_speed:.1f} cm/s")
#
#     def _update_table(self, last_point):
#         """更新表格（和user_monitor的表格操作一致）"""
#         timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
#         x, y = last_point
#         current_speed = float(self.ui.speed_label.text().split("：")[1].split(" ")[0])
#
#         row_idx = self.ui.trajectory_table.rowCount()
#         self.ui.trajectory_table.insertRow(row_idx)
#         self.ui.trajectory_table.setItem(row_idx, 0, QTableWidgetItem(timestamp))
#         self.ui.trajectory_table.setItem(row_idx, 1, QTableWidgetItem(f"{x:.1f}"))
#         self.ui.trajectory_table.setItem(row_idx, 2, QTableWidgetItem(f"{y:.1f}"))
#         self.ui.trajectory_table.setItem(row_idx, 3, QTableWidgetItem(f"{current_speed:.1f}"))
#
#         # 限制行数（和user_monitor一致）
#         if row_idx >= 100:
#             self.ui.trajectory_table.removeRow(0)
#
#     # ---------------------- 资源释放（和user_monitor完全一致）----------------------
#     def closeEvent(self, event):
#         if self.trajectory_thread:
#             self.trajectory_thread.stop()
#         logger.info("DisplayTrajectory模块关闭，资源已释放")
#         super().closeEvent(event)