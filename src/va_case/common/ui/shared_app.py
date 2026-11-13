"""共有データを使うツールの画面の、共通の仕組み（4つのツールで使う）。

VA Case で作ったもの（2026-11-09）を、VA Filing などでも使えるよう、ここに移した：
- 共有データの読み込み・日次バックアップ・競合の写しの知らせ
- 編集モード（編集を始める・終える。始める間はボタンを点滅させ、カーソルを砂時計にする）と、モードの表示
  （編集モードは、一覧の表のスタイルを TableStyleMedium3 にならったオレンジ系にする）
- 共有データの書き込み（裏で行い、画面は止めない。編集モードでなければ、書き込む間だけ編集モードに入る）
- 一覧の組み立て・検索・CSV（3つの画面で共通の作り）
- 一覧の動き（キー操作・加速・折り返し・何行かを選ぶ・コピー）は list_view.py の ListView から受け継ぐ
- 事務所の設定の画面を出す仕組みは office_host.py の OfficeHost から受け継ぐ（2026-11-12 に分けた）
- 診断情報（［ヘルプ］→［診断情報をコピー］）は diagnostics_host.py の DiagnosticsHost から受け継ぐ（同日に分けた）
- 閉じるときの後始末

ツールごとの画面は、この SharedApp を受け継ぎ、クラスの属性（TITLE・TOOL など）と、_build_body・refresh を書く。
"""
import os
import subprocess
import sys
import tkinter as tk
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .. import backup as backupmod
from .. import diagnostics
from .. import csvio
from ..errors import ConflictError, LockedByOtherError, NotEditingError, SharedError
from ..master import create_master
from ..search import Query, normalize
from ..store import SharedStore
from . import ime, theme
from .background import Background
from .icons import IconSet, icon_name
from .ribbon import Ribbon
from .tooltip import Tooltip
from .list_view import ListView
from .office_host import OfficeHost
from .diagnostics_host import DiagnosticsHost


def prepare_process(app_id):
    """画面を作る前に呼ぶ（Windows）。DPI を知らせて、拡大した画面でも字をぼやけさせない（VA Document と同じ）。
    python で起動したときも、タスクバーで python.exe とまとめられないよう、アプリの ID を付ける。"""
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    if not getattr(sys, "frozen", False):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except Exception:
            pass


def open_path(path):
    """フォルダ・ファイル・URL を、OS に任せて開く（現行の FollowHyperlink に当たる）。"""
    if sys.platform == "win32":
        os.startfile(str(path))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def icon_path(name):
    """アイコン（assets の中の name）の場所。exe（PyInstaller）では展開先に入れたもの（VA Document と同じ）。"""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    else:
        base = Path(__file__).resolve().parents[4]
    return base / "assets" / name


def set_window_icon(root, name):
    """ウィンドウ・タスクバーのアイコンを付ける（2026-11-13 班長指示「各ツールのファビコンを作成」。VA Document と同じ
    付け方。exe のアイコンは、PyInstaller の spec で別に埋め込む）。見つからない・読めないときは既定のまま（起動を
    妨げない）。"""
    path = icon_path(name) if name else None
    if path is None or not path.exists():
        return
    try:
        if os.name == "nt":
            root.iconbitmap(default=str(path))
        # ウィンドウ自身にも大小のアイコンを付ける（タスクバー・Alt+Tab が、このアイコンを使う）
        import io
        from PIL import Image
        photos = []
        with Image.open(path) as im:
            for size in sorted(im.info.get("sizes", []), reverse=True):
                if size[0] not in (256, 48, 32, 16):
                    continue
                im.size = size
                buf = io.BytesIO()
                im.convert("RGBA").save(buf, format="PNG")
                photos.append(tk.PhotoImage(master=root, data=buf.getvalue()))
        if photos:
            root._va_icon_images = photos                  # 画像の参照を残す（消えないように）
            root.iconphoto(True, *photos)                  # これから作るウィンドウ（確認の画面など）にも
    except Exception:
        pass


class SharedApp(DiagnosticsHost, OfficeHost, ListView):
    TITLE = ""                 # 画面の題名（例：VA Case）
    ICON_FILE = ""             # ウィンドウ・タスクバーのアイコン（assets の .ico。ツールごとに決める）
    TOOL = ""                  # 共有データの tool の欄
    SCHEMA = None              # テーブル名 → 列名の並び
    MASTER_FILE_NAME = ""      # 共有データのファイル名の既定（例：VA_Case.json）
    BUSY_CLOSE_MESSAGE = "書き込み中です。閉じると途中で止まります（共有データは壊れません）。\nそれでも閉じますか？"
    DEFAULT_GEOMETRY = "1280x720"
    BLINK_MS = 450
    SWITCH_NOTICE_MS = 500     # 編集の開始がこれより長くかかったら、切り替え中の表示を出す（2026-11-11）

    def __init__(self, root, settings_module):
        self.root = root
        self.settings = settings_module
        self.cfg = settings_module.load()
        self.errors = diagnostics.ErrorLog(settings_module.TOOL_KEY)   # 起きた誤り（診断情報に載せる）
        self.bg = Background(root, on_change=self._busy_changed, on_exception=self.errors.record)
        root.report_callback_exception = self._on_callback_error
        self._cursors = None        # 動作中のカーソルにする前の、部品ごとのカーソル
        self._cursor_job = None
        self.store = None
        self.data = None            # 最後に読み込んだ（書き込んだ）共有データ
        self.editing = False
        self.writing = False
        self.loading = False
        self.backup_done_on = None
        self.editor_text = ""
        self._waiting = False
        self._switch_job = None     # 切り替え中の表示を出す予定（_show_switching）
        self._write_queue = []      # 書き込み中に頼まれた書き込み（終わってから順に行う）
        self._after_writes = []     # 書き込みがすべて終わったら行うこと（after_writes）
        self._edit_only = []        # 編集モードでだけ使えるボタン（閲覧モードでは止める）
        self._edit_only_menu = []   # 同じく、メニューの項目（メニュー, 位置）
        self._mode_cards = []       # 一覧の下の入力欄の枠（モードで見た目を変える。mode_card）
        self.init_list_state()
        self.init_office_state()
        self.query = Query("")      # いまの検索
        self.norm_cache = {}        # 検索に使う、行の値を正規化したもの（_norm）

        root.title(self.TITLE)
        theme.apply_theme(root)
        set_window_icon(root, self.ICON_FILE)
        ime.follow_focus(root)      # IME の入力中の字を、入力欄の書体で出す（2026-11-11 班長決定）
        w, h = (int(x) for x in self.DEFAULT_GEOMETRY.split("x"))
        default = f"{theme.px(root, w)}x{theme.px(root, h)}"      # 拡大した画面では、その分大きく
        try:
            root.geometry(self.cfg.window_geometry or default)
        except tk.TclError:
            root.geometry(default)
        self._build_menu()
        self.icons = IconSet(root)
        self._build_toolbar()
        self._build_status()      # 状態の欄を先に下へ置く（VA Filing の入力欄より下にするため）
        self._build_body()
        self._restore_column_widths()
        self._apply_edit_only()   # 起動したときは閲覧モード
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(100, self.startup)

    # ------------------------------------------------------------ ツールごとに書くもの

    def _build_menu(self):
        raise NotImplementedError

    def _build_toolbar(self):
        """リボンを作る：build_ribbon（「編集」の組。self.edit_button）・ツールの組・build_search_group（「検索」の組）。"""
        raise NotImplementedError

    def _build_body(self):
        """self.tree（一覧）を作ること。"""
        raise NotImplementedError

    def refresh(self):
        """self.data を一覧に出す。最後に self._update_mode() を呼ぶこと。"""
        raise NotImplementedError

    def empty_tables(self):
        raise NotImplementedError

    def open_settings(self):
        """この PC の設定の画面。設定を変えたら True。"""
        raise NotImplementedError

    def on_data(self, data):
        """共有データを読み込んだ・書き込んだ後に呼ばれる（ツールごとの下ごしらえ）。"""

    def load_extra(self):
        """読み込むときに、裏で一緒に読むもの（VA Filing が読む VA Case の共有データなど）。"""
        return None

    def on_extra(self, extra):
        """load_extra の結果を受け取る（画面のスレッドで、on_data の前に呼ばれる）。"""

    # ------------------------------------------------------------ 状態の欄

    def _build_status(self):
        sb = ttk.Frame(self.root, padding=(8, 2, 8, 4))
        sb.pack(fill="x", side="bottom")
        self.mode_label = ttk.Label(sb, text="読み込んでいません", style="Status.TLabel")
        self.mode_label.pack(side="left")
        self.count_label = ttk.Label(sb, text="", style="Status.TLabel")
        self.count_label.pack(side="left", padx=(12, 0))
        self.work_label = ttk.Label(sb, text="", style="Status.TLabel")
        self.work_label.pack(side="right")

    # ------------------------------------------------------------ 検索の欄・一覧・検索・CSV（ツールで共通の作り）
    #
    # 2026-11-10 のリファクタリングで、VA Case・VA Call・VA Filing/Receipt の画面に別々に書いていた同じ処理を、
    # ここにまとめた（動きは変えていない。CSV の取り込みの知らせで、知らせることが20件を超えたときの「ほか N 件」
    # は、それまで VA Case だけだったものを、ほかのツールにも出す）。

    ROW_NAME = "行"           # 検索で見つからないときの「当てはまる〇〇はありません。」
    CSV_FILE_NAME = "一覧"    # CSV に出力するファイルの名前の先頭（<名前>_<日付>.csv）
    CSV_NOTE = ""             # CSV に出力した後の注意（何が入っているか）
    CSV_IMPORT_NAME = ""      # 取り込むときの「N 件〇〇を取り込みます」（VA Case は「の事件」）

    def csv_columns(self):
        """CSV の列（共有データの列の順）。"""
        raise NotImplementedError

    def csv_date_columns(self):
        """CSV から取り込むときに、日付として読む列。"""
        return ()

    CSV_REQUIRED = ()          # CSV から取り込むときに、必ず要る列（なければ止める。VA Case の事件番号）
    CSV_MULTI_DATE_COLUMNS = ()   # 日付の列のうち、1行に1つずつ何人かの日付を入れる列（VA Case の生年月日）

    def csv_drop_existing(self, tables, rows):
        """取り込む行のうち、すでに同じ記録があるものを除く。→ (残す行, 除いた数)。既定は除かない
        （VA Case は、すでにある事件番号があれば取り込み全体を止めるので、二重にならない）。"""
        return rows, 0

    def csv_add(self, tables, rows):
        """CSV から読んだ行を足した、新しい tables を返す（読めない値があれば ValueError）。"""
        raise NotImplementedError

    def csv_rows(self):
        """CSV に出力する行（None なら出力しない）。"""
        return self.rows

    # リボン（2026-11-13 班長指示「リボンのコマンドボタンをVA Documentのように変更」。ribbon.py）。それまでは、ふつうの
    # ボタンを1列に並べたツールバーだった。組の順は、編集・ツールの組・検索。

    def build_ribbon(self):
        """リボンを置き、「編集」の組（［編集を始める］大・［最新を読み込む］）を作って返す。"""
        rb = Ribbon(self.root, self.icons)
        rb.pack(fill="x", padx=8, pady=(6, 2))
        g = rb.group("編集")
        self.edit_button = g.large("編集を始める", self.toggle_edit, style="RibbonEdit.TButton", tip=self._edit_tip)
        g.small("最新を読み込む", self.reload_latest,
                tip="共有データを読み直し、ほかの人が書き込んだ変更を一覧に出します。直した値があれば、先に書き込みます。\nF5")
        return rb

    def _edit_button_image(self, text):
        """［編集を始める］（鉛筆）・［編集を終える］（斜線の入った鉛筆）のアイコン。"""
        name = icon_name(text)
        normal = self.icons.image(name, large=True) if name else None
        if normal is None:
            return {}
        return {"image": (normal, "disabled", self.icons.image(name, disabled=True, large=True) or normal)}

    def _edit_tip(self):
        if self.editing:
            return ("編集モードを終えて、閲覧モードに戻ります。ほかの人が編集できるようになります。"
                    "いま出している行で直した値がまだ書き込まれていなければ、先に書き込みます。")
        return ("編集モードにして、追加・直す・消すができるようにします。編集モードの間、ほかの人は閲覧だけになります"
                "（同時に編集できるのは1人です）。一覧とカードの枠がオレンジになります。")

    def build_search_group(self, rb):
        """「検索」の組（検索の欄・OR/AND・結果を表示・すべてを表示）を作る。"""
        g = rb.group("検索")
        box = ttk.Frame(g.body, style="Ribbon.TFrame")
        ttk.Label(box, text="検索", style="Ribbon.TLabel").grid(row=0, column=0, sticky="w", padx=(2, 6), pady=1)
        self.search_var = tk.StringVar()
        e = ttk.Entry(box, textvariable=self.search_var, width=22)
        e.grid(row=0, column=1, columnspan=2, sticky="w", pady=1)
        e.bind("<Return>", lambda ev: self.apply_search())
        e.tooltip = Tooltip(e, "探す語を入れて Enter か［結果を表示］を押すと、その語を含む行だけを出します。"
                               "語は空白で区切って、いくつも入れられます。")
        self.mode_var = tk.StringVar(value="OR")
        modes = ttk.Frame(box, style="Ribbon.TFrame")
        modes.grid(row=1, column=1, sticky="w", pady=1)
        r = ttk.Radiobutton(modes, text="OR", value="OR", variable=self.mode_var)
        r.pack(side="left")
        r.tooltip = Tooltip(r, "語をいくつか入れたとき、どれか1つを含む行を出します。")
        r = ttk.Radiobutton(modes, text="AND", value="AND", variable=self.mode_var)
        r.pack(side="left", padx=(6, 0))
        r.tooltip = Tooltip(r, "語をいくつか入れたとき、すべてを含む行だけを出します。")
        g.block(box)
        g.small("結果を表示", self.apply_search, tip="検索の欄の語で、一覧の行を絞り込みます。")
        # 検索とフィルタ（見出しをクリックして掛ける）の絞り込みを、まとめて外す（2026-11-11 班長決定「A 1つにまとめる」。
        # 名前は同日 班長決定「すべてを表示」。
        # それまでは、検索の「元に戻す」と「フィルタを解除」の2つだった）。絞っていない間は使えない（mark_filtered_columns）。
        # 検索だけを外すときは検索の欄を空にして「結果を表示」、1つの列のフィルタだけを外すときは見出しの「この列のフィルタを解除」
        self.clear_narrow_button = g.small(
            "すべてを表示", self.clear_narrowing, state="disabled",
            tip="検索と、見出しで掛けたフィルタを、まとめて外して、すべての行を出します。")

    def build_list(self, columns, display_columns, widths, parent=None):
        """一覧（self.tree）を、縦横のスクロールバーを付けて、残りの場所いっぱいに置く。

        行を選んだら self._on_select() を呼ぶ。すべてのセルを列の幅で折り返して出し（2026-11-09 班長指示）、キー操作と
        コピーを付ける。字の色のタグ・ダブルクリック・Enter は、ツールの側で付ける。parent：置く場所（既定は窓）。
        """
        frame = ttk.Frame(parent or self.root, padding=(8, 0, 8, 0))
        frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(frame, columns=columns, displaycolumns=display_columns, show="headings",
                                 selectmode="browse")
        for c in columns:
            self.tree.heading(c, text=c, command=lambda c=c: self.open_filter(c))   # 見出しのクリックでフィルタ
            self.tree.column(c, width=theme.px(self.root, widths.get(c, 100)), stretch=False)
        ys = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        xs = ttk.Scrollbar(frame, orient="horizontal", command=self.tree.xview)
        # 一覧が動いたら、セルに重ねた文字の欄を外す（セルの文字を選ぶ。list_view.py）
        self.tree.configure(yscrollcommand=lambda *a: (ys.set(*a), self.cell_text_hide()),
                            xscrollcommand=lambda *a: (xs.set(*a), self.cell_text_hide()))
        self.tree.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="we")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._on_select())
        self.bind_wrapped_list(self.tree)
        self.bind_table_keys(self.tree)
        return self.tree

    def _norm(self, row):
        """検索に使う、行の値を正規化したもの（行ごとに覚える。共有データを読み直したら on_data で空にする）。"""
        key = id(row)
        v = self.norm_cache.get(key)
        if v is None:
            v = [normalize(x) if x else "" for x in row]
            self.norm_cache[key] = v
        return v

    def narrowed_label(self):
        """件数の欄の頭（検索・フィルタで絞っていなければ ""）。"""
        parts = (["検索"] if not self.query.empty else []) + (["フィルタ"] if self.filters else [])
        return "・".join(parts) + "の結果" if parts else ""

    def apply_search(self):
        self.query = Query(self.search_var.get(), self.mode_var.get())
        self.refresh()
        if not self.query.empty and not self.tree.get_children():
            messagebox.showinfo(self.TITLE, f"当てはまる{self.ROW_NAME}はありません。", parent=self.root)
        else:
            self._focus_table()   # 検索の結果を、すぐに矢印キーで選べるように

    def clear_narrowing(self):
        """「すべてを表示」：検索の欄を空にし、検索とすべての列のフィルタを外して、全件を出す。"""
        self.search_var.set("")
        self.query = Query("")
        self.filters = {}
        self.refresh()
        self._focus_table()

    def export_csv(self):
        if self.data is None:
            return
        rows = self.csv_rows()
        if rows is None:
            return
        path = filedialog.asksaveasfilename(parent=self.root, title="CSV に出力", defaultextension=".csv",
                                            initialfile=f"{self.CSV_FILE_NAME}_{date.today():%Y%m%d}.csv",
                                            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            csvio.export_csv(path, self.csv_columns(), rows)
        except OSError as e:
            messagebox.showerror(self.TITLE, f"書き出せませんでした。\n{e}", parent=self.root)
            return
        messagebox.showinfo(self.TITLE, f"{len(rows)} 件を出力しました。\n{path}\n\n{self.CSV_NOTE}"
                                        "使い終わったら消すなど、置き場所に気をつけてください。", parent=self.root)

    def import_csv(self):
        if self.data is None or not self._require_edit():
            return
        path = filedialog.askopenfilename(parent=self.root, title="CSV から取り込む",
                                          filetypes=[("CSV", "*.csv"), ("すべて", "*.*")])
        if not path:
            return
        try:
            got = csvio.import_csv(path, self.csv_columns(), self.csv_date_columns(), self.CSV_REQUIRED,
                                   multi_date_columns=self.CSV_MULTI_DATE_COLUMNS)
            # すでに同じ記録がある行は取り込まない（同じ CSV を2回取り込んで二重になるのを防ぐ。2026-11-11 班長決定）
            rows, same = self.csv_drop_existing(self.data.tables, got.rows)
            self.csv_add(self.data.tables, rows)   # 先に確かめる（書き込むときにも、もう一度確かめる）
        except (csvio.CsvError, ValueError, OSError) as e:
            messagebox.showerror(self.TITLE, f"取り込めませんでした。何も変えていません。\n\n{e}", parent=self.root)
            return
        if not rows:
            messagebox.showinfo(self.TITLE, f"CSV の {len(got.rows)} 件は、すべて、すでに同じ記録があります。"
                                            "何も取り込みませんでした。", parent=self.root)
            return
        msg = f"{len(rows)} 件{self.CSV_IMPORT_NAME}を取り込みます（文字コード：{got.encoding}）。"
        if same:
            msg += f"\n\nCSV の {len(got.rows)} 件のうち {same} 件は、すでに同じ記録があるので取り込みません。"
        if got.warnings:
            msg += "\n\n知らせること：\n" + "\n".join(got.warnings[:20])
            if len(got.warnings) > 20:
                msg += f"\n（ほか {len(got.warnings) - 20} 件）"
        if not messagebox.askyesno(self.TITLE, msg + "\n\nよろしいですか？", parent=self.root):
            return
        # 書き込む直前の最新の共有データでも、同じ記録を除く
        self.write(lambda t: self.csv_add(t, self.csv_drop_existing(t, rows)[0]), f"CSV の {len(rows)} 件")

    # ------------------------------------------------------------ 編集モードでだけ使えるボタン

    def edit_only(self, widget):
        """編集モードでだけ使えるボタンとして覚える（閲覧モードでは止めて、灰色にする。2026-11-10 班長指示）。"""
        self._edit_only.append(widget)
        return widget

    def edit_only_menu(self, menu):
        """直前に足したメニューの項目を、編集モードでだけ使えるものとして覚える。"""
        self._edit_only_menu.append((menu, menu.index("end")))

    def _apply_edit_only(self):
        enabled = self.editing
        for w in self._edit_only:
            w.state(["!disabled"] if enabled else ["disabled"])
        for menu, index in self._edit_only_menu:
            menu.entryconfigure(index, state="normal" if enabled else "disabled")

    # ------------------------------------------------------------ 読み込み

    def startup(self):
        if not self.cfg.master_path:
            messagebox.showinfo(self.TITLE, f"はじめに、共有データのファイル（{self.MASTER_FILE_NAME}）の場所を設定して"
                                            "ください。\n新しく始めるときは、置きたいフォルダを選び、ファイルの名前を入れる"
                                            "と作れます。", parent=self.root)
            if not self.open_settings():
                return
        self.open_store()

    def open_store(self):
        path = Path(self.cfg.master_path)
        if path.suffix.lower() != ".json":
            path = path / self.MASTER_FILE_NAME
            self.cfg.master_path = str(path)
        self.store = SharedStore(path, self.TOOL, self.SCHEMA)
        if not path.exists() and path.parent.is_dir():
            if messagebox.askyesno(self.TITLE, f"共有データのファイルがありません。\n{path}\n\n新しく作りますか？"
                                               "（ほかの人がすでに作っている場合は、同期が終わるのを待ってください）",
                                   parent=self.root):
                try:
                    create_master(path, self.TOOL, self.empty_tables(), self.store.identity)
                except (OSError, SharedError) as e:
                    messagebox.showerror(self.TITLE, str(e), parent=self.root)
                    return
        self.reload()

    def reload(self):
        if self.store is None:
            return
        if self.writing or self._write_queue:
            messagebox.showinfo(self.TITLE, "書き込み中です。終わってから読み込みます。", parent=self.root)
            return
        if self.loading:
            return
        self.loading = True
        self.work_label.configure(text="読み込んでいます…")

        def _load():
            data = self.store.load()
            editor = self.store.editor(data)
            mine = self.store.is_editing() if self.editing else False
            return data, editor, mine, self.store.conflict_copies(), self.load_extra()
        self.bg.run(_load, self._on_loaded, self._on_load_error)

    def _on_loaded(self, result):
        self.loading = False
        data, editor, mine, copies, extra = result
        self.data = data
        self.on_extra(extra)
        if self.editing and not mine:
            self.editing = False
            messagebox.showwarning(self.TITLE, "編集の権利がなくなっていたため、閲覧モードに戻りました。", parent=self.root)
        self.editor_text = f"{editor.user} さん（{editor.machine}）が編集中" if editor else ""
        first = not self.tree.get_children()
        self.on_data(data)
        self.refresh()
        if first:
            self._focus_table()
            self.after_first_load()
        self.work_label.configure(text=f"読み込みました（{datetime.now():%H:%M:%S}・共有データの版 {data.version}）")
        if copies:
            messagebox.showwarning(self.TITLE, "共有フォルダに、共有データの「競合の写し」と思われるファイルがあります。\n"
                                   + "\n".join(f"・{p.name}" for p in copies)
                                   + "\n\n編集を始める前に、どちらの内容が正しいかを確かめ、要らない方を共有フォルダの外へ"
                                     "移してください。", parent=self.root)
        self._daily_backup()

    def after_first_load(self):
        """起動して最初に読み込んだ後に呼ばれる（最初に選ぶ行など）。"""

    def _on_load_error(self, e):
        self.loading = False
        self.work_label.configure(text="読み込めませんでした")
        msg = str(e) if isinstance(e, (SharedError, OSError)) else f"読み込み中に誤りが起きました：{e!r}"
        messagebox.showerror(self.TITLE, msg, parent=self.root)

    def _daily_backup(self):
        if self.backup_done_on == date.today() or not self.cfg.backup_folder:
            return
        self.backup_done_on = date.today()

        def _done(result):
            res, path = result
            if res is backupmod.BackupResult.CREATED:
                self.work_label.configure(text=f"今日のバックアップを作りました（{path.name}）")
            elif res is backupmod.BackupResult.FOLDER_MISSING:
                messagebox.showwarning(self.TITLE, "バックアップのフォルダが見つからないため、バックアップを作りませんで"
                                       f"した。\n{self.cfg.backup_folder}\n\n暗号化した仮想ドライブを使っている場合は、"
                                       "開いているかを確かめてください。", parent=self.root)
        self.bg.run(lambda: backupmod.daily_backup(self.store.path, self.cfg.backup_folder), _done,
                    lambda e: self.work_label.configure(text=f"バックアップを作れませんでした：{e}"))

    # ------------------------------------------------------------ モードの表示

    def _update_mode(self):
        """いまのモードを、一覧の表のスタイル・ウィンドウの題名・ボタン・状態の欄に出す。

        編集モードの一覧は、VA事件データベース（VAブリッジ）と同じく、表のスタイルを替える（見出しをオレンジの地に
        白い太字、行を1行おきに淡いオレンジ、罫線をオレンジ。2026-11-09 班長指示）。
        """
        self.tree.configure(style="Edit.Treeview" if self.editing else "Treeview")
        self.mark_filtered_columns()
        self._sync_office()     # 開いている事務所の設定の画面を、モードに合わせる
        # 1行おきの地の色：編集モードは淡いオレンジ、閲覧モードは淡い灰色（2026-11-09 班長指示）
        self.tree.tag_configure("band", background=theme.EDIT_TABLE_BAND)
        self.tree.tag_configure("band_view", background=theme.VIEW_TABLE_BAND)
        band = "band" if self.editing else "band_view"
        for i, iid in enumerate(self.tree.get_children()):
            tags = [t for t in self.tree.item(iid, "tags") if t not in ("band", "band_view")]
            if i % 2 == 1:
                tags.append(band)
            self.set_row_tags(iid, tags)   # 縞は、データの1行ごと（子の行も同じ地の色）
        for box in self._mode_cards:
            box.configure(style="EditCard.TFrame" if self.editing else "Card.TFrame")
        self._apply_edit_only()
        self.root.title(f"{self.TITLE} － {'編集モード' if self.editing else '閲覧モード'}")
        if not self._waiting:
            text = "編集を終える" if self.editing else "編集を始める"
            self.edit_button.configure(text=text, style=self._edit_button_style(), **self._edit_button_image(text))
        if self.editing:
            self.mode_label.configure(text="編集モード（ほかの人は閲覧だけ）", style="Edit.TLabel")
        else:
            self.mode_label.configure(text="閲覧モード" + (f"　{self.editor_text}" if self.editor_text else ""),
                                      style="Status.TLabel")

    def mode_card(self, parent, padding):
        """一覧の下の入力欄（カード）の枠を作り、中身を置く枠を返す（枠は parent に詰めて置く）。

        一覧と同じく、モードで見た目を変える（2026-11-10 班長指示「カード側も編集が可能になるので、こちらも変更したい」。
        同日 班長決定「帯と枠をオレンジ」「4つのツールすべて」）：編集モードでは、枠線を一覧の罫線と同じオレンジにする。
        閲覧モードは灰色の枠。入力欄の地は変えない。上端の題名の帯（「選んだ事件（編集モード）」など）は、同日 班長指示
        「カードの『選んだ事件』などの標題ラベルは不要」でやめた。
        """
        box = ttk.Frame(parent, style="Card.TFrame", padding=1)
        box.pack(fill="x")
        body = ttk.Frame(box, padding=padding)
        body.pack(fill="both", expand=True)
        self._mode_cards.append(box)
        return body

    # ------------------------------------------------------------ 編集モード

    def toggle_edit(self):
        if self.store is None or self.loading:
            return
        if self.editing:
            # 入力欄で直した値は、先に書き込む（2026-11-12 班長決定。「書き込む」のボタンはなくした）
            if not self.commit_pending():
                return
            if self.writing or self._write_queue:
                self.work_label.configure(text="書き込みが終わったら、編集を終えます…")
                self.after_writes(self.toggle_edit)
                return
            if self.office_dirty() and not messagebox.askyesno(
                    self.TITLE, "事務所の設定の画面に、書き込んでいない変更があります。\n変更を捨てて、編集を終えますか？",
                    icon="warning", parent=self._office_dlg):
                return
            self.store.end_edit()
            self.editing = False
            self._update_mode()
            self.work_label.configure(text="編集を終えました")
            return
        if self.writing:
            return
        self.loading = True
        # 切り替え中の表示（ボタンの文・点滅・状態の欄）は、時間がかかったときだけ出す（2026-11-11 班長決定「遅いときだけ
        # 出す」。同期の待ちをなくしてふだんは 0.3 秒ほどで終わり、すぐ出すと一瞬ちらつくだけになったため。遅い共有フォルダ・
        # 大きな共有データでは、今も数秒かかる）。動作中の回転カーソルは、すぐ出す（_busy_changed）
        self._switch_job = self.root.after(self.SWITCH_NOTICE_MS, self._show_switching)

        def _done(data):
            self.loading = False
            self._cancel_switching()
            self.data = data
            self.editing = True
            self.editor_text = ""
            self.on_data(data)
            self.refresh()
            self.work_label.configure(text=f"編集モードに入りました（{datetime.now():%H:%M:%S}）")

        def _err(e):
            self.loading = False
            self._cancel_switching()
            self._update_mode()
            self.work_label.configure(text="編集を始められませんでした")
            messagebox.showwarning(self.TITLE, str(e), parent=self.root)
            if isinstance(e, (LockedByOtherError, ConflictError)):
                self.reload()
        self.bg.run(self.store.begin_edit, _done, _err)

    # ------------------------------------------------------------ 動作中のカーソル

    def _busy_changed(self):
        """裏の処理が始まった・終わった。画面のカーソルを、少し後でまとめて合わせる（続けて次の書き込みが始まる
        ときに、ちらつかないように。終わったときの画面の作り直しの間も、回転したままにする）。"""
        if self._cursor_job is None:
            try:
                self._cursor_job = self.root.after_idle(self._apply_cursor)
            except tk.TclError:
                pass

    def _apply_cursor(self):
        """動作中（裏で読み書き・ZIP の作成などをしている間）は、画面のどこでも、カーソルを回転表示にする
        （2026-11-10 班長指示「動作中は、常にマウスカーソルを回転表示にする」）。入力欄・一覧などは、それぞれの
        カーソル（文字の入力の I の字など）を持つので、部品ごとに替え、終わったら元に戻す。"""
        self._cursor_job = None
        busy = self.bg.busy or self._waiting
        if busy and self._cursors is None:
            self._cursors = {}
            for w in self._all_widgets(self.root):
                try:
                    self._cursors[w] = w.cget("cursor")
                    w.configure(cursor="watch")
                except tk.TclError:
                    pass
        elif not busy and self._cursors is not None:
            for w, cursor in self._cursors.items():
                try:
                    if w.winfo_exists():
                        w.configure(cursor=cursor)
                except tk.TclError:
                    pass
            self._cursors = None

    @classmethod
    def _all_widgets(cls, w):
        yield w
        for c in w.winfo_children():
            yield from cls._all_widgets(c)

    def _edit_button_style(self):
        """「編集を始める」はオレンジの枠（押すと一覧・カードがオレンジの編集モードになる）、「編集を終える」は青の枠
        （2026-11-10 班長指示「オレンジに変えたい時にオレンジのボタンを押す。ブルーに変えたい時にブルーのボタンを押す」）。"""
        return "RibbonEditEnd.TButton" if self.editing else "RibbonEdit.TButton"

    def _show_switching(self):
        """編集の開始が SWITCH_NOTICE_MS たっても終わっていなければ、切り替え中の表示を出す。"""
        self._switch_job = None
        if not self.loading or self.editing:
            return
        self.work_label.configure(text="モードを切り替えています…")
        self._start_waiting("モードを切り替えています…")   # 2026-11-10 班長指示（それまでは「編集を始めています…」）

    def _cancel_switching(self):
        """編集の開始が終わった。まだ出していない切り替え中の表示を取りやめ、出していれば元に戻す。"""
        if self._switch_job is not None:
            self.root.after_cancel(self._switch_job)
            self._switch_job = None
        if self._waiting:
            self._stop_waiting()

    def _start_waiting(self, text):
        """待っている間、「編集を始める」のボタンを点滅させ、カーソルを砂時計にする（2026-11-09 班長指示。
        押しても動いていないと誤解されないように）。"""
        self._waiting = True
        self.edit_button.configure(text=text)
        self._busy_changed()
        self._blink(True)

    def _blink(self, on):
        if not self._waiting:
            return
        self.edit_button.configure(style="RibbonBlink.TButton" if on else "RibbonEdit.TButton")
        self.root.after(self.BLINK_MS, self._blink, not on)

    def _stop_waiting(self):
        self._waiting = False
        self.edit_button.configure(style=self._edit_button_style())
        self._busy_changed()

    def _require_edit(self, busy_ok=False):
        """閲覧モードなら知らせて False。busy_ok が偽なら、書き込み・読み込みの最中も知らせて False（真なら、書き込み中
        でも編集モードなら通す。書き込みは待ち行列に入る。VA Call・VA Filing・VA Receipt の入力欄の操作）。"""
        if not self.editing:
            messagebox.showinfo(self.TITLE, "閲覧モードです。直すときは「編集を始める」を押してください。",
                                parent=self.root)
            return False
        if not busy_ok and (self.writing or self.loading):
            messagebox.showinfo(self.TITLE, "書き込み中（または読み込み中）です。終わってから、もう一度操作してください。",
                                parent=self.root)
            return False
        return True

    def write(self, transform, label, after=None, select=None, *, action=None, undo=None, on_error=None):
        """共有データを書き替える。裏で行い、画面は止めない。

        transform(いまの tables) → 新しい tables。action を渡すと、書き込む前に action() を行い（ファイルの移動など）、
        その戻り値を transform(tables, 戻り値) に渡す。書き込めなかったときは undo(戻り値) で action を戻す
        （ファイルは動いたのに記録が残らない、という食い違いを避けるため）。
        編集モードでなければ、書き込む間だけ編集モードに入る（2026-11-07 班長決定）。編集の権利を得てから action を
        行うので、ほかの人が編集中なら、ファイルは動かさずに止まる。
        書き込み中に頼まれたら、待ち行列に入れ、いまの書き込みが終わってから行う（VA Filing で続けて保管するとき）。
        """
        if self.writing:
            self._write_queue.append((transform, label, after, select, action, undo, on_error))
            self.work_label.configure(text=f"{label}は、いまの書き込みの後に書き込みます（待ち {len(self._write_queue)} 件）")
            self.on_queue_changed()
            return
        self.writing = True
        self.work_label.configure(text=f"{label}を書き込んでいます…")
        temporary = not self.editing

        def _work():
            if temporary:
                self.store.begin_edit()
            elif not self.store.is_editing():
                raise NotEditingError("編集の権利がなくなっています。もう一度「編集を始める」を押してください。")
            try:
                if action is None:
                    return self.store.save(transform(self.store.loaded.tables))
                ctx = action()
                try:
                    return self.store.save(transform(self.store.loaded.tables, ctx))
                except BaseException:
                    if undo is not None:
                        undo(ctx)
                    raise
            finally:
                if temporary:
                    self.store.end_edit()

        def _done(data):
            self.writing = False
            self.data = data
            self.on_data(data)
            self.refresh()
            if select:
                self.select_key(select)
            self.work_label.configure(text=f"{label}を書き込みました（{datetime.now():%H:%M:%S}・版 {data.version}）")
            if after:
                after()
            self._next_write()

        def _err(e):
            self.writing = False
            dropped = self._write_queue
            self._write_queue = []
            self.on_queue_changed()
            self.work_label.configure(text=f"{label}を書き込めませんでした")
            self._after_writes = []     # 書き込めなかったので、待っていたこと（編集を終える・閉じるなど）は行わない
            if on_error is not None:
                on_error(e)
            else:
                self.show_write_error(e)
            if dropped:
                messagebox.showwarning(self.TITLE, f"書き込みを待っていた {len(dropped)} 件（"
                                       + "・".join(d[1] for d in dropped[:5]) + ("…" if len(dropped) > 5 else "")
                                       + "）は、行いませんでした。確かめてから、もう一度操作してください。",
                                       parent=self.root)
            if isinstance(e, (ConflictError, NotEditingError)):
                self.editing = self.store.is_editing()
                self.reload()
        self.bg.run(_work, _done, _err)

    def show_write_error(self, e):
        msg = str(e) if isinstance(e, (SharedError, ValueError, OSError)) else f"書き込み中に誤りが起きました：{e!r}"
        messagebox.showerror(self.TITLE, msg, parent=self.root)

    def _next_write(self):
        if self._write_queue and not self.writing:
            transform, label, after, select, action, undo, on_error = self._write_queue.pop(0)
            self.on_queue_changed()
            self.write(transform, label, after, select, action=action, undo=undo, on_error=on_error)
        elif not self.writing and self._after_writes:
            todo, self._after_writes = self._after_writes, []
            for then in todo:
                then()

    # ------------------------------------------------------------ 直した値の書き込み（2026-11-12 班長決定）
    #
    # 入力欄（VA Case のカード・VA Call の入力欄・VA Filing と VA Receipt の保管済みの行の備考）で直した値は、ほかの行に
    # 移るとき・編集を終えるとき・閉じるとき・最新を読み込むときなどに、自動で書き込む（それまでは「書き込む」「備考を
    # 書き込む」のボタンで書いた。班長の問い「カードの「書き込む」ボタンは、必要なのだろうか？」に案を示し、決定）。

    def commit_pending(self):
        """入力欄で直したまま書いていない値があれば、書き込みを始める（待ち行列に入れる）。ツールごとに書く。
        → True：書くものがない、または書き込みを始めた。False：確かめで止めた（知らせは済み。その行に留まる）。"""
        return True

    def after_writes(self, then):
        """いまの書き込みと待ち行列がすべて終わってから then() を行う（書き込めなかったときは行わない）。"""
        if not self.writing and not self._write_queue:
            then()
        elif then not in self._after_writes:
            self._after_writes.append(then)

    def reload_latest(self):
        """「最新を読み込む」（メニュー・F5・ボタン）。直した値があれば、先に書き込む。"""
        if not self.commit_pending():
            return
        self.after_writes(self.reload)

    def can_close(self):
        """閉じる前の確かめ（直した値を書き込んだ後に呼ぶ）。ツールごとに書く。False なら閉じない。"""
        return True

    def on_queue_changed(self):
        """書き込みの待ち行列が変わったときに呼ばれる（待っている行の印など）。"""

    def select_key(self, key):
        """書き込んだ後に選ぶ行（ツールごとに、行を見分ける値で選ぶ）。"""

    # ------------------------------------------------------------ 閉じる

    def remember_view(self):
        """閉じるときに、画面の見た目（ツールごとのもの）を設定に覚える。"""

    def on_close(self):
        if not self.commit_pending():
            return
        if self.writing or self._write_queue:
            self.work_label.configure(text="書き込みが終わったら、閉じます…")
            self.after_writes(self.on_close)
            return
        if not self.can_close():
            return
        if self.bg.busy:
            if not messagebox.askyesno(self.TITLE, self.BUSY_CLOSE_MESSAGE, icon="warning", parent=self.root):
                return
        if self.editing and self.store is not None:
            try:
                self.store.end_edit()
            except OSError:
                pass
        try:
            self.cfg.window_geometry = self.root.geometry()
            self._remember_column_widths()
            self.remember_view()
            self.settings.save(self.cfg)
        except OSError:
            pass
        self.root.destroy()
