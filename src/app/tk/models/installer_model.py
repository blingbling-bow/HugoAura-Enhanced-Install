"""
安装器模型 - 封装 HugoAura 安装相关的业务逻辑
"""

from __future__ import annotations

import os
import threading
from typing import Callable, Optional, Dict, Any
import argparse

from loguru import logger

from app.install_manager import run_installation
from app.uninstall_manager import (
    run_uninstallation,
    get_uninstall_info,
    check_hugoaura_installation,
)
from utils.version_manager import version_manager


class InstallerModel:
    """安装器模型类"""

    def __init__(self):
        self.installer = None
        self.install_progress = 0
        self.install_status = "就绪"
        self.current_step = ""
        self.is_installing = False
        self.is_uninstalling = False
        # 当前操作: None / "install" / "update" / "uninstall"
        # 作为唯一的状态判别来源, 避免多个布尔标志同时为 True 造成歧义。
        self.current_operation: Optional[str] = None
        # 一键更新的目标 tag (由 get_update_available 判定):
        # 只推荐发行版, CI 构建由用户手动安装, 不作为更新目标
        self.update_target_tag: Optional[str] = None
        self.install_thread = None

        # 回调函数
        self.progress_callback: Optional[Callable[[int, str, str | None], None]] = None
        self.status_callback: Optional[Callable[[str], None]] = None
        self.completed_callback: Optional[Callable[[bool, str], None]] = None

        # 安装选项
        self.install_options = {
            "version": "latest",
            "custom_version": "",
            "custom_path": "",
            "install_directory": "",
            "non_interactive": True,
        }

        # 卸载选项
        self.uninstall_options = {
            "keep_user_data": False,
            "force": False,
            "dry_run": False,
        }

    def set_progress_callback(self, callback: Callable[[int, str, str | None], None]):
        """设置进度更新回调"""
        self.progress_callback = callback

    def set_status_callback(self, callback: Callable[[str], None]):
        """设置状态更新回调"""
        self.status_callback = callback

    def set_completed_callback(self, callback: Callable[[bool, str], None]):
        """设置安装完成回调"""
        self.completed_callback = callback

    def update_progress(self, progress: int, step: str, status: str | None = None):
        """更新安装进度"""
        self.install_progress = progress
        self.current_step = step
        if self.progress_callback:
            self.progress_callback(progress, step, status)

    def update_status(self, status: str):
        """更新安装状态"""
        self.install_status = status
        if self.status_callback:
            self.status_callback(status)

    def get_seewo_directories(self) -> list:
        """获取希沃管家安装目录列表"""
        try:
            from utils.dirSearch import find_seewo_resources_dir

            dir_path = find_seewo_resources_dir()
            return [dir_path] if dir_path else []
        except Exception as e:
            return []

    def validate_install_options(self) -> tuple[bool, str]:
        """验证安装选项"""
        if self.install_options["version"] == "custom_version":
            if not self.install_options["custom_version"]:
                return False, "请输入自定义版本号"

        if self.install_options["version"] == "custom_path":
            if not self.install_options["custom_path"]:
                return False, "请选择自定义文件路径"
            if not os.path.exists(self.install_options["custom_path"]):
                return False, "指定的文件路径不存在"

        return True, ""

    def start_install(self):
        """开始安装"""
        if self.current_operation is not None:
            return False, "任务正在进行中"

        valid, message = self.validate_install_options()
        if not valid:
            return False, message

        self.is_installing = True
        self.current_operation = "install"
        self.install_progress = 0
        self.update_status("正在安装...")

        self.install_thread = threading.Thread(
            target=self._install_worker, kwargs={"is_update": False}
        )
        self.install_thread.daemon = True
        self.install_thread.start()

        return True, "安装已开始"

    def start_update(self):
        """一键更新到最新稳定版"""
        if self.current_operation is not None:
            return False, "任务正在进行中"

        is_installed, _ = check_hugoaura_installation()
        if not is_installed:
            return False, "HugoAura 尚未安装, 无法更新"

        self.is_installing = True
        self.current_operation = "update"
        self.install_progress = 0
        self.update_status("正在更新...")

        self.install_thread = threading.Thread(
            target=self._install_worker, kwargs={"is_update": True}
        )
        self.install_thread.daemon = True
        self.install_thread.start()

        return True, "更新已开始"

    def start_uninstall(self):
        """开始卸载"""
        if self.current_operation is not None:
            return False, "操作正在进行中"

        self.is_uninstalling = True
        self.current_operation = "uninstall"
        self.install_progress = 0
        self.update_status("正在卸载...")

        self.install_thread = threading.Thread(target=self._uninstall_worker)
        self.install_thread.daemon = True
        self.install_thread.start()

        return True, "卸载已开始"

    def _install_worker(self, is_update: bool = False):
        """安装 / 更新工作线程"""
        operation_name = "更新" if is_update else "安装"
        try:
            # 构建命令行参数对象
            args = (
                self._build_update_args()
                if is_update
                else self._build_install_args()
            )

            # 传递进度回调函数给安装器
            args.progress_callback = self.update_progress
            args.status_callback = self.update_status

            # 开始进度更新
            self.update_progress(0, f"[0 / 10] 准备{operation_name}...", "info")

            # 执行实际操作
            result = run_installation(args, self)

            if result["success"]:
                self.update_status(f"{operation_name}完成")
                if self.completed_callback:
                    self.completed_callback(True, f"HugoAura {operation_name}成功！")
            else:
                self.update_status(f"{operation_name}失败")
                if self.completed_callback:
                    error_info = result.get("errorInfo", "未知错误")
                    if hasattr(error_info, '__str__'):
                        error_detail = str(error_info)
                    else:
                        error_detail = f"{operation_name}过程中发生未知错误"
                    
                    # 根据错误类型提供更详细的错误信息
                    if "资源文件解压失败" in error_detail:
                        error_message = f"{operation_name}失败: {error_detail}\n\n可能原因: \n- 下载的文件损坏\n- 磁盘空间不足\n- 临时目录权限问题"
                    elif "文件结构不正确" in error_detail:
                        error_message = f"{operation_name}失败: {error_detail}\n\n可能原因: \n- 下载的压缩包格式不正确\n- 文件在传输过程中损坏"
                    elif "移动文件夹" in error_detail:
                        error_message = f"{operation_name}失败: {error_detail}\n\n可能原因: \n- 目标目录权限不足\n- 磁盘空间不足\n- 文件被其他程序占用"
                    elif "替换ASAR文件" in error_detail:
                        error_message = f"{operation_name}失败: {error_detail}\n\n可能原因: \n- 希沃管家正在运行\n- 文件系统过滤驱动未正确卸载"
                    else:
                        error_message = f"{operation_name}过程中发生错误: \n{error_detail}"
                    
                    self.completed_callback(False, error_message)

        except Exception as e:
            self.update_status(f"{operation_name}失败")
            if not self.is_installing:
                self.update_progress(0, f"[FAILED] {operation_name}取消", "error")
                self.update_status(f"{operation_name}已取消")
            elif self.completed_callback:
                self.completed_callback(False, f"{operation_name}失败: {str(e)}")
        finally:
            self.is_installing = False
            self.current_operation = None

    def _uninstall_worker(self):
        """卸载工作线程"""
        try:
            # 构建命令行参数对象
            args = self._build_uninstall_args()

            # 传递进度回调函数给卸载器
            args.progress_callback = self.update_progress
            args.status_callback = self.update_status

            # 开始卸载进度更新
            self.update_progress(0, "[0 / 8] 准备卸载...", "info")

            if not self.is_uninstalling:  # 检查是否被取消
                return

            # 执行实际卸载
            result = run_uninstallation(args, self)

            if result["success"]:
                # self.update_progress(100, "[8 / 8] 卸载完成")
                self.update_status("卸载完成")
                if self.completed_callback:
                    self.completed_callback(
                        True, "HugoAura 卸载成功! 希沃管家已恢复原始状态。"
                    )
            else:
                self.update_status("卸载失败")
                if self.completed_callback:
                    error_info = result.get("errorInfo", "未知错误")
                    error_str = str(error_info) if hasattr(error_info, '__str__') else "未知错误"
                    
                    # 根据错误类型提供更详细的错误信息和解决方案
                    if "OLD_ASAR_ENOENT" in error_str:
                        error_message = "卸载失败: 找不到原始ASAR备份文件\n\n无法将希沃管家恢复到原始状态。\n\n建议解决方案: \n1. 从希沃官网(e.seewo.com)重新下载希沃管家完整安装包\n2. 卸载当前希沃管家后重新安装"
                    elif "UNINSTALLATION_CANCELLED" in error_str:
                        error_message = "卸载已被用户取消"
                    elif "恢复原始ASAR文件失败" in error_str:
                        error_message = (
                            f"卸载失败: {error_str}\n\n"
                            "可能原因: 希沃管家相关进程仍在运行或自动重启, "
                            "导致 app.asar 被占用。\n\n"
                            "建议: 重新执行卸载 (安装器已自动重试多次), "
                            "若仍失败请手动结束希沃管家进程后重试。"
                        )
                    elif "删除Aura文件夹失败" in error_str:
                        error_message = f"部分卸载失败: {error_str}\n\n主要卸载流程已完成, 但清理工作未完全成功。\n建议手动删除残留文件。"
                    else:
                        error_message = f"卸载过程中发生错误: \n{error_str}"
                    
                    self.completed_callback(False, error_message)

        except Exception as e:
            self.update_status("卸载失败")
            if not self.is_uninstalling:
                self.update_progress(0, "[FAILED] 卸载取消", "error")
                self.update_status("卸载已取消")
            elif self.completed_callback:
                self.completed_callback(False, f"卸载失败: {str(e)}")
        finally:
            self.is_uninstalling = False
            self.current_operation = None

    def cancel_install(self):
        """取消安装 / 更新

        只清除后端活跃标志, 让 worker 抛出取消异常并快速退出。
        current_operation 由 worker 的 finally 统一清理, 避免旧线程
        覆盖新启动操作的状态。
        """
        if self.is_installing:
            self.is_installing = False
            self.update_status("正在取消安装...")

    def cancel_uninstall(self):
        """取消卸载"""
        if self.is_uninstalling:
            self.is_uninstalling = False
            self.update_status("正在取消卸载...")

    def get_uninstall_info(self) -> Dict[str, Any]:
        """获取卸载信息"""
        return get_uninstall_info()  # Call func in uninstaller.py

    def _build_install_args(self) -> argparse.Namespace:
        """构建安装参数"""
        args = argparse.Namespace()

        # 设置默认值
        args.yes = self.install_options["non_interactive"]
        args.latest = False
        args.pre = False
        args.ci = False
        args.version = None
        args.path = None
        args.dir = None
        args.dry_run = False

        version = self.install_options["version"]
        version_type = self.install_options.get("version_type", "")
        
        # 内置版本标签列表 (CLI 兼容, 与 GitHub 上真实存在的 release tag 对齐)
        # 注意: CI 构建 tag 形如 vAutoBuild-<commit短hash> 且持续更新,
        #       不应在此硬编码, 以免再次出现过时 tag 导致下载旧构建的问题
        built_in_versions = [
            "v0.2.0-rc2",
            "v0.2.0-rc1-p4",
        ]
        
        # 根据版本类型和具体版本进行处理
        if version_type == "custom_path" or version == "custom_path":
            args.path = self.install_options["custom_path"]
        elif version in built_in_versions:
            # 处理内置版本标签
            args.version = version
        elif version_type == "custom_version" or version == "custom_version":
            args.version = self.install_options["custom_version"]
        elif version == "latest":
            args.latest = True
        elif version == "pre":
            args.pre = True
        elif version == "ci":
            args.ci = True
        else:
            # 默认情况, 可能是其他自定义版本
            args.version = version

        if self.install_options["install_directory"]:
            args.dir = self.install_options["install_directory"]

        return args

    def _build_update_args(self) -> argparse.Namespace:
        """构建一键更新参数。

        优先使用检测到的更新目标 (CI 构建或发行版, 按 published_at 判定);
        未检测到时回退到最新稳定版。
        """
        args = argparse.Namespace()

        args.yes = True
        args.latest = False
        args.pre = False
        args.ci = False
        args.version = self.update_target_tag or None
        args.path = None
        args.dir = None
        args.dry_run = False
        args.operation_name = "更新"
        if not args.version:
            args.latest = True

        return args

    def _build_uninstall_args(self) -> argparse.Namespace:
        """构建卸载参数"""
        args = argparse.Namespace()

        args.keep_user_data = self.uninstall_options["keep_user_data"]
        args.force = self.uninstall_options["force"]
        args.dry_run = self.uninstall_options["dry_run"]

        return args

    def get_install_status(self) -> Dict[str, Any]:
        """获取当前安装状态"""
        return {
            "is_installing": self.is_installing,
            "is_uninstalling": self.is_uninstalling,
            "current_operation": self.current_operation,
            "progress": self.install_progress,
            "status": self.install_status,
            "current_step": self.current_step,
        }

    def check_hugoaura_installed(self) -> bool:
        """检查HugoAura是否已安装"""
        try:
            is_installed, _ = check_hugoaura_installation()
            return is_installed
        except Exception as e:
            # 如果检查过程中出错, 默认返回False (未安装)
            return False

    def get_update_available(self) -> Dict[str, Any]:
        """检查是否存在可用更新 (按发布时间比新旧, 只推荐发行版)。

        CI 自动构建 (vAutoBuild-*) 不作为更新目标: CI 安装由用户手动进行,
        一键更新只引导到发行版。CI tag 是 commit hash, 没有版本大小关系,
        因此新旧一律用 GitHub 发布时间 (published_at) 比较:

        - 已装发行版 → 有发布时间更新的发行版才提示
        - 已装 CI → 仅当发行版发布时间比当前 CI 构建新时提示;
          更新的 CI 构建不提示, 由用户手动安装
        """
        is_installed, install_info = check_hugoaura_installation()
        if not is_installed:
            return {
                "installed": False,
                "installed_version": None,
                "update_target": None,
                "target_is_ci": False,
                "update_available": False,
                "offline": False,
            }

        # 离线模式 (GitHub API 不可用, 回退到本地 versions.json 快照) 下
        # 跳过更新检查: 快照是静态的, 其中的"最新版本"可能落后于已安装
        # 版本, 任何比较结果都不可靠。
        try:
            data_source = version_manager.get_versions().get("data_source")
        except Exception:
            data_source = None
        if data_source != "github_api":
            logger.info(
                f"版本信息来源为 {data_source or 'empty'} (离线模式), 跳过更新检查"
            )
            self.update_target_tag = None
            return {
                "installed": True,
                "installed_version": install_info.get("version"),
                "update_target": None,
                "target_is_ci": False,
                "update_available": False,
                "offline": True,
            }

        installed = install_info.get("version")
        if not installed or installed in ("", "local"):
            # local 安装无法与 release 比较
            self.update_target_tag = None
            return {
                "installed": True,
                "installed_version": installed,
                "update_target": None,
                "target_is_ci": False,
                "update_available": False,
                "offline": False,
            }

        # 已装版本的发布时间; None 表示太旧不在列表里 / 离线数据不全,
        # 视为过期, 有更新候选即提示
        installed_at = version_manager.find_published_at(installed)

        def is_newer(candidate_at: Optional[str]) -> bool:
            if not candidate_at:
                return False
            if installed_at is None:
                return True
            # GitHub published_at 是统一 UTC ISO8601, 字符串比较即可
            return candidate_at > installed_at

        # CI 构建不作为更新目标 (由用户手动安装), 一键更新只推荐发行版
        latest_stable = version_manager.get_latest_release()

        target = None
        if (
            latest_stable
            and latest_stable.get("tag") != installed
            and is_newer(latest_stable.get("published_at"))
        ):
            target = latest_stable["tag"]

        self.update_target_tag = target

        return {
            "installed": True,
            "installed_version": installed,
            "update_target": target,
            "target_is_ci": False,
            "update_available": target is not None,
            "offline": False,
        }
