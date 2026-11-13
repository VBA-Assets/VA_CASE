"""VA Case の設定・書類などの画面（事件のカードは card.py。2026-11-10 に、事件の入力欄〔別のウィンドウ〕をカードに替えた）。"""
import tkinter as tk
from tkinter import messagebox, ttk

from ..common.ui import theme
from ..common.ui.dialogs import SettingsDialog as BaseSettingsDialog
from ..common.ui.dialogs import center  # noqa: F401（app から使う）
from ..common.ui.dialogs import TableEditor, office_buttons, wrapping_label
from . import model as m

TITLE = "VA Case"

class SettingsDialog(BaseSettingsDialog):
    """この PC の設定（共有データ・バックアップ・事務所のフォルダの場所・移送待ち）。"""

    APP_TITLE = TITLE
    FIELDS = [
        ("master_path", "共有データのファイル", "file",
         "事務所の共有フォルダに置く VA_Case.json。みなが同じファイルを指すようにします。"),
        ("backup_folder", "バックアップのフォルダ", "dir", "その日の最初に読み込んだときに写しを置きます。空ならバックアップしません。"),
        ("data_root", "事務所のフォルダの場所", "dir",
         "事務所で共有しているフォルダ（事件のフォルダ・スキャンのフォルダなどをまとめて置いているフォルダ）が、この PC で"
         "見える場所。ここに入れておくと、その中のフォルダは、ここからの相対で記録するので、PC ごとに場所が違っても"
         "（Mac でも）使えます。どの PC でも同じ場所（同じドライブ名）なら、空でかまいません。"),
        ("outbox", "移送待ちの場所", "dir", "終了事件の ZIP を置くフォルダ（日常の共有フォルダの中）。"),
    ]
    BOOLS = [("zip_compress", "終了処理の ZIP を圧縮する（既定は無圧縮。スキャンの PDF などはほとんど縮まないため）")]
    FILETYPES = {"master_path": [("VA Case の共有データ", "*.json"), ("すべて", "*.*")]}


class OfficeDialog(tk.Toplevel):
    """事務所の設定（選択肢・フォルダ規則・事務所・裁判所）。共有データに入るので、編集モードのときだけ直せる。"""

    def __init__(self, parent, tables, *, editable):
        super().__init__(parent)
        self.withdraw()
        self.title("事務所の設定（選択肢・フォルダ規則）")
        self.transient(parent)
        self.result = None
        self.editable = editable
        choices = tables[m.CHOICES]
        self.rules = [list(r) for r in tables[m.FOLDER_RULES].rows]
        font = theme.field_font(self)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=10)
        page = ttk.Frame(nb, padding=8)
        nb.add(page, text="選択肢")
        wrapping_label(page, "1行に1つずつ入れます。並べた順に、入力欄の選択肢に出ます。「担当区分の詳細」には、"
                             "同じ行の担当区分の弁護士の氏名を入れます（期日請書・送付書の弁護士名の既定になります。"
                             "2人以上のときは「・」で区切ります。例：佐藤一郎・田中二郎）。", width=760).grid(
            row=0, column=0, columnspan=6, sticky="we", pady=(0, 6))
        self.texts = {}
        state = "normal" if editable else "disabled"
        columns = list(m.CHOICE_ITEMS) + ["担当区分の詳細"]
        for ci, item in enumerate(columns):
            ttk.Label(page, text=item).grid(row=1, column=ci, sticky="w")
            t = tk.Text(page, width=18, height=18, font=font, wrap="none", undo=True)
            if item == "担当区分の詳細":
                lines = [r[2] for r in choices.rows if r[0] == "担当区分"]
            else:
                lines = [r[1] for r in choices.rows if r[0] == item]
            t.insert("1.0", "\n".join(lines))
            t.configure(state=state)
            theme.tab_stop(t, not editable)
            t.grid(row=2, column=ci, sticky="nsew", padx=(0, 6))
            self.texts[item] = t

        from .courtdocs import OFFICE_ITEMS
        page3 = ttk.Frame(nb, padding=8)
        self.office_vars = {}
        for i, item in enumerate(OFFICE_ITEMS):
            ttk.Label(page3, text=item).grid(row=i, column=0, sticky="e", padx=(0, 6), pady=3)
            vals = m.choice_values(choices, item)
            v = tk.StringVar(value=vals[0] if vals else "")
            e = ttk.Entry(page3, textvariable=v, width=30)
            if not editable:
                e.configure(state="readonly")
            e.grid(row=i, column=1, sticky="w", pady=3)
            self.office_vars[item] = v
        ttk.Label(page3, text="送付書に書きます。", style="Note.TLabel").grid(row=len(OFFICE_ITEMS), column=1, sticky="w")

        page2 = ttk.Frame(nb, padding=8)
        nb.add(page2, text="フォルダ規則")
        nb.add(page3, text="事務所")
        # 裁判所の電話番号・FAX番号（2026-11-11 班長決定。事件メモの【ＴＥＬ】【ＦＡＸ】と、送付書の裁判所の FAX 番号に使う）
        page4 = ttk.Frame(nb, padding=8)
        nb.add(page4, text="裁判所")
        wrapping_label(page4, "裁判所ごとに、電話番号と FAX 番号を入れます。事件の「裁判所名」がここの裁判所名と同じとき"
                              "（裁判所名が何行かあるときは、最後の行）、事件メモの【ＴＥＬ】【ＦＡＸ】と、送付書の裁判所の FAX 番号に"
                              "使います。裁判所名は、事件の欄と同じ書き方で入れます（空白の違いは問いません）。例：東京地方裁判所民事第1部",
                       width=760).pack(fill="x", pady=(0, 6))
        courts = tables[m.COURTS].rows if m.COURTS in tables else []
        self.courts = TableEditor(page4, m.COURT_COLUMNS, courts, editable=editable, widths=[340, 160, 160],
                                  title="裁判所", height=12)
        self.courts.pack(fill="both", expand=True)
        wrapping_label(page2, "現況を「C:終了」「B:精算管理」にしたときに、データフォルダの ZIP を置く場所を、"
                              "現況・受任区分・事件区分ごとに決めます。場所は保管庫の中の相対パスで書き、"
                              "yyyy は終了年（2017年以前は -2017）に置き換わります。例：個人一般\\yyyy",
                       width=760).pack(fill="x", pady=(0, 6))
        self.tree = ttk.Treeview(page2, columns=m.FOLDER_RULE_COLUMNS, show="headings", height=12)
        for c, w in zip(m.FOLDER_RULE_COLUMNS, (110, 110, 110, 110, 300)):
            self.tree.heading(c, text=c)
            self.tree.column(c, width=theme.px(self, w), stretch=(c == "フォルダ"))
        self.tree.pack(fill="both", expand=True)
        self._fill_rules()
        rb = ttk.Frame(page2)
        rb.pack(fill="x", pady=(6, 0))
        self.choices_tables = tables
        for text, cmd in (("足す", self._add_rule), ("直す", self._edit_rule), ("消す", self._del_rule)):
            b = ttk.Button(rb, text=text, style="Small.TButton", command=cmd)
            b.pack(side="left", padx=(0, 6))
            if not editable:
                b.state(["disabled"])
        self.tree.bind("<Double-1>", lambda e: self._edit_rule())

        office_buttons(self, editable, self._ok)
        center(self, parent)
        self.deiconify()   # 本体を止めない（開いたまま本体の「編集を始める」を押せる。2026-11-11）

    def _fill_rules(self):
        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(self.rules):
            self.tree.insert("", "end", iid=str(i), values=r)

    def _rule_dialog(self, values):
        win = tk.Toplevel(self)
        win.title("フォルダ規則")
        win.transient(self)
        result = {}
        choices = self.choices_tables[m.CHOICES]
        items = {"現況": "現況区分", "受任区分": "受任区分", "事件区分": "事件区分", "担当区分": "担当区分"}
        ws = []
        for i, c in enumerate(m.FOLDER_RULE_COLUMNS):
            ttk.Label(win, text=c).grid(row=i, column=0, sticky="e", padx=(10, 6), pady=4)
            if c in items:
                w = ttk.Combobox(win, values=[""] + m.choice_values(choices, items[c]), width=24)
            else:
                w = ttk.Entry(win, width=40)
            w.insert(0, values[i])
            w.grid(row=i, column=1, sticky="w", padx=(0, 10), pady=4)
            ws.append(w)

        def ok():
            result["v"] = [w.get().strip() for w in ws]
            win.destroy()
        bf = ttk.Frame(win, padding=10)
        bf.grid(row=len(ws), column=0, columnspan=2, sticky="e")
        ttk.Button(bf, text="キャンセル", command=win.destroy).pack(side="right")
        ttk.Button(bf, text="OK", style="Accent.TButton", command=ok).pack(side="right", padx=6)
        center(win, self)
        win.grab_set()
        self.wait_window(win)
        return result.get("v")

    def _selected(self):
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def _add_rule(self):
        v = self._rule_dialog([""] * len(m.FOLDER_RULE_COLUMNS))
        if v:
            self.rules.append(v)
            self._fill_rules()

    def _edit_rule(self):
        i = self._selected()
        if i is None or not self.editable:
            return
        v = self._rule_dialog(self.rules[i])
        if v:
            self.rules[i] = v
            self._fill_rules()

    def _del_rule(self):
        i = self._selected()
        if i is not None:
            del self.rules[i]
            self._fill_rules()

    def _ok(self):
        rows = []
        lines = {k: [x.strip() for x in t.get("1.0", "end-1c").split("\n")] for k, t in self.texts.items()}
        for item in m.CHOICE_ITEMS:
            vals = lines[item]
            for i, v in enumerate(vals):
                if not v:
                    continue
                detail = ""
                if item == "担当区分":
                    det = lines["担当区分の詳細"]
                    detail = det[i] if i < len(det) else ""
                rows.append([item, v, detail])
        for item, var in self.office_vars.items():
            if var.get().strip():
                rows.append([item, var.get().strip(), ""])
        courts = [r for r in self.courts.rows if any(str(v).strip() for v in r)]
        self.result = (rows, self.rules, courts)
        self.destroy()


class ProgressDialog(tk.Toplevel):
    """ZIP の作成・展開の進み具合。取り消しのボタンを押すと self.cancelled が真になる（作成は裏で続き、次のファイルで止まる）。"""

    def __init__(self, parent, title, message, cancel_question="ZIP の作成を取り消しますか？"):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.resizable(False, False)
        self.cancelled = False
        self.cancel_question = cancel_question
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        f = ttk.Frame(self, padding=14)
        f.pack(fill="both", expand=True)
        wrapping_label(f, message, width=460, style="TLabel").pack(fill="x")
        self.bar = ttk.Progressbar(f, length=theme.px(self, 460), maximum=1000)
        self.bar.pack(pady=(10, 4))
        self.label = ttk.Label(f, text="", style="Note.TLabel", width=70)
        self.label.pack(anchor="w")
        self.button = ttk.Button(f, text="取り消す", command=self._cancel)
        self.button.pack(anchor="e", pady=(8, 0))
        center(self, parent)

    def update_progress(self, done, total, name):
        self.bar["value"] = 1000 * done / total if total else 1000
        mb = 1024 * 1024
        self.label.configure(text=f"{done / mb:,.1f} / {total / mb:,.1f} MB　{name}")

    def _cancel(self):
        if not self.cancelled and messagebox.askyesno(TITLE, self.cancel_question, parent=self):
            self.cancelled = True
            self.label.configure(text="取り消しています…")
            self.button.state(["disabled"])


class HearingAckDialog(tk.Toplevel):
    """期日請書の入力欄（裁判所・期日の名前・日時・弁護士名）。OK で self.result に courtdocs.HearingInfo が入る。"""

    def __init__(self, parent, row, lawyers):
        from ..common.dates import format_datetime_long, parse_datetime
        from . import courtdocs
        super().__init__(parent)
        self.withdraw()
        self.title(f"期日請書　{row[m.COL['事件呼名']]}")
        self.transient(parent)
        self.resizable(False, False)
        self.result = None
        self._parse, self._format, self._cd = parse_datetime, format_datetime_long, courtdocs
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text=courtdocs.case_title(row) or "（裁判所事件番号・事件名が入っていません）",
                  style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        # 宛先の裁判所（送付書の画面と合わせる。2026-11-11 班長指示「期日請書の作成フォームも合わせる」。それまでは欄がなく、
        # 事件の裁判所名の最後の行をそのまま書いていた）
        ttk.Label(f, text="裁判所").grid(row=1, column=0, sticky="e", padx=(0, 6), pady=3)
        self.court = tk.StringVar(value=courtdocs.last_line(row[m.COL["裁判所名"]]))
        ttk.Entry(f, textvariable=self.court, width=36).grid(row=1, column=1, sticky="w", pady=3)
        ttk.Label(f, text="期日の名前").grid(row=2, column=0, sticky="e", padx=(0, 6), pady=3)
        self.kind = ttk.Combobox(f, values=courtdocs.HEARING_KINDS, width=34)
        self.kind.set(courtdocs.HEARING_KINDS[0])
        self.kind.grid(row=2, column=1, sticky="w", pady=3)
        ttk.Label(f, text="日時").grid(row=3, column=0, sticky="e", padx=(0, 6), pady=3)
        self.when = ttk.Entry(f, width=36)
        self.when.grid(row=3, column=1, sticky="w", pady=3)
        ttk.Label(f, text="例：R7.12.1 10:30（和暦・西暦のどちらでも。時刻は 24 時間で）", style="Note.TLabel").grid(
            row=4, column=1, sticky="w")
        ttk.Label(f, text="弁護士名").grid(row=5, column=0, sticky="e", padx=(0, 6), pady=3)
        self.lawyer = ttk.Combobox(f, values=lawyers, width=34)
        self.lawyer.set(lawyers[0] if lawyers else "")
        self.lawyer.grid(row=5, column=1, sticky="w", pady=3)
        if not lawyers:
            ttk.Label(f, text="事務所の設定の「担当区分の詳細」に氏名を入れておくと、ここに出ます。",
                      style="Note.TLabel").grid(row=6, column=1, sticky="w")
        b = ttk.Frame(self, padding=(12, 0, 12, 12))
        b.pack(fill="x")
        ttk.Button(b, text="キャンセル", command=self.destroy).pack(side="right")
        ttk.Button(b, text="PDF を作る", style="Accent.TButton", command=self._ok).pack(side="right", padx=6)
        self.bind("<Escape>", lambda e: self.destroy())
        center(self, parent)
        self.deiconify()
        self.grab_set()
        self.when.focus_set()

    def _ok(self):
        parsed = self._parse(self.when.get())
        if parsed is None or parsed[1] is None:
            messagebox.showwarning(TITLE, "期日の日時を、日付と時刻で入れてください（例：R7.12.1 10:30）。", parent=self)
            return
        if not self.kind.get().strip() or not self.lawyer.get().strip():
            messagebox.showwarning(TITLE, "期日の名前と弁護士名を入れてください。", parent=self)
            return
        self.result = self._cd.HearingInfo(self.kind.get().strip(), self._format(*parsed), self.lawyer.get().strip(),
                                           court=self.court.get().strip())
        self.destroy()


class SendLetterDialog(tk.Toplevel):
    """送付書の入力欄。OK で self.result に courtdocs.SendInfo が入る。"""

    ROWS = 8

    def __init__(self, parent, row, lawyers, office_tel, office_fax, court_fax_of=None):
        """court_fax_of(裁判所名)：事務所の設定の「裁判所」の FAX 番号（なければ ""）。"""
        from . import courtdocs
        super().__init__(parent)
        self.withdraw()
        self.title(f"送付書　{row[m.COL['事件呼名']]}")
        self.transient(parent)
        self.resizable(False, False)
        self.result = None
        self._cd = courtdocs
        self._office = (office_tel, office_fax)
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text=courtdocs.case_title(row) or "（裁判所事件番号・事件名が入っていません）",
                  style="Section.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        self.vars = {}

        def entry(r, label, key, value="", width=36):
            ttk.Label(f, text=label).grid(row=r, column=0, sticky="e", padx=(0, 6), pady=2)
            v = tk.StringVar(value=value)
            ttk.Entry(f, textvariable=v, width=width).grid(row=r, column=1, columnspan=2, sticky="w", pady=2)
            self.vars[key] = v
        # 宛先は、裁判所と相手方代理人を、それぞれ「名前・FAX 番号」の順にそろえて並べる（2026-11-11 班長指摘「裁判所名は
        # ないのに相手方代理人名があるのは統制が取れていない」。それまでは裁判所名の欄がなく、事件の裁判所名をそのまま書いていた）
        self._fax_of = court_fax_of or (lambda name: "")
        court = courtdocs.last_line(row[m.COL["裁判所名"]])
        entry(1, "裁判所", "court", court)
        entry(2, "裁判所の FAX 番号", "court_fax", self._fax_of(court))   # 事務所の設定の「裁判所」にあれば、それを入れておく
        entry(3, "相手方代理人", "agent", courtdocs.first_line(row[m.COL["代理人"]]).replace("弁護士", "").strip())
        entry(4, "相手方代理人の FAX 番号", "agent_fax", courtdocs.first_line(row[m.COL["代理人FAX番号"]]))
        # 裁判所名を直したら、その裁判所の FAX 番号を入れ直す（FAX 番号を手で直していなければ）
        self._auto_fax = self.vars["court_fax"].get()
        self.vars["court"].trace_add("write", lambda *a: self._court_changed())
        ttk.Label(f, text="当職（弁護士名）").grid(row=5, column=0, sticky="e", padx=(0, 6), pady=2)
        self.lawyer = ttk.Combobox(f, values=lawyers, width=34)
        self.lawyer.set(lawyers[0] if lawyers else "")
        self.lawyer.grid(row=5, column=1, columnspan=2, sticky="w", pady=2)
        entry(6, "次回期日（任意）", "next", "")
        ttk.Label(f, text="例：R7.12.1 10:30", style="Note.TLabel").grid(row=7, column=1, sticky="w")
        ttk.Label(f, text="送付書類").grid(row=8, column=0, sticky="ne", padx=(0, 6), pady=(8, 2))
        ttk.Label(f, text="書類の名前", style="Note.TLabel").grid(row=8, column=1, sticky="w", pady=(8, 2))
        ttk.Label(f, text="枚数", style="Note.TLabel").grid(row=8, column=2, sticky="w", pady=(8, 2))
        self.docs = []
        for i in range(self.ROWS):
            n = ttk.Entry(f, width=36)
            n.grid(row=9 + i, column=1, sticky="w", pady=1)
            p = ttk.Spinbox(f, from_=0, to=999, width=5)
            p.set(1)
            p.grid(row=9 + i, column=2, sticky="w", padx=(6, 0), pady=1)
            self.docs.append((n, p))
        r = 9 + self.ROWS
        ttk.Label(f, text="後日クリーンコピー提出").grid(row=r, column=0, sticky="e", padx=(0, 6), pady=(8, 0))
        cf = ttk.Frame(f)
        cf.grid(row=r, column=1, columnspan=2, sticky="w", pady=(8, 0))
        self.clean = [tk.BooleanVar(value=False) for _ in range(3)]
        for v, label in zip(self.clean, ("送付した書面全部", "答弁書・準備書面", "書証")):
            tk.Checkbutton(cf, text=label, variable=v).pack(side="left", padx=(0, 10))
        if not (office_tel or office_fax):
            ttk.Label(f, text="事務所の電話番号・FAX 番号は、事務所の設定で入れておくと、送付書に書きます。",
                      style="Note.TLabel").grid(row=r + 1, column=1, columnspan=2, sticky="w", pady=(6, 0))
        b = ttk.Frame(self, padding=(12, 0, 12, 12))
        b.pack(fill="x")
        ttk.Button(b, text="キャンセル", command=self.destroy).pack(side="right")
        ttk.Button(b, text="PDF を作る", style="Accent.TButton", command=self._ok).pack(side="right", padx=6)
        self.bind("<Escape>", lambda e: self.destroy())
        center(self, parent)
        self.deiconify()
        self.grab_set()
        self.docs[0][0].focus_set()

    def _court_changed(self):
        fax = self.vars["court_fax"]
        if fax.get() == self._auto_fax:       # 手で直していなければ
            self._auto_fax = self._fax_of(self.vars["court"].get())
            fax.set(self._auto_fax)

    def _ok(self):
        from ..common.dates import format_datetime_long, parse_datetime
        docs = []
        for n, p in self.docs:
            name = n.get().strip()
            if not name:
                continue
            try:
                pages = int(p.get())
                if pages < 0:
                    raise ValueError
            except ValueError:
                messagebox.showwarning(TITLE, f"「{name}」の枚数を、数で入れてください。", parent=self)
                return
            docs.append((name, pages))
        if not docs:
            messagebox.showwarning(TITLE, "送付書類を1つ以上入れてください。", parent=self)
            return
        nxt = self.vars["next"].get().strip()
        next_text = ""
        if nxt:
            parsed = parse_datetime(nxt)
            if parsed is None:
                messagebox.showwarning(TITLE, "次回期日の日時を読めません（例：R7.12.1 10:30）。", parent=self)
                return
            next_text = format_datetime_long(*parsed)
        if not self.lawyer.get().strip():
            messagebox.showwarning(TITLE, "当職（弁護士名）を入れてください。", parent=self)
            return
        self.result = self._cd.SendInfo(
            court=self.vars["court"].get().strip(),
            court_fax=self.vars["court_fax"].get().strip(), agent=self.vars["agent"].get().strip(),
            agent_fax=self.vars["agent_fax"].get().strip(), lawyer=self.lawyer.get().strip(),
            office_tel=self._office[0], office_fax=self._office[1], next_hearing=next_text, documents=docs,
            clean_copy=tuple(v.get() for v in self.clean))
        self.destroy()