"""VA Caseシリーズ：事件の情報・保管するファイル・領収書等・電話の記録を、共有フォルダだけで複数人で管理する。

仕様は、作業フォルダの `仕様.md`。

パッケージの構成：
- `va_case.common`：4つの exe で使う共通部品（共有・ロック・設定・バックアップ）
- `va_case.case`・`va_case.filing`・`va_case.receipt`・`va_case.call`：各ツール（VA Case・VA Filing・VA Receipt・VA Call）。それぞれの段で作る
"""

# 版番号（2026-11-14 班長決定「Ver100」。VA Document と同じ付け方で、4つのツールで同じ版にする。画面には「Ver100」と出す）
# Ver101（2026-11-14）：最大化したまま閉じたら、次も最大化して開く（班長指摘「VA CASEシリーズも最大化したことを覚えていない」）
__version__ = "1.0.1"
VERSION_LABEL = "Ver" + __version__.replace(".", "")
SERIES_NAME = "VA Caseシリーズ"
