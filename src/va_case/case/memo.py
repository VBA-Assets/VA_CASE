"""事件メモの PDF（現行の「事件メモ」シート。sht12.bas。2026-11-09 班長決定：PDF を作る）。

現行のシートと同じ項目を A4 の縦に描く。
- 上：事件番号（左上に小さく）、受任日・提起日（手書きの欄）、データフォルダ、事件名（裁判所名・事件名・裁判所事件番号）、
  管轄裁判所・裁判官・書記官・TEL・FAX（手書きの欄）
- 当事者：左に依頼者（依頼人立場）、右に相手方（依頼人立場の反対。原告⇔被告、申立人⇔相手方）。1ページに3人ずつ。
  各人は、改行で区切った欄の何番目か（現行の FncSplit と同じ）で対応を取る
- 代理人：相手方の側に書く。依頼人立場が「破産者」のときは依頼者の側に書く（現行と同じ）
- 期日（第1回〜第11回の記入欄）、書証（甲・乙・調書・関係書類の冊数の記入欄）
4人目以降の当事者・代理人がいるときだけ、2ページ目（【続き】）を作る（現行と同じ）。
"""
import io
import os
from datetime import date

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from ..common.dates import display as date_display
from . import model as m

PAGE_W, PAGE_H = A4
LEFT, RIGHT, TOP = 15 * mm, PAGE_W - 15 * mm, PAGE_H - 14 * mm
LINE = 5.2 * mm           # 期日・書証の1行の高さ（手で書き込むので、広めにとる）
# 当事者・代理人の1行の高さ。住所を2行にして1人分が1行増えた分、A4 の1ページに収まるよう、詰める（2026-11-11）
PEOPLE_LINE = 4.0 * mm
PEOPLE_BASE = 1.0 * mm   # 当事者・代理人の行の、下の罫線から字の並びの線までの高さ
PERSONS_PER_PAGE = 3

OPPOSITE = {"原告": "被告", "被告": "原告", "申立人": "相手方", "相手方": "申立人"}
# 期日の表の見出し（左の列から。2026-11-10 班長指示：左端を「期日」、その右を「年月日」に）
DATE_HEADINGS = ("期日", "年月日", "時刻", "予定", "結果", "経過報告書送付日")

_FONT = None


def font_name():
    """Windows ではＭＳ ゴシック（埋め込む）、なければ reportlab の和文の書体（埋め込まない）。"""
    global _FONT
    if _FONT:
        return _FONT
    path = r"C:\Windows\Fonts\msgothic.ttc"
    if os.name == "nt" and os.path.exists(path):
        try:
            pdfmetrics.registerFont(TTFont("VACase-Gothic", path, subfontIndex=0))
            _FONT = "VACase-Gothic"
            return _FONT
        except Exception:
            pass
    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
    _FONT = "HeiseiKakuGo-W5"
    return _FONT


def part(text, n):
    """改行で区切った欄の n 番目（1 から）。なければ ""（現行の FncSplit）。"""
    items = (text or "").split("\n")
    return items[n - 1].strip() if 0 < n <= len(items) else ""


def count_lines(text):
    return len([x for x in (text or "").split("\n") if x.strip()])


# 人の段のまとまり（名前の列と、その人ごとの値の列）
GROUPS = (("依頼者氏名", ("住所", "電話番号")),
          ("相手方氏名", ("相手方住所", "相手方電話番号")),
          ("代理人", ("代理人住所", "代理人電話番号", "代理人FAX番号")))
# 1人の値が何行かあるときに、1行に並べるときの区切り（住所は続けて読めるよう全角の空白、電話番号などは「・」）
ADDRESS_COLUMNS = ("住所", "相手方住所", "代理人住所")


def detail(row, names_col, col, n):
    """名前の列 names_col の n 番目（1 から）の人の、列 col の値。

    名前が1人（か、空）なら、値が何行あっても、全部をその人のものとして1行に並べる（2026-11-12 班長決定「事件メモを
    直す」。1人の依頼者の電話番号を「03-…」「090-…」の2行に入れると、2つ目の番号が名前のない2人目の段に出ていた。
    現行の FncSplit も同じだった）。2人以上なら、今までどおり n 行目（1行目が1人目）。
    """
    value = row[m.COL[col]]
    if count_lines(row[m.COL[names_col]]) <= 1:
        if n != 1:
            return ""
        lines = [s.strip() for s in (value or "").split("\n") if s.strip()]
        return ("　" if col in ADDRESS_COLUMNS else "・").join(lines)
    return part(value, n)


def page_count(row):
    """4人目以降がいるときだけ2ページ（現行と同じ）。名前が1人のまとまりは、値の行が何行あっても1人と数える。"""
    most = 0
    for names_col, cols in GROUPS:
        if count_lines(row[m.COL[names_col]]) > 1:
            most = max([most] + [count_lines(row[m.COL[c]]) for c in (names_col,) + cols])
    return 2 if most > PERSONS_PER_PAGE else 1


class _Pen:
    def __init__(self, c):
        self.c = c
        self.font = font_name()

    def text(self, x, y, s, size=9.5, max_width=None):
        """s を (x, y) に書く。max_width を超えるときは、字を小さくして収める（6pt まで。それでも長ければ切る）。"""
        s = s or ""
        while max_width and size > 6 and pdfmetrics.stringWidth(s, self.font, size) > max_width:
            size -= 0.5
        if max_width:
            while s and pdfmetrics.stringWidth(s, self.font, size) > max_width:
                s = s[:-1]
        self.c.setFont(self.font, size)
        self.c.drawString(x, y, s)

    def center(self, x1, x2, y, s, size=9.5):
        """s を x1〜x2 の中央に書く。"""
        self.c.setFont(self.font, size)
        self.c.drawCentredString((x1 + x2) / 2, y, s)

    def hline(self, x1, x2, y, width=0.5):
        self.c.setLineWidth(width)
        self.c.line(x1, y, x2, y)

    def vline(self, x, y1, y2, width=0.5):
        self.c.setLineWidth(width)
        self.c.line(x, y1, x, y2)

    def box(self, x1, y1, x2, y2, width=0.8):
        self.c.setLineWidth(width)
        self.c.rect(x1, y2, x2 - x1, y1 - y2)


def _header(pen, row, continued, court=("", "")):
    y = TOP
    v = lambda c: row[m.COL[c]]  # noqa: E731
    # 事件番号は、文書の左上に小さい字で書く（2026-11-11 班長指示。それまでは事件呼名の前に並べていた）
    pen.text(LEFT, PAGE_H - 9 * mm, f"事件番号 {v('事件番号')}", size=7.5)
    # 標題と事件呼名は書かない。2ページ目だけ「【続き】」と書く（2026-11-11 班長決定「VBA版と同じにする」。現行の
    # 事件メモのシートには標題も事件呼名もなく、2ページ目の頭に【続き】がある。それまでは「事件メモ」「事件メモ【続き】」の
    # 標題と、その横に事件呼名を書いていた）
    if continued:
        pen.text(LEFT, y - 5 * mm, "【続き】", size=14)
    for i, label in enumerate(("【受任日】", "【提起日】")):
        yy = y - 4 * mm - i * 6 * mm
        pen.text(RIGHT - 48 * mm, yy, label, size=9)
        pen.hline(RIGHT - 30 * mm, RIGHT, yy - 1 * mm)
    y -= 15 * mm
    pen.text(LEFT, y, "データフォルダ　" + v("データフォルダ"), size=7.5, max_width=RIGHT - LEFT)
    y -= 4 * mm
    # 事件名
    top = y
    pen.box(LEFT, top, RIGHT, top - 13 * mm)
    pen.vline(LEFT + 24 * mm, top, top - 13 * mm)
    pen.text(LEFT + 2 * mm, top - 8 * mm, "【事件名】", size=9.5)
    pen.text(LEFT + 26 * mm, top - 5.5 * mm, f"{v('裁判所名')}　{v('裁判所事件番号')}", size=10,
             max_width=RIGHT - LEFT - 28 * mm)
    pen.text(LEFT + 26 * mm, top - 11 * mm, v("事件名"), size=10.5, max_width=RIGHT - LEFT - 28 * mm)
    y = top - 13 * mm
    # 裁判所（手書きの欄）
    top = y
    pen.box(LEFT, top, RIGHT, top - 18 * mm)
    lines = [("（管轄裁判所）", v("裁判所名"), None, None), ("（裁判官）", "", "（書記官）", ""),
             ("【ＴＥＬ】", court[0], "【ＦＡＸ】", court[1])]   # 事務所の設定の「裁判所」の番号（2026-11-11）
    mid = LEFT + (RIGHT - LEFT) / 2
    for i, (l1, t1, l2, t2) in enumerate(lines):
        yy = top - 4.5 * mm - i * 5.5 * mm
        pen.text(LEFT + 2 * mm, yy, l1, size=9)
        pen.text(LEFT + 26 * mm, yy, t1, size=9.5, max_width=mid - LEFT - 30 * mm)
        if l2:
            pen.text(mid + 2 * mm, yy, l2, size=9)
            pen.text(mid + 26 * mm, yy, t2, size=9.5, max_width=RIGHT - mid - 30 * mm)
        if i:
            pen.hline(LEFT + 24 * mm, mid - 4 * mm, yy - 1.2 * mm, 0.3)
            pen.hline(mid + 24 * mm, RIGHT - 4 * mm, yy - 1.2 * mm, 0.3)
    return top - 18 * mm - 3 * mm


ADDRESS_FIELD = 1      # 欄の見出しのうち、住所の位置（2行に分けて書く）
VALUE_SIZE = 9.5


def split_line(text, width, font, size=VALUE_SIZE):
    """text を、width に収まる頭の部分と、残りに分ける（収まれば残りは ""）。"""
    text = text or ""
    if pdfmetrics.stringWidth(text, font, size) <= width:
        return text, ""
    n = len(text)
    while n > 1 and pdfmetrics.stringWidth(text[:n], font, size) > width:
        n -= 1
    return text[:n], text[n:]


def _people_block(pen, y, label, left_title, right_title, left_people, right_people, fields):
    """当事者・代理人の組。left_people・right_people：[(欄の値の並び)] を3人分。fields：欄の見出し（4つ）。

    住所は2行に書く（2026-11-11 班長指示「2行にする」。現行のシートも住所が2行ある）。1行目は見出しの右に、
    収まらない分を2行目に、見出しの位置から書く（現行のシートの2行目も、見出しの列から書く）。
    """
    col_l, col_r = LEFT + 10 * mm, LEFT + 10 * mm + (RIGHT - LEFT - 10 * mm) / 2
    head = 6 * mm
    rows = len(fields) + 1          # 1人分の行の数（住所の2行目の分、1つ多い）
    height = head + PERSONS_PER_PAGE * rows * PEOPLE_LINE
    pen.box(LEFT, y, RIGHT, y - height)
    pen.vline(col_l, y, y - height)
    pen.vline(col_r, y, y - height, 0.8)
    for i, ch in enumerate(label):
        pen.text(LEFT + 3 * mm, y - head - 8 * mm - i * 6 * mm, ch, size=11)
    pen.hline(col_l, RIGHT, y - head)
    pen.text(col_l + 2 * mm, y - head + 1.8 * mm, left_title, size=9.5)
    pen.text(col_r + 2 * mm, y - head + 1.8 * mm, right_title, size=9.5)
    width = col_r - col_l
    for side, x0, people in ((0, col_l, left_people), (1, col_r, right_people)):
        for pi in range(PERSONS_PER_PAGE):
            values = people[pi] if pi < len(people) else ("",) * len(fields)
            r = pi * rows
            for fi, f in enumerate(fields):
                yy = y - head - (r + 1) * PEOPLE_LINE
                pen.text(x0 + 2 * mm, yy + PEOPLE_BASE, f, size=8.5)
                if fi == ADDRESS_FIELD:
                    first, rest = split_line(values[fi], width - 21 * mm, pen.font)
                    pen.text(x0 + 19 * mm, yy + PEOPLE_BASE, first, size=VALUE_SIZE)
                    r += 1
                    yy = y - head - (r + 1) * PEOPLE_LINE
                    pen.text(x0 + 2 * mm, yy + PEOPLE_BASE, rest, size=VALUE_SIZE, max_width=width - 4 * mm)
                else:
                    pen.text(x0 + 19 * mm, yy + PEOPLE_BASE, values[fi], size=VALUE_SIZE, max_width=width - 21 * mm)
                r += 1
            # 横の罫線は、人と人の区切り（次の人の【氏名】の上）だけに引く（2026-11-11 班長指示「依頼者が３名記載できるが、
            # その区切りが分かりにくい。VBA版と同じで良い」。現行のシートも、人の区切りにだけ罫線がある。それまでは、
            # 欄ごとに細い罫線を引いていた）
            pen.hline(x0, x0 + width, y - head - (pi + 1) * rows * PEOPLE_LINE, 0.8)
    return y - height - 3 * mm


def _dates_block(pen, y):
    head = 5.5 * mm
    rows = 11
    height = head + rows * LINE
    cols = [LEFT, LEFT + 16 * mm, LEFT + 62 * mm, LEFT + 82 * mm, LEFT + 105 * mm, LEFT + 128 * mm, RIGHT]
    pen.box(LEFT, y, RIGHT, y - height)
    for x in cols[1:-1]:
        pen.vline(x, y, y - height, 0.3)
    # 見出しは列の中央に揃える。左端の列（第1回〜）は「期日」、その右は「年月日」（2026-11-10 班長指示）
    for x1, x2, t in zip(cols, cols[1:], DATE_HEADINGS):
        pen.center(x1, x2, y - head + 1.6 * mm, t, size=8.5)
    pen.hline(LEFT, RIGHT, y - head)
    for i in range(rows):
        yy = y - head - (i + 1) * LINE
        pen.text(LEFT + 2 * mm, yy + 1.5 * mm, f"第{i + 1}回", size=8.5)
        pen.text(cols[1] + 2 * mm, yy + 1.5 * mm, "　　　年　　月　　日", size=8.5)
        pen.text(cols[2] + 2 * mm, yy + 1.5 * mm, "　時　　分", size=8.5)
        pen.text(cols[5] + 1 * mm, yy + 1.5 * mm, "　月　日 郵・手渡し・T・F", size=7.5)
        if i < rows - 1:
            pen.hline(LEFT, RIGHT, yy, 0.25)
    return y - height - 3 * mm


def _evidence_block(pen, y):
    height = 2 * LINE
    pen.box(LEFT, y, RIGHT, y - height)
    pen.vline(LEFT + 16 * mm, y, y - height, 0.3)
    pen.text(LEFT + 2 * mm, y - height / 2 - 1 * mm, "書証", size=9)
    cells = [("甲　　　　冊", "調書　　　　　冊", "関係書類　　　　　　袋"), ("乙　　　　冊", "", "　　　　　　　　　　冊")]
    xs = (LEFT + 18 * mm, LEFT + 62 * mm, LEFT + 105 * mm)
    for i, line in enumerate(cells):
        yy = y - (i + 1) * LINE + 1.5 * mm
        for x, t in zip(xs, line):
            pen.text(x, yy, t, size=9)
    pen.hline(LEFT + 16 * mm, RIGHT, y - LINE, 0.25)


def _parties(row, first):
    v = lambda c: row[m.COL[c]]  # noqa: E731
    rng = range(first, first + PERSONS_PER_PAGE)
    d = lambda names, c, n: detail(row, names, c, n)  # noqa: E731
    client = [(part(v("依頼者氏名"), n), d("依頼者氏名", "住所", n), d("依頼者氏名", "電話番号", n), "") for n in rng]
    other = [(part(v("相手方氏名"), n), d("相手方氏名", "相手方住所", n), d("相手方氏名", "相手方電話番号", n), "")
             for n in rng]
    agents = [(part(v("代理人"), n), d("代理人", "代理人住所", n), d("代理人", "代理人電話番号", n),
               d("代理人", "代理人FAX番号", n)) for n in rng]
    return client, other, agents


def build_pdf(row, choices=None, court=("", "")):
    """事件メモの PDF（バイト列）を作る。court：裁判所の (電話番号, FAX番号)（model.court_numbers。なければ手書きの空欄）。"""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"事件メモ {row[m.COL['事件番号']]} {row[m.COL['事件呼名']]}")
    c.setCreator("VA Case")
    pen = _Pen(c)
    stand = row[m.COL["依頼人立場"]]
    client_title = f"依頼者（{stand}）" if stand else "依頼者"
    other_title = f"相手方（{OPPOSITE[stand]}）" if stand in OPPOSITE else "相手方"
    bankrupt = stand == "破産者"
    for page in range(page_count(row)):
        first = page * PERSONS_PER_PAGE + 1
        y = _header(pen, row, continued=page > 0, court=court)
        client, other, agents = _parties(row, first)
        fields = ("【氏　名】", "【住　所】", "【電　話】", "【ＦＡＸ】")
        y = _people_block(pen, y, "当事者", client_title, other_title, client, other, fields)
        empty = [("",) * 4] * PERSONS_PER_PAGE
        left, right = (agents, empty) if bankrupt else (empty, agents)
        y = _people_block(pen, y, "代理人", client_title, other_title, left, right,
                          ("【弁護士】", "【住　所】", "【電　話】", "【ＦＡＸ】"))
        y = _dates_block(pen, y)
        _evidence_block(pen, y)
        pen.text(LEFT, 8 * mm, f"作成 {date_display(date.today().isoformat())}　VA Case", size=7)
        c.showPage()
    c.save()
    return buf.getvalue()


def memo_file_name(row, day=None):
    """「20261113_事件メモ_甲野太郎（貸金）.pdf」（2026-11-13 班長決定。model.document_file_name）。"""
    return m.document_file_name("事件メモ", row, day)
