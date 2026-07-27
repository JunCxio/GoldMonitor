from datetime import datetime


def test_app_builds_portfolio_performance_and_alert_effectiveness(monkeypatch):
    import app

    monkeypatch.setattr(app, "portfolio_transactions", [{
        "id": "transaction-1",
        "position_id": "position-1",
        "name": "金条",
        "type": "buy",
        "mode": "rmb",
        "price": 100,
        "quantity": 2,
        "fee": 0,
        "trade_date": "2026-07-01",
        "created_at": "2026-07-01T09:00:00",
    }])
    monkeypatch.setattr(app, "portfolio_positions", [])
    monkeypatch.setattr(app, "price_rmb", 120.0)
    monkeypatch.setattr(app, "price_usd", 2300.0)
    history = [
        {"timestamp": "2026-07-01T12:00:00", "rmb": 100.0, "usd": 2200.0},
        {"timestamp": "2026-07-02T12:00:00", "rmb": 110.0, "usd": 2250.0},
        {"timestamp": "2026-07-03T12:00:00", "rmb": 120.0, "usd": 2300.0},
    ]
    monkeypatch.setattr(app, "_analytics_price_history", lambda days, limit=1000: list(history))
    monkeypatch.setattr(app, "alert_log_export_entries", lambda limit=None: [{
        "id": "alert-1",
        "timestamp": "2026-07-02T10:00:00",
        "mode": "rmb",
        "threshold_key": "upper_warning_rmb",
        "trigger_price": 109.0,
        "notification_summary": {"status": "sent"},
        "handled": True,
    }])

    state = app.build_portfolio_analytics_state(days=90, now=datetime(2026, 7, 3, 12, 0))

    assert state["range_days"] == 90
    assert state["performance"]["rmb"]["points"][-1]["total_pnl"] == 40.0
    assert state["alert_effectiveness"]["period_days"] == 30
    assert state["alert_effectiveness"]["delivery"]["sent"] == 1


def test_portfolio_analytics_socket_normalizes_range(monkeypatch):
    import app

    calls = []
    monkeypatch.setattr(
        app,
        "build_portfolio_analytics_state",
        lambda days=90, now=None: calls.append(days) or {"range_days": 90, "performance": {}},
    )
    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()
    client.emit("get_portfolio_analytics", {"days": 999})
    events = client.get_received()

    payload = next(item["args"][0] for item in events if item["name"] == "portfolio_analytics_updated")
    assert calls == [999]
    assert payload["range_days"] == 90
    client.disconnect()
