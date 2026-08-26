import math
from datetime import datetime

from goldmonitor.time_utils import parse_datetime


MARKET_OBSERVATION_FIELDS = (
    "source",
    "rate_source",
    "source_at",
    "rate_source_at",
    "received_at",
    "is_cached",
    "gold_cached",
    "rate_cached",
    "age_seconds",
    "rate_age_seconds",
    "quality_score",
    "quality_level",
    "usable_for_history",
    "usable_for_alert",
    "usable_for_automation",
    "blocked_reasons",
)


def market_observation_snapshot(value):
    if not isinstance(value, dict):
        return {}
    snapshot = {
        field: value.get(field)
        for field in MARKET_OBSERVATION_FIELDS
        if field in value
    }
    snapshot["blocked_reasons"] = [
        str(reason)
        for reason in value.get("blocked_reasons", [])
        if str(reason or "").strip()
    ]
    return snapshot


def unavailable_market_observation(reason="尚未获得可用于业务判断的实时行情"):
    return {
        "source": "",
        "rate_source": "",
        "source_at": "",
        "rate_source_at": "",
        "received_at": "",
        "is_cached": False,
        "gold_cached": False,
        "rate_cached": False,
        "age_seconds": None,
        "rate_age_seconds": None,
        "quality_score": 0,
        "quality_level": "unavailable",
        "usable_for_history": False,
        "usable_for_alert": False,
        "usable_for_automation": False,
        "blocked_reasons": [str(reason or "行情不可用")],
    }


def _positive_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _age_seconds(source_at, received_at):
    source_time = parse_datetime(source_at)
    received_time = parse_datetime(received_at)
    if source_time is None or received_time is None:
        return None
    return int((received_time - source_time).total_seconds())


def build_market_observation(
    data,
    *,
    source,
    received_at=None,
    rate_value=None,
    rate_source="",
    rate_source_at="",
    gold_cached=False,
    rate_cached=False,
    comparison=None,
):
    received_at = received_at or datetime.now().isoformat(timespec="seconds")
    data = data if isinstance(data, dict) else {}
    source_at = str(data.get("timestamp") or received_at)
    rate_source_at = str(rate_source_at or "")
    blocked_reasons = []

    open_price = _positive_number(data.get("open"))
    high_price = _positive_number(data.get("high"))
    low_price = _positive_number(data.get("low"))
    close_price = _positive_number(data.get("close"))
    if None in {open_price, high_price, low_price, close_price}:
        blocked_reasons.append("金价数据缺失或不是有效正数")
    elif low_price > high_price or not (
        low_price <= open_price <= high_price
        and low_price <= close_price <= high_price
    ):
        blocked_reasons.append("金价开高低收关系异常")

    age_seconds = _age_seconds(source_at, received_at)
    if age_seconds is None:
        blocked_reasons.append("无法解析金价源时间")
    elif age_seconds < -60:
        blocked_reasons.append("金价源时间晚于接收时间")
    elif age_seconds > 300:
        blocked_reasons.append("金价源时间超过 5 分钟")

    if _positive_number(rate_value) is None:
        blocked_reasons.append("缺少有效 USD/CNY 汇率")
    rate_age_seconds = _age_seconds(rate_source_at, received_at)
    if rate_age_seconds is None:
        blocked_reasons.append("无法解析汇率源时间")
    elif rate_age_seconds < -60:
        blocked_reasons.append("汇率源时间晚于接收时间")
    elif rate_age_seconds > 3600:
        blocked_reasons.append("汇率源时间超过 1 小时")
    if gold_cached:
        blocked_reasons.append("金价来自缓存")
    if rate_cached:
        blocked_reasons.append("汇率来自缓存")
    comparison = comparison if isinstance(comparison, dict) else {}
    if comparison.get("status") == "anomaly":
        blocked_reasons.append(str(comparison.get("message") or "跨源金价差异异常"))

    deductions = 0
    if gold_cached:
        deductions += 40
    if rate_cached:
        deductions += 20
    if comparison.get("status") == "anomaly":
        deductions += 50
    if any(
        reason in blocked_reasons
        for reason in (
            "金价数据缺失或不是有效正数",
            "金价开高低收关系异常",
            "无法解析金价源时间",
            "金价源时间晚于接收时间",
            "金价源时间超过 5 分钟",
            "缺少有效 USD/CNY 汇率",
            "无法解析汇率源时间",
            "汇率源时间晚于接收时间",
            "汇率源时间超过 1 小时",
        )
    ):
        deductions += 100
    score = max(0, 100 - deductions)
    if comparison.get("status") == "anomaly":
        level = "anomaly"
    elif gold_cached or rate_cached:
        level = "stale"
    elif blocked_reasons:
        level = "invalid"
    else:
        level = "normal"
    usable = not blocked_reasons and score >= 90
    return {
        "source": str(source or ""),
        "rate_source": str(rate_source or ""),
        "source_at": source_at,
        "rate_source_at": rate_source_at,
        "received_at": str(received_at),
        "is_cached": bool(gold_cached or rate_cached),
        "gold_cached": bool(gold_cached),
        "rate_cached": bool(rate_cached),
        "age_seconds": max(0, age_seconds) if age_seconds is not None else None,
        "rate_age_seconds": (
            max(0, rate_age_seconds) if rate_age_seconds is not None else None
        ),
        "quality_score": score,
        "quality_level": level,
        "usable_for_history": usable,
        "usable_for_alert": usable,
        "usable_for_automation": usable,
        "blocked_reasons": blocked_reasons,
    }
