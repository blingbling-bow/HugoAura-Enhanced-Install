import ctypes
import sys
import os
from loguru import logger as log


def is_admin() -> bool:
    try:
        is_admin_flag = os.getuid() == 0
    except AttributeError:
        try:
            is_admin_flag = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except AttributeError:
            log.warning("获取管理员权限状态失败, 默认尝试提权...")
            is_admin_flag = False
        except Exception as e:
            log.error(f"获取管理员权限状态时, 发生未知错误: {e}")
            is_admin_flag = False
    return is_admin_flag


def run_as_admin():
    if sys.platform != "win32":
        log.error("HugoAura 目前仅支持 Windows 平台")
        sys.exit(1)

    try:
        log.info("尝试使用管理员权限重启...")
        script = os.path.abspath(sys.executable)

        # 仅传递命令行参数, 排除 argv[0] (exe 自身路径)。
        # ShellExecuteW 的第三个参数 script 就是新进程的 argv[0]。
        params = " ".join([f'"{arg}"' for arg in sys.argv[1:]]) or None

        ret = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            script,
            params,
            None,
            1,
        )

        if ret <= 32:
            log.error(
                f"提权失败。ShellExecuteW returned: {ret} | Error code: {ctypes.get_last_error()}"
            )
            log.error("请尝试手动以管理员权限运行此管理工具。")
            return False
        else:
            log.info("提权成功, 即将退出旧进程...")
            sys.exit(0)

    except FileNotFoundError:
        log.error(f"提权失败, 管理工具可执行文件定位失败: {script}")
        log.error("请尝试手动以管理员权限运行此管理工具。")
        return False
    except Exception as e:
        log.exception(f"提权时发生未知异常: {e}")
        log.error("请尝试手动以管理员权限运行此管理工具。")
        return False
