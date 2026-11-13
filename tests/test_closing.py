"""終了処理（ZIP を作って移送待ちに置く）の試験。氏名は架空。"""
import zipfile

import pytest

from va_case.case import closing
from va_case.case import model as m
from va_case.case.settings import CaseConfig
from va_case.common.errors import FolderMissingError


@pytest.fixture
def env(tmp_path):
    src = tmp_path / "事件" / "101甲野太郎"
    (src / "書証").mkdir(parents=True)
    (src / "空のフォルダ").mkdir()
    (src / "訴状.pdf").write_bytes(b"%PDF" + b"0" * 5000)
    (src / "書証" / "甲第1号証.pdf").write_bytes(b"%PDF" + b"1" * 3000)
    (tmp_path / "移送待ち").mkdir()
    rules = m.empty_tables()[m.FOLDER_RULES]
    rules.rows = [["C:終了", "A:事務所", "B:個人一般", "", r"個人一般\yyyy"]]
    row = m.blank_row(101)
    for k, v in {"現況": "C:終了", "受任区分": "A:事務所", "事件区分": "B:個人一般", "事件呼名": "甲野太郎（貸金）",
                 "終了年月日": "2025-03-31", "データフォルダ": str(src)}.items():
        row[m.COL[k]] = v
    cfg = CaseConfig(outbox=str(tmp_path / "移送待ち"))
    return tmp_path, src, rules, row, cfg


def test_zip_to_outbox_with_vault_layout(env):
    tmp, src, rules, row, cfg = env
    p = closing.plan(row, [row], rules, cfg)
    assert p.rel == "個人一般/2025/101甲野太郎.zip"
    count, size = closing.make_zip(p)
    assert count == 2 and p.target.exists() and not p.target.with_name(p.target.name + ".part").exists()
    with zipfile.ZipFile(p.target) as z:
        names = z.namelist()
        assert "101甲野太郎/書証/甲第1号証.pdf" in names and "101甲野太郎/空のフォルダ/" in names
        assert all(i.compress_type == zipfile.ZIP_STORED for i in z.infolist())   # 既定は無圧縮
    assert not (tmp / "保管庫").exists()                                          # 保管庫には触れない
    value = closing.archived_value(p.rel)
    assert closing.archived_location(value) == "個人一般\\2025\\101甲野太郎.zip"     # 利用者に示す場所
    closing.delete_source(p.source)
    assert not src.exists()


def test_no_vault_setting():
    # 終了した事件のデータは VA Case から開かない（2026-11-09 班長決定）。保管庫の場所は設定に持たない
    assert not hasattr(CaseConfig(), "vault")
    assert not hasattr(closing, "resolve_archived")


def test_compress_option(env):
    tmp, src, rules, row, cfg = env
    p = closing.plan(row, [row], rules, cfg)
    closing.make_zip(p, compress=True)
    with zipfile.ZipFile(p.target) as z:
        assert any(i.compress_type == zipfile.ZIP_DEFLATED for i in z.infolist())


def test_cancel_leaves_nothing(env):
    tmp, src, rules, row, cfg = env
    p = closing.plan(row, [row], rules, cfg)
    with pytest.raises(closing.Cancelled):
        closing.make_zip(p, cancelled=lambda: True)
    assert list((tmp / "移送待ち").rglob("*.zip*")) == [] and src.exists()


def test_outbox_missing_is_not_created(env):
    tmp, src, rules, row, cfg = env
    cfg.outbox = str(tmp / "閉じた金庫" / "移送待ち")
    with pytest.raises(FolderMissingError):
        closing.plan(row, [row], rules, cfg)
    assert not (tmp / "閉じた金庫").exists()


def test_absolute_rule_is_refused(env):
    tmp, src, rules, row, cfg = env
    for rule in (str(tmp / "保管庫" / "個人一般" / "yyyy"), r"Z:\よそ\yyyy", r"\\server\共有\yyyy"):
        rules.rows[0][4] = rule                                       # 現行のような絶対パスの規則
        with pytest.raises(ValueError, match="保管庫の中の場所"):
            closing.plan(row, [row], rules, cfg)
    assert list((tmp / "移送待ち").rglob("*")) == []


def test_refusals(env):
    tmp, src, rules, row, cfg = env
    other = list(row)
    other[m.COL["事件番号"]] = "102"
    other[m.COL["現況"]] = "A:未了"
    with pytest.raises(ValueError, match="まだ終わっていない事件（事件番号 102"):
        closing.plan(row, [row, other], rules, cfg)            # 同じフォルダの事件が続いていれば、ZIP にしない
    no_rule = list(row)
    no_rule[m.COL["事件区分"]] = "D:企業"
    with pytest.raises(ValueError, match="フォルダ規則がありません"):
        closing.plan(no_rule, [no_rule], rules, cfg)
    p = closing.plan(row, [row], rules, cfg)
    closing.make_zip(p)
    with pytest.raises(ValueError, match="すでにあります"):
        closing.plan(row, [row], rules, cfg)


# ------------------------------------------------------------ 現況を戻したとき（2026-11-10 班長決定）

def _closed(env, delete=True):
    tmp, src, rules, row, cfg = env
    p = closing.plan(row, [row], rules, cfg)
    closing.make_zip(p)
    if delete:
        closing.delete_source(p.source)
    closed = list(row)
    closed[m.COL["データフォルダ"]] = closing.archived_value(p.rel, row[m.COL["データフォルダ"]])
    closed[m.COL["現況"]] = "A:未了"
    return p, closed


def test_archived_value_keeps_origin(env):
    tmp, src, rules, row, cfg = env
    value = closing.archived_value("個人一般/2025/101甲野太郎.zip", str(src))
    assert value == f"保管庫：個人一般/2025/101甲野太郎.zip | 元の場所：{src}"
    assert closing.archived_rel(value) == "個人一般/2025/101甲野太郎.zip"
    assert closing.archived_origin(value) == str(src)
    assert closing.archived_location(value) == "個人一般\\2025\\101甲野太郎.zip"
    old = "保管庫：個人一般/2024/401癸山五郎.zip"                      # 元の場所の記録がない値（これまでの事件）
    assert closing.archived_rel(old) == "個人一般/2024/401癸山五郎.zip" and closing.archived_origin(old) == ""


def test_restore_unzips_to_origin(env):
    tmp, src, rules, row, cfg = env
    p, closed = _closed(env)
    r = closing.restore_plan(closed, cfg)
    assert r.kind == "unzip" and r.origin == src and r.zip_exists
    count, size = closing.unzip(r.zip_path, r.origin)
    assert count == 2 and size == 5004 + 3004
    assert (src / "書証" / "甲第1号証.pdf").read_bytes() == b"%PDF" + b"1" * 3000
    assert (src / "空のフォルダ").is_dir() and not list(tmp.glob("事件/*.展開中"))
    closing.delete_zip(r.zip_path, cfg.outbox)
    assert list((tmp / "移送待ち").rglob("*")) == [] and (tmp / "移送待ち").is_dir()   # 空になった上のフォルダも消す


def test_restore_when_folder_was_kept(env):
    tmp, src, rules, row, cfg = env
    p, closed = _closed(env, delete=False)
    r = closing.restore_plan(closed, cfg)
    assert r.kind == "folder" and r.origin_value == str(src) and r.zip_exists


def test_restore_after_moved_to_vault(env):
    tmp, src, rules, row, cfg = env
    p, closed = _closed(env)
    p.target.unlink()                                              # 利用者が保管庫へ移した
    r = closing.restore_plan(closed, cfg)
    assert r.kind == "moved" and not src.exists()


def test_restore_without_recorded_origin(env):
    tmp, src, rules, row, cfg = env
    p, closed = _closed(env)
    closed[m.COL["データフォルダ"]] = closing.archived_value(p.rel)
    r = closing.restore_plan(closed, cfg)
    assert r.kind == "unzip" and r.origin is None                    # 展開する場所を選んでもらう
    other = tmp / "選んだ場所"
    other.mkdir()
    closing.unzip(r.zip_path, other / r.zip_path.stem)
    assert (other / "101甲野太郎" / "訴状.pdf").is_file()


def test_restore_refusals(env):
    tmp, src, rules, row, cfg = env
    p, closed = _closed(env)
    with pytest.raises(ValueError, match="同じ名前"):
        src.write_text("x")                                          # 元の場所にファイルがある
        closing.restore_plan(closed, cfg)
    src.unlink()
    gone = list(closed)
    gone[m.COL["データフォルダ"]] = closing.archived_value(p.rel, str(tmp / "外したドライブ" / "101甲野太郎"))
    with pytest.raises(FolderMissingError):
        closing.restore_plan(gone, cfg)                              # 基点がないときは作らない
    assert not (tmp / "外したドライブ").exists()


def test_unzip_cancel_and_bad_zip_leave_nothing(env):
    tmp, src, rules, row, cfg = env
    p, closed = _closed(env)
    with pytest.raises(closing.Cancelled):
        closing.unzip(p.target, src, cancelled=lambda: True)
    assert not src.exists() and not list((tmp / "事件").iterdir())
    bad = tmp / "移送待ち" / "悪い.zip"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("悪い/../../外.txt", b"x")                        # 外へ出る名前は展開しない
    with pytest.raises(ValueError, match="形が"):
        closing.unzip(bad, tmp / "事件" / "悪い")
    assert not (tmp / "外.txt").exists() and not list((tmp / "事件").iterdir())


# ------------------------------------------------------------ 同じデータフォルダを使う事件（2026-11-13 班長決定）

def test_place_key():
    from va_case.common.paths import place_key
    base = r"C:\事務所"
    same = [r"事件\甲野太郎", "事件\\甲野太郎\\", "事件/甲野太郎", r"C:\事務所\事件\甲野太郎", r"c:\事務所\事件\.\甲野太郎" + "\\",
            r"C:\事務所\事件\x\..\甲野太郎"]
    assert len({place_key(v, base) for v in same}) == 1
    assert place_key(r"事件\甲野太郎（貸金）", base) != place_key(r"事件\甲野太郎", base)
    assert place_key("事件\\甲野太郎\\", "") == place_key("事件/甲野太郎", "")     # 基点がなくても、書き方はそろえる
    assert place_key("", base) == ""


def test_shared_folder_is_zipped_when_all_cases_are_finished(env):
    tmp, src, rules, row, cfg = env
    cfg.data_root = str(tmp)
    other = list(row)
    other[m.COL["事件番号"]], other[m.COL["事件呼名"]] = "102", "甲野太郎（建物明渡）"
    other[m.COL["データフォルダ"]] = "事件\\101甲野太郎\\"             # 同じフォルダを、相対パス・最後の「\」付きで
    other[m.COL["現況"]] = "A:未了"
    with pytest.raises(ValueError, match="最後の事件が終わったときに、まとめて ZIP"):
        closing.plan(row, [row, other], rules, cfg)            # 書き方が違っても、同じフォルダと分かる
    other[m.COL["現況"]] = "C:終了"
    p = closing.plan(row, [row, other], rules, cfg)            # みな終わったら、まとめて ZIP
    assert p.members == ["101", "102"] and p.source == src
    closing.make_zip(p)
    closed = [list(row), list(other)]
    for r in closed:
        r[m.COL["データフォルダ"]] = closing.archived_value(p.rel, r[m.COL["データフォルダ"]])
    assert closing.archived_members(closed[0], closed) == [closed[1]]
    elsewhere = list(row)
    elsewhere[m.COL["事件番号"]] = "103"
    elsewhere[m.COL["データフォルダ"]] = closing.archived_value("個人一般/2024/別.zip")
    assert closing.archived_members(closed[0], closed + [elsewhere]) == [closed[1]]   # 別の ZIP の事件は入れない
