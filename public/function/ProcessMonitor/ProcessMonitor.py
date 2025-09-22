
import multiprocessing
import time
import threading
import json
import os
import traceback

import psutil
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Callable, Any, Set
from datetime import datetime, timedelta
from loguru import logger


def kill_process_tree(pid, including_parent=True):
    """
    确认子进程没有启动其他子进程，如果有，必须递归管理或用系统命令杀死整个进程树。
    用 psutil 库递归杀死进程树
    multiprocessing.Process.terminate() 只会终止对应的单个进程，如果该进程启动了其他进程，这些“子进程”不会被自动终止，因而可能会在任务管理器中残留。
    """
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    children = parent.children(recursive=True)
    for child in children:
        child.terminate()
    gone, alive = psutil.wait_procs(children, timeout=5)
    for p in alive:
        p.kill()
    if including_parent:
        if psutil.pid_exists(pid):
            parent.terminate()
            parent.wait(5)


@dataclass
class ProcessMetrics:
    process_id: str
    pid: int
    status: str
    cpu_percent: float
    cpu_percent_normalized: float  # 新增：标准化后的CPU使用率
    memory_mb: float
    start_time: datetime
    uptime: timedelta
    restart_count: int
    last_heartbeat: Optional[float] = None
    exitcode: Optional[int] = None


def monitored_target(target_func, args, health_queue, process_id):
    """包装目标函数以支持健康检查"""
    try:
        # 启动健康心跳
        if health_queue:
            heartbeat_thread = threading.Thread(
                target=_heartbeat_worker,
                args=(health_queue, process_id)
            )
            heartbeat_thread.daemon = True
            heartbeat_thread.start()

        # 执行实际任务
        return target_func(*args)

    except Exception as e:
        # 发送错误信息
        if health_queue:
            try:
                health_queue.put(('ERROR', str(e), datetime.now()))
            except:
                pass
        raise
    finally:
        # 发送结束信号
        if health_queue:
            try:
                health_queue.put(('FINISHED', 'Process completed',  datetime.now()))
            except:
                pass


def _heartbeat_worker(health_queue, process_id):
    """健康心跳工作线程"""
    while True:
        try:
            health_queue.put(('HEARTBEAT',  datetime.now(), os.getpid()))
            time.sleep(5)  # 每5秒发送一次心跳
        except:
            break


class IntegratedProcessMonitor:
    def __init__(self):
        # 基本监控数据
        self.processes: Dict[str, Dict] = {}
        self.monitoring = True

        # 关键进程管理
        self.critical_processes: Set[str] = set()
        self.shutdown_on_critical_failure = True

        # 指标收集
        self.metrics_history: Dict[str, List[ProcessMetrics]] = {}
        self.current_metrics: Dict[str, ProcessMetrics] = {}

        # 系统信息
        self.cpu_count = psutil.cpu_count()  # 获取CPU核心数
        # CPU监控相关 - 存储psutil.Process对象用于CPU计算
        self.psutil_processes: Dict[str, psutil.Process] = {}
        self.cpu_last_call: Dict[str, float] = {}

        # 事件回调
        self.callbacks = {
            'on_start': [],
            'on_crash': [],
            'on_complete': [],
            'on_restart': [],
            'on_timeout': [],
            'on_unresponsive': [],
            'on_high_cpu': [],
            'on_high_memory': [],
            'on_critical_failure': [],
            'on_shutdown_triggered': []
        }

        # 阈值配置
        self.thresholds = {
            'cpu_percent': 80.0,
            'memory_mb': 1000.0,
            #心跳时间单位秒
            'heartbeat_timeout': 30.0
        }

        # 日志设置
        # logger.remove(0)
        logger.add(
            "./log/process_monitor/process_monitor_{time:YYYY-MM-DD}.log",
            rotation="00:00",  # 日志文件转存
            retention="30 days",  # 多长时间之后清理
            enqueue=True,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level} |{process.name} | {thread.name} |  {name} : {module}:{line} | {message}",

        )

        self.logger = logger
        # 记录系统信息
        self.logger.info(f"系统CPU核心数: {self.cpu_count}")
    def add_critical_process(self, process_id: str):
        """添加关键进程"""
        self.critical_processes.add(process_id)
        self.logger.info(f"添加关键进程: {process_id}")

    def remove_critical_process(self, process_id: str):
        """移除关键进程"""
        self.critical_processes.discard(process_id)
        self.logger.info(f"移除关键进程: {process_id}")

    def set_critical_processes(self, process_ids: List[str]):
        """设置关键进程列表"""
        self.critical_processes = set(process_ids)
        self.logger.info(f"设置关键进程列表: {process_ids}")

    def get_critical_processes(self) -> List[str]:
        """获取关键进程列表"""
        return list(self.critical_processes)

    def is_critical_process(self, process_id: str) -> bool:
        """检查是否为关键进程"""
        return process_id in self.critical_processes

    def check_critical_processes(self):
        """检查关键进程状态"""
        failed_critical = []

        for process_id in self.critical_processes:
            if process_id in self.processes:
                proc_info = self.processes[process_id]
                process = proc_info['process']

                if not process.is_alive():
                    # 关键进程已停止
                    failed_critical.append(process_id)
                    self.logger.critical(f"关键进程停止: {process_id} (退出码: {process.exitcode})")

                    # 触发关键进程失败回调
                    self.trigger_callbacks('on_critical_failure', process_id,
                                           exitcode=process.exitcode,
                                           process_type='critical')

        # 如果有关键进程失败且启用了关闭机制
        if failed_critical and self.shutdown_on_critical_failure:
            self.logger.critical(f"检测到关键进程失败: {failed_critical}")
            self.logger.critical("开始关闭所有其他进程...")

            # 触发关闭回调
            self.trigger_callbacks('on_shutdown_triggered',
                                   failed_critical[0],
                                   failed_processes=failed_critical,
                                   action='shutdown_all')

            self.shutdown_all_processes(exclude_critical=False)
            return True

        return False

    def shutdown_all_processes(self, exclude_critical=True):
        """关闭所有进程"""
        self.logger.warning("开始关闭所有进程...")

        for process_id, proc_info in list(self.processes.items()):
            # 如果设置了排除关键进程，则跳过关键进程
            if exclude_critical and self.is_critical_process(process_id):
                continue

            process = proc_info['process']
            if process and process.is_alive():
                self.logger.info(f"关闭进程: {process_id} (PID: {process.pid})")

                try:
                    # 先尝试优雅关闭
                    process.terminate()
                    process.join(timeout=5)

                    # 如果还没结束，强制杀死
                    if process.is_alive():
                        self.logger.warning(f"强制杀死进程: {process_id}")
                        kill_process_tree(process_id)
                        process.kill()
                        process.join(timeout=2)

                except Exception as e:
                    self.logger.error(f"关闭进程失败 {process_id}: {e}")

        self.logger.warning("所有进程关闭完成")

    def start_worker(self, target_func,restart_target_func=None, args=(), name=None, auto_restart=True,
                     max_restarts=3, timeout=None, health_check=True, is_critical=False):
        """启动工作进程"""
        process_id = name or f"Process-{len(self.processes)}"

        # 如果标记为关键进程，添加到关键进程列表
        if is_critical:
            self.add_critical_process(process_id)

        # 创建健康检查队列
        health_queue = multiprocessing.Queue() if health_check else None

        # 创建进程
        process = multiprocessing.Process(
            target=monitored_target,
            args=(target_func, args, health_queue, process_id),
            name=process_id
        )

        process.start()

        # 保存进程信息
        self.processes[process_id] = {
            'process': process,
            'target_func': target_func,
            'restart_target_func': restart_target_func,
            'args': args,
            'start_time': datetime.now(),
            'restart_count': 0,
            'last_heartbeat':  datetime.now() if health_check else None,
            'status': 'RUNNING',
            'error_info': None,
            'health_queue': health_queue,
            'auto_restart': auto_restart,
            'max_restarts': max_restarts,
            'timeout': timeout,
            'health_check': health_check,
            'is_critical': is_critical
        }

        # 初始化指标历史
        self.metrics_history[process_id] = []

        # 初始化CPU监控 - 延迟初始化psutil.Process对象
        try:
            # 稍等一下确保进程已启动
            time.sleep(0.1)
            if process.is_alive():
                self.psutil_processes[process_id] = psutil.Process(process.pid)
                # 第一次调用cpu_percent()来初始化（这次结果会是0，但为后续调用做准备）
                self.psutil_processes[process_id].cpu_percent()
                self.cpu_last_call[process_id] = time.time()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        critical_flag = "🔴关键" if is_critical else "🟡普通"
        self.logger.info(f"启动进程: {process_id} (PID: {process.pid}) [{critical_flag}]")

        # 触发启动回调
        self.trigger_callbacks('on_start', process_id,
                               pid=process.pid, start_time=datetime.now(),
                               is_critical=is_critical)

        return process_id

    def check_process_status(self, process_id):
        """检查进程状态"""
        if process_id not in self.processes:
            return None

        proc_info = self.processes[process_id]
        process = proc_info['process']
        health_queue = proc_info['health_queue']

        # 处理健康检查队列
        if health_queue:
            while True:
                try:
                    msg_type, data, timestamp = health_queue.get_nowait()

                    if msg_type == 'HEARTBEAT':
                        proc_info['last_heartbeat'] = data
                    elif msg_type == 'ERROR':
                        proc_info['error_info'] = data
                        proc_info['status'] = 'ERROR'
                    elif msg_type == 'FINISHED':
                        proc_info['status'] = 'FINISHED'

                except:
                    break

        # 检查进程状态
        current_time =  datetime.now()

        if not process.is_alive():
            # 清理psutil对象
            if process_id in self.psutil_processes:
                del self.psutil_processes[process_id]
            if process_id in self.cpu_last_call:
                del self.cpu_last_call[process_id]

            if process.exitcode == 0:
                proc_info['status'] = 'COMPLETED'
                # 触发完成回调
                self.trigger_callbacks('on_complete', process_id,
                                       exitcode=process.exitcode,
                                       runtime=current_time - proc_info['start_time'],
                                       is_critical=proc_info.get('is_critical', False))
            else:
                proc_info['status'] = 'CRASHED'
                # 触发崩溃回调
                self.trigger_callbacks('on_crash', process_id,
                                       exitcode=process.exitcode,
                                       runtime=current_time - proc_info['start_time'],
                                       error_info=proc_info['error_info'],
                                       is_critical=proc_info.get('is_critical', False))

                # 处理自动重启（仅对非关键进程或允许重启的关键进程）
                if (proc_info['auto_restart'] and
                        proc_info['restart_count'] < proc_info['max_restarts']):
                    self.restart_process(process_id)

        elif proc_info['health_check'] and proc_info['last_heartbeat']:
            # 检查心跳超时
            heartbeat_age = current_time - proc_info['last_heartbeat']
            if heartbeat_age >timedelta(seconds=self.thresholds['heartbeat_timeout']) :
                proc_info['status'] = 'UNRESPONSIVE'
                self.trigger_callbacks('on_unresponsive', process_id,
                                       heartbeat_age=heartbeat_age,
                                       is_critical=proc_info.get('is_critical', False))

        # 检查运行超时
        if proc_info['timeout']:
            runtime = current_time - proc_info['start_time']
            if runtime > proc_info['timeout']:
                self.logger.warning(f"进程超时: {process_id}")
                process.terminate()
                self.trigger_callbacks('on_timeout', process_id,
                                       timeout=proc_info['timeout'],
                                       runtime=runtime,
                                       is_critical=proc_info.get('is_critical', False))

        return {
            'process_id': process_id,
            'pid': process.pid if process.pid else 'N/A',
            'status': proc_info['status'],
            'exitcode': process.exitcode,
            'uptime': current_time - proc_info['start_time'],
            'restart_count': proc_info['restart_count'],
            'last_heartbeat_age': current_time - proc_info['last_heartbeat'] if proc_info['last_heartbeat'] else None,
            'error_info': proc_info['error_info'],
            'is_critical': proc_info.get('is_critical', False)
        }

    def restart_process(self, process_id):
        """重启进程"""
        if process_id not in self.processes:
            return False

        proc_info = self.processes[process_id]
        old_process = proc_info['process']

        self.logger.info(f"重启进程: {process_id}")

        # 清理旧进程和psutil对象
        if process_id in self.psutil_processes:
            del self.psutil_processes[process_id]
        if process_id in self.cpu_last_call:
            del self.cpu_last_call[process_id]

        if old_process.is_alive():
            old_process.terminate()
            old_process.join(timeout=5)

            if old_process.is_alive():
                old_process.kill()

        # 创建新进程
        new_process = multiprocessing.Process(
            target=monitored_target,
            args=(proc_info['restart_target_func'], proc_info['args'], proc_info['health_queue'], process_id),
            name=process_id
        )

        new_process.start()



        # 更新进程信息
        proc_info['process'] = new_process
        proc_info['start_time'] = datetime.now()
        proc_info['restart_count'] += 1
        proc_info['last_heartbeat'] = datetime.now() if proc_info['health_check'] else None
        proc_info['status'] = 'RUNNING'
        proc_info['error_info'] = None

        # 重新初始化CPU监控
        try:
            time.sleep(0.1)
            if new_process.is_alive():
                self.psutil_processes[process_id] = psutil.Process(new_process.pid)
                self.psutil_processes[process_id].cpu_percent()
                self.cpu_last_call[process_id] = time.time()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        # 触发重启回调
        self.trigger_callbacks('on_restart', process_id,
                               new_pid=new_process.pid,
                               restart_count=proc_info['restart_count'],
                               is_critical=proc_info.get('is_critical', False))

        return True

    def print_process_status(self, status):
        """打印进程状态"""
        status_icons = {
            'RUNNING': '🟢',
            'COMPLETED': '✅',
            'CRASHED': '💥',
            'UNRESPONSIVE': '😵',
            'ERROR': '🔥',
            'FINISHED': '🏁'
        }

        icon = status_icons.get(status['status'], '❓')
        critical_flag = "🔴" if status.get('is_critical', False) else "🟡"
        heartbeat_info = ""

        if status['last_heartbeat_age'] is not None:
            heartbeat_info = f"心跳: {status['last_heartbeat_age']} 前"

        self.logger.info(f"{icon}{critical_flag} {status['process_id']:15} | "
                         f"PID: {str(status['pid']):6} | "
                         f"状态: {status['status']:12} | "
                         f"运行: {status['uptime']} | "
                         f"重启: {status['restart_count']} | "
                         f"{heartbeat_info}")

    def register_callback(self, event_type: str, callback: Callable):
        """注册事件回调"""
        if event_type in self.callbacks:
            self.callbacks[event_type].append(callback)
            self.logger.info(f"注册回调: {event_type}")

    def trigger_callbacks(self, event_type: str, process_id: str, **kwargs):
        """触发回调"""
        for callback in self.callbacks.get(event_type, []):
            try:
                callback(process_id, **kwargs)
            except Exception as e:
                self.logger.error(f"回调执行失败 {event_type}: {e}")

    def collect_metrics(self, process_id: str) -> Optional[ProcessMetrics]:
        """收集进程指标"""
        if process_id not in self.processes:
            return None

        proc_info = self.processes[process_id]
        process = proc_info['process']

        if not process or not process.is_alive():
            return None

        try:
            # 获取或创建psutil.Process对象
            if process_id not in self.psutil_processes:
                self.psutil_processes[process_id] = psutil.Process(process.pid)
                # 第一次调用cpu_percent()来初始化
                self.psutil_processes[process_id].cpu_percent()
                self.cpu_last_call[process_id] = time.time()
                cpu_percent = 0.0  # 第一次调用返回0
            else:
                p = self.psutil_processes[process_id]

                # 检查是否需要等待足够的时间间隔来获取准确的CPU使用率
                current_time = time.time()
                if (process_id in self.cpu_last_call and
                        current_time - self.cpu_last_call[process_id] < 1.0):
                    # 如果距离上次调用不足1秒，使用interval参数
                    cpu_percent = p.cpu_percent(interval=0.1)
                else:
                    # 使用非阻塞调用
                    cpu_percent = p.cpu_percent()

                self.cpu_last_call[process_id] = current_time
            # 计算标准化的CPU使用率（相对于单核）
            cpu_percent_normalized = cpu_percent / self.cpu_count
            # 获取内存信息
            memory_mb = self.psutil_processes[process_id].memory_info().rss / 1024 / 1024

            metrics = ProcessMetrics(
                process_id=process_id,
                pid=process.pid,
                status=proc_info['status'],
                cpu_percent=cpu_percent,  # 原始CPU使用率（可能超过100%）
                cpu_percent_normalized=cpu_percent_normalized,  # 标准化CPU使用率（0-100%）
                memory_mb=memory_mb,
                start_time=proc_info['start_time'],
                uptime=datetime.now() - proc_info['start_time'],
                restart_count=proc_info['restart_count'],
                last_heartbeat=proc_info['last_heartbeat'],
                exitcode=process.exitcode
            )

            # 保存当前指标
            self.current_metrics[process_id] = metrics

            # 保存历史记录
            self.metrics_history[process_id].append(metrics)

            # 限制历史记录长度
            if len(self.metrics_history[process_id]) > 100:
                self.metrics_history[process_id].pop(0)

            # 检查阈值告警
            self.check_thresholds(metrics)

            return metrics

        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            self.logger.warning(f"无法收集进程指标 {process_id}: {e}")
            # 清理无效的psutil对象
            if process_id in self.psutil_processes:
                del self.psutil_processes[process_id]
            if process_id in self.cpu_last_call:
                del self.cpu_last_call[process_id]
            return None

    def check_thresholds(self, metrics: ProcessMetrics):
        """检查阈值"""
        # CPU使用率告警 - 使用标准化的CPU使用率
        if metrics.cpu_percent_normalized > self.thresholds['cpu_percent']:
            self.trigger_callbacks('on_high_cpu', metrics.process_id,
                                   cpu_percent=metrics.cpu_percent_normalized,
                                   cpu_percent_raw=metrics.cpu_percent,
                                   threshold=self.thresholds['cpu_percent'])

        # 内存使用告警
        if metrics.memory_mb > self.thresholds['memory_mb']:
            self.trigger_callbacks('on_high_memory', metrics.process_id,
                                   memory_mb=metrics.memory_mb,
                                   threshold=self.thresholds['memory_mb'])

    # def get_metrics_summary(self) -> Dict:
    #     """获取指标汇总"""
    #     summary = {
    #         'timestamp': datetime.now().isoformat(),
    #         'total_processes': len(self.processes),
    #         'critical_processes': list(self.critical_processes),
    #         'current_metrics': {},
    #         'averages': {}
    #     }
    #
    #     for process_id in self.processes:
    #         if process_id in self.current_metrics:
    #             metrics = self.current_metrics[process_id]
    #             summary['current_metrics'][process_id] = asdict(metrics)
    #
    #             # 计算历史平均值
    #             if process_id in self.metrics_history and self.metrics_history[process_id]:
    #                 history = self.metrics_history[process_id]
    #                 # 过滤掉CPU为0的记录来计算平均值
    #                 valid_cpu_records = [m for m in history if m.cpu_percent > 0]
    #
    #                 if valid_cpu_records:
    #                     avg_cpu = sum(m.cpu_percent for m in valid_cpu_records) / len(valid_cpu_records)
    #                 else:
    #                     avg_cpu = 0.0
    #
    #                 avg_memory = sum(m.memory_mb for m in history) / len(history)
    #
    #                 summary['averages'][process_id] = {
    #                     'avg_cpu_percent': avg_cpu,
    #                     'avg_memory_mb': avg_memory,
    #                     'sample_count': len(history),
    #                     'valid_cpu_samples': len(valid_cpu_records)
    #                 }
    #
    #     return summary
    #
    # def export_metrics(self, filename: str):
    #     """导出指标到文件"""
    #     data = {
    #         'export_time': datetime.now().isoformat(),
    #         'thresholds': self.thresholds,
    #         'critical_processes': list(self.critical_processes),
    #         'current_metrics': {
    #             pid: asdict(metrics)
    #             for pid, metrics in self.current_metrics.items()
    #         },
    #         'metrics_history': {
    #             pid: [asdict(m) for m in metrics]
    #             for pid, metrics in self.metrics_history.items()
    #         }
    #     }
    #
    #     with open(filename, 'w') as f:
    #         json.dump(data, f, indent=2)
    #
    #     self.logger.info(f"指标导出到: {filename}")

    def monitor_all_processes(self):
        """监控所有进程"""
        current_time = time.strftime('%H:%M:%S')
        self.logger.info(f"\n=== 进程监控报告 ({current_time}) ===")

        # 首先检查关键进程
        critical_failed = self.check_critical_processes()
        if critical_failed:
            self.logger.critical("检测到关键进程失败，系统将关闭")
            return False  # 返回False表示需要停止监控

        for process_id in list(self.processes.keys()):
            # 检查基本状态
            status = self.check_process_status(process_id)
            if status:
                self.print_process_status(status)

            # 收集指标
            metrics = self.collect_metrics(process_id)
            if metrics:
                # 显示原始CPU使用率和标准化CPU使用率
                self.logger.info(f"    📊 CPU: {metrics.cpu_percent:.1f}% (原始) / "
                                 f"{metrics.cpu_percent_normalized:.1f}% (标准化) | "
                                 f"内存: {metrics.memory_mb:.1f}MB | "
                                 f"核心数: {self.cpu_count}")

        return True

    def start_monitoring(self, interval=5):
        """开始监控"""

        def monitor_loop():
            self.logger.info("开始集成进程监控")
            self.logger.info(f"关键进程: {list(self.critical_processes)}")

            while self.monitoring:
                try:
                    should_continue = self.monitor_all_processes()
                    if not should_continue:
                        self.logger.critical("监控检测到关键进程失败，停止监控")
                        break
                    time.sleep(interval)
                except Exception as e:
                    self.logger.error(f"监控循环错误: {e},{traceback.format_exc()}")

        self.monitor_thread = threading.Thread(target=monitor_loop)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()

    def stop_monitoring(self):
        """停止监控"""
        self.monitoring = False

        if hasattr(self, 'monitor_thread') and self.monitor_thread:
            self.monitor_thread.join()

        # 清理psutil对象
        self.psutil_processes.clear()
        self.cpu_last_call.clear()

        # 清理所有进程
        self.shutdown_all_processes(exclude_critical=False)