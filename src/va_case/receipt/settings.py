"""VA Receipt の、この PC の設定（共通の ToolConfig に、VA Receipt だけの場所を足す）。"""
from dataclasses import dataclass

from ..common import config as common_config
from ..common.config import ToolConfig

TOOL_KEY = "receipt"


@dataclass
class ReceiptConfig(ToolConfig):
    data_root: str = ""          # フォルダの値が相対パスのときの基点（PC ごとに同期フォルダの場所が違う場合）
    window_geometry: str = ""
    # プレビュー（左側。2026-11-12 班長決定）を出すか・その幅（96 dpi のときの画素。0 は既定）。閉じるときに覚える
    preview_visible: bool = True
    preview_width: int = 0

    def __post_init__(self):
        super().__post_init__()
        for name in ("data_root", "window_geometry"):
            if not isinstance(getattr(self, name), str):
                setattr(self, name, "")
        if not isinstance(self.preview_visible, bool):
            self.preview_visible = True
        self.preview_width = common_config.valid_preview_width(self.preview_width)


def load():
    return common_config.load(TOOL_KEY, ReceiptConfig)


def save(cfg):
    common_config.save(TOOL_KEY, cfg)
