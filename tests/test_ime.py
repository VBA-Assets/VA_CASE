"""IME の入力中の字の書体を、入力欄の書体に合わせる（2026-11-11 班長決定）の試験。Windows だけ。"""
import os
import tkinter as tk
from tkinter import ttk

import pytest

from va_case.common.ui import ime, theme
from conftest import reset_root

pytestmark = pytest.mark.skipif(os.name != "nt", reason="IME の書体は Windows だけで合わせる")


@pytest.fixture(scope="module")
def root(tk_root):   # Tk は試験の全体で1つ（conftest の tk_root）。この試験の後で、作った部品を片付ける
    r = tk_root
    r.deiconify()
    theme.apply_theme(r)
    r.geometry("+0+0")
    yield r
    reset_root(r)


def test_each_input_gets_its_own_font(root):
    field = theme.field_font(root)
    entry = ttk.Entry(root, font=field)
    combo = ttk.Combobox(root, font=field, values=["A:未了"])
    search = ttk.Entry(root)                       # 書体を指定していない欄（画面の字）
    text = tk.Text(root, font=field, height=2)
    for w in (entry, combo, search, text):
        w.pack()
    root.update()
    expect = ime.widget_font(entry)
    assert expect and expect[1] > 0
    for w in (entry, combo, text):
        assert ime.fit(w)
        assert ime.composition_font(w) == (expect[0], -expect[1])
    small = ime.widget_font(search)
    assert ime.fit(search) and ime.composition_font(search) == (small[0], -small[1])   # 入るたびに合わせ直す
    assert not ime.fit(ttk.Button(root, text="押す"))                                    # 字を入力しない部品は合わせない
