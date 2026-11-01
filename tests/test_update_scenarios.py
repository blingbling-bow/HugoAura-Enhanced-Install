"""更新检查场景: 轨道新旧判断 + 安装器自更新版本比较"""

import pytest

from app.tk.models import installer_model
from app.tk.models.installer_model import InstallerModel
from utils.version_manager import _is_newer_release, version_manager


def _mock_github(monkeypatch, releases, ci_all):
    data = {
        "data_source": "github_api",
        "releases": releases,
        "prereleases": [],
        "ci_builds": ci_all[:1],
        "ci_all": ci_all,
    }
    pub = {
        v["tag"]: v["published_at"]
        for lst in (data["releases"], data["ci_all"])
        for v in lst
    }
    monkeypatch.setattr(version_manager, "get_versions", lambda: data)
    monkeypatch.setattr(version_manager, "find_published_at", lambda tag: pub.get(tag))


def test_update_scenarios(monkeypatch):
    """发行版/CI 新旧组合的更新目标判定"""
    _mock_github(
        monkeypatch,
        releases=[
            {"tag": "v0.3.2", "published_at": "2026-10-10T08:00:00Z"},
            {"tag": "v0.3.1", "published_at": "2026-10-01T08:00:00Z"},
        ],
        ci_all=[
            {"tag": "vAutoBuild-fff222", "published_at": "2026-10-11T09:00:00Z"},
            {"tag": "vAutoBuild-aaa111", "published_at": "2026-10-05T09:00:00Z"},
        ],
    )
    cases = [
        ("v0.3.2", False, None),
        ("v0.3.1", True, "v0.3.2"),
        ("vAutoBuild-fff222", False, None),
        ("vAutoBuild-aaa111", True, "v0.3.2"),
    ]
    for installed, exp_update, exp_target in cases:
        monkeypatch.setattr(
            installer_model,
            "check_hugoaura_installation",
            lambda i=installed: (True, {"version": i}),
        )
        info = InstallerModel().get_update_available()
        assert info["update_available"] == exp_update, installed
        assert info["update_target"] == exp_target, installed


def test_installer_version_compare():
    """安装器自更新: 主.次.修订比较, 后缀与解析失败不误报"""
    cases = [
        ("v0.0.5-beta", "v0.0.4-beta-I", True),
        ("v0.0.5-beta", "v0.0.5-beta", False),
        ("v0.0.4-beta", "v0.0.4-beta-I", False),
        ("v0.1.0-beta", "v0.0.9-beta", True),
        ("vAutoBuild-abc", "v0.0.5-beta", False),
        ("", None, False),
        (None, None, False),
    ]
    for latest, cur, exp in cases:
        assert _is_newer_release(latest, cur) == exp, (latest, cur)
