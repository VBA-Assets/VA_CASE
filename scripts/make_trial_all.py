"""4つのツール（VA Case・VA Filing・VA Receipt・VA Call）の試用の場所を、まとめて作る（利用者が使う。配布物の source に入る）。

氏名・住所・番号・ファイルは、すべて架空。実データを使わずに、ツールを試す・AI を使ってツールを改造するときに使う
（操作マニュアルの「AI を使ってツールを改造するとき」。2026-11-14、公開のときに作った）。

使い方（Python を入れた PC で、配布物の source フォルダの中で）：
    python scripts\\make_trial_all.py [作る場所]

    作る場所を省くと、source フォルダの中の「試験用」に作る。すでにあれば作り直さない（消してから実行する）。

作るもの：
    共有\\        VA_Case.json・VA_Filing.json・VA_Receipt.json・VA_Call.json（4つのツールの共有データ）
    事件\\        架空の事件のデータフォルダ
    スキャン\\    VA Filing の読込フォルダ（架空のファイル。読み込む前のものを含む）
    領収書スキャン\\  VA Receipt の読込フォルダ（架空の領収書。読み込む前のものを含む）
    経理\\・未確認\\・写し\\・職務上請求\\・文献\\・移送待ち\\・保管庫\\・バックアップ\\ など

最後に、この PC の4つのツールの設定（%APPDATA%\\VA Case）を、試用の場所に向けるかを一度だけ尋ねる。向けると、前の設定は
「<ツール>_試用前.json」に残す（元に戻すときは、その名前を「<ツール>.json」に戻す）。

中では、ツールごとのスクリプト（make_trial.py・make_trial_filing.py・make_trial_receipt.py・make_trial_call.py）を順に動かす。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from va_case.call import settings as call_settings  # noqa: E402
from va_case.case import settings as case_settings  # noqa: E402
from va_case.filing import settings as filing_settings  # noqa: E402
from va_case.receipt import settings as receipt_settings  # noqa: E402

STEPS = [
    # (スクリプト, 引数〔場所の前〕, 何を作るか)
    ("make_trial.py", [], "VA Case の共有データと事件のフォルダ"),
    ("make_trial_filing.py", [], "VA Filing の共有データと読込フォルダ"),
    ("make_trial_filing.py", ["--unread"], "VA Filing の、読み込む前のファイル"),
    ("make_trial_receipt.py", [], "VA Receipt の共有データと読込フォルダ"),
    ("make_trial_receipt.py", ["--unread"], "VA Receipt の、読み込む前の領収書"),
    ("make_trial_call.py", [], "VA Call の共有データ"),
]


def run(base):
    for script, extra, what in STEPS:
        print(f"── {what}")
        # 各スクリプトの「設定を試用の場所に向けますか」には「いいえ」と答える（最後に4つまとめて尋ねる）
        r = subprocess.run([sys.executable, str(SCRIPTS / script), *extra, str(base)], input="n\n", text=True,
                           encoding="utf-8", capture_output=True, cwd=ROOT)
        out = "\n".join(line for line in r.stdout.splitlines() if "[y/N]" not in line).strip()
        if out:
            print(out)
        if r.returncode != 0:
            print(r.stderr.strip())
            raise SystemExit(f"{script} で止まりました。")


def point_settings(base):
    shared = base / "共有"
    configs = [
        (case_settings, case_settings.CaseConfig(master_path=str(shared / "VA_Case.json"),
                                                  backup_folder=str(base / "バックアップ"),
                                                  outbox=str(base / "移送待ち"))),
        (filing_settings, filing_settings.FilingConfig(master_path=str(shared / "VA_Filing.json"),
                                                        backup_folder=str(base / "バックアップ"),
                                                        case_master_path=str(shared / "VA_Case.json"))),
        (receipt_settings, receipt_settings.ReceiptConfig(master_path=str(shared / "VA_Receipt.json"),
                                                           backup_folder=str(base / "バックアップ"))),
        (call_settings, call_settings.CallConfig(master_path=str(shared / "VA_Call.json"),
                                                  backup_folder=str(base / "バックアップ"))),
    ]
    for mod, cfg in configs:
        path = mod.common_config.config_path(mod.TOOL_KEY)
        if path.exists():
            keep = path.with_name(path.stem + "_試用前.json")
            if keep.exists():
                print(f"前の設定の控え {keep.name} がすでにあるので、上書きせずに残します。")
            else:
                path.replace(keep)
                print(f"前の設定は {keep} に残しました。")
        mod.save(cfg)
    print("4つのツールの設定を、試用の場所に向けました。")


def main():
    # 書いたとおりの場所にする（resolve すると、割り当てたドライブ〔暗号化した仮想ドライブ・ネットワークドライブ〕が
    # \\サーバー\… の形に変わり、共有データに、その形の場所が書かれてしまう。2026-11-14 の試験で分かった）
    base = Path(sys.argv[1]).absolute() if len(sys.argv) > 1 else ROOT / "試験用"
    if base.exists() and any(base.iterdir()):
        print(f"すでにあります。作り直すときは、消してから実行してください：{base}")
        return
    if base.exists():
        base.rmdir()                # 空のフォルダなら、作り直す（ツールごとのスクリプトは、ないところに作る）
    run(base)
    print(f"\n試用の場所を作りました：{base}")
    folder = case_settings.common_config.config_dir()
    ans = input(f"この PC の4つのツールの設定（{folder}）を、試用の場所に向けますか？ [y/N] ").strip().lower()
    if ans == "y":
        point_settings(base)


if __name__ == "__main__":
    main()
