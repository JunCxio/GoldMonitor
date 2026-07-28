from datetime import datetime
from pathlib import Path
import sys
import threading
from types import SimpleNamespace


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from goldmonitor.market_adapters import MarketAdapterRegistry, MarketSourceAdapter
from goldmonitor.market_runtime import (
    MarketRuntime,
    build_market_adapter_catalog,
    build_fetch_status,
    commit_runtime_state,
    fetch_market_data_result,
    market_state_snapshot,
    record_runtime_source_price_sample,
    refresh_runtime_source_comparison,
    runtime_state_snapshot,
)


def sample_gold(close=2350.0):
    return {
        "date": "2026-07-28",
        "time": "12:00:00",
        "open": close - 5,
        "high": close + 10,
        "low": close - 20,
        "close": close,
    }


def adapter(key, name, category, priority, output, provides_rate=False):
    return MarketSourceAdapter(
        key=key,
        name=name,
        category=category,
        priority=priority,
        cache_source=name,
        provides_forex_rate=provides_rate,
        fetcher=lambda: output,
    )


def test_market_adapter_catalog_combines_preferences_runtime_source_and_metrics():
    registry = MarketAdapterRegistry([
        adapter("gold_a", "金价 A", "gold", 10, (sample_gold(), "")),
        adapter("gold_b", "金价 B", "gold", 20, (sample_gold(), "")),
    ])
    catalog = build_market_adapter_catalog(
        registry,
        {
            "enabled": {"gold": ["gold_b"]},
            "order": {"gold": ["gold_b", "gold_a"]},
        },
        {
            "金价 B": {
                "key": "gold_b",
                "sample_count": 10,
                "success_count": 9,
                "success_rate_pct": 90.0,
            },
        },
        {"sources": {"gold": {"source": "金价 B", "cached": False}}},
    )

    assert [item["key"] for item in catalog["gold"]] == ["gold_b", "gold_a"]
    assert catalog["gold"][0]["enabled"] is True
    assert catalog["gold"][0]["active"] is True
    assert catalog["gold"][0]["sample_count"] == 10
    assert catalog["gold"][1]["enabled"] is False


def test_market_fetch_orchestration_preserves_combined_source_rate():
    registry = MarketAdapterRegistry([
        adapter("failed", "失败源", "gold", 10, (None, "失败源请求超时")),
        adapter(
            "combined",
            "组合源",
            "gold",
            20,
            (sample_gold(2360.0), 7.25, ""),
            provides_rate=True,
        ),
    ])
    saved_gold = []
    saved_rates = []

    result = fetch_market_data_result(
        registry,
        save_xauusd_cache=lambda data, source: saved_gold.append((data, source)),
        save_usdcny_cache=lambda value, source, timestamp: (
            saved_rates.append((value, source, timestamp))
            or {"value": value, "source": source, "timestamp": timestamp, "cached": False}
        ),
        fetch_usdcny_rate_result=lambda: (None, "不应调用"),
        load_valid_xauusd_cache=lambda: None,
        record_source_health=lambda *args, **kwargs: None,
        now_factory=lambda: datetime(2026, 7, 28, 12, 0, 0),
    )

    data, rate_info, source, gold_error, forex_error = result
    assert data["close"] == 2360.0
    assert rate_info["value"] == 7.25
    assert source == "组合源"
    assert gold_error == ""
    assert forex_error == ""
    assert saved_gold[0][1] == "组合源"
    assert saved_rates[0][2] == "2026-07-28T12:00:00"


def test_market_runtime_updates_state_and_emits_price_status_and_history():
    state = {
        "price_usd": None,
        "price_rmb": None,
        "previous_usd": None,
        "previous_rmb": None,
        "usdcny_rate": None,
        "usdcny_rate_source": "",
        "usdcny_rate_time": None,
        "usdcny_rate_cached": False,
        "usdcny_rate_error": "",
        "gold_price_source": "",
        "gold_price_time": None,
        "gold_price_cached": False,
        "gold_price_error": "",
        "price_history": [],
        "klines_5min": [],
        "last_fetch_ok": False,
        "last_fetch_error": "",
        "last_fetch_time": None,
        "today_date": None,
        "today_open_usd": None,
        "today_high_usd": None,
        "today_low_usd": None,
        "today_open_rmb": None,
        "today_high_rmb": None,
        "today_low_rmb": None,
    }
    emitted = []
    archived = []
    alerts = []

    class RefreshLock:
        def __init__(self):
            self.released = False

        def acquire(self, blocking=False):
            return True

        def release(self):
            self.released = True

    refresh_lock = RefreshLock()
    runtime = MarketRuntime(
        state_getter=lambda: state,
        state_committer=lambda updated: state.update(updated),
        state_lock=threading.RLock(),
        refresh_lock=refresh_lock,
        fetch_market_data_result=lambda: (
            sample_gold(2300.0),
            {"value": 7.25, "source": "测试汇率", "timestamp": "2026-07-28T12:00:00", "cached": False},
            "测试金价",
            "",
            "",
        ),
        refresh_source_comparison=lambda *args, **kwargs: {"status": "ok"},
        get_source_comparison_state=lambda: {},
        aggregate_klines=lambda history: [{"time": history[-1]["time"], "close": history[-1]["usd"]}],
        add_price_history_entry=lambda entry: archived.append(entry),
        emit=lambda event, payload: emitted.append((event, payload)),
        build_fetch_status=lambda ok, message="", **kwargs: {"ok": ok, "message": message, **kwargs},
        build_price_history_state=lambda **kwargs: {"items": list(state["price_history"])},
        format_price_title=lambda rmb, usd: f"{rmb}/{usd}",
        update_desktop_price_title=lambda title: None,
        update_floating_price=lambda rmb, usd, pct: None,
        check_alert_rules=lambda now_str, now=None: alerts.append((now_str, now)),
        now_factory=lambda: datetime(2026, 7, 28, 12, 0, 0),
        ounce_to_gram=31.1035,
    )

    assert runtime.fetch_once() is True
    assert refresh_lock.released is True
    assert state["price_usd"] == 2300.0
    assert state["price_rmb"] == round(2300.0 * 7.25 / 31.1035, 2)
    assert state["last_fetch_ok"] is True
    assert len(state["price_history"]) == 1
    assert archived == state["price_history"]
    assert alerts[0][0] == "12:00:00"
    assert [event for event, _payload in emitted] == [
        "price_update",
        "fetch_status",
        "price_history_updated",
    ]
    assert emitted[0][1]["source_comparison"] == {"status": "ok"}
    assert emitted[-1][1]["scope"] == "live"


def test_market_runtime_state_helpers_roundtrip_explicit_fields():
    from goldmonitor.runtime_state import ApplicationRuntimeState

    runtime = ApplicationRuntimeState(price_usd=2300.0, price_rmb=535.0)
    snapshot = runtime_state_snapshot(runtime)
    snapshot["price_usd"] = 2310.0
    snapshot["today_high_usd"] = 2320.0
    commit_runtime_state(runtime, snapshot)

    assert runtime.price_usd == 2310.0
    assert runtime.today_high_usd == 2320.0
    assert market_state_snapshot(runtime)["price_rmb"] == 535.0


def test_fetch_status_and_source_sample_helpers_are_deterministic():
    from goldmonitor.runtime_state import ApplicationRuntimeState

    status = build_fetch_status(
        False,
        gold_ok=True,
        forex_ok=False,
        gold_source="测试金价",
        forex_error="汇率失败",
        now_factory=lambda: datetime(2026, 7, 28, 12, 0),
    )
    assert status["status"] == "degraded"
    assert status["sources"]["gold"]["source"] == "测试金价"
    assert status["time"] == "12:00:00"

    runtime = ApplicationRuntimeState()
    record_runtime_source_price_sample(
        runtime,
        "测试金价",
        {"close": "2350.25", "open": "2340", "cached": True},
        number_formatter=lambda value: float(value) if value is not None else None,
        now_factory=lambda: datetime(2026, 7, 28, 12, 30),
    )
    assert runtime.source_price_samples["测试金价"] == {
        "name": "测试金价",
        "usd": 2350.25,
        "open": 2340.0,
        "high": None,
        "low": None,
        "source_time": "",
        "checked_at": "2026-07-28T12:30:00",
        "cached": True,
    }


def test_refresh_source_comparison_records_primary_and_periodic_probes():
    from goldmonitor.runtime_state import ApplicationRuntimeState

    runtime = ApplicationRuntimeState(last_source_comparison_probe_at=0.0)
    samples = []
    secondary = SimpleNamespace(
        cache_source="备用金价",
        fetch=lambda: SimpleNamespace(value={"close": 2348.0}),
    )
    primary = SimpleNamespace(
        cache_source="主金价",
        fetch=lambda: SimpleNamespace(value={"close": 2350.0}),
    )
    registry = SimpleNamespace(
        category_adapters=lambda category: [primary, secondary]
    )

    result = refresh_runtime_source_comparison(
        runtime,
        {"close": 2350.0},
        "主金价",
        False,
        record_sample=(
            lambda name, data, cached=False:
            samples.append((name, data["close"], cached))
        ),
        registry_builder=lambda: registry,
        comparison_builder=lambda: {"status": "ok"},
        refresh_seconds=60,
        monotonic_factory=lambda: 100.0,
    )

    assert result == {"status": "ok"}
    assert samples == [
        ("主金价", 2350.0, False),
        ("备用金价", 2348.0, False),
    ]
    assert runtime.source_comparison_state == {"status": "ok"}
    assert runtime.last_source_comparison_probe_at == 100.0
