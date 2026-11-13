"""VA Case の、ウィンドウの下側のカード（一覧で選んだ事件を出したままにし、そこで直す）。

2026-11-10 班長決定：VA Filing・VA Receipt・VA Call と同じく、選んだ事件をウィンドウの下側のカードに出し、カードで直す
（それまでの、別のウィンドウの入力欄はやめた）。32の項目を横に4列に並べ、何行かの欄は2行の高さにしてスクロールバーを
付ける。閲覧モードでは見るだけ。
直した値は、ほかの事件に移るときなどに、画面の側（app.py）が書き込む。直す前の値には Ctrl+Z で戻す（2026-11-12 班長決定。
それまでは「書き込む」「入力を戻す」のボタンがあった。common/ui/undo.py）。
"""
import re
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from ..common.dates import display_lines as date_display   # 生年月日は何行か（1行の値は1つの日付と同じ）
from ..common.ui import autocomplete, theme
from ..common.ui.tooltip import Tooltip
from . import model as m

# カードの並び（4列。左から、上から順に。Tab で移る順もこの順）。2026-11-10 班長決定「4列に詰める」。
# 同日 班長指示で並べ替え：列は左から 事件・依頼者・関係者・相手方・代理人・その他（それまでの「事件（続き）」を改名して
# 右端へ）。依頼人立場は「事件」から「その他」の事件名の下へ、相談内容は「依頼者・関係者」の一番下へ移した
CARD_LAYOUT = [
    ("事件", ["事件番号", "現況", "事件呼名", "受任区分", "事件区分", "担当区分", "相談弁護士", "相談年月日", "終了年月日"]),
    ("依頼者・関係者", ["依頼者氏名", "ふりがな", "生年月日", "住所", "電話番号", "メールアドレス", "関係者", "相談内容"]),
    ("相手方・代理人", ["相手方氏名", "相手方ふりがな", "相手方住所", "相手方電話番号", "代理人", "代理人住所", "代理人電話番号",
                 "代理人FAX番号"]),
    ("その他", ["裁判所名", "裁判所事件番号", "事件名", "依頼人立場", "データフォルダ", "TeamsURL", "備考"]),
]
assert sorted(n for _, names in CARD_LAYOUT for n in names) == sorted(m.CASE_COLUMNS)
# 4列の幅の割合。「事件」の列は短い値ばかりなので、ほかの3列の半分より狭くし、残りを3列に割り振る（2026-11-10 班長指示
# 「事件列の幅は、もっと小さくて良い。現在の半分程度に縮小し、その分を残りの3つに割り振る」。それまでは4列とも同じ幅）
# 同日 班長指示「カードの事件列の幅を4～6文字増加。他の列の幅が同一で収まるように調整」（全画面表示のときの数値）：
# 全画面（幅 約2010画素の入力欄）で、事件の列が 251 → 約314画素（全角で約5文字分広い）、ほかの3列が 586 → 約565画素
# （3列は同じ幅）になるよう、割合を 3：7：7：7 から 5：9：9：9 にした
GROUP_WEIGHTS = (5, 9, 9, 9)
assert len(GROUP_WEIGHTS) == len(CARD_LAYOUT)
# 何行かの値を入れる欄（2行の高さにし、スクロールバーを付ける。複数の相手方などは、改行で区切って入れる）
TEXT_FIELDS = ("事件呼名", "相談内容", "データフォルダ", "備考", "依頼者氏名", "ふりがな", "生年月日", "住所", "電話番号",
               "メールアドレス", "関係者", "相手方氏名", "相手方ふりがな", "相手方住所", "相手方電話番号", "代理人", "代理人住所", "代理人電話番号",
               "代理人FAX番号")
TEXT_LINES = 2
# 2行でない欄の高さ（2026-11-10 班長指示「事件呼名を高さを2行分にする。備考の高さを4行分にする。代理人電話番号および
# FAX番号の高さを1行分にする」。代理人が何人かいるときは、スクロールバーで見る）
FIELD_LINES = {"備考": 4, "代理人電話番号": 1, "代理人FAX番号": 1,
               "メールアドレス": 1,   # 同日 班長指示「メールアドレスは1行の高さに変更」
               # 依頼者が何人かいるときの生年月日（1行に1人。2026-11-12 班長決定「1行の高さで直す」。2人目からはスクロールバーで見る）
               "生年月日": 1}
# 値は1行だが、長いので2行の高さで折り返して見せる欄（改行は入れさせない。2026-11-09 班長指示：データフォルダの
# 長いパスが、1行の欄では後ろが切れて見えたため）
# 事件呼名も、長い値が切れて見えないよう、2行の高さで折り返して見せる（2026-11-10 班長指示）
WRAPPED_SINGLE_LINE = ("事件呼名", "データフォルダ")
# オートコンプリートを付ける列（2026-11-09 班長決定。同じ値を何度も入れる列。何行かの欄は、行ごとに補う）
AUTOCOMPLETE_COLUMNS = ("裁判所名", "事件名", "代理人", "代理人住所", "代理人電話番号", "代理人FAX番号")
# 欄の横に「開く」ボタンを置く列（一覧のセルのダブルクリックで開いていたもの。一覧に出さなくなったため）
OPEN_COLUMNS = ("データフォルダ", "TeamsURL")
# 「開く」の説明書き（2026-11-13 班長指示「カードの実行ボタンにも説明書きを付ける」）
OPEN_TIPS = {"データフォルダ": "データフォルダを、エクスプローラーで開きます（書き込んだ値の場所）。",
             "TeamsURL": "TeamsURL を開きます（ブラウザーか Teams で開きます）。"}
DATE_NOTE = "日付は R7.1.1・2025/1/1 などの形で入れてください。複数の相手方などは、改行で区切って入れます。"


NO_LINE_START = "、。，．）」』】・？！ー"   # 行の頭に来させない文字（前の文字と一緒に次の行へ送る）


def wrap_text(text, font, width):
    """text を、1行が width 画素に収まるよう折り返す（日本語は1文字ずつ、英数字の続き〔Ctrl+Z など〕は切らない）。"""
    out = []
    for para in text.split("\n"):
        tokens = re.findall(r"[!-~]+| |.", para)
        line = []
        for tok in tokens:
            if line and font.measure("".join(line) + tok) > width:
                carry = []
                if tok in NO_LINE_START and len(line) > 1:   # 行の頭の句読点を避け、前の1文字ごと送る
                    carry = [line.pop()]
                out.append("".join(line).rstrip())
                line = carry
                if tok == " " and not line:
                    continue
            line.append(tok)
        out.append("".join(line).rstrip())
    return "\n".join(out)


def row_values(row):
    """共有データの行を、カードに出す値（列の名前 → 文字列。日付は和暦）にする。"""
    return {c: date_display(row[m.COL[c]]) if c in m.DATE_COLUMNS else row[m.COL[c]] for c in m.CASE_COLUMNS}


class CaseCard(ttk.Frame):
    """選んだ事件のカード。

    on_change()：利用者が欄を直したとき。
    on_open(列の名前)：データフォルダ・TeamsURL の「開く」。rows()：いまの事件の行の一覧（補う候補と代理人を探す）。
    """

    def __init__(self, master, *, on_change, on_open, rows):
        super().__init__(master)   # 枠は、画面の側（SharedApp.mode_card）で付ける
        self._on_change = on_change
        self._rows = rows
        self._loading = False
        self.editable = False
        self.number = None
        self.widgets = {}
        self.vars = {}
        self.open_buttons = {}
        font = theme.field_font(self)
        body = ttk.Frame(self)
        body.pack(fill="x")
        for gi, (group, names) in enumerate(CARD_LAYOUT):
            frame = ttk.Frame(body, padding=(0, 0, 12 if gi < len(CARD_LAYOUT) - 1 else 0, 0))
            frame.grid(row=0, column=gi, sticky="nwe")
            body.columnconfigure(gi, weight=GROUP_WEIGHTS[gi], uniform="card")
            frame.columnconfigure(1, weight=1)
            ttk.Label(frame, text=group, style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky="w",
                                                                     pady=(0, 2))
            for fi, name in enumerate(names, start=1):
                ttk.Label(frame, text=name, style=autocomplete.label_style(name, AUTOCOMPLETE_COLUMNS)).grid(
                    row=fi, column=0, sticky="ne" if name in TEXT_FIELDS else "e", padx=(0, 6), pady=1)
                holder = ttk.Frame(frame)
                holder.grid(row=fi, column=1, sticky="we", pady=1)
                holder.columnconfigure(0, weight=1)
                w = self._make_field(holder, name, font)
                self.widgets[name] = w
                if name in OPEN_COLUMNS:
                    b = ttk.Button(holder, text="開く", style="Small.TButton", command=lambda n=name: on_open(n))
                    b.grid(row=0, column=2, sticky="n", padx=(4, 0))
                    b.tooltip = Tooltip(b, OPEN_TIPS.get(name, ""), above=True)
                    self.open_buttons[name] = b
        # 注意書き（日付の入れ方・オートコンプリート）は、項目のいちばん少ない「その他」の列の下に、列の幅で
        # 折り返してまとめる（2026-11-12 班長指示「カード下端の左右に分かれている注意書きを、まとめて「その他」の列の直下に
        # 移し、カードの高さが最小になるように」。それまではカードの下に1段とって、左右に分けていた）。
        # 同日、いまの状態の文（閲覧モードです・直したら移るときに書き込みます）はなくした（班長指摘「この行は不要ではないか？」）
        assert group == "その他"   # 右端の列（ループの最後の frame・names）
        # 1つのラベルにまとめて余白をなくし、列の幅いっぱいで1文字ずつ折り返す（Tk の折り返しは空白でしか切らず、
        # 行の後ろが空く）。全画面では、ほかの列の高さに収まり、カードが高くならない
        self.notes = ttk.Label(frame, style="TightNote.TLabel", justify="left", wraplength=200)
        self.notes.grid(row=len(names) + 1, column=0, columnspan=2, sticky="we", pady=(2, 0))
        self._notes_width = 0
        self.notes.bind("<Configure>", lambda e: self._wrap_notes(e.width))
        self._attach_autocomplete()

    def _wrap_notes(self, width):
        if width == self._notes_width:
            return
        self._notes_width = width
        font = tkfont.nametofont(self.notes.cget("font") or "TkDefaultFont")
        self.notes.configure(text=wrap_text(DATE_NOTE + autocomplete.NOTE, font, max(width, 100)),
                             wraplength=max(width, 100) + 1)

    # ------------------------------------------------------------ 欄

    def _make_field(self, holder, name, font):
        if name in m.CHOICE_FOR_COLUMN:
            var = tk.StringVar()
            w = ttk.Combobox(holder, textvariable=var, values=[""], width=8, font=font, state="disabled")
            var.trace_add("write", lambda *a: self._changed())
            self.vars[name] = var
            w.grid(row=0, column=0, sticky="we")
            return w
        if name in TEXT_FIELDS:
            w = tk.Text(holder, width=8, height=FIELD_LINES.get(name, TEXT_LINES), font=font, wrap="char", undo=False)
            bar = ttk.Scrollbar(holder, orient="vertical", command=w.yview, style="Thin.Vertical.TScrollbar")
            w.configure(yscrollcommand=bar.set)
            w.grid(row=0, column=0, sticky="we")
            bar.grid(row=0, column=1, sticky="ns")
            w.bind("<Tab>", lambda e: (e.widget.tk_focusNext().focus_set(), "break")[1])
            if name in WRAPPED_SINGLE_LINE:   # Enter で改行させず、次の欄へ進む
                w.bind("<Return>", lambda e: (e.widget.tk_focusNext().focus_set(), "break")[1])
            w.bind("<<Modified>>", lambda e: self._text_modified(e.widget), add="+")
            return w
        var = tk.StringVar()
        w = ttk.Entry(holder, textvariable=var, width=8, font=font)
        var.trace_add("write", lambda *a: self._changed())
        self.vars[name] = var
        w.grid(row=0, column=0, sticky="we")
        return w

    def _text_modified(self, w):
        if w.edit_modified():
            w.edit_modified(False)
            self._changed()

    def _changed(self):
        if not self._loading and self.number is not None:
            self._on_change()

    def set_choices(self, tables):
        """選択肢（事務所の設定）を、ドロップダウンに入れる。"""
        choices = tables[m.CHOICES]
        for name, item in m.CHOICE_FOR_COLUMN.items():
            values = [""] + m.choice_values(choices, item)
            self.widgets[name].configure(values=values)

    def value(self, name):
        w = self.widgets[name]
        if isinstance(w, tk.Text):
            if name in WRAPPED_SINGLE_LINE:   # 貼り付けた改行なども除いて1行にする
                return "".join(w.get("1.0", "end-1c").splitlines()).strip()
            return w.get("1.0", "end-1c").rstrip("\n")
        return self.vars[name].get().strip()

    def values(self):
        return {name: self.value(name) for name in self.widgets}

    def put(self, number, values):
        """事件をカードに出す（number が None なら空にする）。values：列の名前 → 文字列。"""
        self.number = number
        self._auto_agent = {col: {} for col in m.AGENT_DETAIL_COLUMNS}   # 自動で入れた値は、事件ごと
        self.set_values(values)
        self.set_editable(self.editable)

    def set_values(self, values):
        """いまの事件のまま、欄の値だけを入れ替える（Ctrl+Z で戻すとき）。直したとは知らせない。"""
        self._loading = True
        try:
            for name, w in self.widgets.items():
                v = values.get(name, "")
                if isinstance(w, tk.Text):
                    self._set_text(name, v)
                else:
                    if isinstance(w, ttk.Combobox) and v and v not in w.cget("values"):
                        w.configure(values=list(w.cget("values")) + [v])   # 選択肢から外れた古い値も、そのまま残す
                    self.vars[name].set(v)
        finally:
            self._loading = False

    def _set_text(self, name, value):
        w = self.widgets[name]
        state = w.cget("state")
        w.configure(state="normal")
        w.delete("1.0", "end")
        w.insert("1.0", value)
        w.edit_modified(False)    # 入れた値で、その欄のオートコンプリートを働かせない
        w.configure(state=state)

    def set_editable(self, editable):
        """直せるか（編集モードで、事件を選んでいるとき）。閲覧モードでは見るだけ（Tab では移れる）。"""
        self.editable = editable
        on = editable and self.number is not None
        shown = self.number is not None
        for name, w in self.widgets.items():
            if isinstance(w, ttk.Combobox):   # 直せないときは、文字を選べる読み取り専用の欄に替える
                theme.show_choice(w, "readonly" if on else None, shown)
            elif isinstance(w, tk.Text):
                w.configure(state="normal" if on else "disabled",
                            background=theme.FIELD_BG if on else theme.READONLY_BG)
            else:
                # 事件番号も、編集モードでは直せる（2026-11-11 班長指示。それまでは、いつも直せなかった）
                w.configure(state="normal" if on else "readonly" if shown else "disabled")
            theme.tab_stop(w, shown)
        for name, b in self.open_buttons.items():
            b.state(["!disabled"] if shown and self.value(name) else ["disabled"])

    def focus_first(self):
        self.widgets["事件呼名"].focus_set()

    # ------------------------------------------------------------ オートコンプリート・代理人から住所などを入れる

    def _attach_autocomplete(self):
        self._agent_job = None
        self._auto_agent = {col: {} for col in m.AGENT_DETAIL_COLUMNS}   # 列 → {行: 自動で入れた値}
        for name in AUTOCOMPLETE_COLUMNS:
            w = self.widgets[name]
            values = (lambda n=name: autocomplete.column_values(self._rows(), m.COL[n], split_lines=True))
            done = self._agent_changed_later if name == "代理人" else None
            if isinstance(w, tk.Text):
                autocomplete.attach_text(w, values, on_complete=done)
            else:
                autocomplete.attach_entry(w, values, on_complete=done)
        # 代理人が、これまでの事件の代理人と一致したら、住所・電話番号・FAX番号を入れる（2026-11-09 班長指示）。
        # 補ったとき・キーを離したとき・欄を出たとき（日本語入力で確定した字も、欄を出れば確かめる）に確かめる。
        agent = self.widgets["代理人"]
        for seq in ("<KeyRelease>", "<FocusOut>"):
            agent.bind(seq, lambda e: self._agent_changed_later(), add="+")

    def _agent_changed_later(self):
        if self._agent_job is None:
            self._agent_job = self.after_idle(self._agent_changed)

    def _agent_changed(self):
        """代理人の各行（1人ずつ）が、これまでの事件の代理人と一致したら、同じ行に住所・電話番号・FAX番号を入れる。

        利用者が入れた値は変えない（空か、前に自動で入れた値のときだけ入れる。VA Call の電話番号と同じ）。代理人を
        直して一致しなくなったら、自動で入れた値（その後に直していないもの）は消す。代理人が1人なら、欄の全体に
        入れる（住所が2行にわたるときも、そのまま）。何人かなら、代理人と同じ行に、1行の値だけを入れる。
        """
        self._agent_job = None
        if not self.winfo_exists() or not self.editable or self.number is None:
            return
        names = self.value("代理人").split("\n")
        while names and not names[-1].strip():
            names.pop()
        found = [m.agent_details(self._rows(), n, exclude=self.number) if n.strip() else {} for n in names]
        for col in m.AGENT_DETAIL_COLUMNS:
            auto = self._auto_agent[col]
            if len(names) <= 1:
                self._fill_whole(col, found[0].get(col, "") if found else "", auto)
            else:
                self._fill_lines(col, [f.get(col, "") for f in found], auto)

    def _fill_whole(self, col, new, auto):
        cur = self.value(col)
        old = auto.get(0)
        if new and (not cur or cur == old):
            if cur != new:
                self._set_filled(col, new)
            auto.clear()
            auto[0] = new
        elif not new and old is not None and cur == old:
            self._set_filled(col, "")
            auto.clear()

    def _fill_lines(self, col, values, auto):
        lines = self.value(col).split("\n") if self.value(col) else []
        if len(auto) == 1 and 0 in auto and "\n" in auto[0]:
            auto.clear()      # 1人のときに入れた何行かの値は、何人かになったら、行ごとの扱いにしない
        changed = False
        for i, new in enumerate(values):
            if "\n" in new:
                new = ""
            while len(lines) <= i:
                lines.append("")
            cur, old = lines[i].strip(), auto.get(i)
            if new and (not cur or cur == old):
                if cur != new:
                    lines[i], changed = new, True
                auto[i] = new
            elif not new and old is not None and cur == old:
                lines[i], changed = "", True
                auto.pop(i, None)
        if changed:
            while lines and not lines[-1].strip():
                lines.pop()
            self._set_filled(col, "\n".join(lines))

    def _set_filled(self, col, value):
        """自動で入れる（オートコンプリートは働かせず、直した印は付ける）。"""
        self._set_text(col, value)
        self._changed()
