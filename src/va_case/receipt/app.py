"""VA Receipt の画面（一覧・その下の入力欄・ファイルの読み込み・保管・保管の取り消し・CSV）。

VA Filing と同じ画面と動き（common/ui/file_store_app.py。2026-11-09 に示した）。一覧で行を選ぶと、下の入力欄に
その行が出る。種別・日時・相手先・金額を確かめて「保管する」を押すと、次の未保管の行へ進む。
ここには VA Receipt だけのこと（種別ごとの保管フォルダ・保管ファイル名と枝番の作り方・金額のそろえ方）を書く。
"""
import tkinter as tk
from tkinter import messagebox, ttk

from ..common.ui import autocomplete
from ..common.ui.dialogs import WrappedEntry
from ..common.ui.file_store_app import FileStoreApp, StoreCancelled
from ..common.ui.shared_app import prepare_process
from . import model as m
from . import settings
from .dialogs import TITLE, OfficeDialog, SettingsDialog

# 一覧の列の並びは、領収書等ファイル保管 Ver403 の表「保管」と同じ（共有データの列の順と同じ。
# 2026-11-12 班長指示「VA Receiptのリストのフィールドの並び順をVA領収書保管と同一にする」）
DISPLAY_COLUMNS = list(m.STORE_COLUMNS)
COLUMN_WIDTHS = {"日時": 80, "種別": 90, "相手先": 160, "金額": 80, "枝番": 40, "読込ファイル名": 220,
                 "保管ファイル名": 280, "保管フォルダ名": 240, "保管日時": 110, "備考": 140, "読込フォルダ名": 200,
                 "番号": 72}
PANEL_FIELDS = ("種別", "日時", "相手先", "金額", "枝番", "保管フォルダ名", "保管ファイル名", "備考")
# 画面の幅いっぱいに広げる欄（VA Filing と同じく、同じ幅で、できるだけ広く）
WIDE_FIELDS = ("相手先", "保管フォルダ名", "保管ファイル名", "備考")
# オートコンプリートを付ける欄（2026-11-09 班長決定）
AUTOCOMPLETE_FIELDS = ("相手先",)


class ReceiptApp(FileStoreApp):
    TITLE = TITLE
    ICON_FILE = "VA_Receipt.ico"      # ウィンドウ・タスクバーのアイコン（assets。scripts\generate_icons.py）
    TOOL = m.TOOL
    SCHEMA = m.SCHEMA
    MASTER_FILE_NAME = m.MASTER_FILE_NAME
    MODEL = m
    DISPLAY_COLUMNS = DISPLAY_COLUMNS
    COLUMN_WIDTHS = COLUMN_WIDTHS
    PANEL_FIELDS = PANEL_FIELDS
    OFFICE_MENU_LABEL = "事務所の設定（種別と保管フォルダ・読込フォルダなど）…"
    ABOUT_LINE = "領収書などのファイルを、種別ごとのフォルダに保管する"
    CSV_NOTE = "CSV には、相手先・金額などがそのまま入っています。"
    FIRST_FIELD = "種別"

    def __init__(self, root):
        self.auto_branch = ""       # 自動で入れた枝番（利用者が直したかを見分ける）
        super().__init__(root, settings)

    # ------------------------------------------------------------ 入力欄

    def _build_fields(self, p, font):
        r = 1
        for name, width in (("種別", 24), ("日時", 16), ("相手先", 20), ("金額", 16), ("枝番", 6),
                            ("保管フォルダ名", 20), ("保管ファイル名", 20), ("備考", 20)):
            ttk.Label(p, text={"保管フォルダ名": "保管フォルダ"}.get(name, name),
                      style=autocomplete.label_style(name, AUTOCOMPLETE_FIELDS)).grid(row=r, column=0, sticky="e",
                                                                                     padx=(0, 6), pady=2)
            if name == "種別":
                w = ttk.Combobox(p, textvariable=self.vars[name], width=width, font=font)
                w.choose_only = True      # 種別は、事務所の設定の表から選ぶだけ
            elif name in ("保管フォルダ名", "保管ファイル名"):
                w = WrappedEntry(p, self.vars[name], width=width, height=2, font=font)
            else:
                w = ttk.Entry(p, textvariable=self.vars[name], width=width, font=font)
            w.grid(row=r, column=1, sticky="we" if name in WIDE_FIELDS else "w", pady=2)
            self.widgets[name] = w
            self.rows_of[name] = r
            r += 1
        self.widgets["種別"].bind("<<ComboboxSelected>>", lambda e: self._kind_chosen())
        for name in ("日時", "相手先", "金額"):
            self.widgets[name].bind("<KeyRelease>", lambda e: self._update_name(rebranch=True))
        self.widgets["枝番"].bind("<KeyRelease>", lambda e: self._update_name())
        self.widgets["金額"].bind("<Return>", lambda e: (self.store_button.focus_set(), "break")[1])
        # 相手先は、これまでの相手先から補う（オートコンプリート。2026-11-09 班長決定）
        autocomplete.attach_entry(self.widgets["相手先"], lambda: autocomplete.column_values(self.rows, m.COL["相手先"]),
                                  on_complete=lambda: self._update_name(rebranch=True))
        self.folder_buttons(p, self.rows_of["保管フォルダ名"])
        # 欄の右の注記（日時「例：20251101」・金額「「1,100円」なども、数字だけにそろえます。」・保管ファイル名「日時・相手先・
        # 金額・枝番から自動で入ります（直せます）。」）は、2026-11-13 になくした（班長指摘「そもそも、これは不要ではないか？」
        # 「「例：20251101」はVA FILINGにはない」。日時は読み込んだときに入り、金額は保管するときに数字だけにそろえ、
        # 数字でなければ知らせる。使い方はマニュアルに書く）
        return r

    def _name_after_date(self):
        self._update_name(rebranch=True)

    def _draft_extra(self):
        return self.auto_branch

    def _restore_draft_extra(self, extra):
        self.auto_branch = extra or ""

    def _after_show_row(self, row, draft):
        if not draft:
            self.auto_branch = row[m.COL["枝番"]]

    def on_data(self, data):
        super().on_data(data)
        self.widgets["種別"].configure(values=m.type_names(data.tables))

    def _kind_chosen(self):
        self.vars["保管フォルダ名"].set(m.type_folder(self.data.tables, self.vars["種別"].get()))
        self._update_name(rebranch=True)

    def _fill_defaults(self):
        """未保管の行で、保管フォルダ・枝番・保管ファイル名が空なら（読み込んだ行、元に戻した行、CSV から取り込んだ行
        など）、種別の保管フォルダと、枝番・保管ファイル名を入れる。"""
        if not self.vars["保管フォルダ名"].get() and self.data is not None:
            self.vars["保管フォルダ名"].set(m.type_folder(self.data.tables, self.vars["種別"].get()))
        self._update_name(rebranch=not self.vars["枝番"].get())

    def _amount(self):
        a = m.normalize_amount(self.vars["金額"].get())
        return a if a is not None else self.vars["金額"].get().strip()

    def _update_name(self, rebranch=False):
        """枝番と保管ファイル名を作り直す（利用者が直していなければ）。"""
        if self.current is None or self.current_stored or self.data is None:
            return
        row = m.row_by_number(self.data.tables, self.current)
        if row is None:
            return
        read_name = row[m.COL["読込ファイル名"]]
        dt, partner, amount = self.vars["日時"].get().strip(), self.vars["相手先"].get().strip(), self._amount()
        if rebranch and self.vars["枝番"].get() in ("", self.auto_branch):
            folder = self._resolve(self.vars["保管フォルダ名"].get())
            exists = (lambda name: (folder / name).exists()) if folder is not None and folder.is_dir() else None
            branch = str(m.suggest_branch(self.data.tables, self.current, read_name, dt, partner, amount, exists))
            self.vars["枝番"].set(branch)
            self.auto_branch = branch
        new = m.stored_file_name(read_name, dt, partner, amount, self.vars["枝番"].get().strip())
        if self.vars["保管ファイル名"].get() in ("", self.auto_name):
            self.vars["保管ファイル名"].set(new)
        self.auto_name = new

    # ------------------------------------------------------------ 保管

    def _prepare_store(self, row, v):
        number = row[m.COL["番号"]]

        def stop(msg, field=None):
            messagebox.showinfo(TITLE, msg, parent=self.root)
            if field:
                self.widgets[field].focus_set()
            raise StoreCancelled

        if not v["種別"]:
            stop("種別を選んでください。", "種別")
        if not v["日時"]:
            stop("日時を入れてください。", "日時")
        if not m.valid_date_text(v["日時"]):
            stop("日時を読めません。2025/11/1、R7.11.1、20251101 などの形で入れてください。", "日時")
        if not v["相手先"]:
            stop("相手先を入れてください。", "相手先")
        amount = m.normalize_amount(v["金額"])
        if amount == "":   # 金額のない保管はしない（2026-11-12 班長指摘「金額が入力されていなくても保存できてしまう」）
            stop("金額を入れてください。", "金額")
        if amount is None:
            stop("金額を、数字で入れてください（「1,100円」などは、数字だけにそろえます）。", "金額")
        if v["枝番"] and not v["枝番"].isdigit():
            stop("枝番は、数字で入れてください（付けないときは 0 か空）。", "枝番")
        if not v["保管フォルダ名"]:
            stop("保管フォルダを選んでください（事務所の設定で、種別ごとの保管フォルダを決めておくと入ります）。")
        file_name = v["保管ファイル名"]
        if amount != v["金額"] and file_name == self.auto_name:   # 金額をそろえた名前にする
            file_name = m.stored_file_name(row[m.COL["読込ファイル名"]], v["日時"], v["相手先"], amount, v["枝番"])
        problem = m.check_file_name(file_name)
        if problem:
            stop(problem)

        def transform(t):
            return m.mark_stored(t, number, kind=v["種別"], dt=v["日時"], partner=v["相手先"], amount=amount,
                                 branch=v["枝番"] or "0", folder=v["保管フォルダ名"], file_name=file_name, note=v["備考"])
        return dict(folder=v["保管フォルダ名"], file_name=file_name, targets=[], specials=[], transform=transform,
                    notes=[])

    # ------------------------------------------------------------ 設定

    def _settings_dialog(self):
        return SettingsDialog(self.root, settings.ReceiptConfig(**vars(self.cfg)))

    def open_office(self):
        if self.data is None:
            return
        result = self.run_office_dialog(lambda editable: OfficeDialog(self.root, self.data.tables, editable=editable,
                                                                       data_root=self.cfg.data_root))
        if result:
            self.write_office(result)


def main():
    prepare_process("VBAAssets.VAReceipt.Source")
    root = tk.Tk()
    ReceiptApp(root)
    root.mainloop()


