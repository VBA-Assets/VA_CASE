"""VA Receipt の共有データの扱いの試験（画面とファイルの操作に依らない部分）。相手先は架空。"""
from datetime import datetime

import pytest

from va_case.receipt import model as m


def row(number, dt="", partner="", amount="", stored_name="", read="a.pdf"):
    r = m.blank_row()
    r[m.COL["番号"]], r[m.COL["日時"]], r[m.COL["相手先"]], r[m.COL["金額"]] = number, dt, partner, amount
    r[m.COL["読込フォルダ名"]], r[m.COL["読込ファイル名"]] = r"S:\scan", read
    if stored_name:
        r[m.COL["保管ファイル名"]] = stored_name
        r[m.COL["保管日時"]] = "2025-11-01 10:00:00"
    return r


def test_date_from_name_and_fallback():
    t = datetime(2025, 11, 3, 9, 0).timestamp()
    assert m.date_from_name("20251101_ABC商店_1100.pdf", t) == "20251101"
    assert m.date_from_name("IMG_1234.jpg", t) == "20251103"                              # ファイルの日付（既定）
    assert m.date_from_name("IMG_1234.jpg", t, m.DATE_BLANK) == ""                        # 空欄（事務所の設定）
    assert m.date_from_name("20251399_x.pdf", t) == "20251103"                            # ない日付は使わない
    assert m.date_fallback(m.empty_tables()) == m.DATE_FROM_FILE


def test_parts_and_amount():
    assert m.parts_from_name("20251101_ABC商店_1,100円.pdf") == ("ABC商店", "1100")
    assert m.parts_from_name("20251101_ABC商店.pdf") == ("ABC商店", "")
    # 2026-11-12 班長決定「直す」：日付で始まらない名前は読まない。Windows が写したときの「 (2)」などは除く
    assert m.parts_from_name("IMG_1234.jpg") == ("", "")
    assert m.parts_from_name("領収書_甲乙書店_2200.pdf") == ("", "")
    assert m.parts_from_name("20251131_癸山印刷_800.pdf") == ("癸山印刷", "800")       # ない日付でも、この形とみる
    assert m.parts_from_name("20251114_辛田タクシー_1500 (2).pdf") == ("辛田タクシー", "1500")
    assert m.parts_from_name("20251114_辛田タクシー_1500 - コピー.pdf") == ("辛田タクシー", "1500")
    assert m.parts_from_name("20251114_辛田タクシー_1500 - コピー (3).pdf") == ("辛田タクシー", "1500")
    assert m.parts_from_name("20251105_丙野書店 (2).pdf") == ("丙野書店", "")
    assert m.parts_from_name("20251105.pdf") == ("", "")
    assert m.normalize_amount("￥1,100") == "1100"
    assert m.normalize_amount("１１００円") == "1100"
    assert m.normalize_amount("▲500") == "-500"
    assert m.normalize_amount("") == ""
    assert m.normalize_amount("約千円") is None


def test_copies_are_numbered_after_the_original():
    """Windows が写した「 (2)」のファイルは、元のファイルの後に番号を付ける（枝番が写しの方に付く。2026-11-12）。"""
    t = m.empty_tables()
    found = [m.FoundFile(r"S:\scan", "20251114_辛田タクシー_1500 (2).pdf", 0),
             m.FoundFile(r"S:\scan", "20251114_辛田タクシー_1500.pdf", 0),
             m.FoundFile(r"S:\scan", "20251114_辛田タクシー_1500 - コピー.pdf", 0)]
    new, added, _ = m.merge_found(t, found, [], now=datetime(2025, 11, 14, 12))
    rows = sorted(new[m.STORE].rows, key=lambda r: r[m.COL["番号"]])
    assert [r[m.COL["読込ファイル名"]] for r in rows] == [
        "20251114_辛田タクシー_1500.pdf", "20251114_辛田タクシー_1500 - コピー.pdf", "20251114_辛田タクシー_1500 (2).pdf"]
    branches = [m.suggest_branch(new, r[m.COL["番号"]], r[m.COL["読込ファイル名"]], "20251114", "辛田タクシー", "1500")
                for r in rows]
    assert branches == [0, 1, 2]


def test_stored_file_name():
    assert m.stored_file_name("x.PDF", "20251101", "ABC商店", "1100", "0") == "20251101_ABC商店_1100.PDF"
    assert m.stored_file_name("x.pdf", "20251101", "ABC商店", "1100", 2) == "20251101_ABC商店_1100_2.pdf"
    # 金額が空なら末尾の「_」を付けない。枝番があれば金額の場所を空けておく（2026-11-12 班長決定）
    assert m.stored_file_name("x.pdf", "20251105", "丙野書店", "", "0") == "20251105_丙野書店.pdf"
    assert m.stored_file_name("x.pdf", "20251105", "丙野書店", "", 1) == "20251105_丙野書店__1.pdf"


def test_suggest_branch_when_same_and_always():
    t = m.empty_tables()
    t[m.STORE].rows = [row("1", "20251101", "ABC商店", "1100", stored_name="20251101_ABC商店_1100.pdf"),
                       row("2", "20251101", "ABC商店", "1,100円"),
                       row("3", "20251101", "ABC商店", "1100")]
    assert m.suggest_branch(t, "2", "a.pdf", "20251101", "ABC商店", "1100") == 1   # 2件目から _1（現行の既定）
    assert m.suggest_branch(t, "3", "a.pdf", "20251101", "ABC商店", "1100") == 2
    assert m.suggest_branch(t, "9", "a.pdf", "20251102", "ABC商店", "1100") == 0
    t[m.SETTINGS].rows = [[m.SET_BRANCH, m.BRANCH_ALWAYS]]
    assert m.suggest_branch(t, "9", "a.pdf", "20251102", "ABC商店", "1100") == 1   # 常に付加する
    # 保管フォルダに同じ名前のファイルがあれば増やす（Python 版で足した確かめ）
    exists = {"20251102_ABC商店_1100_1.pdf"}
    assert m.suggest_branch(t, "9", "a.pdf", "20251102", "ABC商店", "1100", lambda n: n in exists) == 2


def test_merge_found_fills_from_name():
    t = m.empty_tables()
    t[m.TYPES].rows = [["領収書", r"D:\経理\領収書"], ["請求書", r"D:\経理\請求書"]]
    t[m.STORE].rows = [row("5", stored_name="20251101_ABC商店_1100.pdf", read="20251101_ABC商店_1100.pdf")]
    found = [m.FoundFile(r"S:\scan", "20251101_ABC商店_1100.pdf", 0),   # 保管済みと同じ名前でも新しく読む
             m.FoundFile(r"S:\scan", "IMG_0001.jpg", datetime(2025, 11, 3).timestamp())]
    new, added, removed = m.merge_found(t, found, [], now=datetime(2025, 11, 14, 12, 30, 5))
    assert added == 2 and removed == 0
    rows = [r for r in new[m.STORE].rows if not m.is_stored(r)]
    # 番号は、年月日＋その日の連番（VA Filing・VA Call と同じ。2026-11-13 班長決定「9桁（年月日＋連番）」）
    assert sorted(r[m.COL["番号"]] for r in rows) == ["251114001", "251114002"]
    a = next(r for r in rows if r[m.COL["読込ファイル名"]].startswith("2025"))
    assert (a[m.COL["種別"]], a[m.COL["保管フォルダ名"]], a[m.COL["日時"]], a[m.COL["相手先"]], a[m.COL["金額"]]) == \
        ("領収書", r"D:\経理\領収書", "20251101", "ABC商店", "1100")
    b = next(r for r in rows if r[m.COL["読込ファイル名"]] == "IMG_0001.jpg")
    assert b[m.COL["日時"]] == "20251103"
    t[m.SETTINGS].rows = [[m.SET_DATE_FALLBACK, m.DATE_BLANK]]
    new, _, _ = m.merge_found(t, found[1:], [])
    assert next(r for r in new[m.STORE].rows if not m.is_stored(r))[m.COL["日時"]] == ""


def test_mark_stored_and_restored():
    t = m.empty_tables()
    t[m.STORE].rows = [row("1", "20251101", "ABC商店", "1100")]
    s = m.mark_stored(t, "1", kind="領収書", dt="20251101", partner="ABC商店", amount="1100", branch="0",
                      folder=r"D:\経理\領収書", file_name="20251101_ABC商店_1100.pdf", note="",
                      at=datetime(2025, 11, 4, 10, 0, 0))
    r = s[m.STORE].rows[0]
    assert r[m.COL["保管日時"]] == "2025-11-04 10:00:00" and r[m.COL["種別"]] == "領収書"
    with pytest.raises(ValueError, match="すでに保管"):
        m.mark_stored(s, "1", kind="", dt="", partner="", amount="", branch="", folder="", file_name="", note="")
    back = m.mark_restored(s, "1", "2025-11-04 10:00:00")[m.STORE].rows[0]
    assert back[m.COL["保管日時"]] == back[m.COL["保管ファイル名"]] == back[m.COL["保管フォルダ名"]] == ""
    assert back[m.COL["相手先"]] == "ABC商店"


def test_csv_import_numbers():
    t = m.empty_tables()
    t[m.STORE].rows = [row("3")]
    rows = [row("3"), row(""), row("x")]
    rows[0][m.COL["保管日時"]] = "2025/11/1 9:00"
    new = m.add_imported(t, rows)
    numbers = sorted(int(r[m.COL["番号"]]) for r in new[m.STORE].rows)
    assert numbers[0] == 3 and len(set(numbers)) == 4    # もとの行の番号は、そのまま
    assert all(len(str(n)) == 9 for n in numbers[1:])   # 重なり・空・数字でない番号は、年月日＋連番で付け直す


def test_delete_row_only_unstored():
    t = m.empty_tables()
    t[m.STORE].rows = [row("1", stored_name="20251101_ABC商店_1100.pdf"), row("2")]
    with pytest.raises(ValueError, match="保管を取り消す"):
        m.delete_row(t, "1")                          # 保管済みは消さない
    new = m.delete_row(t, "2")
    assert [r[m.COL["番号"]] for r in new[m.STORE].rows] == ["1"]
    with pytest.raises(ValueError, match="ありません"):
        m.delete_row(new, "2")


def test_list_columns_follow_the_store_table():
    """一覧の列は、表「保管」と同じ並び（2026-11-12 班長指示）。"""
    from va_case.receipt.app import COLUMN_WIDTHS, DISPLAY_COLUMNS
    assert DISPLAY_COLUMNS == ["番号", "読込フォルダ名", "読込ファイル名", "種別", "日時", "相手先", "金額", "枝番",
                               "保管フォルダ名", "保管ファイル名", "保管日時", "備考"]
    assert set(COLUMN_WIDTHS) == set(DISPLAY_COLUMNS)


def test_store_needs_an_amount(monkeypatch):
    """金額が空なら保管しない。「0」は保管できる（2026-11-12 班長指摘「金額が入力されていなくても保存できてしまう」）。"""
    from types import SimpleNamespace

    from va_case.common.ui.file_store_app import StoreCancelled
    from va_case.receipt import app as appmod
    shown = []
    monkeypatch.setattr(appmod.messagebox, "showinfo", lambda title, msg, **k: shown.append(msg))
    focused = []
    fake = SimpleNamespace(root=None, auto_name="", widgets={"金額": SimpleNamespace(focus_set=lambda: focused.append("金額"))})
    r = row("1", "20251101", "ABC商店", read="20251101_ABC商店.pdf")
    v = {"種別": "交通費", "日時": "20251101", "相手先": "ABC商店", "金額": "", "枝番": "", "保管フォルダ名": r"S:\領収書",
         "保管ファイル名": "20251101_ABC商店.pdf", "備考": ""}
    for blank in ("", "  ", "　"):
        with pytest.raises(StoreCancelled):
            appmod.ReceiptApp._prepare_store(fake, r, dict(v, 金額=blank))
    assert shown == ["金額を入れてください。"] * 3 and focused == ["金額"] * 3
    with pytest.raises(StoreCancelled):                     # 「円」だけは、数字でないとして止まる
        appmod.ReceiptApp._prepare_store(fake, r, dict(v, 金額="円"))
    assert shown[-1].startswith("金額を、数字で")
    prep = appmod.ReceiptApp._prepare_store(fake, r, dict(v, 金額="0", 保管ファイル名="20251101_ABC商店_0.pdf"))
    assert prep["file_name"] == "20251101_ABC商店_0.pdf"


def test_new_numbers_never_go_back():
    """番号は年月日＋その日の連番の9桁（2026-11-13 班長決定）。いまの9桁の番号のうち最大のものより小さくしない
    （付けた順＝番号の順）。"""
    from va_case.common.numbering import new_numbers
    now = datetime(2025, 11, 14, 12, 30, 5)
    assert new_numbers(["1", "2"], 2, now) == ["251114001", "251114002"]        # 今までの番号（1, 2…）は見ない
    assert new_numbers(["251114001", "251114002"], 1, now) == ["251114003"]     # その日の最大に1を足す
    assert new_numbers(["251113007"], 1, now) == ["251114001"]                  # 日が替われば 001 から
    assert new_numbers(["251115004"], 1, now) == ["251115005"]                  # 時計が戻っても、前より小さくしない
    assert new_numbers(["251114999"], 2, now) == ["251115000", "251115001"]     # 999 件を超えたら、はみ出して続ける
    assert new_numbers(["251114123005"], 1, now) == ["251114001"]               # VAファイル保管の12桁は見ない
    assert new_numbers(["", "x"], 1, now) == ["251114001"]


def test_unstored_rows_in_number_order():
    """未保管の行は番号の順（読み込んだ順）。保管済みの行は、今までどおり保管日時の順（2026-11-13 班長決定「番号順にする。」）。"""
    t = m.empty_tables()
    a = row("261112003", read="受信FAX_裁判所.pdf")
    b = row("261113012", read="202611131455.pdf")
    c = row("261113013", read="202611131500.pdf")
    c[m.COL["読込フォルダ名"]] = r"S:\scan\複合機2"
    old = row("8", read="IMG_0001.jpg")                       # 取り込んだ今までの番号は、先に並ぶ
    s1 = row("261113001", stored_name="x.pdf", read="z.pdf")
    s2 = row("261112001", stored_name="y.pdf", read="a.pdf")
    s1[m.COL["保管日時"]], s2[m.COL["保管日時"]] = "2026-11-13 10:00:00", "2026-11-13 11:00:00"
    for r in (a, b, old):
        r[m.COL["読込フォルダ名"]] = r"S:\scan"
    t[m.STORE].rows = [c, s2, b, old, a, s1]
    assert [r[m.COL["番号"]] for r in m.sorted_rows(t[m.STORE].rows)] == \
        ["261113001", "261112001", "8", "261112003", "261113012", "261113013"]
