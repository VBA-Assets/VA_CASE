"""入力欄の Ctrl+Z（元に戻す）と Ctrl+Y（やり直す）。4つのツールで共通。

2026-11-12 班長の問い「「入力を戻す」も無くし、Ctrl+Zで元に戻せないか？」に、案（直した順に1つずつ戻す。Excel のセルの
「元に戻す」と同じ）を示し、班長決定「その形で作る」。それまでは、欄ごとの Text の元に戻す（何行かの欄だけ）と、
「入力を戻す」のボタン（その事件・メモの、直す前の値にまとめて戻す）があった。

- 1つの事件・メモ・行を入力欄に出している間の、入力欄全体の値の移り変わりを覚える（reset で始め、ほかの行に移ると
  書き込まれるので、戻せるのはその間だけ）。
- 1つの欄で続けて打った分は1つにまとめる（欄を出る・戻す・やり直すと区切る）。1回の操作で何か所かが変わったとき
  （代理人を選ぶと住所なども入る、内容を打つと保管ファイル名も変わる、など）は、打っていた欄の1回の変更として扱い、
  まとめて戻す。
- 戻した・やり直した欄にカーソルを移す。
- 値は、ツールの側の get_state()・put_state(state) で出し入れする。state は (欄の名前 → 値, そのほか) の組で、
  そのほか（自動で入れた保管ファイル名など）も一緒に戻す。
"""
import tkinter as tk

MAX_STEPS = 200          # 覚える変更の数（古いものから捨てる）


class EditHistory:
    def __init__(self, root, get_state, put_state, focus=None):
        self.root = root
        self._get = get_state
        self._put = put_state
        self._focus = focus          # focus(欄の名前)
        self._names = {}             # 部品の名前（Tk のパス） → 欄の名前
        self.history = None          # 値の移り変わり（[0] は出したときの値）
        self.pos = 0
        self._open = None            # いま続けて打っている欄（その間の変更は1つにまとめる）
        self._job = None
        self._field = None           # 待っている変更を打った欄

    # ------------------------------------------------------------ つなぐ

    def watch(self, widget, name):
        """入力欄の部品に、Ctrl+Z・Ctrl+Y を付ける（Text の欄ごとの元に戻すより先に働かせる）。"""
        self._names[str(widget)] = name
        self.bind_keys(widget)
        widget.bind("<FocusOut>", lambda e: self._close_unit(), add="+")

    def bind_keys(self, widget):
        """Ctrl+Z・Ctrl+Y だけを付ける（一覧など、入力欄でない部品）。"""
        for seq in ("<Control-z>", "<Control-Z>"):
            widget.bind(seq, lambda e: (self.undo(), "break")[1])
        for seq in ("<Control-y>", "<Control-Y>"):
            widget.bind(seq, lambda e: (self.redo(), "break")[1])

    # ------------------------------------------------------------ 覚える

    def reset(self):
        """入力欄に新しく出した（または書き込んだ）値から、覚え直す。"""
        self._cancel()
        self.history = [self._get()]
        self.pos = 0
        self._open = None

    def clear(self):
        """何も出していないとき。"""
        self._cancel()
        self.history = None
        self.pos = 0
        self._open = None

    def changed(self):
        """入力欄の値が変わったときに呼ぶ（まとめて、少し後で覚える）。"""
        if self.history is None:
            return
        if self._field is None:
            self._field = self._focused_name()
        if self._job is None:
            try:
                self._job = self.root.after_idle(self._commit)
            except tk.TclError:
                pass

    def _focused_name(self):
        try:
            w = self.root.focus_get()
        except (KeyError, tk.TclError):     # Combobox の一覧を開いている間などは、取れないことがある
            return None
        return self._names.get(str(w)) if w is not None else None

    def _cancel(self):
        if self._job is not None:
            try:
                self.root.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None
        self._field = None

    def _commit(self):
        self._job = None
        field, self._field = self._field, None
        if self.history is None:
            return
        cur = self._get()
        if cur == self.history[self.pos]:
            return
        del self.history[self.pos + 1:]          # やり直せる分は捨てる
        if field is not None and field == self._open and self.pos > 0:
            self.history[self.pos] = cur         # 同じ欄で続けて打った分は1つにまとめる
        else:
            self.history.append(cur)
            self.pos += 1
            self._open = field
            if len(self.history) > MAX_STEPS + 1:
                del self.history[1]
                self.pos -= 1

    def _close_unit(self):
        """欄を出たら、次に打った分は新しい1つにする。"""
        if self._job is not None:
            self._cancel_keep_field()
            self._commit()
        self._open = None

    def _cancel_keep_field(self):
        try:
            self.root.after_cancel(self._job)
        except tk.TclError:
            pass
        self._job = None

    # ------------------------------------------------------------ 戻す・やり直す

    @property
    def can_undo(self):
        return self.history is not None and (self.pos > 0 or self._job is not None)

    def undo(self):
        if self._job is not None:
            self._cancel_keep_field()
            self._commit()
        if self.history is None or self.pos == 0:
            return False
        self.pos -= 1
        self._apply(self.history[self.pos], self.history[self.pos + 1])
        return True

    def redo(self):
        if self._job is not None:
            self._cancel_keep_field()
            self._commit()
        if self.history is None or self.pos >= len(self.history) - 1:
            return False
        self.pos += 1
        self._apply(self.history[self.pos], self.history[self.pos - 1])
        return True

    def _apply(self, state, other):
        self._open = None
        self._put(state)
        self._cancel()      # 戻した値を入れたことで起きた「変わった」は、覚えない
        if self._focus is not None:
            names = [k for k in state[0] if state[0].get(k) != other[0].get(k)]
            if names:
                try:
                    self._focus(names[0])
                except tk.TclError:
                    pass
