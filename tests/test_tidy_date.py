"""VA Filing・VA Receipt の日時の欄に、別の書き方を入れても、決まった形にそろえる（2026-11-13 班長決定「この形で
作る」）試験。"""
import tkinter as tk
from types import MethodType, SimpleNamespace

import pytest

from va_case.common.dates import compact_datetime
from va_case.common.ui.file_store_app import FileStoreApp
from va_case.filing import app as filing_app
from va_case.receipt import app as receipt_app
from conftest import reset_root


@pytest.mark.parametrize("text, receipt, filing", [
    ("2025/11/1", "20251101", "202511010000"),
    ("2025-11-01", "20251101", "202511010000"),
    ("2025.11.1", "20251101", "202511010000"),
    ("2025年11月1日", "20251101", "202511010000"),
    ("R7.11.1", "20251101", "202511010000"),
    ("令和7年11月1日", "20251101", "202511010000"),
    ("H31.4.30", "20190430", "201904300000"),
    ("２０２５／１１／１", "20251101", "202511010000"),          # 全角
    ("2025/11/1 10:30", "20251101", "202511011030"),
    ("R7.11.1 10時30分", "20251101", "202511011030"),
    ("2025年11月1日10時30分", "20251101", "202511011030"),     # 日と時刻の間に空白がない
    ("20251101", "20251101", "202511010000"),
    ("202511011030", "20251101", "202511011030"),
    ("  20251101 ", "20251101", "202511010000"),
    ("", "", ""),
])
def test_readable_forms(text, receipt, filing):
    assert compact_datetime(text, False) == receipt
    assert compact_datetime(text, True) == filing


@pytest.mark.parametrize("text", ["11/1", "2025/11", "20251301", "202511012460", "2025/2/30", "R7.11.1 25:00",
                                  "あした", "2025111", "１２３"])
def test_unreadable_forms(text):
    assert compact_datetime(text, False) is None
    assert compact_datetime(text, True) is None


@pytest.fixture(scope="module")
def root(tk_root):   # Tk は試験の全体で1つ（conftest の tk_root）。この試験の後で、作った部品を片付ける
    r = tk_root
    r.deiconify()
    yield r
    reset_root(r)


def make(cls, root, state="open", editing=True):
    names = []
    a = SimpleNamespace(_panel_state=state, editing=editing, data=object(), vars={"日時": tk.StringVar(root)})
    a._update_name = lambda rebranch=None: names.append(rebranch)
    a._tidy_date = MethodType(FileStoreApp._tidy_date, a)
    a._name_after_date = MethodType(cls._name_after_date, a)
    a.DATE_WITH_TIME = cls.DATE_WITH_TIME
    return a, names


@pytest.mark.parametrize("cls, typed, want, rebranch", [
    (filing_app.FilingApp, "R7.11.1 9:05", "202511010905", None),
    (receipt_app.ReceiptApp, "2025/11/1", "20251101", True),      # VA Receipt は枝番も作り直す
])
def test_tidy_in_panel(root, cls, typed, want, rebranch):
    a, names = make(cls, root)
    a.vars["日時"].set(typed)
    a._tidy_date()
    assert a.vars["日時"].get() == want and names == [rebranch]
    a._tidy_date()                                     # そろっていれば、何もしない
    assert names == [rebranch]
    a.vars["日時"].set("2025/11")                       # 読めなければ、そのまま（「保管する」のときに知らせる）
    a._tidy_date()
    assert a.vars["日時"].get() == "2025/11" and names == [rebranch]


@pytest.mark.parametrize("state, editing", [("stored", True), ("pending", True), ("open", False), (None, True)])
def test_no_tidy_when_not_editable(root, state, editing):
    a, names = make(filing_app.FilingApp, root, state, editing)
    a.vars["日時"].set("R7.11.1")
    a._tidy_date()
    assert a.vars["日時"].get() == "R7.11.1" and names == []


def test_filing_stops_on_unreadable_date(monkeypatch):
    shown, focused = [], []
    monkeypatch.setattr(filing_app.messagebox, "showinfo", lambda title, msg, **k: shown.append(msg))
    fake = SimpleNamespace(root=None, _case_name=lambda: "甲野太郎（貸金）",
                           widgets={"日時": SimpleNamespace(focus_set=lambda: focused.append("日時"))},
                           case_box=None)
    v = {"日時": "R7.11", "内容": "見積書", "保管フォルダ名": "", "保管ファイル名": ""}
    with pytest.raises(filing_app.StoreCancelled):
        filing_app.FilingApp._prepare_store(fake, ["1"] * 11, v)
    assert shown == ["日時を読めません。2025/11/1、R7.11.1、20251101 などの形で入れてください。"]
    assert focused == ["日時"]
