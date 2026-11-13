"""入力欄の Ctrl+Z・Ctrl+Y（common/ui/undo.py。2026-11-12 班長決定）の試験。"""
import tkinter as tk
from tkinter import ttk

import pytest

from va_case.common.ui.undo import EditHistory


@pytest.fixture(scope="module")
def root():   # Tk は試験のファイルで1つだけ作る
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("画面がない環境")
    yield r
    r.destroy()


class Panel:
    """2つの1行の欄（a・b）と1つの何行かの欄（c）。b を打つと、a の「自動の値」も変わる（保管ファイル名のように）。"""

    def __init__(self, root):
        self.frame = ttk.Frame(root)
        self.frame.pack()
        self.vars = {"a": tk.StringVar(), "b": tk.StringVar()}
        self.a = ttk.Entry(self.frame, textvariable=self.vars["a"])
        self.b = ttk.Entry(self.frame, textvariable=self.vars["b"])
        self.c = tk.Text(self.frame, height=2, undo=False)
        for w in (self.a, self.b, self.c):
            w.pack()
        self.widgets = {"a": self.a, "b": self.b, "c": self.c}
        self.h = EditHistory(root, self.get, self.put, focus=lambda n: self.widgets[n].focus_set())
        for n, w in self.widgets.items():
            self.h.watch(w, n)
        for v in self.vars.values():
            v.trace_add("write", lambda *x: self.h.changed())
        self.c.bind("<<Modified>>", self._modified)

    def _modified(self, e):
        if self.c.edit_modified():
            self.c.edit_modified(False)
            self.h.changed()

    def get(self):
        return ({"a": self.vars["a"].get(), "b": self.vars["b"].get(), "c": self.c.get("1.0", "end-1c")}, None)

    def put(self, state):
        v = state[0]
        self.vars["a"].set(v["a"])
        self.vars["b"].set(v["b"])
        self.c.delete("1.0", "end")
        self.c.insert("1.0", v["c"])

    def values(self):
        return self.get()[0]


def type_into(root, widget, text):
    widget.focus_force()
    root.update()
    for ch in text:
        if isinstance(widget, tk.Text):
            widget.insert("end", ch)
        else:
            widget.insert("end", ch)
        root.update()


def test_typing_in_one_field_is_one_step(root):
    p = Panel(root)
    p.vars["a"].set("元")
    p.h.reset()
    type_into(root, p.a, "の値")
    assert p.values()["a"] == "元の値"
    p.h.undo()
    assert p.values()["a"] == "元"            # 続けて打った分は、1回で戻る
    assert not p.h.undo()                      # 出したときの値より前には戻らない
    p.h.redo()
    assert p.values()["a"] == "元の値"
    p.frame.destroy()


def test_steps_follow_fields_and_focus_moves(root):
    p = Panel(root)
    p.h.reset()
    type_into(root, p.a, "甲")
    type_into(root, p.b, "乙")
    type_into(root, p.c, "丙\n丁")
    type_into(root, p.a, "2")                 # 同じ欄でも、ほかの欄の後に打った分は別の1回
    assert p.values() == {"a": "甲2", "b": "乙", "c": "丙\n丁"}
    p.h.undo()
    assert p.values()["a"] == "甲"
    p.h.undo()
    assert p.values()["c"] == "" and root.focus_get() is p.c    # 戻した欄にカーソルが移る
    p.h.undo()
    assert p.values()["b"] == "" and root.focus_get() is p.b
    p.h.redo()
    assert p.values()["b"] == "乙"
    type_into(root, p.b, "x")                 # 戻した後に打つと、やり直せる分は捨てる
    assert not p.h.redo()
    p.frame.destroy()


def test_automatic_changes_go_with_the_typing(root):
    """打った欄と一緒に変わったほかの欄（自動で入る値）は、まとめて戻る。"""
    p = Panel(root)
    p.h.reset()
    p.b.focus_force()
    root.update()
    p.b.insert("end", "内容")
    p.vars["a"].set("自動の名前")             # 打った後に、自動で入る（KeyRelease の _update_name のように）
    root.update()
    p.h.undo()
    assert p.values() == {"a": "", "b": "", "c": ""}
    p.frame.destroy()


def test_keys_and_reset(root):
    p = Panel(root)
    p.h.reset()
    type_into(root, p.c, "メモ")
    p.c.event_generate("<Control-z>")          # 何行かの欄でも、入力欄全体の Ctrl+Z が働く
    root.update()
    assert p.values()["c"] == ""
    p.c.event_generate("<Control-y>")
    root.update()
    assert p.values()["c"] == "メモ"
    p.h.reset()                                 # ほかの行に移った（書き込んだ）ら、戻せない
    assert not p.h.undo()
    p.h.clear()
    type_into(root, p.a, "何も覚えない")
    assert not p.h.undo()
    p.frame.destroy()
