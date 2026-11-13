"""リボンのボタンのアイコン（2026-11-13 班長指示「リボンのコマンドボタンをVA Documentのように変更」）。

アイコンは Microsoft の Fluent UI System Icons（MIT License。icons\\LICENSE）で、VA Document と同じ2色の形。
scripts\\make_icons.py で SVG から大きめの PNG にしたもの（icons\\<名前>.png・<名前>_disabled.png・<名前>_large.png）を、
起動したときに Pillow で画面の拡大率に合った大きさに縮める（拡大してもぼやけない。PyMuPDF〔AGPL〕を配るものに
入れないため。VA Document は起動のたびに SVG を画像にしている）。
"""
from pathlib import Path

ICON_DIR = Path(__file__).resolve().parent / "icons"
ICON_SIZE = 16          # 小さいアイコンの大きさ（拡大率 100% のとき。画素）
LARGE_ICON = 32         # 大きいボタンのアイコンの大きさ

# ボタンの字（改行と「…」を除く）→ アイコンの名前（icons\<名前>.png）
BUTTON_ICONS = {
    # ［編集を終える］は、斜線の入った鉛筆（2026-11-13 班長指示「「編集を終える」ボタンのアイコンは別のものにする」
    # 「斜線の入った鉛筆が良い」。それまでは［編集を始める］と同じ鉛筆。いったん保存のアイコンにしたが、直した値は行を
    # 移るたびに書き込んでいて、編集を終える働きの中心は書き込みではないので、改めた）
    "編集を始める": "edit", "編集を終える": "edit_off", "最新を読み込む": "arrow_sync",
    "新しい事件": "document_add", "新しいメモ": "document_add", "ファイルを読み込む": "folder_open", "消す": "delete",
    "コピー": "copy",
    "事件メモ": "document_text", "期日請書": "calendar_checkmark", "送付書": "send",
    "結果を表示": "search", "すべてを表示": "filter_dismiss",
}


def icon_name(text):
    return BUTTON_ICONS.get(str(text).replace("\n", "").replace("…", ""))


class IconSet:
    """アイコンの画像を作って覚えておく（Tk の画像は、参照がなくなると消えるため）。"""

    def __init__(self, root):
        self.root = root
        self.scale = max(1.0, root.winfo_fpixels("1i") / 96)        # 画面の拡大率
        self._cache = {}

    def image(self, name, disabled=False, large=False):
        """アイコンの画像（なければ None）。large なら大きいボタンの大きさで、色付きのアイコン（_large）があればそれを
        使う（押せないときは、灰色の線画を大きくする）。"""
        size = round((LARGE_ICON if large else ICON_SIZE) * self.scale)
        key = (name, disabled, large, size)
        if key not in self._cache:
            candidates = [f"{name}_large.png"] if large and not disabled else []
            candidates.append(f"{name}_disabled.png" if disabled else f"{name}.png")
            path = next((ICON_DIR / c for c in candidates if (ICON_DIR / c).exists()), None)
            if path is None:
                return None
            from PIL import Image, ImageTk
            with Image.open(path) as img:
                small = img.convert("RGBA").resize((size, size), Image.LANCZOS)
            self._cache[key] = ImageTk.PhotoImage(small, master=self.root)
        return self._cache[key]
