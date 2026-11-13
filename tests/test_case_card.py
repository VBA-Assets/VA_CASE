"""VA Case の下側のカード（2026-11-10 班長決定）の試験。氏名・住所はすべて架空。"""
import tkinter as tk

import pytest

from va_case.case import model as m
from va_case.case.card import CARD_LAYOUT, TEXT_FIELDS, CaseCard, row_values
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


def make_row(number, **values):
    row = m.blank_row(number)
    for k, v in values.items():
        row[m.COL[k]] = v
    return row


def make_card(root, rows, changes):
    card = CaseCard(root, on_change=lambda: changes.append(1), on_open=lambda name: None, rows=lambda: rows)
    card.pack()
    card.set_choices(m.empty_tables())
    root.update()
    return card


def test_layout_has_every_column_once():
    names = [n for _, ns in CARD_LAYOUT for n in ns]
    assert len(CARD_LAYOUT) == 4 and sorted(names) == sorted(m.CASE_COLUMNS)
    assert set(TEXT_FIELDS) <= set(names)


def test_put_and_values_round_trip(root):
    row = make_row("101", 現況="A:未了", 事件呼名="甲野太郎（貸金）", 相談年月日="2025-04-10",
                   相手方氏名="乙山次郎\n丙川三郎", データフォルダ="保管庫：個人一般/2026/101甲野太郎.zip")
    changes = []
    card = make_card(root, [row], changes)
    card.put("101", row_values(row))
    root.update()
    assert card.values() == row_values(row)
    assert card.values()["相談年月日"] == "R7.4.10"       # 日付は和暦で出す
    assert changes == []                                  # 出しただけでは、直した扱いにしない
    card.destroy()


def test_editable_follows_mode(root):
    row = make_row("101", 事件呼名="甲野太郎（貸金）")
    card = make_card(root, [row], [])
    card.put("101", row_values(row))
    card.set_editable(False)
    assert str(card.widgets["裁判所事件番号"].cget("state")) == "readonly"
    assert str(card.widgets["事件呼名"].cget("state")) == "disabled"
    assert str(card.widgets["相手方氏名"].cget("state")) == "disabled"
    card.set_editable(True)
    assert str(card.widgets["事件呼名"].cget("state")) == "normal"
    assert str(card.widgets["裁判所事件番号"].cget("state")) == "normal"
    assert str(card.widgets["事件番号"].cget("state")) == "normal"   # 事件番号も直せる（2026-11-11 班長指示）
    assert str(card.widgets["相手方氏名"].cget("state")) == "normal"
    card.put(None, {})                                    # 事件を選んでいないときは、編集モードでも直せない
    assert str(card.widgets["事件呼名"].cget("state")) == "disabled"
    # 「書き込む」「入力を戻す」のボタンはない（2026-11-12 班長決定。移るときに書き込み、Ctrl+Z で戻す）
    texts = []
    stack = [card]
    while stack:
        w = stack.pop()
        stack += w.winfo_children()
        try:
            texts.append(str(w.cget("text")))
        except Exception:
            pass
    assert "書き込む" not in texts and "入力を戻す" not in texts
    card.destroy()


def test_change_is_reported(root):
    row = make_row("101", 事件呼名="甲野太郎（貸金）")
    changes = []
    card = make_card(root, [row], changes)
    card.put("101", row_values(row))
    card.set_editable(True)
    card.widgets["事件呼名"].insert("end", "\n・控訴")       # 貼り付けた改行は除いて1行にする
    w = card.widgets["備考"]
    w.insert("1.0", "連絡は夕方")
    root.update()
    assert len(changes) >= 2
    assert card.values()["事件呼名"] == "甲野太郎（貸金）・控訴" and card.values()["備考"] == "連絡は夕方"
    card.destroy()


def test_agent_fills_address_from_earlier_case(root):
    earlier = make_row("101", 代理人="弁護士 己野六郎", 代理人住所="大阪府大阪市中央区一丁目1番1号",
                       代理人電話番号="06-1111-1111", 代理人FAX番号="06-1111-1112")
    now = make_row("102")
    card = make_card(root, [earlier, now], [])
    card.put("102", row_values(now))
    card.set_editable(True)
    card.widgets["代理人"].insert("1.0", "弁護士 己野六郎")
    card._agent_changed()
    assert card.value("代理人住所") == "大阪府大阪市中央区一丁目1番1号"
    assert card.value("代理人電話番号") == "06-1111-1111" and card.value("代理人FAX番号") == "06-1111-1112"
    card.set_editable(False)                              # 閲覧モードでは入れない
    card.put("102", row_values(now))
    card.widgets["代理人"].configure(state="normal")
    card.widgets["代理人"].insert("1.0", "弁護士 己野六郎")
    card._agent_changed()
    assert card.value("代理人住所") == ""
    card.destroy()


def test_field_heights(root):
    # 2026-11-10 班長指示：事件呼名は2行、備考は4行、代理人電話番号・FAX番号は1行の高さ
    card = make_card(root, [], [])
    heights = {n: int(card.widgets[n].cget("height")) for n in ("事件呼名", "備考", "代理人電話番号", "代理人FAX番号",
                                                                 "相談内容", "メールアドレス")}
    assert heights == {"事件呼名": 2, "備考": 4, "代理人電話番号": 1, "代理人FAX番号": 1, "相談内容": 2, "メールアドレス": 1}
    card.destroy()


def test_list_columns_follow_card_order():
    # 2026-11-10 班長指示：一覧の列は、カードの並び（左の列から、上から順）にそろえ、代理人も出す
    from va_case.case.app import DISPLAY_COLUMNS
    card_order = [n for _, names in CARD_LAYOUT for n in names]
    assert DISPLAY_COLUMNS == sorted(DISPLAY_COLUMNS, key=card_order.index)
    assert "代理人" in DISPLAY_COLUMNS and len(DISPLAY_COLUMNS) == 13


def test_birthdays_one_per_line(root):
    """依頼者が何人かいるときは、生年月日を1行に1人ずつ入れる（2026-11-12 班長決定）。カードは1行の高さ。"""
    row = make_row("101", 依頼者氏名="甲野太郎\n甲野花子", 生年月日="1975-04-01\n1977-06-03")
    card = make_card(root, [row], [])
    card.put("101", row_values(row))
    root.update()
    w = card.widgets["生年月日"]
    assert isinstance(w, tk.Text) and int(w.cget("height")) == 1
    assert card.values()["生年月日"] == "S50.4.1\nS52.6.3"
    card.destroy()


def test_notes_wrap_to_width(root):
    """注意書きは「その他」の列の下に、列の幅で1文字ずつ折り返す（2026-11-12 班長指示）。英数字の続きは切らず、
    句読点を行の頭に置かない。"""
    import tkinter.font as tkfont

    from va_case.case.card import NO_LINE_START, wrap_text
    font = tkfont.nametofont("TkDefaultFont")
    text = "直したら、ほかの事件に移るときに書き込みます。Ctrl+Z で直す前に戻せます。\n日付は R7.1.1・2025/1/1 などの形で。"
    for width in (120, 200, 300):
        lines = wrap_text(text, font, width).split("\n")
        assert all(font.measure(ln) <= width for ln in lines)
        assert all(ln and ln[0] not in NO_LINE_START for ln in lines)
        assert "Ctrl+Z" in "\n".join(lines) and "2025/1/1" in "\n".join(lines)
        assert "".join(lines).replace(" ", "") == text.replace("\n", "").replace(" ", "")
    card = make_card(root, [], [])
    root.update()
    assert card.notes.grid_info()["row"] == len(CARD_LAYOUT[-1][1]) + 1
    assert card.notes.master is card.widgets["備考"].master.master       # 「その他」の列の中
    assert card.notes.cget("text").startswith("日付は")                 # 状態の文（閲覧モードです など）は出さない
    assert not hasattr(card, "state_var")
    card.destroy()


def test_notes_never_ask_wider_than_given(root):
    """折り返した注記が、与えられた幅より広い幅を求めない（2026-11-14 に直した不具合。窓の幅 1280 で、注記の幅が
    349 と 350 を行き来し、画面が止まった）。広い幅を求めると「その他」の列が広がり、折り返し直しを繰り返す。"""
    import tkinter.font as tkfont
    card = make_card(root, [], [])
    root.update()
    # 句読点を前の行に付けると、行が折り返しの幅より1字広くなることがある。そのため、全角1字分以上の余りを残す
    # ことを確かめる（試験の環境の字の大きさによらず、余りがあれば、列を広げることはない）
    char = tkfont.nametofont(str(card.notes.cget("font")) or "TkDefaultFont").measure("国")
    over = []
    for width in range(300, 701):
        card._wrap_notes(width)
        card.notes.update_idletasks()
        if card.notes.winfo_reqwidth() > width - char:
            over.append((width, card.notes.winfo_reqwidth()))
    assert not over, over[:5]
    card.destroy()
