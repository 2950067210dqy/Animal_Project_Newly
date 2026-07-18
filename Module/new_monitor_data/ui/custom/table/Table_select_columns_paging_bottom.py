"""
表头初始为空，通过信号（按钮点击）置换表头并分页加载数据（每页 10 条），
当垂直滚动条滑到底部时自动加载下一页。
"""
import sys
import threading
import time

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton,
    QScrollArea, QTableWidget, QTableWidgetItem, QMessageBox, QLabel, QSpinBox, QHBoxLayout, QHeaderView
)
from PyQt6.QtCore import Qt, pyqtSignal

from Module.new_monitor_data.ui.custom.table.Custom_table import CustomTableWidget
from public.config.Data_Column import Data_column_list
from public.config_class.global_setting import global_setting
from public.dao.SQLite.Monitor_Datas_Handle import Monitor_Datas_Handle
from public.entity.MyQThread import MyQThread
from theme.ThemeQt6 import ThemedWindow


class DataFetcher(MyQThread):
    data_fetched = pyqtSignal(int, dict)  # 信号传递值
    _shared_instance = None
    _shared_lock = threading.Lock()

    @classmethod
    def shared(cls):
        with cls._shared_lock:
            if cls._shared_instance is None:
                cls._shared_instance = cls(
                    name="new_monitor_data_table_shared_fetch_thread",
                    gid=-1,
                    page_size=200,
                    page=1,
                )
            if not cls._shared_instance.isRunning():
                cls._shared_instance.start()
            return cls._shared_instance

    def __init__(self, name,gid,page_size,page,all_column_datas=[]):
        super().__init__(name=name)
        self.gid = gid
        self.page_size = page_size
        self.page = page
        self.all_column_datas = all_column_datas
        self.refresh_interval = 3
        self.auto_refresh_enabled = True
        self._fetch_requested = threading.Event()
        self._request_lock = threading.RLock()
        self._requests = {}

        # 数据库操作类
        self.handle: Monitor_Datas_Handle = None

    def register(self, gid, page, page_size, all_column_datas, auto_refresh_enabled):
        with self._request_lock:
            self._requests[gid] = {
                "page": page,
                "page_size": page_size,
                "all_column_datas": list(all_column_datas),
                "auto_refresh_enabled": auto_refresh_enabled,
                "fetch_requested": True,
            }
        self._fetch_requested.set()

    def unregister(self, gid):
        with self._request_lock:
            self._requests.pop(gid, None)
        self._fetch_requested.set()

    def request_fetch(self, gid=None):
        with self._request_lock:
            if gid is None:
                for request in self._requests.values():
                    request["fetch_requested"] = True
            elif gid in self._requests:
                self._requests[gid]["fetch_requested"] = True
        self._fetch_requested.set()

    def set_auto_refresh_enabled(self, enabled, gid=None):
        with self._request_lock:
            if gid is None:
                self.auto_refresh_enabled = enabled
            elif gid in self._requests:
                self._requests[gid]["auto_refresh_enabled"] = enabled
        self._fetch_requested.set()

    def _sleep_interruptible(self, seconds):
        end_time = time.time() + seconds
        while time.time() < end_time:
            if self._stop_requested or self.isInterruptionRequested() or self._fetch_requested.is_set():
                break
            time.sleep(min(0.1, max(0, end_time - time.time())))

    def stop(self):
        super().stop()
        self.requestInterruption()
        self._fetch_requested.set()
        if self.handle is not None:
            self.handle.stop()
            self.handle=None
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

        with self._request_lock:
            requests = {
                gid: request.copy()
                for gid, request in self._requests.items()
                if request.get("auto_refresh_enabled") or request.get("fetch_requested")
            }
            for gid in requests:
                if gid in self._requests:
                    self._requests[gid]["fetch_requested"] = False
            has_auto_refresh = any(
                request.get("auto_refresh_enabled") for request in self._requests.values()
            )

        self._fetch_requested.clear()
        if not requests:
            self._sleep_interruptible(0.2)
            return

        for gid, request in requests.items():
            if self._stop_requested or self.isInterruptionRequested():
                return
            datas = self.handle.query_epoch_data_all_tables_paging(
                gid=gid,
                page=request["page"],
                page_size=request["page_size"],
                all_column_datas=request["all_column_datas"],
            )
            if datas is None:
                datas = {}

            if not self._stop_requested and not self.isInterruptionRequested():
                self.data_fetched.emit(gid, datas)

        self._sleep_interruptible(self.refresh_interval if has_auto_refresh else 0.2)
class Table_select_columns_paging_bottom(ThemedWindow):
    def hide(self):
        self._detach_data_fetcher()
        super().hide()
    def __init__(self,gid):
        super().__init__()
        self.gid = gid
        # 获取数据线程
        self.data_fetcher_thread:DataFetcher = None
        self._init_ui()

        self._init_function()

    def _attach_data_fetcher(self):
        if self.data_fetcher_thread is None:
            self.data_fetcher_thread = DataFetcher.shared()
            self.data_fetcher_thread.data_fetched.connect(self.update_page)

        self.data_fetcher_thread.register(
            gid=self.gid,
            page=self.current_page,
            page_size=self.page_size,
            all_column_datas=self.all_column_datas,
            auto_refresh_enabled=self.current_page == 1,
        )

    def _detach_data_fetcher(self):
        if self.data_fetcher_thread is None:
            return
        thread = self.data_fetcher_thread
        self.data_fetcher_thread = None
        try:
            thread.data_fetched.disconnect(self.update_page)
        except (TypeError, RuntimeError):
            pass
        thread.unregister(self.gid)

    def closeEvent(self, event):
        self._detach_data_fetcher()
        super().closeEvent(event)
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
        self.page_size = 200
        self.current_page = 1  # 1-based page index
        self._columns_sized = False

        # ---- 主界面布局 ----
        central = QWidget()
        self.setCentralWidget(central)
        main_vbox = QVBoxLayout(central)

        self.setMinimumWidth(1100)
        # self.setMinimumHeight(500)

        # 分页器区域（放在表格上方）
        # Scroll area 包含 QTableWidget
        self.page_scroll_area = QScrollArea()
        self.page_scroll_area.setWidgetResizable(True)
        pager_widget = QWidget()
        pager_layout = QHBoxLayout(pager_widget)
        pager_layout.setContentsMargins(0, 0, 0, 0)
        pager_layout.setSpacing(8)
        self.page_scroll_area.setWidget(pager_widget)
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

        main_vbox.addWidget(self.page_scroll_area)

        # Scroll area 包含 QTableWidget
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        main_vbox.addWidget(self.scroll_area, stretch=7)

        # QTableWidget 初始无列
        self.table =CustomTableWidget()


        self.table.setMouseTracking(True)# 启用鼠标跟踪
        self.table.setColumnCount(0)
        self.table.setRowCount(0)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        # 动态改变冻结列
        self.table.set_frozen_columns_by_headers(
            left_headers=["序号","鼠笼号"],  # 左侧冻结
            right_headers=["获取时间"]  # 右侧冻结
        )
        # 将表格放入滚动区域
        self.scroll_area.setWidget(self.table)



        # 初始时分页器不可用，直到表头被置换
        self.set_pager_enabled(False)
    def _init_function(self):

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
        self._columns_sized = False


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

        self._attach_data_fetcher()
    def on_page_size_changed(self, new_page_size: int):
        """当每页显示数改变时，重新计算总页数并跳转到合理页码（保持在相同数据范围尽可能）"""
        if new_page_size <= 0:
            return
        old_page_size = self.page_size
        old_first_item_index = (self.current_page - 1) * old_page_size  # 0-based index of first item on current page

        self.page_size = new_page_size
        # 计算新的页数并更新 page_spin 的范围
        new_total_pages = self.total_pages
        self.page_spin.setMaximum(max(1, new_total_pages))

        # 计算新的 current_page，使得 old_first_item_index 仍然在新页中
        new_current_page = (old_first_item_index // self.page_size) + 1
        new_current_page = max(1, min(new_current_page, new_total_pages))
        self.current_page = new_current_page
        if self.data_fetcher_thread is not None :
            self.data_fetcher_thread.register(
                gid=self.gid,
                page=self.current_page,
                page_size=self.page_size,
                all_column_datas=self.all_column_datas,
                auto_refresh_enabled=self.current_page == 1,
            )
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
            self.data_fetcher_thread.register(
                gid=self.gid,
                page=self.current_page,
                page_size=self.page_size,
                all_column_datas=self.all_column_datas,
                auto_refresh_enabled=self.current_page == 1,
            )
        # 保证 page_spin 与 info_label 同步
        self.page_spin.setValue(self.current_page)
        self.info_label.setText(self._info_text())
        # self.update_page()

    def update_page(self,result_gid:int,result:dict):
        """
        根据 current_page 与 page_size 刷新表格显示（只显示当前页数据）
        :param result: [{表名:数据}....]
        :return: 
        """
        if result_gid != self.gid or not result:
            return

        result_page = result.get('page', self.current_page)
        if result_page != self.current_page:
            return

        cols = result['columns_title']
        if cols != self.all_columns:
            self.all_columns = cols
            self.table.setColumnCount(len(cols))
            self.table.setHorizontalHeaderLabels(cols)
            self._columns_sized = False
        # print(result)
        # 如果表头还没置换，不加载任何数据
        if self.table.columnCount() == 0:
            return



        page_records = result['rows']
        n_rows = len(page_records)
        self.total_items=result['total_items']

        self.table.setUpdatesEnabled(False)
        try:
            # 设置行数与列数
            self.table.setRowCount(n_rows)
            self.table.setColumnCount(len(self.all_columns))

            # 填充当前页的行
            for row_idx, record in enumerate(page_records):
                record: dict
                # logger.error(f"{record}")
                index = 0
                # 检查是否需要将整行设置为红色 remarks 存在则标红
                should_highlight_row = False
                if record.get("remarks") is not None and len(str(record.get("remarks")).strip()) > 3:
                    should_highlight_row = True
                for col_key, col_record in record.items():
                    if col_key == "mouse_cage_number":
                        reference_cage = int(global_setting.get_setting('configer')['mouse_cage']['reference'])
                        if col_record == reference_cage:
                            col_record = "参考笼"
                    # 将二氧化碳的值和氧气的值小数点后4位。
                    if "oxygen" in col_key or "CO2" in col_key:
                        # 区分校0和校span的氧气 因为他们的值有可能是字符串
                        if isinstance(col_record, str):
                            # 校0和校span的氧气
                            item = QTableWidgetItem(str(col_record) if not isinstance(col_record, str) else col_record)
                        else:
                            item = QTableWidgetItem(f"{col_record:.04f}" if col_record is not None else str(None))
                    else:
                        item = QTableWidgetItem(str(col_record) if not isinstance(col_record, str) else col_record)
                    if should_highlight_row:
                        item.setForeground(QColor(255, 0, 0))  # 红色
                    item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                    self.table.setItem(row_idx, index, item)
                    index += 1
        finally:
            self.table.setUpdatesEnabled(True)

        if not self._columns_sized:
            self.table.resizeColumnsToContents()
            self._columns_sized = True
        # self.current_page=result['page']
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



def main():
    app = QApplication(sys.argv)
    w = Table_select_columns_paging_bottom(gid=1)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
