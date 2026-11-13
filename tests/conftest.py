"""共通部品の試験の道具。

氏名などはすべて架空のもの（CLAUDE.md の4：実データは使わない）。
"""
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
