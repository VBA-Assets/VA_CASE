"""新しい行の番号（VA Filing・VA Receipt・VA Call で同じ）。

年月日6桁（yymmdd）とその日の連番3桁の9桁（例：261113001 は、2026年11月13日の1件目）。2026-11-13 班長決定
「9桁（年月日＋連番）」。VA Case の事件番号（年2桁・依頼人3桁・事件2桁の7桁）と同じく、年が頭に来て連番が続く形に
そろえた。桁数が違うので、番号を見ただけで事件番号（7桁）かどうかが分かる。

経緯（2026-11-13）：現行の VAファイル保管は読み込んだときの日時（yymmddhhnnss の12桁）、VA領収書等ファイル保管と
電話メモは、いまの最大に1を足す番号（1, 2, 3…）で、Python 版もそれを引き継いでいた（班長の問い「VA FILINGと
VA RECEIPTで「番号」の作りが異なっているのはなぜなのか？」）。いったん VA Receipt を VA Filing の12桁にそろえ、続けて
班長の案「３桁の依頼人の部分を月日に、残りの2桁を連番に」から、この形にした。

- 年月日は、番号を付けるとき（ファイルを読み込んだとき・メモを作ったとき）のパソコンの日付。
- 連番は、その日の9桁の番号のうち最大のものに1を足す。最後に付けた番号は記録しない（その日の最後の行を消すと、
  次の行が同じ番号を使い回すが、困る場面がほとんどないため。2026-11-13 班長「これが問題になるとは、思えないのだが」）。
- いまの9桁の番号のうち最大のものより小さくはしない（番号の順＝付けた順。VA Receipt の枝番はこの順で付ける）。
  パソコンの時計が戻ったときや、1日に999件を超えたとき（翌日の形にはみ出す）も、重ならず、順も崩れない。
- 取り込んだ今までの番号（1, 2, 3… と、VAファイル保管の12桁）は、そのまま残す。9桁でない番号は、最大を決めるときに
  見ない（12桁の番号は9桁より大きいので、見ると12桁の続きになってしまう）。
"""
from datetime import datetime

WIDTH = 9


def new_numbers(existing, count, now=None):
    """新しい番号を count 個（文字列）。existing：いまある番号（重ならないようにする）。"""
    used = {str(x) for x in existing}
    first = int((now or datetime.now()).strftime("%y%m%d")) * 1000 + 1
    nine = [int(x) for x in used if x.isascii() and x.isdigit() and len(x) == WIDTH]
    n = max([first] + [x + 1 for x in nine])
    out = []
    while len(out) < count:
        s = f"{n:0{WIDTH}d}"
        if s not in used:
            used.add(s)
            out.append(s)
        n += 1
    return out
