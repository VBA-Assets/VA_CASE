"""VA Receipt の共有データの中身と、保管の扱い（画面とファイルの操作に依らない部分）。

現行の VA領収書等ファイル保管 Ver403（`..\\..\\VA事件データベースシリーズ\\VA領収書等ファイル保管\\ShtHokan.bas`）の動きを写す。決まったことは 仕様.md の
4.3.1。共有データ（VA_Receipt.json）には、次のテーブルを持つ（ツールごとに1ファイル）。

- 保管：読み込んだファイルと、その保管の記録（現行の「保管」テーブルと同じ12列）
- 種別：種別ごとの保管フォルダ（現行の「保管フォルダ」テーブル）
- 読込フォルダ・設定：事務所の設定（枝番の付け方・日時の決め方・読み込まないファイル名の先頭）
"""
import re
import unicodedata
from datetime import date, datetime

from ..common import storing, stored_rows
from ..common.master import Table

# VA Filing と共通のもの（common/stored_rows.py。2026-11-12 のリファクタリングまでは、VA Filing の model.py から借りていた）。
# ここの名前でも使う
FoundFile = stored_rows.FoundFile
STORED_AT_FORMAT = stored_rows.STORED_AT_FORMAT
copy_tables = stored_rows.copy_tables
extension = stored_rows.extension
should_skip = stored_rows.should_skip
normalize_stored_at = stored_rows.normalize_stored_at

TOOL = "VA Receipt"
MASTER_FILE_NAME = "VA_Receipt.json"

STORE = "保管"
TYPES = "種別"
READ_FOLDERS = "読込フォルダ"
SETTINGS = "設定"

STORE_COLUMNS = ["番号", "読込フォルダ名", "読込ファイル名", "種別", "日時", "相手先", "金額", "枝番", "保管フォルダ名",
                 "保管ファイル名", "保管日時", "備考"]
TYPE_COLUMNS = ["種別", "保管フォルダ"]
READ_FOLDER_COLUMNS = ["フォルダ", "サブフォルダも"]
SETTING_COLUMNS = ["項目", "値"]
SCHEMA = {STORE: STORE_COLUMNS, TYPES: TYPE_COLUMNS, READ_FOLDERS: READ_FOLDER_COLUMNS, SETTINGS: SETTING_COLUMNS}
COL = {c: i for i, c in enumerate(STORE_COLUMNS)}
YES = "はい"

# 現行の「保管フォルダ」テーブルの種別（保管フォルダは事務所で入れる）
DEFAULT_TYPES = ["領収書", "請求書", "支払明細書", "納品書", "出金伝票", "売上票", "報酬明細書", "振込通知書", "給与明細書"]

SET_BRANCH = "枝番"                          # 現行のオプションの「枝番」
BRANCH_ALWAYS = "常に付加する"                # 1件目から _1 を付ける
BRANCH_WHEN_SAME = "重なるときだけ付加する"    # 日時・相手先・金額が同じものの2件目から _1 を付ける（現行の既定）
SET_DATE_FALLBACK = "ファイル名が日付で始まらないときの日時"   # 2026-11-09 班長指示（事務所の設定で選ぶ）
DATE_FROM_FILE = "ファイルの日付"
DATE_BLANK = "空欄"
SET_SKIP_PREFIX = "読み込まないファイル名の先頭"

check_file_name = storing.check_file_name


def empty_tables():
    return {
        STORE: Table(list(STORE_COLUMNS), []),
        TYPES: Table(list(TYPE_COLUMNS), [[t, ""] for t in DEFAULT_TYPES]),
        READ_FOLDERS: Table(list(READ_FOLDER_COLUMNS), []),
        SETTINGS: Table(list(SETTING_COLUMNS), [[SET_BRANCH, BRANCH_WHEN_SAME], [SET_DATE_FALLBACK, DATE_FROM_FILE]]),
    }


def _number_key(number):
    return (0, int(number)) if str(number).isdigit() else (1, str(number))


# 保管の表の行の扱い（VA Filing と共通。common/stored_rows.py）。並べ替えでは、番号を数として比べる。元に戻すときは、
# 保管日時・保管フォルダ名・保管ファイル名を空にする（現行の RstrFile の後。もう一度保管するときは、入力欄に出したときに、
# 種別の保管フォルダと保管ファイル名を入れ直す）
_rows = stored_rows.StoreRows(STORE, STORE_COLUMNS, SETTINGS,
                              restore_clear=("保管日時", "保管フォルダ名", "保管ファイル名"), number_key=_number_key)
blank_row = _rows.blank_row
is_stored = _rows.is_stored
setting_values = _rows.setting_values
setting_value = _rows.setting_value
sort_key = _rows.sort_key
sorted_rows = _rows.sorted_rows
row_by_number = _rows.row_by_number
mark_restored = _rows.mark_restored
delete_row = _rows.delete_row
update_note = _rows.update_note
drop_existing = _rows.drop_existing


def branch_always(tables):
    return setting_value(tables, SET_BRANCH) == BRANCH_ALWAYS


def date_fallback(tables):
    return setting_value(tables, SET_DATE_FALLBACK, DATE_FROM_FILE)


def type_names(tables):
    return [r[0] for r in tables[TYPES].rows if r[0]]


def type_folder(tables, kind):
    return next((r[1] for r in tables[TYPES].rows if r[0] == kind), "")


def valid_date_text(text):
    """yyyymmdd の8桁で、ある日付か。"""
    if len(text) != 8 or not text.isdigit():
        return False
    try:
        datetime.strptime(text, "%Y%m%d")
        return True
    except ValueError:
        return False


def date_from_name(name, mtime=None, fallback=DATE_FROM_FILE):
    """「日時」の欄（yyyymmdd）。ファイル名の先頭8字が日付（20 で始まる8桁の数字）ならそれを、そうでなければ、
    事務所の設定で「ファイルの日付」ならファイルの更新日を、「空欄」なら空を入れる（2026-11-09 班長決定・班長指示）。"""
    head = name[:8]
    if head.startswith("20") and valid_date_text(head):
        return head
    if fallback == DATE_FROM_FILE and mtime is not None:
        return date.fromtimestamp(mtime).strftime("%Y%m%d")
    return ""


# Windows がファイルを写すときに名前の後ろに付けるもの（「 (2)」「 - コピー」「 - コピー (2)」）
_COPY_SUFFIX = re.compile(r"(\s*-\s*コピー)?(\s*\(\d+\))?$")


def _copy_order(name):
    """読み込む順の鍵：写しの印を除いた名前、写しの何枚目か（元は 0、「 - コピー」は 1、「 (2)」は 2）、元の名前。"""
    ext = extension(name)
    stem = name[: -len(ext)] if ext else name
    mt = _COPY_SUFFIX.search(stem)
    base = stem[: mt.start()] if mt else stem
    n = 0
    if mt and mt.group(2):
        n = int(re.search(r"\d+", mt.group(2)).group())
    elif mt and mt.group(1):
        n = 1
    return (base.casefold() + ext.casefold(), n, name)


def parts_from_name(name):
    """ファイル名（拡張子を除く）を「_」で分けた2つ目を相手先、3つ目を金額とする（現行の ReadFileNames と同じ）。

    2026-11-12 班長決定「直す」で、現行と変えた点：
    - Windows が写したときに付ける「 (2)」「 - コピー」を除いてから読む（それまでは金額が「1500 (2)」になり、同じ日・
      相手先・金額の2枚目として枝番が付かなかった）。
    - 名前が8桁の数字（日付）で始まらないときは、相手先も金額も読まない（「IMG_0001.jpg」の「0001」を相手先と読んで
      いた。日付_相手先_金額 の形でない名前では、「_」で分けた位置に意味がないため）。8桁の数字なら、ない日付
      （20251131 など）でも、この形とみて読む。
    """
    stem = name[: -len(extension(name))] if extension(name) else name
    stem = _COPY_SUFFIX.sub("", stem)
    if not (len(stem) >= 8 and stem[:8].isdigit() and stem[8:9] in ("", "_")):
        return "", ""
    parts = stem.split("_")
    partner = parts[1] if len(parts) > 1 else ""
    amount = parts[2] if len(parts) > 2 else ""
    norm = normalize_amount(amount)
    return partner, (norm if norm is not None else amount)


_AMOUNT_DROP = re.compile(r"[,，、\s円¥￥\\]")


def normalize_amount(text):
    """金額を、数字だけにそろえる（「1,100円」「￥1,100」「１１００」→「1100」。2026-11-09 班長決定）。
    空なら空。数字にならなければ None。負の数（「-500」「▲500」）は「-500」にする。"""
    t = unicodedata.normalize("NFKC", text or "").strip()
    if not t:
        return ""
    t = _AMOUNT_DROP.sub("", t)
    negative = t.startswith(("-", "▲", "△"))
    t = t.lstrip("-▲△")
    if not t.isdigit():
        return None
    t = t.lstrip("0") or "0"
    return ("-" if negative and t != "0" else "") + t


# ---------------------------------------------------------------- 保管ファイル名と枝番

def stored_file_name(read_name, dt, partner, amount, branch):
    """保管ファイル名（現行と同じ）：<日時>_<相手先>_<金額>.<拡張子>。枝番があれば <日時>_<相手先>_<金額>_<枝番>.<拡張子>。

    金額が空で枝番もないときは、末尾の「_」を付けない（<日時>_<相手先>.<拡張子>。2026-11-12 班長決定「直す」。
    それまでは「20251105_丙野書店_.pdf」になった）。枝番があるときは「<日時>_<相手先>__<枝番>」と金額の場所を空けて
    おく（「_1」が金額の1と見分けられなくならないように）。
    """
    has_branch = branch and str(branch) != "0"
    base = f"{dt}_{partner}_{amount}" if (amount or has_branch) else f"{dt}_{partner}"
    if has_branch:
        base += f"_{branch}"
    return base + extension(read_name)


def _key(row):
    amount = normalize_amount(row[COL["金額"]])
    return (row[COL["日時"]], row[COL["相手先"]], amount if amount is not None else row[COL["金額"]])


def suggest_branch(tables, number, read_name, dt, partner, amount, folder_exists=None):
    """枝番を決める（現行の Worksheet_Change と同じ考え方）。

    日時・相手先・金額が同じで、番号が前の行の数を数え、「常に付加する」なら1を足す。さらに、保管済みの行や、
    保管フォルダにすでにある同じ名前のファイルと重なれば、重ならなくなるまで増やす（Python 版で足した確かめ。
    folder_exists(保管ファイル名) は、保管フォルダにその名前のファイルがあるか）。→ 枝番（int。0 は付けない）
    """
    key = (dt, partner, amount)
    me = _number_key(number)
    before = sum(1 for r in tables[STORE].rows
                 if r[COL["番号"]] != number and _key(r) == key and _number_key(r[COL["番号"]]) < me)
    branch = before + (1 if branch_always(tables) else 0)
    used = {r[COL["保管ファイル名"]] for r in tables[STORE].rows if is_stored(r) and r[COL["番号"]] != number}
    for _ in range(1000):
        name = stored_file_name(read_name, dt, partner, amount, branch)
        if name not in used and not (folder_exists and folder_exists(name)):
            return branch
        branch += 1
    return branch


# ---------------------------------------------------------------- 並べ替え・番号・読み込み

def next_numbers(rows, count, now=None):
    """番号を count 個。年月日＋その日の連番の9桁で、VA Filing・VA Call と同じ（2026-11-13 班長決定「9桁（年月日＋
    連番）」。それまでは、現行と同じく、いまの最大に1を足していた。common/numbering.py）。"""
    return stored_rows.new_numbers([r[COL["番号"]] for r in rows], count, now)


def merge_found(tables, found, missing_numbers, now=None):
    """読み込んだファイルを「保管」に足し、読込ファイルがなくなった未保管の行を消す。→ (新しい tables, 足した数, 消した数)

    種別は種別の表の1つ目、保管フォルダはその種別の保管フォルダ、日時・相手先・金額はファイル名から入れる（現行と同じ）。
    重なりは、未保管の行とだけ比べる（現行は、保管済みの行と同じ名前の新しいファイルを読み込めなかった）。
    """
    new = copy_tables(tables)
    rows = new[STORE].rows
    missing = set(missing_numbers)
    kept = [r for r in rows if is_stored(r) or r[COL["番号"]] not in missing]
    removed = len(rows) - len(kept)
    pending = {(r[COL["読込フォルダ名"]].casefold(), r[COL["読込ファイル名"]].casefold())
               for r in kept if not is_stored(r)}
    adds = []
    for f in found:
        key = (f.folder.casefold(), f.name.casefold())
        if key in pending:
            continue
        pending.add(key)
        adds.append(f)
    kinds = type_names(new)
    kind = kinds[0] if kinds else ""
    fallback = date_fallback(new)
    # 番号は、Windows が写した「 (2)」「 - コピー」のファイルを、元のファイルの後にして付ける（名前の順では、
    # 「…1500 (2).pdf」が「…1500.pdf」より先に来て、元のファイルの方に枝番が付いていた。2026-11-12）
    order = {}
    for f in adds:
        order.setdefault(f.folder.casefold(), len(order))
    adds.sort(key=lambda f: (order[f.folder.casefold()],) + _copy_order(f.name))
    for f, number in zip(adds, next_numbers(kept, len(adds), now)):
        row = blank_row()
        row[COL["番号"]] = number
        row[COL["読込フォルダ名"]] = f.folder
        row[COL["読込ファイル名"]] = f.name
        row[COL["種別"]] = kind
        row[COL["保管フォルダ名"]] = type_folder(new, kind)
        row[COL["日時"]] = date_from_name(f.name, f.mtime, fallback)
        row[COL["相手先"]], row[COL["金額"]] = parts_from_name(f.name)
        kept.append(row)
    new[STORE].rows = sorted_rows(kept)
    return new, len(adds), removed


# ---------------------------------------------------------------- 保管・元に戻す（記録の書き替え）

def mark_stored(tables, number, *, kind, dt, partner, amount, branch, folder, file_name, note, at=None):
    new = copy_tables(tables)
    row = next((r for r in new[STORE].rows if r[COL["番号"]] == number), None)
    if row is None:
        raise ValueError(f"番号 {number} の行が、共有データにありません（ほかの PC で消されたかもしれません）。")
    if is_stored(row):
        raise ValueError(f"番号 {number} のファイルは、すでに保管されています（ほかの PC で保管されたかもしれません）。")
    for c, v in (("種別", kind), ("日時", dt), ("相手先", partner), ("金額", amount), ("枝番", str(branch)),
                 ("保管フォルダ名", folder), ("保管ファイル名", file_name), ("備考", note)):
        row[COL[c]] = v
    row[COL["保管日時"]] = (at or datetime.now()).strftime(STORED_AT_FORMAT)
    new[STORE].rows = sorted_rows(new[STORE].rows)
    return new


def add_imported(tables, rows):
    """CSV の行を足す。番号が空・重なり・数字でないときは、新しい番号を付ける。保管日時を読めない行があれば ValueError。"""
    fixed = _rows.imported_rows(rows)
    new = copy_tables(tables)
    used = {r[COL["番号"]] for r in new[STORE].rows}
    need = []
    for r in fixed:
        n = r[COL["番号"]]
        if not str(n).isdigit() or n in used:
            need.append(r)
        else:
            used.add(n)
    all_rows = new[STORE].rows + [r for r in fixed if r not in need]
    for r, n in zip(need, next_numbers(all_rows, len(need))):
        r[COL["番号"]] = n
    new[STORE].rows = sorted_rows(new[STORE].rows + fixed)
    return new

