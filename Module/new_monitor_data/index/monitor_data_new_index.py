import typing

from PyQt6 import QtGui
from PyQt6.QtCore import QRect, QSize
from PyQt6.QtWidgets import QDockWidget, QWidget, QVBoxLayout

from Module.new_experiment.ui.group_window import GroupWindow
from Module.new_monitor_data.ui.monitor_data_new import Ui_monitor_data_new
from Module.new_monitor_data.ui.table_column_check_list_view import Table_Column_check_list_view
from public.component.paging_exportcsv_table_widget import TableWidgetPaging
from public.function.Modbus.Modbus_Type import Modbus_Slave_Ids
from theme.ThemeQt6 import ThemedWindow


class Monitor_data_new_index(ThemedWindow):

    def resizeEvent(self, a0 :typing.Optional[QtGui.QResizeEvent]):
        new_size:QSize = a0.size()
        #


        if self.left_bottom_dock_widget is not None:
            self.left_bottom_dock_widget.resize(int(new_size.width() * 0.6), int(new_size.height() * 0.4))
        if self.left_top_dock_widget is not None:
            self.left_top_dock_widget.resize(int(new_size.width() * 0.6), int(new_size.height()* 0.6))
        if self.right_dock_widget is not None:
            self.right_dock_widget.resize(int(new_size.width() * 0.4), int(new_size.height()))


    def __init__(self, parent=None, geometry: QRect = None, title=""):
        super().__init__()
        self.left_top_dock_widget:QDockWidget = None
        self.left_top_dock_widget_content:TableWidgetPaging=None
        self.left_bottom_dock_widget:QDockWidget = None
        self.right_dock_widget:QDockWidget = None
        self.right_dock_widget_content: Table_Column_check_list_view = None

        # 实例化ui
        self._init_ui(parent, geometry, title)
        # 实例化自定义ui
        self._init_customize_ui()
        # 实例化功能
        self._init_function()
        # 加载qss样式表
        self._init_style_sheet()
        pass

        # 实例化ui

    def _init_ui(self, parent=None, geometry: QRect = None, title=""):
        # 将ui文件转成py文件后 直接实例化该py文件里的类对象  uic工具转换之后就是这一段代码
        # 有父窗口添加父窗口
        if parent != None and geometry != None:
            self.setParent(parent)
            self.setGeometry(geometry)
        else:
            pass

        self.ui = Ui_monitor_data_new()

        self.ui.setupUi(self)

        self._retranslateUi()

        pass
    def _init_customize_ui(self) -> None:
        self.delete_central_widget()
        self.left_top_dock_widget:QDockWidget = self.findChild(QDockWidget, "left_top_dock_widget")

        left_top_dock_widget_content_Widget=QWidget()
        left_top_dock_widget_content_Widget.setObjectName("left_top_dock_widget_content_Widget")
        left_top_dock_widget_content_Widget_layout = QVBoxLayout()
        left_top_dock_widget_content_Widget_layout.setObjectName("left_top_dock_widget_content_Widget_layout")
        # self.left_top_dock_widget_content: TableWidgetPaging = TableWidgetPaging(type=Modbus_Slave_Ids.UFC,
        #                                                                          data_type="monitor_data",
        #                                                                          parent=left_top_dock_widget_content_Widget_layout,
        #                                                                          mouse_cage_number=0)
        # left_top_dock_widget_content_Widget.setLayout(left_top_dock_widget_content_Widget_layout)
        self.left_top_dock_widget.setWidget( left_top_dock_widget_content_Widget)

        self.left_bottom_dock_widget = self.findChild(QDockWidget, "left_bottom_dock_widget")

        self.right_dock_widget = self.findChild(QDockWidget, "right_dock_widget")
        self.right_dock_widget_content = Table_Column_check_list_view()
        self.right_dock_widget.setWidget(self.right_dock_widget_content)
        pass
