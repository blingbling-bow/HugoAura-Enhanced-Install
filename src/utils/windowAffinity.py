"""窗口防截屏: 通过 SetWindowDisplayAffinity Windows API 把主窗口排除出屏幕捕获。

Windows 10 2004+ 支持 WDA_EXCLUDEFROMCAPTURE —— 截图/录屏/远程画面里完全
看不到该窗口; 更旧的系统 (含 Win7) 不支持该标志, 自动降级为 WDA_MONITOR
(截屏中显示为黑块); 依次尝试, 都失败则只记录日志, 不影响安装流程。
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from loguru import logger as log
from config.config import WINDOW_CAPTURE_EXCLUSION

# Display affinity 常量 (winuser.h)
_WDA_NONE = 0x0
_WDA_MONITOR = 0x1
_WDA_EXCLUDEFROMCAPTURE = 0x11

_MODE_NAMES = {
    _WDA_NONE: "无",
    _WDA_MONITOR: "黑块遮挡 (旧系统)",
    _WDA_EXCLUDEFROMCAPTURE: "完全排除截屏",
}

# SetWindowDisplayAffinity / GetWindowDisplayAffinity 函数签名 (user32)
user32 = ctypes.windll.user32
user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.SetWindowDisplayAffinity.restype = wintypes.BOOL
user32.GetWindowDisplayAffinity.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowDisplayAffinity.restype = wintypes.BOOL


def apply_capture_exclusion(hwnd: int) -> int:
    """把窗口排除出屏幕捕获, 返回生效的 affinity 值 (0 表示未生效)。

    依次尝试 WDA_EXCLUDEFROMCAPTURE (Win10 2004+) -> WDA_MONITOR (旧系统降级),
    都失败返回 _WDA_NONE。
    """
    if not WINDOW_CAPTURE_EXCLUSION:
        log.debug("防截屏开关未开启, 跳过")
        return _WDA_NONE

    applied = _WDA_NONE
    for affinity in (_WDA_EXCLUDEFROMCAPTURE, _WDA_MONITOR):
        if user32.SetWindowDisplayAffinity(hwnd, affinity):
            applied = affinity
            break

    if applied:
        log.info(f"防截屏已生效: {_MODE_NAMES.get(applied, hex(applied))}")
    else:
        log.warning("防截屏未生效 (系统不支持 SetWindowDisplayAffinity)")
    return applied
