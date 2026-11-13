"""共有・ロックの試験（1つのプロセスの中で、2人の利用者になりすまして再現する）。

前半は、VAブリッジ（basSync）と同じ動きになることを確かめる。後半は、同期フォルダ・暗号化した仮想ドライブの
性質（仕様.md の3.3：遅れ・日時のずれ・置き換えが一気に行われない・競合の写し）を人為的に起こして確かめる。
"""
import json
import os

import pytest

from conftest import ALICE, BOB, SCHEMA, TOOL, sample_tables
from va_case.common import fileio, lock as lockmod
from va_case.common.errors import (ConflictCopyError, ConflictError, FolderMissingError, LockedByOtherError,
                                   LockRaceError, MasterCorruptError, NotEditingError, SchemaMismatchError,
                                   WriteVerifyError)
from va_case.common.identity import Identity
from va_case.common.master import Table, create_master, read_master, serialize


def edited(data, name="戊野五郎（交通事故）"):
    tables = {k: v.copy() for k, v in data.tables.items()}
    tables["事件"].rows.append([str(300 + len(tables["事件"].rows)), name, ""])
    return tables


# ---------------------------------------------------------------- 形式

def test_roundtrip_keeps_text(shared):
    data = read_master(shared, expected=SCHEMA)
    assert data.version == 1
    assert data.tables["事件"].rows == sample_tables()["事件"].rows   # 日本語・改行がそのまま
    text = shared.read_text(encoding="utf-8")
    assert "甲野太郎" in text and text.count("\n") >= 6                # 1行に1件（メモ帳で読める）


def test_schema_mismatch(make_store):
    store = make_store(ALICE, schema={"事件": ["事件番号", "事件呼名", "相手方氏名", "備考"]})
    with pytest.raises(SchemaMismatchError, match="ない列：備考"):
        store.load()


def test_create_does_not_overwrite(shared):
    with pytest.raises(FileExistsError):
        create_master(shared, TOOL, sample_tables(), BOB)


def test_missing_folder_is_not_created(tmp_path):
    vault = tmp_path / "金庫"       # 開いていない仮想ドライブ（フォルダがない）
    with pytest.raises(FolderMissingError):
        create_master(vault / "VA_Case.json", TOOL, sample_tables(), ALICE)
    with pytest.raises(FolderMissingError):
        read_master(vault / "VA_Case.json")
    assert not vault.exists()


# ---------------------------------------------------------------- VAブリッジと同じ動き

def test_one_editor_others_view(make_store):
    a, b = make_store(ALICE), make_store(BOB)
    a.begin_edit()
    assert a.is_editing()
    with pytest.raises(LockedByOtherError, match="yamada さん"):
        b.begin_edit()
    assert b.load().version == 1            # 閲覧はできる
    assert b.editor().user == "yamada"
    with pytest.raises(NotEditingError):     # 閲覧モードでは書き込めない
        b.save(edited(b.loaded))


def test_lock_file_name_and_content(make_store, shared):
    a = make_store(ALICE)
    a.begin_edit()
    path = shared.with_name("VA_Case.json.yamada@PC-A.lock")   # <マスタ>.<人>@<PC>.lock
    content = json.loads(path.read_text(encoding="utf-8"))
    assert content["user"] == "yamada" and content["machine"] == "PC-A" and content["lock_id"] == a.lock_id


def test_save_then_release(make_store):
    a, b = make_store(ALICE), make_store(BOB)
    data = a.begin_edit()
    saved = a.save(edited(data), end_edit=True)   # VAブリッジの「書き込みが完了しました。閲覧モードに戻ります」
    assert saved.version == 2 and not a.is_editing()
    assert b.begin_edit().tables["事件"].rows[-1][1] == "戊野五郎（交通事故）"


def test_keep_editing_after_save(make_store):
    a, b = make_store(ALICE), make_store(BOB)
    data = a.begin_edit()
    data = a.save(edited(data, "一"))
    data = a.save(edited(data, "二"))        # 書いた後も、編集を続けられる
    assert data.version == 3 and a.is_editing()
    with pytest.raises(LockedByOtherError):  # 書いた後も、ほかの人には編集中と見える
        b.begin_edit()


def test_stale_lock_is_cleaned(make_store, shared):
    """共有データより古いロック（ロックの後にほかの人が書き替えた）は無効として消す（cleanUpStaleLocks）。"""
    a, b = make_store(ALICE), make_store(BOB)
    a.begin_edit()
    old_lock = lockmod.lock_path(shared, ALICE)
    saved_lock = old_lock.read_bytes()
    a.end_edit()
    b.begin_edit()
    b.save(edited(b.loaded), end_edit=True)
    old_lock.write_bytes(saved_lock)          # 同期で古いロックがよみがえった
    c = make_store(Identity("tanaka", "PC-C"))
    c.begin_edit()                            # 古いロックに妨げられない
    assert not old_lock.exists()


def test_own_leftover_lock_is_replaced(make_store):
    """自分の PC で落ちて残ったロックは、次に自分が編集を始めると置き換わる（VAブリッジは自分の名前のロックを無視）。"""
    crashed = make_store(ALICE)
    crashed.begin_edit()
    again = make_store(ALICE)
    again.begin_edit()
    with pytest.raises(NotEditingError):      # 落ちた方（の残り）は、もう書き込めない
        crashed.save(edited(crashed.loaded))
    again.save(edited(again.loaded))


def test_same_user_other_pc_is_other(make_store):
    """同じ人でも、ほかの PC のロックは、ほかの人のロックとして扱う（VAブリッジと違う点）。"""
    a = make_store(ALICE)
    a.begin_edit()
    with pytest.raises(LockedByOtherError):
        make_store(Identity("yamada", "PC-NOTE")).begin_edit()


def test_lock_file_deleted_in_explorer(make_store):
    """残った「編集中」の印は、エクスプローラーで消してもらう（2026-11-09 班長決定）。消された人は書き込めない。"""
    a, b = make_store(ALICE), make_store(BOB)
    a.begin_edit()
    with pytest.raises(LockedByOtherError) as info:
        b.begin_edit()
    assert info.value.lock_file is not None and str(info.value.lock_file) in str(info.value)   # 消すファイルを示す
    info.value.lock_file.unlink()                     # エクスプローラーで消したことにする
    b.begin_edit()
    with pytest.raises(NotEditingError):
        a.save(edited(a.loaded))
    b.save(edited(b.loaded))


# ---------------------------------------------------------------- 同期フォルダ・仮想ドライブの性質（3.3）

def test_race_detected_after_writing_lock(make_store, shared, monkeypatch):
    """自分のロックを書いたのとほぼ同時に、ほかの人のロックが現れた → 自分のロックを消して退く（acquireLock の2回目の確かめ）。"""
    a = make_store(ALICE)
    real = lockmod.write_lock

    def both(*args, **kw):
        lock_id = real(*args, **kw)
        real(shared, BOB, TOOL, read_master(shared))     # 同じときに、ほかの人も書いた
        return lock_id
    monkeypatch.setattr(lockmod, "write_lock", both)
    with pytest.raises(LockRaceError, match="suzuki"):
        a.begin_edit()
    assert not lockmod.lock_path(shared, ALICE).exists()


def _hide(path):
    hidden = path.with_name("hidden_" + path.name)
    os.replace(path, hidden)
    return lambda: os.replace(hidden, path)


def test_locks_not_visible_writes_still_safe(make_store, shared):
    """同期の遅れで2人が互いのロックを見ないまま編集モードに入っても、後から書いた人は止まる（黙って上書きしない）。"""
    a, b = make_store(ALICE), make_store(BOB)
    a.begin_edit()
    show_a = _hide(lockmod.lock_path(shared, ALICE))
    b.begin_edit()                                           # A のロックがまだ届いていない
    show_b = _hide(lockmod.lock_path(shared, BOB))
    show_a()
    a.save(edited(a.loaded, "A の変更"))                      # B のロックはまだ届いていない
    show_b()
    with pytest.raises((ConflictError, NotEditingError)):
        b.save(edited(b.loaded, "B の変更"))
    names = [r[1] for r in read_master(shared).tables["事件"].rows]
    assert "A の変更" in names and "B の変更" not in names


def test_conflict_when_master_changed_after_load(make_store, shared):
    """読み込んだ後に共有データが書き替えられていたら止める（writeToMaster の競合の確かめ）。日時でなく write_id で見る。"""
    a = make_store(ALICE)
    data = a.begin_edit()
    other = read_master(shared)
    other.tables["事件"].rows.append(["999", "ほかの人の変更", ""])
    other.version += 1
    other.write_id = "x" * 32
    other.written = {"user": "suzuki", "machine": "PC-B", "at": "2026-11-09T10:00:00+09:00", "lock_id": ""}
    stat = shared.stat()
    shared.write_bytes(serialize(other))
    os.utime(shared, (stat.st_atime, stat.st_mtime - 3600))   # 日時は古いまま（同期で日時がずれた）
    with pytest.raises(ConflictError, match="suzuki"):
        a.save(edited(data))


def test_restored_backup_is_conflict(make_store, shared):
    """バックアップから戻して版の番号が巻き戻っても、取り違えない。"""
    a = make_store(ALICE)
    data = a.begin_edit()
    before = shared.read_bytes()
    data = a.save(edited(data))
    shared.write_bytes(before)                 # 戻した（版の番号は1に戻る）
    with pytest.raises(ConflictError):
        a.save(edited(data))


def test_timestamps_are_not_used(make_store, shared):
    """ファイルの更新日時がずれても（未来・過去）、ロックの判定は変わらない。"""
    a, b = make_store(ALICE), make_store(BOB)
    a.begin_edit()
    os.utime(shared, (0, 4102444800))                                   # 共有データが 2100 年
    os.utime(lockmod.lock_path(shared, ALICE), (0, 0))                  # ロックが 1970 年
    with pytest.raises(LockedByOtherError):
        b.begin_edit()
    a.end_edit()
    b.begin_edit()


@pytest.mark.parametrize("name", ["VA_Case (Conflict 1).json", "VA_Case-PC-B.json",
                                  "VA_Case (conflicted copy 2026-11-09).json", "VA_Case (1).json"])
def test_conflict_copy_stops_edit(make_store, shared, name):
    a = make_store(ALICE)
    (shared.parent / name).write_bytes(shared.read_bytes())
    assert a.load().version == 1               # 閲覧は止めない
    assert [p.name for p in a.conflict_copies()] == [name]
    with pytest.raises(ConflictCopyError, match="競合の写し"):
        a.begin_edit()


def test_conflict_copy_appears_while_editing(make_store, shared):
    a = make_store(ALICE)
    data = a.begin_edit()
    (shared.parent / "VA_Case (Conflict 1).json").write_bytes(shared.read_bytes())
    with pytest.raises(ConflictCopyError):
        a.save(edited(data))


def test_temp_and_lock_files_are_not_conflict_copies(make_store, shared):
    a = make_store(ALICE)
    a.begin_edit()
    fileio.temp_path_for(shared).write_bytes(b"{")      # 消し損ねた一時ファイル
    assert a.conflict_copies() == []


def test_torn_file_is_detected(shared, clock):
    """置き換えが一気に行われず、途中まで届いたファイルは、確かめで見分けて読み直す。"""
    full = shared.read_bytes()
    shared.write_bytes(full[: len(full) // 2])
    with pytest.raises(MasterCorruptError):
        read_master(shared, sleep=clock)
    clock.hooks.append(lambda: shared.write_bytes(full))   # 待つ間に、同期が終わった
    assert read_master(shared, sleep=clock).version == 1


def test_tampered_content_is_detected(shared, clock):
    """形は正しくても中身が書いたものと違う（ハッシュが合わない）ものは使わない。"""
    text = shared.read_text(encoding="utf-8").replace("丁田一郎", "丁田二郎")
    shared.write_text(text, encoding="utf-8")
    with pytest.raises(MasterCorruptError, match="ハッシュ"):
        read_master(shared, sleep=clock)


def test_write_is_verified(make_store, shared, monkeypatch):
    a = make_store(ALICE)
    data = a.begin_edit()
    original = fileio.write_atomic

    def lost_write(path, raw, **kw):   # 書いたはずが、ほかのものに置き換わった
        original(path, serialize(read_master(shared)), **kw)
    monkeypatch.setattr(fileio, "write_atomic", lost_write)
    with pytest.raises(WriteVerifyError):
        a.save(edited(data))


def test_unreadable_lock_counts_as_locked(make_store, shared):
    """読めないロック（同期の途中など）は、安全側に倒して有効とみなす。"""
    lockmod.lock_path(shared, BOB).write_bytes(b'{"format": "va_ca')
    with pytest.raises(LockedByOtherError, match="suzuki"):
        make_store(ALICE).begin_edit()


def test_failed_write_leaves_master_intact(make_store, shared, monkeypatch):
    """書き込みの途中で落ちても、共有データは元のまま残る（一時ファイルに書いてから置き換える）。"""
    a = make_store(ALICE)
    data = a.begin_edit()
    before = shared.read_bytes()

    def crash(*args, **kw):
        raise OSError("書き込みの途中で落ちた")
    monkeypatch.setattr(os, "replace", crash)
    with pytest.raises(OSError):
        a.save(edited(data))
    monkeypatch.undo()
    assert shared.read_bytes() == before
    assert [p for p in shared.parent.iterdir() if p.name.endswith(".tmp")] == []


def test_no_waiting_for_sync(make_store, clock):
    """同期の伝わりを待たない（2026-11-11 班長決定。VAブリッジの Ver300 以降と同じ）。"""
    a = make_store(ALICE)
    data = a.begin_edit()
    a.save(edited(data), end_edit=True)
    assert clock.waited == 0


def test_table_values_must_be_text(make_store):
    a = make_store(ALICE)
    a.begin_edit()
    with pytest.raises(ValueError):
        a.save({"事件": Table(SCHEMA["事件"], [["101", 5, ""]])})
