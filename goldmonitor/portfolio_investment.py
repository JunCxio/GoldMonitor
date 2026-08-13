import calendar
import csv
import json
import math
import os
import secrets
from bisect import bisect_left
from datetime import date, datetime, timedelta
from io import StringIO

from .data_contracts import unwrap_item_payload, wrap_item_payload


INVESTMENT_PLAN_SCHEMA_VERSION = 1
INVESTMENT_FREQUENCIES = {"daily", "weekly", "monthly", "yearly"}
INVESTMENT_EXECUTION_KINDS = {"scheduled", "catch_up", "manual"}
INVESTMENT_EXECUTION_HISTORY_LIMIT = 10
INVESTMENT_SCHEDULE_PREVIEW_LIMIT = 5
INVESTMENT_COMMITMENT_WINDOW_DAYS = 30
INVESTMENT_ACTUAL_WINDOW_DAYS = 30
INVESTMENT_ACTUAL_TREND_MONTHS = 6
INVESTMENT_RELIABILITY_WINDOW_DAYS = 90
INVESTMENT_SIMULATION_WINDOWS = {7, 30, 90}
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


def _investment_execution_record(raw):
    if not isinstance(raw, dict):
        return None
    if raw.get("source") != "investment_plan" or raw.get("type") != "buy":
        return None
    executed_on = parse_plan_date(raw.get("trade_date"))
    if executed_on is None:
        executed_at = parse_plan_datetime(
            raw.get("created_at") or raw.get("updated_at")
        )
        executed_on = executed_at.date() if executed_at else None
    price = _positive_float(raw.get("price"))
    quantity = _positive_float(raw.get("quantity"))
    fee = _nonnegative_float(raw.get("fee"))
    mode = _clean_text(raw.get("mode")).lower()
    if (
        executed_on is None
        or price is None
        or quantity is None
        or fee is None
        or mode not in {"rmb", "usd"}
    ):
        return None
    return {
        "date": executed_on,
        "mode": mode,
        "total_cost": price * quantity + fee,
        "execution_kind": _clean_text(raw.get("execution_kind")).lower(),
    }


def investment_execution_window_summary(
    transactions,
    *,
    now=None,
    days=INVESTMENT_ACTUAL_WINDOW_DAYS,
):
    now = now or datetime.now()
    window_days = _bounded_int(
        days,
        1,
        366,
        INVESTMENT_ACTUAL_WINDOW_DAYS,
    )
    start_date = now.date() - timedelta(days=window_days - 1)
    result = {
        "days": window_days,
        "execution_count": 0,
        "rmb_invested": 0.0,
        "usd_invested": 0.0,
    }
    for raw in list(transactions or []):
        execution = _investment_execution_record(raw)
        if execution is None or not start_date <= execution["date"] <= now.date():
            continue
        result[execution["mode"] + "_invested"] += execution["total_cost"]
        result["execution_count"] += 1
    return result


def investment_execution_monthly_trend(
    transactions,
    *,
    now=None,
    months=INVESTMENT_ACTUAL_TREND_MONTHS,
):
    now = now or datetime.now()
    month_count = _bounded_int(
        months,
        1,
        24,
        INVESTMENT_ACTUAL_TREND_MONTHS,
    )
    current_month_index = now.year * 12 + now.month - 1
    buckets = []
    by_month = {}
    for offset in range(month_count - 1, -1, -1):
        month_index = current_month_index - offset
        year = month_index // 12
        month = month_index % 12 + 1
        key = f"{year:04d}-{month:02d}"
        bucket = {
            "month": key,
            "execution_count": 0,
            "rmb_invested": 0.0,
            "usd_invested": 0.0,
        }
        buckets.append(bucket)
        by_month[key] = bucket
    first_month = parse_plan_date(buckets[0]["month"] + "-01")
    for raw in list(transactions or []):
        execution = _investment_execution_record(raw)
        if execution is None or not first_month <= execution["date"] <= now.date():
            continue
        bucket = by_month.get(execution["date"].strftime("%Y-%m"))
        if bucket is None:
            continue
        bucket[execution["mode"] + "_invested"] += execution["total_cost"]
        bucket["execution_count"] += 1
    return buckets


def investment_execution_reliability_summary(
    transactions,
    *,
    now=None,
    days=INVESTMENT_RELIABILITY_WINDOW_DAYS,
    source_id=None,
):
    now = now or datetime.now()
    plan_id = _clean_text(source_id)
    window_days = _bounded_int(
        days,
        1,
        366,
        INVESTMENT_RELIABILITY_WINDOW_DAYS,
    )
    start_date = now.date() - timedelta(days=window_days - 1)
    result = {
        "days": window_days,
        "automatic_execution_count": 0,
        "on_time_execution_count": 0,
        "catch_up_execution_count": 0,
        "manual_execution_count": 0,
        "unclassified_execution_count": 0,
        "on_time_rate": None,
    }
    for raw in list(transactions or []):
        if plan_id and (
            not isinstance(raw, dict)
            or _clean_text(raw.get("source_id")) != plan_id
        ):
            continue
        execution = _investment_execution_record(raw)
        if execution is None or not start_date <= execution["date"] <= now.date():
            continue
        execution_kind = execution["execution_kind"]
        if execution_kind == "scheduled":
            result["automatic_execution_count"] += 1
            result["on_time_execution_count"] += 1
        elif execution_kind == "catch_up":
            result["automatic_execution_count"] += 1
            result["catch_up_execution_count"] += 1
        elif execution_kind == "manual":
            result["manual_execution_count"] += 1
        else:
            result["unclassified_execution_count"] += 1
    if result["automatic_execution_count"]:
        result["on_time_rate"] = (
            result["on_time_execution_count"]
            / result["automatic_execution_count"]
            * 100
        )
    return result


def investment_plan_execution_variance_summary(
    plan,
    transactions,
    *,
    now=None,
    days=INVESTMENT_RELIABILITY_WINDOW_DAYS,
):
    now = now or datetime.now()
    window_days = _bounded_int(
        days,
        1,
        366,
        INVESTMENT_RELIABILITY_WINDOW_DAYS,
    )
    start_date = now.date() - timedelta(days=window_days - 1)
    result = {
        "days": window_days,
        "execution_count": 0,
        "covered_execution_count": 0,
        "uncovered_execution_count": 0,
        "planned_amount": 0.0,
        "actual_cost": 0.0,
        "difference": 0.0,
        "difference_percent": None,
        "fee": 0.0,
        "rounding_difference": 0.0,
        "latest": None,
    }
    for execution in investment_plan_executions(plan, transactions):
        executed_on = parse_plan_date(execution.get("trade_date"))
        if executed_on is None:
            executed_at = parse_plan_datetime(
                execution.get("timestamp") or execution.get("scheduled_at")
            )
            executed_on = executed_at.date() if executed_at else None
        if executed_on is None or not start_date <= executed_on <= now.date():
            continue
        result["execution_count"] += 1
        planned_amount = _positive_float(execution.get("planned_amount"))
        if planned_amount is None:
            result["uncovered_execution_count"] += 1
            continue
        actual_cost = execution["total_cost"]
        difference = actual_cost - planned_amount
        difference_percent = difference / planned_amount * 100
        fee = execution["fee"]
        result["covered_execution_count"] += 1
        result["planned_amount"] += planned_amount
        result["actual_cost"] += actual_cost
        result["difference"] += difference
        result["fee"] += fee
        result["rounding_difference"] += difference - fee
        if result["latest"] is None:
            result["latest"] = {
                "id": execution.get("id"),
                "timestamp": (
                    execution.get("timestamp")
                    or execution.get("scheduled_at")
                    or execution.get("trade_date")
                ),
                "execution_kind": execution.get("execution_kind"),
                "planned_amount": planned_amount,
                "actual_cost": actual_cost,
                "difference": difference,
                "difference_percent": difference_percent,
                "fee": fee,
            }
    if result["planned_amount"] > 0:
        result["difference_percent"] = (
            result["difference"] / result["planned_amount"] * 100
        )
    return result


def investment_plan_projection(
    item,
    *,
    existing=None,
    transactions=None,
    now=None,
):
    if not isinstance(item, dict):
        raise ValueError("定投计划格式无效")
    now = now or datetime.now()
    existing = existing if isinstance(existing, dict) else {}
    target_count = _target_count(
        item.get("target_count", existing.get("target_count", 0))
    )
    if not target_count:
        return None
    amount = _positive_float(item.get("amount", existing.get("amount")))
    fee = _nonnegative_float(item.get("fee", existing.get("fee", 0)))
    if amount is None or fee is None:
        return None
    schedule = normalize_investment_schedule(item, existing)
    if transactions is None:
        completed_count = _nonnegative_int(
            item.get("completed_count", existing.get("completed_count", 0))
        )
    else:
        completed_count = investment_plan_execution_count(
            existing or item,
            transactions,
        )
    completed_count = min(target_count, completed_count)
    remaining_count = max(0, target_count - completed_count)
    planned_cost_per_run = amount + fee
    completion_at = None
    completion_limited_by_window = False
    completion_out_of_range = False
    if remaining_count:
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
        projected_count = 0
        while candidate is not None and projected_count < remaining_count:
            completion_at = candidate
            projected_count += 1
            if projected_count >= remaining_count:
                break
            try:
                candidate = next_plan_run_in_window(schedule, candidate)
            except (OverflowError, ValueError):
                candidate = None
                completion_out_of_range = True
        if projected_count < remaining_count:
            completion_at = None
            completion_limited_by_window = bool(schedule.get("end_date"))

    mode = _clean_text(item.get("mode", existing.get("mode", "rmb"))).lower()
    if mode not in {"rmb", "usd"}:
        mode = "rmb"
    return {
        "mode": mode,
        "target_count": target_count,
        "completed_count": completed_count,
        "remaining_count": remaining_count,
        "planned_cost_per_run": planned_cost_per_run,
        "projected_total_cost": planned_cost_per_run * target_count,
        "projected_remaining_cost": planned_cost_per_run * remaining_count,
        "projected_completion_at": (
            completion_at.isoformat(timespec="seconds") if completion_at else ""
        ),
        "completion_limited_by_window": completion_limited_by_window,
        "completion_out_of_range": completion_out_of_range,
    }


def investment_plan_window_projection(
    item,
    *,
    now=None,
    days=INVESTMENT_COMMITMENT_WINDOW_DAYS,
):
    if not isinstance(item, dict):
        raise ValueError("定投计划格式无效")
    now = now or datetime.now()
    window_days = _bounded_int(
        days,
        1,
        366,
        INVESTMENT_COMMITMENT_WINDOW_DAYS,
    )
    mode = _clean_text(item.get("mode", "rmb")).lower()
    if mode not in {"rmb", "usd"}:
        mode = "rmb"
    result = {
        "id": _clean_text(item.get("id")),
        "name": _clean_text(item.get("name")),
        "mode": mode,
        "days": window_days,
        "run_count": 0,
        "planned_cost_per_run": 0.0,
        "projected_cost": 0.0,
        "first_run_at": "",
        "last_run_at": "",
        "run_ats": [],
    }
    if item.get("enabled") is False or _clean_text(item.get("archived_at")):
        return result
    amount = _positive_float(item.get("amount"))
    fee = _nonnegative_float(item.get("fee", 0))
    if amount is None or fee is None:
        return result
    result["planned_cost_per_run"] = amount + fee
    target_count = _target_count(item.get("target_count", 0))
    completed_count = _nonnegative_int(item.get("completed_count", 0))
    remaining_count = max(0, target_count - completed_count) if target_count else None
    if remaining_count == 0:
        return result
    schedule = normalize_investment_schedule(item)
    candidate = pending_plan_run_at(item, now)
    if candidate is None:
        candidate = next_plan_run_in_window(schedule, now)
    cutoff = datetime.combine(
        now.date() + timedelta(days=window_days - 1),
        datetime.max.time(),
    )
    run_ats = []
    while (
        candidate is not None
        and candidate <= cutoff
        and (remaining_count is None or len(run_ats) < remaining_count)
    ):
        run_ats.append(candidate)
        try:
            candidate = next_plan_run_in_window(schedule, candidate)
        except (OverflowError, ValueError):
            candidate = None
    if not run_ats:
        return result
    result.update({
        "run_count": len(run_ats),
        "projected_cost": result["planned_cost_per_run"] * len(run_ats),
        "first_run_at": run_ats[0].isoformat(timespec="seconds"),
        "last_run_at": run_ats[-1].isoformat(timespec="seconds"),
        "run_ats": [item.isoformat(timespec="seconds") for item in run_ats],
    })
    return result


def investment_commitment_calendar(items):
    buckets = {}
    for item in list(items or []):
        if not isinstance(item, dict):
            continue
        plan_id = _clean_text(item.get("id"))
        plan_name = _clean_text(item.get("name")) or "未命名计划"
        mode = _clean_text(item.get("mode")).lower()
        planned_cost = _nonnegative_float(item.get("planned_cost_per_run"))
        if not plan_id or mode not in {"rmb", "usd"} or planned_cost is None:
            continue
        for raw_scheduled_at in list(item.get("run_ats") or []):
            scheduled_at = parse_plan_datetime(raw_scheduled_at)
            if scheduled_at is None:
                continue
            date_key = scheduled_at.date().isoformat()
            bucket = buckets.setdefault(date_key, {
                "date": date_key,
                "run_count": 0,
                "plan_count": 0,
                "rmb_commitment": 0.0,
                "usd_commitment": 0.0,
                "items": [],
                "_plan_ids": set(),
            })
            bucket[mode + "_commitment"] += planned_cost
            bucket["run_count"] += 1
            bucket["_plan_ids"].add(plan_id)
            bucket["items"].append({
                "id": plan_id,
                "name": plan_name,
                "mode": mode,
                "scheduled_at": scheduled_at.isoformat(timespec="seconds"),
                "planned_cost": planned_cost,
            })
    result = []
    for date_key in sorted(buckets):
        bucket = buckets[date_key]
        bucket["plan_count"] = len(bucket.pop("_plan_ids"))
        bucket["items"].sort(
            key=lambda item: (
                item.get("scheduled_at") or "",
                item.get("name") or "",
            )
        )
        result.append(bucket)
    return result


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


def _simulation_history_timestamp(value):
    text = _clean_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed


def _simulation_interval_seconds(points):
    deltas = sorted(
        int((current[0] - previous[0]).total_seconds())
        for previous, current in zip(points, points[1:])
        if current[0] > previous[0]
    )
    if not deltas:
        return None
    middle = len(deltas) // 2
    return (
        deltas[middle]
        if len(deltas) % 2
        else int(round((deltas[middle - 1] + deltas[middle]) / 2))
    )


def _simulation_interval_label(seconds):
    if not seconds:
        return "样本不足"
    if seconds < 60:
        return f"约 {seconds} 秒"
    if seconds < 3600:
        return f"约 {max(1, round(seconds / 60))} 分钟"
    if seconds < 86400:
        return f"约 {max(1, round(seconds / 3600))} 小时"
    return f"约 {max(1, round(seconds / 86400))} 天"


def _simulation_granularity(interval_seconds):
    if not interval_seconds:
        return {"key": "unknown", "label": "无法判断"}
    if interval_seconds <= 15 * 60:
        return {"key": "fine", "label": "分钟级"}
    if interval_seconds <= 2 * 60 * 60:
        return {"key": "hourly", "label": "小时级"}
    if interval_seconds <= 36 * 60 * 60:
        return {"key": "daily", "label": "日级"}
    return {"key": "sparse", "label": "稀疏样本"}


def _simulation_gap_items(points, start_at, end_at, interval_seconds):
    if not interval_seconds or end_at <= start_at:
        return []
    threshold_seconds = interval_seconds * 1.5
    boundaries = [(start_at, None), *points, (end_at, None)]
    gaps = []
    for index, (previous, current) in enumerate(zip(boundaries, boundaries[1:])):
        gap_seconds = int((current[0] - previous[0]).total_seconds())
        if gap_seconds <= threshold_seconds:
            continue
        if index == 0:
            estimated_missing = max(1, math.floor(gap_seconds / interval_seconds))
            position = "leading"
        elif index == len(boundaries) - 2:
            estimated_missing = max(1, math.floor(gap_seconds / interval_seconds))
            position = "trailing"
        else:
            estimated_missing = max(
                1,
                math.floor(gap_seconds / interval_seconds) - 1,
            )
            position = "internal"
        gaps.append({
            "start_timestamp": previous[0].isoformat(timespec="seconds"),
            "end_timestamp": current[0].isoformat(timespec="seconds"),
            "duration_seconds": gap_seconds,
            "estimated_missing_points": estimated_missing,
            "position": position,
        })
    return gaps


def _simulation_data_quality(points, start_at, end_at, interval_seconds):
    window_points = [item for item in points if start_at <= item[0] <= end_at]
    duration_seconds = max(1, int((end_at - start_at).total_seconds()))
    expected_point_count = (
        math.floor(duration_seconds / interval_seconds) + 1
        if interval_seconds
        else 0
    )
    point_count = len(window_points)
    missing_point_count = (
        max(0, expected_point_count - point_count)
        if expected_point_count
        else 0
    )
    density_percent = (
        min(100.0, point_count / expected_point_count * 100)
        if expected_point_count
        else None
    )
    if window_points:
        range_start = max(start_at, window_points[0][0])
        range_end = min(end_at, window_points[-1][0])
        range_coverage_percent = max(
            0.0,
            min(
                100.0,
                (range_end - range_start).total_seconds() / duration_seconds * 100,
            ),
        )
    else:
        range_coverage_percent = 0.0
    gaps = _simulation_gap_items(
        window_points,
        start_at,
        end_at,
        interval_seconds,
    )
    return {
        "requested_start_timestamp": start_at.isoformat(timespec="seconds"),
        "requested_end_timestamp": end_at.isoformat(timespec="seconds"),
        "point_count": point_count,
        "expected_point_count": expected_point_count,
        "missing_point_count": missing_point_count,
        "density_percent": density_percent,
        "range_coverage_percent": range_coverage_percent,
        "gap_count": len(gaps),
        "largest_gap_seconds": max(
            (item["duration_seconds"] for item in gaps),
            default=0,
        ),
        "gaps": sorted(
            gaps,
            key=lambda item: item["duration_seconds"],
            reverse=True,
        )[:5],
        "granularity": _simulation_granularity(interval_seconds),
    }


def _simulation_confidence(
    *,
    scheduled_count,
    covered_count,
    latest_price,
    data_quality,
):
    if not scheduled_count:
        return {
            "level": "unavailable",
            "label": "无法评估",
            "score": None,
            "summary": "所选窗口内没有计划期次，无法评估模拟结果可信度。",
            "reasons": ["调整模拟范围，或检查计划的开始日期和执行频率。"],
        }

    covered_percent = covered_count / scheduled_count * 100
    range_percent = float(data_quality.get("range_coverage_percent") or 0)
    density_percent = float(data_quality.get("density_percent") or 0)
    granularity_key = data_quality.get("granularity", {}).get("key")
    granularity_score = {
        "fine": 100,
        "hourly": 90,
        "daily": 65,
        "sparse": 30,
        "unknown": 0,
    }.get(granularity_key, 0)
    score = round(
        covered_percent * 0.45
        + range_percent * 0.20
        + density_percent * 0.20
        + granularity_score * 0.10
        + (100 if latest_price is not None else 0) * 0.05
    )
    level = "high" if score >= 85 else "medium" if score >= 60 else "low"
    label = {"high": "高", "medium": "中", "low": "低"}[level]
    reasons = []
    if covered_count < scheduled_count:
        reasons.append(f"仅匹配 {covered_count}/{scheduled_count} 个计划期次。")
    if range_percent < 90:
        reasons.append(f"本地行情只覆盖所选时间范围的 {range_percent:.0f}%。")
    if density_percent < 80:
        reasons.append(f"按当前粒度估算，样本完整度为 {density_percent:.0f}%。")
    if granularity_key in {"daily", "sparse", "unknown"}:
        reasons.append(
            "样本粒度较粗，期次成交价可能与真实时点存在偏差。"
            if granularity_key != "unknown"
            else "样本不足，无法判断时间粒度。"
        )
    if latest_price is None:
        reasons.append("范围末端没有邻近行情，无法估算当前市值。")
    if not reasons:
        reasons.append("计划期次、时间范围和末端估值均有连续行情支持。")
    return {
        "level": level,
        "label": label,
        "score": score,
        "summary": {
            "high": "历史样本对当前模拟提供了较完整的支持。",
            "medium": "模拟结果可用于趋势参考，但仍存在数据覆盖限制。",
            "low": "历史样本不足，结果只适合了解大致方向。",
        }[level],
        "reasons": reasons[:4],
    }


def _nearest_simulation_point(points, timestamps, target, tolerance_seconds):
    if not points:
        return None
    index = bisect_left(timestamps, target)
    candidates = []
    if index < len(points):
        candidates.append(points[index])
    if index > 0:
        candidates.append(points[index - 1])
    if not candidates:
        return None
    matched = min(
        candidates,
        key=lambda item: (
            abs((item[0] - target).total_seconds()),
            item[0] > target,
        ),
    )
    return (
        matched
        if abs((matched[0] - target).total_seconds()) <= tolerance_seconds
        else None
    )


def _investment_simulation_run_ats(plan, start_at, end_at):
    schedule = normalize_investment_schedule(plan)
    target_count = _target_count(plan.get("target_count", 0))
    plan_start = parse_plan_datetime(plan.get("created_at"))
    schedule_start = parse_plan_date(schedule.get("start_date"))
    if schedule_start:
        schedule_start_at = datetime.combine(schedule_start, datetime.min.time())
        plan_start = max(plan_start, schedule_start_at) if plan_start else schedule_start_at
    plan_start = plan_start or start_at
    candidate = next_plan_run_in_window(
        schedule,
        plan_start - timedelta(microseconds=1),
    )
    run_ats = []
    generated_count = 0
    while candidate is not None and candidate <= end_at:
        generated_count += 1
        if candidate >= start_at:
            run_ats.append(candidate)
        if target_count and generated_count >= target_count:
            break
        try:
            candidate = next_plan_run_in_window(schedule, candidate)
        except (OverflowError, ValueError):
            candidate = None
    return run_ats


def investment_plan_history_simulation(plan, price_history, *, days=30, now=None):
    if not isinstance(plan, dict):
        raise ValueError("定投计划格式无效")
    try:
        window_days = int(days)
    except (TypeError, ValueError) as exc:
        raise ValueError("历史模拟范围无效") from exc
    if window_days not in INVESTMENT_SIMULATION_WINDOWS:
        raise ValueError("历史模拟仅支持 7、30 或 90 天")

    now = now or datetime.now()
    start_at = datetime.combine(
        now.date() - timedelta(days=window_days - 1),
        datetime.min.time(),
    )
    mode = _clean_text(plan.get("mode", "rmb")).lower()
    if mode not in {"rmb", "usd"}:
        raise ValueError("定投持仓单位无效")
    amount = _positive_float(plan.get("amount"))
    fee = _nonnegative_float(plan.get("fee", 0))
    if amount is None or fee is None:
        raise ValueError("定投金额或手续费无效")

    points_by_timestamp = {}
    for raw in list(price_history or []):
        if not isinstance(raw, dict):
            continue
        timestamp = _simulation_history_timestamp(raw.get("timestamp"))
        price = _positive_float(raw.get(mode))
        if timestamp is None or timestamp > now or price is None:
            continue
        points_by_timestamp[timestamp] = price
    points = sorted(points_by_timestamp.items(), key=lambda item: item[0])
    interval_seconds = _simulation_interval_seconds(points)
    maximum_tolerance_seconds = 2 * 60 * 60 if window_days <= 30 else 24 * 60 * 60
    tolerance_seconds = min(
        max(60, interval_seconds or 0),
        maximum_tolerance_seconds,
    )
    eligible_points = [
        item for item in points
        if item[0] >= start_at - timedelta(seconds=tolerance_seconds)
    ]
    timestamps = [item[0] for item in eligible_points]
    run_ats = _investment_simulation_run_ats(plan, start_at, now)

    executions = []
    total_quantity = 0.0
    gross_invested = 0.0
    total_fees = 0.0
    for scheduled_at in run_ats:
        matched = _nearest_simulation_point(
            eligible_points,
            timestamps,
            scheduled_at,
            tolerance_seconds,
        )
        if matched is None:
            executions.append({
                "scheduled_at": scheduled_at.isoformat(timespec="seconds"),
                "status": "missing",
                "sample_timestamp": "",
                "sample_offset_seconds": None,
                "price": None,
                "quantity": None,
                "gross_amount": None,
                "fee": fee,
                "total_cost": None,
            })
            continue
        sample_timestamp, price = matched
        quantity = round(amount / price, 8)
        gross_amount = price * quantity
        total_cost = gross_amount + fee
        total_quantity += quantity
        gross_invested += gross_amount
        total_fees += fee
        executions.append({
            "scheduled_at": scheduled_at.isoformat(timespec="seconds"),
            "status": "estimated",
            "sample_timestamp": sample_timestamp.isoformat(timespec="seconds"),
            "sample_offset_seconds": int(
                abs((sample_timestamp - scheduled_at).total_seconds())
            ),
            "price": price,
            "quantity": quantity,
            "gross_amount": gross_amount,
            "fee": fee,
            "total_cost": total_cost,
        })

    latest_match = _nearest_simulation_point(
        eligible_points,
        timestamps,
        now,
        tolerance_seconds,
    )
    latest_price = latest_match[1] if latest_match is not None else None
    actual_cost = gross_invested + total_fees
    market_value = (
        total_quantity * latest_price
        if total_quantity > 0 and latest_price is not None
        else None
    )
    pnl = market_value - actual_cost if market_value is not None else None
    covered_count = sum(item["status"] == "estimated" for item in executions)
    scheduled_count = len(executions)
    missing_count = scheduled_count - covered_count
    point_count = len(eligible_points)
    data_quality = _simulation_data_quality(
        points,
        start_at,
        now,
        interval_seconds,
    )
    confidence = _simulation_confidence(
        scheduled_count=scheduled_count,
        covered_count=covered_count,
        latest_price=latest_price,
        data_quality=data_quality,
    )
    return {
        "days": window_days,
        "supported": True,
        "usable": covered_count > 0,
        "partial": missing_count > 0,
        "mode": mode,
        "scheduled_count": scheduled_count,
        "covered_count": covered_count,
        "missing_count": missing_count,
        "planned_amount": amount * scheduled_count,
        "covered_planned_amount": amount * covered_count,
        "actual_cost": actual_cost,
        "total_fees": total_fees,
        "quantity": total_quantity,
        "average_price": (
            gross_invested / total_quantity if total_quantity > 0 else None
        ),
        "latest_price": latest_price,
        "latest_price_timestamp": (
            latest_match[0].isoformat(timespec="seconds")
            if latest_match is not None
            else ""
        ),
        "market_value": market_value,
        "pnl": pnl,
        "pnl_percent": (
            pnl / actual_cost * 100
            if pnl is not None and actual_cost > 0
            else None
        ),
        "coverage": {
            "point_count": point_count,
            "first_timestamp": (
                eligible_points[0][0].isoformat(timespec="seconds")
                if eligible_points
                else ""
            ),
            "last_timestamp": (
                eligible_points[-1][0].isoformat(timespec="seconds")
                if eligible_points
                else ""
            ),
            "interval_seconds": interval_seconds,
            "interval_label": _simulation_interval_label(interval_seconds),
            "match_tolerance_seconds": tolerance_seconds,
            "covered_percent": (
                covered_count / scheduled_count * 100 if scheduled_count else None
            ),
            "data_quality": data_quality,
        },
        "confidence": confidence,
        "executions": executions,
    }


def investment_plan_state(items, *, now=None, transactions=None, prices=None):
    now = now or datetime.now()
    prices = prices if isinstance(prices, dict) else {}
    actual = investment_execution_window_summary(transactions, now=now)
    actual_trend = investment_execution_monthly_trend(transactions, now=now)
    reliability = investment_execution_reliability_summary(transactions, now=now)
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
        "actual_days": actual["days"],
        "actual_execution_count": actual["execution_count"],
        "rmb_actual_invested": actual["rmb_invested"],
        "usd_actual_invested": actual["usd_invested"],
        "actual_trend_months": len(actual_trend),
        "actual_trend": actual_trend,
        "reliability_days": reliability["days"],
        "automatic_execution_count": reliability["automatic_execution_count"],
        "on_time_execution_count": reliability["on_time_execution_count"],
        "catch_up_execution_count": reliability["catch_up_execution_count"],
        "manual_execution_count": reliability["manual_execution_count"],
        "unclassified_execution_count": reliability["unclassified_execution_count"],
        "on_time_rate": reliability["on_time_rate"],
        "commitment_days": INVESTMENT_COMMITMENT_WINDOW_DAYS,
        "commitment_plan_count": 0,
        "commitment_run_count": 0,
        "rmb_commitment": 0.0,
        "usd_commitment": 0.0,
        "commitment_items": [],
        "commitment_calendar": [],
    }
    commitment_calendar_sources = []
    for raw in list(items or []):
        plan = dict(raw)
        archived = bool(_clean_text(plan.get("archived_at")))
        next_run = parse_plan_datetime(plan.get("next_run_at"))
        performance = investment_plan_performance(
            plan,
            transactions,
            current_price=prices.get(plan.get("mode")),
        )
        plan_reliability = investment_execution_reliability_summary(
            transactions,
            now=now,
            source_id=plan.get("id"),
        )
        plan_variance = investment_plan_execution_variance_summary(
            plan,
            transactions,
            now=now,
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
        plan["projection"] = investment_plan_projection(
            {**plan, "completed_count": completed_count},
            existing=plan,
            now=now,
        )
        commitment = investment_plan_window_projection(
            {**plan, "completed_count": completed_count},
            now=now,
        )
        if commitment["run_count"]:
            summary["commitment_plan_count"] += 1
            summary["commitment_run_count"] += commitment["run_count"]
            commitment_key = (
                "usd_commitment"
                if commitment["mode"] == "usd"
                else "rmb_commitment"
            )
            summary[commitment_key] += commitment["projected_cost"]
            commitment_calendar_sources.append(commitment)
            summary["commitment_items"].append({
                key: value
                for key, value in commitment.items()
                if key != "run_ats"
            })
        plan["performance"] = performance
        plan["reliability"] = plan_reliability
        plan["variance"] = plan_variance
        summary["execution_count"] += performance["execution_count"]
        invested_key = "usd_invested" if plan.get("mode") == "usd" else "rmb_invested"
        summary[invested_key] += performance["total_invested"]
        plans.append(plan)
    summary["all_total"] = len(plans)
    summary["total"] = len(plans) - summary["archived"]
    summary["commitment_items"].sort(
        key=lambda item: (
            item.get("first_run_at") or "9999",
            item.get("name") or "",
        )
    )
    summary["commitment_calendar"] = investment_commitment_calendar(
        commitment_calendar_sources
    )
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
