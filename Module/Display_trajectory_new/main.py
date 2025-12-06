from Module.Display_trajectory_new.ui.main_window import TrajectoryViewer
from my_abc.BaseInterfaceWidget import BaseInterfaceWidget
from my_abc.BaseModule import BaseModule
from my_abc.BaseService import BaseService
from public.entity.BaseWindow import BaseWindow
from public.entity.enum.Public_Enum import BaseInterfaceType, AppState
from PyQt6.QtWidgets import QApplication
from loguru import logger


class Main_load_metadata_file_service(BaseService):
    """组件服务"""

    def __init__(self):
        super().__init__()

    def start(self, resolve, reject):
        try:
            logger.info("老鼠轨迹监测服务启动中...")
            resolve()
        except Exception as e:
            logger.error(f"服务启动失败: {e}")
            reject()

    def stop(self):
        logger.info("老鼠轨迹监测服务已停止")


class Main_load_metadata_file_widget(BaseInterfaceWidget):
    """组件自定义界面"""

    def __init__(self):
        super().__init__()
        logger.info("正在初始化轨迹监测界面组件...")

        try:
            self.type = self.get_type()

            # 确保 QApplication 存在
            if QApplication.instance() is None:
                logger.warning("警告: QApplication 实例不存在")

            # 创建主窗口
            logger.info("正在创建轨迹查看器窗口...")
            self.frame_obj = self.create_middle_window()
            logger.info(f"轨迹查看器窗口创建成功: {type(self.frame_obj)}")

            # 其他窗口
            self.left_frame_obj = self.create_left_window()
            self.right_frame_obj = self.create_right_window()
            self.bottom_frame_obj = self.create_bottom_window()

            logger.info("轨迹监测界面组件初始化完成")

        except Exception as e:
            logger.error(f"轨迹监测界面组件初始化失败: {e}")
            import traceback
            traceback.print_exc()
            raise

    def get_type(self):
        """获得类型"""
        return BaseInterfaceType.WINDOW

    def create_middle_window(self) -> BaseWindow:
        """创建主窗口"""
        try:
            logger.info("开始创建 TrajectoryViewer 实例...")
            trajectory_viewer = TrajectoryViewer()
            logger.info("TrajectoryViewer 实例创建成功")
            return trajectory_viewer
        except Exception as e:
            logger.error(f"创建 TrajectoryViewer 失败: {e}")
            import traceback
            traceback.print_exc()

            # 如果创建失败，返回一个简单的测试窗口
            logger.info("使用备用测试窗口...")
            from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel

            class TestWindow(BaseWindow):
                def __init__(self):
                    super().__init__()
                    self.setWindowTitle("轨迹监测界面 - 测试模式")
                    self.resize(800, 600)

                    layout = QVBoxLayout()
                    label = QLabel(
                        "老鼠轨迹监测界面\n\n如果您看到这个消息，说明界面组件加载成功！\n但TrajectoryViewer初始化可能遇到问题。")
                    label.setStyleSheet("font-size: 18px; color: #2E7D32; text-align: center; padding: 50px;")
                    layout.addWidget(label)
                    self.setLayout(layout)

            return TestWindow()

    def create_left_window(self) -> BaseWindow:
        """创建并返回自定义的界面部件left WINDOW"""
        return None

    def create_right_window(self) -> BaseWindow:
        """创建并返回自定义的界面部件right WINDOW"""
        return None

    def create_bottom_window(self) -> BaseWindow:
        """创建并返回自定义的界面部件bottom WINDOW"""
        return None


class Main_User_monitor_Module(BaseModule):
    """主要的用户监测模块"""

    def __init__(self):
        super().__init__()
        logger.info("正在初始化老鼠轨迹监测模块...")

        try:
            self.name = self.get_name()
            self.title = self.get_title()
            self.menu_name = self.get_menu_name()
            self.app_state = self.get_app_state()

            # 创建服务
            logger.info("正在创建服务...")
            self.service = self.create_service()

            # 创建界面组件
            logger.info("正在创建界面组件...")
            self.interface_widget = self.get_interface_widget()

            logger.info(f"老鼠轨迹监测模块初始化完成: {self.title}")

        except Exception as e:
            logger.error(f"老鼠轨迹监测模块初始化失败: {e}")
            import traceback
            traceback.print_exc()
            raise

    def get_app_state(self) -> AppState:
        return AppState.MONITORING

    def get_name(self):
        """返回组件名称"""
        return "Main_User_monitor"

    def get_title(self):
        """获取组件title"""
        return "老鼠轨迹监测测试界面"

    def get_menu_name(self):
        """返回组件所属菜单{id:,text:} 在./config/gui_config.ini文件查看"""
        return {"id": 1, "text": "实验"}

    def create_service(self) -> BaseService:
        """创建并返回组件的相关服务"""
        try:
            service = Main_load_metadata_file_service()
            service.module = self  # 可以通过引用将组件功能传递给service
            return service
        except Exception as e:
            logger.error(f"创建服务失败: {e}")
            raise

    def get_interface_widget(self) -> BaseInterfaceWidget:
        """返回自定义界面构建器"""
        try:
            widget_builder = Main_load_metadata_file_widget()
            widget_builder.module = self  # 可以通过引用将组件功能传递给界面构建器
            return widget_builder
        except Exception as e:
            logger.error(f"创建界面组件失败: {e}")
            import traceback
            traceback.print_exc()
            raise

