import json
import math
import os
import secrets
from bisect import bisect_left
from datetime import datetime, timedelta

from goldmonitor.time_utils import to_local_naive


ALERT_RULE_SCHEMA_VERSION = 1
ALERT_RULE_KINDS = {"price_threshold", "volatility", "watch_target", "portfolio"}
ALERT_RULE_CHANNELS = {"local", "email", "webhook"}
ALERT_RULE_BATCH_ACTIONS = {"enable", "disable", "reset", "delete"}
ALERT_RULE_SIMULATION_KINDS = {"price_threshold", "volatility", "watch_target", "portfolio"}
ALERT_RULE_SIMULATION_PERIODS = {7, 30, 90}
ALERT_RULE_STATUSES = {
    "watching",
    "triggered",
    "expired",
    "disabled",
    "waiting_data",
    "orphaned",
    "scheduled",
}
PORTFOLIO_CONDITIONS = {
    "take_profit",
    "stop_loss",
    "profit_percent",
    "loss_percent",
    "near_cost",
}
THRESHOLD_DEFINITIONS = {
    "upper_warning": {"operator": "gte", "level": "warning", "label": "上涨关注"},
    "upper_critical": {"operator": "gte", "level": "critical", "label": "上涨警告"},
    "lower_warning": {"operator": "lte", "level": "warning", "label": "下跌关注"},
    "lower_critical": {"operator": "lte", "level": "critical", "label": "下跌警告"},
}
PORTFOLIO_FIELD_BY_CONDITION = {
    "take_profit": "take_profit_price",
    "stop_loss": "stop_loss_price",
    "profit_percent": "profit_percent",
    "loss_percent": "loss_percent",
    "near_cost": "near_cost_percent",
}
PORTFOLIO_LABELS = {
    "take_profit": "止盈价",
    "stop_loss": "止损价",
    "profit_percent": "浮盈比例",
    "loss_percent": "浮亏比例",
    "near_cost": "接近成本价",
}


class AlertRuleError(ValueError):
    pass


class AlertRuleStoreError(OSError):
    pass


def generate_alert_rule_id():
    return "rule-" + secrets.token_hex(8)


def _now_iso(now_factory=None):
    now = now_factory() if callable(now_factory) else datetime.now()
    return now.isoformat(timespec="seconds")


def _clean_text(value, limit):
    text = str(value or "").strip()
    return text[:limit]


def _safe_identifier(value):
    text = str(value or "").strip()
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    return text if text and all(character in allowed for character in text) else ""


def _coerce_bool(value, default=True):
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    if isinstance(value, (int, float)):
        return bool(value)
    lowered = str(value).strip().lower()
    if lowered in {"true", "1", "yes", "on"}:
        return True
    if lowered in {"false", "0", "no", "off", ""}:
        return False
    return bool(default)


def _positive_number(value, field_label="条件值"):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise AlertRuleError(f"{field_label}格式无效") from exc
    if not math.isfinite(number) or number <= 0:
        raise AlertRuleError(f"{field_label}必须大于 0")
    return number


def _integer(value, default, minimum, maximum):
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        number = int(default)
    return max(minimum, min(maximum, number))


def _parse_iso(value):
    text = str(value or "").strip()
    if not text:
        return None
    return to_local_naive(text)


def _normalize_iso(value, field_label):
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = _parse_iso(text)
    if parsed is None:
        raise AlertRuleError(f"{field_label}格式无效")
    return parsed.isoformat(timespec="seconds")


def _normalize_delivery(raw, existing=None):
    existing = existing if isinstance(existing, dict) else {}
    raw = raw if isinstance(raw, dict) else {}
    raw_channels = raw.get("channels", existing.get("channels", "inherit"))
    if raw_channels == "inherit" or raw_channels is None:
        channels = "inherit"
    elif isinstance(raw_channels, list):
        channels = []
        for channel in raw_channels:
            channel = str(channel or "").strip().lower()
            if channel in ALERT_RULE_CHANNELS and channel not in channels:
                channels.append(channel)
    else:
        raise AlertRuleError("通知渠道格式无效")

    raw_cooldown = raw.get("cooldown_minutes", existing.get("cooldown_minutes", "inherit"))
    if raw_cooldown == "inherit" or raw_cooldown is None or raw_cooldown == "":
        cooldown = "inherit"
    else:
        try:
            cooldown = int(float(raw_cooldown))
        except (TypeError, ValueError) as exc:
            raise AlertRuleError("冷却时间格式无效") from exc
        if cooldown < 0 or cooldown > 1440:
            raise AlertRuleError("冷却时间必须在 0 到 1440 分钟之间")
    return {"channels": channels, "cooldown_minutes": cooldown}


def _normalize_validity(raw, existing=None):
    existing = existing if isinstance(existing, dict) else {}
    raw = raw if isinstance(raw, dict) else {}
    starts_at = _normalize_iso(raw.get("starts_at", existing.get("starts_at", "")), "开始时间")
    expires_at = _normalize_iso(raw.get("expires_at", existing.get("expires_at", "")), "失效时间")
    starts = _parse_iso(starts_at)
    expires = _parse_iso(expires_at)
    if starts and expires and expires <= starts:
        raise AlertRuleError("失效时间必须晚于开始时间")
    return {"starts_at": starts_at, "expires_at": expires_at}


def _normalize_state(raw, existing=None):
    existing = existing if isinstance(existing, dict) else {}
    raw = raw if isinstance(raw, dict) else {}
    status = str(raw.get("status", existing.get("status", "watching")) or "watching")
    if status not in ALERT_RULE_STATUSES:
        status = "watching"
    last_trigger_value = raw.get("last_trigger_value", existing.get("last_trigger_value"))
    if last_trigger_value in (None, ""):
        last_trigger_value = None
    else:
        try:
            last_trigger_value = float(last_trigger_value)
        except (TypeError, ValueError):
            last_trigger_value = None
    return {
        "status": status,
        "triggered": _coerce_bool(raw.get("triggered", existing.get("triggered", False)), False),
        "last_triggered_at": str(
            raw.get("last_triggered_at", existing.get("last_triggered_at", "")) or ""
        ).strip(),
        "last_trigger_value": last_trigger_value,
        "last_evaluated_at": str(
            raw.get("last_evaluated_at", existing.get("last_evaluated_at", "")) or ""
        ).strip(),
    }


def _normalize_scope(kind, raw, existing=None):
    existing = existing if isinstance(existing, dict) else {}
    raw = raw if isinstance(raw, dict) else {}
    mode = str(raw.get("mode", existing.get("mode", "rmb")) or "").strip().lower()
    position_id = _safe_identifier(raw.get("position_id", existing.get("position_id", "")))
    if kind in {"price_threshold", "volatility", "watch_target"} and mode not in {"rmb", "usd"}:
        raise AlertRuleError("规则单位无效")
    if kind == "portfolio" and not position_id:
        raise AlertRuleError("持仓规则缺少关联持仓")
    return {"mode": mode if mode in {"rmb", "usd"} else "rmb", "position_id": position_id or None}


def _normalize_condition(kind, raw, existing=None):
    existing = existing if isinstance(existing, dict) else {}
    raw = raw if isinstance(raw, dict) else {}
    operator = str(raw.get("operator", existing.get("operator", "")) or "").strip().lower()
    condition_key = str(raw.get("condition_key", existing.get("condition_key", "")) or "").strip().lower()
    value = _positive_number(raw.get("value", existing.get("value")))
    window_minutes = raw.get("window_minutes", existing.get("window_minutes"))

    if kind in {"price_threshold", "watch_target"}:
        if operator not in {"gte", "lte"}:
            raise AlertRuleError("价格规则方向无效")
        window_minutes = None
        condition_key = ""
    elif kind == "volatility":
        operator = "abs_change_gte"
        window_minutes = _integer(window_minutes, 10, 1, 1440)
        condition_key = ""
    elif kind == "portfolio":
        if condition_key not in PORTFOLIO_CONDITIONS:
            raise AlertRuleError("持仓规则条件无效")
        operator = {
            "take_profit": "gte",
            "stop_loss": "lte",
            "profit_percent": "gte",
            "loss_percent": "lte",
            "near_cost": "within",
        }[condition_key]
        window_minutes = None
    return {
        "operator": operator,
        "value": value,
        "window_minutes": window_minutes,
        "condition_key": condition_key or None,
    }


def normalize_alert_rule(item, existing=None, now_factory=None, id_factory=None):
    if not isinstance(item, dict):
        raise AlertRuleError("预警规则格式无效")
    existing = existing if isinstance(existing, dict) else {}
    id_factory = id_factory or generate_alert_rule_id
    now = _now_iso(now_factory)
    raw_id = item.get("id", existing.get("id"))
    rule_id = _safe_identifier(raw_id) or id_factory()
    if not str(rule_id).startswith("rule-"):
        rule_id = "rule-" + str(rule_id)
    kind = str(item.get("kind", existing.get("kind", "")) or "").strip().lower()
    if kind not in ALERT_RULE_KINDS:
        raise AlertRuleError("预警规则类型无效")
    scope = _normalize_scope(kind, item.get("scope"), existing.get("scope"))
    condition = _normalize_condition(kind, item.get("condition"), existing.get("condition"))
    name = _clean_text(item.get("name", existing.get("name", "")), 80)
    if not name:
        name = default_rule_name(kind, scope, condition)
    legacy = item.get("legacy", existing.get("legacy", {}))
    legacy = dict(legacy) if isinstance(legacy, dict) else {}
    normalized = {
        "id": rule_id,
        "kind": kind,
        "name": name,
        "enabled": _coerce_bool(item.get("enabled", existing.get("enabled", True)), True),
        "scope": scope,
        "condition": condition,
        "delivery": _normalize_delivery(item.get("delivery"), existing.get("delivery")),
        "validity": _normalize_validity(item.get("validity"), existing.get("validity")),
        "state": _normalize_state(item.get("state"), existing.get("state")),
        "note": _clean_text(item.get("note", existing.get("note", "")), 200),
        "alert_level": str(item.get("alert_level", existing.get("alert_level", "warning")) or "warning"),
        "created_at": str(item.get("created_at") or existing.get("created_at") or now),
        "updated_at": now if existing else str(item.get("updated_at") or now),
        "legacy": legacy,
    }
    if normalized["alert_level"] not in {"warning", "critical", "volatility"}:
        normalized["alert_level"] = "warning"
    if existing and (
        existing.get("kind") != kind
        or existing.get("scope") != scope
        or existing.get("condition") != condition
    ):
        normalized["state"] = {
            "status": "watching",
            "triggered": False,
            "last_triggered_at": "",
            "last_trigger_value": None,
            "last_evaluated_at": "",
        }
    return normalized


def normalize_alert_rules(items, now_factory=None, id_factory=None):
    if not isinstance(items, list):
        return [], 0
    normalized = []
    invalid_count = 0
    seen = set()
    for item in items:
        try:
            rule = normalize_alert_rule(item, now_factory=now_factory, id_factory=id_factory)
        except AlertRuleError:
            invalid_count += 1
            continue
        if rule["id"] in seen:
            invalid_count += 1
            continue
        seen.add(rule["id"])
        normalized.append(rule)
    return normalized, invalid_count


def default_rule_name(kind, scope, condition):
    mode_label = "国际金价" if scope.get("mode") == "usd" else "国内金价"
    if kind == "price_threshold":
        direction = "上涨" if condition.get("operator") == "gte" else "下跌"
        return f"{mode_label}{direction}提醒"
    if kind == "volatility":
        return f"{condition.get('window_minutes') or 10} 分钟波动提醒"
    if kind == "watch_target":
        direction = "上涨至" if condition.get("operator") == "gte" else "下跌至"
        return f"{mode_label}{direction}目标价"
    condition_key = condition.get("condition_key")
    return f"持仓{PORTFOLIO_LABELS.get(condition_key, '提醒')}"


def _deterministic_rule_id(*parts):
    safe_parts = []
    for part in parts:
        cleaned = "".join(character if character.isalnum() or character in "_-" else "-" for character in str(part or ""))
        safe_parts.append(cleaned.strip("-") or "item")
    return "rule-" + "-".join(safe_parts)


def _legacy_state(triggered, triggered_at="", trigger_value=None):
    return {
        "status": "triggered" if triggered else "watching",
        "triggered": bool(triggered),
        "last_triggered_at": str(triggered_at or ""),
        "last_trigger_value": trigger_value,
        "last_evaluated_at": "",
    }


def migrate_legacy_rules(thresholds=None, watch_targets=None, portfolio_alerts=None, now_factory=None):
    thresholds = thresholds if isinstance(thresholds, dict) else {}
    watch_targets = watch_targets if isinstance(watch_targets, list) else []
    portfolio_alerts = portfolio_alerts if isinstance(portfolio_alerts, list) else []
    rules = []
    skipped = []

    for mode in ("usd", "rmb"):
        for threshold_type, definition in THRESHOLD_DEFINITIONS.items():
            key = f"{threshold_type}_{mode}"
            value = thresholds.get(key)
            if value in (None, ""):
                continue
            try:
                rules.append(normalize_alert_rule({
                    "id": _deterministic_rule_id("threshold", key),
                    "kind": "price_threshold",
                    "name": ("国际金价" if mode == "usd" else "国内金价") + definition["label"],
                    "enabled": True,
                    "scope": {"mode": mode},
                    "condition": {"operator": definition["operator"], "value": value},
                    "alert_level": definition["level"],
                    "legacy": {"source": "threshold", "key": key},
                }, now_factory=now_factory))
            except AlertRuleError as exc:
                skipped.append({"source": "threshold", "id": key, "reason": str(exc)})

    volatility = thresholds.get("volatility_config")
    if isinstance(volatility, dict) and volatility.get("enabled") and volatility.get("percent") not in (None, ""):
        try:
            rules.append(normalize_alert_rule({
                "id": _deterministic_rule_id("volatility", "usd"),
                "kind": "volatility",
                "name": "国际金价波动提醒",
                "enabled": True,
                "scope": {"mode": "usd"},
                "condition": {
                    "operator": "abs_change_gte",
                    "value": volatility.get("percent"),
                    "window_minutes": volatility.get("minutes", 10),
                },
                "alert_level": "volatility",
                "legacy": {"source": "volatility", "key": "volatility_config"},
            }, now_factory=now_factory))
        except AlertRuleError as exc:
            skipped.append({"source": "volatility", "id": "volatility_config", "reason": str(exc)})

    for target in watch_targets:
        if not isinstance(target, dict):
            skipped.append({"source": "watch_target", "id": "", "reason": "观察项格式无效"})
            continue
        target_id = _safe_identifier(target.get("id")) or secrets.token_hex(6)
        direction = target.get("direction")
        operator = "gte" if direction == "rise_to" else "lte" if direction == "fall_to" else ""
        try:
            rules.append(normalize_alert_rule({
                "id": _deterministic_rule_id("watch", target_id),
                "kind": "watch_target",
                "name": target.get("note") or "目标价观察",
                "enabled": target.get("enabled", True),
                "scope": {"mode": target.get("mode")},
                "condition": {"operator": operator, "value": target.get("price")},
                "state": _legacy_state(
                    target.get("triggered"),
                    target.get("triggered_at"),
                    target.get("last_trigger_price"),
                ),
                "note": target.get("note", ""),
                "created_at": target.get("created_at", ""),
                "updated_at": target.get("updated_at", ""),
                "legacy": {"source": "watch_target", "id": target_id},
            }, now_factory=now_factory))
        except AlertRuleError as exc:
            skipped.append({"source": "watch_target", "id": target_id, "reason": str(exc)})

    for legacy_alert in portfolio_alerts:
        if not isinstance(legacy_alert, dict):
            skipped.append({"source": "portfolio_alert", "id": "", "reason": "持仓提醒格式无效"})
            continue
        group_id = _safe_identifier(legacy_alert.get("id")) or secrets.token_hex(6)
        position_id = _safe_identifier(legacy_alert.get("position_id"))
        triggered_map = legacy_alert.get("triggered") if isinstance(legacy_alert.get("triggered"), dict) else {}
        for condition_key, field_name in PORTFOLIO_FIELD_BY_CONDITION.items():
            value = legacy_alert.get(field_name)
            if value in (None, ""):
                continue
            triggered = bool(triggered_map.get(condition_key))
            try:
                rules.append(normalize_alert_rule({
                    "id": _deterministic_rule_id("portfolio", group_id, condition_key),
                    "kind": "portfolio",
                    "name": "持仓" + PORTFOLIO_LABELS[condition_key],
                    "enabled": legacy_alert.get("enabled", True),
                    "scope": {"mode": "rmb", "position_id": position_id},
                    "condition": {"condition_key": condition_key, "value": value},
                    "state": _legacy_state(
                        triggered,
                        legacy_alert.get("last_triggered_at") if triggered else "",
                        legacy_alert.get("last_trigger_price") if triggered else None,
                    ),
                    "note": legacy_alert.get("note", ""),
                    "created_at": legacy_alert.get("created_at", ""),
                    "updated_at": legacy_alert.get("updated_at", ""),
                    "legacy": {"source": "portfolio_alert", "id": group_id, "condition": condition_key},
                }, now_factory=now_factory))
            except AlertRuleError as exc:
                skipped.append({"source": "portfolio_alert", "id": group_id, "reason": str(exc)})

    rules, duplicate_count = normalize_alert_rules(rules, now_factory=now_factory)
    summary = {
        "completed": True,
        "source_version": "1.0.7",
        "migrated": len(rules),
        "skipped": len(skipped) + duplicate_count,
        "issues": skipped,
        "migrated_at": _now_iso(now_factory),
    }
    return rules, summary


def legacy_threshold_state(rules):
    thresholds = {
        f"{threshold_type}_{mode}": None
        for mode in ("usd", "rmb")
        for threshold_type in THRESHOLD_DEFINITIONS
    }
    volatility = {"percent": None, "minutes": 10, "enabled": False}
    for rule in list(rules or []):
        if not isinstance(rule, dict):
            continue
        if rule.get("kind") == "price_threshold":
            key = str((rule.get("legacy") or {}).get("key") or "")
            if key in thresholds and rule.get("enabled"):
                thresholds[key] = (rule.get("condition") or {}).get("value")
        elif rule.get("kind") == "volatility":
            condition = rule.get("condition") or {}
            volatility = {
                "percent": condition.get("value"),
                "minutes": condition.get("window_minutes") or 10,
                "enabled": bool(rule.get("enabled")),
            }
    thresholds["volatility_config"] = volatility
    return thresholds


def legacy_watch_targets(rules):
    items = []
    for rule in list(rules or []):
        if not isinstance(rule, dict) or rule.get("kind") != "watch_target":
            continue
        scope = rule.get("scope") or {}
        condition = rule.get("condition") or {}
        state = rule.get("state") or {}
        legacy = rule.get("legacy") or {}
        items.append({
            "id": legacy.get("id") or rule.get("id"),
            "rule_id": rule.get("id"),
            "mode": scope.get("mode"),
            "direction": "rise_to" if condition.get("operator") == "gte" else "fall_to",
            "price": condition.get("value"),
            "note": rule.get("note", ""),
            "enabled": bool(rule.get("enabled")),
            "triggered": bool(state.get("triggered")),
            "created_at": rule.get("created_at", ""),
            "updated_at": rule.get("updated_at", ""),
            "triggered_at": state.get("last_triggered_at", "") if state.get("triggered") else "",
            "last_trigger_price": state.get("last_trigger_value") if state.get("triggered") else None,
            "expires_at": (rule.get("validity") or {}).get("expires_at", ""),
        })
    return items


def legacy_portfolio_alerts(rules):
    groups = {}
    for rule in list(rules or []):
        if not isinstance(rule, dict) or rule.get("kind") != "portfolio":
            continue
        legacy = rule.get("legacy") or {}
        scope = rule.get("scope") or {}
        condition = rule.get("condition") or {}
        condition_key = condition.get("condition_key")
        field_name = PORTFOLIO_FIELD_BY_CONDITION.get(condition_key)
        if not field_name:
            continue
        group_id = legacy.get("id") or f"portfolio-alert-{scope.get('position_id') or 'unknown'}"
        group = groups.setdefault(group_id, {
            "id": group_id,
            "position_id": scope.get("position_id"),
            "enabled": False,
            "take_profit_price": None,
            "stop_loss_price": None,
            "profit_percent": None,
            "loss_percent": None,
            "near_cost_percent": None,
            "note": "",
            "created_at": rule.get("created_at", ""),
            "updated_at": rule.get("updated_at", ""),
            "last_triggered_at": "",
            "last_trigger_price": None,
            "last_trigger_condition": "",
            "triggered": {key: False for key in PORTFOLIO_CONDITIONS},
            "rule_ids": {},
        })
        group[field_name] = condition.get("value")
        group["enabled"] = group["enabled"] or bool(rule.get("enabled"))
        group["note"] = group["note"] or rule.get("note", "")
        group["rule_ids"][condition_key] = rule.get("id")
        state = rule.get("state") or {}
        if state.get("triggered"):
            group["triggered"][condition_key] = True
            group["last_triggered_at"] = state.get("last_triggered_at", "")
            group["last_trigger_price"] = state.get("last_trigger_value")
            group["last_trigger_condition"] = condition_key
    return list(groups.values())


def _rule_runtime_status(rule, now, positions_by_id=None, prices=None):
    if not rule.get("enabled"):
        return "disabled"
    validity = rule.get("validity") or {}
    starts_at = _parse_iso(validity.get("starts_at"))
    expires_at = _parse_iso(validity.get("expires_at"))
    if starts_at and now < starts_at:
        return "scheduled"
    if expires_at and now >= expires_at:
        return "expired"
    if rule.get("kind") == "portfolio":
        position_id = (rule.get("scope") or {}).get("position_id")
        if position_id not in (positions_by_id or {}):
            return "orphaned"
    elif rule.get("kind") in {"price_threshold", "watch_target"}:
        mode = (rule.get("scope") or {}).get("mode")
        if (prices or {}).get(mode) is None:
            return "waiting_data"
    if (rule.get("state") or {}).get("triggered"):
        return "triggered"
    return "watching"


def _condition_met(operator, current, target):
    if current is None or target is None:
        return False
    if operator == "gte":
        return current >= target
    if operator == "lte":
        return current <= target
    return False


def _position_value(position, condition_key):
    if condition_key in {"take_profit", "stop_loss"}:
        return position.get("current_price")
    if condition_key in {"profit_percent", "loss_percent"}:
        return position.get("unrealized_pnl_percent", position.get("pnl_percent"))
    if condition_key == "near_cost":
        current_price = position.get("current_price")
        average_cost = position.get("average_cost", position.get("entry_price"))
        try:
            current_price = float(current_price)
            average_cost = float(average_cost)
        except (TypeError, ValueError):
            return None
        if average_cost <= 0:
            return None
        return abs(current_price - average_cost) / average_cost * 100
    return None


def _portfolio_condition_met(condition_key, current, target):
    if current is None:
        return False
    if condition_key in {"take_profit", "profit_percent"}:
        return current >= target
    if condition_key == "stop_loss":
        return current <= target
    if condition_key == "loss_percent":
        return current <= -target
    if condition_key == "near_cost":
        return current <= target
    return False


def _finite_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _distance_to_trigger(rule, current, target):
    current = _finite_number(current)
    target = _finite_number(target)
    if current is None or target is None:
        return None
    kind = rule.get("kind")
    condition = rule.get("condition") or {}
    if kind == "volatility":
        return max(0.0, target - current)
    if kind == "portfolio":
        condition_key = condition.get("condition_key")
        if condition_key in {"take_profit", "profit_percent"}:
            return max(0.0, target - current)
        if condition_key == "loss_percent":
            return max(0.0, current + target)
        return max(0.0, current - target)
    if condition.get("operator") == "gte":
        return max(0.0, target - current)
    return max(0.0, current - target)


def inspect_alert_rule(rule, positions=None, prices=None, price_history=None, now=None):
    now = now or datetime.now()
    positions = [item for item in list(positions or []) if isinstance(item, dict)]
    positions_by_id = {item.get("id"): item for item in positions if item.get("id")}
    prices = prices if isinstance(prices, dict) else {}
    scope = rule.get("scope") or {}
    condition = rule.get("condition") or {}
    kind = rule.get("kind")
    target_value = _finite_number(condition.get("value"))
    current_value = None
    source_value = None
    sample_count = 0
    required_samples = 0
    condition_met = False
    status = _rule_runtime_status(rule, now, positions_by_id=positions_by_id, prices=prices)
    reason = status
    value_kind = "price"

    if kind in {"price_threshold", "watch_target"}:
        current_value = _finite_number(prices.get(scope.get("mode")))
        condition_met = _condition_met(condition.get("operator"), current_value, target_value)
        if current_value is None and status not in {"disabled", "scheduled", "expired"}:
            status = "waiting_data"
            reason = "price_missing"
    elif kind == "portfolio":
        position = positions_by_id.get(scope.get("position_id"))
        condition_key = condition.get("condition_key")
        value_kind = "percent" if condition_key in {"profit_percent", "loss_percent", "near_cost"} else "price"
        if position:
            current_value = _finite_number(_position_value(position, condition_key))
            condition_met = _portfolio_condition_met(condition_key, current_value, target_value)
            if current_value is None and status not in {"disabled", "scheduled", "expired"}:
                status = "waiting_data"
                reason = "position_data_missing"
        elif status == "orphaned":
            reason = "position_missing"
    elif kind == "volatility":
        value_kind = "percent"
        window_minutes = condition.get("window_minutes") or 10
        required_samples = max(2, int(window_minutes * 60 / 10))
        values = _volatility_values(price_history, scope.get("mode"), required_samples)
        sample_count = len(values)
        if len(values) >= required_samples and values[0] != 0:
            current_value = abs((values[-1] - values[0]) / values[0] * 100)
            source_value = values[-1]
            condition_met = current_value >= target_value
        elif status not in {"disabled", "scheduled", "expired"}:
            status = "waiting_data"
            reason = "history_insufficient"

    if reason not in {"price_missing", "position_missing", "position_data_missing", "history_insufficient"}:
        if status == "triggered":
            reason = "triggered_condition_met" if condition_met else "triggered_latched"
        elif status in {"disabled", "scheduled", "expired", "orphaned", "waiting_data"}:
            reason = status
        elif condition_met:
            reason = "condition_met"
        else:
            reason = "watching"

    distance = _distance_to_trigger(rule, current_value, target_value)
    distance_percent = None
    if distance is not None and target_value not in (None, 0):
        distance_percent = distance / abs(target_value) * 100
    return {
        "status": status,
        "reason": reason,
        "value_kind": value_kind,
        "current_value": round(current_value, 6) if current_value is not None else None,
        "source_value": round(source_value, 6) if source_value is not None else None,
        "target_value": round(target_value, 6) if target_value is not None else None,
        "distance_to_trigger": round(distance, 6) if distance is not None else None,
        "distance_percent": round(distance_percent, 4) if distance_percent is not None else None,
        "condition_met": bool(condition_met),
        "sample_count": sample_count,
        "required_samples": required_samples,
        "last_evaluated_at": str((rule.get("state") or {}).get("last_evaluated_at") or ""),
    }


def _simulation_points(price_history, mode):
    field = "usd" if mode == "usd" else "rmb"
    points_by_timestamp = {}
    for item in list(price_history or []):
        if not isinstance(item, dict):
            continue
        timestamp = _parse_iso(item.get("timestamp"))
        value = _finite_number(item.get(field))
        if timestamp is None or value is None:
            continue
        points_by_timestamp[timestamp] = value
    return sorted(points_by_timestamp.items(), key=lambda item: item[0])


def _simulation_interval_seconds(points):
    intervals = sorted(
        (points[index][0] - points[index - 1][0]).total_seconds()
        for index in range(1, len(points))
        if points[index][0] > points[index - 1][0]
    )
    if not intervals:
        return 0
    middle = len(intervals) // 2
    if len(intervals) % 2:
        return int(round(intervals[middle]))
    return int(round((intervals[middle - 1] + intervals[middle]) / 2))


def _simulation_interval_label(seconds):
    seconds = max(0, int(seconds or 0))
    if seconds < 60:
        return f"{seconds} 秒" if seconds else "未知"
    if seconds < 3600:
        return f"{max(1, round(seconds / 60))} 分钟"
    if seconds < 86400:
        return f"{max(1, round(seconds / 3600))} 小时"
    return f"{max(1, round(seconds / 86400))} 天"


def _simulation_event(timestamp, value, change_percent=None, details=None):
    event = {
        "timestamp": timestamp.isoformat(timespec="seconds"),
        "value": round(float(value), 6),
    }
    if change_percent is not None:
        event["change_percent"] = round(float(change_percent), 4)
    if isinstance(details, dict):
        for key in (
            "current_price",
            "average_cost",
            "quantity",
            "unrealized_pnl_percent",
            "near_cost_percent",
        ):
            number = _finite_number(details.get(key))
            if number is not None:
                event[key] = round(number, 6)
        mode = str(details.get("mode") or "").strip().lower()
        if mode in {"rmb", "usd"}:
            event["mode"] = mode
    return event


def _portfolio_simulation_entries(portfolio_history, condition_key):
    value_field = {
        "take_profit": "current_price",
        "stop_loss": "current_price",
        "profit_percent": "unrealized_pnl_percent",
        "loss_percent": "unrealized_pnl_percent",
        "near_cost": "near_cost_percent",
    }.get(condition_key)
    entries_by_timestamp = {}
    if not value_field:
        return []
    for item in list((portfolio_history or {}).get("points") or []):
        if not isinstance(item, dict):
            continue
        timestamp = _parse_iso(item.get("timestamp"))
        if timestamp is None:
            continue
        value = _finite_number(item.get(value_field)) if item.get("active") else None
        entries_by_timestamp[timestamp] = {
            "timestamp": timestamp,
            "value": value,
            "details": dict(item),
        }
    return sorted(entries_by_timestamp.values(), key=lambda item: item["timestamp"])


def _apply_simulation_cooldown(events, cooldown_minutes):
    cooldown = timedelta(minutes=max(0, int(cooldown_minutes or 0)))
    accepted = []
    last_triggered_at = None
    for event in events:
        timestamp = _parse_iso(event.get("timestamp"))
        if timestamp is None:
            continue
        if last_triggered_at is not None and timestamp - last_triggered_at < cooldown:
            continue
        accepted.append(event)
        last_triggered_at = timestamp
    return accepted


def _simulation_time_distribution(events):
    buckets = [
        {"key": "overnight", "label": "凌晨", "start_hour": 0, "end_hour": 6, "count": 0},
        {"key": "morning", "label": "上午", "start_hour": 6, "end_hour": 12, "count": 0},
        {"key": "afternoon", "label": "下午", "start_hour": 12, "end_hour": 18, "count": 0},
        {"key": "evening", "label": "晚间", "start_hour": 18, "end_hour": 24, "count": 0},
    ]
    for event in events:
        timestamp = _parse_iso(event.get("timestamp"))
        if timestamp is None:
            continue
        for bucket in buckets:
            if bucket["start_hour"] <= timestamp.hour < bucket["end_hour"]:
                bucket["count"] += 1
                break
    return [
        {"key": bucket["key"], "label": bucket["label"], "count": bucket["count"]}
        for bucket in buckets
    ]


def simulate_alert_rule(
    rule,
    price_history=None,
    cooldown_minutes=0,
    period_days=30,
    portfolio_history=None,
):
    if not isinstance(rule, dict):
        raise AlertRuleError("预警规则格式无效")
    try:
        period_days = int(period_days)
    except (TypeError, ValueError) as exc:
        raise AlertRuleError("历史模拟范围无效") from exc
    if period_days not in ALERT_RULE_SIMULATION_PERIODS:
        raise AlertRuleError("历史模拟仅支持 7、30 或 90 天")
    try:
        cooldown_minutes = int(float(cooldown_minutes or 0))
    except (TypeError, ValueError) as exc:
        raise AlertRuleError("冷却时间格式无效") from exc
    cooldown_minutes = max(0, min(1440, cooldown_minutes))

    kind = str(rule.get("kind") or "")
    mode = str((rule.get("scope") or {}).get("mode") or "rmb")
    response = {
        "supported": kind in ALERT_RULE_SIMULATION_KINDS,
        "usable": False,
        "reason": "",
        "message": "",
        "rule_kind": kind,
        "mode": mode,
        "period_days": period_days,
        "cooldown_minutes": cooldown_minutes,
        "trigger_policy": "single" if kind in {"watch_target", "portfolio"} else "repeat",
        "evaluated_count": 0,
        "match_count": 0,
        "effective_trigger_count": 0,
        "suppressed_count": 0,
        "recent_triggers": [],
        "time_distribution": _simulation_time_distribution([]),
        "portfolio": {},
        "coverage": {
            "point_count": 0,
            "from": "",
            "to": "",
            "actual_days": 0,
            "sampling_interval_seconds": 0,
            "sampling_interval_label": "未知",
            "gap_count": 0,
            "partial": True,
        },
    }
    if not response["supported"]:
        response.update({
            "reason": "rule_kind_unsupported",
            "message": "当前规则类型不支持历史模拟。",
        })
        return response

    portfolio_entries = []
    if kind == "portfolio":
        portfolio_history = portfolio_history if isinstance(portfolio_history, dict) else {}
        response["portfolio"] = {
            "position_id": str(portfolio_history.get("position_id") or ""),
            "position_name": str(portfolio_history.get("position_name") or ""),
            "transaction_count": int(portfolio_history.get("transaction_count") or 0),
            "dated_transaction_count": int(portfolio_history.get("dated_transaction_count") or 0),
            "unknown_date_count": int(portfolio_history.get("unknown_date_count") or 0),
        }
        actual_mode = str(portfolio_history.get("mode") or "").strip().lower()
        if actual_mode in {"rmb", "usd"}:
            mode = actual_mode
            response["mode"] = actual_mode
        if not portfolio_history.get("position_found"):
            response.update({
                "reason": "portfolio_position_history_missing",
                "message": "关联持仓没有可用于历史回放的流水。",
            })
            return response
        if response["portfolio"]["unknown_date_count"]:
            response.update({
                "reason": "portfolio_transaction_time_missing",
                "message": "关联持仓存在缺少交易日期的流水，无法可靠还原历史持仓。",
            })
            return response
        portfolio_entries = _portfolio_simulation_entries(
            portfolio_history,
            (rule.get("condition") or {}).get("condition_key"),
        )
        points = [
            (entry["timestamp"], entry["value"])
            for entry in portfolio_entries
            if entry["value"] is not None
        ]
    else:
        points = _simulation_points(price_history, mode)
    interval_seconds = _simulation_interval_seconds(points)
    if points:
        actual_seconds = max(0, (points[-1][0] - points[0][0]).total_seconds())
        gap_threshold = max(interval_seconds * 3, 15 * 60) if interval_seconds else 15 * 60
        gap_count = sum(
            1 for index in range(1, len(points))
            if (points[index][0] - points[index - 1][0]).total_seconds() > gap_threshold
        )
        response["coverage"] = {
            "point_count": len(points),
            "from": points[0][0].isoformat(timespec="seconds"),
            "to": points[-1][0].isoformat(timespec="seconds"),
            "actual_days": round(actual_seconds / 86400, 2),
            "sampling_interval_seconds": interval_seconds,
            "sampling_interval_label": _simulation_interval_label(interval_seconds),
            "gap_count": gap_count,
            "partial": actual_seconds < period_days * 86400 * 0.8,
        }
    if len(points) < 2:
        response.update({
            "reason": "portfolio_history_insufficient" if kind == "portfolio" else "history_insufficient",
            "message": (
                "可用历史持仓估值不足，至少需要两个有效估值点。"
                if kind == "portfolio"
                else "可用历史行情不足，至少需要两个有效价格点。"
            ),
        })
        return response

    condition = rule.get("condition") or {}
    target_value = _finite_number(condition.get("value"))
    if target_value is None or target_value <= 0:
        raise AlertRuleError("条件值必须大于 0")
    matched_events = []

    if kind == "portfolio":
        previous_met = False
        condition_key = condition.get("condition_key")
        for entry in portfolio_entries:
            current_value = entry.get("value")
            if current_value is None:
                previous_met = False
                continue
            response["evaluated_count"] += 1
            condition_met = _portfolio_condition_met(condition_key, current_value, target_value)
            if condition_met and not previous_met:
                matched_events.append(_simulation_event(
                    entry["timestamp"],
                    current_value,
                    details=entry.get("details"),
                ))
            previous_met = condition_met
    elif kind == "volatility":
        window_minutes = max(1, int(condition.get("window_minutes") or 10))
        window_seconds = window_minutes * 60
        if interval_seconds > window_seconds:
            response.update({
                "reason": "history_resolution_too_coarse",
                "message": (
                    f"历史采样间隔约为 {_simulation_interval_label(interval_seconds)}，"
                    f"无法可靠模拟 {window_minutes} 分钟波动窗口。"
                ),
            })
            return response
        timestamps = [item[0] for item in points]
        last_evaluated_at = None
        tolerance_seconds = max(60, int((interval_seconds or 60) * 0.75))
        for index, (timestamp, current_value) in enumerate(points):
            if last_evaluated_at and (timestamp - last_evaluated_at).total_seconds() < 60:
                continue
            target_timestamp = timestamp - timedelta(seconds=window_seconds)
            insertion = bisect_left(timestamps, target_timestamp, 0, index)
            if insertion < index and timestamps[insertion] == target_timestamp:
                candidates = [insertion]
            else:
                candidates = [insertion - 1] if insertion > 0 else []
            if not candidates:
                continue
            start_index = min(
                candidates,
                key=lambda candidate: abs((timestamps[candidate] - target_timestamp).total_seconds()),
            )
            if abs((timestamps[start_index] - target_timestamp).total_seconds()) > tolerance_seconds:
                continue
            start_value = points[start_index][1]
            if start_value == 0:
                continue
            last_evaluated_at = timestamp
            response["evaluated_count"] += 1
            change_percent = abs((current_value - start_value) / start_value * 100)
            if change_percent >= target_value:
                matched_events.append(_simulation_event(timestamp, current_value, change_percent))
        if response["evaluated_count"] == 0:
            response.update({
                "reason": "history_window_unavailable",
                "message": "历史行情存在，但没有足够连续的窗口样本完成波动模拟。",
            })
            return response
    else:
        previous_met = False
        operator = condition.get("operator")
        for timestamp, current_value in points:
            response["evaluated_count"] += 1
            condition_met = _condition_met(operator, current_value, target_value)
            if condition_met and not previous_met:
                matched_events.append(_simulation_event(timestamp, current_value))
            previous_met = condition_met

    if response["trigger_policy"] == "single":
        effective_events = matched_events[:1]
    else:
        effective_events = _apply_simulation_cooldown(matched_events, cooldown_minutes)
    if response["coverage"]["partial"]:
        message = (
            "持仓或行情历史覆盖不足，结果仅代表现有样本。"
            if kind == "portfolio"
            else "历史覆盖不足，结果仅代表现有样本。"
        )
    elif kind == "portfolio":
        message = "模拟完成。结果按持仓流水、历史行情和当前触发策略计算。"
    else:
        message = "模拟完成。结果按历史行情与当前冷却策略计算。"

    response.update({
        "usable": True,
        "reason": "ok",
        "message": message,
        "match_count": len(matched_events),
        "effective_trigger_count": len(effective_events),
        "suppressed_count": max(0, len(matched_events) - len(effective_events)),
        "recent_triggers": list(reversed(effective_events[-5:])),
        "time_distribution": _simulation_time_distribution(effective_events),
    })
    return response


def _volatility_values(history, mode, points_needed):
    field = "usd" if mode == "usd" else "rmb"
    values = []
    for item in list(history or [])[-points_needed:]:
        if not isinstance(item, dict) or item.get(field) is None:
            continue
        try:
            values.append(float(item[field]))
        except (TypeError, ValueError):
            continue
    return values


def _trigger_title(rule):
    if rule.get("kind") == "volatility":
        return "金价波动预警"
    if rule.get("kind") == "watch_target":
        return "目标价观察提醒"
    if rule.get("kind") == "portfolio":
        return "持仓提醒"
    return "金价预警 - " + rule.get("name", "价格提醒")


def _price_text(value, mode):
    if value is None:
        return "--"
    unit = "$" if mode == "usd" else "¥"
    return f"{unit}{float(value):,.2f}"


def build_rule_trigger(rule, trigger_value, now, position=None, volatility=None):
    scope = rule.get("scope") or {}
    condition = rule.get("condition") or {}
    legacy = rule.get("legacy") or {}
    kind = rule.get("kind")
    mode = scope.get("mode") or (position or {}).get("mode") or "rmb"
    target = condition.get("value")
    direction = "up" if condition.get("operator") == "gte" else "down"
    if kind == "price_threshold":
        message = f"[{('国际金价' if mode == 'usd' else '国内金价')}] {rule.get('name')}: {_price_text(trigger_value, mode)}（条件 {_price_text(target, mode)}）"
    elif kind == "watch_target":
        direction_label = "上涨至" if condition.get("operator") == "gte" else "下跌至"
        note = f"；备注：{rule.get('note')}" if rule.get("note") else ""
        message = f"[{('国际金价' if mode == 'usd' else '国内金价')}] 目标价观察：当前 {_price_text(trigger_value, mode)}，已{direction_label} {_price_text(target, mode)}{note}"
    elif kind == "portfolio":
        condition_key = condition.get("condition_key")
        position_name = (position or {}).get("name") or "未命名持仓"
        label = PORTFOLIO_LABELS.get(condition_key, "持仓提醒")
        if condition_key in {"profit_percent", "loss_percent", "near_cost"}:
            current_text = f"{float(trigger_value):,.2f}%" if trigger_value is not None else "--"
            target_text = f"{float(target):,.2f}%"
        else:
            current_text = _price_text(trigger_value, mode)
            target_text = _price_text(target, mode)
        message = f"[持仓提醒] {position_name}：{label}已触发，当前 {current_text}，提醒值 {target_text}"
    else:
        volatility = volatility or {}
        start_value = volatility.get("start")
        end_value = volatility.get("end")
        change_pct = volatility.get("change_pct")
        direction_label = "上涨" if end_value is not None and start_value is not None and end_value > start_value else "下跌"
        direction = "up" if direction_label == "上涨" else "down"
        message = f"[波动预警] {condition.get('window_minutes')}分钟内{direction_label} {float(change_pct):.2f}%（{_price_text(start_value, mode)} → {_price_text(end_value, mode)}）"
    alert = {
        "time": now.strftime("%H:%M:%S"),
        "timestamp": now.isoformat(timespec="seconds"),
        "type": rule.get("alert_level") or ("volatility" if kind == "volatility" else "warning"),
        "mode": mode,
        "source": {
            "price_threshold": "threshold",
            "volatility": "volatility",
            "watch_target": "watch_target",
            "portfolio": "portfolio_alert",
        }[kind],
        "trigger_price": trigger_value,
        "alert_direction": direction,
        "message": message,
        "rule_id": rule.get("id"),
        "rule_kind": kind,
        "rule_name": rule.get("name"),
        "rule_scope": dict(scope),
        "rule_condition": dict(condition),
        "rule_delivery": dict(rule.get("delivery") or {}),
    }
    if kind == "price_threshold":
        alert["threshold_key"] = legacy.get("key") or rule.get("id")
        alert["threshold_value"] = target
    elif kind == "watch_target":
        alert["watch_target_id"] = legacy.get("id") or rule.get("id")
    elif kind == "portfolio":
        alert["portfolio_alert_id"] = legacy.get("id") or rule.get("id")
        alert["portfolio_position_id"] = scope.get("position_id")
        alert["portfolio_alert_condition"] = condition.get("condition_key")
    delivery = rule.get("delivery") or {}
    if delivery.get("channels") != "inherit":
        alert["delivery_channels"] = list(delivery.get("channels") or [])
    if delivery.get("cooldown_minutes") != "inherit":
        alert["cooldown_minutes"] = delivery.get("cooldown_minutes")
    return {"rule": dict(rule), "title": _trigger_title(rule), "alert": alert}


def evaluate_alert_rules(rules, prices=None, price_history=None, positions=None, now=None):
    now = now or datetime.now()
    prices = prices if isinstance(prices, dict) else {}
    positions = [item for item in list(positions or []) if isinstance(item, dict)]
    positions_by_id = {item.get("id"): item for item in positions if item.get("id")}
    next_rules = []
    triggers = []
    for source_rule in list(rules or []):
        source_state = dict(source_rule.get("state") or {}) if isinstance(source_rule, dict) else {}
        source_updated_at = str(source_rule.get("updated_at") or "") if isinstance(source_rule, dict) else ""
        try:
            rule = normalize_alert_rule(source_rule, existing=source_rule, now_factory=lambda: now)
        except AlertRuleError:
            continue
        state = dict(rule.get("state") or {})
        runtime_status = _rule_runtime_status(rule, now, positions_by_id=positions_by_id, prices=prices)
        state["status"] = runtime_status
        if runtime_status in {"disabled", "expired", "scheduled", "orphaned", "waiting_data"}:
            rule["state"] = state
            rule["updated_at"] = (
                now.isoformat(timespec="seconds")
                if state != source_state
                else source_updated_at or rule.get("updated_at", "")
            )
            next_rules.append(rule)
            continue

        kind = rule.get("kind")
        scope = rule.get("scope") or {}
        condition = rule.get("condition") or {}
        trigger_value = None
        condition_met = False
        position = None
        volatility = None

        if kind in {"price_threshold", "watch_target"}:
            trigger_value = prices.get(scope.get("mode"))
            condition_met = _condition_met(condition.get("operator"), trigger_value, condition.get("value"))
            if kind == "price_threshold" and not condition_met and state.get("triggered"):
                state.update({"triggered": False, "status": "watching"})
        elif kind == "portfolio":
            position = positions_by_id.get(scope.get("position_id"))
            trigger_value = _position_value(position or {}, condition.get("condition_key"))
            if trigger_value is None:
                state["status"] = "waiting_data"
                rule["state"] = state
                rule["updated_at"] = (
                    now.isoformat(timespec="seconds")
                    if state != source_state
                    else source_updated_at or rule.get("updated_at", "")
                )
                next_rules.append(rule)
                continue
            condition_met = _portfolio_condition_met(
                condition.get("condition_key"), trigger_value, condition.get("value")
            )
        elif kind == "volatility":
            last_evaluated = _parse_iso(state.get("last_evaluated_at"))
            if last_evaluated and now - last_evaluated < timedelta(seconds=60):
                rule["updated_at"] = source_updated_at or rule.get("updated_at", "")
                next_rules.append(rule)
                continue
            state["last_evaluated_at"] = now.isoformat(timespec="seconds")
            window_minutes = condition.get("window_minutes") or 10
            points_needed = max(2, int(window_minutes * 60 / 10))
            values = _volatility_values(price_history, scope.get("mode"), points_needed)
            if len(values) < points_needed or not values or values[0] == 0:
                state["status"] = "waiting_data"
                rule["state"] = state
                rule["updated_at"] = (
                    now.isoformat(timespec="seconds")
                    if state != source_state
                    else source_updated_at or rule.get("updated_at", "")
                )
                next_rules.append(rule)
                continue
            change_pct = abs((values[-1] - values[0]) / values[0] * 100)
            trigger_value = values[-1]
            condition_met = change_pct >= condition.get("value")
            volatility = {"start": values[0], "end": values[-1], "change_pct": change_pct}

        should_trigger = condition_met and (kind == "volatility" or not state.get("triggered"))
        if should_trigger:
            state.update({
                "status": "triggered",
                "triggered": True,
                "last_triggered_at": now.isoformat(timespec="seconds"),
                "last_trigger_value": trigger_value,
            })
        elif not state.get("triggered"):
            state["status"] = "watching"
        rule["state"] = state
        rule["updated_at"] = (
            now.isoformat(timespec="seconds")
            if state != source_state
            else source_updated_at or rule.get("updated_at", "")
        )
        next_rules.append(rule)
        if should_trigger:
            triggers.append(build_rule_trigger(rule, trigger_value, now, position=position, volatility=volatility))
    return next_rules, triggers


def alert_rules_state(
    rules,
    positions=None,
    prices=None,
    price_history=None,
    migration=None,
    invalid_count=0,
    load_error="",
    now=None,
):
    now = now or datetime.now()
    positions = [item for item in list(positions or []) if isinstance(item, dict)]
    positions_by_id = {item.get("id"): item for item in positions if item.get("id")}
    items = []
    summary = {status: 0 for status in ALERT_RULE_STATUSES}
    by_kind = {kind: 0 for kind in ALERT_RULE_KINDS}
    for source_rule in list(rules or []):
        if not isinstance(source_rule, dict):
            continue
        rule = dict(source_rule)
        inspection = inspect_alert_rule(
            rule,
            positions=positions,
            prices=prices or {},
            price_history=price_history,
            now=now,
        )
        status = inspection.get("status") or "watching"
        state = dict(rule.get("state") or {})
        state["status"] = status
        rule["state"] = state
        rule["inspection"] = inspection
        position = positions_by_id.get((rule.get("scope") or {}).get("position_id"))
        if position:
            rule["scope_label"] = position.get("name") or position.get("id")
        items.append(rule)
        summary[status] = summary.get(status, 0) + 1
        by_kind[rule.get("kind")] = by_kind.get(rule.get("kind"), 0) + 1
    return {
        "schema_version": ALERT_RULE_SCHEMA_VERSION,
        "items": items,
        "total": len(items),
        "summary": summary,
        "by_kind": by_kind,
        "migration": dict(migration or {}),
        "invalid_count": int(invalid_count or 0),
        "load_error": str(load_error or ""),
    }


def find_rule_index(rules, rule_id):
    rule_id = str(rule_id or "").strip()
    for index, rule in enumerate(list(rules or [])):
        if isinstance(rule, dict) and rule.get("id") == rule_id:
            return index
    return -1


def upsert_alert_rule(rules, data, now_factory=None, id_factory=None):
    next_rules = [dict(rule) for rule in list(rules or []) if isinstance(rule, dict)]
    rule_id = str((data or {}).get("id") or "").strip() if isinstance(data, dict) else ""
    index = find_rule_index(next_rules, rule_id)
    existing = next_rules[index] if index >= 0 else None
    rule = normalize_alert_rule(data, existing=existing, now_factory=now_factory, id_factory=id_factory)
    if index >= 0:
        next_rules[index] = rule
    else:
        next_rules.append(rule)
    return next_rules, rule


def delete_alert_rule(rules, rule_id):
    next_rules = [dict(rule) for rule in list(rules or []) if isinstance(rule, dict)]
    index = find_rule_index(next_rules, rule_id)
    if index < 0:
        return next_rules, False
    next_rules.pop(index)
    return next_rules, True


def toggle_alert_rule(rules, rule_id, enabled, now_factory=None):
    next_rules = [dict(rule) for rule in list(rules or []) if isinstance(rule, dict)]
    index = find_rule_index(next_rules, rule_id)
    if index < 0:
        return next_rules, None
    updated = dict(next_rules[index])
    updated["enabled"] = _coerce_bool(enabled, updated.get("enabled", True))
    next_rules[index] = normalize_alert_rule(updated, existing=next_rules[index], now_factory=now_factory)
    return next_rules, next_rules[index]


def reset_alert_rule(rules, rule_id, now_factory=None):
    next_rules = [dict(rule) for rule in list(rules or []) if isinstance(rule, dict)]
    index = find_rule_index(next_rules, rule_id)
    if index < 0:
        return next_rules, None
    updated = dict(next_rules[index])
    updated["state"] = {
        "status": "watching",
        "triggered": False,
        "last_triggered_at": "",
        "last_trigger_value": None,
        "last_evaluated_at": "",
    }
    next_rules[index] = normalize_alert_rule(updated, existing=next_rules[index], now_factory=now_factory)
    return next_rules, next_rules[index]


def duplicate_alert_rule(rules, rule_id, now_factory=None, id_factory=None):
    index = find_rule_index(rules, rule_id)
    if index < 0:
        return [dict(rule) for rule in list(rules or []) if isinstance(rule, dict)], None
    source = dict(rules[index])
    source.pop("id", None)
    source["name"] = _clean_text((source.get("name") or "预警规则") + " 副本", 80)
    source["legacy"] = {}
    source["state"] = {
        "status": "watching",
        "triggered": False,
        "last_triggered_at": "",
        "last_trigger_value": None,
        "last_evaluated_at": "",
    }
    return upsert_alert_rule(rules, source, now_factory=now_factory, id_factory=id_factory)


def batch_update_alert_rules(rules, rule_ids, action, now_factory=None):
    if not isinstance(rule_ids, list):
        raise AlertRuleError("批量操作规则编号格式无效")
    action = str(action or "").strip().lower()
    if action not in ALERT_RULE_BATCH_ACTIONS:
        raise AlertRuleError("批量操作类型无效")
    normalized_ids = []
    for raw_id in rule_ids:
        rule_id = _safe_identifier(raw_id)
        if not rule_id:
            raise AlertRuleError("批量操作包含无效规则编号")
        if rule_id not in normalized_ids:
            normalized_ids.append(rule_id)
    if not normalized_ids:
        raise AlertRuleError("请至少选择一条预警规则")
    if len(normalized_ids) > 200:
        raise AlertRuleError("单次最多操作 200 条预警规则")

    existing_ids = {
        rule.get("id")
        for rule in list(rules or [])
        if isinstance(rule, dict) and rule.get("id")
    }
    missing = [rule_id for rule_id in normalized_ids if rule_id not in existing_ids]
    if missing:
        raise AlertRuleError("部分预警规则已不存在，请刷新后重试")

    next_rules = [dict(rule) for rule in list(rules or []) if isinstance(rule, dict)]
    if action == "delete":
        selected = set(normalized_ids)
        next_rules = [rule for rule in next_rules if rule.get("id") not in selected]
        return next_rules, normalized_ids

    operation_now = now_factory() if callable(now_factory) else datetime.now()
    fixed_now_factory = lambda: operation_now
    for rule_id in normalized_ids:
        if action == "enable":
            next_rules, _ = toggle_alert_rule(next_rules, rule_id, True, now_factory=fixed_now_factory)
        elif action == "disable":
            next_rules, _ = toggle_alert_rule(next_rules, rule_id, False, now_factory=fixed_now_factory)
        else:
            next_rules, _ = reset_alert_rule(next_rules, rule_id, now_factory=fixed_now_factory)
    return next_rules, normalized_ids


class AlertRuleStore:
    def __init__(self, json_path, now_factory=None, id_factory=None):
        self.json_path = str(json_path or "")
        self.now_factory = now_factory or datetime.now
        self.id_factory = id_factory or generate_alert_rule_id

    def exists(self):
        return bool(self.json_path and os.path.isfile(self.json_path))

    def load(self):
        if not self.exists():
            return {"items": [], "migration": {}, "invalid_count": 0}
        try:
            with open(self.json_path, "r", encoding="utf-8") as file_handle:
                payload = json.load(file_handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise AlertRuleStoreError("预警规则文件无法读取") from exc
        if not isinstance(payload, dict):
            raise AlertRuleStoreError("预警规则文件格式无效")
        raw_version = payload.get("schema_version")
        try:
            version = int(raw_version)
        except (TypeError, ValueError) as exc:
            raise AlertRuleStoreError("预警规则文件版本无效") from exc
        if version != ALERT_RULE_SCHEMA_VERSION:
            raise AlertRuleStoreError(f"不支持预警规则文件版本 {version}")
        items, invalid_count = normalize_alert_rules(
            payload.get("items"),
            now_factory=self.now_factory,
            id_factory=self.id_factory,
        )
        return {
            "items": items,
            "migration": dict(payload.get("migration") or {}),
            "invalid_count": invalid_count,
            "updated_at": str(payload.get("updated_at") or ""),
        }

    def save(self, items, migration=None):
        if self.exists():
            self.load()
        normalized, invalid_count = normalize_alert_rules(
            items,
            now_factory=self.now_factory,
            id_factory=self.id_factory,
        )
        if invalid_count:
            raise AlertRuleStoreError("预警规则包含无效或重复数据")
        payload = {
            "schema_version": ALERT_RULE_SCHEMA_VERSION,
            "updated_at": _now_iso(self.now_factory),
            "migration": dict(migration or {}),
            "items": normalized,
        }
        os.makedirs(os.path.dirname(self.json_path) or ".", exist_ok=True)
        temporary_path = self.json_path + ".tmp"
        try:
            with open(temporary_path, "w", encoding="utf-8") as file_handle:
                json.dump(payload, file_handle, ensure_ascii=False, indent=2)
            with open(temporary_path, "r", encoding="utf-8") as file_handle:
                verified = json.load(file_handle)
            if verified.get("schema_version") != ALERT_RULE_SCHEMA_VERSION or not isinstance(verified.get("items"), list):
                raise AlertRuleStoreError("预警规则写入校验失败")
            os.replace(temporary_path, self.json_path)
        except Exception as exc:
            try:
                os.remove(temporary_path)
            except FileNotFoundError:
                pass
            if isinstance(exc, AlertRuleStoreError):
                raise
            raise AlertRuleStoreError("预警规则保存失败") from exc
        return {"items": normalized, "migration": dict(migration or {}), "invalid_count": 0}

    def migrate(self, thresholds=None, watch_targets=None, portfolio_alerts=None):
        if self.exists():
            return self.load()
        rules, migration = migrate_legacy_rules(
            thresholds=thresholds,
            watch_targets=watch_targets,
            portfolio_alerts=portfolio_alerts,
            now_factory=self.now_factory,
        )
        saved = self.save(rules, migration=migration)
        loaded = self.load()
        if loaded["items"] != saved["items"]:
            raise AlertRuleStoreError("预警规则迁移校验失败")
        return loaded
