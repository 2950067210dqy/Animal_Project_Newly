from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QPushButton

from public.config_class.global_setting import global_setting
from public.entity.BaseWidget import BaseWidget
from public.entity.BaseWindow import BaseWindow


class ThemedWidget(BaseWidget):
    """混入类实现主题响应"""

    def __init__(self):
        super().__init__()

        global_setting.get_setting("theme_manager").theme_changed.connect(self._update_theme)
        self._init_style_sheet()

    # 加载qss样式
    def _init_style_sheet(self):
        # if hasattr(self, ("frame")) and self.frame != None:
        self.setStyleSheet(global_setting.get_setting("theme_manager").get_style_sheet())

    def _update_theme(self):
        self._init_style_sheet()
        self.setStyleSheet(global_setting.get_setting("theme_manager").get_style_sheet())


class ThemedWindow(BaseWindow):
    """混入类实现主题响应"""

    def __init__(self):
        super().__init__()

        global_setting.get_setting("theme_manager").theme_changed.connect(self._update_theme)
        self._init_style_sheet()

    # 加载qss样式
    def _init_style_sheet(self):
        # if hasattr(self, ("frame")) and self.frame != None:
        self.setStyleSheet(global_setting.get_setting("theme_manager").get_style_sheet())

    def _update_theme(self):
        self._init_style_sheet()
        self.setStyleSheet(global_setting.get_setting("theme_manager").get_style_sheet())


class ThemeIconButton(QPushButton):
    def __init__(self, icon_name):
        super().__init__()
        self.icon_name = icon_name
        self.update_icon()

    def update_icon(self):
        path = f":/{global_setting.get_setting('style')}/{self.icon_name}.svg"
        self.setIcon(QIcon(path))
