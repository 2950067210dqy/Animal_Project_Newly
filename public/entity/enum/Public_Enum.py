from enum import Enum


class BaseInterfaceType(Enum):
    WINDOW=0
    FRAME=1
    WIDGET = 1
class Frame_state(Enum):
    Default = 0
    Opening = 1
    Closed = 2