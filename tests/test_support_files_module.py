import json
import tempfile
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def fixed_now():
    return datetime(2026, 6, 12, 10, 0, 0)


def test_log_tail_and_payload_metadata_handle_missing_invalid_and_versioned_files():
    from goldmonitor.data_contracts import wrap_item_payload
    from goldmonitor.support_files import json_payload_metadata, read_log_tail

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        missing = tmp / "missing.json"
        assert read_log_tail(str(missing)) == []
        assert json_payload_metadata(str(missing)) == {
            "exists": False,
            "schema_version": 0,
            "expected_schema_version": 1,
            "format": "missing",
            "needs_migration": False,
        }

        log_path = tmp / "app.log"
        log_path.write_text("a\nb\nc\n", encoding="utf-8")
        assert read_log_tail(str(log_path), max_lines=2) == ["b", "c"]

        invalid = tmp / "invalid.json"
        invalid.write_text("{bad", encoding="utf-8")
        assert json_payload_metadata(str(invalid))["format"] == "invalid"
        assert json_payload_metadata(str(invalid))["needs_migration"] is True

        versioned = tmp / "items.json"
        versioned.write_text(json.dumps(wrap_item_payload([{"id": "a"}])), encoding="utf-8")
        metadata = json_payload_metadata(str(versioned))
        assert metadata["exists"] is True
        assert metadata["format"] == "versioned_dict"
        assert metadata["needs_migration"] is False


def test_config_backup_and_export_file_sanitize_outputs():
    from goldmonitor.support_files import build_config_backup, save_export_file

    with tempfile.TemporaryDirectory() as tmp_dir:
        backup = build_config_backup(
            app_version="1.0.0",
            settings={"smtp_password": ""},
            thresholds={"upper_warning_rmb": 888.88, "volatility_config": {"enabled": True}},
            now_factory=fixed_now,
        )
        assert backup == {
            "app": "GoldMonitor",
            "version": "1.0.0",
            "exported_at": "2026-06-12T10:00:00",
            "settings": {"smtp_password": ""},
            "thresholds": {"upper_warning_rmb": 888.88, "volatility_config": {"enabled": True}},
        }

        saved = save_export_file(tmp_dir, "../report.md", "hello")
        assert saved == str(Path(tmp_dir) / "report.md")
        assert Path(saved).read_text(encoding="utf-8") == "hello"


def test_config_import_preview_reports_sections_ignored_keys_and_secret_actions():
    from goldmonitor.support_files import build_config_import_preview

    preview = build_config_import_preview(
        {
            "settings": {
                "smtp_server": "smtp.example.com",
                "smtp_password_configured": True,
                "smtp_password": "",
                "deepseek_api_key": "sk-imported",
                "unknown_setting": "ignored",
            },
            "thresholds": {
                "upper_warning_rmb": 700,
                "volatility_config": {"enabled": True},
                "unknown_threshold": 1,
            },
        },
        settings_defaults={
            "smtp_server": "",
            "smtp_password": "",
            "deepseek_api_key": "",
        },
        threshold_keys={"upper_warning_rmb", "volatility_config"},
        secret_keys={"smtp_password", "deepseek_api_key", "openai_compatible_api_key"},
    )

    assert preview["ok"] is True
    assert preview["importable"] is True
    assert preview["sections"] == ["settings", "thresholds"]
    assert preview["missing_sections"] == []
    assert preview["ignored"]["settings"] == ["smtp_password_configured", "unknown_setting"]
    assert preview["ignored"]["thresholds"] == ["unknown_threshold"]
    assert preview["secret_actions"] == {
        "deepseek_api_key": "import",
        "openai_compatible_api_key": "preserve_existing",
        "smtp_password": "clear",
    }
    assert preview["counts"] == {"settings": 3, "thresholds": 2}


def test_config_import_preview_rejects_payload_without_importable_sections():
    from goldmonitor.support_files import build_config_import_preview

    preview = build_config_import_preview(
        {"app": "GoldMonitor"},
        settings_defaults={"smtp_server": ""},
        threshold_keys={"upper_warning_rmb"},
        secret_keys={"smtp_password"},
    )

    assert preview["ok"] is False
    assert preview["importable"] is False
    assert preview["sections"] == []
    assert preview["missing_sections"] == ["settings", "thresholds"]
    assert preview["message"] == "备份中没有可导入的配置"


def test_open_exports_folder_plan_matches_platforms():
    from goldmonitor.support_files import build_open_folder_plan

    assert build_open_folder_plan("/tmp/out", os_name="nt", sys_platform="win32") == {
        "kind": "startfile",
        "path": "/tmp/out",
    }
    assert build_open_folder_plan("/tmp/out", os_name="posix", sys_platform="darwin") == {
        "kind": "popen",
        "args": ["open", "/tmp/out"],
        "kwargs": {"close_fds": True},
    }
    assert build_open_folder_plan("/tmp/out", os_name="posix", sys_platform="linux") == {
        "kind": "popen",
        "args": ["xdg-open", "/tmp/out"],
        "kwargs": {"close_fds": True},
    }


if __name__ == "__main__":
    failures = []
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            try:
                value()
            except Exception as exc:
                failures.append((name, exc))
    if failures:
        for name, exc in failures:
            print(f"{name}: {type(exc).__name__}: {exc}")
        raise SystemExit(1)
    print("support files module checks passed.")
