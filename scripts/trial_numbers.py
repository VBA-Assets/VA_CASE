"""番号の付け方を確かめる見本（2026-11-13 班長指示「新しい番号の付け方を確認するため、各ツール用のサンプルデータを
10件ずつ作成」）を、VA Filing・VA Receipt の試用の共有データに足す部品（make_trial_filing.py・make_trial_receipt.py の
--add10 で使う）。

読込フォルダにファイルを作り、それを、決めた日に読み込んだものとして、保管の表に足す。番号は、読み込んだ日の年月日＋
その日の連番（common/numbering.py と同じ形）。日をまたいで足し、その日ごとに 001 から番号が付くことを見られるようにする
（アプリの「ファイルを読み込む」は、いまの日付で番号を付けるので、前の日の見本は作れないため）。共有データの書き込みの
決まり（ロック・競合の確認）を通して書くので、ほかの人（画面を含む）が編集モードのときは、書かずに止まる。
"""
import os
import time
from datetime import datetime

from va_case.common.identity import Identity
from va_case.common.store import SharedStore


def number_on(rows, col, day):
    """day（yymmdd）に読み込んだときの、次の番号。"""
    seq = [int(r[col][6:]) for r in rows if len(r[col]) == 9 and r[col].isdigit() and r[col].startswith(day)]
    return f"{day}{max(seq, default=0) + 1:03d}"


def add_read_files(master, m, scan, files, make_file):
    """files：[(読み込んだ日時 "YYYY-MM-DD HH:MM", ファイル名, ファイルを作るための値)]。make_file(名前, 値) → bytes。"""
    if "試験用" not in master.parts or not master.exists() or not scan.is_dir():
        print(f"試用の共有データか読込フォルダがないか、試用でないので、書きません：{master}")
        return
    store = SharedStore(master, m.TOOL, m.SCHEMA, identity=Identity("試用", "試用"))
    tables = store.begin_edit().tables     # ほかの人が編集中なら、ここで止まる
    try:
        folder_value = tables[m.READ_FOLDERS].rows[0][0]
        col = m.COL["番号"]
        added = []
        for when, name, spec in files:
            p = scan / name
            if p.exists():
                print(f"同じ名前のファイルがあるので、足しません：{name}")
                continue
            p.write_bytes(make_file(name, spec))
            t = time.mktime(datetime.strptime(when, "%Y-%m-%d %H:%M").timetuple())
            os.utime(p, (t, t))
            before = {r[col] for r in tables[m.STORE].rows}
            tables, n, _ = m.merge_found(tables, [m.FoundFile(folder_value, name, t)], [])
            row = next(r for r in tables[m.STORE].rows if r[col] not in before)
            others = [r for r in tables[m.STORE].rows if r is not row]
            row[col] = number_on(others, col, when[2:4] + when[5:7] + when[8:10])   # 読み込んだ日の番号
            tables[m.STORE].rows = m.sorted_rows(tables[m.STORE].rows)
            added.append(row[col])
        store.save(tables, end_edit=True)
    except BaseException:
        store.end_edit()
        raise
    print(f"{len(added)} 件足しました（番号 {'・'.join(added)}）：{master}")


def make_unread(scan, files, make_file):
    """読み込む前の見本のファイルを作る（共有データは変えない。2026-11-13 班長指示「VA Filing と VA Receipt　読み込み前の
    状態のサンプルを作成」）。アプリの「ファイルを読み込む」で読み込むと、その日の年月日＋連番の番号が付く。
    files：[(読込フォルダの中の場所, ファイルを作るための値)]。同じ名前があれば作らない。"""
    if not scan.is_dir():
        print(f"読込フォルダがありません：{scan}")
        return
    made = []
    for rel, spec in files:
        p = scan / rel
        if p.exists():
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(make_file(p.name, spec))
        made.append(rel)
    print(f"読み込む前の見本のファイルを {len(made)} 個作りました（すでにあった {len(files) - len(made)} 個は作っていません）：{scan}")
    print("アプリで「編集を始める」→「ファイルを読み込む」を押すと、一覧に入り、番号が付きます。")
