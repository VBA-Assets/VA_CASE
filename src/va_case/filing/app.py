"""VA Filing の画面（一覧・その下の入力欄・ファイルの読み込み・保管・保管の取り消し・CSV）。

一覧で行を選ぶと、下の入力欄にその行が出る。事件呼名を選び、内容を入れて「保管する」を押すと、次の未保管の行へ進む
（2026-11-09 班長決定）。保管の書き込みは裏で行い、書き込み中に次の行を保管すると、待ち行列に入れて順に行う。
読み込み・編集モード・書き込みなどの仕組みは4つのツールで共通（common/ui/shared_app.py）、一覧と入力欄・保管・元に
戻す・読み込みの仕組みは VA Receipt と共通（common/ui/file_store_app.py）。ここには VA Filing だけのこと（VA Case の
事件から選ぶ保管先・ショートカットと写し・保管ファイル名の作り方）を書く。
閲覧モードでは見るだけ（入力欄を直せず、保管・保管の取り消し・読み込みもできない。2026-11-09 班長決定。VA Case と同じ）。
"""
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from ..case import model as case_model
from ..common import dates
from ..common.errors import SharedError, describe
from ..common.master import read_master
from ..common.search import normalize
from ..common.ui import autocomplete
from ..common.ui.dialogs import WrappedEntry
from ..common.ui.file_store_app import FileStoreApp, StoreCancelled
from ..common.ui.shared_app import prepare_process
from . import model as m
from . import settings
from .dialogs import TITLE, OfficeDialog, SettingsDialog

# 一覧の列の並びは、ファイル保管 Ver708 の表「保管」と同じ（2026-11-12 班長指示「VA Filingもフィールドの並び順を
# VAファイル保管と同一にする」。共有データの列の順と同じ）
DISPLAY_COLUMNS = list(m.STORE_COLUMNS)
COLUMN_WIDTHS = {"日時": 96, "読込ファイル名": 220, "事件呼名": 170, "内容": 170, "保管ファイル名": 300, "保管フォルダ名": 240,
                 "複製作成先": 70, "保管日時": 110, "備考": 140, "読込フォルダ名": 200, "番号": 96}
PANEL_FIELDS = ("日時", "事件呼名", "内容", "保管フォルダ名", "保管ファイル名", "複製作成先", "備考")
# 画面の幅いっぱいに広げる欄（4つとも同じ幅。2026-11-09 班長指示「できるだけ広くする」）
WIDE_FIELDS = ("内容", "保管フォルダ名", "保管ファイル名", "備考")
# オートコンプリートを付ける欄（2026-11-09 班長決定。事件呼名は 2026-11-12 班長指示で足した）
AUTOCOMPLETE_FIELDS = ("事件呼名", "内容")


class FilingApp(FileStoreApp):
    TITLE = TITLE
    ICON_FILE = "VA_Filing.ico"      # ウィンドウ・タスクバーのアイコン（assets。scripts\generate_icons.py）
    TOOL = m.TOOL
    SCHEMA = m.SCHEMA
    MASTER_FILE_NAME = m.MASTER_FILE_NAME
    MODEL = m
    DISPLAY_COLUMNS = DISPLAY_COLUMNS
    COLUMN_WIDTHS = COLUMN_WIDTHS
    PANEL_FIELDS = PANEL_FIELDS
    ABOUT_LINE = "受け取ったファイルを、事件のフォルダに保管する"
    CSV_NOTE = "CSV には、事件呼名などがそのまま入っています。"
    FIRST_FIELD = "事件呼名"

    def __init__(self, root):
        self.case_tables = None     # VA Case の共有データのテーブル（読むだけ）
        self.case_error = ""
        self.candidates = []
        self.cand = None            # 入力欄で選んでいる保管先（Candidate）
        super().__init__(root, settings)

    # ------------------------------------------------------------ 入力欄

    def _build_fields(self, p, font):
        r = 1
        for name, width in (("日時", 16), ("事件呼名", 50), ("内容", 20), ("保管フォルダ名", 20), ("保管ファイル名", 20),
                            ("複製作成先", 50), ("備考", 20)):   # 複製作成先は事件呼名と同じ幅（2026-11-09 班長指示）
            ttk.Label(p, text={"保管フォルダ名": "保管フォルダ"}.get(name, name),
                      style=autocomplete.label_style(name, AUTOCOMPLETE_FIELDS)).grid(row=r, column=0, sticky="e",
                                                                                     padx=(0, 6), pady=2)
            if name in ("事件呼名", "複製作成先"):
                w = ttk.Combobox(p, textvariable=self.vars[name], width=width, font=font)
            elif name in ("保管フォルダ名", "保管ファイル名"):
                # 長いパス・名前の全体が見えるよう、2行の高さで折り返す（2026-11-09 班長指示）
                w = WrappedEntry(p, self.vars[name], width=width, height=2, font=font)
            else:
                w = ttk.Entry(p, textvariable=self.vars[name], width=width, font=font)
            w.grid(row=r, column=1, sticky="we" if name in WIDE_FIELDS else "w", pady=2)
            self.widgets[name] = w
            self.rows_of[name] = r
            r += 1
        self.case_box = self.widgets["事件呼名"]
        self.case_box.bind("<<ComboboxSelected>>", lambda e: self._case_chosen())
        self.case_box.bind("<KeyRelease>", self._filter_cases)
        self.case_box.bind("<FocusOut>", lambda e: self._case_chosen(only_if_changed=True))
        self.case_box.bind("<Return>", lambda e: (self._case_chosen(), self.widgets["内容"].focus_set(), "break")[2])
        for name in ("日時", "内容"):
            self.widgets[name].bind("<KeyRelease>", lambda e: self._update_name())
        self.widgets["内容"].bind("<Return>", lambda e: (self.store_button.focus_set(), "break")[1])
        # 内容は、これまでの内容から補う（オートコンプリート。2026-11-09 班長決定）
        autocomplete.attach_entry(self.widgets["内容"], lambda: autocomplete.column_values(self.rows, m.COL["内容"]),
                                  on_complete=self._update_name)
        # 事件呼名も、選ぶ欄の候補（VA Case の事件と、保管先の表の VA Case にない保管先）から補う（2026-11-12 班長指示
        # 「VA filingの事件呼名もオートコンプリートの対象にする。また、「保管先」リストから選択できるようにもする」）。
        # 補っただけでは保管先を決めない。Enter・Tab で決めたときに、今までどおり保管フォルダ・複製作成先を入れる
        # （補った後に打ち続けて別の名前にしたときに、補った候補の保管フォルダが残らないように）
        autocomplete.attach_entry(self.case_box, lambda: [c.label for c in self.candidates])
        # 欄のすぐ右に置く（2026-11-09 班長指摘「注記が1行下に配置されている」）
        self.folder_buttons(p, self.rows_of["保管フォルダ名"])
        # 保管ファイル名の右の注記（「日時・事件呼名・内容から自動で入ります（直せます）。」）は、2026-11-13 になくした（班長指摘
        # 「そもそも、これは不要ではないか？」。値が入るのは見て分かる。使い方はマニュアルに書く）
        return r

    def _draft_extra(self):
        return self.cand

    def _restore_draft_extra(self, extra):
        self.cand = extra

    def _after_show_row(self, row, draft):
        if not draft:
            self.cand = self._find_candidate(row[m.COL["事件呼名"]])
        self.case_box.configure(values=[c.label for c in self.candidates])

    def _fill_defaults(self):
        """未保管の行で、事件呼名・内容はあるのに、保管フォルダ・保管ファイル名が空のとき（元に戻した行、CSV から
        取り込んだ行など）、保管先の既定と保管ファイル名を入れる（2026-11-09 班長指摘「元に戻した後、保管ファイル名が
        自動生成されない」）。"""
        if self.cand is not None:
            if not self.vars["保管フォルダ名"].get():
                self.vars["保管フォルダ名"].set(self.cand.folder)
            if not self.vars["複製作成先"].get():
                self.vars["複製作成先"].set(self.cand.tantou)
        self._update_name()

    # ------------------------------------------------------------ VA Case の共有データ（保管先の候補）

    def load_extra(self):
        path = self.cfg.case_master_path
        if not path:
            return ("none", None)
        try:
            data = read_master(Path(path))
            if data.tool != case_model.TOOL:
                return ("error", f"VA Case の共有データではありません：{path}")
            return ("ok", data.tables)
        except (SharedError, OSError) as e:
            return ("error", describe(e, detail=False))

    def on_extra(self, extra):
        kind, value = extra
        self.case_status = {"ok": "読めた", "none": "設定なし"}.get(kind, "読めなかった")
        old_error = self.case_error
        if kind == "ok":
            self.case_tables, self.case_error = value, ""
        elif kind == "none":
            # 場所が空なら、VA Case を使わない事務所として、知らせない（2026-11-11 班長決定「空なら出さない」。
            # それまでは、起動のたびに「VA Case の事件を読めませんでした…設定されていません」と出ていた）。
            # 場所を入れてあるのに読めないとき（同期の遅れ・暗号化したドライブの開き忘れなど）は、下で知らせる
            self.case_tables, self.case_error = None, ""
        else:
            self.case_error = value     # 前に読めたものがあれば、それを使い続ける
        if self.case_error and self.case_error != old_error:
            messagebox.showwarning(TITLE, "VA Case の事件を読めませんでした。事件呼名は、VA Filing の保管先だけから"
                                          f"選べます。\n\n{self.case_error}", parent=self.root)

    def diagnostic_lines(self):
        status = getattr(self, "case_status", "まだ読んでいない")
        cases = len(self.case_tables.get(case_model.CASE).rows) \
            if self.case_tables and case_model.CASE in self.case_tables else 0
        return super().diagnostic_lines() + [
            f"VA Case の共有データ：{status}（事件 {cases} 件）・保管先の候補 {len(self.candidates)} 件"]

    def on_data(self, data):
        super().on_data(data)
        # 保管フォルダが見つからない保管先（終了した事件など）を出さず、保管するときに表から消す（2026-11-12 班長決定
        # 「消すようにする」「フォルダ存在しない場合は、保管先から削除する」。VA Case を使う事務所でも使わない事務所でも）。
        # 「（データフォルダ）\…」の行は、VA Case の共有データを、いま読めているときだけ確かめる
        exists = {}

        def folder_exists(value):     # 同じフォルダを2度確かめない（同期フォルダでは時間がかかるため）
            if value not in exists:
                exists[value] = self._folder_exists(value)
            return exists[value]

        case_tables = self.case_tables if not self.case_error else None
        self.missing_dests = m.missing_destinations(data.tables[m.DEST].rows, folder_exists, case_tables)
        self.candidates = m.case_candidates(self.case_tables, data.tables[m.DEST].rows, folder_exists,
                                            hidden=self.missing_dests)
        self.case_box.configure(values=[c.label for c in self.candidates])
        self.widgets["複製作成先"].configure(values=[""] + m.tantou_values(data.tables, self._tantou_choices()))

    def _tantou_choices(self):
        if not self.case_tables:
            return []
        return case_model.choice_values(self.case_tables[case_model.CHOICES], "担当区分")

    def _find_candidate(self, name):
        """事件呼名に当たる候補（VA Case の事件とは、事件呼名で結ぶ。2026-11-12 班長決定「案B」）。"""
        return next((c for c in self.candidates if c.name == name), None) if name else None

    def _filter_cases(self, event):
        if event.keysym in ("Up", "Down", "Return", "Escape", "Tab", "Left", "Right", "Home", "End"):
            return
        q = normalize(self.vars["事件呼名"].get().strip())
        labels = [c.label for c in self.candidates if not q or q in c.search or q in normalize(c.label)]
        self.case_box.configure(values=labels)

    def _case_chosen(self, only_if_changed=False):
        text = self.vars["事件呼名"].get().strip()
        c = next((c for c in self.candidates if c.label == text), None)
        if only_if_changed and c is self.cand:
            return
        self.cand = c
        if c is not None:
            self.vars["事件呼名"].set(c.name)
            self.vars["保管フォルダ名"].set(c.folder)
            self.vars["複製作成先"].set(c.tantou)
        self._update_name()

    def _case_name(self):
        """保管ファイル名に使う事件呼名。"""
        if self.cand is not None:
            return self.cand.name
        return self.vars["事件呼名"].get().strip()

    DATE_WITH_TIME = True      # 日時は 202511011030 の12桁

    def _update_name(self):
        if self.current is None or self.current_stored:
            return
        row = m.row_by_number(self.data.tables, self.current)
        if row is None:
            return
        new = m.stored_file_name(row[m.COL["読込ファイル名"]], self.vars["日時"].get().strip(), self._case_name(),
                                 self.vars["内容"].get().strip())
        if self.vars["保管ファイル名"].get() in ("", self.auto_name):
            self.vars["保管ファイル名"].set(new)
        self.auto_name = new

    # ------------------------------------------------------------ 保管・保管の取り消し

    def _prepare_store(self, row, v):
        number = row[m.COL["番号"]]
        case_name = self._case_name()
        if not case_name:
            messagebox.showinfo(TITLE, "事件呼名を選んでください。", parent=self.root)
            self.case_box.focus_set()
            raise StoreCancelled
        if not v["内容"]:
            messagebox.showinfo(TITLE, "内容を入れてください。", parent=self.root)
            self.widgets["内容"].focus_set()
            raise StoreCancelled
        # 日時を確かめる（2026-11-13。それまでは確かめず、「R7.11.1」などが、そのまま保管ファイル名の頭に入った）。
        # 空は、今までどおり通す
        if v["日時"] and dates.compact_datetime(v["日時"], True) != v["日時"]:
            messagebox.showinfo(TITLE, "日時を読めません。2025/11/1、R7.11.1、20251101 などの形で入れてください。", parent=self.root)
            self.widgets["日時"].focus_set()
            raise StoreCancelled
        if not v["保管フォルダ名"]:
            messagebox.showinfo(TITLE, "保管フォルダを選んでください。", parent=self.root)
            raise StoreCancelled
        problem = m.check_file_name(v["保管ファイル名"])
        if problem:
            messagebox.showinfo(TITLE, problem, parent=self.root)
            raise StoreCancelled
        tables = self.data.tables
        specials = m.special_targets(tables, v["内容"])
        cand = self.cand
        if cand is None:
            cand = m.Candidate(case_name, "", v["保管フォルダ名"], v["複製作成先"])   # 新しい保管先（VA Case にないもの）

        # 終了した事件の、覚えた保管先を消すため（2026-11-12 班長決定）。VA Case の共有データを、いま読めているときだけ
        # 使う（読めなかったときは、前に読めたものがあっても消さない）
        case_tables = self.case_tables if not self.case_error else None
        missing = set(getattr(self, "missing_dests", ()))

        def transform(t):
            t = m.mark_stored(t, number, case_name=case_name, content=v["内容"],
                              folder=v["保管フォルダ名"], file_name=v["保管ファイル名"], tantou=v["複製作成先"],
                              note=v["備考"], dt=v["日時"])
            # 先に古い行を消してから、いま保管した保管先を覚える（見つからなかった保管先の名前で、別のフォルダに
            # 保管し直したときに、覚えた行まで消さないように）
            t = m.prune_destinations(t, case_tables, missing)[0]
            return m.remember_destination(t, cand, v["保管フォルダ名"], v["複製作成先"], self.cfg.data_root)

        notes = ["・".join(w for w, _ in specials) + "の写しを作りました。"] if specials else []
        return dict(folder=v["保管フォルダ名"], file_name=v["保管ファイル名"],
                    targets=m.copy_targets(tables, v["複製作成先"]), specials=specials, transform=transform, notes=notes)

    def _restore_links(self, row):
        tables = self.data.tables
        return m.copy_targets(tables, row[m.COL["複製作成先"]]), m.special_targets(tables, row[m.COL["内容"]])

    # ------------------------------------------------------------ 設定

    def _settings_dialog(self):
        return SettingsDialog(self.root, settings.FilingConfig(**vars(self.cfg)))

    def open_office(self):
        if self.data is None:
            return
        result = self.run_office_dialog(lambda editable: OfficeDialog(
            self.root, self.data.tables, editable=editable,
            tantou_choices=m.tantou_values(self.data.tables, self._tantou_choices()),
            data_root=self.cfg.data_root))
        if result:
            self.write_office(result)


def main():
    prepare_process("VBAAssets.VAFiling.Source")
    root = tk.Tk()
    FilingApp(root)
    root.mainloop()
