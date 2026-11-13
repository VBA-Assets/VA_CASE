"""欄に入れたフォルダの値を、この PC のパスにする（VA Case のデータフォルダ、VA Filing の保管フォルダなど）。

PC ごとに共有フォルダの場所が違う事務所（同期フォルダが利用者のフォルダの下にできる OneDrive・SharePoint、Mac）でも
使えるよう、共有データには、フォルダを「事務所のフォルダの場所」からの相対パスで書く（2026-11-12 班長決定「対応する」）。
- 読むとき（resolve_folder）：相対パスは、この PC の基点の下とみる。区切りは「\\」でも「/」でもよい（Windows で入れた
  「事件\\101甲野太郎\\scan」を Mac でも読めるように）。
- 書くとき（portable）：「参照…」で選んだフォルダや、貼り付けた絶対パスが基点の下なら、基点からの相対パス（区切りは
  「\\」）にして書く。基点の外のフォルダや、基点を決めていない PC では、今までどおり絶対パスのまま。
"""
import os
import re
import unicodedata
from pathlib import Path, PureWindowsPath

_SEP = re.compile(r"[\\/]+")


def is_absolute(value):
    """Windows の絶対パス（C:\\…・\\\\サーバー\\…）か、この PC の絶対パス（Mac の /Users/… など）か。"""
    return bool(value) and (PureWindowsPath(value).is_absolute() or Path(value).is_absolute())


def resolve_folder(value, data_root=""):
    """フォルダの欄の値を、この PC のパスにする。

    絶対パス（現行の VBA 版と同じ）はそのまま。相対パスは、この PC の設定の「事務所のフォルダの場所」の下と
    みる（PC ごとにドライブ名や同期フォルダの場所が違う場合のため）。基点がなければ None。
    """
    if not value:
        return None
    if is_absolute(value):
        return Path(value)
    if not data_root:
        return None
    return Path(data_root).joinpath(*[p for p in _SEP.split(value) if p])


def _key(part):
    # 比べるための形（Windows は大文字・小文字を問わない。Mac のファイル名の濁点の表し方の違いも問わない）
    return os.path.normcase(unicodedata.normalize("NFC", part))


def _parts_under(path, base):
    """path が base の下なら、base からの残りの部分（同じなら []）。下でなければ None。"""
    p, b = Path(os.path.abspath(path)).parts, Path(os.path.abspath(base)).parts
    if len(p) < len(b) or [_key(x) for x in p[:len(b)]] != [_key(x) for x in b]:
        return None
    return list(p[len(b):])


def place_key(value, data_root=""):
    """フォルダの欄の値が「同じ場所か」を比べるための形（2026-11-13 班長決定「案１、２は、提案どおりで良い」）。

    この PC の場所に直してから、大文字・小文字、最後の「\\」、「/」と「\\」、「.」「..」、相対パスと絶対パスの違いを
    そろえる（「事件\\甲野太郎」「事件\\甲野太郎\\」「C:\\…\\事件\\甲野太郎」は同じ）。それまでは、欄の文字が同じかだけで
    比べていたため、書き方が違うと別のフォルダとみなし、終了処理で、続いているほかの事件のフォルダを ZIP にして
    「消しますか？」と尋ねてしまった。相対パスで基点がないときは、文字の形だけをそろえる。空なら ""。
    """
    value = (value or "").strip()
    if not value:
        return ""
    path = resolve_folder(value, data_root)
    if path is None:
        return "\\".join(_key(p) for p in _SEP.split(value) if p)
    return "\\".join(_key(p) for p in Path(os.path.abspath(path)).parts)


def portable(value, data_root):
    """共有データに書くフォルダの値にする。基点の下の絶対パスなら、基点からの相対パス（区切りは「\\」）にする。"""
    value = (value or "").strip()
    if not value or not data_root or not is_absolute(value):
        return value
    rest = _parts_under(value, data_root)
    return "\\".join(rest) if rest else value


def join_value(base, sub):
    """フォルダの値 base の下の sub（「scan」など）を表す値（区切りは base に合わせる）。"""
    if not sub:
        return base
    sep = "/" if "/" in base and "\\" not in base else "\\"
    return base.rstrip("\\/") + sep + sep.join(p for p in _SEP.split(sub) if p)


def sub_of(value, base, data_root=""):
    """フォルダの値 value が、フォルダの値 base の中なら、base からの相対（区切りは「\\」。同じなら ""）。
    中でないか、この PC のパスにできなければ None。"""
    v, b = resolve_folder(value, data_root), resolve_folder(base, data_root)
    if v is None or b is None:
        return None
    rest = _parts_under(v, b)
    return None if rest is None else "\\".join(rest)
