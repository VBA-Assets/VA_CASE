"""VA Filing の設定の画面（この PC の設定・事務所の設定）。"""
import tkinter as tk
from tkinter import ttk

from ..common.master import Table
from ..common.ui import theme
from ..common.ui.dialogs import SettingsDialog as BaseSettingsDialog
from ..common.ui.dialogs import TableEditor, browse_into, center, office_buttons, wrapping_label
from . import model as m

TITLE = "VA Filing"


class SettingsDialog(BaseSettingsDialog):
    """この PC の設定（共有データ・バックアップ・VA Case の共有データ・事務所のフォルダの場所）。"""

    APP_TITLE = TITLE
    FIELDS = [
        ("master_path", "共有データのファイル", "file",
         "事務所の共有フォルダに置く VA_Filing.json。みなが同じファイルを指すようにします。"),
        ("backup_folder", "バックアップのフォルダ", "dir", "その日の最初に読み込んだときに写しを置きます。空ならバックアップしません。"),
        ("case_master_path", "VA Case の共有データ", "file",
         "VA Case の VA_Case.json。事件呼名・データフォルダ・担当区分を読みます（読むだけで、書き込みません）。"
         "VA Case を使わない場合は、空のままにします。"),
        ("data_root", "事務所のフォルダの場所", "dir",
         "事務所で共有しているフォルダ（事件のフォルダ・スキャンのフォルダなどをまとめて置いているフォルダ）が、この PC で"
         "見える場所。ここに入れておくと、その中のフォルダは、ここからの相対で記録するので、PC ごとに場所が違っても"
         "（Mac でも）使えます。どの PC でも同じ場所（同じドライブ名）なら、空でかまいません。"),
    ]
    FILETYPES = {"master_path": [("VA Filing の共有データ", "*.json"), ("すべて", "*.*")],
                 "case_master_path": [("VA Case の共有データ", "*.json"), ("すべて", "*.*")]}


class OfficeDialog(tk.Toplevel):
    """事務所の設定（保管先・読込フォルダ・複製作成先・特別な写し・そのほか）。共有データに入るので、編集モードの
    ときだけ直せる。OK を押すと self.result に、直したテーブル（テーブル名 → Table）が入る。"""

    def __init__(self, parent, tables, *, editable, tantou_choices=(), data_root=None):
        super().__init__(parent)
        self.withdraw()
        self.title("事務所の設定")
        self.transient(parent)
        self.result = None
        self.editable = editable
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=10)

        def page(title, note):
            f = ttk.Frame(nb, padding=8)
            nb.add(f, text=title)
            wrapping_label(f, note, width=720).pack(fill="x", pady=(0, 6))
            return f

        # 保管先のタブを一番左に置く（2026-11-12 班長指示）
        f = page("保管先", "事件呼名ごとに覚えた保管先。VA Case の事件は、データフォルダと違う場所に保管したときに覚えます。"
                        "「（データフォルダ）\\scan」は、その事件のデータフォルダの中の scan フォルダのこと。"
                        "保管フォルダが見つからない行は、次に保管するときに消えます。ここで直したり消したりもできます。")
        self.dest = TableEditor(f, m.DEST_COLUMNS, tables[m.DEST].rows, editable=editable, data_root=data_root,
                                kinds=["text", "dir", ("choice", list(tantou_choices))],
                                widths=[220, 340, 90], title="保管先")
        self.dest.pack(fill="both", expand=True)

        f = page("読込フォルダ", "スキャンの保存先など、保管するファイルを読み込むフォルダ。「サブフォルダも」を「はい」にすると、"
                           "中のフォルダのファイルも読み込みます。")
        self.read_folders = TableEditor(f, m.READ_FOLDER_COLUMNS, tables[m.READ_FOLDERS].rows, editable=editable,
                                        data_root=data_root,
                                        kinds=["dir", ("choice", ["", m.YES])], widths=[520, 100], title="読込フォルダ")
        self.read_folders.pack(fill="both", expand=True)

        f = page("複製作成先", "保管したときに、担当区分ごとに、ショートカットかコピーを置くフォルダ（担当者の未確認フォルダなど）。"
                          "1行に1つのフォルダを入れます。ショートカットは Windows でだけ作ります。")
        self.copy_targets = TableEditor(f, m.COPY_TARGET_COLUMNS, tables[m.COPY_TARGETS].rows, editable=editable,
                                        data_root=data_root,
                                        kinds=[("choice", list(tantou_choices)), ("choice", list(m.KINDS)), "dir"],
                                        widths=[110, 110, 420], title="複製作成先")
        self.copy_targets.pack(fill="both", expand=True)

        f = page("特別な写し", "内容にこの語が入っているときに、写しを置くフォルダ（例：職務上請求・弁護士会照会）。"
                          "フォルダが空の行は、写しを作りません。")
        self.special = TableEditor(f, m.SPECIAL_COLUMNS, tables[m.SPECIAL].rows, editable=editable, data_root=data_root,
                                   kinds=["text", "dir"], widths=[140, 500], title="特別な写し")
        self.special.pack(fill="both", expand=True)

        f = page("そのほか", "")
        ttk.Label(f, text=m.SET_SKIP_PREFIX + "（1行に1つ。ほかのソフトが作るファイルなど、保管しないものの名前の先頭）").pack(
            anchor="w")
        self.skip_text = tk.Text(f, width=60, height=5, font=theme.field_font(self))
        self.skip_text.insert("1.0", "\n".join(m.setting_values(tables, m.SET_SKIP_PREFIX)))
        self.skip_text.pack(anchor="w", pady=(2, 10))
        ttk.Label(f, text=m.SET_PICK_START).pack(anchor="w")
        row = ttk.Frame(f)
        row.pack(anchor="w", pady=(2, 0))
        self.pick_var = tk.StringVar(value=m.setting_value(tables, m.SET_PICK_START))
        ttk.Entry(row, textvariable=self.pick_var, width=60).pack(side="left")
        b = ttk.Button(row, text="参照…", style="Small.TButton",
                       command=lambda: browse_into(self.pick_var, "dir", self, data_root=data_root))
        b.pack(side="left", padx=(6, 0))
        if not editable:
            self.skip_text.configure(state="disabled")
            theme.tab_stop(self.skip_text, True)
            b.state(["disabled"])

        office_buttons(self, editable, self._ok)
        self.bind("<Escape>", lambda e: self.destroy())
        center(self, parent)
        self.deiconify()   # 本体を止めない（開いたまま本体の「編集を始める」を押せる。2026-11-11）

    def _ok(self):
        settings_rows = [[m.SET_SKIP_PREFIX, v.strip()] for v in self.skip_text.get("1.0", "end-1c").split("\n")
                         if v.strip()]
        if self.pick_var.get().strip():
            settings_rows.append([m.SET_PICK_START, self.pick_var.get().strip()])
        self.result = {
            m.READ_FOLDERS: Table(list(m.READ_FOLDER_COLUMNS), [r for r in self.read_folders.rows if r[0]]),
            m.COPY_TARGETS: Table(list(m.COPY_TARGET_COLUMNS), [r for r in self.copy_targets.rows if r[0] and r[2]]),
            m.SPECIAL: Table(list(m.SPECIAL_COLUMNS), [r for r in self.special.rows if r[0]]),
            m.DEST: Table(list(m.DEST_COLUMNS), [r for r in self.dest.rows if r[0]]),
            m.SETTINGS: Table(list(m.SETTING_COLUMNS), settings_rows),
        }
        self.destroy()
