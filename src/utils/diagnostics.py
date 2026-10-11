"""
安装/卸载失败诊断工具

失败时收集环境快照并翻译常见 Windows 错误, 让日志能直接回答
"失败在哪一步、什么原因、环境是什么状态", 而不是只有一句异常文本。
"""

from __future__ import annotations

import shutil
from pathlib import Path
from loguru import logger as log
from config.config import TEMP_INSTALL_DIR, TARGET_ASAR_NAME, EXTRACTED_FOLDER_NAME

# 常见 Windows 文件错误 -> 用户可读的原因
_OS_ERROR_REASONS = {
    5: "权限不足 — 目标文件/目录被系统、安全软件或其他程序保护",
    13: "权限不足 — 拒绝访问",
    32: "文件被占用 — 希沃管家相关进程可能仍在运行",
    112: "磁盘空间不足",
    3: "路径不存在",
}


def explain_os_error(e: BaseException) -> str | None:
    """把常见 Windows 文件错误翻译成用户可读的原因; 非文件错误返回 None"""
    if not isinstance(e, OSError):
        return None
    winerror = getattr(e, "winerror", None)
    if winerror in _OS_ERROR_REASONS:
        return _OS_ERROR_REASONS[winerror]
    errno = getattr(e, "errno", None)
    if errno in _OS_ERROR_REASONS:
        return _OS_ERROR_REASONS[errno]
    return None


def collect_failure_diagnostics(install_path) -> list[str]:
    """收集失败时的环境诊断信息, 逐行返回。

    参数:
        install_path: 安装目录 (resources) 路径或 None (尚未确定时)
    """
    lines = []
    try:
        if install_path and Path(install_path).exists():
            d = Path(install_path)
            lines.append(f"安装目录: {d}")
            for name in (TARGET_ASAR_NAME, "app.asar.bak", EXTRACTED_FOLDER_NAME):
                p = d / name
                try:
                    if not p.exists():
                        lines.append(f"  {name}: 不存在")
                    elif p.is_file():
                        lines.append(f"  {name}: 存在 ({p.stat().st_size} 字节)")
                    else:
                        lines.append(f"  {name}: 存在 (目录)")
                except OSError as e:
                    lines.append(f"  {name}: 状态未知 ({e})")
            try:
                free = shutil.disk_usage(str(d)).free
                lines.append(f"  磁盘剩余空间: {free / 1024 / 1024:.0f} MB")
            except OSError as e:
                lines.append(f"  磁盘剩余空间: 获取失败 ({e})")
        else:
            lines.append("安装目录: 尚未确定")

        tmp = Path(TEMP_INSTALL_DIR)
        lines.append(f"临时目录: {tmp} ({'存在' if tmp.exists() else '不存在'})")

        # 希沃进程状态是文件占用的头号原因, 延迟导入避免依赖环
        try:
            from utils import killer

            running = killer.get_running_target_processes()
            lines.append(
                f"希沃相关进程仍在运行: {', '.join(running) if running else '无'}"
            )
        except Exception as e:
            lines.append(f"希沃相关进程: 检查失败 ({e})")
    except Exception as e:
        lines.append(f"(诊断信息收集失败: {e})")
    return lines


def log_failure_diagnostics(step: str, error, install_path):
    """统一入口: 输出失败阶段、错误原因分析与环境诊断快照"""
    try:
        if step:
            log.error(f"失败阶段: {step}")
        reason = explain_os_error(error)
        if reason:
            log.error(f"错误原因分析: {reason}")
        for line in collect_failure_diagnostics(install_path):
            log.error(line)
    except Exception as e:
        log.debug(f"诊断日志输出失败 (忽略): {e}")
