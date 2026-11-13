"""VA Case の、この PC の設定（共通の ToolConfig に、VA Case だけの場所を足す）。"""
from dataclasses import dataclass

from ..common import config as common_config
from ..common.config import ToolConfig

TOOL_KEY = "case"


@dataclass
class CaseConfig(ToolConfig):
    data_root: str = ""       # データフォルダの欄が相対パスのときの基点（PC ごとに場所が違う場合）
    outbox: str = ""          # 移送待ちの場所（日常の共有フォルダの中。終了事件の ZIP を置く。仕様.md の6）
    zip_compress: bool = False   # ZIP を圧縮するか（既定は無圧縮。2026-11-07 班長決定）
    window_geometry: str = ""

    def __post_init__(self):
        super().__post_init__()
        for name in ("data_root", "outbox", "window_geometry"):
            if not isinstance(getattr(self, name), str):
                setattr(self, name, "")
        if not isinstance(self.zip_compress, bool):
            self.zip_compress = False


def load():
    return common_config.load(TOOL_KEY, CaseConfig)


def save(cfg):
    common_config.save(TOOL_KEY, cfg)
