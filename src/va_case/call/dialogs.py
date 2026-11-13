"""VA Call の設定の画面（この PC の設定・事務所の設定）。"""
import getpass
import tkinter as tk
from tkinter import ttk

from ..common.master import Table
from ..common.ui import theme
from ..common.ui.dialogs import SettingsDialog as BaseSettingsDialog
from ..common.ui.dialogs import TableEditor, center, office_buttons, wrapping_label
from . import model as m

TITLE = "VA Call"


class SettingsDialog(BaseSettingsDialog):
    """この PC の設定（共有データ・バックアップ）。"""

    APP_TITLE = TITLE
    FIELDS = [
        ("master_path", "共有データのファイル", "file",
         "事務所の共有フォルダに置く VA_Call.json。みなが同じファイルを指すようにします。"),
        ("backup_folder", "バックアップのフォルダ", "dir", "その日の最初に読み込んだときに写しを置きます。空ならバックアップしません。"),
    ]
    FILETYPES = {"master_path": [("VA Call の共有データ", "*.json"), ("すべて", "*.*")]}


class OfficeDialog(tk.Toplevel):
    """事務所の設定（所員・選択肢）。共有データに入るので、編集モードのときだけ直せる。
    OK を押すと self.result に、直したテーブル（テーブル名 → Table）が入る。"""

    def __init__(self, parent, tables, *, editable):
        super().__init__(parent)
        self.withdraw()
        self.title("事務所の設定（所員・選択肢）")
        self.transient(parent)
        self.result = None
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=10)

        f = ttk.Frame(nb, padding=8)
        nb.add(f, text="所員")
        wrapping_label(f, "電話メモの入力者・宛先・確認者に出る所員と、メールを送るアドレス。「ユーザー名（Windows）」を入れて"
                          "おくと、新しいメモの入力者に、その PC を使っている人の所員名が入ります。"
                          f"（この PC のユーザー名：{getpass.getuser()}）", width=640).pack(fill="x", pady=(0, 6))
        self.staff = TableEditor(f, m.STAFF_COLUMNS, tables[m.STAFF].rows, editable=editable,
                                 widths=[140, 280, 180], title="所員")
        self.staff.pack(fill="both", expand=True)

        f = ttk.Frame(nb, padding=8)
        nb.add(f, text="選択肢")
        wrapping_label(f, "1行に1つずつ入れます。並べた順に、入力欄の選択肢に出ます。", width=640).grid(
            row=0, column=0, columnspan=3, sticky="we", pady=(0, 6))
        self.texts = {}
        font = theme.field_font(self)
        for ci, item in enumerate(m.CHOICE_ITEMS):
            ttk.Label(f, text=item).grid(row=1, column=ci, sticky="w")
            t = tk.Text(f, width=22, height=8, font=font, wrap="none", undo=True)
            t.insert("1.0", "\n".join(m.choice_values(tables, item)))
            t.grid(row=2, column=ci, sticky="nw", padx=(0, 8))
            if not editable:
                t.configure(state="disabled", background=theme.READONLY_BG)
                theme.tab_stop(t, True)
            self.texts[item] = t

        office_buttons(self, editable, self._ok)
        self.bind("<Escape>", lambda e: self.destroy())
        center(self, parent)
        self.deiconify()   # 本体を止めない（開いたまま本体の「編集を始める」を押せる。2026-11-11）

    def _ok(self):
        choices = [[item, v.strip()] for item, t in self.texts.items()
                   for v in t.get("1.0", "end-1c").split("\n") if v.strip()]
        self.result = {
            m.STAFF: Table(list(m.STAFF_COLUMNS), [r for r in self.staff.rows if r[0]]),
            m.CHOICES: Table(list(m.CHOICE_COLUMNS), choices),
        }
        self.destroy()
