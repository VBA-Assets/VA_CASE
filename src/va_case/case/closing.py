"""終了処理：データフォルダを ZIP にして「移送待ち」に置く（仕様.md の6。2026-11-07 班長決定）。

現行（sht11.MoveFolder・Fldr.MoveInZip）は、手で作っておいた「<データフォルダ>.zip」を、フォルダ規則の場所へ移す。
Python 版では：
1. ZIP をアプリが作る（裏で行い、画面は止めない。進み具合を出し、取り消せる）。既定は無圧縮。
2. 置き場所は、日常の共有フォルダの中の「移送待ち」の、保管庫と同じフォルダ構成（フォルダ規則。yyyy は終了年）の場所。
   VA Case は保管庫に一切触れない。保管庫への移送は、利用者が保管庫を開いたときに手で行う。
3. 一時の名前（.part）で書き、中身（ファイルの数と CRC）を確かめてから正式の名前にする。
4. 元のデータフォルダは、利用者に確かめてから消す（確かめが通らなければ消さない）。
5. 事件の「データフォルダ」には「保管庫：<保管庫の中の相対パス>」を残す。VA Case からは開かない。終了した事件は、
   利用者がエクスプローラーで保管庫から探す（2026-11-09 班長決定。開けるようにしておくと、保管庫を常に開いておく
   運用につながるため。保管庫の場所も設定に持たない）。
   元のデータフォルダの欄の値も「 | 元の場所：<元の値>」として残す（2026-11-10 班長決定。現況を戻したときのため）。
6. 現況を「未了」などに戻したときは、元に戻す（2026-11-10 班長決定）：元のフォルダが残っていれば欄を戻すだけ、
   消してあって ZIP が移送待ちにあれば元の場所に展開して戻す。保管庫へ移した後は、VA Case は保管庫に触れないため
   戻さず、場所を知らせる（restore_plan・unzip）。

基点（移送待ちの場所）が見つからなければ、作らずに止める（3.3）。作ってよいのは、その下のフォルダだけ。
"""
import os
import shutil
import stat
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from ..common.errors import FolderMissingError
from ..common.paths import place_key
from . import model as m

ARCHIVE_PREFIX = "保管庫："
ORIGIN_SEP = " | 元の場所："    # 「|」はフォルダの名前に使えない字なので、区切りに使える
PART_SUFFIX = ".part"
RESTORING_SUFFIX = ".展開中"


class Cancelled(Exception):
    pass


@dataclass
class ClosingPlan:
    source: Path      # 元のデータフォルダ
    rel: str          # 保管庫の中の相対パス（ZIP のファイルまで。区切りは /）
    target: Path      # 移送待ちの中の ZIP
    members: list = None   # データフォルダの欄を保管庫の値にする事件の番号（この事件と、同じフォルダを使う終わった事件）


def sharing_rows(row, rows, data_root=""):
    """同じデータフォルダ（場所で比べる。保管庫の値は除く）を使う、ほかの事件の行。"""
    value = row[m.COL["データフォルダ"]]
    if not value or is_archived(value):
        return []
    key = place_key(value, data_root)
    number = row[m.COL["事件番号"]]
    return [r for r in rows if r[m.COL["事件番号"]] != number and r[m.COL["データフォルダ"]]
            and not is_archived(r[m.COL["データフォルダ"]]) and place_key(r[m.COL["データフォルダ"]], data_root) == key]


def archived_members(row, rows):
    """同じ ZIP（保管庫の値の場所が同じ）を指す、ほかの事件の行（まとめて ZIP にした事件。現況を戻すときに一緒に戻す）。"""
    value = row[m.COL["データフォルダ"]]
    if not is_archived(value):
        return []
    rel = archived_rel(value)
    number = row[m.COL["事件番号"]]
    return [r for r in rows if r[m.COL["事件番号"]] != number and is_archived(r[m.COL["データフォルダ"]])
            and archived_rel(r[m.COL["データフォルダ"]]) == rel]


def case_label(rows):
    return "・".join(f"{r[m.COL['事件番号']]}「{r[m.COL['事件呼名']]}」" for r in rows)


def is_archived(value):
    return (value or "").startswith(ARCHIVE_PREFIX)


def archived_value(rel, origin=""):
    """終了処理の後の「データフォルダ」の値。origin：元の欄の値（現況を戻したときに使う）。"""
    return ARCHIVE_PREFIX + rel + (ORIGIN_SEP + origin if origin else "")


def archived_rel(value):
    """「保管庫：…」の値から、保管庫の中の相対パス（区切りは /）を取り出す。"""
    return value[len(ARCHIVE_PREFIX):].split(ORIGIN_SEP, 1)[0].strip()


def archived_origin(value):
    """「保管庫：…」の値から、元のデータフォルダの欄の値を取り出す（記録がなければ ""。2026-11-10 より前の事件など）。"""
    parts = value[len(ARCHIVE_PREFIX):].split(ORIGIN_SEP, 1)
    return parts[1].strip() if len(parts) == 2 else ""


def archived_location(value):
    """「保管庫：…」の値から、保管庫の中の場所（Windows の区切り）を取り出す（利用者に示すため）。"""
    return archived_rel(value).replace("/", "\\")


def _relative_rule(rule):
    """フォルダ規則の場所を、保管庫の中の相対パスにする。

    現行の規則は「E:\\終了事件\\個人一般\\yyyy」のような絶対パスだが、VA Case は保管庫の場所を持たないため
    （2026-11-09 班長決定）、絶対パスの規則は受け付けず、保管庫の中の相対パスに書き直してもらう。
    """
    norm = rule.replace("\\", "/")
    if not (PureWindowsPath(rule).drive or norm.startswith("/")):
        return norm.strip("/")
    raise ValueError(f"フォルダ規則の場所「{rule}」は、保管庫の中の場所として読めません。\n"
                     "フォルダ規則には、保管庫の中の場所（例：個人一般\\yyyy）を書いてください。")


def plan(row, rows, rules_table, cfg):
    """終了処理の計画を立てる。できないときは ValueError（利用者に示す文）か FolderMissingError。"""
    value = row[m.COL["データフォルダ"]]
    if not value:
        raise ValueError("データフォルダが入っていないため、終了処理（ZIP の作成）はしません。")
    if is_archived(value):
        raise ValueError("この事件のデータフォルダは、すでに ZIP にして移送待ちに置いてあります。")
    number = row[m.COL["事件番号"]]
    # 同じデータフォルダを使うほかの事件（2026-11-13 班長決定「案１、２は、提案どおりで良い」）：まだ終わっていない事件が
    # あれば ZIP にしない。すべて終わっていれば、まとめて ZIP にし、それらの事件の欄もすべて保管庫の値にする。それまでは
    # 現行の Ver7J0 と同じく、ほかの事件があれば（終わっていても）知らせるだけで、共有のフォルダは ZIP にならなかった
    others = sharing_rows(row, rows, getattr(cfg, "data_root", ""))
    active = [r for r in others if r[m.COL["現況"]] not in m.MOVE_STATUSES]
    if active:
        raise ValueError(f"同じデータフォルダを使う、まだ終わっていない事件（事件番号 {case_label(active)}）があるため、"
                         "ZIP にはしません。\n最後の事件が終わったときに、まとめて ZIP にします。")
    source = m.resolve_folder(value, cfg.data_root)
    if source is None or not source.is_dir():
        raise ValueError(f"データフォルダが見つかりません：{value}")
    rule = m.find_folder_rule(rules_table, row)
    if rule is None:
        raise ValueError("この事件の現況・受任区分・事件区分に合うフォルダ規則がありません。\n"
                         "「事務所の設定」のフォルダ規則に足してください。")
    rel_dir = _relative_rule(m.apply_year(rule, m.end_year_text(row)))
    if not cfg.outbox:
        raise ValueError("移送待ちの場所が設定されていません。「この PC の設定」で設定してください。")
    outbox = Path(cfg.outbox)
    if not outbox.is_dir():
        raise FolderMissingError(outbox, "移送待ちのフォルダ")
    rel = (PurePosixPath(rel_dir) / (source.name + ".zip")).as_posix() if rel_dir else source.name + ".zip"
    target = outbox / Path(*PurePosixPath(rel).parts)
    if target.exists():
        raise ValueError(f"移送待ちに、同じ名前の ZIP がすでにあります：{target}")
    return ClosingPlan(source, rel, target, [number] + [r[m.COL["事件番号"]] for r in others])


def _files(source):
    files, dirs = [], []
    for root, dnames, fnames in os.walk(source):
        rootp = Path(root)
        if not dnames and not fnames:
            dirs.append(rootp)
        for f in fnames:
            files.append(rootp / f)
    return files, dirs


def make_zip(p, *, compress=False, progress=None, cancelled=None):
    """ZIP を作り、確かめてから正式の名前にする。（ファイルの数, 大きさ）を返す。

    progress(済んだバイト数, 全体のバイト数, いまのファイル名)、cancelled()：真なら取り消す。
    中の名前は、データフォルダの名前を先頭に付ける（エクスプローラーの「圧縮」と同じ形）。
    """
    files, empty_dirs = _files(p.source)
    sizes = {}
    for f in files:
        try:
            sizes[f] = f.stat().st_size
        except OSError:
            sizes[f] = 0
    total = sum(sizes.values())
    p.target.parent.mkdir(parents=True, exist_ok=True)   # 移送待ちの下だけを作る（移送待ちそのものは plan で確かめ済み）
    part = p.target.with_name(p.target.name + PART_SUFFIX)
    method = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
    base = p.source.parent
    done = 0
    try:
        with zipfile.ZipFile(part, "w", compression=method, allowZip64=True) as z:
            for d in empty_dirs:
                z.writestr(d.relative_to(base).as_posix() + "/", b"")
            for f in files:
                if cancelled and cancelled():
                    raise Cancelled()
                if progress:
                    progress(done, total, f.name)
                z.write(f, f.relative_to(base).as_posix())
                done += sizes[f]
        if progress:
            progress(total, total, "中身を確かめています")
        with zipfile.ZipFile(part) as z:
            bad = z.testzip()
            if bad is not None:
                raise OSError(f"ZIP の中身の確かめが通りませんでした（{bad}）。")
            count = sum(1 for i in z.infolist() if not i.is_dir())
        if count != len(files):
            raise OSError(f"ZIP の中のファイルの数（{count}）が、元のフォルダ（{len(files)}）と合いません。")
        os.rename(part, p.target)   # 正式の名前に（Windows では、同じ名前があれば失敗する）
    except BaseException:
        try:
            part.unlink()
        except OSError:
            pass
        raise
    return len(files), p.target.stat().st_size


def delete_source(source):
    """元のデータフォルダを消す（利用者に確かめてから呼ぶ）。読み取り専用のファイルも消す。"""
    def _retry(func, path, _exc):
        os.chmod(path, stat.S_IWRITE)
        func(path)
    if sys.version_info >= (3, 12):
        shutil.rmtree(source, onexc=_retry)
    else:   # Mac などで、古い Python から使う場合
        shutil.rmtree(source, onerror=_retry)


# ------------------------------------------------------------ 現況を戻したとき（2026-11-10 班長決定）

@dataclass
class RestorePlan:
    """終了処理を戻す計画。

    kind："folder"（元のフォルダが残っている。欄を戻すだけ）、"unzip"（移送待ちの ZIP を展開して戻す）、
    "moved"（移送待ちに ZIP がない。保管庫へ移した後とみて、戻さずに知らせる）。
    """
    kind: str
    zip_path: Path            # 移送待ちの中の ZIP（ないこともある）
    origin_value: str         # 戻す欄の値（記録がなければ ""）
    origin: Path = None       # 戻す場所（記録がなく、展開する場所を選んでもらうときは None）

    @property
    def zip_exists(self):
        return self.zip_path.is_file()


def restore_plan(row, cfg):
    """終了処理を戻す計画を立てる。できないときは ValueError（利用者に示す文）か FolderMissingError。"""
    value = row[m.COL["データフォルダ"]]
    if not is_archived(value):
        raise ValueError("この事件は、終了処理で ZIP にしていません。")
    if not cfg.outbox:
        raise ValueError("移送待ちの場所が設定されていません。「この PC の設定」で設定してください。")
    outbox = Path(cfg.outbox)
    if not outbox.is_dir():
        raise FolderMissingError(outbox, "移送待ちのフォルダ")
    zip_path = outbox / Path(*PurePosixPath(archived_rel(value)).parts)
    origin_value = archived_origin(value)
    origin = m.resolve_folder(origin_value, cfg.data_root) if origin_value else None
    if origin_value and origin is None:
        raise ValueError(f"元の場所「{origin_value}」は相対パスですが、「この PC の設定」の"
                         "「事務所のフォルダの場所」が空です。")
    if origin is not None and origin.is_dir():
        return RestorePlan("folder", zip_path, origin_value, origin)
    if not zip_path.is_file():
        return RestorePlan("moved", zip_path, origin_value, origin)
    if origin is not None:
        if origin.exists():
            raise ValueError(f"元の場所に、同じ名前のファイルがあります：{origin}")
        if not origin.parent.is_dir():   # 基点（ドライブ・同期フォルダ）がないときは作らない（3.3）
            raise FolderMissingError(origin.parent, "元のデータフォルダの上のフォルダ")
    return RestorePlan("unzip", zip_path, origin_value, origin)


def _members(z, top):
    """ZIP の中身が「<top>/…」だけであることを確かめ、(名前, 情報) の一覧を返す。"""
    out = []
    for i in z.infolist():
        parts = PurePosixPath(i.filename).parts
        bad = (not parts or parts[0] != top or any(x in ("..", "") for x in parts) or i.filename.startswith("/")
               or ":" in i.filename or "\\" in i.filename)
        if bad:
            raise ValueError(f"ZIP の中の形が、終了処理で作ったものと違います（{i.filename}）。手で展開してください。")
        out.append(i)
    return out


def unzip(zip_path, target, *, progress=None, cancelled=None):
    """移送待ちの ZIP を target（戻すデータフォルダ）に展開する。（ファイルの数, 大きさ）を返す。

    target の隣の一時の名前のフォルダに展開し、ファイルの数と CRC を確かめてから正式の名前にする（途中で止まっても、
    中途半端なデータフォルダを残さない）。ZIP の中は「<フォルダの名前>/…」の形（make_zip で作ったもの）に限る。
    """
    target = Path(target)
    if target.exists():
        raise ValueError(f"戻す場所に、同じ名前のフォルダかファイルがあります：{target}")
    top = Path(zip_path).stem
    work = target.parent / (target.name + RESTORING_SUFFIX)
    if work.exists():
        raise ValueError(f"前に展開しかけたフォルダが残っています。中を確かめて、手で消してください：{work}")
    with zipfile.ZipFile(zip_path) as z:
        members = _members(z, top)
        files = [i for i in members if not i.is_dir()]
        total = sum(i.file_size for i in files)
        done = 0
        work.mkdir()
        try:
            for i in members:
                if cancelled and cancelled():
                    raise Cancelled()
                dest = work.joinpath(*PurePosixPath(i.filename).parts[1:])
                if i.is_dir():
                    dest.mkdir(parents=True, exist_ok=True)
                    continue
                if progress:
                    progress(done, total, PurePosixPath(i.filename).name)
                dest.parent.mkdir(parents=True, exist_ok=True)
                with z.open(i) as r, open(dest, "wb") as w:   # 読み終わりに CRC を確かめる（合わなければ BadZipFile）
                    shutil.copyfileobj(r, w, 1024 * 1024)
                done += i.file_size
            if progress:
                progress(total, total, "中身を確かめています")
            count = sum(1 for f in work.rglob("*") if f.is_file())
            if count != len(files):
                raise OSError(f"展開したファイルの数（{count}）が、ZIP の中（{len(files)}）と合いません。")
            os.rename(work, target)   # 正式の名前に（同じ名前があれば失敗する）
        except BaseException:
            delete_source(work)
            raise
    return len(files), total


def delete_zip(zip_path, outbox):
    """移送待ちの ZIP を消し、空になった上のフォルダも消す（移送待ちそのものは残す）。"""
    zip_path = Path(zip_path)
    zip_path.unlink()
    outbox = Path(outbox).resolve()
    d = zip_path.parent
    while d.resolve() != outbox and outbox in d.resolve().parents:
        try:
            d.rmdir()          # 空でなければ失敗する
        except OSError:
            break
        d = d.parent
