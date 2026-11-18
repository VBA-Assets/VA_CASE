"""VA Case の共有データの中身と、事件の扱い（画面に依らない部分）。

現行の事件データベース VerA05（`..\\..\\VA事件データベースシリーズ\\VA事件データベース\\sht11.bas` ほか）の動きを写す。共有データ（VA_Case.json）には、
次の3つのテーブルを持つ（ツールごとに1ファイル。2026-11-09 班長決定）。

- 事件：現行の「事件」テーブルと同じ32列
- 選択肢：現行の「オプション」シートのリスト（現況区分・受任区分・事件区分・担当区分・依頼人立場）。事務所で1つ
- フォルダ規則：現行の「フォルダ」シート（現況・受任区分・事件区分ごとの、データフォルダの置き場所）。事務所で1つ
"""
import unicodedata
from dataclasses import dataclass
from datetime import date

from ..common.dates import parse_date
from ..common.master import Table
from ..common.paths import resolve_folder as _resolve_folder

TOOL = "VA Case"
MASTER_FILE_NAME = "VA_Case.json"

CASE = "事件"
CHOICES = "選択肢"
FOLDER_RULES = "フォルダ規則"
COURTS = "裁判所"            # 裁判所の電話番号・FAX番号（2026-11-11 班長決定。事件メモと送付書に使う）

CASE_COLUMNS = [
    "事件番号", "現況", "事件呼名", "依頼者氏名", "ふりがな", "生年月日", "住所", "電話番号", "メールアドレス",
    "相談内容", "相談年月日", "相談弁護士", "関係者", "相手方氏名", "相手方ふりがな", "相手方住所", "相手方電話番号",
    "受任区分", "事件区分", "担当区分", "データフォルダ", "TeamsURL", "終了年月日", "代理人", "代理人住所",
    "代理人電話番号", "代理人FAX番号", "裁判所名", "裁判所事件番号", "事件名", "依頼人立場", "備考",
]
CHOICE_COLUMNS = ["項目", "値", "詳細"]
FOLDER_RULE_COLUMNS = ["現況", "受任区分", "事件区分", "担当区分", "フォルダ"]
COURT_COLUMNS = ["裁判所名", "電話番号", "FAX番号"]

# 「裁判所」は 2026-11-11 に足した。それより前に作った共有データは、テーブルが足りないので読めない（班長のほかに
# まだ使っている人がいないため、前の形を読む仕組みは作らない。同日 班長）
SCHEMA = {CASE: CASE_COLUMNS, CHOICES: CHOICE_COLUMNS, FOLDER_RULES: FOLDER_RULE_COLUMNS, COURTS: COURT_COLUMNS}

DATE_COLUMNS = ("生年月日", "相談年月日", "終了年月日")
# 1行に1つずつ、何人かの日付を入れられる日付の列（2026-11-12 班長指摘「依頼者が２人居て、それぞれの生年月日を入力
# したい場合がある」。同日 班長決定「1行の高さで直す」。依頼者氏名と同じ順に並べる。行ごとに日付として読む）
MULTI_DATE_COLUMNS = ("生年月日",)
# 1つの欄に、改行で区切って複数の値を入れる列（現行と同じ。事件メモはこれを1行ずつに分けて書く）
MULTI_LINE_COLUMNS = ("依頼者氏名", "ふりがな", "生年月日", "住所", "電話番号", "メールアドレス", "相談内容", "関係者",
                      "相手方氏名", "相手方ふりがな", "相手方住所", "相手方電話番号", "代理人", "代理人住所",
                      "代理人電話番号", "代理人FAX番号", "備考")

# 選択肢の項目と、それを選ぶ列（現行の SetColumnValidation と同じ。相談弁護士は担当区分から選ぶ）
CHOICE_ITEMS = ("現況区分", "受任区分", "事件区分", "担当区分", "依頼人立場")
CHOICE_FOR_COLUMN = {"現況": "現況区分", "受任区分": "受任区分", "事件区分": "事件区分",
                     "担当区分": "担当区分", "相談弁護士": "担当区分", "依頼人立場": "依頼人立場"}

# 現況の値（現行のコードに書かれた値。色分けと終了処理に使う）
STATUS_SETTLEMENT = "B:精算管理"
STATUS_CLOSED = "C:終了"
STATUS_CONSULT_ONLY = "D:相談のみ"
STATUS_REFUSED = "E:相談不可"
MOVE_STATUSES = (STATUS_CLOSED, STATUS_SETTLEMENT)   # 現況をこれにすると、データフォルダの終了処理をする

# 新しく共有データを作るときの選択肢（現行の配布版の「オプション」シートの既定。担当区分は事務所ごとに入れる）
DEFAULT_CHOICES = (
    [("現況区分", v, "") for v in ("A:未了", "B:精算管理", "C:終了", "D:相談のみ", "E:相談不可")]
    + [("受任区分", "A:事務所", "")]
    + [("事件区分", v, "") for v in ("A:管財", "B:個人一般", "C:個人債務", "D:企業", "E:顧問")]
    + [("依頼人立場", v, "") for v in ("原告", "被告", "申立人", "相手方", "債権者", "債務者", "控訴人", "被控訴人",
                                       "本人", "被相続人", "破産者", "被保佐人", "被後見人", "審査請求人", "請求者",
                                       "申述人", "被疑者")]
)


def empty_tables():
    return {
        CASE: Table(list(CASE_COLUMNS), []),
        CHOICES: Table(list(CHOICE_COLUMNS), [list(r) for r in DEFAULT_CHOICES]),
        FOLDER_RULES: Table(list(FOLDER_RULE_COLUMNS), []),
        COURTS: Table(list(COURT_COLUMNS), []),
    }


def court_numbers(tables, court_name):
    """裁判所名に当たる (電話番号, FAX番号)。登録がなければ ("", "")。

    裁判所名の欄が何行かある（控訴審などで下に足していく）ときは、最後の行（今の裁判所）で探す。空白の違いは無視する。
    """
    lines = [x.strip() for x in str(court_name or "").split("\n") if x.strip()]
    if not lines or COURTS not in tables:
        return "", ""
    key = "".join(lines[-1].split())
    for name, tel, fax in tables[COURTS].rows:
        if "".join(str(name).split()) == key:
            return tel, fax
    return "", ""


# ---------------------------------------------------------------- 事件

COL = {name: i for i, name in enumerate(CASE_COLUMNS)}


def case_number(row):
    """事件番号（整数）。数でなければ None。"""
    try:
        return int(row[COL["事件番号"]].strip())
    except (ValueError, AttributeError):
        return None


def new_case_number(rows, base_row=None):
    """新しい事件番号（現行の InsertCase）。

    base_row が None：新規の依頼人。最大の番号を100で割った整数部×100＋101（例：最大が 1234 なら 1301）。
    base_row があるとき：その依頼人の追加の事件。番号を100で割った整数部が同じ事件のうち、最大の番号＋1。
    """
    numbers = [n for n in (case_number(r) for r in rows) if n is not None]
    if base_row is None:
        top = max(numbers, default=0)
        return top // 100 * 100 + 101
    base = case_number(base_row)
    if base is None:
        raise ValueError("元の事件の事件番号が数ではありません。")
    client = base // 100
    return max([n for n in numbers if n // 100 == client] + [base]) + 1


def _text_key(v):
    # Excel の並べ替えと同じく、空は最後にする
    return (v == "", v)


def sort_key(row):
    """並べ替えの順（現行の SortTable）：現況・受任区分・事件区分・事件番号の昇順。"""
    n = case_number(row)
    return (_text_key(row[COL["現況"]]), _text_key(row[COL["受任区分"]]), _text_key(row[COL["事件区分"]]),
            (n is None, n if n is not None else 0, row[COL["事件番号"]]))


def sorted_rows(rows):
    return sorted(rows, key=sort_key)


def status_kind(row):
    """色分けの種類（現行の ApplyStatusColor）："closed"・"consult"・"refused"・""。"""
    return {STATUS_CLOSED: "closed", STATUS_CONSULT_ONLY: "consult", STATUS_REFUSED: "refused"}.get(
        row[COL["現況"]], "")


# 同じ依頼人の新しい事件で、選んでいる事件から写す列（2026-11-12 班長決定。依頼者の6列と、関係者・相手方・代理人。
# 調停の後の訴訟など、同じ争いの続きで入れ直さずに済むように。事件呼名・日付・区分・データフォルダなど、事件ごとに
# 違う値や新しく決める値は写さない。現行は番号を付けるだけだった）
SAME_CLIENT_COLUMNS = ("依頼者氏名", "ふりがな", "生年月日", "住所", "電話番号", "メールアドレス", "関係者",
                       "相手方氏名", "相手方ふりがな", "相手方住所", "相手方電話番号",
                       "代理人", "代理人住所", "代理人電話番号", "代理人FAX番号")


def blank_row(number, base_row=None):
    """新しい事件の行。base_row（同じ依頼人の事件）があれば、SAME_CLIENT_COLUMNS の値を写す。"""
    row = [""] * len(CASE_COLUMNS)
    row[COL["事件番号"]] = str(number)
    if base_row is not None:
        for c in SAME_CLIENT_COLUMNS:
            row[COL[c]] = base_row[COL[c]]
    return row


# ---------------------------------------------------------------- 確認（オプションの「コマンド」）

@dataclass
class Problem:
    number: str       # 事件番号（そのまま）
    message: str


# 現行の CheckNumbers（事件番号の重複・空白の確認）は作らない（2026-11-11 班長決定。共有データの中では起きないため）


def check_folders(rows, resolve):
    """データフォルダが見つからない事件を挙げる（現行の CheckFolders）。resolve：欄の値 → Path（なければ None）。"""
    problems = []
    for r in rows:
        value = r[COL["データフォルダ"]]
        if not value:
            continue
        path = resolve(value)
        if path is None or not path.is_dir():
            problems.append(Problem(r[COL["事件番号"]], f"データフォルダが見つかりません：{value}"))
    return problems


def check_row(row, choices):
    """入力欄の OK のときに確かめること。問題の文の一覧を返す（空なら問題なし）。"""
    msgs = []
    if case_number(row) is None:
        msgs.append("事件番号は数で入れてください。")
    for col in DATE_COLUMNS:
        v = row[COL[col]]
        values = [s for s in v.split("\n") if s.strip()] if col in MULTI_DATE_COLUMNS else [v] if v else []
        bad = [s for s in values if parse_date(s) is None]
        if bad:
            msgs.append(f"「{col}」を日付として読めません：{'・'.join(bad)}")
    return msgs


# ---------------------------------------------------------------- 選択肢

def choice_values(choice_table, item):
    return [r[1] for r in choice_table.rows if r[0] == item and r[1]]


def choice_detail(choice_table, item, value):
    for r in choice_table.rows:
        if r[0] == item and r[1] == value:
            return r[2]
    return ""


# ---------------------------------------------------------------- フォルダ規則（現行の MoveFolder の前半）

def find_folder_rule(rules_table, row):
    """現況・受任区分・事件区分が一致する規則の「フォルダ」。なければ None。"""
    for r in rules_table.rows:
        if (r[0] == row[COL["現況"]] and r[1] == row[COL["受任区分"]] and r[2] == row[COL["事件区分"]]):
            return r[4]
    return None


def end_year_text(row):
    """終了年（現行と同じく、2017年以前は「-2017」にまとめる）。終了年月日がなければ今年。"""
    from datetime import date
    d = parse_date(row[COL["終了年月日"]]) or date.today()
    return "-2017" if d.year <= 2017 else str(d.year)


def apply_year(folder, year_text):
    """規則のフォルダの「yyyy」を終了年に置き換える。"""
    return folder.replace("yyyy", year_text)


# ---------------------------------------------------------------- 共有データの書き替え（画面から使う。元の tables は変えない）

def _copy(tables):
    return {k: v.copy() for k, v in tables.items()}


def upsert_case(tables, row, old_number=None):
    """事件を1件入れる。old_number（直す前の事件番号）が与えられればその行を置き換え、なければ足す。並べ替えて返す。"""
    row = list(row)
    if len(row) != len(CASE_COLUMNS):
        raise ValueError("事件の列の数が違います。")
    new = _copy(tables)
    rows = new[CASE].rows
    number = row[COL["事件番号"]].strip()
    row[COL["事件番号"]] = number
    key = old_number if old_number is not None else number
    hit = [i for i, r in enumerate(rows) if r[COL["事件番号"]] == key]
    clash = [r for r in rows if r[COL["事件番号"]] == number and r[COL["事件番号"]] != key]
    if clash:
        raise ValueError(f"事件番号 {number} は、すでにあります（{clash[0][COL['事件呼名']]}）。")
    if old_number is not None and not hit:
        raise ValueError(f"事件番号 {old_number} の事件が、共有データにありません（ほかの人が消した可能性があります）。")
    if old_number is None and hit:
        raise ValueError(f"事件番号 {number} は、すでにあります（{rows[hit[0]][COL['事件呼名']]}）。")
    if hit:
        rows[hit[0]] = row
    else:
        rows.append(row)
    new[CASE].rows = sorted_rows(rows)
    return new


def delete_case(tables, number):
    new = _copy(tables)
    before = len(new[CASE].rows)
    new[CASE].rows = [r for r in new[CASE].rows if r[COL["事件番号"]] != number]
    if len(new[CASE].rows) == before:
        raise ValueError(f"事件番号 {number} の事件が、共有データにありません。")
    return new


# 代理人から引いて入れる列（2026-11-09 班長指示「代理人が入力されたら、代理人の住所、電話番号、FAX番号を入れる」）
AGENT_DETAIL_COLUMNS = ("代理人住所", "代理人電話番号", "代理人FAX番号")


def _name_key(text):
    """代理人の名前を比べる形（全角・半角、大文字・小文字と、前後の空白を問わない）。"""
    return unicodedata.normalize("NFKC", text).casefold().strip()


def _lines(value):
    return value.strip("\n").split("\n") if value.strip() else []


def _detail_for(value, agents, index):
    """ある事件の代理人住所などの値のうち、index 番目の代理人のもの（決められなければ空）。

    代理人が1人なら、値の全体（住所が2行にわたるときも、そのまま）。何人かなら、値の行の数が代理人の数と同じときは
    同じ行のもの、値が1行だけなら、皆に共通のものとしてその行。それ以外は、どの行が誰のものか決められないので空。
    """
    lines = _lines(value)
    if not lines:
        return ""
    if len(agents) == 1:
        return value.strip()
    if len(lines) == len(agents):
        return lines[index].strip()
    if len(lines) == 1:
        return lines[0].strip()
    return ""


def agent_details(rows, name, exclude=None):
    """代理人の名前（1人分）から、これまでの事件の代理人住所・代理人電話番号・代理人FAX番号を引く。

    名前が一致する代理人がいる事件のうち、新しい行（共有データで後ろにある行）から探し、列ごとに、最初に見つかった
    空でない値を使う。exclude の事件番号の事件（いま直している事件）は除く。{列の名前: 値} を返す（ないものは入れない）。
    """
    key = _name_key(name)
    if not key:
        return {}
    found = {}
    for row in reversed(rows):
        if exclude and row[COL["事件番号"]] == exclude:
            continue
        agents = _lines(row[COL["代理人"]])
        index = next((j for j, a in enumerate(agents) if _name_key(a) == key), None)
        if index is None:
            continue
        for col in AGENT_DETAIL_COLUMNS:
            if col not in found:
                v = _detail_for(row[COL[col]], agents, index)
                if v:
                    found[col] = v
        if len(found) == len(AGENT_DETAIL_COLUMNS):
            break
    return found


def add_imported(tables, rows):
    """CSV から読んだ事件を足す。事件番号が数でない・重複する（共有データの中・CSV の中）ものがあれば、何も足さずに
    ValueError（問題をすべて挙げる）。"""
    existing = {case_number(r) for r in tables[CASE].rows}
    problems, seen = [], set()
    for i, r in enumerate(rows, start=1):
        n = case_number(r)
        name = r[COL["事件呼名"]]
        if n is None or n == 0:
            problems.append(f"{i} 件目（{name}）：事件番号が空白か、数ではありません（{r[COL['事件番号']]}）。")
        elif n in existing:
            problems.append(f"{i} 件目（{name}）：事件番号 {n} は、すでに共有データにあります。")
        elif n in seen:
            problems.append(f"{i} 件目（{name}）：事件番号 {n} が、CSV の中で重複しています。")
        seen.add(n)
    if problems:
        raise ValueError("\n".join(problems))
    new = _copy(tables)
    new[CASE].rows = sorted_rows(new[CASE].rows + [list(r) for r in rows])
    return new


# データフォルダの値を、この PC のパスにする（共通部品。VA Filing でも使う）
resolve_folder = _resolve_folder


# ---------------------------------------------------------------- 書類の PDF の名前

# ファイル名に使えない字は、全角に置き換える
_FILE_NAME_CHARS = str.maketrans({"\\": "＼", "/": "／", ":": "：", "*": "＊", "?": "？", '"': "＂", "<": "＜",
                                  ">": "＞", "|": "｜"})


def document_file_name(kind, row, day=None):
    """書類（事件メモ・期日請書・送付書）の PDF の名前「yyyymmdd_書類_事件呼名.pdf」（例：20261113_事件メモ_甲野太郎（貸金）.pdf）。

    2026-11-13 班長決定（班長の問い「事件メモのファイル名に事件呼名を付け加えれば、根本的に解決できるのではないか？」）。
    それまでは現行と同じ「事件メモ20261113.pdf」で、データフォルダをほかの事件と共有していると（依頼人ごとのフォルダ
    など）、同じ日に作ったほかの事件の書類と同じ名前になり、「置き換えますか？」で上書きできてしまった。事件呼名の
    ファイル名に使えない字は全角にする。事件呼名が空なら事件番号を使う。
    """
    name = "".join(ch for ch in (row[COL["事件呼名"]] or "").translate(_FILE_NAME_CHARS) if ord(ch) >= 32)
    name = name.strip().rstrip(".").strip() or row[COL["事件番号"]]
    return f"{(day or date.today()):%Y%m%d}_{kind}_{name}.pdf"
