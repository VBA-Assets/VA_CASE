"""右クリックのメニュー（コピー・貼り付け）。4つのツールで共通。

2026-11-15 班長指示「シリーズの全ツールについて、次の右クリックメニューを追加する。プレビュー、リスト、カードのすべてで、
文字列を選択した後に右クリックするとコピーができるようにする。編集モードにおいては、カードのテキストボックスで右クリック
すると貼り付けができるようにする。」
- 入力欄（ttk.Entry・ttk.Combobox・tk.Text。カードの欄のほか、番号などの読み取り専用の欄、検索の欄、設定の画面の欄
  も）：「コピー」（文字を選んでいなければ押せない）。直せる欄（編集モードのカードの欄など）では、「貼り付け」も出す。
  閲覧モードの欄と、読み取り専用の欄には、「貼り付け」を出さない。install で、部品の種類（クラス）ごとに付ける。
- 一覧：セルの中でなぞって選んだ文字の「コピー」（cell_text.py の _cell_menu から popup を呼ぶ）。行のコピーは出さない
  （2026-11-14 に、リボンの［コピー］にまとめた）。
- プレビュー：もとからある（preview.py の _menu。「このページの文字をすべて選ぶ」もある）。
コピーと貼り付けは、Ctrl+C・Ctrl+V と同じ処理で行う（1行の欄に何行かを貼り付けたら1行につなげる theme の
_paste_one_line、入力欄全体の元に戻す〔undo.py〕、保管ファイル名を作り直すなどのキーを離したときの処理も、そのまま働く）。
メニューを開くと、入力先が一時メニューへ移り、欄で選んだ字が外れることがある（theme の、欄を出たら選んだ字を外す決まり）。
そのため、選んでいた字と範囲は、右クリックしたときに覚えておく。
"""
import tkinter as tk
from tkinter import ttk

CLASSES = ("TEntry", "TCombobox", "TSpinbox", "Text", "Entry")   # 右クリックのメニューを付ける部品の種類


def install(root):
    """入力欄（文字を選べる部品）すべてに、右クリックのメニューを付ける。"""
    for cls in CLASSES:
        root.bind_class(cls, "<Button-3>", _field_menu)


def popup(widget, x_root, y_root, copy=None, paste=None):
    """右クリックのメニューを出す。copy：「コピー」で呼ぶもの（None なら、押せない「コピー」を出す）。paste：
    「貼り付け」で呼ぶもの（None なら、「貼り付け」を出さない）。クリップボードに字がなければ、「貼り付け」は押せない。"""
    root = widget.winfo_toplevel()
    menu = getattr(root, "_va_text_menu", None)
    if menu is None or not menu.winfo_exists():
        menu = tk.Menu(root, tearoff=False)
        root._va_text_menu = menu
    menu.delete(0, "end")
    menu.add_command(label="コピー", accelerator="Ctrl+C", command=copy or (lambda: None),
                     state="normal" if copy else "disabled")
    if paste is not None:
        menu.add_command(label="貼り付け", accelerator="Ctrl+V", command=paste,
                         state="normal" if _clipboard_text(widget) else "disabled")
    try:
        menu.tk_popup(x_root, y_root)
    finally:
        menu.grab_release()


# ------------------------------------------------------------ 入力欄

def _field_menu(event):
    w = event.widget
    if isinstance(w, str):          # 消えかけの部品など（名前しか取れない）
        return "break"
    sel = selection(w)
    text = selected_text(w, sel)
    copy = (lambda: _copy(w, text)) if text else None
    paste = (lambda: _paste(w, sel)) if editable(w) else None
    popup(w, event.x_root, event.y_root, copy=copy, paste=paste)
    return "break"


def editable(w):
    """直せる欄か（ttk の欄は disabled でも readonly でもない。tk の欄は normal）。"""
    try:
        if isinstance(w, ttk.Widget):
            return bool(w.instate(["!disabled", "!readonly"]))
        return str(w.cget("state")) == "normal"
    except tk.TclError:
        return False


def selection(w):
    """欄で選んでいる範囲（始め, 終わり）。選んでいなければ None。"""
    try:
        if isinstance(w, tk.Text):
            r = w.tag_ranges("sel")
            return (str(r[0]), str(r[1])) if r else None
        if w.selection_present():
            return (w.index("sel.first"), w.index("sel.last"))
    except (tk.TclError, AttributeError):
        pass
    return None


def selected_text(w, sel):
    if sel is None:
        return ""
    try:
        if isinstance(w, tk.Text):
            return w.get(*sel)
        return w.get()[sel[0]:sel[1]]
    except tk.TclError:
        return ""


def _copy(w, text):
    try:
        w.clipboard_clear()
        w.clipboard_append(text)
    except tk.TclError:
        pass


def _paste(w, sel):
    """Ctrl+V と同じく貼り付ける。右クリックしたときに選んでいた字は、貼り付けた字で置き換える。"""
    try:
        if not w.winfo_exists() or not editable(w):
            return
        w.focus_set()          # 元に戻す（undo.py）が、どの欄の変更かを入力先で知るため
        if sel is not None:
            if isinstance(w, tk.Text):
                w.tag_remove("sel", "1.0", "end")
                w.tag_add("sel", *sel)
                w.mark_set("insert", sel[1])
            else:
                w.selection_range(*sel)
                w.icursor(sel[1])
        w.event_generate("<<Paste>>")
        # Ctrl+V では、キーを離したときの処理（VA Filing・VA Receipt の保管ファイル名の作り直し、VA Case の代理人の
        # 住所などを入れる処理など）も働くので、同じく、キーを離したことにする
        w.event_generate("<KeyRelease>", keysym="v")
    except tk.TclError:        # 消えかけの部品など
        pass


def _clipboard_text(widget):
    try:
        return bool(widget.clipboard_get())
    except tk.TclError:        # クリップボードが空・文字でない
        return False
