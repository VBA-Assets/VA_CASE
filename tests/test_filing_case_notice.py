"""VA Filing の、VA Case の共有データの知らせ（2026-11-11 班長決定「空なら出さない」）の試験。"""
from types import SimpleNamespace

import pytest

from va_case.filing import app as filing_app


@pytest.fixture
def shown(monkeypatch):
    got = []
    monkeypatch.setattr(filing_app.messagebox, "showwarning", lambda title, msg, **k: got.append(msg))
    return got


def _app():
    return SimpleNamespace(case_error="", case_tables=None, root=None)


def test_empty_place_means_no_va_case_and_no_notice(shown):
    a = _app()
    for _ in range(3):                                   # 起動・最新の読み込みを何度しても出ない
        filing_app.FilingApp.on_extra(a, ("none", None))
    assert shown == [] and a.case_tables is None and a.case_status == "設定なし"


def test_unreadable_place_is_notified_once(shown):
    a = _app()
    filing_app.FilingApp.on_extra(a, ("error", "共有データのファイルが見つかりません。"))
    filing_app.FilingApp.on_extra(a, ("error", "共有データのファイルが見つかりません。"))   # 同じ誤りは繰り返さない
    assert len(shown) == 1 and "読めませんでした" in shown[0]
    filing_app.FilingApp.on_extra(a, ("ok", {"事件": None}))
    assert a.case_error == "" and a.case_status == "読めた"
