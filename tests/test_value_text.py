"""カードの番号・読込ファイルを、なぞって選び Ctrl+C でコピーできる（2026-11-13 班長指摘「カードで番号がコピーできない」）試験。"""
import tkinter as tk
from tkinter import ttk

import pytest

from va_case.common.ui import theme


@pytest.fixture(scope="module")
def root():
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("画面がない環境")
    theme.apply_theme(r)
    yield r
    r.destroy()


def test_value_text_can_be_selected_and_copied(root):
    var = tk.StringVar(root, "261113012")
    w = theme.value_text(root, var)
    w.pack()
    root.update()
    assert str(w.cget("state")) == "readonly" and str(w.cget("style")) == "Value.TEntry"
    assert str(w.cget("takefocus")) == "0"                     # Tab では止まらない
    assert int(w.cget("width")) == 10                          # 値の長さに合わせる
    var.set("（一覧でメモを選んでください）")
    assert int(w.cget("width")) == 31                          # 全角は2として数える
    var.set("261113012")
    w.focus_force()
    w.selection_range(0, "end")
    root.clipboard_clear()
    w.event_generate("<<Copy>>")
    root.update()
    assert root.clipboard_get() == "261113012"
    w.insert("end", "x")                                       # 直せない
    assert var.get() == "261113012"


def test_selection_is_cleared_when_focus_leaves(root):
    """欄から出たら、選んだ文字を外す（2026-11-13 班長指摘「選択状態が解除されない」）。"""
    import time
    var = tk.StringVar(root, "261113012")
    w = theme.value_text(root, var)
    other = ttk.Entry(root)
    w.pack()
    other.pack()
    root.update()
    w.focus_force()
    root.update()
    w.selection_range(0, "end")
    assert w.selection_present()
    other.focus_force()
    for _ in range(3):
        root.update()
        time.sleep(0.05)
    assert not w.selection_present()
