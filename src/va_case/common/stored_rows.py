"""VA Filing・VA Receipt の「保管」の表の扱いで、2つのツールに共通のもの（画面とファイルの操作に依らない部分）。

2026-11-12 のリファクタリングで、2つのツールの model.py に同じものを書いていたのを、ここにまとめた（それまでは、
VA Receipt の model.py が、VA Filing の model.py から一部を借りていた）。各ツールの model.py は、ここの StoreRows に
表の名前と列を渡して作り、その関数を同じ名前（m.is_stored・m.row_by_number など）で出す。

- 読み込んだファイル（FoundFile）・拡張子・いつも読み込まないファイル・CSV の保管日時の読み替え
- StoreRows：保管の表の行の扱い（空の行・保管済みか・並べ替え・行を探す・元に戻す・消す・備考・CSV の取り込みの下ごしらえ）
"""
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePath

from . import numbering

STORED_AT_FORMAT = "%Y-%m-%d %H:%M:%S"

# いつも読み込まないファイル（現行は「.」で始まるものだけ。Office の一時ファイル・Windows の管理用のファイルも足した）
ALWAYS_SKIP_NAMES = {"thumbs.db", "desktop.ini", ".ds_store"}
ALWAYS_SKIP_PREFIXES = (".", "~$")
ALWAYS_SKIP_SUFFIXES = (".tmp", ".part", ".crdownload")


@dataclass
class FoundFile:
    folder: str        # 読込フォルダ名の欄に入れる値（設定のフォルダの値に、サブフォルダの部分を足したもの）
    name: str
    mtime: float


def extension(name):
    """拡張子（最後の点から後ろ。現行は最初の点から後ろだった。仕様.md の 4.2.1）。"""
    return PurePath(name).suffix


def should_skip(name, prefixes=()):
    low = name.lower()
    if low in ALWAYS_SKIP_NAMES or name.startswith(ALWAYS_SKIP_PREFIXES) or low.endswith(ALWAYS_SKIP_SUFFIXES):
        return True
    return any(p and name.startswith(p) for p in prefixes)


def copy_tables(tables):
    return {k: v.copy() for k, v in tables.items()}


_STORED_AT = re.compile(r"^\s*(\d{4})[/-](\d{1,2})[/-](\d{1,2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?\s*$")


def normalize_stored_at(text):
    """CSV の保管日時（Excel の「2025/3/1 10:00」など）を YYYY-MM-DD HH:MM:SS にする。読めなければ None。"""
    if not text.strip():
        return ""
    m = _STORED_AT.match(text)
    if not m:
        return None
    y, mo, d, h, mi, s = (int(x) if x else 0 for x in m.groups())
    try:
        return datetime(y, mo, d, h, mi, s).strftime(STORED_AT_FORMAT)
    except ValueError:
        return None


class StoreRows:
    """保管の表の行の扱い。store：保管の表の名前、columns：その列、settings：設定の表の名前、
    restore_clear：元に戻すときに空にする列、number_key：並べ替えで、番号を比べる形にする関数。"""

    def __init__(self, store, columns, settings, *, restore_clear, number_key=str):
        self.store = store
        self.columns = list(columns)
        self.settings = settings
        self.col = {c: i for i, c in enumerate(columns)}
        self.restore_clear = tuple(restore_clear)
        self.number_key = number_key

    def blank_row(self):
        return [""] * len(self.columns)

    def is_stored(self, row):
        return bool(row[self.col["保管日時"]])

    def setting_values(self, tables, item):
        return [r[1] for r in tables[self.settings].rows if r[0] == item and r[1]]

    def setting_value(self, tables, item, default=""):
        vals = self.setting_values(tables, item)
        return vals[0] if vals else default

    def sort_key(self, row):
        """並びの順。保管済みの行が先で、保管日時・読込フォルダ名・読込ファイル名の昇順（現行の SortAndFormatTable）。
        未保管の行はその後ろで、番号の順（＝読み込んだ順。番号は年月日＋その日の連番）。

        未保管の行は、2026-11-13 から番号の順にした（班長の問い「261113012のデータが途中に紛れ込んでいるのはなぜか？」。
        班長決定「番号順にする。」）。それまでは現行と同じく読込フォルダ名・読込ファイル名の順で、前の日に読み込んだ
        「受信FAX_…」が、その日に読み込んだ数字の名前のファイルと、サブフォルダのファイルとの間に並んだ。"""
        c = self.col
        number = self.number_key(row[c["番号"]])
        if not self.is_stored(row):
            return (True, number, row[c["読込フォルダ名"]], row[c["読込ファイル名"]])
        return (False, row[c["保管日時"]], row[c["読込フォルダ名"]], row[c["読込ファイル名"]], number)

    def sorted_rows(self, rows):
        return sorted(rows, key=self.sort_key)

    def row_by_number(self, tables, number):
        return next((r for r in tables[self.store].rows if r[self.col["番号"]] == number), None)

    def mark_restored(self, tables, number, stored_at):
        """元に戻したときの記録（現行の RstrFile の後：restore_clear の列を空にする）。"""
        new = copy_tables(tables)
        row = self.row_by_number(new, number)
        if row is None or row[self.col["保管日時"]] != stored_at:
            raise ValueError(f"番号 {number} の行が、ほかの PC で変えられています。読み込み直してから、もう一度試してください。")
        for c in self.restore_clear:
            row[self.col[c]] = ""
        new[self.store].rows = self.sorted_rows(new[self.store].rows)
        return new

    def delete_row(self, tables, number):
        """未保管の行を消す（「消す」。2026-11-09 班長決定）。保管済みの行は消さない（先に「保管を取り消す」）。"""
        new = copy_tables(tables)
        row = self.row_by_number(new, number)
        if row is None:
            raise ValueError(f"番号 {number} の行が、共有データにありません（ほかの PC で消されたかもしれません）。")
        if self.is_stored(row):
            raise ValueError(f"番号 {number} のファイルは保管済みのため、消せません。先に「保管を取り消す」を押してください。")
        new[self.store].rows = [r for r in new[self.store].rows if r[self.col["番号"]] != number]
        return new

    def update_note(self, tables, number, note):
        new = copy_tables(tables)
        row = self.row_by_number(new, number)
        if row is None:
            raise ValueError(f"番号 {number} の行が、共有データにありません。")
        row[self.col["備考"]] = note
        return new

    # ------------------------------------------------------------ CSV の取り込み

    def _normalize_imported(self, r):
        at = normalize_stored_at(r[self.col["保管日時"]])
        if at is None:
            return None
        r[self.col["保管日時"]] = at
        return r

    def drop_existing(self, tables, rows):
        """取り込む行のうち、すでに同じ記録（番号のほかの値が同じ）があるものを除く。→ (残す行, 除いた数)"""
        from .csvio import drop_same
        return drop_same(tables[self.store].rows, rows, self.col["番号"], self._normalize_imported)

    def imported_rows(self, rows):
        """CSV の行の保管日時を YYYY-MM-DD HH:MM:SS にそろえた写し。読めない行があれば ValueError（番号は、ツールが付ける）。"""
        at_col = self.col["保管日時"]
        problems, fixed = [], []
        for i, r in enumerate(rows, start=1):
            r = list(r)
            at = normalize_stored_at(r[at_col])
            if at is None:
                problems.append(f"{i} 件目の保管日時を読めません：{r[at_col]}")
                continue
            r[at_col] = at
            fixed.append(r)
        if problems:
            raise ValueError("\n".join(problems[:20]))
        return fixed


# 新しい行の番号（年月日＋その日の連番の9桁。VA Call と共通。common/numbering.py）
new_numbers = numbering.new_numbers
