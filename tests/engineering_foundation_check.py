import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_platform_capabilities_are_explicit():
    from goldmonitor.platform import platform_capabilities

    windows = platform_capabilities("windows")
    assert windows["platform"] == "windows"
    assert windows["has_system_tray"] is True
    assert windows["floating_price_mode"] == "floating_window"

    macos = platform_capabilities("macos")
    assert macos["platform"] == "macos"
    assert macos["has_menu_bar_status"] is True
    assert macos["floating_price_mode"] == "menu_bar"

    other = platform_capabilities("other")
    assert other["platform"] == "other"
    assert other["floating_price_mode"] == "none"


def test_item_payloads_are_versioned_and_legacy_payloads_still_load():
    from goldmonitor.data_contracts import (
        CURRENT_SCHEMA_VERSION,
        item_payload_metadata,
        unwrap_item_payload,
        wrap_item_payload,
    )

    payload = wrap_item_payload([{"id": "a"}], updated_at="2026-06-24T10:00:00")
    assert payload["schema_version"] == CURRENT_SCHEMA_VERSION
    assert payload["updated_at"] == "2026-06-24T10:00:00"
    assert payload["items"] == [{"id": "a"}]
    assert unwrap_item_payload(payload) == [{"id": "a"}]

    legacy_list = [{"id": "legacy"}]
    assert unwrap_item_payload(legacy_list) == legacy_list
    assert item_payload_metadata(legacy_list)["format"] == "legacy_list"

    legacy_dict = {"items": [{"id": "legacy-dict"}]}
    metadata = item_payload_metadata(legacy_dict)
    assert metadata["schema_version"] == 0
    assert metadata["format"] == "legacy_dict"
    assert metadata["needs_migration"] is True


def test_diagnostics_summary_marks_degraded_health():
    from goldmonitor.diagnostics import build_health_summary

    summary = build_health_summary(
        fetch_status={"ok": False, "message": "行情数据异常"},
        source_health={
            "summary": {"total": 2, "ok": 1, "failed": 1, "cached": 1},
            "items": [{"name": "缓存金价", "cached": True, "ok": True}],
        },
        price_history={"total": 3},
        watch_targets={"total": 2, "enabled": 1, "triggered": 1},
        risk_history_count=4,
        recent_alerts=[{"id": "alert-1", "read": False}],
        paths={"settings": "/tmp/settings.json", "price_history_db": "/tmp/price.sqlite3"},
    )

    assert summary["status"] == "degraded"
    assert "行情数据异常" in summary["messages"]
    assert summary["counts"]["price_history_points"] == 3
    assert summary["counts"]["unread_alerts"] == 1
    assert summary["storage"]["settings"]["path"] == "/tmp/settings.json"


def test_diagnostics_summary_counts_alert_notification_states():
    from goldmonitor.diagnostics import build_health_summary

    summary = build_health_summary(
        fetch_status={"ok": True, "message": "行情数据正常"},
        source_health={"summary": {"total": 1, "ok": 1, "failed": 0, "cached": 0}},
        price_history={"total": 8},
        watch_targets={"total": 0, "enabled": 0, "triggered": 0},
        risk_history_count=0,
        recent_alerts=[
            {"id": "alert-1", "notification_summary": {"status": "muted"}},
            {"id": "alert-2", "notification_summary": {"status": "partial"}},
            {"id": "alert-3", "notification_summary": {"status": "skipped"}},
        ],
        paths={},
    )

    assert summary["status"] == "degraded"
    assert summary["counts"]["notification_muted_alerts"] == 1
    assert summary["counts"]["notification_problem_alerts"] == 2
    assert "2 条警报通知未完全送达" in summary["messages"]


def test_frontend_shell_static_resource_is_referenced():
    template = Path("templates/index.html").read_text(encoding="utf-8")
    shell = Path("static/app-shell.js")

    assert "static/app-shell.js" in template
    assert shell.exists()
    assert "window.GoldMonitorShell" in shell.read_text(encoding="utf-8")


def test_extension_readiness_docs_gate_boundary_expansion():
    checklist = Path("docs/product-discovery/extension-readiness-checklist.md")
    readme = Path("README.md").read_text(encoding="utf-8")

    assert checklist.exists()
    text = checklist.read_text(encoding="utf-8")
    assert "阶段 1：模块边界整理" in text
    assert "阶段 2：本地数据能力完善" in text
    assert "阶段 3：持仓、预警、复盘闭环" in text
    assert "阶段 4：行情可信度增强" in text
    assert "多品种贵金属" in text
    assert "云同步" in text
    assert "extension-readiness-checklist.md" in readme


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
    print("engineering foundation checks passed.")
