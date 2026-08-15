"""
主窗口 UI
"""

from logging import WARN
from version import __appVer__
import tkinter as tk
from tkinter import filedialog, messagebox
import ttkbootstrap as ttk_bs
from ttkbootstrap.constants import *
from tkinter.font import ITALIC
from typing import Callable, Optional, Dict
import ctypes
import os
from pathlib import Path
from datetime import datetime
from utils.version_manager import version_manager


def _enable_high_dpi_awareness():
    """
    在 Windows 上启用高 DPI 感知, 避免高缩放比例下窗口被放大裁剪。

    需要在创建 Tk 根窗口之前调用。
    """
    try:
        if os.name != "nt":
            return

        # 优先使用 shcore 接口 (Windows 8.1+)
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
            return
        except Exception:
            pass

        # 回退到较旧的 DPIAware 接口
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    except Exception:
        # DPI 设置失败时静默忽略, 不影响程序其他逻辑
        pass


class MainWindow:
    """主窗口UI类"""

    def __init__(self, theme="flatly"):
        # 在创建根窗口前启用高 DPI 感知, 解决高缩放比例下窗口显示异常的问题
        _enable_high_dpi_awareness()

        # 创建根窗口
        self.root = ttk_bs.Window(themename=theme)
        self.root.title("HugoAura-Enhanced 安装器")

        self.geometry_info = {
            "BASELINE_HEIGHT": 400,  # 增加基准高度以确保内容完整显示
            "BASELINE_WIDTH": 400,   # 增加基准宽度以提供更好的显示效果
            "scaleFactor": ctypes.windll.shcore.GetScaleFactorForDevice(0) / 100
        }

        # 初始大小, 允许后续根据内容和屏幕大小自动调整
        self.root.geometry(
            f"{int(self.geometry_info["BASELINE_WIDTH"] * self.geometry_info["scaleFactor"])}x{int(self.geometry_info["BASELINE_HEIGHT"] * self.geometry_info["scaleFactor"])}"
        )
        self.root.tk.call("tk", "scaling", self.geometry_info["scaleFactor"] * 100 / 75)
        # 允许窗口缩放和最大化, 方便在小分辨率/高 DPI 下查看完整内容
        self.root.resizable(True, True)
        self.root.iconbitmap(
            os.path.join(
                Path(os.path.dirname(__file__)).parents[1],
                "public",
                "installer.ico",
            )
        )

        # 居中显示窗口
        self._center_window()

        # 回调函数
        self.install_callback: Optional[Callable] = None
        self.update_callback: Optional[Callable] = None
        self.uninstall_callback: Optional[Callable] = None
        self.cancel_callback: Optional[Callable] = None

        # 控件变量
        self.version_var = tk.StringVar(
            value="release"
        )  # 版本类型：release, prerelease, ci, custom_version, custom_path
        self.specific_version_var = tk.StringVar()  # 具体版本
        self.custom_version_var = tk.StringVar()
        self.custom_path_var = tk.StringVar()
        self.install_directory_var = tk.StringVar()
        self.progress_var = tk.DoubleVar()
        self.status_var = tk.StringVar(value="正在加载版本信息...")
        self.step_var = tk.StringVar()

        # 控件全局挂载
        self.version_frame = None

        # 版本信息
        self.versions_data = {}
        self.version_widgets = {}  # 存储动态创建的版本选择控件
        self.is_refreshing = False  # 刷新状态标志

        # 创建界面
        self._create_widgets()

        # 初始状态
        self.is_installing = False
        # 标记窗口是否已完成首次自适应居中, 之后不再重复居中, 避免点击按钮时窗口跳回屏幕中央
        self._window_centered = False

        # 异步加载版本信息
        self._load_versions_async()

    def _load_versions_async(self, is_refresh=False):
        """异步加载版本信息"""
        import threading
        import time

        def load_versions():
            try:
                # 设置超时保护
                if is_refresh:
                    # 启动超时保护定时器
                    timeout_timer = threading.Timer(
                        10.0,
                        lambda: self.root.after(
                            0,
                            lambda: self._on_versions_load_error(
                                "操作超时", is_refresh
                            ),
                        ),
                    )
                    timeout_timer.start()

                self.versions_data = version_manager.get_versions()

                # 取消超时定时器
                if is_refresh:
                    timeout_timer.cancel()

                # 在主线程中更新UI
                self.root.after(0, lambda: self._on_versions_loaded(is_refresh))
            except Exception as e:
                # 取消超时定时器
                if is_refresh:
                    try:
                        timeout_timer.cancel()
                    except:
                        pass
                # 在主线程中显示错误
                self.root.after(
                    0, lambda: self._on_versions_load_error(str(e), is_refresh)
                )

        # 在后台线程中加载版本信息
        thread = threading.Thread(target=load_versions, daemon=True)
        thread.start()

    def _on_versions_loaded(self, is_refresh=False):
        """版本信息加载完成后的回调"""
        # 获取数据来源信息
        data_source = self.versions_data.get("data_source", "unknown")
        source_text = {
            "github_api": "来自 GitHub API",
            "local_json": "来自本地文件",
            "empty": "无版本数据",
        }.get(data_source, "未知来源")

        if is_refresh:
            self._set_refresh_state(False)
            if data_source == "github_api":
                self.status_var.set("版本信息刷新成功")
                self.step_var.set(f"已获取最新版本信息 ({source_text})")
                # 显示成功提示
                self.show_message("刷新成功", "版本信息已更新到最新状态", "info")
            else:
                self.status_var.set("版本信息刷新完成")
                self.step_var.set(f"使用备份版本信息 ({source_text})")
                # 显示警告提示
                self.show_message(
                    "刷新完成", f"GitHub API 不可用, 使用本地备份版本信息", "warning"
                )
        else:
            self.status_var.set("就绪")
            self.step_var.set(f"版本信息已加载 ({source_text})")

        self._rebuild_version_options()
        self._update_version_inputs()

    def _on_versions_load_error(self, error_msg: str, is_refresh=False):
        """版本信息加载失败后的回调"""
        if is_refresh:
            self._set_refresh_state(False)
            self.status_var.set("版本信息刷新失败")
            self.step_var.set(f"刷新错误: {error_msg}")
            # 显示错误提示
            self.show_message(
                "刷新失败",
                f"无法获取最新版本信息：{error_msg}\n\n将继续使用本地版本信息",
                "warning",
            )
        else:
            self.status_var.set("版本信息加载失败, 使用默认配置")
            self.step_var.set(f"错误: {error_msg}")

        # 使用空的版本数据, 让用户至少可以使用自定义选项
        self.versions_data = {"releases": [], "prereleases": [], "ci_builds": []}
        self._rebuild_version_options()
        self._update_version_inputs()

    def _format_version_date(self, published_at: Optional[str]) -> str:
        """
        格式化版本发布日期
        
        Args:
            published_at: ISO格式的日期字符串 (例如: "2025-06-20T12:00:00Z")
            
        Returns:
            格式化后的日期字符串 (例如: "2025/06/20"), 如果日期无效则返回空字符串
        """
        if not published_at:
            return ""
        
        try:
            # 处理不同的ISO日期格式
            date_str = published_at.strip()
            
            # 如果以Z结尾，替换为+00:00以便fromisoformat解析
            if date_str.endswith('Z'):
                date_str = date_str[:-1] + '+00:00'
            # 如果没有时区信息，直接解析
            elif '+' not in date_str and date_str.count(':') >= 2:
                # 包含时间但没有时区，尝试添加默认时区
                if 'T' in date_str:
                    date_str = date_str + '+00:00'
            
            # 解析ISO格式日期
            dt = datetime.fromisoformat(date_str)
            
            # 格式化为 YYYY/MM/DD
            return dt.strftime("%Y/%m/%d")
        except (ValueError, AttributeError, TypeError) as e:
            # 如果解析失败，返回空字符串
            return ""

    def _create_version_option_widget(self, parent_frame, version_info: Dict, bootstyle: str):
        """
        创建带日期显示的版本选项控件
        
        Args:
            parent_frame: 父框架
            version_info: 版本信息字典
            bootstyle: ttkbootstrap样式
            
        Returns:
            包含版本选项的Frame控件
        """
        # 创建容器Frame
        option_frame = ttk_bs.Frame(parent_frame)
        
        # 创建单选按钮（不显示文本）
        radio = ttk_bs.Radiobutton(
            option_frame,
            text="",  # 文本Label显示
            variable=self.specific_version_var,
            value=version_info["tag"],
            bootstyle=bootstyle,
            takefocus=False,
        )
        radio.pack(side=LEFT, padx=(0, 6))
        
        # 创建版本名称标签
        version_name = version_info["name"]
        version_label = ttk_bs.Label(
            option_frame,
            text=version_name,
            font=("Microsoft YaHei UI", 9),
        )
        version_label.pack(side=LEFT)
        
        # 创建日期标签（如果有日期）
        published_at = version_info.get("published_at")
        date_str = self._format_version_date(published_at)
        if date_str:
            # 添加分隔符
            separator_label = ttk_bs.Label(
                option_frame,
                text=" · ",
                font=("Microsoft YaHei UI", 8),
                bootstyle=SECONDARY,
            )
            separator_label.pack(side=LEFT, padx=(6, 0))
            
            # 日期标签（较小字号、斜体、灰色）
            date_label = ttk_bs.Label(
                option_frame,
                text=date_str,
                font=("Microsoft YaHei UI", 8, ITALIC),
                bootstyle=SECONDARY,
            )
            date_label.pack(side=LEFT)
        
        # 绑定点击事件：点击整个Frame或任何子控件时也选中单选按钮
        def on_frame_click(event):
            radio.invoke()
        
        option_frame.bind("<Button-1>", on_frame_click)
        version_label.bind("<Button-1>", on_frame_click)
        if date_str:
            separator_label.bind("<Button-1>", on_frame_click)
            date_label.bind("<Button-1>", on_frame_click)
        
        return option_frame

    def _rebuild_version_options(self):
        """根据加载的版本数据重建版本选择选项"""
        # 清理现有的版本选择控件
        for frame in [self.release_frame, self.prerelease_frame, self.ci_frame]:
            for widget in frame.winfo_children():
                widget.destroy()

        self.version_widgets.clear()

        # 创建发行版选项
        releases = self.versions_data.get("releases", [])
        for version_info in releases:
            option_frame = self._create_version_option_widget(
                self.release_frame,
                version_info,
                INFO
            )
            option_frame.pack(anchor=W, pady=1, fill=X)
            self.version_widgets[version_info["tag"]] = option_frame

        # 创建预发行版选项
        prereleases = self.versions_data.get("prereleases", [])
        for version_info in prereleases:
            option_frame = self._create_version_option_widget(
                self.prerelease_frame,
                version_info,
                WARNING
            )
            option_frame.pack(anchor=W, pady=1, fill=X)
            self.version_widgets[version_info["tag"]] = option_frame

        # 创建CI构建版选项
        ci_builds = self.versions_data.get("ci_builds", [])
        for version_info in ci_builds:
            option_frame = self._create_version_option_widget(
                self.ci_frame,
                version_info,
                INFO
            )
            option_frame.pack(anchor=W, pady=1, fill=X)
            self.version_widgets[version_info["tag"]] = option_frame

        # 设置默认选择
        self._set_default_version_selection()

    def _set_default_version_selection(self):
        """设置默认的版本选择"""
        # 优先选择最新的发行版
        releases = self.versions_data.get("releases", [])
        if releases:
            self.specific_version_var.set(releases[0]["tag"])
            return

        # 如果没有发行版, 选择最新的预发行版
        prereleases = self.versions_data.get("prereleases", [])
        if prereleases:
            self.specific_version_var.set(prereleases[0]["tag"])
            return

        # 如果都没有, 选择CI构建版
        ci_builds = self.versions_data.get("ci_builds", [])
        if ci_builds:
            self.specific_version_var.set(ci_builds[0]["tag"])

    def _is_valid_version_for_type(self, version_type: str) -> bool:
        """检查当前选择的版本是否对指定的版本类型有效"""
        current_version = self.specific_version_var.get()
        if not current_version:
            return False

        version_list_key = {
            "release": "releases",
            "prerelease": "prereleases",
            "ci": "ci_builds",
        }.get(version_type)

        if not version_list_key:
            return False

        versions = self.versions_data.get(version_list_key, [])
        return any(v["tag"] == current_version for v in versions)

    def _set_refresh_state(self, refreshing: bool):
        """设置刷新状态"""
        self.is_refreshing = refreshing

        # 找到刷新按钮并更新状态
        for widget in self.root.winfo_children():
            self._update_refresh_button_recursive(widget, refreshing)

    def _update_refresh_button_recursive(self, widget, refreshing: bool):
        """递归查找并更新刷新按钮状态"""
        try:
            # 检查是否是刷新按钮
            if hasattr(widget, "cget") and widget.cget("text") in [
                "🔄 刷新版本",
                "⏳ 刷新中...",
            ]:
                if refreshing:
                    widget.config(text="⏳ 刷新中...", state="disabled")
                else:
                    widget.config(text="🔄 刷新版本", state="normal")

            # 递归检查子控件
            for child in widget.winfo_children():
                self._update_refresh_button_recursive(child, refreshing)
        except:
            # 忽略任何错误, 继续处理其他控件
            pass

    def _disable_refresh_button_recursive(self, widget):
        """递归禁用刷新按钮"""
        try:
            if hasattr(widget, "cget") and "刷新版本" in widget.cget("text"):
                widget.config(state="disabled")

            for child in widget.winfo_children():
                self._disable_refresh_button_recursive(child)
        except:
            pass

    def _enable_refresh_button_recursive(self, widget):
        """递归启用刷新按钮"""
        try:
            if hasattr(widget, "cget") and "刷新版本" in widget.cget("text"):
                widget.config(state="normal")

            for child in widget.winfo_children():
                self._enable_refresh_button_recursive(child)
        except:
            pass

    def _refresh_versions(self):
        """刷新版本信息"""
        if self.is_installing or self.is_refreshing:
            return  # 安装过程中或正在刷新时不允许重复刷新

        # 设置刷新状态
        self._set_refresh_state(True)
        self.status_var.set("正在刷新版本信息...")
        self.step_var.set("从GitHub API获取最新版本信息")

        # 清除缓存
        version_manager.refresh_cache()

        # 重新加载版本信息
        self._load_versions_async(is_refresh=True)

    def _handle_frame_resize(self, newFrameHeight=None):
        """
        根据整个内容框架的实际需求高度自适应窗口高度, 确保内容完整展示,
        同时限制不超过屏幕可用区域 (预留边距避免贴边), 无需滚动即可看到全部内容。

        宽度保持固定的紧凑值, 不随内容过度扩展, 避免产生多余空白区域。

        参数 newFrameHeight 为兼容旧调用点保留, 已不再使用。
        """
        # 让布局引擎先结算出内容框架的真实需求高度
        try:
            self.root.update_idletasks()
            content_height = self._main_frame.winfo_reqheight()
        except Exception:
            content_height = None

        scale = self.geometry_info["scaleFactor"]
        screen_height = self.root.winfo_screenheight() or (400 * scale)

        # 宽度保持固定的紧凑值, 避免窗口过宽产生空白
        final_width = int(self.geometry_info["BASELINE_WIDTH"] * scale)

        # 预留边距, 避免窗口贴边/被任务栏遮挡
        margin_y = 100

        if content_height:
            # geometry 的高度即客户区高度(标题栏在外), 直接等于内容需求高度即可精确贴合,
            # 再加装饰高度会导致客户区比内容高一截, 底部出现留白
            final_height = int(content_height)
        else:
            final_height = int(self.geometry_info["BASELINE_HEIGHT"] * scale)

        # 限制在屏幕可用范围内
        final_height = min(final_height, int(screen_height - margin_y))

        # 首次自适应时重新居中; 之后保持窗口当前位置, 仅微调保证不超出屏幕
        # (避免点击按钮触发高度变化时, 窗口每次都跳回屏幕中央)
        try:
            current_x = self.root.winfo_x()
            current_y = self.root.winfo_y()
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            final_x = min(max(current_x, 0), max(screen_width - final_width, 0))
            final_y = min(max(current_y, 0), max(screen_height - final_height, 0))
        except Exception:
            final_x, final_y = 0, 0

        if not self._window_centered:
            self._window_centered = True
            # 首次调用时窗口尚未达到最终尺寸, 直接居中
            self.root.geometry(f"{final_width}x{final_height}")
            self._center_window()
        else:
            self.root.geometry(f"{final_width}x{final_height}+{final_x}+{final_y}")

    def _center_window(self):
        """窗口居中显示, 并确保不会超出屏幕范围"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = max(0, int((screen_width - width) // 2))
        y = max(0, int((screen_height - height) // 2))
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _on_scrollable_frame_configure(self, event):
        """
        当内部内容尺寸变化时, 更新画布的滚动区域, 并自适应宽度。
        """
        if not hasattr(self, "_canvas") or not hasattr(self, "_canvas_window"):
            return

        canvas = self._canvas
        # 更新滚动区域
        canvas.configure(scrollregion=canvas.bbox("all"))
        
        # 更新内容居中位置
        self._update_content_center()

    def _on_canvas_configure(self, event):
        """当画布大小变化时, 更新内容居中位置和滚动区域"""
        if not hasattr(self, "_canvas") or not hasattr(self, "_canvas_window"):
            return
        
        canvas = self._canvas
        # 更新滚动区域
        canvas.configure(scrollregion=canvas.bbox("all"))
        
        # 更新内容居中位置
        self._update_content_center()

    def _update_content_center(self):
        """
        更新内容在画布中的水平居中位置，确保垂直位置始终从顶部开始
        修复窗口最大化/还原时内容飘到视口外的：Canvas窗口的y坐标必须始终为0
        """
        if not hasattr(self, "_canvas") or not hasattr(self, "_canvas_window"):
            return
        
        canvas = self._canvas
        canvas.update_idletasks()
        
        # 获取画布实际宽度
        canvas_width = canvas.winfo_width()
        if canvas_width <= 1:  # 画布尚未初始化
            return
        
        # 内容宽度完全铺满画布, 消除左右两侧的空白区域
        content_width = canvas_width
        
        # 设置内容宽度
        canvas.itemconfigure(self._canvas_window, width=content_width)
        
        # 内容从画布最左侧开始, 完全填充可视区域
        center_x = 0
        
        # 获取当前滚动位置，以便在更新后恢复
        try:
            current_scroll = canvas.yview()
        except:
            current_scroll = (0.0, 1.0)
        
        # 关键修复：确保Canvas窗口的y坐标始终为0
        # 如果y坐标不是0，内容会飘到视口外
        # 滚动应该通过Canvas的yview实现，而不是移动Canvas窗口的位置
        canvas.coords(self._canvas_window, center_x, 0)
        
        # 更新滚动区域（必须在设置坐标之后）
        canvas.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))
        
        # 恢复之前的滚动位置
        try:
            canvas.yview_moveto(current_scroll[0])
        except:
            pass

    def _on_window_configure(self, event):
        """当窗口大小变化时（包括最大化/还原），更新Canvas内容位置"""
        # 只处理根窗口的配置事件
        if event.widget != self.root:
            return
        
        # 延迟更新，确保窗口大小已经稳定
        # 这会确保Canvas窗口的y坐标始终为0，防止内容飘到视口外
        self.root.after_idle(self._update_content_center)

    def _on_mousewheel(self, event):
        """鼠标滚轮垂直滚动"""
        if not hasattr(self, "_canvas"):
            return
        # Windows 上 event.delta 通常为 120 的倍数
        delta = int(-1 * (event.delta / 120))
        self._canvas.yview_scroll(delta, "units")

    def _create_widgets(self):
        """创建界面控件"""
        # ===== 可滚动主容器 =====
        container = ttk_bs.Frame(self.root)
        container.pack(fill=BOTH, expand=True)

        # 使用 Canvas + Scrollbar 实现垂直滚动
        # 设置与主题一致的背景色, 避免内容未铺满时露出灰色区域
        try:
            _theme_bg = ttk_bs.Style().colors.bg
        except Exception:
            _theme_bg = "#F8F9FA"
        canvas = tk.Canvas(container, highlightthickness=0, bg=_theme_bg)
        v_scrollbar = ttk_bs.Scrollbar(
            container, orient="vertical", command=canvas.yview
        )
        canvas.configure(yscrollcommand=v_scrollbar.set)

        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=BOTH, expand=True)

        self._canvas = canvas

        # 真正放控件的主 Frame, 嵌入到 Canvas 中
        main_frame = ttk_bs.Frame(canvas, padding=20)
        self._main_frame = main_frame
        self._canvas_window = canvas.create_window(
            (0, 0), window=main_frame, anchor="nw"
        )

        # 内容尺寸变化时更新滚动区域和居中位置
        main_frame.bind("<Configure>", self._on_scrollable_frame_configure)
        
        # 画布大小变化时也更新居中位置
        canvas.bind("<Configure>", self._on_canvas_configure)
        
        # 绑定窗口大小变化事件，确保最大化/还原时正确更新
        self.root.bind("<Configure>", self._on_window_configure)

        # 绑定鼠标滚轮滚动
        canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        # 标题
        title_label = ttk_bs.Label(
            main_frame,
            text="HugoAura 安装器\n增强版",
            font=("Microsoft YaHei UI", 20, "bold"),
            bootstyle=PRIMARY,
            justify="center",
        )
        title_label.pack(pady=(0, 10))

        # 权限状态显示
        self._create_permission_status(main_frame)

        # 版本选择区域
        self._create_version_section(main_frame)

        # 安装目录选择区域
        self._create_directory_section(main_frame)

        # 进度显示区域
        self._create_progress_section(main_frame)

        # 按钮区域
        self._create_button_section(main_frame)

        # 初始时根据内容自适应窗口大小, 确保打开即可完整展示全部内容
        self.root.after(100, self._handle_frame_resize)

    def _create_permission_status(self, parent):
        """创建权限状态显示区域"""
        # 检查管理员权限
        is_admin = self._check_admin_privileges()

        status_frame = ttk_bs.Frame(parent)
        status_frame.pack(fill=X, pady=(0, 15))

        # 权限图标和文本
        if is_admin:
            status_text = "✅ 已获得管理员权限"
            status_style = SUCCESS
        else:  # 理论上来说这种场景不会被触发
            status_text = "⚠ 需要管理员权限"
            status_style = WARNING

        status_label = ttk_bs.Label(
            status_frame,
            text=status_text,
            font=("Microsoft YaHei UI", 10),
            bootstyle=status_style,
        )
        status_label.pack()

    def _check_admin_privileges(self):
        """检查是否有管理员权限"""
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False

    def _create_version_section(self, parent):
        """创建版本选择区域"""
        # 版本选择框架
        version_frame = ttk_bs.LabelFrame(
            parent, text="版本选择", padding=15, bootstyle=INFO
        )
        version_frame.pack(fill=X, pady=(0, 15))
        self.version_frame = version_frame

        # 版本类型选择标题和刷新按钮
        type_header_frame = ttk_bs.Frame(version_frame)
        type_header_frame.pack(fill=X, pady=(0, 5))

        type_label = ttk_bs.Label(
            type_header_frame,
            text="版本类型：",
            font=("Microsoft YaHei UI", 10, "bold"),
            bootstyle=PRIMARY,
        )
        type_label.pack(side=LEFT)

        # 刷新版本信息按钮
        refresh_btn = ttk_bs.Button(
            type_header_frame,
            text="🔄 刷新版本",
            command=self._refresh_versions,
            bootstyle=(INFO, "outline"),
            width=12,
        )
        refresh_btn.pack(side=RIGHT)

        # 版本类型选项
        version_types = [
            ("release", "发行版"),
            ("prerelease", "预发行版"),
            ("ci", "CI 版"),
            ("custom_version", "自定义版本"),
            ("custom_path", "本地文件"),
        ]

        for value, text in version_types:
            radio = ttk_bs.Radiobutton(
                version_frame,
                text=text,
                variable=self.version_var,
                value=value,
                command=self._update_version_inputs,
                bootstyle=PRIMARY,
                takefocus=False,
            )
            radio.pack(anchor=W, pady=2, padx=(20, 0))

        # 具体版本选择框架
        self.specific_version_frame = ttk_bs.LabelFrame(
            version_frame, text="具体版本", padding=10, bootstyle=SECONDARY
        )

        # 版本选择框架 (将动态创建)
        self.release_frame = ttk_bs.Frame(self.specific_version_frame)
        self.prerelease_frame = ttk_bs.Frame(self.specific_version_frame)
        self.ci_frame = ttk_bs.Frame(self.specific_version_frame)

        # 自定义版本输入框
        self.custom_version_frame = ttk_bs.Frame(version_frame)
        ttk_bs.Label(self.custom_version_frame, text="版本号:").pack(side=LEFT)
        self.custom_version_entry = ttk_bs.Entry(
            self.custom_version_frame, textvariable=self.custom_version_var, width=20
        )
        self.custom_version_entry.pack(side=LEFT, padx=(10, 0))

        # 自定义文件路径
        self.custom_path_frame = ttk_bs.Frame(version_frame)
        ttk_bs.Label(self.custom_path_frame, text="文件夹路径:").pack(side=LEFT)
        self.custom_path_entry = ttk_bs.Entry(
            self.custom_path_frame, textvariable=self.custom_path_var, width=25
        )
        self.custom_path_entry.pack(side=LEFT, padx=(10, 5))

        self.browse_file_btn = ttk_bs.Button(
            self.custom_path_frame,
            text="浏览",
            command=self._browse_file,
            bootstyle=OUTLINE,
        )
        self.browse_file_btn.pack(side=LEFT)

    def _create_directory_section(self, parent):
        """创建安装目录选择区域"""
        directory_frame = ttk_bs.LabelFrame(
            parent, text="安装目录 (可选)", padding=15, bootstyle=INFO
        )
        directory_frame.pack(fill=X, pady=(0, 15))

        dir_input_frame = ttk_bs.Frame(directory_frame)
        dir_input_frame.pack(fill=X)

        ttk_bs.Label(dir_input_frame, text="目录路径:").pack(side=LEFT)
        self.directory_entry = ttk_bs.Entry(
            dir_input_frame, textvariable=self.install_directory_var, width=40
        )
        self.directory_entry.pack(side=LEFT, padx=(10, 5))

        self.browse_dir_btn = ttk_bs.Button(
            dir_input_frame,
            text="浏览",
            command=self._browse_directory,
            bootstyle=OUTLINE,
        )
        self.browse_dir_btn.pack(side=LEFT)

        # 提示文本
        hint_label = ttk_bs.Label(
            directory_frame,
            text="留空则自动检测希沃管家安装目录",
            font=("Microsoft YaHei UI", 9),
            bootstyle=(SECONDARY, ITALIC),
        )
        hint_label.pack(anchor=W, pady=(5, 0))

    def _create_progress_section(self, parent):
        """创建进度显示区域"""
        progress_frame = ttk_bs.LabelFrame(
            parent, text="安装进度", padding=15, bootstyle=INFO
        )
        progress_frame.pack(fill=X, pady=(0, 15))

        # 状态标签 + 百分比
        progress_header = ttk_bs.Frame(progress_frame)
        progress_header.pack(fill=X, pady=(0, 5))

        self.status_label = ttk_bs.Label(
            progress_header,
            textvariable=self.status_var,
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        self.status_label.pack(side=LEFT, anchor=W)

        self.percent_label = ttk_bs.Label(
            progress_header,
            text="0%",
            font=("Microsoft YaHei UI", 10, "bold"),
            bootstyle=INFO,
        )
        self.percent_label.pack(side=RIGHT, anchor=E)

        # 进度条
        self.progress_bar = ttk_bs.Progressbar(
            progress_frame,
            variable=self.progress_var,
            length=400,
            mode="determinate",
            bootstyle="INFO-striped",
        )
        self.progress_bar.pack(fill=X, pady=(0, 5))

        # 当前步骤
        self.step_label = ttk_bs.Label(
            progress_frame,
            textvariable=self.step_var,
            font=("Microsoft YaHei UI", 9),
            bootstyle=SECONDARY,
        )
        self.step_label.pack(anchor=W)

    def _create_button_section(self, parent):
        """创建按钮区域"""
        button_frame = ttk_bs.Frame(parent)
        button_frame.pack(pady=(10, 0))

        # 安装按钮 (主操作, 实色突出)
        self.install_btn = ttk_bs.Button(
            button_frame,
            text="开始安装",
            command=self._on_install_click,
            bootstyle=INFO,
            width=14,
        )
        self.install_btn.pack(side=LEFT, padx=(0, 10))

        # 一键更新按钮 (默认隐藏, 仅在检测到可用更新时显示)
        self.update_btn = ttk_bs.Button(
            button_frame,
            text="一键更新",
            command=self._on_update_click,
            bootstyle=(SUCCESS, "outline"),
            width=14,
        )

        # 卸载按钮
        self.uninstall_btn = ttk_bs.Button(
            button_frame,
            text="开始卸载",
            command=self._on_uninstall_click,
            bootstyle=(WARNING, "outline"),
            width=15,
        )
        self.uninstall_btn.pack(side=LEFT, padx=(0, 10))

        # 取消按钮
        self.cancel_btn = ttk_bs.Button(
            button_frame,
            text="取消",
            command=self._on_cancel_click,
            bootstyle=(DANGER, "outline"),
            width=14,
            state=DISABLED,
        )
        self.cancel_btn.pack(side=LEFT)

        about_btn_frame = ttk_bs.Frame(parent)
        about_btn_frame.pack(pady=(8, 0))

        # 关于按钮
        about_btn = ttk_bs.Button(
            about_btn_frame,
            text="关于",
            command=self._show_about,
            bootstyle=(SECONDARY, "link"),
            width=14,
        )
        about_btn.pack(side=BOTTOM)

    def _update_version_inputs(self):
        """更新版本输入控件状态"""
        version_type = self.version_var.get()

        # 隐藏所有具体版本选择框架
        self.specific_version_frame.pack_forget()
        self.release_frame.pack_forget()
        self.prerelease_frame.pack_forget()
        self.ci_frame.pack_forget()
        self.custom_version_frame.pack_forget()
        self.custom_path_frame.pack_forget()

        if version_type == "release":
            # 显示发行版选择
            releases = self.versions_data.get("releases", [])
            if releases:
                self.specific_version_frame.pack(fill=X, pady=(10, 0))
                self.release_frame.pack(fill=X)
                # 设置默认选择
                if (
                    not self.specific_version_var.get()
                    or not self._is_valid_version_for_type("release")
                ):
                    self.specific_version_var.set(releases[0]["tag"])

        elif version_type == "prerelease":
            # 显示预发行版选择
            prereleases = self.versions_data.get("prereleases", [])
            if prereleases:
                self.specific_version_frame.pack(fill=X, pady=(10, 0))
                self.prerelease_frame.pack(fill=X)
                # 设置默认选择
                if (
                    not self.specific_version_var.get()
                    or not self._is_valid_version_for_type("prerelease")
                ):
                    self.specific_version_var.set(prereleases[0]["tag"])

        elif version_type == "ci":
            # 显示自动构建版选择
            ci_builds = self.versions_data.get("ci_builds", [])
            if ci_builds:
                self.specific_version_frame.pack(fill=X, pady=(10, 0))
                self.ci_frame.pack(fill=X)
                # 设置默认选择
                if (
                    not self.specific_version_var.get()
                    or not self._is_valid_version_for_type("ci")
                ):
                    self.specific_version_var.set(ci_builds[0]["tag"])

        elif version_type == "custom_version":
            # 显示自定义版本输入
            self.custom_version_entry.config(state=NORMAL)
            self.custom_version_frame.pack(fill=X, pady=(10, 0))

        elif version_type == "custom_path":
            # 显示自定义文件路径选择
            self.custom_path_entry.config(state=NORMAL)
            self.browse_file_btn.config(state=NORMAL)
            self.custom_path_frame.pack(fill=X, pady=(10, 0))

        # 禁用其他输入控件
        if version_type != "custom_version":
            self.custom_version_entry.config(state=DISABLED)
        if version_type != "custom_path":
            self.custom_path_entry.config(state=DISABLED)
            self.browse_file_btn.config(state=DISABLED)

        self.root.after(
            50, # Ensure comp upd finished
            lambda: self._handle_frame_resize(
                self.version_frame.winfo_height() if self.version_frame else 300
            ),
        )

    def _browse_file(self):
        """选择文件夹"""
        filename = filedialog.askdirectory(
            title="选择 HugoAura 资源文件所在文件夹",
        )
        if filename:
            self.custom_path_var.set(filename)

    def _browse_directory(self):
        """浏览目录"""
        directory = filedialog.askdirectory(title="选择安装目录")
        if directory:
            self.install_directory_var.set(directory)

    def _on_install_click(self):
        """安装按钮点击事件"""
        if self.install_callback:
            version_type = self.version_var.get()

            # 根据版本类型确定最终的版本值
            if version_type in ["release", "prerelease", "ci"]:
                # 使用具体选择的版本
                final_version = self.specific_version_var.get()
            elif version_type == "custom_version":
                # 使用自定义版本号
                final_version = self.custom_version_var.get()
            else:
                # 其他情况使用版本类型
                final_version = version_type

            # 收集安装选项
            options = {
                "version": final_version,
                "version_type": version_type,  # 保留版本类型信息
                "custom_version": self.custom_version_var.get(),
                "custom_path": self.custom_path_var.get(),
                "install_directory": self.install_directory_var.get(),
                "non_interactive": True,
            }
            self.install_callback(options)

    def _on_update_click(self):
        """一键更新按钮点击事件"""
        if self.update_callback:
            self.update_callback()

    def _on_uninstall_click(self):
        """卸载按钮点击事件"""
        # 询问用户是否删除配置数据
        user_data_choice = self._ask_user_data_action()
        if user_data_choice is None:  # 用户取消
            return

        if self.uninstall_callback:
            # 收集卸载选项
            uninstall_options = {
                "keep_user_data": user_data_choice == "keep",
                "force": False,
                "dry_run": False,
            }
            self.uninstall_callback(uninstall_options)

    def _ask_user_data_action(self):
        """
        弹出配置数据处理选择对话框, 询问卸载时是否删除配置数据

        返回:
            str: "keep" 保留配置数据 / "delete" 删除配置数据 / None 用户取消
        """
        result = {"value": None}

        dialog = ttk_bs.Toplevel(self.root)
        dialog.title("卸载确认")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()  # 模态, 阻止操作主窗口
        dialog.protocol("WM_DELETE_WINDOW", lambda: result.update(value=None) or dialog.destroy())

        container = ttk_bs.Frame(dialog, padding=20)
        container.pack(fill=BOTH, expand=True)

        ttk_bs.Label(
            container,
            text="确认卸载 HugoAura",
            font=("Microsoft YaHei UI", 14, "bold"),
            bootstyle=PRIMARY,
        ).pack(pady=(0, 8))

        ttk_bs.Label(
            container,
            text="卸载后希沃管家将恢复到原始状态, 此操作不可逆。\n请选择是否同时删除 HugoAura 的配置数据:",
            font=("Microsoft YaHei UI", 10),
        ).pack(anchor=W, pady=(0, 10))

        # 保留配置数据说明
        keep_frame = ttk_bs.LabelFrame(
            container, text="保留配置数据", padding=10, bootstyle=SUCCESS
        )
        keep_frame.pack(fill=X, pady=(0, 8))
        ttk_bs.Label(
            keep_frame,
            text="配置文件、用户偏好设置及本地存储数据将完整保留,\n卸载后重新安装可恢复之前的配置。",
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor=W)

        # 删除配置数据说明
        delete_frame = ttk_bs.LabelFrame(
            container, text="删除配置数据", padding=10, bootstyle=DANGER
        )
        delete_frame.pack(fill=X, pady=(0, 14))
        ttk_bs.Label(
            delete_frame,
            text="所有配置文件、用户偏好设置及本地存储数据将被彻底清除,\n卸载后将无法恢复。",
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor=W)

        # 按钮
        button_frame = ttk_bs.Frame(container)
        button_frame.pack(fill=X)

        def choose(value):
            result["value"] = value
            dialog.destroy()

        ttk_bs.Button(
            button_frame,
            text="保留配置数据",
            command=lambda: choose("keep"),
            bootstyle=SUCCESS,
            width=14,
        ).pack(side=LEFT, padx=(0, 10))

        ttk_bs.Button(
            button_frame,
            text="删除配置数据",
            command=lambda: choose("delete"),
            bootstyle=(DANGER, "outline"),
            width=14,
        ).pack(side=LEFT, padx=(0, 10))

        ttk_bs.Button(
            button_frame,
            text="取消",
            command=lambda: choose(None),
            bootstyle=SECONDARY,
            width=10,
        ).pack(side=LEFT)

        # 将对话框居中显示在主窗口上方
        dialog.update_idletasks()
        parent_x = self.root.winfo_rootx()
        parent_y = self.root.winfo_rooty()
        parent_w = self.root.winfo_width()
        parent_h = self.root.winfo_height()
        dlg_w = dialog.winfo_reqwidth()
        dlg_h = dialog.winfo_reqheight()
        dialog.geometry(
            f"+{max(parent_x + (parent_w - dlg_w) // 2, 0)}"
            f"+{max(parent_y + (parent_h - dlg_h) // 2, 0)}"
        )

        dialog.wait_window()
        return result["value"]

    def _on_cancel_click(self):
        """取消按钮点击事件"""
        if self.cancel_callback:
            self.cancel_callback()

    def _show_about(self):
        """显示关于对话框"""
        about_text = f"""HugoAura-Install {__appVer__}

这是一个用于安装和管理 HugoAura 的工具。
HugoAura 是针对希沃设备的增强工具。

主要功能:
• 一键安装 HugoAura
• 一键更新到最新版
• 智能检测希沃管家
• 自动备份原始文件  
• 一键完全卸载
• 多版本支持
• 备份机制
• 完整的卸载恢复

作者: HugoAura Devs
GUI 基于: ttkbootstrap & tkinter
GitHub 主仓库: blingbling-bow/HugoAura-Enhanced
Install 主仓库: blingbling-bow/HugoAura-Install"""

        messagebox.showinfo("关于 HugoAura-Install", about_text)

    def set_install_callback(self, callback: Callable):
        """设置安装回调函数"""
        self.install_callback = callback

    def set_update_callback(self, callback: Callable):
        """设置一键更新回调函数"""
        self.update_callback = callback

    def set_cancel_callback(self, callback: Callable):
        """设置取消回调函数"""
        self.cancel_callback = callback

    def set_uninstall_callback(self, callback: Callable):
        """设置卸载回调函数"""
        self.uninstall_callback = callback

    def update_progress(self, progress: int, step: str = "", status: str | None = None):
        """更新进度"""
        self.progress_var.set(progress)
        if hasattr(self, "percent_label"):
            self.percent_label.config(text=f"{progress}%")
        if step:
            self.step_var.set(step)
        if status:
            match status:
                case "success":
                    self.progress_bar.config(bootstyle="SUCCESS-striped")
                case "info":
                    self.progress_bar.config(bootstyle="INFO-striped")
                case "error":
                    self.progress_bar.config(bootstyle="DANGER-striped")
                case "warn":
                    self.progress_bar.config(bootstyle="WARNING-striped")
                case _:
                    pass
        self.root.update_idletasks()

    def update_status(self, status: str):
        """更新状态"""
        self.status_var.set(status)
        self.root.update_idletasks()

    def set_installing_state(self, installing: bool, operation: str = "安装"):
        """设置安装/更新/卸载状态"""
        self.is_installing = installing
        if installing:
            if operation == "卸载":
                self.install_btn.config(state=DISABLED)
                self.update_btn.config(state=DISABLED)
                self.uninstall_btn.config(state=DISABLED, text="卸载中...")
            elif operation == "更新":
                self.install_btn.config(state=DISABLED)
                self.update_btn.config(state=DISABLED, text="更新中...")
                self.uninstall_btn.config(state=DISABLED)
            else:
                self.install_btn.config(state=DISABLED, text="安装中...")
                self.update_btn.config(state=DISABLED)
                self.uninstall_btn.config(state=DISABLED)
            self.cancel_btn.config(state=NORMAL)
            # 禁用刷新按钮
            self._set_refresh_state(False)  # 确保刷新按钮可用状态正确
            for widget in self.root.winfo_children():
                self._disable_refresh_button_recursive(widget)
            # 禁用输入控件
            for widget in [
                self.custom_version_entry,
                self.custom_path_entry,
                self.directory_entry,
                self.browse_file_btn,
                self.browse_dir_btn,
            ]:
                widget.config(state=DISABLED)
        else:
            self.install_btn.config(state=NORMAL, text="开始安装")
            self.update_btn.config(state=NORMAL, text="一键更新")
            self.uninstall_btn.config(state=NORMAL, text="开始卸载")
            self.cancel_btn.config(state=DISABLED)
            # 恢复刷新按钮
            for widget in self.root.winfo_children():
                self._enable_refresh_button_recursive(widget)
            # 恢复输入控件状态
            self._update_version_inputs()
            self.directory_entry.config(state=NORMAL)
            self.browse_dir_btn.config(state=NORMAL)

    def set_install_button_state(self, enabled: bool, text: str = "开始安装"):
        """设置安装按钮状态"""
        if enabled:
            self.install_btn.config(state=NORMAL, text=text)
        else:
            self.install_btn.config(state=DISABLED, text=text)

    def set_update_button_state(self, enabled: bool, text: str = "一键更新"):
        """设置一键更新按钮状态"""
        if enabled:
            self.update_btn.config(state=NORMAL, text=text)
        else:
            self.update_btn.config(state=DISABLED, text=text)

    def set_update_button_visible(self, visible: bool):
        """显示或隐藏一键更新按钮"""
        if visible:
            # 插入到安装按钮和卸载按钮之间, 保持原有布局顺序
            self.update_btn.pack(
                side=LEFT, padx=(0, 10), before=self.uninstall_btn
            )
        else:
            self.update_btn.pack_forget()

    def set_install_button_visible(self, visible: bool):
        """显示或隐藏安装按钮"""
        if visible:
            # 安装按钮始终位于最左侧; 依据更新按钮当前是否可见决定插入位置
            if self.update_btn.winfo_manager() == "pack":
                self.install_btn.pack(
                    side=LEFT, padx=(0, 10), before=self.update_btn
                )
            else:
                self.install_btn.pack(
                    side=LEFT, padx=(0, 10), before=self.uninstall_btn
                )
        else:
            self.install_btn.pack_forget()

    def show_message(self, title: str, message: str, msg_type: str = "info"):
        """显示消息对话框"""
        if msg_type == "error":
            messagebox.showerror(title, message)
        elif msg_type == "warning":
            messagebox.showwarning(title, message)
        else:
            messagebox.showinfo(title, message)

    def run(self):
        """运行主窗口"""
        self.root.mainloop()

    def destroy(self):
        """销毁窗口"""
        self.root.destroy()
