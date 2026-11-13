"""試用の共有フォルダを作る（架空の事件・データフォルダ・移送待ち・保管庫・バックアップ）。

使い方：python scripts\\make_trial.py [作る場所（既定は 作業フォルダ\\試験用）]
氏名・住所・番号はすべて架空。すでにあれば作り直さない（消してから実行する）。
最後に、この PC の VA Case の設定（%APPDATA%\\VA Case\\case.json）を試用の場所に向けるかを尋ねる。

事件は、下の CASES の6件に、自動で作る架空の事件を足して、TRIAL_TOTAL 件（100件）にする（2026-11-10 班長指示
「VA CASE のサンプルデータを100件程度まで増加」。一覧の折り返し・検索・並べ替えなどを、件数のある状態で試すため）。

すでにある試用の共有データの事件を増やすとき：python scripts\\make_trial.py --fill [件数（既定は TRIAL_TOTAL）]
いまある事件は変えず、足りない分だけ足す。共有データの書き込みの決まり（ロック・競合の確認）を通して書くので、
ほかの人（VA Case の画面を含む）が編集モードのときは、書かずに止まる。

事件番号の付け方を確かめる見本を10件足すとき：python scripts\\make_trial.py --add10 [試用の場所]
（2026-11-13 班長指示「新しい番号の付け方を確認するため、各ツール用のサンプルデータを10件ずつ作成」。今年の新しい依頼人と、
いまある依頼人の追加の事件を、VA Case の画面と同じ決まりで足す。）

事件番号は、年（西暦の下2桁）・依頼人（3桁）・事件（2桁）の7桁（例：2500101。2026-11-13 班長「その7桁だ」）。データ
フォルダの名前は事件呼名（2026-11-13 班長指示「データフォルダの名前は事件呼名とする」）。
"""
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from va_case.case import courtdocs as cd  # noqa: E402
from va_case.case import model as m  # noqa: E402
from va_case.case import settings  # noqa: E402
from va_case.common.identity import Identity  # noqa: E402
from va_case.common.master import create_master  # noqa: E402

CASES = [
    dict(事件番号="2500101", 現況="A:未了", 事件呼名="甲野太郎（貸金）", 依頼者氏名="甲野太郎", ふりがな="こうのたろう",
         生年月日="1980-04-01", 住所="東京都千代田区霞が関一丁目1番1号", 電話番号="03-0000-0001",
         相談年月日="2025-04-10", 相談弁護士="佐", 相手方氏名="乙山次郎\n丙川三郎", 相手方ふりがな="おつやまじろう\nへいかわさぶろう",
         相手方住所="大阪府大阪市北区一丁目2番3号\n神奈川県横浜市中区四丁目5番6号", 受任区分="A:事務所", 事件区分="B:個人一般",
         担当区分="佐", 代理人="弁護士 己野六郎", 代理人住所="大阪府大阪市中央区一丁目1番1号", 代理人電話番号="06-1111-1111",
         代理人FAX番号="06-1111-1112", 裁判所名="東京地方裁判所", 裁判所事件番号="令和7年(ワ)第1234号", 事件名="貸金返還請求事件",
         依頼人立場="原告"),
    dict(事件番号="2500102", 現況="A:未了", 事件呼名="甲野太郎（建物明渡）", 依頼者氏名="甲野太郎", ふりがな="こうのたろう",
         受任区分="A:事務所", 事件区分="B:個人一般", 担当区分="佐・田", 相手方氏名="庚田七郎", 依頼人立場="原告",
         裁判所名="東京地方裁判所", 裁判所事件番号="令和7年(ワ)第2345号", 事件名="建物明渡請求事件"),
    dict(事件番号="2500201", 現況="A:未了", 事件呼名="辛川花子（自己破産）", 依頼者氏名="辛川花子", ふりがな="からかわはなこ",
         受任区分="A:事務所", 事件区分="C:個人債務", 担当区分="田", 依頼人立場="破産者", 裁判所名="東京地方裁判所",
         裁判所事件番号="令和7年(フ)第100号", 事件名="破産手続開始申立事件"),
    dict(事件番号="2500301", 現況="D:相談のみ", 事件呼名="壬野四郎（相続の相談）", 依頼者氏名="壬野四郎",
         相談年月日="2025-06-01", 相談内容="父の相続について", 相談弁護士="佐"),
    dict(事件番号="2500401", 現況="C:終了", 事件呼名="癸山五郎（交通事故）", 依頼者氏名="癸山五郎", 受任区分="A:事務所",
         事件区分="B:個人一般", 担当区分="田", 終了年月日="2024-03-31",
         データフォルダ="保管庫：個人一般/2024/癸山五郎（交通事故）.zip"),
    dict(事件番号="2500501", 現況="E:相談不可", 事件呼名="子田六子（利益相反）", 依頼者氏名="子田六子"),
]


TRIAL_TOTAL = 100
SEED = 20261110   # 毎回、同じ事件ができるように

# 架空の氏名（姓・名とその読み）。実在の人とは関係がない
SURNAMES = [("青木", "あおき"), ("石川", "いしかわ"), ("上田", "うえだ"), ("遠藤", "えんどう"), ("大野", "おおの"),
            ("加藤", "かとう"), ("北村", "きたむら"), ("久保", "くぼ"), ("小松", "こまつ"), ("斎藤", "さいとう"),
            ("柴田", "しばた"), ("杉山", "すぎやま"), ("関口", "せきぐち"), ("高木", "たかぎ"), ("千葉", "ちば"),
            ("土屋", "つちや"), ("中島", "なかじま"), ("西田", "にしだ"), ("野村", "のむら"), ("橋本", "はしもと"),
            ("平野", "ひらの"), ("福田", "ふくだ"), ("堀内", "ほりうち"), ("松本", "まつもと"), ("宮崎", "みやざき"),
            ("村上", "むらかみ"), ("森田", "もりた"), ("山口", "やまぐち"), ("吉川", "よしかわ"), ("渡部", "わたなべ")]
GIVEN = [("一郎", "いちろう"), ("健太", "けんた"), ("誠", "まこと"), ("浩二", "こうじ"), ("大輔", "だいすけ"),
         ("翔太", "しょうた"), ("直樹", "なおき"), ("隆", "たかし"), ("恵子", "けいこ"), ("裕子", "ゆうこ"),
         ("美穂", "みほ"), ("陽子", "ようこ"), ("真理", "まり"), ("さくら", "さくら"), ("由美", "ゆみ"),
         ("和也", "かずや"), ("拓也", "たくや"), ("聡", "さとし"), ("明美", "あけみ"), ("千尋", "ちひろ")]
COMPANIES = ["株式会社青葉商事", "株式会社みどり建設", "有限会社さくら運送", "株式会社東西ファイナンス",
             "合同会社ひかり企画", "株式会社北斗システム", "医療法人社団あおぞら会", "株式会社なごみ不動産"]
PLACES = ["東京都新宿区西新宿", "東京都世田谷区三軒茶屋", "東京都練馬区豊玉北", "神奈川県川崎市中原区小杉町",
          "神奈川県横浜市港北区新横浜", "埼玉県さいたま市浦和区高砂", "千葉県船橋市本町", "東京都八王子市旭町",
          "埼玉県川口市本町", "千葉県千葉市中央区富士見", "東京都江東区豊洲", "東京都立川市曙町"]
KANJI_NUM = "一二三四五"
# 相手方の代理人（何件かで同じ人が出る。代理人の住所などを補う機能を試せるように）
AGENTS = [("弁護士 戸田修", "東京都中央区銀座一丁目2番3号", "03-0000-2001", "03-0000-2002"),
          ("弁護士 長谷川京子", "東京都港区虎ノ門二丁目4番1号", "03-0000-2101", "03-0000-2102"),
          ("弁護士 岡本健", "神奈川県横浜市中区日本大通5番", "045-000-2201", "045-000-2202"),
          ("弁護士 三浦礼子", "埼玉県さいたま市浦和区高砂三丁目1番", "048-000-2301", "048-000-2302"),
          ("弁護士 西村大和", "東京都千代田区丸の内一丁目6番5号", "03-0000-2401", "03-0000-2402")]
# 事件の種類：(事件区分, 呼名に付ける語, 事件名, 裁判所の種類, 符号, 依頼人立場の候補, 相手方を置くか)
KINDS = [
    ("B:個人一般", "貸金", "貸金返還請求事件", "地方", "ワ", ["原告", "被告"], True),
    ("B:個人一般", "損害賠償", "損害賠償請求事件", "地方", "ワ", ["原告", "被告"], True),
    ("B:個人一般", "交通事故", "損害賠償請求事件", "地方", "ワ", ["原告", "被告"], True),
    ("B:個人一般", "建物明渡", "建物明渡請求事件", "地方", "ワ", ["原告", "被告"], True),
    ("B:個人一般", "離婚", "夫婦関係調整調停申立事件", "家庭", "家イ", ["申立人", "相手方"], True),
    ("B:個人一般", "遺産分割", "遺産分割調停申立事件", "家庭", "家イ", ["申立人", "相手方"], True),
    ("B:個人一般", "労働", "労働審判事件", "地方", "労", ["申立人"], True),
    ("B:個人一般", "後見", "後見開始の審判申立事件", "家庭", "家", ["申立人"], False),
    ("C:個人債務", "自己破産", "破産手続開始申立事件", "地方", "フ", ["破産者"], False),
    ("C:個人債務", "個人再生", "小規模個人再生申立事件", "地方", "再イ", ["申立人"], False),
    ("C:個人債務", "任意整理", "", "", "", [], False),
    ("D:企業", "売掛金", "売買代金請求事件", "地方", "ワ", ["原告"], True),
    ("D:企業", "契約", "", "", "", [], True),
    ("E:顧問", "顧問", "", "", "", [], False),
]
COURTS = {"地方": ["東京地方裁判所", "東京地方裁判所立川支部", "横浜地方裁判所", "さいたま地方裁判所", "千葉地方裁判所"],
          "家庭": ["東京家庭裁判所", "横浜家庭裁判所", "さいたま家庭裁判所"]}


def trial_courts():
    """事務所の設定の「裁判所」の試用の行（番号は架空。0000 を入れて、実在の番号と紛れないようにする）。
    最後の裁判所は、登録のない場合を試せるよう、入れない。"""
    names = COURTS["地方"] + COURTS["家庭"]
    return [[name, f"03-0000-{2001 + i}", f"03-0000-{3001 + i}"] for i, name in enumerate(names[:-1])]


STATUSES = (["A:未了", "B:精算管理", "C:終了", "D:相談のみ", "E:相談不可"], [50, 8, 27, 11, 4])


def _person(rnd):
    (s, sr), (g, gr) = rnd.choice(SURNAMES), rnd.choice(GIVEN)
    return s + g, sr + gr


def _address(rnd):
    return f"{rnd.choice(PLACES)}{rnd.choice(KANJI_NUM)}丁目{rnd.randint(1, 30)}番{rnd.randint(1, 20)}号"


def _phone(rnd, mobile=False):
    return f"090-0000-{rnd.randint(0, 9999):04d}" if mobile else f"03-0000-{rnd.randint(3000, 9999):04d}"


LAST_DAY = "2026-11-10"   # 相談年月日・終了年月日は、この日まで（作った日。未来の日付にしない）


def _date(rnd, start, end):
    """start〜end（"YYYY-MM-DD"）の日付を1つ。"""
    from datetime import date, timedelta
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    return (a + timedelta(days=rnd.randint(0, (b - a).days))).isoformat()


def new_client_number(rows, year):
    """その年の新しい依頼人の事件番号（年2桁＋その年の依頼人の連番3桁＋01）。year：西暦（4桁）。

    VA Case の画面は年を見ず、いまの最大の番号の次の依頼人を付ける（年が替わったら、最初の依頼人だけ人が直す）。
    試用の事件は、相談年月日の年で振る（人が直した後と同じ形にする）。"""
    yy = year % 100
    clients = [n // 100 % 1000 for n in (m.case_number(r) for r in rows) if n is not None and n // 100000 == yy]
    return yy * 100000 + (max(clients, default=0) + 1) * 100 + 1


def generated_cases(existing_rows, total=TRIAL_TOTAL, seed=SEED, since="2023-01-01"):
    """架空の事件を作り、existing_rows と合わせて total 件にする（足す行の一覧を返す）。

    事件番号は、新しい依頼人は相談年月日の年の次の依頼人（例：2600101 の次は 2600201）、同じ依頼人の追加の事件は
    VA Case と同じ決まり（2600101 の次は 2600102）。相談年月日は since から LAST_DAY まで。
    現況・事件区分・相手方（2人の事件も）・代理人・裁判所・複数の電話番号など、一覧と入力欄で試したいものが混ざる
    ようにする。
    """
    rnd = random.Random(seed)
    rows = list(existing_rows)
    added = []
    while len(rows) < total:
        company = rnd.random() < 0.15
        name, kana = (rnd.choice(COMPANIES), "") if company else _person(rnd)
        client = {"依頼者氏名": name, "ふりがな": kana, "住所": _address(rnd)}   # 同じ依頼人の事件では同じにする
        if not company:
            client["生年月日"] = _date(rnd, "1950-01-01", "2000-12-31")
        client["電話番号"] = _phone(rnd) if company else "\n".join(
            [_phone(rnd, mobile=True)] + ([_phone(rnd)] if rnd.random() < 0.3 else []))
        first = _date(rnd, since, LAST_DAY)          # 依頼人が初めて相談に来た日（事件番号の年）
        if rnd.random() < 0.4:
            client["メールアドレス"] = f"client{new_client_number(rows, int(first[:4]))}@example.com"
        base = None
        for _ in range(min(rnd.choice([1, 1, 1, 1, 2, 2, 3]), total - len(rows))):
            number = m.new_case_number(rows, base) if base else new_client_number(rows, int(first[:4]))
            row = m.blank_row(number)
            consult = first if base is None else _date(rnd, first, LAST_DAY)
            category, word, case_name, court_kind, mark, sides, has_other = rnd.choice(
                [k for k in KINDS if (k[0] in ("D:企業", "E:顧問")) == company])
            status = rnd.choices(*STATUSES)[0]
            title = f"{name}（{word}{'の相談' if status[0] in 'DE' else ''}）"
            if any(r[m.COL["事件呼名"]] == title for r in rows):
                continue                                  # 同じ事件呼名にしない（データフォルダの名前が重なるため）
            base = base or row
            v = dict(client, 現況=status, 事件呼名=title,
                     相談年月日=consult, 相談弁護士=rnd.choice(["佐", "田"]))
            if status[0] in "DE":
                v["相談内容"] = rnd.choice(["今後の見通しについて", "相手方からの請求書について",
                                         "契約書の内容について", "手続の費用について"])
            else:
                v.update({"受任区分": "A:事務所", "事件区分": category, "担当区分": rnd.choice(["佐", "田", "佐・田"])})
                if has_other:
                    others = [_person(rnd) for _ in range(rnd.choice([1, 1, 1, 2]))]
                    v["相手方氏名"] = "\n".join(o[0] for o in others)
                    v["相手方ふりがな"] = "\n".join(o[1] for o in others)
                    v["相手方住所"] = "\n".join(_address(rnd) for _ in others)
                    if rnd.random() < 0.5:
                        v["相手方電話番号"] = _phone(rnd)
                    if rnd.random() < 0.45:
                        v.update(zip(("代理人", "代理人住所", "代理人電話番号", "代理人FAX番号"), rnd.choice(AGENTS)))
                if case_name and rnd.random() < 0.8:
                    v.update({"裁判所名": rnd.choice(COURTS[court_kind]),
                              "裁判所事件番号": f"令和{int(consult[:4]) - 2018}年({mark})第{rnd.randint(100, 9999)}号",
                              "事件名": case_name, "依頼人立場": rnd.choice(sides)})
                if rnd.random() < 0.15:
                    v["関係者"] = "\n".join(_person(rnd)[0] + rnd.choice(["（依頼者の親族）", "（証人）", "（保証人）"])
                                         for _ in range(rnd.choice([1, 2])))
                if status == "C:終了":
                    v["終了年月日"] = _date(rnd, consult, LAST_DAY)
                    if category in ("B:個人一般", "C:個人債務"):
                        v["データフォルダ"] = f"保管庫：{category[2:]}/{v['終了年月日'][:4]}/{title}.zip"
            if rnd.random() < 0.1:
                v["備考"] = rnd.choice(["連絡は夕方以降を希望", "郵送物は事務所留め", "着手金は分割払い"])
            for k, val in v.items():
                row[m.COL[k]] = val
            rows.append(row)
            added.append(row)
    return added


def fill(total, seed=SEED, since="2023-01-01", path=None):
    """すでにある試用の共有データに、架空の事件を足して total 件にする。path：共有データ（既定はこの PC の設定の場所）。"""
    from va_case.common.store import SharedStore
    cfg = settings.load()
    path = path or (Path(cfg.master_path) if cfg.master_path else ROOT / "試験用" / "共有" / m.MASTER_FILE_NAME)
    if "試験用" not in path.parts:   # 試用でない共有データ（事務所の実データ）には書かない
        print(f"試用の共有データではないので、書きません：{path}")
        return
    store = SharedStore(path, m.TOOL, m.SCHEMA, identity=Identity("試用", "試用"))
    tables = store.begin_edit().tables     # ほかの人が編集中なら、ここで止まる
    try:
        rows = tables[m.CASE].rows
        added = generated_cases(rows, total, seed, since)
        tables[m.CASE].rows = m.sorted_rows(rows + added)
        store.save(tables, end_edit=True)
    except BaseException:
        store.end_edit()
        raise
    print(f"事件を {len(added)} 件足して、{len(tables[m.CASE].rows)} 件にしました：{path}")


def add10(base):
    """事件番号の付け方を確かめる見本を10件足す（今年〔2026年〕の相談の、新しい依頼人と追加の事件）。"""
    from va_case.common.master import read_master
    path = base / "共有" / m.MASTER_FILE_NAME
    if "試験用" not in path.parts or not path.exists():
        print(f"試用の共有データがないか、試用でないので、書きません：{path}")
        return
    count = len(read_master(path).tables[m.CASE].rows)
    fill(count + 10, seed=SEED + 1113, since="2026-01-01", path=path)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--fill":
        fill(int(sys.argv[2]) if len(sys.argv) > 2 else TRIAL_TOTAL)
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--add10":
        add10(Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "試験用")
        return
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "試験用"
    if base.exists():
        print(f"すでにあります。作り直すときは、消してから実行してください：{base}")
        return
    shared, cases, outbox, vault, backup = (base / n for n in ("共有", "事件", "移送待ち", "保管庫", "バックアップ"))
    for d in (shared, cases, outbox, vault, backup):
        d.mkdir(parents=True)
    tables = m.empty_tables()
    for spec in CASES:
        row = m.blank_row(spec["事件番号"])
        for k, v in spec.items():
            row[m.COL[k]] = v
        if spec["事件番号"] in ("2500101", "2500102", "2500201"):
            folder = cases / spec["事件呼名"]            # データフォルダの名前は事件呼名
            folder.mkdir()
            (folder / "訴状（架空）.txt").write_text("試用のファイルです。", encoding="utf-8")
            (folder / "書証").mkdir()
            (folder / "書証" / "甲第1号証（架空）.txt").write_text("試用のファイルです。", encoding="utf-8")
            row[m.COL["データフォルダ"]] = str(folder)
        tables[m.CASE].rows.append(row)
    tables[m.CASE].rows += generated_cases(tables[m.CASE].rows)
    tables[m.CASE].rows = m.sorted_rows(tables[m.CASE].rows)
    tables[m.CHOICES].rows += [["担当区分", "佐", "佐藤一郎"], ["担当区分", "田", "田中二郎"],
                               ["担当区分", "佐・田", "佐藤一郎・田中二郎"],
                               [cd.OFFICE_TEL, "03-0000-0000", ""], [cd.OFFICE_FAX, "03-0000-0009", ""]]
    tables[m.COURTS].rows = trial_courts()
    tables[m.FOLDER_RULES].rows = [
        ["C:終了", "A:事務所", "B:個人一般", "", r"個人一般\yyyy"],
        ["C:終了", "A:事務所", "C:個人債務", "", r"個人債務\yyyy"],
        ["B:精算管理", "A:事務所", "B:個人一般", "", r"精算管理\個人一般"],
    ]
    create_master(shared / m.MASTER_FILE_NAME, m.TOOL, tables, Identity("試用", "試用"))
    print(f"試用の共有フォルダを作りました：{base}")
    cfg_path = settings.common_config.config_path(settings.TOOL_KEY)
    ans = input(f"この PC の VA Case の設定（{cfg_path}）を、試用の場所に向けますか？ [y/N] ").strip().lower()
    if ans == "y":
        if cfg_path.exists():
            keep = cfg_path.with_name(cfg_path.stem + "_試用前.json")
            cfg_path.replace(keep)
            print(f"前の設定は {keep} に残しました。")
        cfg = settings.CaseConfig(master_path=str(shared / m.MASTER_FILE_NAME), backup_folder=str(backup),
                                  outbox=str(outbox))
        settings.save(cfg)
        print("設定を書きました。python main_case.py で起動してください。")


if __name__ == "__main__":
    main()
