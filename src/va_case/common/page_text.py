"""プレビューのページの文字と、その位置（VA Filing・VA Receipt で、プレビューの文字を選んでコピーするため）。

2026-11-13 班長指示「VA FILINGと VA RECEIPTで、プレビュー画像の中の文字列をコピーできるようにできないか？」・
班長決定「OCR も入れる」。同日 班長指示「通常の文字列の選択方式の方が良い」「コピーもCtrl+Cで行う」で、範囲を囲む
方式から、ふつうの文字の選び方（字の上をなぞる）に改めた。

- PDF に文字が入っていれば、その字と位置を使う（pypdfium2）。入っていなければ（スキャン・受信した FAX・写真）、
  ページの画像を Windows の文字認識で読み取り、字と位置を知る（common/ocr.py）。
- 位置は、画面に出したページの幅・高さに対する割合（左上が 0、右下が 1）。ページの向き（/Rotate）と切り取りは、
  描くときと同じに扱う。
- 字は、行ごとに読む順に並べ、行の間に改行（"\\n"）を置く。選ぶ範囲は、字の間の位置（0 から字の数まで）で表す。
- 画面の部品（Tk）には触らない。プレビューの裏のスレッドで作り、画面のスレッドで使う。
"""
import io
import unicodedata
from dataclasses import dataclass, field

OCR_DPI = 300                   # 文字の入っていないページを読み取るときの細かさ
OCR_MAX_PIXELS = 40_000_000     # そのときに描くページの画素の上限（大きな紙で、メモリを使いすぎないように）
LETTER_GAP = 0.35       # 読み取った英字の語の間が、字の高さのこれだけ空いていれば空白を入れる（「VA Filing」など）
WIDE_GAP = 0.8          # ほか（日本語・数字）の字の間が、字の高さのこれだけ空いていれば空白を入れる。数字は、日本語の
                        # 書体では1字ごとに間が空いて見えるため、英字より広くとる（「2025」が「2 0 2 5」にならないように）
HYPHENS = "-‐－―─"


@dataclass
class Line:
    top: float
    bottom: float
    left: float
    right: float
    start: int          # 行の最初の字の番号
    end: int            # 行の最後の字の次の番号（行の後の改行の番号）
    ux: float = 1.0     # 読む向き（単位の長さ）。横書きは (1, 0)。ページに向き（/Rotate）があると縦になる
    uy: float = 0.0

    def along(self, x, y):
        """読む向きに沿った位置。"""
        return x * self.ux + y * self.uy

    def vertical(self):
        return abs(self.uy) > abs(self.ux)


@dataclass
class PageText:
    chars: list                         # (字, 左, 上, 右, 下)。改行は ("\n", …)
    how: str                            # "pdf"（PDF の文字）か "ocr"（読み取った）
    lines: list = field(default_factory=list)

    @classmethod
    def from_lines(cls, rows, how):
        """rows：行ごとの、字の (字, 左, 上, 右, 下) のリスト。"""
        chars, lines = [], []
        for row in rows:
            if not row:
                continue
            if chars:
                last = chars[-1]
                chars.append(("\n", last[3], last[2], last[3], last[4]))
            start = len(chars)
            chars.extend(row)
            ux, uy = 1.0, 0.0
            if len(row) > 1:      # 最初の字から最後の字への向き
                dx = (row[-1][1] + row[-1][3] - row[0][1] - row[0][3]) / 2
                dy = (row[-1][2] + row[-1][4] - row[0][2] - row[0][4]) / 2
                n = (dx * dx + dy * dy) ** 0.5
                if n > 0:
                    ux, uy = dx / n, dy / n
            lines.append(Line(min(c[2] for c in row), max(c[4] for c in row), min(c[1] for c in row),
                              max(c[3] for c in row), start, len(chars), ux, uy))
        return cls(chars, how, lines)

    def _center(self, i, ln):
        c = self.chars[i]
        return ln.along((c[1] + c[3]) / 2, (c[2] + c[4]) / 2)

    def has_text(self):
        return any(c[0].strip() for c in self.chars)

    # ------------------------------------------------------------ 位置と字

    def _line_at(self, x, y):
        """(x, y) にいちばん近い行（上下の離れ、次に左右の離れで比べる）。"""
        def distance(ln):
            dy = 0 if ln.top <= y <= ln.bottom else min(abs(y - ln.top), abs(y - ln.bottom))
            dx = 0 if ln.left <= x <= ln.right else min(abs(x - ln.left), abs(x - ln.right))
            return (dy, dx)
        return min(self.lines, key=distance) if self.lines else None

    def pos_at(self, x, y):
        """(x, y) に近い、字の間の位置（その字の前半分なら字の前、後ろ半分なら字の後）。"""
        ln = self._line_at(x, y)
        if ln is None:
            return 0
        at = ln.along(x, y)
        for i in range(ln.start, ln.end):
            if at < self._center(i, ln):
                return i
        return ln.end

    def char_at(self, x, y):
        """(x, y) の字の番号（行の外なら、いちばん近い字）。字がなければ None。"""
        ln = self._line_at(x, y)
        if ln is None or ln.start == ln.end:
            return None
        at = ln.along(x, y)
        for i in range(ln.start, ln.end - 1):
            if at < (self._center(i, ln) + self._center(i + 1, ln)) / 2:
                return i
        return ln.end - 1

    def text(self, a, b):
        """a から b までの字（行の後ろの空白は除く）。"""
        a, b = sorted((a, b))
        s = "".join(c[0] for c in self.chars[a:b])
        return "\n".join(part.rstrip() for part in s.split("\n")).strip("\n")

    def rects(self, a, b):
        """a から b までを選んだときに、色を付ける長方形（行ごとに1つ）。"""
        a, b = sorted((a, b))
        out = []
        for ln in self.lines:
            i0, i1 = max(a, ln.start), min(b, ln.end)
            if i0 >= i1:
                continue
            part = self.chars[i0:i1]
            if ln.vertical():
                out.append((ln.left, min(c[2] for c in part), ln.right, max(c[4] for c in part)))
            else:
                out.append((min(c[1] for c in part), ln.top, max(c[3] for c in part), ln.bottom))
        return out

    def word_at(self, x, y):
        """(x, y) の字と、同じ種類（漢字・ひらがな・カタカナ・英数字）が続く範囲。→ (a, b)。ダブルクリックで選ぶ。"""
        i = self.char_at(x, y)
        if i is None:
            return (0, 0)
        ln = next(ln for ln in self.lines if ln.start <= i < ln.end)
        kind = _kind(self.chars[i][0])
        a = b = i
        if kind is not None:
            while a > ln.start and _kind(self.chars[a - 1][0]) == kind:
                a -= 1
            while b + 1 < ln.end and _kind(self.chars[b + 1][0]) == kind:
                b += 1
        return (a, b + 1)

    def line_range(self, x, y):
        """(x, y) の行の全体。→ (a, b)。トリプルクリックで選ぶ。"""
        ln = self._line_at(x, y)
        return (ln.start, ln.end) if ln else (0, 0)


def _kind(ch):
    if ch.isascii():
        return "a" if ch.isalnum() else None
    if "ぁ" <= ch <= "ゖ":
        return "h"
    if "ァ" <= ch <= "ヺ" or ch in "ーｰ" or "ｦ" <= ch <= "ﾝ":
        return "k"
    if ch in "々〆ヶ" or unicodedata.name(ch, "").startswith("CJK UNIFIED"):
        return "c"
    if unicodedata.category(ch)[0] in "LN":     # 全角の英数字など
        return "a"
    return None


# ------------------------------------------------------------ 作る（裏のスレッドで）

def load(kind, data, index):
    """index ページ目（0 から）の字と位置。PDF に文字がなければ、画像を読み取る。→ PageText。
    読み取れない PC では ocr.OcrUnavailable、ページを読めなければ ValueError。"""
    if kind == "pdf":
        page_text, image = _from_pdf(data, index)
        if page_text is not None:
            return page_text
    else:
        image = _image_page(data, index)
    return from_ocr(image)


def _from_pdf(data, index):
    """→ (PageText か None, 文字がないときに読み取る、ページの画像)。"""
    import ctypes

    import pypdfium2 as pdfium
    import pypdfium2.raw as raw
    try:
        doc = pdfium.PdfDocument(data)
    except pdfium.PdfiumError:
        raise ValueError("PDF を読めませんでした。")
    try:
        page = doc[index]
        try:
            w, h = page.get_width(), page.get_height()    # 画面に出した向きの大きさ（描くときと同じ）
            sx, sy = 10000, max(1, round(10000 * h / max(w, 1)))

            def to_screen(px, py):
                dx, dy = ctypes.c_int(), ctypes.c_int()
                raw.FPDF_PageToDevice(page, 0, 0, sx, sy, 0, px, py, dx, dy)
                return dx.value / sx, dy.value / sy

            textpage = page.get_textpage()
            try:
                rows = _pdf_rows(textpage, to_screen)
            finally:
                textpage.close()
            page_text = PageText.from_lines(rows, "pdf")
            if page_text.has_text():
                return page_text, None
            scale = OCR_DPI / 72
            if w * h * scale * scale > OCR_MAX_PIXELS:
                scale = (OCR_MAX_PIXELS / max(w * h, 1)) ** 0.5
            bitmap = page.render(scale=scale)
            try:
                image = bitmap.to_pil().convert("RGB")
            finally:
                bitmap.close()
        finally:
            page.close()
    except pdfium.PdfiumError:
        raise ValueError(f"PDF の {index + 1} ページ目を読めませんでした。")
    finally:
        doc.close()
    return None, image


def _pdf_rows(textpage, to_screen):
    """PDF の字を行に分ける。pdfium が入れる改行で分け、改行がなくても、字の高さが前の字の行から外れたら分ける。"""
    n = textpage.count_chars()
    if n <= 0:
        return []
    s = textpage.get_text_range(0, n)
    same_length = len(s) == n
    rows, row = [], []
    for i in range(n):
        ch = s[i] if same_length else textpage.get_text_range(i, 1)
        if ch in "\r\n":                         # pdfium が入れた改行（\r\n）
            if row:
                rows.append(row)
                row = []
            continue
        left, bottom, right, top = textpage.get_charbox(i, loose=True)
        x0, y0 = to_screen(left, top)
        x1, y1 = to_screen(right, bottom)
        box = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        if box[2] - box[0] <= 0 and box[3] - box[1] <= 0 and row:   # 位置のない字（足された空白など）
            prev = row[-1]
            box = (prev[3], prev[2], prev[3], prev[4])
        if row and _new_line(row[-1], box):
            rows.append(row)                     # pdfium の改行がなくても、別の行に移った
            row = []
        row.append((ch,) + box)
    if row:
        rows.append(row)
    return rows


def _new_line(prev, box):
    """前の字 prev から、次の字 box が別の行に移ったか（横にも縦にも、前の字の並びから外れた）。"""
    def outside(a0, a1, b0, b1):
        margin = (a1 - a0) / 2
        middle = (b0 + b1) / 2
        return not (a0 - margin <= middle <= a1 + margin)
    return outside(prev[2], prev[4], box[1], box[3]) and outside(prev[1], prev[3], box[0], box[2])


def _image_page(data, index):
    from PIL import Image, ImageOps
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.seek(index)
            return ImageOps.exif_transpose(im.convert("RGB"))   # 画面に出したのと同じ向き
    except (OSError, ValueError, EOFError, Image.DecompressionBombError):
        raise ValueError("画像を読めませんでした。")


def from_ocr(image):
    """画像を読み取って、字と位置を作る。"""
    from . import ocr
    return PageText.from_lines([_ocr_row(words) for words in ocr.recognize_lines(image)], "ocr")


def _ocr_row(words):
    """読み取った1行の語を、字に分ける。語の間が実際に空いているときだけ空白を入れる（Windows の文字認識は、日本語を
    1字ずつの語として返すので、語ごとに空白を入れると「試 用 の」になる）。カタカナの間の「-」は「ー」に直す。"""
    words = sorted((w for w in words if w[0]), key=lambda w: w[1])
    if not words:
        return []
    heights = sorted(w[4] - w[2] for w in words)
    h = max(heights[len(heights) // 2], 1e-9)
    row = []
    for k, (text, x0, y0, x1, y1) in enumerate(words):
        if k:
            prev = words[k - 1]
            letters = prev[0][-1].isascii() and prev[0][-1].isalpha() and text[0].isascii() and text[0].isalpha()
            if x0 - prev[3] > (LETTER_GAP if letters else WIDE_GAP) * h:
                row.append((" ", prev[3], min(prev[2], y0), x0, max(prev[4], y1)))
        step = (x1 - x0) / len(text)
        for j, ch in enumerate(text):                # 語の中の字は、幅を等しく分ける
            row.append((ch, x0 + step * j, y0, x0 + step * (j + 1), y1))
    for j in range(1, len(row) - 1):
        if row[j][0] in HYPHENS and _kind(row[j - 1][0]) == "k" and _kind(row[j + 1][0]) == "k":
            row[j] = ("ー",) + row[j][1:]
    return row
