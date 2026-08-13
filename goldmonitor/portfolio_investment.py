import calendar
import csv
import json
import math
import os
import secrets
from datetime import datetime, timedelta
from io import StringIO

from .data_contracts import unwrap_item_payload, wrap_item_payload


INVESTMENT_PLAN_SCHEMA_VERSION = 1
INVESTMENT_FREQUENCIES = {"daily", "weekly", "monthly", "yearly"}
INVESTMENT_EXECUTION_KINDS = {"scheduled", "catch_up", "manual"}
INVESTMENT_EXECUTION_HISTORY_LIMIT = 10
INVESTMENT_EXECUTION_CSV_FIELDS = [
    "plan_id",
    "plan_name",
    "transaction_id",
    "execution_kind",
    "scheduled_at",
    "executed_at",
    "trade_date",
    "mode",
    "planned_amount",
    "price",
    "quantity",
    "gross_amount",
    "fee",
    "total_cost",
    "position_id",
    "position_name",
    "note",
]


def generate_investment_plan_id():
    return "investment-plan-" + secrets.token_hex(8)


def _clean_text(value, limit=None):
    text = str(value or "").strip()
    return text[:limit] if limit is not None else text


def _positive_float(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _nonnegative_float(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _bounded_int(value, minimum, maximum, default):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return min(maximum, max(minimum, number))


def _parse_time(value):
    text = _clean_text(value)
    try:
        parsed = datetime.strptime(text, "%H:%M")
    except ValueError as exc:
        raise ValueError("定投执行时间无效") from exc
    return parsed.strftime("%H:%M")


def _schedule_signature(frequency, time_text, month, day, weekday):
    signature = [frequency, time_text]
    if frequency == "weekly":
        signature.append(weekday)
    elif frequency == "monthly":
        signature.append(day)
    elif frequency == "yearly":
        signature.extend([month, day])
    return tuple(signature)


def parse_plan_datetime(value):
    text = _clean_text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _scheduled_datetime(year, month, day, time_text):
    last_day = calendar.monthrange(year, month)[1]
    hour, minute = (int(part) for part in time_text.split(":"))
    return datetime(year, month, min(day, last_day), hour, minute)


def next_plan_run_at(plan, after):
    frequency = plan["frequency"]
    time_text = plan["time"]
    if frequency == "daily":
        candidate = _scheduled_datetime(after.year, after.month, after.day, time_text)
        return candidate if candidate > after else candidate + timedelta(days=1)
    if frequency == "weekly":
        target_weekday = plan["weekday"] - 1
        days_ahead = (target_weekday - after.weekday()) % 7
        candidate_date = after + timedelta(days=days_ahead)
        candidate = _scheduled_datetime(
            candidate_date.year,
            candidate_date.month,
            candidate_date.day,
            time_text,
        )
        return candidate if candidate > after else candidate + timedelta(days=7)
    if frequency == "monthly":
        candidate = _scheduled_datetime(
            after.year,
            after.month,
            plan["day"],
            time_text,
        )
        if candidate > after:
            return candidate
        next_month = after.month + 1
        next_year = after.year
        if next_month > 12:
            next_month = 1
            next_year += 1
        return _scheduled_datetime(next_year, next_month, plan["day"], time_text)
    candidate = _scheduled_datetime(
        after.year,
        plan["month"],
        plan["day"],
        time_text,
    )
    if candidate > after:
        return candidate
    return _scheduled_datetime(
        after.year + 1,
        plan["month"],
        plan["day"],
        time_text,
    )


def latest_due_run_at(plan, now):
    next_run = parse_plan_datetime(plan.get("next_run_at"))
    if next_run is None or next_run > now:
        return None
    time_text = plan["time"]
    if plan["frequency"] == "daily":
        candidate = _scheduled_datetime(now.year, now.month, now.day, time_text)
        return candidate if candidate <= now else candidate - timedelta(days=1)
    if plan["frequency"] == "weekly":
        target_weekday = plan["weekday"] - 1
        days_back = (now.weekday() - target_weekday) % 7
        candidate_date = now - timedelta(days=days_back)
        candidate = _scheduled_datetime(
            candidate_date.year,
            candidate_date.month,
            candidate_date.day,
            time_text,
        )
        return candidate if candidate <= now else candidate - timedelta(days=7)
    if plan["frequency"] == "monthly":
        candidate = _scheduled_datetime(now.year, now.month, plan["day"], time_text)
        if candidate <= now:
            return candidate
        month = now.month - 1
        year = now.year
        if month < 1:
            month = 12
            year -= 1
        return _scheduled_datetime(year, month, plan["day"], time_text)
    candidate = _scheduled_datetime(now.year, plan["month"], plan["day"], time_text)
    if candidate <= now:
        return candidate
    return _scheduled_datetime(now.year - 1, plan["month"], plan["day"], time_text)


def normalize_investment_plan(
    item,
    existing=None,
    *,
    now_factory=None,
    id_factory=None,
):
    if not isinstance(item, dict):
        raise ValueError("定投计划格式无效")
    existing = existing if isinstance(existing, dict) else {}
    now_factory = now_factory or datetime.now
    id_factory = id_factory or generate_investment_plan_id
    now = now_factory()
    now_text = now.isoformat(timespec="seconds")

    plan_id = _clean_text(item.get("id") or existing.get("id"))
    if not plan_id:
        plan_id = id_factory()
    name = _clean_text(item.get("name", existing.get("name", "")), 60)
    if not name:
        raise ValueError("定投计划名称不能为空")
    position_id = _clean_text(
        item.get("position_id", existing.get("position_id", "")),
        80,
    )
    position_name = _clean_text(
        item.get("position_name", existing.get("position_name", "")),
        60,
    )
    if not position_name:
        raise ValueError("定投持仓名称不能为空")
    mode = _clean_text(item.get("mode", existing.get("mode", "rmb"))).lower()
    if mode not in {"rmb", "usd"}:
        raise ValueError("定投持仓单位无效")
    amount = _positive_float(item.get("amount", existing.get("amount")))
    if amount is None:
        raise ValueError("定投金额无效")
    fee = _nonnegative_float(item.get("fee", existing.get("fee", 0)))
    if fee is None:
        raise ValueError("定投手续费不能为负数")
    frequency = _clean_text(
        item.get("frequency", existing.get("frequency", "monthly"))
    ).lower()
    if frequency not in INVESTMENT_FREQUENCIES:
        raise ValueError("定投周期无效")
    time_text = _parse_time(item.get("time", existing.get("time", "09:00")))
    month = _bounded_int(item.get("month", existing.get("month", 1)), 1, 12, 1)
    day = _bounded_int(item.get("day", existing.get("day", 1)), 1, 31, 1)
    weekday = _bounded_int(
        item.get("weekday", existing.get("weekday", 1)),
        1,
        7,
        1,
    )
    enabled = item.get("enabled", existing.get("enabled", True)) is not False

    existing_frequency = _clean_text(existing.get("frequency", "monthly")).lower()
    existing_signature = _schedule_signature(
        existing_frequency,
        _clean_text(existing.get("time", "09:00")),
        _bounded_int(existing.get("month", 1), 1, 12, 1),
        _bounded_int(existing.get("day", 1), 1, 31, 1),
        _bounded_int(existing.get("weekday", 1), 1, 7, 1),
    )
    schedule_changed = existing_signature != _schedule_signature(
        frequency,
        time_text,
        month,
        day,
        weekday,
    ) if existing else False
    was_enabled = existing.get("enabled") is not False if existing else False
    supplied_next_run = parse_plan_datetime(item.get("next_run_at"))
    preserved_next_run = parse_plan_datetime(existing.get("next_run_at"))
    if not enabled:
        next_run_at = ""
    elif existing and was_enabled and not schedule_changed and preserved_next_run:
        next_run_at = preserved_next_run.isoformat(timespec="seconds")
    elif not existing and supplied_next_run:
        next_run_at = supplied_next_run.isoformat(timespec="seconds")
    else:
        schedule_plan = {
            "frequency": frequency,
            "time": time_text,
            "month": month,
            "day": day,
            "weekday": weekday,
        }
        next_run_at = next_plan_run_at(schedule_plan, now).isoformat(timespec="seconds")

    return {
        "id": plan_id,
        "name": name,
        "position_id": position_id,
        "position_name": position_name,
        "mode": mode,
        "amount": amount,
        "fee": fee,
        "frequency": frequency,
        "time": time_text,
        "month": month,
        "day": day,
        "weekday": weekday,
        "enabled": enabled,
        "next_run_at": next_run_at,
        "last_scheduled_at": _clean_text(
            item.get("last_scheduled_at", existing.get("last_scheduled_at", ""))
        ),
        "last_executed_at": _clean_text(
            item.get("last_executed_at", existing.get("last_executed_at", ""))
        ),
        "last_transaction_id": _clean_text(
            item.get("last_transaction_id", existing.get("last_transaction_id", ""))
        ),
        "last_price": item.get("last_price", existing.get("last_price")),
        "last_quantity": item.get("last_quantity", existing.get("last_quantity")),
        "last_result": _clean_text(
            item.get("last_result", existing.get("last_result", "waiting"))
        ) or "waiting",
        "last_message": _clean_text(
            item.get("last_message", existing.get("last_message", "等待首次执行")),
            200,
        ) or "等待首次执行",
        "created_at": _clean_text(existing.get("created_at") or item.get("created_at") or now_text),
        "updated_at": now_text,
    }


def normalize_investment_plans(items, *, now_factory=None, id_factory=None):
    normalized = []
    seen = set()
    for item in list(items or []):
        try:
            plan = normalize_investment_plan(
                item,
                now_factory=now_factory,
                id_factory=id_factory,
            )
        except ValueError:
            continue
        if plan["id"] in seen:
            continue
        seen.add(plan["id"])
        normalized.append(plan)
    return normalized


def investment_plan_executions(plan, transactions):
    plan_id = _clean_text((plan or {}).get("id"))
    if not plan_id:
        return []
    executions = []
    for raw in list(transactions or []):
        if not isinstance(raw, dict):
            continue
        if raw.get("source") != "investment_plan" or _clean_text(raw.get("source_id")) != plan_id:
            continue
        if raw.get("type") != "buy":
            continue
        price = _positive_float(raw.get("price"))
        quantity = _positive_float(raw.get("quantity"))
        fee = _nonnegative_float(raw.get("fee"))
        if price is None or quantity is None or fee is None:
            continue
        gross_amount = price * quantity
        total_cost = gross_amount + fee
        executions.append({
            "id": _clean_text(raw.get("id")),
            "plan_id": plan_id,
            "plan_name": _clean_text((plan or {}).get("name")),
            "timestamp": _clean_text(raw.get("created_at") or raw.get("updated_at")),
            "trade_date": _clean_text(raw.get("trade_date")),
            "scheduled_at": _clean_text(raw.get("scheduled_at")),
            "execution_kind": _clean_text(raw.get("execution_kind")),
            "mode": _clean_text(raw.get("mode") or (plan or {}).get("mode")),
            "position_id": _clean_text(raw.get("position_id")),
            "position_name": _clean_text(raw.get("name")),
            "price": price,
            "quantity": quantity,
            "fee": fee,
            "planned_amount": raw.get("planned_amount"),
            "gross_amount": gross_amount,
            "total_cost": total_cost,
            "note": _clean_text(raw.get("note")),
        })
    executions.sort(
        key=lambda item: (
            item.get("timestamp") or item.get("scheduled_at") or item.get("trade_date") or "",
            item.get("id") or "",
        ),
        reverse=True,
    )
    return executions


def build_investment_plan_executions_csv(plan, transactions):
    plan_id = _clean_text((plan or {}).get("id"))
    if not plan_id:
        raise ValueError("定投计划标识不能为空")
    executions = investment_plan_executions(plan, transactions)
    buffer = StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=INVESTMENT_EXECUTION_CSV_FIELDS,
        lineterminator="\n",
    )
    writer.writeheader()
    for item in reversed(executions):
        writer.writerow({
            "plan_id": item.get("plan_id"),
            "plan_name": item.get("plan_name"),
            "transaction_id": item.get("id"),
            "execution_kind": item.get("execution_kind"),
            "scheduled_at": item.get("scheduled_at"),
            "executed_at": item.get("timestamp"),
            "trade_date": item.get("trade_date"),
            "mode": item.get("mode"),
            "planned_amount": item.get("planned_amount"),
            "price": item.get("price"),
            "quantity": item.get("quantity"),
            "gross_amount": item.get("gross_amount"),
            "fee": item.get("fee"),
            "total_cost": item.get("total_cost"),
            "position_id": item.get("position_id"),
            "position_name": item.get("position_name"),
            "note": item.get("note"),
        })
    return buffer.getvalue(), len(executions)


def investment_plan_performance(plan, transactions, current_price=None, history_limit=INVESTMENT_EXECUTION_HISTORY_LIMIT):
    executions = investment_plan_executions(plan, transactions)
    total_quantity = sum(item["quantity"] for item in executions)
    gross_invested = sum(item["gross_amount"] for item in executions)
    total_fees = sum(item["fee"] for item in executions)
    total_invested = gross_invested + total_fees
    average_price = gross_invested / total_quantity if total_quantity > 0 else None
    average_cost = total_invested / total_quantity if total_quantity > 0 else None
    price = _positive_float(current_price)
    market_value = total_quantity * price if price is not None and total_quantity > 0 else None
    pnl = market_value - total_invested if market_value is not None else None
    pnl_percent = pnl / total_invested * 100 if pnl is not None and total_invested > 0 else None
    return {
        "execution_count": len(executions),
        "total_quantity": total_quantity,
        "gross_invested": gross_invested,
        "total_fees": total_fees,
        "total_invested": total_invested,
        "average_price": average_price,
        "average_cost": average_cost,
        "current_price": price,
        "market_value": market_value,
        "pnl": pnl,
        "pnl_percent": pnl_percent,
        "valuation_status": "valued" if market_value is not None else "waiting_price" if executions else "empty",
        "recent_executions": executions[:max(1, int(history_limit))],
    }


def investment_plan_state(items, *, now=None, transactions=None, prices=None):
    now = now or datetime.now()
    prices = prices if isinstance(prices, dict) else {}
    plans = []
    summary = {
        "total": 0,
        "enabled": 0,
        "due": 0,
        "attention": 0,
        "execution_count": 0,
        "rmb_invested": 0.0,
        "usd_invested": 0.0,
    }
    for raw in list(items or []):
        plan = dict(raw)
        next_run = parse_plan_datetime(plan.get("next_run_at"))
        if plan.get("enabled"):
            status = "due" if next_run and next_run <= now else "active"
            summary["enabled"] += 1
            if status == "due":
                summary["due"] += 1
        else:
            status = "paused"
        if plan.get("last_result") in {"error", "waiting_price", "orphaned"}:
            summary["attention"] += 1
        plan["status"] = status
        performance = investment_plan_performance(
            plan,
            transactions,
            current_price=prices.get(plan.get("mode")),
        )
        plan["performance"] = performance
        summary["execution_count"] += performance["execution_count"]
        invested_key = "usd_invested" if plan.get("mode") == "usd" else "rmb_invested"
        summary[invested_key] += performance["total_invested"]
        plans.append(plan)
    summary["total"] = len(plans)
    return {
        "items": plans,
        "summary": summary,
        "updated_at": now.isoformat(timespec="seconds"),
    }


class InvestmentPlanStore:
    def __init__(self, path, *, now_factory=None, id_factory=None):
        self.path = str(path or "")
        self.now_factory = now_factory or datetime.now
        self.id_factory = id_factory or generate_investment_plan_id

    def load(self):
        if not self.path or not os.path.exists(self.path):
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as file_handle:
                payload = json.load(file_handle)
        except (OSError, json.JSONDecodeError):
            return []
        return normalize_investment_plans(
            unwrap_item_payload(payload),
            now_factory=self.now_factory,
            id_factory=self.id_factory,
        )

    def save(self, items):
        normalized = normalize_investment_plans(
            items,
            now_factory=self.now_factory,
            id_factory=self.id_factory,
        )
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        payload = wrap_item_payload(
            normalized,
            updated_at=self.now_factory().isoformat(timespec="seconds"),
            schema_version=INVESTMENT_PLAN_SCHEMA_VERSION,
        )
        temporary_path = self.path + ".tmp"
        with open(temporary_path, "w", encoding="utf-8") as file_handle:
            json.dump(payload, file_handle, ensure_ascii=False, indent=2)
        os.replace(temporary_path, self.path)
        return normalized
