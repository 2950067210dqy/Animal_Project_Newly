try:
    from public.entity.BaseWidget import BaseWidget
except ImportError:
    from PyQt6.QtWidgets import QWidget as BaseWidget

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel, QPushButton, QComboBox, QGridLayout

try:
    from public.entity.BaseWidget import BaseWidget
except ImportError:
    from PyQt6.QtWidgets import QWidget as BaseWidget

from .trajectory_canvas import MouseCagePanel


class MouseTrajectoryMainUI(BaseWidget):
    """老鼠轨迹主界面"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.all_cage_panels = {}  # 存储所有笼子面板，key为cage_id
        self.visible_cage_panels = []  # 当前页面显示的笼子面板
        self.cage_count = 4
        self.mice_per_cage = 1
        self.current_page = 1
        self.cages_per_page = 4
        self.total_pages = 1

        # 笼子面板尺寸 - 调小一些
        self.cage_panel_width = 400
        self.cage_panel_height = 380

        self.setWindowTitle("老鼠轨迹监控界面")
        self._init_ui()

    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout()
        layout.setSpacing(2)  # 进一步减小整体间隔

        # 控制面板
        control_panel = self._create_control_panel()
        layout.addWidget(control_panel)

        # 滚动区域用于显示笼子
        self.scroll_area = QScrollArea()
        self.scroll_widget = QWidget()
        self.scroll_layout = QGridLayout(self.scroll_widget)
        self.scroll_layout.setSpacing(8)  # 减小网格布局间隔，从3改为8
        self.scroll_layout.setContentsMargins(10, 5, 10, 5)  # 减小内容边距
        # 设置网格布局居中对齐
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setWidget(self.scroll_widget)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; }")

        layout.addWidget(self.scroll_area)

        self.setLayout(layout)

        # 创建默认笼子
        self._create_initial_cages()

    def _create_control_panel(self):
        """创建控制面板"""
        group_box = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)  # 减小控制面板边距

        # 笼子数量选择
        layout.addWidget(QLabel("笼子数量:"))
        self.cage_count_combo = QComboBox()
        self.cage_count_combo.addItems([str(i) for i in range(1, 9)])
        self.cage_count_combo.setCurrentIndex(3)  # 默认4个笼子
        self.cage_count_combo.currentIndexChanged.connect(self._update_cage_count)
        layout.addWidget(self.cage_count_combo)

        layout.addStretch()

        # 全局控制按钮
        start_all_btn = QPushButton("全部开始")
        stop_all_btn = QPushButton("全部停止")
        clear_all_btn = QPushButton("全部清除")
        self.prev_page_btn = QPushButton("上一页")
        self.next_page_btn = QPushButton("下一页")
        self.page_label = QLabel(f"{self.current_page} / {self.total_pages}")

        button_style = """
            QPushButton {
                min-width: 80px;
                min-height: 30px;
                border-radius: 4px;
                font-size: 10pt;
                background-color: #4A5568;
                color: #E1E1E1;
                border: 1px solid #666;
            }
            QPushButton:hover {
                background-color: #5A6578;
            }
            QPushButton:disabled {
                background-color: #2D3748;
                color: #718096;
            }
        """

        start_all_btn.setStyleSheet(button_style)
        stop_all_btn.setStyleSheet(button_style)
        clear_all_btn.setStyleSheet(button_style)
        self.prev_page_btn.setStyleSheet(button_style)
        self.next_page_btn.setStyleSheet(button_style)

        start_all_btn.clicked.connect(self.start_all_tracking)
        stop_all_btn.clicked.connect(self.stop_all_tracking)
        clear_all_btn.clicked.connect(self.clear_all_trajectory)
        self.prev_page_btn.clicked.connect(self.on_prev_page)
        self.next_page_btn.clicked.connect(self.on_next_page)

        layout.addWidget(start_all_btn)
        layout.addWidget(stop_all_btn)
        layout.addWidget(clear_all_btn)
        layout.addWidget(self.prev_page_btn)
        layout.addWidget(self.next_page_btn)
        layout.addWidget(self.page_label)

        group_box.setLayout(layout)
        return group_box

    def _update_cage_count(self, index):
        """更新笼子数量"""
        # 先清除所有现有的笼子面板
        self._clear_all_panels()

        self.cage_count = index + 1
        self.current_page = 1
        self._create_initial_cages()

    def _clear_all_panels(self):
        """清除所有笼子面板"""
        # 停止所有追踪
        for panel in self.all_cage_panels.values():
            panel.stop_tracking()
            panel.setParent(None)

        self.all_cage_panels.clear()
        self.visible_cage_panels.clear()

        # 清除布局中的所有项目
        for i in reversed(range(self.scroll_layout.count())):
            item = self.scroll_layout.itemAt(i)
            if item and item.widget():
                item.widget().setParent(None)

    def _create_initial_cages(self):
        """创建初始笼子"""
        # 创建所有笼子面板但不显示
        for i in range(1, self.cage_count + 1):
            if i not in self.all_cage_panels:
                cage_panel = MouseCagePanel(cage_id=i, mouse_count=self.mice_per_cage,
                                            panel_width=self.cage_panel_width,
                                            panel_height=self.cage_panel_height)
                cage_panel.setFixedSize(self.cage_panel_width, self.cage_panel_height)
                cage_panel.cage_status_changed.connect(self._on_cage_status_changed)
                self.all_cage_panels[i] = cage_panel

        self._update_cage_display()

    def _update_cage_display(self):
        """更新笼子显示"""
        # 隐藏当前显示的笼子面板
        for panel in self.visible_cage_panels:
            panel.setParent(None)
        self.visible_cage_panels.clear()

        # 清除布局中的所有项目
        for i in reversed(range(self.scroll_layout.count())):
            item = self.scroll_layout.itemAt(i)
            if item and item.widget():
                item.widget().setParent(None)

        # 计算总页数
        self.total_pages = (self.cage_count + self.cages_per_page - 1) // self.cages_per_page

        # 确保当前页不超过总页数
        if self.current_page > self.total_pages:
            self.current_page = self.total_pages

        # 计算当前页要显示的笼子范围
        start_idx = (self.current_page - 1) * self.cages_per_page + 1
        end_idx = min(start_idx + self.cages_per_page - 1, self.cage_count)

        # 显示当前页的笼子面板，减小水平间距
        display_index = 0
        for cage_id in range(start_idx, end_idx + 1):
            if cage_id in self.all_cage_panels:
                cage_panel = self.all_cage_panels[cage_id]
                self.visible_cage_panels.append(cage_panel)

                row = display_index // 2
                col = display_index % 2
                self.scroll_layout.addWidget(cage_panel, row, col, Qt.AlignmentFlag.AlignCenter)
                display_index += 1

        # 设置列拉伸，减小水平间���
        for col in range(2):
            self.scroll_layout.setColumnStretch(col, 0)  # 改为0，不拉伸
        self.scroll_layout.setRowStretch(0, 0)  # 改为0，不拉伸
        self.scroll_layout.setRowStretch(1, 0)  # 改为0，不拉伸

        # 更新分页控件状态
        self._update_pagination_controls()

    def _update_pagination_controls(self):
        """更新分页控件状态"""
        # 只有当笼子数量大于每页显示数量时才显示分页控件
        show_pagination = self.cage_count > self.cages_per_page

        self.prev_page_btn.setVisible(show_pagination)
        self.next_page_btn.setVisible(show_pagination)
        self.page_label.setVisible(show_pagination)

        if show_pagination:
            self.prev_page_btn.setEnabled(self.current_page > 1)
            self.next_page_btn.setEnabled(self.current_page < self.total_pages)
            self.page_label.setText(f"{self.current_page} / {self.total_pages}")

    def _on_cage_status_changed(self, cage_id, status):
        """笼子状态改变回调"""
        print(f"笼子 {cage_id} 状态: {status}")

    def start_all_tracking(self):
        """开始所有笼子的追踪"""
        for panel in self.all_cage_panels.values():
            panel.start_tracking()

    def stop_all_tracking(self):
        """停止所有笼子的追踪"""
        for panel in self.all_cage_panels.values():
            panel.stop_tracking()

    def clear_all_trajectory(self):
        """清除所有轨迹"""
        for panel in self.all_cage_panels.values():
            panel.clear_trajectory()

    def on_prev_page(self):
        """上一页"""
        if self.current_page > 1:
            self.current_page -= 1
            self._update_cage_display()

    def on_next_page(self):
        """下一页"""
        if self.current_page < self.total_pages:
            self.current_page += 1
            self._update_cage_display()

    def get_all_trajectory_data(self):
        """获取所有轨迹数据"""
        all_data = {
            "cage_count": self.cage_count,
            "mice_per_cage": self.mice_per_cage,
            "cages": []
        }

        for cage_id in sorted(self.all_cage_panels.keys()):
            cage_data = self.all_cage_panels[cage_id].get_trajectory_data()
            all_data["cages"].append(cage_data)

        return all_data