import calendar
import csv
import json
import math
import os
import secrets
from datetime import date, datetime, timedelta
from io import StringIO

from .data_contracts import unwrap_item_payload, wrap_item_payload


INVESTMENT_PLAN_SCHEMA_VERSION = 1
INVESTMENT_FREQUENCIES = {"daily", "weekly", "monthly", "yearly"}
INVESTMENT_EXECUTION_KINDS = {"scheduled", "catch_up", "manual"}
INVESTMENT_EXECUTION_HISTORY_LIMIT = 10
INVESTMENT_SCHEDULE_PREVIEW_LIMIT = 5
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


def _nonnegative_int(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 0
    return max(0, number)


def _target_count(value):
    if value in (None, "", 0, "0"):
        return 0
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("定投目标期数必须为 1 至 10000 的整数") from exc
    if not math.isfinite(number) or not number.is_integer() or not 1 <= number <= 10000:
        raise ValueError("定投目标期数必须为 1 至 10000 的整数")
    return int(number)


def _parse_time(value):
    text = _clean_text(value)
    try:
        parsed = datetime.strptime(text, "%H:%M")
    except ValueError as exc:
        raise ValueError("定投执行时间无效") from exc
    return parsed.strftime("%H:%M")


def _parse_date(value, field_name):
    text = _clean_text(value)
    if not text:
        return ""
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValueError(f"定投{field_name}无效") from exc


def normalize_investment_schedule(item, existing=None):
    if not isinstance(item, dict):
        raise ValueError("定投计划格式无效")
    existing = existing if isinstance(existing, dict) else {}
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
    start_date = _parse_date(
        item.get("start_date", existing.get("start_date", "")),
        "开始日期",
    )
    end_date = _parse_date(
        item.get("end_date", existing.get("end_date", "")),
        "结束日期",
    )
    if start_date and end_date and start_date > end_date:
        raise ValueError("定投结束日期不能早于开始日期")
    return {
        "frequency": frequency,
        "time": time_text,
        "month": month,
        "day": day,
        "weekday": weekday,
        "start_date": start_date,
        "end_date": end_date,
    }


def _schedule_signature(
    frequency,
    time_text,
    month,
    day,
    weekday,
    start_date="",
    end_date="",
):
    signature = [frequency, time_text]
    if frequency == "weekly":
        signature.append(weekday)
    elif frequency == "monthly":
        signature.append(day)
    elif frequency == "yearly":
        signature.extend([month, day])
    signature.extend([start_date, end_date])
    return tuple(signature)


def _schedule_signature_from_plan(plan):
    return _schedule_signature(
        plan["frequency"],
        plan["time"],
        plan["month"],
        plan["day"],
        plan["weekday"],
        plan.get("start_date", ""),
        plan.get("end_date", ""),
    )


def parse_plan_datetime(value):
    text = _clean_text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def parse_plan_date(value):
    text = _clean_text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text)
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


def next_plan_run_in_window(plan, after):
    anchor = after
    start_date = parse_plan_date(plan.get("start_date"))
    if start_date and start_date > after.date():
        anchor = datetime.combine(start_date, datetime.min.time()) - timedelta(microseconds=1)
    candidate = next_plan_run_at(plan, anchor)
    end_date = parse_plan_date(plan.get("end_date"))
    return None if end_date and candidate.date() > end_date else candidate


def latest_due_run_at(plan, now):
    next_run = parse_plan_datetime(plan.get("next_run_at"))
    end_date = parse_plan_date(plan.get("end_date"))
    effective_now = now
    if end_date and now.date() > end_date:
        effective_now = _scheduled_datetime(
            end_date.year,
            end_date.month,
            end_date.day,
            plan["time"],
        )
    if next_run is None or next_run > effective_now:
        return None
    time_text = plan["time"]
    if plan["frequency"] == "daily":
        candidate = _scheduled_datetime(
            effective_now.year,
            effective_now.month,
            effective_now.day,
            time_text,
        )
        candidate = candidate if candidate <= effective_now else candidate - timedelta(days=1)
    elif plan["frequency"] == "weekly":
        target_weekday = plan["weekday"] - 1
        days_back = (effective_now.weekday() - target_weekday) % 7
        candidate_date = effective_now - timedelta(days=days_back)
        candidate = _scheduled_datetime(
            candidate_date.year,
            candidate_date.month,
            candidate_date.day,
            time_text,
        )
        candidate = candidate if candidate <= effective_now else candidate - timedelta(days=7)
    elif plan["frequency"] == "monthly":
        candidate = _scheduled_datetime(
            effective_now.year,
            effective_now.month,
            plan["day"],
            time_text,
        )
        if candidate > effective_now:
            month = effective_now.month - 1
            year = effective_now.year
            if month < 1:
                month = 12
                year -= 1
            candidate = _scheduled_datetime(year, month, plan["day"], time_text)
    else:
        candidate = _scheduled_datetime(
            effective_now.year,
            plan["month"],
            plan["day"],
            time_text,
        )
        if candidate > effective_now:
            candidate = _scheduled_datetime(
                effective_now.year - 1,
                plan["month"],
                plan["day"],
                time_text,
            )
    start_date = parse_plan_date(plan.get("start_date"))
    if start_date and candidate.date() < start_date:
        return None
    return candidate


def pending_plan_run_at(plan, now):
    if plan.get("enabled") is False:
        return None
    due_at = latest_due_run_at(plan, now)
    if due_at is not None:
        return due_at
    next_run = parse_plan_datetime(plan.get("next_run_at"))
    if next_run is None:
        return None
    start_date = parse_plan_date(plan.get("start_date"))
    end_date = parse_plan_date(plan.get("end_date"))
    if start_date and next_run.date() < start_date:
        return None
    if end_date and next_run.date() > end_date:
        return None
    return next_run


def investment_schedule_preview(
    item,
    *,
    existing=None,
    now=None,
    limit=INVESTMENT_SCHEDULE_PREVIEW_LIMIT,
):
    now = now or datetime.now()
    existing = existing if isinstance(existing, dict) else {}
    schedule = normalize_investment_schedule(item, existing)
    preview_limit = _bounded_int(
        limit,
        1,
        12,
        INVESTMENT_SCHEDULE_PREVIEW_LIMIT,
    )
    target_count = _target_count(
        item.get("target_count", existing.get("target_count", 0))
    )
    completed_count = _nonnegative_int(
        item.get("completed_count", existing.get("completed_count", 0))
    )
    if target_count:
        preview_limit = min(preview_limit, max(0, target_count - completed_count))
    if preview_limit <= 0:
        return []
    existing_schedule = normalize_investment_schedule(existing) if existing else None
    schedule_unchanged = bool(
        existing_schedule
        and _schedule_signature_from_plan(existing_schedule)
        == _schedule_signature_from_plan(schedule)
    )
    plan = {**existing, **schedule}
    candidate = pending_plan_run_at(plan, now) if schedule_unchanged else None
    if candidate is None:
        candidate = next_plan_run_in_window(schedule, now)
    run_ats = []
    while candidate is not None and len(run_ats) < preview_limit:
        run_ats.append(candidate.isoformat(timespec="seconds"))
        candidate = next_plan_run_in_window(schedule, candidate)
    return run_ats


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
    target_count = _target_count(
        item.get("target_count", existing.get("target_count", 0))
    )
    schedule = normalize_investment_schedule(item, existing)
    frequency = schedule["frequency"]
    time_text = schedule["time"]
    month = schedule["month"]
    day = schedule["day"]
    weekday = schedule["weekday"]
    start_date = schedule["start_date"]
    end_date = schedule["end_date"]
    archived_at = _clean_text(
        item.get("archived_at", existing.get("archived_at", ""))
    )
    enabled = (
        item.get("enabled", existing.get("enabled", True)) is not False
        and not archived_at
    )

    existing_frequency = _clean_text(existing.get("frequency", "monthly")).lower()
    existing_signature = _schedule_signature(
        existing_frequency,
        _clean_text(existing.get("time", "09:00")),
        _bounded_int(existing.get("month", 1), 1, 12, 1),
        _bounded_int(existing.get("day", 1), 1, 31, 1),
        _bounded_int(existing.get("weekday", 1), 1, 7, 1),
        _clean_text(existing.get("start_date")),
        _clean_text(existing.get("end_date")),
    )
    schedule_changed = existing_signature != _schedule_signature(
        frequency,
        time_text,
        month,
        day,
        weekday,
        start_date,
        end_date,
    ) if existing else False
    was_enabled = existing.get("enabled") is not False if existing else False
    supplied_next_run = parse_plan_datetime(item.get("next_run_at"))
    preserved_next_run = parse_plan_datetime(existing.get("next_run_at"))
    if not enabled:
        next_run_at = ""
    elif existing and was_enabled and not schedule_changed and preserved_next_run:
        next_run_at = preserved_next_run.isoformat(timespec="seconds")
    elif not existing and supplied_next_run:
        supplied_outside_window = (
            (start_date and supplied_next_run.date() < parse_plan_date(start_date))
            or (end_date and supplied_next_run.date() > parse_plan_date(end_date))
        )
        if supplied_outside_window:
            schedule_plan = {
                "frequency": frequency,
                "time": time_text,
                "month": month,
                "day": day,
                "weekday": weekday,
                "start_date": start_date,
                "end_date": end_date,
            }
            next_run = next_plan_run_in_window(schedule_plan, now)
            next_run_at = next_run.isoformat(timespec="seconds") if next_run else ""
        else:
            next_run_at = supplied_next_run.isoformat(timespec="seconds")
    else:
        schedule_plan = {
            "frequency": frequency,
            "time": time_text,
            "month": month,
            "day": day,
            "weekday": weekday,
            "start_date": start_date,
            "end_date": end_date,
        }
        next_run = next_plan_run_in_window(schedule_plan, now)
        next_run_at = next_run.isoformat(timespec="seconds") if next_run else ""

    return {
        "id": plan_id,
        "name": name,
        "position_id": position_id,
        "position_name": position_name,
        "mode": mode,
        "amount": amount,
        "fee": fee,
        "target_count": target_count,
        "frequency": frequency,
        "time": time_text,
        "month": month,
        "day": day,
        "weekday": weekday,
        "start_date": start_date,
        "end_date": end_date,
        "archived_at": archived_at,
        "enabled": enabled,
        "next_run_at": next_run_at,
        "last_scheduled_at": _clean_text(
            item.get("last_scheduled_at", existing.get("last_scheduled_at", ""))
        ),
        "last_executed_at": _clean_text(
            item.get("last_executed_at", existing.get("last_executed_at", ""))
        ),
        "last_skipped_at": _clean_text(
            item.get("last_skipped_at", existing.get("last_skipped_at", ""))
        ),
        "last_skipped_scheduled_at": _clean_text(
            item.get(
                "last_skipped_scheduled_at",
                existing.get("last_skipped_scheduled_at", ""),
            )
        ),
        "skip_count": _nonnegative_int(
            item.get("skip_count", existing.get("skip_count", 0))
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


def investment_plan_execution_count(plan, transactions):
    return len(investment_plan_executions(plan, transactions))


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
        "all_total": 0,
        "archived": 0,
        "enabled": 0,
        "due": 0,
        "attention": 0,
        "execution_count": 0,
        "rmb_invested": 0.0,
        "usd_invested": 0.0,
    }
    for raw in list(items or []):
        plan = dict(raw)
        archived = bool(_clean_text(plan.get("archived_at")))
        next_run = parse_plan_datetime(plan.get("next_run_at"))
        performance = investment_plan_performance(
            plan,
            transactions,
            current_price=prices.get(plan.get("mode")),
        )
        target_count = _target_count(plan.get("target_count", 0))
        completed_count = performance["execution_count"]
        target_reached = bool(target_count and completed_count >= target_count)
        pending_run = None if archived or target_reached else pending_plan_run_at(plan, now)
        if archived:
            status = "archived"
            summary["archived"] += 1
        elif target_reached:
            status = "completed"
            plan["enabled"] = False
            plan["next_run_at"] = ""
        elif plan.get("enabled"):
            start_date = parse_plan_date(plan.get("start_date"))
            end_date = parse_plan_date(plan.get("end_date"))
            if start_date and now.date() < start_date:
                status = "pending_start"
                summary["enabled"] += 1
            elif end_date and (next_run is None or next_run.date() > end_date):
                status = "completed"
            else:
                status = "due" if next_run and next_run <= now else "active"
                summary["enabled"] += 1
                if status == "due":
                    summary["due"] += 1
        else:
            status = "paused"
        if not archived and not target_reached and plan.get("last_result") in {"error", "waiting_price", "orphaned"}:
            summary["attention"] += 1
        plan["status"] = status
        plan["completed_count"] = completed_count
        plan["remaining_count"] = max(0, target_count - completed_count) if target_count else None
        plan["pending_run_at"] = (
            pending_run.isoformat(timespec="seconds") if pending_run else ""
        )
        plan["upcoming_run_ats"] = (
            investment_schedule_preview(
                plan,
                existing=plan,
                now=now,
            )
            if plan.get("enabled") and not archived and not target_reached
            else []
        )
        plan["performance"] = performance
        summary["execution_count"] += performance["execution_count"]
        invested_key = "usd_invested" if plan.get("mode") == "usd" else "rmb_invested"
        summary[invested_key] += performance["total_invested"]
        plans.append(plan)
    summary["all_total"] = len(plans)
    summary["total"] = len(plans) - summary["archived"]
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
