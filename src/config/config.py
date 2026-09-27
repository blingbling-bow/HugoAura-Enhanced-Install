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
# 已于 2026-09 用真实 release 资产 (aura.zip) 两轮实测筛选:
# 剔除失效源 (gh.llkk.cc 超时 / github.dpik.top 失效 / ghfast.top 限速严重
# / gh.acmsz.top 403 / cfgh.ikgy.top 403 / gh.ddlc.top 429 / github.geekery.cn 极慢),
# 并补充新可用源; 顺序仅作测速失败时的回退顺序, 正常使用前会自动测速排序
BASE_DOWNLOAD_URLS = [
    f"https://git.yylx.win/https://github.com/{GITHUB_OWNER}/{GITHUB_DL_REPO}/releases/download",
    f"https://github.chenc.dev/https://github.com/{GITHUB_OWNER}/{GITHUB_DL_REPO}/releases/download",
    f"https://gh.07150721.xyz/https://github.com/{GITHUB_OWNER}/{GITHUB_DL_REPO}/releases/download",
    f"https://cdn.gh-proxy.org/https://github.com/{GITHUB_OWNER}/{GITHUB_DL_REPO}/releases/download",
    f"https://axisnow.gh-proxy.org/https://github.com/{GITHUB_OWNER}/{GITHUB_DL_REPO}/releases/download",
    f"https://gh-proxy.org/https://github.com/{GITHUB_OWNER}/{GITHUB_DL_REPO}/releases/download",
    f"https://githubdog.com/https://github.com/{GITHUB_OWNER}/{GITHUB_DL_REPO}/releases/download",
    f"https://js.jiangss.shop/https://github.com/{GITHUB_OWNER}/{GITHUB_DL_REPO}/releases/download",
    f"https://gh.927223.xyz/https://github.com/{GITHUB_OWNER}/{GITHUB_DL_REPO}/releases/download",
    f"https://ghproxy.felicity.land/https://github.com/{GITHUB_OWNER}/{GITHUB_DL_REPO}/releases/download",
    f"https://github.tbap.top/https://github.com/{GITHUB_OWNER}/{GITHUB_DL_REPO}/releases/download",
    f"https://github.com/{GITHUB_OWNER}/{GITHUB_DL_REPO}/releases/download",  # 直连兜底
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
