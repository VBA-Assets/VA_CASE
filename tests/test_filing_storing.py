"""VA Filing の保管・元に戻す（ファイルの移動・ショートカット・写し）の試験。"""
import sys

import pytest

from va_case.common.paths import resolve_folder
from va_case.filing import model as m
from va_case.common import shortcut, storing

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="ショートカットは Windows だけ")


@pytest.fixture
def env(tmp_path):
    scan = tmp_path / "スキャン"
    case = tmp_path / "事件" / "101甲野太郎"
    for d in (scan, case, tmp_path / "未確認" / "佐藤", tmp_path / "写し" / "佐藤", tmp_path / "職務上請求"):
        d.mkdir(parents=True)
    src = scan / "202503011030.pdf"
    src.write_bytes(b"%PDF-1.4 " + b"x" * 2000)
    return tmp_path, src, case


def resolve(tmp):
    return lambda v: resolve_folder(v, str(tmp))


def test_store_and_restore_with_copies(env):
    tmp, src, case = env
    name = "20250301103000000甲野太郎（貸金）　住民票の職務上請求.pdf"
    targets = [(m.KIND_COPY, r"写し\佐藤")]
    specials = [("職務上請求", "職務上請求")]
    p = storing.plan_store(src, r"事件\101甲野太郎", name, targets, specials, resolve=resolve(tmp))
    res = storing.store(p)
    assert not src.exists() and (case / name).read_bytes().startswith(b"%PDF")
    assert (tmp / "写し" / "佐藤" / name).exists() and (tmp / "職務上請求" / name).exists()
    assert len(res.made) == 2
    rp = storing.plan_restore(case / name, src, targets, specials, resolve=resolve(tmp), file_name=name)
    removed = storing.restore(rp)
    assert src.exists() and not (case / name).exists() and len(removed) == 2
    assert not (tmp / "写し" / "佐藤" / name).exists() and not (tmp / "職務上請求" / name).exists()


@windows_only
def test_shortcut_points_to_stored_file(env):
    tmp, src, case = env
    name = "x.pdf"
    p = storing.plan_store(src, str(case), name, [(m.KIND_SHORTCUT, str(tmp / "未確認" / "佐藤"))], [],
                           resolve=resolve(tmp))
    storing.store(p)
    lnk = tmp / "未確認" / "佐藤" / "x.pdf.lnk"
    assert shortcut.read(lnk) == (str(case / name), str(case))      # リンク先と作業フォルダ（現行と同じ）
    rp = storing.plan_restore(case / name, src, [(m.KIND_SHORTCUT, str(tmp / "未確認" / "佐藤"))], [],
                              resolve=resolve(tmp), file_name=name)
    storing.restore(rp)
    assert not lnk.exists() and src.exists()


def test_checks_before_moving_anything(env):
    tmp, src, case = env
    with pytest.raises(storing.StoringError, match="がありません"):          # 写しの置き場所がない
        storing.plan_store(src, str(case), "x.pdf", [(m.KIND_COPY, str(tmp / "ない"))], [], resolve=resolve(tmp))
    with pytest.raises(storing.StoringError, match="見つかりません"):        # 保管フォルダがない（作らない）
        storing.plan_store(src, str(tmp / "閉じた金庫" / "事件"), "x.pdf", [], [], resolve=resolve(tmp))
    assert not (tmp / "閉じた金庫").exists()
    (case / "x.pdf").write_bytes(b"old")
    with pytest.raises(storing.StoringError, match="同じ名前"):
        storing.plan_store(src, str(case), "x.pdf", [], [], resolve=resolve(tmp))
    with pytest.raises(storing.StoringError, match="使えない字"):
        storing.plan_store(src, str(case), "a/b.pdf", [], [], resolve=resolve(tmp))
    with pytest.raises(storing.StoringError, match="事務所のフォルダの場所"):
        storing.plan_store(src, r"相対\フォルダ", "y.pdf", [], [], resolve=lambda v: resolve_folder(v, ""))
    assert src.exists()


def test_failure_midway_rolls_back(env, monkeypatch):
    tmp, src, case = env
    targets = [(m.KIND_COPY, r"写し\佐藤"), (m.KIND_COPY, r"未確認\佐藤")]
    p = storing.plan_store(src, str(case), "x.pdf", targets, [], resolve=resolve(tmp))
    real = storing.make_link
    calls = []

    def flaky(link, target):
        calls.append(link)
        if len(calls) == 2:
            raise OSError("書けない")
        real(link, target)
    monkeypatch.setattr(storing, "make_link", flaky)
    with pytest.raises(OSError):
        storing.store(p)
    assert src.exists() and not (case / "x.pdf").exists()                 # ファイルは読込フォルダに戻る
    assert not (tmp / "写し" / "佐藤" / "x.pdf").exists()                   # 作った写しは消す


def test_undo_store_when_record_cannot_be_written(env):
    tmp, src, case = env
    p = storing.plan_store(src, str(case), "x.pdf", [(m.KIND_COPY, r"写し\佐藤")], [], resolve=resolve(tmp))
    res = storing.store(p)
    storing.undo_store(res)                       # 共有データに書けなかったとき
    assert src.exists() and not (case / "x.pdf").exists() and not (tmp / "写し" / "佐藤" / "x.pdf").exists()


def test_cross_device_move_copies_then_deletes(env, monkeypatch):
    tmp, src, case = env
    real_rename = storing.os.rename
    state = {"first": True}

    def rename(a, b):
        if state["first"]:
            state["first"] = False
            e = OSError("別のドライブ")
            e.winerror = 17
            raise e
        return real_rename(a, b)
    monkeypatch.setattr(storing.os, "rename", rename)
    storing.move_file(src, case / "x.pdf")
    assert not src.exists() and (case / "x.pdf").stat().st_size == 2009
    assert [p.name for p in case.iterdir()] == ["x.pdf"]                  # 一時のファイルは残らない


def test_restore_tolerates_missing_copies(env):
    tmp, src, case = env
    p = storing.plan_store(src, str(case), "x.pdf", [], [], resolve=resolve(tmp))
    storing.store(p)
    rp = storing.plan_restore(case / "x.pdf", src, [(m.KIND_COPY, r"写し\佐藤")], [], resolve=resolve(tmp),
                              file_name="x.pdf")
    assert rp.missing and not rp.links                 # 写しがなくても止めない（現行は止まった）
    storing.restore(rp)
    assert src.exists()
