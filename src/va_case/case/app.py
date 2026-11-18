"""VA Case の画面（一覧・その下のカード・検索・編集モード・終了処理・CSV）。

一覧で行を選ぶと、ウィンドウの下側のカードにその事件が出る。カードで直す（2026-11-10 班長決定。VA Filing・VA Receipt・
VA Call と同じ形。それまでは別のウィンドウの入力欄で直していた）。直した値は、ほかの事件に移るとき・新しい事件・
書類を作るとき・編集を終えるとき・閉じるとき・最新を読み込むときに書き込み、直す前の値には Ctrl+Z で戻す（2026-11-12
班長決定。それまでは「書き込む」「入力を戻す」のボタンがあった）。
共有データの読み書きと ZIP の作成は裏で行い、画面は止めない（2026-11-09 班長決定）。書き込みは1件ずつ行い、編集モードは
書き込んだ後も続ける（同）。読み込み・編集モード・書き込み・キー操作などの仕組みは、4つのツールで共通（common/ui/shared_app.py）。
"""
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ..common.dates import display_lines as date_display   # 生年月日は何行か（1行の値は1つの日付と同じ）
from ..common.dates import normalize_date_text, normalize_dates_text, to_storage
from ..common.master import Table
from ..common.paths import portable
from ..common.ui import theme
from ..common.ui.undo import EditHistory
from ..common.ui.shared_app import SharedApp, open_path, prepare_process
from . import closing
from .closing_ui import ClosingUI
from . import courtdocs
from . import memo
from . import model as m
from . import settings
from .card import CARD_LAYOUT, CaseCard, row_values
from .dialogs import TITLE, HearingAckDialog, OfficeDialog, SendLetterDialog, SettingsDialog, center

# 一覧に出す列（2026-11-10 班長決定：主な11列に関係者を加えた12列。ほかの列はカードに出す。検索は全部の列で行う）。
# 同日 班長指示「リストの順番をカードの順番に揃える。リストに代理人を追加する」：代理人を加えた13列を、カードの並び
# （左の列から、上から順）に出す。カードの並び（CARD_LAYOUT）を変えたら、一覧の並びも合わせて変わる
LIST_COLUMNS = {"事件番号", "現況", "事件呼名", "受任区分", "事件区分", "担当区分", "依頼者氏名", "関係者", "相手方氏名", "代理人",
                "裁判所名", "裁判所事件番号", "事件名"}
DISPLAY_COLUMNS = [c for _, names in CARD_LAYOUT for c in names if c in LIST_COLUMNS]
assert len(DISPLAY_COLUMNS) == len(LIST_COLUMNS)
COLUMN_WIDTHS = {"事件番号": 64, "現況": 84, "事件呼名": 190, "依頼者氏名": 120, "相手方氏名": 120, "関係者": 140,
                 "代理人": 140, "受任区分": 80, "事件区分": 84, "担当区分": 64, "裁判所名": 140, "裁判所事件番号": 140,
                 "事件名": 160}


class CaseApp(ClosingUI, SharedApp):
    TITLE = TITLE
    ABOUT_LINE = "事件の情報を、事務所の共有フォルダで管理する"
    ICON_FILE = "VA_Case.ico"      # ウィンドウ・タスクバーのアイコン（assets。scripts\generate_icons.py）
    TOOL = m.TOOL
    SCHEMA = m.SCHEMA
    MASTER_FILE_NAME = m.MASTER_FILE_NAME
    BUSY_CLOSE_MESSAGE = ("書き込み中、または ZIP の作成中です。閉じると途中で止まります"
                          "（共有データは壊れません。作りかけの ZIP は残りません）。\nそれでも閉じますか？")
    DEFAULT_GEOMETRY = "1280x800"   # 下側のカードの分、高くする
    ROW_NAME = "事件"
    CSV_FILE_NAME = "事件"
    CSV_NOTE = "CSV には、依頼者の氏名・住所などがそのまま入っています。"
    CSV_IMPORT_NAME = "の事件"

    def __init__(self, root):
        self.problems = set()       # 確かめで問題のあった事件番号（赤字で出す）
        self.current = None         # カードに出している事件の事件番号
        self.drafts = {}            # 事件番号 → カードで直した値（書き込み中のもの・書き込めなかったもの。この画面の中だけ）
        self.created = set()        # この画面で「新しい事件」で足した事件番号（番号を直すときの知らせを省く）
        self.writing_cases = set()  # いま書き込んでいる（待ち行列を含む）事件番号
        super().__init__(root, settings)

    def empty_tables(self):
        return m.empty_tables()

    # 事件番号の列がない CSV は、すべての行を挙げる代わりに、列がないと知らせて止める（2026-11-11 班長決定）。
    # VA Filing・VA Receipt・VA Call の番号は、空なら取り込むときに付けるので、要らない
    CSV_REQUIRED = ("事件番号",)

    def csv_columns(self):
        return m.CASE_COLUMNS

    def csv_date_columns(self):
        return m.DATE_COLUMNS

    CSV_MULTI_DATE_COLUMNS = m.MULTI_DATE_COLUMNS   # 生年月日は、1行ずつ日付として読む

    def csv_add(self, tables, rows):
        return m.add_imported(tables, rows)

    def csv_rows(self):
        """検索しているときは、検索の結果だけを出力するかを尋ねる。"""
        rows = self.rows
        label = self.narrowed_label()
        if label:
            ans = messagebox.askyesnocancel(TITLE, f"{label}だけを出力しますか？\n「いいえ」を選ぶと、すべての事件を出力します。",
                                            parent=self.root)
            if ans is None:
                return None
            if ans:   # 一覧に出している事件（検索とフィルタに当てはまる事件）
                shown = {self._cells[k]["事件番号"] for k in self.tree.get_children() if k in self._cells}
                rows = [r for r in rows if r[m.COL["事件番号"]] in shown]
        return rows

    def on_data(self, data):
        self.norm_cache = {}
        self.card.set_choices(data.tables)

    def after_first_load(self):
        items = self.tree.get_children()
        if items and not self.tree.selection():
            self._select_item(items[0])

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
        f.add_command(label="閉じる", command=self.on_close)
        f.add_separator()
        f.add_command(label="この PC の設定…", command=self.open_settings)
        f.add_command(label="事務所の設定…", command=self.open_office)
        bar.add_cascade(label="ファイル", menu=f)
        c = tk.Menu(bar, tearoff=False)
        # 「事件番号の確認」（現行の CheckNumbers）は、2026-11-11 になくした（班長決定）。カードの書き込み・新しい事件・
        # CSV の取り込みのどれも、重なる・空の番号を書く前に止めるので、共有データの中では起きないため
        c.add_command(label="データフォルダの確認", command=self.check_folders)
        bar.add_cascade(label="確認", menu=c)
        d = tk.Menu(bar, tearoff=False)
        d.add_command(label="事件メモ", command=self.make_memo)
        d.add_command(label="期日請書…", command=self.make_hearing_ack)
        d.add_command(label="送付書…", command=self.make_send_letter)
        bar.add_cascade(label="書類", menu=d)
        self.build_help_menu(bar)
        self.root.configure(menu=bar)
        self.root.bind("<F5>", lambda e: self.reload_latest())

    def _build_toolbar(self):
        rb = self.build_ribbon()
        # 「開く・直す」はなくした（選んだ事件は、いつも下側のカードに出るため。2026-11-10 班長決定）
        g = rb.group("事件")
        self.edit_only(g.large("新しい事件…", self.new_case,
                               tip="新しい事件を足します。新規の依頼人か、選んでいる事件と同じ依頼人かを尋ねて事件番号を付け、"
                                   "カードに出します。同じ依頼人なら、依頼者・相手方などの欄を写します。"
                                   "いま出している事件で直した値がまだ書き込まれていなければ、先に書き込みます。編集モードで使えます。"))
        # ［コピー］（2026-11-14 班長指示。4つのツールで同じ。閲覧モードでも使える）
        g.small("コピー", self.copy_selected_rows,
                tip="選んでいる事件の、一覧に出している値を、タブ区切りでコピーします（見出しは付けません）。Excel などに"
                    "貼り付けられます。何件かを選んでいれば、その全部をコピーします。")
        self.edit_only(g.small("削除", self.delete_selected,
                               tip="選んでいる事件を削除します（確かめてから）。データフォルダは消しません。編集モードで使えます。"))
        # 書類は、それまでの「書類を作る」のメニューを、3つのボタンにした（2026-11-13 リボンにしたとき）
        g = rb.group("書類")
        g.small("事件メモ", self.make_memo,
                tip="選んでいる事件の事件メモ（PDF）を作り、データフォルダに保存して開きます。閲覧モードでも作れます。")
        g.small("期日請書…", self.make_hearing_ack,
                tip="期日の名前・日時などを入れて、期日請書（PDF）を作り、データフォルダに保存して開きます。")
        g.small("送付書…", self.make_send_letter,
                tip="送る書類と枚数などを入れて、直送の送付書と受領書（PDF）を作り、データフォルダに保存して開きます。")
        self.build_search_group(rb)

    def _build_body(self):
        outer = ttk.Frame(self.root, padding=(8, 6, 8, 0))
        outer.pack(fill="x", side="bottom")     # カードを先に下へ置き、残りを一覧にする
        holder = self.mode_card(outer, padding=(10, 6))
        self.card = CaseCard(holder, on_change=self._mark_dirty, on_open=self.open_from_card, rows=lambda: self.rows)
        self.card.pack(fill="x")
        # Ctrl+Z・Ctrl+Y（2026-11-12 班長決定。カードの欄と一覧で）
        self.history = EditHistory(self.root, lambda: (self.card.values(), None), self._restore_card,
                                   focus=lambda name: self.card.widgets[name].focus_set())
        for name, w in self.card.widgets.items():
            self.history.watch(w, name)
        self.build_list(m.CASE_COLUMNS, DISPLAY_COLUMNS, COLUMN_WIDTHS)
        self.history.bind_keys(self.tree)
        for kind, fg in theme.STATUS_FG.items():
            self.tree.tag_configure(kind, foreground=fg)
        self.tree.tag_configure("problem", foreground=theme.PROBLEM_FG)
        self.tree.tag_configure("draft", foreground=theme.ACCENT)    # 書き込み中・書き込めなかった変更がある
        self.tree.bind("<Double-1>", self.on_double_click)
        # Enter で、カードの最初の欄へ（ttk の既定の、行を開く・閉じる動きはさせない）
        self.tree.bind("<Return>", lambda e: (self.flush_selected(), self.card.focus_first(), "break")[2])

    # ------------------------------------------------------------ 一覧

    @property
    def rows(self):
        return self.data.tables[m.CASE].rows if self.data else []

    def _tags(self, row):
        number = row[m.COL["事件番号"]]
        if number in self.drafts:
            return ["draft"]
        tags = []
        kind = m.status_kind(row)
        if kind:
            tags.append(kind)
        if number in self.problems:
            tags.append("problem")
        return tags

    def refresh(self):
        self.flush_selected()
        selected = self.current or self.selected_number()
        self.tree.delete(*self.tree.get_children())
        shown = 0
        self.begin_wrapped_list()     # すべてのセルを、列の幅で折り返して出す（2026-11-09 班長指示）
        # 一覧の行 → 事件番号（と、その逆）。一覧の「事件番号」の字は、カードで直している番号のことがあるため、行の
        # 事件番号は、ここで覚えたもので引く（2026-11-13。直している値を一覧に出すようにしたため）
        self._number_by_iid, self._iid_by_number = {}, {}
        for row in self.rows:
            if not self.query.matches(row, self._norm(row)):
                continue
            values = self._list_values(row)
            if not self.passes_filter(m.CASE_COLUMNS, values):
                continue
            iid, number = f"r{shown}", row[m.COL["事件番号"]]
            self.insert_wrapped(iid, m.CASE_COLUMNS, values, self._tags(row))
            self._number_by_iid[iid] = number
            self._iid_by_number.setdefault(number, iid)
            shown += 1
        total = len(self.rows)
        label = self.narrowed_label()
        self.count_label.configure(text=f"{label} {shown} 件（全 {total} 件）" if label else f"{total} 件")
        self._update_mode()
        if selected and self.select_number(selected):
            if selected not in self.drafts:
                self._show(selected)     # 読み込み直した値を出す（入れかけた値があれば、それを残す）
        elif selected:
            self.current = None
            self._show(None)

    def _list_values(self, row):
        """一覧に出す値（列の順。日付は和暦）。カードで直していて、まだ書き込んでいない値（書き込み中・書き込めなかった
        値も）があれば、その値を出す（字は青。2026-11-13 班長決定「A 青字のまま一覧に出す」。それまでは、書き込むまで
        前の値のままで、青字だけで示していた）。"""
        draft = self.drafts.get(row[m.COL["事件番号"]]) or {}
        return [draft[c] if c in draft else date_display(v) if c in m.DATE_COLUMNS else v
                for c, v in zip(m.CASE_COLUMNS, row)]

    def number_of(self, iid):
        """一覧の行（最初の行の iid）の事件番号。"""
        return getattr(self, "_number_by_iid", {}).get(iid) if iid else None

    def selected_number(self):
        return self.number_of(self.selected_key())

    def _iid_of(self, number):
        iid = getattr(self, "_iid_by_number", {}).get(number)
        return iid if iid is not None and self.tree.exists(iid) else None

    def select_number(self, number):
        iid = self._iid_of(number)
        if iid is None:
            return False
        self._select_item(iid)
        return True

    def select_key(self, key):
        if self.select_number(key):
            self._on_select()

    def row_by_number(self, number):
        for r in self.rows:
            if r[m.COL["事件番号"]] == number:
                return r
        return None

    # ------------------------------------------------------------ カード

    # 矢印キーで行を動かしている間は、カードの書き換えをあとに回す（list_view.py の _on_select。2026-11-10 班長指示。
    # カードの書き換えに1回約0.06秒かかり、書き換えなければ1行動くのが約0.11秒から約0.05秒になった）

    def _show_selected(self):
        number = self.selected_number()
        if number is None or number == self.current:
            return
        if not self.commit_pending():       # 確かめで止めたときは、カードの事件を選び直す（移らない）
            if self.current is not None:
                self.select_number(self.current)
            return
        self._keep_draft()
        self._show(number)

    def _show(self, number):
        row = self.row_by_number(number) if number is not None and self.data else None
        if row is None:
            self.current = None
            self.card.put(None, {})
        else:
            self.current = number
            self.card.put(number, self.drafts.get(number) or row_values(row))
        if self.current is None:
            self.history.clear()
        else:
            self.history.reset()
        self._update_card_state()

    def _restore_card(self, state):
        """Ctrl+Z・Ctrl+Y で、カードの値を入れ替える。"""
        self.card.set_values(state[0])
        self._mark_dirty()

    def _keep_draft(self):
        """直した値を、事件ごとに覚える（書き込みが終わるまで。書き込めなかったときも残す）。"""
        if self.current is None or self.data is None:
            return
        row = self.row_by_number(self.current)
        if row is None:
            return
        v = self.card.values()
        if v != row_values(row):
            self.drafts[self.current] = v
        else:
            self.drafts.pop(self.current, None)

    def _mark_dirty(self):
        if self.current is None:
            return
        self.history.changed()
        before = self.current in self.drafts
        self._keep_draft()
        if (self.current in self.drafts) != before:
            self._update_card_state()
        else:                               # 直している値を、一覧にも出す（2026-11-13 班長決定「A 青字のまま一覧に出す」）
            iid, row = self._iid_of(self.current), self.row_by_number(self.current)
            if iid is not None and row is not None:
                self.update_list_row(iid, m.CASE_COLUMNS, self._list_values(row))

    def _update_card_state(self):
        """いまの事件の行の色（書き込んでいない値があれば青字）を合わせる。カードの下の状態の文（閲覧モードです・
        直したら移るときに書き込みます）は、2026-11-12 班長指摘「この行は不要ではないか？」でなくした（モードは枠の色と
        「編集を始める」のボタンで分かる。書き込むときと Ctrl+Z はマニュアルに書く）。"""
        number = self.current
        if number is not None:
            iid = self._iid_of(number)
            row = self.row_by_number(number)
            if iid is not None and row is not None:
                self.update_list_row(iid, m.CASE_COLUMNS, self._list_values(row), self._tags(row))
                super()._update_mode()   # 縞を付け直す

    def _update_mode(self):
        super()._update_mode()
        if hasattr(self, "card"):
            self.card.set_editable(self.editing)     # 編集モードに入った・抜けたら、カードの直せるかを合わせる
            self._update_card_state()

    def open_from_card(self, name):
        """カードの「開く」（データフォルダ・TeamsURL）。書き込んだ値で開く。"""
        self.flush_selected()
        row = self.row_by_number(self.current) if self.current else None
        if row is None or not row[m.COL[name]]:
            return
        if name == "データフォルダ":
            self.open_data_folder(row)
        else:
            try:
                open_path(row[m.COL["TeamsURL"]])
            except OSError as e:
                messagebox.showwarning(TITLE, f"URL を開けませんでした。\n\n{self.error_text(e)}", parent=self.root)

    # ------------------------------------------------------------ 事件の追加・書き込み・削除

    def new_case(self, base_number=None):
        """新しい事件を足す（現行と同じく、新規の依頼人か同じ依頼人かを尋ねて番号を付け、すぐに空の事件を書き込む。
        VA Call の「新しいメモ」と同じ）。続けてカードで事件呼名などを入れてもらう（ほかの事件に移るときに書き込む）。
        同じ依頼人のときは、元の事件の依頼者・関係者・相手方・代理人の欄を写す（2026-11-12 班長決定。現行は番号だけ）。"""
        if self.data is None or not self._require_edit(busy_ok=True):
            return
        self.flush_selected()
        if not self.commit_pending():       # いまの事件で直した値を、先に書き込む（待ち行列に入る）
            return
        ans = messagebox.askyesnocancel(TITLE, "追加するのは、新規の依頼人ですか？\n\n"
                                               "「いいえ」を選ぶと、選んでいる事件と同じ依頼人の事件として番号を付け、"
                                               "依頼者・関係者・相手方・代理人の欄を写します。",
                                        parent=self.root)
        if ans is None:
            return
        base_number = None if ans else (base_number or self.current)
        if not ans and (base_number is None or self.row_by_number(base_number) is None):
            messagebox.showinfo(TITLE, "同じ依頼人の事件を足すときは、先に一覧でその依頼人の事件を選んでください。",
                                parent=self.root)
            return
        holder = {}

        def transform(t):
            base = None
            if base_number is not None:
                base = next((r for r in t[m.CASE].rows if r[m.COL["事件番号"]] == base_number), None)
                if base is None:
                    raise ValueError(f"事件番号 {base_number} の事件が、共有データにありません。")
            number = str(m.new_case_number(t[m.CASE].rows, base))   # 書き込む直前の最新の共有データで番号を付ける
            holder["number"] = number
            self.created.add(number)
            return m.upsert_case(t, m.blank_row(number, base))   # 同じ依頼人なら、依頼者・相手方などを写す

        def after():
            number = holder.get("number")
            if number:
                self.select_key(number)
                self.card.focus_first()
        self.write(transform, "新しい事件", after)

    def commit_pending(self):
        """カードで直した値があれば、書き込みを始める（ほかの事件に移るとき・新しい事件・書類を作るとき・編集を終える
        とき・閉じるとき・最新を読み込むとき。2026-11-12 班長決定）。確かめで止めたら False（その事件に留まる）。"""
        self.flush_selected()
        if self.current is None or not self.editing or self.data is None:
            return True
        row = self.row_by_number(self.current)
        if row is None:
            return True
        values = self.card.values()
        if values == row_values(row) or (self.current in self.writing_cases and self.drafts.get(self.current) == values):
            return True     # 直していない（か、いま書き込んでいる値のまま）
        return self.save_case()

    def save_case(self):
        """カードの値を書き込む（確かめてから、待ち行列に入れる）。→ True：書き込みを始めた・書くものがない。
        False：確かめで止めた（知らせは済み）。"""
        if self.current is None or not self._require_edit(busy_ok=True):
            return False
        number = self.current
        old = self.row_by_number(number)
        if old is None:
            messagebox.showwarning(TITLE, f"事件 {number} は、共有データにありません（ほかの PC で消されたようです）。",
                                   parent=self.root)
            return False
        values = self.card.values()
        row = list(old)
        errors = []
        for name in m.CASE_COLUMNS:
            v = values[name]
            if name in m.DATE_COLUMNS:
                try:
                    v = (normalize_dates_text if name in m.MULTI_DATE_COLUMNS else normalize_date_text)(v)
                except ValueError:
                    pass       # 読めない日付は、下の check_row が知らせる（ここでも知らせると、同じ知らせが2つ出ていた）
            if name == "データフォルダ" and not closing.is_archived(v):
                # 貼り付けた絶対パスも、基点の下なら基点からの相対で書く（2026-11-12 班長決定。PC ごとに共有フォルダの
                # 場所が違う事務所・Mac でも使えるように）
                v = portable(v, self.cfg.data_root)
            row[m.COL[name]] = v
        # 事件番号はカードで直せる（2026-11-11 班長指示。番号の重なりを直すとき・西暦を入れた番号にするときなど）
        new_number = row[m.COL["事件番号"]].strip()
        if new_number.isdigit():
            new_number = str(int(new_number))     # 頭の 0 は付けない（数として並べるため）
        row[m.COL["事件番号"]] = new_number
        errors += m.check_row(row, None)
        if errors:
            messagebox.showwarning(TITLE, f"事件 {number} を書き込めません。直してください。\n\n" + "\n".join(errors),
                                   parent=self.root)
            return False
        if new_number != number:
            clash = [r for r in self.rows if r[m.COL["事件番号"]] == new_number]
            if clash:
                messagebox.showwarning(TITLE, f"事件番号 {new_number} は、すでにあります（{clash[0][m.COL['事件呼名']]}）。"
                                              "ほかの番号にしてください。", parent=self.root)
                return False
            if number not in self.created and not messagebox.askyesno(
                    TITLE, f"事件番号を {number} から {new_number} に変えます。\n\nよろしいですか？",
                           parent=self.root):
                return False
        if not row[m.COL["事件呼名"]]:
            if not messagebox.askyesno(TITLE, f"事件 {number} の事件呼名が空です。このまま書き込みますか？",
                                       parent=self.root):
                return False
        old_status = old[m.COL["現況"]]
        new_status = row[m.COL["現況"]]
        if new_status == m.STATUS_CLOSED and old_status != new_status and not row[m.COL["終了年月日"]]:
            # 現行と同じ：終了にしたときに、終了年月日に今日の日付を入れるか確かめる
            if messagebox.askyesno(TITLE, "終了年月日に今日の日付を入力します。\nよろしいですか？", parent=self.root):
                row[m.COL["終了年月日"]] = to_storage(date.today())
        if row == list(old):
            self.drafts.pop(number, None)
            return True

        def after():
            self.writing_cases.discard(number)
            self.drafts.pop(number, None)
            if new_number != number and number in self.created:
                self.created.add(new_number)
            if self.current in (number, new_number):    # まだこの事件にいる（編集を終える・閉じるときなど）
                if new_number != number:
                    self.select_number(new_number)
                self._show(new_number)
            else:
                self._update_row_tags(number if new_number == number else new_number)
            self._after_status_change(old_status, row)

        def on_error(e):
            self.writing_cases.discard(number)
            self._update_card_state()
            self.show_write_error(e)
        self.drafts[number] = values      # 書き込みが終わるまでは、直した値を残す（書き込めなかったときも残す）
        self.writing_cases.add(number)
        label = f"事件 {number}" if new_number == number else f"事件 {number}（番号を {new_number} に）"
        self.write(lambda t: m.upsert_case(t, row, old_number=number), label, after, on_error=on_error)
        return True

    def _update_row_tags(self, number):
        iid = self._iid_of(number)
        row = self.row_by_number(number)
        if iid is not None and row is not None:
            self.set_row_tags(iid, self._tags(row))
            SharedApp._update_mode(self)   # 縞を付け直す

    def delete_selected(self):
        self.flush_selected()
        number = self.current
        if not number or not self._require_edit():
            return
        row = self.row_by_number(number)
        if row is None:
            return
        if not messagebox.askyesno(TITLE, f"事件 {number}「{row[m.COL['事件呼名']]}」を消します。\n"
                                          "データフォルダは消しません。よろしいですか？", icon="warning",
                                   parent=self.root):
            return
        items = list(self.tree.get_children())
        iid = self._iid_of(number)
        i = items.index(iid) if iid in items else -1
        nxt = items[i + 1] if 0 <= i < len(items) - 1 else (items[i - 1] if i > 0 else None)
        nxt_number = self.number_of(nxt)
        self.drafts.pop(number, None)

        def after():
            if nxt_number:
                self.select_key(nxt_number)
        self.current = None
        self.write(lambda t: m.delete_case(t, number), f"事件 {number} の削除", after)

    def on_double_click(self, event):
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        iid = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if not iid or not col:
            return
        iid = self._list_row(iid)  # 事件の2行目以降をダブルクリックしたときも、その事件
        self._select_item(iid)
        self._on_select()
        self.flush_selected()
        names = self._shown_columns(self.tree)
        column = names[int(col[1:]) - 1]
        if column == "事件番号" and self.editing:
            self.new_case(base_number=self.number_of(self._list_row(iid)))   # 現行と同じく、事件番号のダブルクリックで事件を足す
        else:
            self.card.focus_first()
        return "break"             # ttk の既定の、行を開く・閉じる動きをさせない

    def can_close(self):
        """直した値を書き込んだ後にも、書き込めなかった事件が残っていれば確かめる。"""
        self._keep_draft()
        if self.drafts:
            return messagebox.askyesno(TITLE, f"書き込めなかった変更のある事件が {len(self.drafts)} 件あります（事件番号 "
                                              + "・".join(sorted(self.drafts, key=lambda n: int(n) if n.isdigit() else 0))
                                              + "）。\n書き込まずに閉じますか？", icon="warning", parent=self.root)
        return True

    def open_data_folder(self, row):
        value = row[m.COL["データフォルダ"]]
        if closing.is_archived(value):
            # 終了した事件のデータは、VA Case からは開かない（2026-11-09 班長決定。開けるようにしておくと、保管庫を
            # 常に開いておく運用につながるため）。保管庫の中の場所だけを示し、エクスプローラーで探してもらう
            messagebox.showinfo(TITLE, "この事件は終了処理で ZIP にしてあります。VA Case からは開きません。\n"
                                       "保管庫を開いて、エクスプローラーで次の場所を探してください"
                                       "（保管庫へ移す前なら、移送待ちの同じ場所にあります）。\n\n"
                                       f"{closing.archived_location(value)}", parent=self.root)
            return
        path = m.resolve_folder(value, self.cfg.data_root)
        if path is None or not path.exists():
            messagebox.showwarning(TITLE, f"データフォルダが見つかりません。\n{value}", parent=self.root)
            return
        try:
            open_path(path)
        except OSError as e:
            messagebox.showwarning(TITLE, f"開けませんでした。\n\n{self.error_text(e)}", parent=self.root)

    # ------------------------------------------------------------ 事件メモ

    def make_memo(self):
        """選んでいる事件の事件メモの PDF を作り、データフォルダに保存して開く（現行の sht12）。閲覧モードでも作れる。"""
        row = self._selected_row("事件メモ", self.make_memo)
        if row is None:
            return
        if not messagebox.askyesno(TITLE, f"{row[m.COL['事件呼名']]}の事件メモを作成しますか？\n"
                                          "作成したファイルは、当該事件のデータフォルダに保存されます。", parent=self.root):
            return
        try:
            data = memo.build_pdf(row, court=m.court_numbers(self.data.tables, row[m.COL["裁判所名"]]))
        except Exception as e:
            messagebox.showerror(TITLE, f"事件メモを作れませんでした。\n\n{self.error_text(e)}", parent=self.root)
            return
        self._save_document(row, data, memo.memo_file_name(row), "事件メモ")

    def _selected_row(self, what, retry):
        """書類を作る事件の行。書類は書き込んだ値で作るので、カードで直した値があれば、先に書き込み、書き込みが
        終わってから retry() でもう一度始める（2026-11-12 班長決定。それまでは「先に書き込む」と知らせて止めた）。"""
        self.flush_selected()
        if not self.commit_pending():
            return None
        if self.writing or self._write_queue:
            self.after_writes(retry)
            return None
        number = self.current
        row = self.row_by_number(number) if number else None
        if row is None:
            messagebox.showinfo(TITLE, f"事件番号が選択されていないため、{what}は作成できません。", parent=self.root)
        return row

    def _save_document(self, row, data, name, what):
        """書類の PDF を、事件のデータフォルダに保存して開く（なければ保存する場所を選んでもらう）。"""
        value = row[m.COL["データフォルダ"]]
        folder = None if closing.is_archived(value) else m.resolve_folder(value, self.cfg.data_root)
        if folder is not None and folder.is_dir():
            path = folder / name
            if path.exists() and not messagebox.askyesno(TITLE, f"今日の{what}がすでにあります。\n{path}\n\n"
                                                                "置き換えますか？", parent=self.root):
                return
        else:
            messagebox.showinfo(TITLE, "データフォルダが見つからないため、保存する場所を選んでください。", parent=self.root)
            chosen = filedialog.asksaveasfilename(parent=self.root, title=f"{what}を保存", defaultextension=".pdf",
                                                  initialfile=name, filetypes=[("PDF", "*.pdf")])
            if not chosen:
                return
            path = Path(chosen)
        try:
            path.write_bytes(data)
        except OSError as e:
            messagebox.showerror(TITLE, f"ファイルの保存に失敗しました。\n\n{self.error_text(e)}", parent=self.root)
            return
        self.work_label.configure(text=f"{what}を保存しました（{path.name}）")
        try:
            open_path(path)    # 既定の PDF の閲覧ソフトで開く。印刷はそこから行う
        except OSError:
            messagebox.showinfo(TITLE, f"保存しました。\n{path}", parent=self.root)

    def make_hearing_ack(self):
        row = self._selected_row("期日請書", self.make_hearing_ack)
        if row is None:
            return
        dlg = HearingAckDialog(self.root, row, courtdocs.lawyer_names(self.data.tables[m.CHOICES], row))
        self.root.wait_window(dlg)
        self._focus_table()
        if not dlg.result:
            return
        try:
            data = courtdocs.build_hearing_ack(row, dlg.result)
        except Exception as e:
            messagebox.showerror(TITLE, f"期日請書を作れませんでした。\n\n{self.error_text(e)}", parent=self.root)
            return
        self._save_document(row, data, courtdocs.file_name("期日請書", row), "期日請書")

    def make_send_letter(self):
        row = self._selected_row("送付書", self.make_send_letter)
        if row is None:
            return
        choices = self.data.tables[m.CHOICES]
        dlg = SendLetterDialog(self.root, row, courtdocs.lawyer_names(choices, row),
                               courtdocs.office_value(choices, courtdocs.OFFICE_TEL),
                               courtdocs.office_value(choices, courtdocs.OFFICE_FAX),
                               court_fax_of=lambda name: m.court_numbers(self.data.tables, name)[1])
        self.root.wait_window(dlg)
        self._focus_table()
        if not dlg.result:
            return
        try:
            data = courtdocs.build_send_letter(row, dlg.result)
        except Exception as e:
            messagebox.showerror(TITLE, f"送付書を作れませんでした。\n\n{self.error_text(e)}", parent=self.root)
            return
        self._save_document(row, data, courtdocs.file_name("送付書", row), "送付書")
    # ------------------------------------------------------------ 確認・設定

    def _show_list(self, title, lines):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.transient(self.root)
        t = tk.Text(win, width=90, height=20, wrap="char", font=theme.field_font(win))
        t.insert("1.0", "\n".join(lines))
        t.configure(state="disabled")
        t.pack(fill="both", expand=True, padx=10, pady=10)
        ttk.Button(win, text="閉じる", command=win.destroy).pack(anchor="e", padx=10, pady=(0, 10))
        center(win, self.root)

    def check_folders(self):
        if self.data is None:
            return
        rows = [r for r in self.rows if not closing.is_archived(r[m.COL["データフォルダ"]])]
        self.work_label.configure(text="データフォルダを確かめています…")

        def _done(probs):
            self.problems = {p.number for p in probs}
            self.refresh()
            self.work_label.configure(text="データフォルダの確認を終えました")
            if not probs:
                messagebox.showinfo(TITLE, "データフォルダのチェックを完了しました。見つからないものはありません。",
                                    parent=self.root)
            else:
                self._show_list("データフォルダの確認", [f"事件番号 {p.number}：{p.message}" for p in probs])
        self.bg.run(lambda: m.check_folders(rows, lambda v: m.resolve_folder(v, self.cfg.data_root)), _done,
                    lambda e: messagebox.showerror(TITLE, "データフォルダを確かめられませんでした。\n\n"
                                                   + self.error_text(e, record=False), parent=self.root))

    def open_settings(self):
        dlg = SettingsDialog(self.root, settings.CaseConfig(**vars(self.cfg)))
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
        return True

    def open_office(self):
        if self.data is None:
            return
        result = self.run_office_dialog(lambda editable: OfficeDialog(self.root, self.data.tables, editable=editable))
        if not result:
            return
        choice_rows, rules, courts = result

        def transform(t):
            new = {k: v.copy() for k, v in t.items()}
            new[m.CHOICES] = Table(list(m.CHOICE_COLUMNS), choice_rows)
            new[m.FOLDER_RULES] = Table(list(m.FOLDER_RULE_COLUMNS), rules)
            new[m.COURTS] = Table(list(m.COURT_COLUMNS), courts)
            return new
        self.write(transform, "事務所の設定")


def main():
    prepare_process("VBAAssets.VACase.Source")
    root = tk.Tk()
    CaseApp(root)
    root.mainloop()
