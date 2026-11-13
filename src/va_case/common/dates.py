"""日付の読み取りと書き方（西暦・和暦）。

共有データには、日付を「YYYY-MM-DD」で書く（並べ替えでき、Excel でも日付として読める）。画面には、現行の
事件データベースと同じく和暦の「R7.1.1」の形（Excel の書式 ge.m.d）で出す。

読み取れる書き方（全角の数字・記号も可）：
- 西暦：2025/1/1・2025-01-01・2025.1.1・2025年1月1日
- 和暦：R7.1.1・R7/1/1・令和7年1月1日・令和元年5月1日・H31.4.30（M・T・S・H・R と明治・大正・昭和・平成・令和）
"""
import re
import unicodedata
from datetime import date, datetime

# 元号（頭文字、名前、始まりの日）。新しいものから順に並べる
ERAS = [
    ("R", "令和", date(2019, 5, 1)),
    ("H", "平成", date(1989, 1, 8)),
    ("S", "昭和", date(1926, 12, 25)),
    ("T", "大正", date(1912, 7, 30)),
    ("M", "明治", date(1868, 10, 23)),
]
_ERA_BY_KEY = {}
for _letter, _name, _start in ERAS:
    _ERA_BY_KEY[_letter] = _start.year - 1
    _ERA_BY_KEY[_name] = _start.year - 1

_SEIREKI = re.compile(r"^(\d{4})\s*[/\-.年]\s*(\d{1,2})\s*[/\-.月]\s*(\d{1,2})\s*日?$")
_WAREKI = re.compile(r"^(令和|平成|昭和|大正|明治|[RHSTM])\s*(\d{1,2}|元)\s*[/\-.年]\s*(\d{1,2})\s*[/\-.月]\s*(\d{1,2})\s*日?$",
                     re.IGNORECASE)


def parse_date(text):
    """文字列を日付として読む。読めなければ None。"""
    if not text:
        return None
    s = unicodedata.normalize("NFKC", str(text)).strip()
    if not s or len(s) > 20:
        return None
    m = _SEIREKI.match(s)
    if m:
        y, mo, d = (int(g) for g in m.groups())
    else:
        m = _WAREKI.match(s)
        if not m:
            return None
        era, ny, mo, d = m.groups()
        era = era.upper() if len(era) == 1 else era
        y = _ERA_BY_KEY[era] + (1 if ny == "元" else int(ny))
        mo, d = int(mo), int(d)
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def to_storage(d):
    """共有データに書く形（YYYY-MM-DD）。"""
    return f"{d:%Y-%m-%d}"


def normalize_date_text(text):
    """入力された日付を、共有データに書く形にする。空はそのまま空。読めなければ ValueError。"""
    text = (text or "").strip()
    if not text:
        return ""
    d = parse_date(text)
    if d is None:
        raise ValueError(f"日付として読めません：{text}")
    return to_storage(d)


def normalize_dates_text(text):
    """1行に1つずつ日付を入れた値（何人かの生年月日など）を、共有データに書く形にする。空の行は除く。
    読めない行があれば、その行をすべて挙げて ValueError。"""
    lines = [s.strip() for s in (text or "").splitlines() if s.strip()]
    bad = [s for s in lines if parse_date(s) is None]
    if bad:
        raise ValueError("日付として読めません：" + "・".join(bad))
    return "\n".join(to_storage(parse_date(s)) for s in lines)


def to_wareki(d):
    """和暦の短い形（例：R7.1.1。Excel の書式 ge.m.d と同じ）。明治より前は西暦（yyyy/m/d）。"""
    for letter, _name, start in ERAS:
        if d >= start:
            return f"{letter}{d.year - start.year + 1}.{d.month}.{d.day}"
    return to_seireki(d)


def to_seireki(d):
    """西暦の短い形（例：2025/1/1。Excel の書式 yyyy/m/d と同じ）。"""
    return f"{d.year}/{d.month}/{d.day}"


def display(text):
    """共有データの日付を画面に出す形にする。日付として読めなければ、そのまま返す。"""
    d = parse_date(text)
    return to_wareki(d) if d else (text or "")


def display_lines(text):
    """display を1行ずつ行う（1行に1つずつ日付を入れた値。1行の値なら display と同じ）。"""
    return "\n".join(display(s) for s in (text or "").split("\n"))


_ZENKAKU = str.maketrans("0123456789", "０１２３４５６７８９")


def zenkaku_digits(text):
    """数字を全角にする（現行の Excel の DBCS に当たる。書類の日付・事件番号）。"""
    return (text or "").translate(_ZENKAKU)


def to_wareki_long(d):
    """和暦の長い形（例：令和7年11月9日。元年は「元年」）。Excel の書式 ggge年m月d日 と同じ。"""
    for _letter, name, start in ERAS:
        if d >= start:
            y = d.year - start.year + 1
            return f"{name}{'元' if y == 1 else y}年{d.month}月{d.day}日"
    return f"{d.year}年{d.month}月{d.day}日"


_TIME = re.compile(r"(\d{1,2})\s*(?:[:：時])\s*(\d{1,2})?\s*分?")


def parse_datetime(text):
    """「R7.12.1 10:30」「2025/12/1 10時30分」などを (日付, 時, 分) にする。時刻がなければ (日付, None, None)。
    読めなければ None。"""
    s = unicodedata.normalize("NFKC", text or "").strip()
    if not s:
        return None
    parts = s.split(None, 1)
    d = parse_date(parts[0])
    if d is None:
        return None
    if len(parts) == 1:
        return d, None, None
    m = _TIME.fullmatch(parts[1].strip())
    if not m:
        return None
    hh, mm = int(m.group(1)), int(m.group(2) or 0)
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        return None
    return d, hh, mm


def format_datetime_long(d, hh=None, mm=None):
    """「令和7年12月1日午前10時30分」（Excel の書式 ggge年m月d日AM/PMh時mm分 と同じ形。数字は全角）。"""
    s = to_wareki_long(d)
    if hh is not None:
        ampm = "午前" if hh < 12 else "午後"
        h12 = hh if hh <= 12 else hh - 12
        s += f"{ampm}{h12}時{mm:02d}分"
    return zenkaku_digits(s)


_DAY_THEN_TIME = re.compile(r"日\s*(?=\d)")


def compact_datetime(text, with_time):
    """日時の入力を、VA Filing の「202511011030」（with_time が真）・VA Receipt の「20251101」の形にそろえる
    （2026-11-13 班長決定「この形で作る」：日時の欄に別の書き方を入れても、自動で直す）。空なら空、読めなければ None。

    読める書き方（全角の数字・記号も可）：parse_datetime と同じもの（西暦・和暦。時刻は「10:30」「10時30分」。
    「2025年11月1日10時30分」のように、日と時刻の間の空白がなくてもよい）と、8桁（yyyymmdd）・12桁（yyyymmddhhnn）の
    数字。日付だけのときの時刻は 0000。with_time が偽なら、時刻は捨てる。年を省いた書き方（「11/1」）は読まない
    （年をまたぐころに、違う年になるおそれがあるため。VA Case の日付の欄と同じ）。
    """
    s = unicodedata.normalize("NFKC", text or "").strip()
    if not s:
        return ""
    if s.isascii() and s.isdigit() and len(s) in (8, 12):
        try:
            d = datetime.strptime(s, "%Y%m%d%H%M" if len(s) == 12 else "%Y%m%d")
        except ValueError:
            return None
        day, hh, mm = d.date(), d.hour, d.minute
    else:
        parsed = parse_datetime(_DAY_THEN_TIME.sub("日 ", s))
        if parsed is None:
            return None
        day, hh, mm = parsed
    out = f"{day:%Y%m%d}"
    if with_time:
        out += f"{hh or 0:02d}{mm or 0:02d}"
    return out
