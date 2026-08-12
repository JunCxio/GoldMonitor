import threading
from datetime import datetime
from types import SimpleNamespace


def _runtime(**overrides):
    from goldmonitor.alert_notification_runtime import AlertNotificationRuntime

    state = overrides.pop(
        "state",
        SimpleNamespace(
            lock=threading.RLock(),
            price_usd=2388.5,
            price_rmb=552.3,
            usdcny_rate=7.1234,
            gold_price_source="黄金源",
            usdcny_rate_source="汇率源",
            alert_cooldown_state={},
            alert_log=[],
        ),
    )
    emitted = []
    saved = []
    entries = {}

    def update_entry(alert_id, updater):
        current = entries.get(alert_id)
        if current is None:
            return False, None
        updated = updater(dict(current))
        entries[alert_id] = updated
        return True, updated

    options = {
        "get_settings": lambda: {
            "email_warning_enabled": True,
            "webhook_enabled": False,
            "alert_cooldown_minutes": 30,
        },
        "generate_id": lambda: "alert-fixed",
        "select_news": lambda title: [{"title": title}],
        "save_entry": lambda entry: saved.append(dict(entry)),
        "update_entry": update_entry,
        "emit": lambda event, payload: emitted.append((event, payload)),
        "build_history_state": lambda **kwargs: {"limit": kwargs["limit"]},
        "send_desktop_notification": lambda *args: None,
        "play_system_alert_sound": lambda *args: None,
        "show_alert_dialog": lambda *args: None,
        "email_sender": lambda *args, **kwargs: None,
        "webhook_sender": lambda *args, **kwargs: None,
        "alert_level_map": {"warning": "关注"},
        "alert_log_limit": 10,
        "now_factory": lambda: datetime(2026, 8, 11, 12, 0, 0),
        "logger": SimpleNamespace(warning=lambda *args: None),
    }
    options.update(overrides)
    runtime = AlertNotificationRuntime(state, **options)
    return runtime, state, emitted, saved, entries


def test_alert_notification_runtime_uses_market_and_cooldown_state():
    runtime, state, _emitted, _saved, _entries = _runtime()

    values = runtime.build_template_values("warning", "价格提醒", "已达到目标")
    first = runtime.evaluate_delivery(
        {"type": "warning", "mode": "rmb", "source": "threshold"},
        now=datetime(2026, 8, 11, 12, 0, 0),
    )
    second = runtime.evaluate_delivery(
        {"type": "warning", "mode": "rmb", "source": "threshold"},
        now=datetime(2026, 8, 11, 12, 5, 0),
    )

    assert values["price_usd"] == "2,388.50"
    assert values["price_rmb"] == "552.30"
    assert values["gold_source"] == "黄金源"
    assert first == {"deliver": True, "reason": ""}
    assert second["reason"] == "cooldown"
    assert state.alert_cooldown_state


def test_alert_notification_runtime_persists_delivery_updates():
    runtime, _state, emitted, _saved, entries = _runtime()
    entries["alert-1"] = {
        "id": "alert-1",
        "notifications": [{"channel": "email", "status": "pending"}],
    }

    ok, updated = runtime.persist_notification_update(
        "alert-1",
        [{"channel": "email", "status": "sent", "message": "发送成功"}],
    )

    assert ok is True
    assert updated["notification_summary"]["status"] == "sent"
    assert emitted == [("alert_log_status_updated", {"ok": True, "entry": updated})]


def test_alert_notification_runtime_emits_muted_alert_without_local_delivery():
    local = []
    runtime, state, emitted, saved, _entries = _runtime(
        send_desktop_notification=lambda *args: local.append("desktop"),
        play_system_alert_sound=lambda *args: local.append("sound"),
        show_alert_dialog=lambda *args: local.append("dialog"),
    )

    runtime.emit_alert(
        {"type": "warning", "mode": "rmb", "time": "12:00", "message": "测试"},
        "静默提醒",
        evaluate_delivery=lambda entry, settings: {
            "deliver": False,
            "reason": "quiet_time",
        },
    )

    assert state.alert_log[0]["id"] == "alert-fixed"
    assert state.alert_log[0]["notification_summary"]["status"] == "muted"
    assert saved[0]["related_news"] == [{"title": "静默提醒"}]
    assert [event for event, _payload in emitted] == [
        "alert",
        "price_history_updated",
    ]
    assert local == []
