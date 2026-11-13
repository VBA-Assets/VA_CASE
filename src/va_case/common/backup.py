"""日次バックアップ（VA事件データベースの Setup.PerformDailyBackup に当たる）。

その日の最初の読み込みのときに、共有データをバックアップのフォルダへ「yyyymmdd_<共有データの名前>.json」として写す。
- 現行と同じく、データが1件もないときと、その日のバックアップがすでにあるときは作らない。
- 現行は、バックアップのフォルダがなければ黙って何もしない。ここでは作らずに、ないことを知らせる（3.3。結果で返す）。
- 写すのは、読み込んで中身の確かめ（sha256）が通ったものだけとする（同期の途中の壊れたファイルを残さない）。
- 2人が同時に作ろうとしても、先にできた方を残す（上書きしない）。
- 古いバックアップは消さない（現行と同じ）。
"""
import time
from datetime import date
from enum import Enum
from pathlib import Path

from . import fileio
from .master import parse


class BackupResult(Enum):
    CREATED = "作った"
    EXISTS = "その日の分がすでにある"
    NO_DATA = "データがない"
    NOT_CONFIGURED = "バックアップのフォルダが設定されていない"
    FOLDER_MISSING = "バックアップのフォルダが見つからない"


def backup_name(master_path, day):
    return f"{day:%Y%m%d}_{Path(master_path).stem}.json"


def daily_backup(master_path, backup_folder, *, today=None, sleep=time.sleep):
    """その日のバックアップを作る。結果（BackupResult）と、作った（またはあった）ファイルのパスを返す。

    共有データが読めない・確かめが通らないときは、master.MasterCorruptError などをそのまま出す。
    """
    if not backup_folder:
        return BackupResult.NOT_CONFIGURED, None
    folder = Path(backup_folder)
    if not folder.is_dir():
        return BackupResult.FOLDER_MISSING, None
    target = folder / backup_name(master_path, today or date.today())
    if target.exists():
        return BackupResult.EXISTS, target
    raw = fileio.read_bytes(master_path, sleep=sleep)
    data = parse(raw, Path(master_path))
    if data.row_count() == 0:
        return BackupResult.NO_DATA, None
    try:
        fileio.write_atomic(target, raw, overwrite=False, sleep=sleep)
    except FileExistsError:
        return BackupResult.EXISTS, target
    return BackupResult.CREATED, target
