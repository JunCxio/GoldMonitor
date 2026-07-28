import json
from datetime import datetime, timedelta

import pytest


def fixed_now():
    return datetime(2026, 7, 27, 14, 0, 0)


def test_rule_normalization_crud_and_delivery_contract():
    from goldmonitor.alert_rules import (
        AlertRuleError,
        duplicate_alert_rule,
        normalize_alert_rule,
        reset_alert_rule,
        toggle_alert_rule,
        upsert_alert_rule,
    )

    rule = normalize_alert_rule(
        {
            "kind": "watch_target",
            "name": "预算观察",
            "scope": {"mode": "rmb"},
            "condition": {"operator": "lte", "value": "688.8"},
            "delivery": {"channels": ["local", "email", "email"], "cooldown_minutes": "15"},
            "validity": {"expires_at": "2026-08-01T00:00:00"},
            "note": "等待回落",
        },
        now_factory=fixed_now,
        id_factory=lambda: "rule-fixed",
    )

    assert rule["id"] == "rule-fixed"
    assert rule["condition"]["value"] == 688.8
    assert rule["delivery"] == {"channels": ["local", "email"], "cooldown_minutes": 15}
    assert rule["state"]["status"] == "watching"

    rules, saved = upsert_alert_rule([], rule, now_factory=fixed_now)
    assert saved["id"] == "rule-fixed"
    rules, toggled = toggle_alert_rule(rules, "rule-fixed", False, now_factory=fixed_now)
    assert toggled["enabled"] is False

    rules[0]["state"] = {
        "status": "triggered",
        "triggered": True,
        "last_triggered_at": "2026-07-27T14:00:00",
        "last_trigger_value": 688.0,
        "last_evaluated_at": "",
    }
    rules, reset = reset_alert_rule(rules, "rule-fixed", now_factory=fixed_now)
    assert reset["state"]["triggered"] is False

    rules, copied = duplicate_alert_rule(
        rules,
        "rule-fixed",
        now_factory=fixed_now,
        id_factory=lambda: "rule-copy",
    )
    assert copied["id"] == "rule-copy"
    assert copied["name"] == "预算观察 副本"
    assert copied["state"]["triggered"] is False

    with pytest.raises(AlertRuleError, match="失效时间必须晚于开始时间"):
        normalize_alert_rule({
            "kind": "price_threshold",
            "scope": {"mode": "usd"},
            "condition": {"operator": "gte", "value": 2400},
            "validity": {
                "starts_at": "2026-08-01T00:00:00",
                "expires_at": "2026-07-31T00:00:00",
            },
        })


def test_rule_inspection_explains_current_value_distance_and_blockers():
    from goldmonitor.alert_rules import inspect_alert_rule, normalize_alert_rule

    price_rule = normalize_alert_rule({
        "id": "rule-price",
        "kind": "price_threshold",
        "scope": {"mode": "rmb"},
        "condition": {"operator": "gte", "value": 720},
    }, now_factory=fixed_now)
    price_inspection = inspect_alert_rule(
        price_rule,
        prices={"rmb": 714},
        now=fixed_now(),
    )
    assert price_inspection["status"] == "watching"
    assert price_inspection["reason"] == "watching"
    assert price_inspection["current_value"] == 714
    assert price_inspection["distance_to_trigger"] == 6

    loss_rule = normalize_alert_rule({
        "id": "rule-loss",
        "kind": "portfolio",
        "scope": {"position_id": "position-gold"},
        "condition": {"condition_key": "loss_percent", "value": 5},
    }, now_factory=fixed_now)
    loss_inspection = inspect_alert_rule(
        loss_rule,
        positions=[{"id": "position-gold", "unrealized_pnl_percent": -3}],
        now=fixed_now(),
    )
    assert loss_inspection["value_kind"] == "percent"
    assert loss_inspection["distance_to_trigger"] == 2

    orphaned = inspect_alert_rule(loss_rule, positions=[], now=fixed_now())
    assert orphaned["status"] == "orphaned"
    assert orphaned["reason"] == "position_missing"

    disabled_rule = dict(price_rule)
    disabled_rule["enabled"] = False
    disabled = inspect_alert_rule(disabled_rule, prices={}, now=fixed_now())
    assert disabled["status"] == "disabled"
    assert disabled["reason"] == "disabled"

    volatility_rule = normalize_alert_rule({
        "id": "rule-volatility",
        "kind": "volatility",
        "scope": {"mode": "usd"},
        "condition": {"value": 1, "window_minutes": 1},
    }, now_factory=fixed_now)
    waiting = inspect_alert_rule(
        volatility_rule,
        prices={"usd": 2300},
        price_history=[{"usd": 2300}],
        now=fixed_now(),
    )
    assert waiting["status"] == "waiting_data"
    assert waiting["reason"] == "history_insufficient"
    assert waiting["required_samples"] == 6


def test_rule_history_simulation_covers_crossings_cooldown_and_unsupported_rules():
    from goldmonitor.alert_rules import normalize_alert_rule, simulate_alert_rule

    price_rule = normalize_alert_rule({
        "id": "rule-price-simulation",
        "kind": "price_threshold",
        "scope": {"mode": "rmb"},
        "condition": {"operator": "gte", "value": 100},
    }, now_factory=fixed_now)
    price_history = [
        {"timestamp": timestamp, "rmb": value}
        for timestamp, value in (
            ("2026-07-27T09:00:00", 99),
            ("2026-07-27T09:01:00", 101),
            ("2026-07-27T09:02:00", 102),
            ("2026-07-27T09:03:00", 99),
            ("2026-07-27T09:05:00", 101),
            ("2026-07-27T09:15:00", 99),
            ("2026-07-27T09:16:00", 102),
        )
    ]
    simulated = simulate_alert_rule(
        price_rule,
        price_history,
        cooldown_minutes=10,
        period_days=7,
    )
    assert simulated["usable"] is True
    assert simulated["match_count"] == 3
    assert simulated["effective_trigger_count"] == 2
    assert simulated["suppressed_count"] == 1
    assert simulated["coverage"]["point_count"] == 7
    assert next(item for item in simulated["time_distribution"] if item["key"] == "morning")["count"] == 2

    watch_rule = normalize_alert_rule({
        "id": "rule-watch-simulation",
        "kind": "watch_target",
        "scope": {"mode": "rmb"},
        "condition": {"operator": "gte", "value": 100},
    }, now_factory=fixed_now)
    watch_simulation = simulate_alert_rule(watch_rule, price_history, period_days=7)
    assert watch_simulation["match_count"] == 3
    assert watch_simulation["effective_trigger_count"] == 1
    assert watch_simulation["trigger_policy"] == "single"

    portfolio_rule = normalize_alert_rule({
        "id": "rule-portfolio-simulation",
        "kind": "portfolio",
        "scope": {"position_id": "position-gold"},
        "condition": {"condition_key": "take_profit", "value": 760},
    }, now_factory=fixed_now)
    unsupported = simulate_alert_rule(portfolio_rule, price_history, period_days=7)
    assert unsupported["supported"] is False
    assert unsupported["reason"] == "portfolio_history_unavailable"


def test_volatility_history_simulation_requires_usable_window_resolution():
    from goldmonitor.alert_rules import normalize_alert_rule, simulate_alert_rule

    rule = normalize_alert_rule({
        "id": "rule-volatility-simulation",
        "kind": "volatility",
        "scope": {"mode": "usd"},
        "condition": {"value": 1, "window_minutes": 2},
    }, now_factory=fixed_now)
    history = [
        {"timestamp": timestamp, "usd": value}
        for timestamp, value in (
            ("2026-07-27T10:00:00", 100),
            ("2026-07-27T10:01:00", 100),
            ("2026-07-27T10:02:00", 102),
            ("2026-07-27T10:03:00", 102),
            ("2026-07-27T10:04:00", 100),
        )
    ]
    simulated = simulate_alert_rule(rule, history, cooldown_minutes=3, period_days=7)
    assert simulated["usable"] is True
    assert simulated["evaluated_count"] == 3
    assert simulated["match_count"] == 3
    assert simulated["effective_trigger_count"] == 1

    coarse = simulate_alert_rule(
        rule,
        [
            {"timestamp": "2026-07-27T10:00:00", "usd": 100},
            {"timestamp": "2026-07-27T11:00:00", "usd": 105},
        ],
        period_days=7,
    )
    assert coarse["usable"] is False
    assert coarse["reason"] == "history_resolution_too_coarse"


def test_batch_rule_updates_are_atomic_and_cover_supported_actions():
    from goldmonitor.alert_rules import AlertRuleError, batch_update_alert_rules, normalize_alert_rule

    rules = [
        normalize_alert_rule({
            "id": rule_id,
            "kind": "watch_target",
            "scope": {"mode": "rmb"},
            "condition": {"operator": "lte", "value": value},
        }, now_factory=fixed_now)
        for rule_id, value in (("rule-one", 700), ("rule-two", 690))
    ]

    disabled, affected = batch_update_alert_rules(
        rules,
        ["rule-one", "rule-two", "rule-one"],
        "disable",
        now_factory=fixed_now,
    )
    assert affected == ["rule-one", "rule-two"]
    assert all(rule["enabled"] is False for rule in disabled)

    enabled, _ = batch_update_alert_rules(disabled, affected, "enable", now_factory=fixed_now)
    assert all(rule["enabled"] is True for rule in enabled)

    enabled[0]["state"]["triggered"] = True
    reset, _ = batch_update_alert_rules(enabled, ["rule-one"], "reset", now_factory=fixed_now)
    assert reset[0]["state"]["triggered"] is False

    deleted, _ = batch_update_alert_rules(reset, ["rule-two"], "delete", now_factory=fixed_now)
    assert [rule["id"] for rule in deleted] == ["rule-one"]

    snapshot = [dict(rule) for rule in rules]
    with pytest.raises(AlertRuleError, match="已不存在"):
        batch_update_alert_rules(rules, ["rule-one", "rule-missing"], "disable", now_factory=fixed_now)
    assert rules == snapshot


def test_legacy_migration_and_compatibility_snapshots():
    from goldmonitor.alert_rules import (
        legacy_portfolio_alerts,
        legacy_threshold_state,
        legacy_watch_targets,
        migrate_legacy_rules,
    )

    rules, migration = migrate_legacy_rules(
        thresholds={
            "upper_warning_rmb": 720,
            "lower_critical_usd": 2200,
            "volatility_config": {"enabled": True, "percent": 1.5, "minutes": 15},
        },
        watch_targets=[{
            "id": "target-budget",
            "mode": "rmb",
            "direction": "fall_to",
            "price": 688.8,
            "note": "预算价",
            "enabled": True,
            "triggered": True,
            "triggered_at": "2026-07-27T12:00:00",
            "last_trigger_price": 688.0,
        }],
        portfolio_alerts=[{
            "id": "portfolio-alert-gold",
            "position_id": "position-gold",
            "enabled": True,
            "take_profit_price": 760,
            "profit_percent": 8,
            "triggered": {"take_profit": True, "profit_percent": False},
            "last_triggered_at": "2026-07-27T13:00:00",
            "last_trigger_price": 761,
        }],
        now_factory=fixed_now,
    )

    assert migration["completed"] is True
    assert migration["migrated"] == 6
    assert migration["skipped"] == 0

    threshold_state = legacy_threshold_state(rules)
    assert threshold_state["upper_warning_rmb"] == 720
    assert threshold_state["lower_critical_usd"] == 2200
    assert threshold_state["volatility_config"] == {"enabled": True, "percent": 1.5, "minutes": 15}

    targets = legacy_watch_targets(rules)
    assert targets[0]["id"] == "target-budget"
    assert targets[0]["triggered"] is True
    assert targets[0]["expires_at"] == ""

    alerts = legacy_portfolio_alerts(rules)
    assert len(alerts) == 1
    assert alerts[0]["position_id"] == "position-gold"
    assert alerts[0]["take_profit_price"] == 760
    assert alerts[0]["profit_percent"] == 8
    assert alerts[0]["triggered"]["take_profit"] is True


def test_alert_rule_store_migrates_once_and_rejects_corrupt_file(tmp_path):
    from goldmonitor.alert_rules import AlertRuleStore, AlertRuleStoreError

    path = tmp_path / "alert_rules.json"
    store = AlertRuleStore(path, now_factory=fixed_now, id_factory=lambda: "rule-store")
    migrated = store.migrate(
        thresholds={"upper_warning_rmb": 720},
        watch_targets=[],
        portfolio_alerts=[],
    )
    assert path.exists()
    assert len(migrated["items"]) == 1
    first_payload = json.loads(path.read_text(encoding="utf-8"))

    second = store.migrate(
        thresholds={"upper_warning_rmb": 999},
        watch_targets=[],
        portfolio_alerts=[],
    )
    assert second["items"][0]["condition"]["value"] == 720
    assert json.loads(path.read_text(encoding="utf-8")) == first_payload

    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(AlertRuleStoreError, match="无法读取"):
        store.load()
    with pytest.raises(AlertRuleStoreError, match="无法读取"):
        store.save([])
    assert path.read_text(encoding="utf-8") == "{broken"


def test_evaluate_rules_covers_price_watch_portfolio_volatility_and_states():
    from goldmonitor.alert_rules import evaluate_alert_rules, normalize_alert_rule

    now = fixed_now()
    rules = [
        normalize_alert_rule({
            "id": "rule-price",
            "kind": "price_threshold",
            "name": "国内金价上涨关注",
            "scope": {"mode": "rmb"},
            "condition": {"operator": "gte", "value": 720},
            "legacy": {"source": "threshold", "key": "upper_warning_rmb"},
        }, now_factory=fixed_now),
        normalize_alert_rule({
            "id": "rule-watch",
            "kind": "watch_target",
            "name": "预算价",
            "scope": {"mode": "rmb"},
            "condition": {"operator": "lte", "value": 690},
            "legacy": {"source": "watch_target", "id": "target-budget"},
        }, now_factory=fixed_now),
        normalize_alert_rule({
            "id": "rule-portfolio",
            "kind": "portfolio",
            "name": "金条止盈价",
            "scope": {"position_id": "position-gold"},
            "condition": {"condition_key": "take_profit", "value": 740},
            "legacy": {"source": "portfolio_alert", "id": "portfolio-alert-gold"},
        }, now_factory=fixed_now),
        normalize_alert_rule({
            "id": "rule-volatility",
            "kind": "volatility",
            "name": "短时波动",
            "scope": {"mode": "usd"},
            "condition": {"value": 1.0, "window_minutes": 1},
            "alert_level": "volatility",
        }, now_factory=fixed_now),
        normalize_alert_rule({
            "id": "rule-expired",
            "kind": "watch_target",
            "scope": {"mode": "usd"},
            "condition": {"operator": "gte", "value": 2500},
            "validity": {"expires_at": (now - timedelta(minutes=1)).isoformat()},
        }, now_factory=fixed_now),
        normalize_alert_rule({
            "id": "rule-orphaned",
            "kind": "portfolio",
            "scope": {"position_id": "position-missing"},
            "condition": {"condition_key": "stop_loss", "value": 650},
        }, now_factory=fixed_now),
    ]
    history = [
        {"usd": 2300 + index * 5, "rmb": 680 + index, "timestamp": (now - timedelta(seconds=(6 - index) * 10)).isoformat()}
        for index in range(6)
    ]
    positions = [{
        "id": "position-gold",
        "name": "金条",
        "mode": "rmb",
        "current_price": 742,
        "average_cost": 700,
        "unrealized_pnl_percent": 6,
    }]

    next_rules, triggers = evaluate_alert_rules(
        rules,
        prices={"rmb": 688, "usd": history[-1]["usd"]},
        price_history=history,
        positions=positions,
        now=now,
    )
    triggered_ids = {item["rule"]["id"] for item in triggers}
    assert triggered_ids == {"rule-watch", "rule-portfolio", "rule-volatility"}

    alerts_by_rule = {item["alert"]["rule_id"]: item["alert"] for item in triggers}
    assert alerts_by_rule["rule-watch"]["watch_target_id"] == "target-budget"
    assert alerts_by_rule["rule-portfolio"]["portfolio_position_id"] == "position-gold"
    assert alerts_by_rule["rule-volatility"]["type"] == "volatility"

    state_by_id = {item["id"]: item["state"]["status"] for item in next_rules}
    assert state_by_id["rule-price"] == "watching"
    assert state_by_id["rule-expired"] == "expired"
    assert state_by_id["rule-orphaned"] == "orphaned"

    repeated_rules, repeated = evaluate_alert_rules(
        next_rules,
        prices={"rmb": 688, "usd": history[-1]["usd"]},
        price_history=history,
        positions=positions,
        now=now + timedelta(seconds=10),
    )
    assert repeated == []
    assert next(item for item in repeated_rules if item["id"] == "rule-watch")["state"]["triggered"] is True
