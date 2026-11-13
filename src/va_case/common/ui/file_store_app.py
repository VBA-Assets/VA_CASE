"""読み込んだファイルを保管していくツール（VA Filing・VA Receipt）の画面の、共通の仕組み。

VA Filing で作ったもの（2026-11-09）を、VA Receipt でも使えるよう、ここに移した：
- 一覧（保管済みは灰色、処理中の行は点滅）と、その下の入力欄（行を選ぶと出る。入れかけた値は行ごとに覚える）
- 読込フォルダのファイルの読み込み、保管（次の未保管の行へ進む。書き込み中なら待ち行列に入れる）、保管の取り消し、備考
  （保管済みの行の備考は、ほかの行に移るとき・Enter で書き込む。入力欄の Ctrl+Z・Ctrl+Y。2026-11-12 班長決定）
- 閲覧モードでは見るだけ。ファイル・フォルダを開く、検索、CSV の出力・取り込み
- 左側のプレビュー（選んだ行のファイル。preview.py。2026-11-12 班長決定「プレビューは左側に表示」）

ツールごとの画面は、この FileStoreApp を受け継ぎ、クラスの属性（MODEL・DISPLAY_COLUMNS など）と、入力欄の組み立て
（_build_fields）・保管の下ごしらえ（_prepare_store）などを書く。MODEL には、そのツールの model モジュールを渡す
（STORE・COL・STORE_COLUMNS・READ_FOLDERS・SET_SKIP_PREFIX・YES・FoundFile と、is_stored・row_by_number・
setting_values・should_skip・merge_found・mark_restored・update_note・add_imported・copy_tables を持つこと）。
"""
import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ..errors import SharedError
from .. import dates, storing, trash
from ..paths import portable, resolve_folder
from . import autocomplete, theme
from .preview import PreviewPane
from .tooltip import Tooltip
from .undo import EditHistory
from .shared_app import SharedApp, open_path


class StoreCancelled(Exception):
    """保管の下ごしらえで、利用者に知らせて止めたとき（知らせは済んでいる）。"""


class FileStoreApp(SharedApp):
    MODEL = None
    DISPLAY_COLUMNS = []
    COLUMN_WIDTHS = {}
    PANEL_FIELDS = ()
    OFFICE_MENU_LABEL = "事務所の設定…"
    CSV_NOTE = "CSV には、記録の内容がそのまま入っています。"
    ROW_NAME = "ファイル"
    CSV_FILE_NAME = "保管"
    FIRST_FIELD = ""             # 次の行へ進んだときに、キーボードの入力先にする欄
    PREVIEW_WIDTH = 380          # プレビューの既定の幅（96 dpi のときの画素）
    BUSY_CLOSE_MESSAGE = ("書き込み中です（保管の途中かもしれません）。閉じると途中で止まります（共有データは壊れません）。\n"
                          "それでも閉じますか？")

    def __init__(self, root, settings_module):
        self.drafts = {}            # 番号 → 入力欄に入れかけた値（共有データには書かない。この画面の中だけ）
        self.current = None         # 入力欄に出している行の番号
        self.current_stored = False
        self.pending = set()        # 書き込み中・書き込み待ちの番号
        self.auto_name = ""         # 自動で入れた保管ファイル名（利用者が直したかを見分ける）
        self.writing_notes = {}     # 番号 → いま書き込んでいる、保管済みの行の備考
        self._row_blinking = False
        super().__init__(root, settings_module)

    @property
    def m(self):
        return self.MODEL

    def empty_tables(self):
        return self.m.empty_tables()

    # ------------------------------------------------------------ ツールごとに書くもの

    def _build_fields(self, p, font):
        """入力欄の行（1行目から）を作る。列：0 見出し・1 欄・2 欄の右のボタンや注記。self.widgets・self.rows_of に入れ、
        次の行の番号を返す。"""
        raise NotImplementedError

    def _draft_extra(self):
        """入れかけた値と一緒に覚えるもの（VA Filing の選んだ保管先など）。"""
        return None

    def _restore_draft_extra(self, extra):
        pass

    def _after_show_row(self, row, draft):
        """入力欄に行を出した後（draft がなければ、記録の値を出した後）。"""

    def _fill_defaults(self):
        """未保管の行を出したとき、空の欄に既定を入れ、保管ファイル名を作る。"""

    def _update_name(self):
        """入力した値から保管ファイル名を作り直す（利用者が直していなければ）。"""

    def _prepare_store(self, row, values):
        """保管の下ごしらえ。→ dict(folder, file_name, targets, specials, transform(t), notes)。
        保管できないときは、知らせてから StoreCancelled を投げる。"""
        raise NotImplementedError

    def _restore_links(self, row):
        """元に戻すときに消す写し → (targets, specials)。"""
        return [], []

    def _settings_dialog(self):
        raise NotImplementedError

    def open_office(self):
        raise NotImplementedError

    # ------------------------------------------------------------ 画面の組み立て

    def _build_menu(self):
        bar = tk.Menu(self.root)
        f = tk.Menu(bar, tearoff=False)
        f.add_command(label="最新を読み込む", command=self.reload_latest, accelerator="F5")
        f.add_command(label="読込フォルダのファイルを読み込む", command=self.read_files)
        f.add_separator()
        f.add_command(label="CSV に出力…", command=self.export_csv)
        f.add_command(label="CSV から取り込む…（編集モード）", command=self.import_csv)
        self.edit_only_menu(f)
        f.add_separator()
        f.add_command(label="この PC の設定…", command=self.open_settings)
        f.add_command(label=self.OFFICE_MENU_LABEL, command=self.open_office)
        f.add_separator()
        f.add_command(label="閉じる", command=self.on_close)
        bar.add_cascade(label="ファイル", menu=f)
        v = tk.Menu(bar, tearoff=False)
        self.preview_var = tk.BooleanVar(value=getattr(self.cfg, "preview_visible", True))
        v.add_checkbutton(label="プレビュー", variable=self.preview_var, command=self._toggle_preview)
        bar.add_cascade(label="表示", menu=v)
        self.build_help_menu(bar)
        self.root.configure(menu=bar)
        self.root.bind("<F5>", lambda e: self.reload_latest())

    def _build_toolbar(self):
        rb = self.build_ribbon()
        g = rb.group("ファイル")
        self.edit_only(g.large("ファイルを読み込む", self.read_files,
                               tip="読込フォルダにあるファイルを、一覧に足します（番号は、読み込んだ日の年月日＋その日の"
                                   "連番）。読込フォルダからなくなった未保管の行は消します。編集モードで使えます。"))
        # ［コピー］（2026-11-14 班長指示。VA Call と同じ。閲覧モードでも使える）
        g.small("コピー", self.copy_selected_rows,
                tip="選んでいる行の、一覧に出している値（番号・日時・ファイル名など）を、タブ区切りでコピーします（見出しは"
                    "付けません）。ファイルそのものはコピーしません。Excel などに貼り付けられます。何行かを選んでいれば、"
                    "その全部をコピーします。")
        self.edit_only(g.small("消す", self.delete_selected,
                               tip="選んでいる未保管の行を消し、読込フォルダのファイルをごみ箱へ移します（確かめてから）。"
                                   "保管済みの行は消せません。編集モードで使えます。"))
        self.build_search_group(rb)

    def _build_body(self):
        # 左にプレビュー、右に一覧と入力欄。境目はドラッグして幅を変えられる（ttk.Panedwindow は最小の幅を持てないため、
        # classic の PanedWindow を使う。グローバルの UI 設計方針のとおり）
        self.split = tk.PanedWindow(self.root, orient="horizontal", sashwidth=theme.px(self.root, 6),
                                    bg=theme.WINDOW_BG, bd=0, sashrelief="flat", showhandle=False)
        self.split.pack(fill="both", expand=True)
        self.preview = PreviewPane(self.split, padding=(8, 0, 0, 6))
        self.main_area = ttk.Frame(self.split)
        self.split.add(self.main_area, minsize=theme.px(self.root, 420), stretch="always")
        self._show_preview(self.preview_var.get())
        self._build_panel()      # 入力欄を先に下へ置き、残りを一覧にする
        self.build_list(self.m.STORE_COLUMNS, self.DISPLAY_COLUMNS, self.COLUMN_WIDTHS, parent=self.main_area)
        self.tree.tag_configure("stored", foreground=theme.STATUS_FG["closed"])   # 保管済み（灰色）
        self.tree.tag_configure("pending", foreground=theme.PENDING_FG)
        self.tree.tag_configure("pending_dim", foreground=theme.PENDING_DIM_FG)   # 点滅の「消えた」側
        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<Return>", lambda e: (self._focus_first_field(), "break")[1])
        self.history.bind_keys(self.tree)

    def _focus_first_field(self):
        self.flush_selected()
        w = self.widgets.get(self.FIRST_FIELD)
        if w is not None:
            w.focus_set()

    def _build_panel(self):
        outer = ttk.Frame(self.main_area, padding=(8, 6, 8, 0))
        outer.pack(fill="x", side="bottom")
        p = self.mode_card(outer, padding=(10, 6))
        p.columnconfigure(1, weight=1)
        font = theme.field_font(self.root)
        self.vars = {k: tk.StringVar() for k in self.PANEL_FIELDS}
        self.source_var = tk.StringVar()
        self.number_var = tk.StringVar()
        self.state_var = tk.StringVar()
        # 列：0 見出し・1 欄（画面の幅いっぱいに広げるものがある）・2 欄の右に置くボタンや注記
        # 一番上の行に、番号と読込ファイルを出す（番号は VA Call と同じ場所。カードの高さは変えない）。どちらも、見た目は
        # ラベルのまま、なぞって選び Ctrl+C でコピーできる（2026-11-13 班長指摘「カードで番号がコピーできない」。それまでは
        # 番号をカードに出さず、読込ファイルはラベルで、選べなかった）
        ttk.Label(p, text="番号").grid(row=0, column=0, sticky="e", padx=(0, 6))
        head = ttk.Frame(p)
        head.grid(row=0, column=1, sticky="w")
        theme.value_text(head, self.number_var).pack(side="left")
        ttk.Label(head, text="読込ファイル").pack(side="left", padx=(16, 6))
        theme.value_text(head, self.source_var).pack(side="left")
        top = ttk.Frame(p)
        top.grid(row=0, column=2, sticky="w", padx=(6, 0))
        self.open_file_button = ttk.Button(top, text="ファイルを開く", command=self.open_file)
        self.open_file_button.tooltip = Tooltip(
            self.open_file_button, "選んでいる行のファイルを、ふだん使うソフトで開きます（保管済みなら保管した場所の"
                                   "ファイル、未保管なら読込フォルダのファイル）。", above=True)
        self.open_file_button.pack(side="left")
        ttk.Label(top, textvariable=self.state_var, style="Note.TLabel").pack(side="left", padx=(10, 0))
        self.widgets = {}
        self.rows_of = {}           # 欄の名前 → その行の番号（欄の右に、ボタンや注記を置く）
        self.pick_button = None
        r = self._build_fields(p, font)
        bb = ttk.Frame(p)
        bb.grid(row=r, column=1, columnspan=2, sticky="w", pady=(6, 2))
        self.store_button = ttk.Button(bb, text="保管する", style="Accent.TButton", command=self.store_selected)
        self.store_button.tooltip = Tooltip(
            self.store_button, "ファイルを、保管ファイル名にして保管フォルダへ移し、記録を書き込みます。"
                               "決まっていればショートカットや写しも作ります。終わると、次の未保管の行へ進みます。"
                               "編集モードで使えます。", above=True)
        self.store_button.pack(side="left")
        self.store_button.bind("<Return>", lambda e: self.store_selected())
        # 「保管を取り消す」（2026-11-12 班長決定。それまでは「元に戻す（保管の取り消し）」。入力欄の Ctrl+Z〔元に戻す〕で
        # 保管も取り消せると思われないように改めた）。「備考を書き込む」はなくした（保管済みの行の備考は、ほかの行に
        # 移るとき・Enter で書き込む）
        self.restore_button = ttk.Button(bb, text="保管を取り消す", command=self.restore_selected)
        self.restore_button.tooltip = Tooltip(
            self.restore_button, "保管したファイルを、もとの読込フォルダへ戻し、未保管の行に戻します（確かめてから）。"
                                 "作ったショートカットや写しも消します。編集モードで使えます。", above=True)
        self.restore_button.pack(side="left", padx=(6, 0))
        # オートコンプリートを付けた欄（名前に下線）の説明（2026-11-09 班長決定）。2026-11-12 から、ボタンの右に置く
        # （それまでは、ここに「閲覧モードです」「「保管する」を押すと、…次の未保管のファイルへ進みます」「備考を直したら、
        # …書き込みます」を出し、この説明は1段下に置いていた。班長指摘「この行は不要ではないか？」で、その文をなくし、
        # 入力欄を1段低くした。使い方はマニュアルに書く）
        ttk.Label(bb, text=autocomplete.NOTE, style="Note.TLabel").pack(side="left", padx=(12, 0))
        # Ctrl+Z・Ctrl+Y（2026-11-12 班長決定。入力欄と一覧で）。自動で入れた保管ファイル名・選んだ保管先も一緒に戻す
        self.history = EditHistory(self.root, self._panel_snapshot, self._restore_snapshot,
                                   focus=lambda name: self.widgets[name].focus_set())
        for name, w in self.widgets.items():
            self.history.watch(w, name)
        for var in self.vars.values():
            var.trace_add("write", lambda *a: self.history.changed())
        self.widgets["備考"].bind("<Return>", self._note_return, add="+")
        # 日時の欄から出たとき・Enter で、決まった形にそろえる（2026-11-13 班長決定「この形で作る」）
        self.widgets["日時"].bind("<FocusOut>", lambda e: self._tidy_date(), add="+")
        self.widgets["日時"].bind("<Return>", lambda e: self._tidy_date(), add="+")
        self._panel_state = None
        self._set_panel_state(None)

    def _panel_snapshot(self):
        return ({k: v.get() for k, v in self.vars.items()}, (self.auto_name, self._draft_extra()))

    def _restore_snapshot(self, state):
        vals, (auto, extra) = state
        for k, v in vals.items():
            self.vars[k].set(v)
        self._restore_draft_extra(extra)
        self.auto_name = auto

    # 日時の欄の形（VA Filing は 12 桁 yyyymmddhhnn、VA Receipt は 8 桁 yyyymmdd）
    DATE_WITH_TIME = False

    def _tidy_date(self):
        """日時の欄に別の書き方（「2025/11/1」「R7.11.1」「令和7年11月1日 10時30分」など）が入っていれば、決まった形に
        そろえ、保管ファイル名も作り直す（2026-11-13 班長決定「この形で作る」）。読めなければ、そのままにする（打っている
        途中で知らせると、うるさいため。「保管する」のときに知らせる）。保管済みの行・閲覧モードでは何もしない。"""
        if getattr(self, "_panel_state", None) != "open" or not self.editing or self.data is None:
            return
        var = self.vars["日時"]
        text = var.get()
        new = dates.compact_datetime(text, self.DATE_WITH_TIME)
        if new and new != text:
            var.set(new)
            self._name_after_date()

    def _name_after_date(self):
        """日時をそろえた後に、保管ファイル名を作り直す（VA Receipt は枝番も）。"""
        self._update_name()

    def _note_return(self, event):
        """保管済みの行の備考で Enter を押したら、書き込む。"""
        row = self._current_row()
        if row is not None and self.m.is_stored(row):
            self.commit_pending()
            return "break"
        return None

    def folder_buttons(self, p, row):
        """保管フォルダの欄の右の「参照…」「開く」。"""
        fb = ttk.Frame(p)
        fb.grid(row=row, column=2, sticky="w", padx=(6, 0))
        self.pick_button = ttk.Button(fb, text="参照…", style="Small.TButton", command=self._pick_folder)
        self.pick_button.pack(side="left")
        self.pick_button.tooltip = Tooltip(self.pick_button, "保管フォルダを、フォルダの一覧から選びます。", above=True)
        b = ttk.Button(fb, text="開く", style="Small.TButton", command=self.open_folder)
        b.pack(side="left", padx=(6, 0))
        b.tooltip = Tooltip(b, "保管フォルダを、エクスプローラーで開きます。", above=True)

    # ------------------------------------------------------------ 読み込み

    def _resolve(self, value):
        return resolve_folder(value, getattr(self.cfg, "data_root", ""))

    def _folder_exists(self, value):
        p = self._resolve(value)
        return p is not None and p.is_dir()

    def after_first_load(self):
        """起動したら、最初の未保管の行を選ぶ（現行の Workbook_Open と同じ）。"""
        for iid in self.tree.get_children():
            if "stored" not in self.tree.item(iid, "tags"):
                self._select_item(iid)
                break

    # ------------------------------------------------------------ 一覧

    @property
    def rows(self):
        return self.data.tables[self.m.STORE].rows if self.data else []

    def csv_columns(self):
        return self.m.STORE_COLUMNS

    def csv_add(self, tables, rows):
        return self.m.add_imported(tables, rows)

    def csv_drop_existing(self, tables, rows):
        return self.m.drop_existing(tables, rows)

    def on_data(self, data):
        self.norm_cache = {}
        # 一覧は、いまの並べ方で出す（共有データは、書き込んだときの並びのまま。並べ方を変えた前に書いたもの〔2026-11-13
        # 未保管の行を番号の順にした〕も、読み込んだときに並べ直す。画面の中だけで、共有データは変えない）
        if data is not None:
            data.tables[self.m.STORE].rows = self.m.sorted_rows(data.tables[self.m.STORE].rows)

    def diagnostic_lines(self):
        m = self.m
        stored = sum(1 for row in self.rows if m.is_stored(row))
        return [f"保管済み {stored} 件・未保管 {len(self.rows) - stored} 件・書き込み中または待ちの行 {len(self.pending)} 件",
                f"入力欄に出している行：{'あり' if self.current else 'なし'}"]

    def refresh(self):
        m = self.m
        self.flush_selected()
        selected = self.current
        self.tree.delete(*self.tree.get_children())
        shown = pending_rows = 0
        self.begin_wrapped_list()     # すべてのセルを、列の幅で折り返して出す（2026-11-09 班長指示）
        for row in self.rows:
            if not m.is_stored(row):
                pending_rows += 1
            if not self.query.matches(row, self._norm(row)):
                continue
            values = list(row)
            values[m.COL["保管日時"]] = row[m.COL["保管日時"]][:16].replace("-", "/")
            if not self.passes_filter(m.STORE_COLUMNS, values):
                continue
            tags = []
            if row[m.COL["番号"]] in self.pending:
                tags.append("pending")
            elif m.is_stored(row):
                tags.append("stored")
            self.insert_wrapped(row[m.COL["番号"]], m.STORE_COLUMNS, values, tags)
            shown += 1
        total = len(self.rows)
        text = f"全 {total} 件（未保管 {pending_rows} 件）"
        label = self.narrowed_label()
        if label:
            # 2026-11-10 まで「検索の結果 5 件（全 5 件（未保管 4 件）」と、かっこが閉じていなかった
            text = f"{label} {shown} 件（全 {total} 件・未保管 {pending_rows} 件）"
        self.count_label.configure(text=text)
        self._update_mode()
        if selected and self.tree.exists(selected):
            self.tree.selection_set(self._group(self.tree, selected))
            self.tree.focus(selected)
            row = m.row_by_number(self.data.tables, selected)
            if row is not None and m.is_stored(row) != self.current_stored:
                self._show_row(row)       # 保管した・元に戻したときは、入力欄を出し直す
        elif selected:
            self.current = None
            self._set_panel_state(None)

    def on_queue_changed(self):
        m = self.m
        if self.data is not None:
            for iid in self.tree.get_children():
                tags = [t for t in self.tree.item(iid, "tags") if t not in ("pending", "pending_dim", "stored")]
                row = m.row_by_number(self.data.tables, iid)
                if iid in self.pending:
                    tags.append("pending")
                elif row is not None and m.is_stored(row):
                    tags.append("stored")
                self.set_row_tags(iid, tags)
        if self.pending and not self._row_blinking:
            self._row_blinking = True
            self.root.after(self.BLINK_MS, self._blink_rows, False)

    def _blink_rows(self, on):
        """保管・元に戻すの最中（書き込み待ちを含む）の行の字を点滅させる（2026-11-09 班長指示）。"""
        if not self.pending:
            self._row_blinking = False
            self.on_queue_changed()     # 点滅を止め、ふだんの色に戻す
            return
        for iid in self.pending:
            if self.tree.exists(iid):
                tags = [t for t in self.tree.item(iid, "tags") if t not in ("pending", "pending_dim", "stored")]
                self.set_row_tags(iid, tags + ["pending" if on else "pending_dim"])
        self.root.after(self.BLINK_MS, self._blink_rows, not on)

    def select_key(self, key):
        if key and self.tree.exists(key):
            self._select_item(key)

    def on_double_click(self, event):
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        iid = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if not iid or not col:
            return
        iid = self._list_row(iid)     # 2行目以降（子の行）をダブルクリックしたときも、その行
        column = self.DISPLAY_COLUMNS[int(col[1:]) - 1]
        self._select_item(iid)
        # 選んだ行を、すぐ入力欄に出す（<<TreeviewSelect>> は後から届くため、待つと前の行のファイルを開いてしまう）
        self._on_select()
        self.flush_selected()           # 矢印キーの直後でも、あとに回さず、いま出す
        row = self._current_row()
        if column in ("保管フォルダ名", "読込フォルダ名") and row is not None and row[self.m.COL[column]]:
            self.open_folder(column)
        else:
            self.open_file()   # フォルダの欄が空なら（未保管の行の保管フォルダ名など）、ファイルを開く
        return "break"         # ttk の既定の、行を開く・閉じる動きをさせない

    # ------------------------------------------------------------ 入力欄

    # 矢印キーで送っている間は、入力欄とプレビューの書き換えをあとに回す（list_view.py の _on_select。2026-11-13 班長指摘
    # 「VA FILINGでは、矢印キーを押している間もカードの更新が行われているような気がする。矢印キーを押し続けた場合の加速も
    # 行われていないのではないか？」。入力欄の書き換えに1回約0.1秒かかり、押し続けても1秒に約9行しか進まず、加速が始まる
    # 前に一覧の端に着いていた）

    def _selected_by_key(self):
        """前の行のファイルを出したままにしない（プレビューを空にして、キーを止めるのを待つ）。"""
        number = self.selected_key()
        row = self.m.row_by_number(self.data.tables, number) if (number and self.data) else None
        if row is not None and number != self.current:
            self.preview.show(self._file_path(row), wait=True)

    def _show_selected(self):
        number = self.selected_key()
        if number is None or number == self.current:
            return     # 選択を外しただけ（処理中の行など）なら、入力欄はそのまま
        self.commit_pending()     # 保管済みの行で直した備考を書き込む（止めることはない）
        self._keep_draft()
        row = self.m.row_by_number(self.data.tables, number) if (number and self.data) else None
        if row is None:
            self.current = None
            self._set_panel_state(None)
            return
        self._show_row(row)

    def _keep_draft(self):
        if self.current and not self.current_stored:
            self._tidy_date()        # ほかの行に移る前に、入れかけの日時をそろえる
            row = self._current_row()
            self.drafts[self.current] = {"vals": {k: v.get() for k, v in self.vars.items()},
                                         "extra": self._draft_extra(), "auto": self.auto_name,
                                         "file": self._file_key(row) if row is not None else None}

    def _file_key(self, row):
        return (row[self.m.COL["読込フォルダ名"]], row[self.m.COL["読込ファイル名"]])

    def _show_row(self, row):
        m = self.m
        number = row[m.COL["番号"]]
        self.current = number
        self.current_stored = m.is_stored(row)
        self.number_var.set(number)
        self.source_var.set(str(Path(row[m.COL["読込フォルダ名"]]) / row[m.COL["読込ファイル名"]]))
        draft = None if self.current_stored else self.drafts.get(number)
        # 入れかけの値は、同じファイルの行にだけ出す。読み込みで消えた行の番号を、新しく読み込んだファイルが使い回す
        # ことがあるため（番号は「その日の最大に1を足す」。2026-11-13）。別のファイルのものは捨てる
        if draft and draft.get("file") != self._file_key(row):
            self.drafts.pop(number, None)
            draft = None
        if draft:
            for k, v in draft["vals"].items():
                self.vars[k].set(v)
            self._restore_draft_extra(draft["extra"])
            self.auto_name = draft["auto"]
        else:
            for k in self.PANEL_FIELDS:
                self.vars[k].set(row[m.COL[k]])
            self.auto_name = row[m.COL["保管ファイル名"]]
        if self.current_stored and number in self.writing_notes:
            self.vars["備考"].set(self.writing_notes[number])     # 書き込み中の備考
        self._after_show_row(row, draft)
        # 矢印キーで送っている間は、プレビューを出さない（キーを離したら出す。2026-11-13 班長指示）。入力欄の書き換えを
        # キーを止めるまであとに回すので、ここに来たときは、もう待たずに出す
        self.preview.show(self._file_path(row))
        if self.current_stored:
            self.state_var.set(f"保管済み（{row[m.COL['保管日時']][:16].replace('-', '/')}）")
        elif number in self.pending:
            self.state_var.set("書き込み中・書き込み待ち")
        else:
            self.state_var.set("未保管")
        self._set_panel_state("stored" if self.current_stored else "pending" if number in self.pending else "open")
        if not self.current_stored and not draft:
            self._fill_defaults()
        self.history.reset()      # Ctrl+Z で戻せるのは、この行を出してから直した分

    def _set_panel_state(self, state):
        """入力欄の状態：None（行を選んでいない）・"open"（未保管）・"stored"（保管済み）・"pending"（書き込み中）。"""
        self._panel_state = state
        if state is None:
            for v in self.vars.values():
                v.set("")
            self.source_var.set("（一覧で行を選んでください）")
            self.number_var.set("")
            self.state_var.set("")
            if hasattr(self, "preview"):
                self.preview.show(None)
            if hasattr(self, "history"):
                self.history.clear()
        # 閲覧モードでは見るだけ（2026-11-09 班長決定）。ファイルを開くことはできる
        editing = self.editing
        editable = state == "open" and editing
        # 保管済みの行では、備考のほかの欄を、入力欄に見えない形（地を窓の地と同じにし、枠線を消す）にする。直せるのが
        # 備考だけであることを、見ただけで分かるように（2026-11-13 班長決定「案１のみ」。閲覧モードでも同じ）
        locked_style = "Locked.TEntry" if state == "stored" else "TEntry"
        for name, w in self.widgets.items():
            if name == "備考":
                w.configure(state="normal" if editing and state in ("open", "stored")
                            else "readonly" if state else "disabled")
            elif isinstance(w, ttk.Combobox):   # 直せないときは、文字を選べる読み取り専用の欄に替える
                mirror = theme.show_choice(w, ("readonly" if getattr(w, "choose_only", False) else "normal")
                                           if editable else None, bool(state))
                mirror.configure(style=locked_style)
            else:
                w.configure(state="normal" if editable else "readonly" if state else "disabled",
                            style=locked_style)
            theme.tab_stop(w, bool(state))   # 閲覧でも、行を選んでいれば Tab で移れるように
        self.store_button.state(["!disabled"] if editable else ["disabled"])
        if self.pick_button is not None:
            self.pick_button.state(["!disabled"] if editable else ["disabled"])
        self.restore_button.state(["!disabled"] if state == "stored" and editing else ["disabled"])
        self.open_file_button.state(["!disabled"] if state else ["disabled"])

    def _update_mode(self):
        super()._update_mode()
        if hasattr(self, "_panel_state"):
            self._set_panel_state(self._panel_state)    # 編集モードに入った・抜けたら、入力欄の直せるかを合わせる

    def _pick_folder(self):
        start = self._resolve(self.vars["保管フォルダ名"].get())
        item = getattr(self.m, "SET_PICK_START", "")
        if (start is None or not start.is_dir()) and self.data is not None and item:
            start = self._resolve(self.m.setting_value(self.data.tables, item))
        path = filedialog.askdirectory(parent=self.root, title="保管フォルダを選ぶ", mustexist=True,
                                       initialdir=str(start) if start and start.is_dir() else None)
        if path:
            # 事務所のフォルダの場所の下なら、基点からの相対にする（2026-11-12 班長決定。PC ごとに場所が違っても使える）
            path = path.replace("/", "\\") if os.sep == "\\" else path
            self.vars["保管フォルダ名"].set(portable(path, getattr(self.cfg, "data_root", "")))

    def _current_row(self):
        if self.current is None or self.data is None:
            return None
        return self.m.row_by_number(self.data.tables, self.current)

    def _file_path(self, row):
        """行のファイルのいまの場所（保管済みなら保管した場所、未保管なら読込フォルダ）。読めなければ None。"""
        m = self.m
        if m.is_stored(row):
            folder = self._resolve(row[m.COL["保管フォルダ名"]])
            return folder / row[m.COL["保管ファイル名"]] if folder and row[m.COL["保管ファイル名"]] else None
        folder = self._resolve(row[m.COL["読込フォルダ名"]])
        return folder / row[m.COL["読込ファイル名"]] if folder and row[m.COL["読込ファイル名"]] else None

    # ------------------------------------------------------------ プレビュー

    def _show_preview(self, visible):
        """プレビューの欄を出す・隠す。"""
        panes = [str(p) for p in self.split.panes()]
        if visible and str(self.preview) not in panes:
            width = getattr(self.cfg, "preview_width", 0) or self.PREVIEW_WIDTH
            self.split.add(self.preview, before=self.main_area, width=theme.px(self.root, width),
                           minsize=theme.px(self.root, 150), stretch="never")
        elif not visible and str(self.preview) in panes:
            self._remember_preview_width()
            self.split.forget(self.preview)
        self.preview.set_active(visible)

    def _toggle_preview(self):
        self._show_preview(self.preview_var.get())

    def _remember_preview_width(self):
        w = self.preview.winfo_width()
        if w > 1:
            self.cfg.preview_width = int(round(w / theme.scale(self.root)))

    def remember_view(self):
        self.cfg.preview_visible = bool(self.preview_var.get())
        if self.cfg.preview_visible:
            self._remember_preview_width()

    def open_file(self):
        self.flush_selected()
        row = self._current_row()
        if row is None:
            return
        path = self._file_path(row)
        if path is None or not path.is_file():
            messagebox.showinfo(self.TITLE, f"ファイルが見つかりませんでした。\n{path or ''}", parent=self.root)
            return
        try:
            open_path(path)
        except OSError as e:
            messagebox.showwarning(self.TITLE, f"開けませんでした。\n{e}", parent=self.root)

    def open_folder(self, column="保管フォルダ名"):
        self.flush_selected()
        m = self.m
        row = self._current_row()
        value = self.vars["保管フォルダ名"].get() if column == "保管フォルダ名" and row is not None and \
            not m.is_stored(row) else (row[m.COL[column]] if row is not None else "")
        path = self._resolve(value) if value else None
        if path is None or not path.is_dir():
            messagebox.showinfo(self.TITLE, f"フォルダが見つかりませんでした。\n{value}", parent=self.root)
            return
        try:
            open_path(path)
        except OSError as e:
            messagebox.showwarning(self.TITLE, f"開けませんでした。\n{e}", parent=self.root)

    def _next_open_number(self, after):
        """after の次の未保管（書き込み待ちでない）の行の番号。なければ前の方から探す。"""
        items = list(self.tree.get_children())
        if after in items:
            start = items.index(after)
            order = items[start + 1:] + items[:start]
        else:
            order = items
        for iid in order:
            if iid == after or iid in self.pending:
                continue
            row = self.m.row_by_number(self.data.tables, iid)
            if row is not None and not self.m.is_stored(row):
                return iid
        return None

    def _source_path(self, row):
        folder = self._resolve(row[self.m.COL["読込フォルダ名"]])
        if folder is None:
            messagebox.showwarning(self.TITLE, "読込フォルダを、この PC の場所として読めません（事務所のフォルダの場所を"
                                               "設定してください）。", parent=self.root)
            raise StoreCancelled
        return folder / row[self.m.COL["読込ファイル名"]]

    # ------------------------------------------------------------ 保管する

    def store_selected(self):
        m = self.m
        self.flush_selected()
        row = self._current_row()
        if row is None or m.is_stored(row) or self.current in self.pending or not self._require_edit(busy_ok=True):
            return
        number = self.current
        self._tidy_date()            # 日時の欄から出ずに「保管する」を押したときも、そろえてから
        values = {k: var.get().strip() for k, var in self.vars.items()}
        # 貼り付けた絶対パスも、基点の下なら基点からの相対で記録する（2026-11-12 班長決定）
        values["保管フォルダ名"] = portable(values["保管フォルダ名"], getattr(self.cfg, "data_root", ""))
        try:
            prep = self._prepare_store(row, values)
            source = self._source_path(row)
        except StoreCancelled:
            return
        folder, file_name, targets, specials = prep["folder"], prep["file_name"], prep["targets"], prep["specials"]
        try:   # 先に確かめる（書き込むときにも、もう一度確かめる）
            storing.plan_store(source, folder, file_name, targets, specials, resolve=self._resolve)
        except storing.StoringError as e:
            messagebox.showwarning(self.TITLE, f"{e}\n\nこのファイルの移動を中止しました。", parent=self.root)
            return
        moved = {}

        def action():
            p = storing.plan_store(source, folder, file_name, targets, specials, resolve=self._resolve)
            result = storing.store(p)
            moved["yes"] = True        # この後で書き込めなければ、undo で戻す
            return result

        def after():
            self.pending.discard(number)
            self.drafts.pop(number, None)
            self.on_queue_changed()
            self._reshow_if_current(number)
            if prep.get("notes"):
                messagebox.showinfo(self.TITLE, "\n".join(prep["notes"]), parent=self.root)

        def on_error(e):
            self.pending.discard(number)
            self.on_queue_changed()
            self._reshow_if_current(number)
            where = "ファイルは読込フォルダに戻しました" if moved else "ファイルは動かしていません"
            if isinstance(e, storing.StoringError):
                msg = f"{e}\n\nこのファイルの移動を中止しました。"
            elif isinstance(e, PermissionError) and not moved:
                msg = ("このファイルを移動できませんでした。ファイルが別のアプリケーションで開かれているかもしれません。\n"
                       f"詳細：{e}")
            elif isinstance(e, (SharedError, OSError, ValueError)):
                msg = f"保管しませんでした（{where}）。\n\n{e}"
            else:
                msg = f"保管しませんでした（{where}）。\n{e!r}"
            messagebox.showerror(self.TITLE, msg, parent=self.root)

        self.pending.add(number)
        self._keep_draft()
        nxt = self._next_open_number(number)
        self.write(lambda t, result: prep["transform"](t), f"保管（{file_name}）", after, action=action,
                   undo=storing.undo_store, on_error=on_error)
        self.on_queue_changed()
        if nxt:
            self._select_item(nxt)
            self._focus_first_field()
        else:
            self._show_row(row)
            self._unhighlight(number)

    def _unhighlight(self, number):
        """処理中の行の選択の色を外す（選んだ行は字の色が黒に決まっていて、点滅が見えないため）。入力欄には、
        その行を出したままにする。終わったら _reshow_if_current で選び直す。"""
        if number in self.tree.selection():
            self.tree.selection_remove(self._group(self.tree, number))

    # ------------------------------------------------------------ 保管を取り消す（2026-11-12 までのボタンの名前は「元に戻す（保管の取り消し）」）

    def restore_selected(self):
        m = self.m
        self.flush_selected()
        row = self._current_row()
        if row is None or not m.is_stored(row) or self.current in self.pending or not self._require_edit(busy_ok=True):
            return
        number = self.current
        targets, specials = self._restore_links(row)
        links = "\n\n作ったショートカット・写しも消します。" if (targets or specials) else ""
        if not messagebox.askyesno(self.TITLE, "このファイルを、元の読込フォルダへ戻します（保管の取り消し）。\n"
                                               f"{row[m.COL['保管ファイル名']]}{links}\n\nよろしいですか？",
                                   parent=self.root):
            return
        folder = self._resolve(row[m.COL["保管フォルダ名"]])
        back = self._resolve(row[m.COL["読込フォルダ名"]])
        if folder is None or back is None:
            messagebox.showwarning(self.TITLE, "フォルダを、この PC の場所として読めません（事務所のフォルダの場所を設定"
                                               "してください）。", parent=self.root)
            return
        stored = folder / row[m.COL["保管ファイル名"]]
        back = back / row[m.COL["読込ファイル名"]]
        stored_at = row[m.COL["保管日時"]]
        file_name = row[m.COL["保管ファイル名"]]
        try:
            storing.plan_restore(stored, back, targets, specials, resolve=self._resolve, file_name=file_name)
        except storing.StoringError as e:
            messagebox.showwarning(self.TITLE, f"{e}\n\nこのファイルの元のフォルダへの移動を中止しました。",
                                   parent=self.root)
            return
        holder = {}

        def action():
            p = storing.plan_restore(stored, back, targets, specials, resolve=self._resolve, file_name=file_name)
            removed = storing.restore(p)
            holder["plan"] = p
            return p, removed

        def undo(ctx):
            storing.redo_restore(*ctx)

        def after():
            self.pending.discard(number)
            self.on_queue_changed()
            self._reshow_if_current(number)
            p = holder.get("plan")
            if p is not None and p.missing:
                messagebox.showinfo(self.TITLE, "保管を取り消しました。次の写しは見つからなかったため、消していません。\n"
                                    + "\n".join(p.missing[:20]), parent=self.root)

        def on_error(e):
            self.pending.discard(number)
            self.on_queue_changed()
            self._reshow_if_current(number)
            where = "ファイルは保管フォルダに戻しました" if holder else "ファイルは動かしていません"
            msg = f"{e}\n\nこのファイルの元のフォルダへの移動を中止しました。" if isinstance(e, storing.StoringError) \
                else f"保管を取り消しませんでした（{where}）。\n\n{e}"
            messagebox.showerror(self.TITLE, msg, parent=self.root)

        self.pending.add(number)
        self._set_panel_state("pending")
        self.state_var.set("書き込み中・書き込み待ち")
        self.write(lambda t, ctx: m.mark_restored(t, number, stored_at), f"保管の取り消し（{file_name}）", after,
                   select=number, action=action, undo=undo, on_error=on_error)
        self.on_queue_changed()
        self._unhighlight(number)

    def _reshow_if_current(self, number):
        """書き込みが終わった（失敗した）行を、入力欄に出していれば、出し直す（状態の表示と、直せるかを合わせる）。"""
        if self.current == number and self.data is not None:
            row = self.m.row_by_number(self.data.tables, number)
            if row is not None:
                self._show_row(row)
                if not self.tree.selection() and self.tree.exists(number):
                    self._select_item(number)    # 処理中に外した選択を戻す

    def delete_selected(self):
        """未保管の行を消し、読込フォルダのファイルをごみ箱へ移す（2026-11-09 班長決定。誤って消しても、ごみ箱から
        戻せる。ファイルを残すと、次に読み込んだときに、また足されるため）。保管済みの行は消さない（先に「保管を取り消す」）。"""
        self.flush_selected()
        m = self.m
        row = self._current_row()
        if row is None or not self._require_edit(busy_ok=True) or self.current in self.pending:
            return
        number = self.current
        if m.is_stored(row):
            messagebox.showinfo(self.TITLE, "保管済みのファイルは、消せません。消すときは、先に「保管を取り消す」で読込フォルダへ"
                                            "戻してください。", parent=self.root)
            return
        folder = self._resolve(row[m.COL["読込フォルダ名"]])
        path = folder / row[m.COL["読込ファイル名"]] if folder is not None else None
        exists = path is not None and path.is_file()
        if exists and trash.is_network_path(path):
            messagebox.showinfo(self.TITLE, "ネットワーク上のフォルダのファイルは、ごみ箱へ移せない（戻せなくなる）ため、消せません。"
                                            f"エクスプローラーで消してから、「ファイルを読み込む」を押してください。\n{path}",
                                parent=self.root)
            return
        what = f"{path}\n\nファイルは、ごみ箱へ移します（ごみ箱から戻せます）。" if exists else \
            f"{row[m.COL['読込ファイル名']]}\n\n（読込フォルダには、もうこのファイルはありません。行だけを消します。）"
        if not messagebox.askyesno(self.TITLE, f"この行を消します。\n{what}\n\nよろしいですか？", icon="warning",
                                   parent=self.root):
            return
        nxt = self._next_open_number(number)
        moved = {}

        def action():
            if exists:
                trash.send_to_trash(path)    # 編集の権利を得てから移す（ほかの人が編集中なら、移さずに止まる）
                moved["yes"] = True

        def after():
            self.drafts.pop(number, None)
            if nxt:
                self.select_key(nxt)

        def on_error(e):
            if moved:
                msg = ("ファイルはごみ箱へ移しましたが、行を消せませんでした。ごみ箱から元へ戻すか、「ファイルを読み込む」を押して"
                       f"ください（行は、読み込んだときに消えます）。\n\n{e}")
            else:
                msg = f"消しませんでした（ファイルは動かしていません）。\n\n{e}"
            messagebox.showerror(self.TITLE, msg, parent=self.root)

        self.write(lambda t, ctx: m.delete_row(t, number), f"行の削除（{row[m.COL['読込ファイル名']]}）", after,
                   action=action, on_error=on_error)

    def commit_pending(self):
        """保管済みの行の備考を直していれば、書き込みを始める（ほかの行に移るとき・Enter・ファイルを読み込むとき・編集を
        終えるとき・閉じるとき・最新を読み込むとき。2026-11-12 班長決定。それまでは「備考を書き込む」のボタン）。
        未保管の行で入れかけた値は、今までどおり「保管する」のときに書く（移っても、行ごとに覚える）。止めることはない。"""
        self.flush_selected()
        if self.current is None or not self.editing or self.data is None or self.current in self.pending:
            return True
        row = self._current_row()
        if row is None or not self.m.is_stored(row):
            return True
        number, note = self.current, self.vars["備考"].get().strip()
        if note == (self.writing_notes[number] if number in self.writing_notes else row[self.m.COL["備考"]]):
            return True

        def after():
            if self.writing_notes.get(number) == note:
                self.writing_notes.pop(number, None)
            if self.current == number and self.data is not None:   # まだこの行にいる（Enter・編集を終えるときなど）
                self._reshow_if_current(number)

        def on_error(e):
            self.writing_notes.pop(number, None)
            self.show_write_error(e)
        self.writing_notes[number] = note
        self.write(lambda t: self.m.update_note(t, number, note), "備考", after, on_error=on_error)
        return True

    # ------------------------------------------------------------ 読込フォルダのファイルを読み込む

    def read_files(self):
        m = self.m
        if self.data is None or not self._require_edit(busy_ok=True):
            return
        self.commit_pending()
        if not self.data.tables[m.READ_FOLDERS].rows:
            messagebox.showinfo(self.TITLE, "読込フォルダが設定されていません。「事務所の設定」の「読込フォルダ」に足して"
                                            "ください。", parent=self.root)
            return
        if not messagebox.askokcancel(self.TITLE, "読込フォルダ内のファイル名を読み込みます。", parent=self.root):
            return
        warnings = []
        counts = {}

        def action():
            tables = self.store.loaded.tables
            found, warn = self._scan(tables)
            warnings.extend(warn)
            missing = []
            for r in tables[m.STORE].rows:
                if m.is_stored(r):
                    continue
                folder = self._resolve(r[m.COL["読込フォルダ名"]])
                if folder is not None and folder.is_dir() and not (folder / r[m.COL["読込ファイル名"]]).exists():
                    missing.append(r[m.COL["番号"]])   # 読込フォルダはあるのに、ファイルがなくなった
            return found, missing

        def transform(t, ctx):
            found, missing = ctx
            new, added, removed = m.merge_found(t, found, missing)
            counts.update(added=added, removed=removed)
            return new

        def after():
            msg = "読込ファイル名の読み込みを完了しました。\n"
            msg += (f"{counts['added']}個のファイル名を読み込みました。" if counts.get("added")
                    else "読み込むファイルがありませんでした。")
            if counts.get("removed"):
                msg += f"\n読込ファイルがなくなった未保管の行を {counts['removed']} 件消しました。"
            if warnings:
                msg += "\n\n" + "\n".join(warnings[:20])
            messagebox.showinfo(self.TITLE, msg, parent=self.root)
            if self.current is None:
                self.after_first_load()
        self.write(transform, "読み込んだファイル名", after, action=action)

    def _scan(self, tables):
        """読込フォルダのファイルを集める（裏のスレッドで）。→ (FoundFile の並び, 知らせ)"""
        m = self.m
        prefixes = m.setting_values(tables, m.SET_SKIP_PREFIX)
        found, warnings = [], []
        for value, sub in tables[m.READ_FOLDERS].rows:
            base = self._resolve(value)
            if base is None or not base.is_dir():
                warnings.append(f"{value} が見つかりません。")
                continue
            sep = "\\" if ("\\" in value or ":" in value) else "/"
            try:
                walker = os.walk(base) if sub == m.YES else [(str(base), [], [e.name for e in os.scandir(base)
                                                                                if e.is_file()])]
                for dirpath, dirs, files in walker:
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                    rel = os.path.relpath(dirpath, base)
                    folder = value if rel == "." else value.rstrip("\\/") + sep + rel.replace(os.sep, sep)
                    for name in sorted(files):
                        if m.should_skip(name, prefixes):
                            continue
                        try:
                            mtime = os.stat(os.path.join(dirpath, name)).st_mtime
                        except OSError:
                            warnings.append(f"{dirpath} に読み込めないファイルがありました。")
                            continue
                        found.append(m.FoundFile(folder, name, mtime))
            except OSError as e:
                warnings.append(f"{value} の読み込み時にエラーが発生しました：{e}")
        return found, warnings

    # ------------------------------------------------------------ 設定

    def open_settings(self):
        dlg = self._settings_dialog()
        self.root.wait_window(dlg)
        self._focus_table()
        if not dlg.result:
            return False
        changed_master = dlg.result.master_path != self.cfg.master_path
        if changed_master and self.editing:
            self.store.end_edit()
            self.editing = False
        self.cfg = dlg.result
        self.settings.save(self.cfg)
        if changed_master or self.store is None:
            self.open_store()
        else:
            self.reload()
        return True

    def write_office(self, result):
        """事務所の設定の画面の結果（テーブル名 → Table）を書き込む。"""
        def transform(t):
            new = self.m.copy_tables(t)
            new.update({k: v.copy() for k, v in result.items()})
            return new
        self.write(transform, "事務所の設定")
