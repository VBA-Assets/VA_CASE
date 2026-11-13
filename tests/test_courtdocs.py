"""期日請書・送付書の試験。氏名・番号は架空。"""
from datetime import date

from va_case.case import courtdocs as cd
from va_case.case import model as m
from va_case.common import dates


def make(**kw):
    row = m.blank_row(101)
    row[m.COL["事件呼名"]] = "甲野太郎（貸金）"
    for k, v in kw.items():
        row[m.COL[k]] = v
    return row


def test_parties_follow_stand():
    row = make(依頼人立場="被告", 依頼者氏名="甲野太郎\n甲野花子", 相手方氏名="乙山次郎")
    assert cd.parties(row) == [("原告", "乙山次郎"), ("被告", "甲野太郎")]
    assert cd.parties(make(依頼人立場="申立人", 依頼者氏名="甲", 相手方氏名="乙")) == [("申立人", "甲"), ("相手方", "乙")]
    assert cd.parties(make(依頼人立場="破産者", 依頼者氏名="甲"))[0] == ("依頼者", "甲")
    assert cd.opposite("控訴人") == "被控訴人" and cd.opposite("債務者") == "債権者"


def test_case_title_uses_last_line():
    row = make(裁判所事件番号="令和7年(ワ)第1234号\n令和8年(ネ)第56号", 事件名="貸金返還請求事件\n貸金返還請求控訴事件")
    assert cd.case_title(row) == "令和８年(ネ)第５６号　貸金返還請求控訴事件"


def test_lawyer_names_from_choice_detail():
    t = m.empty_tables()[m.CHOICES]
    t.rows.append(["担当区分", "佐・田", "佐藤一郎先生・田中二郎"])
    assert cd.lawyer_names(t, make(担当区分="佐・田")) == ["佐藤一郎", "田中二郎"]
    assert cd.lawyer_names(t, make(担当区分="なし")) == []
    assert cd.spaced("佐藤 一郎") == "佐　藤　一　郎"


def test_datetime_text():
    parsed = dates.parse_datetime("R7.12.1 10:30")
    assert dates.format_datetime_long(*parsed) == "令和７年１２月１日午前１０時３０分"
    assert dates.format_datetime_long(*dates.parse_datetime("2025/12/1 13時5分")) == "令和７年１２月１日午後１時０５分"
    assert dates.parse_datetime("R7.12.1 25:00") is None and dates.parse_datetime("あした") is None
    assert dates.to_wareki_long(date(2019, 5, 1)) == "令和元年5月1日"


def test_build_pdfs():
    row = make(依頼人立場="原告", 依頼者氏名="甲野太郎", 相手方氏名="乙山次郎", 裁判所名="東京地方裁判所",
               裁判所事件番号="令和7年(ワ)第1234号", 事件名="貸金返還請求事件")
    a = cd.build_hearing_ack(row, cd.HearingInfo("第1回口頭弁論期日", "令和７年１２月１日午前１０時３０分", "佐藤一郎"))
    s = cd.build_send_letter(row, cd.SendInfo(lawyer="佐藤一郎", documents=[("準備書面", 3)]))
    assert a.startswith(b"%PDF") and s.startswith(b"%PDF")
    assert cd.file_name("期日請書", row, date(2026, 11, 9)) == f"20261109_期日請書_{row[m.COL['事件呼名']]}.pdf"


def test_send_letter_court_name_from_form():
    """送付書の宛先の裁判所名は、作成の画面で直した名前を使う（空なら事件の裁判所名の最後の行。2026-11-11）。"""
    fitz = __import__("pytest").importorskip("fitz")
    row = make(依頼人立場="原告", 裁判所名="東京地方裁判所\n東京高等裁判所", 裁判所事件番号="令和7年(ネ)第56号",
               事件名="貸金返還請求控訴事件")

    def to_line(info):
        text = fitz.open(stream=cd.build_send_letter(row, info), filetype="pdf")[0].get_text()
        return next(line for line in text.splitlines() if "御中" in line)
    assert to_line(cd.SendInfo(lawyer="佐藤一郎", documents=[("準備書面", 3)])).startswith("東京高等裁判所")
    line = to_line(cd.SendInfo(court="東京高等裁判所第2民事部", court_fax="03-0000-3002", lawyer="佐藤一郎",
                               documents=[("準備書面", 3)]))
    assert line.startswith("東京高等裁判所第2民事部") and "03-0000-3002" in line


def test_hearing_ack_court_name_from_form():
    """期日請書の宛先の裁判所名も、作成の画面で直した名前を使う（送付書と同じ。2026-11-11）。"""
    fitz = __import__("pytest").importorskip("fitz")
    row = make(依頼人立場="原告", 裁判所名="東京地方裁判所\n東京高等裁判所", 裁判所事件番号="令和7年(ネ)第56号",
               事件名="貸金返還請求控訴事件")

    def to_line(info):
        text = fitz.open(stream=cd.build_hearing_ack(row, info), filetype="pdf")[0].get_text()
        return next(line for line in text.splitlines() if "御中" in line)
    hearing = ("第1回口頭弁論期日", "令和７年１２月１日午前１０時３０分", "佐藤一郎")
    assert to_line(cd.HearingInfo(*hearing)).startswith("東京高等裁判所")
    assert to_line(cd.HearingInfo(*hearing, court="東京高等裁判所第2民事部")).startswith("東京高等裁判所第2民事部")


def test_pdf_properties_do_not_carry_case_label():
    """期日請書・送付書の PDF のプロパティに、事件呼名を入れない（mints に出すため。2026-11-11 班長決定）。"""
    fitz = __import__("pytest").importorskip("fitz")
    row = make(依頼人立場="原告", 裁判所名="東京地方裁判所", 裁判所事件番号="令和7年(ワ)第1234号", 事件名="貸金返還請求事件")
    a = cd.build_hearing_ack(row, cd.HearingInfo("第1回口頭弁論期日", "令和７年１２月１日午前１０時３０分", "佐藤一郎"))
    s = cd.build_send_letter(row, cd.SendInfo(lawyer="佐藤一郎", documents=[("準備書面", 3)]))
    for data, title in ((a, "期日請書"), (s, "送付書")):
        meta = fitz.open(stream=data, filetype="pdf").metadata
        assert meta["title"] == title
        assert not any(row[m.COL["事件呼名"]] in str(v) for v in meta.values())
