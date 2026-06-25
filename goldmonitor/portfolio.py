import csv
import json
import math
import os
import secrets
from datetime import datetime
from io import StringIO

from .data_contracts import unwrap_item_payload, wrap_item_payload


PORTFOLIO_MODES = {"rmb", "usd"}
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


def generate_portfolio_position_id():
    return "position-" + secrets.token_hex(8)


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


def build_portfolio_csv(items, prices):
    state = build_portfolio_state(items, prices)
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=PORTFOLIO_CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for item in state["items"]:
        writer.writerow({field: item.get(field) for field in PORTFOLIO_CSV_FIELDS})
    return buffer.getvalue(), state["total"]
