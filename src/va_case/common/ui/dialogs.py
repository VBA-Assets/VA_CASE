"""4つのツールで使う画面の部品（真ん中に出す・この PC の設定・表の行を足す・直す・消す）。"""
import re
import tkinter as tk
from tkinter import font as tkfont
from tkinter import filedialog, ttk

from ..paths import portable
from . import theme
from .theme import px


def center(win, parent):
    win.update_idletasks()
    try:
        x = parent.winfo_rootx() + (parent.winfo_width() - win.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - win.winfo_height()) // 3
        win.geometry(f"+{max(0, x)}+{max(0, y)}")
    except tk.TclError:
        pass


# 行の頭に来てはいけない字・行の終わりに来てはいけない字（禁則）
NO_LINE_START = set("、。，．,.）)」』】〕〉》］]｝}・：:；;？?！!ー々ゝゞヽヾぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ％%")
NO_LINE_END = set("（(「『【〔〈《［[｛{")
_TOKEN = re.compile(r"[A-Za-z0-9_\-./\\:@%+=#~]+|\s|.")


def wrap_text(text, font, width):
    """文を、幅 width（画素）に収まるよう、改行を入れて折り返す。

    Tk の折り返し（wraplength）は、文に空白があるとそこで改行し、空白がなければ英単語の途中でも改行する。日本語の文
    では「VA Case の」の後や「Wi / ndows」のような半端なところで改行されるため（2026-11-09 班長指摘）、自分で折り返す：
    日本語は字の間のどこでも改行してよく、英数字の続き（単語・ファイル名・パス）の中では改行しない。行の頭に「、」「。」
    「）」などが来るときは、前の行の最後の字と一緒に次の行へ送る（禁則）。
    """
    lines = []
    for para in text.split("\n"):
        line = ""
        for tok in _TOKEN.findall(para):
            if not line.strip() or font.measure(line + tok) <= width:
                line += tok
                continue
            if tok.isspace():
                lines.append(line.rstrip())
                line = ""
                continue
            carry = ""
            if tok[0] in NO_LINE_START and len(line) > 1:
                carry, line = line[-1], line[:-1]          # 追い出し：前の行の最後の字と一緒に送る
            while len(line) > 1 and line[-1] in NO_LINE_END:
                carry, line = line[-1] + carry, line[:-1]
            lines.append(line.rstrip())
            line = carry + tok
        lines.append(line.rstrip())
    return "\n".join(lines)


def _label_font(label, style):
    name = ttk.Style(label).lookup(style, "font") or "TkDefaultFont"
    try:
        return tkfont.nametofont(name)
    except tk.TclError:
        return tkfont.Font(font=name)


def office_buttons(dialog, editable, on_ok):
    """事務所の設定の画面の、下のボタンの並び（4つのツールで共通）。

    編集モード：「OK（書き込む）」「キャンセル」。閲覧モード：「閉じる」だけ。編集を始めるのは、本体の「編集を始める」
    （2026-11-11 班長指示「同じことを行うボタンは、１つに統一すべき」。この画面は本体を止めないので、開いたまま本体の
    ボタンを押せる。モードが変わると、ツールの側で画面を開き直す。shared_app.py の run_office_dialog）。
    """
    buttons = ttk.Frame(dialog, padding=(10, 0, 10, 10))
    buttons.pack(fill="x")
    if editable:
        ttk.Button(buttons, text="キャンセル", command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text="OK（書き込む）", style="Accent.TButton", command=on_ok).pack(side="right", padx=6)
    else:
        ttk.Button(buttons, text="閉じる", command=dialog.destroy).pack(side="right")
        ttk.Label(buttons, text="閲覧モードです。直すときは、本体の「編集を始める」を押してください。",
                  style="Note.TLabel").pack(side="left")
    return buttons


def widget_snapshot(win):
    """画面の中の入力欄・表の値の写し（直したかを見分けるため。値そのものを比べるだけで、どこにも出さない）。"""
    values = []

    def walk(w):
        for c in w.winfo_children():
            try:
                if isinstance(c, tk.Text):
                    values.append(c.get("1.0", "end-1c"))
                elif isinstance(c, ttk.Treeview):
                    values.append(tuple(tuple(c.item(i, "values")) for i in c.get_children()))
                elif isinstance(c, (ttk.Entry, ttk.Combobox, ttk.Spinbox, tk.Entry)):
                    values.append(c.get())
                elif isinstance(c, tk.Checkbutton):
                    values.append(c.getvar(c.cget("variable")))
            except tk.TclError:
                pass
            walk(c)
    walk(win)
    return values


def wrapping_label(parent, text, *, width=600, style="Note.TLabel", **kw):
    """何行かに折り返す注記（wrap_text で折り返す）。置いた場所の幅に合わせて折り返し直す（pack(fill="x") か
    grid(sticky="we") で置くこと）。width は、置く前の幅（96 dpi のときの画素。画面の拡大率に合わせる）。
    幅を決めて折り返すときは、label.fit(画素) を呼ぶ。"""
    label = ttk.Label(parent, style=style, **kw)
    font = _label_font(label, style)
    state = {"width": 0}

    def fit(w):
        w = max(int(w), px(parent, 100))
        if abs(w - state["width"]) > 2:
            state["width"] = w
            label.configure(text=wrap_text(text, font, w - px(parent, 4)))
    label.fit = fit
    fit(px(parent, width))
    # 置いた場所が広ければ、その幅まで広げて折り返し直す。狭める向きには追わない（自分の幅で折り返し直すと、
    # 少しずつ狭まり続けるため）
    label.bind("<Configure>", lambda e: fit(e.width) if e.width > state["width"] + 2 else None)
    return label


def browse_into(var, kind, parent, title="フォルダを選ぶ", filetypes=None, data_root=None):
    """参照のボタン：選んだファイル・フォルダを var に入れる（Windows では \\ の区切りにする）。"""
    if kind == "file":
        path = filedialog.askopenfilename(parent=parent, title=title,
                                          filetypes=filetypes or [("共有データ", "*.json"), ("すべて", "*.*")])
    else:
        path = filedialog.askdirectory(parent=parent, title=title, mustexist=True)
    if path:
        path = path.replace("/", "\\") if "\\" in var.get() or ":" in path else path
        # 共有データに書くフォルダ（data_root を渡したとき）は、基点の下なら基点からの相対にする（2026-11-12 班長決定。
        # PC ごとに共有フォルダの場所が違っても使えるように）。この PC の設定の欄には渡さない
        var.set(portable(path, data_root) if data_root else path)


class SettingsDialog(tk.Toplevel):
    """この PC の設定の画面（ツールごとに FIELDS・BOOLS を決める）。

    FIELDS：(設定の名前, 見出し, "file" か "dir", 注記)。BOOLS：(設定の名前, 印の文)。
    2026-11-11 まであった「同期を待つ秒数」の欄は、なくした（班長決定。仕様.md の 3.3）。
    """

    APP_TITLE = ""
    FIELDS = []
    BOOLS = []
    FILETYPES = {}     # 設定の名前 → 参照のときのファイルの種類

    def __init__(self, parent, cfg):
        super().__init__(parent)
        self.withdraw()
        self.title("この PC の設定")
        self.transient(parent)
        self.resizable(False, False)
        self.cfg = cfg
        self.result = None
        self.vars = {}
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        r = 0
        notes = []
        for key, label, kind, note in self.FIELDS:
            ttk.Label(body, text=label).grid(row=r, column=0, sticky="e", padx=(0, 6), pady=(6, 0))
            var = tk.StringVar(value=getattr(cfg, key))
            self.vars[key] = var
            entry = ttk.Entry(body, textvariable=var, width=60)
            entry.grid(row=r, column=1, sticky="we", pady=(6, 0))
            button = ttk.Button(body, text="参照…", style="Small.TButton",
                                command=lambda v=var, k=kind, n=key: browse_into(
                                    v, k, self, title=f"{label}を選ぶ", filetypes=self.FILETYPES.get(n)))
            button.grid(row=r, column=2, padx=(6, 0), pady=(6, 0))
            n = wrapping_label(body, note)
            n.grid(row=r + 1, column=1, columnspan=2, sticky="w")
            notes.append(n)
            r += 2
        self.bool_vars = {}
        for key, label in self.BOOLS:
            var = tk.BooleanVar(value=bool(getattr(cfg, key)))
            self.bool_vars[key] = var
            tk.Checkbutton(body, text=label, variable=var).grid(row=r, column=1, columnspan=2, sticky="w", pady=(10, 0))
            r += 1
        buttons = ttk.Frame(self, padding=(12, 0, 12, 12))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="キャンセル", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="OK", style="Accent.TButton", command=self._ok).pack(side="right", padx=6)
        self.bind("<Escape>", lambda e: self.destroy())
        if notes:   # 注記は、入力欄と「参照…」を合わせた幅で折り返す（画素で決めると、拡大した画面で途中で折り返すため）
            self.update_idletasks()
            width = entry.winfo_reqwidth() + button.winfo_reqwidth() + px(self, 6)
            for n in notes:
                n.fit(width)
        center(self, parent)
        self.deiconify()
        self.grab_set()

    def _ok(self):
        for key, var in self.vars.items():
            setattr(self.cfg, key, var.get().strip())
        for key, var in self.bool_vars.items():
            setattr(self.cfg, key, bool(var.get()))
        self.result = self.cfg
        self.destroy()


class WrappedEntry(tk.Text):
    """値は1行だが、長いので何行かの高さで折り返して見せる入力欄（保管ファイル名など。2026-11-09 班長指示）。

    ttk.Entry と同じく textvariable（StringVar）と結び、state に "normal"・"readonly"・"disabled" を受け付ける。
    Enter・Tab では改行せず、次の欄へ進む。貼り付けた改行は、値からは除く。
    """

    def __init__(self, parent, textvariable, *, width=60, height=2, font=None):
        super().__init__(parent, width=width, height=height, wrap="char", font=font, undo=True)
        self.var = textvariable
        self._syncing = False
        self.insert("1.0", textvariable.get())
        self.edit_modified(False)
        textvariable.trace_add("write", self._from_var)
        self.bind("<<Modified>>", self._to_var)
        for key in ("<Return>", "<KP_Enter>", "<Tab>"):
            self.bind(key, lambda e: (e.widget.tk_focusNext().focus_set(), "break")[1])

    def _from_var(self, *args):
        if self._syncing:
            return
        value = self.var.get()
        if self.get("1.0", "end-1c") != value:
            state = super().cget("state")
            super().configure(state="normal")
            self.delete("1.0", "end")
            self.insert("1.0", value)
            super().configure(state=state)
            self.edit_modified(False)

    def _to_var(self, event=None):
        if not self.edit_modified():
            return
        self.edit_modified(False)
        self._syncing = True
        try:
            self.var.set("".join(self.get("1.0", "end-1c").splitlines()))
        finally:
            self._syncing = False

    def get_value(self):
        return "".join(self.get("1.0", "end-1c").splitlines())

    _locked = False

    def configure(self, cnf=None, **kw):
        # style：ttk.Entry と同じく "Locked.TEntry"（直せない値の欄。地を窓の地と同じにし、枠線を消す。2026-11-13）と
        # "TEntry"（ふつうの欄）を受け付ける。Text には style がないので、地と枠線の色で同じ見た目にする
        if "style" in kw:
            self._locked = kw.pop("style") == "Locked.TEntry"
            kw.setdefault("state", "normal" if super().cget("state") == "normal" else "readonly")
        if "state" in kw:   # Text には readonly がないので、直せない状態（disabled）にして、地の色で示す
            state = kw.pop("state")
            kw["state"] = "normal" if state == "normal" else "disabled"
            if self._locked:
                kw.update(background=theme.WINDOW_BG, highlightbackground=theme.WINDOW_BG,
                          highlightcolor=theme.BORDER)
            else:
                kw.update(background=theme.FIELD_BG if state == "normal" else theme.READONLY_BG,
                          highlightbackground=theme.BORDER, highlightcolor=theme.ACCENT)
        return super().configure(cnf, **kw)

    config = configure


class TableEditor(ttk.Frame):
    """表の行を、足す・直す・消す・上へ・下へで直す部品（事務所の設定の画面で使う）。

    columns：列の見出し。kinds：列ごとの入力の種類（"text"・"dir"・("choice", [候補])）。rows：文字列の並びの並び。
    """

    def __init__(self, parent, columns, rows, *, kinds=None, widths=None, editable=True, title="行を直す",
                 height=10, data_root=None):
        super().__init__(parent)
        self.data_root = data_root   # フォルダの列を、基点からの相対で書くため（browse_into）
        self.columns = list(columns)
        self.kinds = kinds or ["text"] * len(self.columns)
        self.rows = [list(r) for r in rows]
        self.editable = editable
        self.row_title = title
        self.tree = ttk.Treeview(self, columns=self.columns, show="headings", height=height, selectmode="browse")
        for i, c in enumerate(self.columns):
            self.tree.heading(c, text=c)
            w = (widths or [])[i] if widths and i < len(widths) else 160
            self.tree.column(c, width=px(self, w), stretch=(i == len(self.columns) - 1))
        self.tree.pack(fill="both", expand=True)
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(6, 0))
        for text, cmd in (("足す", self._add), ("直す", self._edit), ("消す", self._delete),
                          ("上へ", lambda: self._move(-1)), ("下へ", lambda: self._move(1))):
            b = ttk.Button(bar, text=text, style="Small.TButton", command=cmd)
            b.pack(side="left", padx=(0, 6))
            if not editable:
                b.state(["disabled"])
        self.tree.bind("<Double-1>", lambda e: self._edit())
        self._fill()

    def _fill(self, select=None):
        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(self.rows):
            self.tree.insert("", "end", iid=str(i), values=r)
        if select is not None and 0 <= select < len(self.rows):
            self.tree.selection_set(str(select))
            self.tree.see(str(select))

    def _selected(self):
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def _row_dialog(self, values):
        win = tk.Toplevel(self)
        win.title(self.row_title)
        win.transient(self.winfo_toplevel())
        result = {}
        vars_ = []
        for i, (c, kind) in enumerate(zip(self.columns, self.kinds)):
            ttk.Label(win, text=c).grid(row=i, column=0, sticky="e", padx=(10, 6), pady=4)
            var = tk.StringVar(value=values[i] if i < len(values) else "")
            if isinstance(kind, tuple) and kind[0] == "choice":
                w = ttk.Combobox(win, textvariable=var, values=list(kind[1]), width=30)
            else:
                w = ttk.Entry(win, textvariable=var, width=56 if kind == "dir" else 40)
            w.grid(row=i, column=1, sticky="w", padx=(0, 6), pady=4)
            if kind == "dir":
                ttk.Button(win, text="参照…", style="Small.TButton",
                           command=lambda v=var: browse_into(v, "dir", win, data_root=self.data_root)).grid(
                    row=i, column=2, padx=(0, 10))
            vars_.append(var)

        def ok():
            # フォルダの列は、貼り付けた絶対パスも、基点の下なら基点からの相対にする
            result["v"] = [portable(v.get(), self.data_root) if k == "dir" and self.data_root else v.get().strip()
                           for v, k in zip(vars_, self.kinds)]
            win.destroy()
        bf = ttk.Frame(win, padding=10)
        bf.grid(row=len(vars_), column=0, columnspan=3, sticky="e")
        ttk.Button(bf, text="キャンセル", command=win.destroy).pack(side="right")
        ttk.Button(bf, text="OK", style="Accent.TButton", command=ok).pack(side="right", padx=6)
        win.bind("<Return>", lambda e: ok())
        win.bind("<Escape>", lambda e: win.destroy())
        center(win, self.winfo_toplevel())
        win.grab_set()
        self.wait_window(win)
        v = result.get("v")
        return v if v and any(v) else None

    def _add(self):
        v = self._row_dialog([""] * len(self.columns))
        if v:
            self.rows.append(v)
            self._fill(len(self.rows) - 1)

    def _edit(self):
        i = self._selected()
        if i is None or not self.editable:
            return
        v = self._row_dialog(self.rows[i])
        if v:
            self.rows[i] = v
            self._fill(i)

    def _delete(self):
        i = self._selected()
        if i is not None:
            del self.rows[i]
            self._fill(min(i, len(self.rows) - 1))

    def _move(self, d):
        i = self._selected()
        if i is None or not 0 <= i + d < len(self.rows):
            return
        self.rows[i], self.rows[i + d] = self.rows[i + d], self.rows[i]
        self._fill(i + d)
