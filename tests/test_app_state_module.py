def test_build_price_api_state_limits_klines_and_preserves_market_fields():
    from goldmonitor.app_state import build_price_api_state

    state = build_price_api_state(
        {
            "price_usd": 2350.12,
            "price_rmb": 544.21,
            "usdcny_rate": 7.21,
            "gold_price_source": "测试金价源",
            "gold_price_time": "2026-06-30T10:00:00",
            "gold_price_cached": False,
            "gold_price_error": "",
            "usdcny_rate_source": "测试汇率源",
            "usdcny_rate_time": "2026-06-30T10:00:01",
            "usdcny_rate_cached": True,
            "usdcny_rate_error": "启动时使用缓存汇率",
            "previous_usd": 2349.0,
            "previous_rmb": 543.9,
            "price_history": [{"time": "09:59:59"}],
            "last_fetch_ok": True,
            "klines_5min": [{"idx": idx} for idx in range(80)],
        }
    )

    assert state["usd"] == 2350.12
    assert state["rmb"] == 544.21
    assert state["rate"] == 7.21
    assert state["gold_source"] == "测试金价源"
    assert state["gold_time"] == "2026-06-30T10:00:00"
    assert state["gold_cached"] is False
    assert state["gold_error"] == ""
    assert state["rate_source"] == "测试汇率源"
    assert state["rate_time"] == "2026-06-30T10:00:01"
    assert state["rate_cached"] is True
    assert state["rate_error"] == "启动时使用缓存汇率"
    assert state["previous_usd"] == 2349.0
    assert state["previous_rmb"] == 543.9
    assert state["time"] == "09:59:59"
    assert state["ok"] is True
    assert [item["idx"] for item in state["klines_5min"]] == list(range(8, 80))


def test_build_socket_init_state_limits_live_lists_and_preserves_injected_sections():
    from goldmonitor.app_state import build_socket_init_state

    state = build_socket_init_state(
        {
            "price_usd": 2350.12,
            "price_rmb": 544.21,
            "usdcny_rate": 7.21,
            "price_history": [{"idx": idx, "time": f"10:{idx:02d}:00"} for idx in range(70)],
            "klines_5min": [{"idx": idx} for idx in range(80)],
            "last_fetch_ok": False,
        },
        thresholds={"upper_warning_rmb": 560.0},
        volatility_config={"enabled": True, "percent": 1.0, "minutes": 10},
        watch_targets={"items": [{"id": "target-1"}], "total": 1},
        portfolio={"items": [{"id": "position-1"}], "total": 1},
        settings={"risk_assistant_enabled": True},
        alert_log=[{"idx": idx} for idx in range(25)],
        fetch_status={"status": "degraded"},
        source_health={"summary": {"status": "degraded"}},
        source_comparison={"status": "insufficient"},
        price_history_state={"items": [{"idx": "history"}]},
        daily={"open_rmb": 540.0},
        news={"items": [{"title": "news"}]},
        risk_analysis_history={"items": [{"id": "risk-1"}]},
    )

    assert state["usd"] == 2350.12
    assert state["rmb"] == 544.21
    assert state["rate"] == 7.21
    assert [item["idx"] for item in state["history"]] == list(range(10, 70))
    assert [item["idx"] for item in state["klines_5min"]] == list(range(8, 80))
    assert [item["idx"] for item in state["alert_log"]] == list(range(5, 25))
    assert state["thresholds"] == {"upper_warning_rmb": 560.0}
    assert state["volatility_config"] == {"enabled": True, "percent": 1.0, "minutes": 10}
    assert state["watch_targets"] == {"items": [{"id": "target-1"}], "total": 1}
    assert state["portfolio"] == {"items": [{"id": "position-1"}], "total": 1}
    assert state["settings"] == {"risk_assistant_enabled": True}
    assert state["fetch_status"] == {"status": "degraded"}
    assert state["source_health"] == {"summary": {"status": "degraded"}}
    assert state["source_comparison"] == {"status": "insufficient"}
    assert state["price_history_state"] == {"items": [{"idx": "history"}]}
    assert state["daily"] == {"open_rmb": 540.0}
    assert state["news"] == {"items": [{"title": "news"}]}
    assert state["risk_analysis_history"] == {"items": [{"id": "risk-1"}]}
