"""オートコンプリート（Excel と同じ動き）の試験。

欄に字を入れる（キーでも日本語入力でも、最後は欄に字が入る）と補うことを確かめる。キーを離した出来事には頼らない
（2026-11-09 班長指摘：日本語入力では、キーを離した出来事で確かめる作りが効かなかった）。
"""
import tkinter as tk
from tkinter import ttk

import pytest

from va_case.common.ui import autocomplete as ac
from conftest import reset_root

CANDIDATES = ["東京地方裁判所", "東京高等裁判所", "大阪地方裁判所", "Abc商店"]


def test_unique_completion():
    assert ac.unique_completion("大阪", CANDIDATES) == "大阪地方裁判所"
    assert ac.unique_completion("東京", CANDIDATES) is None          # 2つあるあいだは補わない
    assert ac.unique_completion("東京地", CANDIDATES) == "東京地方裁判所"
    assert ac.unique_completion("abc", CANDIDATES) == "Abc商店"       # 大文字・小文字は問わない
    assert ac.unique_completion("大阪地方裁判所", CANDIDATES) is None  # もう全部入っている
    assert ac.unique_completion("", CANDIDATES) is None


def test_column_values_newest_first_and_lines():
    rows = [["a", "甲\n乙"], ["b", "丙"], ["c", "甲"]]
    assert ac.column_values(rows, 1, split_lines=True) == ["甲", "丙", "乙"]
    assert ac.column_values(rows, 0) == ["c", "b", "a"]


@pytest.fixture(scope="module")
def root(tk_root):   # Tk は試験の全体で1つ（conftest の tk_root）。この試験の後で、作った部品を片付ける
    r = tk_root
    r.withdraw()
    yield r
    reset_root(r)


def type_into(root, widget, text):
    """打った字を、ふつうの入力と同じように入れる（選んである部分は置き換わる）。日本語入力の確定も、最後は同じく
    欄に字が入る。"""
    if isinstance(widget, tk.Text):
        if widget.tag_ranges("sel"):
            widget.delete("sel.first", "sel.last")
    elif widget.selection_present():
        widget.delete("sel.first", "sel.last")
    widget.insert("insert", text)
    root.update()


def test_entry_completes_and_selects_rest(root):
    var = tk.StringVar()
    e = ttk.Entry(root, textvariable=var)
    calls = []
    ac.attach_entry(e, lambda: CANDIDATES, on_complete=lambda: calls.append(1))
    type_into(root, e, "東京")                       # 日本語入力で「東京」と確定した
    assert e.get() == "東京" and not calls           # まだ決まらない
    type_into(root, e, "地")
    assert e.get() == "東京地方裁判所" and calls == [1] and var.get() == "東京地方裁判所"
    assert e.selection_get() == "方裁判所"           # 補った部分は選ばれている
    type_into(root, e, "方")                         # 続けて打つと、補った部分と置き換わり、また補う
    assert e.get() == "東京地方裁判所" and e.selection_get() == "裁判所"
    e.delete("sel.first", "sel.last")               # Backspace で補った部分を消す
    root.update()
    assert e.get() == "東京地方"                       # 消した後は補わない
    var.set("")                                      # 別の行を出した（変数から入れた）
    root.update()
    type_into(root, e, "大阪")
    assert e.get() == "大阪地方裁判所"
    e.delete(0, "end")
    e.insert(0, "x")
    e.icursor(0)
    type_into(root, e, "大")                          # 途中に入れたときは補わない
    assert e.get() == "大x"


def test_disabled_entry_is_left_alone(root):
    e = ttk.Entry(root)
    ac.attach_entry(e, lambda: CANDIDATES)
    e.insert(0, "大阪")
    e.configure(state="readonly")
    root.update()
    assert e.get() == "大阪"


def test_text_completes_per_line(root):
    t = tk.Text(root, height=2)
    ac.attach_text(t, lambda: ["弁護士 己野六郎", "弁護士 庚田七郎"])
    type_into(root, t, "弁護士 己")
    assert t.get("1.0", "end-1c") == "弁護士 己野六郎"
    t.tag_remove("sel", "1.0", "end")
    t.mark_set("insert", "end-1c")
    t.insert("insert", "\n")                          # 次の行へ
    root.update()
    type_into(root, t, "弁護士 庚")
    assert t.get("1.0", "end-1c") == "弁護士 己野六郎\n弁護士 庚田七郎"


def test_zenkaku_typed_completes_to_candidate_spelling(root):
    """日本語入力のまま打った全角の「０６」でも、半角で入っている「06-1111-1111」を補い、書き方もそろえる。"""
    assert ac.unique_completion("０６", ["06-1111-1111", "03-0000-0001"]) == "06-1111-1111"
    e = ttk.Entry(root)
    ac.attach_entry(e, lambda: ["06-1111-1111", "03-0000-0001"])
    type_into(root, e, "０６")
    assert e.get() == "06-1111-1111" and e.selection_get() == "-1111-1111"
    t = tk.Text(root, height=2)
    ac.attach_text(t, lambda: ["ABC法律事務所"])
    type_into(root, t, "ａｂ")
    assert t.get("1.0", "end-1c") == "ABC法律事務所"


def test_enter_accepts_completion(root):
    """補った後に Enter を押すと、選んである部分が外れ、カーソルが最後へ行く（2026-11-09 班長指摘）。
    キーの出来事は入力先の欄にしか届かないので、窓を出して欄に入力先を移してから送る。"""
    win = tk.Toplevel(root)
    e = ttk.Entry(win)
    t = tk.Text(win, height=2)
    e.pack()
    t.pack()
    win.update()
    ac.attach_entry(e, lambda: CANDIDATES)
    ac.attach_text(t, lambda: ["弁護士 己野六郎"])
    e.focus_force()
    root.update()
    type_into(root, e, "大阪")
    assert e.selection_present()
    e.event_generate("<Return>")
    root.update()
    assert not e.selection_present() and e.index("insert") == len("大阪地方裁判所") and e.get() == "大阪地方裁判所"
    t.focus_force()
    root.update()
    type_into(root, t, "弁護士 己")
    assert t.tag_ranges("sel")
    t.event_generate("<Return>")
    root.update()
    assert not t.tag_ranges("sel") and t.get("1.0", "end-1c") == "弁護士 己野六郎"   # この Enter では改行しない
    win.destroy()


def test_enter_clears_selection_and_tab_does_not_select_all(root):
    """全体が選ばれていても Enter で外す。Tab で入っても全体を選ばない（相手先から自動で入った電話番号。
    2026-11-09 班長指摘）。"""
    win = tk.Toplevel(root)
    a, b = ttk.Entry(win), ttk.Entry(win)
    a.pack()
    b.pack()
    b.insert(0, "06-1111-1111")
    win.update()
    ac.attach_entry(b, lambda: [])
    a.focus_force()
    root.update()
    b.focus_force()
    root.update()
    b.selection_range(0, "end")                     # 全体が選ばれた状態（クリックなど）
    b.event_generate("<Return>")
    root.update()
    assert not b.selection_present() and b.index("insert") == len("06-1111-1111")
    a.focus_force()
    root.update()
    a.event_generate("<Tab>")                       # Tab で入っても、全体を選ばない（2026-11-09 班長指摘）
    root.update()
    assert root.focus_get() == b and not b.selection_present() and b.index("insert") == len("06-1111-1111")
    win.destroy()


def test_combobox_completes_too(root):
    """選ぶ欄（ttk.Combobox）にも付けられる（VA Filing の事件呼名。2026-11-12 班長指示）。"""
    var = tk.StringVar()
    box = ttk.Combobox(root, textvariable=var, values=["民法（文献）", "甲野太郎（貸金）", "甲野太郎（離婚）"])
    ac.attach_entry(box, lambda: list(box.cget("values")))
    type_into(root, box, "民法")
    assert box.get() == "民法（文献）" and box.selection_get() == "（文献）"
    box.delete(0, "end")
    root.update()
    type_into(root, box, "甲野")
    assert box.get() == "甲野"                        # 2つあるあいだは補わない
    type_into(root, box, "太郎（離")
    assert box.get() == "甲野太郎（離婚）"
