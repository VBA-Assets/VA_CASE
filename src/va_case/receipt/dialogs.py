"""VA Receipt の設定の画面（この PC の設定・事務所の設定）。"""
import tkinter as tk
from tkinter import ttk

from ..common.master import Table
from ..common.ui import theme
from ..common.ui.dialogs import SettingsDialog as BaseSettingsDialog
from ..common.ui.dialogs import TableEditor, center, office_buttons, wrapping_label
from . import model as m

TITLE = "VA Receipt"


class SettingsDialog(BaseSettingsDialog):
    """この PC の設定（共有データ・バックアップ・事務所のフォルダの場所）。"""

    APP_TITLE = TITLE
    FIELDS = [
        ("master_path", "共有データのファイル", "file",
         "事務所の共有フォルダに置く VA_Receipt.json。みなが同じファイルを指すようにします。"),
        ("backup_folder", "バックアップのフォルダ", "dir", "その日の最初に読み込んだときに写しを置きます。空ならバックアップしません。"),
        ("data_root", "事務所のフォルダの場所", "dir",
         "事務所で共有しているフォルダ（事件のフォルダ・スキャンのフォルダなどをまとめて置いているフォルダ）が、この PC で"
         "見える場所。ここに入れておくと、その中のフォルダは、ここからの相対で記録するので、PC ごとに場所が違っても"
         "（Mac でも）使えます。どの PC でも同じ場所（同じドライブ名）なら、空でかまいません。"),
    ]
    FILETYPES = {"master_path": [("VA Receipt の共有データ", "*.json"), ("すべて", "*.*")]}


class OfficeDialog(tk.Toplevel):
    """事務所の設定（種別と保管フォルダ・読込フォルダ・そのほか）。共有データに入るので、編集モードのときだけ直せる。
    OK を押すと self.result に、直したテーブル（テーブル名 → Table）が入る。"""

    def __init__(self, parent, tables, *, editable, data_root=None):
        super().__init__(parent)
        self.withdraw()
        self.title("事務所の設定（種別と保管フォルダ・読込フォルダなど）")
        self.transient(parent)
        self.result = None
        self.editable = editable
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=10)

        def page(title, note):
            f = ttk.Frame(nb, padding=8)
            nb.add(f, text=title)
            if note:
                wrapping_label(f, note, width=640).pack(fill="x", pady=(0, 6))
            return f

        f = page("種別と保管フォルダ", "種別ごとに、ファイルを保管するフォルダを決めます。入力欄で種別を選ぶと、その保管フォルダが"
                               "入ります。並べた順に、種別の選択肢に出ます（1つ目は、読み込んだファイルの種別の既定）。")
        self.types = TableEditor(f, m.TYPE_COLUMNS, tables[m.TYPES].rows, editable=editable,
                                 data_root=data_root, kinds=["text", "dir"],
                                 widths=[140, 480], title="種別と保管フォルダ")
        self.types.pack(fill="both", expand=True)

        f = page("読込フォルダ", "スキャンの保存先など、保管するファイルを読み込むフォルダ。「サブフォルダも」を「はい」にすると、"
                           "中のフォルダのファイルも読み込みます。")
        self.read_folders = TableEditor(f, m.READ_FOLDER_COLUMNS, tables[m.READ_FOLDERS].rows, editable=editable,
                                        data_root=data_root,
                                        kinds=["dir", ("choice", ["", m.YES])], widths=[520, 100], title="読込フォルダ")
        self.read_folders.pack(fill="both", expand=True)

        f = page("そのほか", "")
        state = "readonly" if editable else "disabled"
        ttk.Label(f, text="枝番").grid(row=0, column=0, sticky="e", padx=(0, 6), pady=4)
        self.branch_var = tk.StringVar(value=m.setting_value(tables, m.SET_BRANCH, m.BRANCH_WHEN_SAME))
        w = ttk.Combobox(f, textvariable=self.branch_var, values=[m.BRANCH_WHEN_SAME, m.BRANCH_ALWAYS], width=24,
                         state=state)
        w.grid(row=0, column=1, sticky="w", pady=4)
        theme.tab_stop(w, not editable)
        wrapping_label(f, "日時・相手先・金額が同じファイルの保管ファイル名に付ける番号（_1・_2）。「常に付加する」にすると、"
                          "1件目から _1 を付けます。", width=560).grid(row=1, column=1, sticky="we")
        ttk.Label(f, text="日時").grid(row=2, column=0, sticky="e", padx=(0, 6), pady=(12, 4))
        self.date_var = tk.StringVar(value=m.date_fallback(tables))
        w = ttk.Combobox(f, textvariable=self.date_var, values=[m.DATE_FROM_FILE, m.DATE_BLANK], width=24,
                         state=state)
        w.grid(row=2, column=1, sticky="w", pady=(12, 4))
        theme.tab_stop(w, not editable)
        wrapping_label(f, "ファイル名が日付（例：20251101）で始まらないファイルを読み込んだときの「日時」。「ファイルの日付」は"
                          "ファイルの更新日（スキャンした日など）を入れ、「空欄」は入れずに、保管するときに入れてもらいます。",
                       width=560).grid(row=3, column=1, sticky="we")
        ttk.Label(f, text=m.SET_SKIP_PREFIX).grid(row=4, column=0, sticky="ne", padx=(0, 6), pady=(12, 4))
        self.skip_text = tk.Text(f, width=40, height=4, font=theme.field_font(self))
        self.skip_text.insert("1.0", "\n".join(m.setting_values(tables, m.SET_SKIP_PREFIX)))
        self.skip_text.grid(row=4, column=1, sticky="w", pady=(12, 4))
        wrapping_label(f, "1行に1つ。ほかのソフトが作るファイルなど、保管しないものの名前の先頭。", width=560).grid(
            row=5, column=1, sticky="we")
        f.columnconfigure(1, weight=1)
        if not editable:
            self.skip_text.configure(state="disabled", background=theme.READONLY_BG)
            theme.tab_stop(self.skip_text, True)

        office_buttons(self, editable, self._ok)
        self.bind("<Escape>", lambda e: self.destroy())
        center(self, parent)
        self.deiconify()   # 本体を止めない（開いたまま本体の「編集を始める」を押せる。2026-11-11）

    def _ok(self):
        settings_rows = [[m.SET_BRANCH, self.branch_var.get()], [m.SET_DATE_FALLBACK, self.date_var.get()]]
        settings_rows += [[m.SET_SKIP_PREFIX, v.strip()] for v in self.skip_text.get("1.0", "end-1c").split("\n")
                          if v.strip()]
        self.result = {
            m.TYPES: Table(list(m.TYPE_COLUMNS), [r for r in self.types.rows if r[0]]),
            m.READ_FOLDERS: Table(list(m.READ_FOLDER_COLUMNS), [r for r in self.read_folders.rows if r[0]]),
            m.SETTINGS: Table(list(m.SETTING_COLUMNS), settings_rows),
        }
        self.destroy()
