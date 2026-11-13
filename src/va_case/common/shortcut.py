"""ショートカット（.lnk）を作る・読む（Windows だけ）。

現行（Sht1Hokan.MakeShortcuts）は WScript.Shell の CreateShortcut で作る。Python 版は、Windows がもとから持つ
シェルリンクの機能（IShellLinkW・IPersistFile）を ctypes で呼ぶ（2026-11-09 班長決定。外の部品〔pywin32〕は足さない。
VA Document の印刷と同じ考え方）。作られるショートカットは、現行と同じもの（リンク先と作業フォルダ）。

COM は呼ぶスレッドごとに初期化する（裏のスレッドから呼ぶため）。Windows 以外では available() が False になる。
"""
import ctypes
import sys
import uuid
from pathlib import Path

CLSID_SHELL_LINK = "00021401-0000-0000-C000-000000000046"
IID_ISHELL_LINK_W = "000214F9-0000-0000-C000-000000000046"
IID_IPERSIST_FILE = "0000010B-0000-0000-C000-000000000046"
CLSCTX_INPROC_SERVER = 1
COINIT_APARTMENTTHREADED = 2
RPC_E_CHANGED_MODE = -2147417850    # 0x80010106（このスレッドは別の方式で初期化ずみ。そのまま使える）
STGM_READ = 0
SLGP_RAWPATH = 4
MAX_PATH_W = 32768

# 仮想関数の表での位置（IUnknown の3つを含む）
_QUERY_INTERFACE, _RELEASE = 0, 2
_SL_GET_PATH, _SL_GET_WORKING_DIRECTORY, _SL_SET_WORKING_DIRECTORY, _SL_SET_PATH = 3, 8, 9, 20
_PF_LOAD, _PF_SAVE = 5, 6


def available():
    return sys.platform == "win32"


class ShortcutError(OSError):
    pass


if available():
    from ctypes import wintypes

    class _GUID(ctypes.Structure):
        _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort),
                    ("Data4", ctypes.c_ubyte * 8)]

    def _guid(text):
        u = uuid.UUID(text)
        g = _GUID()
        g.Data1, g.Data2, g.Data3 = u.fields[0], u.fields[1], u.fields[2]
        for i, b in enumerate(u.bytes[8:]):
            g.Data4[i] = b
        return g

    _ole32 = ctypes.WinDLL("ole32")
    _ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    _ole32.CoInitializeEx.restype = ctypes.c_long
    _ole32.CoUninitialize.argtypes = []
    _ole32.CoUninitialize.restype = None
    _ole32.CoCreateInstance.argtypes = [ctypes.POINTER(_GUID), ctypes.c_void_p, wintypes.DWORD,
                                        ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)]
    _ole32.CoCreateInstance.restype = ctypes.c_long

    def _method(ptr, index, restype, *argtypes):
        vtable = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
        proto = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
        return proto(vtable[index])

    def _check(hr, what):
        if hr < 0:
            raise ShortcutError(f"{what}に失敗しました（HRESULT 0x{hr & 0xFFFFFFFF:08X}）。")

    class _Com:
        """スレッドごとの COM の初期化と、シェルリンクのオブジェクト（IShellLinkW と IPersistFile）。"""

        def __enter__(self):
            hr = _ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
            self._uninit = hr >= 0          # S_OK・S_FALSE なら、終わりに対の CoUninitialize を呼ぶ
            if hr < 0 and hr != RPC_E_CHANGED_MODE:
                _check(hr, "COM の初期化")
            self.link = ctypes.c_void_p()
            self.file = ctypes.c_void_p()
            try:
                _check(_ole32.CoCreateInstance(ctypes.byref(_guid(CLSID_SHELL_LINK)), None, CLSCTX_INPROC_SERVER,
                                               ctypes.byref(_guid(IID_ISHELL_LINK_W)), ctypes.byref(self.link)),
                       "ショートカットの部品の作成")
                qi = _method(self.link, _QUERY_INTERFACE, ctypes.c_long, ctypes.POINTER(_GUID),
                             ctypes.POINTER(ctypes.c_void_p))
                _check(qi(self.link, ctypes.byref(_guid(IID_IPERSIST_FILE)), ctypes.byref(self.file)),
                       "ショートカットの保存の部品の取得")
            except BaseException:
                self.__exit__(None, None, None)
                raise
            return self

        def __exit__(self, *exc):
            for p in (self.file, self.link):
                if p:
                    _method(p, _RELEASE, ctypes.c_ulong)(p)
            self.file = self.link = None
            if self._uninit:
                _ole32.CoUninitialize()
            return False


def create(shortcut_path, target_path, working_dir=None):
    """target_path を指すショートカットを shortcut_path（.lnk）に作る。すでにあれば ShortcutError（上書きしない）。"""
    if not available():
        raise ShortcutError("ショートカットは Windows でだけ作れます。")
    shortcut_path = Path(shortcut_path)
    if shortcut_path.exists():
        raise ShortcutError(f"{shortcut_path} と同じ名前のショートカットが既にあります。")
    target = str(Path(target_path))
    workdir = str(Path(working_dir)) if working_dir else str(Path(target_path).parent)
    with _Com() as com:
        _check(_method(com.link, _SL_SET_PATH, ctypes.c_long, ctypes.c_wchar_p)(com.link, target),
               "ショートカットのリンク先の設定")
        _check(_method(com.link, _SL_SET_WORKING_DIRECTORY, ctypes.c_long, ctypes.c_wchar_p)(com.link, workdir),
               "ショートカットの作業フォルダの設定")
        _check(_method(com.file, _PF_SAVE, ctypes.c_long, ctypes.c_wchar_p, ctypes.c_int)(
            com.file, str(shortcut_path), 1), "ショートカットの保存")
    if not shortcut_path.exists():
        raise ShortcutError(f"ショートカットを作れませんでした：{shortcut_path}")


def read(shortcut_path):
    """ショートカットのリンク先と作業フォルダ → (リンク先, 作業フォルダ)。作ったものを確かめるために使う。"""
    if not available():
        raise ShortcutError("ショートカットは Windows でだけ読めます。")
    with _Com() as com:
        _check(_method(com.file, _PF_LOAD, ctypes.c_long, ctypes.c_wchar_p, ctypes.c_ulong)(
            com.file, str(Path(shortcut_path)), STGM_READ), "ショートカットの読み込み")
        buf = ctypes.create_unicode_buffer(MAX_PATH_W)
        _check(_method(com.link, _SL_GET_PATH, ctypes.c_long, ctypes.c_wchar_p, ctypes.c_int, ctypes.c_void_p,
                       ctypes.c_ulong)(com.link, buf, MAX_PATH_W, None, SLGP_RAWPATH), "リンク先の読み取り")
        target = buf.value
        wd = ctypes.create_unicode_buffer(MAX_PATH_W)
        _check(_method(com.link, _SL_GET_WORKING_DIRECTORY, ctypes.c_long, ctypes.c_wchar_p, ctypes.c_int)(
            com.link, wd, MAX_PATH_W), "作業フォルダの読み取り")
        return target, wd.value
