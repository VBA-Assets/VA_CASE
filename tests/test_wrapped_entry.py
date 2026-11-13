"""2行の高さで見せる1行の入力欄（WrappedEntry）の試験。"""
import tkinter as tk

import pytest

from va_case.common.ui.dialogs import WrappedEntry


@pytest.fixture(scope="module")
def root():   # Tk は試験のファイルで1つだけ作る（作り直すと、続けて作れないことがある）
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("画面がない環境")
    r.withdraw()
    yield r
    r.destroy()


def test_syncs_with_variable_and_keeps_one_line(root):
    var = tk.StringVar(value="20251105103000000甲野太郎（貸金）　訴状.pdf")
    w = WrappedEntry(root, var, width=20)
    assert w.get("1.0", "end-1c") == var.get()
    var.set("新しい名前.pdf")                       # 変数から欄へ
    assert w.get("1.0", "end-1c") == "新しい名前.pdf"
    w.insert("end", "\n続き")                       # 欄から変数へ（改行は除く）
    w.event_generate("<<Modified>>")
    root.update()
    assert var.get() == "新しい名前.pdf続き"
    assert w.get_value() == "新しい名前.pdf続き"


def test_readonly_state(root):
    var = tk.StringVar(value="x.pdf")
    w = WrappedEntry(root, var)
    w.configure(state="readonly")
    assert str(w.cget("state")) == "disabled"
    var.set("y.pdf")                               # 直せない状態でも、変数の値は出す
    assert w.get("1.0", "end-1c") == "y.pdf"
    w.configure(state="normal")
    assert str(w.cget("state")) == "normal"
