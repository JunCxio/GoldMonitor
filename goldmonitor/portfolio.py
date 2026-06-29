import csv
import json
import math
import os
import secrets
from datetime import datetime
from io import StringIO

from .data_contracts import unwrap_item_payload, wrap_item_payload


PORTFOLIO_MODES = {"rmb", "usd"}
PORTFOLIO_TRANSACTION_TYPES = {"buy", "sell"}
PORTFOLIO_NAME_LIMIT = 60
PORTFOLIO_NOTE_LIMIT = 200
PORTFOLIO_CSV_FIELDS = [
    "id",
    "name",
    "mode",
    "entry_price",
    "quantity",
    "entry_date",
    "current_price",
    "cost",
    "market_value",
    "pnl",
    "pnl_percent",
    "valuation_status",
    "note",
]
PORTFOLIO_POSITION_CSV_FIELDS = [
    "id",
    "name",
    "mode",
    "quantity",
    "average_cost",
    "cost_basis",
    "current_price",
    "market_value",
    "unrealized_pnl",
    "unrealized_pnl_percent",
    "realized_pnl",
    "total_pnl",
    "fees",
    "last_trade_date",
    "valuation_status",
]
PORTFOLIO_TRANSACTION_CSV_FIELDS = [
    "id",
    "position_id",
    "name",
    "type",
    "mode",
    "price",
    "quantity",
    "fee",
    "trade_date",
    "realized_pnl",
    "note",
    "created_at",
    "updated_at",
]


def generate_portfolio_position_id():
    return "position-" + secrets.token_hex(8)


def generate_portfolio_transaction_id():
    return "transaction-" + secrets.token_hex(8)


def _clean_text(value, limit=None):
    text = str(value or "").strip()
    if limit is not None and len(text) > limit:
        text = text[:limit]
    return text


def _positive_float_or_none(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def _nonnegative_float_or_none(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


def _valid_position_id(value):
    text = _clean_text(value)
    if not text:
        return ""
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    if any(ch not in allowed for ch in text):
        return ""
    return text


def _normalize_entry_date(value):
    text = _clean_text(value)
    if len(text) < 10:
        return ""
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date().isoformat()
    except ValueError:
        return ""


def _round_value(value, digits=4):
    if value is None:
        return None
    return round(float(value), digits)


def normalize_portfolio_position(item, existing=None, now_factory=None, id_factory=None):
    if not isinstance(item, dict):
        raise ValueError("持仓格式无效")

    existing = existing if isinstance(existing, dict) else {}
    now_factory = now_factory or datetime.now
    id_factory = id_factory or generate_portfolio_position_id
    now = now_factory().isoformat(timespec="seconds")

    position_id = _valid_position_id(item.get("id") or existing.get("id"))
    if not position_id:
        position_id = _valid_position_id(id_factory()) or generate_portfolio_position_id()

    name = _clean_text(item.get("name", existing.get("name", "")), PORTFOLIO_NAME_LIMIT)
    if not name:
        raise ValueError("持仓名称不能为空")

    mode = _clean_text(item.get("mode", existing.get("mode", "rmb"))).lower()
    if mode not in PORTFOLIO_MODES:
        raise ValueError("持仓单位无效")

    entry_price = _positive_float_or_none(item.get("entry_price", existing.get("entry_price")))
    quantity = _positive_float_or_none(item.get("quantity", existing.get("quantity")))
    entry_date = _normalize_entry_date(item.get("entry_date", existing.get("entry_date", "")))
    note = _clean_text(item.get("note", existing.get("note", "")), PORTFOLIO_NOTE_LIMIT)
    created_at = str(existing.get("created_at") or item.get("created_at") or now)
    updated_at = now

    return {
        "id": position_id,
        "name": name,
        "mode": mode,
        "entry_price": entry_price,
        "quantity": quantity,
        "entry_date": entry_date,
        "note": note,
        "created_at": created_at,
        "updated_at": updated_at,
    }


def normalize_portfolio_positions(items, now_factory=None, id_factory=None):
    if not isinstance(items, list):
        return []
    normalized = []
    seen = set()
    for item in items:
        try:
            position = normalize_portfolio_position(
                item,
                now_factory=now_factory,
                id_factory=id_factory,
            )
        except ValueError:
            continue
        position_id = position.get("id")
        if position_id in seen:
            continue
        seen.add(position_id)
        normalized.append(position)
    return normalized


def find_portfolio_position_index(items, position_id):
    position_id = _clean_text(position_id)
    if not position_id:
        return -1
    for index, item in enumerate(list(items or [])):
        if isinstance(item, dict) and item.get("id") == position_id:
            return index
    return -1


def empty_portfolio_summary():
    return {
        "count": 0,
        "valued": 0,
        "cost": 0.0,
        "market_value": 0.0,
        "pnl": 0.0,
        "pnl_percent": 0.0,
    }


def value_portfolio_position(position, prices):
    item = dict(position) if isinstance(position, dict) else {}
    mode = item.get("mode")
    prices = prices if isinstance(prices, dict) else {}
    current_price = _positive_float_or_none(prices.get(mode))
    entry_price = _positive_float_or_none(item.get("entry_price"))
    quantity = _positive_float_or_none(item.get("quantity"))

    item.update({
        "current_price": current_price,
        "cost": None,
        "market_value": None,
        "pnl": None,
        "pnl_percent": None,
        "valuation_status": "valued",
    })

    if entry_price is None or quantity is None:
        item["valuation_status"] = "invalid_position"
        return item

    cost = entry_price * quantity
    item["cost"] = _round_value(cost)

    if current_price is None:
        item["valuation_status"] = "waiting_price"
        return item

    market_value = current_price * quantity
    pnl = market_value - cost
    item.update({
        "market_value": _round_value(market_value),
        "pnl": _round_value(pnl),
        "pnl_percent": _round_value((pnl / cost) * 100),
    })
    return item


def _add_to_summary(summary, item):
    summary["count"] += 1
    if item.get("valuation_status") != "valued":
        return
    summary["valued"] += 1
    summary["cost"] = _round_value(summary["cost"] + float(item.get("cost") or 0.0))
    summary["market_value"] = _round_value(
        summary["market_value"] + float(item.get("market_value") or 0.0)
    )
    summary["pnl"] = _round_value(summary["pnl"] + float(item.get("pnl") or 0.0))
    summary["pnl_percent"] = _round_value((summary["pnl"] / summary["cost"]) * 100) if summary["cost"] else 0.0


def build_portfolio_state(items, prices):
    valued_items = [value_portfolio_position(item, prices) for item in list(items or [])]
    rmb_summary = empty_portfolio_summary()
    usd_summary = empty_portfolio_summary()
    for item in valued_items:
        if item.get("mode") == "usd":
            _add_to_summary(usd_summary, item)
        else:
            _add_to_summary(rmb_summary, item)
    return {
        "items": valued_items,
        "total": len(valued_items),
        "rmb_summary": rmb_summary,
        "usd_summary": usd_summary,
    }


def empty_portfolio_transaction_summary():
    summary = empty_portfolio_summary()
    summary.update({
        "cost_basis": 0.0,
        "unrealized_pnl": 0.0,
        "unrealized_pnl_percent": 0.0,
        "realized_pnl": 0.0,
        "total_pnl": 0.0,
        "fees": 0.0,
        "quantity": 0.0,
    })
    return summary


def normalize_portfolio_transaction(item, existing=None, now_factory=None, id_factory=None, position_id_factory=None):
    if not isinstance(item, dict):
        raise ValueError("流水格式无效")

    existing = existing if isinstance(existing, dict) else {}
    now_factory = now_factory or datetime.now
    id_factory = id_factory or generate_portfolio_transaction_id
    position_id_factory = position_id_factory or generate_portfolio_position_id
    now = now_factory().isoformat(timespec="seconds")

    transaction_id = _valid_position_id(item.get("id") or existing.get("id"))
    if not transaction_id:
        transaction_id = _valid_position_id(id_factory()) or generate_portfolio_transaction_id()

    position_id = _valid_position_id(item.get("position_id") or existing.get("position_id"))
    if not position_id:
        position_id = _valid_position_id(position_id_factory()) or generate_portfolio_position_id()

    name = _clean_text(item.get("name", existing.get("name", "")), PORTFOLIO_NAME_LIMIT)
    if not name:
        raise ValueError("流水名称不能为空")

    transaction_type = _clean_text(item.get("type", existing.get("type", "buy"))).lower()
    if transaction_type not in PORTFOLIO_TRANSACTION_TYPES:
        raise ValueError("流水类型无效")

    mode = _clean_text(item.get("mode", existing.get("mode", "rmb"))).lower()
    if mode not in PORTFOLIO_MODES:
        raise ValueError("持仓单位无效")

    price = _positive_float_or_none(item.get("price", existing.get("price")))
    if price is None:
        raise ValueError("流水价格无效")

    quantity = _positive_float_or_none(item.get("quantity", existing.get("quantity")))
    if quantity is None:
        raise ValueError("流水数量无效")

    fee = _nonnegative_float_or_none(item.get("fee", existing.get("fee", 0)))
    if fee is None:
        raise ValueError("手续费不能为负数")

    trade_date = _normalize_entry_date(item.get("trade_date", existing.get("trade_date", "")))
    note = _clean_text(item.get("note", existing.get("note", "")), PORTFOLIO_NOTE_LIMIT)
    created_at = str(existing.get("created_at") or item.get("created_at") or now)
    updated_at = now

    return {
        "id": transaction_id,
        "position_id": position_id,
        "name": name,
        "type": transaction_type,
        "mode": mode,
        "price": price,
        "quantity": quantity,
        "fee": fee,
        "trade_date": trade_date,
        "note": note,
        "created_at": created_at,
        "updated_at": updated_at,
    }


def normalize_portfolio_transactions(items, now_factory=None, id_factory=None, position_id_factory=None):
    if not isinstance(items, list):
        return []
    normalized = []
    seen = set()
    for item in items:
        try:
            transaction = normalize_portfolio_transaction(
                item,
                now_factory=now_factory,
                id_factory=id_factory,
                position_id_factory=position_id_factory,
            )
        except ValueError:
            continue
        transaction_id = transaction.get("id")
        if transaction_id in seen:
            continue
        seen.add(transaction_id)
        normalized.append(transaction)
    return normalized


def find_portfolio_transaction_index(items, transaction_id):
    transaction_id = _clean_text(transaction_id)
    if not transaction_id:
        return -1
    for index, item in enumerate(list(items or [])):
        if isinstance(item, dict) and item.get("id") == transaction_id:
            return index
    return -1


def transactions_from_positions(items, now_factory=None):
    now_factory = now_factory or datetime.now
    now = now_factory().isoformat(timespec="seconds")
    transactions = []
    seen = set()
    for item in list(items or []):
        if not isinstance(item, dict):
            continue
        position_id = _valid_position_id(item.get("id")) or _valid_position_id(generate_portfolio_position_id())
        if not position_id or position_id in seen:
            continue
        name = _clean_text(item.get("name", ""), PORTFOLIO_NAME_LIMIT)
        mode = _clean_text(item.get("mode", "rmb")).lower()
        price = _positive_float_or_none(item.get("entry_price"))
        quantity = _positive_float_or_none(item.get("quantity"))
        if not name or mode not in PORTFOLIO_MODES or price is None or quantity is None:
            continue
        seen.add(position_id)
        created_at = str(item.get("created_at") or now)
        updated_at = str(item.get("updated_at") or created_at)
        transactions.append({
            "id": "transaction-" + position_id,
            "position_id": position_id,
            "name": name,
            "type": "buy",
            "mode": mode,
            "price": price,
            "quantity": quantity,
            "fee": 0.0,
            "trade_date": _normalize_entry_date(item.get("entry_date", "")),
            "note": _clean_text(item.get("note", ""), PORTFOLIO_NOTE_LIMIT),
            "created_at": created_at,
            "updated_at": updated_at,
        })
    return transactions


def _portfolio_transaction_sort_key(item):
    trade_date = _clean_text(item.get("trade_date"))
    created_at = _clean_text(item.get("created_at"))
    transaction_id = _clean_text(item.get("id"))
    return (1 if not trade_date else 0, trade_date, created_at, transaction_id)


def _sorted_portfolio_transactions(items):
    return sorted([dict(item) for item in list(items or [])], key=_portfolio_transaction_sort_key)


def _ensure_position_state(states, item):
    position_id = item["position_id"]
    if position_id not in states:
        states[position_id] = {
            "id": position_id,
            "name": item["name"],
            "mode": item["mode"],
            "quantity": 0.0,
            "cost_basis": 0.0,
            "average_cost": None,
            "realized_pnl": 0.0,
            "fees": 0.0,
            "last_trade_date": "",
        }
    state = states[position_id]
    if state["mode"] != item["mode"]:
        raise ValueError("同一持仓单位必须一致")
    state["name"] = item["name"]
    if item.get("trade_date"):
        state["last_trade_date"] = item["trade_date"]
    return state


def _apply_portfolio_transaction(states, item):
    state = _ensure_position_state(states, item)
    trade_quantity = float(item["quantity"])
    price = float(item["price"])
    fee = float(item.get("fee") or 0.0)
    item["realized_pnl"] = 0.0

    if item["type"] == "buy":
        buy_cost = price * trade_quantity + fee
        state["cost_basis"] += buy_cost
        state["quantity"] += trade_quantity
        state["fees"] += fee
        state["average_cost"] = state["cost_basis"] / state["quantity"] if state["quantity"] else None
        return item

    current_quantity = float(state["quantity"])
    if current_quantity + 1e-9 < trade_quantity:
        raise ValueError("卖出数量不能超过当前持仓")
    average_cost = state["cost_basis"] / current_quantity if current_quantity else 0.0
    cost_removed = average_cost * trade_quantity
    proceeds = price * trade_quantity - fee
    realized_pnl = proceeds - cost_removed
    state["realized_pnl"] += realized_pnl
    state["cost_basis"] -= cost_removed
    state["quantity"] -= trade_quantity
    state["fees"] += fee
    item["realized_pnl"] = _round_value(realized_pnl)
    if abs(state["quantity"]) < 1e-9:
        state["quantity"] = 0.0
        state["cost_basis"] = 0.0
        state["average_cost"] = None
    else:
        state["average_cost"] = state["cost_basis"] / state["quantity"]
    return item


def replay_portfolio_transactions(items):
    states = {}
    enriched_transactions = []
    for item in _sorted_portfolio_transactions(items):
        enriched_transactions.append(_apply_portfolio_transaction(states, item))
    return states, enriched_transactions


def validate_portfolio_transactions(items):
    replay_portfolio_transactions(items)
    return True


def empty_portfolio_review_summary(mode):
    return {
        "mode": mode,
        "trade_count": 0,
        "buy_count": 0,
        "sell_count": 0,
        "buy_amount": 0.0,
        "sell_amount": 0.0,
        "fee_total": 0.0,
        "realized_pnl": 0.0,
        "net_invested": 0.0,
        "current_quantity": 0.0,
        "cost_basis": 0.0,
        "average_cost": None,
        "first_trade_date": "",
        "last_trade_date": "",
        "points": [],
    }


def empty_portfolio_review():
    return {
        "rmb": empty_portfolio_review_summary("rmb"),
        "usd": empty_portfolio_review_summary("usd"),
    }


def _portfolio_review_trade_date(item):
    trade_date = _normalize_entry_date(item.get("trade_date", ""))
    if trade_date:
        return trade_date
    created_date = _normalize_entry_date(str(item.get("created_at") or "")[:10])
    return created_date or "未标日期"


def _empty_portfolio_review_point(date):
    return {
        "date": date,
        "trade_count": 0,
        "buy_amount": 0.0,
        "sell_amount": 0.0,
        "fee": 0.0,
        "realized_pnl": 0.0,
        "cumulative_buy_amount": 0.0,
        "cumulative_sell_amount": 0.0,
        "cumulative_fee": 0.0,
        "cumulative_realized_pnl": 0.0,
        "net_invested": 0.0,
        "quantity": 0.0,
        "cost_basis": 0.0,
    }


def _empty_portfolio_review_mode_state():
    return {
        "positions": {},
        "point_by_date": {},
        "point_dates": [],
        "cumulative_buy_amount": 0.0,
        "cumulative_sell_amount": 0.0,
        "cumulative_fee": 0.0,
        "cumulative_realized_pnl": 0.0,
        "quantity": 0.0,
        "cost_basis": 0.0,
    }


def _finalize_portfolio_review_summary(summary, mode_state):
    summary["buy_amount"] = _round_value(mode_state["cumulative_buy_amount"])
    summary["sell_amount"] = _round_value(mode_state["cumulative_sell_amount"])
    summary["fee_total"] = _round_value(mode_state["cumulative_fee"])
    summary["realized_pnl"] = _round_value(mode_state["cumulative_realized_pnl"])
    summary["net_invested"] = _round_value(summary["buy_amount"] - summary["sell_amount"])
    summary["current_quantity"] = _round_value(mode_state["quantity"])
    summary["cost_basis"] = _round_value(mode_state["cost_basis"])
    summary["average_cost"] = (
        _round_value(mode_state["cost_basis"] / mode_state["quantity"])
        if mode_state["quantity"] else None
    )
    summary["points"] = [
        {
            "date": point["date"],
            "trade_count": int(point["trade_count"]),
            "buy_amount": _round_value(point["buy_amount"]),
            "sell_amount": _round_value(point["sell_amount"]),
            "fee": _round_value(point["fee"]),
            "realized_pnl": _round_value(point["realized_pnl"]),
            "cumulative_buy_amount": _round_value(point["cumulative_buy_amount"]),
            "cumulative_sell_amount": _round_value(point["cumulative_sell_amount"]),
            "cumulative_fee": _round_value(point["cumulative_fee"]),
            "cumulative_realized_pnl": _round_value(point["cumulative_realized_pnl"]),
            "net_invested": _round_value(point["net_invested"]),
            "quantity": _round_value(point["quantity"]),
            "cost_basis": _round_value(point["cost_basis"]),
        }
        for point in (mode_state["point_by_date"][date] for date in mode_state["point_dates"])
    ]
    return summary


def _apply_portfolio_review_transaction(summary, mode_state, item):
    price = float(item.get("price") or 0.0)
    quantity = float(item.get("quantity") or 0.0)
    fee = float(item.get("fee") or 0.0)
    realized_pnl = float(item.get("realized_pnl") or 0.0)
    position_id = item.get("position_id") or ""
    position = mode_state["positions"].setdefault(position_id, {"quantity": 0.0, "cost_basis": 0.0})
    buy_amount = 0.0
    sell_amount = 0.0

    summary["trade_count"] += 1
    if item.get("type") == "buy":
        buy_amount = price * quantity + fee
        position["quantity"] += quantity
        position["cost_basis"] += buy_amount
        mode_state["quantity"] += quantity
        mode_state["cost_basis"] += buy_amount
        summary["buy_count"] += 1
    else:
        sell_amount = price * quantity - fee
        current_quantity = float(position.get("quantity") or 0.0)
        average_cost = position["cost_basis"] / current_quantity if current_quantity else 0.0
        cost_removed = average_cost * quantity
        position["quantity"] -= quantity
        position["cost_basis"] -= cost_removed
        mode_state["quantity"] -= quantity
        mode_state["cost_basis"] -= cost_removed
        summary["sell_count"] += 1
        if abs(position["quantity"]) < 1e-9:
            position["quantity"] = 0.0
            position["cost_basis"] = 0.0

    if abs(mode_state["quantity"]) < 1e-9:
        mode_state["quantity"] = 0.0
        mode_state["cost_basis"] = 0.0

    mode_state["cumulative_buy_amount"] += buy_amount
    mode_state["cumulative_sell_amount"] += sell_amount
    mode_state["cumulative_fee"] += fee
    mode_state["cumulative_realized_pnl"] += realized_pnl

    date = _portfolio_review_trade_date(item)
    if date not in mode_state["point_by_date"]:
        mode_state["point_by_date"][date] = _empty_portfolio_review_point(date)
        mode_state["point_dates"].append(date)
    point = mode_state["point_by_date"][date]
    point["trade_count"] += 1
    point["buy_amount"] += buy_amount
    point["sell_amount"] += sell_amount
    point["fee"] += fee
    point["realized_pnl"] += realized_pnl
    point["cumulative_buy_amount"] = mode_state["cumulative_buy_amount"]
    point["cumulative_sell_amount"] = mode_state["cumulative_sell_amount"]
    point["cumulative_fee"] = mode_state["cumulative_fee"]
    point["cumulative_realized_pnl"] = mode_state["cumulative_realized_pnl"]
    point["net_invested"] = mode_state["cumulative_buy_amount"] - mode_state["cumulative_sell_amount"]
    point["quantity"] = mode_state["quantity"]
    point["cost_basis"] = mode_state["cost_basis"]

    if date != "未标日期":
        if not summary["first_trade_date"]:
            summary["first_trade_date"] = date
        summary["last_trade_date"] = date


def _build_portfolio_review_from_replay(enriched_transactions):
    review = empty_portfolio_review()
    mode_states = {
        "rmb": _empty_portfolio_review_mode_state(),
        "usd": _empty_portfolio_review_mode_state(),
    }
    for item in _sorted_portfolio_transactions(enriched_transactions):
        mode = item.get("mode")
        if mode not in PORTFOLIO_MODES:
            continue
        _apply_portfolio_review_transaction(review[mode], mode_states[mode], item)
    for mode in PORTFOLIO_MODES:
        _finalize_portfolio_review_summary(review[mode], mode_states[mode])
    return review


def build_portfolio_review_from_transactions(items):
    normalized = normalize_portfolio_transactions(items)
    _states, enriched_transactions = replay_portfolio_transactions(normalized)
    return _build_portfolio_review_from_replay(enriched_transactions)


def _value_transaction_position(position, prices):
    item = dict(position)
    mode = item.get("mode")
    prices = prices if isinstance(prices, dict) else {}
    quantity = float(item.get("quantity") or 0.0)
    cost_basis = float(item.get("cost_basis") or 0.0)
    realized_pnl = float(item.get("realized_pnl") or 0.0)
    current_price = _positive_float_or_none(prices.get(mode))

    item.update({
        "quantity": _round_value(quantity),
        "average_cost": _round_value(item.get("average_cost")),
        "cost_basis": _round_value(cost_basis),
        "cost": _round_value(cost_basis),
        "current_price": current_price,
        "market_value": None,
        "unrealized_pnl": None,
        "unrealized_pnl_percent": None,
        "realized_pnl": _round_value(realized_pnl),
        "total_pnl": _round_value(realized_pnl),
        "fees": _round_value(item.get("fees") or 0.0),
        "pnl": None,
        "pnl_percent": None,
        "entry_price": _round_value(item.get("average_cost")),
        "entry_date": item.get("last_trade_date", ""),
        "valuation_status": "valued",
    })

    if quantity <= 0:
        item.update({
            "market_value": 0.0,
            "unrealized_pnl": 0.0,
            "unrealized_pnl_percent": 0.0,
            "total_pnl": _round_value(realized_pnl),
            "pnl": 0.0,
            "pnl_percent": 0.0,
            "valuation_status": "closed",
        })
        return item

    if current_price is None:
        item["valuation_status"] = "waiting_price"
        return item

    market_value = current_price * quantity
    unrealized_pnl = market_value - cost_basis
    unrealized_percent = (unrealized_pnl / cost_basis) * 100 if cost_basis else 0.0
    item.update({
        "market_value": _round_value(market_value),
        "unrealized_pnl": _round_value(unrealized_pnl),
        "unrealized_pnl_percent": _round_value(unrealized_percent),
        "total_pnl": _round_value(realized_pnl + unrealized_pnl),
        "pnl": _round_value(unrealized_pnl),
        "pnl_percent": _round_value(unrealized_percent),
    })
    return item


def _add_transaction_position_to_summary(summary, item):
    summary["count"] += 1
    summary["quantity"] = _round_value(summary["quantity"] + float(item.get("quantity") or 0.0))
    summary["cost_basis"] = _round_value(summary["cost_basis"] + float(item.get("cost_basis") or 0.0))
    summary["cost"] = summary["cost_basis"]
    summary["realized_pnl"] = _round_value(summary["realized_pnl"] + float(item.get("realized_pnl") or 0.0))
    summary["fees"] = _round_value(summary["fees"] + float(item.get("fees") or 0.0))
    if item.get("valuation_status") == "valued":
        summary["valued"] += 1
        summary["market_value"] = _round_value(summary["market_value"] + float(item.get("market_value") or 0.0))
        summary["unrealized_pnl"] = _round_value(summary["unrealized_pnl"] + float(item.get("unrealized_pnl") or 0.0))
    elif item.get("valuation_status") == "closed":
        summary["valued"] += 1
        summary["unrealized_pnl"] = _round_value(summary["unrealized_pnl"] + float(item.get("unrealized_pnl") or 0.0))
    summary["total_pnl"] = _round_value(summary["realized_pnl"] + summary["unrealized_pnl"])
    summary["pnl"] = summary["total_pnl"]
    summary["unrealized_pnl_percent"] = (
        _round_value((summary["unrealized_pnl"] / summary["cost_basis"]) * 100)
        if summary["cost_basis"] else 0.0
    )
    summary["pnl_percent"] = (
        _round_value((summary["total_pnl"] / summary["cost_basis"]) * 100)
        if summary["cost_basis"] else 0.0
    )


def build_portfolio_state_from_transactions(items, prices):
    normalized = normalize_portfolio_transactions(items)
    states, enriched_transactions = replay_portfolio_transactions(normalized)
    review = _build_portfolio_review_from_replay(enriched_transactions)
    valued_items = [
        _value_transaction_position(position, prices)
        for position in states.values()
    ]
    valued_items.sort(key=lambda item: (item.get("mode") or "", item.get("name") or "", item.get("id") or ""))
    rmb_summary = empty_portfolio_transaction_summary()
    usd_summary = empty_portfolio_transaction_summary()
    for item in valued_items:
        if item.get("mode") == "usd":
            _add_transaction_position_to_summary(usd_summary, item)
        else:
            _add_transaction_position_to_summary(rmb_summary, item)
    enriched_transactions.sort(key=_portfolio_transaction_sort_key)
    return {
        "items": valued_items,
        "transactions": enriched_transactions,
        "total": len(valued_items),
        "rmb_summary": rmb_summary,
        "usd_summary": usd_summary,
        "prices": dict(prices or {}),
        "review": review,
    }


def _portfolio_markdown_generated_at(generated_at=None):
    if generated_at is None:
        generated_at = datetime.now()
    if hasattr(generated_at, "strftime"):
        return generated_at.strftime("%Y-%m-%d %H:%M:%S")
    text = _clean_text(generated_at)
    return text.replace("T", " ")[:19] if text else datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _portfolio_markdown_cell(value):
    text = "--" if value is None or value == "" else str(value)
    return text.replace("\n", " ").replace("|", "\\|")


def _portfolio_markdown_number(value, digits=4):
    if value is None or value == "":
        return "--"
    try:
        number = _round_value(value, digits)
    except (TypeError, ValueError):
        return _portfolio_markdown_cell(value)
    if number is None:
        return "--"
    if abs(number) < 1e-9:
        number = 0.0
    text = f"{number:.{digits}f}".rstrip("0").rstrip(".")
    return text or "0"


def _portfolio_markdown_mode_title(mode):
    return "美元" if mode == "usd" else "人民币"


def _portfolio_markdown_type_label(item):
    return "卖出" if item.get("type") == "sell" else "买入"


def _append_portfolio_review_summary(lines, mode, summary):
    title = _portfolio_markdown_mode_title(mode)
    lines.extend([
        f"### {title}复盘",
        "",
        "| 指标 | 数值 |",
        "| --- | --- |",
        f"| 流水数量 | {_portfolio_markdown_number(summary.get('trade_count'), 0)} |",
        f"| 买入金额 | {_portfolio_markdown_number(summary.get('buy_amount'))} |",
        f"| 卖出金额 | {_portfolio_markdown_number(summary.get('sell_amount'))} |",
        f"| 手续费 | {_portfolio_markdown_number(summary.get('fee_total'))} |",
        f"| 已实现 | {_portfolio_markdown_number(summary.get('realized_pnl'))} |",
        f"| 净投入 | {_portfolio_markdown_number(summary.get('net_invested'))} |",
        f"| 当前数量 | {_portfolio_markdown_number(summary.get('current_quantity'))} |",
        f"| 剩余成本 | {_portfolio_markdown_number(summary.get('cost_basis'))} |",
        f"| 平均成本 | {_portfolio_markdown_number(summary.get('average_cost'))} |",
        f"| 首笔日期 | {_portfolio_markdown_cell(summary.get('first_trade_date'))} |",
        f"| 最近日期 | {_portfolio_markdown_cell(summary.get('last_trade_date'))} |",
        "",
    ])


def _append_portfolio_positions_table(lines, items):
    lines.extend([
        "## 当前持仓",
        "",
        "| 名称 | 单位 | 数量 | 平均成本 | 剩余成本 | 市值 | 未实现 | 已实现 | 合计 | 手续费 | 最近交易 | 状态 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ])
    if not items:
        lines.extend(["| -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- |", ""])
        return
    for item in items:
        mode = item.get("mode") or "rmb"
        lines.append(
            "| "
            + " | ".join([
                _portfolio_markdown_cell(item.get("name") or "未命名持仓"),
                _portfolio_markdown_mode_title(mode),
                _portfolio_markdown_number(item.get("quantity")),
                _portfolio_markdown_number(item.get("average_cost")),
                _portfolio_markdown_number(item.get("cost_basis")),
                _portfolio_markdown_number(item.get("market_value")),
                _portfolio_markdown_number(item.get("unrealized_pnl")),
                _portfolio_markdown_number(item.get("realized_pnl")),
                _portfolio_markdown_number(item.get("total_pnl")),
                _portfolio_markdown_number(item.get("fees")),
                _portfolio_markdown_cell(item.get("last_trade_date")),
                _portfolio_markdown_cell(item.get("valuation_status")),
            ])
            + " |"
        )
    lines.append("")


def _append_portfolio_transactions_table(lines, transactions):
    lines.extend([
        "## 流水明细",
        "",
        "| 日期 | 类型 | 名称 | 单位 | 成交价 | 数量 | 手续费 | 已实现 | 持仓 ID | 流水 ID | 备注 |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- |",
    ])
    if not transactions:
        lines.extend(["| -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- |", ""])
        return
    for item in transactions:
        mode = item.get("mode") or "rmb"
        lines.append(
            "| "
            + " | ".join([
                _portfolio_markdown_cell(item.get("trade_date")),
                _portfolio_markdown_type_label(item),
                _portfolio_markdown_cell(item.get("name") or "未命名流水"),
                _portfolio_markdown_mode_title(mode),
                _portfolio_markdown_number(item.get("price")),
                _portfolio_markdown_number(item.get("quantity")),
                _portfolio_markdown_number(item.get("fee")),
                _portfolio_markdown_number(item.get("realized_pnl")),
                _portfolio_markdown_cell(item.get("position_id")),
                _portfolio_markdown_cell(item.get("id")),
                _portfolio_markdown_cell(item.get("note")),
            ])
            + " |"
        )
    lines.append("")


def build_portfolio_review_markdown(items, prices, generated_at=None):
    state = build_portfolio_state_from_transactions(items, prices)
    transactions = state["transactions"]
    lines = [
        "# 持仓复盘",
        "",
        f"导出时间：{_portfolio_markdown_generated_at(generated_at)}",
        f"持仓数量：{state['total']}",
        f"流水数量：{len(transactions)}",
        "",
        "## 复盘总览",
        "",
    ]
    _append_portfolio_review_summary(lines, "rmb", state["review"]["rmb"])
    _append_portfolio_review_summary(lines, "usd", state["review"]["usd"])
    _append_portfolio_positions_table(lines, state["items"])
    _append_portfolio_transactions_table(lines, transactions)
    return "\n".join(lines).rstrip() + "\n", len(transactions)


class PortfolioPositionStore:
    def __init__(self, json_path, now_factory=None, id_factory=None):
        self.json_path = json_path
        self.now_factory = now_factory or datetime.now
        self.id_factory = id_factory or generate_portfolio_position_id

    def normalize(self, items):
        return normalize_portfolio_positions(
            items,
            now_factory=self.now_factory,
            id_factory=self.id_factory,
        )

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
        payload = wrap_item_payload(
            normalized,
            updated_at=self.now_factory().isoformat(timespec="seconds"),
        )
        tmp_path = self.json_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.json_path)
        return normalized


class PortfolioTransactionStore:
    def __init__(self, json_path, legacy_positions_path=None, now_factory=None, id_factory=None, position_id_factory=None):
        self.json_path = json_path
        self.legacy_positions_path = legacy_positions_path
        self.now_factory = now_factory or datetime.now
        self.id_factory = id_factory or generate_portfolio_transaction_id
        self.position_id_factory = position_id_factory or generate_portfolio_position_id

    def normalize(self, items):
        return normalize_portfolio_transactions(
            items,
            now_factory=self.now_factory,
            id_factory=self.id_factory,
            position_id_factory=self.position_id_factory,
        )

    def _load_legacy_positions(self):
        if not self.legacy_positions_path or not os.path.exists(self.legacy_positions_path):
            return []
        try:
            with open(self.legacy_positions_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            return normalize_portfolio_positions(
                unwrap_item_payload(payload),
                now_factory=self.now_factory,
                id_factory=self.position_id_factory,
            )
        except (OSError, json.JSONDecodeError):
            return []

    def load(self):
        if os.path.exists(self.json_path):
            try:
                with open(self.json_path, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                normalized = self.normalize(unwrap_item_payload(payload))
                validate_portfolio_transactions(normalized)
            except (OSError, json.JSONDecodeError, ValueError):
                return []
            if normalized:
                return normalized

        legacy_positions = self._load_legacy_positions()
        migrated = transactions_from_positions(legacy_positions, now_factory=self.now_factory)
        if not migrated:
            return []
        try:
            return self.save(migrated)
        except OSError:
            return migrated

    def save(self, items):
        normalized = self.normalize(items)
        validate_portfolio_transactions(normalized)
        os.makedirs(os.path.dirname(self.json_path) or ".", exist_ok=True)
        payload = wrap_item_payload(
            normalized,
            updated_at=self.now_factory().isoformat(timespec="seconds"),
        )
        tmp_path = self.json_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.json_path)
        return normalized


def build_portfolio_csv(items, prices):
    state = build_portfolio_state(items, prices)
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=PORTFOLIO_CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for item in state["items"]:
        writer.writerow({field: item.get(field) for field in PORTFOLIO_CSV_FIELDS})
    return buffer.getvalue(), state["total"]


def build_portfolio_positions_csv(items, prices):
    state = build_portfolio_state_from_transactions(items, prices)
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=PORTFOLIO_POSITION_CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for item in state["items"]:
        writer.writerow({field: item.get(field) for field in PORTFOLIO_POSITION_CSV_FIELDS})
    return buffer.getvalue(), state["total"]


def build_portfolio_transactions_csv(items):
    state = build_portfolio_state_from_transactions(items, {})
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=PORTFOLIO_TRANSACTION_CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for item in state["transactions"]:
        writer.writerow({field: item.get(field) for field in PORTFOLIO_TRANSACTION_CSV_FIELDS})
    return buffer.getvalue(), len(state["transactions"])


def _portfolio_csv_reader(csv_text):
    text = str(csv_text or "").strip()
    if not text:
        raise ValueError("CSV 内容不能为空")
    reader = csv.DictReader(StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV 缺少表头")
    reader.fieldnames = [_clean_text(field).lstrip("\ufeff") for field in reader.fieldnames]
    return reader


def import_portfolio_transactions_csv(
    existing_items,
    csv_text,
    now_factory=None,
    id_factory=None,
    position_id_factory=None,
):
    merged, imported_ids = _merge_portfolio_transactions_csv(
        existing_items,
        csv_text,
        now_factory=now_factory,
        id_factory=id_factory,
        position_id_factory=position_id_factory,
    )
    return merged, len(imported_ids)


def preview_portfolio_transactions_csv(
    existing_items,
    csv_text,
    now_factory=None,
    id_factory=None,
    position_id_factory=None,
):
    try:
        _merged, imported_ids = _merge_portfolio_transactions_csv(
            existing_items,
            csv_text,
            now_factory=now_factory,
            id_factory=id_factory,
            position_id_factory=position_id_factory,
        )
    except ValueError as exc:
        return {
            "ok": False,
            "kind": "transactions",
            "count": 0,
            "create": 0,
            "overwrite": 0,
            "message": str(exc),
        }
    existing = normalize_portfolio_transactions(
        list(existing_items or []),
        now_factory=now_factory,
        id_factory=id_factory,
        position_id_factory=position_id_factory,
    )
    existing_ids = {item["id"] for item in existing}
    overwrite = sum(1 for transaction_id in imported_ids if transaction_id in existing_ids)
    return {
        "ok": True,
        "kind": "transactions",
        "count": len(imported_ids),
        "create": len(imported_ids) - overwrite,
        "overwrite": overwrite,
        "message": "",
    }


def _merge_portfolio_transactions_csv(
    existing_items,
    csv_text,
    now_factory=None,
    id_factory=None,
    position_id_factory=None,
):
    reader = _portfolio_csv_reader(csv_text)
    required_fields = {"name", "type", "mode", "price", "quantity"}
    missing_fields = sorted(field for field in required_fields if field not in reader.fieldnames)
    if missing_fields:
        raise ValueError("CSV 缺少必要字段: " + ", ".join(missing_fields))

    existing = normalize_portfolio_transactions(
        list(existing_items or []),
        now_factory=now_factory,
        id_factory=id_factory,
        position_id_factory=position_id_factory,
    )
    by_id = {item["id"]: dict(item) for item in existing}
    imported_ids = []
    for index, row in enumerate(reader, start=2):
        if not row or not any(_clean_text(value) for value in row.values()):
            continue
        try:
            normalized = normalize_portfolio_transaction(
                row,
                existing=by_id.get(_valid_position_id(row.get("id"))),
                now_factory=now_factory,
                id_factory=id_factory,
                position_id_factory=position_id_factory,
            )
        except ValueError as exc:
            raise ValueError(f"第 {index} 行导入失败: {exc}") from exc
        by_id[normalized["id"]] = normalized
        if normalized["id"] not in imported_ids:
            imported_ids.append(normalized["id"])

    if not imported_ids:
        raise ValueError("CSV 没有可导入流水")

    imported_set = set(imported_ids)
    merged = [by_id[item["id"]] for item in existing if item["id"] not in imported_set]
    merged.extend(by_id[transaction_id] for transaction_id in imported_ids)
    validate_portfolio_transactions(merged)
    return normalize_portfolio_transactions(
        merged,
        now_factory=now_factory,
        id_factory=id_factory,
        position_id_factory=position_id_factory,
    ), imported_ids
