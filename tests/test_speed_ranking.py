"""两阶段测速排序: 镜像优先 / 跳过测速 / 综合排序 / 失败源垫底"""

import utils.fileDownloader as fd

MIRRORS = [
    "https://a.example/prefix",
    "https://b.example/prefix",
    "https://c.example/prefix",
]


def test_skip_speedtest_returns_default_order(monkeypatch):
    monkeypatch.setattr(fd, "BASE_DOWNLOAD_URLS", list(MIRRORS))
    order = fd.benchmark_download_sources("v9.9.9", enabled=False)
    assert order == MIRRORS, order


def test_mirror_prefixed_in_skipped_and_cached_paths(monkeypatch):
    monkeypatch.setattr(fd, "BASE_DOWNLOAD_URLS", list(MIRRORS))
    order = fd.benchmark_download_sources("v9.9.9", enabled=False, mirror="https://m.example/p")
    assert order[0] == "https://m.example/p"
    assert order.count("https://m.example/p") == 1


def test_composite_ranking(monkeypatch):
    """按 预估总时间 = 延迟 + 大小/带宽 升序; 探测失败垫底, 阶段一失败最后"""
    monkeypatch.setattr(fd, "BASE_DOWNLOAD_URLS", list(MIRRORS))
    monkeypatch.setattr(fd, "SPEED_PROBE_COUNT", 3)

    def fake_screen(base_url, tag, sha):
        lat = {"a": 0.1, "b": 0.2, "c": 0.3}[base_url[8]]
        return (base_url, lat, True)

    def fake_bw(base_url, tag):
        bps = {"a": 200 * 1024, "b": 1000 * 1024, "c": None}[base_url[8]]
        return bps

    monkeypatch.setattr(fd, "_speed_test_single", fake_screen)
    monkeypatch.setattr(fd, "_measure_bandwidth", fake_bw)
    order = fd.benchmark_download_sources("v9.9.9")
    hosts = [u[8] for u in order]
    assert hosts[0] == "b", order
    assert hosts[1] == "a", order
    assert hosts[2] == "c", order
