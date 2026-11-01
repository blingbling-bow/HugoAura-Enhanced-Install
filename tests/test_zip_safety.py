"""zip 解压安全: 路径穿越成员不得逃逸出目标目录"""

import zipfile

import utils.fileDownloader as fd


def test_zip_traversal_member_cannot_escape(download_dir):
    """含 ../ 成员的 zip 解压后不得出现在目标目录之外 (CPython 会规整路径)"""
    zpath = download_dir / "evil.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("../evil_escaped.txt", "pwned")
        z.writestr("normal/inside.txt", "ok")
    esc_target = download_dir / "evil_escaped.txt"
    ok = fd.unzip_file(zpath, download_dir / "sliptest")
    assert ok is True
    assert not esc_target.exists(), "zip 成员逃逸出目标目录"
    assert (download_dir / "sliptest" / "normal" / "inside.txt").exists()
