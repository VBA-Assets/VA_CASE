"""共有データ（マスタ）のファイルの形式と読み書き（仕様.md の3.2・3.3。2026-11-09 班長決定：JSON・ツールごとに1ファイル）。

ファイルの中身：

    {"format": "va_case.master", "format_version": 1, "tool": "VA Case",
     "version": 12, "write_id": "…", "written": {"user": …, "machine": …, "at": …, "lock_id": …},
     "tables": {"事件": {"columns": [...], "rows": [[...], ...]}},
     "sha256": "…"}

- version は書き込みのたびに1増やす番号（画面に出す・順を見るため）。
- write_id は書き込みのたびに作る一意の値。競合の判定はこれで行う（バックアップから戻して version が
  巻き戻っても、取り違えない）。ファイルの更新日時には頼らない（3.3）。
- sha256 は、sha256 の欄を除く中身から計算する。同期・置き換えの途中で切れたファイルを見分ける。
- セルの値は文字列だけとする（日付も文字列。空は ""）。同じ欄に複数の値を入れるときは、改行で区切る（現行と同じ）。
- 1行に1件を書く（メモ帳で開いても読めるように）。
"""
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import fileio
from .errors import FolderMissingError, MasterCorruptError, MasterNotFoundError, SchemaMismatchError

FORMAT = "va_case.master"
FORMAT_VERSION = 1

# 読めなかったときのやり直し（同期の途中のファイルを読んだ場合に備える）
READ_RETRIES = 3


def now_text():
    """書き込みの記録に使う時刻（地域の時差付き。例：2026-11-09T10:15:30+09:00）。"""
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class Table:
    columns: list
    rows: list = field(default_factory=list)

    def copy(self):
        return Table(list(self.columns), [list(r) for r in self.rows])


@dataclass
class MasterData:
    tool: str
    tables: dict                      # テーブル名 → Table（順を保つ）
    version: int = 0
    write_id: str = ""
    written: dict = field(default_factory=dict)   # user・machine・at・lock_id

    def row_count(self):
        return sum(len(t.rows) for t in self.tables.values())


def _content(data):
    """sha256 の計算と書き込みに使う中身（sha256 の欄を除く）。"""
    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "tool": data.tool,
        "version": data.version,
        "write_id": data.write_id,
        "written": data.written,
        "tables": {name: {"columns": t.columns, "rows": t.rows} for name, t in data.tables.items()},
    }


def checksum(data):
    canonical = json.dumps(_content(data), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_tables(tables):
    """セルがすべて文字列で、各行の欄の数が列の数と同じであることを確かめる（書き込む前）。"""
    for name, t in tables.items():
        if not isinstance(name, str) or not name:
            raise ValueError(f"テーブルの名前が不正です：{name!r}")
        if len(set(t.columns)) != len(t.columns):
            raise ValueError(f"テーブル「{name}」の列の名前が重複しています")
        n = len(t.columns)
        for i, row in enumerate(t.rows):
            if len(row) != n:
                raise ValueError(f"テーブル「{name}」の {i + 1} 行目の欄の数（{len(row)}）が列の数（{n}）と違います")
            for v in row:
                if not isinstance(v, str):
                    raise ValueError(f"テーブル「{name}」の {i + 1} 行目に文字列でない値があります：{v!r}")


def serialize(data):
    """MasterData を、ファイルに書くバイト列にする（1行に1件）。"""
    validate_tables(data.tables)
    dumps = lambda v: json.dumps(v, ensure_ascii=False)  # noqa: E731
    head = _content(data)
    lines = ["{"]
    for key in ("format", "format_version", "tool", "version", "write_id", "written"):
        lines.append(f"{dumps(key)}: {dumps(head[key])},")
    lines.append('"tables": {')
    names = list(data.tables)
    for ti, name in enumerate(names):
        t = data.tables[name]
        lines.append(f'{dumps(name)}: {{"columns": {dumps(t.columns)}, "rows": [')
        for ri, row in enumerate(t.rows):
            lines.append(dumps(row) + ("," if ri < len(t.rows) - 1 else ""))
        lines.append("]}" + ("," if ti < len(names) - 1 else ""))
    lines.append("},")
    lines.append(f'"sha256": {dumps(checksum(data))}')
    lines.append("}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def parse(raw, path="(共有データ)"):
    """バイト列を MasterData にする。形式・sha256 が合わなければ MasterCorruptError。"""
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise MasterCorruptError(path, "JSON として読めない") from None
    if not isinstance(obj, dict) or obj.get("format") != FORMAT:
        raise MasterCorruptError(path, "VA Caseシリーズの共有データの形式でない")
    if obj.get("format_version") != FORMAT_VERSION:
        raise MasterCorruptError(path, f"形式の版が {obj.get('format_version')!r} で、このアプリは {FORMAT_VERSION}")
    try:
        tables = {name: Table(list(t["columns"]), [list(r) for r in t["rows"]])
                  for name, t in obj["tables"].items()}
        data = MasterData(tool=obj["tool"], tables=tables, version=int(obj["version"]),
                          write_id=str(obj["write_id"]), written=dict(obj["written"]))
        validate_tables(tables)
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        raise MasterCorruptError(path, f"中身が欠けている：{e}") from None
    if obj.get("sha256") != checksum(data):
        raise MasterCorruptError(path, "中身の確かめ（ハッシュ）が合わない")
    return data


def read_master(path, *, expected=None, sleep=time.sleep, retry_wait=1.0):
    """共有データを読む。

    expected：{テーブル名: 列の名前の一覧}。与えたときは、テーブルと列が一致することを確かめる。
    読めない・確かめが通らないときは、同期の途中のことがあるので、retry_wait 秒ずつ待って読み直す。
    """
    path = Path(path)
    last = None
    for i in range(READ_RETRIES):
        if not path.exists():
            if not path.parent.exists():
                raise FolderMissingError(path.parent)
            raise MasterNotFoundError(path)
        try:
            data = parse(fileio.read_bytes(path, sleep=sleep), path)
            break
        except FileNotFoundError:
            last = MasterNotFoundError(path)
        except MasterCorruptError as e:
            last = e
        if i < READ_RETRIES - 1:
            sleep(retry_wait)
    else:
        raise last
    if expected is not None:
        check_schema(data, expected)
    return data


def check_schema(data, expected):
    for name, columns in expected.items():
        t = data.tables.get(name)
        if t is None:
            raise SchemaMismatchError(name, "テーブルがない")
        if list(t.columns) != list(columns):
            missing = [c for c in columns if c not in t.columns]
            extra = [c for c in t.columns if c not in columns]
            detail = []
            if missing:
                detail.append("ない列：" + "・".join(missing))
            if extra:
                detail.append("知らない列：" + "・".join(extra))
            if not detail:
                detail.append("列の順が違う")
            raise SchemaMismatchError(name, "、".join(detail))


def new_write_id():
    return uuid.uuid4().hex


def create_master(path, tool, tables, identity, *, sleep=time.sleep):
    """新しい共有データのファイルを作る（最初に共有フォルダを用意するとき）。

    フォルダは作らない（3.3）。すでにファイルがあれば FileExistsError（ほかの人のデータを上書きしない）。
    """
    path = Path(path)
    if not path.parent.is_dir():
        raise FolderMissingError(path.parent)
    data = MasterData(tool=tool, tables={k: v.copy() for k, v in tables.items()}, version=1,
                      write_id=new_write_id(),
                      written={"user": identity.user, "machine": identity.machine, "at": now_text(), "lock_id": ""})
    fileio.write_atomic(path, serialize(data), overwrite=False, sleep=sleep)
    return data
