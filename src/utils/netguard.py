"""
网络请求安全防护: 服务端请求 URL 的统一校验入口。

采用域名白名单策略: 仅允许 GitHub 官方域名与 config 中配置的镜像源域名。
相比 IP 黑名单, 白名单不受代理 TUN+Fake-IP 模式影响 (此类模式下 DNS 解析
结果为保留段虚拟地址, IP 校验无法工作); 传输层安全由 HTTPS 证书校验兜底。

重定向采用手动跟随 (safe_get_follow): 每一跳都重新校验目标地址,
比 requests 自动重定向更严格。
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse, urljoin

import requests

from config.config import BASE_DOWNLOAD_URLS

# GitHub 官方域名 (release 资产下载会重定向到 objects.githubusercontent.com)
_FIXED_ALLOWED_HOSTS = {
    "github.com",
    "api.github.com",
    "objects.githubusercontent.com",
    "raw.githubusercontent.com",
    "codeload.github.com",
    "gist.githubusercontent.com",
}

# 代理软件 (Clash/Mihomo 等) TUN+Fake-IP 模式的 DNS 虚拟地址段,
# 对应 RFC 2544 / RFC 4038 的基准测试保留段 (见 is_allowed_redirect_target)。
_FAKE_IP_NETWORKS = (
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("2001:2::/48"),
)

_REDIRECT_STATUSES = (301, 302, 303, 307, 308)


def _allowed_hosts() -> set:
    """允许的域名集合 = GitHub 官方域名 + 配置的镜像源域名"""
    hosts = set(_FIXED_ALLOWED_HOSTS)
    for base in BASE_DOWNLOAD_URLS:
        host = urlparse(base).hostname
        if host:
            hosts.add(host.lower())
    return hosts


def is_safe_url(url: str) -> bool:
    """校验 URL: 仅允许 https 协议 + 白名单内的 GitHub 官方/镜像域名。

    白名单来自 config 的 BASE_DOWNLOAD_URLS (单一维护点), 镜像源增删时
    白名单自动跟随。
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme != "https":
        return False

    host = (parsed.hostname or "").lower()
    if not host:
        return False

    return host in _allowed_hosts()


def safe_get(url: str, timeout, headers: dict | None = None) -> "requests.Response":
    """受限的 GET 请求: 先校验目标地址, 再发起不跟随重定向的请求。

    用于 GitHub API 等 JSON 端点 (这些地址不存在重定向);
    禁止跟随重定向可防止被 3xx 引向白名单之外的地址。
    文件下载需要跟随镜像源重定向, 请使用 safe_get_follow。
    """
    if not is_safe_url(url):
        raise ValueError(f"拒绝请求白名单之外的地址: {url}")
    return requests.get(
        url,
        timeout=timeout,
        headers=headers,
        allow_redirects=False,
    )


def is_allowed_redirect_target(url: str) -> bool:
    """校验重定向目标: https + 解析结果非环回/链路本地/私有地址。

    代理 TUN+Fake-IP 的保留段虚拟地址放行 (见 _FAKE_IP_NETWORKS)。
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
            if any(ip in net for net in _FAKE_IP_NETWORKS):
                continue
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


def safe_get_follow(
    url: str,
    timeout,
    headers: dict | None = None,
    stream: bool = False,
    max_redirects: int = 5,
) -> "requests.Response":
    """校验起始 URL 后手动跟随重定向的 GET 请求。

    每一跳 (含重定向目标) 都重新过校验, 比 requests 自动重定向更严格:
    自动模式无法对中间跳做地址检查。超过重定向上限抛 ValueError。
    """
    current = url
    response = None
    for _ in range(max_redirects + 1):
        if not (is_safe_url(current) or is_allowed_redirect_target(current)):
            raise ValueError(f"拒绝请求白名单/公网之外的地址: {current}")
        response = requests.get(
            current,
            timeout=timeout,
            headers=headers,
            stream=stream,
            allow_redirects=False,
        )
        if response.status_code in _REDIRECT_STATUSES:
            location = response.headers.get("Location")
            if not location:
                return response
            next_url = urljoin(current, location)
            if stream:
                response.close()
            current = next_url
            continue
        return response
    raise ValueError(f"重定向次数超过上限 ({max_redirects})")
