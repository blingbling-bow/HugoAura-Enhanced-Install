"""download_file 回归测试: 进度回调契约 / 取消 / 回调隔离 / SHA 与字节校验"""

import requests
import pytest

import lifecycle as lifecycleMgr
import utils.fileDownloader as fd
from typeDefs.lifecycle import GLOBAL_CALLBACKS


class FakeResp:
    """替代 safe_get_follow 的假响应 (stream 模式)"""

    def __init__(self, chunks, headers=None, status=200):
        self._chunks = chunks
        self.headers = headers or {}
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def iter_content(self, chunk_size=8192):
        for c in self._chunks:
            yield c

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture()
def patched_downloader(monkeypatch):
    """让 download_file 走假响应, 不出网"""
    def _install(chunks, headers=None):
        resp = FakeResp(chunks, headers)
        monkeypatch.setattr(fd, "safe_get_follow", lambda url, **kw: resp)
        monkeypatch.setattr(fd, "_is_safe_url", lambda url: True)
    return _install


def test_progress_callback_receives_str_filename(patched_downloader, download_dir):
    """回归: fd 方式打开文件后 f.name 是 int, 回调曾因此拿到非字符串崩溃"""
    chunks = [b"a" * 4096, b"b" * 3279]  # 共 7375 字节
    patched_downloader(chunks, headers={"content-length": "7375"})
    seen = []

    def cb(downloaded, total, filename):
        seen.append((downloaded, total, filename))

    lifecycleMgr.callbacks[GLOBAL_CALLBACKS.REPORT_DOWNLOAD_PROGRESS.value] = cb

    result = fd.download_file("https://mirror.example/x/core.zip", str(download_dir), "core.zip")

    assert result is not None
    assert seen, "progress callback never fired"
    assert all(isinstance(f, str) for _, _, f in seen), seen
    assert seen[-1][0] == 7375 and seen[-1][1] == 7375


def test_callback_exception_does_not_abort(patched_downloader, download_dir):
    """进度回调抛任意异常不应中止下载 (取消信号除外)"""
    patched_downloader([b"x" * 1000])

    def bad_cb(downloaded, total, filename):
        raise ZeroDivisionError("simulated UI error")

    lifecycleMgr.callbacks[GLOBAL_CALLBACKS.REPORT_DOWNLOAD_PROGRESS.value] = bad_cb
    result = fd.download_file("https://mirror.example/x/core.zip", str(download_dir), "core.zip")
    assert result is not None, "callback error aborted the download"


def test_cancel_signal_returns_dl_cancel(patched_downloader, download_dir):
    """回调里的 INSTALLATION_CANCELLED 必须穿透为 DL_CANCEL"""
    patched_downloader([b"x" * 1000])

    def cancel_cb(downloaded, total, filename):
        raise Exception("INSTALLATION_CANCELLED")

    lifecycleMgr.callbacks[GLOBAL_CALLBACKS.REPORT_DOWNLOAD_PROGRESS.value] = cancel_cb
    result = fd.download_file("https://mirror.example/x/core.zip", str(download_dir), "core.zip")
    assert result == "DL_CANCEL"


def test_sha_mismatch_rejects_and_deletes(patched_downloader, download_dir):
    """SHA256 不匹配时返回 None 并删除落盘文件"""
    patched_downloader([b"hello-world"])
    result = fd.download_file(
        "https://mirror.example/x/core.zip",
        str(download_dir),
        "core.zip",
        expected_sha256="0" * 64,
    )
    assert result is None
    assert not (download_dir / "core.zip").exists()


def test_sha_match_passes(patched_downloader, download_dir):
    import hashlib

    data = b"payload-bytes"
    patched_downloader([data])
    good = hashlib.sha256(data).hexdigest()
    result = fd.download_file(
        "https://mirror.example/x/core.zip",
        str(download_dir),
        "core.zip",
        expected_sha256=good,
    )
    assert result is not None
    assert (download_dir / "core.zip").read_bytes() == data


def test_incomplete_download_rejected(patched_downloader, download_dir):
    """content-length 声明更多字节时判为不完整并拒绝"""
    patched_downloader([b"x" * 100], headers={"content-length": "9999"})
    result = fd.download_file("https://mirror.example/x/core.zip", str(download_dir), "core.zip")
    assert result is None
