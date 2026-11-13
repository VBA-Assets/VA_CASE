"""VA Call の共有データの扱いとメール（mailto）の試験。氏名は架空。"""
from datetime import datetime
from urllib.parse import parse_qs, unquote, urlparse

import pytest

from va_case.call import model as m


def tables():
    t = m.empty_tables()
    t[m.STAFF].rows = [["佐藤", "sato@example.jp", "sato"], ["田中", "tanaka@example.jp", "TanakaJ"]]
    return t


def test_staff_lookup():
    t = tables()
    assert m.staff_for_user(t, "tanakaj") == "田中"           # Windows のユーザー名は大文字・小文字を問わない
    assert m.staff_for_user(t, "someone") == ""
    assert m.mail_address(t, "佐藤") == "sato@example.jp"
    assert m.choice_values(t, "処理") == ["処理済み", "確認済み"]


def test_add_and_update_memo():
    t = tables()
    t, n1 = m.add_memo(t, "佐藤", now=datetime(2025, 11, 9, 10, 30))
    t, n2 = m.add_memo(t, "田中", now=datetime(2025, 11, 9, 11, 0))
    assert (n1, n2) == ("251109001", "251109002")   # 年月日＋その日の連番（2026-11-13 班長決定「9桁（年月日＋連番）」）
    t, n3 = m.add_memo(t, "田中", now=datetime(2025, 11, 10, 9, 0))
    assert n3 == "251110001"                            # 日が替われば 001 から
    row = m.row_by_number(t, n1)
    assert row[m.COL["日時"]] == "2025-11-09 10:30" and row[m.COL["入力者"]] == "佐藤"
    t = m.update_memo(t, n1, {"相手先": "甲野太郎", "宛先": "田中", "番号": "99"})
    assert m.row_by_number(t, n1)[m.COL["相手先"]] == "甲野太郎"      # 番号は変えない
    with pytest.raises(ValueError, match="ほかの PC"):
        m.update_memo(t, n1, {"内容": "x"}, base=["違う"] * len(m.MEMO_COLUMNS))
    with pytest.raises(ValueError, match="ありません"):
        m.update_memo(t, "9", {"内容": "x"})


def test_datetime_input():
    assert m.normalize_datetime("2025/11/9 10:30") == "2025-11-09 10:30"
    assert m.normalize_datetime("２０２５年１１月９日 ９時５分") == "2025-11-09 09:05"
    assert m.normalize_datetime("2025-11-09") == "2025-11-09 00:00"
    assert m.normalize_datetime("") == ""
    assert m.normalize_datetime("きのう") is None
    assert m.display_datetime("2025-11-09 09:05") == "2025/11/9 9:05"
    vals, probs = m.check_values({"日時": "2025/13/1 10:00", "相手先": "x"})
    assert probs and vals["相手先"] == "x"


def test_mail_body_and_mailto():
    t = tables()
    t, n = m.add_memo(t, "佐藤", now=datetime(2025, 11, 9, 10, 30))
    t = m.update_memo(t, n, {"相手先": "甲野太郎", "電話番号": "03-0000-0001", "宛先": "田中", "用件": "電話がありました。",
                             "対応": "電話をいただきたい。", "内容": "貸金の件\n折り返し希望"})
    body = m.mail_body(m.row_by_number(t, n))
    assert body.startswith("番　号：251109001\r\n日　付：2025/11/9\r\n時　間：10:30\r\n相手先：甲野太郎\r\n")
    assert "入力者：佐藤" in body
    url = m.mailto_url("tanaka@example.jp", m.MAIL_SUBJECT, body)
    u = urlparse(url)
    assert u.scheme == "mailto" and unquote(u.path) == "tanaka@example.jp"
    q = parse_qs(u.query)
    assert q["subject"] == ["電話メモ"] and q["body"][0] == body


def test_csv_import():
    t = tables()
    t[m.MEMO].rows = [[""] * len(m.MEMO_COLUMNS)]
    t[m.MEMO].rows[0][m.COL["番号"]] = "1"           # 取り込んでいた、今までの番号
    rows = [[""] * len(m.MEMO_COLUMNS) for _ in range(2)]
    rows[0][m.COL["番号"]] = "1"                     # 重なる番号は付け直す
    rows[0][m.COL["日時"]] = "2025/11/1 9:00"
    rows[1][m.COL["番号"]] = "7"                     # 今までの番号は、そのまま
    new = m.import_rows(t, rows)
    numbers = [r[m.COL["番号"]] for r in new[m.MEMO].rows]
    assert numbers[:2] == ["1", "7"] and len(numbers[2]) == 9
    assert m.row_by_number(new, numbers[2])[m.COL["日時"]] == "2025-11-01 09:00"
    bad = [[""] * len(m.MEMO_COLUMNS)]
    bad[0][m.COL["日時"]] = "きのう"
    with pytest.raises(ValueError, match="日時"):
        m.import_rows(t, bad)


def test_phone_for_latest_memo_of_partner():
    t = tables()
    for partner, phone in (("甲野太郎", "03-0000-0001"), ("乙山次郎", "06-0000-0002"), ("甲野太郎", "090-0000-0003"),
                           ("甲野太郎", "")):
        t, n = m.add_memo(t, "佐藤")
        t = m.update_memo(t, n, {"相手先": partner, "電話番号": phone})
        if phone == "090-0000-0003":
            third = n
    assert m.phone_for(t, "甲野太郎") == "090-0000-0003"              # 電話番号のある、いちばん新しいメモ
    assert m.phone_for(t, "甲野太郎", exclude=third) == "03-0000-0001"
    assert m.phone_for(t, "丙川") == "" and m.phone_for(t, "") == ""


def test_delete_memo():
    t = tables()
    now = datetime(2025, 11, 9, 10, 0)
    for _ in range(3):
        t, _n = m.add_memo(t, "佐藤", now=now)
    t = m.delete_memo(t, "251109002")
    assert [r[m.COL["番号"]] for r in t[m.MEMO].rows] == ["251109001", "251109003"]
    assert m.next_number(t, now) == "251109004"       # 番号は付け直さない
    t = m.delete_memo(t, "251109003")
    assert m.next_number(t, now) == "251109002"       # その日の最後を消すと、使い回す（記録は持たない。2026-11-13 班長）
    with pytest.raises(ValueError, match="ありません"):
        m.delete_memo(t, "251109003")


def test_list_columns_follow_the_memo_table():
    """一覧の列は、表「電話メモ」と同じ並び（2026-11-12 班長指示）。"""
    from va_case.call.app import COLUMN_WIDTHS, DISPLAY_COLUMNS
    assert DISPLAY_COLUMNS == ["番号", "入力者", "日時", "相手先", "電話番号", "用件", "対応", "内容", "宛先",
                               "メール送信日時", "確認者", "処理"]
    assert set(COLUMN_WIDTHS) == set(DISPLAY_COLUMNS)
