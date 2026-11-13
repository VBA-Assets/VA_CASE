"""画像の文字の読み取り（OCR）。Windows に初めから入っている文字認識（Windows.Media.Ocr）を使う。

2026-11-13 班長決定「OCR も入れる」：VA Filing・VA Receipt のプレビューで文字を選んでコピーするとき、PDF に文字が
入っていなければ（スキャン・受信した FAX・写真）、ページの画像を読み取って、字の位置を知る（common/page_text.py）。
- 読み取りは、この PC の中だけで行う（Windows の機能。外部と通信しない）。Python からは、Microsoft の winrt の部品
  （winrt-Windows.Media.Ocr など。MIT License）で呼ぶ。
- 日本語の文字認識は、日本語版の Windows なら初めから入っている。入っていない PC・Windows でない PC（Mac）では
  OcrUnavailable を出す（プレビューは、そのわけを知らせる）。
- 画面の部品（Tk）には触らない。プレビューの裏のスレッドから呼ぶ。
"""
import io

MAX_SIDE = 4000          # 読み取りに渡す画像の長い辺の上限（Windows の上限は 10000 画素。大きいほど時間がかかる）
MIN_HEIGHT = 120         # これより低い画像は、拡大してから読む（小さい字は読み違いが増えるため）

UNAVAILABLE = ("この PC では、画像の文字を読み取れません（Windows の日本語の文字認識が入っていないか、Windows で"
               "ありません）。")


class OcrUnavailable(Exception):
    """読み取れない PC（利用者に示す文を持つ）。"""


_engine = None


def _get_engine():
    """日本語の文字認識（なければ、利用者の言語のもの）。作ったものを覚えて使い回す（呼ぶのは裏の1本のスレッドだけ）。"""
    global _engine
    if _engine is not None:
        return _engine
    try:
        from winrt.windows.globalization import Language
        from winrt.windows.media.ocr import OcrEngine
    except ImportError:
        raise OcrUnavailable(UNAVAILABLE)
    try:
        tags = [lang.language_tag for lang in OcrEngine.available_recognizer_languages]
        tag = next((t for t in tags if t.lower().startswith("ja")), None)
        engine = (OcrEngine.try_create_from_language(Language(tag)) if tag
                  else OcrEngine.try_create_from_user_profile_languages())
    except OSError:
        engine = None
    if engine is None:
        raise OcrUnavailable(UNAVAILABLE)
    _engine = engine
    return engine


def fit_for_ocr(image):
    """読み取りに向く大きさにする（大きすぎれば縮め、低すぎれば拡大する）。→ RGB の PIL の画像。"""
    from PIL import Image
    image = image.convert("RGB")
    w, h = image.size
    k = 1.0
    if max(w, h) > MAX_SIDE:
        k = MAX_SIDE / max(w, h)
    elif h < MIN_HEIGHT:
        k = min(MIN_HEIGHT / max(h, 1), MAX_SIDE / max(w, 1), 4.0)
    if k != 1.0:
        image = image.resize((max(1, round(w * k)), max(1, round(h * k))), Image.LANCZOS)
    return image


async def _recognize(image):
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream
    buf = io.BytesIO()
    image.save(buf, "BMP")
    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(buf.getvalue())
    await writer.store_async()
    writer.detach_stream()
    stream.seek(0)
    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    result = await _get_engine().recognize_async(bitmap)
    w, h = image.size
    lines = []
    for line in result.lines:
        words = []
        for word in line.words:
            r = word.bounding_rect
            words.append((word.text, r.x / w, r.y / h, (r.x + r.width) / w, (r.y + r.height) / h))
        lines.append(words)
    return lines


def recognize_lines(image):
    """PIL の画像の文字を読み取る。→ 行ごとの、語の (文字, 左, 上, 右, 下) のリスト（位置は画像の幅・高さに対する
    割合）。Windows の文字認識は、日本語の文書では1字ずつ（数字も1字ずつ）の語として返す。
    読み取れない PC では OcrUnavailable。"""
    import asyncio
    _get_engine()                      # 先に確かめる（読み取れない PC では、すぐ知らせる）
    try:
        return asyncio.run(_recognize(fit_for_ocr(image)))
    except OcrUnavailable:
        raise
    except OSError:
        raise OcrUnavailable("画像の文字を読み取れませんでした（Windows の文字認識が使えませんでした）。")
