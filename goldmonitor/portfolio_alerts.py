import json
import math
import os
import secrets
from datetime import datetime

from .data_contracts import unwrap_item_payload, wrap_item_payload


PORTFOLIO_ALERT_CONDITIONS = ("take_profit", "stop_loss", "profit_percent", "loss_percent", "near_cost")
PORTFOLIO_ALERT_NOTE_LIMIT = 120


def generate_portfolio_alert_id():
    return "portfolio-alert-" + secrets.token_hex(8)


def _clean_text(value, limit=None):
    text = str(value or "").strip()
    if limit is not None and len(text) > limit:
        text = text[:limit]
    return text


def _positive_float_or_none(value):
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def _valid_id(value, prefix):
    text = _clean_text(value)
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    if not text or any(ch not in allowed for ch in text):
        return ""
    return text if text.startswith(prefix) else text


def _coerce_bool(value, default):
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


def empty_portfolio_alert_triggered():
    return {condition: False for condition in PORTFOLIO_ALERT_CONDITIONS}


def _normalize_triggered(raw, existing=None):
    source = raw if isinstance(raw, dict) else existing if isinstance(existing, dict) else {}
    return {
        condition: _coerce_bool(source.get(condition), False)
        for condition in PORTFOLIO_ALERT_CONDITIONS
    }


def _condition_thresholds(alert):
    return {
        "take_profit": alert.get("take_profit_price"),
        "stop_loss": alert.get("stop_loss_price"),
        "profit_percent": alert.get("profit_percent"),
        "loss_percent": alert.get("loss_percent"),
        "near_cost": alert.get("near_cost_percent"),
    }


def _threshold_changed(condition, current, existing):
    return _condition_thresholds(current).get(condition) != _condition_thresholds(existing).get(condition)


def normalize_portfolio_alert(item, existing=None, now_factory=None, id_factory=None, note_limit=PORTFOLIO_ALERT_NOTE_LIMIT):
    if not isinstance(item, dict):
        raise ValueError("持仓提醒格式无效")

    existing = existing if isinstance(existing, dict) else {}
    now_factory = now_factory or datetime.now
    id_factory = id_factory or generate_portfolio_alert_id
    now = now_factory().isoformat(timespec="seconds")

    alert_id = _valid_id(item.get("id") or existing.get("id") or id_factory(), "portfolio-alert-") or id_factory()
    position_id = _valid_id(item.get("position_id") or existing.get("position_id"), "position-")
    if not position_id:
        raise ValueError("请选择要提醒的持仓")

    normalized = {
        "id": alert_id,
        "position_id": position_id,
        "enabled": _coerce_bool(item.get("enabled", existing.get("enabled", True)), True),
        "take_profit_price": _positive_float_or_none(item.get("take_profit_price", existing.get("take_profit_price"))),
        "stop_loss_price": _positive_float_or_none(item.get("stop_loss_price", existing.get("stop_loss_price"))),
        "profit_percent": _positive_float_or_none(item.get("profit_percent", existing.get("profit_percent"))),
        "loss_percent": _positive_float_or_none(item.get("loss_percent", existing.get("loss_percent"))),
        "near_cost_percent": _positive_float_or_none(item.get("near_cost_percent", existing.get("near_cost_percent"))),
        "note": _clean_text(item.get("note", existing.get("note", "")), note_limit),
        "created_at": str(item.get("created_at") or existing.get("created_at") or now),
        "updated_at": now if existing else str(item.get("updated_at") or now),
        "last_triggered_at": _clean_text(item.get("last_triggered_at", existing.get("last_triggered_at", ""))),
        "last_trigger_price": _positive_float_or_none(item.get("last_trigger_price", existing.get("last_trigger_price"))),
        "last_trigger_condition": _clean_text(item.get("last_trigger_condition", existing.get("last_trigger_condition", ""))),
    }
    triggered = _normalize_triggered(item.get("triggered"), existing.get("triggered"))
    for condition in PORTFOLIO_ALERT_CONDITIONS:
        if existing and _threshold_changed(condition, normalized, existing):
            triggered[condition] = False
    normalized["triggered"] = triggered
    if not any(triggered.values()):
        normalized["last_triggered_at"] = ""
        normalized["last_trigger_price"] = None
        normalized["last_trigger_condition"] = ""
    return normalized


def normalize_portfolio_alerts(items, now_factory=None, id_factory=None):
    if not isinstance(items, list):
        return []
    normalized = []
    seen_positions = set()
    for item in items:
        try:
            alert = normalize_portfolio_alert(item, now_factory=now_factory, id_factory=id_factory)
        except ValueError:
            continue
        position_id = alert.get("position_id")
        if position_id in seen_positions:
            continue
        seen_positions.add(position_id)
        normalized.append(alert)
    return normalized


def portfolio_alert_has_conditions(alert):
    return any(_condition_thresholds(alert).get(condition) is not None for condition in PORTFOLIO_ALERT_CONDITIONS)


def portfolio_alert_status(alert):
    if not portfolio_alert_has_conditions(alert):
        return "empty"
    if not alert.get("enabled"):
        return "disabled"
    if any((alert.get("triggered") or {}).values()):
        return "triggered"
    return "watching"


def portfolio_alerts_state(items):
    alerts = [dict(item) for item in list(items or [])]
    return {
        "items": alerts,
        "total": len(alerts),
        "enabled": sum(1 for item in alerts if item.get("enabled") and portfolio_alert_has_conditions(item)),
        "triggered": sum(1 for item in alerts if any((item.get("triggered") or {}).values())),
    }


def _position_by_id(positions):
    return {
        item.get("id"): item
        for item in list(positions or [])
        if isinstance(item, dict) and item.get("id")
    }


def _condition_triggered(condition, alert, position):
    current_price = _positive_float_or_none(position.get("current_price"))
    if current_price is None:
        return False
    average_cost = _positive_float_or_none(position.get("average_cost") or position.get("entry_price"))
    if condition == "take_profit":
        threshold = alert.get("take_profit_price")
        return threshold is not None and current_price >= threshold
    if condition == "stop_loss":
        threshold = alert.get("stop_loss_price")
        return threshold is not None and current_price <= threshold
    pnl_percent = position.get("unrealized_pnl_percent", position.get("pnl_percent"))
    try:
        pnl_percent = float(pnl_percent)
    except (TypeError, ValueError):
        pnl_percent = None
    if condition == "profit_percent":
        threshold = alert.get("profit_percent")
        return threshold is not None and pnl_percent is not None and pnl_percent >= threshold
    if condition == "loss_percent":
        threshold = alert.get("loss_percent")
        return threshold is not None and pnl_percent is not None and pnl_percent <= -threshold
    if condition == "near_cost":
        threshold = alert.get("near_cost_percent")
        if threshold is None or average_cost is None:
            return False
        distance_percent = abs(current_price - average_cost) / average_cost * 100
        return distance_percent <= threshold
    return False


def _trigger_detail(alert, position, condition):
    current_price = _positive_float_or_none(position.get("current_price"))
    mode = position.get("mode") or "rmb"
    return {
        "alert": dict(alert),
        "position": dict(position),
        "condition": condition,
        "mode": mode,
        "current_price": current_price,
        "threshold": _condition_thresholds(alert).get(condition),
        "pnl_percent": position.get("unrealized_pnl_percent", position.get("pnl_percent")),
    }


def check_portfolio_alerts(alerts, positions, now_factory=None):
    now_factory = now_factory or datetime.now
    positions_by_id = _position_by_id(positions)
    next_alerts = [dict(item) for item in list(alerts or [])]
    triggered_entries = []
    for index, alert in enumerate(next_alerts):
        if not alert.get("enabled") or not portfolio_alert_has_conditions(alert):
            continue
        position = positions_by_id.get(alert.get("position_id"))
        if not position or position.get("valuation_status") in {"closed", "waiting_price", "invalid_position"}:
            continue
        triggered = _normalize_triggered(alert.get("triggered"))
        for condition in PORTFOLIO_ALERT_CONDITIONS:
            if triggered.get(condition) or not _condition_triggered(condition, alert, position):
                continue
            triggered[condition] = True
            now = now_factory().isoformat(timespec="seconds")
            updated = dict(alert)
            updated["triggered"] = triggered
            updated["last_triggered_at"] = now
            updated["last_trigger_price"] = _positive_float_or_none(position.get("current_price"))
            updated["last_trigger_condition"] = condition
            updated["updated_at"] = now
            next_alerts[index] = normalize_portfolio_alert(updated, existing=alert, now_factory=now_factory)
            alert = next_alerts[index]
            triggered_entries.append(_trigger_detail(alert, position, condition))
    return next_alerts, triggered_entries


def build_portfolio_alert_message(trigger):
    position = trigger.get("position") or {}
    condition = trigger.get("condition")
    mode = trigger.get("mode") or position.get("mode") or "rmb"
    unit = "$" if mode == "usd" else "¥"
    current_price = trigger.get("current_price")
    threshold = trigger.get("threshold")
    name = position.get("name") or "未命名持仓"
    labels = {
        "take_profit": "止盈价",
        "stop_loss": "止损价",
        "profit_percent": "浮盈比例",
        "loss_percent": "浮亏比例",
        "near_cost": "接近成本价",
    }
    label = labels.get(condition, "持仓提醒")
    if condition in {"profit_percent", "loss_percent", "near_cost"}:
        threshold_text = f"{threshold:,.2f}%" if threshold is not None else "--"
        current_text = f"{trigger.get('pnl_percent', 0):,.2f}%"
        return f"[持仓提醒] {name}: {label}已触发，当前浮动比例 {current_text}，提醒值 {threshold_text}"
    current_text = f"{unit}{current_price:,.2f}" if current_price is not None else "--"
    threshold_text = f"{unit}{threshold:,.2f}" if threshold is not None else "--"
    return f"[持仓提醒] {name}: {label}已触发，当前 {current_text}，提醒值 {threshold_text}"


class PortfolioAlertStore:
    def __init__(self, json_path, now_factory=None, id_factory=None):
        self.json_path = json_path
        self.now_factory = now_factory or datetime.now
        self.id_factory = id_factory or generate_portfolio_alert_id

    def normalize(self, items):
        return normalize_portfolio_alerts(items, now_factory=self.now_factory, id_factory=self.id_factory)

    def load(self):
        if not os.path.exists(self.json_path):
            return []
        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            return self.normalize(unwrap_item_payload(payload))
        except (OSError, json.JSONDecodeError):
            return []

    def save(self, items):
        normalized = self.normalize(items)
        os.makedirs(os.path.dirname(self.json_path) or ".", exist_ok=True)
        payload = wrap_item_payload(normalized)
        tmp_path = self.json_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.json_path)
        return normalized
