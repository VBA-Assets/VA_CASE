"""入力欄のオートコンプリート（Excel のオートコンプリートと同じ動き。2026-11-09 班長指示）。

- 欄に入力していくと、同じ列のこれまでの値のうち、入力した文字で始まるものが1つに決まったときに、残りの部分を
  選んだ状態で補う（同じ文字で始まる値が2つ以上あるあいだは補わない。Excel と同じ）。
- 続けて打つと、補った部分は打った文字に置き換わる。Backspace・Delete で補った部分を消すと、その後は補わない
  （もう一度打つまで）。Tab などで次の欄へ進むと、補った値が入る。
- 何行かの欄（tk.Text）では、カーソルのある行ごとに補う（候補も、値を1行ずつに分けたもの）。

補うのは、欄に字が入った（増えた）とき。キーを離したとき（<KeyRelease>）に確かめる作りでは、日本語入力（IME）で
確定した字が入っても確かめられず、補わなかった（2026-11-09 班長指摘「全く効いていない」）。字が入ったことは、
1行の欄では入力の確かめ（validatecommand。キーでも IME でも、字が入るたびに呼ばれる）で、何行かの欄では
<<Modified>> で知り、少し後（after_idle）に確かめる。

全角・半角と大文字・小文字は問わずに比べ、補うときは、打った部分も候補の書き方にそろえる（日本語入力のまま打った
「０６」から「06-1111-1111」を補えるように）。

付ける列は、ツールごとに班長が選んだ列だけ（仕様.md）。候補は、そのツールの共有データの同じ列の値。
"""
import unicodedata

# オートコンプリートを付けた欄は、欄の名前に下線を引き（ttk のスタイル "Auto.TLabel"）、入力欄の下にこの説明を置く
# （2026-11-09 班長決定。4つのツールとも）
NOTE = "下線の付いた欄は、入力すると、これまでに入れた値から続きを補います（Enter で確定）。"
LABEL_STYLE = "Auto.TLabel"


def label_style(name, names):
    """欄の名前のラベルのスタイル（オートコンプリートを付けた欄なら下線）。"""
    return LABEL_STYLE if name in names else "TLabel"


def _key(text):
    """比べるための形（全角・半角と、大文字・小文字を問わない。日本語入力のまま打った「０６」も「06」と同じに見る）。"""
    return unicodedata.normalize("NFKC", text).casefold()


def unique_completion(typed, candidates):
    """typed で始まる候補が1つに決まれば、その候補を返す（全角・半角、大文字・小文字は問わない）。決まらなければ None。"""
    if not typed:
        return None
    t = _key(typed)
    found = {c for c in candidates if c and len(_key(c)) > len(t) and _key(c).startswith(t)}
    if len(found) != 1:
        return None
    return found.pop()


def attach_entry(entry, candidates, on_complete=None):
    """ttk.Entry に付ける。candidates() は候補の文字列の並びを返す関数。確かめる処理を返す（試験で使う）。"""
    state = {"busy": False, "job": None, "before": "", "suggest": None}

    def check():
        state["job"] = None
        if state["busy"] or str(entry.cget("state")) in ("disabled", "readonly"):
            return
        text = entry.get()
        before, state["suggest"] = state["before"], None
        if len(text) <= len(before):                     # 消した・置き換えただけなら補わない
            return
        if entry.index("insert") != len(text) or entry.selection_present():
            return                                        # 途中に入れたときは補わない
        done = unique_completion(text, candidates())
        if done is None:
            return
        state["busy"] = True
        try:   # 打った部分も、候補の書き方（半角など）にそろえる
            entry.delete(0, "end")
            entry.insert(0, done)
        finally:
            state["busy"] = False
        entry.select_range(len(text), "end")
        entry.icursor(len(text))
        text = done[:len(text)]
        state["suggest"] = (text, entry.get())
        if on_complete:
            on_complete()

    def changed(before):
        """字が入る・消える直前に呼ばれる（before は変わる前の値）。変わった後に check を行う。"""
        if state["busy"]:
            return True
        if state["job"] is None:
            s = state["suggest"]
            # 補った部分を打った字で置き換えるときは、補う前（打った分まで）と比べる
            state["before"] = s[0] if s and before == s[1] else before
            state["job"] = entry.after_idle(check)
        return True

    def accept(event=None):
        """Enter で、欄の値を確定する（選んである部分を外し、カーソルを最後へ。Excel と同じ。2026-11-09 班長指摘
        「リターンキーを押しても背景色が消えない」）。補った部分だけでなく、Tab で欄に入ったときに全体が選ばれた
        ものも外す（相手先から自動で入った電話番号など。同日 班長指摘）。"""
        if entry.selection_present():
            entry.selection_clear()
            entry.icursor("end")
        state["suggest"] = None

    def leave(event=None):
        """ほかの欄へ移るときは、補った部分の選択だけを外す。"""
        if state["suggest"] and entry.selection_present():
            entry.selection_clear()
            entry.icursor("end")
        state["suggest"] = None

    entry.configure(validate="key", validatecommand=(entry.register(changed), "%s"))
    entry.bind("<Return>", accept, add="+")
    entry.bind("<KP_Enter>", accept, add="+")
    entry.bind("<FocusOut>", leave, add="+")

    def traverse_in(event=None):
        """Tab で欄に入ったときに、全体を選ばない（選ぶと、確定した値が未確定のように見えるため。2026-11-09 班長
        指摘）。カーソルを最後に置くだけにする（ttk の既定の、全体を選ぶ動きを止める）。"""
        entry.selection_clear()
        entry.icursor("end")
        return "break"
    entry.bind("<<TraverseIn>>", traverse_in, add="+")
    return check


def attach_text(text, candidates, on_complete=None):
    """tk.Text（何行かの欄）に付ける。カーソルのある行ごとに補う。candidates() は1行ずつの候補を返す関数。"""
    state = {"busy": False, "job": None, "line": "", "suggest": None}

    def line_text():
        return text.get("insert linestart", "insert lineend")

    def remember(event=None):
        state["line"] = line_text()
        state["suggest"] = None

    def check():
        state["job"] = None
        if state["busy"] or str(text.cget("state")) == "disabled":
            return
        line = line_text()
        before, s = state["line"], state["suggest"]
        if s and before == s[1]:
            before = s[0]
        state["line"], state["suggest"] = line, None
        if len(line) <= len(before) or text.get("insert linestart", "insert") != line or text.tag_ranges("sel"):
            return
        done = unique_completion(line, candidates())
        if done is None:
            return
        state["busy"] = True
        try:
            text.delete("insert linestart", "insert lineend")   # 打った部分も、候補の書き方にそろえる
            text.insert("insert linestart", done)
            start = text.index(f"insert linestart + {len(line)} chars")
            text.mark_set("insert", "insert lineend")
            text.tag_remove("sel", "1.0", "end")
            text.tag_add("sel", start, "insert lineend")
            text.mark_set("insert", start)
            text.edit_modified(False)
        finally:
            state["busy"] = False
        state["line"], state["suggest"] = line_text(), (done[:len(line)], line_text())
        if on_complete:
            on_complete()

    def modified(event=None):
        if not text.edit_modified():
            return
        text.edit_modified(False)
        if not state["busy"] and state["job"] is None:
            state["job"] = text.after_idle(check)

    text.edit_modified(False)
    def accept(event=None):
        """Enter で、補った値を確定する（選んである部分を外し、カーソルを行の最後へ。改行はしない）。"""
        if state["suggest"] and text.tag_ranges("sel"):
            text.tag_remove("sel", "1.0", "end")
            text.mark_set("insert", "insert lineend")
            state["suggest"] = None
            state["line"] = line_text()
            return "break"      # この Enter では改行しない（もう一度押せば改行する）
        return None

    def leave(event=None):
        if state["suggest"] and text.tag_ranges("sel"):
            text.tag_remove("sel", "1.0", "end")
        state["suggest"] = None

    text.bind("<<Modified>>", modified, add="+")
    text.bind("<Return>", accept, add="+")
    text.bind("<KP_Enter>", accept, add="+")
    text.bind("<FocusOut>", leave, add="+")
    for seq in ("<FocusIn>", "<ButtonRelease-1>", "<KeyRelease-Up>", "<KeyRelease-Down>", "<KeyRelease-Left>",
                "<KeyRelease-Right>", "<KeyRelease-Home>", "<KeyRelease-End>"):
        text.bind(seq, remember, add="+")
    remember()
    return check


def column_values(rows, index, split_lines=False):
    """候補にする、ある列の値（重なりを除き、新しい行のものを先に）。split_lines なら、値を1行ずつに分ける。"""
    seen, out = set(), []
    for row in reversed(rows):
        values = row[index].split("\n") if split_lines else [row[index]]
        for v in values:
            v = v.strip()
            if v and v not in seen:
                seen.add(v)
                out.append(v)
    return out
