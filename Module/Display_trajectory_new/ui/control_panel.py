from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QComboBox, QLabel, QScrollArea, QGroupBox,
                             QTabWidget, QGridLayout, QSlider, QCheckBox)
from PyQt6.QtCore import Qt


class ControlPanel:
    """控制面板类"""

    def __init__(self, parent):
        self.parent = parent

    def create_control_panel(self):
        """创建左侧控制面板"""
        panel = QWidget()
        panel.setMaximumWidth(450)
        panel.setMinimumWidth(350)

        # 使用滚动区域包装控制面板
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # 创建主控制容器
        control_container = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # 使用选项卡组织控制面板
        tab_widget = QTabWidget()

        # 数据选项卡
        data_tab = self.create_data_tab()
        tab_widget.addTab(data_tab, "数据控制")

        # 动画选项卡
        animation_tab = self.create_animation_tab()
        tab_widget.addTab(animation_tab, "动画控制")

        # 显示选项卡
        display_tab = self.create_display_tab()
        tab_widget.addTab(display_tab, "显示设置")

        layout.addWidget(tab_widget)

        # 温度显示组
        layout.addWidget(self.create_temperature_group())

        # 信息显示组
        info_group = self.create_collapsible_info_group()
        layout.addWidget(info_group)

        control_container.setLayout(layout)
        scroll_area.setWidget(control_container)

        # 将滚动区域包装在面板中
        panel_layout = QVBoxLayout()
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.addWidget(scroll_area)
        panel.setLayout(panel_layout)

        return panel

    def create_data_tab(self):
        """创建数据控制选项卡"""
        tab = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(10)

        # 文件选择组
        layout.addWidget(self.create_file_selection_group())

        # Sheet选择组
        layout.addWidget(self.create_sheet_selection_group())

        layout.addStretch()
        tab.setLayout(layout)
        return tab

    def create_animation_tab(self):
        """创建动画控制选项卡"""
        tab = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(10)

        # 动画控制组
        layout.addWidget(self.create_animation_control_group())

        layout.addStretch()
        tab.setLayout(layout)
        return tab

    def create_display_tab(self):
        """创建显示设置选项卡"""
        tab = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(10)

        # 3D设置组
        layout.addWidget(self.create_3d_settings_group())

        layout.addStretch()
        tab.setLayout(layout)
        return tab

    def create_file_selection_group(self):
        """创建文件选择组"""
        file_group = QGroupBox("选择数据文件")
        layout = QVBoxLayout()

        # 文件路径显示
        self.parent.file_path_label = QLabel("文件: 未选择")
        self.parent.file_path_label.setWordWrap(True)
        self.parent.file_path_label.setStyleSheet("background-color: #f9f9f9; padding: 8px; border-radius: 4px;")
        layout.addWidget(self.parent.file_path_label)

        # 选择文件按钮
        self.parent.select_file_btn = QPushButton("选择数据文件")
        layout.addWidget(self.parent.select_file_btn)

        file_group.setLayout(layout)
        return file_group

    def create_sheet_selection_group(self):
        """创建Sheet选择组"""
        sheet_group = QGroupBox("Excel Sheet选择")
        layout = QVBoxLayout()

        # 轨迹数据Sheet选择
        traj_layout = QHBoxLayout()
        traj_layout.addWidget(QLabel("轨迹数据:"))
        self.parent.trajectory_sheet_combo = QComboBox()
        self.parent.trajectory_sheet_combo.setEditable(True)  # 允许编辑
        self.parent.trajectory_sheet_combo.addItem("无sheet")  # 默认显示"无sheet"
        traj_layout.addWidget(self.parent.trajectory_sheet_combo)
        layout.addLayout(traj_layout)

        # 温度数据Sheet选择
        temp_layout = QHBoxLayout()
        temp_layout.addWidget(QLabel("温度数据:"))
        self.parent.temperature_sheet_combo = QComboBox()
        self.parent.temperature_sheet_combo.setEditable(True)  # 允许编辑
        self.parent.temperature_sheet_combo.addItem("无sheet")  # 默认显示"无sheet"
        temp_layout.addWidget(self.parent.temperature_sheet_combo)
        layout.addLayout(temp_layout)

        # 添加说明文字
        info_label = QLabel("说明: 系统将自动识别合适的sheet，如不正确可手动修改")
        info_label.setStyleSheet("color: #666; font-size: 11px; font-style: italic;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # 加载数据按钮
        self.parent.load_data_btn = QPushButton("加载选定数据")
        self.parent.load_data_btn.setStyleSheet("background-color: #FF9800;")
        layout.addWidget(self.parent.load_data_btn)

        sheet_group.setLayout(layout)
        return sheet_group

    def create_temperature_group(self):
        """创建温度显示组"""
        temp_group = QGroupBox("老鼠温度监控")
        temp_group.setMaximumHeight(80)
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 15, 10, 10)

        # 当前温度显示
        self.parent.current_temp_label = QLabel("当前温度: 等待数据...")
        self.parent.current_temp_label.setStyleSheet("""
            background-color: #e8f5e8;
            border: 2px solid #4CAF50;
            border-radius: 6px;
            padding: 8px;
            font-size: 14px;
            font-weight: bold;
            color: #2E7D32;
        """)
        self.parent.current_temp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.parent.current_temp_label.setMaximumHeight(40)
        layout.addWidget(self.parent.current_temp_label)

        temp_group.setLayout(layout)
        return temp_group

    def create_animation_control_group(self):
        """创建动画控制组"""
        anim_group = QGroupBox("动画控制")
        layout = QVBoxLayout()
        layout.setSpacing(8)

        # 播放控制按钮
        btn_frame = QWidget()
        btn_layout = QGridLayout()
        btn_layout.setSpacing(5)

        self.parent.play_btn = QPushButton("▶ 播放")
        self.parent.play_btn.setStyleSheet("background-color: #FF9800; font-weight: bold;")
        self.parent.pause_btn = QPushButton("⏸ 暂停")
        self.parent.pause_btn.setStyleSheet("background-color: #f44336; font-weight: bold;")
        self.parent.reset_btn = QPushButton("⏹ 重置")
        self.parent.reset_btn.setStyleSheet("background-color: #9C27B0; font-weight: bold;")

        btn_layout.addWidget(self.parent.play_btn, 0, 0)
        btn_layout.addWidget(self.parent.pause_btn, 0, 1)
        btn_layout.addWidget(self.parent.reset_btn, 1, 0, 1, 2)

        btn_frame.setLayout(btn_layout)
        layout.addWidget(btn_frame)

        # 速度控制
        speed_frame = QWidget()
        speed_layout = QVBoxLayout()
        speed_layout.setSpacing(3)

        speed_label_layout = QHBoxLayout()
        speed_label_layout.addWidget(QLabel("播放速度:"))
        self.parent.speed_label = QLabel("50")
        self.parent.speed_label.setStyleSheet("font-weight: bold; color: #1976D2;")
        speed_label_layout.addStretch()
        speed_label_layout.addWidget(self.parent.speed_label)

        self.parent.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.parent.speed_slider.setRange(1, 100)
        self.parent.speed_slider.setValue(50)

        speed_layout.addLayout(speed_label_layout)
        speed_layout.addWidget(self.parent.speed_slider)
        speed_frame.setLayout(speed_layout)
        layout.addWidget(speed_frame)

        # 播放进度控制
        progress_frame = QWidget()
        progress_layout = QVBoxLayout()
        progress_layout.setSpacing(3)

        # 进度标签布局
        progress_label_layout = QHBoxLayout()
        progress_label_layout.addWidget(QLabel("播放进度:"))
        self.parent.progress_label = QLabel("0 / 0")
        self.parent.progress_label.setStyleSheet("font-weight: bold; color: #1976D2;")
        progress_label_layout.addStretch()
        progress_label_layout.addWidget(self.parent.progress_label)

        self.parent.animation_progress = QSlider(Qt.Orientation.Horizontal)
        self.parent.animation_progress.setRange(0, 100)

        progress_layout.addLayout(progress_label_layout)
        progress_layout.addWidget(self.parent.animation_progress)

        progress_frame.setLayout(progress_layout)
        layout.addWidget(progress_frame)

        anim_group.setLayout(layout)
        return anim_group

    def create_3d_settings_group(self):
        """创建3D设置组"""
        settings_group = QGroupBox("3D显示设置")
        layout = QVBoxLayout()
        layout.setSpacing(8)

        # 显示选项
        display_frame = QWidget()
        display_layout = QGridLayout()
        display_layout.setSpacing(5)

        self.parent.show_points_cb = QCheckBox("显示数据点")
        self.parent.show_points_cb.setChecked(True)
        self.parent.show_lines_cb = QCheckBox("显示连接线")
        self.parent.show_lines_cb.setChecked(True)
        self.parent.show_trail_cb = QCheckBox("显示轨迹尾迹")
        self.parent.show_trail_cb.setChecked(True)
        self.parent.show_grid_cb = QCheckBox("显示网格")
        self.parent.show_grid_cb.setChecked(True)

        display_layout.addWidget(self.parent.show_points_cb, 0, 0)
        display_layout.addWidget(self.parent.show_lines_cb, 0, 1)
        display_layout.addWidget(self.parent.show_trail_cb, 1, 0)
        display_layout.addWidget(self.parent.show_grid_cb, 1, 1)

        display_frame.setLayout(display_layout)
        layout.addWidget(display_frame)

        # 样式控制
        style_frame = QWidget()
        style_layout = QVBoxLayout()
        style_layout.setSpacing(5)

        # 点大小
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("点大小:"))
        self.parent.point_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.parent.point_size_slider.setRange(10, 200)
        self.parent.point_size_slider.setValue(50)
        size_layout.addWidget(self.parent.point_size_slider)
        self.parent.point_size_label = QLabel("50")
        self.parent.point_size_label.setMinimumWidth(30)
        self.parent.point_size_label.setStyleSheet("font-weight: bold;")
        size_layout.addWidget(self.parent.point_size_label)
        style_layout.addLayout(size_layout)

        style_frame.setLayout(style_layout)
        layout.addWidget(style_frame)

        settings_group.setLayout(layout)
        return settings_group

    def create_collapsible_info_group(self):
        """创建可折叠的信息显示组"""
        from PyQt6.QtWidgets import QTextEdit

        # 主容器
        container = QWidget()
        container.setMaximumHeight(200)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # 折叠按钮
        self.parent.info_toggle_btn = QPushButton("▼ 系统日志")
        self.parent.info_toggle_btn.setCheckable(True)
        self.parent.info_toggle_btn.setChecked(True)
        self.parent.info_toggle_btn.setMaximumHeight(30)
        self.parent.info_toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: #607D8B;
                color: white;
                border: none;
                padding: 5px;
                text-align: left;
                font-weight: bold;
            }
            QPushButton:checked {
                background-color: #455A64;
            }
        """)
        layout.addWidget(self.parent.info_toggle_btn)

        # 信息文本区域
        self.parent.info_text = QTextEdit()
        self.parent.info_text.setMaximumHeight(150)
        self.parent.info_text.setReadOnly(True)
        self.parent.info_text.setStyleSheet("""
            font-family: Consolas, monospace; 
            font-size: 10px;
            background-color: #263238;
            color: #E0E0E0;
            border: 1px solid #37474F;
        """)
        layout.addWidget(self.parent.info_text)

        container.setLayout(layout)
        return container