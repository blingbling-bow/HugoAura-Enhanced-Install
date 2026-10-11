import subprocess
import threading
import time
from loguru import logger as log
from config.config import TARGET_PROCESS_NAME, PROCESS_KILL_INTERVAL_SECONDS

_stop_event = threading.Event()
_kill_thread = None


def _kill_loop():
    log.info(
        f"启动后台任务: 每 {PROCESS_KILL_INTERVAL_SECONDS} 秒结束一次 {TARGET_PROCESS_NAME} 进程"
    )
    while not _stop_event.is_set():
        try:
            creationflags = subprocess.CREATE_NO_WINDOW
            for procName in TARGET_PROCESS_NAME:
                # /t: 同时结束进程树, 防止守护进程拉起的子进程继续占用文件
                # 中文 Windows 的 taskkill 输出是 ANSI/GBK 编码, 必须显式指定,
                # 否则 text=True 的 UTF-8 解码会崩掉读取线程
                result = subprocess.run(
                    ["taskkill", "/f", "/t", "/im", procName],
                    capture_output=True,
                    text=True,
                    encoding="mbcs",
                    errors="replace",
                    check=False,
                    creationflags=creationflags,
                )
                result_stderr = result.stderr or ""
                result_stdout = result.stdout or ""
                if (
                    result.returncode != 0
                    and "没有找到进程" not in result_stderr.lower()
                ):
                    log.warning(
                        f"进程结束失败: {result_stderr.strip()} (Code: {result.returncode}) 请检查管理工具的权限状态"
                    )
                else:
                    log.debug(
                        f"尝试结束进程 {procName}。操作输出: {result_stdout.strip() or result_stderr.strip()}"
                    )

        except FileNotFoundError:
            log.error('无法调用 "taskkill", 请确认系统环境是否完整。')
            _stop_event.set()
        except Exception as e:
            log.error(f"停止 taskkill 循环时发生意外错误: {e}")

        _stop_event.wait(PROCESS_KILL_INTERVAL_SECONDS)

    log.info(f"结束后台任务: 持续结束 {TARGET_PROCESS_NAME} 进程")


def _is_process_running(proc_name: str) -> bool:
    """检查指定进程是否仍在运行; 检查失败时保守返回 True (视为仍在运行)"""
    try:
        creationflags = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(
            ["tasklist", "/nh", "/fi", f"IMAGENAME eq {proc_name}"],
            capture_output=True,
            text=True,
            encoding="mbcs",
            errors="replace",
            check=False,
            creationflags=creationflags,
        )
        return proc_name.lower() in (result.stdout or "").lower()
    except Exception as e:
        log.warning(f"检查进程 {proc_name} 状态失败: {e}")
        return True


def wait_for_process_exit(timeout_seconds: float = 30.0) -> bool:
    """等待目标进程全部退出。

    参数:
        timeout_seconds: 最长等待时间 (秒)

    返回:
        bool: 是否在超时前全部退出
    """
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not any(_is_process_running(name) for name in TARGET_PROCESS_NAME):
            log.info("目标进程已全部退出")
            return True
        time.sleep(1.0)
    log.warning(f"等待目标进程退出超时 ({timeout_seconds}s), 继续执行...")
    return False


def get_running_target_processes() -> list[str]:
    """返回仍在运行的目标进程名列表 (去重), 供失败诊断使用"""
    running = []
    for name in TARGET_PROCESS_NAME:
        if _is_process_running(name) and name not in running:
            running.append(name)
    return running


def start_killing_process():
    global _kill_thread, _stop_event
    if _kill_thread and _kill_thread.is_alive():
        return

    _stop_event.clear()
    _kill_thread = threading.Thread(target=_kill_loop, daemon=True)
    _kill_thread.start()


def stop_killing_process():
    global _kill_thread
    _stop_event.set()
    if _kill_thread and _kill_thread.is_alive():
        _kill_thread.join(timeout=PROCESS_KILL_INTERVAL_SECONDS * 4)
        if _kill_thread.is_alive():
            log.warning("taskkill 循环意外结束。(可忽略)")
    _kill_thread = None
