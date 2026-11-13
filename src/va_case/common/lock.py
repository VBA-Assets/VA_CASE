"""編集の排他（ロックファイル。仕様.md の3.1・3.3）。

VAブリッジと同じく、共有データと同じフォルダに「<共有データのファイル名>.<人>@<PC>.lock」を置いた人が、
そのツールの編集者になる。ほかの人は閲覧だけとする。ツールごとに共有データのファイルが違うので、ロックもツールごとに分かれる。

VAブリッジとの対応：
- 「マスタより古いロックは無効」（cleanUpStaleLocks・isLocked）は、ファイルの更新日時を比べず、中身で判定する（3.3）。
  ロックには、取ったときの共有データの write_id（base_write_id）を書く。共有データが、そのロックを取った後に
  ほかの人に書き替えられている（write_id が base_write_id と違い、かつ書いたのがそのロックの持ち主でない）なら、
  そのロックは無効とする。持ち主自身が書いた場合は、続けて有効（編集を続けられる）。
- 作る前と作った直後の2回、ほかのロックを確かめる（acquireLock）。直後の確かめは、同期の伝わりを待ってから行う（3.3）。
- 同じ人のロックでも、ほかの PC のものは、ほかの人のロックとして扱う（VAブリッジは人の名前だけで見ていた）。
- 読めないロックファイル（同期の途中など）は、安全側に倒して有効とみなす。
"""
import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from . import fileio
from .master import now_text

LOCK_FORMAT = "va_case.lock"
LOCK_SUFFIX = ".lock"


@dataclass
class LockInfo:
    path: Path
    key: str            # ファイル名の「人@PC」の部分
    data: dict = None   # 読めなかったときは None

    @property
    def user(self):
        if self.data:
            return self.data.get("user", "")
        return self.key.split("@", 1)[0]

    @property
    def machine(self):
        if self.data:
            return self.data.get("machine", "")
        return self.key.split("@", 1)[1] if "@" in self.key else ""

    @property
    def at(self):
        return (self.data or {}).get("at", "")

    @property
    def lock_id(self):
        return (self.data or {}).get("lock_id", "")


def lock_path(master_path, identity):
    master_path = Path(master_path)
    return master_path.with_name(f"{master_path.name}.{identity.key}{LOCK_SUFFIX}")


def list_locks(master_path):
    """共有データのロックファイルをすべて挙げる（VAブリッジの Dir("<マスタ>.*.lock") に当たる）。"""
    master_path = Path(master_path)
    prefix = master_path.name + "."
    found = []
    try:
        entries = list(master_path.parent.iterdir())
    except OSError:
        return found
    for p in entries:
        name = p.name
        if not (name.startswith(prefix) and name.endswith(LOCK_SUFFIX)) or fileio.is_temp_name(name):
            continue
        key = name[len(prefix):-len(LOCK_SUFFIX)]
        if not key:
            continue
        found.append(LockInfo(p, key, _read_lock(p)))
    return sorted(found, key=lambda li: li.key)


def _read_lock(path):
    try:
        obj = json.loads(fileio.read_bytes(path).decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    if not isinstance(obj, dict) or obj.get("format") != LOCK_FORMAT or not obj.get("lock_id"):
        return None
    return obj


def is_valid(lock, master):
    """ロックが有効か（master：いまの共有データ）。

    無効となるのは、ロックを取った後に、ほかの人が共有データを書き替えた場合だけ。
    読めないロックは有効とみなす（安全側）。
    """
    if lock.data is None:
        return True
    if lock.data.get("base_write_id") == master.write_id:
        return True   # ロックを取ってから、共有データは書き替えられていない
    if lock.lock_id and master.written.get("lock_id") == lock.lock_id:
        return True   # 最後に書いたのが、このロックの持ち主
    return False


def write_lock(master_path, identity, tool, master, *, sleep=time.sleep):
    """自分のロックファイルを書く（同じ人・PC の古いロックは置き換える）。書いたロックの lock_id を返す。"""
    lock_id = uuid.uuid4().hex
    content = {
        "format": LOCK_FORMAT,
        "tool": tool,
        "user": identity.user,
        "machine": identity.machine,
        "at": now_text(),
        "lock_id": lock_id,
        "base_version": master.version,
        "base_write_id": master.write_id,
    }
    raw = json.dumps(content, ensure_ascii=False, indent=1).encode("utf-8")
    fileio.write_atomic(lock_path(master_path, identity), raw, sleep=sleep)
    return lock_id


def remove_lock(path, *, sleep=time.sleep):
    fileio.delete(path, sleep=sleep)
