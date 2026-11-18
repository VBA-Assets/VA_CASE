"""MIT License で配るための確かめ（標準 01「オープンソースとライセンス」、02「テスト」。2026-11-19 に雛形から写した）。

配るプログラム（src）が読み込む外の部品は、RUNTIME_PACKAGES に書いたものだけとし、どれも MIT License と両立する
ライセンスで、THIRD_PARTY_NOTICES.txt に載っていること。AGPL・GPL の部品（PyMuPDF など）を読み込まないこと。
部品を足したら、RUNTIME_PACKAGES に書き足し、python scripts\\make_notices.py で THIRD_PARTY_NOTICES.txt を作り直す。
"""
import ast
import importlib.metadata as metadata
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "va_case"

# 配るプログラムが読み込む外の部品：{import の名前: (配布の名前, …)}。標準ライブラリ（tkinter を含む）は書かない。
# winrt は、Windows の文字認識を呼ぶ部品（requirements.txt の winrt-*。Windows でだけ入れる）
RUNTIME_PACKAGES = {
    "reportlab": ("reportlab",),
    "pypdfium2": ("pypdfium2",),
    "PIL": ("pillow",),
    "winrt": ("winrt-runtime", "winrt-Windows.Foundation", "winrt-Windows.Foundation.Collections",
              "winrt-Windows.Globalization", "winrt-Windows.Graphics.Imaging", "winrt-Windows.Media.Ocr",
              "winrt-Windows.Storage.Streams"),
}
# THIRD_PARTY_NOTICES.txt での名前（配布の名前と違うもの）
NOTICE_NAMES = {"winrt": "PyWinRT"}

# MIT License と両立するライセンス（配布の情報の License・Classifier に、どれかの語が入っていること）
COMPATIBLE = ("MIT", "BSD", "Apache", "PSF", "Python Software Foundation", "ISC", "HPND", "MIT-CMU", "Zlib")
FORBIDDEN_MODULES = ("fitz", "pymupdf")


def _imported_top_modules():
    found = set()
    for path in (ROOT / "src" / PACKAGE).rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                found.add(node.module.split(".")[0])
    return found - set(sys.stdlib_module_names) - {PACKAGE}


def test_only_listed_packages_are_imported():
    imported = _imported_top_modules()
    assert not imported & set(FORBIDDEN_MODULES)
    assert imported <= set(RUNTIME_PACKAGES), f"RUNTIME_PACKAGES にない部品：{sorted(imported - set(RUNTIME_PACKAGES))}"


@pytest.mark.parametrize("module", sorted(RUNTIME_PACKAGES))
def test_runtime_packages_are_mit_compatible_and_noticed(module):
    notices = (ROOT / "THIRD_PARTY_NOTICES.txt").read_text(encoding="utf-8")
    for dist in RUNTIME_PACKAGES[module]:
        try:
            meta = metadata.metadata(dist)
        except metadata.PackageNotFoundError:
            if module == "winrt" and sys.platform != "win32":
                pytest.skip("winrt は Windows でだけ入れる")
            raise
        text = " ".join([meta.get("License", "") or "", meta.get("License-Expression", "") or ""]
                        + [c for c in meta.get_all("Classifier") or [] if c.startswith("License")])
        assert any(word in text for word in COMPATIBLE), f"{dist} のライセンスを確かめる：{text}"
        assert "GPL" not in text.replace("LGPL", ""), f"{dist} は GPL"
    name = NOTICE_NAMES.get(module, RUNTIME_PACKAGES[module][0])
    assert name.lower() in notices.lower(), f"{name} が THIRD_PARTY_NOTICES.txt にない"


def test_license_file():
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert text.startswith("MIT License")
    assert "VBAアセット" in text and "All Rights Reserved" not in text
