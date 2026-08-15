import hashlib
import ipaddress
import socket
import requests
import time
import zipfile
import shutil
import os
from pathlib import Path
from urllib.parse import urlparse
from loguru import logger as log
from config.config import (
    BASE_DOWNLOAD_URLS,
    AURA_FILENAME,
    CORE_FILENAME,
    TEMP_INSTALL_DIR,
    GITHUB_API_URL,
)
import typeDefs.lifecycle
import lifecycle as lifecycleMgr
import asyncio
import aiohttp
from typing import List, Tuple


desiredTag = None


def _compute_sha256(path: Path) -> str:
    """计算文件 SHA256 十六进制摘要"""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_release_asset_digests(tag_name: str) -> dict:
    """获取指定 release 资源的 SHA256 摘要。

    GitHub release asset API 返回 digest 字段 (格式 sha256:<hex>)。
    这是 best-effort: 失败或字段缺失时返回空字典, 不阻断安装, 仅跳过校验。
    """
    url = f"{GITHUB_API_URL}/tags/{tag_name}"
    if not _is_safe_url(url):
        log.warning(f"跳过 GitHub API 摘要获取 (非法 URL): {url}")
        return {}

    headers = {"User-Agent": "HugoAura-Install", "Accept": "application/vnd.github+json"}
    try:
        resp = requests.get(url, timeout=30, headers=headers)
        resp.raise_for_status()
        release = resp.json()
    except Exception as e:
        log.warning(f"获取 release 资源摘要失败, 跳过 SHA256 校验: {e}")
        return {}

    digests = {}
    for asset in release.get("assets", []):
        name = asset.get("name")
        digest = asset.get("digest") or ""
        if name and digest.startswith("sha256:"):
            digests[name] = digest[len("sha256:"):]
    return digests


def _is_safe_url(url: str) -> bool:
    """校验下载 URL, 仅允许 http/https 且所有解析结果均为公网地址。

    采用“任一地址不安全即拒绝”的严格策略, 防止 DNS rebinding:
    若某个域名同时解析出公网和内网地址, 应视为不可信, 而不是放行。
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme not in ("http", "https"):
        return False

    host = parsed.hostname
    if not host:
        return False

    try:
        for info in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(info[4][0])
            if (
                ip.is_loopback
                or ip.is_private
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            ):
                return False
    except Exception:
        return False

    return True


def download_file(
    url: str,
    dest_folder: str,
    filename: str,
    expected_sha256: str | None = None,
) -> Path | str | None:
    dest_path = Path(dest_folder) / filename
    log.info(f"正在从 {url} 下载 {filename}, 目标目录: {dest_path}")

    if not _is_safe_url(url):
        log.error(f"拒绝下载非法 URL (仅允许 http/https 公网地址): {url}")
        return None

    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        downloadHeaders = {
            "Accept-Encoding": "",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        }
        with requests.get(url, stream=True, timeout=60, headers=downloadHeaders) as r:
            r.raise_for_status()
            total_size = int(r.headers.get("content-length", 0))
            log.info(
                f"文件大小: {total_size / 1024 / 1024:.2f} MB"
                if total_size
                else "文件大小: 未知"
            )

            with open(dest_path, "wb") as f:
                downloaded_size = 0
                chunk_size = 8192
                for chunk in r.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)

                        callbackFuncName = (
                            typeDefs.lifecycle.GLOBAL_CALLBACKS.REPORT_DOWNLOAD_PROGRESS.value
                        )
                        if callbackFuncName in lifecycleMgr.callbacks.keys():
                            if lifecycleMgr.callbacks[callbackFuncName]:
                                lifecycleMgr.callbacks[callbackFuncName](
                                    downloaded_size, total_size, f.name.split("\\")[-1]
                                )  # type: ignore

        log.success(f"文件 {filename} 下载成功。")
        # 完整性校验: 当服务器提供 content-length 时, 校验实际下载字节数
        if total_size > 0 and downloaded_size != total_size:
            log.error(
                f"文件 {filename} 下载不完整: 预期 {total_size} 字节, 实际 {downloaded_size} 字节"
            )
            if dest_path.exists():
                os.remove(dest_path)
            return None

        # 内容完整性校验: 若提供了权威摘要, 对比下载文件的实际 SHA256
        if expected_sha256:
            actual_sha256 = _compute_sha256(dest_path)
            if actual_sha256.lower() != expected_sha256.lower():
                log.error(
                    f"文件 {filename} SHA256 校验失败: 预期 {expected_sha256}, 实际 {actual_sha256}"
                )
                if dest_path.exists():
                    os.remove(dest_path)
                return None
            log.success(f"文件 {filename} SHA256 校验通过")

        return dest_path
    except requests.exceptions.RequestException as e:
        log.error(f"下载文件 {filename} 时发生网络错误: {e}")
        if dest_path.exists():
            os.remove(dest_path)
        return None
    except Exception as e:
        if "INSTALLATION_CANCELLED" in str(e):
            return "DL_CANCEL"
        log.error(f"写入文件 {filename} 时发生意外错误: {e}")
        if dest_path.exists():
            os.remove(dest_path)
        return None


async def test_download_source_speed(
    base_url: str, test_filename: str = None
) -> Tuple[str, float, bool]:
    test_url = f"{base_url}/{desiredTag}/{AURA_FILENAME}" if test_filename else base_url

    if not _is_safe_url(test_url):
        log.warning(f"跳过非法测速 URL: {test_url}")
        return (base_url, float("inf"), False)

    try:
        start_time = time.time()

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10)
        ) as session:
            async with session.head(test_url) as response:
                if response.status == 200:
                    response_time = time.time() - start_time
                    return (base_url, response_time, True)
                else:
                    return (base_url, float("inf"), False)

    except Exception as e:
        log.warning(f"测速失败 {base_url}: {e}")
        return (base_url, float("inf"), False)


async def benchmark_download_sources(tag_name: str) -> List[str]:
    log.info("正在测试下载源速度...")

    tasks = [
        test_download_source_speed(url, AURA_FILENAME) for url in BASE_DOWNLOAD_URLS
    ]
    results = await asyncio.gather(*tasks)

    # 筛选可用源并按响应时间排序
    available_sources = [(url, time) for url, time, available in results if available]
    available_sources.sort(key=lambda x: x[1])

    sorted_urls = [url for url, _ in available_sources]

    # 输出测速结果
    for url, response_time in available_sources[:3]:  # 只输出前 3 个最快的
        log.info(
            f"下载源 {url.split('//')[1].split('/')[0]} 响应时间: {response_time:.2f}s"
        )

    return sorted_urls if sorted_urls else BASE_DOWNLOAD_URLS


def download_file_multi_sources(
    filename: str,
    dest_folder: str,
    use_speed_optimization: bool = True,
    expected_sha256: str | None = None,
) -> Path | None:
    """
    尝试从多个下载源下载文件
    """
    global desiredTag

    download_urls = BASE_DOWNLOAD_URLS

    if use_speed_optimization and desiredTag:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            optimized_urls = loop.run_until_complete(
                benchmark_download_sources(desiredTag)
            )
            loop.close()

            if optimized_urls:
                download_urls = optimized_urls
                log.info("测速完成, 将按测速顺序进行下载")
        except Exception as e:
            log.warning(f"测速失败, 使用默认顺序: {e}")

    for base_url in download_urls:
        url = f"{base_url}/{desiredTag}/{filename}"
        result = download_file(url, dest_folder, filename, expected_sha256=expected_sha256)
        if result == "DL_CANCEL":
            log.warning("下载已取消")
            return None
        elif result:
            return result  # type: ignore
        else:
            log.warning(f"从 {url} 下载失败, 尝试下一个源...")
    log.critical(f"所有下载源均失败, 无法下载 {filename}")
    return None


def unzip_file(zip_path: Path, extract_to: Path) -> bool:
    log.info(f"正在解压 {zip_path.name}, 目标目录: {extract_to}")
    try:
        extract_to.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_to)
        log.success(f"解压 {zip_path.name} 成功。")
        return True
    except zipfile.BadZipFile:
        log.error(f"解压时发生错误: {zip_path.name} 不是一个有效的 ZIP 文件。")
        return False
    except Exception as e:
        log.error(f"解压时发生错误: 文件名称: {zip_path.name} | 错误: {e}")
        return False


def download_release_files(tagName) -> tuple[Path | None, Path | None]:
    log.info(f"准备下载 HugoAura 资源文件...")

    global desiredTag
    desiredTag = tagName
    temp_dir = Path(TEMP_INSTALL_DIR)
    if temp_dir.exists():
        log.info(f"正在清理旧的临时文件夹: {temp_dir}")
        try:
            shutil.rmtree(temp_dir)
        except OSError as e:
            log.error(f"清理失败 {temp_dir}, 请确保当前用户有 %TEMP% 的写入权限: {e}")
            return None, None
    try:
        temp_dir.mkdir(parents=True, exist_ok=True)
        log.info(f"成功创建临时文件夹: {temp_dir}")
    except OSError as e:
        log.error(
            f"未能创建临时文件夹 {temp_dir}, 错误信息: {e} | 请确保当前用户有 %TEMP% 的写入权限"
        )
        return None, None

    downloaded_core_path = None
    downloaded_zip_path = None

    # 获取权威 SHA256 摘要; 失败时为空字典, 走原有仅字节数校验逻辑
    digests = fetch_release_asset_digests(tagName)
    core_sha = digests.get(CORE_FILENAME)
    aura_sha = digests.get(AURA_FILENAME)

    if core_sha and aura_sha:
        log.info("已获取资源 SHA256 摘要, 下载后启用内容校验")
    else:
        log.warning("未获取到资源 SHA256 摘要, 下载后仅校验字节数")

    downloaded_core_path = download_file_multi_sources(
        CORE_FILENAME, str(temp_dir), expected_sha256=core_sha
    )
    if not downloaded_core_path:
        log.critical("下载 core.zip 时发生错误, 安装进程终止。")
        return None, None

    downloaded_zip_path = download_file_multi_sources(
        AURA_FILENAME, str(temp_dir), expected_sha256=aura_sha
    )
    if not downloaded_zip_path:
        log.critical("下载 aura.zip 时发生错误, 安装进程终止。")
        return downloaded_core_path, None

    return downloaded_core_path, downloaded_zip_path
