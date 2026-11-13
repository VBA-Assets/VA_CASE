"""VA Filing の共有データの扱いの試験（画面とファイルの操作に依らない部分）。氏名は架空。"""
from datetime import datetime

import pytest

from va_case.case import model as cm
from va_case.filing import model as m


def case_tables():
    t = cm.empty_tables()
    for number, status, name, kana, folder, tantou in (
            ("101", "A:未了", "甲野太郎（貸金）", "こうのたろう", r"D:\事件\101甲野太郎", "佐"),
            ("201", "A:未了", "辛川花子（自己破産）", "からかわはなこ", r"D:\事件\201辛川花子", "田"),
            ("102", "B:精算管理", "甲野太郎（建物明渡）", "こうのたろう", r"D:\事件\102甲野太郎", "佐・田"),
            ("401", "C:終了", "癸山五郎（交通事故）", "みずのとやまごろう", "保管庫：個人一般/2024/401.zip", "田"),
            ("501", "A:未了", "子田六子", "", "", ""),
            ("601", "A:未了", "乙山（相談）", "おつやま", "保管庫：個人一般/2025/601.zip", "")):
        row = cm.blank_row(number)
        row[cm.COL["現況"]], row[cm.COL["事件呼名"]], row[cm.COL["ふりがな"]] = status, name, kana
        row[cm.COL["データフォルダ"]], row[cm.COL["担当区分"]] = folder, tantou
        row[cm.COL["依頼者氏名"]] = name.split("（")[0]
        t[cm.CASE].rows.append(row)
    return t


def test_file_name_rules():
    assert m.extension("2025.1.1受信.pdf") == ".pdf"          # 現行は「.1.1受信.pdf」になった
    assert m.extension("名前なし") == ""
    assert m.datetime_text("202503011030_scan.pdf") == "202503011030"
    assert m.datetime_text("20250301_scan.pdf", mtime=datetime(2025, 3, 2, 9, 5).timestamp()) == "202503020905"
    assert m.datetime_text("1903011030xx.pdf", mtime=None) == ""
    assert m.stored_file_name("a.pdf", "202503011030", "甲野太郎（貸金）", "訴状") == \
        "20250301103000000甲野太郎（貸金）\u3000訴状.pdf"
    assert m.stored_file_name("a.pdf", "202503011030", "民法（文献）", "注釈民法") == "注釈民法.pdf"
    assert m.stored_file_name("a.pdf", "202503011030", "甲野太郎", "") == ""
    assert m.check_file_name("訴状/写し.pdf")
    assert m.check_file_name("訴状.pdf.")
    assert m.check_file_name("訴状.pdf") == ""


def test_skip_rules():
    assert m.should_skip(".hidden")
    assert m.should_skip("~$文書.docx")
    assert m.should_skip("Thumbs.db") and m.should_skip("desktop.ini")
    assert m.should_skip("書きかけ.pdf.part")
    assert m.should_skip("FAXDATA001.pdf", ["FAXDATA"])   # 事務所の設定の「読み込まないファイル名の先頭」
    assert not m.should_skip("202503011030.pdf", ["FAXDATA"])


def test_merge_found_dedupes_only_against_pending_rows():
    t = m.empty_tables()
    stored = m.blank_row()
    stored[m.COL["番号"]], stored[m.COL["読込フォルダ名"]], stored[m.COL["読込ファイル名"]] = "250101000000", r"S:\scan", "a.pdf"
    stored[m.COL["保管日時"]] = "2025-01-01 10:00:00"
    pending = m.blank_row()
    pending[m.COL["番号"]], pending[m.COL["読込フォルダ名"]], pending[m.COL["読込ファイル名"]] = "250101000001", r"S:\scan", "b.pdf"
    gone = m.blank_row()
    gone[m.COL["番号"]], gone[m.COL["読込フォルダ名"]], gone[m.COL["読込ファイル名"]] = "250101000002", r"S:\scan", "c.pdf"
    t[m.STORE].rows = [stored, pending, gone]
    found = [m.FoundFile(r"S:\scan", "a.pdf", 0), m.FoundFile(r"S:\scan", "B.PDF", 0),
             m.FoundFile(r"S:\scan", "202503011030.pdf", 0)]
    new, added, removed = m.merge_found(t, found, ["250101000002", "250101000000"], now=datetime(2025, 3, 1, 12))
    names = [r[m.COL["読込ファイル名"]] for r in new[m.STORE].rows]
    assert added == 2 and removed == 1                    # a.pdf は保管済みと同じ名前でも新しく読む。B.PDF は重なり
    assert names.count("a.pdf") == 2 and "c.pdf" not in names
    assert m.is_stored(new[m.STORE].rows[0])              # 保管済みが先、未保管が後（現行の並べ替え）
    numbers = [r[m.COL["番号"]] for r in new[m.STORE].rows]
    assert len(set(numbers)) == len(numbers)
    assert next(r for r in new[m.STORE].rows if r[m.COL["読込ファイル名"]] == "202503011030.pdf")[m.COL["日時"]] == \
        "202503011030"
    assert t[m.STORE].rows == [stored, pending, gone]     # 元のテーブルは変えない


def test_candidates_from_va_case():
    dest = [["甲野太郎（貸金）", r"D:\事件\101甲野太郎\scan", "佐"], ["民法（文献）", r"D:\文献", ""]]
    cands = m.case_candidates(case_tables(), dest, folder_exists=lambda v: True)
    names = [c.name for c in cands]
    assert "癸山五郎（交通事故）" not in names and "乙山（相談）" not in names   # 終了・保管庫の事件は出さない
    assert "子田六子" not in names                                               # データフォルダが空の事件も出さない
    assert names[:3] == ["辛川花子（自己破産）", "甲野太郎（貸金）", "甲野太郎（建物明渡）"]   # ふりがなの順
    assert names[-1] == "民法（文献）"                                          # VA Case にない保管先は最後
    koono = cands[1]
    assert koono.folder.endswith(r"\scan") and koono.case_folder == r"D:\事件\101甲野太郎"   # 覚えた保管先
    assert koono.from_case and not cands[-1].from_case
    cands = m.case_candidates(case_tables(), dest, folder_exists=lambda v: False)
    assert cands[1].folder == r"D:\事件\101甲野太郎"                             # 覚えた場所がなければ戻す
    assert m.case_candidates(None, dest)[0].name == "民法（文献）"
    assert all(c.label == c.name for c in cands)                                # 事件番号は添えない
    assert not hasattr(cands[0], "number")                                     # 事件番号を持たない（2026-11-12）
    assert all("101" not in c.search for c in cands)                          # 事件番号では絞り込まない
    # データフォルダが空でも、覚えた保管先があれば出す。VA Case にない保管先も、保管フォルダが空なら出さない
    # （2026-11-12 班長指示「事件呼名の一覧には、保管フォルダのデータが有るものだけを表示」）
    dest = [["子田六子", r"D:\事件\501子田六子", ""], ["空の保管先", "", ""]]
    names = [c.name for c in m.case_candidates(case_tables(), dest, folder_exists=lambda v: True)]
    assert "子田六子" in names and "空の保管先" not in names


def test_cases_with_same_name_are_one_candidate():
    """同じ事件呼名の事件は、1つの候補にまとめる（データフォルダも同じはずのため。2026-11-12 班長決定「案B」）。"""
    ct = case_tables()
    ct[cm.CASE].rows[2][cm.COL["事件呼名"]] = "甲野太郎（貸金）"          # 102 を 101 と同じ事件呼名にする
    cands = [c for c in m.case_candidates(ct, []) if c.name == "甲野太郎（貸金）"]
    assert len(cands) == 1 and cands[0].folder == r"D:\事件\101甲野太郎"           # 前の事件（101）のデータフォルダ
    # 「（データフォルダ）\…」の行は、VA Case の事件がなければ候補に出さない
    dest = [["消した事件", m.IN_DATA_FOLDER + r"\scan", ""]]
    assert m.case_candidates(ct, dest, folder_exists=lambda v: True) == m.case_candidates(ct, [])
    assert m.case_candidates(None, dest) == []


def test_remember_destination_inside_data_folder():
    """データフォルダの中に保管したときは、データフォルダからの相対で覚える（2026-11-12 班長決定）。"""
    t = m.empty_tables()
    koono = next(c for c in m.case_candidates(case_tables(), []) if c.name == "甲野太郎（貸金）")
    t = m.remember_destination(t, koono, r"D:\事件\101甲野太郎\scan", "佐")
    assert t[m.DEST].rows == [["甲野太郎（貸金）", m.IN_DATA_FOLDER + r"\scan", "佐"]]
    # データフォルダの名前が変わっても、その中の scan を既定にする
    ct = case_tables()
    ct[cm.CASE].rows[0][cm.COL["データフォルダ"]] = r"D:\事件\101甲野太郎（貸金）"
    c = next(c for c in m.case_candidates(ct, t[m.DEST].rows, folder_exists=lambda v: True) if c.name == "甲野太郎（貸金）")
    assert c.folder == r"D:\事件\101甲野太郎（貸金）\scan" and c.tantou == "佐"
    # 担当区分だけ変えたときは、データフォルダそのものを覚える
    t = m.remember_destination(m.empty_tables(), koono, r"D:\事件\101甲野太郎", "田")
    assert t[m.DEST].rows == [["甲野太郎（貸金）", m.IN_DATA_FOLDER, "田"]]
    c = next(c for c in m.case_candidates(case_tables(), t[m.DEST].rows, folder_exists=lambda v: True)
             if c.name == "甲野太郎（貸金）")
    assert c.folder == r"D:\事件\101甲野太郎" and c.tantou == "田"
    # データフォルダの外は、今までどおりそのまま覚える
    t = m.remember_destination(m.empty_tables(), koono, r"E:\別\101", "佐")
    assert t[m.DEST].rows == [["甲野太郎（貸金）", r"E:\別\101", "佐"]]


def test_prune_destinations_of_closed_cases():
    """終了した事件・保管庫へ移した事件の行を除く（事件呼名で結ぶ）。VA Case にない保管先は残す（2026-11-12 班長決定）。"""
    t = m.empty_tables()
    t[m.DEST].rows = [["甲野太郎（貸金）", m.IN_DATA_FOLDER + r"\scan", "佐"],      # 未了：残す
                      ["癸山五郎（交通事故）", r"D:\事件\401\scan", "田"],           # 終了：除く
                      ["乙山（相談）", r"D:\事件\601\scan", ""],                     # 保管庫へ移した：除く
                      ["民法（文献）", r"D:\文献", ""]]                              # VA Case にない保管先：残す
    new, n = m.prune_destinations(t, case_tables())
    assert n == 2 and [r[0] for r in new[m.DEST].rows] == ["甲野太郎（貸金）", "民法（文献）"]
    assert len(t[m.DEST].rows) == 4                                    # 元のテーブルは変えない
    assert m.prune_destinations(t, None) == (t, 0)                     # VA Case を読めなかったときは除かない
    # 同じ事件呼名の終了していない事件があれば、除かない
    ct = case_tables()
    ct[cm.CASE].rows[1][cm.COL["事件呼名"]] = "癸山五郎（交通事故）"
    assert "癸山五郎（交通事故）" in [r[0] for r in m.prune_destinations(t, ct)[0][m.DEST].rows]


def test_missing_destinations_are_hidden_and_pruned():
    """保管フォルダが見つからない保管先を出さず、保管するときに消す。VA Case を使う事務所でも使わない事務所でも
    （2026-11-12 班長決定「消すようにする」「フォルダ存在しない場合は、保管先から削除する」）。"""
    t = m.empty_tables()
    t[m.DEST].rows = [["甲野太郎（貸金）", r"D:\事件\甲野", ""], ["乙山次郎（離婚）", r"D:\終了\乙山", ""],
                      ["民法（文献）", r"D:\文献", ""]]
    exists = {r"D:\事件\甲野", r"D:\文献"}
    missing = m.missing_destinations(t[m.DEST].rows, lambda v: v in exists)
    assert missing == {"乙山次郎（離婚）"}
    assert sorted(c.name for c in m.case_candidates(None, t[m.DEST].rows, hidden=missing)) == \
        sorted(["甲野太郎（貸金）", "民法（文献）"])
    new, n = m.prune_destinations(t, None, missing)
    assert n == 1 and [r[0] for r in new[m.DEST].rows] == ["甲野太郎（貸金）", "民法（文献）"]
    # 1つも見つからないとき（暗号化したドライブの開き忘れなど）は、何も除かない
    assert m.missing_destinations(t[m.DEST].rows, lambda v: False) == set()
    # VA Case の事件の保管先も、見つからなければ除く（事件の候補は、データフォルダに戻る）
    t[m.DEST].rows = [["甲野太郎（貸金）", r"D:\事件\101甲野太郎\古いscan", "佐"], ["民法（文献）", r"D:\文献", ""]]
    missing = m.missing_destinations(t[m.DEST].rows, lambda v: v in exists, case_tables())
    assert missing == {"甲野太郎（貸金）"}
    koono = next(c for c in m.case_candidates(case_tables(), t[m.DEST].rows, lambda v: True, hidden=missing)
                 if c.name == "甲野太郎（貸金）")
    assert koono.folder == r"D:\事件\101甲野太郎" and koono.tantou == "佐"


def test_missing_destinations_inside_data_folder():
    """「（データフォルダ）\…」の行：VA Case の事件のデータフォルダの中を確かめる。事件がない（事件呼名を直した・消した）
    ときは見つからないとみる。VA Case を読めていないときは確かめない。"""
    rows = [["甲野太郎（貸金）", m.IN_DATA_FOLDER + r"\scan", "佐"],
            ["辛川花子（自己破産）", m.IN_DATA_FOLDER + r"\scan", ""],
            ["前の事件呼名", m.IN_DATA_FOLDER + r"\scan", ""],
            ["民法（文献）", r"D:\文献", ""]]
    exists = {r"D:\事件\101甲野太郎\scan", r"D:\文献"}
    assert m.missing_destinations(rows, lambda v: v in exists, case_tables()) == {"辛川花子（自己破産）", "前の事件呼名"}
    assert m.missing_destinations(rows, lambda v: v in exists, None) == set()
    # フォルダが1つも見つからなくても、事件がない行は除く（共有フォルダが見えるかに関わらないため）
    assert m.missing_destinations(rows, lambda v: False, case_tables()) == {"前の事件呼名"}


def test_remember_destination():
    t = m.empty_tables()
    cands = m.case_candidates(case_tables(), [])
    koono = next(c for c in cands if c.name == "甲野太郎（貸金）")
    t = m.remember_destination(t, koono, r"D:\事件\101甲野太郎\scan", "佐")
    assert t[m.DEST].rows == [["甲野太郎（貸金）", m.IN_DATA_FOLDER + r"\scan", "佐"]]
    t = m.remember_destination(t, koono, r"D:\事件\101甲野太郎", "佐")        # 既定のとおりなら、覚えた行を消す
    assert t[m.DEST].rows == []
    t = m.remember_destination(t, m.Candidate("民法（文献）", "", "", ""), r"D:\文献", "")
    t = m.remember_destination(t, m.Candidate("民法（文献）", "", "", ""), r"D:\文献2", "")
    assert t[m.DEST].rows == [["民法（文献）", r"D:\文献2", ""]]


def test_copy_and_special_targets():
    t = m.empty_tables()
    t[m.COPY_TARGETS].rows = [["佐", m.KIND_SHORTCUT, r"D:\未確認\佐藤"], ["佐", m.KIND_COPY, r"D:\写し\佐藤"],
                              ["田", m.KIND_SHORTCUT, r"D:\未確認\田中"], ["佐", "ほか", r"D:\x"]]
    assert m.copy_targets(t, "佐") == [(m.KIND_SHORTCUT, r"D:\未確認\佐藤"), (m.KIND_COPY, r"D:\写し\佐藤")]
    assert m.copy_targets(t, "") == []
    t[m.SPECIAL].rows = [["職務上請求", r"D:\職務上請求"], ["弁護士会照会", ""]]
    assert m.special_targets(t, "住民票の職務上請求") == [("職務上請求", r"D:\職務上請求")]
    assert m.special_targets(t, "弁護士会照会の回答") == []          # 置き場所が空なら作らない
    assert m.tantou_values(t, ["佐", "佐・田"]) == ["佐", "田", "佐・田"]


def test_mark_stored_and_restored():
    t = m.empty_tables()
    row = m.blank_row()
    row[m.COL["番号"]], row[m.COL["読込ファイル名"]] = "250301000000", "a.pdf"
    t[m.STORE].rows = [row]
    s = m.mark_stored(t, "250301000000", case_name="甲野太郎（貸金）", content="訴状",
                      folder=r"D:\事件\101", file_name="x.pdf", tantou="佐", note="", dt="202503011030",
                      at=datetime(2025, 3, 1, 12, 0, 5))
    r = s[m.STORE].rows[0]
    assert r[m.COL["保管日時"]] == "2025-03-01 12:00:05" and r[m.COL["事件呼名"]] == "甲野太郎（貸金）"
    with pytest.raises(ValueError, match="すでに保管"):
        m.mark_stored(s, "250301000000", case_name="", content="", folder="", file_name="",
                      tantou="", note="", dt="")
    with pytest.raises(ValueError, match="ほかの PC"):
        m.mark_restored(s, "250301000000", "2025-03-01 12:00:06")
    back = m.mark_restored(s, "250301000000", "2025-03-01 12:00:05")[m.STORE].rows[0]
    assert back[m.COL["保管日時"]] == back[m.COL["保管フォルダ名"]] == back[m.COL["保管ファイル名"]] == ""
    assert back[m.COL["内容"]] == "訴状"


def test_csv_import_stored_at():
    assert m.normalize_stored_at("2025/3/1 10:00") == "2025-03-01 10:00:00"
    assert m.normalize_stored_at("2025-03-01 10:00:07") == "2025-03-01 10:00:07"
    assert m.normalize_stored_at("") == ""
    assert m.normalize_stored_at("令和7年") is None
    t = m.empty_tables()
    rows = [m.blank_row() for _ in range(3)]
    rows[0][m.COL["番号"]] = rows[1][m.COL["番号"]] = "250101000000"
    rows[0][m.COL["保管日時"]] = "2025/1/1 9:00"
    new = m.add_imported(t, rows)
    numbers = [r[m.COL["番号"]] for r in new[m.STORE].rows]
    assert len(set(numbers)) == 3 and all(numbers)
    bad = m.blank_row()
    bad[m.COL["保管日時"]] = "きのう"
    with pytest.raises(ValueError, match="保管日時"):
        m.add_imported(t, [bad])


def test_delete_row_only_unstored():
    t = m.empty_tables()
    a, b = m.blank_row(), m.blank_row()
    a[m.COL["番号"]], a[m.COL["保管日時"]] = "1", "2025-11-01 10:00:00"
    b[m.COL["番号"]] = "2"
    t[m.STORE].rows = [a, b]
    with pytest.raises(ValueError, match="保管を取り消す"):
        m.delete_row(t, "1")
    assert [r[m.COL["番号"]] for r in m.delete_row(t, "2")[m.STORE].rows] == ["1"]


def test_list_columns_follow_the_store_table():
    """一覧の列は、表「保管」と同じ並び（2026-11-12 班長指示）。事件番号は持たない（同日 班長決定「案B」）。"""
    from va_case.filing.app import COLUMN_WIDTHS, DISPLAY_COLUMNS
    assert DISPLAY_COLUMNS == ["番号", "読込フォルダ名", "読込ファイル名", "日時", "事件呼名", "内容", "保管フォルダ名",
                               "保管ファイル名", "複製作成先", "保管日時", "備考"]
    assert DISPLAY_COLUMNS == m.STORE_COLUMNS
    assert set(COLUMN_WIDTHS) == set(DISPLAY_COLUMNS)



def test_closed_case_destinations_are_not_candidates():
    """VA Case で終了した事件（現況が終了・保管庫へ移した事件）について覚えた保管先は、そのフォルダがまだあっても、
    「VA Case にない保管先」として候補に出さない（2026-11-14 に直した不具合。それまでは、次に保管して表から消える
    〔prune_destinations〕まで、候補に出た。操作マニュアル 5.5「終了した事件は出ません」）。VA Case を使わないときは、
    今までどおり出す。"""
    dest = [["癸山五郎（交通事故）", r"D:\事件\癸山五郎\scan", "佐"], ["乙山（相談）", r"D:\相談\乙山", ""],
            ["民法（文献）", r"D:\文献", ""]]
    names = [c.name for c in m.case_candidates(case_tables(), dest, folder_exists=lambda v: True)]
    assert "癸山五郎（交通事故）" not in names and "乙山（相談）" not in names and "民法（文献）" in names
    names = [c.name for c in m.case_candidates(None, dest, folder_exists=lambda v: True)]
    assert "癸山五郎（交通事故）" in names                       # VA Case を使わない・読めないときは出す
