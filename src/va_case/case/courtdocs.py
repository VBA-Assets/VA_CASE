"""期日請書・送付書の PDF（2021年の版の「期日請書」「送付書」シートを写す。2026-11-09 班長決定）。

どちらも A4 縦、ＭＳ 明朝（なければ reportlab の和文の明朝。埋め込まない）。事件の情報（裁判所事件番号・事件名・
裁判所名・依頼人立場・依頼者と相手方の氏名・代理人）は事件の行から取り、期日・送付書類などは作るときに入れてもらう。
弁護士名は、事務所の設定の「担当区分の詳細」に入れた氏名を既定にする（同）。
"""
import io
import os
from dataclasses import dataclass, field
from datetime import date

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from ..common.dates import to_wareki_long, zenkaku_digits
from . import model as m

PAGE_W, PAGE_H = A4

# 依頼人立場ごとの当事者の組（2021年の版の期日請書の IFS と同じ）
PAIRS = {}
for _a, _b in (("原告", "被告"), ("申立人", "相手方"), ("債権者", "債務者"), ("控訴人", "被控訴人")):
    PAIRS[_a] = PAIRS[_b] = (_a, _b)

# 期日の名前の候補（入力欄の選択肢。自由に入れてもよい）
HEARING_KINDS = ("第1回口頭弁論期日", "口頭弁論期日", "弁論準備手続期日", "書面による準備手続協議期日", "進行協議期日",
                 "和解期日", "証拠調べ期日", "判決言渡期日", "審尋期日", "調停期日", "審判期日")

# 事務所の設定（「選択肢」の表に、項目と値で持つ）
OFFICE_TEL = "事務所の電話番号"
OFFICE_FAX = "事務所のFAX番号"
OFFICE_ITEMS = (OFFICE_TEL, OFFICE_FAX)

_FONT = None


def font_name():
    global _FONT
    if _FONT:
        return _FONT
    path = r"C:\Windows\Fonts\msmincho.ttc"
    if os.name == "nt" and os.path.exists(path):
        try:
            pdfmetrics.registerFont(TTFont("VACase-Mincho", path, subfontIndex=0))
            _FONT = "VACase-Mincho"
            return _FONT
        except Exception:
            pass
    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiMin-W3"))
    _FONT = "HeiseiMin-W3"
    return _FONT


# ---------------------------------------------------------------- 事件の行から取る値

def first_line(text):
    lines = [x.strip() for x in (text or "").split("\n") if x.strip()]
    return lines[0] if lines else ""


def last_line(text):
    """欄の最後の行（控訴審などで、裁判所・事件番号を下に足していく使い方のため。2021年の版と同じ）。"""
    lines = [x.strip() for x in (text or "").split("\n") if x.strip()]
    return lines[-1] if lines else ""


def parties(row):
    """当事者の2行 [(呼び方, 氏名), (呼び方, 氏名)]。依頼人立場が組にないときは、依頼者・相手方とする。"""
    stand = row[m.COL["依頼人立場"]]
    client, other = first_line(row[m.COL["依頼者氏名"]]), first_line(row[m.COL["相手方氏名"]])
    if stand not in PAIRS:
        return [("依頼者", client), ("相手方", other)]
    return [(label, client if label == stand else other) for label in PAIRS[stand]]


def opposite(stand):
    pair = PAIRS.get(stand)
    if not pair:
        return "相手方"
    return pair[1] if pair[0] == stand else pair[0]


def lawyer_names(choice_table, row):
    """担当区分の詳細から、弁護士の氏名の候補を出す（「・」で区切った順。末尾の「先生」は除く）。"""
    detail = m.choice_detail(choice_table, "担当区分", row[m.COL["担当区分"]])
    names = []
    for x in detail.replace("、", "・").split("・"):
        x = x.strip()
        if x.endswith("先生"):
            x = x[:-2].strip()
        if x:
            names.append(x)
    return names


def office_value(choice_table, item):
    vals = m.choice_values(choice_table, item)
    return vals[0] if vals else ""


def spaced(name):
    """氏名を1字ずつ空ける（2021年の版の期日請書の署名と同じ。例：甲　野　太　郎）。"""
    chars = [c for c in name if not c.isspace()]
    return "\u3000".join(chars)


# ---------------------------------------------------------------- 描く道具

class _Pen:
    def __init__(self, c):
        self.c = c
        self.font = font_name()

    def width(self, s, size):
        return pdfmetrics.stringWidth(s, self.font, size)

    def text(self, x, y, s, size=12, align="left"):
        self.c.setFont(self.font, size)
        if align == "right":
            self.c.drawRightString(x, y, s)
        elif align == "center":
            self.c.drawCentredString(x, y, s)
        else:
            self.c.drawString(x, y, s)

    def fit(self, x, y, s, max_width, size=12):
        while size > 7 and self.width(s, size) > max_width:
            size -= 0.5
        self.text(x, y, s, size)

    def wrap(self, x, y, s, max_width, size=12, leading=None):
        """字単位で折り返して書く。書き終えた次の行の y を返す。"""
        leading = leading or size * 1.75
        line = ""
        for ch in s:
            if ch == "\n" or self.width(line + ch, size) > max_width:
                self.text(x, y, line, size)
                y -= leading
                line = "" if ch == "\n" else ch
            else:
                line += ch
        if line:
            self.text(x, y, line, size)
            y -= leading
        return y

    def checkbox(self, x, y, checked, size=3.6 * mm):
        self.c.setLineWidth(0.6)
        self.c.rect(x, y - 0.6 * mm, size, size)
        if checked:
            self.c.setLineWidth(1.0)
            self.c.line(x + 0.7 * mm, y + 1.2 * mm, x + 1.5 * mm, y + 0.2 * mm)
            self.c.line(x + 1.5 * mm, y + 0.2 * mm, x + size - 0.5 * mm, y + size - 1.0 * mm)

    def line(self, x1, y1, x2, y2, width=0.5, dash=None):
        self.c.setLineWidth(width)
        if dash:
            self.c.setDash(*dash)
        self.c.line(x1, y1, x2, y2)
        if dash:
            self.c.setDash()


def _canvas(title):
    """PDF の書き出し先。title（文書のプロパティの題）には、書類の種類だけを入れる。

    期日請書・送付書は、mints で裁判所に出したり、相手方に送ったりするので、事務所の中で使う事件呼名（依頼者の名前など）を
    プロパティに入れない（2026-11-11 班長決定「外す」。それまでは「期日請書 甲野太郎（貸金）」のように入れていた）。
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(title)
    c.setCreator("VA Case")
    return buf, c


def case_title(row):
    """「裁判所事件番号　事件名」（どちらも欄の最後の行。数字は全角）。"""
    no = zenkaku_digits(last_line(row[m.COL["裁判所事件番号"]]))
    name = last_line(row[m.COL["事件名"]])
    return "\u3000".join(x for x in (no, name) if x)


# ---------------------------------------------------------------- 期日請書

@dataclass
class HearingInfo:
    hearing: str          # 期日の名前（例：第1回口頭弁論期日）
    when: str             # 期日の日時（書類に書く形。例：令和７年１２月１日午前１０時３０分）
    lawyer: str           # 弁護士の氏名
    made_on: date = field(default_factory=date.today)
    court: str = None     # 宛先の裁判所名（None なら事件の裁判所名の最後の行。画面で直せる。2026-11-11）


def build_hearing_ack(row, info):
    """期日請書の PDF（バイト列）。"""
    buf, c = _canvas("期日請書")
    pen = _Pen(c)
    left, right = 28 * mm, PAGE_W - 15 * mm
    y = PAGE_H - 30 * mm
    pen.fit(left, y, case_title(row), right - left)
    for label, name in parties(row):
        y -= 8 * mm
        pen.text(left, y, label)
        pen.fit(left + 22 * mm, y, name, right - left - 22 * mm)
    y -= 17 * mm
    pen.text((left + right) / 2, y, "期\u3000日\u3000請\u3000書", size=16, align="center")
    y -= 16 * mm
    pen.text(right, y, zenkaku_digits(to_wareki_long(info.made_on)), align="right")
    y -= 22 * mm
    court = last_line(row[m.COL["裁判所名"]]) if info.court is None else info.court
    pen.text(left, y, f"{court}\u3000御中" if court else "\u3000\u3000\u3000\u3000\u3000\u3000御中")
    y -= 22 * mm
    stand = row[m.COL["依頼人立場"]]
    pen.text(right, y, f"{stand}訴訟代理人弁護士\u3000{spaced(info.lawyer)}", align="right")
    y -= 22 * mm
    body = f"\u3000上記当事者間の御庁頭書事件の{zenkaku_digits(info.hearing)}（{info.when}）をお請けします。"
    y = pen.wrap(left, y, body, right - left)
    y -= 4 * mm
    pen.text(right, y, "以上", align="right")
    c.showPage()
    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------- 送付書

@dataclass
class SendInfo:
    court: str = None                   # 裁判所名（None なら事件の裁判所名の最後の行。画面で直せる。2026-11-11）
    court_fax: str = ""                 # 裁判所の FAX 番号
    agent: str = ""                     # 相手方代理人の氏名
    agent_fax: str = ""                 # 相手方代理人の FAX 番号
    lawyer: str = ""                    # 当職の氏名
    office_tel: str = ""
    office_fax: str = ""
    next_hearing: str = ""              # 次回期日（書類に書く形。空なら書かない）
    documents: list = field(default_factory=list)   # [(書類の名前, 枚数)]
    clean_copy: tuple = (False, False, False)        # 後日クリーンコピー提出：送付した書面全部・答弁書・準備書面・書証
    made_on: date = field(default_factory=date.today)


def build_send_letter(row, info):
    """送付書（直送の送付書と受領書）の PDF（バイト列）。"""
    buf, c = _canvas("送付書")
    pen = _Pen(c)
    left, right = 18 * mm, PAGE_W - 13 * mm
    size = 11
    y = PAGE_H - 22 * mm
    pen.text((left + right) / 2, y, "送\u3000付\u3000書", size=15, align="center")
    court = last_line(row[m.COL["裁判所名"]]) if info.court is None else info.court
    y -= 12 * mm
    pen.text(left, y, f"{court}\u3000御中（FAX {info.court_fax or '　　　　　　　'}）", size)
    y -= 7 * mm
    pen.text(left, y, f"弁護士\u3000{info.agent}\u3000先生（FAX {info.agent_fax or '　　　　　　　'}）", size)
    y -= 10 * mm
    y = pen.wrap(left, y, "\u3000下記の事件につき、「送付書類」欄記載の書類を送付します。これを受領した代理人は、下段「受領書」"
                          "部分に記名捺印のうえ、当職と裁判所にこの書面を送付してください。", right - left, size)
    y -= 2 * mm
    pen.text(left, y, zenkaku_digits(to_wareki_long(info.made_on)), size)
    stand = row[m.COL["依頼人立場"]]
    y -= 8 * mm
    pen.text(right - 10 * mm, y, f"{stand}代理人弁護士\u3000{info.lawyer}", size, align="right")
    pen.text(right, y, "印", size, align="right")
    y -= 7 * mm
    tel = f"（TEL {info.office_tel}、FAX {info.office_fax}）" if (info.office_tel or info.office_fax) else ""
    pen.text(right, y, tel, size - 1, align="right")

    # 事件の欄
    y -= 6 * mm
    top = y
    label_w = 14 * mm
    lines = [case_title(row), "\u3000".join(f"{a}：{b}" for a, b in parties(row))]
    if info.next_hearing:
        lines.append(f"次回期日\u3000{info.next_hearing}")
    row_h = 7 * mm
    bottom = top - row_h * len(lines) - 2 * mm
    c.setLineWidth(0.8)
    c.rect(left, bottom, right - left, top - bottom)
    pen.line(left + label_w, top, left + label_w, bottom)
    pen.text(left + label_w / 2, (top + bottom) / 2 - 1.5 * mm, "事\u3000件", size, align="center")
    for i, s in enumerate(lines):
        pen.fit(left + label_w + 3 * mm, top - (i + 1) * row_h + 1 * mm, s, right - left - label_w - 6 * mm, size)

    # 送付書類の欄
    docs = [(n, p) for n, p in info.documents if n.strip()]
    top = bottom
    n_rows = max(len(docs), 3) + 3
    bottom = top - row_h * n_rows - 2 * mm
    c.rect(left, bottom, right - left, top - bottom)
    pen.line(left + label_w, top, left + label_w, bottom)
    for i, ch in enumerate("送付書類"):
        pen.text(left + label_w / 2, (top + bottom) / 2 + 9 * mm - i * 6 * mm, ch, size, align="center")
    x0 = left + label_w + 3 * mm
    total = sum(p for _, p in docs)
    yy = top - row_h + 1 * mm
    pen.text(x0, yy, "送付書を除く送付枚数", size)
    pen.text(right - 4 * mm, yy, f"{total}枚", size, align="right")
    for i in range(max(len(docs), 3)):
        yy -= row_h
        name, pages = docs[i] if i < len(docs) else ("", 0)
        pen.checkbox(x0, yy, bool(name))
        pen.fit(x0 + 6 * mm, yy, name, right - x0 - 30 * mm, size)
        if name:
            pen.text(right - 4 * mm, yy, f"{pages}枚", size, align="right")
    yy -= row_h
    pen.text(x0, yy, "※次の書面につき、後日正式書面としてクリーンコピー提出", size - 1)
    yy -= row_h
    for (label, checked), dx in zip(zip(("送付した書面全部", "答弁書・準備書面", "書証"), info.clean_copy),
                                    (0, 52 * mm, 104 * mm)):
        pen.checkbox(x0 + dx, yy, checked)
        pen.text(x0 + dx + 6 * mm, yy, label, size)

    # 受領書（切り取り線の下）
    y = bottom - 10 * mm
    pen.line(left, y, right, y, 0.5, dash=(3, 2))
    y -= 10 * mm
    pen.text((left + right) / 2, y, "受\u3000領\u3000書", size=14, align="center")
    y -= 10 * mm
    pen.text(left, y, f"{court}\u3000御中", size)
    y -= 7 * mm
    pen.text(left, y, f"{stand}代理人弁護士\u3000{info.lawyer}\u3000先生" if stand else f"弁護士\u3000{info.lawyer}\u3000先生",
             size)
    y -= 10 * mm
    pen.text(left + 4 * mm, y, "上記書類を受領しました。", size)
    y -= 9 * mm
    pen.text(left + 30 * mm, y, f"{'令和' if info.made_on >= date(2019, 5, 1) else ''}\u3000\u3000年\u3000\u3000月\u3000\u3000日",
             size)
    y -= 10 * mm
    pen.text(left + 30 * mm, y, f"{opposite(stand)}代理人", size)
    pen.line(left + 60 * mm, y - 1 * mm, right - 12 * mm, y - 1 * mm, 0.4)
    pen.text(right, y, "印", size, align="right")
    c.showPage()
    c.save()
    return buf.getvalue()


def file_name(kind, row, day=None):
    """「20261113_期日請書_甲野太郎（貸金）.pdf」「20261113_送付書_…」（事件メモと同じ付け方。model.document_file_name）。"""
    return m.document_file_name(kind, row, day)
