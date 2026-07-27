from datetime import datetime, timedelta


EVENT_TIMELINE_TYPES = (
    "price_summary",
    "alert",
    "risk_analysis",
    "news",
    "data_status",
    "review_note",
)
EVENT_TIMELINE_DEFAULT_MINUTES = 60
EVENT_TIMELINE_ALLOWED_MINUTES = (60, 240, 1440, 10080, 43200, 129600)
EVENT_TIMELINE_MAX_LIMIT = 500
EVENT_TIMELINE_DEFAULT_LIMIT = 300
REVIEW_REPORT_EXPORT_PREFIX = "GoldMonitor-review-report"


def parse_iso_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def format_number(value, digits=2):
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def normalize_event_timeline_request(
    data=None,
    event_types=EVENT_TIMELINE_TYPES,
    allowed_minutes=EVENT_TIMELINE_ALLOWED_MINUTES,
    default_minutes=EVENT_TIMELINE_DEFAULT_MINUTES,
    default_limit=EVENT_TIMELINE_DEFAULT_LIMIT,
    max_limit=EVENT_TIMELINE_MAX_LIMIT,
):
    if not isinstance(data, dict):
        data = {}

    try:
        minutes = int(data.get("minutes") or default_minutes)
    except (TypeError, ValueError):
        minutes = default_minutes
    if minutes not in allowed_minutes:
        minutes = default_minutes

    try:
        limit = int(data.get("limit") or default_limit)
    except (TypeError, ValueError):
        limit = default_limit
    limit = max(1, min(max_limit, limit))

    raw_types = data.get("types")
    if isinstance(raw_types, str):
        raw_types = [raw_types]
    if isinstance(raw_types, list):
        types = []
        for item in raw_types:
            event_type = str(item or "").strip()
            if event_type in event_types and event_type not in types:
                types.append(event_type)
    else:
        types = list(event_types)
    if not types:
        types = list(event_types)

    return {"minutes": minutes, "limit": limit, "types": types}


def event_timeline_range(minutes, now_factory=None):
    now_factory = now_factory or datetime.now
    now = now_factory()
    start = now - timedelta(minutes=int(minutes))
    return start, now


def event_time_from_alert(entry, today_date=None):
    timestamp = entry.get("timestamp") if isinstance(entry, dict) else None
    parsed = parse_iso_datetime(timestamp)
    if parsed:
        return parsed
    raw_time = str(entry.get("time") or "").strip() if isinstance(entry, dict) else ""
    if raw_time and today_date:
        parsed = parse_iso_datetime(f"{today_date}T{raw_time}")
        if parsed:
            return parsed
    return None


def make_timeline_event(event_type, timestamp, title, summary, source, payload=None, event_id=None):
    parsed = parse_iso_datetime(timestamp)
    if not parsed:
        return None
    stable_id = event_id or f"{event_type}-{parsed.isoformat(timespec='seconds')}-{source}"
    return {
        "id": str(stable_id),
        "type": str(event_type or ""),
        "timestamp": parsed.isoformat(timespec="seconds"),
        "title": str(title or ""),
        "summary": str(summary or ""),
        "source": str(source or ""),
        "payload": payload if isinstance(payload, dict) else {},
    }


def summarize_price_series(points, field):
    values = [point.get(field) for point in points if isinstance(point, dict) and point.get(field) is not None]
    if not values:
        return {
            "points": 0,
            "start": None,
            "end": None,
            "high": None,
            "low": None,
            "change": None,
            "change_pct": None,
        }
    start = values[0]
    end = values[-1]
    change = end - start
    return {
        "points": len(values),
        "start": format_number(start),
        "end": format_number(end),
        "high": format_number(max(values)),
        "low": format_number(min(values)),
        "change": format_number(change),
        "change_pct": format_number(change / start * 100 if start else 0),
    }


def build_event_price_summary(points):
    points = list(points or [])
    return {
        "usd": summarize_price_series(points, "usd"),
        "rmb": summarize_price_series(points, "rmb"),
    }


def build_price_timeline_series(points):
    series = []
    for point in list(points or []):
        if not isinstance(point, dict):
            continue
        parsed = parse_iso_datetime(point.get("timestamp"))
        if not parsed:
            continue
        usd = format_number(point.get("usd"))
        rmb = format_number(point.get("rmb"))
        if usd is None and rmb is None:
            continue
        series.append({
            "timestamp": parsed.isoformat(timespec="seconds"),
            "usd": usd,
            "rmb": rmb,
        })
    series.sort(key=lambda item: item.get("timestamp", ""))
    return series


def build_price_summary_timeline_event(points, start_time, end_time):
    points = list(points or [])
    summary = build_event_price_summary(points)
    series = build_price_timeline_series(points)
    total = len(points)
    rmb = summary.get("rmb", {})
    if total:
        change_pct = rmb.get("change_pct")
        change_text = "--" if change_pct is None else f"{change_pct}%"
        text = f"范围内共有 {total} 个价格点，RMB/克变动 {change_text}。"
    else:
        text = "当前范围内暂无价格历史。"
    return make_timeline_event(
        "price_summary",
        end_time.isoformat(timespec="seconds"),
        "价格摘要",
        text,
        "price_history",
        {
            "points": total,
            "summary": summary,
            "series": series,
            "range_start": start_time.isoformat(timespec="seconds"),
            "range_end": end_time.isoformat(timespec="seconds"),
        },
        event_id=f"price-summary-{start_time.isoformat(timespec='seconds')}-{end_time.isoformat(timespec='seconds')}",
    )


def alert_level_label(alert_type):
    if alert_type == "critical":
        return "关键预警"
    if alert_type == "volatility":
        return "波动预警"
    return "价格预警"


def build_alert_timeline_events(start_time, end_time, alert_entries=None, today_date=None):
    events = []
    skipped = 0
    for entry in list(alert_entries or []):
        event_time = event_time_from_alert(entry, today_date=today_date)
        if not event_time:
            skipped += 1
            continue
        if event_time < start_time or event_time > end_time:
            continue
        rule_name = str(entry.get("rule_name") or "").strip()
        event_title = alert_level_label(entry.get("type"))
        if rule_name:
            event_title += "：" + rule_name
        event = make_timeline_event(
            "alert",
            event_time.isoformat(timespec="seconds"),
            event_title,
            str(entry.get("message") or "达到预警条件")[:180],
            "alert_log",
            {
                "id": entry.get("id", ""),
                "level": entry.get("type", ""),
                "mode": entry.get("mode", ""),
                "message": entry.get("message", ""),
                "time": entry.get("time", event_time.strftime("%H:%M:%S")),
                "title": entry.get("title", ""),
                "read": bool(entry.get("read")),
                "acknowledged": bool(entry.get("acknowledged")),
                "handled": bool(entry.get("handled")),
                "handled_at": entry.get("handled_at", ""),
                "handling_note": entry.get("handling_note", ""),
                "notifications": entry.get("notifications") if isinstance(entry.get("notifications"), list) else [],
                "related_news": entry.get("related_news") if isinstance(entry.get("related_news"), list) else [],
                "source": entry.get("source", ""),
                "rule_id": entry.get("rule_id", ""),
                "rule_kind": entry.get("rule_kind", ""),
                "rule_name": entry.get("rule_name", ""),
                "rule_scope": entry.get("rule_scope") if isinstance(entry.get("rule_scope"), dict) else {},
                "rule_condition": entry.get("rule_condition") if isinstance(entry.get("rule_condition"), dict) else {},
                "watch_target_id": entry.get("watch_target_id", ""),
            },
            event_id=f"alert-{entry.get('id') or event_time.isoformat(timespec='seconds')}",
        )
        if event:
            events.append(event)
    return events, skipped


def build_risk_timeline_events(start_time, end_time, risk_items=None):
    events = []
    skipped = 0
    for entry in list(risk_items or []):
        snapshot = entry.get("snapshot") if isinstance(entry.get("snapshot"), dict) else {}
        event_time = parse_iso_datetime(entry.get("analysis_time") or snapshot.get("analysis_time"))
        if not event_time:
            skipped += 1
            continue
        if event_time < start_time or event_time > end_time:
            continue
        structured = entry.get("structured") if isinstance(entry.get("structured"), dict) else {}
        content = str(entry.get("content") or "")
        content_lines = [line for line in content.splitlines() if line.strip()]
        risk_level = structured.get("risk_level") or ""
        title = f"风险分析：{risk_level}" if risk_level else "风险分析"
        summary = structured.get("summary") or (content_lines[0] if content_lines else "已有风险分析记录")
        event = make_timeline_event(
            "risk_analysis",
            event_time.isoformat(timespec="seconds"),
            title[:80],
            str(summary)[:180],
            "risk_analysis_history",
            {
                "id": entry.get("id", ""),
                "analysis_time": entry.get("analysis_time", ""),
                "provider": entry.get("provider", ""),
                "model": entry.get("model", ""),
                "content": content,
                "structured": structured,
                "snapshot": snapshot,
                "data_quality": snapshot.get("data_quality") if isinstance(snapshot.get("data_quality"), dict) else {},
                "market_quality": snapshot.get("market_quality") if isinstance(snapshot.get("market_quality"), dict) else {},
            },
            event_id=f"risk-analysis-{entry.get('id') or event_time.isoformat(timespec='seconds')}",
        )
        if event:
            events.append(event)
    return events, skipped


def default_news_key(item):
    url = str(item.get("url") or "").strip().lower()
    if url:
        return url
    return str(item.get("title") or "").strip().lower()


def build_news_timeline_events(start_time, end_time, news_items=None, news_key=None):
    events = []
    skipped = 0
    news_key = news_key or default_news_key
    for index, item in enumerate(list(news_items or [])):
        event_time = parse_iso_datetime(item.get("time"))
        if not event_time:
            skipped += 1
            continue
        if event_time < start_time or event_time > end_time:
            continue
        title = str(item.get("title") or "相关新闻")
        summary = str(item.get("summary") or item.get("topic") or item.get("source") or "相关新闻")[:180]
        event = make_timeline_event(
            "news",
            event_time.isoformat(timespec="seconds"),
            title[:80],
            summary,
            "news_cache",
            {
                "title": title,
                "url": item.get("url", ""),
                "source": item.get("source", ""),
                "topic": item.get("topic", ""),
                "summary": item.get("summary", ""),
            },
            event_id=f"news-{news_key(item) or index}",
        )
        if event:
            events.append(event)
    return events, skipped


def is_initial_fetch_waiting_status(fetch_status):
    if not isinstance(fetch_status, dict):
        return False
    message = str(fetch_status.get("message") or "").strip()
    error = str(fetch_status.get("error") or "").strip()
    return not error and "等待首次行情" in message


def build_data_status_timeline_events(
    start_time,
    end_time,
    fetch_status=None,
    source_health_state=None,
    source_comparison_state=None,
    now_factory=None,
):
    events = []
    skipped = 0
    now_factory = now_factory or datetime.now
    now = now_factory()

    fetch_status = fetch_status if isinstance(fetch_status, dict) else {}
    if not is_initial_fetch_waiting_status(fetch_status) and (fetch_status.get("ok") is False or fetch_status.get("error")):
        event = make_timeline_event(
            "data_status",
            now.isoformat(timespec="seconds"),
            "行情数据状态",
            fetch_status.get("message") or "行情数据异常",
            "fetch_status",
            fetch_status,
            event_id=f"data-status-fetch-{now.isoformat(timespec='seconds')}",
        )
        event_time = parse_iso_datetime(event["timestamp"]) if event else None
        if event and event_time and start_time <= event_time <= end_time:
            events.append(event)

    health = source_health_state if isinstance(source_health_state, dict) else {}
    for item in health.get("items", []):
        event_time = parse_iso_datetime(item.get("last_checked"))
        if not event_time:
            skipped += 1
            continue
        if event_time < start_time or event_time > end_time:
            continue
        if item.get("ok") is True and not item.get("cached"):
            continue
        title = "缓存行情" if item.get("cached") else "数据源异常"
        summary = item.get("error") or item.get("name") or title
        event = make_timeline_event(
            "data_status",
            event_time.isoformat(timespec="seconds"),
            title,
            summary,
            "source_health",
            dict(item),
            event_id=f"data-status-source-{item.get('name', '')}-{event_time.isoformat(timespec='seconds')}",
        )
        if event:
            events.append(event)

    comparison = source_comparison_state if isinstance(source_comparison_state, dict) else {}
    if comparison.get("status") == "anomaly":
        event_time = parse_iso_datetime(comparison.get("updated_at"))
        if not event_time:
            skipped += 1
        elif start_time <= event_time <= end_time:
            event = make_timeline_event(
                "data_status",
                event_time.isoformat(timespec="seconds"),
                "多源价差异常",
                comparison.get("message") or "数据源价差异常",
                "source_comparison",
                comparison,
                event_id=f"data-status-comparison-{event_time.isoformat(timespec='seconds')}",
            )
            if event:
                events.append(event)

    return events, skipped


def build_review_note_timeline_events(start_time, end_time, review_notes=None):
    events = []
    skipped = 0
    for index, item in enumerate(list(review_notes or [])):
        if not isinstance(item, dict):
            skipped += 1
            continue
        event_time = parse_iso_datetime(item.get("timestamp"))
        if not event_time:
            skipped += 1
            continue
        if event_time < start_time or event_time > end_time:
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            skipped += 1
            continue
        note_id = str(item.get("id") or index)
        title = str(item.get("title") or "复盘笔记").strip() or "复盘笔记"
        summary = " ".join(content.split())[:180]
        event = make_timeline_event(
            "review_note",
            event_time.isoformat(timespec="seconds"),
            title[:80],
            summary,
            "review_notes",
            dict(item),
            event_id=f"review-note-{note_id}",
        )
        if event:
            events.append(event)
    return events, skipped


def build_event_timeline_events(
    start_time,
    end_time,
    types=None,
    alert_entries=None,
    risk_items=None,
    news_items=None,
    fetch_status=None,
    source_health_state=None,
    source_comparison_state=None,
    review_notes=None,
    today_date=None,
    news_key=None,
    now_factory=None,
):
    selected = set(types or EVENT_TIMELINE_TYPES)
    events = []
    skipped = 0

    if "alert" in selected:
        built, count = build_alert_timeline_events(
            start_time,
            end_time,
            alert_entries=alert_entries,
            today_date=today_date,
        )
        events.extend(built)
        skipped += count
    if "risk_analysis" in selected:
        built, count = build_risk_timeline_events(start_time, end_time, risk_items=risk_items)
        events.extend(built)
        skipped += count
    if "news" in selected:
        built, count = build_news_timeline_events(start_time, end_time, news_items=news_items, news_key=news_key)
        events.extend(built)
        skipped += count
    if "data_status" in selected:
        built, count = build_data_status_timeline_events(
            start_time,
            end_time,
            fetch_status=fetch_status,
            source_health_state=source_health_state,
            source_comparison_state=source_comparison_state,
            now_factory=now_factory,
        )
        events.extend(built)
        skipped += count
    if "review_note" in selected:
        built, count = build_review_note_timeline_events(
            start_time,
            end_time,
            review_notes=review_notes,
        )
        events.extend(built)
        skipped += count

    events.sort(key=lambda item: item.get("timestamp", ""))
    return events, skipped


def build_event_timeline_state(
    minutes=None,
    limit=EVENT_TIMELINE_DEFAULT_LIMIT,
    types=None,
    price_points=None,
    alert_entries=None,
    risk_items=None,
    news_items=None,
    fetch_status=None,
    source_health_state=None,
    source_comparison_state=None,
    review_notes=None,
    today_date=None,
    news_key=None,
    now_factory=None,
):
    minutes = minutes or EVENT_TIMELINE_DEFAULT_MINUTES
    start_time, end_time = event_timeline_range(minutes, now_factory=now_factory)
    selected = list(types or EVENT_TIMELINE_TYPES)
    points = list(price_points or [])
    price_summary = build_event_price_summary(points)
    events, skipped = build_event_timeline_events(
        start_time,
        end_time,
        selected,
        alert_entries=alert_entries,
        risk_items=risk_items,
        news_items=news_items,
        fetch_status=fetch_status,
        source_health_state=source_health_state,
        source_comparison_state=source_comparison_state,
        review_notes=review_notes,
        today_date=today_date,
        news_key=news_key,
        now_factory=now_factory,
    )

    if "price_summary" in selected:
        price_event = build_price_summary_timeline_event(points, start_time, end_time)
        if price_event:
            events.insert(0, price_event)

    events.sort(key=lambda item: (item.get("timestamp", ""), item.get("type", ""), item.get("id", "")))
    if limit:
        events = events[-int(limit):]

    by_type = {event_type: 0 for event_type in EVENT_TIMELINE_TYPES}
    for event in events:
        event_type = event.get("type", "")
        by_type[event_type] = by_type.get(event_type, 0) + 1

    return {
        "range": {
            "start": start_time.isoformat(timespec="seconds"),
            "end": end_time.isoformat(timespec="seconds"),
            "minutes": int(minutes),
        },
        "filters": {"types": selected},
        "summary": {
            "total": len(events),
            "skipped": skipped,
            "by_type": by_type,
        },
        "price_summary": price_summary,
        "events": events,
        "updated_at": (now_factory or datetime.now)().isoformat(timespec="seconds"),
    }


def build_price_chart_events(items, timeline_event_builder):
    if not items:
        return []
    parsed_points = [
        parse_iso_datetime(item.get("timestamp"))
        for item in items
        if isinstance(item, dict)
    ]
    parsed_points = [item for item in parsed_points if item]
    if not parsed_points:
        return []
    events, _skipped = timeline_event_builder(min(parsed_points), max(parsed_points), ["alert", "risk_analysis"])
    chart_events = []
    for event in events[-100:]:
        payload = event.get("payload", {})
        event_type = "risk" if event.get("type") == "risk_analysis" else event.get("type")
        chart_events.append({
            "type": event_type,
            "level": payload.get("level", "analysis"),
            "mode": payload.get("mode", ""),
            "timestamp": event.get("timestamp", ""),
            "time": payload.get("time", ""),
            "label": event.get("title", ""),
            "message": event.get("summary", ""),
        })
    return chart_events


def report_number(value):
    formatted = format_number(value)
    return "--" if formatted is None else str(formatted)


def report_price_direction(price_summary, key="rmb", label="RMB/克"):
    item = price_summary.get(key, {}) if isinstance(price_summary, dict) else {}
    points = item.get("points") or 0
    start = format_number(item.get("start"))
    end = format_number(item.get("end"))
    change = format_number(item.get("change"))
    change_pct = format_number(item.get("change_pct"), digits=4)
    if points < 2 or start is None or end is None:
        return f"{label}样本不足，暂不判断整体方向。"
    if change is None:
        change = format_number(end - start)
    if change and change > 0:
        direction = "整体上行"
    elif change and change < 0:
        direction = "整体下行"
    else:
        direction = "整体持平"
    return (
        f"{label}{direction}：{report_number(start)} -> {report_number(end)}，"
        f"变动 {report_number(change)}（{report_number(change_pct)}%）。"
    )


def review_report_price_series(events):
    for event in events:
        if not isinstance(event, dict) or event.get("type") != "price_summary":
            continue
        payload = event.get("payload", {})
        raw_series = payload.get("series") if isinstance(payload, dict) else []
        if isinstance(raw_series, list):
            return build_price_timeline_series(raw_series)
    return []


def build_alert_followup_report_lines(events, price_series):
    alerts = [
        event for event in events
        if isinstance(event, dict) and event.get("type") == "alert"
    ]
    if not alerts:
        return ["暂无告警事件。"]
    if not price_series:
        return ["暂无可用价格序列，无法复盘告警后走势。"]

    parsed_series = []
    for point in price_series:
        parsed = parse_iso_datetime(point.get("timestamp")) if isinstance(point, dict) else None
        if parsed:
            parsed_series.append((parsed, point))
    parsed_series.sort(key=lambda item: item[0])
    if not parsed_series:
        return ["暂无可用价格序列，无法复盘告警后走势。"]

    lines = []
    for alert in alerts:
        alert_time = parse_iso_datetime(alert.get("timestamp"))
        title = alert.get("title") or "价格预警"
        if not alert_time:
            lines.append(f"- {title}：告警时间无效，无法复盘后续走势。")
            continue

        baseline = None
        followup = None
        for point_time, point in parsed_series:
            if point_time <= alert_time:
                baseline = point
            if point_time >= alert_time:
                if baseline is None:
                    baseline = point
                followup = point

        if baseline is None:
            lines.append(f"- {title}：告警前后暂无可用价格样本。")
            continue
        if followup is None:
            lines.append(f"- {title}：告警后暂无新的价格样本。")
            continue

        start_rmb = format_number(baseline.get("rmb"))
        end_rmb = format_number(followup.get("rmb"))
        if start_rmb is None or end_rmb is None:
            lines.append(f"- {title}：告警后暂无可用 RMB/克样本。")
            continue

        change = format_number(end_rmb - start_rmb)
        lines.append(
            f"- {title}：告警后 RMB/克 {report_number(start_rmb)} -> {report_number(end_rmb)}，"
            f"变动 {report_number(change)}。"
        )
    return lines


def build_data_quality_report_lines(events, summary, price_series):
    data_status_events = [
        event for event in events
        if isinstance(event, dict) and event.get("type") == "data_status"
    ]
    skipped = summary.get("skipped", 0) if isinstance(summary, dict) else 0
    lines = [
        f"- 价格序列样本：{len(price_series)} 个；跳过记录：{skipped}。",
    ]
    if data_status_events:
        lines.append(f"- 记录到 {len(data_status_events)} 条数据状态事件，需结合行情源、缓存和多源价差判断可信度。")
        latest = sorted(data_status_events, key=lambda item: item.get("timestamp", ""))[-1]
        lines.append(
            f"- 最近数据状态：{latest.get('timestamp', '--')} "
            f"{latest.get('title', '')}：{latest.get('summary', '')}"
        )
    else:
        lines.append("- 未记录数据状态异常，当前报告未发现行情源、缓存或多源价差异常事件。")

    risk_quality_scores = []
    for event in events:
        if not isinstance(event, dict) or event.get("type") != "risk_analysis":
            continue
        payload = event.get("payload", {})
        quality = payload.get("data_quality") if isinstance(payload, dict) else {}
        score = quality.get("score") if isinstance(quality, dict) else None
        score = format_number(score)
        if score is not None:
            risk_quality_scores.append(score)
    if risk_quality_scores:
        lines.append(f"- 风险分析数据质量评分：{', '.join(str(score) for score in risk_quality_scores)}。")
    else:
        lines.append("- 本次范围内暂无风险分析数据质量评分。")
    return lines


def build_review_report(timeline_state):
    range_info = timeline_state.get("range", {}) if isinstance(timeline_state, dict) else {}
    summary = timeline_state.get("summary", {}) if isinstance(timeline_state, dict) else {}
    price_summary = timeline_state.get("price_summary", {}) if isinstance(timeline_state, dict) else {}
    events = timeline_state.get("events", []) if isinstance(timeline_state, dict) else []
    if not isinstance(events, list):
        events = []
    price_series = review_report_price_series(events)

    lines = [
        "# GoldMonitor 复盘报告",
        "",
        "## 时间范围",
        f"- 开始：{range_info.get('start', '--')}",
        f"- 结束：{range_info.get('end', '--')}",
        f"- 范围：最近 {range_info.get('minutes', '--')} 分钟",
        "",
        "## 复盘结论",
        f"- {report_price_direction(price_summary)}",
        f"- 本次复盘记录 {summary.get('total', 0)} 条事件，跳过 {summary.get('skipped', 0)} 条无法解析记录。",
        "",
        "## 价格摘要",
    ]

    for label, key in (("USD/oz", "usd"), ("RMB/克", "rmb")):
        item = price_summary.get(key, {}) if isinstance(price_summary, dict) else {}
        lines.extend([
            f"- {label} 样本：{item.get('points', 0)}",
            f"- {label} 起止：{item.get('start', '--')} -> {item.get('end', '--')}",
            f"- {label} 高低：{item.get('high', '--')} / {item.get('low', '--')}",
            f"- {label} 变动：{item.get('change', '--')}（{item.get('change_pct', '--')}%）",
        ])

    by_type = summary.get("by_type", {}) if isinstance(summary, dict) else {}
    lines.extend([
        "",
        "## 事件概览",
        f"- 事件总数：{summary.get('total', 0)}",
        f"- 跳过记录：{summary.get('skipped', 0)}",
        f"- 价格摘要：{by_type.get('price_summary', 0)}",
        f"- 预警：{by_type.get('alert', 0)}",
        f"- 风险分析：{by_type.get('risk_analysis', 0)}",
        f"- 新闻：{by_type.get('news', 0)}",
        f"- 数据状态：{by_type.get('data_status', 0)}",
        f"- 复盘笔记：{by_type.get('review_note', 0)}",
        "",
        "## 关键事件",
    ])

    visible_events = [event for event in events if isinstance(event, dict) and event.get("type") != "price_summary"]
    if not visible_events:
        lines.append("暂无事件。")
    else:
        for event in visible_events[:80]:
            lines.append(
                f"- {event.get('timestamp', '--')} [{event.get('type', '--')}] "
                f"{event.get('title', '')}：{event.get('summary', '')}"
            )

    def add_section(title, event_type, empty_text):
        lines.extend(["", f"## {title}"])
        subset = [event for event in events if isinstance(event, dict) and event.get("type") == event_type]
        if not subset:
            lines.append(empty_text)
            return
        for event in subset:
            lines.append(f"- {event.get('timestamp', '--')} {event.get('title', '')}：{event.get('summary', '')}")

    add_section("预警回顾", "alert", "暂无预警。")
    lines.extend(["", "## 告警后走势"])
    lines.extend(build_alert_followup_report_lines(events, price_series))
    add_section("风险分析记录", "risk_analysis", "暂无风险分析记录。")
    add_section("新闻回顾", "news", "暂无相关新闻。")
    lines.extend(["", "## 复盘笔记"])
    note_events = [
        event
        for event in events
        if isinstance(event, dict) and event.get("type") == "review_note"
    ]
    if not note_events:
        lines.append("暂无复盘笔记。")
    else:
        for event in note_events:
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            content = str(payload.get("content") or event.get("summary") or "").strip()
            lines.extend([
                f"### {event.get('timestamp', '--')} {event.get('title', '复盘笔记')}",
                content or "暂无内容。",
            ])
            related_title = str(payload.get("related_event_title") or "").strip()
            if related_title:
                lines.append(f"- 关联事件：{related_title}")
            lines.append("")
    lines.extend(["", "## 数据质量结论"])
    lines.extend(build_data_quality_report_lines(events, summary, price_series))
    add_section("数据状态", "data_status", "暂无数据状态异常。")

    return "\n".join(lines) + "\n"


def review_report_filename(now=None, prefix=REVIEW_REPORT_EXPORT_PREFIX):
    now = now or datetime.now()
    return f"{prefix}-{now.strftime('%Y%m%d-%H%M%S')}.md"
