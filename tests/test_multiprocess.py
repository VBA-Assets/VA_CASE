"""2つ以上のプロセスから同じフォルダを使う試験（仕様.md の3.3）。

1台の PC の中で、別々のプロセスを別々の PC に見立てる。同期の遅れそのものは起きないが、同時の読み書き・置き換えの
重なり（Windows では、読んでいる間の置き換えが拒まれる）と、ロックの取り合いを実際に起こす。
"""
import json
import subprocess
import sys
import time
from pathlib import Path


from va_case.common.identity import Identity
from va_case.common.master import Table, create_master, read_master

SRC = str(Path(__file__).resolve().parents[1] / "src")
WORKER = str(Path(__file__).resolve().parent / "mp_worker.py")
SCHEMA = {"件数": ["名前", "値"]}


def _master(tmp_path):
    path = tmp_path / "試験.json"
    create_master(path, "試験", {"件数": Table(SCHEMA["件数"], [["件数", "0"]])}, Identity("setup", "PC-0"))
    return path


def _run(mode, path, users, *args):
    procs = [subprocess.Popen([sys.executable, WORKER, SRC, mode, str(path), u, *map(str, args)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
             for u in users]
    results = []
    for p in procs:
        out, err = p.communicate(timeout=180)
        assert p.returncode == 0, err
        results.append(json.loads(out.strip().splitlines()[-1]))
    return results


def test_lock_race_at_most_one_editor(tmp_path):
    """4つのプロセスが同じ時刻に編集を始めても、編集モードに入れるのは多くて1つ。
    同期を待たず、VAブリッジと同じく、ロックを書いた直後に確かめ直す（2026-11-11 班長決定）。取れたら 1.5 秒持ち続ける。"""
    path = _master(tmp_path)
    for _ in range(3):
        start = time.time() + 2.0
        results = _run("race", path, ["u1", "u2", "u3", "u4"], start, 1.5)
        winners = [r for r in results if r["ok"]]
        assert len(winners) <= 1, results
        for r in results:
            assert r["ok"] or r["err"] in ("LockedByOtherError", "LockRaceError"), results


def test_no_lost_update(tmp_path):
    """3つのプロセスが、編集の開始 → 件数を1増やす → 書いて終える、を5回ずつくり返す。

    途中で拒まれた回はやり直す。最後の件数が、書けた回数の合計（15）と一致すれば、上書きで失われた書き込みはない。
    """
    path = _master(tmp_path)
    results = _run("counter", path, ["u1", "u2", "u3"], 5, 0.05)
    done = sum(r["done"] for r in results)
    assert done == 15, results
    final = read_master(path, expected=SCHEMA)
    assert final.tables["件数"].rows[0][1] == "15"
    assert final.version == 1 + 15


def test_reads_during_writes(tmp_path):
    """書き込み（置き換え）が続く間に、ほかのプロセスが読み続けても、壊れたデータを読まない。"""
    path = _master(tmp_path)
    readers = [subprocess.Popen([sys.executable, WORKER, SRC, "reader", str(path), u, "6"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
               for u in ("r1", "r2")]
    writers = _run("counter", path, ["w1"], 20, 0.0)
    reads = []
    for p in readers:
        out, err = p.communicate(timeout=60)
        assert p.returncode == 0, err
        reads.append(json.loads(out.strip().splitlines()[-1]))
    assert writers[0]["done"] == 20
    for r in reads:
        assert r["reads"] > 0 and r["error_count"] == 0, r
    assert read_master(path).tables["件数"].rows[0][1] == "20"
