import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def fixed_now():
    return datetime(2026, 6, 26, 10, 0, 0)


def test_portfolio_alerts_normalize_and_reset_changed_conditions():
    from goldmonitor.portfolio_alerts import normalize_portfolio_alert

    alert = normalize_portfolio_alert(
        {
            "position_id": "position-rmb",
            "enabled": True,
            "take_profit_price": "740",
            "stop_loss_price": "650",
            "profit_percent": "5",
            "loss_percent": "3",
            "near_cost_percent": "1",
            "note": "关注回撤" * 40,
        },
        now_factory=fixed_now,
        id_factory=lambda: "portfolio-alert-fixed",
    )

    assert alert["id"] == "portfolio-alert-fixed"
    assert alert["position_id"] == "position-rmb"
    assert alert["take_profit_price"] == 740.0
    assert alert["stop_loss_price"] == 650.0
    assert alert["profit_percent"] == 5.0
    assert alert["loss_percent"] == 3.0
    assert alert["near_cost_percent"] == 1.0
    assert len(alert["note"]) == 120
    assert alert["triggered"] == {
        "take_profit": False,
        "stop_loss": False,
        "profit_percent": False,
        "loss_percent": False,
        "near_cost": False,
    }

    changed = normalize_portfolio_alert(
        {**alert, "take_profit_price": "750"},
        existing={**alert, "triggered": {**alert["triggered"], "take_profit": True}},
        now_factory=fixed_now,
    )
    assert changed["triggered"]["take_profit"] is False


def test_portfolio_alerts_trigger_once_for_price_percent_and_near_cost():
    from goldmonitor.portfolio_alerts import (
        build_portfolio_alert_message,
        check_portfolio_alerts,
        normalize_portfolio_alerts,
    )

    alerts = normalize_portfolio_alerts(
        [
            {
                "id": "alert-main",
                "position_id": "position-rmb",
                "take_profit_price": "740",
                "profit_percent": "5",
                "near_cost_percent": "1",
                "enabled": True,
            },
            {
                "id": "alert-disabled",
                "position_id": "position-rmb",
                "stop_loss_price": "650",
                "enabled": False,
            },
        ],
        now_factory=fixed_now,
    )
    positions = [
        {
            "id": "position-rmb",
            "name": "金条",
            "mode": "rmb",
            "current_price": 742.0,
            "average_cost": 700.0,
            "unrealized_pnl_percent": 6.0,
            "valuation_status": "valued",
        }
    ]

    next_alerts, triggered = check_portfolio_alerts(alerts, positions, now_factory=fixed_now)

    assert [item["condition"] for item in triggered] == ["take_profit", "profit_percent"]
    assert next_alerts[0]["triggered"]["take_profit"] is True
    assert next_alerts[0]["triggered"]["profit_percent"] is True
    assert next_alerts[0]["last_trigger_price"] == 742.0
    assert next_alerts[0]["last_triggered_at"] == "2026-06-26T10:00:00"

    again_alerts, again_triggered = check_portfolio_alerts(next_alerts, positions, now_factory=fixed_now)
    assert again_alerts == next_alerts
    assert again_triggered == []

    near_cost_positions = [{**positions[0], "current_price": 704.0, "unrealized_pnl_percent": 0.5714}]
    reset_alerts = normalize_portfolio_alerts(
        [{**next_alerts[0], "triggered": {**next_alerts[0]["triggered"], "near_cost": False}}],
        now_factory=fixed_now,
    )
    _near_alerts, near_triggered = check_portfolio_alerts(reset_alerts, near_cost_positions, now_factory=fixed_now)
    assert [item["condition"] for item in near_triggered] == ["near_cost"]

    message = build_portfolio_alert_message(triggered[0])
    assert "金条" in message
    assert "止盈价" in message
    assert "¥742.00" in message
