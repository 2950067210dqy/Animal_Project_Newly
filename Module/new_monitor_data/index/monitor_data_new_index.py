import typing

from PyQt6 import QtGui
from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtWidgets import QDockWidget, QWidget, QVBoxLayout, QLabel

from Module.new_experiment.ui.group_window import GroupWindow
from Module.new_monitor_data.ui.Table_select_columns_paging_bottom import Table_select_columns_paging_bottom
from Module.new_monitor_data.ui.monitor_data_new import Ui_monitor_data_new
from Module.new_monitor_data.ui.monitor_data_windows import MonitorDataWindows
from Module.new_monitor_data.ui.table_column_check_list_view import Table_Column_check_list_view
from public.component.paging_exportcsv_table_widget import TableWidgetPaging
from public.config_class.global_setting import global_setting
from public.entity.experiment_setting_entity import Experiment_setting_entity
from public.function.Modbus.Modbus_Type import Modbus_Slave_Ids
from theme.ThemeQt6 import ThemedWindow


class Monitor_data_new_index(ThemedWindow):
    def hideEvent(self, a0: typing.Optional[QtGui.QHideEvent]) -> None:
        for widget in self.left_top_dock_widget_content._docks_widget:
            widget: Table_select_columns_paging_bottom
            if widget is not None and widget.data_fetcher_thread is not None and widget.data_fetcher_thread.isRunning():
                widget.data_fetcher_thread.pause()

        pass
    def showEvent(self, a0: typing.Optional[QtGui.QShowEvent]) -> None:
        for widget in self.left_top_dock_widget_content._docks_widget:
            widget: Table_select_columns_paging_bottom
            if widget is not None and widget.data_fetcher_thread is not None and  widget.data_fetcher_thread.isRunning():

                widget.data_fetcher_thread.resume()
            elif widget.data_fetcher_thread is not None and not widget.data_fetcher_thread.isRunning():

                widget.data_fetcher_thread.start()
        # pass
        pass
    def closeEvent(self, a0: typing.Optional[QtGui.QCloseEvent]) -> None:
        pass
    def resizeEvent(self, a0 :typing.Optional[QtGui.QResizeEvent]):
        new_size:QSize = a0.size()
        #


        if self.left_bottom_dock_widget is not None:
            self.left_bottom_dock_widget.widget().resize(int(new_size.width() * 0.8), int(new_size.height() * 0.4))
            self.left_bottom_dock_widget.resize(int(new_size.width() * 0.8), int(new_size.height() * 0.4))

        if self.left_top_dock_widget is not None:
            self.left_top_dock_widget.widget().resize(int(new_size.width() * 0.8), int(new_size.height() * 0.6))
            self.left_top_dock_widget.resize(int(new_size.width() * 0.8), int(new_size.height()* 0.6))

        if self.right_top_dock_widget is not None:
            self.right_top_dock_widget.widget().resize(int(new_size.width() * 0.2), int(new_size.height()*0.4))
            self.right_top_dock_widget.resize(int(new_size.width() * 0.2), int(new_size.height()*0.4))
        if self.right_bottom_dock_widget is not None:
            self.right_bottom_dock_widget.widget().resize(int(new_size.width() * 0.2), int(new_size.height()*0.6))
            self.right_bottom_dock_widget.resize(int(new_size.width() * 0.2), int(new_size.height()*0.6))

        self.setMinimumSize(0, 0)

    def __init__(self, parent=None, geometry: QRect = None, title=""):
        super().__init__()
        self.setMinimumSize(0,0)
        self.left_top_dock_widget:QDockWidget = None
        self.left_top_dock_widget_content:MonitorDataWindows=None
        self.left_bottom_dock_widget:QDockWidget = None
        self.right_top_dock_widget:QDockWidget = None
        self.right_top_dock_widget_content: Table_Column_check_list_view = None
        self.right_bottom_dock_widget:QDockWidget = None
        self.right_bottom_dock_widget_content: Table_Column_check_list_view = None

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

        self.left_top_dock_widget_content: MonitorDataWindows = MonitorDataWindows()
        self.left_top_dock_widget.setWidget( self.left_top_dock_widget_content)

        self.left_bottom_dock_widget:QDockWidget = self.findChild(QDockWidget, "left_bottom_dock_widget")

        self.right_top_dock_widget:QDockWidget = self.findChild(QDockWidget, "right_top_dock_widget")

        self.right_top_dock_widget_content = Table_Column_check_list_view(ok_btn_text="确定选择通道",datas_type=1)
        self.right_top_dock_widget.setWidget(self.right_top_dock_widget_content)

        self.right_top_dock_widget_content.set_table_column_signal.connect(self.create_table)




        # 这部分挪到数据处理区域
        self.right_bottom_dock_widget: QDockWidget = self.findChild(QDockWidget, "right_bottom_dock_widget")
        # self.right_bottom_dock_widget.hide()
        self.right_bottom_dock_widget_content = Table_Column_check_list_view(ok_btn_text="生成图表",datas_type=0)
        self.right_bottom_dock_widget.setWidget(self.right_bottom_dock_widget_content)

        self.right_bottom_dock_widget_content.set_table_column_signal.connect(
            self.create_table)

        pass
    def create_table(self,dict_ids:dict):
        if dict_ids is not None:
            type = dict_ids.get('type',"")
            if type == "column":
                for widget in self.left_top_dock_widget_content._docks_widget:
                    widget: Table_select_columns_paging_bottom
                    widget.on_replace_headers(dict_ids['data'])
                pass
            elif type == "group":
                settings: Experiment_setting_entity = global_setting.get_setting("experiment_setting", None)
                if settings:
                    gids = [group.id  for index,group in enumerate(settings.groups) if index in dict_ids['data']]
                    self.left_top_dock_widget_content.create_tiled_docks(n=len(gids),gids=gids)
                pass
            else:

                pass
        pass