# plugin_interface.py
import queue
from abc import abstractmethod, ABC

from PyQt6.QtWidgets import QVBoxLayout, QWidget, QScrollArea, QHBoxLayout, QMainWindow

from index import Content_index
from index.Content_index import content_index
from my_abc import BaseInterfaceWidget

from my_abc.BaseService import BaseService
from public.entity.BaseWindow import BaseWindow
from public.entity.enum.Public_Enum import Frame_state, BaseInterfaceType, AppState
from public.function.promise.AsyPromise import AsyPromise
from theme.ThemeQt6 import ThemedWindow


class BaseModule(ABC):

    def __init__(self):
        self.interface_widget:BaseInterfaceWidget =None
        self.name =None
        self.title=None
        self.menu_name=None
        self.service:BaseService =None
        self.main_gui:BaseWindow =None
        self.app_state :AppState =None
        pass
    @abstractmethod
    def get_app_state(self) -> AppState:
        """返回该组件在程序什么状态才能被点击"""
        pass
    @abstractmethod
    def get_menu_name(self):
        """返回组件所属菜单{id:,text:} 在./config/gui_config.ini文件查看"""
        pass
    @abstractmethod
    def get_name(self):
        """返回组件名称"""
        pass
    @abstractmethod
    def get_title(self):
        """获取组件title"""
        pass
    @abstractmethod
    def create_service(self) -> BaseService:
        """创建并返回组件的相关服务"""
        pass

    @abstractmethod
    def get_interface_widget(self) -> BaseInterfaceWidget:
        """返回自定义界面构建器"""
        pass
    def close(self):
        """关闭所有窗口 若有"""
        if self.interface_widget is not None:
            self.interface_widget.close()
    def show(self):
        """显示页面"""
        if self.interface_widget is not None:
            # 重新加载页面 而不是加载之前的页面 start
            # self.interface_widget.close()
            self.interface_widget = None
            self.interface_widget=self.get_interface_widget()
            self.set_main_gui_to_children()
            # 重新加载页面 而不是加载之前的页面 end
            self.interface_widget.show()

    def hide(self):
        """隐藏页面"""
        if self.interface_widget is not None:
            self.interface_widget.hide()
    def setParent(self, parent):
        """设置父界面"""
        if self.interface_widget is not None:
            self.interface_widget.setParent(parent)
    def set_main_gui(self,main_gui:BaseWindow=None) -> None:
        # 获取主界面变量
        self.main_gui=main_gui
        pass
    def set_main_gui_to_children(self):
        # 设置父界面给所有子界面
        if self.interface_widget.frame_obj is not None:
            self.interface_widget.frame_obj.set_main_gui(self.main_gui)
            self.interface_widget.frame_obj_state = Frame_state.Opening
        if self.interface_widget.left_frame_obj is not None:
            self.interface_widget.left_frame_obj.set_main_gui(self.main_gui)
            self.interface_widget.left_frame_obj_state = Frame_state.Opening
        if self.interface_widget.right_frame_obj is not None:
            self.interface_widget.right_frame_obj.set_main_gui(self.main_gui)
            self.interface_widget.right_frame_obj_state = Frame_state.Opening
        if self.interface_widget.bottom_frame_obj is not None:
            self.interface_widget.bottom_frame_obj.set_main_gui(self.main_gui)
            self.interface_widget.bottom_frame_obj_state = Frame_state.Opening
        pass
    # 点击的方法
    def click_method(self):
        AsyPromise(self.start_service).then(
            lambda r:AsyPromise(self.adjustGUIPolicy).then()
        )
        # self.start_service()
        # self.adjustGUIPolicy()
    def start_service(self,resolve,reject):
        """开始服务"""
        if self.service is not None:
            AsyPromise(self.service.start).then(
                lambda r:resolve(r)
            ).catch( lambda e:reject(e))
        else:
            resolve(None)

    def adjustGUIPolicy(self,resolve,reject):
        if self.interface_widget is None or self.interface_widget.type is None or self.interface_widget.frame_obj is None or self.main_gui is None:
            reject(None)
            return

        self.set_main_gui_to_children()
        # 根据type来确定相关策略
        if self.interface_widget.type == BaseInterfaceType.WIDGET or self.interface_widget.type == BaseInterfaceType.FRAME:


            tab_content = QWidget()
            tab_content.setObjectName(f"tab_content_{self.menu_name['text']}_{self.name}")
            tab_layout = QVBoxLayout(tab_content)
            tab_layout.setObjectName(f"tab_content_{self.menu_name['text']}_{self.name}_layout")

            # 创建一个内容小部件并填充内容

            tab_frame = content_index()



            left_layout =tab_frame.findChild(QVBoxLayout, "left_layout")
            right_layout = tab_frame.findChild(QVBoxLayout, "right_layout")
            bottom_layout = tab_frame.findChild(QVBoxLayout, "bottom_layout")
            middle_layout =tab_frame.findChild(QVBoxLayout, "middle_layout")

            scroll_left_layout =    BaseWindow.add_scroll_area_if_not_exists( tab_frame.findChild(QVBoxLayout,"left_layout"))
            scroll_right_layout =   BaseWindow.add_scroll_area_if_not_exists( tab_frame.findChild(QVBoxLayout,"right_layout"))
            scroll_bottom_layout =  BaseWindow.add_scroll_area_if_not_exists( tab_frame.findChild(QVBoxLayout,"bottom_layout"))
            scroll_middle_layout =   BaseWindow.add_scroll_area_if_not_exists(tab_frame.findChild(QVBoxLayout,"middle_layout"))

            scroll_middle_layout.addWidget(self.interface_widget.frame_obj)
            scroll_left_layout.addWidget(self.interface_widget.left_frame_obj)
            scroll_right_layout.addWidget(self.interface_widget.right_frame_obj)
            scroll_bottom_layout.addWidget(self.interface_widget.bottom_frame_obj)
            self.interface_widget.setMinimumSize()
            # 拉伸系数的layout
            main_layout:QVBoxLayout = tab_frame.findChild(QVBoxLayout,"main_layout")
            top_layout:QHBoxLayout = tab_frame.findChild(QHBoxLayout,"top_layout")
            if self.interface_widget.bottom_frame_obj is None:
                "没有bottomlayout"
                main_layout.setStretchFactor(bottom_layout,0)
                main_layout.setStretchFactor(top_layout,6)
            else:
                main_layout.setStretchFactor(bottom_layout,2)
                main_layout.setStretchFactor(top_layout, 4)
            if self.interface_widget.left_frame_obj is None and self.interface_widget.right_frame_obj is None:
                top_layout.setStretchFactor(left_layout,0)
                top_layout.setStretchFactor(middle_layout,6)
                top_layout.setStretchFactor(right_layout,0)
            elif self.interface_widget.left_frame_obj is None:
                top_layout.setStretchFactor(left_layout, 0)
                top_layout.setStretchFactor(middle_layout, 5)
                top_layout.setStretchFactor(right_layout, 1)
            elif self.interface_widget.right_frame_obj is None:
                top_layout.setStretchFactor(left_layout, 1)
                top_layout.setStretchFactor(middle_layout, 5)
                top_layout.setStretchFactor(right_layout, 0)
            else:
                top_layout.setStretchFactor(left_layout, 1)
                top_layout.setStretchFactor(right_layout, 1)
                top_layout.setStretchFactor(middle_layout, 4)
            size_factor = 0.9
            if self.interface_widget.frame_obj is not None:
                self.interface_widget.frame_obj.menuBar().hide()
                self.interface_widget.frame_obj.statusBar().hide()
                self.interface_widget.frame_obj.resize(int(middle_layout.geometry().width()),
                                                       int(middle_layout.geometry().height()*size_factor-self.main_gui.statusBar().height()))


            if self.interface_widget.left_frame_obj is not None:
                self.interface_widget.left_frame_obj.menuBar().hide()
                self.interface_widget.left_frame_obj.statusBar().hide()
                self.interface_widget.left_frame_obj.resize(
                    int(left_layout.geometry().width()),
                    int(left_layout.geometry().height()*size_factor-self.main_gui.statusBar().height()))


            if self.interface_widget.right_frame_obj is not None:
                self.interface_widget.right_frame_obj.menuBar().hide()
                self.interface_widget.right_frame_obj.statusBar().hide()
                self.interface_widget.right_frame_obj.resize(int(right_layout.geometry().width()),
                                                             int(right_layout.geometry().height()*size_factor-self.main_gui.statusBar().height()))


            if self.interface_widget.bottom_frame_obj is not None:
                self.interface_widget.bottom_frame_obj.menuBar().hide()
                self.interface_widget.bottom_frame_obj.statusBar().hide()
                self.interface_widget.bottom_frame_obj.resize(int(bottom_layout.geometry().width()),
                                                              int(bottom_layout.geometry().height()*size_factor-self.main_gui.statusBar().height()))





            # 将 scroll_area 添加进去
            tab_layout.addWidget(tab_frame)
            self.main_gui.tab_widget.addTab(tab_content,self.title)

            # 将界面放入正在显示界面
            if self not in self.main_gui.active_module_widgets:
                self.main_gui.active_module_widgets.append(self)
            pass
        else:
            self.show()
            #WINDOW
            flag = 10
            # ，每部分layout占多少
            if self.interface_widget.bottom_frame_obj is None:
                "没有bottomlayout"
                v_stretch = {'top': 5, 'bottom': 0}
            else:
                v_stretch = {'top': 4, 'bottom': 1}
            if self.interface_widget.left_frame_obj is None and self.interface_widget.right_frame_obj is None:
                h_stretch = {'left': 0, 'middle': 5, 'right': 0}
            elif self.interface_widget.left_frame_obj is None:
                h_stretch = {'left': 0, 'middle': 4, 'right': 1}
            elif self.interface_widget.right_frame_obj is None:
                h_stretch = {'left': 1, 'middle': 4, 'right':0}
            else:
                h_stretch = {'left': 1, 'middle': 3, 'right': 1}

            h_all = h_stretch['left']+h_stretch['middle']+h_stretch['right']
            v_all = v_stretch['top']+v_stretch['bottom']
            h_each = self.main_gui.centralWidget().geometry().width()//h_all
            v_each = (self.main_gui.centralWidget().geometry().height()-self.main_gui.statusBar().height())//v_all

            self.interface_widget.setMinimumSize(0, 0)
            if self.interface_widget.left_frame_obj is not None:
                self.interface_widget.left_frame_obj.menuBar().show()
                self.interface_widget.left_frame_obj.statusBar().show()
                self.interface_widget.left_frame_obj.setWindowTitle(self.title + 'left')
                self.interface_widget.left_frame_obj.setGeometry(
                    0,
                    self.main_gui.centralWidget().geometry().top() + self.main_gui.toolbar.geometry().height() + flag,
                    h_each * (h_stretch['left']),
                    v_each * (v_stretch['top'])

                )
            if self.interface_widget.frame_obj is not None:
                self.interface_widget.frame_obj.menuBar().show()
                self.interface_widget.frame_obj.statusBar().show()
                self.interface_widget.frame_obj.setWindowTitle(self.title+'content')
                self.interface_widget.frame_obj.setGeometry(h_each*(h_stretch['left']),
                                                            self.main_gui.centralWidget().geometry().top() + self.main_gui.toolbar.geometry().height() + flag,
                                                            h_each*(h_stretch['middle']),
                                                            v_each*(v_stretch['top']),
                                                            )
            if self.interface_widget.right_frame_obj is not None:
                self.interface_widget.right_frame_obj.menuBar().show()
                self.interface_widget.right_frame_obj.statusBar().show()
                self.interface_widget.right_frame_obj.setWindowTitle(self.title+'right')
                self.interface_widget.right_frame_obj.setGeometry(
                    h_each * (h_stretch['middle'] +h_stretch['left']),
                    self.main_gui.centralWidget().geometry().top() + self.main_gui.toolbar.geometry().height() + flag,
                    h_each * (h_stretch['right']),
                    v_each * (v_stretch['top']) ,
                )
            if self.interface_widget.bottom_frame_obj is not None:
                self.interface_widget.bottom_frame_obj.menuBar().show()
                self.interface_widget.bottom_frame_obj.statusBar().show()
                self.interface_widget.bottom_frame_obj.setWindowTitle(self.title+'bottom')
                self.interface_widget.bottom_frame_obj.setGeometry(
                    0,
                    self.main_gui.centralWidget().geometry().top()+v_each * (v_stretch['top'])+ self.main_gui.toolbar.geometry().height() ,
                    self.main_gui.centralWidget().width(),
                    v_each * (v_stretch['bottom'])-self.main_gui.toolbar.geometry().height() ,

                )



            # 添加窗口
            if self not in  self.main_gui.open_windows:
                self.main_gui.open_windows.append(self)

            pass

        resolve()
        pass

