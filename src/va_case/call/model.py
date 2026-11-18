"""VA Call の共有データの中身と、電話メモの扱い（画面に依らない部分）。

現行の VA電話メモ Ver402（`..\\..\\VA事件データベースシリーズ\\VA電話メモ\\sht11.bas`・`Mail.bas`）の動きを写す。決まったことは 仕様.md の 4.4.1。
共有データ（VA_Call.json）には、次のテーブルを持つ（ツールごとに1ファイル）。

- 電話メモ：現行の「電話メモ」テーブルと同じ12列
- 所員：所員名・メールアドレス・ユーザー名（Windows）（現行の「所員別設定」）
- 選択肢：用件・対応・処理の選択肢（現行の「オプション」シートのリスト）
"""
import re
from datetime import datetime
from urllib.parse import quote

from ..common import numbering
from ..common.master import Table

TOOL = "VA Call"
MASTER_FILE_NAME = "VA_Call.json"

MEMO = "電話メモ"
STAFF = "所員"
CHOICES = "選択肢"

MEMO_COLUMNS = ["番号", "入力者", "日時", "相手先", "電話番号", "用件", "対応", "内容", "宛先", "メール送信日時", "確認者",
                "処理"]
STAFF_COLUMNS = ["所員名", "メールアドレス", "ユーザー名（Windows）"]
CHOICE_COLUMNS = ["項目", "値"]
SCHEMA = {MEMO: MEMO_COLUMNS, STAFF: STAFF_COLUMNS, CHOICES: CHOICE_COLUMNS}
COL = {c: i for i, c in enumerate(MEMO_COLUMNS)}

CHOICE_ITEMS = ("用件", "対応", "処理")
DEFAULT_CHOICES = {
    "用件": ["電話がありました。", "来訪されました。", "電話をしました。"],
    "対応": ["電話をいただきたい。", "もう一度電話します。", "もう一度訪問します。"],
    "処理": ["処理済み", "確認済み"],
}
DATETIME_FORMAT = "%Y-%m-%d %H:%M"
MAIL_SUBJECT = "電話メモ"
MAILTO_LIMIT = 1800       # mailto の長さの目安（長いと、メールソフトが本文を受け取れないことがある）


def empty_tables():
    return {
        MEMO: Table(list(MEMO_COLUMNS), []),
        STAFF: Table(list(STAFF_COLUMNS), []),
        CHOICES: Table(list(CHOICE_COLUMNS), [[k, v] for k in CHOICE_ITEMS for v in DEFAULT_CHOICES[k]]),
    }


def copy_tables(tables):
    return {k: v.copy() for k, v in tables.items()}


def choice_values(tables, item):
    return [r[1] for r in tables[CHOICES].rows if r[0] == item and r[1]]


def staff_names(tables):
    return [r[0] for r in tables[STAFF].rows if r[0]]


def phone_for(tables, partner, exclude=None):
    """相手先が同じ、いちばん新しいメモの電話番号（なければ空）。exclude の番号のメモは除く。"""
    if not partner:
        return ""
    for row in sorted(tables[MEMO].rows, key=sort_key, reverse=True):
        if row[COL["番号"]] != exclude and row[COL["相手先"]] == partner and row[COL["電話番号"]]:
            return row[COL["電話番号"]]
    return ""


def staff_for_user(tables, user):
    """Windows のユーザー名から所員名を引く（現行の InputUserName）。なければ空。"""
    u = (user or "").casefold()
    return next((r[0] for r in tables[STAFF].rows if r[2] and r[2].casefold() == u), "")


def mail_address(tables, name):
    return next((r[1] for r in tables[STAFF].rows if r[0] == name), "")


def row_by_number(tables, number):
    return next((r for r in tables[MEMO].rows if r[COL["番号"]] == number), None)


def is_done(row):
    return bool(row[COL["処理"]])


# ---------------------------------------------------------------- 日時

_DT = re.compile(r"^\s*(\d{4})[/\-.年](\d{1,2})[/\-.月](\d{1,2})日?(?:[ T　]+(\d{1,2})[:時](\d{1,2})分?(?::\d{1,2})?)?\s*$")


def now_text(now=None):
    return (now or datetime.now()).strftime(DATETIME_FORMAT)


def normalize_datetime(text):
    """日時の入力（「2025/11/9 10:30」「2025-11-09 10:30」など）を YYYY-MM-DD HH:MM にする。空なら空、読めなければ None。"""
    import unicodedata
    t = unicodedata.normalize("NFKC", text or "").strip()
    if not t:
        return ""
    m = _DT.match(t)
    if not m:
        return None
    y, mo, d, h, mi = (int(x) if x else 0 for x in m.groups())
    try:
        return datetime(y, mo, d, h, mi).strftime(DATETIME_FORMAT)
    except ValueError:
        return None


def display_datetime(text):
    """一覧・入力欄に出す日時（2025/11/9 10:30）。"""
    try:
        d = datetime.strptime(text, DATETIME_FORMAT)
    except (TypeError, ValueError):
        return text or ""
    return f"{d.year}/{d.month}/{d.day} {d.hour}:{d.minute:02d}"


# ---------------------------------------------------------------- メモ

def sort_key(row):
    n = row[COL["番号"]]
    return (0, int(n)) if str(n).isdigit() else (1, str(n))


def sorted_rows(rows):
    """番号の昇順（現行の FormatTable）。"""
    return sorted(rows, key=sort_key)


def next_number(tables, now=None):
    """新しいメモの番号：年月日＋その日の連番の9桁（2026-11-13 班長決定「9桁（年月日＋連番）」。VA Filing・VA Receipt と
    同じ。common/numbering.py）。それまでは、現行と同じく、いまの最大に1を足していた。取り込んだ今までの番号は残す。"""
    return numbering.new_numbers([r[COL["番号"]] for r in tables[MEMO].rows], 1, now)[0]


def add_memo(tables, entered_by, now=None):
    """新しいメモを足す（現行の「番号」のダブルクリック：番号・入力者・日時を入れる）。→ (新しい tables, 番号)"""
    new = copy_tables(tables)
    number = next_number(new, now)
    row = [""] * len(MEMO_COLUMNS)
    row[COL["番号"]] = number
    row[COL["入力者"]] = entered_by
    row[COL["日時"]] = now_text(now)
    new[MEMO].rows = sorted_rows(new[MEMO].rows + [row])
    return new, number


def delete_memo(tables, number):
    """メモを消す（2026-11-09 班長指摘「行の削除ができない」で足した）。番号は付け直さない。"""
    new = copy_tables(tables)
    rows = new[MEMO].rows
    kept = [r for r in rows if r[COL["番号"]] != number]
    if len(kept) == len(rows):
        raise ValueError(f"番号 {number} のメモが、共有データにありません（ほかの PC で消されたかもしれません）。")
    new[MEMO].rows = kept
    return new


def update_memo(tables, number, values, base=None):
    """メモを書き替える（values：列名 → 値。番号は変えない）。base を渡すと、書き込む前の値と比べ、ほかの PC で
    変えられていれば ValueError（同じ人が編集モードで書くので、ふつうは起きない）。"""
    new = copy_tables(tables)
    row = next((r for r in new[MEMO].rows if r[COL["番号"]] == number), None)
    if row is None:
        raise ValueError(f"番号 {number} のメモが、共有データにありません（ほかの PC で消されたかもしれません）。")
    if base is not None and row != list(base):
        raise ValueError(f"番号 {number} のメモが、ほかの PC で変えられています。読み込み直してから、もう一度直してください。")
    for c, v in values.items():
        if c != "番号":
            row[COL[c]] = v
    return new


def check_values(values):
    """入力の確かめ。→ (直した値, 問題の並び)"""
    out = dict(values)
    problems = []
    for c in ("日時", "メール送信日時"):
        if c in out:
            v = normalize_datetime(out[c])
            if v is None:
                problems.append(f"「{c}」を日時として読めません（例：2025/11/9 10:30）：{out[c]}")
            else:
                out[c] = v
    return out, problems


# ---------------------------------------------------------------- メール（mailto。2026-11-09 班長決定）

def mail_body(row):
    """メールの本文（現行の SendMail と同じ並び）。"""
    try:
        d = datetime.strptime(row[COL["日時"]], DATETIME_FORMAT)
        day, time = f"{d.year}/{d.month}/{d.day}", f"{d.hour}:{d.minute:02d}"
    except ValueError:
        day, time = row[COL["日時"]], ""
    lines = [("番　号", row[COL["番号"]]), ("日　付", day), ("時　間", time), ("相手先", row[COL["相手先"]]),
             ("電　話", row[COL["電話番号"]]), ("宛　先", row[COL["宛先"]]), ("用　件", row[COL["用件"]]),
             ("対　応", row[COL["対応"]]), ("内　容", row[COL["内容"]]), ("入力者", row[COL["入力者"]])]
    return "\r\n".join(f"{k}：{v}" for k, v in lines) + "\r\n"


def mailto_url(address, subject, body):
    """mailto の URL（件名・本文は UTF-8 で百分率符号化。改行は CRLF）。"""
    return f"mailto:{quote(address, safe='@')}?subject={quote(subject, safe='')}&body={quote(body, safe='')}"


def _normalize_imported(r):
    vals, probs = check_values({"日時": r[COL["日時"]], "メール送信日時": r[COL["メール送信日時"]]})
    if probs:
        return None
    r[COL["日時"]], r[COL["メール送信日時"]] = vals["日時"], vals["メール送信日時"]
    return r


def drop_existing(tables, rows):
    """取り込む行のうち、すでに同じ記録（番号のほかの値が同じ）があるものを除く。→ (残す行, 除いた数)"""
    from ..common.csvio import drop_same
    return drop_same(tables[MEMO].rows, rows, COL["番号"], _normalize_imported)


def import_rows(tables, rows):
    """CSV の行を足す。番号が空・重なり・数字でないときは、新しい番号を付ける。日時を読めない行があれば ValueError。"""
    problems, fixed = [], []
    for i, r in enumerate(rows, start=1):
        r = list(r)
        vals, probs = check_values({"日時": r[COL["日時"]], "メール送信日時": r[COL["メール送信日時"]]})
        if probs:
            problems += [f"{i} 件目：{p}" for p in probs]
            continue
        r[COL["日時"]], r[COL["メール送信日時"]] = vals["日時"], vals["メール送信日時"]
        fixed.append(r)
    if problems:
        raise ValueError("\n".join(problems[:20]))
    new = copy_tables(tables)
    used = {r[COL["番号"]] for r in new[MEMO].rows}
    need = []
    for r in fixed:
        n = r[COL["番号"]]
        if not str(n).isdigit() or n in used:
            need.append(r)
        else:
            used.add(n)
    for r, n in zip(need, numbering.new_numbers(used, len(need))):
        r[COL["番号"]] = n
    new[MEMO].rows = sorted_rows(new[MEMO].rows + fixed)
    return new
