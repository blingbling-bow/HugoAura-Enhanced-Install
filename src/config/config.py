import os
import tempfile

# 应用信息
APP_NAME = "HugoAura"
TARGET_PROCESS_NAME = ["SeewoServiceAssistant.exe", "SeewoCore.exe", "SeewoAbility.exe"]

# GitHub 仓库信息
GITHUB_OWNER = "blingbling-bow"
GITHUB_REPO = "HugoAura-Enhanced"
GITHUB_DL_REPO = "HugoAura-Enhanced"

# 文件名
ASAR_FILENAME = "app-patched.asar"
CORE_FILENAME = "core.zip"
AURA_FILENAME = "aura.zip"
TARGET_ASAR_NAME = "app.asar"
EXTRACTED_FOLDER_NAME = "aura"

# 下载 URL 列表
# 于 2026-10-11 用真实 release 资产 (v0.3.0/core.zip) 全量实测筛选:
# 节点池来源为 GitHub Accelerator 扩展的 nodes.json (81 节点) + 原有源,
# 共 85 个候选; 以 "GET 真实文件 + SHA256 内容验证 + 响应延迟" 为标准,
# 剔除 DNS 异常 (githubdog.com / js.jiangss.shop 等)、限流 (429) 和超时源,
# 补入实测延迟 <= 1.8s 的优秀源。顺序仅作测速失败时的回退顺序,
# 正常使用前会自动测速排序 (GET core.zip 校验内容, 结果缓存 2 小时)
BASE_DOWNLOAD_URLS = [
    f"https://cdn.gh-proxy.org/https://github.com/{GITHUB_OWNER}/{GITHUB_DL_REPO}/releases/download",
    f"https://cfgh.ikgy.top/https://github.com/{GITHUB_OWNER}/{GITHUB_DL_REPO}/releases/download",
    f"https://github.chenc.dev/https://github.com/{GITHUB_OWNER}/{GITHUB_DL_REPO}/releases/download",
    f"https://gh.jjj.gv.uy/https://github.com/{GITHUB_OWNER}/{GITHUB_DL_REPO}/releases/download",
    f"https://ghproxy.imciel.com/https://github.com/{GITHUB_OWNER}/{GITHUB_DL_REPO}/releases/download",
    f"https://gh.acmsz.top/https://github.com/{GITHUB_OWNER}/{GITHUB_DL_REPO}/releases/download",
    f"https://gh-proxy.org/https://github.com/{GITHUB_OWNER}/{GITHUB_DL_REPO}/releases/download",
    f"https://v4.gh-proxy.org/https://github.com/{GITHUB_OWNER}/{GITHUB_DL_REPO}/releases/download",
    f"https://axisnow.gh-proxy.org/https://github.com/{GITHUB_OWNER}/{GITHUB_DL_REPO}/releases/download",
    f"https://ghproxy.felicity.land/https://github.com/{GITHUB_OWNER}/{GITHUB_DL_REPO}/releases/download",
    f"https://gg.z321.cc.cd/https://github.com/{GITHUB_OWNER}/{GITHUB_DL_REPO}/releases/download",
    f"https://gh.my-website.ccwu.cc/https://github.com/{GITHUB_OWNER}/{GITHUB_DL_REPO}/releases/download",
    f"https://g.z321.cc.cd/https://github.com/{GITHUB_OWNER}/{GITHUB_DL_REPO}/releases/download",
    f"https://free.cn.eu.org/https://github.com/{GITHUB_OWNER}/{GITHUB_DL_REPO}/releases/download",
    f"https://github.mxw.qzz.io/https://github.com/{GITHUB_OWNER}/{GITHUB_DL_REPO}/releases/download",
    f"https://git.yylx.win/https://github.com/{GITHUB_OWNER}/{GITHUB_DL_REPO}/releases/download",
    f"https://github.com/{GITHUB_OWNER}/{GITHUB_DL_REPO}/releases/download",  # 官方直连兜底
]

# GitHub API URL
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases"

# 目标路径模式
SWASS_PATH_PATTERN = r"C:\\Program Files (x86)\\Seewo\\SeewoService\\SeewoService_*\\SeewoServiceAssistant\\resources"

# 临时目录信息
TEMP_DIR_NAME = "Aura-Install-Temp"
TEMP_INSTALL_DIR = os.path.join(tempfile.gettempdir(), TEMP_DIR_NAME)

# HugoAura 数据路径
HUGOAURA_USER_DATA_DIR = os.path.join(os.path.expanduser("~"), "Documents", "HugoAura")
HUGOAURA_REGISTRY_KEY = r"SOFTWARE\\HugoAura"

# 进程杀死间隔
PROCESS_KILL_INTERVAL_SECONDS = 0.5

# 安装/更新成功后延迟启动希沃管家 (秒); 设为 0 关闭该行为
# 到时先检查进程是否已在运行 (守护可能已自行拉起), 未运行才启动
POST_INSTALL_RESTART_DELAY_SECONDS = 20

# 退出代码释义
EXIT_CODES = {
    0: "安装成功",
    1: "安装失败 (一般错误)",
    2: "权限不足, 需要管理员权限",
    3: "未找到希沃管家安装目录",
    4: "资源文件下载失败",
    5: "资源文件解压失败",
    6: "文件系统操作失败",
    7: "参数错误"
}
