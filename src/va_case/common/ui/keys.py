"""ショートカットのキーの組（標準 02「メニュー」：Windows の Ctrl と同じものを、Mac の ⌘ にも割り当てる。2026-11-19）。

⌘（Command）は、Mac（Tk の windowingsystem が aqua）のときだけ足す。Windows の Tk でも <Command-…> は登録できて
しまうが、Windows では別の修飾キーに当たり、思わぬときに働くおそれがあるため、付けない。
"""


def modifiers(widget):
    """Ctrl のショートカットに使う修飾キー。Windows では ("Control",)、Mac では ("Control", "Command")。"""
    try:
        aqua = widget.tk.call("tk", "windowingsystem") == "aqua"
    except Exception:
        aqua = False
    return ("Control", "Command") if aqua else ("Control",)


def ctrl_sequences(widget, key):
    """Ctrl＋key の bind に使う並び。1文字の英字なら、Caps Lock でも効くよう大文字も付ける。
    例："z" → ["<Control-z>", "<Control-Z>"]（Mac では "<Command-z>"・"<Command-Z>" も）。"Home" → ["<Control-Home>"]。"""
    keys = (key, key.upper()) if len(key) == 1 and key.isalpha() else (key,)
    return [f"<{mod}-{k}>" for mod in modifiers(widget) for k in keys]
