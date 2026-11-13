"""VA Receipt の試用の場所を、VA Case の試用の場所（scripts\\make_trial.py で作る 試験用\\）に足す。

使い方：python scripts\\make_trial_receipt.py [試用の場所（既定は 作業フォルダ\\試験用）]
作るもの：共有\\VA_Receipt.json、領収書スキャン\\（読込フォルダ。架空の領収書の PDF）、経理\\<種別>\\（保管フォルダ）。
すでに VA_Receipt.json があれば作り直さない。
最後に、この PC の VA Receipt の設定（%APPDATA%\\VA Case\\receipt.json）を試用の場所に向けるかを尋ねる。

python scripts\\make_trial_receipt.py --add [試用の場所]
  領収書スキャン\\ に、いろいろな形の架空の領収書のファイルを足す（2026-11-12 班長指示「VA RECEIPT用のサンプルファイルを
  作成」）。共有データは変えない。同じ名前のファイルがあれば、足さない。VA Receipt の「ファイルを読み込む」で読み込む。

python scripts\\make_trial_receipt.py --add10 [試用の場所]
  番号の付け方を確かめる見本を10件足す（2026-11-13 班長指示「新しい番号の付け方を確認するため、各ツール用のサンプルデータを
  10件ずつ作成」）。領収書スキャン\\ に領収書を作り、11月10日・11日・13日に読み込んだものとして保管の表に足す（番号は、
  読み込んだ日の年月日＋その日の連番。scripts\\trial_numbers.py）。

python scripts\\make_trial_receipt.py --unread [試用の場所]
  読み込む前の見本の領収書を10個、領収書スキャン\\ に作る（2026-11-13 班長指示「VA Filing と VA Receipt　読み込み前の
  状態のサンプルを作成」）。共有データは変えない。アプリの「ファイルを読み込む」で読み込むと、その日の年月日＋連番の
  番号が付く。
"""
import io
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from make_trial_filing import sample_pdf  # noqa: E402

from va_case.common.identity import Identity  # noqa: E402
from va_case.common.master import create_master  # noqa: E402
from va_case.receipt import model as m  # noqa: E402
from va_case.receipt import settings  # noqa: E402

# 架空の領収書（日付_相手先_金額 の名前のものと、そうでないもの）
FILES = ["20251101_甲山文具店_1100.pdf", "20251101_甲山文具店_1100 (2).pdf", "20251102_乙川タクシー_2,340円.pdf",
         "20251105_丙野書店.pdf", "IMG_0001.jpg"]

# --add で足す、いろいろな形の架空の領収書。(ファイル名, 書類の名前, 相手先, 金額, 日付, 試すこと)
MORE = [
    ("20251110_丁田コンビニ_498.pdf", "領収書", "丁田コンビニ", "498", "2025年11月10日", "ふつうの形"),
    ("20251111_戊山駐車場_￥1,200.pdf", "領収書", "戊山駐車場", "1,200", "2025年11月11日", "金額の ￥ とカンマを除く"),
    ("20251112_己野郵便局_１２０円.pdf", "領収書", "己野郵便局", "120", "2025年11月12日", "全角の数字と「円」"),
    ("20251113_庚川商店_▲300.pdf", "領収書", "庚川商店", "▲300", "2025年11月13日", "返品（負の金額）"),
    ("20251114_辛田タクシー_1500.pdf", "領収書", "辛田タクシー", "1,500", "2025年11月14日", "同じ日・相手先・金額（1枚目）"),
    ("20251114_辛田タクシー_1500 (2).pdf", "領収書", "辛田タクシー", "1,500", "2025年11月14日",
     "同じ日・相手先・金額（2枚目。枝番が付く）"),
    ("20251115_壬野弁当.pdf", "領収書", "壬野弁当", "650", "2025年11月15日", "ファイル名に金額がない"),
    ("20251131_癸山印刷_800.pdf", "領収書", "癸山印刷", "800", "2025年11月31日（ない日付）", "ファイル名の日付がない日付"),
    ("領収書_甲乙書店_2200.pdf", "領収書", "甲乙書店", "2,200", "2025年11月16日", "ファイル名が日付で始まらない"),
    ("20251117_乙丙法律書院_33,000.pdf", "請求書", "乙丙法律書院", "33,000", "2025年11月17日", "請求書（種別を選び直す）"),
    ("20251118_丙丁リース_5,500.pdf", "納品書", "丙丁リース", "5,500", "2025年11月18日", "納品書（種別を選び直す）"),
    ("20251119_丁戊銀行_330.pdf", "振込通知書", "丁戊銀行", "330", "2025年11月19日", "振込手数料"),
    ("IMG_0002.jpg", "領収書", "戊己食堂", "1,080", "2025年11月20日", "スマートフォンで撮った写真（本当の JPEG）"),
]


def receipt_pdf(title, partner, amount, day, note):
    """開ける見本の領収書の PDF（A5 横。架空であることを書く）。"""
    from reportlab.lib.pagesizes import A5, landscape
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas
    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
    font = "HeiseiKakuGo-W5"
    w, h = landscape(A5)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(w, h))
    c.setTitle(f"試用の{title}（架空）")
    c.setFont(font, 26)
    c.drawCentredString(w / 2, h - 70, title)
    c.setFont(font, 14)
    c.drawString(60, h - 120, "VA法律事務所　様")
    c.setFont(font, 22)
    c.drawCentredString(w / 2, h - 175, f"金額　￥{amount.lstrip('▲')}－" if not amount.startswith("▲")
                        else f"返金　￥{amount.lstrip('▲')}－")
    c.line(w / 2 - 150, h - 182, w / 2 + 150, h - 182)
    c.setFont(font, 12)
    c.drawString(60, h - 225, f"日付：{day}")
    c.drawString(60, h - 248, f"発行：{partner}（架空）")
    c.setFont(font, 9)
    c.drawString(60, 40, f"VA Receipt を試すための架空の書類です。試すこと：{note}")
    c.showPage()
    c.save()
    return buf.getvalue()


def receipt_jpeg(title, partner, amount, day):
    """スマートフォンで撮ったような、見本の領収書の写真（JPEG）。"""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (900, 600), (236, 232, 222))
    d = ImageDraw.Draw(img)
    d.rectangle((90, 50, 810, 550), fill=(252, 252, 250), outline=(180, 180, 180))
    font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "msgothic.ttc"
    try:
        big, mid, small = (ImageFont.truetype(str(font_path), s) for s in (46, 30, 20))
    except OSError:
        big = mid = small = ImageFont.load_default()
    d.text((380, 80), title, fill=(30, 30, 30), font=big)
    d.text((130, 180), "VA法律事務所　様", fill=(30, 30, 30), font=mid)
    d.text((260, 270), f"￥{amount}－", fill=(30, 30, 30), font=big)
    d.text((130, 380), f"日付：{day}", fill=(30, 30, 30), font=small)
    d.text((130, 420), f"発行：{partner}（架空）", fill=(30, 30, 30), font=small)
    d.text((130, 500), "VA Receipt を試すための架空の写真です。", fill=(90, 90, 90), font=small)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def first_file(name):
    """FILES のファイルの中身。.jpg は本物の JPEG にする（2026-11-13 まではすべて PDF の中身で書いていて、IMG_0001.jpg は
    名前だけ .jpg の PDF だったため、プレビューに出なかった。班長指摘「VARECEIPTのサンプルのIMG_0001.jpgが表示されない。」）。"""
    if name.lower().endswith(".jpg"):
        return receipt_jpeg("領収書", "甲丁喫茶", "750", "2025年11月7日")
    return sample_pdf(name)


def add_more(base):
    scan = base / "領収書スキャン"
    if not scan.is_dir():
        print(f"領収書スキャンのフォルダがありません。先に、--add を付けずに実行してください：{scan}")
        return
    t0 = time.mktime((2025, 11, 21, 9, 0, 0, 0, 0, -1))
    added = 0
    for i, (name, title, partner, amount, day, note) in enumerate(MORE):
        p = scan / name
        if p.exists():
            continue
        data = receipt_jpeg(title, partner, amount, day) if name.endswith(".jpg") else \
            receipt_pdf(title, partner, amount, day, note)
        p.write_bytes(data)
        os.utime(p, (t0 + i * 60, t0 + i * 60))   # 日付で始まらない名前は、この日付（11月21日）になる
        added += 1
    print(f"{scan} に、架空の領収書のファイルを {added} 個足しました（すでにあった {len(MORE) - added} 個は足していません）。")
    print("VA Receipt で「編集を始める」→「ファイルを読み込む」を押すと、一覧に入ります。")


# --add10 の見本：(読み込んだ日時, ファイル名, (相手先, 金額, 日付))
ADD10 = [("2026-11-10 10:00", "20261106_子田文具店_880.pdf", ("子田文具店", "880", "2026年11月6日")),
         ("2026-11-10 10:00", "20261107_丑山タクシー_1,960.pdf", ("丑山タクシー", "1,960", "2026年11月7日")),
         ("2026-11-10 17:00", "20261110_寅川郵便局_140.pdf", ("寅川郵便局", "140", "2026年11月10日")),
         ("2026-11-11 09:30", "20261109_卯野書店_3,300.pdf", ("卯野書店", "3,300", "2026年11月9日")),
         ("2026-11-11 09:30", "20261110_辰巳駐車場_600.pdf", ("辰巳駐車場", "600", "2026年11月10日")),
         ("2026-11-11 18:00", "20261111_巳山弁当_750.pdf", ("巳山弁当", "750", "2026年11月11日")),
         ("2026-11-13 09:00", "20261112_午田コンビニ_432.pdf", ("午田コンビニ", "432", "2026年11月12日")),
         ("2026-11-13 09:00", "20261112_午田コンビニ_432 (2).pdf", ("午田コンビニ", "432", "2026年11月12日")),
         ("2026-11-13 12:00", "20261113_未野印刷_5,500.pdf", ("未野印刷", "5,500", "2026年11月13日")),
         ("2026-11-13 12:00", "20261113_申川交通_2,100.pdf", ("申川交通", "2,100", "2026年11月13日"))]


# --unread の見本：(ファイル名, (相手先, 金額, 日付))
UNREAD = [("20261113_酉田文具店_550.pdf", ("酉田文具店", "550", "2026年11月13日")),
          ("20261113_戌山タクシー_2,480.pdf", ("戌山タクシー", "2,480", "2026年11月13日")),
          ("20261113_亥野郵便局_1,180円.pdf", ("亥野郵便局", "1,180", "2026年11月13日")),
          ("20261112_子丑書店_4,400.pdf", ("子丑書店", "4,400", "2026年11月12日")),
          ("20261112_寅卯駐車場_800.pdf", ("寅卯駐車場", "800", "2026年11月12日")),
          ("20261112_寅卯駐車場_800 (2).pdf", ("寅卯駐車場", "800", "2026年11月12日")),
          ("20261111_辰巳弁当.pdf", ("辰巳弁当", "1,200", "2026年11月11日")),
          ("20261110_午未銀行_440.pdf", ("午未銀行", "440", "2026年11月10日")),
          ("20261109_申酉コンビニ_￥365.pdf", ("申酉コンビニ", "365", "2026年11月9日")),
          ("領収書_戌亥印刷_7,700.pdf", ("戌亥印刷", "7,700", "2026年11月8日"))]


def unread(base):
    from trial_numbers import make_unread
    make_unread(base / "領収書スキャン", [(n, spec) for n, spec in UNREAD],
                lambda name, spec: receipt_pdf("領収書", spec[0], spec[1], spec[2], "読み込む前の見本（架空）"))


def add10(base):
    from trial_numbers import add_read_files
    add_read_files(base / "共有" / m.MASTER_FILE_NAME, m, base / "領収書スキャン", ADD10,
                   lambda name, spec: receipt_pdf("領収書", spec[0], spec[1], spec[2], "番号の見本（架空）"))


def main():
    args = [a for a in sys.argv[1:] if a not in ("--add", "--add10", "--unread")]
    base = Path(args[0]) if args else ROOT / "試験用"
    if "--add10" in sys.argv[1:]:
        add10(base)
        return
    if "--unread" in sys.argv[1:]:
        unread(base)
        return
    if "--add" in sys.argv[1:]:
        add_more(base)
        return
    if not (base / "共有").is_dir():
        print(f"先に scripts\\make_trial.py で VA Case の試用の場所を作ってください：{base}")
        return
    master = base / "共有" / m.MASTER_FILE_NAME
    if master.exists():
        print(f"すでにあります。作り直すときは、消してから実行してください：{master}")
        print("領収書のファイルだけを足すときは、--add を付けて実行してください。")
        return
    scan = base / "領収書スキャン"
    scan.mkdir(parents=True, exist_ok=True)
    t0 = time.mktime((2025, 11, 7, 9, 0, 0, 0, 0, -1))
    for i, name in enumerate(FILES):
        p = scan / name
        p.write_bytes(first_file(name))
        os.utime(p, (t0 + i * 60, t0 + i * 60))
    tables = m.empty_tables()
    rows = []
    for kind in m.DEFAULT_TYPES:
        folder = base / "経理" / kind
        folder.mkdir(parents=True, exist_ok=True)
        rows.append([kind, str(folder)])
    tables[m.TYPES].rows = rows
    tables[m.READ_FOLDERS].rows = [[str(scan), ""]]
    create_master(master, m.TOOL, tables, Identity("試用", "試用"))
    print(f"VA Receipt の試用の共有データを作りました：{master}")
    add_more(base)
    cfg_path = settings.common_config.config_path(settings.TOOL_KEY)
    ans = input(f"この PC の VA Receipt の設定（{cfg_path}）を、試用の場所に向けますか？ [y/N] ").strip().lower()
    if ans == "y":
        if cfg_path.exists():
            keep = cfg_path.with_name(cfg_path.stem + "_試用前.json")
            cfg_path.replace(keep)
            print(f"前の設定は {keep} に残しました。")
        settings.save(settings.ReceiptConfig(master_path=str(master), backup_folder=str(base / "バックアップ")))
        print("設定を書きました。python main_receipt.py で起動してください。")


if __name__ == "__main__":
    main()
