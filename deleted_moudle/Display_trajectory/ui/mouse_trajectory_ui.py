# from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
#                              QPushButton, QComboBox, QSlider, QTableWidget)
# from PyQt6.QtCore import Qt
# # 导入项目已有轨迹组件（替换为真实组件名，如Q2DTrajectoryWidget）
# from Module.Display_trajectory.widgets.trajectory_base import TrajectoryBaseWidget
# from loguru import logger
# from public.config_class.global_setting import global_setting  # 导入全局配置
#
# class DisplayTrajectoryUI(QWidget):
#     """纯UI类（模仿user_monitor_ui：仅继承QWidget，复用项目已有组件）"""
#     def __init__(self, parent=None, theme=None):
#         super().__init__(parent)
#         self.theme = theme  # 接收主题（从Index传递）
#         self._init_ui()
#
#     def _init_ui(self):
#         """搭建布局（完全对齐user_monitor_ui结构，优化组件初始化）"""
#         self.main_layout = QHBoxLayout(self)
#         self.main_layout.setContentsMargins(10, 10, 10, 10)
#         self.main_layout.setSpacing(10)
#
#         # ---------------------- 左侧控制区 ----------------------
#         self.left_control_widget = QWidget()
#         self.left_control_widget.setFixedWidth(200)
#         self.left_layout = QVBoxLayout(self.left_control_widget)
#         self.left_layout.setContentsMargins(0, 0, 0, 0)
#         self.left_layout.setSpacing(8)
#
#         # 鼠笼选择
#         self.cage_label = QLabel("选择鼠笼")
#         self.cage_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
#         self.cage_combo = QComboBox()
#         self.cage_combo.addItems([f"鼠笼{i+1}" for i in range(8)])
#         self.left_layout.addWidget(self.cage_label)
#         self.left_layout.addWidget(self.cage_combo)
#
#         # 显示设置
#         self.display_label = QLabel("显示设置")
#         self.display_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
#         self.grid_btn = QPushButton("显示网格")
#         self.grid_btn.setCheckable(True)
#         self.grid_btn.setChecked(True)
#         self.color_btn = QPushButton("切换轨迹颜色")
#         self.left_layout.addWidget(self.display_label)
#         self.left_layout.addWidget(self.grid_btn)
#         self.left_layout.addWidget(self.color_btn)
#
#         # 轨迹控制
#         self.control_label = QLabel("轨迹控制")
#         self.control_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
#         self.play_btn = QPushButton("开始")
#         self.clear_btn = QPushButton("清空轨迹")
#         self.left_layout.addWidget(self.control_label)
#         self.left_layout.addWidget(self.play_btn)
#         self.left_layout.addWidget(self.clear_btn)
#
#         # 回放速度（修复命名冲突）
#         self.speed_control_label = QLabel("回放速度")
#         self.speed_control_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
#         self.speed_slider = QSlider(Qt.Orientation.Horizontal)
#         self.speed_slider.setRange(1, 10)
#         self.speed_slider.setValue(5)
#         self.left_layout.addWidget(self.speed_control_label)
#         self.left_layout.addWidget(self.speed_slider)
#
#         self.left_layout.addStretch()
#
#         # ---------------------- 中间2D轨迹区（核心优化：组件初始化和user_monitor一致）----------------------
#         # 1. 从全局配置读取轨迹组件配置（避免硬编码，和user_monitor配置方式一致）
#         trajectory_config = global_setting.get_section("trajectory_config", {})  # 读取配置段
#         cage_width = trajectory_config.get("cage_width", 600)  # 配置默认值
#         cage_height = trajectory_config.get("cage_height", 400)
#         grid_step = trajectory_config.get("grid_step", 50)
#         default_color = trajectory_config.get("default_color", "#FF0000")
#
#         # 2. 初始化项目已有组件（构造函数传参，传递parent+theme+配置，和user_monitor一致）
#         self.trajectory_widget = TrajectoryBaseWidget(
#             parent=self,  # 绑定父控件，确保样式/生命周期统一
#             theme=self.theme,  # 直接传递主题，无需后续set
#             cage_width=cage_width,  # 配置参数
#             cage_height=cage_height,
#             grid_step=grid_step,
#             trajectory_color=self.theme.primary_color or default_color  # 主题优先
#         )
#
#         # 3. 挂载组件（和user_monitor布局方式一致）
#         self.main_layout.addWidget(self.left_control_widget)
#         self.main_layout.addWidget(self.trajectory_widget, stretch=1)  # 占比最大
#
#         # ---------------------- 右侧统计区 ----------------------
#         self.right_stats_widget = QWidget()
#         self.right_stats_widget.setFixedWidth(250)
#         self.right_layout = QVBoxLayout(self.right_stats_widget)
#         self.right_layout.setContentsMargins(0, 0, 0, 0)
#         self.right_layout.setSpacing(8)
#
#         # 实时统计标签（修复命名冲突）
#         self.coord_label = QLabel("当前坐标：(0.0, 0.0)")
#         self.distance_label = QLabel("总距离：0.0 cm")
#         self.speed_stats_label = QLabel("当前速度：0.0 cm/s")
#         self._apply_label_theme([self.coord_label, self.distance_label, self.speed_stats_label])
#         self.right_layout.addWidget(self.coord_label)
#         self.right_layout.addWidget(self.distance_label)
#         self.right_layout.addWidget(self.speed_stats_label)
#
#         # 轨迹点表格
#         self.table_label = QLabel("轨迹点数据")
#         self._apply_label_theme([self.table_label])
#         self.trajectory_table = QTableWidget()
#         self.trajectory_table.setColumnCount(4)
#         self.trajectory_table.setHorizontalHeaderLabels(["时间戳", "X(cm)", "Y(cm)", "速度(cm/s)"])
#         self.trajectory_table.horizontalHeader().setStretchLastSection(True)
#         self._apply_table_theme()
#         self.right_layout.addWidget(self.table_label)
#         self.right_layout.addWidget(self.trajectory_table, stretch=1)
#
#         self.main_layout.addWidget(self.right_stats_widget)
#
#         # 加载样式（和user_monitor_ui完全一致）
#         self._load_style_sheet()
#
#     def _apply_label_theme(self, labels):
#         """主题应用（模仿user_monitor的UI主题方法）"""
#         for label in labels:
#             label.setStyleSheet(f"color: {self.theme.text_color or '#212529'}; font-size: 13px; margin: 2px 0;")
#
#     def _apply_table_theme(self):
#         """表格主题（和user_monitor一致）"""
#         self.trajectory_table.setStyleSheet(f"""
#             QTableWidget {{
#                 background-color: {self.theme.bg_color or '#FFFFFF'};
#                 color: {self.theme.text_color or '#212529'};
#                 border: 1px solid {self.theme.border_color or '#E9ECEF'};
#                 gridline-color: {self.theme.grid_color or '#E9ECEF'};
#                 font-size: 12px;
#             }}
#             QHeaderView::section {{
#                 background-color: {self.theme.header_color or '#F8F9FA'};
#                 color: {self.theme.text_color or '#212529'};
#                 border: 1px solid {self.theme.border_color or '#E9ECEF'};
#                 padding: 4px;
#             }}
#         """)
#
#     def _load_style_sheet(self):
#         """UI样式（完全模仿user_monitor_ui）"""
#         self.setStyleSheet(f"""
#             QWidget {{ background-color: {self.theme.bg_color or '#F8F9FA'}; }}
#             QPushButton {{
#                 padding: 8px 12px;
#                 margin: 4px 0;
#                 border: none;
#                 border-radius: 4px;
#                 background-color: {self.theme.btn_bg_color or '#E9ECEF'};
#                 color: {self.theme.btn_text_color or '#212529'};
#                 font-size: 13px;
#             }}
#             QPushButton:hover {{ background-color: {self.theme.btn_hover_color or '#DEE2E6'}; }}
#             QPushButton:checked {{ background-color: {self.theme.btn_active_color or '#4361EE'}; color: white; }}
#             QComboBox, QSlider {{
#                 margin: 4px 0;
#                 border: 1px solid {self.theme.border_color or '#E9ECEF'};
#                 border-radius: 4px;
#                 padding: 4px;
#                 background-color: {self.theme.bg_color or '#FFFFFF'};
#                 color: {self.theme.text_color or '#212529'};
#             }}
#         """)