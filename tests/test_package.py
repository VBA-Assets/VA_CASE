"""パッケージが読み込めることを確かめる（土台の確認）。"""
import va_case
import va_case.common


def test_import():
    assert va_case.SERIES_NAME == "VA Caseシリーズ"
