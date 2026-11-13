"""別のプロセス（別の PC に見立てる）として共有データを使う、試験用の働き手。test_multiprocess.py から起動する。

使い方：python mp_worker.py <src> <モード> <共有データ> <人> [引数…]
結果は JSON で標準出力に1行書く。
"""
import json
import random
import sys
import time


def main():
    src, mode, master, user = sys.argv[1:5]
    rest = sys.argv[5:]
    sys.path.insert(0, src)
    from va_case.common.errors import SharedError
    from va_case.common.identity import Identity
    from va_case.common.master import read_master
    from va_case.common.store import SharedStore

    schema = {"件数": ["名前", "値"]}
    me = Identity(user, "PC-" + user)

    if mode == "race":
        # 決めた時刻に一斉に編集を始め、取れたら少し持ち続ける（ほかの人の確かめが終わるまで）
        start, hold = float(rest[0]), float(rest[1])
        store = SharedStore(master, "試験", schema, identity=me)
        time.sleep(max(0.0, start - time.time()))
        try:
            store.begin_edit()
            ok, err = True, ""
            time.sleep(hold)
            store.end_edit()
        except SharedError as e:
            ok, err = False, type(e).__name__
        print(json.dumps({"user": user, "ok": ok, "err": err}))

    elif mode == "counter":
        # 編集を始め、件数を1増やして書き、編集を終える、を times 回くり返す
        times = int(rest[0])
        store = SharedStore(master, "試験", schema, identity=me)
        done, refused, conflicts = 0, 0, 0
        deadline = time.time() + 120
        while done < times and time.time() < deadline:
            try:
                data = store.begin_edit()
            except SharedError:
                refused += 1
                time.sleep(random.uniform(0.01, 0.1))
                continue
            try:
                t = data.tables["件数"].copy()
                t.rows[0][1] = str(int(t.rows[0][1]) + 1)
                store.save({"件数": t}, end_edit=True)
                done += 1
            except SharedError:
                conflicts += 1
                store.end_edit()
        print(json.dumps({"user": user, "done": done, "refused": refused, "conflicts": conflicts}))

    elif mode == "reader":
        # 書き込みと重なるように読み続け、読めなかった回数を数える
        seconds = float(rest[0])
        reads, errors = 0, []
        end = time.time() + seconds
        while time.time() < end:
            try:
                read_master(master, expected=schema)
                reads += 1
            except (SharedError, OSError) as e:
                errors.append(f"{type(e).__name__}: {e}")
        print(json.dumps({"user": user, "reads": reads, "errors": errors[:5], "error_count": len(errors)},
                         ensure_ascii=False))


if __name__ == "__main__":
    main()
