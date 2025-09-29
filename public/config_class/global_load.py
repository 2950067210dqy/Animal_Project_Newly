import os

from PyQt6.QtCore import QThreadPool
from loguru import logger

from public.config_class.App_Setting import AppSettings
from public.config_class.global_setting import global_setting
from public.config_class.ini_parser import ini_parser
from public.entity.enum.Public_Enum import AppState
from theme.ThemeManager import ThemeManager


def load_global_setting():
    # """应用程序设置管理器"""
    app_setting = AppSettings()
    global_setting.set_setting("app_setting", app_setting)
    config_path = "/config"
    # 加载配置
    config_file_path = os.getcwd() + config_path + "/gui_config.ini"
    # 串口配置数据{"section":{"key1":value1,"key2":value2,....}，...}
    configer = ini_parser(config_file_path).read()
    if (len(configer) != 0):
        logger.info("gui配置文件读取成功。")
    else:
        logger.error("gui配置文件读取失败。")
    global_setting.set_setting("configer", configer)
    # 加载相机配置
    config_file_path = os.getcwd() + config_path + "/camera_config.ini"
    # 串口配置数据{"section":{"key1":value1,"key2":value2,....}，...}
    config = ini_parser(config_file_path).read()
    if (len(config) != 0):
        logger.info("相机配置文件读取成功。")
    else:
        logger.error("相机配置文件读取失败。")
    global_setting.set_setting("camera_config", config)
    # 加载监控数据配置
    config_file_path = os.getcwd() + config_path + "/monitor_datas_config.ini"
    # 配置数据{"section":{"key1":value1,"key2":value2,....}，...}
    config = ini_parser(config_file_path).read()
    if (len(config) != 0):
        logger.info("监控配置文件读取成功。")
    else:
        logger.error("监控配置文件读取失败。")
    global_setting.set_setting("monitor_data", config)
    config_file_path = os.getcwd() + config_path+"/UFC_UGC_ZOS_Test.ini"
    config = ini_parser(config_file_path).read()
    if len(config) != 0:
        logger.info("UFC_UGC_ZOS_config配置文件读取成功。")
    else:
        logger.error("UFC_UGC_ZOS_config配置文件读取失败。")
    global_setting.set_setting("UFC_UGC_ZOS_config", config)
    # 风格默认是dark  light
    global_setting.set_setting("style", configer['theme']['default'])
    # 图标风格 white black
    global_setting.set_setting("icon_style", "white")
    # 主题管理
    theme_manager = ThemeManager()
    global_setting.set_setting("theme_manager", theme_manager)
    # qt线程池
    thread_pool = QThreadPool()
    global_setting.set_setting("thread_pool", thread_pool)
    # 程序状态
    global_setting.set_setting("app_state", AppState.INITIALIZED)
    pass
def load_global_setting_without_Qt():
    # """应用程序设置管理器"""
    app_setting = AppSettings()
    global_setting.set_setting("app_setting", app_setting)
    config_path = "/config"
    # 加载配置
    config_file_path = os.getcwd() + config_path + "/gui_config.ini"
    # 串口配置数据{"section":{"key1":value1,"key2":value2,....}，...}
    configer = ini_parser(config_file_path).read()
    if (len(configer) != 0):
        logger.info("gui配置文件读取成功。")
    else:
        logger.error("gui配置文件读取失败。")
    global_setting.set_setting("configer", configer)
    # 加载相机配置
    config_file_path = os.getcwd() + config_path + "/camera_config.ini"
    # 串口配置数据{"section":{"key1":value1,"key2":value2,....}，...}
    config = ini_parser(config_file_path).read()
    if (len(config) != 0):
        logger.info("相机配置文件读取成功。")
    else:
        logger.error("相机配置文件读取失败。")
    global_setting.set_setting("camera_config", config)
    # 加载监控数据配置
    config_file_path = os.getcwd() + config_path + "/monitor_datas_config.ini"
    # 配置数据{"section":{"key1":value1,"key2":value2,....}，...}
    config = ini_parser(config_file_path).read()
    if (len(config) != 0):
        logger.info("监控配置文件读取成功。")
    else:
        logger.error("监控配置文件读取失败。")
    global_setting.set_setting("monitor_data", config)
    config_file_path = os.getcwd() + config_path + "/UFC_UGC_ZOS_Test.ini"
    config = ini_parser(config_file_path).read()
    if len(config) != 0:
        logger.info("UFC_UGC_ZOS_config配置文件读取成功。")
    else:
        logger.error("UFC_UGC_ZOS_config配置文件读取失败。")
    global_setting.set_setting("UFC_UGC_ZOS_config", config)
    # 风格默认是dark  light
    global_setting.set_setting("style", configer['theme']['default'])
    # 图标风格 white black
    global_setting.set_setting("icon_style", "white")
    # 主题管理
    theme_manager = ThemeManager()
    global_setting.set_setting("theme_manager", theme_manager)

    # 程序状态
    global_setting.set_setting("app_state", AppState.INITIALIZED)
    pass
def load_global_setting_without_Qt_for_subprocess():
    # """应用程序设置管理器"""
    app_setting = AppSettings()
    global_setting.set_setting("app_setting", app_setting)
    config_path = "/config"
    # 加载配置
    config_file_path = "../" + config_path + "/gui_config.ini"
    # 串口配置数据{"section":{"key1":value1,"key2":value2,....}，...}
    configer = ini_parser(config_file_path).read()
    if (len(configer) != 0):
        logger.info("gui配置文件读取成功。")
    else:
        logger.error("gui配置文件读取失败。")
    global_setting.set_setting("configer", configer)
    # 加载相机配置
    config_file_path = "../"  + config_path + "/camera_config.ini"
    # 串口配置数据{"section":{"key1":value1,"key2":value2,....}，...}
    config = ini_parser(config_file_path).read()
    if (len(config) != 0):
        logger.info("相机配置文件读取成功。")
    else:
        logger.error("相机配置文件读取失败。")
    global_setting.set_setting("camera_config", config)
    # 加载监控数据配置
    config_file_path = "../" + config_path + "/monitor_datas_config.ini"
    # 配置数据{"section":{"key1":value1,"key2":value2,....}，...}
    config = ini_parser(config_file_path).read()
    if (len(config) != 0):
        logger.info("监控配置文件读取成功。")
    else:
        logger.error("监控配置文件读取失败。")
    global_setting.set_setting("monitor_data", config)
    # 风格默认是dark  light
    global_setting.set_setting("style", configer['theme']['default'])
    # 图标风格 white black
    global_setting.set_setting("icon_style", "white")
    # 主题管理
    theme_manager = ThemeManager()
    global_setting.set_setting("theme_manager", theme_manager)

    # 程序状态
    global_setting.set_setting("app_state", AppState.INITIALIZED)