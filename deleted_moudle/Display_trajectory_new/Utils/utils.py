import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class Utils:
    """工具类"""

    @staticmethod
    def get_basic_stylesheet():
        """获取基础样式表"""
        return """
        QWidget {
            background-color: #f5f5f5;
        }
        QGroupBox {
            font-weight: bold;
            border: 2px solid #cccccc;
            border-radius: 8px;
            margin-top: 1ex;
            padding-top: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px 0 5px;
        }
        QPushButton {
            background-color: #4CAF50;
            border: none;
            color: white;
            padding: 8px 16px;
            text-align: center;
            font-size: 14px;
            border-radius: 4px;
            min-height: 30px;
        }
        QPushButton:hover {
            background-color: #45a049;
        }
        QPushButton:disabled {
            background-color: #cccccc;
            color: #666666;
        }
        """

    @staticmethod
    def log_message_to_widget(info_text, message, level="INFO"):
        """记录日志消息到文本控件"""
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            formatted_message = f"[{timestamp}] {level}: {message}"
            if info_text:
                info_text.append(formatted_message)
                scrollbar = info_text.verticalScrollBar()
                scrollbar.setValue(scrollbar.maximum())

            if level == "INFO":
                logger.info(message)
            elif level == "ERROR":
                logger.error(message)
            else:
                logger.warning(message)
        except Exception as e:
            logger.error(f"记录日志失败: {e}")