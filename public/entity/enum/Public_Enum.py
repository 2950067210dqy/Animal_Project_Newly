from enum import Enum

class AppState(Enum):
    #程序当前状态
    # 初始化状态
    INITIALIZED = 0
    #应用实验状态
    APPLYING = 1
    #设备配置状态
    CONFIGURING = 2
    #开始监测数据状态
    MONITORING = 3

    def __lt__(self, other):
        return self.value < other.value

    def __le__(self, other):
        return self.value <= other.value

    def __gt__(self, other):
        return self.value > other.value

    def __ge__(self, other):
        return self.value >= other.value

class AnimalGender(Enum):
    # 雌性
    FEMALE = True
    # 雄性
    MALE = False


class BaseInterfaceType(Enum):
    WINDOW=0
    FRAME=1
    WIDGET = 1
class Frame_state(Enum):
    Default = 0
    Opening = 1
    Closed = 2