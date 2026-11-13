"""利用者と PC の名前（ロック・マスタの書き込み記録に使う）。

外部と通信しない：PC の名前は OS が持っている値を読むだけで、名前の解決（DNS など）はしない。
"""
import getpass
import os
import platform
import re

# ファイル名に使えない文字（Windows と Mac の両方）。VAブリッジの SanitizeFileName に当たる
_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def user_name():
    """利用者の名前（Windows のユーザー名。Mac はログイン名）。取れなければ "unknown"。"""
    try:
        name = getpass.getuser()
    except Exception:  # 環境変数がない場合など
        name = ""
    return name or "unknown"


def machine_name():
    """PC の名前（Windows は COMPUTERNAME）。取れなければ "unknown"。"""
    name = os.environ.get("COMPUTERNAME") or platform.node()
    return name or "unknown"


def sanitize(text):
    """ファイル名の一部に使えるよう、使えない文字を _ に置き換える。"""
    text = _UNSAFE.sub("_", text).strip(" .")
    return text or "_"


class Identity:
    """書き込む人・PC の組。試験では、別の人・PC になりすまして2人の動きを再現するために、値を指定して作る。"""

    def __init__(self, user=None, machine=None):
        self.user = user if user is not None else user_name()
        self.machine = machine if machine is not None else machine_name()

    @property
    def key(self):
        """ロックファイルの名前に使う「人@PC」。"""
        return f"{sanitize(self.user)}@{sanitize(self.machine)}"

    def __eq__(self, other):
        return isinstance(other, Identity) and self.key == other.key

    def __hash__(self):
        return hash(self.key)

    def __repr__(self):
        return f"Identity({self.user!r}, {self.machine!r})"
