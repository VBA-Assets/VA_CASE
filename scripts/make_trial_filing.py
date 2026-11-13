"""VA Filing の試用の場所を、VA Case の試用の場所（scripts\\make_trial.py で作る 試験用\\）に足す。

使い方：python scripts\\make_trial_filing.py [試用の場所（既定は 作業フォルダ\\試験用）]
作るもの：共有\\VA_Filing.json、スキャン\\（読込フォルダ。架空のファイル）、未確認\\佐藤・田中（ショートカット）、
写し\\佐藤（コピー）、職務上請求\\（特別な写し）。すでに VA_Filing.json があれば作り直さない。
最後に、この PC の VA Filing の設定（%APPDATA%\\VA Case\\filing.json）を試用の場所に向けるかを尋ねる。

python scripts\\make_trial_filing.py --pdfs [試用の場所] とすると、試用の場所の中の、開けない見本の PDF（前の版の
このスクリプトが作った、1行目だけのもの）を、開ける PDF に作り直す（名前と日時はそのまま）。

python scripts\\make_trial_filing.py --add [試用の場所] とすると、スキャン\\ に、複数ページの見本の PDF（MULTI_PAGE）を足す
（2026-11-12 班長指示「VA Filingのサンプルに複数ページのPDFを追加」。プレビューでページが縦に並ぶのを試すため）。
あわせて、一覧がスクロールするだけの数の1ページの見本（MANY_FILES。30個）も足す（2026-11-12 班長指示「VA Filingのリストの
スクロールも確認できるように、サンプルを追加」）。共有データは変えない。同じ名前があれば足さない。最初から作るときも、これらを作る。

python scripts\\make_trial_filing.py --add10 [試用の場所] とすると、番号の付け方を確かめる見本を10件足す（2026-11-13 班長指示
「新しい番号の付け方を確認するため、各ツール用のサンプルデータを10件ずつ作成」）。スキャン\\ にファイルを作り、11月10日・
11日・13日に読み込んだものとして保管の表に足す（番号は、読み込んだ日の年月日＋その日の連番。scripts\\trial_numbers.py）。

python scripts\\make_trial_filing.py --unread [試用の場所] とすると、読み込む前の見本のファイルを10個、スキャン\\ に作る
（2026-11-13 班長指示「VA Filing と VA Receipt　読み込み前の状態のサンプルを作成」）。共有データは変えない。アプリの
「ファイルを読み込む」で読み込むと、その日の年月日＋連番の番号が付く。
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from va_case.case import model as cm  # noqa: E402
from va_case.common.identity import Identity  # noqa: E402
from va_case.common.master import create_master  # noqa: E402
from va_case.filing import model as m  # noqa: E402
from va_case.filing import settings  # noqa: E402

FAKE_HEAD = "%PDF-1.4\n% 試用".encode()


def sample_pdf(name, pages=1, landscape=(), title="試用のファイル（架空）"):
    """開ける見本の PDF（A4。架空の書類であることと、ファイル名を書く）。pages ページで、landscape のページ（1 から）は横向き。
    2ページ以上なら、どのページかが一目でわかるよう、ページ番号を大きく書く。"""
    import io

    from reportlab.lib.pagesizes import A4, landscape as to_landscape
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas
    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(title)
    for n in range(1, pages + 1):
        size = to_landscape(A4) if n in landscape else A4
        c.setPageSize(size)
        top = size[1] - 82
        c.setFont("HeiseiKakuGo-W5", 20)
        c.drawString(72, top, title)
        c.setFont("HeiseiKakuGo-W5", 12)
        c.drawString(72, top - 30, f"ファイル名：{name}")
        c.drawString(72, top - 50, "VA Filing を試すための見本です。中身はありません。")
        if pages > 1:
            c.drawString(72, top - 70, f"全 {pages} ページ中 {n} ページ目" + ("（横向き）" if n in landscape else ""))
            c.setFont("HeiseiKakuGo-W5", 96)
            c.drawCentredString(size[0] / 2, size[1] / 2 - 40, f"{n} / {pages}")
        c.showPage()
    c.save()
    return buf.getvalue()


def refresh_pdfs(base):
    """前の版が作った、開けない見本の PDF を作り直す（名前と日時はそのまま）。"""
    count = 0
    for p in base.rglob("*.pdf"):
        if p.read_bytes().startswith(FAKE_HEAD):
            st = p.stat()
            p.write_bytes(sample_pdf(p.name))
            os.utime(p, (st.st_atime, st.st_mtime))
            count += 1
    print(f"見本の PDF を {count} 件作り直しました：{base}")


FILES = ["202511051030.pdf", "202511051032.pdf", "202511061415.pdf", "受信FAX_相手方代理人.pdf",
         "FAXDATA_0001.pdf", "Thumbs.db"]

# 複数ページの見本（ファイル名, ページ数, 横向きのページ, 書類の名前）。名前の日時は、ほかの見本より後
MULTI_PAGE = [("202511081000.pdf", 3, (), "準備書面（架空）"),
              ("202511081030.pdf", 8, (3,), "書証の写し（架空）"),
              ("受信FAX_裁判所_期日請書.pdf", 2, (), "期日請書（架空）")]


# 一覧のスクロールを試すための、1ページの見本（2025-11-10 から 15 日、1日2つ。書類の名前は架空）
_KINDS = ["訴状（写し）", "答弁書", "準備書面", "証拠説明書", "書証", "期日呼出状", "送付書", "受領書", "陳述書", "和解案",
          "上申書", "照会回答", "委任状", "請求書", "通知書"]
MANY_FILES = [(f"202511{10 + d:02d}{h:02d}{mi:02d}.pdf", _KINDS[(d * 2 + k) % len(_KINDS)] + "（架空）")
              for d in range(15) for k, (h, mi) in enumerate(((9, 30), (15, 10)))]


def add_multi_page(base):
    """スキャン\\ に、複数ページの見本と、一覧がスクロールするだけの数の見本の PDF を足す（同じ名前があれば足さない）。
    → (足した複数ページの見本の数, 足した1ページの見本の数)。"""
    scan = base / "スキャン"
    scan.mkdir(parents=True, exist_ok=True)

    def put(name, data, at):
        p = scan / name
        if p.exists():
            return 0
        p.write_bytes(data)
        os.utime(p, (at, at))
        return 1

    t0 = time.mktime((2025, 11, 8, 10, 0, 0, 0, 0, -1))
    multi = sum(put(name, sample_pdf(name, pages, landscape, title), t0 + i * 60)
                for i, (name, pages, landscape, title) in enumerate(MULTI_PAGE))
    t1 = time.mktime((2025, 11, 10, 9, 0, 0, 0, 0, -1))
    many = sum(put(name, sample_pdf(name, title=title), t1 + i * 3600) for i, (name, title) in enumerate(MANY_FILES))
    return multi, many


# --add10 の見本：(読み込んだ日時, ファイル名)。ファイル名の頭12桁が、日時の欄に入る
ADD10 = [("2026-11-10 09:30", "202611100915.pdf"), ("2026-11-10 09:30", "202611101030.pdf"),
         ("2026-11-10 14:00", "202611101345.pdf"), ("2026-11-11 10:00", "202611110940.pdf"),
         ("2026-11-11 10:00", "202611110955.pdf"), ("2026-11-11 16:30", "202611111610.pdf"),
         ("2026-11-13 09:10", "202611130900.pdf"), ("2026-11-13 09:10", "202611130905.pdf"),
         ("2026-11-13 13:20", "202611131300.pdf"), ("2026-11-13 13:20", "202611131315.pdf")]


# --unread の見本（読込フォルダの中の場所）。2つは、サブフォルダ（複合機2）に置く
UNREAD = ["202611131400.pdf", "202611131405.pdf", "202611131410.pdf", "202611131420.pdf", "202611131430.pdf",
          "202611131440.pdf", "202611131450.pdf", "202611131455.pdf", "複合機2\\202611131500.pdf",
          "複合機2\\202611131510.pdf"]


def unread(base):
    from trial_numbers import make_unread
    make_unread(base / "スキャン", [(rel, None) for rel in UNREAD],
                lambda name, spec: sample_pdf(name, title="読み込む前の見本（架空）"))


def add10(base):
    from trial_numbers import add_read_files
    add_read_files(base / "共有" / m.MASTER_FILE_NAME, m, base / "スキャン", [(w, n, None) for w, n in ADD10],
                   lambda name, spec: sample_pdf(name, title="番号の見本（架空）"))


def main():
    args = sys.argv[1:]
    if args and args[0] == "--add10":
        add10(Path(args[1]) if len(args) > 1 else ROOT / "試験用")
        return
    if args and args[0] == "--unread":
        unread(Path(args[1]) if len(args) > 1 else ROOT / "試験用")
        return
    if args and args[0] == "--pdfs":
        refresh_pdfs(Path(args[1]) if len(args) > 1 else ROOT / "試験用")
        return
    if args and args[0] == "--add":
        base = Path(args[1]) if len(args) > 1 else ROOT / "試験用"
        multi, many = add_multi_page(base)
        print(f"複数ページの見本の PDF を {multi} 個、1ページの見本の PDF を {many} 個足しました：{base / 'スキャン'}")
        return
    base = Path(args[0]) if args else ROOT / "試験用"
    case_master = base / "共有" / cm.MASTER_FILE_NAME
    if not case_master.exists():
        print(f"先に scripts\\make_trial.py で VA Case の試用の場所を作ってください：{base}")
        return
    master = base / "共有" / m.MASTER_FILE_NAME
    if master.exists():
        print(f"すでにあります。作り直すときは、消してから実行してください：{master}")
        return
    scan = base / "スキャン"
    for d in (scan, scan / "複合機2", base / "未確認" / "佐藤", base / "未確認" / "田中", base / "写し" / "佐藤",
              base / "職務上請求", base / "文献"):
        d.mkdir(parents=True, exist_ok=True)
    t0 = time.mktime((2025, 11, 7, 9, 0, 0, 0, 0, -1))
    for i, name in enumerate(FILES):
        p = scan / name
        p.write_bytes(sample_pdf(name) if name.endswith(".pdf") else b"\0" * 64)
        os.utime(p, (t0 + i * 60, t0 + i * 60))
    (scan / "複合機2" / "202511071200.pdf").write_bytes(sample_pdf("202511071200.pdf"))
    add_multi_page(base)
    tables = m.empty_tables()
    tables[m.READ_FOLDERS].rows = [[str(scan), m.YES]]
    tables[m.COPY_TARGETS].rows = [["佐", m.KIND_SHORTCUT, str(base / "未確認" / "佐藤")],
                                   ["佐", m.KIND_COPY, str(base / "写し" / "佐藤")],
                                   ["田", m.KIND_SHORTCUT, str(base / "未確認" / "田中")],
                                   ["佐・田", m.KIND_SHORTCUT, str(base / "未確認" / "佐藤")],
                                   ["佐・田", m.KIND_SHORTCUT, str(base / "未確認" / "田中")]]
    tables[m.SPECIAL].rows = [["職務上請求", str(base / "職務上請求")], ["弁護士会照会", ""]]
    tables[m.DEST].rows = [["民法（文献）", str(base / "文献"), ""]]
    tables[m.SETTINGS].rows = [[m.SET_SKIP_PREFIX, "FAXDATA"], [m.SET_PICK_START, str(base / "事件")]]
    create_master(master, m.TOOL, tables, Identity("試用", "試用"))
    print(f"VA Filing の試用の共有データを作りました：{master}")
    cfg_path = settings.common_config.config_path(settings.TOOL_KEY)
    ans = input(f"この PC の VA Filing の設定（{cfg_path}）を、試用の場所に向けますか？ [y/N] ").strip().lower()
    if ans == "y":
        if cfg_path.exists():
            keep = cfg_path.with_name(cfg_path.stem + "_試用前.json")
            cfg_path.replace(keep)
            print(f"前の設定は {keep} に残しました。")
        settings.save(settings.FilingConfig(master_path=str(master), backup_folder=str(base / "バックアップ"),
                                            case_master_path=str(case_master)))
        print("設定を書きました。python main_filing.py で起動してください。")


if __name__ == "__main__":
    main()
