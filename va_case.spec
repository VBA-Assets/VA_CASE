# -*- mode: python ; coding: utf-8 -*-
# VA Caseシリーズの4つの実行ファイル（dist\VA_Case.exe・VA_Filing.exe・VA_Receipt.exe・VA_Call.exe）を作る
# （VA Document の va_document.spec・VA FAX の motfax.spec と同じ作り。1つのファイルの exe）。
# 作り方：python -m PyInstaller va_case.spec --noconfirm
#
# 4つの exe は、それぞれ別に配れる（どれか1つだけを入れた PC でも動く）よう、どの exe にも共通部品をすべて入れる。
#
# 入れるもの：
# ・ボタンのアイコン（Fluent UI System Icons の PNG と LICENSE）。icons.py は va_case\common\ui\icons から読む
# ・ウィンドウ（タイトルバー・タスクバー）のアイコン（assets の .ico）。exe そのもののアイコンは EXE(icon=...) で埋め込むが、
#   Tk のウィンドウには実行時にファイルとして読ませるため、展開先（sys._MEIPASS）の assets に入れる（shared_app.icon_path）
# ・pypdfium2 の pdfium.dll（VA Filing・VA Receipt のプレビュー。VA FAX と同じ）
# ・winrt（Windows の文字認識 Windows.Media.Ocr を呼ぶ部品。プレビューの字の読み取り。ocr.py が関数の中で読み込むので、
#   読み落とされないよう、入れてある winrt の部品をすべて挙げる）
# 入れないもの：試験の部品、ほかの GUI、PyMuPDF（AGPL。試験でだけ使う）

from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules

TOOLS = [
    # (起動のスクリプト, exe の名前, アイコン)
    ('main_case.py', 'VA_Case', 'assets/VA_Case.ico'),
    ('main_filing.py', 'VA_Filing', 'assets/VA_Filing.ico'),
    ('main_receipt.py', 'VA_Receipt', 'assets/VA_Receipt.ico'),
    ('main_call.py', 'VA_Call', 'assets/VA_Call.ico'),
]

datas = [('src/va_case/common/ui/icons', 'va_case/common/ui/icons')]
datas += [(icon, 'assets') for _, _, icon in TOOLS]
binaries = collect_dynamic_libs('pypdfium2_raw')
hiddenimports = collect_submodules('winrt')
excludes = ['pytest', 'fitz', 'pymupdf', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'matplotlib', 'numpy', 'pandas']

for script, name, icon in TOOLS:
    a = Analysis(
        [script],
        pathex=['src'],
        binaries=binaries,
        datas=datas,
        hiddenimports=hiddenimports,
        hookspath=[],
        hooksconfig={},
        runtime_hooks=[],
        excludes=excludes,
        noarchive=False,
        optimize=0,
    )
    pyz = PYZ(a.pure)
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name=name,
        icon=icon,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
