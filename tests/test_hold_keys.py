"""上下の矢印キーを押し続けたときの加速（2026-11-10 班長指示）の試験。画面は使わず、一覧の代わりを使う。"""
from types import SimpleNamespace

from va_case.common.ui.shared_app import SharedApp


class FakeTree:
    def __init__(self, n):
        self.items = tuple(f"r{i}" for i in range(n))
        self.sel = ("r0",)

    def get_children(self, item=""):
        return self.items

    def selection(self):
        return self.sel

    def focus(self):
        return self.sel[0] if self.sel else ""

    def parent(self, iid):
        return ""


def make_app(n=1000):
    app = SharedApp.__new__(SharedApp)
    app.tree = FakeTree(n)
    app._hold = None
    app._released_at = None
    app.last_key_move = 0.0
    app._list_row = lambda iid: iid

    def move(m):
        items = app.tree.items
        cur = items.index(app.tree.sel[0])
        app.tree.sel = (items[min(max(cur + m, 0), len(items) - 1)],)
        return "break"
    app._move_selection = move
    return app


def press(app, t, step=1):
    app._arrow(SimpleNamespace(time=t), step)


def release(app, t):
    app._arrow_released(SimpleNamespace(time=t))


def index(app):
    return app.tree.items.index(app.tree.sel[0])


def test_hold_rows():
    app = make_app()
    assert app._hold_rows(0.9) == 0          # 1秒までは加速しない
    assert app._hold_rows(2.0) == 30         # 1〜2.5秒は1秒に30行
    assert app._hold_rows(3.5) == 45 + 60    # 2.5秒からは1秒に60行


def test_one_row_per_press_before_acceleration():
    app = make_app()
    t = 1000
    press(app, t)
    for _ in range(10):                       # 0.5秒の間、33ミリ秒ごとに繰り返す
        t += 33
        release(app, t)                       # 繰り返しの合間の「離す」（同じ時刻）
        press(app, t)
    assert index(app) == 11


def test_holding_accelerates_by_time_even_if_repeats_are_merged():
    app = make_app()
    t = 1000
    press(app, t)
    t += 500
    press(app, t)                             # 繰り返しの開始
    for _ in range(10):                       # 描き直しが遅く、繰り返しが0.3秒ごとにまとまって届く
        t += 300
        press(app, t)
    # 3.5秒押し続けた：加速の前の1行ずつの分＋加速の分（1秒の時点から 30×1.5＋60×1.0＝105行。最初の1回は除く）
    assert index(app) >= 100


def test_pressing_again_starts_over():
    app = make_app()
    t = 1000
    press(app, t)
    for _ in range(80):                       # 2.6秒押し続けて加速した
        t += 33
        press(app, t)
    fast = index(app)
    release(app, t + 10)
    t += 200                                  # 離して、押し直した
    press(app, t)
    t += 33
    release(app, t)
    press(app, t)
    assert index(app) == fast + 2             # 押し直したら、1行ずつに戻る


def test_reverse_direction_starts_over():
    app = make_app()
    t = 1000
    press(app, t)
    for _ in range(80):
        t += 33
        press(app, t)
    fast = index(app)
    t += 33
    press(app, t, step=-1)                    # 逆向きのキーは押し直し
    assert index(app) == fast - 1


def test_stops_at_the_end():
    app = make_app(n=50)
    t = 1000
    press(app, t)
    for _ in range(150):
        t += 33
        press(app, t)
    assert index(app) == 49
