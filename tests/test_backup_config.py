"""日次バックアップと、この PC の設定の試験。"""
from datetime import date

from conftest import ALICE, SCHEMA, TOOL
from va_case.common import config
from va_case.common.backup import BackupResult, daily_backup
from va_case.common.master import Table, create_master, read_master

DAY = date(2026, 11, 9)


def test_backup_once_a_day(shared, tmp_path):
    folder = tmp_path / "バックアップ"
    folder.mkdir()
    result, path = daily_backup(shared, folder, today=DAY)
    assert result is BackupResult.CREATED and path.name == "20261109_VA_Case.json"
    assert read_master(path).tables == read_master(shared).tables
    assert daily_backup(shared, folder, today=DAY)[0] is BackupResult.EXISTS
    assert daily_backup(shared, folder, today=date(2026, 11, 10))[0] is BackupResult.CREATED


def test_backup_folder_missing_is_not_created(shared, tmp_path):
    folder = tmp_path / "閉じた金庫" / "バックアップ"
    assert daily_backup(shared, folder, today=DAY) == (BackupResult.FOLDER_MISSING, None)
    assert not folder.exists()
    assert daily_backup(shared, "", today=DAY) == (BackupResult.NOT_CONFIGURED, None)


def test_backup_skips_empty(tmp_path):
    shared = tmp_path / "VA_Case.json"
    create_master(shared, TOOL, {"事件": Table(SCHEMA["事件"], [])}, ALICE)
    folder = tmp_path / "b"
    folder.mkdir()
    assert daily_backup(shared, folder, today=DAY)[0] is BackupResult.NO_DATA
    assert list(folder.iterdir()) == []


def test_config_roundtrip_and_defaults(tmp_path):
    path = tmp_path / "設定" / "case.json"
    cfg = config.load("case", path=path)
    assert cfg.master_path == ""
    cfg.master_path = r"S:\共有\VA_Case.json"
    config.save("case", cfg, path=path)
    again = config.load("case", path=path)
    assert again.master_path == r"S:\共有\VA_Case.json"
    assert "sync_wait" not in path.read_text(encoding="utf-8")   # 同期を待つ秒数は、2026-11-11 になくした


def test_config_rejects_bad_values(tmp_path):
    path = tmp_path / "case.json"
    # 前の版の設定ファイルに残った「同期を待つ秒数」（sync_wait）は、ほかの知らない欄と同じく無視する
    path.write_text('{"sync_wait": 3.0, "master_path": 3, "unknown": 1}', encoding="utf-8")
    cfg = config.load("case", path=path)
    assert cfg.master_path == "" and not hasattr(cfg, "sync_wait")
    path.write_text("{壊れた", encoding="utf-8")
    assert config.load("case", path=path).master_path == ""


def test_config_keeps_column_widths(tmp_path):
    """一覧の列の幅を、この PC の設定に覚える（2026-11-09 班長指示）。おかしな値は捨てる。"""
    path = tmp_path / "case.json"
    cfg = config.ToolConfig(column_widths={"住所": 260, "備考": 180})
    config.save("case", cfg, path=path)
    assert config.load("case", path=path).column_widths == {"住所": 260, "備考": 180}
    path.write_text('{"column_widths": {"住所": 260, "備考": "広い", "事件名": 5, "x": true, "y": 99999}}',
                    encoding="utf-8")
    assert config.load("case", path=path).column_widths == {"住所": 260}
    path.write_text('{"column_widths": ["住所", 260]}', encoding="utf-8")
    assert config.load("case", path=path).column_widths == {}
    assert config.ToolConfig().column_widths == {}


def test_config_keeps_office_layout(tmp_path):
    """事務所の設定の画面の大きさと列の幅を、この PC の設定に覚える（2026-11-12 班長指示）。おかしな値は捨てる。"""
    path = tmp_path / "filing.json"
    cfg = config.ToolConfig(office_size="1000x620", office_column_widths={"保管先/保管フォルダ": 500})
    config.save("filing", cfg, path=path)
    got = config.load("filing", path=path)
    assert got.office_size == "1000x620" and got.office_column_widths == {"保管先/保管フォルダ": 500}
    path.write_text('{"office_size": "大きい", "office_column_widths": {"保管先/保管フォルダ": "広い", "a/b": 300}}',
                    encoding="utf-8")
    got = config.load("filing", path=path)
    assert got.office_size == "" and got.office_column_widths == {"a/b": 300}
    path.write_text('{"office_size": "1000x620+30+40"}', encoding="utf-8")   # 位置は覚えない
    assert config.load("filing", path=path).office_size == ""
