from enum import Enum
class ModBusResponseCode(Enum):
    #一般错误
    ERROR = 404
    #操作超时
    OPERATOR_TIMEOUT =401
    #发送接收异常
    SEND_RECEIVE_EXCEPTION=402
    #解析报文TIMEOUT1
    VALIDATE_RESP_TIMEOUT1 =301
    VALIDATE_RESP_TIMEOUT2=302
    VALIDATE_RESP_TIMEOUT3 =303
    VALIDATE_RESP_FUNC_CODE_EXCEPTION =304
    #成功
    SUCCESS =200
    def __lt__(self, other):
        if other is None:
            return False
        return self.value < other.value

    def __le__(self, other):
        if other is None:
            return False
        return self.value <= other.value

    def __gt__(self, other):
        if other is None:
            return False
        return self.value > other.value

    def __ge__(self, other):
        if other is None:
            return False
        return self.value >= other.value
    def __eq__(self, other):
        if other is None:
            return False
        return self.value == other.value
    def __ne__(self, other):
        if other is None:
            return False
        return self.value != other.value
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
        if other is None:
            return False
        return self.value < other.value

    def __le__(self, other):
        if other is None:
            return False
        return self.value <= other.value

    def __gt__(self, other):
        if other is None:
            return False
        return self.value > other.value

    def __ge__(self, other):
        if other is None:
            return False
        return self.value >= other.value
    def __eq__(self, other):
        if other is None:
            return False
        return self.value == other.value
    def __ne__(self, other):
        if other is None:
            return False
        return self.value != other.value
class AnimalGender(Enum):
    # 雌性
    FEMALE = True
    # 雄性
    MALE = False

class Tutorial_Type(Enum):
    OVERLAY_GUIDE = 0
    BUBBLE_GUIDE = 1
    ARROW_GUIDE = 2

    def __lt__(self, other):
        if other is None:
            return False
        return self.value < other.value

    def __le__(self, other):
        if other is None:
            return False
        return self.value <= other.value

    def __gt__(self, other):
        if other is None:
            return False
        return self.value > other.value

    def __ge__(self, other):
        if other is None:
            return False
        return self.value >= other.value

    def __eq__(self, other):
        if other is None:
            return False
        return self.value == other.value

    def __ne__(self, other):
        if other is None:
            return False
        return self.value != other.value
class BaseInterfaceType(Enum):
    WINDOW=0
    FRAME=1
    WIDGET = 1

    def __lt__(self, other):
        if other is None:
            return False
        return self.value < other.value

    def __le__(self, other):
        if other is None:
            return False
        return self.value <= other.value

    def __gt__(self, other):
        if other is None:
            return False
        return self.value > other.value

    def __ge__(self, other):
        if other is None:
            return False
        return self.value >= other.value

    def __eq__(self, other):
        if other is None:
            return False
        return self.value == other.value

    def __ne__(self, other):
        if other is None:
            return False
        return self.value != other.value
class Frame_state(Enum):
    Default = 0
    Opening = 1
    Closed = 2

    def __lt__(self, other):
        if other is None:
            return False
        return self.value < other.value

    def __le__(self, other):
        if other is None:
            return False
        return self.value <= other.value

    def __gt__(self, other):
        if other is None:
            return False
        return self.value > other.value

    def __ge__(self, other):
        if other is None:
            return False
        return self.value >= other.value

    def __eq__(self, other):
        if other is None:
            return False
        return self.value == other.value

    def __ne__(self, other):
        if other is None:
            return False
        return self.value != other.value