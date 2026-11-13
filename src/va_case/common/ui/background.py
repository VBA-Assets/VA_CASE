"""時間のかかる処理（共有データの読み書き・ZIP の作成）を裏で行い、画面を止めない。

Tk の部品は、画面のスレッドからだけ触る。裏の処理は、終わったら結果を待ち行列に入れ、画面のスレッドが
root.after で受け取って、on_done・on_error を呼ぶ。
"""
import queue
import threading

POLL_MS = 100


class Background:
    def __init__(self, root, on_change=None, on_exception=None):
        self.root = root
        self._q = queue.Queue()
        self._running = 0
        self.on_change = on_change      # 裏の処理が始まった・終わったときに呼ぶ（動作中のカーソルなど）
        # 誤りが起きたときに呼ぶ（例外, どの処理か）。診断情報に残すため（2026-11-11）
        self.on_exception = on_exception
        self.root.after(POLL_MS, self._poll)

    @property
    def busy(self):
        return self._running > 0

    def run(self, func, on_done=None, on_error=None, *args):
        """func(*args) を裏で行う。progress を受け取る関数には report を使う。"""
        self._running += 1
        if self.on_change:
            self.on_change()

        def _work():
            try:
                result = func(*args)
            except BaseException as e:  # 利用者に示すため、すべて受け取る
                self._note(e, getattr(func, "__qualname__", ""))
                self._q.put((on_error, e, True))
            else:
                self._q.put((on_done, result, True))
        threading.Thread(target=_work, daemon=True).start()

    def report(self, callback, *values):
        """裏の処理から、画面のスレッドで callback(*values) を呼んでもらう（進み具合の表示など）。"""
        self._q.put((lambda v: callback(*v), values, False))

    def _note(self, e, stage):
        if self.on_exception is not None:
            try:
                self.on_exception(e, stage)
            except Exception:
                pass

    def _poll(self):
        try:
            while True:
                callback, value, finished = self._q.get_nowait()
                if finished:
                    self._running -= 1
                    if self.on_change:
                        self.on_change()
                if callback is not None:
                    try:
                        callback(value)
                    except Exception as e:   # 画面の処理の誤りで、待ち行列の受け取りを止めない
                        self._note(e, getattr(callback, "__qualname__", ""))
                        import traceback
                        traceback.print_exc()
        except queue.Empty:
            pass
        try:
            self.root.after(POLL_MS, self._poll)
        except Exception:
            pass   # 画面を閉じた後
