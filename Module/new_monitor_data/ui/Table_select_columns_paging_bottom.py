"""
表头初始为空，通过信号（按钮点击）置换表头并分页加载数据（每页 10 条），
当垂直滚动条滑到底部时自动加载下一页。
"""
import sys
import random
import time

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton,
    QScrollArea, QTableWidget, QTableWidgetItem, QMessageBox, QLabel, QSpinBox, QHBoxLayout, QListWidget, QFileDialog
)
from PyQt6.QtCore import Qt, pyqtSignal
from loguru import logger

from Module.new_monitor_data.ui.Custom_table import CustomTableWidget
from public.component.dialog.custom.InfoDialog import InfoDialog
from public.config.Data_Column import Data_column_list
from public.config_class.global_setting import global_setting
from public.dao.SQLite.Monitor_Datas_Handle import Monitor_Datas_Handle
from public.entity.BaseWindow import BaseWindow
from public.entity.MyQThread import MyQThread
from public.entity.dict.AdvancedFuzzyDict import FuzzyDict
from public.entity.queue.ObjectQueueItem import ObjectQueueItem
from public.util.time_util import time_util


class DataFetcher(MyQThread):
    data_fetched = pyqtSignal(dict)  # 信号传递值

    def __init__(self, name,gid,page_size,page,all_column_datas=[]):
        super().__init__(name=name)
        self.gid = gid
        self.page_size = page_size
        self.page = page
        self.all_column_datas = all_column_datas

        # 数据库操作类
        self.handle: Monitor_Datas_Handle = None

    def stop(self):
        if self.handle is not None:
            self.handle.stop()
            self.handle=None
        super().stop()
        # if self.handle is not None:
        #     self.handle.stop()

    def pause(self):
        super().pause()
        # if self.handle is not None:
        #     self.handle.stop()

    def dosomething(self):
        # if self.handle is not None:
        #     self.handle.stop()
        if self.handle is None:
            self.handle = Monitor_Datas_Handle()  # # 创建数据库
        data =[]


        datas = self.handle.query_epoch_data_all_tables_paging(gid=self.gid,page=self.page,page_size=self.page_size,all_column_datas=self.all_column_datas)
        if datas is None:
            datas = []
        # logger.error(f"get_data:{datas}")
        self.data_fetched.emit(datas)

        time.sleep(0.3)  # 每秒获取一次数据
class Table_select_columns_paging_bottom(BaseWindow):

    def __init__(self,gid):
        super().__init__()
        self.gid = gid
        # 获取数据线程
        self.data_fetcher_thread:DataFetcher = None
        self._init_ui()

        self._init_function()
    def _init_ui(self):
        self.setWindowTitle("带分页器的 QTableWidget（PyQt6）")


        # ---- 数据和列定义 ----
        self.all_columns = ["时间"]
        self.all_column_datas = []
        # 数据
        self.total_items = 0  # 总条数
        #[{表头1:数据，表头2:数据，}....]
        self.data = []

        # 分页参数（默认）
        self.page_size = 1000
        self.current_page = 1  # 1-based page index

        # ---- 主界面布局 ----
        central = QWidget()
        self.setCentralWidget(central)
        main_vbox = QVBoxLayout(central)



        # 分页器区域（放在表格上方）
        pager_widget = QWidget()
        pager_layout = QHBoxLayout(pager_widget)
        pager_layout.setContentsMargins(0, 0, 0, 0)
        pager_layout.setSpacing(8)

        # 分页控件：首页/上一页/下一页/尾页
        self.first_btn = QPushButton("首页")
        self.prev_btn = QPushButton("上一页")
        self.next_btn = QPushButton("下一页")
        self.last_btn = QPushButton("尾页")
        self.first_btn.clicked.connect(lambda: self.go_to_page(1))
        self.prev_btn.clicked.connect(lambda: self.go_to_page(self.current_page - 1))
        self.next_btn.clicked.connect(lambda: self.go_to_page(self.current_page + 1))
        self.last_btn.clicked.connect(lambda: self.go_to_page(self.total_pages))

        for w in (self.first_btn, self.prev_btn, self.next_btn, self.last_btn):
            pager_layout.addWidget(w)

        # 分页跳转：页号输入 + 跳转按钮
        pager_layout.addWidget(QLabel(" 跳转到第"))
        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setValue(1)
        self.page_spin.setFixedWidth(80)
        pager_layout.addWidget(self.page_spin)
        self.goto_btn = QPushButton("跳转")
        self.goto_btn.clicked.connect(lambda: self.go_to_page(self.page_spin.value()))
        pager_layout.addWidget(self.goto_btn)



        self.zero_calibration_btn =QPushButton("校零")
        self.range_calibration_btn = QPushButton("校量程")
        self.calibration_btn = QPushButton("校零且量程")
        pager_layout.addWidget(self.zero_calibration_btn)
        pager_layout.addWidget(self.range_calibration_btn)
        pager_layout.addWidget(self.calibration_btn)

        # 每页显示条数：SpinBox 或 ComboBox
        pager_layout.addWidget(QLabel(" 每页显示"))
        self.page_size_spin = QSpinBox()
        self.page_size_spin.setMinimum(1)
        self.page_size_spin.setMaximum(1000)
        self.page_size_spin.setValue(self.page_size)
        self.page_size_spin.setFixedWidth(80)
        self.page_size_spin.valueChanged.connect(self.on_page_size_changed)
        pager_layout.addWidget(self.page_size_spin)
        pager_layout.addWidget(QLabel("条"))

        # 显示总条数与总页数
        self.info_label = QLabel(self._info_text())
        pager_layout.addStretch()
        pager_layout.addWidget(self.info_label)

        main_vbox.addWidget(pager_widget)

        # Scroll area 包含 QTableWidget
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        main_vbox.addWidget(self.scroll_area, 3)

        # QTableWidget 初始无列
        self.table =CustomTableWidget()
        self.table.setMouseTracking(True)# 启用鼠标跟踪
        self.table.setColumnCount(0)
        self.table.setRowCount(0)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        # 将表格放入滚动区域
        self.scroll_area.setWidget(self.table)

        # Scroll area2 包含 QListView

        h_layout = QHBoxLayout()
        tip_label=QLabel("操作（操作必须手动导出数据，否则停止实验和关闭程序不会导出操作数据！）:")
        # 创建导出按钮
        self.export_button = QPushButton("导出操作")
        self.export_button.setMaximumHeight(40)
        h_layout.addWidget(tip_label)
        h_layout.addWidget(self.export_button)
        main_vbox.addLayout(h_layout)

        self.scroll_area_2 = QScrollArea()
        self.scroll_area_2.setWidgetResizable(True)
        # 创建滚动区域内的内容窗口部件
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        # 创建 QListWidget
        self.list_widget = QListWidget()
        self.list_widget.setMinimumHeight(300)

        # 添加组件到滚动布局
        scroll_layout.addWidget(self.list_widget)

        # 设置滚动区域的内容
        self.scroll_area_2.setWidget(scroll_content)
        main_vbox.addWidget(self.scroll_area_2,1)
        # 初始时分页器不可用，直到表头被置换
        self.set_pager_enabled(False)
    def _init_function(self):
        # 绑定按钮事件
        self.zero_calibration_btn.clicked.connect(self.zero_calibration_start)
        self.range_calibration_btn.clicked.connect(self.range_calibration_start)
        self.calibration_btn.clicked.connect(self.calibration_start)
        self.export_button.clicked.connect(self.export_opera_data)
        pass
    def export_opera_data(self):
        """导出所有操作数据功能"""
        try:
            # 获取文件保存路径
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "保存所有数据",
                "all_data.txt",
                "文本文件 (*.txt);;所有文件 (*)"
            )

            if file_path:
                # 获取列表中的所有数据
                all_items = []
                for i in range(self.list_widget.count()):
                    item = self.list_widget.item(i)
                    all_items.append(item.text())

                # 写入文件
                with open(file_path, 'w', encoding='utf-8') as file:
                    for item_text in all_items:
                        file.write(item_text + '\n')

                QMessageBox.information(
                    self,
                    "导出成功",
                    f"已导出 {len(all_items)} 项数据到:\n{file_path}"
                )

        except Exception as e:
            QMessageBox.critical(
                self,
                "导出失败",
                f"导出过程中发生错误:\n{str(e)}"
            )
        pass
    # ---------- 属性辅助 ----------
    @property
    def total_pages(self) -> int:
        if self.page_size <= 0:
            return 1
        return (self.total_items + self.page_size - 1) // self.page_size

    # ---------- UI 与逻辑 ----------
    def _info_text(self) -> str:
        return f"共 {self.total_items} 条 | 共 {self.total_pages} 页 | 当前第 {self.current_page} 页"

    def set_pager_enabled(self, enabled: bool):
        """启用/禁用分页器控件（除置换表头按钮外）"""
        for w in (
            self.first_btn, self.prev_btn, self.next_btn, self.last_btn,
            self.page_spin, self.goto_btn, self.page_size_spin
        ):
            w.setEnabled(enabled)

    def set_init_value(self):
        """
        设置初始值
        :return:
        """
        # ---- 数据和列定义 ----
        self.all_columns = ["时间"]
        self.all_column_datas = []
        # 数据
        self.total_items = 0  # 总条数
        # [{表头1:数据，表头2:数据，}....]
        self.data = []



    def find_columns_by_id(self, ids):
        """根据ids寻找data ——column数据"""
        if ids is None or len(ids) == 0:
            return []
        for id in ids:
            id =id-1
            if id >=0 and id < len(Data_column_list.Data_list.value):
                self.all_column_datas.append(Data_column_list.Data_list.value[id])
                self.all_columns.append(Data_column_list.Data_list.value[id].value["column_text"])
            pass
    def on_replace_headers(self,ids:list):
        """信号触发：置换表头并加载第一页"""
        self.set_init_value()
        self.find_columns_by_id(ids)


        # 置换列
        cols = self.all_columns
        self.table.setColumnCount(len(cols))
        self.table.setHorizontalHeaderLabels(cols)


        # 重置分页状态到第一页
        self.current_page = 1
        self.page_size = self.page_size_spin.value()
        self.page_spin.setValue(1)
        self.page_spin.setMaximum(max(1, self.total_pages))
        self.info_label.setText(self._info_text())

        # 启用分页器
        self.set_pager_enabled(True)
        #
        # 加载第一页
        # self.update_page()

        if self.data_fetcher_thread is None :
            self.data_fetcher_thread = DataFetcher(name="tab_2_tab_0_table_data_fetch_thread",gid = self.gid,page=self.current_page,page_size=self.page_size)
            self.data_fetcher_thread.data_fetched.connect(self.update_page)
        self.data_fetcher_thread.all_column_datas = self.all_column_datas
        if not self.data_fetcher_thread.isRunning():
            self.data_fetcher_thread.start()
    def on_page_size_changed(self, new_page_size: int):
        """当每页显示数改变时，重新计算总页数并跳转到合理页码（保持在相同数据范围尽可能）"""
        if new_page_size <= 0:
            return
        old_page_size = self.page_size
        old_first_item_index = (self.current_page - 1) * old_page_size  # 0-based index of first item on current page

        self.page_size = new_page_size
        if self.data_fetcher_thread is not None :
            self.data_fetcher_thread.page_size = self.page_size
        # 计算新的页数并更新 page_spin 的范围
        new_total_pages = self.total_pages
        self.page_spin.setMaximum(max(1, new_total_pages))

        # 计算新的 current_page，使得 old_first_item_index 仍然在新页中
        new_current_page = (old_first_item_index // self.page_size) + 1
        new_current_page = max(1, min(new_current_page, new_total_pages))
        self.current_page = new_current_page
        if self.data_fetcher_thread is not None :
            self.data_fetcher_thread.page = self.current_page
        self.page_spin.setValue(self.current_page)

        self.info_label.setText(self._info_text())
        # self.update_page()

    def go_to_page(self, page: int):
        """跳转到指定页（1-based），并刷新表格"""
        if not (1 <= page <= max(1, self.total_pages)):
            QMessageBox.warning(self, "页码错误", f"请输入有效页码：1 到 {max(1, self.total_pages)}")
            return
        self.current_page = page
        if self.data_fetcher_thread is not None :
            self.data_fetcher_thread.page = self.current_page
        # 保证 page_spin 与 info_label 同步
        self.page_spin.setValue(self.current_page)
        self.info_label.setText(self._info_text())
        # self.update_page()

    def update_page(self,result:dict):
        """
        根据 current_page 与 page_size 刷新表格显示（只显示当前页数据）
        :param result: [{表名:数据}....]
        :return: 
        """
        # 置换列

        self.all_columns=result['columns_title']
        cols = result['columns_title']
        self.table.setColumnCount(len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        # print(result)
        # 如果表头还没置换，不加载任何数据
        if self.table.columnCount() == 0:
            return



        page_records = result['rows']
        n_rows = len(page_records)

        # 设置行数与列数
        self.table.setRowCount(n_rows)
        self.table.setColumnCount(len(self.all_columns))

        # 填充当前页的行
        for row_idx, record in enumerate(page_records):
            record :dict
            index = 0
            for col_key, col_record in record.items():
                # 将二氧化碳的值和氧气的值小数点后4位。
                if "oxygen" in col_key or "CO2" in col_key:
                    item = QTableWidgetItem(f"{col_record:.04f}"  if col_record is not None else None)
                else:
                    item = QTableWidgetItem(str(col_record))
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                self.table.setItem(row_idx, index, item)
                index+=1
        self.table.resizeColumnsToContents()
        # self.current_page=result['page']
        self.total_items=result['total_items']
        # 更新分页信息与按钮状态
        self.info_label.setText(self._info_text())
        self.page_spin.setMaximum(max(1, self.total_pages))
        # self.page_spin.setValue(self.current_page)
        self._update_nav_buttons()

        # 如果页内行较少导致表格高度不足以出现滚动，可以选择调整最低高度或不做处理（这里不强制加载更多）
        # 若需要自动扩展以填满视图，可以在这里考虑加载更多或调整策略。

    def _update_nav_buttons(self):
        """根据 current_page 与 total_pages 更新上一页/下一页按钮可用性"""
        tp = max(1, self.total_pages)
        self.first_btn.setEnabled(self.current_page > 1)
        self.prev_btn.setEnabled(self.current_page > 1)
        self.next_btn.setEnabled(self.current_page < tp)
        self.last_btn.setEnabled(self.current_page < tp)

    # 如果需要对外提供刷新数据的接口，可以添加方法从数据源重新加载 self.data / self.total_items
    # 并在替换表头后或数据变化时调用 self.go_to_page(1) 或 self.update_page() 来刷新界面。
    def zero_calibration_start(self):
        #校0按钮事件
        send_message_queue = global_setting.get_setting("send_message_queue")
        send_message_queue.put(ObjectQueueItem(origin='Table_select_columns_paging_bottom', to='main_monitor_data', title='start_zero_calibration',
                                               data=None,
                                               time=time_util.get_format_from_time(time.time())))
        msg_box = InfoDialog(title="校0", info=f"确认校0开始，校准完成还需要至少4轮次时间，请耐心等待", icon=QMessageBox.Icon.Information)
        msg_box.exec()
        self.list_widget.insertItem(0,f"{time_util.get_format_from_time(time.time())}-校0按钮被点击时间")
        pass
    def range_calibration_start(self):
        #校span按钮事件
        #校0按钮事件
        send_message_queue = global_setting.get_setting("send_message_queue")
        send_message_queue.put(ObjectQueueItem(origin='Table_select_columns_paging_bottom', to='main_monitor_data', title='start_span_calibration',
                                               data=None,
                                               time=time_util.get_format_from_time(time.time())))
        msg_box = InfoDialog(title="校span", info=f"确认校span开始，校准完成还需要至少3-4轮次时间，请耐心等待", icon=QMessageBox.Icon.Information)
        msg_box.exec()
        self.list_widget.insertItem(0,f"{time_util.get_format_from_time(time.time())}-校span按钮被点击时间")
        pass
    def calibration_start(self):
        #校0校span按钮事件
        #校0按钮事件
        send_message_queue = global_setting.get_setting("send_message_queue")
        send_message_queue.put(ObjectQueueItem(origin='Table_select_columns_paging_bottom', to='main_monitor_data', title='start_calibration',
                                               data=None,
                                               time=time_util.get_format_from_time(time.time())))
        msg_box = InfoDialog(title="校0和校span", info=f"确认校0和校span开始，校准完成还需要至少3-5轮次时间，请耐心等待", icon=QMessageBox.Icon.Information)
        msg_box.exec()
        self.list_widget.insertItem(0,f"{time_util.get_format_from_time(time.time())}-校0和校span按钮被点击时间")
        pass


def main():
    app = QApplication(sys.argv)
    w = Table_select_columns_paging_bottom()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()