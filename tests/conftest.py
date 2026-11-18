"""共通部品の試験の道具。

氏名などはすべて架空のもの（CLAUDE.md の4：実データは使わない）。
設定と誤りの記録は、試験ごとの一時フォルダに置く（班長の %APPDATA%\\VA Case に書かない。標準 02「テスト」）。
画面（Tk）は、試験の全体で1つだけ作る（tk_root）。Windows の Python では、Tk を作り直すと、まれに初期化に失敗する
（2026-11-19 に、試験のファイルごとに作っていたときに「Can't find a usable init.tcl」「invalid command name
"tcl_findLibrary"」で、画面の試験が飛ばされたり、落ちたりした）。
"""
import gc
import tkinter as tk

import pytest

from va_case.common.identity import Identity
from va_case.common.master import Table, create_master
from va_case.common.store import SharedStore

SCHEMA = {"事件": ["事件番号", "事件呼名", "相手方氏名"]}
TOOL = "VA Case"

ALICE = Identity("yamada", "PC-A")     # 架空の利用者
BOB = Identity("suzuki", "PC-B")


def sample_tables():
    return {"事件": Table(SCHEMA["事件"], [
        ["101", "甲野太郎（貸金）", "乙山次郎\n丙川三郎"],   # 複数の相手方は改行で区切る（現行と同じ）
        ["201", "丁田花子（離婚）", "丁田一郎"],
    ])}


class Clock:
    """sleep の代わり。待った秒数を数え、待つたびに呼ぶ関数（同期の遅れの間に起きることの再現）を受け付ける。"""

    def __init__(self):
        self.waited = 0.0
        self.hooks = []

    def __call__(self, seconds):
        self.waited += seconds
        if self.hooks:
            self.hooks.pop(0)()


@pytest.fixture
def shared(tmp_path):
    folder = tmp_path / "共有"
    folder.mkdir()
    path = folder / "VA_Case.json"
    create_master(path, TOOL, sample_tables(), ALICE)
    return path


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def make_store(shared, clock):
    def _make(identity, path=None, schema=SCHEMA):
        return SharedStore(path or shared, TOOL, schema, identity=identity, sleep=clock)
    return _make


@pytest.fixture(autouse=True)
def _config_dir(tmp_path_factory, monkeypatch):
    """設定と誤りの記録の置き場所（%APPDATA%\\VA Case）を、試験ごとの一時フォルダに差し替える。"""
    folder = tmp_path_factory.mktemp("appdata")
    monkeypatch.setenv("APPDATA", str(folder))
    return folder


@pytest.fixture(scope="session")
def tk_root():
    """試験の全体で1つの Tk。各試験のファイルの root の fixture が使い、終わりに reset_root で片付ける。"""
    try:
        r = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"画面がない環境（{e}）")
    from va_case.common.ui import theme
    theme.apply_theme(r)
    r.withdraw()
    yield r
    r.destroy()
    gc.collect()


def reset_root(r):
    """1つの試験のファイルが終わったら、作った部品と、右クリックのメニューの割り当てを片付け、隠す。"""
    from va_case.common.ui import text_menu
    for w in r.winfo_children():
        try:
            w.destroy()
        except tk.TclError:
            pass
    for cls in text_menu.CLASSES:
        r.unbind_class(cls, "<Button-3>")
    r.withdraw()
    r.geometry("")
    r.update_idletasks()
    gc.collect()
