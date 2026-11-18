"""VA Case の画面の、終了処理（データフォルダを ZIP にして移送待ちに置く・現況を戻したときに元に戻す）の部分。

ZIP を作る・確かめる・展開する仕組みそのものは closing.py。ここは、画面での確かめ・進み具合・共有データへの記録。
2026-11-13 のリファクタリングで app.py から分けた（動きは変えていない）。CaseApp が受け継ぐ。受け継ぐ側は、self.root・
self.rows・self.data・self.cfg・self.bg・self.work_label と、row_by_number・write を持つこと。
"""
from pathlib import Path
from tkinter import filedialog, messagebox

from ..common.errors import FolderMissingError
from ..common.paths import place_key, portable
from . import closing
from . import model as m
from .dialogs import TITLE, ProgressDialog


class ClosingUI:
    # ------------------------------------------------------------ 終了処理

    def _after_status_change(self, old_status, row):
        new_status = row[m.COL["現況"]]
        if new_status in m.MOVE_STATUSES and new_status != old_status and row[m.COL["データフォルダ"]]:
            self.start_closing(row[m.COL["事件番号"]])
        elif new_status not in m.MOVE_STATUSES and new_status != old_status \
                and closing.is_archived(row[m.COL["データフォルダ"]]):
            self.start_restoring(row[m.COL["事件番号"]])   # 終了処理を戻す（2026-11-10 班長決定）
        elif new_status not in m.MOVE_STATUSES and row[m.COL["データフォルダ"]] \
                and not closing.is_archived(row[m.COL["データフォルダ"]]):
            path = m.resolve_folder(row[m.COL["データフォルダ"]], self.cfg.data_root)
            if path is None or not path.is_dir():   # 現行の CheckFolder
                messagebox.showwarning(TITLE, "データフォルダの値が不正か、フォルダが存在しません。", parent=self.root)

    def start_closing(self, number):
        row = self.row_by_number(number)
        if row is None:
            return
        try:
            p = closing.plan(row, self.rows, self.data.tables[m.FOLDER_RULES], self.cfg)
        except (ValueError, FolderMissingError) as e:
            messagebox.showinfo(TITLE, "終了処理（データフォルダの ZIP の作成）をしませんでした。\n\n" + self.error_text(e),
                                parent=self.root)
            return
        others = [r for r in self.rows if r[m.COL["事件番号"]] in (p.members or [])[1:]]
        also = (f"同じデータフォルダを使う、終わった事件（事件番号 {closing.case_label(others)}）も、まとめて"
                "保管庫の値にします。\n\n" if others else "")
        if not messagebox.askyesno(
                TITLE, "データフォルダを ZIP にして、移送待ちに置きます。\n\n"
                       f"元のフォルダ：{p.source}\n置き場所：{p.target}\n\n" + also +
                       "大きさによっては時間がかかります。そのあいだも VA Case は使えます。\n"
                       "OneDrive・SharePoint のフォルダで、手元にないファイルは、ダウンロードしながら作ります。\n"
                       "よろしいですか？", parent=self.root):
            return
        origin_value = row[m.COL["データフォルダ"]]
        dlg = ProgressDialog(self.root, "終了処理", f"事件 {number}「{row[m.COL['事件呼名']]}」のデータフォルダを"
                                                   "ZIP にしています。")
        self.work_label.configure(text=f"事件 {number} の ZIP を作っています…")

        def _work():
            return closing.make_zip(p, compress=self.cfg.zip_compress,
                                    progress=lambda d, t, n: self.bg.report(dlg.update_progress, d, t, n),
                                    cancelled=lambda: dlg.cancelled)

        def _done(result):
            count, size = result
            dlg.destroy()
            self.work_label.configure(text=f"事件 {number} の ZIP を作りました")
            delete = messagebox.askyesno(
                TITLE, f"ZIP を作り、中身を確かめました（ファイル {count} 件、{size / 1024 / 1024:,.1f} MB）。\n"
                       f"{p.target}\n\n元のデータフォルダを消しますか？\n{p.source}\n\n消すと元に戻せません。",
                icon="warning", parent=self.root)
            if delete:
                try:
                    closing.delete_source(p.source)
                except OSError as e:
                    messagebox.showerror(TITLE, f"元のフォルダを消せませんでした。手で消してください。\n\n{self.error_text(e)}",
                                         parent=self.root)
            else:
                messagebox.showinfo(TITLE, "元のフォルダは残しました。確かめてから、手で消してください。", parent=self.root)
            value = closing.archived_value(p.rel, origin_value)   # 元の場所も残す（現況を戻したときのため）
            key = place_key(origin_value, self.cfg.data_root)

            def transform(t):
                cur = next((r for r in t[m.CASE].rows if r[m.COL["事件番号"]] == number), None)
                if cur is None:
                    raise ValueError(f"事件番号 {number} の事件が、共有データにありません。")
                cur = list(cur)
                cur[m.COL["データフォルダ"]] = value
                t = m.upsert_case(t, cur, old_number=number)
                # 同じデータフォルダを使う、終わった事件の欄も、保管庫の値にする（元の場所は、それぞれの欄の値を残す）
                for other in (p.members or [])[1:]:
                    r = next((r for r in t[m.CASE].rows if r[m.COL["事件番号"]] == other), None)
                    v = r[m.COL["データフォルダ"]] if r is not None else ""
                    if r is None or closing.is_archived(v) or place_key(v, self.cfg.data_root) != key:
                        continue              # ほかで消された・書き替えられた事件は、そのまま
                    r = list(r)
                    r[m.COL["データフォルダ"]] = closing.archived_value(p.rel, v)
                    t = m.upsert_case(t, r, old_number=other)
                return t
            self.write(transform, f"事件 {number} のデータフォルダ（保管庫）", select=number)

        def _err(e):
            dlg.destroy()
            self.work_label.configure(text=f"事件 {number} の ZIP を作れませんでした")
            if isinstance(e, closing.Cancelled):
                messagebox.showinfo(TITLE, "ZIP の作成を取り消しました。元のデータフォルダはそのままです。", parent=self.root)
            else:
                messagebox.showerror(TITLE, f"ZIP を作れませんでした。元のデータフォルダはそのままです。\n\n{self.error_text(e, record=False)}",
                                     parent=self.root)
        self.bg.run(_work, _done, _err)

    def start_restoring(self, number):
        """終了処理を戻す（現況を「未了」などに戻したとき。2026-11-10 班長決定）。

        元のフォルダが残っていれば欄を戻すだけ。消してあって ZIP が移送待ちにあれば、元の場所に展開して戻す。
        移送待ちに ZIP がなければ（保管庫へ移した後）、VA Case は保管庫に触れないため、戻さずに知らせる。
        欄を書き替えた後で、移送待ちの ZIP を消すかを確かめる。
        """
        row = self.row_by_number(number)
        if row is None:
            return
        value = row[m.COL["データフォルダ"]]
        location = closing.archived_location(value)
        # まとめて ZIP にした、同じフォルダのほかの事件も、欄を戻した場所に直す（現況は「終了」のまま。2026-11-13）
        others = closing.archived_members(row, self.rows)
        also = (f"\n\n同じ ZIP にまとめた事件（事件番号 {closing.case_label(others)}）のデータフォルダの欄も、"
                "戻した場所に直します（現況はそのままです）。" if others else "")
        try:
            p = closing.restore_plan(row, self.cfg)
        except (ValueError, FolderMissingError) as e:
            messagebox.showinfo(TITLE, "終了処理を戻しませんでした（データフォルダは「保管庫：…」のままです）。\n\n"
                                       + self.error_text(e), parent=self.root)
            return
        if p.kind == "moved":
            messagebox.showinfo(
                TITLE, "移送待ちに ZIP がないため（保管庫へ移した後とみて）、データフォルダを戻しませんでした。\n"
                       "VA Case は保管庫に触れません。保管庫を開いて、次の ZIP を展開し、"
                       "データフォルダの欄に、展開した場所を入れてください。\n\n"
                       f"保管庫の中の場所：{location}"
                       + (f"\n元の場所：{p.origin_value}" if p.origin_value else ""), parent=self.root)
            return
        if p.kind == "folder":
            if not messagebox.askyesno(TITLE, "元のデータフォルダが残っています。データフォルダの欄を、元の場所に"
                                              f"戻します。\n\n{p.origin_value}{also}\n\nよろしいですか？",
                                       parent=self.root):
                return
            self._write_restored(number, value, p.origin_value, p)
            return
        target = p.origin
        if target is None:
            if not messagebox.askokcancel(
                    TITLE, "移送待ちの ZIP を展開して、データフォルダを戻します。\n"
                           "元の場所が記録されていないため、展開する場所（データフォルダを置くフォルダ）を選んでください。"
                           f"\n\nZIP：{p.zip_path}{also}", parent=self.root):
                return
            parent = filedialog.askdirectory(parent=self.root, title="データフォルダを置くフォルダ",
                                             initialdir=self.cfg.data_root or None, mustexist=True)
            if not parent:
                return
            target = Path(parent) / p.zip_path.stem
            if target.exists():
                messagebox.showwarning(TITLE, f"選んだ場所に、同じ名前のフォルダかファイルがあります。\n{target}",
                                       parent=self.root)
                return
            new_value = portable(str(target), self.cfg.data_root)
        else:
            if not messagebox.askyesno(
                    TITLE, "移送待ちの ZIP を、元の場所に展開して、データフォルダを戻します。\n\n"
                           f"ZIP：{p.zip_path}\n戻す場所：{target}{also}\n\n"
                           "大きさによっては時間がかかります。そのあいだも VA Case は使えます。\nよろしいですか？",
                    parent=self.root):
                return
            new_value = p.origin_value
        dlg = ProgressDialog(self.root, "終了処理を戻す", f"事件 {number}「{row[m.COL['事件呼名']]}」のデータフォルダを"
                                                         "元に戻しています。", cancel_question="展開を取り消しますか？")
        self.work_label.configure(text=f"事件 {number} のデータフォルダを戻しています…")

        def _work():
            return closing.unzip(p.zip_path, target,
                                 progress=lambda d, t, n: self.bg.report(dlg.update_progress, d, t, n),
                                 cancelled=lambda: dlg.cancelled)

        def _done(result):
            count, size = result
            dlg.destroy()
            self.work_label.configure(text=f"事件 {number} のデータフォルダを戻しました")
            messagebox.showinfo(TITLE, f"ZIP を展開し、中身を確かめました（ファイル {count} 件、"
                                       f"{size / 1024 / 1024:,.1f} MB）。\n{target}", parent=self.root)
            self._write_restored(number, value, new_value, p)

        def _err(e):
            dlg.destroy()
            self.work_label.configure(text=f"事件 {number} のデータフォルダを戻せませんでした")
            if isinstance(e, closing.Cancelled):
                messagebox.showinfo(TITLE, "展開を取り消しました。移送待ちの ZIP はそのままです。", parent=self.root)
            else:
                messagebox.showerror(TITLE, f"展開できませんでした。移送待ちの ZIP はそのままです。\n\n{self.error_text(e, record=False)}",
                                     parent=self.root)
        self.bg.run(_work, _done, _err)

    def _write_restored(self, number, old_value, new_value, p):
        """戻したデータフォルダを記録に書き、書けたら、移送待ちの ZIP を消すかを確かめる。"""
        def transform(t):
            cur = next((r for r in t[m.CASE].rows if r[m.COL["事件番号"]] == number), None)
            if cur is None:
                raise ValueError(f"事件番号 {number} の事件が、共有データにありません。")
            if cur[m.COL["データフォルダ"]] != old_value:
                raise ValueError(f"事件番号 {number} のデータフォルダが、ほかで書き替えられています。")
            cur = list(cur)
            cur[m.COL["データフォルダ"]] = new_value
            t = m.upsert_case(t, cur, old_number=number)
            # 同じ ZIP にまとめたほかの事件の欄も、戻した場所に直す（現況はそのまま。2026-11-13）
            rel = closing.archived_rel(old_value)
            for r in [r for r in t[m.CASE].rows if r[m.COL["事件番号"]] != number]:
                if closing.is_archived(r[m.COL["データフォルダ"]]) and \
                        closing.archived_rel(r[m.COL["データフォルダ"]]) == rel:
                    r = list(r)
                    r[m.COL["データフォルダ"]] = new_value
                    t = m.upsert_case(t, r, old_number=r[m.COL["事件番号"]])
            return t

        def after():
            if not p.zip_exists:
                return
            if messagebox.askyesno(TITLE, "データフォルダを戻しました。移送待ちの ZIP を消しますか？\n"
                                          f"{p.zip_path}\n\n消すと元に戻せません。", icon="warning", parent=self.root):
                try:
                    closing.delete_zip(p.zip_path, self.cfg.outbox)
                except OSError as e:
                    messagebox.showerror(TITLE, f"ZIP を消せませんでした。手で消してください。\n\n{self.error_text(e)}", parent=self.root)
            else:
                messagebox.showinfo(TITLE, "移送待ちの ZIP は残しました。保管庫へ移さないよう、手で消してください。",
                                    parent=self.root)
        self.write(transform, f"事件 {number} のデータフォルダ（元に戻す）", after, select=number)
