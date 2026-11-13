"""CSV の取り込みで、すでに同じ記録がある行を取り込まない（VA Filing・VA Receipt・VA Call。2026-11-11 班長決定）。氏名は架空。"""
import pytest

from va_case.call import model as call_m
from va_case.filing import model as filing_m
from va_case.receipt import model as receipt_m


def make(m, columns, **values):
    row = [""] * len(columns)
    for k, v in values.items():
        row[m.COL[k]] = v
    return row


@pytest.mark.parametrize("m", [filing_m, receipt_m])
def test_store_tools_skip_same_records(m):
    tables = m.empty_tables()
    stored = make(m, m.STORE_COLUMNS, 番号="1", 読込ファイル名="202511051030.pdf", 保管日時="2026-11-09 15:43:00")
    tables[m.STORE].rows = [stored]
    # 番号が違い、保管日時の書き方が違うだけの同じ記録は除く。値が1つでも違えば、別の記録として残す
    same = make(m, m.STORE_COLUMNS, 番号="7", 読込ファイル名="202511051030.pdf", 保管日時="2026/11/9 15:43")
    other = make(m, m.STORE_COLUMNS, 番号="1", 読込ファイル名="202511051032.pdf", 保管日時="2026/11/9 15:43")
    keep, dropped = m.drop_existing(tables, [same, other, list(other)])
    assert dropped == 1 and keep == [other, other]          # CSV の中の同じ行2つは、どちらも残す
    new = m.add_imported(tables, keep)
    assert len(new[m.STORE].rows) == 3


def test_call_skips_same_memos():
    m = call_m
    tables = m.empty_tables()
    tables[m.MEMO].rows = [make(m, m.MEMO_COLUMNS, 番号="1", 日時="2026-11-09 09:05", 相手先="甲野太郎", 内容="期日の確認")]
    same = make(m, m.MEMO_COLUMNS, 番号="", 日時="2026/11/9 9:05", 相手先="甲野太郎", 内容="期日の確認")
    other = make(m, m.MEMO_COLUMNS, 番号="", 日時="2026/11/9 9:06", 相手先="甲野太郎", 内容="期日の確認")
    bad = make(m, m.MEMO_COLUMNS, 日時="読めない日時")     # 読めない行は残す（取り込むときに知らせる）
    keep, dropped = m.drop_existing(tables, [same, other, bad])
    assert dropped == 1 and keep == [other, bad]
