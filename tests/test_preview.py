"""プレビュー（VA Filing・VA Receipt の左側。2026-11-12 班長決定）の試験。書類はすべて架空。"""
import io
import os
import time
import tkinter as tk

import pytest

from va_case.common.ui import preview as pv
from conftest import reset_root

pytest.importorskip("pypdfium2")
Image = pytest.importorskip("PIL.Image")


def make_pdf(path, pages=2, encrypt=None):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(path), pagesize=A4, encrypt=encrypt)
    for i in range(pages):
        c.drawString(72, 720, f"page {i + 1}")
        c.showPage()
    c.save()
    return path


def test_kind_of():
    assert pv.kind_of("a.PDF") == "pdf"
    assert pv.kind_of("領収書.jpeg") == "image" and pv.kind_of("fax.TIF") == "image"
    assert pv.kind_of("準備書面.docx") is None and pv.kind_of("名前なし") is None


def test_read_file_closes_the_file(tmp_path):
    """読んだら閉じる：読んだ直後に、ファイルを移せる（保管を妨げない）。"""
    p = make_pdf(tmp_path / "訴状.pdf")
    kind, data = pv.read_file(p)
    assert kind == "pdf" and data.startswith(b"%PDF")
    os.replace(p, tmp_path / "移した.pdf")


def test_read_file_errors(tmp_path):
    with pytest.raises(pv.PreviewError, match="プレビューできません"):
        pv.read_file(tmp_path / "準備書面.docx")
    with pytest.raises(pv.PreviewError, match="見つかりません"):
        pv.read_file(tmp_path / "ない.pdf")


def pages(kind, data, width, limit=pv.MAX_PAGES):
    return [(i, im.size, n) for i, im, n in pv.iter_pages(kind, data, width, limit)]


def test_render_pdf_pages(tmp_path):
    _, data = pv.read_file(make_pdf(tmp_path / "a.pdf", pages=3))
    got = pages("pdf", data, 400)
    assert [i for i, _, _ in got] == [0, 1, 2] and all(n == 3 for _, _, n in got)
    assert all(w == 400 and h > 500 for _, (w, h), _ in got)            # A4 縦を幅に合わせる
    assert [i for i, _, _ in pages("pdf", data, 300, limit=2)] == [0, 1]   # 並べるのは上限まで


def test_render_pdf_errors(tmp_path):
    _, data = pv.read_file(make_pdf(tmp_path / "鍵.pdf", encrypt="secret"))
    with pytest.raises(pv.PreviewError, match="パスワード"):
        pages("pdf", data, 300)
    with pytest.raises(pv.PreviewError, match="PDF を読めません"):
        pages("pdf", b"%PDF-1.4 broken", 300)


def test_render_images(tmp_path):
    buf = io.BytesIO()
    Image.new("RGB", (200, 100), "white").save(buf, "PNG")
    assert pages("image", buf.getvalue(), 400) == [(0, (400, 200), 1)]
    frames = [Image.new("L", (100, 140), v) for v in (255, 128)]       # 2ページの TIFF（FAX など）
    buf = io.BytesIO()
    frames[0].save(buf, "TIFF", save_all=True, append_images=frames[1:])
    assert pages("image", buf.getvalue(), 50) == [(0, (50, 70), 2), (1, (50, 70), 2)]
    with pytest.raises(pv.PreviewError, match="画像を読めません"):
        pages("image", b"not an image", 100)


@pytest.fixture(scope="module")
def root(tk_root):   # Tk は試験の全体で1つ（conftest の tk_root）。この試験の後で、作った部品を片付ける
    r = tk_root
    r.deiconify()
    r.geometry("400x600")
    yield r
    reset_root(r)


def wait_until(root, cond, seconds=10):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_pane_shows_pages_and_messages(root, tmp_path):
    """見出しもページのボタンもなく、ページを縦に並べる（2026-11-12 班長指示）。"""
    pane = pv.PreviewPane(root)
    pane.pack(fill="both", expand=True)
    root.update()
    assert not [w for w in pane.winfo_children() if isinstance(w, (tk.Button, pv.ttk.Button, pv.ttk.Label))]
    pdf = make_pdf(tmp_path / "a.pdf", pages=3)
    pane.show(pdf)
    assert wait_until(root, lambda: pane.drawn == 3)
    assert pane.count == 3 and len(pane._photos) == 3
    heights = [pane.canvas.bbox(i)[1] for i in pane.canvas.find_all() if pane.canvas.type(i) == "image"]
    assert heights == sorted(heights) and len(set(heights)) == 3        # 上から順に並ぶ
    os.replace(pdf, tmp_path / "移した.pdf")                  # 出している間も、ファイルを移せる
    pane.show(tmp_path / "準備書面.docx")
    assert wait_until(root, lambda: pane.error)
    assert "プレビューできません" in pane.error and not pane._photos
    pane.show(None)
    assert not pane._photos and pane.path is None
    # 隠している間は読まず、出したら読む
    pane.set_active(False)
    pane.show(tmp_path / "移した.pdf")
    root.update()
    time.sleep(0.2)
    root.update()
    assert pane.drawn == 0
    pane.set_active(True)
    assert wait_until(root, lambda: pane.drawn == 3)
    pane.destroy()


def test_many_pages_stop_at_the_limit(root, tmp_path, monkeypatch):
    monkeypatch.setattr(pv, "MAX_PAGES", 2)
    pane = pv.PreviewPane(root)
    pane.pack(fill="both", expand=True)
    root.update()
    pane.show(make_pdf(tmp_path / "長い.pdf", pages=4))
    assert wait_until(root, lambda: pane.drawn == 2)
    root.update()
    texts = [pane.canvas.itemcget(i, "text") for i in pane.canvas.find_all() if pane.canvas.type(i) == "text"]
    assert texts and "3 ページ目からは" in texts[0] and "全部で 4 ページ" in texts[0]
    pane.destroy()


def test_old_results_are_dropped(root, tmp_path):
    """続けて別のファイルを選んだら、最後のものだけを出す。"""
    pane = pv.PreviewPane(root)
    pane.pack(fill="both", expand=True)
    root.update()
    a = make_pdf(tmp_path / "a.pdf", pages=1)
    b = make_pdf(tmp_path / "b.pdf", pages=3)
    pane.show(a)
    pane.show(b)
    assert wait_until(root, lambda: pane.drawn == 3)
    root.update()
    time.sleep(0.2)
    root.update()
    assert pane.path == b and pane.count == 3 and len(pane._photos) == 3
    pane.destroy()


def test_same_width_does_not_redraw(root, tmp_path):
    """幅が変わらないときは描き直さない（送った位置が先頭に戻らないように）。"""
    pane = pv.PreviewPane(root)
    pane.pack(fill="both", expand=True)
    root.update()
    pane.show(make_pdf(tmp_path / "a.pdf", pages=3))
    assert wait_until(root, lambda: pane.drawn == 3)
    gen = pane._gen
    pane.canvas.yview_moveto(0.5)
    pane._after_resize()
    root.update()
    assert pane._gen == gen and pane.canvas.yview()[0] > 0.3
    pane.destroy()


def test_wait_while_moving_by_key(root, tmp_path):
    """一覧を矢印キーで送っている間は出さず、止まって KEY_WAIT_MS たったら、最後のファイルだけを出す（2026-11-13 班長指示）。"""
    pane = pv.PreviewPane(root)
    pane.pack(fill="both", expand=True)
    root.update()
    a = make_pdf(tmp_path / "a.pdf", pages=1)
    b = make_pdf(tmp_path / "b.pdf", pages=2)
    c = make_pdf(tmp_path / "c.pdf", pages=3)
    pane.show(a)
    assert wait_until(root, lambda: pane.drawn == 1)
    asked = []
    real_ask = pane._worker.ask
    pane._worker.ask = lambda gen, path, width: (asked.append(path), real_ask(gen, path, width))
    for path in (b, c):                       # 送っている間：前のページを消し、読まない
        pane.show(path, wait=True)
        root.update()
        assert not pane.canvas.find_all() and not pane._photos and not asked
    assert wait_until(root, lambda: pane.drawn == 3)
    assert asked == [c] and pane.path == c
    pane.show(None)                           # 待っている間に行の選択を外したら、待ちも捨てる
    pane.show(a, wait=True)
    pane.show(None)
    root.update()
    time.sleep(pv.KEY_WAIT_MS / 1000 + 0.2)
    root.update()
    assert asked == [c] and pane.path is None
    pane.destroy()
