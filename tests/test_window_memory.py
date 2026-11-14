"""ウィンドウの位置と大きさ・最大化を覚えて戻す（window_memory.py。2026-11-14 班長指摘「最大化したことを覚えていない」）の試験。

Tk は作らない（試験の全体で Tk を増やさない）。Tk のウィンドウの代わりに、geometry・state・winfo_* を持つ偽物を使う。
実際の画面での動きは、一時の設定で4つのツールを起動して確かめる（仕様.md に記録）。
"""
import json
from types import SimpleNamespace

import pytest

from va_case.call import settings as call_settings
from va_case.case import settings as case_settings
from va_case.common import config
from va_case.common.ui.window_memory import WindowMemory, fills_screen
from va_case.filing import settings as filing_settings
from va_case.receipt import settings as receipt_settings

DEFAULT = "1280x800"


class FakeRoot:
    """Tk の root の代わり。最大化すると、大きさは画面いっぱいになり、解くと最大化する前の大きさに戻る（Windows と同じ）。"""

    def __init__(self, screen=(2560, 1440)):
        self.screen = screen
        self._state = "normal"
        self._geo = "1x1+0+0"       # 画面を組む前
        self._restore_geo = None
        self.handler = None

    # Tk と同じ名前の操作
    def geometry(self, value=None):
        if value is None:
            return self._geo
        self._geo = value if "+" in value else value + "+10+10"

    def state(self, value=None):
        if value is None:
            return self._state
        if value == "zoomed" and self._state != "zoomed":
            self._restore_geo = self._geo
            self._geo = f"{self.screen[0]}x{self.screen[1] - 70}+-8+-8"
        elif value == "normal" and self._state == "zoomed":
            self._geo = self._restore_geo
        self._state = value
        self.configure()

    def winfo_width(self):
        return int(self._geo.split("x")[0])

    def winfo_height(self):
        return int(self._geo.split("x")[1].split("+")[0])

    def winfo_screenwidth(self):
        return self.screen[0]

    def winfo_screenheight(self):
        return self.screen[1]

    def bind(self, sequence, func, add=None):
        assert sequence == "<Configure>"
        self.handler = func

    # 試験の操作
    def configure(self):
        if self.handler:
            self.handler(SimpleNamespace(widget=self))

    def resize(self, geo):
        self._geo = geo
        self.configure()


def open_close(cfg, actions, screen=(2560, 1440)):
    """開いて、actions(root) をして、閉じる（cfg に書く）。開いた直後の root を返す。"""
    root = FakeRoot(screen)
    mem = WindowMemory(root, cfg, DEFAULT)
    mem.restore()
    opened = (root.state(), root.geometry())
    actions(root)
    mem.remember()
    return opened


def test_zoomed_is_remembered_and_restored():
    cfg = config.ToolConfig()
    open_close(cfg, lambda r: (r.resize("1000x700+50+60"), r.state("zoomed")))
    assert cfg.window_zoomed is True
    assert cfg.window_geometry == "1000x700+50+60"      # 最大化した大きさを、ふつうの大きさとして覚えない
    root = FakeRoot()
    WindowMemory(root, cfg, DEFAULT).restore()
    assert root.state() == "zoomed"
    root.state("normal")                                 # 最大化を解くと、最大化する前の大きさに戻る
    assert root.geometry() == "1000x700+50+60"


def test_normal_is_remembered_and_restored():
    cfg = config.ToolConfig()
    open_close(cfg, lambda r: (r.state("zoomed"), r.state("normal"), r.resize("900x650+30+40")))
    assert cfg.window_zoomed is False and cfg.window_geometry == "900x650+30+40"
    assert open_close(cfg, lambda r: None) == ("normal", "900x650+30+40")


def test_zoomed_before_minimized_is_remembered():
    cfg = config.ToolConfig()
    open_close(cfg, lambda r: (r.resize("1000x700+50+60"), r.state("zoomed"), r.state("iconic")))
    assert cfg.window_zoomed is True and cfg.window_geometry == "1000x700+50+60"


def test_tiny_sizes_are_not_remembered():
    cfg = config.ToolConfig()
    open_close(cfg, lambda r: (r.resize("1x1+0+0"), r.resize("1000x700+5+5"), r.resize("1x1+0+0")))
    assert cfg.window_geometry == "1000x700+5+5"


@pytest.mark.parametrize("saved", ["1x1+0+0", "1x1", "100x800+0+0", "abc", "", 12, None])
def test_bad_saved_geometry_opens_at_default_size(saved):
    cfg = config.ToolConfig(window_geometry=saved, window_zoomed=False)
    assert cfg.window_geometry == ""
    assert open_close(cfg, lambda r: None) == ("normal", DEFAULT + "+10+10")


def test_ver100_settings_that_saved_the_zoomed_size_open_zoomed():
    # Ver100 は window_zoomed を書かず、最大化したまま閉じると、画面いっぱいの大きさを覚えていた
    cfg = config.ToolConfig(window_geometry="2560x1326+-8+114")
    assert cfg.window_zoomed is None
    opened = open_close(cfg, lambda r: r.state("normal"))
    assert opened[0] == "zoomed"
    assert cfg.window_geometry == DEFAULT + "+10+10" and cfg.window_zoomed is False   # 解くと既定の大きさ
    # Ver100 の設定でも、画面より小さい大きさは、そのまま
    cfg = config.ToolConfig(window_geometry="1983x1141+338+59")
    assert open_close(cfg, lambda r: None) == ("normal", "1983x1141+338+59")
    # 最大化を覚えた後の設定は、画面いっぱいでも、そのまま（利用者がそう広げたもの）
    cfg = config.ToolConfig(window_geometry="2560x1326+0+0", window_zoomed=False)
    assert open_close(cfg, lambda r: None) == ("normal", "2560x1326+0+0")


def test_fills_screen():
    root = FakeRoot((2560, 1440))
    assert fills_screen(root, "2560x1326+-8+114")
    assert not fills_screen(root, "2559x1326+0+0") and not fills_screen(root, "2560x1000+0+0")
    assert not fills_screen(root, "")


@pytest.mark.parametrize("module", [case_settings, filing_settings, receipt_settings, call_settings])
def test_all_four_tools_keep_zoomed_in_their_settings(module, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))       # 班長の設定に書かない
    cfg = module.load()
    assert cfg.window_zoomed is None and cfg.window_geometry == ""
    cfg.window_geometry, cfg.window_zoomed = "1000x700+50+60", True
    module.save(cfg)
    path = config.config_path(module.TOOL_KEY)
    assert path.parent.parent == tmp_path
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["window_zoomed"] is True and data["window_geometry"] == "1000x700+50+60"
    again = module.load()
    assert again.window_zoomed is True and again.window_geometry == "1000x700+50+60"
