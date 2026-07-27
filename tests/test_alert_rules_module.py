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
