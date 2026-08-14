import threading
from datetime import datetime


def test_export_directory_helpers_preserve_actionable_failure_details(tmp_path):
    from goldmonitor.operations_runtime import (
        build_export_dir_check,
        build_export_error_payload,
        resolve_export_dir,
    )

    export_dir = resolve_export_dir({"export_dir": str(tmp_path / "exports")}, "fallback")
    check = build_export_dir_check(export_dir, actions=("choose", "reset"))
    assert check["ok"] is True
    assert check["path"] == export_dir

    failure = build_export_dir_check(
        export_dir,
        actions=("choose", "reset"),
        probe_writer=lambda path: (_ for _ in ()).throw(PermissionError("denied")),
    )
    payload = build_export_error_payload("导出失败", {"ok": False, "message": "最近失败"}, failure)
    assert failure["actions"] == ["choose", "reset"]
    assert payload["message"] == "最近失败"


def test_archive_upload_store_cleanup_and_consume(tmp_path):
    from goldmonitor.operations_runtime import cleanup_uploads, consume_upload, store_upload

    uploads = {}
    lock = threading.RLock()
    stale_path = tmp_path / "stale.zip"
    stale_path.write_bytes(b"stale")
    uploads["stale"] = {"path": str(stale_path), "created_at": 1.0}

    cleanup = lambda: cleanup_uploads(uploads, lock, 10, now_monotonic=20.0)
    token = store_upload(
        uploads,
        lock,
        str(tmp_path / "current.zip"),
        {"files": 2},
        cleanup=cleanup,
        token_factory=lambda: "token-1",
        monotonic_factory=lambda: 20.0,
    )

    assert token == "token-1"
    assert not stale_path.exists()
    assert consume_upload(uploads, lock, token, cleanup=lambda: None)["preview"] == {"files": 2}
    assert uploads == {}


def test_save_export_file_records_success_and_failure(tmp_path):
    from goldmonitor.operations_runtime import save_export_file

    statuses = []
    now = lambda: datetime(2026, 7, 28, 12, 0)
    saved = save_export_file(
        "report.md",
        "content",
        export_dir=str(tmp_path),
        writer=lambda export_dir, filename, content: str(tmp_path / filename),
        set_status=statuses.append,
        now_factory=now,
    )
    assert saved.endswith("report.md")
    assert statuses[-1]["status"] == "success"

    try:
        save_export_file(
            "report.md",
            "content",
            export_dir=str(tmp_path),
            writer=lambda *args: (_ for _ in ()).throw(PermissionError("denied")),
            set_status=statuses.append,
            now_factory=now,
        )
    except PermissionError:
        pass
    assert statuses[-1]["category"] == "permission_denied"


def test_create_data_archive_holds_archive_and_state_locks(tmp_path):
    from goldmonitor.operations_runtime import create_data_archive

    events = []

    class RecordingLock:
        def __init__(self, name):
            self.name = name

        def __enter__(self):
            events.append(f"enter:{self.name}")
            return self

        def __exit__(self, exc_type, exc, traceback):
            events.append(f"exit:{self.name}")

    class Manager:
        def create(self, destination_path, content_overrides):
            events.append("create")
            assert content_overrides["settings"]
            return {
                "path": destination_path,
                "filename": "GoldMonitor-data.zip",
                "files": 2,
                "bytes": 12,
                "contains_sensitive_data": True,
            }

    result = create_data_archive(
        now=datetime(2026, 8, 14, 12, 0),
        export_dir=str(tmp_path),
        settings={"theme": "dark"},
        archive_lock=RecordingLock("archive"),
        state_locks=(RecordingLock("history"),),
        manager=Manager(),
        set_status=lambda _status: None,
        directory_status={"ok": True},
    )

    assert result["ok"] is True
    assert events == [
        "enter:archive",
        "enter:history",
        "create",
        "exit:history",
        "exit:archive",
    ]
