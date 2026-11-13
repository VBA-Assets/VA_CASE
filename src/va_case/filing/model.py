"""VA Filing の共有データの中身と、保管の扱い（画面とファイルの操作に依らない部分）。

現行の VAファイル保管 Ver708（`..\\VAファイル保管\\Sht1Hokan.bas` ほか）の動きを写す。決まったことは 仕様.md の 4.2.1。
共有データ（VA_Filing.json）には、次のテーブルを持つ（ツールごとに1ファイル。2026-11-09 班長決定）。

- 保管：読み込んだファイルと、その保管の記録（現行の「保管」テーブルと同じ列）
- 保管先：事件呼名ごとに覚えた保管先（現行と同じ列。VA Case の事件とも、事件呼名で結ぶ）
- 読込フォルダ・複製作成先・特別な写し・設定：事務所の設定（現行の「オプション」シート。事務所で1つ）

VA Case の事件とは、事件番号ではなく事件呼名で結ぶ（2026-11-12 班長決定「案B」。同じ事件呼名の事件は基本的になく、
あってもデータフォルダは同じはずのため）。それまでは、保管と保管先の表に事件番号を持っていた。
"""
from dataclasses import dataclass
from datetime import datetime

from ..common.master import Table
from ..common import stored_rows
from ..common.paths import join_value, sub_of
from ..common import storing
from ..common.search import normalize

TOOL = "VA Filing"
MASTER_FILE_NAME = "VA_Filing.json"

STORE = "保管"
DEST = "保管先"
READ_FOLDERS = "読込フォルダ"
COPY_TARGETS = "複製作成先"
SPECIAL = "特別な写し"
SETTINGS = "設定"

STORE_COLUMNS = ["番号", "読込フォルダ名", "読込ファイル名", "日時", "事件呼名", "内容", "保管フォルダ名",
                 "保管ファイル名", "複製作成先", "保管日時", "備考"]
DEST_COLUMNS = ["事件呼名", "保管フォルダ", "担当区分"]
# 保管先の表で、VA Case の事件のデータフォルダからの相対を表す頭（「（データフォルダ）\scan」。2026-11-12 班長決定）
IN_DATA_FOLDER = "（データフォルダ）"
READ_FOLDER_COLUMNS = ["フォルダ", "サブフォルダも"]
COPY_TARGET_COLUMNS = ["担当区分", "種類", "フォルダ"]
SPECIAL_COLUMNS = ["語", "フォルダ"]
SETTING_COLUMNS = ["項目", "値"]

SCHEMA ={STORE: STORE_COLUMNS, DEST: DEST_COLUMNS, READ_FOLDERS: READ_FOLDER_COLUMNS,
          COPY_TARGETS: COPY_TARGET_COLUMNS, SPECIAL: SPECIAL_COLUMNS, SETTINGS: SETTING_COLUMNS}
COL = {c: i for i, c in enumerate(STORE_COLUMNS)}

KIND_SHORTCUT = storing.KIND_SHORTCUT
KIND_COPY = storing.KIND_COPY
check_file_name = storing.check_file_name
KINDS = (KIND_SHORTCUT, KIND_COPY)
YES = "はい"

SET_SKIP_PREFIX = "読み込まないファイル名の先頭"     # 1行に1つ（ほかのソフトが作るファイルを読み飛ばす。既定は空）
SET_PICK_START = "保管フォルダを選ぶときの初めのフォルダ"   # 現行のオプションの「保管フォルダ」

# 現行の MakeCopyOfSpecialFile と同じ語（置き場所は事務所で入れる。空なら写しを作らない）
DEFAULT_SPECIAL = [["職務上請求", ""], ["弁護士会照会", ""]]

LITERATURE_SUFFIX = "（文献）"   # 事件呼名がこれで終わるときは、保管ファイル名に日時と事件呼名を付けない（現行と同じ）

def empty_tables():
    return {
        STORE: Table(list(STORE_COLUMNS), []),
        DEST: Table(list(DEST_COLUMNS), []),
        READ_FOLDERS: Table(list(READ_FOLDER_COLUMNS), []),
        COPY_TARGETS: Table(list(COPY_TARGET_COLUMNS), []),
        SPECIAL: Table(list(SPECIAL_COLUMNS), [list(r) for r in DEFAULT_SPECIAL]),
        SETTINGS: Table(list(SETTING_COLUMNS), []),
    }


# VA Receipt と共通のもの（common/stored_rows.py。2026-11-12 のリファクタリング）。ここの名前でも使う
FoundFile = stored_rows.FoundFile
STORED_AT_FORMAT = stored_rows.STORED_AT_FORMAT
copy_tables = stored_rows.copy_tables
extension = stored_rows.extension
should_skip = stored_rows.should_skip
normalize_stored_at = stored_rows.normalize_stored_at

# 保管の表の行の扱い
_rows = stored_rows.StoreRows(STORE, STORE_COLUMNS, SETTINGS,
                              restore_clear=("保管日時", "保管フォルダ名", "保管ファイル名", "複製作成先"))
blank_row = _rows.blank_row
is_stored = _rows.is_stored
setting_values = _rows.setting_values
setting_value = _rows.setting_value
sort_key = _rows.sort_key
sorted_rows = _rows.sorted_rows
row_by_number = _rows.row_by_number
mark_restored = _rows.mark_restored      # 元に戻したときの記録（現行の RstrFile の後。複製作成先も空にする）
delete_row = _rows.delete_row
update_note = _rows.update_note
drop_existing = _rows.drop_existing


# ---------------------------------------------------------------- ファイル名

def datetime_text(name, mtime=None):
    """「日時」の欄（yyyymmddhhnn）。ファイル名の先頭12字が 20 で始まる数字ならそれを、なければファイルの日時を使う。"""
    head = name[:12]
    if head.startswith("20") and len(head) == 12 and head.isdigit():
        return head
    if mtime is None:
        return ""
    return datetime.fromtimestamp(mtime).strftime("%Y%m%d%H%M")


def stored_file_name(read_name, dt, case_name, content):
    """保管ファイル名（現行の InputStoredFile）：<日時>00000<事件呼名>　<内容><拡張子>。

    事件呼名が「（文献）」で終わるときは <内容><拡張子>。内容がなければ空（まだ決められない）。
    """
    if not content:
        return ""
    ext = extension(read_name)
    if case_name.endswith(LITERATURE_SUFFIX):
        return f"{content}{ext}"
    return f"{dt}00000{case_name}　{content}{ext}"


# ---------------------------------------------------------------- 並べ替え・番号

# 番号（年月日＋その日の連番の9桁。2026-11-13 班長決定「9桁（年月日＋連番）」。それまでは現行と同じ yymmddhhnnss。
# VA Receipt・VA Call と共通。common/numbering.py）
new_numbers = stored_rows.new_numbers


# ---------------------------------------------------------------- 読み込み（現行の ReadFileNames・DeleteInvalidData）

def merge_found(tables, found, missing_numbers, now=None):
    """読み込んだファイルを「保管」に足し、読込ファイルがなくなった未保管の行を消す。→ (新しい tables, 足した数, 消した数)

    重なりは、未保管の行とだけ比べる（現行は保管済みの行とも比べ、前に保管したファイルと同じ名前の新しいファイルを
    読み込めなかった。仕様.md の 4.2.1）。
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
    numbers = new_numbers([r[COL["番号"]] for r in kept], len(adds), now)
    for f, number in zip(adds, numbers):
        row = blank_row()
        row[COL["番号"]] = number
        row[COL["読込フォルダ名"]] = f.folder
        row[COL["読込ファイル名"]] = f.name
        row[COL["日時"]] = datetime_text(f.name, f.mtime)
        kept.append(row)
    new[STORE].rows = sorted_rows(kept)
    return new, len(adds), removed


# ---------------------------------------------------------------- 保管先（VA Case の事件と、VA Filing の保管先）

@dataclass
class Candidate:
    name: str          # 事件呼名
    kana: str          # 並べ替えに使う読み（VA Case のふりがなの1行目）
    folder: str        # 保管フォルダの既定（VA Case のデータフォルダ、または覚えた保管先）
    tantou: str        # 複製作成先の既定（担当区分）
    label: str = ""    # 選ぶ欄に出す文字（事件呼名）
    case_folder: str = ""   # VA Case のデータフォルダ（覚えた保管先と比べるため）
    case_tantou: str = ""
    search: str = ""   # 選ぶ欄で絞り込むための文字（正規化したもの）
    from_case: bool = False   # VA Case の事件か（VA Case にない保管先でないか）


def _case_name_of(row):
    from ..case import model as cm
    return row[cm.COL["事件呼名"]] or row[cm.COL["依頼者氏名"]].split("\n")[0]


def _is_closed(row):
    from ..case import closing as case_closing
    from ..case import model as cm
    return row[cm.COL["現況"]] == cm.STATUS_CLOSED or case_closing.is_archived(row[cm.COL["データフォルダ"]])


def active_cases(case_tables):
    """VA Case の終了していない事件：事件呼名 → 事件の行。同じ事件呼名の事件は、前の行だけ（データフォルダも同じはずのため）。"""
    from ..case import model as cm
    out = {}
    if case_tables is None or cm.CASE not in case_tables:
        return out
    for row in case_tables[cm.CASE].rows:
        name = _case_name_of(row)
        if name and not _is_closed(row) and name not in out:
            out[name] = row
    return out


def dest_folder(value, case_row):
    """保管先の表の保管フォルダの値を、使う値にする。「（データフォルダ）\\scan」は、VA Case の事件のデータフォルダの中の
    scan にする（事件がない・データフォルダが空なら ""）。"""
    from ..case import model as cm
    if not value.startswith(IN_DATA_FOLDER):
        return value
    folder = case_row[cm.COL["データフォルダ"]] if case_row is not None else ""
    return join_value(folder, value[len(IN_DATA_FOLDER):].lstrip("\\/")) if folder else ""


def missing_destinations(dest_rows, folder_exists, case_tables=None):
    """保管フォルダが見つからない保管先の事件呼名の集まり（一覧に出さず、保管するときに表から消す）。

    終了した事件のフォルダには、アクセスできない状態になっていることを前提にする（2026-11-12 班長）。VA Case を使う
    事務所でも使わない事務所でも、保管フォルダが見つからない保管先は消す（同日 班長決定「フォルダ存在しない場合は、
    保管先から削除する」。それまでは、VA Case を使わない事務所だけだった）。
    「（データフォルダ）\\…」の行は、VA Case の終了していない事件のデータフォルダから作り、その事件がない（事件呼名を
    直した・事件を消した・終了した）ときも、見つからないとみる。case_tables が None（VA Case を使わない・読めない）なら、
    この行は確かめない。
    フォルダを1つも見つけられないときは、暗号化したドライブの開き忘れなど、この PC から共有フォルダが見えていないとみて、
    フォルダを確かめた行は除かない。
    """
    active = active_cases(case_tables) if case_tables is not None else None
    unresolved, checked, missing = set(), set(), set()
    for r in dest_rows:
        name, value = r[0], r[1]
        if not name or not value:
            continue
        if value.startswith(IN_DATA_FOLDER):
            if active is None:
                continue
            value = dest_folder(value, active.get(name))
            if not value:
                unresolved.add(name)
                continue
        checked.add(name)
        if not folder_exists(value):
            missing.add(name)
    if checked and missing == checked:
        missing = set()
    return unresolved | missing


def case_candidates(case_tables, dest_rows, folder_exists=None, hidden=()):
    """選ぶ欄の候補：VA Case の終了していない事件（ふりがなの順）と、VA Case にない保管先（事件呼名の順）。
    保管フォルダが空のものは除く（2026-11-12 班長指示）。

    case_tables は VA Case の共有データのテーブル（None なら VA Case の事件は出さない）。保管先の表の行とは、事件呼名で
    結ぶ。folder_exists(値) は、覚えた保管先がまだあるかを確かめる関数（なければデータフォルダに戻す）。
    hidden：使わない保管先の事件呼名（missing_destinations。保管フォルダが見つからないもの）。
    """
    from ..case import model as cm

    remembered_rows = {}
    for r in dest_rows:
        if r[0] and r[0] not in hidden and r[0] not in remembered_rows:
            remembered_rows[r[0]] = r
    cases = active_cases(case_tables)
    out = []
    for name, row in cases.items():
        folder = row[cm.COL["データフォルダ"]]
        kana = row[cm.COL["ふりがな"]].split("\n")[0]
        tantou = row[cm.COL["担当区分"]]
        c = Candidate(name, kana, folder, tantou, case_folder=folder, case_tantou=tantou, from_case=True)
        o = remembered_rows.get(name)
        remembered = dest_folder(o[1], row) if o is not None else ""
        if remembered and (folder_exists is None or folder_exists(remembered)):
            c.folder = remembered
            c.tantou = o[2]
        c.search = normalize(" ".join((name, kana, row[cm.COL["依頼者氏名"]])))
        out.append(c)
    # ふりがなの順。同じふりがな（同じ依頼者）なら VA Case の表の順のまま。ふりがながなければ最後
    out.sort(key=lambda c: normalize(c.kana) if c.kana else "\uffff")
    # VA Case にない保管先（「（文献）」など）。「（データフォルダ）\…」の行は、VA Case の事件がなければ使えないので出さない
    others = [Candidate(name, "", r[1], r[2]) for name, r in remembered_rows.items()
              if name not in cases and not r[1].startswith(IN_DATA_FOLDER)]
    for c in others:
        c.search = normalize(c.name)
    others.sort(key=lambda c: normalize(c.name))
    out += others
    # 保管フォルダ（VA Case のデータフォルダか、覚えた保管先）が空のものは出さない（2026-11-12 班長指示「事件呼名の
    # 一覧には、保管フォルダのデータが有るものだけを表示」。選んでも保管フォルダを選び直すことになるため）。
    # 値があれば出す（フォルダがあるかは、ここでは確かめない。同期フォルダでは確かめるのに時間がかかるため）
    out = [c for c in out if c.folder.strip()]
    for c in out:
        c.label = c.name
    return out


def remember_destination(tables, candidate, folder, tantou, data_root=""):
    """保管したときの保管先を、事件呼名ごとに覚える（現行の MoveFile の後半。保管先の表を足す・直す）。

    VA Case の事件で、データフォルダと担当区分のとおりに保管したときは、覚えた行を消す（既定に戻る）。
    データフォルダの中のフォルダ（scan など）に保管したときは、「（データフォルダ）\\scan」のように、データフォルダ
    からの相対で覚える（2026-11-12 班長決定。PC ごとに共有フォルダの場所が違っても、VA Case でデータフォルダの名前や
    場所を変えても、既定が切れないように）。data_root：この PC の事務所のフォルダの場所（相対の値を比べるため）。
    """
    new = copy_tables(tables)
    rows = new[DEST].rows
    name = candidate.name if candidate is not None else ""
    if not name:
        return new
    rows[:] = [r for r in rows if r[0] != name]
    if candidate.from_case:
        sub = sub_of(folder, candidate.case_folder, data_root) if candidate.case_folder else None
        if sub is not None:
            value = IN_DATA_FOLDER + ("\\" + sub if sub else "")
            if sub or tantou != candidate.case_tantou:
                rows.append([name, value, tantou])
        elif folder != candidate.case_folder or tantou != candidate.case_tantou:
            rows.append([name, folder, tantou])
    else:
        rows.append([name, folder, tantou])
    return new


def prune_destinations(tables, case_tables, missing=()):
    """保管先の表から、VA Case で終了した事件（現況が終了か、データフォルダを保管庫へ移したもの）の行と、保管フォルダが
    見つからない行（missing。missing_destinations）を除く（2026-11-12 班長決定「自動で消す」「フォルダ存在しない場合は、
    保管先から削除する」。データフォルダの中の scan などに保管すると、事件ごとに行ができ、終了した事件の行がたまり続ける
    ため）。事件とは事件呼名で結ぶ。同じ事件呼名の終了していない事件があれば、終了した事件の行とはみない。
    case_tables が None（VA Case の共有データを読めなかった・使わない）なら、終了した事件の行は除かない。
    → (新しい tables, 除いた数)
    """
    from ..case import model as cm

    closed = set()
    if case_tables is not None and cm.CASE in case_tables:
        closed = {_case_name_of(r) for r in case_tables[cm.CASE].rows if _is_closed(r)} - set(active_cases(case_tables))
    rows = tables[DEST].rows
    keep = [r for r in rows if r[0] not in closed and r[0] not in missing]
    if len(keep) == len(rows):
        return tables, 0
    new = copy_tables(tables)
    new[DEST].rows = keep
    return new, len(rows) - len(keep)


# ---------------------------------------------------------------- 写し（ショートカット・コピー・特別な写し）

def copy_targets(tables, tantou):
    """複製作成先（担当区分）に当たる、(種類, フォルダの値) の並び。"""
    if not tantou:
        return []
    return [(r[1], r[2]) for r in tables[COPY_TARGETS].rows if r[0] == tantou and r[1] in KINDS and r[2]]


def special_targets(tables, content):
    """内容に語が入っているときの、特別な写しの (語, フォルダの値) の並び（現行の職務上請求・弁護士会照会）。"""
    return [(r[0], r[1]) for r in tables[SPECIAL].rows if r[0] and r[1] and r[0] in content]


def tantou_values(tables, case_choice_values=()):
    """複製作成先の選ぶ欄の候補（事務所の設定の複製作成先の担当区分。VA Case の担当区分も足す）。"""
    vals = []
    for v in [r[0] for r in tables[COPY_TARGETS].rows] + list(case_choice_values):
        if v and v not in vals:
            vals.append(v)
    return vals


# ---------------------------------------------------------------- 保管・元に戻す（記録の書き替え）

def mark_stored(tables, number, *, case_name, content, folder, file_name, tantou, note, dt, at=None):
    new = copy_tables(tables)
    row = next((r for r in new[STORE].rows if r[COL["番号"]] == number), None)
    if row is None:
        raise ValueError(f"番号 {number} の行が、共有データにありません（ほかの PC で消されたかもしれません）。")
    if is_stored(row):
        raise ValueError(f"番号 {number} のファイルは、すでに保管されています（ほかの PC で保管されたかもしれません）。")
    row[COL["日時"]] = dt
    row[COL["事件呼名"]] = case_name
    row[COL["内容"]] = content
    row[COL["保管フォルダ名"]] = folder
    row[COL["保管ファイル名"]] = file_name
    row[COL["複製作成先"]] = tantou
    row[COL["備考"]] = note
    row[COL["保管日時"]] = (at or datetime.now()).strftime(STORED_AT_FORMAT)
    new[STORE].rows = sorted_rows(new[STORE].rows)
    return new


# ---------------------------------------------------------------- CSV の取り込み

def add_imported(tables, rows):
    """CSV の行を足す。番号が空・重なりのときは、新しい番号を付ける。保管日時を読めない行があれば ValueError。"""
    fixed = _rows.imported_rows(rows)
    new = copy_tables(tables)
    used = {r[COL["番号"]] for r in new[STORE].rows}
    need = []
    for r in fixed:
        if not r[COL["番号"]] or r[COL["番号"]] in used:
            need.append(r)
        else:
            used.add(r[COL["番号"]])
    for r, n in zip(need, new_numbers(used, len(need))):
        r[COL["番号"]] = n
    new[STORE].rows = sorted_rows(new[STORE].rows + fixed)
    return new
