"""保管（ファイルの移動と写しの作成）と、元に戻す（現行の MoveFile・MakeShortcuts・MakeCopies・MakeCopyOfSpecialFile
と、その逆の RstrFile・DeleteShortcuts・DeleteCopies・DeleteCopyOfSpecialFile）。

現行と違う点（仕様.md の 4.2.1）：
- 先にすべて確かめてから動かす（読込ファイル・保管フォルダ・写しの置き場所があるか、同じ名前のファイルがないか）。
  現行は、ファイルを移した後に写しの置き場所がないと分かると、写しだけ作らずに残った。
- 別のドライブへは、一時の名前で写し、大きさを確かめてから正式の名前にし、それから元のファイルを消す。
- 途中で失敗したら、それまでにしたことを戻す（ファイルを読込フォルダへ戻し、作った写しを消す）。
- フォルダは作らない（3.3。保管フォルダ・写しの置き場所が見つからなければ、知らせて止まる）。
"""
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from .fileio import temp_path_for
from . import shortcut

RETRY_COUNT = 10
RETRY_WAIT = 0.5

KIND_SHORTCUT = "ショートカット"
KIND_COPY = "コピー"

BAD_NAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def check_file_name(name):
    """保管ファイル名に使えない字があれば、その知らせ（なければ空）。"""
    if not name:
        return "保管ファイル名が入っていません。"
    bad = sorted(set(BAD_NAME_CHARS.findall(name)))
    if bad:
        shown = "・".join("改行など" if ord(c) < 32 else c for c in bad)
        return f"保管ファイル名に、ファイル名に使えない字（{shown}）があります。"
    if name.endswith((" ", ".")):
        return "保管ファイル名の最後に、空白か「.」があります。"
    return ""


class StoringError(Exception):
    """利用者に示す文を持つ誤り（保管・元に戻すを、何もせずに止めたとき）。"""


@dataclass
class Link:
    kind: str          # "ショートカット"・"コピー"・"特別な写し"
    folder: Path
    path: Path         # 作るファイル（ショートカットは <保管ファイル名>.lnk）
    label: str = ""    # 知らせに出す名前（特別な写しの語など）


@dataclass
class StorePlan:
    source: Path
    target: Path
    links: list = field(default_factory=list)
    skipped: list = field(default_factory=list)   # 作らなかった写しの知らせ（Mac でのショートカットなど）


@dataclass
class StoreResult:
    plan: StorePlan
    made: list         # 作った写し（Link）


def _retry(func):
    for i in range(RETRY_COUNT):
        try:
            return func()
        except PermissionError:
            if i == RETRY_COUNT - 1:
                raise
            time.sleep(RETRY_WAIT)


def link_path(kind, folder, file_name):
    return Path(folder) / (file_name + ".lnk" if kind == KIND_SHORTCUT else file_name)


def plan_store(source, folder, file_name, targets, specials, *, resolve):
    """保管の計画を立て、すべて確かめる。できなければ StoringError（何も動かしていない）。

    targets：(種類, フォルダの値) の並び（複製作成先）。specials：(語, フォルダの値) の並び（特別な写し）。
    resolve(値) は、フォルダの値をこの PC のパスにする（基点がなく読めなければ None）。
    """
    source = Path(source)
    if not source.is_file():
        raise StoringError(f"{source} が見つかりません。")
    dest = resolve(folder)
    if dest is None:
        raise StoringError(f"保管フォルダ「{folder}」を、この PC の場所として読めません（事務所のフォルダの場所を設定して"
                           "ください）。")
    if not dest.is_dir():
        raise StoringError(f"{dest} が見つかりません。\n（フォルダは作りません。暗号化した仮想ドライブを使っている場合は、"
                           "開いているかを確かめてください。）")
    problem = check_file_name(file_name)
    if problem:
        raise StoringError(problem)
    target = dest / file_name
    if target.exists():
        raise StoringError(f"{target} と同じ名前のファイルが既にあります。")
    p = StorePlan(source, target)
    for kind, value in targets:
        if kind == KIND_SHORTCUT and not shortcut.available():
            p.skipped.append(f"ショートカット（{value}）は、Windows でないため作りません。")
            continue
        p.links.append(Link(kind, _resolve_or_fail(resolve, value, f"{kind}の置き場所"), Path(), value))
    for word, value in specials:
        p.links.append(Link("特別な写し", _resolve_or_fail(resolve, value, f"{word}の写しの置き場所"), Path(), word))
    for link in p.links:
        if not link.folder.is_dir():
            raise StoringError(f"{link.folder} がありません（{link.kind}の置き場所）。\n（フォルダは作りません。）")
        link.path = link_path(link.kind, link.folder, file_name)
        if link.path.exists():
            raise StoringError(f"{link.path} と同じ名前のファイルが既にあります。")
    return p


def _resolve_or_fail(resolve, value, what):
    path = resolve(value)
    if path is None:
        raise StoringError(f"{what}「{value}」を、この PC の場所として読めません（事務所のフォルダの場所を設定してください）。")
    return path


def move_file(source, target):
    """ファイルを移す（上書きしない）。同じドライブなら名前の付け替え、別のドライブなら写して確かめてから元を消す。"""
    source, target = Path(source), Path(target)
    if target.exists():
        raise StoringError(f"{target} と同じ名前のファイルが既にあります。")
    try:
        _retry(lambda: os.rename(source, target))     # Windows の os.rename は、移す先にあれば失敗する（上書きしない）
        return
    except OSError as e:
        if target.exists() or not _is_cross_device(e):
            raise
    tmp = temp_path_for(target)
    try:
        shutil.copy2(source, tmp)
        if tmp.stat().st_size != source.stat().st_size:
            raise StoringError(f"{target} への写しの大きさが、元のファイルと合いません。")
        if target.exists():
            raise StoringError(f"{target} と同じ名前のファイルが既にあります。")
        os.rename(tmp, target)
    except BaseException:
        _quiet_unlink(tmp)
        raise
    try:
        _retry(lambda: os.unlink(source))
    except OSError:
        _quiet_unlink(target)    # 元を消せなければ、写しを消して、移さなかったことにする（両方に残さない）
        raise


def _is_cross_device(e):
    import errno
    return getattr(e, "winerror", None) == 17 or e.errno == errno.EXDEV


def _quiet_unlink(path):
    try:
        Path(path).unlink()
    except OSError:
        pass


def make_link(link, target):
    if link.kind == KIND_SHORTCUT:
        shortcut.create(link.path, target, target.parent)
    else:
        if link.path.exists():
            raise StoringError(f"{link.path} と同じ名前のファイルが既にあります。")
        tmp = temp_path_for(link.path)
        try:
            shutil.copy2(target, tmp)
            os.rename(tmp, link.path)
        except BaseException:
            _quiet_unlink(tmp)
            raise


def store(p):
    """計画のとおり保管する。途中で失敗したら、それまでにしたことを戻して、誤りを伝える。"""
    move_file(p.source, p.target)
    made = []
    try:
        for link in p.links:
            make_link(link, p.target)
            made.append(link)
    except BaseException:
        undo_store(StoreResult(p, made))
        raise
    return StoreResult(p, made)


def undo_store(result):
    """store を戻す（作った写しを消し、ファイルを読込フォルダへ戻す）。記録を書き込めなかったときに使う。"""
    problems = []
    for link in result.made:
        try:
            _retry(lambda: os.unlink(link.path))
        except OSError as e:
            problems.append(f"{link.path}：{e}")
    try:
        move_file(result.plan.target, result.plan.source)
    except (OSError, StoringError) as e:
        problems.append(f"{result.plan.target} を {result.plan.source} へ戻せませんでした：{e}")
    if problems:
        raise StoringError("戻しきれなかったものがあります。手で直してください。\n" + "\n".join(problems))


# ---------------------------------------------------------------- 元に戻す（保管の取り消し）

@dataclass
class RestorePlan:
    stored: Path       # いまの保管ファイル
    back: Path         # 戻す先（読込フォルダ・読込ファイル名）
    links: list = field(default_factory=list)   # 消す写し（あるものだけ）
    missing: list = field(default_factory=list)  # 見つからなかった写し（知らせるだけ）


def plan_restore(stored, back, targets, specials, *, resolve, file_name):
    """元に戻す計画（現行の RstrFile ほか）。保管ファイルと戻す先は必ず確かめる。写しは、あるものだけ消す
    （現行は、写しが1つ見つからないと、そこで止まった）。"""
    stored, back = Path(stored), Path(back)
    if not stored.is_file():
        raise StoringError(f"{stored} が見つかりません。")
    if not back.parent.is_dir():
        raise StoringError(f"{back.parent} が見つかりません（読込フォルダ）。\n（フォルダは作りません。）")
    if back.exists():
        raise StoringError(f"{back} と同じ名前のファイルが既にあります。")
    p = RestorePlan(stored, back)
    for kind, value in list(targets) + [("特別な写し", v) for _, v in specials]:
        if kind == KIND_SHORTCUT and not shortcut.available():
            continue
        folder = resolve(value)
        if folder is None:
            p.missing.append(f"{value}（この PC の場所として読めません）")
            continue
        path = link_path(kind, folder, file_name)
        if path.exists():
            p.links.append(Link(kind, folder, path, value))
        else:
            p.missing.append(str(path))
    return p


def restore(p):
    """写しを消し、ファイルを読込フォルダへ戻す。→ 消した写し（Link）の並び。"""
    move_file(p.stored, p.back)
    removed = []
    failed = []
    for link in p.links:
        try:
            _retry(lambda: os.unlink(link.path))
            removed.append(link)
        except OSError as e:
            failed.append(f"{link.path}：{e}")
    if failed:
        p.missing += [f"消せなかった：{x}" for x in failed]
    return removed


def redo_restore(p, removed):
    """restore を戻す（記録を書き込めなかったとき）：ファイルを保管フォルダへ戻し、消した写しを作り直す。"""
    move_file(p.back, p.stored)
    for link in removed:
        try:
            make_link(link, p.stored)
        except (OSError, StoringError):
            pass
