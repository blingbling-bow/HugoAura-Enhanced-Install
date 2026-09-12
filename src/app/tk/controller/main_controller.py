"""
主控制器
"""

from __future__ import annotations

import threading
from typing import Dict, Any
from loguru import logger

from app.tk.ui.main_window import MainWindow
from app.tk.models.installer_model import InstallerModel
import tkinter.messagebox as messagebox


class MainController:
    """主控制器类"""

    def __init__(self, theme="flatly"):
        # 创建模型和视图
        self.model = InstallerModel()
        self.view = MainWindow(theme=theme)

        # 绑定事件
        self._bind_events()

        # 设置模型回调
        self._setup_model_callbacks()

        # 检查安装状态并更新UI
        self._check_installation_status()

        logger.info("主控制器初始化完成")

    def _bind_events(self):
        """绑定界面事件"""
        # 设置按钮回调
        self.view.set_install_callback(self._on_install)
        self.view.set_update_callback(self._on_update)
        self.view.set_cancel_callback(self._on_cancel)
        self.view.set_uninstall_callback(self._on_uninstall)

        # 设置窗口关闭事件
        self.view.root.protocol("WM_DELETE_WINDOW", self._on_window_close)

        logger.debug("界面事件绑定完成")

    def _setup_model_callbacks(self):
        """设置模型回调函数"""
        self.model.set_progress_callback(self._on_progress_update)
        self.model.set_status_callback(self._on_status_update)
        self.model.set_completed_callback(self._on_install_completed)

        logger.debug("模型回调设置完成")

    def _on_install(self, options: Dict[str, Any]):
        """处理安装事件"""
        logger.info(f"开始安装, 选项: {options}")

        try:
            # 更新模型的安装选项
            self.model.install_options.update(options)

            # 验证安装选项
            valid, message = self.model.validate_install_options()
            if not valid:
                self.view.show_message("错误", message, "error")
                return

            # 设置UI为安装状态
            self.view.set_installing_state(True)

            # 开始安装
            success, message = self.model.start_install()
            if not success:
                self.view.show_message("错误", message, "error")
                self.view.set_installing_state(False)
                return

            logger.info("安装已开始")

        except Exception as e:
            logger.error(f"安装启动失败: {e}")
            self.view.show_message("错误", f"安装启动失败: {str(e)}", "error")
            self.view.set_installing_state(False)

    def _on_update(self):
        """处理一键更新事件"""
        logger.info("用户请求一键更新")

        if self.model.current_operation is not None:
            return

        try:
            # 设置UI为安装状态
            self.view.set_installing_state(True, "更新")

            # 开始更新
            success, message = self.model.start_update()
            if not success:
                self.view.show_message("提示", message, "info")
                self.view.set_installing_state(False)
                return

            logger.info("更新已开始")

        except Exception as e:
            logger.error(f"更新启动失败: {e}")
            self.view.show_message("错误", f"更新启动失败: {str(e)}", "error")
            self.view.set_installing_state(False)

    def _on_cancel(self):
        """处理取消事件"""
        logger.info("用户请求取消操作")

        op = self.model.current_operation

        # 显示确认对话框
        if op in ("install", "update"):
            operation = "更新" if op == "update" else "安装"
            if messagebox.askyesno("确认", f"确定要取消{operation}吗？"):
                self.model.cancel_install()
                self.view.set_installing_state(False)
                logger.info(f"{operation}已取消")
        elif op == "uninstall":
            if messagebox.askyesno("确认", "确定要取消卸载吗？"):
                self.model.cancel_uninstall()
                self.view.set_installing_state(False)
                logger.info("卸载已取消")

    def _on_progress_update(self, progress: int, step: str, status: str | None = None):
        """处理进度更新"""
        # 使用线程安全的方式更新UI
        self.view.root.after(
            0, lambda: self.view.update_progress(progress, step, status)
        )
        logger.debug(f"进度更新: {progress}% - {step}")

    def _on_status_update(self, status: str):
        """处理状态更新"""
        # 使用线程安全的方式更新UI
        self.view.root.after(0, lambda: self.view.update_status(status))
        logger.debug(f"状态更新: {status}")

    def _on_install_completed(self, success: bool, message: str):
        """处理操作完成事件"""
        logger.info(f"操作完成: {'成功' if success else '失败'} - {message}")

        # 使用线程安全的方式更新UI
        def update_ui():
            self.view.set_installing_state(False)

            if success:
                self.view.show_message("成功", message, "info")
                # 安装成功后重新检查安装状态
                self._check_installation_status()
            else:
                self.view.show_message("失败", message, "error")
                # 安装失败后也重新检查安装状态, 以防部分安装成功
                self._check_installation_status()

        self.view.root.after(0, update_ui)

    def _on_window_close(self):
        """处理窗口关闭事件"""
        logger.info("用户请求关闭窗口")

        # 如果正在执行操作, 询问是否确认关闭
        op = self.model.current_operation
        if op is not None:
            operation = {
                "install": "安装",
                "update": "更新",
                "uninstall": "卸载",
            }.get(op, "操作")
            if not messagebox.askyesno(
                "确认", f"{operation}正在进行中, 确定要退出吗？"
            ):
                return

            # 取消操作
            if op in ("install", "update"):
                self.model.cancel_install()
            elif op == "uninstall":
                self.model.cancel_uninstall()

        # 清理资源
        self._cleanup()

        # 关闭窗口
        self.view.destroy()

        logger.info("应用程序已退出")

    def _cleanup(self):
        """清理资源"""
        try:
            # 等待安装线程结束 (最多等待2秒)
            if self.model.install_thread and self.model.install_thread.is_alive():
                self.model.install_thread.join(timeout=2.0)

            logger.debug("资源清理完成")
        except Exception as e:
            logger.error(f"资源清理失败: {e}")

    def run(self):
        """运行应用程序"""
        logger.info("启动GUI应用程序")
        try:
            self.view.run()
        except KeyboardInterrupt:
            logger.info("用户中断应用程序")
        except Exception as e:
            logger.error(f"应用程序运行出错: {e}")
            raise
        finally:
            self._cleanup()

    def get_install_status(self) -> Dict[str, Any]:
        """获取当前安装状态"""
        return self.model.get_install_status()

    def set_theme(self, theme: str):
        """设置主题"""
        try:
            logger.info(f"切换主题到: {theme}")
        except Exception as e:
            logger.error(f"主题切换失败: {e}")

    def _on_uninstall(self, options: Dict[str, Any]):
        """处理卸载事件"""
        logger.info(f"开始卸载, 选项: {options}")

        try:
            # 更新模型的卸载选项
            self.model.uninstall_options.update(options)

            # 获取卸载信息
            uninstall_info = self.model.get_uninstall_info()

            if not uninstall_info["can_uninstall"]:
                self.view.show_message("信息", "HugoAura 未安装", "info")
                return

            # 设置UI为卸载状态
            self.view.set_installing_state(True, "卸载")

            # 开始卸载
            success, message = self.model.start_uninstall()
            if not success:
                self.view.show_message("错误", message, "error")
                self.view.set_installing_state(False)
                return

            logger.info("卸载已开始")

        except Exception as e:
            logger.error(f"卸载启动失败: {e}")
            self.view.show_message("错误", f"卸载启动失败: {str(e)}", "error")
            self.view.set_installing_state(False)

    def _check_installation_status(self):
        """检查HugoAura安装状态并更新UI"""
        try:
            # 检查是否已安装
            is_installed = self.model.check_hugoaura_installed()

            if is_installed:
                # 如果已安装, 禁用安装按钮并更新状态
                self.view.set_install_button_visible(True)
                self.view.set_install_button_state(False, "已安装")
                self.view.set_update_button_visible(False)
                self.view.update_status("HugoAura 已安装")
                logger.info("检测到 HugoAura 已安装, 安装按钮已禁用")

                # 后台检查是否有可用的更新
                self._check_update_async()
            else:
                # 如果未安装, 确保安装按钮可用
                self.view.set_install_button_visible(True)
                self.view.set_install_button_state(True, "开始安装")
                self.view.set_update_button_state(False, "一键更新")
                self.view.set_update_button_visible(False)
                logger.info("HugoAura 未安装, 安装按钮可用")

        except Exception as e:
            logger.error(f"检查安装状态失败: {e}")
            # 出错时默认允许安装
            self.view.set_install_button_visible(True)
            self.view.set_install_button_state(True, "开始安装")
            self.view.set_update_button_state(False, "一键更新")
            self.view.set_update_button_visible(False)

    def _check_update_async(self):
        """后台检查已安装版本是否可更新"""
        def worker():
            try:
                info = self.model.get_update_available()
            except Exception as e:
                logger.error(f"检查更新失败: {e}")
                info = {
                    "installed": True,
                    "installed_version": None,
                    "latest_version": None,
                    "update_available": False,
                }
            self.view.root.after(0, lambda: self._on_update_available(info))

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def _on_update_available(self, info: Dict[str, Any]):
        """根据更新检测结果更新一键更新按钮"""
        if not info.get("installed"):
            self.view.set_update_button_visible(False)
            return

        update_available = info.get("update_available", False)

        if update_available:
            installed_version = info.get("installed_version") or "未知"
            latest_version = info.get("latest_version") or "未知"

            # 有可用更新时隐藏“已安装”按钮, 避免按钮过多挤掉“取消”按钮
            self.view.set_install_button_visible(False)
            self.view.set_update_button_visible(True)
            self.view.set_update_button_state(True, "一键更新")
            self.view.update_status(f"发现新版本 {latest_version}")
            self.view.step_var.set(
                f"当前版本 {installed_version} → 最新版本 {latest_version}"
            )
            logger.info(
                f"检测到可更新版本: {installed_version} -> {latest_version}"
            )
        else:
            # 已是最新时恢复“已安装”按钮, 并隐藏更新按钮
            self.view.set_update_button_visible(False)
            self.view.set_update_button_state(False, "已是最新")
            self.view.set_install_button_visible(True)
            self.view.update_status("HugoAura 已是最新版本")
            self.view.step_var.set("当前已是最新版本")
            logger.info("HugoAura 已是最新版本")


# 便捷函数
def create_app(theme="flatly") -> MainController:
    """创建应用程序实例"""
    return MainController(theme=theme)


def run_app(theme="flatly"):
    """运行应用程序"""
    app = create_app(theme)
    app.run()
