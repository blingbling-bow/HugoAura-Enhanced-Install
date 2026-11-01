import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest


@pytest.fixture(autouse=True)
def _reset_downloader_globals():
    """每条测试前后重置下载器全局状态与进度回调, 避免用例间串扰"""
    import lifecycle as lifecycleMgr
    import utils.fileDownloader as fd
    from typeDefs.lifecycle import GLOBAL_CALLBACKS

    fd._speed_test_cache["order"] = None
    fd.desiredTag = None
    yield
    lifecycleMgr.callbacks[GLOBAL_CALLBACKS.REPORT_DOWNLOAD_PROGRESS.value] = None


@pytest.fixture()
def download_dir():
    """位于 TEMP_INSTALL_DIR 内的临时下载目录 (满足下载路径防御)"""
    from config.config import TEMP_INSTALL_DIR

    d = Path(TEMP_INSTALL_DIR) / "pytest-dl"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)
