"""入力欄を Tab で移るときの決まりの試験（2026-11-10 班長指摘）。

- 閲覧モードで直せない状態にしたドロップダウン・何行かの欄にも、Tab で移れる。
- Tab で入った入力欄の文字全体を選ばない（確定前の文字のように見えるため）。
- 選ぶだけのドロップダウンに入っても、文字が消えない（白い地に白い文字にしない）。
"""
import tkinter as tk
from tkinter import ttk

import pytest

from va_case.common.ui import theme


@pytest.fixture(scope="module")
def root():   # Tk は試験のファイルで1つだけ作る
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("画面がない環境")
    theme.apply_theme(r)
    r.withdraw()
    yield r
    r.destroy()


def test_view_mode_fields_are_tab_stops(root):
    win = tk.Toplevel(root)
    first = ttk.Entry(win)
    combo = ttk.Combobox(win, values=["A:未了"], state="disabled")
    text = tk.Text(win, height=2)
    text.configure(state="disabled")
    last = ttk.Entry(win)
    for w in (first, combo, text, last):
        w.pack()
    win.update()
    assert first.tk_focusNext() is last          # 既定では、直せない状態の欄は飛ばされる
    theme.tab_stop(combo, True)
    theme.tab_stop(text, True)
    assert first.tk_focusNext() is combo
    assert combo.tk_focusNext() is text
    assert text.tk_focusNext() is last
    theme.tab_stop(combo, False)                  # 行を選んでいないときなどは、元の決まりに戻す
    theme.tab_stop(text, False)
    assert first.tk_focusNext() is last
    win.destroy()


def test_traverse_in_does_not_select_all(root):
    win = tk.Toplevel(root)
    e = ttk.Entry(win)
    ro = ttk.Entry(win)
    cb = ttk.Combobox(win, values=["佐"])
    for w in (e, ro, cb):
        w.pack()
    e.insert(0, "甲野太郎（貸金）")
    ro.insert(0, "R7.4.10")
    ro.configure(state="readonly")
    cb.set("佐")
    win.update()
    for w, n in ((e, len("甲野太郎（貸金）")), (ro, len("R7.4.10")), (cb, 1)):
        w.event_generate("<<TraverseIn>>")
        root.update()
        assert not w.selection_present() and w.index("insert") == n
    win.destroy()


def test_readonly_combobox_text_stays_visible_on_focus(root):
    style = ttk.Style(root)
    fg = style.lookup("TCombobox", "foreground", ["readonly", "focus"])
    bg = style.lookup("TCombobox", "fieldbackground", ["readonly", "focus"])
    assert fg == theme.TEXT and fg != bg
