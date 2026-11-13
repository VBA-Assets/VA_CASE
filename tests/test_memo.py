"""事件メモの PDF の試験。氏名は架空。"""
from datetime import date

from va_case.case import memo
from va_case.case import model as m


def make(**kw):
    row = m.blank_row(101)
    row[m.COL["事件呼名"]] = "甲野太郎（貸金）"
    for k, v in kw.items():
        row[m.COL[k]] = v
    return row


def test_part_like_fncsplit():
    assert memo.part("乙山次郎\n丙川三郎", 2) == "丙川三郎"
    assert memo.part("乙山次郎", 3) == "" and memo.part("", 1) == ""


def test_second_page_only_when_needed():
    assert memo.page_count(make(相手方氏名="乙\n丙\n丁")) == 1
    assert memo.page_count(make(相手方氏名="乙\n丙\n丁\n戊")) == 2
    assert memo.page_count(make(代理人="丁\n戊", 代理人住所="a\nb\nc\nd")) == 2
    # 名前が1人なら、値の行が何行あっても1人と数える（2026-11-12 班長決定）
    assert memo.page_count(make(代理人="丁", 代理人住所="a\nb\nc\nd")) == 1
    assert memo.page_count(make(依頼者氏名="甲野太郎", 電話番号="1\n2\n3\n4")) == 1


def test_one_person_with_several_phones_stays_on_one_row():
    """1人の依頼者の電話番号を2行に入れても、2つ目が名前のない2人目の段に出ない（2026-11-12 班長決定）。"""
    row = make(依頼者氏名="甲野太郎", 住所="東京都千代田区架空町1-1\n架空ビル101", 電話番号="03-0000-0001\n090-0000-0002",
               相手方氏名="乙山次郎\n丙川三郎", 相手方電話番号="06-0000-0003\n06-0000-0004",
               代理人="弁護士 丁野四郎", 代理人電話番号="06-0000-0005\n06-0000-0006", 代理人FAX番号="06-0000-0007")
    client, other, agents = memo._parties(row, 1)
    assert client[0] == ("甲野太郎", "東京都千代田区架空町1-1　架空ビル101", "03-0000-0001・090-0000-0002", "")
    assert client[1] == ("", "", "", "")
    assert [o[2] for o in other] == ["06-0000-0003", "06-0000-0004", ""]     # 2人なら、今までどおり1行ずつ
    assert agents[0][2:] == ("06-0000-0005・06-0000-0006", "06-0000-0007") and agents[1] == ("", "", "", "")


def test_build_pdf():
    data = memo.build_pdf(make(依頼人立場="破産者", 依頼者氏名="甲野太郎", 代理人="弁護士 己野六郎"))
    assert data.startswith(b"%PDF") and data.count(b"/Type /Page\n") + data.count(b"/Type /Page ") >= 1
    row = make(事件呼名="甲野太郎（貸金）")
    assert memo.memo_file_name(row, date(2026, 11, 13)) == "20261113_事件メモ_甲野太郎（貸金）.pdf"


def test_case_number_small_at_top_left():
    """事件番号は、文書の左上に小さい字で書く（2026-11-11 班長指示）。2ページ目（【続き】）も同じ。"""
    fitz = __import__("pytest").importorskip("fitz")
    doc = fitz.open(stream=memo.build_pdf(make(相手方氏名="乙\n丙\n丁\n戊")), filetype="pdf")
    assert doc.page_count == 2
    for page in doc:
        spans = [s for b in page.get_text("dict")["blocks"] for line in b.get("lines", []) for s in line["spans"]]
        number = next(s for s in spans if s["text"].startswith("事件番号"))
        assert number["text"].strip() == "事件番号 101"
        assert number["size"] < 8                                        # 小さい字
        top = min(s["bbox"][1] for s in spans)
        assert number["bbox"][1] == top and number["bbox"][0] < 50       # いちばん上の、左の端
        texts = [s["text"] for s in spans]
        # 標題「事件メモ」と事件呼名は書かない。2ページ目の頭だけ「【続き】」（2026-11-11 班長決定「VBA版と同じにする」）
        assert "事件メモ" not in texts and not any("甲野太郎（貸金）" in x for x in texts)
        assert ("【続き】" in texts) == (page.number == 1)


def test_split_line_for_two_line_address():
    font = memo.font_name()
    head, rest = memo.split_line("東京都千代田区一番町1-1", 500, font)
    assert (head, rest) == ("東京都千代田区一番町1-1", "")                          # 収まれば1行
    head, rest = memo.split_line("東京都千代田区一番町1-1 一番町マンション1001号室", 100, font)
    assert head and rest and head + rest == "東京都千代田区一番町1-1 一番町マンション1001号室"


def test_long_address_goes_to_second_line_and_fits_on_a4():
    """住所は2行に書き、収まらない分は2行目に出す（2026-11-11 班長指示）。1ページに収まり、作成日の行と重ならない。"""
    fitz = __import__("pytest").importorskip("fitz")
    addr = "大阪府大阪市北区梅田一丁目2番3号 梅田ビルディング南館15階"
    doc = fitz.open(stream=memo.build_pdf(make(依頼者氏名="甲野太郎", 住所=addr)), filetype="pdf")
    page = doc[0]
    text = page.get_text()
    assert doc.page_count == 1
    joined = "".join(line.strip() for line in text.splitlines())
    assert addr.replace(" ", "") in joined.replace(" ", "")                         # 2行に分けても、全部書いてある
    foot = next(b for b in page.get_text("blocks") if "VA Case" in b[4])
    lowest = max([d["rect"].y1 for d in page.get_drawings()] +
                 [b[3] for b in page.get_text("blocks") if "VA Case" not in b[4]])
    assert lowest < foot[1] < page.rect.height


def test_document_file_name():
    """書類の名前「yyyymmdd_書類_事件呼名.pdf」（2026-11-13 班長決定）。使えない字は全角、事件呼名が空なら事件番号。"""
    day = date(2026, 11, 13)
    assert m.document_file_name("送付書", make(事件呼名="甲野/乙山（A:B）"), day) == "20261113_送付書_甲野／乙山（A：B）.pdf"
    assert m.document_file_name("事件メモ", make(事件番号="2500101", 事件呼名=""), day) == "20261113_事件メモ_2500101.pdf"
