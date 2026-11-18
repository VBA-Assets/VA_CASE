"""VA Filing・VA Receipt の保管済みの行で、備考のほかの欄を入力欄に見えない形にする（2026-11-13 班長決定「案１のみ」：
保管済みのファイルの日時などは直せないが、画面では直せる欄と見分けがつかなかった）試験。"""
import tkinter as tk
from tkinter import ttk
from types import MethodType, SimpleNamespace

import pytest

from va_case.common.ui import theme
from va_case.common.ui.dialogs import WrappedEntry
from va_case.common.ui.file_store_app import FileStoreApp
from conftest import reset_root


@pytest.fixture(scope="module")
def root(tk_root):   # Tk は試験の全体で1つ（conftest の tk_root）。この試験の後で、作った部品を片付ける
    r = tk_root
    r.deiconify()
    theme.apply_theme(r)
    yield r
    reset_root(r)


def make(root, editing):
    p = ttk.Frame(root)
    p.pack()
    vars_ = {k: tk.StringVar(value=f"{k}の値") for k in ("日時", "事件呼名", "保管ファイル名", "備考")}
    widgets = {}
    for r, (name, var) in enumerate(vars_.items()):
        if name == "事件呼名":
            w = ttk.Combobox(p, textvariable=var)
        elif name == "保管ファイル名":
            w = WrappedEntry(p, var, width=20, height=2)
        else:
            w = ttk.Entry(p, textvariable=var)
        w.grid(row=r, column=1)
        widgets[name] = w
    button = SimpleNamespace(state=lambda s: None)
    a = SimpleNamespace(widgets=widgets, vars=vars_, editing=editing, store_button=button, pick_button=None,
                        restore_button=button, open_file_button=button)
    a._set_panel_state = MethodType(FileStoreApp._set_panel_state, a)
    return a


def looks(w):
    """欄の見た目：入力欄に見えない形なら "locked"、ふつうの欄なら "field"。"""
    if isinstance(w, ttk.Combobox):
        w = w._va_mirror if w._va_mirror.winfo_manager() else w
    if isinstance(w, WrappedEntry):
        return "locked" if (w.cget("background"), w.cget("highlightbackground")) == (theme.WINDOW_BG,) * 2 \
            else "field"
    return "locked" if str(w.cget("style")) == "Locked.TEntry" else "field"


@pytest.mark.parametrize("editing", [True, False])
def test_stored_row_shows_only_note_as_field(root, editing):
    a = make(root, editing)
    a._set_panel_state("stored")
    assert {n: looks(w) for n, w in a.widgets.items()} == {
        "日時": "locked", "事件呼名": "locked", "保管ファイル名": "locked", "備考": "field"}
    assert str(a.widgets["備考"].cget("state")) == ("normal" if editing else "readonly")
    assert str(a.widgets["日時"].cget("state")) == "readonly"     # 文字は選んでコピーできる
    a._set_panel_state("open")                                      # 未保管の行に移ったら、ふつうの欄に戻す
    assert set(looks(w) for w in a.widgets.values()) == {"field"}
    assert a.widgets["保管ファイル名"].cget("background") == (theme.FIELD_BG if editing else theme.READONLY_BG)


def test_locked_style_colors(root):
    s = ttk.Style(root)
    assert s.lookup("Locked.TEntry", "fieldbackground", ["readonly"]) == theme.WINDOW_BG
    assert s.lookup("Locked.TEntry", "bordercolor") == theme.WINDOW_BG
    assert s.lookup("Locked.TEntry", "bordercolor", ["focus"]) == theme.BORDER   # Tab で入ったときは灰色の枠
