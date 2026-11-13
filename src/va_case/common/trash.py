"""ファイルをごみ箱へ移す（VA Filing・VA Receipt の「消す」。2026-11-09 班長決定）。

誤って消しても、ごみ箱から戻せるようにする。Windows では、シェルの機能（SHFileOperationW。ごみ箱を使う指定）を
ctypes で呼ぶ（外の部品は足さない）。Mac では、ホームの .Trash へ移す。

ネットワーク上のフォルダ（\\\\server\\share や、ネットワークドライブ）には、ごみ箱がなく、ごみ箱を使う指定でも
すぐに消えてしまう。戻せないので、その場合は消さずに TrashError とする（利用者にエクスプローラーで消してもらう）。
"""
import ctypes
import os
import shutil
import sys
from pathlib import Path

FO_DELETE = 3
FOF_SILENT = 0x0004
FOF_NOCONFIRMATION = 0x0010
FOF_ALLOWUNDO = 0x0040
FOF_NOERRORUI = 0x0400
DRIVE_REMOTE = 4


class TrashError(OSError):
    pass


def is_network_path(path):
    """ネットワーク上のパスか（UNC か、ネットワークドライブ）。Windows 以外では False。"""
    if sys.platform != "win32":
        return False
    p = str(Path(path).resolve()) if Path(path).exists() else str(path)
    if p.startswith("\\\\"):
        return True
    drive = os.path.splitdrive(p)[0]
    if not drive:
        return False
    return ctypes.windll.kernel32.GetDriveTypeW(drive + "\\") == DRIVE_REMOTE


def send_to_trash(path):
    """ファイルをごみ箱へ移す。戻せない場所（ネットワーク）や、移せなかったときは TrashError。"""
    path = Path(path)
    if not path.exists():
        return
    if sys.platform == "win32":
        if is_network_path(path):
            raise TrashError(f"ネットワーク上のフォルダのファイルは、ごみ箱へ移せない（戻せなくなる）ため、消しませんでした。"
                             f"エクスプローラーで消してください。\n{path}")
        from ctypes import wintypes

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
                        ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
                        ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]

        op = SHFILEOPSTRUCTW()
        op.wFunc = FO_DELETE
        op.pFrom = str(path.resolve()) + "\0"     # 2つの \0 で終わる（もう1つは、文字列の終わりとして付く）
        op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
        shell32 = ctypes.windll.shell32
        shell32.SHFileOperationW.argtypes = [ctypes.POINTER(SHFILEOPSTRUCTW)]
        rc = shell32.SHFileOperationW(ctypes.byref(op))
        if rc != 0 or op.fAnyOperationsAborted or path.exists():
            raise TrashError(f"ごみ箱へ移せませんでした（ほかのアプリで開いているかもしれません）。\n{path}")
        return
    trash = Path.home() / ".Trash"
    if not trash.is_dir():
        raise TrashError(f"ごみ箱が見つからないため、消しませんでした。\n{path}")
    target = trash / path.name
    i = 1
    while target.exists():
        target = trash / f"{path.stem} {i}{path.suffix}"
        i += 1
    shutil.move(str(path), str(target))
