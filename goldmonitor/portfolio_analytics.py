import math
from datetime import datetime, timedelta


PORTFOLIO_ANALYTICS_MODES = ("rmb", "usd")


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _parse_datetime(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if parsed.tzinfo:
        parsed = parsed.replace(tzinfo=None)
    return parsed


def _transaction_datetime(item):
    trade_date = str(item.get("trade_date") or "").strip()
    parsed = _parse_datetime(trade_date)
    if parsed:
        return parsed
    return _parse_datetime(item.get("created_at"))


def _price_points(items, mode):
    points = []
    for item in list(items or []):
        if not isinstance(item, dict):
            continue
        timestamp = _parse_datetime(item.get("timestamp"))
        price = _number(item.get(mode))
        if not timestamp or price is None or price <= 0:
            continue
        points.append({
            "timestamp": timestamp,
            "timestamp_text": timestamp.isoformat(timespec="seconds"),
            "price": price,
        })
    points.sort(key=lambda item: item["timestamp"])
    deduplicated = []
    for point in points:
        if deduplicated and deduplicated[-1]["timestamp"] == point["timestamp"]:
            deduplicated[-1] = point
        else:
            deduplicated.append(point)
    return deduplicated


def _empty_position_state():
    return {
        "quantity": 0.0,
        "cost_basis": 0.0,
        "realized_pnl": 0.0,
    }


def _apply_transaction(states, transaction):
    position_id = str(transaction.get("position_id") or transaction.get("id") or "")
    state = states.setdefault(position_id, _empty_position_state())
    quantity = _number(transaction.get("quantity")) or 0.0
    price = _number(transaction.get("price")) or 0.0
    fee = _number(transaction.get("fee")) or 0.0
    if quantity <= 0 or price <= 0:
        return
    if transaction.get("type") == "sell":
        available = max(0.0, state["quantity"])
        sell_quantity = min(quantity, available)
        average_cost = state["cost_basis"] / available if available else 0.0
        cost_removed = average_cost * sell_quantity
        proceeds = price * sell_quantity - fee
        state["realized_pnl"] += proceeds - cost_removed
        state["quantity"] -= sell_quantity
        state["cost_basis"] -= cost_removed
        if state["quantity"] <= 1e-9:
            state["quantity"] = 0.0
            state["cost_basis"] = 0.0
        return
    state["quantity"] += quantity
    state["cost_basis"] += price * quantity + fee


def _portfolio_totals(states, price):
    quantity = sum(max(0.0, state["quantity"]) for state in states.values())
    cost_basis = sum(max(0.0, state["cost_basis"]) for state in states.values())
    realized_pnl = sum(state["realized_pnl"] for state in states.values())
    market_value = quantity * price
    unrealized_pnl = market_value - cost_basis
    total_pnl = realized_pnl + unrealized_pnl
    return {
        "quantity": round(quantity, 4),
        "cost_basis": round(cost_basis, 4),
        "market_value": round(market_value, 4),
        "unrealized_pnl": round(unrealized_pnl, 4),
        "realized_pnl": round(realized_pnl, 4),
        "total_pnl": round(total_pnl, 4),
        "total_pnl_percent": round((total_pnl / cost_basis) * 100, 4) if cost_basis else 0.0,
    }


def _performance_summary(points):
    if not points:
        return {
            "points": 0,
            "start_at": "",
            "end_at": "",
            "start_pnl": None,
            "end_pnl": None,
            "change": None,
            "min_pnl": None,
            "max_pnl": None,
            "max_drawdown": None,
        }
    pnl_values = [float(item["total_pnl"]) for item in points]
    running_peak = pnl_values[0]
    max_drawdown = 0.0
    for value in pnl_values:
        running_peak = max(running_peak, value)
        max_drawdown = min(max_drawdown, value - running_peak)
    return {
        "points": len(points),
        "start_at": points[0]["timestamp"],
        "end_at": points[-1]["timestamp"],
        "start_pnl": round(pnl_values[0], 4),
        "end_pnl": round(pnl_values[-1], 4),
        "change": round(pnl_values[-1] - pnl_values[0], 4),
        "min_pnl": round(min(pnl_values), 4),
        "max_pnl": round(max(pnl_values), 4),
        "max_drawdown": round(max_drawdown, 4),
    }


def build_portfolio_performance(transactions, price_history, current_prices=None, now=None):
    now = now or datetime.now()
    current_prices = current_prices if isinstance(current_prices, dict) else {}
    result = {}
    for mode in PORTFOLIO_ANALYTICS_MODES:
        mode_transactions = []
        unknown_date_count = 0
        for item in list(transactions or []):
            if not isinstance(item, dict) or item.get("mode") != mode:
                continue
            timestamp = _transaction_datetime(item)
            if not timestamp:
                unknown_date_count += 1
                continue
            mode_transactions.append((timestamp, dict(item)))
        mode_transactions.sort(key=lambda pair: (pair[0], str(pair[1].get("id") or "")))

        prices = _price_points(price_history, mode)
        current_price = _number(current_prices.get(mode))
        if current_price is not None and current_price > 0:
            if not prices or prices[-1]["timestamp"].date() < now.date():
                prices.append({
                    "timestamp": now,
                    "timestamp_text": now.isoformat(timespec="seconds"),
                    "price": current_price,
                })
            elif prices:
                prices[-1] = {
                    "timestamp": now,
                    "timestamp_text": now.isoformat(timespec="seconds"),
                    "price": current_price,
                }

        states = {}
        transaction_index = 0
        points = []
        for price_point in prices:
            while (
                transaction_index < len(mode_transactions)
                and mode_transactions[transaction_index][0] <= price_point["timestamp"]
            ):
                _apply_transaction(states, mode_transactions[transaction_index][1])
                transaction_index += 1
            if not states:
                continue
            totals = _portfolio_totals(states, price_point["price"])
            if totals["quantity"] <= 0 and totals["realized_pnl"] == 0:
                continue
            points.append({
                "timestamp": price_point["timestamp_text"],
                "date": price_point["timestamp"].date().isoformat(),
                "price": round(price_point["price"], 4),
                **totals,
            })

        result[mode] = {
            "mode": mode,
            "points": points,
            "summary": _performance_summary(points),
            "transaction_count": len(mode_transactions),
            "unknown_date_count": unknown_date_count,
        }
    return result


def _alert_direction(entry):
    explicit = str(entry.get("alert_direction") or "").lower()
    if explicit in {"up", "down"}:
        return explicit
    threshold_key = str(entry.get("threshold_key") or "").lower()
    if "upper" in threshold_key:
        return "up"
    if "lower" in threshold_key:
        return "down"
    condition = str(entry.get("portfolio_alert_condition") or "").lower()
    if condition in {"take_profit", "profit_percent"}:
        return "up"
    if condition in {"stop_loss", "loss_percent"}:
        return "down"
    return ""


def _notification_outcome(entry):
    summary = entry.get("notification_summary") if isinstance(entry, dict) else None
    status = str(summary.get("status") or "") if isinstance(summary, dict) else ""
    if status in {"sent", "queued"}:
        return "sent"
    if status in {"failed", "partial", "skipped"}:
        return "failed"
    if status == "muted":
        return "muted"
    return status or "unknown"


def _alert_rule_kind(entry):
    explicit = str(entry.get("rule_kind") or "").strip()
    if explicit:
        return explicit
    return {
        "threshold": "price_threshold",
        "volatility": "volatility",
        "watch_target": "watch_target",
        "portfolio_alert": "portfolio",
    }.get(str(entry.get("source") or "").strip(), "legacy")


def _nearest_trigger_price(points, timestamp, explicit_price):
    explicit = _number(explicit_price)
    if explicit is not None and explicit > 0:
        return explicit
    nearest = None
    nearest_distance = None
    for point in points:
        distance = abs((point["timestamp"] - timestamp).total_seconds())
        if distance > 6 * 3600:
            continue
        if nearest_distance is None or distance < nearest_distance:
            nearest = point["price"]
            nearest_distance = distance
    return nearest


def build_alert_effectiveness(
    alerts,
    price_history,
    horizon_hours=24,
    minimum_evaluation_hours=1,
    follow_through_threshold_pct=0.1,
):
    alerts = [dict(item) for item in list(alerts or []) if isinstance(item, dict)]
    price_by_mode = {mode: _price_points(price_history, mode) for mode in PORTFOLIO_ANALYTICS_MODES}
    delivery_sent = sum(1 for item in alerts if _notification_outcome(item) == "sent")
    delivery_failed = sum(1 for item in alerts if _notification_outcome(item) == "failed")
    muted = sum(1 for item in alerts if _notification_outcome(item) == "muted")
    acknowledged = sum(1 for item in alerts if item.get("acknowledged"))
    handled = sum(1 for item in alerts if item.get("handled"))
    evaluated_items = []

    for entry in alerts:
        timestamp = _parse_datetime(entry.get("timestamp"))
        mode = str(entry.get("mode") or "")
        direction = _alert_direction(entry)
        points = price_by_mode.get(mode, [])
        if not timestamp or not direction or not points:
            continue
        trigger_price = _nearest_trigger_price(points, timestamp, entry.get("trigger_price"))
        if trigger_price is None or trigger_price <= 0:
            continue
        horizon_end = timestamp + timedelta(hours=max(1, int(horizon_hours or 24)))
        window = [
            point for point in points
            if timestamp < point["timestamp"] <= horizon_end
        ]
        if not window:
            continue
        evaluation_hours = (window[-1]["timestamp"] - timestamp).total_seconds() / 3600
        if evaluation_hours < float(minimum_evaluation_hours or 1):
            continue
        multiplier = 1.0 if direction == "up" else -1.0
        signed_changes = [
            ((point["price"] - trigger_price) / trigger_price) * 100 * multiplier
            for point in window
        ]
        final_change = signed_changes[-1]
        follow_through = final_change >= float(follow_through_threshold_pct or 0)
        evaluated_items.append({
            "id": str(entry.get("id") or ""),
            "rule_id": str(entry.get("rule_id") or ""),
            "rule_kind": _alert_rule_kind(entry),
            "timestamp": timestamp.isoformat(timespec="seconds"),
            "title": str(entry.get("title") or entry.get("message") or "预警"),
            "source": str(entry.get("source") or "alert"),
            "mode": mode,
            "direction": direction,
            "trigger_price": round(trigger_price, 4),
            "end_price": round(window[-1]["price"], 4),
            "evaluation_hours": round(evaluation_hours, 2),
            "final_signed_change_pct": round(final_change, 4),
            "max_favorable_excursion_pct": round(max(signed_changes), 4),
            "max_adverse_excursion_pct": round(min(signed_changes), 4),
            "follow_through": follow_through,
            "notification": _notification_outcome(entry),
            "acknowledged": bool(entry.get("acknowledged")),
            "handled": bool(entry.get("handled")),
        })

    evaluated_items.sort(key=lambda item: item["timestamp"], reverse=True)
    follow_through_count = sum(1 for item in evaluated_items if item["follow_through"])
    total = len(alerts)
    by_rule_kind = {}
    for entry in alerts:
        kind = _alert_rule_kind(entry)
        group = by_rule_kind.setdefault(kind, {"total": 0, "evaluated": 0, "follow_through": 0})
        group["total"] += 1
    for item in evaluated_items:
        group = by_rule_kind.setdefault(item["rule_kind"], {"total": 0, "evaluated": 0, "follow_through": 0})
        group["evaluated"] += 1
        if item["follow_through"]:
            group["follow_through"] += 1
    for group in by_rule_kind.values():
        group["rate"] = (
            round((group["follow_through"] / group["evaluated"]) * 100, 2)
            if group["evaluated"]
            else None
        )
    return {
        "period_alerts": total,
        "delivery": {
            "sent": delivery_sent,
            "failed": delivery_failed,
            "muted": muted,
            "sent_rate": round((delivery_sent / total) * 100, 2) if total else None,
        },
        "response": {
            "acknowledged": acknowledged,
            "handled": handled,
            "acknowledged_rate": round((acknowledged / total) * 100, 2) if total else None,
            "handled_rate": round((handled / total) * 100, 2) if total else None,
        },
        "market_follow_through": {
            "evaluated": len(evaluated_items),
            "follow_through": follow_through_count,
            "rate": round((follow_through_count / len(evaluated_items)) * 100, 2) if evaluated_items else None,
            "horizon_hours": int(horizon_hours or 24),
            "threshold_pct": float(follow_through_threshold_pct or 0),
        },
        "by_rule_kind": by_rule_kind,
        "items": evaluated_items[:50],
    }
