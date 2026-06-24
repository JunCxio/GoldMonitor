import tempfile
from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


THRESHOLD_KEYS = [
    f"{kind}_{mode}"
    for mode in ("usd", "rmb")
    for kind in ("upper_warning", "upper_critical", "lower_warning", "lower_critical")
]


def fixed_now():
    return datetime(2026, 6, 12, 10, 0, 0)


def test_thresholds_normalize_persist_and_build_alert_plans():
    from goldmonitor.targets import (
        ThresholdStore,
        build_threshold_alert,
        normalize_thresholds,
        normalize_volatility_config,
    )

    defaults = {key: None for key in THRESHOLD_KEYS}
    normalized = normalize_thresholds(
        {
            "upper_warning_rmb": "888.88",
            "lower_critical_usd": "1800",
            "unexpected_badmode": 1,
            "volatility_config": {"percent": "1.5", "minutes": "15", "enabled": True},
        },
        defaults,
        {"percent": None, "minutes": 10, "enabled": False},
    )
    assert normalized["upper_warning_rmb"] == 888.88
    assert normalized["lower_critical_usd"] == 1800.0
    assert "unexpected_badmode" not in normalized
    assert normalized["volatility_config"] == {"percent": 1.5, "minutes": 15, "enabled": True}
    assert normalize_volatility_config({"percent": "-1", "minutes": "bad", "enabled": True}) == {
        "percent": None,
        "minutes": 10,
        "enabled": False,
    }

    plan = build_threshold_alert(
        "rmb",
        889.0,
        "12:00:00",
        normalized,
        alerted_flags={},
        usdcny_rate=7.19,
        usdcny_rate_cached=True,
        usdcny_rate_source="cache",
    )
    assert plan["key"] == "upper_warning_rmb"
    assert plan["alert"]["type"] == "warning"
    assert plan["title"] == "金价预警 - 上涨关注"
    assert "缓存汇率 7.1900" in plan["alert"]["message"]

    flags = {"upper_warning_rmb": True}
    reset = build_threshold_alert("rmb", 880.0, "12:00:10", normalized, flags)
    assert reset is None
    assert flags["upper_warning_rmb"] is False

    with tempfile.TemporaryDirectory() as tmp_dir:
        store = ThresholdStore(str(Path(tmp_dir) / "thresholds.json"), defaults, now_factory=fixed_now)
        store.save(normalized)
        loaded = store.load()
    assert loaded == normalized


def test_watch_targets_normalize_mutate_and_trigger_once():
    from goldmonitor.targets import (
        WatchTargetStore,
        build_watch_target_alert_message,
        check_watch_targets,
        normalize_watch_target,
        normalize_watch_targets,
        watch_targets_state,
    )

    target = normalize_watch_target(
        {
            "mode": "usd",
            "direction": "rise_to",
            "price": "2400",
            "note": "突破观察" * 40,
        },
        now_factory=fixed_now,
        id_factory=lambda: "target-fixed",
    )
    assert target["id"] == "target-fixed"
    assert target["price"] == 2400.0
    assert len(target["note"]) == 120

    edited = normalize_watch_target(
        {**target, "price": 2410, "triggered": True, "triggered_at": "2026-06-12T09:00:00", "last_trigger_price": 2401},
        existing={**target, "triggered": True, "triggered_at": "2026-06-12T08:00:00", "last_trigger_price": 2401},
        now_factory=fixed_now,
    )
    assert edited["triggered"] is False
    assert edited["triggered_at"] == ""
    assert edited["last_trigger_price"] is None

    items = normalize_watch_targets([target, target, {"id": "bad", "mode": "bad", "direction": "fall_to", "price": 1}])
    assert len(items) == 1
    assert watch_targets_state(items) == {"items": items, "total": 1, "enabled": 1, "triggered": 0}

    checked_at = fixed_now() + timedelta(minutes=1)
    next_items, triggered = check_watch_targets(
        items,
        prices={"usd": 2401.0, "rmb": 688.0},
        now_factory=lambda: checked_at,
    )
    assert len(triggered) == 1
    assert triggered[0]["current_price"] == 2401.0
    assert next_items[0]["triggered"] is True
    assert next_items[0]["triggered_at"] == "2026-06-12T10:01:00"

    again_items, again_triggered = check_watch_targets(next_items, prices={"usd": 2402.0}, now_factory=lambda: checked_at)
    assert again_items == next_items
    assert again_triggered == []

    message = build_watch_target_alert_message(next_items[0], 2401.0)
    assert "国际金价" in message
    assert "$2,401.00" in message

    with tempfile.TemporaryDirectory() as tmp_dir:
        store = WatchTargetStore(str(Path(tmp_dir) / "watch_targets.json"), now_factory=fixed_now, id_factory=lambda: "target-store")
        saved = store.save(items)
        loaded = store.load()
    assert loaded == saved


def test_volatility_alert_plan_respects_window_and_cooldown():
    from goldmonitor.targets import build_volatility_alert

    history = [
        {"usd": 2300.0, "timestamp": "2026-06-12T09:59:40"},
        {"usd": 2304.0, "timestamp": "2026-06-12T09:59:50"},
        {"usd": 2330.0, "timestamp": "2026-06-12T10:00:00"},
    ]
    plan, checked_at = build_volatility_alert(
        history,
        {"percent": 1.0, "minutes": 0.5, "enabled": True},
        "12:00:00",
        last_checked_at=None,
        now_factory=fixed_now,
    )
    assert plan["title"] == "金价波动预警"
    assert plan["alert"]["type"] == "volatility"
    assert "上涨" in plan["alert"]["message"]
    assert checked_at == fixed_now()

    blocked, second_checked_at = build_volatility_alert(
        history,
        {"percent": 1.0, "minutes": 0.5, "enabled": True},
        "12:00:10",
        last_checked_at=fixed_now(),
        now_factory=lambda: fixed_now() + timedelta(seconds=30),
    )
    assert blocked is None
    assert second_checked_at == fixed_now()


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
    print("targets module checks passed.")
