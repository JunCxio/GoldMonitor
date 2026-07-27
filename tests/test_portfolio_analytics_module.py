from datetime import datetime


def test_portfolio_performance_replays_transactions_against_historical_prices():
    from goldmonitor.portfolio_analytics import build_portfolio_performance

    transactions = [
        {
            "id": "buy-1",
            "position_id": "position-1",
            "name": "金条",
            "type": "buy",
            "mode": "rmb",
            "price": 100,
            "quantity": 10,
            "fee": 0,
            "trade_date": "2026-07-01",
        },
        {
            "id": "sell-1",
            "position_id": "position-1",
            "name": "金条",
            "type": "sell",
            "mode": "rmb",
            "price": 120,
            "quantity": 2,
            "fee": 0,
            "trade_date": "2026-07-03",
        },
    ]
    prices = [
        {"timestamp": "2026-07-01T12:00:00", "rmb": 100, "usd": 2200},
        {"timestamp": "2026-07-02T12:00:00", "rmb": 110, "usd": 2250},
        {"timestamp": "2026-07-03T12:00:00", "rmb": 120, "usd": 2300},
    ]

    performance = build_portfolio_performance(
        transactions,
        prices,
        current_prices={},
        now=datetime(2026, 7, 3, 12, 0),
    )

    points = performance["rmb"]["points"]
    assert [point["total_pnl"] for point in points] == [0.0, 100.0, 200.0]
    assert points[-1]["quantity"] == 8.0
    assert points[-1]["cost_basis"] == 800.0
    assert points[-1]["market_value"] == 960.0
    assert points[-1]["unrealized_pnl"] == 160.0
    assert points[-1]["realized_pnl"] == 40.0
    assert points[-1]["total_pnl_percent"] == 25.0
    assert performance["rmb"]["summary"]["max_drawdown"] == 0.0
    assert performance["usd"]["points"] == []


def test_portfolio_performance_uses_current_price_as_latest_point_and_tracks_drawdown():
    from goldmonitor.portfolio_analytics import build_portfolio_performance

    transactions = [{
        "id": "buy-1",
        "position_id": "position-1",
        "type": "buy",
        "mode": "usd",
        "price": 100,
        "quantity": 1,
        "fee": 0,
        "trade_date": "2026-07-01",
    }]
    prices = [
        {"timestamp": "2026-07-01T12:00:00", "usd": 100},
        {"timestamp": "2026-07-02T12:00:00", "usd": 120},
    ]

    performance = build_portfolio_performance(
        transactions,
        prices,
        current_prices={"usd": 90},
        now=datetime(2026, 7, 3, 12, 0),
    )["usd"]

    assert [point["total_pnl"] for point in performance["points"]] == [0.0, 20.0, -10.0]
    assert performance["summary"]["max_drawdown"] == -30.0


def test_alert_effectiveness_separates_delivery_response_and_market_follow_through():
    from goldmonitor.portfolio_analytics import build_alert_effectiveness

    alerts = [
        {
            "id": "alert-up",
            "timestamp": "2026-07-01T10:00:00",
            "title": "突破上限",
            "mode": "rmb",
            "threshold_key": "upper_warning_rmb",
            "trigger_price": 100,
            "notification_summary": {"status": "sent"},
            "acknowledged": True,
            "handled": True,
        },
        {
            "id": "alert-down",
            "timestamp": "2026-07-01T10:00:00",
            "title": "跌破下限",
            "mode": "usd",
            "threshold_key": "lower_warning_usd",
            "trigger_price": 200,
            "notification_summary": {"status": "failed"},
            "acknowledged": False,
            "handled": False,
        },
        {
            "id": "alert-neutral",
            "timestamp": "2026-07-01T10:00:00",
            "title": "接近成本",
            "mode": "rmb",
            "portfolio_alert_condition": "near_cost",
            "notification_summary": {"status": "muted"},
        },
    ]
    prices = [
        {"timestamp": "2026-07-01T11:00:00", "rmb": 101, "usd": 198},
        {"timestamp": "2026-07-01T20:00:00", "rmb": 102, "usd": 196},
    ]

    result = build_alert_effectiveness(alerts, prices, horizon_hours=24)

    assert result["period_alerts"] == 3
    assert result["delivery"] == {
        "sent": 1,
        "failed": 1,
        "muted": 1,
        "sent_rate": 33.33,
    }
    assert result["response"]["acknowledged_rate"] == 33.33
    assert result["response"]["handled_rate"] == 33.33
    assert result["market_follow_through"]["evaluated"] == 2
    assert result["market_follow_through"]["follow_through"] == 2
    assert result["market_follow_through"]["rate"] == 100.0
    assert {item["id"] for item in result["items"]} == {"alert-up", "alert-down"}
