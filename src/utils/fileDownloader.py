from __future__ import annotations

import hashlib
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
from utils.netguard import is_safe_url as _is_safe_url
from utils.netguard import safe_get
from utils.netguard import safe_get_follow
import typeDefs.lifecycle
import lifecycle as lifecycleMgr
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List


desiredTag = None

# 测速配置
SPEED_TEST_TIMEOUT_SECONDS = 5.0       # 阶段一: 单源健康度/延迟探测超时
SPEED_TEST_CACHE_TTL_SECONDS = 2 * 60 * 60  # 测速结果缓存 2 小时
SPEED_PROBE_COUNT = 5                 # 阶段二: 参与带宽探测的名额
# 阶段二: 每源拉取的字节数 (Range 请求)。
# 流量预算: 摘要 ~50KB + 阶段一 17源×6KB ≈ 100KB + 阶段二 5源×128KB = 640KB
#          + 实际下载 ~0.6MB ≈ 1.3MB (含一次重试余量 < 1.9MB)
SPEED_PROBE_BYTES = 128 * 1024
BANDWIDTH_PROBE_TIMEOUT_SECONDS = 6.0  # 阶段二: 单源带宽探测超时
# 综合排序的预估基准: aura.zip 的近似大小, 用于 "延迟 + 传输时间" 估算
AURA_ESTIMATED_SIZE_BYTES = 560 * 1024
_speed_test_cache: dict = {}           # 进程内缓存: {"order": {tag, timestamp, urls}}


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
        resp = safe_get(url, timeout=30, headers=headers)
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

    # 路径防御: 下载目标必须位于临时下载目录内, 防止路径穿越
    try:
        dest_path.resolve().relative_to(Path(TEMP_INSTALL_DIR).resolve())
    except ValueError:
        log.error(f"拒绝写入临时下载目录之外的路径: {dest_path}")
        return None

    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        downloadHeaders = {
            "Accept-Encoding": "",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        }
        # 受限请求: 校验起始 URL 并手动跟随重定向 (每一跳都重新校验)
        with safe_get_follow(
            url, timeout=60, headers=downloadHeaders, stream=True
        ) as r:
            r.raise_for_status()
            total_size = int(r.headers.get("content-length", 0))
            log.info(
                f"文件大小: {total_size / 1024 / 1024:.2f} MB"
                if total_size
                else "文件大小: 未知"
            )

            # 流式写入用底层 fd 打开 (行为与 open("wb") 一致)
            dest_fd = os.open(
                str(dest_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644
            )
            with os.fdopen(dest_fd, "wb") as f:
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
                                try:
                                    lifecycleMgr.callbacks[callbackFuncName](
                                        downloaded_size, total_size, filename
                                    )  # type: ignore
                                except Exception as cb_err:
                                    # 取消信号必须继续向上抛, 其余回调异常只影响进度展示
                                    if "INSTALLATION_CANCELLED" in str(cb_err):
                                        raise
                                    log.debug(f"进度回调异常 (不影响下载): {cb_err}")

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


def _speed_test_single(
    base_url: str, tag: str, expected_sha256: str | None
) -> tuple[str, float, bool]:
    """单源测速: GET 真实资源小文件 (core.zip, 约 6KB) 并校验 SHA256 内容。

    参考 GitHub Accelerator 扩展的做法: 相比 HEAD 请求, GET 真实文件
    能识别"返回 200 但内容是错误页"的污染源。
    """
    test_url = f"{base_url}/{tag}/{CORE_FILENAME}"
    if not _is_safe_url(test_url):
        log.warning(f"跳过非法测速 URL: {test_url}")
        return (base_url, float("inf"), False)

    start = time.perf_counter()
    try:
        with safe_get_follow(
            test_url,
            timeout=(SPEED_TEST_TIMEOUT_SECONDS, SPEED_TEST_TIMEOUT_SECONDS),
            headers={"User-Agent": "Mozilla/5.0 HugoAura-Install", "Accept-Encoding": "identity"},
        ) as resp:
            resp.raise_for_status()
            data = resp.content
        latency = time.perf_counter() - start

        # 内容验证: 有权威摘要时, 哈希不匹配即判定为污染源
        if expected_sha256 and hashlib.sha256(data).hexdigest().lower() != expected_sha256.lower():
            log.warning(f"测速源 {base_url} 内容校验失败, 判定为不可信源")
            return (base_url, float("inf"), False)

        return (base_url, latency, True)
    except Exception as e:
        log.debug(f"测速失败 {base_url}: {e}")
        return (base_url, float("inf"), False)


def _measure_bandwidth(base_url: str, tag: str) -> float | None:
    """阶段二带宽探测: Range 拉取真实待下载文件 (aura.zip) 的前 128KB。

    延迟快不等于带宽快 (小文件只测到 RTT/TLS 握手); 用实际字节速率排序,
    对 aura.zip 的下载更准。Range 响应为 206, 也能避开部分代理不回
    content-length 的问题。测量失败返回 None (调用方回退延迟排序)。

    速率计算剔除建连耗时 (resp.elapsed = TCP+TLS+服务器处理):
    128KB 样本较短, 不剔除的话建连时间会主导测量, 排名偏向"建连快"
    而非"传输快"。
    """
    url = f"{base_url}/{tag}/{AURA_FILENAME}"
    if not _is_safe_url(url):
        return None

    start = time.perf_counter()
    got = 0
    try:
        with safe_get_follow(
            url,
            timeout=(BANDWIDTH_PROBE_TIMEOUT_SECONDS, BANDWIDTH_PROBE_TIMEOUT_SECONDS),
            headers={
                "User-Agent": "Mozilla/5.0 HugoAura-Install",
                "Accept-Encoding": "identity",
                "Range": f"bytes=0-{SPEED_PROBE_BYTES - 1}",
            },
            stream=True,
        ) as resp:
            if resp.status_code not in (200, 206):
                return None
            ttfb = resp.elapsed.total_seconds()  # 到响应头为止的建连耗时
            for chunk in resp.iter_content(32 * 1024):
                got += len(chunk)
                if got >= SPEED_PROBE_BYTES:
                    break

        total = time.perf_counter() - start
        transfer = max(total - ttfb, 0.0)
        # 退化样本不参与排序: 数据量过小, 或传输时间过短 (除零/抖动)
        if got < SPEED_PROBE_BYTES // 4 or transfer <= 0.05:
            return None
        return got / transfer
    except Exception:
        return None


def benchmark_download_sources(
    tag: str, expected_sha256: str | None = None
) -> List[str]:
    """两阶段并发测速, 返回按质量排序的 URL 列表。

    - 阶段一 (SCREEN): GET 真实小文件 (core.zip) 并验证 SHA256, 筛掉
      死源/限流源/污染源, 记录延迟
    - 阶段二 (RANK): 最快的 5 个源对 aura.zip 做并发 Range 探测,
      按实际带宽排序 (延迟快不代表带宽快)
    - 结果缓存 2 小时, core.zip 与 aura.zip 两次下载共用一次测速
    - 全部失败时保持默认顺序 (官方直连兜底)
    """
    cached = _speed_test_cache.get("order")
    if (
        cached
        and cached.get("tag") == tag
        and time.time() - cached.get("timestamp", 0) < SPEED_TEST_CACHE_TTL_SECONDS
    ):
        log.info("使用缓存的测速结果")
        return cached["urls"]

    log.info(
        f"开始并发测速 ({len(BASE_DOWNLOAD_URLS)} 个源, GET {CORE_FILENAME} 校验内容)..."
    )
    results = {}
    with ThreadPoolExecutor(max_workers=len(BASE_DOWNLOAD_URLS)) as pool:
        futures = {
            pool.submit(_speed_test_single, url, tag, expected_sha256): url
            for url in BASE_DOWNLOAD_URLS
        }
        for fut in as_completed(futures):
            url, latency, ok = fut.result()
            results[url] = (latency, ok)

    verified = sorted((lat, url) for url, (lat, ok) in results.items() if ok)

    # 阶段二: 延迟最快的前几名测真实带宽 (并发, 与阶段一慢尾无重叠必要,
    # 阶段一已全部结算)
    phase2 = [url for _, url in verified[:SPEED_PROBE_COUNT]]
    measured: List[tuple[float, str]] = []
    probed_failed: List[str] = []
    if phase2:
        log.info(f"对延迟最快的 {len(phase2)} 个源进行带宽探测 (Range 拉 {AURA_FILENAME})...")
        with ThreadPoolExecutor(max_workers=len(phase2)) as pool:
            bps_futures = {
                url: pool.submit(_measure_bandwidth, url, tag) for url in phase2
            }
        for url, fut in bps_futures.items():
            bps = fut.result()
            if bps:
                measured.append((bps, url))
            else:
                probed_failed.append(url)

    # 综合排序: 预估下载 aura.zip 的总时间 = 延迟 + 传输时间 (大小/带宽)。
    # 纯带宽排序会漏掉"带宽第一但延迟一般"以外的综合优解;
    # 按预估总时间升序, 带宽快且延迟也不差的源自然排前。
    latency_by_url = {url: lat for lat, url in verified}
    scored = []
    for bps, url in measured:
        latency = latency_by_url.get(url, 1.0)
        est_seconds = latency + AURA_ESTIMATED_SIZE_BYTES / bps
        scored.append((est_seconds, bps, url))
    scored.sort()
    for est, bps, url in scored[:3]:
        log.info(
            f"综合最优: {urlparse(url).hostname} "
            f"带宽 {bps / 1024:.0f} KB/s, 预估下载 {AURA_FILENAME} 约 {est:.1f}s"
        )

    measured_urls = [url for _, _, url in scored]
    probed_set = set(phase2)
    unprobed = [url for _, url in verified if url not in probed_set]

    ordered = measured_urls + unprobed + probed_failed
    for url in BASE_DOWNLOAD_URLS:
        if url not in ordered:
            ordered.append(url)  # 阶段一失败/污染源按默认顺序垫底

    if verified:
        best_host = urlparse(ordered[0]).hostname
        log.info(
            f"测速完成, 最优源: {best_host}, "
            f"阶段一可用 {len(verified)}/{len(BASE_DOWNLOAD_URLS)}"
        )
    else:
        log.warning("所有源测速失败, 保持默认顺序下载")

    _speed_test_cache["order"] = {
        "tag": tag,
        "timestamp": time.time(),
        "urls": ordered,
    }
    return ordered


def download_file_multi_sources(
    filename: str,
    dest_folder: str,
    expected_sha256: str | None = None,
    download_urls: List[str] | None = None,
) -> Path | None:
    """
    尝试从多个下载源下载文件 (按传入的测速排序顺序依次尝试)
    """
    global desiredTag

    for base_url in download_urls or BASE_DOWNLOAD_URLS:
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


def download_release_files(
    tagName, status_callback=None
) -> tuple[Path | None, Path | None]:
    """下载指定 release 的资源文件。

    参数:
        tagName: release 标签
        status_callback: 可选状态回调 (str -> None), 把 "测速中/下载中"
            等阶段提示实时推给界面, 避免测速期间界面停留在旧提示上
            像卡住。
    """

    def emit_status(text: str):
        if status_callback:
            try:
                status_callback(text)
            except Exception as e:
                log.debug(f"状态回调失败 (忽略): {e}")

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
    emit_status("正在获取资源校验信息...")
    digests = fetch_release_asset_digests(tagName)
    core_sha = digests.get(CORE_FILENAME)
    aura_sha = digests.get(AURA_FILENAME)

    if core_sha and aura_sha:
        log.info("已获取资源 SHA256 摘要, 下载后启用内容校验")
    else:
        log.warning("未获取到资源 SHA256 摘要, 下载后仅校验字节数")

    # 一次并发测速 (GET core.zip + 哈希验证), core 与 aura 两次下载共用结果
    emit_status("正在进行下载测速...")
    ordered_urls = benchmark_download_sources(tagName, core_sha)

    emit_status(f"正在下载资源文件 ({CORE_FILENAME})...")
    downloaded_core_path = download_file_multi_sources(
        CORE_FILENAME,
        str(temp_dir),
        expected_sha256=core_sha,
        download_urls=ordered_urls,
    )
    if not downloaded_core_path:
        log.critical("下载 core.zip 时发生错误, 安装进程终止。")
        return None, None

    emit_status(f"正在下载资源文件 ({AURA_FILENAME})...")
    downloaded_zip_path = download_file_multi_sources(
        AURA_FILENAME,
        str(temp_dir),
        expected_sha256=aura_sha,
        download_urls=ordered_urls,
    )
    if not downloaded_zip_path:
        log.critical("下载 aura.zip 时发生错误, 安装进程终止。")
        return downloaded_core_path, None

    return downloaded_core_path, downloaded_zip_path
