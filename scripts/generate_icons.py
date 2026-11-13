"""4つのツールの実行ファイル・ウィンドウ用のアイコン（assets\\VA_Case.ico など）を作るスクリプト（2026-11-13 班長指示
「各ツールのファビコンを作成」）。

VA mints・VA FAX・VA Document と同じ作り（角丸の四角に白い太字。角の丸み・左右の余白は同じ。1行目に「VA」を小さく、
2行目にツールの名前を大きく）。背景の色は、ほかのツール（VA mints の青 #0078D4、VA FAX の緑 #107C41、VA Document の
紫 #5C2D91）と見分けられる色にする。字は Segoe UI Bold。2行目は、左右の余白に収まるいちばん大きい字にする。

アイコンのファイルはリポジトリに入れ、作り方もコードとして残す（VA Document の scripts\\generate_icon.py と同じ方針）。

実行のしかた：
    python scripts\\generate_icons.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

# ツール → (ファイルの名前, 2行目の字, 背景の色)
TOOLS = {
    "case": ("VA_Case.ico", "Case", "#C55A11"),          # 濃いオレンジ（編集モードのオレンジと同じ系統）
    "filing": ("VA_Filing.ico", "Filing", "#00827F"),    # 青緑
    "receipt": ("VA_Receipt.ico", "Rcpt", "#8E562E"),     # 茶。字は Receipt の略（小さいアイコンでも読めるよう。2026-11-13 班長指示「Rcptにする。」）
    "call": ("VA_Call.ico", "Call", "#C42B1C"),          # 赤
}
TEXT_COLOR = "#ffffff"
CANVAS = 256            # 元の画像の一辺（ここから各大きさへ縮める）
CORNER_RADIUS = 28      # VA mints・VA FAX・VA Document と同じ
SIDE_PADDING = 30       # 同じ
TOP_TEXT, TOP_SIZE = "VA", 56          # 1行目（小さく）
MAIN_MAX = 128          # 2行目（この大きさから、余白に収まるまで小さくする）
LINE_GAP = 14
SEGOE = r"C:\Windows\Fonts\segoeuib.ttf"
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def font(path, size):
    if not Path(path).is_file():
        raise FileNotFoundError(f"書体が見つかりません：{path}")
    return ImageFont.truetype(path, size)


def build_image(main_text, background):
    image = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, CANVAS - 1, CANVAS - 1), radius=CORNER_RADIUS, fill=background)
    width = CANVAS - SIDE_PADDING * 2
    top = font(SEGOE, TOP_SIZE)
    size = MAIN_MAX
    while size > 10:
        main = font(SEGOE, size)
        box = main.getbbox(main_text, anchor="ls")
        if box[2] - box[0] <= width:
            break
        size -= 2
    # 高さは、ベースラインからの上端・下端で測る
    top_box = top.getbbox(TOP_TEXT, anchor="ls")
    ascent1, descent1 = -top_box[1], top_box[3]
    ascent2 = -box[1]
    y = (CANVAS - (ascent1 + descent1 + LINE_GAP + ascent2)) / 2
    base1 = y + ascent1
    base2 = base1 + descent1 + LINE_GAP + ascent2
    draw.text(((CANVAS - (top_box[2] - top_box[0])) / 2 - top_box[0], base1), TOP_TEXT, font=top,
              fill=TEXT_COLOR, anchor="ls")
    draw.text(((CANVAS - (box[2] - box[0])) / 2 - box[0], base2), main_text, font=main, fill=TEXT_COLOR, anchor="ls")
    return image


def build():
    ASSETS.mkdir(parents=True, exist_ok=True)
    for name, text, color in TOOLS.values():
        build_image(text, color).save(ASSETS / name, format="ICO", sizes=ICO_SIZES)
        print(f"作りました：{ASSETS / name}")


if __name__ == "__main__":
    build()
