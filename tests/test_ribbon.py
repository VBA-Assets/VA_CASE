"""リボン（VA Document と同じ形。2026-11-13 班長指示「リボンのコマンドボタンをVA Documentのように変更」）の試験。"""
from tkinter import ttk

import pytest

from va_case.common.ui import theme
from va_case.common.ui.icons import BUTTON_ICONS, ICON_DIR, IconSet, icon_name
from va_case.common.ui.ribbon import Ribbon
from conftest import reset_root


@pytest.fixture(scope="module")
def root(tk_root):   # Tk は試験の全体で1つ（conftest の tk_root）。この試験の後で、作った部品を片付ける
    r = tk_root
    r.deiconify()
    theme.apply_theme(r)
    yield r
    reset_root(r)


def test_every_button_icon_has_images():
    for name in set(BUTTON_ICONS.values()):
        assert (ICON_DIR / f"{name}.png").exists() and (ICON_DIR / f"{name}_disabled.png").exists(), name
    assert (ICON_DIR / "LICENSE").exists()                      # Fluent UI System Icons（MIT License）
    assert icon_name("新しい事件…") == "document_add"            # 「…」は除いて引く


def test_ribbon_groups_and_buttons(root):
    icons = IconSet(root)
    rb = Ribbon(root, icons)
    rb.pack(fill="x")
    g = rb.group("編集")
    big = g.large("編集を始める", lambda: None, style="RibbonEdit.TButton")
    small = g.small("最新を読み込む", lambda: None)
    g2 = rb.group("記録")
    gone = g2.small("削除", lambda: None)
    root.update()
    assert str(big.cget("compound")) == "top" and str(small.cget("compound")) == "left"
    assert big.cget("image") and small.cget("image")
    assert str(big.cget("takefocus")) in ("0", "False") and str(small.cget("style")) == "Ribbon.TButton"
    gone.state(["disabled"])                                    # 押せないときは灰色のアイコン（image の disabled の指定）
    assert "disabled" in str(gone.cget("image"))
    assert [g.title for g in rb.groups] == ["編集", "記録"]
    rb.reflow(60)                                               # 狭いときは、組を次の段に送る
    root.update()
    assert g.winfo_manager() == "grid" and g2.grid_info()["in"] != g.grid_info()["in"]


def test_tooltips(root):
    """マウスを重ねたときの説明書き（2026-11-13 班長指示「マウスオーバーした時に説明を表示」「カードの実行ボタンにも
    説明書きを付ける」）。説明は、文字列か、いまの説明を返す関数。"""
    from va_case.common.ui.tooltip import Tooltip, _by_sentence
    rb = Ribbon(root, IconSet(root))
    rb.pack(fill="x")
    state = {"editing": False}
    g = rb.group("編集")
    edit = g.large("編集を始める", lambda: None, tip=lambda: "終える" if state["editing"] else "始める")
    plain = g.small("最新を読み込む", lambda: None)
    assert edit.tooltip.current_text() == "始める"
    state["editing"] = True
    assert edit.tooltip.current_text() == "終える"            # 字が変わるボタンは、説明も変わる
    assert not hasattr(plain, "tooltip")                       # 説明を渡さなければ付けない
    root.update()
    edit.tooltip.show()
    assert edit.tooltip._win is not None
    edit.tooltip.hide()
    assert edit.tooltip._win is None
    assert _by_sentence("一つ。二つ。") == "一つ。\n二つ。"       # 文ごとに改行する
    b = ttk.Button(root, text="保管する")
    assert Tooltip(b, "").current_text() == ""                # 空の説明は出さない


def test_card_button_tip_above(root):
    """カードのボタンの説明は、ボタンの上に出す（2026-11-13 班長指示「カードのボタンの説明は、上側に表示」）。"""
    from va_case.common.ui.tooltip import Tooltip
    b = ttk.Button(root, text="保管する")
    b.pack(pady=(200, 0))
    root.update()
    t = Tooltip(b, "説明", above=True)
    t.show()
    root.update()
    assert t._win.winfo_rooty() + t._win.winfo_height() <= b.winfo_rooty()
    t.hide()
    b.destroy()


def test_end_edit_has_its_own_icon():
    """［編集を終える］は、［編集を始める］（鉛筆）と別のアイコン（斜線の入った鉛筆。2026-11-13 班長指示）。"""
    assert icon_name("編集を始める") == "edit" and icon_name("編集を終える") == "edit_off"
