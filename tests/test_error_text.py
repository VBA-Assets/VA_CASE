"""例外を画面に出すときの文（common/errors.py の describe。標準 02「メッセージとエラー」。2026-11-19）と、
⌘ キーの割り当て（common/ui/keys.py）。"""
import pytest

from va_case.common.errors import DIAGNOSTICS_HINT, ConflictError, describe, is_for_user
from va_case.common.ui.keys import ctrl_sequences


def test_messages_written_for_users_are_shown_as_they_are():
    e = ConflictError("甲野", "10:00")
    assert is_for_user(e) and describe(e) == str(e)
    v = ValueError("事件番号 12 は、すでにあります。")
    assert is_for_user(v) and describe(v) == str(v)


def test_other_errors_show_a_summary_and_the_hint():
    e = PermissionError(13, "Access is denied", "X:\\共有\\VA_Case.json")
    assert not is_for_user(e)
    text = describe(e)
    assert "Access is denied" not in text and "権限" in text
    assert "X:\\共有\\VA_Case.json" in text and DIAGNOSTICS_HINT in text
    assert describe(e, detail=False) == text.split("\n")[0]
    k = describe(KeyError("x"))
    assert k.startswith("予期しない誤り") and "KeyError" not in k and "'x'" not in k
    assert not is_for_user(ValueError("invalid literal for int() with base 10: 'a'"))


def test_japanese_text_raised_outside_this_tool_is_not_shown():
    """部品の例外の文にも、日本語のファイル名が入ることがある。誤りが起きた場所がこのパッケージの外なら、見せない（Ver104）。"""
    code = compile("raise ValueError('甲野.pdf を読めません: bad xref')", "C:\\lib\\site-packages\\pdfpart\\reader.py", "exec")
    with pytest.raises(ValueError) as info:
        exec(code, {})
    assert not is_for_user(info.value)
    assert "bad xref" not in describe(info.value)


def test_master_corrupt_shows_only_text_written_for_users():
    """共有データの中身が欠けているときの文に、KeyError などの文（'rows' など）を入れない（master.parse。Ver104）。"""
    import json
    from va_case.common import master
    from va_case.common.errors import MasterCorruptError

    def raw(tables):
        return json.dumps({"format": master.FORMAT, "format_version": master.FORMAT_VERSION, "tool": "case",
                           "tables": tables, "version": 1, "write_id": "x", "written": {}}).encode("utf-8")

    with pytest.raises(MasterCorruptError) as info:
        master.parse(raw({"事件": {"columns": ["番号"]}}))
    assert "中身が欠けている" in str(info.value) and "'rows'" not in str(info.value)
    with pytest.raises(MasterCorruptError) as info:
        master.parse(raw({"事件": {"columns": ["番号", "番号"], "rows": []}}))
    assert "列の名前が重複しています" in str(info.value)


def test_restore_reports_a_summary_for_links_it_could_not_remove(tmp_path, monkeypatch):
    """保管を取り消すときに写しを消せなかったら、OSError の文でなく要旨を知らせる（storing.restore。Ver104）。"""
    from va_case.common import storing
    stored, back, link = tmp_path / "保管.pdf", tmp_path / "戻す先.pdf", tmp_path / "写し.pdf"
    stored.write_bytes(b"x")
    link.write_bytes(b"x")
    p = storing.RestorePlan(stored, back, [storing.Link(storing.KIND_COPY, tmp_path, link)])

    def fail(path):
        raise OSError(22, "Invalid argument", str(path))

    monkeypatch.setattr(storing.os, "unlink", fail)
    assert storing.restore(p) == []
    assert back.exists() and len(p.missing) == 1
    assert "Invalid argument" not in p.missing[0] and "読み書きできませんでした" in p.missing[0]


class _Tk:
    def __init__(self, system):
        self.system = system

    def call(self, *args):
        return self.system


class _Widget:
    def __init__(self, system):
        self.tk = _Tk(system)


def test_command_key_only_on_mac():
    assert ctrl_sequences(_Widget("win32"), "z") == ["<Control-z>", "<Control-Z>"]
    assert ctrl_sequences(_Widget("aqua"), "z") == ["<Control-z>", "<Control-Z>", "<Command-z>", "<Command-Z>"]
    assert ctrl_sequences(_Widget("win32"), "Home") == ["<Control-Home>"]
