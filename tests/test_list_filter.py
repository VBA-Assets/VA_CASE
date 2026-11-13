"""一覧のフィルタ（2026-11-10 班長決定「A Excel に近い形」）の試験。氏名は架空。"""
import tkinter as tk
from tkinter import ttk

import pytest

from va_case.common.search import Query
from va_case.common.ui import theme
from va_case.common.ui.list_view import FilterPopup
from va_case.common.ui.shared_app import SharedApp


@pytest.fixture(scope="module")
def root():
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("画面がない環境")
    r.withdraw()
    theme.apply_theme(r)
    yield r
    r.destroy()


COLUMNS = ("番号", "現況", "相手方氏名")
ROWS = [
    ("1", "A:未了", "乙山次郎\n丙川三郎"),      # 相手方2人（セルの中の改行）
    ("2", "C:終了", "乙山次郎"),
    ("3", "A:未了", ""),                         # 空のセル
    ("4", "B:精算管理", "丁原四郎"),
]


class FakeApp(SharedApp):
    """一覧の作り直しだけを持つ画面の代わり。"""

    def __init__(self, root):
        self.root = root
        self.data = object()
        self.query = Query("")
        self.init_list_state()
        self.tree = ttk.Treeview(root, columns=COLUMNS, show="headings")
        for c in COLUMNS:
            self.tree.heading(c, text=c)
        self.search_var = tk.StringVar()
        self.clear_narrow_button = ttk.Button(root, text="すべてを表示")

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        self._filter_rows = []
        self.shown = []
        for row in ROWS:
            if self.query.matches(list(row), list(row)) and self.passes_filter(COLUMNS, row):
                self.shown.append(row[0])
                self.tree.insert("", "end", iid=row[0], values=row)
        self.mark_filtered_columns()

    def _focus_table(self):
        pass


def test_filter_by_value_and_multi_line_cells(root):
    app = FakeApp(root)
    app.refresh()
    assert app.filter_values("相手方氏名") == ["丁原四郎", "丙川三郎", "乙山次郎", ""]   # 1行ずつ・空白は最後
    app.set_filter("相手方氏名", {"乙山次郎"}, app.filter_values("相手方氏名"))
    assert app.shown == ["1", "2"]                                   # 2人のうち1人が当てはまれば出す
    assert app.tree.heading("相手方氏名", "text") == "相手方氏名 ▼"
    assert app.clear_narrow_button.instate(["!disabled"])
    assert app.narrowed_label() == "フィルタの結果"


def test_several_columns_and_values_follow_other_filters(root):
    app = FakeApp(root)
    app.refresh()
    app.set_filter("現況", {"A:未了"}, app.filter_values("現況"))
    assert app.shown == ["1", "3"]
    # 相手方氏名の値の一覧は、現況のフィルタに当てはまる行の値だけ（Excel と同じ）
    assert app.filter_values("相手方氏名") == ["丙川三郎", "乙山次郎", ""]
    app.set_filter("相手方氏名", {""}, app.filter_values("相手方氏名"))   # 空白だけ
    assert app.shown == ["3"]                                          # 何列かは、すべてに当てはまる行だけ
    app.clear_narrowing()
    assert app.shown == ["1", "2", "3", "4"] and app.filters == {}
    assert app.tree.heading("現況", "text") == "現況" and app.clear_narrow_button.instate(["disabled"])


def test_choosing_all_values_removes_the_filter_and_search_works_together(root):
    app = FakeApp(root)
    app.refresh()
    app.set_filter("現況", {"A:未了"}, app.filter_values("現況"))
    values = app.filter_values("現況")
    app.set_filter("現況", set(values), values)                       # すべて選んだら、その列のフィルタは外す
    assert "現況" not in app.filters and app.shown == ["1", "2", "3", "4"]
    app.query = Query("乙山")
    app.set_filter("現況", {"C:終了"}, app.filter_values("現況"))
    assert app.shown == ["2"] and app.narrowed_label() == "検索・フィルタの結果"


def test_clear_narrowing_button(root):
    """「すべてを表示」は、検索かフィルタで絞っている間だけ使え、押すと両方を外す（2026-11-11 班長決定）。"""
    app = FakeApp(root)
    app.refresh()
    assert app.clear_narrow_button.instate(["disabled"])              # 絞っていない
    app.query = Query("乙山")
    app.refresh()
    assert app.clear_narrow_button.instate(["!disabled"])             # 検索だけ
    app.query = Query("")
    app.set_filter("現況", {"C:終了"}, app.filter_values("現況"))
    assert app.clear_narrow_button.instate(["!disabled"])             # フィルタだけ
    app.search_var.set("乙山")
    app.query = Query("乙山")
    app.set_filter("相手方氏名", {"乙山次郎"}, app.filter_values("相手方氏名"))
    assert app.shown == ["2"]
    app.clear_narrowing()                                              # 両方を一度に外す
    assert app.shown == ["1", "2", "3", "4"] and app.filters == {} and app.query.empty
    assert app.search_var.get() == "" and app.clear_narrow_button.instate(["disabled"])
    assert app.tree.heading("現況", "text") == "現況"


def test_popup_toggle_search_and_ok(root):
    got = []
    values = ["A:未了", "B:精算管理", "C:終了", ""]
    p = FilterPopup(root, "現況", values, set(values), got.append)
    root.update()
    assert [p.list.item(i, "text") for i in p.list.get_children()][-1] == "☑  （空白）"
    p._toggle("1")                                                     # B:精算管理を外す
    assert p.list.item("1", "text") == "☐  B:精算管理"
    p.search_var.set("終了")                                          # 値を探す欄で絞る
    root.update()
    assert p.list.get_children() == ("2",)
    p._set_all(False)                                                  # 見えている値（C:終了）だけを外す
    p.search_var.set("")
    root.update()
    assert p.checked == {"A:未了", ""}
    p._ok()
    assert got == [{"A:未了", ""}]


def test_popup_needs_at_least_one_value_and_can_clear(root):
    got = []
    p = FilterPopup(root, "現況", ["A:未了", "C:終了"], {"A:未了"}, got.append)
    root.update()
    p._set_all(False)
    assert p.ok_button.instate(["disabled"])                           # 何も選ばないと、1行も出なくなるため
    p._ok()
    assert got == []
    p._clear()                                                         # この列のフィルタを解除
    assert got == [None]
