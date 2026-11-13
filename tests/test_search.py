"""検索（VAサーチと同じ同一視）と日付の試験。氏名は架空。"""
from datetime import date

import pytest

from va_case.common import dates
from va_case.common.search import Query, normalize, search

ROWS = [
    ["101", "髙橋一郎", "たかはし", "2025-01-01", "東京都千代田区"],
    ["102", "齋藤花子", "サイトウ", "1980-04-01", "ＡＢＣ株式会社"],
    ["201", "山崎次郎", "やまざき", "", "コンピューター"],
    ["202", "渡邉三郎", "わたなべ", "2019-04-30", "キャノン"],
]


@pytest.mark.parametrize("word, expected", [
    ("高橋", [0]),            # 異字体（髙）
    ("斎藤", [1]),            # 齋⇔斎
    ("渡辺", [3]),            # 邉⇔辺
    ("abc", [1]),             # 全角/半角・大文字/小文字
    ("タカハシ", [0]),        # ひらがな/カタカナ
    ("やまさき", [2]),        # 濁点の有無
    ("キヤノン", [3]),        # 小書き文字
    ("コンピュータ", [2]),    # 長音
    ("R7.1.1", [0]),          # 和暦で、西暦で書いた日付が見つかる
    ("2019/4/30", [3]),
    ("H31.4.30", [3]),
    ("令和元年5月1日", []),
    ("昭和55年4月1日", [1]),
    ("千代田", [0]),
])
def test_same_as_va_search(word, expected):
    assert search(ROWS, word) == expected


def test_or_and():
    assert search(ROWS, "高橋　斎藤") == [0, 1]           # 既定は OR。全角の空白でも区切る
    assert search(ROWS, "高橋 千代田", "AND") == [0]
    assert search(ROWS, "高橋 斎藤", "AND") == []
    assert Query("  ").empty and search(ROWS, "") == [0, 1, 2, 3]


def test_ivs_is_ignored():
    assert normalize("葛\U000E0100飾") == normalize("葛飾")


def test_dates():
    assert dates.parse_date("令和元年5月1日") == date(2019, 5, 1)
    assert dates.parse_date("Ｒ７．１．１") == date(2025, 1, 1)
    assert dates.parse_date("2025年1月1日") == date(2025, 1, 1)
    assert dates.parse_date("2025/2/30") is None and dates.parse_date("事件") is None
    assert dates.to_wareki(date(2019, 4, 30)) == "H31.4.30"
    assert dates.to_wareki(date(2019, 5, 1)) == "R1.5.1"
    assert dates.normalize_date_text("S55.4.1") == "1980-04-01"
    assert dates.display("2025-01-01") == "R7.1.1" and dates.display("不明") == "不明"
    with pytest.raises(ValueError):
        dates.normalize_date_text("あした")


def test_dates_one_per_line():
    """1行に1つずつ日付を入れた欄（何人かの生年月日。2026-11-12）も、どの行の日付でも当たる。"""
    rows = [["甲野太郎\n甲野花子", "1975-04-01\n1977-06-03"], ["乙山次郎", "1980-01-01"]]
    assert search(rows, "S52.6.3") == [0] and search(rows, "1975/4/1") == [0] and search(rows, "S55.1.1") == [1]
