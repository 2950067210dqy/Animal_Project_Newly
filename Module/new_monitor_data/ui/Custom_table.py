from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTableWidget

from Module.new_monitor_data.ui.TableCellDetailDialog import CellDetailDialog


class CustomTableWidget(QTableWidget):
    """自定义表格控件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)  # 启用鼠标跟踪


        # 连接双击信号
        self.cellDoubleClicked.connect(self.on_cell_double_clicked)

    def on_cell_double_clicked(self, row, column):
        """处理单元格双击事件"""
        item = self.item(row, column)
        if item:
            cell_value = item.text()
        else:
            cell_value = ""

        column_name = self.horizontalHeaderItem(column).text() if self.horizontalHeaderItem(
            column) else f"列{column + 1}"

        # 显示详情弹窗
        dialog = CellDetailDialog(cell_value, row, column, column_name,self)
        dialog.exec()

