"""ウィンドウの位置と大きさ・最大化を覚えて、次に開いたときに戻す（4つのツールで共通。SharedApp が使う）。

2026-11-14 班長指摘「VA CASEシリーズも最大化したことを覚えていないようである」。それまでは、閉じるときに
root.geometry() だけを覚えていたので、最大化したまま閉じると、最大化した大きさを「ふつうの大きさ」として覚え、
次は最大化していない、画面いっぱいの窓で開いていた。同じ日に VA Request で同じ直しをした（その app.py の
_restore_window・_on_root_configure・_save_window）のにならう。

- 最大化していないときの位置と大きさは、<Configure> で、最大化も最小化もしていない（state が normal）で、
  幅・高さが MIN_WINDOW_SIZE より大きいときだけ覚える（画面を組む前の 1x1 を覚えない）。
- 閉じるときは、その大きさと、最大化していたか（window_zoomed）を書く。最小化したまま閉じたときは、
  最小化する前に最大化していたかを書く。
- 開くときは、ふつうの大きさを当ててから最大化する（最大化を解くと、その大きさに戻る）。
- Ver100 の設定（window_zoomed がない）で、覚えた大きさが画面いっぱいなら、最大化したまま閉じたものとみて、
  最大化して開き、ふつうの大きさは既定にする。
"""
import re
import tkinter as tk

from ..config import MIN_WINDOW_SIZE, valid_window_geometry


def fills_screen(root, geometry):
    """覚えた大きさが、画面いっぱい（最大化したときの大きさ）か。幅が画面の幅以上で、高さが画面の高さの8割以上。"""
    m = re.match(r"(\d+)x(\d+)", geometry or "")
    if not m:
        return False
    w, h = int(m.group(1)), int(m.group(2))
    return w >= root.winfo_screenwidth() and h >= root.winfo_screenheight() * 0.8


class WindowMemory:
    def __init__(self, root, cfg, default):
        """cfg：ToolConfig（window_geometry・window_zoomed）。default：既定の大きさ（「幅x高さ」。画面の拡大率に合わせたもの）。"""
        self.root = root
        self.cfg = cfg
        self.default = default
        self.normal_geometry = ""   # 最大化していないときの位置と大きさ（最後に見たもの）
        self.zoomed = False         # 最小化していないときに、最後に見た状態が最大化だったか

    def restore(self):
        """覚えた位置と大きさを当て、最大化して閉じていたなら最大化する。<Configure> を見始める。"""
        root, cfg = self.root, self.cfg
        geo = valid_window_geometry(cfg.window_geometry)
        zoomed = cfg.window_zoomed is True
        if geo and cfg.window_zoomed is None and fills_screen(root, geo):
            geo, zoomed = "", True      # Ver100 で、最大化したまま閉じたもの
        try:
            root.geometry(geo or self.default)
        except tk.TclError:
            geo = ""
            root.geometry(self.default)
        self.normal_geometry = geo or self.default
        if zoomed:
            try:
                root.state("zoomed")
                self.zoomed = True
            except tk.TclError:         # 最大化のない環境
                pass
        root.bind("<Configure>", self._on_configure, add="+")

    def _on_configure(self, event):
        root = self.root
        if event.widget is not root:
            return
        try:
            state = root.state()
        except tk.TclError:
            return
        if state == "zoomed":
            self.zoomed = True
        elif state == "normal":
            self.zoomed = False
            if root.winfo_width() > MIN_WINDOW_SIZE and root.winfo_height() > MIN_WINDOW_SIZE:
                self.normal_geometry = root.geometry()

    def remember(self):
        """閉じるときに、いまの状態を cfg に書く（ファイルへの保存は呼ぶ側）。"""
        root, cfg = self.root, self.cfg
        state = root.state()
        if state == "zoomed":
            zoomed = True
        elif state == "normal":
            zoomed = False
        else:                           # 最小化したまま閉じたとき（iconic）は、最小化する前の状態
            zoomed = self.zoomed
        geo = valid_window_geometry(root.geometry()) if state == "normal" else ""
        geo = geo or valid_window_geometry(self.normal_geometry)
        if geo:
            cfg.window_geometry = geo
        cfg.window_zoomed = zoomed
