"""注記の折り返し（wrap_text）の試験。字の幅は、1字10画素として測る。"""
from va_case.common.ui.dialogs import wrap_text


class FakeFont:
    def measure(self, text):
        return len(text) * 10


def test_does_not_break_inside_ascii_words():
    lines = wrap_text("ショートカットは Windows でだけ作ります。", FakeFont(), 120).split("\n")
    assert "Windows" in "".join(lines) and all("Win" not in l or "Windows" in l for l in lines)
    assert all(len(l) * 10 <= 120 or " " not in l for l in lines)


def test_fills_line_instead_of_breaking_at_space():
    # Tk の折り返しでは「VA Case の」の後で改行された（2026-11-09 班長指摘）
    out = wrap_text("VA Case の VA_Case.json。事件呼名・データフォルダを読みます。", FakeFont(), 300)
    assert out.split("\n")[0].startswith("VA Case の VA_Case.json。事件呼名")


def test_kinsoku():
    out = wrap_text("あいうえおかきくけこ。さしすせそ", FakeFont(), 100)
    assert not any(l.startswith("。") for l in out.split("\n"))
    out = wrap_text("あいうえおかきく（けこ）さし", FakeFont(), 90)
    assert not any(l.endswith("（") for l in out.split("\n"))


def test_keeps_paragraphs_and_short_text():
    assert wrap_text("短い文。", FakeFont(), 500) == "短い文。"
    assert wrap_text("一行目\n二行目", FakeFont(), 500) == "一行目\n二行目"


def test_case_list_cell_wraps_like_excel():
    """VA Case の一覧のセル（2026-11-09 班長指示「すべてのセルを折り返して表示」）：改行はそのまま行の区切り、
    幅を超える文は折り返す。1行に収まらない英数字の続き（パス）は、字の間で切る。"""
    from types import SimpleNamespace

    from va_case.case.app import CaseApp
    cell = SimpleNamespace(_wrap_cache={})
    wrap = lambda text, width: CaseApp._wrap_cell(cell, text, FakeFont(), width, 10)   # noqa: E731
    assert wrap("", 100) == [""]
    assert wrap("架空一郎\n架空二郎\n架空三郎", 100) == ["架空一郎", "架空二郎", "架空三郎"]
    assert wrap("東京都千代田区架空町一丁目", 60) == ["東京都千代田", "区架空町一丁", "目"]
    path = r"D:\scan\abcdefghijklmnopqrstuvwxyz"
    lines = wrap(path, 60)
    assert "".join(lines) == path and len(lines) > 1 and all(len(line) * 10 <= 60 for line in lines)
