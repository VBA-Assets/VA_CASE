"""共通部品が利用者に知らせる事態。str(例外) が、そのまま利用者に示す文になる。"""


class SharedError(Exception):
    """共有に関わる事態の基底。"""


class FolderMissingError(SharedError):
    """基点となるフォルダが見つからない。作らずに止める（3.3）。"""

    def __init__(self, folder, what="共有フォルダ"):
        self.folder = folder
        super().__init__(
            f"{what}が見つかりません。\n{folder}\n\n"
            "暗号化した仮想ドライブを使っている場合は、開いているか（ロックを解除しているか）を確かめてください。"
            "共有フォルダの接続と、設定のフォルダの場所も確かめてください。")


class MasterNotFoundError(SharedError):
    def __init__(self, path):
        self.path = path
        super().__init__(
            f"共有データのファイルが見つかりません。\n{path}\n\n"
            "暗号化した仮想ドライブを使っている場合は、開いているかを確かめてください。"
            "同期フォルダの場合は、同期が終わっているかを確かめてください。")


class MasterCorruptError(SharedError):
    """読めない・中身の確かめが通らない（同期・置き換えの途中の可能性がある）。"""

    def __init__(self, path, detail):
        self.path = path
        super().__init__(
            f"共有データのファイルを正しく読めませんでした（{detail}）。\n{path}\n\n"
            "同期の途中の可能性があります。しばらく待ってから、もう一度読み込んでください。"
            "続く場合は、バックアップから戻す必要があります。")


class SchemaMismatchError(SharedError):
    """テーブルの列が、このアプリの期待と違う（VAブリッジの checkHeaderConsistency に当たる）。"""

    def __init__(self, table, detail):
        self.table = table
        super().__init__(f"共有データのテーブル「{table}」の列が、このアプリと合いません（{detail}）。"
                         "アプリの版が違う可能性があります。")


class ConflictCopyError(SharedError):
    """同期・仮想ドライブが作った競合の写しがある。黙って使わず知らせる（3.3）。"""

    def __init__(self, copies):
        self.copies = list(copies)
        names = "\n".join(f"・{p.name}" for p in self.copies)
        super().__init__(
            "共有フォルダに、共有データの「競合の写し」と思われるファイルがあります。\n"
            f"{names}\n\n"
            "2台以上の PC で同時に書き込まれ、同期のソフトが別のファイルとして残したものと考えられます。"
            "どちらの内容が正しいかを確かめ、要らない方を共有フォルダの外へ移してから、もう一度操作してください。")


class LockedByOtherError(SharedError):
    """ほかの人（ほかの PC）が編集中。

    PC が止まるなどして「編集中」の印（ロックファイル）が残ったときは、アプリの機能では消さず、本人に確かめてから
    エクスプローラーで消してもらう（2026-11-09 班長決定。ふだん使わない機能は、そのほうが確実で分かりやすい）。
    """

    def __init__(self, user, machine="", at="", lock_file=None):
        self.user, self.machine, self.at, self.lock_file = user, machine, at, lock_file
        where = f"（{machine}" + (f"、{at} から" if at else "") + "）" if machine else ""
        msg = f"{user} さん{where}が編集中です。閲覧だけできます。"
        if lock_file:
            msg += ("\n\nその PC が止まるなどして、編集を終えないまま「編集中」の印が残っている場合は、"
                    "本人に確かめてから、次のファイルをエクスプローラーで消してください。\n" f"{lock_file}")
        super().__init__(msg)


class LockRaceError(SharedError):
    """ロックを取った直後に、ほかの人のロックが見つかった（VAブリッジの acquireLock の「競合が発生しました」）。"""

    def __init__(self, user):
        self.user = user
        super().__init__(f"{user} さんが、ほぼ同時に編集を始めました。自分の編集の開始を取り消しました。"
                         "閲覧だけできます。")


class NotEditingError(SharedError):
    """編集の権利（自分の有効なロック）がない。"""

    def __init__(self, reason=""):
        super().__init__("編集の権利がないため、書き込めません。" + (f"\n{reason}" if reason else ""))


class ConflictError(SharedError):
    """読み込んだ後に、ほかの人が共有データを書き替えていた（VAブリッジの MSG_CONFLICT_GUIDE に当たる）。"""

    def __init__(self, by_user="", at=""):
        self.by_user, self.at = by_user, at
        who = f"{by_user} さんによって" if by_user else "ほかの人によって"
        when = f"（{at}）" if at else ""
        super().__init__(
            f"共有データが、読み込んだ後に{who}更新されています{when}。\n"
            "書き込みを止めました。いまの変更は書き込まれていません。"
            "もう一度読み込んでから、変更をやり直してください。")


class WriteVerifyError(SharedError):
    def __init__(self, path):
        self.path = path
        super().__init__(
            f"共有データを書き込んだ後の確かめで、書いた内容と一致しませんでした。\n{path}\n\n"
            "ほかの PC の書き込みや同期と重なった可能性があります。もう一度読み込んで、内容を確かめてください。")
