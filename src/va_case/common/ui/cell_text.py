"""一覧のセルの中の文字を、なぞって選んでコピーする（4つのツールで共通。ListView が受け継ぐ）。

2026-11-13 に list_view.py へ入れ、同日のリファクタリングで、このモジュールに分けた。
受け継ぐ側は、self.root・self.tree・self._cells（データの行の鍵 → {列: 一覧に出した値}）と、ListView の
_list_row・_group・_shown_columns・_list_drag（初めに cell_drag を呼ぶ）・_list_shift_click・_wheel_x を
持つこと。
"""
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from . import theme


class CellText:
    # ------------------------------------------------------------ セルの中の文字を選ぶ
    #
    # 2026-11-13 班長決定「案Aを適用」（班長「ユーザーは、コピーしたいデータをマウスで選択して、コピーしようとする」
    # 「プレビューと同じように選択してコピーするようにはできないのか」）。ttk の一覧は文字の単位で選べないため、
    # セルの中でなぞり始めたら、そのセルに、同じ位置・同じ字・同じ色で、文字を選べる欄（tk.Text。直せない状態）を
    # 重ね、なぞった範囲を選ぶ。見た目は変わらない。
    # - Ctrl+C でコピーする（右クリックのメニューは 2026-11-14 になくした）。選んだ後、Shift+左右の矢印キーで、範囲を1字ずつ変えられる。折り返して何行かになったセルも、全体に重ねる。
    #   コピーするのは、折り返しの改行を除いた、もとの値の文字。
    # - クリックは今までどおり行を選び、ダブルクリックは今までどおり（入力欄を開くなど）。セルの外までなぞったら、
    #   今までどおり何行かを選ぶ（行のコピー）。
    # - 文字を選んだ後は、重ねた欄はそのまま（Ctrl+C を押せるように）。ほかをクリックする・キーで行を動かす・一覧を
    #   動かす・入力先がほかへ移ると外す。
    # 最初は、マウスを載せたセルに欄を重ねていたが、セルを移るたびに欄を置き直すので、一覧がちらついた（2026-11-13
    # 班長指摘「リストにマウスを置くと、チラツキがある」）。同日、なぞり始めたときだけ重ねる形に改めた。
    # 字の位置は、一覧のセルの字とそろうよう、左の余白を CELL_PADX にし、行の高さに合わせて上下に間を入れる（試用の
    # 画面で、重ねる前と後の画素が同じになることを確かめた）。

    CELL_PADX = 4

    def bind_cell_text(self, tree):
        self._cell = None            # 重ねている欄の情報（鍵・列・一覧の行・字の対応・選び始めの位置）
        self._cell_press = None      # 一覧のセルでボタンを押したところ ((鍵, 列), x, y)
        self._cell_rowdrag = False   # セルの外までなぞって、何行かを選んでいる
        self._cell_forwarding = False   # 重ねた欄のクリックを、一覧に渡している間
        t = tk.Text(tree, bd=0, highlightthickness=0, pady=0, wrap="none", cursor="xterm", takefocus=0,
                    exportselection=False, insertwidth=0, relief="flat",
                    selectbackground=theme.TEXT_SELECT_BG, selectforeground=theme.TEXT,
                    inactiveselectbackground=theme.TEXT_SELECT_BG)
        self._cell_text = t
        tree.bind("<ButtonPress-1>", self._cell_tree_press, add="+")
        tree.bind("<ButtonRelease-1>", self._cell_tree_release, add="+")
        tree.bind("<<TreeviewSelect>>", lambda e: self._cell_recolor(), add="+")
        tree.bind("<MouseWheel>", lambda e: self.cell_text_hide(), add="+")
        tree.bind("<FocusOut>", self._cell_focus_out, add="+")
        # 文字を選んだ後の、重ねた欄の上のマウス：一覧の上の出来事として扱う（Text の既定の動きはさせない）
        t.bind("<ButtonPress-1>", self._cell_press_on_text)
        t.bind("<B1-Motion>", lambda e: (self._list_drag(self._tree_event(e)), "break")[1])
        t.bind("<ButtonRelease-1>", self._cell_release_on_text)
        t.bind("<Double-1>", self._cell_double)
        t.bind("<Shift-ButtonPress-1>", lambda e: (self._list_shift_click(self._tree_event(e)), "break")[1])
        t.bind("<MouseWheel>", self._cell_wheel)
        t.bind("<Shift-MouseWheel>", lambda e: (self.cell_text_hide(), self._wheel_x(e))[1])
        # キーボードの入力先は一覧のまま（矢印キーで行を動かし、Ctrl+C は copy_selection で、もとの値の文字をコピー
        # するため）
        t.bind("<FocusIn>", lambda e: self.tree.focus_set())
        # Shift+左右の矢印キーで、選んだ文字の範囲を1字ずつ変える（2026-11-13 班長指示「Shift+左右矢印で選択範囲を
        # 変更できるようにならないか」）。文字を選んでいなければ、今までどおり一覧を横に動かす（<Left>・<Right> は、
        # Shift を押していても受けていたため）
        for key, step in (("<Shift-Left>", -1), ("<Shift-Right>", 1)):
            tree.bind(key, lambda e, s=step: self._cell_shift_arrow(s))

    def _tree_event(self, e):
        """重ねた欄の上のマウスの出来事を、一覧の上の位置に直す（一覧の処理に渡すため）。"""
        c = getattr(self, "_cell", None)
        t = self._cell_text
        ox, oy = (c["x"], c["y"]) if c else (t.winfo_x(), t.winfo_y())
        return SimpleEvent(x=e.x + ox, y=e.y + oy, x_root=e.x_root, y_root=e.y_root,
                           delta=getattr(e, "delta", 0), state=e.state)

    def _cell_at(self, x, y):
        tree = self.tree
        if tree.identify_region(x, y) != "cell":
            return None
        iid, col_id = tree.identify_row(y), tree.identify_column(x)
        shown = list(self._shown_columns(tree))
        if not iid or not (col_id.startswith("#") and col_id[1:].isdigit() and 1 <= int(col_id[1:]) <= len(shown)):
            return None
        return self._list_row(iid), shown[int(col_id[1:]) - 1]

    # 一覧のセルでボタンを押した・なぞった・離した

    def _cell_tree_press(self, event):
        if not self._cell_forwarding:
            self.cell_text_hide()
        at = self._cell_at(event.x, event.y)
        self._cell_press = (at, event.x, event.y) if at else None
        self._cell_rowdrag = False
        if self._cell is not None:
            self._cell_text.tag_remove("sel", "1.0", "end")
            self._cell["pinned"] = False

    def cell_drag(self, event):
        """なぞっている間（_list_drag から呼ぶ）。押したセルの中なら、そのセルの文字を選んで True。セルの外へ出たら、
        文字の選択をやめて False（何行かを選ぶ、今までの動き）。"""
        press = getattr(self, "_cell_press", None)
        if not press or self._cell_rowdrag:
            return False
        at, px, py = press
        if self._cell_at(event.x, event.y) != at:
            self._cell_rowdrag = True
            self.cell_text_hide()
            return False
        c = self._cell
        if c is None or (c["key"], c["column"]) != at:
            if not self._cell_show(*at):
                self._cell_press = None
                return False
            c = self._cell
        t = self._cell_text
        if c.get("anchor") is None:
            c["anchor"] = self._cell_gap(px - c["x"], py - c["y"])
        end = self._cell_gap(event.x - c["x"], event.y - c["y"])
        self._cell_select_to(end)
        return True

    def _cell_select_to(self, end):
        """重ねた欄で、選び始めの位置から end までを選ぶ（end は、動かしている側の端として覚える）。"""
        c, t = self._cell, self._cell_text
        c["end"] = end = t.index(end)
        first, last = sorted((c["anchor"], end), key=lambda i: tuple(int(n) for n in t.index(i).split(".")))
        t.tag_remove("sel", "1.0", "end")
        if t.compare(first, "<", last):
            t.tag_add("sel", first, last)

    def cell_extend_by_char(self, step):
        """選んだ文字の範囲の、動かしている側の端（なぞり終えた側）を1字ずつ動かす。始めの側は動かさない（ワープロと
        同じ）。折り返しで入れた改行は、続けて次の字まで動かす。文字を選んだ後（なぞり終えた後）でなければ False。"""
        c = getattr(self, "_cell", None)
        if not c or not c.get("pinned") or c.get("anchor") is None or c.get("end") is None:
            return False
        t = self._cell_text
        last = t.index("end-1c")
        pos = c["end"]
        while True:
            new = t.index(f"{pos}{'+' if step > 0 else '-'}1c")
            if t.compare(new, ">", last):
                new = last
            if t.compare(new, "==", pos):
                break
            crossed = t.get(pos, new) if step > 0 else t.get(new, pos)
            pos = new
            if crossed != "\n":
                break
        self._cell_select_to(pos)
        return True

    def _cell_shift_arrow(self, step):
        if not self.cell_extend_by_char(step):
            self.tree.xview_scroll(step * self.H_STEP, "units")
        return "break"

    def _cell_gap(self, x, y):
        """欄の中の位置 (x, y) にいちばん近い字の間（Text の index）。"""
        t = self._cell_text
        idx = t.index(f"@{x},{y}")
        box = t.bbox(idx)
        if box and x > box[0] + box[2] / 2:
            idx = t.index(f"{idx}+1c")
        return idx

    def _cell_tree_release(self, event):
        self._cell_press = None
        self._cell_rowdrag = False
        if self._cell is not None:
            if self.cell_text_selected() is None:
                self.cell_text_hide()
            else:
                self._cell["pinned"] = True

    # 文字を選んだ後の、重ねた欄の上のマウス

    def _cell_press_on_text(self, event):
        """重ねた欄をクリック：一覧のクリックとして渡す（行を選び、なぞり始める）。欄は、なぞるまでそのまま置く
        （押している間に欄を外すと、続くマウスの出来事の行き先がなくなるため）。"""
        e = self._tree_event(event)
        self._cell_forwarding = True
        try:
            self.tree.event_generate("<ButtonPress-1>", x=e.x, y=e.y)
        finally:
            self._cell_forwarding = False
        if self._cell is not None:
            self._cell["anchor"] = self._cell["end"] = None
        self._cell_recolor()
        return "break"

    def _cell_release_on_text(self, event):
        e = self._tree_event(event)
        self.tree.event_generate("<ButtonRelease-1>", x=e.x, y=e.y)
        return "break"

    def _cell_show(self, key, column):
        """セル（データの1行 key の列 column）に、文字を選べる欄を重ねる。空のセル・見えていないセルなら False。"""
        tree, t = self.tree, self._cell_text
        items = self._group(tree, key)
        lines = [str(tree.set(i, column)) for i in items]
        while len(lines) > 1 and lines[-1] == "":
            lines.pop()
        if not any(lines):
            self.cell_text_hide()
            return False
        first, last = tree.bbox(items[0], column), tree.bbox(items[len(lines) - 1], column)
        if not first or not last:
            self.cell_text_hide()
            return False
        x, y, w, h = first
        height = last[1] + last[3] - y
        f = self._cell_font_obj()
        extra = max(h - f.metrics("linespace"), 0)
        t.configure(state="normal", font=f, padx=theme.px(self.root, self.CELL_PADX), spacing1=extra // 2,
                    spacing3=extra - extra // 2)
        t.delete("1.0", "end")
        shown = "\n".join(lines)
        t.insert("1.0", shown)
        t.configure(state="disabled")
        original = str(self._cells.get(key, {}).get(column, "") or "")
        self._cell = {"key": key, "column": column, "items": items, "shown": shown, "anchor": None, "x": x, "y": y,
                      "map": _display_map(original, lines), "original": original, "pinned": False}
        self._cell_recolor()
        t.place(x=x, y=y, width=w, height=height)
        t.lift()
        t.update_idletasks()      # 字の位置（@x,y）を、すぐ求められるように
        return True

    def _cell_font_obj(self):
        name = ttk.Style(self.root).lookup("Treeview", "font") or "TkDefaultFont"
        try:
            return tkfont.nametofont(name)
        except tk.TclError:
            return tkfont.Font(font=name)

    def _cell_recolor(self):
        """重ねた欄の地と字の色を、その行の見た目（選んだ行・字の色・縞）に合わせる。"""
        c = getattr(self, "_cell", None)
        if not c:
            return
        tree = self.tree
        if not tree.exists(c["key"]):
            self.cell_text_hide()
            return
        style = ttk.Style(self.root)
        name = tree.cget("style") or "Treeview"
        bg = style.lookup(name, "background") or theme.FIELD_BG
        fg = style.lookup(name, "foreground") or theme.TEXT
        for tag in tree.item(c["key"], "tags") or ():
            bg = tree.tag_configure(tag, "background") or bg
            fg = tree.tag_configure(tag, "foreground") or fg
        if c["key"] in tree.selection():
            bg = theme.PRESSED_BG             # 字の色は、選んだ行でも印の色のまま（theme の Treeview の map）
        self._cell_text.configure(bg=bg, fg=fg)

    def cell_text_hide(self):
        if getattr(self, "_cell", None) is None:
            return
        self._cell = None
        t = self._cell_text
        t.tag_remove("sel", "1.0", "end")
        t.place_forget()

    def cell_text_selected(self):
        """セルの中で選んでいる文字（もとの値の文字。折り返しの改行は除く）。選んでいなければ None。"""
        c = getattr(self, "_cell", None)
        if not c:
            return None
        t = self._cell_text
        try:
            a, b = t.index("sel.first"), t.index("sel.last")
        except tk.TclError:
            return None
        start, end = len(t.get("1.0", a)), len(t.get("1.0", b))
        mapped = [c["map"][i] for i in range(start, end) if i < len(c["map"]) and c["map"][i] is not None]
        if not mapped:
            return None
        return c["original"][min(mapped):max(mapped) + 1]

    def _cell_double(self, event):
        """ダブルクリックは、今までどおり一覧のダブルクリック（入力欄を開くなど）。字の単位では選ばない。"""
        e = self._tree_event(event)
        self.cell_text_hide()
        self.tree.event_generate("<Double-1>", x=e.x, y=e.y)
        return "break"

    def _cell_focus_out(self, event):
        """入力先が一覧の外（カードの欄など）へ移ったら、セルで選んだ文字を外す（2026-11-13 班長指摘「選択した状態で、
        他のテキストボックス等をクリックしても、選択状態が解除されない」）。重ねた欄をクリックした瞬間にも入力先が
        いったん移るので、少し待って、移った先を確かめる。"""
        def check():
            try:
                now = self.root.focus_get()
            except (KeyError, tk.TclError):
                now = None
            if now not in (self.tree, self._cell_text):
                self.cell_text_hide()
        self.root.after(50, check)

    def _cell_wheel(self, event):
        self.cell_text_hide()
        self.tree.yview_scroll(int(-event.delta / 120) or (-1 if event.delta > 0 else 1), "units")
        return "break"


class SimpleEvent:
    """一覧の処理に渡す、マウスの出来事の代わり（x・y は一覧の上の位置）。"""

    def __init__(self, **kw):
        self.__dict__.update(kw)


def _display_map(original, lines):
    """一覧に出した行（折り返した値）の字が、もとの値の何字目かの並び（折り返しで入れた改行は None）。

    折り返しでは、行の終わりの空白を除くことがある（wrap_text）ので、もとの値の空白は読み飛ばして合わせる。"""
    out, o, n = [], 0, len(original)
    for li, line in enumerate(lines):
        if li > 0:
            if o < n and original[o] == "\n":
                out.append(o)          # もとの値の改行
                o += 1
            else:
                out.append(None)       # 折り返しで入れた改行
        for ch in line:
            while o < n and original[o] != ch and original[o] in " \t\u3000":
                o += 1
            if o < n and original[o] == ch:
                out.append(o)
                o += 1
            else:
                out.append(None)
    return out
