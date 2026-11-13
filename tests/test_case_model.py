"""VA Case の事件の扱い（採番・並べ替え・確認・CSV）の試験。氏名・住所は架空。"""
import pytest

from va_case.case import model as m
from va_case.common.csvio import CsvError, export_csv, import_csv


def row(number, status="A:未了", juin="A:事務所", kubun="B:個人一般", name="", **kw):
    r = m.blank_row(number)
    r[m.COL["現況"]], r[m.COL["受任区分"]], r[m.COL["事件区分"]] = status, juin, kubun
    r[m.COL["事件呼名"]] = name or f"事件{number}"
    for k, v in kw.items():
        r[m.COL[k]] = v
    return r


def test_new_case_number_like_vba():
    rows = [row(101), row(102), row(1234)]
    assert m.new_case_number(rows) == 1301                 # 新規の依頼人：最大の百の位を繰り上げ、01
    assert m.new_case_number(rows, rows[0]) == 103         # 同じ依頼人：その依頼人の最大＋1
    assert m.new_case_number(rows, rows[2]) == 1235
    assert m.new_case_number([]) == 101


def test_same_client_copies_client_and_other_party():
    """同じ依頼人の新しい事件は、依頼者・関係者・相手方・代理人の欄を写す（2026-11-12 班長決定）。"""
    base = row(101, name="甲野太郎（貸金）", 依頼者氏名="甲野太郎", ふりがな="こうのたろう", 生年月日="1970-01-01",
               住所="東京都千代田区架空町1-1", 電話番号="03-0000-0001", メールアドレス="kono@example.invalid",
               関係者="甲野花子（妻）", 相手方氏名="乙山次郎", 相手方ふりがな="おつやまじろう", 相手方住所="大阪市架空区2-2",
               相手方電話番号="06-0000-0002", 代理人="丙川三郎", 代理人住所="大阪市架空区3-3",
               代理人電話番号="06-0000-0003", 代理人FAX番号="06-0000-0004", 相談年月日="2026-11-01",
               裁判所名="東京地方裁判所", 裁判所事件番号="令和7年(ワ)第1号", 事件名="貸金返還請求事件",
               データフォルダ="X:\\事件\\101", TeamsURL="https://example.invalid/101", 備考="メモ", 相談内容="貸金")
    new = m.blank_row(102, base)
    for c in m.CASE_COLUMNS:
        if c == "事件番号":
            assert new[m.COL[c]] == "102"
        elif c in m.SAME_CLIENT_COLUMNS:
            assert new[m.COL[c]] == base[m.COL[c]] != "", c
        else:
            assert new[m.COL[c]] == "", c                  # 事件呼名・日付・区分・裁判所・データフォルダなどは写さない
    assert m.blank_row(1301) == [("1301" if c == "事件番号" else "") for c in m.CASE_COLUMNS]   # 新規の依頼人は空


def test_sort_like_vba():
    rows = [row(301, "C:終了"), row(102, "A:未了", kubun="C:個人債務"), row(101, "A:未了", kubun="C:個人債務"),
            row(201, "A:未了", kubun="A:管財"), row(5, "")]
    order = [r[0] for r in m.sorted_rows(rows)]
    assert order == ["201", "101", "102", "301", "5"]      # 現況・受任区分・事件区分・事件番号。空は最後


def test_status_kind():
    assert m.status_kind(row(1, "C:終了")) == "closed"
    assert m.status_kind(row(1, "D:相談のみ")) == "consult"
    assert m.status_kind(row(1, "E:相談不可")) == "refused"
    assert m.status_kind(row(1, "B:精算管理")) == ""


def test_check_folders(tmp_path):
    (tmp_path / "甲野").mkdir()
    rows = [row(101, データフォルダ=str(tmp_path / "甲野")), row(102, データフォルダ=str(tmp_path / "乙山")),
            row(103, データフォルダ="丙川"), row(104)]
    probs = m.check_folders(rows, lambda v: m.resolve_folder(v, str(tmp_path)))
    assert [p.number for p in probs] == ["102", "103"]


def test_upsert_and_delete():
    t = m.empty_tables()
    t = m.upsert_case(t, row(101))
    t = m.upsert_case(t, row(201))
    with pytest.raises(ValueError, match="すでにあります"):
        m.upsert_case(t, row(101))
    changed = row(101, name="甲野太郎（貸金）")
    t2 = m.upsert_case(t, changed, old_number="101")
    assert [r[m.COL["事件呼名"]] for r in t2[m.CASE].rows] == ["甲野太郎（貸金）", "事件201"]
    assert t[m.CASE].rows[0][m.COL["事件呼名"]] == "事件101"   # 元は変えない
    with pytest.raises(ValueError, match="ほかの人が消した"):
        m.upsert_case(t2, row(999), old_number="999")
    assert [r[0] for r in m.delete_case(t2, "101")[m.CASE].rows] == ["201"]


def test_folder_rule_and_year():
    t = m.empty_tables()
    t[m.FOLDER_RULES].rows = [["C:終了", "A:事務所", "B:個人一般", "", r"個人一般\yyyy"]]
    r = row(101, "C:終了", 終了年月日="2025-03-31")
    rule = m.find_folder_rule(t[m.FOLDER_RULES], r)
    assert m.apply_year(rule, m.end_year_text(r)) == r"個人一般\2025"
    r[m.COL["終了年月日"]] = "2016-12-01"
    assert m.end_year_text(r) == "-2017"                    # 2017年以前はまとめる（現行と同じ）
    assert m.find_folder_rule(t[m.FOLDER_RULES], row(102, "A:未了")) is None


def test_csv_roundtrip_with_newlines(tmp_path):
    rows = [row(101, 相手方氏名="乙山次郎\n丙川三郎", 生年月日="1980-04-01", 住所="東京都千代田区一丁目1番1号")]
    path = tmp_path / "事件.csv"
    export_csv(path, m.CASE_COLUMNS, rows)
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    back = import_csv(path, m.CASE_COLUMNS, m.DATE_COLUMNS)
    assert back.rows == rows and back.warnings == []


def test_csv_from_excel_shift_jis_wareki(tmp_path):
    """Excel の「CSV（コンマ区切り）」：Shift_JIS、列の順は問わない、日付は表示の和暦のまま、末尾に空の列。"""
    text = '事件番号,事件呼名,生年月日,相手方氏名,\r\n101,甲野太郎（貸金）,S55.4.1,"乙山次郎\r\n丙川三郎",\r\n'
    path = tmp_path / "excel.csv"
    path.write_bytes(text.encode("cp932"))
    got = import_csv(path, m.CASE_COLUMNS, m.DATE_COLUMNS)
    r = got.rows[0]
    assert got.encoding == "Shift_JIS"
    assert r[m.COL["生年月日"]] == "1980-04-01" and r[m.COL["相手方氏名"]] == "乙山次郎\n丙川三郎"
    assert any("CSV にない列" in w for w in got.warnings)


def test_csv_rejects_unknown_columns(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("事件番号,知らない列\n1,2\n", encoding="utf-8")
    with pytest.raises(CsvError, match="知らない列"):
        import_csv(path, m.CASE_COLUMNS)


def test_csv_header_ignores_width_spaces_and_case(tmp_path):
    """列の名前は、全角と半角・空白・英字の大小の違いを問わない（2026-11-11 班長決定）。読み替えたことは知らせる。"""
    path = tmp_path / "x.csv"
    path.write_text("事件番号,代理人ＦＡＸ番号,事件 呼名,teamsurl\n1,03-0000-0009,甲野太郎（貸金）,https://example.invalid\n",
                    encoding="utf-8")
    got = import_csv(path, m.CASE_COLUMNS, required=("事件番号",))
    r = got.rows[0]
    assert r[m.COL["代理人FAX番号"]] == "03-0000-0009" and r[m.COL["事件呼名"]] == "甲野太郎（貸金）"
    assert r[m.COL["TeamsURL"]] == "https://example.invalid"
    assert any("読み替えました" in w and "「代理人ＦＡＸ番号」を「代理人FAX番号」" in w for w in got.warnings)


def test_csv_unknown_column_shows_missing_ones(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("事件番号,依頼者名\n1,甲野太郎\n", encoding="utf-8")
    with pytest.raises(CsvError) as e:
        import_csv(path, m.CASE_COLUMNS)
    assert "「依頼者名」" in str(e.value) and "CSV にないもの" in str(e.value) and "「依頼者氏名」" in str(e.value)


def test_csv_required_column_and_same_column_twice(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("事件呼名\n甲野太郎（貸金）\n", encoding="utf-8")
    with pytest.raises(CsvError, match="「事件番号」の列がありません"):
        import_csv(path, m.CASE_COLUMNS, required=("事件番号",))
    path.write_text("事件番号,代理人FAX番号,代理人ＦＡＸ番号\n1,a,b\n", encoding="utf-8")
    with pytest.raises(CsvError, match="同じ列が2つ以上"):
        import_csv(path, m.CASE_COLUMNS)


def test_add_imported_rejects_duplicates():
    t = m.upsert_case(m.empty_tables(), row(101))
    with pytest.raises(ValueError) as e:
        m.add_imported(t, [row(101), row(102), row(102), m.blank_row("")])
    msg = str(e.value)
    assert "すでに共有データ" in msg and "CSV の中で重複" in msg and "数ではありません" in msg
    t2 = m.add_imported(t, [row(201), row(102)])
    assert [r[0] for r in t2[m.CASE].rows] == ["101", "102", "201"]


def test_agent_details_from_earlier_cases():
    """代理人から、これまでの事件の代理人住所・電話番号・FAX番号を引く（2026-11-09 班長指示）。"""
    rows = [
        row("101", **{"代理人": "弁護士 己野六郎", "代理人住所": "大阪府大阪市中央区一丁目1番1号\n○○ビル3階",
                      "代理人電話番号": "06-1111-1111", "代理人FAX番号": "06-1111-1112"}),
        row("102", **{"代理人": "弁護士 庚田七郎\n弁護士 己野六郎", "代理人住所": "京都府京都市一丁目\n大阪府大阪市二丁目",
                      "代理人電話番号": "075-000-0000", "代理人FAX番号": ""}),
        row("103", **{"代理人": "弁護士 辛木八郎", "代理人住所": "", "代理人電話番号": "", "代理人FAX番号": ""}),
    ]
    # 新しい行（102）から探す。102 は2人で、住所は2行なので2行目、電話番号は1行なので共通、FAX は空なので 101 から
    assert m.agent_details(rows, "弁護士　己野六郎") == {
        "代理人住所": "大阪府大阪市二丁目", "代理人電話番号": "075-000-0000", "代理人FAX番号": "06-1111-1112"}
    # いま直している事件（102）は除く。代理人が1人の事件の住所は、2行のまま
    assert m.agent_details(rows, "弁護士 己野六郎", exclude="102") == {
        "代理人住所": "大阪府大阪市中央区一丁目1番1号\n○○ビル3階", "代理人電話番号": "06-1111-1111",
        "代理人FAX番号": "06-1111-1112"}
    assert m.agent_details(rows, "弁護士 辛木八郎") == {}
    assert m.agent_details(rows, "弁護士 己野") == {}          # 名前の全体が一致したときだけ
    assert m.agent_details(rows, "") == {}
    # 2人で住所が3行など、どの行が誰のものか決められないときは使わない
    rows.append(row("104", **{"代理人": "弁護士 壬川九郎\n弁護士 癸山十郎", "代理人住所": "一\n二\n三"}))
    assert "代理人住所" not in m.agent_details(rows, "弁護士 壬川九郎")


def test_birthdays_one_per_line():
    """生年月日は1行ずつ日付として読む（2026-11-12 班長決定）。ほかの日付の列は1つだけ。"""
    from va_case.common.dates import display_lines, normalize_dates_text
    assert normalize_dates_text("S50.4.1\n\n 1977/6/3 \n") == "1975-04-01\n1977-06-03"   # 空の行は除く
    assert normalize_dates_text("") == ""
    with pytest.raises(ValueError, match="S50.4.31・R8.2.30"):
        normalize_dates_text("S50.4.31\nS52.6.3\nR8.2.30")
    assert display_lines("1975-04-01\n1977-06-03") == "S50.4.1\nS52.6.3"
    assert display_lines("2025-04-10") == "R7.4.10"
    r = row(101, 生年月日="1975-04-01\n1977-06-03")
    assert m.check_row(r, None) == []
    r[m.COL["生年月日"]] = "1975-04-01\n読めない"
    assert m.check_row(r, None) == ["「生年月日」を日付として読めません：読めない"]
    r = row(101, 相談年月日="2025-04-10\n2025-04-11")
    assert m.check_row(r, None)                              # 相談年月日は1つだけ


def test_csv_birthdays_one_per_line(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text('事件番号,生年月日,相談年月日\n101,"S50.4.1\nS52.6.3",R7.4.10\n102,"S50.4.1\n読めない","R7.4.10\nR7.4.11"\n',
                    encoding="utf-8")
    got = import_csv(path, m.CASE_COLUMNS, m.DATE_COLUMNS, multi_date_columns=m.MULTI_DATE_COLUMNS)
    r1, r2 = got.rows
    assert r1[m.COL["生年月日"]] == "1975-04-01\n1977-06-03" and r1[m.COL["相談年月日"]] == "2025-04-10"
    assert r2[m.COL["生年月日"]] == "S50.4.1\n読めない"          # 読めなければ、知らせてそのまま入れる（今までと同じ）
    assert sum("2 件目" in w for w in got.warnings) == 2
