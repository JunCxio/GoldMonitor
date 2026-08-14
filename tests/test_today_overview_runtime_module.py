import threading
from datetime import datetime
from types import SimpleNamespace


def _runtime(tmp_path, **overrides):
    from goldmonitor.today_overview_runtime import TodayOverviewRuntime

    state = SimpleNamespace(today_overview_lock=threading.RLock())
    options = {
        "state_path": lambda: str(tmp_path / "today-overview.json"),
        "get_alert_entries": lambda: [
            {
                "id": "alert-1",
                "timestamp": "2026-08-12T09:00:00",
                "handled": False,
                "read": False,
            }
        ],
        "get_alert_rules": lambda: {"items": []},
        "get_source_health": lambda: {
            "quality": {"level": "normal", "score": 100, "label": "数据可信"}
        },
        "get_fetch_status": lambda: {"ok": True},
        "get_background_tasks": lambda: {"tasks": []},
        "build_portfolio": lambda: {"total": 0, "transactions": []},
        "get_risk_history": lambda: {"items": []},
        "get_review_notes": lambda: {"items": []},
        "now_factory": lambda: datetime(2026, 8, 12, 10, 0),
    }
    options.update(overrides)
    return TodayOverviewRuntime(state, **options)


def test_today_overview_runtime_builds_from_injected_fact_sources(tmp_path):
    runtime = _runtime(tmp_path)

    result = runtime.build()

    assert result["generated_at"] == "2026-08-12T10:00:00"
    assert result["summary"]["alerts_today"] == 1
    assert result["summary"]["unhandled_alerts"] == 1
    assert result["summary"]["new_since_last_view"] == 0


def test_today_overview_runtime_marks_viewed_and_rebuilds_counts(tmp_path):
    runtime = _runtime(tmp_path)

    result = runtime.mark_viewed(now=datetime(2026, 8, 12, 9, 30))

    assert result["view_state"]["last_viewed_at"] == "2026-08-12T09:30:00"
    assert result["overview"]["summary"]["new_since_last_view"] == 0
    assert runtime.get_view_state() == result["view_state"]


def test_today_overview_socket_handlers_return_updates_and_safe_errors():
    from goldmonitor.socket_today_overview import register_today_overview_handlers

    registered = {}
    emitted = []

    class Socket:
        def __init__(self, registry):
            self.registry = registry

        def on(self, event):
            return lambda handler: self.registry.setdefault(event, handler)

        def emit(self, event, payload):
            emitted.append((event, payload))

    socket = Socket(registered)
    register_today_overview_handlers(
        socket,
        build_today_overview=lambda: {"schema_version": 1},
        mark_today_overview_viewed=lambda: {
            "view_state": {"last_viewed_at": "2026-08-12T10:00:00"},
            "overview": {"schema_version": 1, "summary": {}},
        },
    )

    assert set(registered) == {
        "get_today_overview",
        "mark_today_overview_viewed",
    }

    from unittest.mock import patch

    with patch("goldmonitor.socket_today_overview.emit") as direct_emit:
        registered["get_today_overview"]()
        direct_emit.assert_called_with(
            "today_overview_updated",
            {"schema_version": 1},
        )

        registered["mark_today_overview_viewed"]()
        assert emitted[-1] == (
            "today_overview_updated",
            {"schema_version": 1, "summary": {}},
        )
        direct_emit.assert_called_with(
            "today_overview_viewed",
            {
                "ok": True,
                "view_state": {"last_viewed_at": "2026-08-12T10:00:00"},
            },
        )

    failing_registered = {}
    failing_socket = Socket(failing_registered)
    register_today_overview_handlers(
        failing_socket,
        build_today_overview=lambda: (_ for _ in ()).throw(
            OSError("/private/user/today-overview.json")
        ),
        mark_today_overview_viewed=lambda: (_ for _ in ()).throw(
            OSError("/private/user/today-overview.json")
        ),
    )
    with patch("goldmonitor.socket_today_overview.emit") as direct_emit:
        failing_registered["get_today_overview"]()
        assert "/private/user" not in str(direct_emit.call_args)
        assert direct_emit.call_args.args == (
            "today_overview_error",
            {"message": "今日概览加载失败，请稍后重试。"},
        )

        failing_registered["mark_today_overview_viewed"]()
        assert "/private/user" not in str(direct_emit.call_args)
        assert direct_emit.call_args.args == (
            "today_overview_error",
            {"message": "今日概览查看状态保存失败，请检查配置目录权限。"},
        )


def test_app_today_overview_socket_persists_view_state(monkeypatch, tmp_path):
    import app

    monkeypatch.setattr(
        app,
        "TODAY_OVERVIEW_STATE_PATH",
        str(tmp_path / "today_overview_state.json"),
    )
    monkeypatch.setattr(app, "alert_log_export_entries", lambda limit=1000: [{
        "id": "alert-app-1",
        "timestamp": datetime.now().replace(microsecond=0).isoformat(timespec="seconds"),
        "message": "应用级概览警报",
        "handled": False,
        "read": False,
    }])
    monkeypatch.setattr(app, "get_alert_rules_state", lambda: {"items": []})
    monkeypatch.setattr(app, "get_source_health_state", lambda: {
        "quality": {"level": "normal", "score": 100, "label": "数据可信"}
    })
    monkeypatch.setattr(app, "get_fetch_status", lambda: {"ok": True})
    monkeypatch.setattr(app, "get_background_task_status", lambda: {
        "tasks": [{
            "name": "price_history_health",
            "label": "历史数据检查",
            "state": "error",
            "attention_required": True,
            "consecutive_failures": 3,
            "last_message": "历史数据需要处理",
            "last_error_at": datetime.now().replace(microsecond=0).isoformat(timespec="seconds"),
            "schedule_delayed": False,
        }]
    })
    monkeypatch.setattr(app, "build_portfolio_state", lambda: {"total": 0, "transactions": []})
    monkeypatch.setattr(app, "get_risk_analysis_history_state", lambda: {"items": []})
    monkeypatch.setattr(app, "get_review_notes_state", lambda: {"items": []})
    monkeypatch.setattr(app.runtime, "today_overview_runtime_instance", None)

    client = app.socketio.test_client(
        app.app,
        auth={"token": app.SOCKET_ACCESS_TOKEN},
    )
    client.get_received()
    client.emit("get_today_overview")
    received = client.get_received()
    overview = next(
        item["args"][0]
        for item in received
        if item["name"] == "today_overview_updated"
    )
    assert overview["summary"]["unhandled_alerts"] == 1
    assert overview["summary"]["background_task_issues"] == 1

    client.emit("mark_today_overview_viewed")
    received = client.get_received()
    viewed = next(
        item["args"][0]
        for item in received
        if item["name"] == "today_overview_viewed"
    )
    assert viewed["ok"] is True
    assert viewed["view_state"]["last_viewed_at"]
    assert (tmp_path / "today_overview_state.json").exists()
    client.disconnect()
