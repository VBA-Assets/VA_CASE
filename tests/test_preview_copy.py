"""プレビューの文字を選んでコピーする（2026-11-13 班長決定「OCR も入れる」・班長指示「通常の文字列の選択方式の方が
良い」「コピーもCtrl+Cで行う」）の試験。書類はすべて架空。"""
import io
import time
from types import SimpleNamespace

import pytest

from va_case.common import ocr, page_text as pt
from va_case.common.ui import preview as pv
from conftest import reset_root

pdfium = pytest.importorskip("pypdfium2")
Image = pytest.importorskip("PIL.Image")

LINES = (("準備書面（架空）", 720), ("令和7年(ワ)第1234号 VA Filing", 400))


def make_pdf(path=None, lines=LINES, size=24):
    """文字の入った A4 の PDF（上の方と真ん中に1行ずつ）。"""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas
    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("HeiseiKakuGo-W5", size)
    for text, y in lines:
        c.drawString(72, y, text)
    c.showPage()
    c.save()
    data = buf.getvalue()
    if path is not None:
        path.write_bytes(data)
    return data


def as_image(data, dpi=200):
    return pdfium.PdfDocument(data)[0].render(scale=dpi / 72).to_pil().convert("RGB")


def as_image_pdf(data):
    """文字の層のない PDF（スキャンと同じ：ページを画像にして、画像だけの PDF にする）。"""
    buf = io.BytesIO()
    as_image(data).save(buf, "PDF", resolution=200)
    return buf.getvalue()


def ocr_or_skip():
    try:
        ocr._get_engine()
    except ocr.OcrUnavailable:
        pytest.skip("この PC では OCR が使えない")


def middle(text, line):
    ln = text.lines[line]
    return (ln.left + ln.right) / 2, (ln.top + ln.bottom) / 2


# ------------------------------------------------------------ ページの字と位置（page_text.py）

def test_pdf_text_and_positions():
    text = pt.load("pdf", make_pdf(), 0)
    assert text.how == "pdf" and len(text.lines) == 2
    assert text.text(0, len(text.chars)) == "準備書面（架空）\n令和7年(ワ)第1234号 VA Filing"
    first, second = text.lines
    assert first.bottom < 0.2 and 0.4 < second.top < 0.6 and first.left < 0.15     # 画面での位置（割合）
    # 字の左半分なら字の前、右半分なら字の後
    c = text.chars[2]
    y = (c[2] + c[4]) / 2
    assert text.pos_at(c[1] + (c[3] - c[1]) * 0.2, y) == 2 and text.pos_at(c[1] + (c[3] - c[1]) * 0.8, y) == 3
    assert text.pos_at(0.99, y) == first.end and text.pos_at(0.0, y) == first.start   # 行の右・左の外
    assert text.text(first.start, second.start + 2) == "準備書面（架空）\n令和"
    assert len(text.rects(0, second.start + 2)) == 2                                   # 行ごとに1つ
    # ダブルクリック（同じ種類の字が続く範囲）・トリプルクリック（行）
    x, y = middle(text, 1)
    s = text.text(*text.word_at(text.chars[second.start + 9][1] + 0.001, y))
    assert s == "1234"
    assert text.text(*text.line_range(x, y)) == "令和7年(ワ)第1234号 VA Filing"


def test_rotated_page():
    """ページに向き（/Rotate）があっても、画面に出た向きの位置にする。"""
    doc = pdfium.PdfDocument(make_pdf())
    doc[0].set_rotation(90)                   # 右に90度：ページの上の方の行は、画面では右の方に縦に出る
    buf = io.BytesIO()
    doc.save(buf)
    text = pt.load("pdf", buf.getvalue(), 0)
    first = next(ln for ln in text.lines if "準備書面" in text.text(ln.start, ln.end))
    assert first.left > 0.75 and first.vertical()
    # 縦に出た行でも、上から下へなぞって選べる
    x = (first.left + first.right) / 2
    a = text.pos_at(x, text.chars[first.start][2] - 0.01)
    b = text.pos_at(x, text.chars[first.start + 3][4] - 0.001)
    assert text.text(a, b) == "準備書面"
    assert len(text.rects(a, b)) == 1


def test_ocr_row_joins_characters():
    """Windows の文字認識は1字ずつの語で返す。間が空いているときだけ空白を入れ、カタカナの間の「-」は「ー」にする。"""
    h = 0.02
    words = [("全", 0.10, 0, 0.12, h), ("3", 0.122, 0, 0.13, h), ("ペ", 0.132, 0, 0.152, h), ("-", 0.153, 0, 0.17, h),
             ("ジ", 0.171, 0, 0.191, h), ("VA", 0.25, 0, 0.28, h), ("Filing", 0.29, 0, 0.35, h)]
    row = pt._ocr_row(words)
    text = pt.PageText.from_lines([row], "ocr")
    assert text.text(0, len(text.chars)) == "全3ページ VA Filing"
    assert [c[0] for c in row[-6:]] == list("Filing") and row[-6][1] == pytest.approx(0.29)   # 語の幅を字で分ける


def test_fit_for_ocr():
    assert ocr.fit_for_ocr(Image.new("L", (300, 30))).size == (1200, 120)     # 低い画像は拡大（4倍まで）
    assert max(ocr.fit_for_ocr(Image.new("RGB", (8000, 1000))).size) == ocr.MAX_SIDE
    assert ocr.fit_for_ocr(Image.new("RGB", (800, 600))).size == (800, 600)


def test_ocr_when_no_text_layer():
    ocr_or_skip()
    data = make_pdf(size=28)
    text = pt.load("pdf", as_image_pdf(data), 0)                   # 文字の層のない PDF
    assert text.how == "ocr"
    lines = [text.text(ln.start, ln.end) for ln in text.lines]
    assert any("準備書面" in s for s in lines) and any("1234" in s for s in lines)
    buf = io.BytesIO()
    as_image(data).save(buf, "PNG")
    assert "準備書面" in pt.load("image", buf.getvalue(), 0).text(0, 10_000)   # 画像（写真・スキャンの JPG など）


def test_ocr_unavailable(monkeypatch):
    """読み取れない PC（Mac・日本語の文字認識がない）では、そのわけを返す（落ちない）。"""
    def no_engine():
        raise ocr.OcrUnavailable(ocr.UNAVAILABLE)
    monkeypatch.setattr(ocr, "_get_engine", no_engine)
    with pytest.raises(ocr.OcrUnavailable, match="読み取れません"):
        pt.load("pdf", as_image_pdf(make_pdf()), 0)
    assert pt.load("pdf", make_pdf(), 0).how == "pdf"            # PDF の文字は、そのまま使える


# ------------------------------------------------------------ プレビューの欄で選ぶ

@pytest.fixture(scope="module")
def root(tk_root):   # Tk は試験の全体で1つ（conftest の tk_root）。この試験の後で、作った部品を片付ける
    r = tk_root
    r.deiconify()
    r.geometry("420x640")
    yield r
    reset_root(r)


def wait_until(root, cond, seconds=15):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        if cond():
            return True
        time.sleep(0.02)
    return False


def screen(pane, index, fx, fy):
    """ページの割合の位置を、欄の中の画素にする。"""
    px, py, pw, ph = pane._pages[index]
    return int(px + fx * pw - pane.canvas.canvasx(0)), int(py + fy * ph - pane.canvas.canvasy(0))


def drag(root, pane, start, end, index=0):
    c = pane.canvas
    x0, y0 = screen(pane, index, *start)
    x1, y1 = screen(pane, index, *end)
    c.event_generate("<Motion>", x=x0, y=y0)
    c.event_generate("<ButtonPress-1>", x=x0, y=y0)
    c.event_generate("<B1-Motion>", x=(x0 + x1) // 2, y=(y0 + y1) // 2)
    c.event_generate("<B1-Motion>", x=x1, y=y1)
    c.event_generate("<ButtonRelease-1>", x=x1, y=y1)
    root.update()


def make_pane(root, path):
    pane = pv.PreviewPane(root)
    pane.pack(fill="both", expand=True)
    root.update()
    pane.show(path)
    assert wait_until(root, lambda: pane.drawn >= 1)
    return pane


def test_select_and_copy_with_ctrl_c(root, tmp_path):
    make_pdf(tmp_path / "a.pdf")
    pane = make_pane(root, tmp_path / "a.pdf")
    assert pane.canvas.cget("cursor") == "xterm"
    text = pt.load("pdf", make_pdf(), 0)
    first = text.lines[0]
    y = (first.top + first.bottom) / 2
    before = pane._bases[0].copy()
    root.clipboard_clear()
    root.clipboard_append("前の値")
    drag(root, pane, (0.0, y), (text.chars[3][3] + 0.001, y))            # 行の左から4字目の右まで
    assert wait_until(root, lambda: pane.selected_text() == "準備書面")
    assert root.clipboard_get() == "前の値"                               # 選んだだけでは、コピーしない
    shown = pane._photos[0]._PhotoImage__photo                             # 選んだ字に色が付く
    assert shown.get(*[int(v) for v in screen_on_page(pane, text.chars[1])]) != \
        before.getpixel(tuple(int(v) for v in screen_on_page(pane, text.chars[1])))
    key(root, pane)
    pane.canvas.event_generate("<Control-c>")
    root.update()
    assert root.clipboard_get() == "準備書面" and pane.copied == "準備書面"
    # 2行にわたって選ぶ
    second = text.lines[1]
    drag(root, pane, (text.chars[5][1] + 0.001, y), (text.chars[second.start + 2][3] + 0.001,
                                                       (second.top + second.bottom) / 2))
    assert pane.selected_text() == "架空）\n令和7"
    # ダブルクリック・トリプルクリック・Ctrl+A
    x2, y2 = screen(pane, 0, text.chars[second.start + 9][1] + 0.001, (second.top + second.bottom) / 2)
    pane.canvas.event_generate("<ButtonPress-1>", x=x2, y=y2)
    click = SimpleNamespace(x=x2, y=y2)      # Tk は、ダブルクリックの出来事を作れないので、受ける関数を呼ぶ
    assert pane.canvas.bind("<Double-Button-1>") and pane.canvas.bind("<Triple-Button-1>")
    pane._select_unit(click, "word")
    assert pane.selected_text() == "1234"
    pane._select_unit(click, "line")
    assert pane.selected_text() == "令和7年(ワ)第1234号 VA Filing"
    key(root, pane)
    pane.canvas.event_generate("<Control-a>")
    root.update()
    assert pane.selected_text() == "準備書面（架空）\n令和7年(ワ)第1234号 VA Filing"
    # Shift+左右の矢印キーで、なぞり終えた側の端を1字ずつ動かす（2026-11-13 班長指示）。改行は続けて越える
    drag(root, pane, (0.0, y), (text.chars[3][3] + 0.001, y))
    assert pane.selected_text() == "準備書面"
    key(root, pane)
    pane.canvas.event_generate("<Shift-Right>")
    root.update()
    assert pane.selected_text() == "準備書面（"
    pane.canvas.event_generate("<Shift-Left>")
    pane.canvas.event_generate("<Shift-Left>")
    root.update()
    assert pane.selected_text() == "準備書"
    for _ in range(6):
        pane.extend_by_char(1)
    assert pane.selected_text() == "準備書面（架空）\n令"      # 行の終わりの後は、次の行の1字目まで
    # ページの外をクリックしたら、選ぶのをやめる
    pane.canvas.event_generate("<ButtonPress-1>", x=pane.canvas.winfo_width() - 3, y=2)
    root.update()
    assert pane.selection is None and pane.selected_text() == ""
    pane.destroy()


def key(root, pane):
    """キーを、プレビューの欄に送れるようにする（アプリでは、欄を押したときに入力先を欄に移す。試験の窓は前に
    出ていないことがあり、そのままでは、キーが欄に届かない）。"""
    pane.canvas.focus_force()
    root.update()


def screen_on_page(pane, ch):
    """字の真ん中の、ページの絵の中の画素。"""
    w, h = pane._bases[0].size
    return (ch[1] + ch[3]) / 2 * w, (ch[2] + ch[4]) / 2 * h


def test_select_before_text_arrives_and_file_change(root, tmp_path):
    """字が届く前に押してなぞっても、届いたら押した点から選ぶ。ほかのファイルに移ったら、届いた字は捨てる。"""
    make_pdf(tmp_path / "a.pdf")
    pane = make_pane(root, tmp_path / "a.pdf")
    text = pt.load("pdf", make_pdf(), 0)
    first = text.lines[0]
    y = (first.top + first.bottom) / 2
    c = pane.canvas
    x0, y0 = screen(pane, 0, 0.0, y)
    x1, _ = screen(pane, 0, text.chars[1][3] + 0.001, y)
    c.event_generate("<ButtonPress-1>", x=x0, y=y0)       # <Motion> なしで押す（まだ頼んでいない）
    c.event_generate("<B1-Motion>", x=x1, y=y0)
    assert 0 not in pane.texts
    assert wait_until(root, lambda: pane.selected_text() == "準備")
    c.event_generate("<ButtonRelease-1>", x=x1, y=y0)
    pane.show(None)
    pane._worker.read_text(pane._file_token - 1, tmp_path / "a.pdf", 0)    # 前のファイルの頼みの返事
    root.update()
    time.sleep(0.5)
    root.update()
    assert pane.texts == {} and pane.selection is None
    pane.destroy()


def test_scanned_page_selection(root, tmp_path):
    """文字の層のないページも、読み取った字を選んでコピーできる。コピーしても知らせは出さない（2026-11-13 班長指示）。"""
    ocr_or_skip()
    path = tmp_path / "スキャン.pdf"
    path.write_bytes(as_image_pdf(make_pdf(size=28)))
    pane = make_pane(root, path)
    pane.canvas.event_generate("<Motion>", x=50, y=50)
    assert wait_until(root, lambda: 0 in pane.texts)
    pane.canvas.focus_force()
    pane.canvas.event_generate("<ButtonPress-1>", x=50, y=50)
    key(root, pane)
    pane.canvas.event_generate("<Control-a>")
    pane.canvas.event_generate("<Control-c>")
    root.update()
    assert "準備書面" in root.clipboard_get()
    assert not pane.canvas.find_withtag("toast")
    pane.destroy()


def test_text_request_does_not_stop_drawing(root, tmp_path):
    """描いている途中で字を頼んでも、描く続きは止めず、字の頼みも捨てない。"""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    path = tmp_path / "長い.pdf"
    c = canvas.Canvas(str(path), pagesize=A4)
    for i in range(12):
        c.setFont("Helvetica", 30)
        c.drawString(72, 720, f"PAGE {i + 1}")
        c.showPage()
    c.save()
    pane = pv.PreviewPane(root)
    pane.pack(fill="both", expand=True)
    root.update()
    pane.show(path)
    assert wait_until(root, lambda: pane.drawn >= 1)
    pane._ask_text(0)
    assert wait_until(root, lambda: pane.drawn == 12 and 0 in pane.texts)
    assert pane.texts[0].text(0, 100) == "PAGE 1"
    pane.destroy()


def test_paste_into_one_line_field(root):
    """何行かの文字を1行の欄に貼り付けると、1行につなげる（英数字どうしの間だけ空白）。"""
    from tkinter import ttk

    from va_case.common.ui import theme
    assert theme.one_line("東京都千代田区\r\n1丁目\n\n") == "東京都千代田区1丁目"
    assert theme.one_line("VA\nFiling\n2025") == "VA Filing 2025"
    theme.apply_theme(root)
    e = ttk.Entry(root)
    e.pack()
    e.insert(0, "前後")
    e.icursor(1)
    e.focus_force()
    root.clipboard_clear()
    root.clipboard_append("甲山\n文具店")
    root.update()
    e.event_generate("<<Paste>>")
    root.update()
    assert e.get() == "前甲山文具店後"
    root.clipboard_clear()
    root.clipboard_append("1行")
    e.event_generate("<<Paste>>")                 # 1行は、そのまま入れる
    root.update()
    assert e.get() == "前甲山文具店1行後"
    e.state(["readonly"])
    root.clipboard_clear()
    root.clipboard_append("x\ny")
    e.event_generate("<<Paste>>")                 # 直せない欄には入れない
    root.update()
    assert e.get() == "前甲山文具店1行後"
    e.destroy()
