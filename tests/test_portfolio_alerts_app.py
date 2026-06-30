import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_app_portfolio_alerts_attach_to_state_and_trigger_once(monkeypatch, tmp_path):
    import app

    emitted_alerts = []
    monkeypatch.setattr(app, "PORTFOLIO_ALERTS_PATH", str(tmp_path / "portfolio_alerts.json"))
    monkeypatch.setattr(app, "portfolio_alerts", [])
    monkeypatch.setattr(app, "portfolio_positions", [])
    monkeypatch.setattr(app, "portfolio_transactions", [{
        "id": "transaction-rmb",
        "position_id": "position-rmb",
        "name": "金条",
        "type": "buy",
        "mode": "rmb",
        "price": 700.0,
        "quantity": 10.0,
        "fee": 0.0,
        "trade_date": "2026-06-01",
        "note": "",
        "created_at": "2026-06-25T10:00:00",
        "updated_at": "2026-06-25T10:00:00",
    }])
    monkeypatch.setattr(app, "price_rmb", 742.0)
    monkeypatch.setattr(app, "price_usd", 2350.0)
    monkeypatch.setattr(app, "emit_alert", lambda entry, title: emitted_alerts.append((dict(entry), title)))

    state = app.upsert_portfolio_alert({
        "position_id": "position-rmb",
        "take_profit_price": "740",
        "profit_percent": "5",
        "near_cost_percent": "1",
        "enabled": True,
    })

    assert state["alerts"]["total"] == 1
    assert state["items"][0]["alert"]["status"] == "watching"
    assert Path(app.PORTFOLIO_ALERTS_PATH).exists()

    triggered = app.check_portfolio_alerts("12:00:00")

    assert [item["condition"] for item in triggered] == ["take_profit", "profit_percent"]
    assert len(emitted_alerts) == 2
    first_entry, first_title = emitted_alerts[0]
    assert first_title == "持仓提醒"
    assert first_entry["source"] == "portfolio_alert"
    assert first_entry["portfolio_position_id"] == "position-rmb"
    assert first_entry["portfolio_alert_condition"] == "take_profit"
    assert "金条" in first_entry["message"]
    assert app.portfolio_alerts[0]["triggered"]["take_profit"] is True

    triggered_again = app.check_portfolio_alerts("12:00:10")

    assert triggered_again == []
    assert len(emitted_alerts) == 2
    state_after = app.build_portfolio_state()
    assert state_after["alerts"]["triggered"] == 1
    assert state_after["items"][0]["alert"]["status"] == "triggered"
    assert state_after["items"][0]["portfolio_status"] == "target_hit"


def test_portfolio_alert_socket_events_save_reset_and_delete(monkeypatch, tmp_path):
    import app

    monkeypatch.setattr(app, "PORTFOLIO_ALERTS_PATH", str(tmp_path / "portfolio_alerts.json"))
    monkeypatch.setattr(app, "portfolio_alerts", [])
    monkeypatch.setattr(app, "portfolio_positions", [])
    monkeypatch.setattr(app, "portfolio_transactions", [])
    monkeypatch.setattr(app, "price_rmb", 742.0)
    monkeypatch.setattr(app, "price_usd", 2350.0)

    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()
    client.emit("save_portfolio_alert", {
        "position_id": "position-rmb",
        "take_profit_price": "740",
        "enabled": True,
    })
    events = client.get_received()
    updated = next(event["args"][0] for event in events if event["name"] == "portfolio_updated")
    assert updated["alerts"]["total"] == 1

    alert_id = updated["alerts"]["items"][0]["id"]
    client.emit("reset_portfolio_alert", {"id": alert_id})
    events = client.get_received()
    reset = next(event["args"][0] for event in events if event["name"] == "portfolio_updated")
    assert reset["alerts"]["triggered"] == 0

    client.emit("delete_portfolio_alert", {"id": alert_id})
    events = client.get_received()
    deleted = next(event["args"][0] for event in events if event["name"] == "portfolio_updated")
    assert deleted["alerts"]["total"] == 0
    client.disconnect()
