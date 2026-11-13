"""一覧を矢印キーで送っている間は入力欄を書き換えない（2026-11-13 班長指摘「VA FILINGでは、矢印キーを押している間も
カードの更新が行われているような気がする」・班長指示「VA Phoneも同じことを確認。」）試験。VA Filing・VA Receipt
（file_store_app.py）と VA Call、VA Case のカード（2026-11-13 のリファクタリングで list_view.py にまとめた）。"""
from types import MethodType, SimpleNamespace

import pytest

from va_case.call.app import CallApp
from va_case.case.app import CaseApp
from va_case.common.ui.file_store_app import FileStoreApp


class FakeRoot:
    def __init__(self):
        self.jobs = {}
        self.n = 0

    def after(self, ms, func):
        self.n += 1
        self.jobs[self.n] = (ms, func)
        return self.n

    def after_cancel(self, job):
        self.jobs.pop(job, None)

    def run(self):
        jobs, self.jobs = self.jobs, {}
        for _, func in jobs.values():
            func()


def make(cls, by_key, held):
    shown, previews = [], []
    a = SimpleNamespace(root=FakeRoot(), _show_job=None, current="1", SHOW_DELAY_MS=cls.SHOW_DELAY_MS,
                        selected=["1"], data=SimpleNamespace(tables={}))
    a.expand_selection = lambda tree: None
    a.tree = None
    a.moved_by_key_recently = lambda: by_key[0]
    a.key_held = lambda: held[0]
    a.selected_key = lambda: a.selected[0]
    a.m = SimpleNamespace(row_by_number=lambda tables, number: ["row", number])
    a._file_path = lambda row: f"{row[1]}.pdf"
    a.preview = SimpleNamespace(show=lambda path, wait=False: previews.append((path, wait)))
    a._show_selected = lambda: shown.append(a.selected[0])
    for name in ("_on_select", "flush_selected", "_show_due", "_cancel_show", "_selected_by_key"):
        setattr(a, name, MethodType(getattr(cls, name), a))
    return a, shown, previews


@pytest.mark.parametrize("cls", [FileStoreApp, CallApp, CaseApp])
def test_panel_waits_while_moving_by_key(cls):
    by_key, held = [True], [True]
    a, shown, previews = make(cls, by_key, held)
    for number in ("2", "3", "4"):                 # 押し続けて3行送る
        a.selected = [number]
        a._on_select()
    assert shown == []                             # 入力欄は、まだ書き換えない
    if cls is FileStoreApp:                        # プレビューは空にして待つ
        assert previews == [("2.pdf", True), ("3.pdf", True), ("4.pdf", True)]
    assert len(a.root.jobs) == 1 and next(iter(a.root.jobs.values()))[0] == cls.SHOW_DELAY_MS
    a.root.run()                                   # 時刻が来ても、まだ押し続けていれば、さらに待つ
    assert shown == [] and len(a.root.jobs) == 1
    held[0] = False                                # 離した
    a.root.run()
    assert shown == ["4"]


@pytest.mark.parametrize("cls", [FileStoreApp, CallApp, CaseApp])
def test_click_shows_at_once_and_actions_flush(cls):
    by_key, held = [False], [False]
    a, shown, _ = make(cls, by_key, held)
    a.selected = ["2"]
    a._on_select()
    assert shown == ["2"] and not a.root.jobs     # クリックは、すぐ書き換える
    by_key[0] = True
    a.selected = ["5"]
    a._on_select()
    a.flush_selected()                             # 保管する・消す・メールを送るなどの前に、待たずに書き換える
    assert shown == ["2", "5"] and not a.root.jobs
    a.flush_selected()                             # 待っていなければ、何もしない
    assert shown == ["2", "5"]


def test_key_held():
    from va_case.common.ui.list_view import ListView
    import time
    v = SimpleNamespace(_hold=None, _released_at=None, last_key_move=time.monotonic())
    v.moved_by_key_recently = MethodType(ListView.moved_by_key_recently, v)
    assert not ListView.key_held(v)                # 押していない
    v._hold = {"step": 1}
    assert ListView.key_held(v)                    # 押した後に「離す」が来ていない
    v._released_at = 123
    assert not ListView.key_held(v)                # 離した
    v._released_at, v.last_key_move = None, time.monotonic() - 2
    assert not ListView.key_held(v)                # 「離す」が来ないまま1秒たった
