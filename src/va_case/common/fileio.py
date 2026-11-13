"""共有フォルダのファイルの読み書き（仕様.md の3.2・3.3）。

- 書き込みは、同じフォルダの一時ファイルに書いて、OS のバッファを書き出して（fsync）から、正式の名前に置き換える。
  書き込みの途中で落ちても、正式のファイルは元のまま残る。
- Windows では、ほかの人（ほかのプロセス）がファイルを読んでいる間は、置き換えが拒まれる（PermissionError）。
  少し待ってやり直す（VAブリッジの writeToMaster の「1秒待って3回まで」に当たる）。
- OS のファイルロックやファイルの監視（変更の通知）は使わない（ほかの PC に伝わらないため。3.3）。
"""
import os
import time
import uuid
from pathlib import Path

TMP_SUFFIX = ".tmp"

# 置き換え・読み込みを拒まれたときのやり直し（合わせて約5秒）
RETRY_COUNT = 10
RETRY_WAIT = 0.5


def temp_path_for(path):
    """path と同じフォルダに置く一時ファイルの名前。先頭の「.」と末尾の .tmp で、競合の写しと見分ける。"""
    path = Path(path)
    return path.with_name(f".{path.name}.{uuid.uuid4().hex[:12]}{TMP_SUFFIX}")


def _retry(func, *, retries=RETRY_COUNT, wait=RETRY_WAIT, sleep=time.sleep):
    for i in range(retries):
        try:
            return func()
        except PermissionError:
            if i == retries - 1:
                raise
            sleep(wait)
    return None


def read_bytes(path, *, sleep=time.sleep):
    """ファイルを読む。ほかの人が置き換えている最中で拒まれたら、少し待ってやり直す。"""
    return _retry(lambda: Path(path).read_bytes(), sleep=sleep)


def write_atomic(path, data, *, overwrite=True, sleep=time.sleep):
    """data（bytes）を、一時ファイルを介して path に書く。

    overwrite=False のときは、path がすでにあれば FileExistsError とする（新しいマスタ・バックアップを作るとき。
    ほかの人が同時に作ったものを上書きしない）。
    """
    path = Path(path)
    tmp = temp_path_for(path)
    try:
        with open(tmp, "xb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if overwrite:
            _retry(lambda: os.replace(tmp, path), sleep=sleep)
        else:
            _place_new(tmp, path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass  # 消せなかった一時ファイルは、名前で競合の写しと見分けるので、残っても害はない


def _place_new(tmp, path):
    """tmp を path に置く。path がすでにあれば FileExistsError。"""
    if os.name == "nt":
        os.rename(tmp, path)  # Windows の rename は、行き先があれば FileExistsError になる
        return
    # Mac などの rename は行き先を上書きするので、ハードリンクで「なければ作る」を行う。
    # ハードリンクを使えないドライブ（一部の暗号化した仮想ドライブなど）では、有無を確かめてから置き換える
    try:
        os.link(tmp, path)
    except FileExistsError:
        raise
    except OSError:
        if path.exists():
            raise FileExistsError(str(path))
        os.replace(tmp, path)


def delete(path, *, sleep=time.sleep):
    """ファイルを消す。なければ何もしない。"""
    def _do():
        try:
            Path(path).unlink()
        except FileNotFoundError:
            pass
    _retry(_do, sleep=sleep)


def is_temp_name(name):
    return name.startswith(".") and name.endswith(TMP_SUFFIX)


def find_conflict_copies(path):
    """同期・暗号化した仮想ドライブが作る「競合の写し」らしいファイルを探す（3.3）。

    path の名前の本体（拡張子の前）で始まり、同じ拡張子で終わる、path 以外のファイルを挙げる。
    例：VA_Case.json に対し「VA_Case-PC名.json」（OneDrive）・「VA_Case (Conflict 1).json」・
    「VA_Case (conflicted copy …).json」・「VA_Case (1).json」。一時ファイル（.….tmp）は除く。
    見つけても黙って使わず、利用者に知らせるためのもの。
    """
    path = Path(path)
    stem, suffix = path.stem.casefold(), path.suffix.casefold()
    found = []
    try:
        entries = list(path.parent.iterdir())
    except OSError:
        return found
    for p in entries:
        name = p.name
        folded = name.casefold()
        if folded == path.name.casefold() or is_temp_name(name):
            continue
        if folded.startswith(stem) and folded.endswith(suffix) and p.is_file():
            found.append(p)
    return sorted(found)
