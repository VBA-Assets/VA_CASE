"""一覧（ttk.Treeview）の動き（4つのツールで共通。SharedApp が受け継ぐ）。

2026-11-10 のリファクタリングで、shared_app.py から分けた（動きは変えていない）：
- キー操作（上下の矢印・PageUp/Down・Home/End・左右。Excel にそろえる）と、上下の矢印キーを押し続けたときの加速
- すべてのセルを列の幅で折り返して出す（データの1行の2行目からは、その行の子の行）・列の幅を覚える
- 何行かを選ぶ操作（なぞる・Shift＋クリック・Shift＋矢印キー）とコピー（Ctrl+C・リボンの［コピー］）
- セルの中の文字を、なぞって選んでコピーする（cell_text.py の CellText から受け継ぐ）
- フィルタ（見出しをクリックして、出す値を選ぶ。Excel のフィルタに近い形）

受け継ぐ側は、self.root・self.tree・self.cfg・self.data・self.work_label と、_on_select・refresh を持つこと。
"""
import time
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from ..search import normalize
from . import theme
from .cell_text import CellText
from .dialogs import wrap_text


class CharWidths:
    """字ごとの幅を覚えて、文字列の幅を足し合わせで出す（wrap_text の font の代わり。measure だけを持つ）。"""

    def __init__(self, font, key):
        self.font, self.key, self.widths = font, key, {}

    def measure(self, text):
        widths, total = self.widths, 0
        for ch in text:
            w = widths.get(ch)
            if w is None:
                w = widths[ch] = self.font.measure(ch)
            total += w
        return total


class ListView(CellText):
    H_STEP = 40                # 左右の矢印キーで横に動かす幅（画素）

    def init_list_state(self):
        self.last_key_move = 0.0    # キー（上下の矢印・PageUp/Down）で選ぶ行を動かした時刻（time.monotonic）
        self._hold = None           # 上下の矢印キーを押し続けている間の記録（加速に使う）
        self._released_at = None    # 上下の矢印キーを離した時刻（event.time）
        self._range = None          # (起点の行, 端の行)。続いた何行かを選んでいるとき
        self._drag = None           # なぞって選んでいる間の、起点と端
        self._cells = {}            # データの行の鍵 → {列: 一覧に出した値}（コピーに使う）
        self._show_job = None       # あとに回した、選んだ行を入力欄（カード）に出す処理（矢印キーで送っている間）
        self.filters = {}           # 列 → 出す値の集合（フィルタ）
        self._filter_rows = []      # 検索に当てはまった行の {列: 一覧に出した値}（フィルタの値の一覧に使う）

    # ------------------------------------------------------------ 一覧のキー操作

    def bind_table_keys(self, tree):
        """一覧をキーで動かす（2026-11-09 班長指摘「矢印キーや PageUp/Down でスクロールできない」）。

        ttk の既定は、「いまの行」（フォーカスの行）がないと矢印キーが効かず、PageUp/Down は表示を動かすだけで行を
        選ばず、Home/End は効かない。選んでいる行を、見えるところまで動かす。Home・Ctrl+Home・Ctrl+End は Excel に
        そろえる（2026-11-09 班長指示）：Home は行の先頭（左端の列）へ、Ctrl+Home は先頭の行の左端へ、Ctrl+End は
        最後の行の右端へ。End は、Home と対にして行の最後（右端の列）へ。左右の矢印キーは横に動かす（列が多いため）。
        """
        for key, step in (("Up", -1), ("Down", 1)):
            tree.bind(f"<KeyPress-{key}>", lambda e, s=step: self._arrow(e, s))
            tree.bind(f"<KeyRelease-{key}>", self._arrow_released)
        for key, move in (("<Prior>", "page-"), ("<Next>", "page+")):
            tree.bind(key, lambda e, mv=move: self._key_move(mv))
        tree.bind("<Home>", lambda e: self._scroll_x(0.0))
        tree.bind("<End>", lambda e: self._scroll_x(1.0))
        tree.bind("<Control-Home>", lambda e: (self._move_selection("first"), self._scroll_x(0.0))[1])
        tree.bind("<Control-End>", lambda e: (self._move_selection("last"), self._scroll_x(1.0))[1])
        tree.bind("<Left>", lambda e: (self.tree.xview_scroll(-self.H_STEP, "units"), "break")[1])
        tree.bind("<Right>", lambda e: (self.tree.xview_scroll(self.H_STEP, "units"), "break")[1])
        # 横のホイール（Shift＋ホイール・ホイールの左右・タッチパッドの横）。ttk の既定は 1目盛りで1画素しか動かず、
        # ほとんど動かないので、1目盛りを左右の矢印キーと同じ幅にする。
        tree.bind("<Shift-MouseWheel>", self._wheel_x)
        self.bind_list_copy(tree)

    def _key_move(self, move):
        """キーで選ぶ行を動かす。時刻を覚えておき、押し続けている間は、入力欄（VA Case のカード）の書き換えを
        あとに回せるようにする（moved_by_key_recently）。"""
        self.last_key_move = time.monotonic()
        return self._move_selection(move)

    def moved_by_key_recently(self, seconds=0.5):
        return time.monotonic() - self.last_key_move < seconds

    def key_held(self):
        """上下の矢印キーを、まだ押し続けているか（押した後に「離す」が来ていない。2026-11-13）。一覧の描き直しに
        時間がかかると、次の「押す」を受け取る前に、あとに回した入力欄の書き換えの時刻が来てしまう（そのときは、
        さらに待つ）。「離す」が来ないまま入力先が移ったときなどのため、最後に動かしてから1秒たったら、押していないと
        みなす。"""
        return self._hold is not None and self._released_at is None and self.moved_by_key_recently(1.0)

    # 上下の矢印キーを押し続けたときの加速（2026-11-10 班長指示「加速を入れる」）。
    #
    # 押し始めは1行ずつ進み、押し続けるほど、1回に何行もまとめて進む（HOLD_SPEEDS）。進む行数は、押し始めてからの
    # 時間で決める（一覧の描き直しが追いつかない分のキーの繰り返しは、Windows が1回にまとめてしまうため、回数では
    # 決めない）。時間は、アプリの処理の遅れに左右されないよう、キーの入力に付く時刻（event.time。ミリ秒）で測る。
    # キーを離したら（「離す」の後に、間を置いて「押す」が来たら）、押し直しとみなして1行ずつに戻る。自動の繰り返しで、
    # 「離す」と「押す」が同じ時刻に続けて来る環境もあるので、その「離す」は押し続けとみなす。
    HOLD_SPEEDS = ((1.0, 30), (2.5, 60))   # (押し始めてからの秒, それからの1秒あたりの行数)
    HOLD_GAP_MS = 1100        # 前の「押す」からこれより空いたら、押し直し（Windows の繰り返しの開始は最長1秒）
    RELEASE_GAP_MS = 30       # 「離す」からこれより空いて「押す」が来たら、押し直し

    @staticmethod
    def _ms_between(earlier, later):
        return (later - earlier) & 0xFFFFFFFF   # event.time は32ビットで一回りする

    def _hold_rows(self, elapsed):
        """押し始めてから elapsed 秒までに、加速で進む行数（1行ずつ進む分を除く）。"""
        rows = 0.0
        bounds = list(self.HOLD_SPEEDS) + [(float("inf"), 0)]
        for (start, speed), (end, _) in zip(bounds, bounds[1:]):
            if elapsed > start:
                rows += (min(elapsed, end) - start) * speed
        return int(rows)

    def _arrow(self, event, step):
        self.last_key_move = time.monotonic()
        t = event.time
        h = self._hold
        released = self._released_at
        self._released_at = None
        if (h is None or h["step"] != step or self._ms_between(h["last"], t) > self.HOLD_GAP_MS
                or (released is not None and self._ms_between(released, t) > self.RELEASE_GAP_MS)):
            self._hold = {"step": step, "start": t, "last": t, "origin": None, "base": 0}
            return self._move_selection(step)     # 押し始め：1行
        h["last"] = t
        extra = self._hold_rows(self._ms_between(h["start"], t) / 1000)
        items = self.tree.get_children()
        current = self.selected_key()
        if extra <= 0 or current not in items:
            return self._move_selection(step)     # 加速の前：1行ずつ
        cur = items.index(current)
        if h["origin"] is None:                    # 加速の始まり：ここから数える
            h["origin"], h["base"] = cur, extra
        target = h["origin"] + step * (extra - h["base"])
        if (target - cur) * step < 1:
            target = cur + step                    # 少なくとも1行は進む
        return self._move_selection(target - cur)

    def _arrow_released(self, event):
        self._released_at = event.time

    def _wheel_x(self, event):
        notches = event.delta / 120
        step = round(self.H_STEP * notches) or (1 if notches > 0 else -1)   # タッチパッドの細かい動きも捨てない
        self.tree.xview_scroll(-step, "units")
        return "break"

    def _scroll_x(self, where):
        """一覧を横の端へ動かす（0.0 は左端、1.0 は右端）。"""
        self.tree.xview_moveto(where)
        return "break"

    def _page_rows(self):
        """一覧に一度に見える行の数（PageUp/Down で動かす行の数）。"""
        style = self.tree.cget("style") or "Treeview"
        try:
            height = int(ttk.Style(self.root).lookup(style, "rowheight") or 20)
        except (TypeError, ValueError):
            height = 20
        return max(1, self.tree.winfo_height() // height - 2)

    def _page_index(self, items, cur, step):
        """PageUp/Down で動く先：見える行の数だけ動かす（1件を何行かで出すときは、その行の数を数える）。"""
        page, used, index = self._page_rows(), 0, cur
        while 0 <= index + step < len(items):
            used += 1 + len(self.tree.get_children(items[index + step]))
            if used > page and index != cur:
                break
            index += step
        return index

    def _move_selection(self, move):
        items = self.tree.get_children()
        if not items:
            return "break"
        current = self.selected_key() or (self._list_row(self.tree.focus()) if self.tree.focus() else None)
        if current not in items:
            index = len(items) - 1 if move == "last" else 0   # 選んでいなければ、先頭（End なら最後）から
        elif move in ("page-", "page+"):
            index = self._page_index(items, items.index(current), -1 if move == "page-" else 1)
        else:
            cur = items.index(current)
            index = {"first": 0, "last": len(items) - 1}.get(move, cur + move if isinstance(move, int) else cur)
        index = min(max(index, 0), len(items) - 1)
        self._select_item(items[index])
        return "break"

    def _select_item(self, iid):
        """データの1行（全部の行）を選び、「いまの行」にして、見えるところまで動かす（矢印キーがその行から効くように）。"""
        self.cell_text_hide()
        self._range = None
        group = self._group(self.tree, iid)
        self.tree.selection_set(group)
        self.tree.focus(group[0])
        self.tree.see(group[-1])
        self.tree.see(group[0])

    # ------------------------------------------------------------ 選んだ行を入力欄（カード）に出す
    #
    # 矢印キー・PageUp/Down で行を動かしている間は、入力欄（VA Case のカード、VA Call・VA Filing・VA Receipt の入力欄）を
    # 書き換えず、キーを止めて SHOW_DELAY_MS たったら書き換える。時刻が来ても、まだ押し続けていれば、さらに待つ（key_held）。
    # クリックで選んだときは、すぐ書き換える。経緯：2026-11-10 班長指示「矢印キーを押している間はカードを更新せず、離した
    # 時に更新する」（VA Case）、2026-11-13 班長指摘「VA FILINGでは、矢印キーを押している間もカードの更新が行われている
    # ような気がする」「VA Phoneも同じことを確認。」（VA Filing・VA Receipt・VA Call）。それまでは3つの画面に同じ処理を
    # 別々に書いていたのを、2026-11-13 のリファクタリングでここにまとめた。
    # 受け継ぐ側は、_show_selected（いま選んでいる行を入力欄に出す）を持つこと。キーで送り始めたときに何かするなら
    # _selected_by_key（VA Filing・VA Receipt はプレビューを空にする）。
    SHOW_DELAY_MS = 200

    def _on_select(self):
        self.expand_selection(self.tree)   # 2行目以降（子の行）を選んだときも、その行の全部を選ぶ
        self._cancel_show()
        if self.moved_by_key_recently():
            self._selected_by_key()
            self._show_job = self.root.after(self.SHOW_DELAY_MS, self._show_due)
        else:
            self._show_selected()

    def _selected_by_key(self):
        """矢印キーで行を動かし、入力欄の書き換えをあとに回すときに呼ぶ（受け継ぐ側で、必要なら書き換える）。"""

    def _cancel_show(self):
        if self._show_job is not None:
            self.root.after_cancel(self._show_job)
            self._show_job = None

    def _show_due(self):
        """あとに回した書き換えの時刻。まだ矢印キーを押し続けていれば、さらに待つ。"""
        if self.key_held():
            self._show_job = self.root.after(self.SHOW_DELAY_MS, self._show_due)
        else:
            self._show_job = None
            self._show_selected()

    def flush_selected(self):
        """あとに回した書き換えを、いま行う（書き込む・消す・書類を作るなどの前に。選んでいる行と入力欄をそろえる）。"""
        if self._show_job is not None:
            self._cancel_show()
            self._show_selected()

    def _focus_table(self):
        """キーボードの入力先を一覧にする（読み込んだあと・画面を閉じたあと・検索のあと）。"""
        if self.tree.winfo_exists():
            self.tree.focus_set()

    # ------------------------------------------------------------ 一覧の行（データの1行と、その子の行）

    def _list_row(self, iid):
        """一覧の行が属する、データの1行の最初の行（その iid が、データの1行の鍵）。"""
        return self.tree.parent(iid) or iid

    def _group(self, tree, iid):
        top = tree.parent(iid) or iid
        return (top,) + tuple(tree.get_children(top))

    def selected_key(self):
        """選んでいるデータの1行の鍵（最初の行の iid）。選んでいなければ None。"""
        sel = self.tree.selection()
        if not sel:
            return None
        focus = self.tree.focus()
        return self._list_row(focus) if focus and focus in sel else self._list_row(sel[0])

    def expand_selection(self, tree):
        """一覧で選んだ行（子の行のこともある）を、データの1行の全部の行に広げる（何行かを選んでいるときは、それぞれ）。"""
        sel = tree.selection()
        if not sel:
            return
        tops = list(dict.fromkeys(tree.parent(i) or i for i in sel))
        groups = tuple(x for top in tops for x in self._group(tree, top))
        if set(sel) != set(groups):
            tree.selection_set(groups)
        focus = tree.focus()
        focus = (tree.parent(focus) or focus) if focus else None
        tree.focus(focus if focus in tops else tops[0])

    def set_row_tags(self, iid, tags):
        """データの1行の字の色・縞を、子の行にも付ける。"""
        if self.tree.exists(iid):
            for item in self._group(self.tree, iid):
                self.tree.item(item, tags=tags)

    # ------------------------------------------------------------ 一覧の折り返し
    #
    # すべてのセルを、列の幅で折り返して出す（Excel の「折り返して表示」。2026-11-09 班長指示。VA Case で作り、同日
    # 「すべてのツールに適用」）。セルの中の改行は、そのまま行の区切り。データの1行（事件・ファイル・メモ）の高さは、
    # いちばん行の多いセルの行数。ttk の一覧は行ごとに高さを変えられないため、2行目からを、その行の子の行として出す。
    # 選ぶ・動かす・字の色・縞は、データの1行ごと（最初の行と子の行をまとめて）に行う。

    def bind_wrapped_list(self, tree):
        """折り返して出す一覧に付ける：子の行を畳ませない。列の幅を変えたら折り返し直す。"""
        tree.bind("<<TreeviewClose>>", lambda e, t=tree: self._keep_open(t))
        tree.bind("<ButtonRelease-1>", self._column_resized, add="+")

    def _keep_open(self, tree):
        for iid in tree.get_children():
            tree.item(iid, open=True)

    def _cell_font(self):
        """一覧の字の幅を測るもの。字ごとの幅を覚えて足し合わせる（Tk で文字列を測ると、2000件の一覧で数秒かかった
        ため。字の間の詰めは無視するので、測った幅は実際よりわずかに広めになり、はみ出すことはない）。"""
        name = ttk.Style(self.root).lookup("Treeview", "font") or "TkDefaultFont"
        try:
            font = tkfont.nametofont(name)
        except tk.TclError:
            font = tkfont.Font(font=name)
        key = str(font.actual())
        if getattr(self, "_measure", None) is None or self._measure.key != key:
            self._measure = CharWidths(font, key)
            self._wrap_cache = {}
        return self._measure

    def _wrap_cell(self, text, font, width, wide):
        """セルの値を、列の幅で折り返した行の並びにする（改行は、そのまま行の区切り）。
        英数字の続き（パスなど）が1行に収まらないときは、字の間で切る。"""
        if not text:
            return [""]
        if "\n" not in text and len(text) * wide <= width:
            return [text]                     # どの字も全角の幅以下なので、測らなくても収まる
        key = (text, width)
        lines = self._wrap_cache.get(key)
        if lines is None:
            lines = []
            for line in wrap_text(text, font, width).split("\n"):
                while len(line) > 1 and font.measure(line) > width:
                    n = len(line) - 1
                    while n > 1 and font.measure(line[:n]) > width:
                        n -= 1
                    lines.append(line[:n])
                    line = line[n:]
                lines.append(line)
            if len(self._wrap_cache) > 20000:
                self._wrap_cache.clear()
            self._wrap_cache[key] = lines
        return lines

    @staticmethod
    def _shown_columns(tree):
        shown = tree["displaycolumns"]
        return tree["columns"] if shown in ("#all", ("#all",)) else shown

    def _column_widths(self):
        """一覧に出している列ごとの幅。出していない列は入れない。"""
        return {c: int(self.tree.column(c, "width")) for c in self._shown_columns(self.tree)}

    def _restore_column_widths(self):
        """覚えた列の幅に戻す（2026-11-09 班長指示「列の幅を保存する」。この PC の設定に、利用者ごとに覚える）。"""
        saved = getattr(self.cfg, "column_widths", None) or {}
        for c in self._shown_columns(self.tree):
            if c in saved:
                self.tree.column(c, width=theme.px(self.root, saved[c]))

    def _remember_column_widths(self):
        """いまの列の幅を、設定に入れる（画面の拡大率によらないよう、96 dpi のときの画素で）。"""
        s = theme.scale(self.root)
        self.cfg.column_widths = {c: int(round(w / s)) for c, w in self._column_widths().items()}

    def begin_wrapped_list(self):
        """一覧を作り直す前に呼ぶ（いまの字と列の幅を測る）。"""
        font = self._cell_font()
        self._cells = {}            # データの行の鍵 → {列: 一覧に出した値}（コピーに使う）
        self._filter_rows = []
        self._range = None
        self.cell_text_hide()
        self._widths = self._column_widths()
        self._wrap_ctx = (font, font.measure("国"), theme.px(self.root, 12))

    def insert_wrapped(self, iid, columns, values, tags):
        """データの1行を、折り返して一覧に入れる（columns は values の列の名前）。"""
        font, wide, pad = self._wrap_ctx
        widths = self._widths
        self._cells[iid] = dict(zip(columns, values))
        cells = [self._wrap_cell(v, font, max(widths[c] - pad, wide), wide) if c in widths else [v]
                 for c, v in zip(columns, values)]
        height = max(len(x) for x in cells)
        for j in range(height):
            line = [x[j] if j < len(x) else "" for x in cells]
            item, parent = (iid, "") if j == 0 else (f"{iid}#{j}", iid)
            self.tree.insert(parent, "end", iid=item, values=line, tags=tags, open=True)

    def update_list_row(self, iid, columns, values, tags=None):
        """データの1行（最初の行が iid）の一覧の字を、values に出し直す。入力欄で直している値を、書き込む前から一覧に
        出すため（VA Case・VA Call。2026-11-13 班長決定「A 青字のまま一覧に出す」）。

        一覧を作り直さず、その行の字だけを替える（位置・選択・入力先・スクロールはそのまま。一覧の作り直しは、選択の
        出来事を起こし、入力欄を出し直してしまうため）。折り返しの行の数が変われば、子の行を足す・除く。縞の地の色は
        そのまま残す。tags を渡さなければ、字の色もそのまま。"""
        tree = self.tree
        if not tree.exists(iid) or getattr(self, "_wrap_ctx", None) is None:
            return
        band = [t for t in tree.item(iid, "tags") if t in ("band", "band_view")]
        if tags is None:
            tags = [t for t in tree.item(iid, "tags") if t not in ("band", "band_view")]
        tags = list(tags) + band
        cells_now = dict(zip(columns, values))
        if self._cells.get(iid) == cells_now and list(tree.item(iid, "tags")) == tags:
            return                  # 変わっていない（打つたびに呼ぶので、同じなら何もしない）
        c = getattr(self, "_cell", None)
        if c is not None and c.get("key") == iid:
            self.cell_text_hide()   # 重ねた欄の字は、もとの値のもの
        font, wide, pad = self._wrap_ctx
        widths = self._widths
        self._cells[iid] = cells_now
        cells = [self._wrap_cell(v, font, max(widths[c] - pad, wide), wide) if c in widths else [v]
                 for c, v in zip(columns, values)]
        height = max(len(x) for x in cells)
        lines = [[x[j] if j < len(x) else "" for x in cells] for j in range(height)]
        old = list(tree.get_children(iid))
        keep = {f"{iid}#{j}" for j in range(1, height)}
        tree.item(iid, values=lines[0], tags=tags)
        added = []
        for j in range(1, height):
            item = f"{iid}#{j}"
            if tree.exists(item):
                tree.item(item, values=lines[j], tags=tags)
            else:
                tree.insert(iid, "end", iid=item, values=lines[j], tags=tags, open=True)
                added.append(item)
        extra = [i for i in old if i not in keep]
        if extra:
            tree.delete(*extra)
        if added and iid in tree.selection():
            tree.selection_add(added)       # 選んでいる行は、子の行も選ぶ

    def _column_resized(self, event):
        """列の幅を変えたら、その幅で折り返し直す（縦の位置は、そのまま）。"""
        if self.data is None or self._column_widths() == getattr(self, "_widths", None):
            return
        top = self.tree.yview()[0]
        self.refresh()
        self.tree.yview_moveto(top)

    # ------------------------------------------------------------ 一覧の何行かを選ぶ・コピーする
    #
    # 2026-11-10 班長決定（班長の問い「通常の Web 画面をコピーするように選択し、Ctrl+C でコピーすることはできないか？」。
    # ttk の一覧は行を単位に選ぶ作りで、文字をなぞって選ぶことはできないため、行とセルの単位にした）：
    # - マウスでなぞる・Shift＋クリック・Shift＋上下の矢印キーで、続いた何行かを選ぶ。
    # - Ctrl+C で、選んだ行の、一覧に出している列を、タブ区切りでコピーする（Excel にそのまま貼れる。セルの中の改行は、
    #   Excel と同じく " で囲む）。リボンの［コピー］も同じ（文字を選んでいても行をコピーする。見出しは付けない）。
    #   右クリックのメニュー（見出しを付けたコピーもできた）は、2026-11-14 になくした（班長指示。copy_selected_rows）。
    #   「このセルをコピー」は、セルの文字を選べるようにしたので、2026-11-13 になくした。
    # - 何行かを選んでいる間、入力欄（カード）には、クリックした行（なぞったときは、なぞり始めた行）を出す。
    # コピーするのは、一覧に出している値そのもの（列の幅での折り返しの前の値）。

    def bind_list_copy(self, tree):
        """一覧に、何行かを選ぶ操作とコピーを付ける。"""
        self._range = None          # (起点の行, 端の行)。続いた何行かを選んでいるとき
        self._drag = None
        tree.bind("<ButtonPress-1>", self._list_press, add="+")
        tree.bind("<B1-Motion>", self._list_drag, add="+")
        tree.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag", None), add="+")
        tree.bind("<Shift-ButtonPress-1>", self._list_shift_click)
        tree.bind("<Shift-KeyPress-Up>", lambda e: self._extend_by_key(-1))
        tree.bind("<Shift-KeyPress-Down>", lambda e: self._extend_by_key(1))
        tree.bind("<<Copy>>", lambda e: (self.copy_selection(), "break")[1])
        self.bind_cell_text(tree)

    def _row_at(self, y):
        iid = self.tree.identify_row(y)
        return self._list_row(iid) if iid else None

    def _list_press(self, event):
        """クリック（行を1つ選ぶのは ttk の既定に任せる）。なぞる起点を覚える。"""
        self._range = None
        region = self.tree.identify_region(event.x, event.y)
        key = self._row_at(event.y) if region in ("cell", "tree") else None
        self._drag = {"anchor": key, "end": key} if key else None

    def _list_drag(self, event):
        if self.cell_drag(event):     # 押したセルの中：そのセルの文字を選ぶ（cell_text.py）
            return
        d = self._drag
        if not d:
            return
        tree = self.tree
        if event.y < 0:                          # 一覧の上・下の外までなぞったら、そちらへ動かす
            tree.yview_scroll(-1, "units")
        elif event.y > tree.winfo_height():
            tree.yview_scroll(1, "units")
        y = min(max(event.y, 1), tree.winfo_height() - 2)
        key = self._row_at(y)
        if key and key != d["end"]:
            d["end"] = key
            self._select_range(d["anchor"], key, focus=d["anchor"])

    def _list_shift_click(self, event):
        key = self._row_at(event.y)
        if key is None:
            return "break"
        anchor = self._range[0] if self._range else self.selected_key()
        self.tree.focus_set()
        self._select_range(anchor or key, key, focus=key)
        return "break"

    def _extend_by_key(self, step):
        anchor, end = self._range if self._range else (self.selected_key(),) * 2
        items = self.tree.get_children()
        if anchor not in items or end not in items:
            return "break"
        i = min(max(items.index(end) + step, 0), len(items) - 1)
        self._select_range(anchor, items[i], focus=anchor)
        return "break"

    def _select_range(self, anchor, end, focus):
        """起点から端までのデータの行（子の行も）を選ぶ。focus の行を「いまの行」（入力欄に出す行）にする。"""
        tree = self.tree
        items = tree.get_children()
        if anchor not in items or end not in items:
            return
        i, j = sorted((items.index(anchor), items.index(end)))
        tree.selection_set(tuple(x for key in items[i:j + 1] for x in self._group(tree, key)))
        tree.focus(focus)
        group = self._group(tree, end)
        tree.see(group[-1])
        tree.see(group[0])
        self._range = (anchor, end)

    def selected_keys(self):
        """選んでいるデータの行の鍵（一覧の順）。"""
        sel = set(self.tree.selection())
        return [key for key in self.tree.get_children() if key in sel]

    @staticmethod
    def _tsv_cell(value):
        value = str(value or "")
        if any(ch in value for ch in '\t\n\r"'):
            return '"' + value.replace('"', '""') + '"'    # Excel と同じ形（貼り付けると、セルの中の改行になる）
        return value

    def rows_text(self, keys, header=False):
        """データの行を、一覧に出している列のタブ区切りの文にする。"""
        columns = list(self._shown_columns(self.tree))
        cells = getattr(self, "_cells", {})
        lines = []
        if header:
            lines.append("\t".join(self._tsv_cell(c) for c in columns))
        for key in keys:
            row = cells.get(key, {})
            lines.append("\t".join(self._tsv_cell(row.get(c, "")) for c in columns))
        return "\r\n".join(lines) + "\r\n"

    def _to_clipboard(self, text, what):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.work_label.configure(text=f"{what}をコピーしました")

    def copy_rows(self, header=False):
        keys = self.selected_keys()
        if keys:
            self._to_clipboard(self.rows_text(keys, header), f"{len(keys)} 行" + ("（見出しを付けて）" if header else ""))

    def copy_selection(self):
        """Ctrl+C：セルの中で文字を選んでいればその文字を、そうでなければ選んだ行をコピーする。"""
        text = self.cell_text_selected()
        if text is not None:
            self._to_clipboard(text, "選んだ文字")
        else:
            self.copy_rows()

    def copy_selected_rows(self):
        """リボンの［コピー］：選んでいる行（何行かを選んでいれば、その全部）を、見出しを付けずにコピーする。セルの中で
        文字を選んでいても、行をコピーする（文字だけをコピーするのは Ctrl+C）。

        2026-11-14 班長指示「「コピー」ボタンを追加。「消す」ボタンの上に配置。選択しているメモをコピーする。見出しは
        付けない。リストの右クリックメニューは廃止。」「VA CASEを含め、すべてのツールに適用」。それまでは、一覧の右クリック
        のメニューで「選んだ文字をコピー」「選んだ○行をコピー」「見出しを付けてコピー」を出していた（見出しを付けた
        コピーは、なくした）。"""
        self.flush_selected()
        self.copy_rows(header=False)

    # ------------------------------------------------------------ 一覧のフィルタ
    #
    # 2026-11-10 班長決定（班長の問い「リストでフィルタを掛けられるようにはできるか？」。同日「A Excel に近い形」
    # 「覚えない」）：見出しをクリックすると、その列の値の一覧（チェックを付けて選ぶ）を出し、選んだ値の行だけを出す。
    # - 何列かに掛けたときは、すべてに当てはまる行だけを出す（Excel と同じ）。検索とも一緒に使える。
    # - 値は、一覧に出している値（日付は一覧と同じ形）。セルの中に何行かある値（相手方2人など）は、1行ずつを値として
    #   並べ、どれか1つが選んだ値なら出す。空のセルは「（空白）」。
    # - 値の一覧に並べるのは、検索とほかの列のフィルタに当てはまる行の値（Excel と同じ）。
    # - 掛けた列は、見出しに ▼ を付ける。ツールバーの「すべてを表示」で、検索と一緒に、すべての列のフィルタを外す
    #   （2026-11-11 まではフィルタだけを外す「フィルタを解除」だった）。
    # - フィルタは覚えない（閉じたら解除。現行の Excel 版の「リロード時にフィルターを解除」〔Ver7A1〕と同じ考え方）。
    #   「最新を読み込む」・書き込みの後は、掛けたままにする。

    FILTER_MARK = " ▼"
    BLANK_LABEL = "（空白）"

    @staticmethod
    def _cell_values(value):
        """セルの値を、フィルタの値の集合にする（何行かあれば1行ずつ。空なら "" ひとつ）。"""
        values = {line.strip() for line in str(value or "").split("\n") if line.strip()}
        return values or {""}

    def passes_filter(self, columns, values):
        """一覧に出す行か（フィルタに当てはまるか）。一覧を作り直すときに、検索に当てはまった行ごとに呼ぶこと。"""
        cells = dict(zip(columns, values))
        self._filter_rows.append(cells)
        return all(self._cell_values(cells.get(c, "")) & allowed for c, allowed in self.filters.items())

    def filter_values(self, column):
        """フィルタの値の一覧に並べる値（検索と、ほかの列のフィルタに当てはまる行の値。空白は最後）。"""
        others = {c: v for c, v in self.filters.items() if c != column}
        found = set()
        for cells in self._filter_rows:
            if all(self._cell_values(cells.get(c, "")) & allowed for c, allowed in others.items()):
                found |= self._cell_values(cells.get(column, ""))
        return sorted(found, key=lambda v: (v == "", v))

    def open_filter(self, column):
        """見出しをクリックしたとき：その列の値の一覧を出す。"""
        if self.data is None:
            return
        values = self.filter_values(column)
        checked = set(values) & self.filters[column] if column in self.filters else set(values)
        FilterPopup(self.root, column, values, checked, lambda chosen: self.set_filter(column, chosen, values))

    def set_filter(self, column, chosen, values):
        """列のフィルタを決める（すべての値を選んだら、その列のフィルタを外す）。"""
        if chosen is None or set(chosen) >= set(values):
            self.filters.pop(column, None)
        else:
            self.filters[column] = set(chosen)
        self.refresh()
        self._focus_table()

    def mark_filtered_columns(self):
        """フィルタを掛けた列の見出しに ▼ を付け、「すべてを表示」を使えるかを合わせる（一覧を作り直したら呼ぶ）。

        「すべてを表示」は、検索かフィルタで絞っている間だけ使える（2026-11-11 班長決定。narrowed_label と同じ判定）。
        """
        for c in self.tree["columns"]:
            self.tree.heading(c, text=c + (self.FILTER_MARK if c in self.filters else ""))
        button = getattr(self, "clear_narrow_button", None)
        query = getattr(self, "query", None)
        if button is not None:
            narrowed = bool(self.filters) or (query is not None and not query.empty)
            button.state(["!disabled"] if narrowed else ["disabled"])


class FilterPopup(tk.Toplevel):
    """フィルタの値の一覧（見出しをクリックしたときに、マウスの所に出す）。

    値ごとにチェック（☑・☐）を付けて選ぶ。値を探す欄・すべて選ぶ・すべて外す・この列のフィルタを解除・OK・キャンセル。
    値が多くても速いよう、チェックボックスを並べず、一覧（Treeview）の行の頭の印で示す。
    on_ok(選んだ値の集合)。「この列のフィルタを解除」は on_ok(None)。
    """
    ON, OFF = "☑", "☐"

    def __init__(self, parent, column, values, checked, on_ok):
        super().__init__(parent)
        self.withdraw()
        self.title(f"フィルタ　{column}")
        self.transient(parent)
        self.resizable(False, True)
        self.values = list(values)
        self.checked = set(checked)
        self.on_ok = on_ok
        f = ttk.Frame(self, padding=8)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="値を探す", style="Note.TLabel").pack(anchor="w")
        self.search_var = tk.StringVar()
        e = ttk.Entry(f, textvariable=self.search_var, width=30)
        e.pack(fill="x")
        self.search_var.trace_add("write", lambda *a: self._fill())
        bf = ttk.Frame(f)
        bf.pack(fill="x", pady=(6, 4))
        ttk.Button(bf, text="すべて選ぶ", command=lambda: self._set_all(True)).pack(side="left")
        ttk.Button(bf, text="すべて外す", command=lambda: self._set_all(False)).pack(side="left", padx=(6, 0))
        lf = ttk.Frame(f)
        lf.pack(fill="both", expand=True)
        self.list = ttk.Treeview(lf, show="tree", selectmode="browse", height=14)
        self.list.column("#0", width=theme.px(self, 300))
        bar = ttk.Scrollbar(lf, orient="vertical", command=self.list.yview)
        self.list.configure(yscrollcommand=bar.set)
        self.list.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.list.bind("<ButtonRelease-1>", self._clicked)
        self.list.bind("<space>", lambda ev: (self._toggle(self.list.focus()), "break")[1])
        self.note = ttk.Label(f, text="", style="Note.TLabel")
        self.note.pack(anchor="w", pady=(4, 0))
        ok = ttk.Frame(f)
        ok.pack(fill="x", pady=(6, 0))
        ttk.Button(ok, text="この列のフィルタを解除", command=self._clear).pack(side="left")
        ttk.Button(ok, text="キャンセル", command=self.destroy).pack(side="right")
        self.ok_button = ttk.Button(ok, text="OK", style="Accent.TButton", command=self._ok)
        self.ok_button.pack(side="right", padx=(0, 6))
        self.bind("<Return>", lambda ev: self._ok())
        self.bind("<Escape>", lambda ev: self.destroy())
        self._fill()
        self.update_idletasks()
        x, y = self.winfo_pointerx() - 20, self.winfo_pointery() + 10
        x = max(0, min(x, self.winfo_screenwidth() - self.winfo_reqwidth()))
        y = max(0, min(y, self.winfo_screenheight() - self.winfo_reqheight() - 40))
        self.geometry(f"+{x}+{y}")
        self.deiconify()
        self.grab_set()
        e.focus_set()

    def _label(self, value):
        return value if value else ListView.BLANK_LABEL

    def _shown(self):
        q = normalize(self.search_var.get().strip())
        return [v for v in self.values if not q or q in normalize(self._label(v))]

    def _fill(self):
        self.list.delete(*self.list.get_children())
        for i, v in enumerate(self._shown()):
            self.list.insert("", "end", iid=str(self.values.index(v)),
                             text=f"{self.ON if v in self.checked else self.OFF}  {self._label(v)}")
        self._update_ok()

    def _clicked(self, event):
        if self.list.identify_region(event.x, event.y) == "tree":
            self._toggle(self.list.identify_row(event.y))

    def _toggle(self, iid):
        if not iid:
            return
        v = self.values[int(iid)]
        if v in self.checked:
            self.checked.discard(v)
        else:
            self.checked.add(v)
        self.list.item(iid, text=f"{self.ON if v in self.checked else self.OFF}  {self._label(v)}")
        self._update_ok()

    def _set_all(self, on):
        """いま見えている値（値を探す欄で絞っていれば、その値）を、すべて選ぶ・外す。"""
        for v in self._shown():
            if on:
                self.checked.add(v)
            else:
                self.checked.discard(v)
        self._fill()

    def _update_ok(self):
        n = len(self.checked & set(self.values))
        self.note.configure(text=f"{len(self.values)} 個の値のうち {n} 個を選んでいます")
        self.ok_button.state(["!disabled"] if n else ["disabled"])   # 何も選ばないと、1行も出なくなるため

    def _ok(self):
        chosen = self.checked & set(self.values)
        if not chosen:
            return
        self.destroy()
        self.on_ok(chosen)

    def _clear(self):
        self.destroy()
        self.on_ok(None)
