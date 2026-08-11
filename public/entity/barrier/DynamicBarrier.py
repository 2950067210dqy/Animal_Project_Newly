import threading

class DynamicBarrier:
    """
    可动态调整parties数量的Barrier。
    parties=1时只有add_message_thread一个参与者，气路未启动时环境模块数据正常出。
    气路启动完成后升级为4，UFC+UGC+ZOS+add_message_thread四路同步。
    """
    def __init__(self, parties: int, action=None):
        self._lock = threading.Condition(threading.Lock())
        self._parties = parties
        self._action = action
        self._count = 0       # 当前已到达wait的线程数
        self._generation = 0  # 代号，用于区分每一轮

    def wait(self):
        with self._lock:
            gen = self._generation
            self._count += 1
            if self._count >= self._parties:
                # 最后一个到达，触发action并唤醒所有
                self._generation += 1
                self._count = 0
                if self._action:
                    try:
                        self._action()
                    except Exception:
                        pass
                self._lock.notify_all()
            else:
                # 等待本代完成
                while self._generation == gen:
                    self._lock.wait(timeout=30)  # 防死锁超时

    def set_parties(self, parties: int):
        """动态修改参与者数量，在新一轮开始前调用"""
        with self._lock:
            self._parties = parties
            # 如果已经有count个在等，且新parties <= count，立即触发
            if self._count >= self._parties:
                self._generation += 1
                self._count = 0
                if self._action:
                    try:
                        self._action()
                    except Exception:
                        pass
                self._lock.notify_all()

    def reset(self, parties: int = None):
        """停止实验时重置，下次从新parties开始"""
        with self._lock:
            if parties is not None:
                self._parties = parties
            self._count = 0
            self._generation += 1  # 打断所有正在等待的线程
            self._lock.notify_all()

    @property
    def parties(self):
        return self._parties