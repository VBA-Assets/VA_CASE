"""VA Call の画面（一覧・その下の入力欄・新しいメモ・書き込み・メール・CSV）。

一覧で行を選ぶと、下の入力欄にそのメモが出る（2026-11-09 班長決定。VA Filing・VA Receipt と同じ形）。「新しいメモ」で、
番号・入力者・日時を入れた空のメモを書き込み（現行と同じ）、相手先などを入れる。直した値は、ほかのメモに移るとき・
新しいメモ・メールを送るとき・編集を終えるとき・閉じるとき・最新を読み込むときに書き込み、直す前の値には Ctrl+Z で
戻す（2026-11-12 班長決定。それまでは「書き込む」「入力を戻す」のボタンがあった）。編集モードは、ほかのツールと同じく「編集を始める」を押してから（閲覧モードでは見るだけ。同日 班長決定）。
メールは、既定のメールソフトを、宛先・件名・本文を入れた状態で開き、利用者が送信を押す（mailto。同日 班長決定）。
"""
import getpass
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter import font as tkfont

from ..common.ui import autocomplete, theme
from ..common.ui.tooltip import Tooltip
from ..common.ui.undo import EditHistory
from ..common.ui.shared_app import SharedApp, open_path, prepare_process
from . import model as m
from . import settings
from .dialogs import TITLE, OfficeDialog, SettingsDialog

# 一覧の列の並びは、電話メモ Ver402 の表「電話メモ」と同じ（共有データの列の順と同じ。
# 2026-11-12 班長指示「VA CALLも同じにする」）
DISPLAY_COLUMNS = list(m.MEMO_COLUMNS)
COLUMN_WIDTHS = {"番号": 72, "日時": 110, "相手先": 150, "電話番号": 110, "用件": 130, "対応": 140, "内容": 360,
                 "宛先": 80, "メール送信日時": 110, "確認者": 80, "処理": 70, "入力者": 80}
PANEL_FIELDS = ("入力者", "日時", "相手先", "電話番号", "用件", "対応", "内容", "宛先", "確認者", "処理")
CHOOSE = {"入力者": "staff", "宛先": "staff", "確認者": "staff", "用件": "用件", "対応": "対応", "処理": "処理"}
WIDE_FIELDS = ("内容",)
# オートコンプリートを付ける欄（2026-11-09 班長決定）
AUTOCOMPLETE_FIELDS = ("相手先", "電話番号")
# 全角で40字が入る幅にし、入力欄がそれより狭いときは、それに合わせて狭くする欄（2026-11-09 班長指示）
FIT_FIELDS = {"相手先": 40}


class CallApp(SharedApp):
    TITLE = TITLE
    ABOUT_LINE = "電話のメモを、事務所の共有フォルダで管理する"
    ICON_FILE = "VA_Call.ico"      # ウィンドウ・タスクバーのアイコン（assets。scripts\generate_icons.py）
    TOOL = m.TOOL
    SCHEMA = m.SCHEMA
    MASTER_FILE_NAME = m.MASTER_FILE_NAME
    ROW_NAME = "メモ"
    CSV_FILE_NAME = "電話メモ"
    CSV_NOTE = "CSV には、相手先・電話番号・内容などがそのまま入っています。"

    def __init__(self, root):
        self.current = None
        self.drafts = {}            # 番号 → 入力欄で直した値（書き込み中のもの・書き込めなかったもの。この画面の中だけ）
        self.writing_memos = set()  # いま書き込んでいる（待ち行列を含む）メモの番号
        self.me = ""                # この PC を使っている人の所員名（所員の表のユーザー名から引く）
        super().__init__(root, settings)

    def empty_tables(self):
        return m.empty_tables()

    def diagnostic_lines(self):
        return [f"入れかけて、まだ書き込んでいないメモ {len(self.drafts)} 件・この PC の人の所員名："
                f"{'見つかった' if self.me else '見つからない'}"]

    def csv_columns(self):
        return m.MEMO_COLUMNS

    def csv_add(self, tables, rows):
        return m.import_rows(tables, rows)

    def csv_drop_existing(self, tables, rows):
        return m.drop_existing(tables, rows)

    # ------------------------------------------------------------ 画面の組み立て

    def _build_menu(self):
        bar = tk.Menu(self.root)
        f = tk.Menu(bar, tearoff=False)
        f.add_command(label="最新を読み込む", command=self.reload_latest, accelerator="F5")
        f.add_separator()
        f.add_command(label="CSV に出力…", command=self.export_csv)
        f.add_command(label="CSV から取り込む…（編集モード）", command=self.import_csv)
        self.edit_only_menu(f)
        f.add_separator()
        f.add_command(label="この PC の設定…", command=self.open_settings)
        f.add_command(label="事務所の設定（所員・選択肢）…", command=self.open_office)
        f.add_separator()
        f.add_command(label="閉じる", command=self.on_close)
        bar.add_cascade(label="ファイル", menu=f)
        self.build_help_menu(bar)
        self.root.configure(menu=bar)
        self.root.bind("<F5>", lambda e: self.reload_latest())

    def _build_toolbar(self):
        rb = self.build_ribbon()
        g = rb.group("メモ")
        self.edit_only(g.large("新しいメモ", self.new_memo,
                               tip="新しいメモを足します。番号・入力者・日時を入れた空のメモを書き込み、入力欄に出します。"
                                   "いま出しているメモで直した値がまだ書き込まれていなければ、先に書き込みます。"
                                   "編集モードで使えます。"))
        # ［コピー］（2026-11-14 班長指示「「コピー」ボタンを追加。「消す」ボタンの上に配置。選択しているメモをコピーする。
        # 見出しは付けない。リストの右クリックメニューは廃止。」「VA CASEを含め、すべてのツールに適用」）。閲覧モードでも使える
        g.small("コピー", self.copy_selected_rows,
                tip="選んでいるメモを、一覧に出している列のタブ区切りでコピーします（見出しは付けません）。Excel などに"
                    "貼り付けられます。何件かを選んでいれば、その全部をコピーします。")
        self.edit_only(g.small("消す", self.delete_memo,
                               tip="選んでいるメモを消します（確かめてから）。編集モードで使えます。"))
        self.build_search_group(rb)

    def _build_body(self):
        self._build_panel()
        self.build_list(m.MEMO_COLUMNS, DISPLAY_COLUMNS, COLUMN_WIDTHS)
        self.history.bind_keys(self.tree)
        self.tree.tag_configure("done", foreground=theme.STATUS_FG["closed"])     # 処理済み・確認済み（灰色）
        self.tree.tag_configure("draft", foreground=theme.ACCENT)                  # 書き込み中・書き込めなかった変更がある
        self.tree.bind("<Return>", lambda e: (self.flush_selected(), self.widgets["相手先"].focus_set(), "break")[2])

    def _build_panel(self):
        outer = ttk.Frame(self.root, padding=(8, 6, 8, 0))
        outer.pack(fill="x", side="bottom")
        p = self.mode_card(outer, padding=(10, 6))
        p.columnconfigure(1, weight=1)
        font = theme.field_font(self.root)
        self.vars = {k: tk.StringVar() for k in PANEL_FIELDS if k != "内容"}
        self.number_var = tk.StringVar()
        self.state_var = tk.StringVar()
        self.mail_var = tk.StringVar()
        ttk.Label(p, text="番号").grid(row=0, column=0, sticky="e", padx=(0, 6))
        top = ttk.Frame(p)
        top.grid(row=0, column=1, columnspan=2, sticky="w")
        # 番号は、なぞって選び Ctrl+C でコピーできる（見た目はラベルのまま。2026-11-13 班長指摘「カードで番号がコピーできない」）
        theme.value_text(top, self.number_var).pack(side="left")
        ttk.Label(top, textvariable=self.state_var, style="Note.TLabel").pack(side="left", padx=(16, 0))
        self.widgets = {}
        r = 1
        for name, width in (("入力者", 16), ("日時", 18), ("相手先", 20), ("電話番号", 20), ("用件", 30), ("対応", 30),
                            ("内容", 20), ("宛先", 16), ("確認者", 16), ("処理", 16)):
            ttk.Label(p, text=name, style=autocomplete.label_style(name, AUTOCOMPLETE_FIELDS)).grid(
                row=r, column=0, sticky="ne" if name == "内容" else "e", padx=(0, 6), pady=2)
            if name in CHOOSE:
                w = ttk.Combobox(p, textvariable=self.vars[name], width=width, font=font)
            elif name == "内容":
                # 長い内容も入れられるよう、右にスクロールバーを付ける（2026-11-09 班長指示）
                holder = ttk.Frame(p)
                holder.grid(row=r, column=1, columnspan=2, sticky="we", pady=2)   # 入力欄の幅いっぱい（2026-11-09 班長指示）
                # 6行（2026-11-09 班長指示）。欄ごとの元に戻すは使わない（入力欄全体の Ctrl+Z にまとめた）
                w = tk.Text(holder, width=width, height=6, font=font, wrap="char", undo=False)
                bar = ttk.Scrollbar(holder, orient="vertical", command=w.yview)
                w.configure(yscrollcommand=bar.set)
                w.pack(side="left", fill="both", expand=True)
                bar.pack(side="right", fill="y")
                w.bind("<Tab>", lambda e: (e.widget.tk_focusNext().focus_set(), "break")[1])
                w.bind("<<Modified>>", self._text_modified)
            else:
                w = ttk.Entry(p, textvariable=self.vars[name], width=width, font=font)
            # 日時の欄の右の入力例（「例：2025/11/9 10:30」）は、2026-11-13 になくした（班長決定「なくす」。VA Receipt の
            # 「例：20251101」をなくしたのにそろえた。読めない日時のときは、例を添えて知らせる）
            if name != "内容":
                # 幅を合わせる欄は、右の列（メールなど）の上にもかかってよい（狭いウィンドウで、右の列に押されないように）
                w.grid(row=r, column=1, columnspan=2 if name in FIT_FIELDS else 1,
                       sticky="we" if name in WIDE_FIELDS else "w", pady=2)
            self.widgets[name] = w
            r += 1
        self.widgets["処理"].bind("<<ComboboxSelected>>", lambda e: self._done_chosen())
        # 相手先・電話番号は、これまでの値から補う（オートコンプリート。2026-11-09 班長決定）
        for name in AUTOCOMPLETE_FIELDS:
            autocomplete.attach_entry(self.widgets[name],
                                      lambda n=name: autocomplete.column_values(self.rows, m.COL[n]))
        for name in self.vars:
            self.vars[name].trace_add("write", lambda *a: self._mark_dirty())
        # 相手先が、これまでのメモの相手先と一致したら、電話番号を入れる（2026-11-09 班長指示）
        self.vars["相手先"].trace_add("write", lambda *a: self._partner_changed())
        self._auto_phone = ""
        bb = ttk.Frame(p)
        bb.grid(row=r, column=1, sticky="w", pady=(6, 2))
        # オートコンプリートを付けた欄（名前に下線）の説明（2026-11-09 班長決定）。2026-11-12 から、メールの行の左に置く
        # （それまでは、ここに「閲覧モードです」「直したら、ほかのメモに移るときに書き込みます」を出し、この説明は1段下に
        # 置いていた。班長指摘「この行は不要ではないか？」で、その文をなくし、入力欄を1段低くした）
        ttk.Label(bb, text=autocomplete.NOTE, style="Note.TLabel").pack(side="left")
        # メールは付け足しの機能なので、入力欄の右下の隅に離して置く（2026-11-09 班長指示）
        mf = ttk.Frame(p)
        mf.grid(row=r, column=2, sticky="se", padx=(24, 0), pady=(6, 2))
        ttk.Label(mf, text="メール送信日時", style="Note.TLabel").pack(side="left")
        ttk.Label(mf, textvariable=self.mail_var, style="Note.TLabel").pack(side="left", padx=(6, 10))
        self.mail_button = ttk.Button(mf, text="メールを送る…", command=self.send_mail)
        self.mail_button.tooltip = Tooltip(
            self.mail_button, "このメモを、宛先の所員へのメールにして、メールソフトで開きます（直した値は、先に書き込みます）。"
                              "内容を確かめてから、メールソフトで送信してください。送った日時をメモに書きます。", above=True)
        self.mail_button.pack(side="left")
        self._loading_panel = False
        # Ctrl+Z・Ctrl+Y（2026-11-12 班長決定。入力欄と一覧で）
        self.history = EditHistory(self.root, lambda: (self._panel_values(), None), self._restore_panel,
                                   focus=lambda name: self.widgets[name].focus_set())
        for name, w in self.widgets.items():
            self.history.watch(w, name)
        self._field_font = tkfont.Font(font=font)
        p.bind("<Configure>", lambda e: self._fit_fields(e.width))
        self._set_panel(None)

    def _fit_fields(self, panel_width):
        """相手先の欄を、全角で40字が入る幅にする。入力欄がそれより狭いときは、右端に収まるよう狭くする。"""
        unit = max(1, self._field_font.measure("0"))    # ttk の欄の幅の1単位（「0」の幅）
        for name, zenkaku in FIT_FIELDS.items():
            w = self.widgets[name]
            now = int(str(w.cget("width")))
            pad = theme.px(self.root, 10)                 # 欄の枠と内側の余白
            want = self._field_font.measure("国" * zenkaku) + pad
            room = panel_width - w.winfo_x() - theme.px(self.root, 16)
            chars = max(8, -(-(min(want, room) - pad) // unit))
            if min(want, room) == room:
                chars = max(8, (room - pad) // unit)
            if chars != now:
                w.configure(width=chars)

    # ------------------------------------------------------------ 読み込み

    @property
    def rows(self):
        return self.data.tables[m.MEMO].rows if self.data else []

    def on_data(self, data):
        self.norm_cache = {}
        self.me = m.staff_for_user(data.tables, getpass.getuser())
        staff = [""] + m.staff_names(data.tables)
        for name, kind in CHOOSE.items():
            w = self.widgets[name]
            w.configure(values=staff if kind == "staff" else [""] + m.choice_values(data.tables, kind))

    def after_first_load(self):
        items = self.tree.get_children()
        if items:
            self._select_item(items[-1])     # いちばん新しいメモ（番号の昇順の最後）

    # ------------------------------------------------------------ 一覧

    def refresh(self):
        self.flush_selected()
        selected = self.current
        self.tree.delete(*self.tree.get_children())
        shown = 0
        # すべてのセルを、列の幅で折り返して出す（2026-11-09 班長指示。それまでは内容だけを折り返し、一覧のすべての
        # 行の高さを、いちばん行数の多い内容に合わせていた）
        self.begin_wrapped_list()
        for row in self.rows:
            if not self.query.matches(row, self._norm(row)):
                continue
            values = self._list_values(row)
            if not self.passes_filter(m.MEMO_COLUMNS, values):
                continue
            self.insert_wrapped(row[m.COL["番号"]], m.MEMO_COLUMNS, values, self._row_tags(row))
            shown += 1
        total = len(self.rows)
        label = self.narrowed_label()
        self.count_label.configure(text=f"{label} {shown} 件（全 {total} 件）" if label else f"{total} 件")
        self._update_mode()
        if selected and self.tree.exists(selected):
            self._select_item(selected)
            if selected not in self.drafts:
                self._show(selected)
        elif selected:
            self.current = None
            self._set_panel(None)

    def select_key(self, key):
        if key and self.tree.exists(key):
            self._select_item(key)
            self._on_select()
            self.flush_selected()           # 矢印キーの直後でも、あとに回さず、いま出す

    # ------------------------------------------------------------ 入力欄

    def _panel_values(self):
        v = {k: var.get().strip() for k, var in self.vars.items()}
        v["内容"] = self.widgets["内容"].get("1.0", "end-1c").rstrip("\n")
        return v

    def _row_values(self, row):
        v = {k: row[m.COL[k]] for k in PANEL_FIELDS}
        v["日時"] = m.display_datetime(v["日時"])
        return v

    def _put_values(self, v):
        self._loading_panel = True
        try:
            for k, var in self.vars.items():
                var.set(v.get(k, ""))
            t = self.widgets["内容"]
            state = t.cget("state")
            t.configure(state="normal")
            t.delete("1.0", "end")
            t.insert("1.0", v.get("内容", ""))
            t.edit_modified(False)
            t.configure(state=state)
        finally:
            self._loading_panel = False

    # 矢印キーで送っている間は、入力欄の書き換えをあとに回す（list_view.py の _on_select。2026-11-13 班長指示「VA Phoneも
    # 同じことを確認。」）

    def _show_selected(self):
        number = self.selected_key()
        if number is None or number == self.current:
            return
        if not self.commit_pending():       # 確かめで止めたときは、入力欄のメモを選び直す（移らない）
            if self.current is not None and self.tree.exists(self.current):
                self._select_item(self.current)
            return
        self._keep_draft()
        self._show(number)

    def _show(self, number):
        row = m.row_by_number(self.data.tables, number) if self.data else None
        if row is None:
            self.current = None
            self._set_panel(None)
            return
        self.current = number
        self._auto_phone = ""     # 自動で入れた電話番号は、メモごと
        self._put_values(self.drafts.get(number) or self._row_values(row))
        self.number_var.set(number)
        self.mail_var.set(m.display_datetime(row[m.COL["メール送信日時"]]) or "（まだ）")
        self._set_panel(number)
        self.history.reset()

    def _restore_panel(self, state):
        """Ctrl+Z・Ctrl+Y で、入力欄の値を入れ替える。"""
        self._put_values(state[0])
        self._mark_dirty()

    def _keep_draft(self):
        """直した値を、行ごとに覚える（書き込みが終わるまで。書き込めなかったときも残す）。"""
        if self.current is None or self.data is None:
            return
        row = m.row_by_number(self.data.tables, self.current)
        if row is None:
            return
        v = self._panel_values()
        if v != self._row_values(row):
            self.drafts[self.current] = v
        else:
            self.drafts.pop(self.current, None)

    def _mark_dirty(self):
        if self._loading_panel or self.current is None:
            return
        self.history.changed()
        self._keep_draft()
        self._update_state()

    def _text_modified(self, event):
        t = self.widgets["内容"]
        if t.edit_modified():
            t.edit_modified(False)
            self._mark_dirty()

    def _update_state(self):
        if self.current is None:
            self.state_var.set("")
            return
        # 番号の右には、処理済みならその処理を出す。書き込んでいない値があるときの文（直した値は、ほかのメモに移るときに
        # 書き込みます）は、2026-11-12 になくした（一覧で青字になる。書き込むときと Ctrl+Z はマニュアルに書く）
        row = m.row_by_number(self.data.tables, self.current)
        self.state_var.set(row[m.COL["処理"]] if row is not None and m.is_done(row) and self.current not in self.drafts
                           else "")
        if self.tree.exists(self.current):
            self._update_list_row(self.current)     # 直している値を、一覧にも出す（2026-11-13 班長決定）
            self._update_mode()

    def _set_panel(self, number):
        if number is None:
            self._put_values({})
            self.number_var.set("（一覧でメモを選んでください）")
            self.mail_var.set("")
            self.history.clear()
        self._apply_panel_state()
        self._update_state()

    def _apply_panel_state(self):
        """入力欄とボタンを、いまのモードに合わせる（閲覧モードでは見るだけ。2026-11-09 班長決定）。"""
        number = self.current
        editable = number is not None and self.editing
        for name, w in self.widgets.items():
            if isinstance(w, ttk.Combobox):   # 直せないときは、文字を選べる読み取り専用の欄に替える
                theme.show_choice(w, "readonly" if editable else None, number is not None)
            elif isinstance(w, tk.Text):
                w.configure(state="normal" if editable else "disabled",
                            background=theme.FIELD_BG if editable else theme.READONLY_BG)
            else:
                w.configure(state="normal" if editable else "readonly" if number is not None else "disabled")
            theme.tab_stop(w, number is not None)   # 閲覧でも、メモを選んでいれば Tab で移れるように
        self.mail_button.state(["!disabled"] if editable else ["disabled"])

    def _update_mode(self):
        super()._update_mode()
        if hasattr(self, "mail_button"):
            self._apply_panel_state()     # 編集モードに入った・抜けたら、入力欄の直せるかを合わせる

    def _partner_changed(self):
        """相手先が、これまでのメモの相手先と一致したら、そのいちばん新しいメモの電話番号を入れる。
        電話番号を利用者が入れたときは変えない（空か、前に自動で入れた番号のときだけ入れる）。"""
        if self._loading_panel or self.current is None or self.data is None or not self.editing:
            return
        phone = m.phone_for(self.data.tables, self.vars["相手先"].get().strip(), exclude=self.current)
        if phone and self.vars["電話番号"].get().strip() in ("", self._auto_phone):
            self.vars["電話番号"].set(phone)
            self._auto_phone = phone

    def _done_chosen(self):
        """処理を選んだとき、確認者が空なら、自分の所員名を入れる（2026-11-09 に示した）。"""
        if self.vars["処理"].get() and not self.vars["確認者"].get() and self.me:
            self.vars["確認者"].set(self.me)

    # ------------------------------------------------------------ 新しいメモ・書き込む・消す

    def delete_memo(self):
        """選んでいるメモを消す（確かめてから。編集モードのときだけ）。消したら、次のメモを選ぶ。"""
        self.flush_selected()
        if self.current is None or not self._require_edit(busy_ok=True):
            return
        number = self.current
        row = m.row_by_number(self.data.tables, number)
        if row is None:
            return
        if not messagebox.askyesno(TITLE, f"メモ {number}（{m.display_datetime(row[m.COL['日時']])}　"
                                          f"{row[m.COL['相手先']] or '相手先なし'}）を消します。\n\n"
                                          "消すと元に戻せません。よろしいですか？", icon="warning", parent=self.root):
            return
        items = list(self.tree.get_children())
        i = items.index(number) if number in items else -1
        nxt = items[i + 1] if 0 <= i < len(items) - 1 else (items[i - 1] if i > 0 else None)
        self.drafts.pop(number, None)

        def after():
            if nxt:
                self.select_key(nxt)
        self.current = None
        self.write(lambda t: m.delete_memo(t, number), f"メモ {number} の削除", after)

    def new_memo(self):
        if self.data is None or not self._require_edit(busy_ok=True):
            return
        if not self.commit_pending():       # いまのメモで直した値を、先に書き込む（待ち行列に入る）
            return
        holder = {}

        def transform(t):
            new, number = m.add_memo(t, self.me)
            holder["number"] = number
            return new

        def after():
            number = holder.get("number")
            self.select_key(number)
            self.widgets["相手先"].focus_set()
        self.write(transform, "新しいメモ", after)

    def commit_pending(self):
        """入力欄で直した値があれば、書き込みを始める（ほかのメモに移るとき・新しいメモ・メールを送るとき・編集を
        終えるとき・閉じるとき・最新を読み込むとき。2026-11-12 班長決定）。確かめで止めたら False（そのメモに留まる）。"""
        self.flush_selected()
        if self.current is None or not self.editing or self.data is None:
            return True
        row = m.row_by_number(self.data.tables, self.current)
        if row is None:
            return True
        v = self._panel_values()
        if v == self._row_values(row) or (self.current in self.writing_memos and self.drafts.get(self.current) == v):
            return True     # 直していない（か、いま書き込んでいる値のまま）
        return self.save_memo()

    def save_memo(self):
        """入力欄の値を書き込む（確かめてから、待ち行列に入れる）。→ True：書き込みを始めた。False：確かめで止めた。"""
        if self.current is None or not self._require_edit(busy_ok=True):
            return False
        number = self.current
        values, problems = m.check_values(self._panel_values())
        if problems:
            messagebox.showwarning(TITLE, f"メモ {number} を書き込めません。直してください。\n\n" + "\n".join(problems),
                                   parent=self.root)
            return False

        def after():
            self.writing_memos.discard(number)
            self.drafts.pop(number, None)
            if self.current == number:      # まだこのメモにいる（編集を終える・閉じるときなど）
                self._show(number)
            else:
                self._update_row_tags(number)

        def on_error(e):
            self.writing_memos.discard(number)
            self._update_state()
            self.show_write_error(e)
        self.drafts.pop(number, None)
        self.drafts[number] = self._panel_values()      # 書き込みが終わるまでは、直した値を残す（書き込めなかったときも残す）
        self.writing_memos.add(number)
        self.write(lambda t: m.update_memo(t, number, values), f"メモ {number}", after, on_error=on_error)
        return True

    def _list_values(self, row):
        """一覧に出す値（列の順）。入力欄で直していて、まだ書き込んでいない値（書き込み中・書き込めなかった値も）が
        あれば、その値を出す（字は青。2026-11-13 班長決定「A 青字のまま一覧に出す」。それまでは、書き込むまで前の値の
        ままで、青字だけで示していた）。"""
        values = list(row)
        for c in ("日時", "メール送信日時"):
            values[m.COL[c]] = m.display_datetime(row[m.COL[c]])
        for k, v in (self.drafts.get(row[m.COL["番号"]]) or {}).items():
            if k in m.COL:
                values[m.COL[k]] = v       # 入力欄の値（日時も、一覧と同じ出し方）
        return values

    def _row_tags(self, row):
        return ["draft"] if row[m.COL["番号"]] in self.drafts else (["done"] if m.is_done(row) else [])

    def _update_list_row(self, number):
        """メモ number の一覧の字と色を、いまの値（直している値）に合わせる。"""
        row = m.row_by_number(self.data.tables, number) if self.data else None
        if row is not None and self.tree.exists(number):
            self.update_list_row(number, m.MEMO_COLUMNS, self._list_values(row), self._row_tags(row))

    def _update_row_tags(self, number):
        if self.data is not None and self.tree.exists(number):
            self._update_list_row(number)
            SharedApp._update_mode(self)   # 縞を付け直す

    # ------------------------------------------------------------ メール（mailto。2026-11-09 班長決定）

    def send_mail(self):
        self.flush_selected()
        if self.current is None or not self._require_edit(busy_ok=True):
            return
        # メールは書き込んだ値で作るので、直した値があれば先に書き込み、終わってからもう一度始める（2026-11-12 班長決定。
        # それまでは「先に書き込む」と知らせて止めた）
        if not self.commit_pending():
            return
        if self.writing or self._write_queue:
            self.after_writes(self.send_mail)
            return
        number = self.current
        row = m.row_by_number(self.data.tables, number)
        if row[m.COL["メール送信日時"]]:
            if not messagebox.askyesno(TITLE, f"既に送信しています（{m.display_datetime(row[m.COL['メール送信日時']])}）。"
                                              "\n\nもう一度送信しますか？", parent=self.root):
                return
        to = row[m.COL["宛先"]]
        address = m.mail_address(self.data.tables, to)
        if not to or not address:
            messagebox.showinfo(TITLE, "宛先を選んでください。宛先の所員のメールアドレスは、事務所の設定の「所員」に入れて"
                                       "ください。" if not to else f"{to} のメールアドレスが設定されていません。",
                                parent=self.root)
            return
        if not messagebox.askokcancel(TITLE, f"このメモを、次の宛先へのメールにします。\n\n{to}（{address}）\n\n"
                                             "メールソフトが開きます。内容を確かめてから、送信を押してください。",
                                      parent=self.root):
            return
        body = m.mail_body(row)
        url = m.mailto_url(address, m.MAIL_SUBJECT, body)
        pasted = False
        if len(url) > m.MAILTO_LIMIT:   # 長すぎると本文が渡らないので、本文はクリップボードから貼ってもらう
            self.root.clipboard_clear()
            self.root.clipboard_append(body)
            url = m.mailto_url(address, m.MAIL_SUBJECT, "（本文を貼り付けてください）")
            pasted = True
        try:
            open_path(url)
        except OSError as e:
            messagebox.showerror(TITLE, f"メールソフトを開けませんでした。既定のメールソフトを確かめてください。\n{e}",
                                 parent=self.root)
            return
        if pasted:
            messagebox.showinfo(TITLE, "本文が長いため、本文はクリップボードに写しました。メールの本文に貼り付けてから"
                                       "送信してください。", parent=self.root)
        sent_at = m.now_text()
        self.write(lambda t: m.update_memo(t, number, {"メール送信日時": sent_at}), f"メモ {number} のメール送信日時",
                   select=number)

    # ------------------------------------------------------------ 設定・閉じる

    def open_settings(self):
        dlg = SettingsDialog(self.root, settings.CallConfig(**vars(self.cfg)))
        self.root.wait_window(dlg)
        self._focus_table()
        if not dlg.result:
            return False
        changed_master = dlg.result.master_path != self.cfg.master_path
        if changed_master and self.editing:
            self.store.end_edit()
            self.editing = False
        self.cfg = dlg.result
        settings.save(self.cfg)
        if changed_master or self.store is None:
            self.open_store()
        else:
            self.reload()
        return True

    def open_office(self):
        if self.data is None:
            return
        result = self.run_office_dialog(lambda editable: OfficeDialog(self.root, self.data.tables, editable=editable))
        if not result:
            return

        def transform(t):
            new = m.copy_tables(t)
            new.update({k: v.copy() for k, v in result.items()})
            return new
        self.write(transform, "事務所の設定")

    def can_close(self):
        """直した値を書き込んだ後にも、書き込めなかったメモが残っていれば確かめる。"""
        self._keep_draft()
        if self.drafts:
            return messagebox.askyesno(TITLE, f"書き込めなかった変更のあるメモが {len(self.drafts)} 件あります（番号 "
                                              + "・".join(sorted(self.drafts, key=lambda n: int(n) if n.isdigit() else 0))
                                              + "）。\n書き込まずに閉じますか？", icon="warning", parent=self.root)
        return True


def main():
    prepare_process("VBAAssets.VACall.Source")
    root = tk.Tk()
    CallApp(root)
    root.mainloop()
