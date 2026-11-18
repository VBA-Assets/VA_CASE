"""読込ファイル・保管したファイルのプレビュー（VA Filing・VA Receipt。2026-11-12 班長指示「ファイルをプレビューしながら
作業できるととても便利である」。同日 班長決定「プレビューは左側に表示」）。

- PDF（pypdfium2）と画像（Pillow。JPG・PNG・TIFF・BMP・GIF）を、欄の幅に合わせて出す。ほかの種類は出さない。
  どちらも外部と通信しない部品で、VA FAX のプレビューと同じもの（PyMuPDF は AGPL のため使わない）。
- 見出しやページを送るボタンは置かず、ページを上から縦に並べて、ホイール・スクロールバーで送る（2026-11-12 班長指示
  「プレビューのラベルやページ切り替えボタンは不要」。それまでは「プレビュー」の見出しと「前のページ」「次のページ」が
  あった）。並べるのは MAX_PAGES ページまで。描けたページから順に出す。
- ファイルを開いたままにしない：中身をいったんメモリに読んで、すぐ閉じる（保管でファイルを移すときに、使用中で
  失敗しないように）。表示のために、ディスクへ書き出さない。
- 読み込みと描画は、裏の1本のスレッドで行う（同期フォルダ・暗号化したドライブでは時間がかかるため。pdfium は
  スレッドを並べて使えないため1本にする）。その間も画面は使える。ほかのファイルに移ったら、古い頼みは捨てる。
- Tk の部品は、画面のスレッドからだけ触る（裏の結果は待ち行列で受け取る。background.py と同じ考え方）。
"""
import io
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from . import theme
from .keys import ctrl_sequences

PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif"}
MAX_BYTES = 100 * 1024 * 1024   # これより大きいファイルは出さない（メモリに読むため）
MAX_PAGES = 50                  # 並べるページの数の上限（それより後は「ファイルを開く」で見る）
MAX_WIDTH = 2400                # 描く幅の上限（画素）
POLL_MS = 60
RESIZE_DELAY_MS = 250           # 欄の幅を変えている間は描き直さず、止まってから描き直す
# 一覧を矢印キーで送っている間は出さず、キーを止めてこれだけたったら出す（2026-11-13 班長指示「プレビューの表示は、
# カードの表示と同様に、リストを矢印キーで送っている間は表示しないようにする。（矢印キーを離した時に表示する。）」。
# 入力欄の書き換えを待つ SHOW_DELAY_MS〔list_view.py〕と同じ）
KEY_WAIT_MS = 200
MARGIN = 6                      # ページの周りの余白（画素）
GAP = 8                         # ページの間（画素）

NOTE_EMPTY = ("一覧で行を選ぶと、ファイルの中身がここに出ます。\n\n字の上をなぞって選び、Ctrl+C でコピーできます"
              "（入力欄に Ctrl+V で貼り付けます）。")
TOAST_MS = 4000                 # コピーしたことの知らせを出しておく時間
SELECT_COLOR = (0, 120, 212, 80)   # 選んだ字に重ねる色（アクセントの青を薄く）
NOTE_LOADING = "読み込んでいます…"


class PreviewError(Exception):
    """出せないわけ（利用者に示す文）。"""


def kind_of(path):
    """"pdf"・"image"・None（出さない種類）。"""
    ext = Path(path).suffix.lower()
    if ext in PDF_EXTENSIONS:
        return "pdf"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    return None


def read_file(path):
    """ファイルの中身を読む（読んだら閉じる）。→ (種類, bytes)。出せなければ PreviewError。"""
    path = Path(path)
    kind = kind_of(path)
    if kind is None:
        raise PreviewError("この種類のファイルは、プレビューできません（PDF と画像だけ）。\n「ファイルを開く」で開いてください。")
    try:
        size = path.stat().st_size
    except OSError:
        raise PreviewError("ファイルが見つかりませんでした。")
    if size > MAX_BYTES:
        raise PreviewError("ファイルが大きいため、プレビューしません。\n「ファイルを開く」で開いてください。")
    try:
        return kind, path.read_bytes()
    except OSError:
        raise PreviewError("ファイルを読めませんでした（ほかのソフトが使っているか、同期が終わっていない可能性があります）。")


def iter_pages(kind, data, width, limit=MAX_PAGES):
    """1ページ目から順に、幅 width 画素の画像にする。→ (ページの番号〔0 から〕, PIL の画像, ページ数) を順に返す。
    limit ページまで。出せなければ PreviewError（1ページ目で出せなければ、何も返さないうちに）。"""
    width = max(1, min(int(width), MAX_WIDTH))
    if kind == "pdf":
        yield from _pdf_pages(data, width, limit)
    else:
        yield from _image_pages(data, width, limit)


def _pdf_pages(data, width, limit):
    import pypdfium2 as pdfium
    try:
        doc = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as e:
        if "password" in str(e).lower():
            raise PreviewError("パスワードの付いた PDF は、プレビューできません。\n「ファイルを開く」で開いてください。")
        raise PreviewError("PDF を読めませんでした（壊れているか、PDF でない可能性があります）。")
    try:
        count = len(doc)
        if count == 0:
            raise PreviewError("ページのない PDF です。")
        for i in range(min(count, limit)):
            try:
                p = doc[i]
                try:
                    bitmap = p.render(scale=width / max(p.get_width(), 1))
                    try:
                        image = bitmap.to_pil().convert("RGB")
                    finally:
                        bitmap.close()
                finally:
                    p.close()
            except pdfium.PdfiumError:
                raise PreviewError(f"PDF の {i + 1} ページ目を描けませんでした。")
            yield i, image, count
    finally:
        doc.close()


def _image_pages(data, width, limit):
    from PIL import Image, ImageOps
    try:
        im = Image.open(io.BytesIO(data))
    except (OSError, ValueError, Image.DecompressionBombError):
        raise PreviewError("画像を読めませんでした（壊れているか、大きすぎる可能性があります）。")
    with im:
        count = getattr(im, "n_frames", 1) or 1      # TIFF の複数ページ・GIF のこま
        for i in range(min(count, limit)):
            try:
                im.seek(i)
                frame = ImageOps.exif_transpose(im.convert("RGB"))   # スマートフォンの写真の向き
                height = max(1, round(frame.height * width / max(frame.width, 1)))
                image = frame.resize((width, height), Image.LANCZOS)
            except (OSError, ValueError, EOFError, Image.DecompressionBombError):
                raise PreviewError("画像を読めませんでした（壊れているか、大きすぎる可能性があります）。")
            yield i, image, count


class _Worker:
    """裏の1本のスレッド。描く頼みは新しいものだけを行い、描けたページから順に、結果を待ち行列に入れる。新しい描く頼みが
    来たら、描きかけのページの続きはやめる。ページの字と位置の頼み（read_text）は捨てず、描いている途中でも、ページの
    合間に行う。読んだファイルの中身は、次に別のファイルを頼まれるまで覚える（幅を変えるたびに読み直さないため）。

    結果：("page", gen, ページの番号, 画像, ページ数, 出せないわけ)・("text", 頼んだ番号, ページの番号, PageText,
    出せないわけ)"""

    def __init__(self):
        self.jobs = queue.Queue()
        self.results = queue.Queue()
        self._cache = (None, None, None)     # (場所, 種類, 中身)。このスレッドの中だけで使う
        self._next_draw = None               # ページの合間に届いた、描く頼み
        threading.Thread(target=self._run, daemon=True).start()

    def ask(self, gen, path, width):
        self.jobs.put(("draw", gen, path, width))

    def read_text(self, token, path, index):
        self.jobs.put(("text", token, path, index))

    def _data(self, path):
        if self._cache[0] != path:
            self._cache = (None, None, None)
            kind, data = read_file(path)
            self._cache = (path, kind, data)
        return self._cache[1], self._cache[2]

    def _take_jobs(self, block):
        """たまった頼みを受け取る。文字の頼みは、すぐ行う。描く頼みは、最後のものを _next_draw に残す。"""
        while True:
            try:
                job = self.jobs.get(block=block)
            except queue.Empty:
                return
            block = False
            if job[0] == "text":
                self._do_text(*job[1:])
            else:
                self._next_draw = job

    def _do_text(self, token, path, index):
        from .. import ocr, page_text
        try:
            kind, data = self._data(path)
            self.results.put(("text", token, index, page_text.load(kind, data, index), None))
        except (PreviewError, ocr.OcrUnavailable, ValueError) as e:
            self.results.put(("text", token, index, None, str(e)))
        except Exception:                     # 思わぬ誤りでも、文字を選べないと知らせるだけにする
            self.results.put(("text", token, index, None, "このページの文字を取り出せませんでした。"))

    def _run(self):
        while True:
            if self._next_draw is None:
                self._take_jobs(block=True)
            self._take_jobs(block=False)
            if self._next_draw is None:
                continue
            _, gen, path, width = self._next_draw
            self._next_draw = None
            try:
                kind, data = self._data(path)
                for i, image, count in iter_pages(kind, data, width, MAX_PAGES):
                    self.results.put(("page", gen, i, image, count, None))
                    self._take_jobs(block=False)
                    if self._next_draw is not None:
                        break                 # 新しい描く頼みが来た
            except PreviewError as e:
                self.results.put(("page", gen, None, None, 0, str(e)))
            except Exception:                 # 思わぬ誤りでも、プレビューが止まるだけにする
                self.results.put(("page", gen, None, None, 0, "プレビューできませんでした。「ファイルを開く」で開いてください。"))


class PreviewPane(ttk.Frame):
    """プレビューの欄。show(場所) で、そのファイルを出す（None なら何も出さない）。"""

    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)
        self._worker = _Worker()
        self.path = None
        self.count = 0              # ファイルのページ数（わかったら）
        self.drawn = 0              # 出したページの数
        self.active = True          # 欄を出しているか（隠しているときは読まない）
        self.error = ""             # 出せなかったわけ
        self._gen = 0
        self._loaded = False        # いまの場所のファイルを、出した（か、出せないわけを出した）
        self._photos = []
        self._next_y = MARGIN       # 次のページを置く高さ
        self._keep_view = None      # 描き直すときに戻すスクロールの位置
        self._resize_job = None
        self._show_job = None       # あとに回した表示（矢印キーで送っている間）
        self._last_width = 0
        self._asked_width = 0       # いまのファイルを描くよう頼んだ幅
        self._asked = False         # いまのファイルを、描くよう頼んだ
        self._pages = []            # 出したページの置き場（左, 上, 幅, 高さ）。ページの番号の順
        self._bases = {}            # 出したページの絵（PIL）。選んだ字に色を付けるときの元
        self._toast_job = None
        # 文字を選んでコピーする（2026-11-13 班長決定）
        self._file_token = 0        # いまのファイルの番号（ほかのファイルに移ったら、届いたページの字を捨てる）
        self.texts = {}             # ページの番号 → PageText か、出せないわけ（文字）
        self._asked_texts = set()
        self.selection = None       # [ページの番号, 始めの位置, いまの位置]
        self._pending = None        # ページの字が届くのを待っている押した点 [ページの番号, 押した点, いまの点]
        self._button_down = False
        self._pending_toast_job = None
        self.copied = None          # 最後にコピーした字（試験で確かめるため）

        self.canvas = tk.Canvas(self, bg=theme.WINDOW_BG, highlightthickness=1, highlightbackground=theme.BORDER,
                                bd=0, yscrollincrement=20)
        ys = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=ys.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        # 文字を選んでコピーする（2026-11-13 班長決定）：字の上をなぞって選び（ダブルクリックで語、トリプルクリックで
        # 行、Ctrl+A でページの全部。Shift+左右の矢印キーで、選んだ範囲を1字ずつ変える）、Ctrl+C か右クリックの
        # 「コピー」でコピーする
        self.canvas.bind("<Motion>", self._hover)
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<Double-Button-1>", lambda e: self._select_unit(e, "word"))
        self.canvas.bind("<Triple-Button-1>", lambda e: self._select_unit(e, "line"))
        for key in ctrl_sequences(self.canvas, "c") + ["<Control-Insert>"]:     # Mac では ⌘ にも（keys.py）
            self.canvas.bind(key, lambda e: (self.copy_selection(), "break")[1])
        for key in ctrl_sequences(self.canvas, "a"):
            self.canvas.bind(key, lambda e: (self._select_page(), "break")[1])
        for key, step in (("<Shift-Left>", -1), ("<Shift-Right>", 1)):
            self.canvas.bind(key, lambda e, s=step: (self.extend_by_char(s), "break")[1])
        self.canvas.bind("<Button-3>", self._menu)
        self._context = tk.Menu(self, tearoff=False)
        self._context.add_command(label="コピー", accelerator="Ctrl+C", command=self.copy_selection)
        self._context.add_command(label="このページの文字をすべて選ぶ", accelerator="Ctrl+A", command=self._select_page)
        self._message(NOTE_EMPTY)
        self.after(POLL_MS, self._poll)

    # ------------------------------------------------------------ 外から使うもの

    def show(self, path, wait=False):
        """path のファイルを出す（None なら何も出さない）。同じファイルなら、出し直さない。
        wait：一覧を矢印キーで送っている。欄を空にして待ち、KEY_WAIT_MS の間、次の show が来なければ出す。"""
        path = Path(path) if path else None
        if path == self.path and path is not None:
            if self._loaded or (self._show_job is None and self._asked):
                return                      # 出した・読んでいる最中（同じファイルを2度読まない）
            if self._show_job is not None:
                if not wait:                # 待っている間に「いま出す」と言われた
                    self._cancel_wait()
                    self._start()
                return
        self._cancel_wait()
        self._file_token += 1               # 前のファイルで頼んだ字は、届いても捨てる
        self._asked = False
        self.texts, self._asked_texts = {}, set()
        self.selection = self._pending = None
        self._cancel_pending_toast()
        self.path = path
        self._loaded = False
        self._keep_view = None
        self.count = self.drawn = 0
        self._gen += 1                      # 作りかけの結果は捨てる（前のファイルのページを出さない）
        if path is None:
            self._message(NOTE_EMPTY)
            return
        if wait:
            self._clear()
            self._show_job = self.after(KEY_WAIT_MS, self._start)
            return
        self._start()

    def _start(self):
        self._show_job = None
        self._message(NOTE_LOADING)
        self._ask()

    def _cancel_wait(self):
        if self._show_job is not None:
            self.after_cancel(self._show_job)
            self._show_job = None

    def set_active(self, active):
        """欄を出した・隠した。隠している間は読まず、出したら今のファイルを出す。"""
        self.active = active
        if active and self.path is not None and not self._loaded and self._show_job is None:
            self._message(NOTE_LOADING)
            self._ask()

    # ------------------------------------------------------------ 中の仕組み

    def _width(self):
        return max(self.canvas.winfo_width() - 2 * MARGIN - 2, 50)

    def _ask(self):
        if not self.active or self.path is None:
            return
        self._gen += 1
        self._asked = True
        self._asked_width = self._width()
        self._worker.ask(self._gen, self.path, self._asked_width)

    def _poll(self):
        try:
            while True:
                result = self._worker.results.get_nowait()
                if result[0] == "text":
                    if result[1] == self._file_token:
                        self._text_arrived(*result[2:])
                    continue
                if result[1] != self._gen:
                    continue                 # 古い頼み（前のファイル）の結果は捨てる
                _, _, index, image, count, error = result
                if error:
                    self._show_error(error)
                else:
                    self._add_page(index, image, count)
        except queue.Empty:
            pass
        except tk.TclError:
            return                           # 窓を閉じた
        self.after(POLL_MS, self._poll)

    def _show_error(self, error):
        self.error = error
        self._loaded = True
        if self.drawn:                       # 途中のページで描けなかった：そこに、わけを出す
            self._note_at(self._next_y + GAP, error)
        else:
            self._message(error)

    def _add_page(self, index, image, count):
        from PIL import ImageTk
        c = self.canvas
        if index == 0:                       # 1ページ目：前に出していたものを消す
            self._reset_canvas()
            self.error = ""
            c.configure(cursor="xterm")      # 字を選べる
        photo = ImageTk.PhotoImage(image)
        self._photos.append(photo)
        y = self._next_y
        self._pages.append((MARGIN, y, image.width, image.height))
        self._bases[index] = image
        if self.selection and self.selection[0] == index:
            self._paint(index)
        c.create_rectangle(MARGIN - 1, y - 1, MARGIN + image.width, y + image.height, outline=theme.BORDER)
        c.create_image(MARGIN, y, image=photo, anchor="nw")
        self._next_y = y + image.height + GAP
        self.count, self.drawn, self._loaded = count, index + 1, True
        bottom = self._next_y
        if self.drawn == min(count, MAX_PAGES) and count > MAX_PAGES:
            bottom = self._note_at(bottom, f"{MAX_PAGES + 1} ページ目からは、「ファイルを開く」で見てください"
                                           f"（全部で {count} ページ）。")
        c.configure(scrollregion=(0, 0, image.width + 2 * MARGIN, bottom + MARGIN))
        if index == 0:
            c.yview_moveto(self._keep_view or 0)
        elif self._keep_view:
            c.yview_moveto(self._keep_view)  # 幅を変えて描き直している間は、見ていた位置に戻す

    def _note_at(self, y, text):
        """y の高さに注記を置く。→ 注記の下の高さ。"""
        c = self.canvas
        w = max(c.winfo_width(), 200)
        item = c.create_text(w // 2, y, text=text, fill=theme.NOTE, width=w - 30, justify="center", anchor="n",
                             font=(theme.UI_FONT_FAMILY, theme.UI_FONT_SIZE))
        box = c.bbox(item)
        return (box[3] if box else y + 40) + GAP

    def _reset_canvas(self):
        c = self.canvas
        c.delete("all")
        c.configure(cursor="")
        self._photos = []
        self._pages = []
        self._bases = {}
        self._next_y = MARGIN
        if self._toast_job is not None:
            self.after_cancel(self._toast_job)
            self._toast_job = None

    def _clear(self):
        """何も出さない（矢印キーで送っている間）。"""
        c = self.canvas
        self._reset_canvas()
        c.configure(scrollregion=(0, 0, 1, 1))
        c.yview_moveto(0)

    def _message(self, text):
        c = self.canvas
        self._reset_canvas()
        bottom = self._note_at(40, text)
        c.configure(scrollregion=(0, 0, max(c.winfo_width(), 200), bottom))
        c.yview_moveto(0)

    def _on_resize(self, event):
        if abs(event.width - self._last_width) < 8:
            return
        self._last_width = event.width
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(RESIZE_DELAY_MS, self._after_resize)

    def _after_resize(self):
        self._resize_job = None
        if self._show_job is not None:
            return                           # 矢印キーで送っている間：出すときに、その幅で描く
        if self.path is None:
            self._message(NOTE_EMPTY)
        elif self._loaded and not self.drawn:
            self._message(self.error)        # 出せなかったわけを、幅に合わせて出し直す
        elif self._width() != self._asked_width:   # 同じ幅なら描き直さない（窓を出した直後の知らせなど）
            self._keep_view = self.canvas.yview()[0] if self.drawn else None
            self._ask()                      # 覚えた中身から、新しい幅で描き直す

    def _on_wheel(self, event):
        if event.delta:
            self.canvas.yview_scroll(int(-event.delta / 120) * 3, "units")

    # ------------------------------------------------------------ 文字を選んでコピーする（2026-11-13 班長決定）

    def _page_at(self, x, y):
        for i, (px, py, pw, ph) in enumerate(self._pages):
            if px <= x <= px + pw and py <= y <= py + ph:
                return i
        return None

    def _point(self, event, index):
        """マウスの位置を、index ページの中の割合にする（ページの外なら、ページの端に寄せる）。"""
        px, py, pw, ph = self._pages[index]
        x = (self.canvas.canvasx(event.x) - px) / pw
        y = (self.canvas.canvasy(event.y) - py) / ph
        return min(max(x, 0.0), 1.0), min(max(y, 0.0), 1.0)

    def _ask_text(self, index):
        """ページの字と位置を、裏で作るよう頼む（ページの上にマウスが来たら、先に頼んでおく）。"""
        if index in self._asked_texts or self.path is None:
            return
        self._asked_texts.add(index)
        self._worker.read_text(self._file_token, self.path, index)

    def _hover(self, event):
        index = self._page_at(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
        if index is not None:
            self._ask_text(index)

    def _press(self, event):
        self.canvas.focus_set()              # Ctrl+C・Ctrl+A を受けるため
        self._button_down = True
        index = self._page_at(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
        self._set_selection(None)
        self._pending = None
        if index is None:
            return
        point = self._point(event, index)
        text = self.texts.get(index)
        if text is None:                     # まだ届いていない：届いたら、押した点から選ぶ
            self._ask_text(index)
            self._pending = [index, point, point]
            self._pending_toast_job = self.after(300, lambda: self._toast("文字を読み取っています…", keep=True))
        elif isinstance(text, str):
            self._toast(text)
        elif not text.has_text():
            self._toast("このページには、選べる文字がありません。")
        else:
            pos = text.pos_at(*point)
            self._set_selection([index, pos, pos])

    def _drag(self, event):
        if self._pending is not None:
            self._pending[2] = self._point(event, self._pending[0])
            return
        if self.selection is None:
            return
        index = self.selection[0]
        pos = self.texts[index].pos_at(*self._point(event, index))
        if pos != self.selection[2]:
            self._set_selection([index, self.selection[1], pos])

    def _release(self, event):
        self._button_down = False

    def _select_unit(self, event, unit):
        """ダブルクリック（語）・トリプルクリック（行）。"""
        if self.selection is None:
            return "break"
        index = self.selection[0]
        text = self.texts[index]
        point = self._point(event, index)
        a, b = text.word_at(*point) if unit == "word" else text.line_range(*point)
        self._set_selection([index, a, b])
        return "break"

    def _select_page(self):
        """Ctrl+A：選んでいるページ（なければ、見えているいちばん上のページ）の字をすべて選ぶ。"""
        if self.selection is not None:
            index = self.selection[0]
        else:
            top = self.canvas.canvasy(0)
            index = next((i for i, (px, py, pw, ph) in enumerate(self._pages) if py + ph > top), None)
        text = self.texts.get(index) if index is not None else None
        if text is None or isinstance(text, str):
            if index is not None:
                self._ask_text(index)
            return
        self._set_selection([index, 0, len(text.chars)])

    def extend_by_char(self, step):
        """Shift+左右の矢印キー：選んだ範囲の、動かしている側の端（なぞり終えた側）を1字ずつ動かす（2026-11-13 班長
        指示「Shift+左右矢印で選択範囲を変更できるようにならないか」）。始めの側は動かさない（ワープロと同じ）。
        行の区切り（改行）は、色の付く字がないので、続けて次の字まで動かす。ページをまたいでは選ばない。"""
        sel = self.selection
        text = self.texts.get(sel[0]) if sel is not None else None
        if text is None or isinstance(text, str):
            return
        pos = sel[2]
        while True:
            new = min(max(pos + step, 0), len(text.chars))
            if new == pos:
                break
            crossed = text.chars[min(pos, new)][0]
            pos = new
            if crossed != "\n":
                break
        if pos != sel[2]:
            self._set_selection([sel[0], sel[1], pos])

    def _text_arrived(self, index, text, error):
        self.texts[index] = error if error else text
        if self._pending is None or self._pending[0] != index:
            return
        _, start, now = self._pending
        self._pending = None
        self._cancel_pending_toast()
        self.canvas.delete("toast")
        if error:
            self._toast(error)
        elif not text.has_text():
            self._toast("このページには、選べる文字がありません。")
        else:
            self._set_selection([index, text.pos_at(*start), text.pos_at(*now)])

    def _cancel_pending_toast(self):
        if self._pending_toast_job is not None:
            self.after_cancel(self._pending_toast_job)
            self._pending_toast_job = None

    def _set_selection(self, selection):
        old = self.selection
        self.selection = selection
        if old is not None and (selection is None or old[0] != selection[0]):
            self._paint(old[0])
        if selection is not None:
            self._paint(selection[0])

    def _paint(self, index):
        """index ページの絵に、選んだ字の色を付けて出し直す（選んでいなければ元の絵に戻す）。"""
        from PIL import Image, ImageDraw
        base = self._bases.get(index)
        if base is None or index >= len(self._photos):
            return
        image = base
        sel = self.selection
        if sel is not None and sel[0] == index and sel[1] != sel[2]:
            w, h = base.size
            overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            for x0, y0, x1, y1 in self.texts[index].rects(sel[1], sel[2]):
                draw.rectangle((x0 * w, y0 * h, x1 * w, y1 * h), fill=SELECT_COLOR)
            image = Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")
        self._photos[index].paste(image)

    def selected_text(self):
        sel = self.selection
        if sel is None or sel[1] == sel[2]:
            return ""
        return self.texts[sel[0]].text(sel[1], sel[2])

    def copy_selection(self):
        """選んだ字をクリップボードに入れる（Ctrl+C・右クリックの「コピー」）。"""
        text = self.selected_text()
        if not text:
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.copied = text     # 知らせは出さない（2026-11-13 班長指示「「コピーしました」というメッセージも不要」）

    def _menu(self, event):
        index = self._page_at(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
        if index is None:
            return
        self._ask_text(index)
        self._context.entryconfigure(0, state="normal" if self.selected_text() else "disabled")
        self._context.tk_popup(event.x_root, event.y_root)

    def _toast(self, text, keep=False):
        """見えているところの上に、短い知らせを出す（keep でなければ、TOAST_MS たったら、囲んだ枠と一緒に消す）。"""
        c = self.canvas
        c.delete("toast")
        if self._toast_job is not None:
            self.after_cancel(self._toast_job)
            self._toast_job = None
        w = max(c.winfo_width(), 200)
        left, top = c.canvasx(0), c.canvasy(0)
        item = c.create_text(left + w // 2, top + 14, text=text, fill=theme.TEXT, width=w - 40, justify="center",
                             anchor="n", font=(theme.UI_FONT_FAMILY, theme.UI_FONT_SIZE), tags="toast")
        x1, y1, x2, y2 = c.bbox(item)
        back = c.create_rectangle(x1 - 8, y1 - 5, x2 + 8, y2 + 5, fill=theme.FIELD_BG, outline=theme.ACCENT,
                                  tags="toast")
        c.tag_lower(back, item)
        if not keep:
            self._toast_job = self.after(TOAST_MS, self._end_toast)

    def _end_toast(self):
        self._toast_job = None
        self.canvas.delete("toast")
