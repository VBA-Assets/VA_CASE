"""例外を画面に出すときの文（common/errors.py の describe。標準 02「メッセージとエラー」。2026-11-19）と、
⌘ キーの割り当て（common/ui/keys.py）。"""
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
