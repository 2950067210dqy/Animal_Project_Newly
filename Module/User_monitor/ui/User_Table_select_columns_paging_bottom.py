import sys
import time

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton,
    QScrollArea, QTableWidget, QTableWidgetItem, QMessageBox, QLabel, QHBoxLayout, QListWidget, QFileDialog
)
from PyQt6.QtCore import Qt, pyqtSignal
from loguru import logger

from Module.User_monitor.ui.User_Custom_table import CustomTableWidget
from public.component.dialog.custom.InfoDialog import InfoDialog
from public.config.Data_Column import Data_column_list
from public.config_class.global_setting import global_setting
from public.dao.SQLite.Monitor_Datas_Handle import Monitor_Datas_Handle
from public.entity.BaseWindow import BaseWindow
from public.entity.MyQThread import MyQThread
from public.entity.queue.ObjectQueueItem import ObjectQueueItem
from public.util.time_util import time_util
from theme.ThemeQt6 import ThemedWindow


class DataFetcher(MyQThread):
    data_fetched = pyqtSignal(dict)  # 信号传递数据（字典格式）

    def __init__(self, name, gid, page_size, page, all_column_datas=[]):
        super().__init__(name=name)
        self.gid = gid
        self.page_size = page_size  # 每页条数（固定500）
        self.page = page  # 当前页码
        self.all_column_datas = all_column_datas
        self.handle: Monitor_Datas_Handle = None  # 数据库操 作实例

    def stop(self):
        if self.handle is not None:
            self.handle.stop()
            self.handle = None
        super().stop()

    def pause(self):
        super().pause()

    def dosomething(self):
        # 初始化数据库连接
        if self.handle is None:
            self.handle = Monitor_Datas_Handle()
        # 分页查询数据
        datas = self.handle.query_epoch_data_all_tables_paging(
            gid=self.gid,
            page=self.page,
            page_size=self.page_size,
            all_column_datas=self.all_column_datas
        )
        # 若查询结果为空，返回空字典
        if datas is None:
            datas = {}
        self.data_fetched.emit(datas)
        time.sleep(0.3)  # 避免请求过于频繁


class Table_select_columns_paging_bottom(ThemedWindow):
    def hide(self):
        # 窗口隐藏时停止数据线程
        if self.data_fetcher_thread is not None:
            self.data_fetcher_thread.stop()

    def __init__(self, gid):
        super().__init__()
        self.gid = gid
        self.data_fetcher_thread: DataFetcher = None  # 数据加载线程
        self._init_ui()
        self._init_function()

    def _init_ui(self):
        self.setWindowTitle("带分页器的 QTableWidget（PyQt6）")
        self.setMinimumWidth(1100)

        # ---- 核心数据与分页参数 ----
        self.all_columns = ["时间"]  # 表格列名（初始含时间列）
        self.all_column_datas = []  # 列对应的数据源配置
        self.total_items = 0  # 数据总条数
        self.data = []  # 存储当前页数据
        self.page_size = 500  # 固定每页500条（删除页大小调整功能）
        self.current_page = 1  # 当前页码（1-based）

        # ---- 主布局 ----
        central = QWidget()
        self.setCentralWidget(central)
        main_vbox = QVBoxLayout(central)

        # ---- 分页器区域（仅保留4个核心按钮）----
        self.page_scroll_area = QScrollArea()
        self.page_scroll_area.setWidgetResizable(True)
        pager_widget = QWidget()
        pager_layout = QHBoxLayout(pager_widget)
        pager_layout.setContentsMargins(0, 0, 0, 0)
        pager_layout.setSpacing(8)
        self.page_scroll_area.setWidget(pager_widget)

        # 1. 核心分页按钮（首页/上一页/下一页/尾页）
        self.first_btn = QPushButton("首页")
        self.prev_btn = QPushButton("上一页")
        self.next_btn = QPushButton("下一页")
        self.last_btn = QPushButton("尾页")
        # 绑定按钮点击事件
        self.first_btn.clicked.connect(lambda: self.go_to_page(1))
        self.prev_btn.clicked.connect(lambda: self.go_to_page(self.current_page - 1))
        self.next_btn.clicked.connect(lambda: self.go_to_page(self.current_page + 1))
        self.last_btn.clicked.connect(lambda: self.go_to_page(self.total_pages))

        # 添加按钮到分页布局
        for btn in (self.first_btn, self.prev_btn, self.next_btn, self.last_btn):
            pager_layout.addWidget(btn)

        # 2. 分页信息显示（总条数/总页数/当前页）
        pager_layout.addStretch()  # 右对齐信息标签
        self.info_label = QLabel(self._info_text())
        pager_layout.addWidget(self.info_label)

        main_vbox.addWidget(self.page_scroll_area)

        # ---- 表格区域 ----
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        main_vbox.addWidget(self.scroll_area, stretch=7)

        # 初始化表格（无初始列）
        self.table = CustomTableWidget()
        self.table.setMouseTracking(True)
        self.table.setColumnCount(0)
        self.table.setRowCount(0)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.scroll_area.setWidget(self.table)

        # ---- 操作日志与导出区域（保留原有功能）----
        h_layout = QHBoxLayout()
        tip_label = QLabel("操作（操作必须手动导出数据，否则停止实验和关闭程序不会导出操作数据！）:")
        self.export_button = QPushButton("导出操作")
        self.export_button.setMaximumHeight(40)
        h_layout.addWidget(tip_label)
        h_layout.addWidget(self.export_button)
        main_vbox.addLayout(h_layout)

        # 操作日志列表
        self.scroll_area_2 = QScrollArea()
        self.scroll_area_2.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        self.list_widget = QListWidget()
        self.list_widget.setMinimumHeight(300)
        scroll_layout.addWidget(self.list_widget)
        self.scroll_area_2.setWidget(scroll_content)
        main_vbox.addWidget(self.scroll_area_2, stretch=1)

        # 初始时分页器禁用（需先置换表头）
        self.set_pager_enabled(False)

    def _init_function(self):
        # 绑定导出按钮事件（保留原有功能）
        self.export_button.clicked.connect(self.export_opera_data)
        # 若原有校准按钮需保留，可在此补充绑定（示例代码中已注释，故暂不处理）

    def export_opera_data(self):
        """导出操作日志功能（保留原有逻辑）"""
        try:
            file_path, _ = QFileDialog.getSaveFileName(
                self, "保存所有数据", "all_data.txt", "文本文件 (*.txt);;所有文件 (*)"
            )
            if not file_path:
                return
            # 读取列表所有日志
            all_items = [self.list_widget.item(i).text() for i in range(self.list_widget.count())]
            # 写入文件
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(all_items))
            QMessageBox.information(self, "导出成功", f"已导出 {len(all_items)} 项数据到:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出错误:\n{str(e)}")

    # ---- 分页辅助方法 ----
    @property
    def total_pages(self) -> int:
        """计算总页数（向上取整）"""
        if self.page_size <= 0 or self.total_items == 0:
            return 1
        return (self.total_items + self.page_size - 1) // self.page_size

    def _info_text(self) -> str:
        """生成分页信息文本"""
        return f"共 {self.total_items} 条 | 共 {self.total_pages} 页 | 当前第 {self.current_page} 页"

    def set_pager_enabled(self, enabled: bool):
        """启用/禁用所有分页按钮"""
        for btn in (self.first_btn, self.prev_btn, self.next_btn, self.last_btn):
            btn.setEnabled(enabled)

    def set_init_value(self):
        """重置表格与分页数据（置换表头时调用）"""
        self.all_columns = ["时间"]
        self.all_column_datas = []
        self.total_items = 0
        self.data = []
        self.current_page = 1

    def find_columns_by_id(self, ids):
        """根据ID匹配列配置（保留原有逻辑）"""
        if not ids:
            return
        for id in ids:
            id_adjusted = id - 1  # 转换为0-based索引
            if 0 <= id_adjusted < len(Data_column_list.Data_list.value):
                col_data = Data_column_list.Data_list.value[id_adjusted]
                self.all_column_datas.append(col_data)
                self.all_columns.append(col_data.value["column_text"])

    # ---- 表头置换与数据加载核心逻辑 ----
    def on_replace_headers(self, ids: list):
        """信号触发：置换表头并加载第一页数据"""
        self.set_init_value()
        self.find_columns_by_id(ids)

        # 1. 更新表格列名
        self.table.setColumnCount(len(self.all_columns))
        self.table.setHorizontalHeaderLabels(self.all_columns)

        # 2. 初始化并启动数据线程
        if self.data_fetcher_thread is None:
            self.data_fetcher_thread = DataFetcher(
                name="tab_2_tab_0_table_data_fetch_thread",
                gid=self.gid,
                page=self.current_page,
                page_size=self.page_size,
                all_column_datas=self.all_column_datas
            )
            self.data_fetcher_thread.data_fetched.connect(self.update_page)
        # 更新线程的列配置（防止表头切换后数据不匹配）
        self.data_fetcher_thread.all_column_datas = self.all_column_datas
        self.data_fetcher_thread.page = self.current_page  # 确保加载第一页
        if not self.data_fetcher_thread.isRunning():
            self.data_fetcher_thread.start()

        # 3. 启用分页器
        self.set_pager_enabled(True)

    def go_to_page(self, page: int):
        """跳转到指定页（核心分页逻辑）"""
        # 页码合法性校验
        valid_page = max(1, min(page, self.total_pages))
        if valid_page != page:
            QMessageBox.warning(self, "页码错误", f"有效页码范围：1 ~ {self.total_pages}")
            return
        # 更新当前页并加载数据
        self.current_page = valid_page
        if self.data_fetcher_thread is not None:
            self.data_fetcher_thread.page = self.current_page
            # 若线程未运行，启动线程；若已运行，等待下一次数据刷新（通过线程循环）
            if not self.data_fetcher_thread.isRunning():
                self.data_fetcher_thread.start()
        # 更新分页信息显示
        self.info_label.setText(self._info_text())
        self._update_nav_buttons()  # 同步按钮状态

    def update_page(self, result: dict):
        """接收线程数据，更新表格内容（核心修改：鼠笼号强制转为整数）"""
        # 1. 提取结果中的列名与数据（兼容数据库返回格式）
        if "columns_title" not in result or "rows" not in result:
            logger.warning("数据格式错误：缺少 columns_title 或 rows 字段")
            return
        self.all_columns = result["columns_title"]
        page_records = result["rows"]
        self.total_items = result.get("total_items", 0)  # 更新总条数

        # 2. 清空并重置表格
        self.table.setRowCount(0)
        self.table.setColumnCount(len(self.all_columns))
        self.table.setHorizontalHeaderLabels(self.all_columns)

        # 3. 填充表格数据（核心修改：增加鼠笼号整数格式化）
        for row_idx, record in enumerate(page_records):
            self.table.insertRow(row_idx)
            col_idx = 0
            for col_key, col_val in record.items():
                final_val = ""  # 最终显示值，默认空（无空格）

                # -------------------------- 核心逻辑：分情况处理值 --------------------------
                # 情况1：当前是时间列（col_idx=0），按原有逻辑处理（None显示空）
                if col_idx == 0:
                    final_val = str(col_val) if col_val is not None else ""

                # 情况2：数据列（col_idx>0）
                else:
                    current_col_title = self.all_columns[col_idx]
                    is_cage_column = "鼠笼号" in current_col_title  # 判断是否为鼠笼号列

                    # 子情况2.1：原始值非None → 分列处理
                    if col_val is not None:
                        if is_cage_column:
                            # 鼠笼号列：强制转为整数（处理浮点数如1.0→1、字符串如"2.0"→2）
                            try:
                                # 先转为数字类型（兼容int/float/字符串格式数字）
                                num_val = float(col_val) if not isinstance(col_val, (int, float)) else col_val
                                final_val = str(int(num_val))  # 强制转int（如2.5→2，根据业务合理）
                            except (ValueError, TypeError):
                                # 无法转为数字的情况（如"未知"），直接显示原始值
                                final_val = str(col_val).strip()
                        else:
                            # 非鼠笼号列：按原有逻辑格式化
                            if isinstance(col_val, (int, float)):
                                if "oxygen" in col_key or "CO2" in col_key:
                                    final_val = f"{col_val:.04f}"  # 氧气/CO2保留4位小数
                                else:
                                    final_val = f"{col_val:.2f}"  # 其他数字保留2位小数
                            else:
                                final_val = str(col_val).strip()  # 非数字类型直接转字符串

                    # 子情况2.2：原始值为None → 继承上一行同列内容
                    else:
                        # 检查上一行是否存在（row_idx > 0 说明有上一行）
                        if row_idx > 0:
                            prev_item = self.table.item(row_idx - 1, col_idx)
                            # 若上一行单元格存在且有内容，直接继承（去除空格）
                            if prev_item is not None and prev_item.text().strip() != "":
                                final_val = prev_item.text().strip()
                            # 上一行无有效内容 → 显示空（无空格）
                            else:
                                final_val = ""
                        # 无上行数据（当前是第一行）→ 显示空（无空格）
                        else:
                            final_val = ""

                # -------------------------- 统一：设置单元格值与对齐 --------------------------
                item = QTableWidgetItem(final_val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                self.table.setItem(row_idx, col_idx, item)
                col_idx += 1

        # 4. 调整列宽与同步分页状态（原有逻辑不变）
        self.table.resizeColumnsToContents()
        self.info_label.setText(self._info_text())
        self._update_nav_buttons()

    def _update_nav_buttons(self):
        """根据当前页更新按钮启用状态（核心联动逻辑）"""
        total_p = self.total_pages
        # 首页/上一页：当前页为1时禁用
        self.first_btn.setEnabled(self.current_page > 1)
        self.prev_btn.setEnabled(self.current_page > 1)
        # 下一页/尾页：当前页为最后一页时禁用
        self.next_btn.setEnabled(self.current_page < total_p)
        self.last_btn.setEnabled(self.current_page < total_p)


def main():
    app = QApplication(sys.argv)
    w = Table_select_columns_paging_bottom(gid=1)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()