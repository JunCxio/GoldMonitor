def test_build_5min_klines_groups_history_by_timestamp_and_unit():
    import app

    history = [
        {"usd": 100.0, "rmb": 500.0, "rate": 7.0, "time": "09:01:00", "timestamp": "2026-06-30T09:01:00"},
        {"usd": 102.0, "rmb": 506.0, "rate": 7.0, "time": "09:03:00", "timestamp": "2026-06-30T09:03:00"},
        {"usd": 101.0, "rmb": 504.0, "rate": 7.0, "time": "09:04:00", "timestamp": "2026-06-30T09:04:00"},
        {"usd": 105.0, "rmb": 510.0, "rate": 7.0, "time": "09:05:00", "timestamp": "2026-06-30T09:05:00"},
        {"usd": 104.0, "rmb": 508.0, "rate": 7.0, "time": "09:08:00", "timestamp": "2026-06-30T09:08:00"},
    ]

    candles = app.build_5min_klines(history, limit=10)

    assert len(candles) == 2
    assert candles[0] == {
        "open": 100.0,
        "high": 102.0,
        "low": 100.0,
        "close": 101.0,
        "open_rmb": 500.0,
        "high_rmb": 506.0,
        "low_rmb": 500.0,
        "close_rmb": 504.0,
        "time": "09:00",
        "timestamp": "2026-06-30T09:00:00",
    }
    assert candles[1]["open"] == 105.0
    assert candles[1]["close"] == 104.0
    assert candles[1]["open_rmb"] == 510.0
    assert candles[1]["close_rmb"] == 508.0
    assert candles[1]["time"] == "09:05"


def test_restore_price_history_state_rebuilds_klines_from_archive():
    import app

    original_history = list(app.price_history)
    original_klines = list(app.klines_5min)
    archive = [
        {"usd": 200.0, "rmb": 600.0, "rate": 7.0, "time": "10:00:00", "timestamp": "2026-06-30T10:00:00"},
        {"usd": 201.0, "rmb": 602.0, "rate": 7.0, "time": "10:02:00", "timestamp": "2026-06-30T10:02:00"},
        {"usd": 205.0, "rmb": 610.0, "rate": 7.0, "time": "10:05:00", "timestamp": "2026-06-30T10:05:00"},
    ]

    try:
        app.price_history = []
        app.klines_5min = []
        app.restore_price_history_state(archive)

        assert app.price_history == archive
        assert [item["time"] for item in app.klines_5min] == ["10:00", "10:05"]
    finally:
        app.price_history = original_history
        app.klines_5min = original_klines
