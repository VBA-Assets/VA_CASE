"""検索（VAサーチ Ver211 と同じ。2026-11-09 班長決定）。

表のすべての列から語を探し、当てはまる行を返す。語は空白（全角も可）で区切り、既定は OR（どれかを含む）、
AND（すべてを含む）も選べる。比べる前に、語と表の値の両方を次のように揃える（VAサーチの NormalizeString）：

1. 異字体を同一視する（IVS を除き、置換表で代表の字にする。高⇔髙・斉⇔齋⇔斎など）
2. 全角/半角・大文字/小文字を同一視する
3. ひらがな/カタカナを同一視する
4. 濁点・半濁点の有無を同一視する（が⇔か、ぱ⇔は）
5. 小書き文字を同一視する（っ⇔つ、ゃ⇔や）
6. 長音（ー）とハイフンを除く（サーバ⇔サーバー）

語が日付として読めるときは、表の値のうち日付として読めるものと、日の一致でも当てはまりとする
（2025/1/1 で R7.1.1 も、R7.1.1 で 2025-01-01 も見つかる）。
"""
import re
import unicodedata

from .dates import parse_date, to_seireki, to_wareki

# 異字体の置換表（VAサーチの NormalizeString の (B) と同じ。キー → 代表の字）
VARIANTS = {
    "亞": "亜", "醫": "医", "榮": "栄", "惠": "恵",
    "會": "会", "學": "学", "國": "国", "劍": "剣", "廣": "広", "舊": "旧", "\U00020BB7": "吉",
    "齋": "斉", "齊": "斉", "斎": "斉", "櫻": "桜", "澤": "沢", "嶋": "島", "嶌": "島", "壽": "寿", "眞": "真",
    "穰": "穣",
    "髙": "高", "瀧": "滝", "鐵": "鉄", "德": "徳", "冨": "富", "豐": "豊",
    "濱": "浜", "濵": "浜", "邉": "辺", "邊": "辺", "檜": "桧", "渕": "淵",
    "萬": "万", "峯": "峰", "楳": "梅",
    "藪": "薮",
    "龍": "竜", "禮": "礼",
    "﨑": "崎", "區": "区",
}
_VARIANT_TABLE = str.maketrans(VARIANTS)

# 異体字セレクタ（IVS：U+E0100〜E01EF、SVS：U+FE00〜FE0F）
_SELECTORS = re.compile("[\U000E0100-\U000E01EF︀-️]")

_SMALL = str.maketrans("ァィゥェォッャュョヮヵヶ", "アイウエオツヤユヨワカケ")
_CHOON = str.maketrans("", "", "ー-‐‑‒–—―－ｰ−")
_DAKUTEN = {"゙", "゚"}


def _to_katakana(s):
    return "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in s)


def normalize(text):
    """比べるための形にする（VAサーチの NormalizeString と同じ同一視）。"""
    s = _SELECTORS.sub("", text)
    s = s.translate(_VARIANT_TABLE)
    s = unicodedata.normalize("NFKC", s)   # 全角/半角（英数字・カナ）と、互換用の漢字（塚・隆など）を揃える
    s = _to_katakana(s)
    s = "".join(c for c in unicodedata.normalize("NFD", s) if c not in _DAKUTEN)
    s = unicodedata.normalize("NFC", s)
    s = s.translate(_SMALL)
    s = s.translate(_CHOON)
    return s.casefold()


class _Term:
    def __init__(self, word):
        self.word = word
        self.norm = normalize(word)
        self.date = parse_date(word)
        self.date_texts = (to_seireki(self.date), to_wareki(self.date)) if self.date else ()


class Query:
    """検索の条件。text：語（空白で区切る）、mode："OR" か "AND"。"""

    def __init__(self, text, mode="OR"):
        words = (text or "").replace("　", " ").split()
        self.terms = [_Term(w) for w in words]
        self.mode = "AND" if mode == "AND" else "OR"

    @property
    def empty(self):
        return not self.terms

    def _term_hits(self, term, row, norm_row):
        for raw, norm in zip(row, norm_row):
            if not raw:
                continue
            if term.norm and term.norm in norm:
                return True
            if term.date:
                # 1行に1つずつ日付を入れた欄（何人かの生年月日。2026-11-12）も、行ごとに見る
                if any(parse_date(s) == term.date for s in raw.split("\n")):
                    return True
                if any(t in raw for t in term.date_texts):
                    return True
        return False

    def matches(self, row, norm_row=None):
        """row：1行の値（文字列の並び）。norm_row：normalize 済みの値（速さのため、あれば使う）。"""
        if self.empty:
            return True
        norm_row = norm_row if norm_row is not None else [normalize(v) if v else "" for v in row]
        hits = (self._term_hits(t, row, norm_row) for t in self.terms)
        return all(hits) if self.mode == "AND" else any(hits)


def search(rows, text, mode="OR"):
    """当てはまる行の番号（0 から）の一覧を返す。"""
    q = Query(text, mode)
    return [i for i, row in enumerate(rows) if q.matches(row)]
