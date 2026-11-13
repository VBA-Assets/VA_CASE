"""フォルダの値の読み書き（PC ごとに共有フォルダの場所が違う事務所・Mac。2026-11-12 班長決定「対応する」）。"""
import sys
from pathlib import Path

import pytest

from va_case.common.paths import join_value, portable, resolve_folder, sub_of

WIN = sys.platform == "win32"
ROOT = r"C:\Users\a\OneDrive\共有" if WIN else "/Users/a/OneDrive/共有"


def test_relative_value_reads_with_either_separator():
    assert resolve_folder(r"事件\101甲野太郎\scan", ROOT) == Path(ROOT) / "事件" / "101甲野太郎" / "scan"
    assert resolve_folder("事件/101甲野太郎/scan", ROOT) == Path(ROOT) / "事件" / "101甲野太郎" / "scan"
    assert resolve_folder(r"事件\101", "") is None                       # 基点がなければ読めない
    assert resolve_folder(r"O:\事件\101", ROOT) == Path(r"O:\事件\101")   # Windows の絶対パスはそのまま


@pytest.mark.skipif(not WIN, reason="Windows のパスの試験")
def test_portable_on_windows():
    root = r"C:\Users\a\OneDrive\共有"
    # 基点の下なら、基点からの相対にする（大文字・小文字は問わない）
    assert portable(r"c:\users\A\onedrive\共有\事件\101\scan", root) == r"事件\101\scan"
    assert portable(r"D:\文献", root) == r"D:\文献"                       # 基点の外は、そのまま
    assert portable(root, root) == root                                    # 基点そのものも、そのまま
    assert portable(r"事件\101", root) == r"事件\101"                     # もう相対なら、そのまま
    assert portable(r"C:\x", "") == r"C:\x"                                # 基点を決めていない PC
    assert portable(r"C:\Users\a\OneDrive\共有2\x", root) == r"C:\Users\a\OneDrive\共有2\x"   # 名前の頭だけ同じは外


def test_join_and_sub():
    assert join_value(r"事件\101", "scan") == r"事件\101\scan"
    assert join_value("/Users/a/事件", r"scan\a") == "/Users/a/事件/scan/a"
    assert join_value(r"事件\101", "") == r"事件\101"
    assert sub_of(r"事件\101\Scan", str(Path(ROOT) / "事件" / "101"), ROOT) == "Scan"   # 相対と絶対を混ぜても比べる
    assert sub_of(r"事件\101", r"事件\101", ROOT) == ""
    assert sub_of(r"事件\1010", r"事件\101", ROOT) is None
    assert sub_of(r"事件\101", "", ROOT) is None
