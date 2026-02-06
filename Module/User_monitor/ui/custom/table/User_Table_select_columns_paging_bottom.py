"""
表头初始为空，通过信号（按钮点击）置换表头并分页加载数据（每页 10 条），
当垂直滚动条滑到底部时自动加载下一页。
"""
import sys
import time

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton,
    QScrollArea, QTableWidget, QTableWidgetItem, QMessageBox, QLabel, QHBoxLayout, QListWidget, QFileDialog
)
from loguru import logger

from Module.User_monitor.ui.custom.table.User_Custom_table import CustomTableWidget
from public.config.Data_Column import Data_column_list
from public.dao.SQLite.Monitor_Datas_Handle import Monitor_Datas_Handle
from public.entity.MyQThread import MyQThread
from theme.ThemeQt6 import ThemedWindow


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

        self.data_fetched.emit(datas)

        time.sleep(3)  # 每秒获取一次数据


class User_table_select_columns_paging_bottom(ThemedWindow):
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

        # ---- 数据和列定义 ----
        self.all_columns = ["时间"]
        self.all_column_datas = []
        # 数据
        self.total_items = 0  # 总条数
        # [{表头1:数据，表头2:数据，}....]
        self.data = []

        # 分页参数（默认）
        self.page_size = 500
        self.current_page = 1  # 1-based page index

        # ---- 主界面布局 ----
        central = QWidget()
        self.setCentralWidget(central)
        main_vbox = QVBoxLayout(central)

        self.setMinimumWidth(1100)

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
        # 绑定按钮点击事件
        self.first_btn.clicked.connect(lambda: self.go_to_page(1))
        self.prev_btn.clicked.connect(lambda: self.go_to_page(self.current_page - 1))
        self.next_btn.clicked.connect(lambda: self.go_to_page(self.current_page + 1))
        self.last_btn.clicked.connect(lambda: self.go_to_page(self.total_pages))

        # 添加按钮到分页布局
        for w in (self.first_btn, self.prev_btn, self.next_btn, self.last_btn):
            pager_layout.addWidget(w)

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

        # 动态改变冻结列
        self.table.set_frozen_columns_by_headers(
            left_headers=["序号", "鼠笼号"],  # 左侧冻结
            right_headers=["获取时间"]  # 右侧冻结
        )

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
        pass

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
        """接收线程数据，更新表格内容（修改：预处理None值，使其参与后续计算，并过滤掉指定列）"""
        # 1. 提取结果中的列名与数据（兼容数据库返回格式）
        if "columns_title" not in result or "rows" not in result:
            logger.warning("数据格式错误：缺少 columns_title 或 rows 字段")
            return

        original_columns = result["columns_title"]
        page_records = result["rows"]
        self.total_items = result.get("total_items", 0)  # 更新总条数

        # 过滤掉第25、26、27列（索引24、25、26）
        columns_to_remove = [24, 25, 26]  # 对应第25、26、27列

        # 安全检查：确保索引不超出范围
        safe_columns_to_remove = [i for i in columns_to_remove if i < len(original_columns)]

        filtered_columns = []
        for i, col in enumerate(original_columns):
            if i not in safe_columns_to_remove:
                filtered_columns.append(col)

        self.all_columns = filtered_columns

        # 2. 预处理数据：处理None值和空行，并过滤掉指定列
        processed_records = self._preprocess_data(page_records, safe_columns_to_remove)

        # 3. 清空并重置表格
        self.table.setRowCount(0)
        self.table.setColumnCount(len(self.all_columns))
        self.table.setHorizontalHeaderLabels(self.all_columns)

        # 4. 填充表格数据（使用预处理后的数据）
        for row_idx, record in enumerate(processed_records):
            self.table.insertRow(row_idx)
            col_idx = 0

            for col_key, col_val in record.items():
                # 安全检查：确保col_idx不超出范围
                if col_idx >= len(self.all_columns):
                    break

                final_val = ""  # 最终显示值

                # -------------------------- 格式化显示值 --------------------------
                # 情况1：当前是时间列（col_idx=0）
                if col_idx == 0:
                    final_val = str(col_val) if col_val is not None else ""

                # 情况2：数据列（col_idx>0）
                else:
                    current_col_title = self.all_columns[col_idx]
                    is_cage_column = "鼠笼号" in current_col_title

                    if col_val is not None:
                        if is_cage_column:
                            # 鼠笼号列：强制转为整数
                            try:
                                num_val = float(col_val) if not isinstance(col_val, (int, float)) else col_val
                                final_val = str(int(num_val))
                            except (ValueError, TypeError):
                                final_val = str(col_val).strip()
                        else:
                            # 非鼠笼号列：按原有逻辑格式化
                            if isinstance(col_val, (int, float)):
                                if "oxygen" in col_key or "CO2" in col_key:
                                    final_val = f"{col_val:.04f}"  # 氧气/CO2保留4位小数
                                else:
                                    final_val = f"{col_val:.2f}"  # 其他数字保留2位小数
                            else:
                                final_val = str(col_val).strip()
                    else:
                        final_val = ""  # None值显示为空

                # -------------------------- 设置单元格值与对齐 --------------------------
                item = QTableWidgetItem(final_val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                self.table.setItem(row_idx, col_idx, item)
                col_idx += 1

        # 5. 调整列宽与同步分页状态
        self.table.resizeColumnsToContents()
        self.info_label.setText(self._info_text())
        self._update_nav_buttons()

    def _preprocess_data(self, page_records: list, columns_to_remove: list = None) -> list:
        """预处理数据：处理None值和空行，并过滤掉指定列，返回处理后的数据列表"""
        if not page_records:
            return []

        if columns_to_remove is None:
            columns_to_remove = []

        # 创建处理后的数据副本，并过滤掉指定列
        processed_records = []
        for record in page_records:
            # 过滤掉指定列
            filtered_record = {}
            for i, (key, value) in enumerate(record.items()):
                if i not in columns_to_remove:
                    filtered_record[key] = value
            processed_records.append(filtered_record)

        # 逐行处理
        for row_idx, record in enumerate(processed_records):
            # 检查当前行是否为空行（除时间列外的所有数据都为None或空）
            is_empty_row = self._is_empty_row_in_data(record)

            # 如果是空行，继承上一行的所有数据列值
            if is_empty_row and row_idx > 0:
                prev_record = processed_records[row_idx - 1]
                col_keys = list(record.keys())[1:]  # 排除第一列（时间列）
                for col_key in col_keys:
                    record[col_key] = prev_record[col_key]

            # 如果不是空行，处理单个None值
            elif not is_empty_row:
                col_idx = 0
                for col_key, col_val in record.items():
                    # 跳过时间列
                    if col_idx == 0:
                        col_idx += 1
                        continue

                    # 处理None值
                    if col_val is None:
                        # 安全检查：确保col_idx不超出范围
                        if col_idx < len(self.all_columns):
                            current_col_title = self.all_columns[col_idx]
                        is_cage_column = "鼠笼号" in current_col_title

                        # 检查该列是否已经出现过有效数据
                        if self._has_valid_data_before(processed_records, row_idx, col_key):
                            # 如果前面已经有有效数据，计算前三项的平均值
                            avg_val = self._get_average_from_processed_data(
                                processed_records, row_idx, col_key, is_cage_column
                            )

                            # 更新当前记录的值
                            if avg_val is not None:
                                record[col_key] = avg_val
                        # 如果前面全是None，保持当前的None值不变

                    col_idx += 1

        return processed_records

    def _has_valid_data_before(self, processed_records: list, current_row_idx: int, col_key: str) -> bool:
        """检查指定列在当前行之前是否已经出现过有效数据"""
        for i in range(current_row_idx):
            val = processed_records[i].get(col_key)
            if val is not None:
                try:
                    float(val)  # 尝试转换为数字
                    return True  # 找到了有效数据
                except (ValueError, TypeError):
                    continue
        return False  # 前面全是None或无效数据

    def _is_empty_row_in_data(self, record: dict) -> bool:
        """判断数据记录中当前行是否为空行（除时间列外的所有数据都为None或空）"""
        data_values = list(record.values())[1:]  # 排除第一列（时间列）
        for val in data_values:
            if val is not None and str(val).strip() != "":
                return False
        return True

    def _get_average_from_processed_data(self, processed_records: list, current_row_idx: int,
                                         col_key: str, is_cage_column: bool = False):
        """从已处理的数据中获取指定列前三项的平均值"""
        # 收集前面行的有效数值（最多前三行）
        valid_values = []
        for i in range(max(0, current_row_idx - 3), current_row_idx):
            val = processed_records[i].get(col_key)
            if val is not None:
                try:
                    num_val = float(val)
                    valid_values.append(num_val)
                except (ValueError, TypeError):
                    continue  # 跳过无法转换的值

        # 如果没有有效值，返回None
        if not valid_values:
            return None

        # 计算平均值
        avg = sum(valid_values) / len(valid_values)

        # 如果是鼠笼号列，返回整数；否则返回浮点数
        return int(round(avg)) if is_cage_column else avg

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