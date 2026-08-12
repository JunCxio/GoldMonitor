import threading
from datetime import datetime
from types import SimpleNamespace


def _runtime(tmp_path, **overrides):
    from goldmonitor.export_runtime import ExportRuntime

    state = SimpleNamespace(
        last_export_status={},
        last_export_status_lock=threading.RLock(),
    )
    settings = {"export_dir": ""}
    options = {
        "get_settings": lambda: dict(settings),
        "default_export_dir": lambda: str(tmp_path / "default"),
        "check_actions": lambda: ("choose", "reset"),
        "home_dir": lambda: str(tmp_path),
        "writer": lambda export_dir, filename, content: str(
            tmp_path / filename
        ),
        "now_factory": lambda: datetime(2026, 8, 11, 11, 0, 0),
    }
    options.update(overrides)
    return ExportRuntime(state, **options)


def test_export_runtime_resolves_checks_and_selects_export_directory(tmp_path):
    custom_dir = tmp_path / "custom"
    custom_dir.mkdir()
    captured = []
    runtime = _runtime(tmp_path)

    assert runtime.resolve_export_dir() == str(tmp_path / "default")
    assert runtime.resolve_export_dir({"export_dir": str(custom_dir)}) == str(
        custom_dir
    )
    check = runtime.build_export_dir_check(
        {"export_dir": str(custom_dir)},
        probe_writer=lambda path: captured.append(path),
    )
    picker = runtime.build_export_dir_picker_payload(
        lambda initial_dir: captured.append(initial_dir) or (str(custom_dir),),
        {"export_dir": str(custom_dir)},
    )

    assert check["ok"] is True
    assert captured == [str(custom_dir), str(custom_dir)]
    assert picker["path"] == str(custom_dir)


def test_export_runtime_records_success_and_failure_status(tmp_path):
    saved = []
    runtime = _runtime(
        tmp_path,
        writer=lambda export_dir, filename, content: (
            saved.append((export_dir, filename, content))
            or str(tmp_path / filename)
        ),
    )

    path = runtime.save_export_file("report.md", "content")
    status = runtime.get_last_export_status()

    assert path == str(tmp_path / "report.md")
    assert saved == [(str(tmp_path / "default"), "report.md", "content")]
    assert status["status"] == "success"
    assert status["timestamp"] == "2026-08-11T11:00:00"

    runtime.writer = lambda *args: (_ for _ in ()).throw(
        PermissionError("denied")
    )
    try:
        runtime.save_export_file("report.md", "content")
    except PermissionError:
        pass
    else:
        raise AssertionError("export failure must be propagated")

    failure = runtime.get_last_export_status()
    assert failure["category"] == "permission_denied"
    assert runtime.build_export_error_payload("导出失败")["message"].startswith(
        "导出目录不可写"
    )
