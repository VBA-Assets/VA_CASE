"""CSV での出力と取り込み（2026-11-09 班長決定：.xlsm からの取り込みの代わり）。

- 出力：UTF-8（BOM 付き。Excel で開いても文字化けしない）、1行目に列の名前、改行は CRLF。欄の中の改行はそのまま
  （引用符で囲む）。日付は共有データと同じ YYYY-MM-DD（Excel は日付として読む）。
- 取り込み：UTF-8（BOM の有無を問わない）と Shift_JIS（Excel の「CSV（コンマ区切り）」で保存したもの）を読む。
  1行目の列の名前で対応を取る（列の順は問わない）。名前は、全角と半角・空白・英字の大小の違いを問わない（2026-11-11）。
  知らない列があれば止め、このツールの列のうち CSV にないものも示す。必ず要る列（VA Case の事件番号）がなければ止める。
  足りない列は空として、知らせる。
  日付の列は、和暦（R7.1.1。現行の事件データベースの表示の形）・西暦を読み取って YYYY-MM-DD にする。
"""
import csv
import io
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .dates import normalize_dates_text, parse_date, to_storage


class CsvError(Exception):
    """取り込めない（利用者に示す文）。"""


@dataclass
class CsvImport:
    rows: list
    warnings: list = field(default_factory=list)
    encoding: str = ""


def export_csv(path, columns, rows):
    """columns・rows を CSV に書く。"""
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(columns)
    for r in rows:
        w.writerow(r)
    Path(path).write_bytes(buf.getvalue().encode("utf-8-sig"))


def _decode(raw):
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8"), "UTF-8（BOM 付き）"
    try:
        return raw.decode("utf-8"), "UTF-8"
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode("cp932"), "Shift_JIS"
    except UnicodeDecodeError:
        raise CsvError("文字コードを読み取れません（UTF-8 か Shift_JIS で保存してください）。") from None


def header_key(name):
    """列の名前を見比べるための形（全角と半角・空白・英字の大小の違いを問わない。例：「代理人ＦＡＸ番号」→「代理人fax番号」）。"""
    s = unicodedata.normalize("NFKC", str(name))
    return "".join(s.split()).casefold()


def import_csv(path, columns, date_columns=(), required=(), multi_date_columns=()):
    """CSV を読み、columns の順の行（文字列の並び）にする。required：必ず要る列（なければ止める）。
    multi_date_columns：日付の列のうち、1行に1つずつ何人かの日付を入れる列（行ごとに読む。VA Case の生年月日）。"""
    text, encoding = _decode(Path(path).read_bytes())
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = next(reader)
    except StopIteration:
        raise CsvError("CSV が空です。") from None
    header = [h.strip() for h in header]
    while header and header[-1] == "":
        header.pop()   # Excel が末尾に付ける空の列
    # 1行目の名前を、このツールの列の名前に合わせる（全角と半角・空白・英字の大小の違いを問わない。2026-11-11 班長決定）
    known = {header_key(c): c for c in columns}
    matched = [known.get(header_key(h)) for h in header]
    unknown = [h for h, c in zip(header, matched) if c is None]
    if unknown:
        found = {c for c in matched if c}
        missing = [c for c in columns if c not in found]
        msg = "このツールの知らない列があります：" + "・".join(f"「{h}」" for h in unknown)
        if missing:
            msg += "\nこのツールの列のうち、CSV にないもの：" + "・".join(f"「{c}」" for c in missing)
        raise CsvError(msg + "\n1行目の名前を、このツールの列の名前に合わせてください（CSV に出力すると、列の名前が分かります）。")
    dup = sorted({c for c in matched if matched.count(c) > 1})
    if dup:
        raise CsvError("同じ列が2つ以上あります：" + "・".join(f"「{c}」" for c in dup))
    absent = [c for c in required if c not in matched]
    if absent:
        raise CsvError("・".join(f"「{c}」" for c in absent) + "の列がありません。この列がないと取り込めません。")
    result = CsvImport([], [], encoding)
    renamed = [f"「{h}」を「{c}」" for h, c in zip(header, matched) if h != c]
    if renamed:
        result.warnings.append("列の名前を読み替えました：" + "・".join(renamed))
    missing = [c for c in columns if c not in matched]
    if missing:
        result.warnings.append("CSV にない列は、空にしました：" + "・".join(missing))
    index = {c: i for i, c in enumerate(matched)}
    for rec_no, rec in enumerate(reader, start=1):
        if not any(v.strip() for v in rec):
            continue   # 空の行
        extra = [v for v in rec[len(header):] if v.strip()]
        if extra:
            raise CsvError(f"{rec_no} 件目（見出しの次から数えて）の欄が、列の数より多くあります。")
        row = []
        for c in columns:
            i = index.get(c)
            v = rec[i] if i is not None and i < len(rec) else ""
            v = v.replace("\r\n", "\n").replace("\r", "\n")
            if c in multi_date_columns and v.strip():
                try:
                    v = normalize_dates_text(v)
                except ValueError:
                    result.warnings.append(f"{rec_no} 件目の「{c}」を日付として読めないため、そのまま入れました：{v}")
            elif c in date_columns and v.strip():
                d = parse_date(v)
                if d is None:
                    result.warnings.append(f"{rec_no} 件目の「{c}」を日付として読めないため、そのまま入れました：{v}")
                else:
                    v = to_storage(d)
            row.append(v)
        result.rows.append(row)
    return result


def drop_same(existing, rows, key_index, normalize):
    """取り込む行のうち、番号（key_index の列）のほかの値が、すでにある行と同じものを除く。→ (残す行, 除いた数)

    normalize(行)：共有データと同じ形に直した行（日時の書き方など）。直せない行（None）は残す（取り込むときに知らせる）。
    同じ CSV を2回取り込んで、番号だけが違う同じ記録が二重にできるのを防ぐ（2026-11-11 班長決定「防ぐ」）。
    CSV の中で同じ行が2つあるときは、どちらも取り込む（同じ日の同じ金額の領収書など、別の記録のことがあるため）。
    """
    def key(r):
        return tuple(v for i, v in enumerate(r) if i != key_index)
    have = {key(r) for r in existing}
    keep, dropped = [], 0
    for r in rows:
        n = normalize(list(r))
        if n is not None and key(n) in have:
            dropped += 1
        else:
            keep.append(r)
    return keep, dropped
