"""
版本管理器
负责从GitHub API获取版本信息, 失败时回退到本地JSON文件
"""

import json
import os
import requests
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from loguru import logger as log
from config.config import GITHUB_OWNER, GITHUB_REPO


class VersionManager:
    """版本管理器"""
    
    def __init__(self, github_repo: str = f"{GITHUB_OWNER}/{GITHUB_REPO}", timeout: int = 3000):
        """
        初始化版本管理器
        
        Args:
            github_repo: GitHub仓库名称 (owner/repo)
            timeout: API请求超时时间 (毫秒)
        """
        self.github_repo = github_repo
        self.timeout = timeout / 1000.0  # 转换为秒
        self.api_base = f"https://api.github.com/repos/{github_repo}"
        
        # 本地版本文件路径
        self.local_versions_file = Path(__file__).parents[1] / "app" / "public" / "versions.json"
        
        # 缓存的版本信息
        self._cached_versions: Optional[Dict] = None
    
    def get_versions(self) -> Dict[str, List[Dict]]:
        """
        获取版本信息
        优先从GitHub API获取, 超时后使用本地JSON
        
        Returns:
            包含releases、prereleases、ci_builds的字典
        """
        if self._cached_versions is not None:
            log.info("使用缓存的版本信息")
            return self._cached_versions
            
        log.info("正在获取版本信息...")
        
        # 尝试从GitHub API获取
        try:
            log.info("尝试从GitHub API获取版本信息...")
            github_versions = self._fetch_from_github()
            if github_versions:
                log.info("✅ 成功从GitHub API获取版本信息")
                self._cached_versions = github_versions
                # 标记数据来源
                self._cached_versions["data_source"] = "github_api"
                return self._cached_versions
        except Exception as e:
            log.warning(f"从GitHub API获取版本信息失败: {e}")
        
        # 回退到本地JSON
        try:
            log.info("回退到本地版本信息...")
            local_versions = self._load_local_versions()
            log.info("✅ 成功加载本地版本信息")
            self._cached_versions = local_versions
            # 标记数据来源
            self._cached_versions["data_source"] = "local_json"
            return self._cached_versions
        except Exception as e:
            log.error(f"❌ 加载本地版本信息失败: {e}")
            # 返回空的版本信息
            return {
                "releases": [], 
                "prereleases": [], 
                "ci_builds": [],
                "data_source": "empty",
                "error": str(e)
            }
    
    def _fetch_from_github(self) -> Optional[Dict]:
        """
        从GitHub API获取版本信息
        
        Returns:
            版本信息字典, 失败时返回None
        """
        try:
            # 获取所有releases
            releases_url = f"{self.api_base}/releases"
            response = requests.get(releases_url, timeout=self.timeout)
            response.raise_for_status()
            
            releases_data = response.json()
            
            # 分类版本
            releases = []
            prereleases = []
            ci_releases = []
            
            for release in releases_data:
                if release.get("draft", False):
                    continue  # 跳过草稿版本

                version_info = {
                    "tag": release["tag_name"],
                    "name": f"{release['name'] or release['tag_name']}",
                    "type": "prerelease" if release["prerelease"] else "release",
                    "published_at": release.get("published_at"),
                    "download_url": self._get_download_url(release)
                }
                
                # 识别 CI 自动构建版本: tag 以 vAutoBuild 开头, 或 name 以 [CI] 开头
                # (CI 构建 tag 形如 vAutoBuild-<commit短hash>, 每次构建独立 tag)
                tag_name = release["tag_name"] or ""
                release_name = release.get("name") or ""
                if tag_name.startswith("vAutoBuild") or release_name.startswith("[CI]"):
                    version_info["type"] = "ci"
                    ci_releases.append(version_info)
                    continue
                
                if release["prerelease"] and len(prereleases) <= 5: # 仅显示前 5 个版本
                    prereleases.append(version_info)
                elif len(releases) <= 5: # 同上
                    releases.append(version_info)
            
            # 从所有 CI 构建中选取最新构建 (按发布时间倒序, 取第一个)
            ci_builds = []
            if ci_releases:
                ci_releases.sort(
                    key=lambda r: r.get("published_at") or "",
                    reverse=True,
                )
                ci_builds = [ci_releases[0]]
            
            return {
                "releases": releases,
                "prereleases": prereleases,
                "ci_builds": ci_builds,
                "last_updated": releases_data[0].get("published_at") if releases_data else None
            }
            
        except requests.exceptions.Timeout:
            log.warning(f"GitHub API 请求超时 ({self.timeout}s)")
            return None
        except requests.exceptions.RequestException as e:
            log.warning(f"GitHub API 请求失败: {e}")
            return None
        except Exception as e:
            log.error(f"处理 GitHub API 响应时出错: {e}")
            return None
    
    def _get_download_url(self, release: Dict) -> Optional[str]:
        """
        从release信息中提取下载URL
        
        Args:
            release: GitHub release信息
            
        Returns:
            下载URL, 如果没有找到合适的资源则返回None
        """
        assets = release.get("assets", [])
        
        # 寻找.asar文件
        for asset in assets:
            if asset["name"].endswith(".asar"):
                return asset["browser_download_url"]
        
        # 如果没有.asar文件, 返回第一个资源的下载链接
        if assets:
            return assets[0]["browser_download_url"]
            
        return None
    
    def _load_local_versions(self) -> Dict:
        """
        加载本地版本信息文件
        
        Returns:
            版本信息字典
        """
        if not self.local_versions_file.exists():
            raise FileNotFoundError(f"本地版本文件不存在: {self.local_versions_file}")
        
        with open(self.local_versions_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def get_latest_release(self) -> Optional[Dict]:
        """
        获取最新的发行版
        
        Returns:
            最新发行版信息, 如果没有则返回None
        """
        versions = self.get_versions()
        releases = versions.get("releases", [])
        return releases[0] if releases else None
    
    def get_latest_prerelease(self) -> Optional[Dict]:
        """
        获取最新的预发行版
        
        Returns:
            最新预发行版信息, 如果没有则返回None
        """
        versions = self.get_versions()
        prereleases = versions.get("prereleases", [])
        return prereleases[0] if prereleases else None
    
    def get_version_by_tag(self, tag: str) -> Optional[Dict]:
        """
        根据标签获取版本信息
        
        Args:
            tag: 版本标签
            
        Returns:
            版本信息, 如果没有找到则返回None
        """
        versions = self.get_versions()
        
        # 在所有版本类型中搜索
        for version_list in [versions.get("releases", []), 
                           versions.get("prereleases", []), 
                           versions.get("ci_builds", [])]:
            for version in version_list:
                if version["tag"] == tag:
                    return version
        
        return None
    
    def refresh_cache(self):
        """刷新缓存的版本信息"""
        self._cached_versions = None
        log.info("版本信息缓存已刷新")


# 全局版本管理器实例
version_manager = VersionManager() 