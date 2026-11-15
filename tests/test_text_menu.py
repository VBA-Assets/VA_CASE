"""入力欄の右クリックのメニュー（コピー・貼り付け。2026-11-15 班長指示）の試験。氏名は架空。"""
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace

import pytest

from va_case.common.ui import text_menu, theme
from va_case.common.ui.dialogs import WrappedEntry


@pytest.fixture(scope="module")
def root():
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("画面がない環境")
    r.withdraw()
    theme.apply_theme(r)
    text_menu.install(r)
    yield r
    r.destroy()


@pytest.fixture
def shown(monkeypatch):
    """出したメニュー（画面には出さない）。"""
    out = []
    monkeypatch.setattr(tk.Menu, "tk_popup", lambda self, x, y, entry="": out.append(self))
    return out


def right_click(w):
    return text_menu._field_menu(SimpleNamespace(widget=w, x_root=0, y_root=0))


def labels(menu):
    return [(menu.entrycget(i, "label"), str(menu.entrycget(i, "state"))) for i in range(menu.index("end") + 1)]


def test_bound_to_field_classes(root):
    for cls in ("TEntry", "TCombobox", "Text"):
        assert root.bind_class(cls, "<Button-3>")


def test_entry_copy_and_paste(root, shown):
    var = tk.StringVar(value="甲野太郎")
    e = ttk.Entry(root, textvariable=var)
    e.selection_range(0, 2)
    root.clipboard_clear()
    root.clipboard_append("乙山")
    assert right_click(e) == "break"
    menu = shown[-1]
    assert labels(menu) == [("コピー", "normal"), ("貼り付け", "normal")]
    e.selection_clear()                    # メニューを開いて選んだ字が外れても、右クリックしたときの範囲で
    menu.invoke(0)
    assert root.clipboard_get() == "甲野"
    root.clipboard_clear()
    root.clipboard_append("乙山\n次郎")      # 何行かは、1行につなげる（Ctrl+V と同じ）
    e.selection_range(0, 2)
    right_click(e)
    e.selection_clear()
    menu.invoke(1)
    assert var.get() == "乙山次郎太郎"        # 選んでいた「甲野」を置き換えた
    keys = []
    e.bind("<KeyRelease>", lambda ev: keys.append(ev.keysym))
    e.icursor("end")
    root.deiconify()                       # キーの出来事は、入力先の欄に届く（隠した窓では届かない）
    e.pack()
    e.focus_force()                        # 右クリックした窓は前にある（ほかのアプリが前にあると、キーが届かない）
    root.update()
    right_click(e)
    menu.invoke(1)
    root.update()
    assert var.get() == "乙山次郎太郎乙山次郎" and keys == ["v"]   # キーを離したときの処理も働く
    e.destroy()
    root.withdraw()


def test_readonly_entry_has_no_paste(root, shown):
    """閲覧モードの欄・番号などの読み取り専用の欄：コピーだけ。選んでいなければ押せない。"""
    var = tk.StringVar(value="12")
    e = ttk.Entry(root, textvariable=var)
    e.configure(state="readonly")
    right_click(e)
    assert labels(shown[-1]) == [("コピー", "disabled")]
    e.selection_range(0, "end")
    right_click(e)
    assert labels(shown[-1]) == [("コピー", "normal")]


def test_combobox(root, shown):
    c = ttk.Combobox(root, values=["委任", "顧問"])
    c.set("委任")
    c.selection_range(0, "end")
    right_click(c)
    assert labels(shown[-1]) == [("コピー", "normal"), ("貼り付け", "normal")]
    c.configure(state="readonly")           # 選ぶだけの欄には貼り付けない
    right_click(c)
    assert labels(shown[-1]) == [("コピー", "normal")]


def test_text_copy_and_paste(root, shown):
    t = tk.Text(root)
    t.insert("1.0", "東京都千代田区\n一丁目")
    t.tag_add("sel", "1.0", "1.3")
    root.clipboard_clear()
    root.clipboard_append("大阪府")
    right_click(t)
    menu = shown[-1]
    assert labels(menu) == [("コピー", "normal"), ("貼り付け", "normal")]
    menu.invoke(0)
    assert root.clipboard_get() == "東京都"
    root.clipboard_clear()
    root.clipboard_append("大阪府")
    right_click(t)
    t.tag_remove("sel", "1.0", "end")
    menu.invoke(1)
    assert t.get("1.0", "end-1c") == "大阪府千代田区\n一丁目"
    t.configure(state="disabled")          # 閲覧モード：コピーだけ
    t.tag_add("sel", "2.0", "2.3")
    right_click(t)
    assert labels(menu) == [("コピー", "normal")]
    menu.invoke(0)
    assert root.clipboard_get() == "一丁目"


def test_wrapped_entry(root, shown):
    var = tk.StringVar(value="甲野太郎（貸金）.pdf")
    w = WrappedEntry(root, var, width=10)
    w.configure(state="readonly")
    right_click(w)
    assert labels(shown[-1]) == [("コピー", "disabled")]
    w.configure(state="normal")
    root.clipboard_clear()
    root.clipboard_append("訴状")
    w.mark_set("insert", "1.8")
    right_click(w)
    shown[-1].invoke(1)
    root.update()
    assert var.get() == "甲野太郎（貸金）訴状.pdf"


def test_paste_disabled_when_clipboard_empty(root, shown):
    e = ttk.Entry(root)
    root.clipboard_clear()
    right_click(e)
    assert labels(shown[-1]) == [("コピー", "disabled"), ("貼り付け", "disabled")]
