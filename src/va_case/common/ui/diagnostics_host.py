"""診断情報（［ヘルプ］→［診断情報をコピー］。仕様.md の 6.5。2026-11-11）の画面の側（4つのツールで共通。SharedApp が受け継ぐ）。

2026-11-12 のリファクタリングで、shared_app.py から分けた（中身は変えていない）。文を作る部品は common/diagnostics.py。
中身（値・場所・名前）を一切入れない（diagnostics.py の冒頭）。ツールごとのことは diagnostic_lines で足す。

使うもの（SharedApp にあるもの）：self.root・self.cfg・self.data・self.store・self.errors・self.bg・self.TITLE・self.SCHEMA と、
モード・検索の状態（state_lines）。
"""
import dataclasses
import tkinter as tk
from datetime import date, datetime
from tkinter import messagebox

from ... import VERSION_LABEL
from .. import diagnostics


class DiagnosticsHost:
    # この PC の設定の欄の名前（診断情報に出す名前）。場所の欄は、あるか・種類だけを出し、場所は出さない
    CONFIG_LABELS = {
        "master_path": "共有データ", "case_master_path": "VA Case の共有データ", "backup_folder": "バックアップの置き場所",
        "data_root": "事務所のフォルダの場所", "outbox": "移送待ちの場所",
        "zip_compress": "ZIP を圧縮する", "window_geometry": "ウィンドウの位置と大きさ", "window_zoomed": "最大化して閉じた", "column_widths": "覚えた列の幅",
        "office_size": "事務所の設定の画面の大きさ", "office_column_widths": "事務所の設定の画面の覚えた列の幅",
        "preview_visible": "プレビューを表示する", "preview_width": "プレビューの幅",
    }
    PATH_FIELDS = ("master_path", "case_master_path", "backup_folder", "data_root", "outbox")

    def _on_callback_error(self, exc_type, exc, tb):
        """画面の処理（ボタン・キーなど）で起きた、予期しない誤りを覚える（Tk の既定どおり、出力にも出す）。"""
        self.errors.record(exc, "画面の処理")
        try:
            import traceback
            traceback.print_exception(exc_type, exc, tb)
        except Exception:
            pass

    ABOUT_LINE = ""     # 「について」に出す、ツールの1行の説明（各ツールで決める）

    def about_text(self):
        """「について」の文。VA FAX の「について」と同じ形：名前と版・1行の説明・空の行・作った者・ライセンス
        （2026-11-14 班長決定「MIT License」、班長指示「「について」の表示内容をVA FAXに合わせる。」。いったん、シリーズの名前と
        「使っている部品のライセンスは、配布物の THIRD_PARTY_NOTICES.txt に書いてあります。」も出していたが、VA FAX に
        合わせて外した。部品のライセンスは、配布物に添える THIRD_PARTY_NOTICES.txt に書く）。"""
        return f"{self.TITLE}  {VERSION_LABEL}\n{self.ABOUT_LINE}\n\nVBAアセット（vba-assets.net）\nMIT License"

    def build_help_menu(self, bar):
        """「ヘルプ」のメニュー（診断情報をコピー・について）。"""
        h = tk.Menu(bar, tearoff=False)
        h.add_command(label="診断情報をコピー", command=self.copy_diagnostics)
        h.add_separator()
        h.add_command(label=f"{self.TITLE} について",
                      command=lambda: messagebox.showinfo(self.TITLE, self.about_text(), parent=self.root))
        bar.add_cascade(label="ヘルプ", menu=h)

    def copy_diagnostics(self):
        text = self.diagnostic_text()
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        messagebox.showinfo(self.TITLE, "診断情報をコピーしました。\n\n"
                            "不具合を相談するときは、これを貼り付けて渡してください。版・環境・件数・誤りの起きた場所だけが"
                            "入っていて、氏名などの値や、ファイル・フォルダの場所と名前は入っていません。\n"
                            "渡す前に、メモ帳などに貼り付けて、中身を確かめることができます。", parent=self.root)

    def diagnostic_text(self):
        """診断情報の文。中身（値・場所・名前）を一切入れない（diagnostics.py の冒頭）。"""
        d = diagnostics
        lines = [f"{self.TITLE} 診断情報（{datetime.now():%Y-%m-%d %H:%M}）",
                 "※ 氏名・住所などの値、ファイルやフォルダの場所・名前、利用者と PC の名前は入っていません。", ""]
        lines += ["■ 環境"] + d.environment_lines(self.root, self.TITLE, VERSION_LABEL) + [""]
        lines.append("■ この PC の設定")
        for f in dataclasses.fields(self.cfg):
            label = self.CONFIG_LABELS.get(f.name, f.name)
            value = getattr(self.cfg, f.name)
            if f.name in self.PATH_FIELDS:
                lines += d.file_lines(label, value)
            elif isinstance(value, dict):
                lines.append(f"{label}：{len(value)} 列")
            elif isinstance(value, bool):
                lines.append(f"{label}：{'はい' if value else 'いいえ'}")
            elif isinstance(value, (int, float)) or f.name in ("window_geometry", "office_size"):
                lines.append(f"{label}：{value if value != '' else '設定なし'}")
            else:                       # ほかの文字の欄は、値を出さない
                lines.append(f"{label}：{'設定あり' if value else '設定なし'}")
        lines += [""] + ["■ 状態"] + self.state_lines() + [""]
        lines.append("■ 共有データ")
        if self.data is None:
            lines.append("読み込んでいない")
        else:
            at = str(self.data.written.get("at", "")) if isinstance(self.data.written, dict) else ""
            lines.append(f"共有データの版 {self.data.version}・最後に書き込まれた日時 {at or '不明'}")
            lines += d.table_lines(self.data.tables, self.SCHEMA)
        extra = self.diagnostic_lines()
        if extra:
            lines += ["", f"■ {self.TITLE} だけのこと"] + extra
        records = self.errors.records
        lines += ["", f"■ 起きた誤り（新しいものから {min(len(records), d.SHOW_ERRORS)} 件。覚えているのは全 {len(records)} 件）"]
        if not records:
            lines.append("なし")
        for r in reversed(records[-d.SHOW_ERRORS:]):
            lines += d.format_record(r)
        return "\n".join(lines) + "\n"

    def state_lines(self):
        other = bool(self.editor_text) and not self.editing
        lines = [f"モード：{'編集' if self.editing else '閲覧'}（ほかの人が編集中：{'はい' if other else 'いいえ'}）",
                 f"読み込み中：{'はい' if self.loading else 'いいえ'}・書き込み中：{'はい' if self.writing else 'いいえ'}・"
                 f"書き込み待ち {len(self._write_queue)} 件・裏の処理 {'動作中' if self.bg.busy else 'なし'}",
                 f"検索：{'あり' if not self.query.empty else 'なし'}・フィルタ：{len(self.filters)} 列・"
                 f"一覧に出ている行 {len(self._cells)} 件"]
        if self.store is not None:
            try:
                lines.append(f"競合の写し：{len(self.store.conflict_copies())} 個")
            except Exception as e:
                lines.append(f"競合の写し：確かめられない（{type(e).__name__}）")
        lines.append(f"日次バックアップ：{'今日は済み' if self.backup_done_on == date.today() else '今日はまだ'}")
        return lines

    def diagnostic_lines(self):
        """ツールごとの診断情報（件数など。値・場所・名前は入れない）。"""
        return []
