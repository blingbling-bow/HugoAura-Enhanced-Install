"""
HugoAura-Install GUI 启动器
"""

import sys
import os
import ctypes
from pathlib import Path
from loguru import logger

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 在路径初始化后导入 CLI 入口，确保源码和 PyInstaller 环境都能解析顶层模块。
import main as cliEntryMain

# 在PyInstaller环境中, 需要特殊处理导入
try:
    from logger.initLogger import setup_logger
except ImportError as e:
    print(f"导入logger失败: {e}")
    # 创建一个简单的fallback logger
    def setup_logger():
        print("使用简单日志输出")
        return None

try:
    from app.tk.controller.main_controller import MainController
except ImportError as e:
    print(f"导入MainController失败: {e}")
    print("请确保所有依赖都已正确安装")
    sys.exit(1)


def is_admin():
    """检查是否以管理员权限运行"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def run_as_admin():
    """以管理员权限重新运行程序"""
    if is_admin():
        return True

    try:
        script = os.path.abspath(sys.executable)
        # 构建命令行参数, 完整传递所有参数 (如 --cli)
        if len(sys.argv) > 1:
            params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])
        else:
            params = ""

        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", script, params, None, 1
        )

        if ret <= 32:
            print(f"提升权限失败。ShellExecuteW returned: {ret}")
            return False

        return False  # 已启动新的管理员进程, 需要退出当前进程
    except Exception as e:
        print(f"提升权限失败: {e}")
        return False


def show_error_dialog(message):
    """显示错误对话框"""
    try:
        import tkinter as tk
        from tkinter import messagebox
        
        root = tk.Tk()
        root.withdraw()  # 隐藏主窗口
        messagebox.showerror("AuraInstaller 错误", message)
        root.destroy()
    except:
        # 如果连tkinter都不可用, 就用系统消息框
        try:
            ctypes.windll.user32.MessageBoxW(0, message, "AuraInstaller 错误", 0x10)
        except:
            print(f"错误: {message}")


def main():
    """应用程序入口"""
    try:
        # 检查并提升管理员权限
        if not is_admin():
            print("AuraInstaller 需要管理员权限才能正常工作")
            print("正在请求管理员权限...")
            if not run_as_admin():
                sys.exit(0)  # 已启动新的管理员进程, 退出当前进程
        
        # 初始化日志系统
        try:
            setup_logger()
        except Exception as e:
            print(f"日志初始化失败: {e}")
            # 继续执行, 不让日志问题阻止程序运行
        
        if "--cli" in sys.argv:
            # 以 CLI 模式启动
            app = cliEntryMain.main()
        else:
            # 创建并启动主控制器
            app = MainController()
            app.run()
        
    except ImportError as e:
        error_msg = f"模块导入失败: {e}\n\n请确保所有依赖都已正确安装:\n- ttkbootstrap\n- pillow\n- loguru\n- requests"
        show_error_dialog(error_msg)
        sys.exit(1)
    except Exception as e:
        error_msg = f"启动GUI应用失败: {e}"
        logger.error(f"{e}")
        show_error_dialog(error_msg)
        sys.exit(1)


if __name__ == "__main__":
    main()
