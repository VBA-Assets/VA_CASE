"""事務所の設定の画面を出す仕組み（4つのツールで共通。SharedApp が受け継ぐ）。

2026-11-12 のリファクタリングで、shared_app.py から分けた（中身は変えていない）。
- 画面を出し、閉じるまで待つ（本体は止めないので、開いたまま本体の「編集を始める」「編集を終える」を押せる。
  モードが変わったら、その形で開き直す。2026-11-11 班長指示）
- 画面の大きさと表の列の幅を、この PC の設定に覚える（2026-11-12 班長指示）
- 書き込んでいない変更があるか（編集を終えるときの確かめ）

使うもの（SharedApp にあるもの）：self.root・self.cfg・self.settings・self.editing・self.open_office()・self._focus_table()。
"""
import tkinter as tk
from tkinter import ttk

from . import theme
from .dialogs import widget_snapshot


class OfficeHost:
    def init_office_state(self):
        self._office_dlg = None     # 開いている事務所の設定の画面（run_office_dialog）
        self._office_restore = None # 開き直すときの、画面の位置と開いていたタブ

    def run_office_dialog(self, make):
        """事務所の設定の画面を出し、閉じるまで待つ。make(editable) で画面を作る。OK を押したら dlg.result を返す。

        画面は本体を止めないので、開いたまま本体の「編集を始める」「編集を終える」を押せる。モードが変わったら、
        その形で開き直す（_sync_office。2026-11-11 班長指示「「編集を始める」のボタンは、本体側のボタンを使用する」）。
        すでに開いていれば、前に出すだけ。
        """
        old = self._office_dlg
        if old is not None and old.winfo_exists():
            old.deiconify()
            old.lift()
            old.focus_set()
            return None
        editable = self.editing
        dlg = make(editable)
        dlg.office_editable = editable
        restore, self._office_restore = self._office_restore, None
        if restore:
            geometry, tab = restore
            try:
                dlg.geometry(geometry)
                nb = self._office_notebook(dlg)
                if nb is not None and tab is not None:
                    nb.select(tab)
            except tk.TclError:
                pass
        else:
            self._restore_office_size(dlg)
        self._restore_office_widths(dlg)
        seen = self._watch_office_layout(dlg)
        dlg.office_start = widget_snapshot(dlg)
        self._office_dlg = dlg
        self.root.wait_window(dlg)
        if self._office_dlg is dlg:
            self._office_dlg = None
        self._remember_office_layout(seen)
        self._focus_table()
        return getattr(dlg, "result", None)

    @staticmethod
    def _office_notebook(dlg):
        return next((c for c in dlg.winfo_children() if isinstance(c, ttk.Notebook)), None)

    # 事務所の設定の画面の大きさと、表の列の幅を、この PC の設定に覚える（2026-11-12 班長指示「フォームのサイズや
    # 列幅の設定を保存する」。一覧の列の幅と同じく、利用者ごと。4つのツールとも）

    def _office_tables(self, dlg):
        """画面の中の表（Treeview）と、その名前（タブの名前。1つのタブに表が2つ以上あれば番号を添える）の並び。"""
        nb = self._office_notebook(dlg)
        if nb is None:
            return []
        out = []
        for tab in nb.tabs():
            frame = dlg.nametowidget(tab)
            trees, stack = [], [frame]
            while stack:
                w = stack.pop(0)
                if isinstance(w, ttk.Treeview):
                    trees.append(w)
                stack += w.winfo_children()
            name = nb.tab(tab, "text")
            out += [(name if i == 0 else f"{name}{i + 1}", t) for i, t in enumerate(trees)]
        return out

    def _restore_office_size(self, dlg):
        size = getattr(self.cfg, "office_size", "")
        if not size:
            return
        try:
            w, h = (int(v) for v in size.split("x"))
            # 画面より大きくしない（解像度の低い PC に替えたときなど）
            w = min(w, dlg.winfo_screenwidth())
            h = min(h, dlg.winfo_screenheight() - 40)
            dlg.geometry(f"{w}x{h}")
            dlg.update_idletasks()
            parent = self.root
            x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
            y = parent.winfo_rooty() + (parent.winfo_height() - h) // 3
            dlg.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")
        except (tk.TclError, ValueError):
            pass

    def _restore_office_widths(self, dlg):
        saved = getattr(self.cfg, "office_column_widths", None) or {}
        for name, tree in self._office_tables(dlg):
            for c in tree["columns"]:
                key = f"{name}/{c}"
                if key in saved:
                    tree.column(c, width=theme.px(self.root, saved[key]))

    def _watch_office_layout(self, dlg):
        """閉じた後は大きさも列の幅も読めないので、変わるたびに控えておく。"""
        seen = {}
        tables = self._office_tables(dlg)
        s = theme.scale(self.root)

        def size(event=None):
            if event is None or event.widget is dlg:
                now = f"{dlg.winfo_width()}x{dlg.winfo_height()}"
                seen.setdefault("start", now)       # 開いたときの大きさ（変えなければ覚えない）
                seen["size"] = now

        def widths(event=None):
            # 右端の列（画面の幅に合わせて伸び縮みする列）は覚えない
            seen["widths"] = {f"{name}/{c}": int(round(int(t.column(c, "width")) / s))
                              for name, t in tables for c in t["columns"] if not int(t.column(c, "stretch"))}
        dlg.bind("<Configure>", size, add="+")
        for _name, t in tables:
            t.bind("<ButtonRelease-1>", widths, add="+")   # 列の境目を動かし終えたとき
        return seen

    def _remember_office_layout(self, seen):
        if not seen or not hasattr(self.cfg, "office_size"):
            return
        old = (self.cfg.office_size, dict(self.cfg.office_column_widths))
        if "size" in seen and seen["size"] != seen.get("start"):
            self.cfg.office_size = seen["size"]
        if "widths" in seen:
            self.cfg.office_column_widths = {**self.cfg.office_column_widths, **seen["widths"]}
        if (self.cfg.office_size, self.cfg.office_column_widths) == old:
            return          # 変わっていなければ書かない
        try:
            self.settings.save(self.cfg)
        except OSError:
            pass

    def office_dirty(self):
        """開いている事務所の設定の画面（編集の形）に、書き込んでいない変更があるか。"""
        dlg = self._office_dlg
        if dlg is None or not dlg.winfo_exists() or not dlg.office_editable:
            return False
        return widget_snapshot(dlg) != dlg.office_start

    def _sync_office(self):
        """モードが変わったら、開いている事務所の設定の画面を、そのモードの形で開き直す（位置と開いていたタブはそのまま）。"""
        dlg = self._office_dlg
        if dlg is None or not dlg.winfo_exists() or dlg.office_editable == self.editing:
            return
        nb = self._office_notebook(dlg)
        try:
            tab = nb.index("current") if nb is not None else None
        except tk.TclError:
            tab = None
        self._office_restore = (dlg.geometry(), tab)
        self._office_dlg = None
        dlg.destroy()
        self.root.after_idle(self.open_office)
