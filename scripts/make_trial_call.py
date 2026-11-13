"""VA Call の試用の場所を、VA Case の試用の場所（scripts\\make_trial.py で作る 試験用\\）に足す。

使い方：python scripts\\make_trial_call.py [試用の場所（既定は 作業フォルダ\\試験用）]
作るもの：共有\\VA_Call.json（架空の所員3人と、架空の電話メモ3件。番号は、メモを作った日の年月日＋その日の連番）。
番号の付け方を確かめる見本のメモを10件足すとき：python scripts\\make_trial_call.py --add10 [試用の場所]
所員の1人目「佐藤一郎」のユーザー名（Windows）に、
この PC のユーザー名を入れる（新しいメモの入力者に入るのを試せるように。試験用\\ は git に入れない）。
すでに VA_Call.json があれば作り直さない。最後に、この PC の VA Call の設定を試用の場所に向けるかを尋ねる。
"""
import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from va_case.call import model as m  # noqa: E402
from va_case.call import settings  # noqa: E402
from va_case.common.identity import Identity  # noqa: E402
from va_case.common.master import create_master  # noqa: E402

MEMOS = [
    dict(入力者="鈴木花子", 日時="2025-11-07 10:15", 相手先="甲野太郎", 電話番号="03-0000-0001", 用件="電話がありました。",
         対応="電話をいただきたい。", 内容="貸金の件で、期日の確認をしたい。", 宛先="佐藤一郎", メール送信日時="2025-11-07 10:20"),
    dict(入力者="鈴木花子", 日時="2025-11-07 14:40", 相手先="辛川花子", 電話番号="090-0000-0002", 用件="来訪されました。",
         対応="もう一度訪問します。", 内容="書類を持参。明日もう一度来所するとのこと。", 宛先="田中二郎",
         確認者="田中二郎", 処理="確認済み"),
    dict(入力者="佐藤一郎", 日時="2025-11-08 09:05", 相手先="己野六郎（相手方代理人）", 電話番号="06-1111-1111",
         用件="電話がありました。", 対応="もう一度電話します。", 内容="和解案について。午後に改めて電話するとのこと。",
         宛先="佐藤一郎"),
]


def number_on(tables, when):
    """when（YYYY-MM-DD HH:MM）にメモを作ったときの番号（年月日＋その日の連番の9桁。common/numbering.py）。
    試用のメモは、日時の日に作ったものとして振る。"""
    day = when[2:4] + when[5:7] + when[8:10]
    seq = [int(r[m.COL["番号"]][6:]) for r in tables[m.MEMO].rows
           if len(r[m.COL["番号"]]) == 9 and r[m.COL["番号"]].startswith(day)]
    return f"{day}{max(seq, default=0) + 1:03d}"


# --add10 で足す、番号の付け方を確かめる見本（2026-11-13 班長指示「各ツール用のサンプルデータを10件ずつ作成」）。
# 日をまたいで作り、その日ごとに 001 から番号が付くことを見られるようにする
MORE = [("2026-11-10 09:12", "甲野太郎", "03-0000-0001", "電話がありました。", "電話をいただきたい。", "期日の時刻の確認"),
        ("2026-11-10 11:40", "丑田商店", "03-0000-4101", "電話がありました。", "もう一度電話します。", "請求書の宛名について"),
        ("2026-11-10 16:05", "寅川一郎", "090-0000-4102", "来訪されました。", "", "委任状を持参"),
        ("2026-11-11 10:20", "辛川花子", "090-0000-0002", "電話がありました。", "電話をいただきたい。", "申立書の添付書類について"),
        ("2026-11-11 13:30", "卯野法律事務所", "03-0000-4103", "電話がありました。", "もう一度電話します。", "和解条項の案"),
        ("2026-11-11 17:45", "辰巳次郎", "090-0000-4104", "電話がありました。", "電話をいただきたい。", "相談の予約"),
        ("2026-11-12 09:00", "東京地方裁判所", "03-0000-2001", "電話がありました。", "電話をいただきたい。", "期日の変更について"),
        ("2026-11-12 15:10", "甲野太郎", "03-0000-0001", "電話がありました。", "", "書類を受け取ったとのこと"),
        ("2026-11-13 10:00", "巳山三郎", "090-0000-4105", "電話がありました。", "電話をいただきたい。", "交通事故の相談"),
        ("2026-11-13 11:25", "午田四郎", "03-0000-4106", "来訪されました。", "", "資料を持参")]


def add10(base):
    """番号の付け方を確かめる見本のメモを10件足す（共有データの書き込みの決まりを通して書く）。"""
    from va_case.common.store import SharedStore
    master = base / "共有" / m.MASTER_FILE_NAME
    if "試験用" not in master.parts or not master.exists():
        print(f"試用の共有データがないか、試用でないので、書きません：{master}")
        return
    store = SharedStore(master, m.TOOL, m.SCHEMA, identity=Identity("試用", "試用"))
    tables = store.begin_edit().tables     # ほかの人が編集中なら、ここで止まる
    try:
        added = []
        for when, partner, phone, matter, reply, content in MORE:
            row = [""] * len(m.MEMO_COLUMNS)
            row[m.COL["番号"]] = number_on(tables, when)
            for k, v in dict(入力者="鈴木花子", 日時=when, 相手先=partner, 電話番号=phone, 用件=matter, 対応=reply,
                              内容=content + "（番号の見本・架空）", 宛先="佐藤一郎").items():
                row[m.COL[k]] = v
            tables[m.MEMO].rows = m.sorted_rows(tables[m.MEMO].rows + [row])
            added.append(row[m.COL["番号"]])
        store.save(tables, end_edit=True)
    except BaseException:
        store.end_edit()
        raise
    print(f"メモを {len(added)} 件足しました（番号 {'・'.join(added)}）：{master}")


def main():
    if "--add10" in sys.argv[1:]:
        args = [a for a in sys.argv[1:] if a != "--add10"]
        add10(Path(args[0]) if args else ROOT / "試験用")
        return
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "試験用"
    if not (base / "共有").is_dir():
        print(f"先に scripts\\make_trial.py で VA Case の試用の場所を作ってください：{base}")
        return
    master = base / "共有" / m.MASTER_FILE_NAME
    if master.exists():
        print(f"すでにあります。作り直すときは、消してから実行してください：{master}")
        return
    tables = m.empty_tables()
    tables[m.STAFF].rows = [["佐藤一郎", "sato@example.jp", getpass.getuser()],
                            ["田中二郎", "tanaka@example.jp", ""], ["鈴木花子", "suzuki@example.jp", ""]]
    for spec in MEMOS:
        row = [""] * len(m.MEMO_COLUMNS)
        row[m.COL["番号"]] = number_on(tables, spec["日時"])   # メモを作った日の番号（2026-11-13）
        for k, v in spec.items():
            row[m.COL[k]] = v
        tables[m.MEMO].rows.append(row)
    create_master(master, m.TOOL, tables, Identity("試用", "試用"))
    print(f"VA Call の試用の共有データを作りました：{master}")
    cfg_path = settings.common_config.config_path(settings.TOOL_KEY)
    ans = input(f"この PC の VA Call の設定（{cfg_path}）を、試用の場所に向けますか？ [y/N] ").strip().lower()
    if ans == "y":
        if cfg_path.exists():
            keep = cfg_path.with_name(cfg_path.stem + "_試用前.json")
            cfg_path.replace(keep)
            print(f"前の設定は {keep} に残しました。")
        settings.save(settings.CallConfig(master_path=str(master), backup_folder=str(base / "バックアップ")))
        print("設定を書きました。python main_call.py で起動してください。")


if __name__ == "__main__":
    main()
