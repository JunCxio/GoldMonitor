import json
import os
from datetime import datetime


DAILY_DIGEST_SCHEMA_VERSION = 1


def _number(value, digits=2):
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return "--"


def _price_line(price_summary, key, label):
    item = price_summary.get(key) if isinstance(price_summary, dict) else None
    item = item if isinstance(item, dict) else {}
    if int(item.get("points") or 0) <= 0:
        return f"- {label}：暂无可用价格历史"
    change = _number(item.get("change"))
    change_pct = _number(item.get("change_pct"))
    return (
        f"- {label}：{_number(item.get('start'))} -> {_number(item.get('end'))}，"
        f"高/低 {_number(item.get('high'))} / {_number(item.get('low'))}，"
        f"变动 {change}（{change_pct}%）"
    )


def _event_counts(summary):
    by_type = summary.get("by_type") if isinstance(summary, dict) else None
    by_type = by_type if isinstance(by_type, dict) else {}
    return {
        "alert": int(by_type.get("alert") or 0),
        "risk_analysis": int(by_type.get("risk_analysis") or 0),
        "news": int(by_type.get("news") or 0),
        "data_status": int(by_type.get("data_status") or 0),
        "review_note": int(by_type.get("review_note") or 0),
    }


def _portfolio_line(portfolio_state, key, label):
    summary = portfolio_state.get(key) if isinstance(portfolio_state, dict) else None
    summary = summary if isinstance(summary, dict) else {}
    count = int(summary.get("count") or 0)
    if count <= 0:
        return f"- {label}：暂无持仓"
    return (
        f"- {label}：{count} 项，市值 {_number(summary.get('market_value'))}，"
        f"盈亏 {_number(summary.get('pnl'))}（{_number(summary.get('pnl_percent'))}%）"
    )


def _quality_line(market_quality):
    quality = market_quality if isinstance(market_quality, dict) else {}
    label = str(quality.get("label") or "未评估")
    score = quality.get("score")
    headline = f"{label} / {int(score)} 分" if isinstance(score, (int, float)) else label
    reasons = [str(item) for item in list(quality.get("reasons") or []) if str(item).strip()]
    return headline, reasons


def _recent_events(events, limit=5):
    items = [
        dict(item)
        for item in list(events or [])
        if isinstance(item, dict) and item.get("type") != "price_summary"
    ]
    items.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
    selected = []
    selected_ids = set()
    for event_type in ("alert", "risk_analysis", "news", "data_status", "review_note"):
        item = next((event for event in items if event.get("type") == event_type), None)
        if item is not None:
            selected.append(item)
            selected_ids.add(id(item))
    for item in items:
        if len(selected) >= int(limit):
            break
        if id(item) not in selected_ids:
            selected.append(item)
    selected.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
    return selected[: int(limit)]


def build_daily_digest(timeline_state, portfolio_state=None, market_quality=None, now=None):
    now = now or datetime.now()
    timeline_state = timeline_state if isinstance(timeline_state, dict) else {}
    portfolio_state = portfolio_state if isinstance(portfolio_state, dict) else {}
    market_quality = market_quality if isinstance(market_quality, dict) else {}
    range_info = timeline_state.get("range") if isinstance(timeline_state.get("range"), dict) else {}
    summary = timeline_state.get("summary") if isinstance(timeline_state.get("summary"), dict) else {}
    price_summary = (
        timeline_state.get("price_summary")
        if isinstance(timeline_state.get("price_summary"), dict)
        else {}
    )
    counts = _event_counts(summary)
    quality_headline, quality_reasons = _quality_line(market_quality)
    recent_events = _recent_events(timeline_state.get("events"))

    lines = [
        "GoldMonitor 每日摘要",
        "",
        f"生成时间：{now.strftime('%Y-%m-%d %H:%M:%S')}",
        f"统计范围：{range_info.get('start', '--')} -> {range_info.get('end', '--')}",
        "",
        "价格变化",
        _price_line(price_summary, "usd", "USD/oz"),
        _price_line(price_summary, "rmb", "RMB/克"),
        "",
        "事件概览",
        (
            f"- 预警 {counts['alert']} 条，风险分析 {counts['risk_analysis']} 条，"
            f"新闻 {counts['news']} 条，数据状态 {counts['data_status']} 条，"
            f"复盘笔记 {counts['review_note']} 条"
        ),
        "",
        "行情质量",
        f"- {quality_headline}",
    ]
    if quality_reasons:
        lines.append("- 原因：" + "；".join(quality_reasons[:5]))
    lines.extend([
        "",
        "持仓概览",
        _portfolio_line(portfolio_state, "rmb_summary", "人民币持仓"),
        _portfolio_line(portfolio_state, "usd_summary", "美元持仓"),
        "",
        "关键事件",
    ])
    if recent_events:
        for event in recent_events:
            lines.append(
                f"- {event.get('timestamp', '--')} {event.get('title', '')}：{event.get('summary', '')}"
            )
    else:
        lines.append("- 暂无关键事件")

    message = "\n".join(lines) + "\n"
    payload = {
        "kind": "daily_summary",
        "generated_at": now.isoformat(timespec="seconds"),
        "range": dict(range_info),
        "price_summary": dict(price_summary),
        "event_summary": counts,
        "market_quality": dict(market_quality),
        "portfolio_summary": {
            "rmb": dict(portfolio_state.get("rmb_summary") or {}),
            "usd": dict(portfolio_state.get("usd_summary") or {}),
        },
        "recent_events": recent_events,
        "message": message,
    }
    return {
        "subject": f"[GoldMonitor] 每日摘要 {now.strftime('%Y-%m-%d')}",
        "message": message,
        "payload": payload,
    }


def empty_daily_digest_state():
    return {
        "schema_version": DAILY_DIGEST_SCHEMA_VERSION,
        "last_attempt_at": "",
        "last_completed_at": "",
        "last_sent_at": "",
        "last_test_at": "",
        "last_status": "idle",
        "last_message": "",
        "last_channels": [],
        "updated_at": "",
    }


def normalize_daily_digest_state(payload):
    state = empty_daily_digest_state()
    if not isinstance(payload, dict):
        return state
    for key in (
        "last_attempt_at",
        "last_completed_at",
        "last_sent_at",
        "last_test_at",
        "last_status",
        "last_message",
        "updated_at",
    ):
        state[key] = str(payload.get(key) or "")
    state["last_channels"] = [
        str(item)
        for item in list(payload.get("last_channels") or [])
        if str(item).strip()
    ]
    return state


class DailyDigestStateStore:
    def __init__(self, state_path, now_factory=None):
        self.state_path = state_path
        self.now_factory = now_factory or datetime.now

    def load(self):
        if not os.path.exists(self.state_path):
            return empty_daily_digest_state()
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                return normalize_daily_digest_state(json.load(f))
        except (OSError, json.JSONDecodeError):
            return empty_daily_digest_state()

    def save(self, state):
        normalized = normalize_daily_digest_state(state)
        os.makedirs(os.path.dirname(self.state_path) or ".", exist_ok=True)
        tmp_path = self.state_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(normalized, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.state_path)
        return normalized

    def record_result(self, status, message, channels=None, sent=False, manual=False):
        state = self.load()
        now_text = self.now_factory().isoformat(timespec="seconds")
        if manual:
            state["last_test_at"] = now_text
        else:
            state["last_attempt_at"] = now_text
            state["last_completed_at"] = now_text
            if sent:
                state["last_sent_at"] = now_text
        state["last_status"] = str(status or "")
        state["last_message"] = str(message or "")
        state["last_channels"] = [str(item) for item in list(channels or []) if str(item).strip()]
        state["updated_at"] = now_text
        return self.save(state)
