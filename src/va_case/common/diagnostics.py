"""診断情報（［ヘルプ］→［診断情報をコピー］。仕様.md の 6.5。2026-11-11 班長指示で作る）。

不具合を AI や開発者に相談するときに渡す文を作る。中身（氏名・住所などのセルの値、ファイルやフォルダの場所・名前、
利用者・PC の名前、例外のメッセージの本文）は、一切入れない。入れてよいのは、版・環境・設定の数値・件数・列の名前・
値の長さや改行の数・誤りの型と起きた場所（ファイル名・行・関数名）だけとする。
例外のメッセージの本文を入れないのは、ファイルの読み書きの誤り（OSError など）のメッセージに、フォルダの場所
（＝依頼者名が入ることがある）が入るため（VA FAX の F-24 と同じ考え方）。
"""
import json
import os
import platform
import sys
import traceback
from datetime import datetime
from pathlib import Path

from . import config

KEEP_ERRORS = 30     # 覚えておく誤りの数（古いものから消す）
SHOW_ERRORS = 10     # 診断情報に載せる誤りの数（新しいものから）
MAX_FRAMES = 12      # 1つの誤りに載せる場所の数（深い方から）


# ---------------------------------------------------------------- 誤りの記録

def exception_record(exc, stage=""):
    """例外を、型の名前と起きた場所だけの記録にする（メッセージの本文は入れない）。"""
    frames = traceback.extract_tb(exc.__traceback__)[-MAX_FRAMES:]
    record = {
        "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "stage": stage,
        "type": type(exc).__name__,
        "where": [f"{Path(f.filename).name}:{f.lineno}:{f.name}" for f in frames],
    }
    # OSError の番号（何の誤りかの手がかりになり、場所や名前は含まない）
    for name in ("errno", "winerror"):
        value = getattr(exc, name, None)
        if isinstance(value, int):
            record[name] = value
    cause = exc.__cause__ or exc.__context__
    if cause is not None:
        record["cause"] = type(cause).__name__
    return record


def errors_path(tool_key):
    """誤りの記録の置き場所（この PC の設定と同じフォルダ）。"""
    return config.config_dir() / f"{tool_key}_errors.json"


class ErrorLog:
    """起きた誤りを覚える。閉じた後や、落ちた後でも渡せるよう、この PC の設定のフォルダにも書く。

    書けなくても、画面の動きは止めない（診断のための記録なので）。
    """

    def __init__(self, tool_key, path=None):
        self.path = Path(path) if path else errors_path(tool_key)
        try:
            records = json.loads(self.path.read_text(encoding="utf-8"))
            self.records = [r for r in records if isinstance(r, dict)][-KEEP_ERRORS:]
        except (OSError, ValueError, TypeError):
            self.records = []

    def record(self, exc, stage=""):
        try:
            self.records.append(exception_record(exc, stage))
            self.records = self.records[-KEEP_ERRORS:]
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.records, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self.path)
        except Exception:
            pass

    def clear(self):
        self.records = []
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass


def format_record(r):
    head = f"{r.get('at', '')}　{r.get('type', '')}"
    extra = [f"{k}={r[k]}" for k in ("errno", "winerror") if k in r]
    if r.get("cause"):
        extra.append(f"原因 {r['cause']}")
    if extra:
        head += "（" + "・".join(extra) + "）"
    lines = [head]
    if r.get("stage"):
        lines.append(f"    処理：{r['stage']}")
    for w in r.get("where", []):
        lines.append(f"    {w}")
    return lines


# ---------------------------------------------------------------- 中身を含まない要約

def table_lines(tables, schema=None):
    """テーブルごとの行数と、列ごとの「空でない数・最も長い値の字数・改行を含む数」（値そのものは入れない）。"""
    lines = []
    for name, table in tables.items():
        expected = list(schema.get(name, [])) if schema else None
        lines.append(f"[{_safe_name(name, schema)}] {len(table.rows)} 行・{len(table.columns)} 列"
                     + ("" if expected is None else ("（列は既定どおり）" if list(table.columns) == expected
                                                     else "（列が既定と違う）")))
        for i, col in enumerate(table.columns):
            values = [row[i] if i < len(row) else "" for row in table.rows]
            texts = ["" if v is None else str(v) for v in values]
            filled = sum(1 for t in texts if t != "")
            longest = max((len(t) for t in texts), default=0)
            newline = sum(1 for t in texts if "\n" in t)
            label = col if expected is None or col in expected else f"（既定にない列 {i + 1}）"
            lines.append(f"  {label}：空でない {filled}・最長 {longest} 字・改行あり {newline}")
    return lines


def _safe_name(name, schema):
    """テーブルの名前（既定にないものは、名前を出さない）。"""
    return name if schema is None or name in schema else "既定にないテーブル"


def drive_kind(path):
    """場所の種類（ネットワーク・ローカルなど）。場所そのものは返さない。"""
    if not path:
        return "設定なし"
    p = str(path)
    kinds = []
    if p.startswith("\\\\"):
        kinds.append("ネットワークの場所（\\\\ で始まる）")
    elif os.name == "nt":
        try:
            import ctypes
            drive = os.path.splitdrive(p)[0]
            t = ctypes.windll.kernel32.GetDriveTypeW(drive + "\\") if drive else 0
            kinds.append({2: "取り外しできるドライブ", 3: "PC のドライブ", 4: "ネットワークドライブ", 5: "CD・DVD",
                          6: "RAM ディスク"}.get(t, f"ドライブの種類 {t}"))
        except Exception:
            kinds.append("ドライブの種類は不明")
    for env in ("OneDriveCommercial", "OneDriveConsumer", "OneDrive"):
        base = os.environ.get(env)
        if base and os.path.normcase(p).startswith(os.path.normcase(base.rstrip("\\/")) + os.sep):
            kinds.append("OneDrive の同期フォルダの中")
            break
    return "・".join(kinds)


def file_lines(label, path):
    """ファイル・フォルダがあるか・大きさ・最後に変わってからの時間（場所と名前は入れない）。"""
    if not path:
        return [f"{label}：設定なし"]
    p = Path(path)
    try:
        if p.is_file():
            st = p.stat()
            age = datetime.now() - datetime.fromtimestamp(st.st_mtime)
            return [f"{label}：ある（{st.st_size:,} バイト・最後に変わってから {_age(age)}）・{drive_kind(p)}"]
        if p.is_dir():
            return [f"{label}：フォルダがある・{drive_kind(p)}"]
        return [f"{label}：見つからない・{drive_kind(p)}"]
    except OSError as e:
        return [f"{label}：確かめられない（{type(e).__name__}）"]


def _age(delta):
    s = int(delta.total_seconds())
    if s < 120:
        return f"{s} 秒"
    if s < 7200:
        return f"{s // 60} 分"
    if s < 172800:
        return f"{s // 3600} 時間"
    return f"{s // 86400} 日"


def environment_lines(root, title, version):
    frozen = getattr(sys, "frozen", False)
    lines = [f"ツール：{title}  {version}（{'exe' if frozen else 'ソースから起動'}）",
             f"OS：{platform.platform()}",
             f"Python：{platform.python_version()}　Tk：{_tk_patchlevel(root)}"]
    try:
        scale = root.winfo_fpixels("1i") / 96.0
        lines.append(f"画面：{root.winfo_screenwidth()}×{root.winfo_screenheight()}・拡大率 {scale:.0%}・"
                     f"ウィンドウ {root.winfo_width()}×{root.winfo_height()}")
    except Exception:
        pass
    return lines


def _tk_patchlevel(root):
    try:
        return root.tk.call("info", "patchlevel")
    except Exception:
        return "不明"
