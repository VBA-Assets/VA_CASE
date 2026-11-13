"""この PC だけの設定（ツールごとに1ファイル）。

書くのは、共有データ・バックアップの場所や列の幅などの、場所と見た目の設定だけで、事件の情報は書かない
（2026-11-11 まであった「同期を待つ秒数」は、なくした。前の設定ファイルに残っていても、読むときに無視する）
（利用者の PC に共有データの写しを残さない。2026-11-09 班長決定）。
置き場所は %APPDATA%\\VA Case\\<ツール>.json（Windows 以外はホームの .va_case）。VA Document と同じ作り。

各 PC がそれぞれの設定を持つので、共有フォルダの場所が PC ごとに違って（Windows のドライブ名と Mac の /Volumes/ など）も、
それぞれの PC で設定すればよい（VAブリッジは設定をブックに持ったため、パスを相互に変換していた）。
"""
import json
import os
import re
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path


COLUMN_WIDTH_RANGE = (20, 2000)  # 覚えた列の幅として受け付ける範囲（96 dpi のときの画素）
PREVIEW_WIDTH_RANGE = (150, 3000)   # 覚えたプレビューの幅として受け付ける範囲（96 dpi のときの画素。VA Filing・VA Receipt）


def config_dir():
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / "VA Case"
    return Path.home() / ".va_case"


def config_path(tool_key):
    """tool_key：case・filing・receipt・call。"""
    return config_dir() / f"{tool_key}.json"


@dataclass
class ToolConfig:
    master_path: str = ""          # 共有データのファイル
    backup_folder: str = ""        # 日次バックアップの置き場所（"" はバックアップしない。現行と同じ）
    # 一覧の列の幅（列の名前 → 96 dpi のときの画素）。閉じるときに覚え、次に起動したときに戻す（2026-11-09 班長指示）
    column_widths: dict = field(default_factory=dict)
    # 事務所の設定の画面の大きさ（「幅x高さ」の画素）と、表の列の幅（「タブの名前/列の名前」→ 96 dpi のときの画素）。
    # 閉じるときに覚え、次に開いたときに戻す（2026-11-12 班長指示「フォームのサイズや列幅の設定を保存する」）
    office_size: str = ""
    office_column_widths: dict = field(default_factory=dict)

    def __post_init__(self):
        for name in ("master_path", "backup_folder", "office_size"):
            if not isinstance(getattr(self, name), str):
                setattr(self, name, "")
        self.column_widths = _valid_widths(self.column_widths)
        self.office_column_widths = _valid_widths(self.office_column_widths)
        if not re.fullmatch(r"\d{2,5}x\d{2,5}", self.office_size):
            self.office_size = ""


def valid_preview_width(value):
    """覚えたプレビューの幅。範囲の外や数でなければ 0（既定の幅）。"""
    lo, hi = PREVIEW_WIDTH_RANGE
    return value if isinstance(value, int) and not isinstance(value, bool) and lo <= value <= hi else 0


def _valid_widths(widths):
    widths = widths if isinstance(widths, dict) else {}
    lo, hi = COLUMN_WIDTH_RANGE
    return {k: v for k, v in widths.items()
            if isinstance(k, str) and isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi}


def load(tool_key, cls=ToolConfig, path=None):
    """設定を読む。ないか読めなければ既定。cls には ToolConfig を受け継いだ、ツールごとの設定を渡せる。"""
    path = Path(path or config_path(tool_key))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})
    except (OSError, ValueError, TypeError, AttributeError):
        return cls()


def save(tool_key, cfg, path=None):
    path = Path(path or config_path(tool_key))
    path.parent.mkdir(parents=True, exist_ok=True)   # PC の中の設定の置き場所は作ってよい
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(cfg), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
