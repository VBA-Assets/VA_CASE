"""VA Caseシリーズが使っている部品のライセンスの表示（THIRD_PARTY_NOTICES.txt）を作る（VA Document の make_notices.py と
同じ作り。2026-11-14 班長の問い「ヘルプの「◯◯について」の情報にMITを含めるべきではないのか？」）。

4つの exe（VA_Case.exe・VA_Filing.exe・VA_Receipt.exe・VA_Call.exe）に入る部品（Python・Tcl/Tk・ReportLab・
charset-normalizer・Pillow・pypdfium2 と PDFium・PyWinRT・PyInstaller のブートローダー）と、ボタンのアイコン（Fluent UI
System Icons）のライセンスの全文を、いま入っている部品のファイルから集める。部品を足したとき・版を上げたときは、作り直して
コミットする（exe に入る部品は、PyInstaller の build\\va_case\\PKG-00.toc・PYZ-00.toc で確かめられる）。

PyWinRT（winrt-runtime など）は、配布の部品の中にライセンスの文がない（METADATA に「MIT」とだけある）。著作権の行は、
PyWinRT のリポジトリの LICENSE（https://github.com/pywinrt/pywinrt/blob/main/LICENSE。2026-11-14 に読んで確かめた）から
写し、本文は MIT License の決まった文（この作業フォルダの LICENSE と同じ文）を使う。

実行のしかた：
    python scripts\\make_notices.py
"""

from __future__ import annotations

import importlib.metadata as metadata
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "THIRD_PARTY_NOTICES.txt"
PY_HOME = Path(sys.base_prefix)

# MIT License の許諾の文（著作権の行の後）。この作業フォルダの LICENSE から取る
MIT_BODY = (ROOT / "LICENSE").read_text(encoding="utf-8").split("\n", 3)[3].lstrip("\n")
PYWINRT_COPYRIGHT = ("Copyright (c) Microsoft Corporation. All rights reserved.\n"
                     "Copyright (c) 2021-2026 David Lechner <david@pybricks.com>")
PYWINRT_DISTS = ["winrt-runtime", "winrt-Windows.Foundation", "winrt-Windows.Foundation.Collections",
                 "winrt-Windows.Globalization", "winrt-Windows.Graphics.Imaging", "winrt-Windows.Media.Ocr",
                 "winrt-Windows.Storage.Streams"]


def _dist_license_files(dist: str, *, startswith: str = "") -> list[Path]:
    """配布 dist の dist-info の licenses の下のファイル（startswith で絞る）。"""
    out = []
    for f in metadata.distribution(dist).files or []:
        s = str(f).replace("\\", "/")
        if ".dist-info/licenses/" in s and s.split(".dist-info/licenses/", 1)[1].startswith(startswith):
            out.append(Path(metadata.distribution(dist).locate_file(f)))
    return sorted(out)


# (表示する名前, 配布の名前〔版を読む。None は版を書かない〕, 用途, ライセンス, 全文〔ファイルの並び か 文字列〕)
COMPONENTS = [
    ("Python", None, "プログラムの言語（exe に入る）", "PSF License Version 2（Windows 版に入っている部品のライセンスを含む）",
     [PY_HOME / "LICENSE.txt"]),
    ("Tcl/Tk", None, "画面", "Tcl/Tk License（BSD 形式）", [PY_HOME / "tcl" / "tk8.6" / "license.terms"]),
    ("ReportLab", "reportlab", "PDF の作成（VA Case の事件メモ・期日請書・送付書）", "BSD License",
     lambda: _dist_license_files("reportlab")),
    ("charset-normalizer", "charset-normalizer", "ReportLab が使う部品", "MIT License",
     lambda: _dist_license_files("charset-normalizer")),
    ("Pillow", "pillow", "画像（プレビュー・アイコン）", "MIT-CMU License（Pillow に入っている画像の部品のライセンスを含む）",
     lambda: _dist_license_files("pillow")),
    ("pypdfium2（PDFium を含む）", "pypdfium2", "PDF のプレビューと字の位置（VA Filing・VA Receipt）",
     "Apache-2.0・BSD-3-Clause（PDFium とその部品のライセンスを含む）",
     lambda: _dist_license_files("pypdfium2")),
    ("PyWinRT（winrt-runtime ほか）", "winrt-runtime", "Windows の文字認識（Windows.Media.Ocr）を呼ぶ（プレビューの字の読み取り）",
     "MIT License", None),
    ("PyInstaller", "pyinstaller", "実行ファイルの作成（ブートローダーが exe に入る）",
     "GNU General Public License 第2版以降（ブートローダーの例外条項付き）", lambda: _dist_license_files("pyinstaller")),
    ("Fluent UI System Icons", None, "ボタンのアイコン", "MIT License",
     [ROOT / "src" / "va_case" / "common" / "ui" / "icons" / "LICENSE"]),
]


def build() -> Path:
    parts = [
        "VA Caseシリーズが使っている部品のライセンスの表示",
        "",
        "VA Caseシリーズ（VA Case・VA Filing・VA Receipt・VA Call）そのものは、MIT License で公開しています（LICENSE）。",
        "4つの実行ファイル（VA_Case.exe・VA_Filing.exe・VA_Receipt.exe・VA_Call.exe）には、次の部品が入っています。",
        "",
    ]
    for name, dist, use, lic, files in COMPONENTS:
        if name == "Python":
            version = sys.version.split()[0]
        elif name == "Tcl/Tk":
            import tkinter
            version = str(tkinter.Tcl().eval("info patchlevel"))
        else:
            version = metadata.version(dist) if dist else ""
        parts += ["=" * 78, f"{name} {version}".rstrip(), f"用途：{use}", f"ライセンス：{lic}"]
        if name.startswith("PyWinRT"):
            parts.append("配布の名前と版：" + "・".join(f"{d} {metadata.version(d)}" for d in PYWINRT_DISTS))
        parts.append("=" * 78)
        if name.startswith("PyWinRT"):
            parts += ["--- LICENSE ---", "MIT License", "", PYWINRT_COPYRIGHT, "", MIT_BODY.rstrip(), ""]
        else:
            paths = files() if callable(files) else files
            if not paths:
                raise SystemExit(f"{name} のライセンスの文が見つかりません。")
            for path in paths:
                parts += [f"--- {path.name} ---", path.read_text(encoding="utf-8-sig", errors="replace").rstrip(), ""]
        parts.append("")
    OUTPUT.write_text("\n".join(parts) + "\n", encoding="utf-8", newline="\n")
    return OUTPUT


if __name__ == "__main__":
    print(f"作りました：{build()}")
