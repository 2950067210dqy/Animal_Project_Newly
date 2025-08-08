from datetime import datetime


class Animal:
    """
    类描述：表示数据库中的动物记录
    """

    def __init__(self,
                 id: int,
                 id_write: int,
                 name: str,
                 sex: bool,
                 weight: float,
                 weight_unit: str,
                 note: str,
                 create_time: datetime,
                 update_time: datetime):
        self.id = id  # 序号
        self.id_write = id_write  # ID
        self.name = name  # 动物名称
        self.sex = sex  # 性别
        self.weight = weight  # 重量
        self.weight_unit = weight_unit  # 重量单位
        self.note = note  # 备注
        self.create_time = create_time  # 获取时间
        self.update_time = update_time  # 更新时间

    def __repr__(self):
        return (f"Animal(id={self.id}, id_write={self.id_write}, name='{self.name}', "
                f"sex={self.sex}, weight={self.weight}, weight_unit='{self.weight_unit}', "
                f"note='{self.note}', create_time='{self.create_time}', update_time='{self.update_time}')")


class Group:
    """
    类描述：表示数据库中的分组记录
    """

    def __init__(self,
                 id: int,
                 name: str,
                 create_time: datetime,
                 update_time: datetime):
        self.id = id  # 序号
        self.name = name  # 名称
        self.create_time = create_time  # 获取时间
        self.update_time = update_time  # 更新时间

    def __repr__(self):
        return (f"Record(id={self.id}, name='{self.name}', "
                f"create_time='{self.create_time}', update_time='{self.update_time}')")
class AnimalGroupRecord:
    """
    类描述：表示数据库中的动物和组的记录
    """

    def __init__(self,
                 id: int,
                 aid: str,
                 gid: bool,
                 note: str,
                 create_time: datetime,
                 update_time: datetime):
        self.id = id                    # 序号
        self.aid = aid                  # 动物序号
        self.gid = gid                  # 组/通道序号，布尔值
        self.note = note                # 备注
        self.create_time = create_time   # 获取时间
        self.update_time = update_time   # 更新时间

    def __repr__(self):
        return (f"AnimalGroupRecord(id={self.id}, aid='{self.aid}', gid={self.gid}, "
                f"note='{self.note}', create_time='{self.create_time}', update_time='{self.update_time}')")