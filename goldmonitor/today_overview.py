import json
import os
from datetime import datetime, time, timedelta


TODAY_OVERVIEW_SCHEMA_VERSION = 1
TODAY_OVERVIEW_ATTENTION_LIMIT = 50
TODAY_OVERVIEW_ACTIVITY_LIMIT = 20
NOTIFICATION_ISSUE_STATUSES = {"failed", "partial", "skipped"}
RULE_ATTENTION_STATUSES = {"waiting_data", "orphaned", "expired"}


def empty_today_overview_state():
    return {
        "schema_version": TODAY_OVERVIEW_SCHEMA_VERSION,
        "last_viewed_at": "",
        "updated_at": "",
    }


def normalize_today_overview_state(payload):
    state = empty_today_overview_state()
    if not isinstance(payload, dict):
        return state
    state["last_viewed_at"] = _timestamp_text(payload.get("last_viewed_at"))
    state["updated_at"] = _timestamp_text(payload.get("updated_at"))
    return state


class TodayOverviewStateStore:
    def __init__(self, state_path, now_factory=None):
        self.state_path = state_path
        self.now_factory = now_factory or datetime.now

    def load(self):
        if not os.path.exists(self.state_path):
            return empty_today_overview_state()
        try:
            with open(self.state_path, "r", encoding="utf-8") as file_handle:
                return normalize_today_overview_state(json.load(file_handle))
        except (OSError, json.JSONDecodeError):
            return empty_today_overview_state()

    def save(self, state):
        normalized = normalize_today_overview_state(state)
        os.makedirs(os.path.dirname(self.state_path) or ".", exist_ok=True)
        temporary_path = self.state_path + ".tmp"
        with open(temporary_path, "w", encoding="utf-8") as file_handle:
            json.dump(normalized, file_handle, ensure_ascii=False, indent=2)
        os.replace(temporary_path, self.state_path)
        return normalized

    def mark_viewed(self, viewed_at=None):
        viewed_at = viewed_at or self.now_factory()
        viewed_at_text = _timestamp_text(viewed_at)
        if not viewed_at_text:
            raise ValueError("查看时间无效")
        return self.save({
            "schema_version": TODAY_OVERVIEW_SCHEMA_VERSION,
            "last_viewed_at": viewed_at_text,
            "updated_at": viewed_at_text,
        })


def parse_iso_datetime(value):
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo:
        parsed = parsed.replace(tzinfo=None)
    return parsed


def _items(value):
    if isinstance(value, dict):
        value = value.get("items")
    if not isinstance(value, (list, tuple)):
        return []
    return [dict(item) for item in list(value or []) if isinstance(item, dict)]


def _bounded_limit(value, default, maximum=200):
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(maximum, limit))


def _day_bounds(now):
    start = datetime.combine(now.date(), time.min)
    return start, start + timedelta(days=1)


def _in_range(value, start, end):
    parsed = parse_iso_datetime(value)
    return parsed is not None and start <= parsed < end


def _timestamp_text(value):
    parsed = parse_iso_datetime(value)
    return parsed.isoformat(timespec="seconds") if parsed else ""


def _latest(items, keys):
    candidates = []
    for item in items:
        timestamp = ""
        for key in keys:
            timestamp = _timestamp_text(item.get(key))
            if timestamp:
                break
        if timestamp:
            candidates.append((timestamp, item))
    return dict(max(candidates, key=lambda value: value[0])[1]) if candidates else None


def _notification_status(entry):
    summary = entry.get("notification_summary")
    if isinstance(summary, dict):
        return str(summary.get("status") or "")
    statuses = {
        str(item.get("status") or "")
        for item in list(entry.get("notifications") or [])
        if isinstance(item, dict)
    }
    if ("failed" in statuses or "skipped" in statuses) and ("sent" in statuses or "queued" in statuses):
        return "partial"
    if "failed" in statuses:
        return "failed"
    if "skipped" in statuses:
        return "skipped"
    return ""


def _severity(priority):
    if priority >= 95:
        return "critical"
    if priority >= 75:
        return "high"
    if priority >= 50:
        return "medium"
    return "low"


def _attention_item(kind, source_id, priority, title, summary, timestamp, reason_codes, action, **extra):
    item = {
        "id": f"{kind}:{source_id}",
        "kind": kind,
        "source_id": str(source_id or ""),
        "priority": int(priority),
        "severity": _severity(priority),
        "title": str(title or ""),
        "summary": str(summary or ""),
        "timestamp": _timestamp_text(timestamp),
        "reason_codes": list(reason_codes or []),
        "action": dict(action or {}),
    }
    item.update(extra)
    return item


def _activity_item(kind, source_id, timestamp, title, summary, action, **extra):
    item = {
        "id": f"{kind}:{source_id}",
        "kind": kind,
        "source_id": str(source_id or ""),
        "timestamp": _timestamp_text(timestamp),
        "title": str(title or ""),
        "summary": str(summary or ""),
        "action": dict(action or {}),
    }
    item.update(extra)
    return item


def _alert_title(entry):
    return str(entry.get("rule_name") or entry.get("title") or "价格预警")


def _alert_attention(entries, start, end):
    items = []
    notification_issue_count = 0
    unread_count = 0
    unhandled_count = 0
    for entry in entries:
        unread = not bool(entry.get("read"))
        unhandled = not bool(entry.get("handled"))
        notification_status = _notification_status(entry)
        notification_issue = notification_status in NOTIFICATION_ISSUE_STATUSES
        unread_count += int(unread)
        unhandled_count += int(unhandled)
        notification_issue_count += int(notification_issue)
        if not unhandled and not notification_issue:
            continue
        alert_type = str(entry.get("type") or "warning")
        priority = 100 if alert_type == "critical" and unhandled else 80 if unhandled else 70
        if notification_issue:
            priority = min(100, max(priority, 90) + (10 if unhandled else 0))
        timestamp = entry.get("timestamp")
        reason_codes = []
        if unhandled:
            reason_codes.append("unhandled")
        if notification_issue:
            reason_codes.append("notification_issue")
        items.append(_attention_item(
            "alert",
            entry.get("id") or entry.get("alert_id") or timestamp,
            priority,
            _alert_title(entry),
            entry.get("message") or "警报需要处理。",
            timestamp,
            reason_codes,
            {"kind": "open_alert", "target_id": str(entry.get("id") or entry.get("alert_id") or "")},
            occurred_today=_in_range(timestamp, start, end),
            alert_type=alert_type,
            rule_id=str(entry.get("rule_id") or ""),
            notification_status=notification_status,
        ))
    return items, {
        "unread": unread_count,
        "unhandled": unhandled_count,
        "notification_issues": notification_issue_count,
    }


def _rule_attention(rule_state):
    items = []
    counts = {"waiting_data": 0, "orphaned": 0, "expired": 0}
    for rule in _items(rule_state):
        state = rule.get("state") if isinstance(rule.get("state"), dict) else {}
        status = str(state.get("status") or "")
        if status not in RULE_ATTENTION_STATUSES:
            continue
        counts[status] += 1
        priority = {"orphaned": 75, "waiting_data": 65, "expired": 40}[status]
        label = {"orphaned": "关联失效", "waiting_data": "等待数据", "expired": "规则已过期"}[status]
        inspection = rule.get("inspection") if isinstance(rule.get("inspection"), dict) else {}
        items.append(_attention_item(
            "rule",
            rule.get("id") or rule.get("name") or status,
            priority,
            str(rule.get("name") or "预警规则"),
            label,
            rule.get("updated_at") or inspection.get("last_evaluated_at"),
            [status],
            {"kind": "open_rule", "target_id": str(rule.get("id") or "")},
            occurred_today=False,
            rule_kind=str(rule.get("kind") or ""),
            rule_status=status,
        ))
    return items, counts


def _market_attention(market_quality, fetch_status, generated_at):
    quality = dict(market_quality or {}) if isinstance(market_quality, dict) else {}
    fetch = dict(fetch_status or {}) if isinstance(fetch_status, dict) else {}
    level = str(quality.get("level") or "")
    message = str(fetch.get("message") or fetch.get("error") or "")
    initial_wait = fetch.get("ok") is False and not str(fetch.get("error") or "").strip() and any(
        fragment in message for fragment in ("等待首次", "等待行情", "正在等待")
    )
    if level not in {"anomaly", "stale", "degraded"}:
        if fetch.get("ok") is not False or initial_wait:
            return None
        level = "degraded"
    priority = {"anomaly": 95, "stale": 90, "degraded": 70}[level]
    reasons = [str(value) for value in list(quality.get("reasons") or []) if str(value or "").strip()]
    summary = reasons[0] if reasons else message or str(quality.get("label") or "行情状态需要检查")
    return _attention_item(
        "market",
        "quality",
        priority,
        str(quality.get("label") or "行情状态异常"),
        summary,
        generated_at,
        [f"market_{level}"],
        {"kind": "open_market_status", "target_id": "market-quality"},
        occurred_today=True,
        market_level=level,
        market_score=quality.get("score"),
        details=reasons,
    )


def _portfolio_summary(summary):
    source = summary if isinstance(summary, dict) else {}
    return {
        key: source.get(key)
        for key in (
            "count",
            "market_value",
            "cost_basis",
            "unrealized_pnl",
            "realized_pnl",
            "total_pnl",
            "pnl",
            "pnl_percent",
            "valued",
        )
        if key in source
    }


def _today_transactions(portfolio_state, start, end):
    state = portfolio_state if isinstance(portfolio_state, dict) else {}
    result = []
    for transaction in _items(state.get("transactions")):
        trade_date = str(transaction.get("trade_date") or "")[:10]
        if trade_date:
            occurred_today = trade_date == start.date().isoformat()
        else:
            occurred_today = _in_range(transaction.get("created_at"), start, end)
        if not occurred_today:
            continue
        created_at = _timestamp_text(transaction.get("created_at"))
        timestamp = (
            created_at
            if created_at.startswith(start.date().isoformat())
            else f"{start.date().isoformat()}T00:00:00"
        )
        transaction_type = str(transaction.get("type") or "")
        result.append(_activity_item(
            "portfolio_transaction",
            transaction.get("id") or timestamp,
            timestamp,
            str(transaction.get("name") or "持仓流水"),
            "买入" if transaction_type == "buy" else "卖出" if transaction_type == "sell" else "持仓变动",
            {"kind": "open_portfolio_transaction", "target_id": str(transaction.get("id") or "")},
            transaction_type=transaction_type,
            mode=str(transaction.get("mode") or ""),
            price=transaction.get("price"),
            quantity=transaction.get("quantity"),
        ))
    return result


def _risk_summary(item):
    structured = item.get("structured") if isinstance(item.get("structured"), dict) else {}
    content = str(item.get("content") or "").strip()
    return str(structured.get("summary") or (content.splitlines()[0] if content else ""))[:200]


def _risk_activity(items, start, end):
    result = []
    for item in items:
        timestamp = item.get("analysis_time")
        if not _in_range(timestamp, start, end):
            continue
        structured = item.get("structured") if isinstance(item.get("structured"), dict) else {}
        risk_level = str(structured.get("risk_level") or "")
        result.append(_activity_item(
            "risk_analysis",
            item.get("id") or timestamp,
            timestamp,
            f"风险分析{f'：{risk_level}' if risk_level else ''}",
            _risk_summary(item),
            {"kind": "open_risk_analysis", "target_id": str(item.get("id") or timestamp or "")},
            risk_level=risk_level,
            provider=str(item.get("provider") or ""),
            model=str(item.get("model") or ""),
        ))
    return result


def _review_activity(items, start, end):
    result = []
    for item in items:
        timestamp = item.get("timestamp") or item.get("updated_at") or item.get("created_at")
        if not _in_range(timestamp, start, end):
            continue
        result.append(_activity_item(
            "review_note",
            item.get("id") or timestamp,
            timestamp,
            str(item.get("title") or "复盘笔记"),
            str(item.get("content") or "").strip()[:200],
            {"kind": "open_review_note", "target_id": str(item.get("id") or "")},
        ))
    return result


def _alert_activity(entries, start, end):
    result = []
    for entry in entries:
        timestamp = entry.get("timestamp")
        if not _in_range(timestamp, start, end):
            continue
        result.append(_activity_item(
            "alert",
            entry.get("id") or entry.get("alert_id") or timestamp,
            timestamp,
            _alert_title(entry),
            str(entry.get("message") or ""),
            {"kind": "open_alert", "target_id": str(entry.get("id") or entry.get("alert_id") or "")},
            handled=bool(entry.get("handled")),
            read=bool(entry.get("read")),
            alert_type=str(entry.get("type") or "warning"),
        ))
    return result


def _sort_attention(items):
    return sorted(
        items,
        key=lambda item: (
            int(item.get("priority") or 0),
            str(item.get("timestamp") or ""),
            item["id"],
        ),
        reverse=True,
    )


def _sort_activity(items):
    return sorted(items, key=lambda item: (str(item.get("timestamp") or ""), item["id"]), reverse=True)


def _latest_summary(item, keys, summary_builder=None):
    if not item:
        return None
    timestamp = ""
    for key in keys:
        timestamp = _timestamp_text(item.get(key))
        if timestamp:
            break
    result = {
        "id": str(item.get("id") or timestamp),
        "timestamp": timestamp,
    }
    if summary_builder:
        result["summary"] = summary_builder(item)
    return result


def build_today_overview(
    *,
    alert_entries=None,
    alert_rules=None,
    market_quality=None,
    fetch_status=None,
    portfolio_state=None,
    risk_items=None,
    review_notes=None,
    last_viewed_at="",
    now=None,
    attention_limit=TODAY_OVERVIEW_ATTENTION_LIMIT,
    activity_limit=TODAY_OVERVIEW_ACTIVITY_LIMIT,
):
    now = now or datetime.now()
    start, end = _day_bounds(now)
    generated_at = now.isoformat(timespec="seconds")
    alerts = _items(alert_entries)
    risks = _items(risk_items)
    notes = _items(review_notes)
    portfolio = dict(portfolio_state or {}) if isinstance(portfolio_state, dict) else {}

    alert_attention, alert_counts = _alert_attention(alerts, start, end)
    rule_attention, rule_counts = _rule_attention(alert_rules)
    market_item = _market_attention(market_quality, fetch_status, generated_at)
    attention = alert_attention + rule_attention + ([market_item] if market_item else [])
    attention = _sort_attention(attention)
    attention_total = len(attention)
    attention = attention[:_bounded_limit(attention_limit, TODAY_OVERVIEW_ATTENTION_LIMIT)]

    alert_activity = _alert_activity(alerts, start, end)
    transaction_activity = _today_transactions(portfolio, start, end)
    risk_activity = _risk_activity(risks, start, end)
    note_activity = _review_activity(notes, start, end)
    activity = _sort_activity(alert_activity + transaction_activity + risk_activity + note_activity)
    activity_total = len(activity)
    activity = activity[:_bounded_limit(activity_limit, TODAY_OVERVIEW_ACTIVITY_LIMIT)]

    last_viewed = parse_iso_datetime(last_viewed_at)
    new_since_last_view = 0
    if last_viewed is not None:
        for item in alert_activity + transaction_activity + risk_activity + note_activity:
            timestamp = parse_iso_datetime(item.get("timestamp"))
            if timestamp is not None and timestamp > last_viewed:
                new_since_last_view += 1

    latest_risk = _latest(risks, ("analysis_time",))
    latest_note = _latest(notes, ("timestamp", "updated_at", "created_at"))
    return {
        "schema_version": TODAY_OVERVIEW_SCHEMA_VERSION,
        "generated_at": generated_at,
        "range": {
            "date": start.date().isoformat(),
            "start": start.isoformat(timespec="seconds"),
            "end": end.isoformat(timespec="seconds"),
            "timezone": "local",
        },
        "summary": {
            "attention_total": attention_total,
            "activity_total": activity_total,
            "new_since_last_view": new_since_last_view,
            "alerts_today": len(alert_activity),
            "unread_alerts": alert_counts["unread"],
            "unhandled_alerts": alert_counts["unhandled"],
            "notification_issues": alert_counts["notification_issues"],
            "rule_issues": sum(rule_counts.values()),
            "rules_waiting_data": rule_counts["waiting_data"],
            "rules_orphaned": rule_counts["orphaned"],
            "rules_expired": rule_counts["expired"],
            "portfolio_positions": int(portfolio.get("total") or len(_items(portfolio.get("items")))),
            "portfolio_transactions_today": len(transaction_activity),
            "risk_analyses_today": len(risk_activity),
            "review_notes_today": len(note_activity),
        },
        "attention": {
            "items": attention,
            "total": attention_total,
            "truncated": attention_total > len(attention),
        },
        "activity": {
            "items": activity,
            "total": activity_total,
            "truncated": activity_total > len(activity),
        },
        "market": {
            "quality": dict(market_quality or {}) if isinstance(market_quality, dict) else {},
            "fetch_status": dict(fetch_status or {}) if isinstance(fetch_status, dict) else {},
        },
        "portfolio": {
            "current": {
                "rmb": _portfolio_summary(portfolio.get("rmb_summary")),
                "usd": _portfolio_summary(portfolio.get("usd_summary")),
            },
            "transactions_today": transaction_activity,
        },
        "recent": {
            "risk_analysis": _latest_summary(latest_risk, ("analysis_time",), _risk_summary),
            "review_note": _latest_summary(
                latest_note,
                ("timestamp", "updated_at", "created_at"),
                lambda item: str(item.get("content") or "").strip()[:200],
            ),
        },
    }
