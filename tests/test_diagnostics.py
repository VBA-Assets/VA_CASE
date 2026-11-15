"""診断情報（仕様.md の 6.5。2026-11-11）の試験：中身（値・場所・名前・例外のメッセージ）が入らないこと。氏名は架空。"""
import json
import time

from va_case.common import diagnostics as d
from va_case.common.master import Table
from va_case.common.ui.background import Background


def _raise(exc):
    try:
        raise exc
    except Exception as e:
        return e


def test_record_has_type_and_place_but_no_message(tmp_path):
    path = tmp_path / "事件" / "102甲野太郎"
    e = _raise(FileNotFoundError(2, "見つかりません", str(path)))
    r = d.exception_record(e, "読み込み")
    text = json.dumps(r, ensure_ascii=False)
    assert r["type"] == "FileNotFoundError" and r["errno"] == 2 and r["stage"] == "読み込み"
    assert r["where"] and r["where"][-1].startswith("test_diagnostics.py:")       # ファイル名だけ（フォルダは出さない）
    assert "甲野太郎" not in text and str(tmp_path) not in text and "見つかりません" not in text


def test_error_log_keeps_the_latest_and_survives_restart(tmp_path):
    path = tmp_path / "case_errors.json"
    log = d.ErrorLog("case", path)
    for i in range(d.KEEP_ERRORS + 5):
        log.record(_raise(ValueError(f"乙山次郎 {i}")), "書き込み")
    again = d.ErrorLog("case", path)                       # 閉じた後に開き直しても残る
    assert len(again.records) == d.KEEP_ERRORS
    assert "乙山次郎" not in path.read_text(encoding="utf-8")
    again.clear()
    assert not path.exists() and d.ErrorLog("case", path).records == []


def test_error_log_never_raises_when_it_cannot_write(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    log = d.ErrorLog("case", blocker / "sub" / "case_errors.json")   # ファイルの下にフォルダは作れない
    log.record(_raise(KeyError("x")))
    assert len(log.records) == 1


def test_table_lines_have_counts_and_lengths_but_no_values():
    tables = {"事件": Table(["番号", "相手方氏名"], [["1", "乙山次郎\n丙川三郎"], ["2", ""]]),
              "余計": Table(["秘密"], [["丁原四郎"]])}
    schema = {"事件": ["番号", "相手方氏名"]}
    text = "\n".join(d.table_lines(tables, schema))
    assert "[事件] 2 行・2 列（列は既定どおり）" in text
    assert "相手方氏名：空でない 1・最長 9 字・改行あり 1" in text
    assert "既定にないテーブル" in text and "（既定にない列 1）" in text
    for name in ("乙山次郎", "丙川三郎", "丁原四郎", "余計", "秘密"):
        assert name not in text


def test_file_lines_do_not_show_the_place(tmp_path):
    f = tmp_path / "102甲野太郎" / "VA_Case.json"
    f.parent.mkdir()
    f.write_text("{}", encoding="utf-8")
    for line in d.file_lines("共有データ", f) + d.file_lines("移送待ち", tmp_path / "ない") + d.file_lines("x", ""):
        assert "甲野太郎" not in line and str(tmp_path) not in line and "VA_Case.json" not in line
    assert d.file_lines("共有データ", f)[0].startswith("共有データ：ある（2 バイト")


def test_background_reports_errors(tmp_path):
    class FakeRoot:
        def after(self, ms, func):
            pass
    got = []
    bg = Background(FakeRoot(), on_exception=lambda e, stage: got.append((type(e).__name__, stage)))

    def failing():
        raise OSError("場所")
    bg.run(failing)
    for _ in range(100):
        if got:
            break
        time.sleep(0.01)
    assert got == [("OSError", "test_background_reports_errors.<locals>.failing")]


def test_about_text_has_license():
    """「について」に、版・1行の説明・MIT License を出す（2026-11-14 班長決定「MIT License」）。"""
    from va_case.call.app import CallApp
    from va_case.case.app import CaseApp
    from va_case.filing.app import FilingApp
    from va_case.receipt.app import ReceiptApp
    for cls in (CaseApp, FilingApp, ReceiptApp, CallApp):
        app = cls.__new__(cls)
        text = app.about_text()
        assert text.startswith(f"{cls.TITLE}  Ver102\n") and cls.ABOUT_LINE and cls.ABOUT_LINE in text
        # VA FAX と同じ形（2026-11-14 班長指示「「について」の表示内容をVA FAXに合わせる。」）
        assert text == f"{cls.TITLE}  Ver102\n{cls.ABOUT_LINE}\n\nVBAアセット（vba-assets.net）\nMIT License"
