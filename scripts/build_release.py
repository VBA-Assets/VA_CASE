"""配布用のリリース（release_VerNNN\\VA_Case_VerNNN\\ と、dist\\ の zip）を組み立てる。

VA Document の build_release.py と同じ作り。統合版のインストーラー（VA_Caseシリーズ\\共通\\統合版）は、
release_VerNNN\\VA_Case_VerNNN\\ を直接参照する。

前提（このスクリプトはビルドそのものはしない。先に済ませておく）：
    1. python -m PyInstaller va_case.spec --noconfirm   （dist\\ の4つの exe を最新のコードで作る）
    2. python scripts\\generate_manual.py                （docs\\manual\\VA_Case_操作マニュアル_VerNNN.pdf。
       先にマニュアルのフロントマターの version を上げておく）
    3. python scripts\\make_notices.py                   （部品を足したとき・版を上げたとき）

実行のしかた：
    python scripts\\build_release.py Ver100

できるもの：
    release_Ver100\\VA_Case_Ver100\\  （VA_Case.exe・VA_Filing.exe・VA_Receipt.exe・VA_Call.exe・LICENSE・
                                      THIRD_PARTY_NOTICES.txt・README.md・マニュアル\\・source\\）
    dist\\VA_Case_Series_Ver100.zip   （上のフォルダを zip にしたもの。4つのツールが入る）
    dist\\VA_Case_Ver100.zip・VA_Filing_Ver100.zip・VA_Receipt_Ver100.zip・VA_Call_Ver100.zip
                                     （ツールごとの zip。サイトの「サンプル」の各ツールの記事に載せる。そのツールの
                                      exe と、マニュアル・LICENSE・THIRD_PARTY_NOTICES.txt・README.md・source\\。
                                      source は4つのツールで共通なので、どの zip にも全部入れる。2026-11-14 班長決定
                                      「ツールごとの zip」。それまでは、4つのツールが入った zip を VA_Case_VerNNN.zip と
                                      していた）
release_*\\・dist\\ は、ビルドの生成物として git に入れない。
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXES = ["VA_Case.exe", "VA_Filing.exe", "VA_Receipt.exe", "VA_Call.exe"]

# source\\ に入れないもの（git の管理下でも、公開しない内部の資料。VAプロジェクト\\CLAUDE.md の
# 「GitHub でのソースの公開」と同じ考え方）：作業の指示の CLAUDE.md、検討と決定の記録の 仕様.md
_EXCLUDE = [re.compile(p) for p in (r"^CLAUDE\.md$", r"^仕様\.md$")]


def _source_files() -> list[str]:
    out = subprocess.run(["git", "-c", "core.quotepath=false", "ls-files", "-z"], cwd=ROOT, capture_output=True,
                         check=True).stdout
    files = [f for f in out.decode("utf-8").split("\0") if f]
    return [f for f in files if not any(p.search(f) for p in _EXCLUDE)]


def _clear_readonly(func, path, exc):
    """OneDrive はフォルダに読み取り専用の属性を付け、Windows は読み取り専用のフォルダを消せない。属性を外して、もう一度消す。"""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def build(version: str) -> Path:
    if not re.fullmatch(r"Ver[0-9A-Z]{3}", version):
        raise SystemExit("版は「Ver100」の形で指定してください。")
    exes = [ROOT / "dist" / name for name in EXES]
    manual = ROOT / "docs" / "manual" / f"VA_Case_操作マニュアル_{version}.pdf"
    required = exes + [manual, ROOT / "LICENSE", ROOT / "THIRD_PARTY_NOTICES.txt", ROOT / "README.md"]
    missing = [str(p.relative_to(ROOT)) for p in required if not p.exists()]
    if missing:
        raise SystemExit("足りないファイルがあります：" + "、".join(missing))
    # 版のつじつま（exe の画面に出る版と、指定した版）を確かめる
    sys.path.insert(0, str(ROOT / "src"))
    from va_case import VERSION_LABEL
    if VERSION_LABEL != version:
        raise SystemExit(f"src\\va_case\\__init__.py の版（{VERSION_LABEL}）が {version} と合いません。")
    # exe が、いまのソースより古くないかを確かめる（直したのに作り直し忘れるのを防ぐ）
    newest = max(p.stat().st_mtime for p in (ROOT / "src").rglob("*.py"))
    old = [p.name for p in exes if p.stat().st_mtime < newest]
    if old:
        raise SystemExit("ソースより古い exe があります。先に PyInstaller で作り直してください：" + "、".join(old))

    stage = ROOT / f"release_{version}" / f"VA_Case_{version}"
    if stage.exists():
        shutil.rmtree(stage, onexc=_clear_readonly)
    (stage / "マニュアル").mkdir(parents=True)
    for exe in exes:
        shutil.copy2(exe, stage / exe.name)
    shutil.copy2(manual, stage / "マニュアル" / manual.name)
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.txt", "README.md"):
        shutil.copy2(ROOT / name, stage / name)
    for f in _source_files():
        dest = stage / "source" / f
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / f, dest)

    zip_path = ROOT / "dist" / f"VA_Case_Series_{version}.zip"
    _zip(zip_path, stage, stage.name, lambda rel: True)
    paths = [zip_path]
    # ツールごとの zip：そのツールの exe だけを入れ、ほかの3つの exe は入れない
    for exe in EXES:
        tool = exe[:-4]                                   # VA_Case など
        others = {e for e in EXES if e != exe}
        path = ROOT / "dist" / f"{tool}_{version}.zip"
        _zip(path, stage, f"{tool}_{version}", lambda rel, o=others: str(rel) not in o)
        paths.append(path)
    return paths


def _zip(zip_path: Path, stage: Path, top: str, keep) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(stage.rglob("*")):
            rel = p.relative_to(stage)
            if p.is_file() and keep(rel):
                z.write(p, Path(top) / rel)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("使い方：python scripts\\build_release.py Ver100")
    for path in build(sys.argv[1]):
        print(f"作りました：{path}（{path.stat().st_size:,} バイト）")
