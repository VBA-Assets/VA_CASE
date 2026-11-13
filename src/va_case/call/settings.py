"""VA Call の、この PC の設定（共通の ToolConfig に、VA Call だけのものを足す）。"""
from dataclasses import dataclass

from ..common import config as common_config
from ..common.config import ToolConfig

TOOL_KEY = "call"


@dataclass
class CallConfig(ToolConfig):
    window_geometry: str = ""

    def __post_init__(self):
        super().__post_init__()
        if not isinstance(self.window_geometry, str):
            self.window_geometry = ""


def load():
    return common_config.load(TOOL_KEY, CallConfig)


def save(cfg):
    common_config.save(TOOL_KEY, cfg)
