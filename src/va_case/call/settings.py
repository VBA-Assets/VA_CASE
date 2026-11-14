"""VA Call の、この PC の設定（共通の ToolConfig のまま。VA Call だけのものは、いまはない）。"""
from dataclasses import dataclass

from ..common import config as common_config
from ..common.config import ToolConfig

TOOL_KEY = "call"


@dataclass
class CallConfig(ToolConfig):
    # ウィンドウの位置と大きさ（window_geometry）は、2026-11-14 に最大化（window_zoomed）とともに ToolConfig へ移した
    pass


def load():
    return common_config.load(TOOL_KEY, CallConfig)


def save(cfg):
    common_config.save(TOOL_KEY, cfg)
