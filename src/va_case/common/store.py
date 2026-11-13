"""共有データの読み込み・編集の開始・書き込み・編集の終了（VAブリッジの basSync に当たる。仕様.md の3）。

使い方（各ツールの画面から）：

    store = SharedStore(path, "VA Case", schema)
    data = store.load()                 # 閲覧（いつでも）
    data = store.begin_edit()           # 編集モード（ロックを取り、最新を読み直す）
    data = store.save(tables)           # 書き込み（編集モードのまま続けられる）
    store.end_edit()                    # 編集モードを終える（ロックを消す）

VAブリッジとの対応と違い：
- 読み込み（loadFromMaster）：共有データを丸ごと読む。利用者の PC に写しを残さない（2026-11-09 班長決定）。
- 編集の開始：ロックを取ってから読み直す（Ver321 の「ロック確保→データ読み込み」の順）。
- 書き込み（writeToMaster）：共有データを読み直し、読み込んだ後にほかの人が書き替えて
  いないか（write_id）、自分のロックがまだ有効かを確かめ、一時ファイルを介して丸ごと書き替える。書いた後に読み直して
  確かめる。VAブリッジは書き込むと閲覧モードに戻るが、ここでは end_edit=True を渡したときだけ戻る（編集を続けられる）。
- 競合の判定は、ファイルの更新日時ではなく、共有データの中の write_id で行う（3.3）。
- 競合の写しがあれば、編集の開始・書き込みを止めて知らせる（3.3）。閲覧の読み込みは止めない（conflict_copies で知らせる）。

- 同期の伝わりを待つことはしない（VAブリッジの Ver300 以降と同じ）。2026-11-11 まで「同期を待つ秒数」（既定3秒、のち0秒）の
  設定を持ち、編集の開始と書き込みの前に待っていたが、2台での試験で同期フォルダの遅れが数秒〜5分と分かり、待ちでは
  守れないので、設定ごとなくした（2026-11-11 班長決定。仕様.md の 3.1・3.3）。守りは、編集の開始でロックを書いた直後の
  確かめ、書く直前の読み直し（write_id）、競合の写しの検出が担う。

限界：同期の遅れの間に2人がほぼ同時に編集を始めると、2人が互いのロックを見ないまま編集モードに入ることがある。
その場合も、後から書き込んだ人は write_id の食い違いで止まるので、共有データが黙って上書きされることはない。
"""
import time
from pathlib import Path

from . import fileio
from . import lock as lockmod
from .errors import (ConflictCopyError, ConflictError, LockedByOtherError, LockRaceError, NotEditingError,
                     SchemaMismatchError, WriteVerifyError)
from .identity import Identity
from .master import MasterData, check_schema, new_write_id, now_text, parse, read_master, serialize


class SharedStore:
    def __init__(self, master_path, tool, schema=None, *, identity=None, sleep=time.sleep):
        """
        master_path：共有データのファイル
        tool：ツールの名前（共有データ・ロックに書く）
        schema：{テーブル名: 列の名前の一覧}。読み書きのたびに、共有データのテーブルと列がこれと一致することを確かめる
        identity：書き込む人・PC（試験では、別の人になりすますために指定する）
        sleep：待つ関数（読めないとき・拒まれたときのやり直しの間。試験で差し替える）
        """
        self.path = Path(master_path)
        self.tool = tool
        self.schema = schema
        self.identity = identity or Identity()
        self.sleep = sleep
        self.loaded = None      # 最後に読み込んだ（または書き込んだ）共有データ
        self.lock_id = None     # 自分が取ったロック（編集モードでなければ None）

    # ---- 閲覧 ----

    def _read(self):
        data = read_master(self.path, sleep=self.sleep)
        if self.schema is not None:
            check_schema(data, self.schema)
        return data

    def load(self):
        """共有データを読む（閲覧）。編集モードのときは、編集モードのまま最新を読み直す。"""
        self.loaded = self._read()
        return self.loaded

    def conflict_copies(self):
        """競合の写しと思われるファイル（画面で知らせるため）。"""
        return fileio.find_conflict_copies(self.path)

    def _check_conflict_copies(self):
        copies = self.conflict_copies()
        if copies:
            raise ConflictCopyError(copies)

    def locks(self):
        return lockmod.list_locks(self.path)

    def editor(self, master=None):
        """いま有効なロックを持っている、自分以外の人（LockInfo）。いなければ None。"""
        master = master or self._read()
        for li in self.locks():
            if li.key != self.identity.key and lockmod.is_valid(li, master):
                return li
        return None

    # ---- 編集モード ----

    def is_editing(self):
        """自分の有効なロックがあるか（VAブリッジの hasMyLock。都度ファイルで確かめる）。"""
        if not self.lock_id:
            return False
        try:
            master = self._read()
            self._check_my_lock(master)
        except Exception:
            return False
        return True

    def begin_edit(self):
        """編集モードに入る（VAブリッジの acquireLock）。入れたら、最新の共有データを返す。"""
        master = self._read()
        self._check_conflict_copies()
        mine_key = self.identity.key
        for li in self.locks():
            if li.key == mine_key:
                continue   # 自分（この PC）の前のロック。この後で置き換える
            if lockmod.is_valid(li, master):
                raise LockedByOtherError(li.user, li.machine, li.at, li.path)
            lockmod.remove_lock(li.path, sleep=self.sleep)   # 無効なロックを消す（cleanUpStaleLocks）

        lock_id = lockmod.write_lock(self.path, self.identity, self.tool, master, sleep=self.sleep)
        # 書いた直後に、自分のロックが残っていること、ほかのロックがないことを確かめる（VAブリッジの acquireLock の2回目）
        try:
            master2 = self._read()
            self._check_conflict_copies()
            locks = self.locks()
            mine = next((li for li in locks if li.key == mine_key), None)
            if mine is None or mine.lock_id != lock_id:
                raise NotEditingError("自分のロックファイルを確かめられませんでした。もう一度試してください。")
            for li in locks:
                if li.key != mine_key and lockmod.is_valid(li, master2):
                    raise LockRaceError(li.user)
            if master2.write_id != master.write_id:
                w = master2.written
                raise ConflictError(w.get("user", ""), w.get("at", ""))
        except Exception:
            self._remove_my_lock(lock_id)
            raise
        self.lock_id = lock_id
        self.loaded = master2
        return master2

    def _check_my_lock(self, master):
        """自分のロックがまだ有効で、ほかの人の有効なロックがないことを確かめる。"""
        locks = self.locks()
        mine = next((li for li in locks if li.key == self.identity.key), None)
        if mine is None or mine.lock_id != self.lock_id:
            raise NotEditingError("自分の「編集中」の印（ロックファイル）がなくなっています。共有フォルダから消された可能性が"
                                  "あります。もう一度「編集を始める」を押してください。")
        if not lockmod.is_valid(mine, master):
            w = master.written
            raise ConflictError(w.get("user", ""), w.get("at", ""))
        for li in locks:
            if li.key != self.identity.key and lockmod.is_valid(li, master):
                raise NotEditingError(f"{li.user} さんが編集を始めています。")

    def save(self, tables, *, end_edit=False):
        """共有データを tables（テーブル名 → Table）で丸ごと書き替える（VAブリッジの writeToMaster）。

        書けたら、書いた共有データを返す。end_edit=True なら、書いた後に編集モードを終える。
        """
        if not self.lock_id:
            raise NotEditingError("閲覧モードです。")
        if self.loaded is None:
            raise NotEditingError("共有データを読み込んでいません。")
        new = MasterData(tool=self.tool, tables={k: v.copy() for k, v in tables.items()})
        if self.schema is not None:
            check_schema(new, self.schema)
            if set(new.tables) != set(self.schema):
                extra = sorted(set(new.tables) - set(self.schema))
                raise SchemaMismatchError("・".join(extra), "このアプリの知らないテーブル")

        # 書く直前に読み直して確かめる
        master = self._read()
        self._check_conflict_copies()
        if master.write_id != self.loaded.write_id:
            w = master.written
            raise ConflictError(w.get("user", ""), w.get("at", ""))
        self._check_my_lock(master)

        new.version = master.version + 1
        new.write_id = new_write_id()
        new.written = {"user": self.identity.user, "machine": self.identity.machine, "at": now_text(),
                       "lock_id": self.lock_id}
        fileio.write_atomic(self.path, serialize(new), sleep=self.sleep)

        # 書いた後に読み直して、書いたとおりであることを確かめる（3.3）
        try:
            back = parse(fileio.read_bytes(self.path, sleep=self.sleep), self.path)
        except Exception:
            raise WriteVerifyError(self.path) from None
        if back.write_id != new.write_id:
            raise WriteVerifyError(self.path)
        self.loaded = back
        if end_edit:
            self.end_edit()
        return back

    def _remove_my_lock(self, lock_id):
        path = lockmod.lock_path(self.path, self.identity)
        for li in self.locks():
            if li.path.name == path.name and (li.lock_id == lock_id or li.data is None):
                lockmod.remove_lock(li.path, sleep=self.sleep)

    def end_edit(self):
        """編集モードを終える（VAブリッジの releaseLock）。自分のロックだけを消す。"""
        if self.lock_id:
            self._remove_my_lock(self.lock_id)
        self.lock_id = None
