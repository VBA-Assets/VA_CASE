"""裁判所の電話番号・FAX番号（事務所の設定の「裁判所」。2026-11-11 班長決定）の試験。番号は架空。"""
import pytest

from va_case.case import memo
from va_case.case import model as m
from va_case.common.master import Table


def tables(rows):
    t = m.empty_tables()
    t[m.COURTS] = Table(list(m.COURT_COLUMNS), rows)
    return t


def test_new_shared_data_has_courts_table():
    assert m.SCHEMA[m.COURTS] == ["裁判所名", "電話番号", "FAX番号"]
    assert m.empty_tables()[m.COURTS].rows == []


def test_court_numbers_uses_last_line_and_ignores_spaces():
    t = tables([["東京地方裁判所民事第1部", "03-0000-2001", "03-0000-3001"],
                ["東京高等裁判所第2民事部", "03-0000-2002", "03-0000-3002"]])
    assert m.court_numbers(t, "東京地方裁判所民事第1部") == ("03-0000-2001", "03-0000-3001")
    assert m.court_numbers(t, "東京地方裁判所 民事第1部") == ("03-0000-2001", "03-0000-3001")   # 空白の違いは問わない
    # 控訴審などで下に足した裁判所名は、最後の行（今の裁判所）で探す
    assert m.court_numbers(t, "東京地方裁判所民事第1部\n東京高等裁判所第2民事部") == ("03-0000-2002", "03-0000-3002")
    assert m.court_numbers(t, "横浜地方裁判所") == ("", "") and m.court_numbers(t, "") == ("", "")


def test_memo_writes_court_numbers():
    fitz = pytest.importorskip("fitz")
    row = m.blank_row(101)
    row[m.COL["裁判所名"]] = "東京地方裁判所民事第1部"
    doc = fitz.open(stream=memo.build_pdf(row, court=("03-0000-2001", "03-0000-3001")), filetype="pdf")
    text = doc[0].get_text()
    assert "03-0000-2001" in text and "03-0000-3001" in text
    blank = fitz.open(stream=memo.build_pdf(row), filetype="pdf")[0].get_text()
    assert "03-0000" not in blank                                             # 登録がなければ、手書きの空欄
