"""一覧の何行かを選ぶ操作とコピー、閲覧モードの選択の欄（2026-11-10 班長決定）の試験。氏名は架空。"""
import tkinter as tk
from types import SimpleNamespace
from tkinter import ttk

import pytest

from va_case.common.ui import theme
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


ROWS = {
    "1": {"番号": "1", "氏名": "甲野太郎", "住所": "東京都千代田区一丁目1番1号"},
    "2": {"番号": "2", "氏名": "乙山次郎\n丙川三郎", "住所": "大阪府"},       # 何人か（セルの中の改行）
    "3": {"番号": "3", "氏名": '丁原"四郎"', "住所": ""},
}


def make_app(root):
    app = SharedApp.__new__(SharedApp)
    app.root = root
    tree = ttk.Treeview(root, columns=("番号", "氏名", "住所"), show="headings", selectmode="browse")
    for c in ("番号", "氏名", "住所"):
        tree.heading(c, text=c)
    tree["displaycolumns"] = ("氏名", "番号")                  # 出している列だけ、出している順に
    for key, row in ROWS.items():
        lines = row["氏名"].split("\n")
        tree.insert("", "end", iid=key, values=(row["番号"], lines[0], row["住所"]), open=True)
        for j, line in enumerate(lines[1:], start=1):           # 折り返した2行目からは子の行
            tree.insert(key, "end", iid=f"{key}#{j}", values=("", line, ""), open=True)
    app.tree = tree
    app._cells = {k: dict(v) for k, v in ROWS.items()}
    app._range = None
    app.work_label = ttk.Label(root)
    return app


def test_select_range_includes_child_rows_and_keeps_current_row(root):
    app = make_app(root)
    app._select_item("1")
    app._select_range("1", "3", focus="1")
    assert set(app.tree.selection()) == {"1", "2", "2#1", "3"}
    assert app.selected_keys() == ["1", "2", "3"]
    assert app.selected_key() == "1"                             # 入力欄に出すのは、いまの行
    app._extend_by_key(-1)                                       # Shift＋上：端を1行戻す
    assert app.selected_keys() == ["1", "2"]
    app._select_item("3")                                        # ふつうに選び直すと、1行に戻る
    assert app.selected_keys() == ["3"] and app._range is None


def test_copy_rows_as_tab_separated_text(root):
    app = make_app(root)
    app._select_range("1", "3", focus="1")
    app.copy_rows()
    assert root.clipboard_get() == ('甲野太郎\t1\r\n"乙山次郎\n丙川三郎"\t2\r\n"丁原""四郎"""\t3\r\n')
    app.copy_rows(header=True)
    assert root.clipboard_get().startswith("氏名\t番号\r\n甲野太郎\t1\r\n")
    assert "3 行" in app.work_label.cget("text")


# ------------------------------------------------------------ セルの中の文字を選ぶ（2026-11-13 班長決定「案Aを適用」）

def shown_app(root):
    app = make_app(root)
    root.deiconify()
    app.tree.pack()
    app.tree.column("氏名", width=200)
    app._cell = None
    app.bind_cell_text(app.tree)
    root.update()
    return app


def test_cell_text_select_and_copy(root):
    app = shown_app(root)
    app._cell_show("2", "氏名")                                   # 2行に折り返したセル（子の行も）
    t = app._cell_text
    assert t.winfo_manager() == "place" and t.get("1.0", "end-1c") == "乙山次郎\n丙川三郎"
    assert str(t.cget("state")) == "disabled"                  # 直せない
    t.tag_add("sel", "1.2", "2.2")                             # 「次郎」から「丙川」まで
    assert app.cell_text_selected() == "次郎\n丙川"              # セルの中の改行は、もとの値の改行
    app.copy_selection()                                       # Ctrl+C
    assert root.clipboard_get() == "次郎\n丙川" and "選んだ文字" in app.work_label.cget("text")
    app.cell_text_hide()
    assert t.winfo_manager() == "" and app.cell_text_selected() is None
    app._select_item("1")
    app.copy_selection()                                       # 文字を選んでいなければ、今までどおり行
    assert root.clipboard_get() == "甲野太郎\t1\r\n"
    root.withdraw()


def test_cell_text_colors_follow_the_row(root):
    app = shown_app(root)
    app.tree.tag_configure("closed", foreground="#7f7f7f")
    app.tree.item("3", tags=("closed",))
    app._cell_show("3", "氏名")
    assert app._cell_text.cget("fg") == "#7f7f7f"
    app.tree.selection_set("3")
    app._cell_recolor()
    # 選んだ行でも、字は印の色のまま（2026-11-13 班長指摘「黒字で表示されている」。それまでは黒字）
    assert app._cell_text.cget("bg") == theme.PRESSED_BG and app._cell_text.cget("fg") == "#7f7f7f"
    app.cell_text_hide()
    root.withdraw()


def test_display_map_skips_wrap_breaks():
    from va_case.common.ui.cell_text import _display_map
    m = _display_map("甲野 太郎（貸金）", ["甲野", "太郎（貸", "金）"])  # 空白のところと、字の途中で折り返した
    assert m == [0, 1, None, 3, 4, 5, 6, None, 7, 8]
    assert _display_map("a\nb", ["a", "b"]) == [0, 1, 2]          # もとの改行


def test_expand_selection_keeps_several_rows(root):
    app = make_app(root)
    app.tree.selection_set(("1", "2#1"))                         # 子の行だけを選んだ
    app.tree.focus("2#1")
    app.expand_selection(app.tree)
    assert set(app.tree.selection()) == {"1", "2", "2#1"} and app.tree.focus() == "2"


def test_choice_field_becomes_selectable_text_when_read_only(root):
    win = tk.Toplevel(root)
    var = tk.StringVar(value="A:未了")
    first = ttk.Entry(win)
    combo = ttk.Combobox(win, textvariable=var, values=["A:未了", "C:終了"])
    last = ttk.Entry(win)
    for i, w in enumerate((first, combo, last)):
        w.grid(row=i, column=0)
    mirror = theme.show_choice(combo, None, True)                # 閲覧モード：文字を選べる読み取り専用の欄に
    win.update()
    assert not combo.winfo_manager() and mirror.winfo_manager() == "grid"
    assert str(mirror.cget("state")) == "readonly" and mirror.get() == "A:未了"
    assert int(mirror.grid_info()["row"]) == 1                   # ドロップダウンと同じ場所
    assert first.tk_focusNext() is mirror and mirror.tk_focusNext() is last   # Tab の順も同じ
    mirror.selection_range(0, 1)
    mirror.event_generate("<<Copy>>")
    assert root.clipboard_get() == "A"
    theme.show_choice(combo, "readonly", True)                   # 編集モード：ドロップダウンに戻す
    assert combo.winfo_manager() == "grid" and not mirror.winfo_manager()
    assert str(combo.cget("state")) == "readonly"
    var.set("C:終了")
    assert theme.show_choice(combo, None, True).get() == "C:終了"   # 同じ値を出す
    win.destroy()


def test_cell_text_appears_only_when_dragging_in_a_cell(root):
    """マウスを載せただけでは欄を重ねず（ちらつかない。2026-11-13 班長指摘）、セルの中でなぞったときに重ねて選ぶ。"""
    from va_case.common.ui.cell_text import SimpleEvent
    app = shown_app(root)
    app._drag = None
    x, y, w, h = app.tree.bbox("1", "氏名")
    app._cell_tree_press(SimpleEvent(x=x + 6, y=y + 5))
    assert app._cell is None                                   # 押しただけでは重ねない
    assert app.cell_drag(SimpleEvent(x=x + 60, y=y + 5)) is True
    assert app._cell_text.winfo_manager() == "place" and app.cell_text_selected()
    app._cell_tree_release(SimpleEvent(x=x + 60, y=y + 5))
    assert app._cell["pinned"]                                 # 選んだ文字は、離した後も残す
    app._cell_tree_press(SimpleEvent(x=x + 6, y=y + 5))
    assert app.cell_drag(SimpleEvent(x=x + 6, y=y + 3 * h)) is False   # セルの外へ：何行かを選ぶ動き
    assert app._cell is None
    root.withdraw()


def test_cell_text_shift_arrows_change_the_range(root):
    """文字を選んだ後、Shift+左右の矢印キーで、なぞり終えた側の端を1字ずつ動かす（2026-11-13 班長指示）。折り返しの
    改行は続けて越える。文字を選んでいなければ、今までどおり一覧を横に動かす。"""
    from va_case.common.ui.cell_text import SimpleEvent
    app = shown_app(root)
    app._drag = None
    t = app._cell_text
    x, y, w, h = app.tree.bbox("2", "氏名")
    app._cell_tree_press(SimpleEvent(x=x + 2, y=y + 5))       # 「乙山次郎」の先頭から
    app.cell_drag(SimpleEvent(x=x + 2 + t.tk.call("font", "measure", app._cell_font_obj(), "乙山"), y=y + 5))
    app._cell_tree_release(SimpleEvent(x=x + 60, y=y + 5))
    assert app.cell_text_selected() == "乙山"
    assert app._cell_shift_arrow(1) == "break" and app.cell_text_selected() == "乙山次"
    app.cell_extend_by_char(1)
    assert app.cell_text_selected() == "乙山次郎"
    app.cell_extend_by_char(1)                                 # 改行を越えて、次の行の1字目まで
    assert app.cell_text_selected() == "乙山次郎\n丙"
    for _ in range(2):
        app.cell_extend_by_char(-1)                            # 「丙」を外し、改行を越えて「郎」を外す
    assert app.cell_text_selected() == "乙山次"
    for _ in range(5):
        app.cell_extend_by_char(-1)                            # 選び始めの位置（左端）で止まる
    assert app.cell_text_selected() is None and app._cell is not None   # 範囲が空になっても、続けて広げられる
    for _ in range(20):
        app.cell_extend_by_char(1)                             # 右端で止まる
    assert app.cell_text_selected() == "乙山次郎\n丙川三郎"
    app.cell_text_hide()
    app.H_STEP = 40
    app.tree.column("住所", width=900)
    app.tree["displaycolumns"] = ("氏名", "番号", "住所")
    root.update()
    before = app.tree.xview()[0]
    assert app._cell_shift_arrow(1) == "break" and app.tree.xview()[0] >= before   # 選んでいない：横に動かす
    root.withdraw()


def test_update_list_row_keeps_place_and_selection(root):
    """直している値を一覧に出す（2026-11-13 班長決定「A 青字のまま一覧に出す」）：その行の字だけを替え、位置・選択・
    縞はそのまま。折り返しの行の数が変われば、子の行を足す・除く（選んでいれば、足した子の行も選ぶ）。"""
    app = shown_app(root)
    tree = app.tree
    app.begin_wrapped_list()
    tree.delete(*tree.get_children())
    for key, row in ROWS.items():
        app.insert_wrapped(key, ("番号", "氏名", "住所"), (row["番号"], row["氏名"], row["住所"]), [])
    tree.item("2", tags=["band"])
    tree.item("2#1", tags=["band"])
    app._select_item("1")
    order = list(tree.get_children())
    app.update_list_row("1", ("番号", "氏名", "住所"), ("1", "甲野花子\n甲野一郎", "東京都"), ["draft"])
    assert list(tree.get_children()) == order                      # 位置は同じ
    assert tree.set("1", "氏名") == "甲野花子" and tree.set("1#1", "氏名") == "甲野一郎"   # 2行になった
    assert set(tree.selection()) == {"1", "1#1"}                   # 足した子の行も選ぶ
    assert tree.item("1", "tags") == ("draft",) and app._cells["1"]["氏名"] == "甲野花子\n甲野一郎"
    app.update_list_row("2", ("番号", "氏名", "住所"), ("2", "乙山次郎", "大阪府"), ["draft"])
    assert not tree.exists("2#1") and tree.set("2", "氏名") == "乙山次郎"      # 1行に戻った
    assert tree.item("2", "tags") == ("draft", "band")             # 縞の地の色は残す
    app.update_list_row("2", ("番号", "氏名", "住所"), ("2", "乙山次郎", "大阪府"))
    assert tree.item("2", "tags") == ("draft", "band")             # tags を渡さなければ、字の色もそのまま
    root.withdraw()


def test_copy_button_and_list_menu(root, monkeypatch):
    """リボンの［コピー］で、選んでいる行を見出しを付けずにコピーする（2026-11-14 班長指示）。一覧の右クリックのメニュー
    は、セルの中で選んだ文字の「コピー」だけ（2026-11-15 班長指示。行のコピーは出さない）。"""
    app = make_app(root)
    app._show_job = None
    app._select_range("1", "2", focus="1")
    app.copy_selected_rows()
    assert root.clipboard_get() == '甲野太郎\t1\r\n"乙山次郎\n丙川三郎"\t2\r\n'     # 見出しなし・選んだ2件
    shown = []
    monkeypatch.setattr(tk.Menu, "tk_popup", lambda self, x, y, entry="": shown.append(self))
    for w in root.pack_slaves():                                   # ほかの試験の一覧は外す（セルが見えるように）
        w.pack_forget()
    app = shown_app(root)
    for w in (app.tree, app._cell_text):
        assert w.bind("<Button-3>")
    app._cell_menu(SimpleNamespace(x_root=0, y_root=0))           # 文字を選んでいない
    menu = shown[-1]
    assert menu.index("end") == 0 and menu.entrycget(0, "label") == "コピー"
    assert menu.entrycget(0, "state") == "disabled"
    assert app._cell_show("2", "氏名")
    app._cell_text.tag_add("sel", "1.2", "2.2")                    # 「次郎」から「丙川」まで
    app._cell_menu(SimpleNamespace(x_root=0, y_root=0))
    assert menu.index("end") == 0 and menu.entrycget(0, "state") == "normal"   # 「コピー」だけ（貼り付けはない）
    app.cell_text_hide()                                           # メニューを開いている間に外れても
    menu.invoke(0)
    assert root.clipboard_get() == "次郎\n丙川" and "選んだ文字" in app.work_label.cget("text")
    root.withdraw()
