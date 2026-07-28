import json
import logging
import os
from datetime import datetime, timedelta

from goldmonitor.data_contracts import unwrap_item_payload, wrap_item_payload


RISK_SECTION_LABELS = (
    ("risk_level", "风险等级"),
    ("trend_direction", "趋势方向"),
    ("data_credibility", "数据可信度"),
    ("main_factors", "主要影响因素"),
    ("watch_range", "观察价格区间"),
    ("follow_up", "后续关注"),
)


class _NeverRaised(Exception):
    pass


def parse_iso_datetime(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo:
            parsed = parsed.replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


def format_number(value, digits=2):
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def valid_market_price(value):
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def market_data_error(price_usd, price_rmb):
    if valid_market_price(price_usd) or valid_market_price(price_rmb):
        return ""
    return "当前没有可用于风险分析的行情价格，请先重新获取行情数据。"


def summarize_price_series(points, field):
    values = [item.get(field) for item in points if item.get(field) is not None]
    if not values:
        return {key: value for key, value in (
            ("points", 0), ("start", None), ("end", None), ("high", None),
            ("low", None), ("change", None), ("change_pct", None),
        )}
    start, end = values[0], values[-1]
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


def summarize_klines(candles):
    if not candles:
        return {"points": 0, "latest": None, "high": None, "low": None, "direction": "样本不足"}
    closes = [item.get("close") for item in candles if item.get("close") is not None]
    highs = [item.get("high") for item in candles if item.get("high") is not None]
    lows = [item.get("low") for item in candles if item.get("low") is not None]
    latest = candles[-1]
    direction = "样本不足"
    if len(closes) >= 2:
        direction = "上行" if closes[-1] > closes[0] else "下行" if closes[-1] < closes[0] else "震荡"
    return {
        "points": len(candles),
        "latest": {
            "time": latest.get("time"),
            **{key: format_number(latest.get(key)) for key in ("open", "high", "low", "close")},
        },
        "high": format_number(max(highs) if highs else None),
        "low": format_number(min(lows) if lows else None),
        "direction": direction,
    }


def history_window(points, minutes, now_factory=None):
    if not points:
        return []
    now_factory = now_factory or datetime.now
    latest_time = parse_iso_datetime(points[-1].get("timestamp")) or now_factory()
    cutoff = latest_time - timedelta(minutes=minutes)
    filtered = [
        item for item in points
        if (parse_iso_datetime(item.get("timestamp")) or latest_time) >= cutoff
    ]
    return filtered or points[-max(2, int(minutes * 6)):]


def trend_direction(summary):
    if summary.get("points", 0) < 2 or summary.get("change_pct") is None:
        return "样本不足"
    percent = summary.get("change_pct") or 0
    return "震荡" if abs(percent) < 0.03 else "上行" if percent > 0 else "下行"


def build_multi_period_trends(history, periods, now_factory=None):
    trends = []
    for minutes in periods:
        window = history_window(history, minutes, now_factory=now_factory)
        usd = summarize_price_series(window, "usd")
        rmb = summarize_price_series(window, "rmb")
        trends.append({
            "minutes": minutes,
            "points": len(window),
            "usd": usd,
            "rmb": rmb,
            "direction_usd": trend_direction(usd),
            "direction_rmb": trend_direction(rmb),
        })
    return trends


def assess_data_quality(context, now_factory=None):
    market = context.get("market", {})
    history = context.get("history_summary", {}).get("usd", {})
    kline = context.get("kline_summary", {}).get("usd", {})
    score, issues = 100, []
    for applies, points, message in (
        (market.get("price_usd") is None, 35, "国际金价缺失"),
        (market.get("price_rmb") is None, 25, "人民币金价缺失"),
        (market.get("gold_cached"), 15, "金价来自缓存"),
        (market.get("rate_cached"), 10, "汇率来自缓存"),
        (not market.get("last_fetch_ok"), 10, "最近一次行情刷新异常"),
    ):
        if applies:
            score -= points
            issues.append(message)
    history_points = history.get("points", 0)
    if history_points < 12:
        score -= 15
        issues.append("历史价格样本偏少")
    elif history_points < 60:
        score -= 6
        issues.append("历史样本不足 10 分钟")
    if kline.get("points", 0) < 2:
        score -= 10
        issues.append("5分钟K线样本不足")
    if not context.get("news"):
        score -= 5
        issues.append("近期资讯为空")
    now = (now_factory or datetime.now)()
    for value, seconds, points, message in (
        (market.get("gold_time"), 15 * 60, 8, "金价更新时间超过 15 分钟"),
        (market.get("rate_time"), 60 * 60, 5, "汇率更新时间超过 1 小时"),
    ):
        parsed = parse_iso_datetime(value)
        if parsed and (now - parsed).total_seconds() > seconds:
            score -= points
            issues.append(message)
    score = max(0, min(100, score))
    return {
        "score": score,
        "level": "高" if score >= 85 else "中" if score >= 65 else "低",
        "issues": issues,
        "summary": "；".join(issues) if issues else "数据状态良好",
    }


def build_risk_scorecard(context):
    trends = context.get("multi_period_trends", [])
    history = context.get("history_summary", {})
    news = context.get("news", [])
    rmb = history.get("rmb", {})
    rates = [item.get("rate") for item in history.get("latest_points", []) if item.get("rate") is not None]
    changes = [abs((item.get("rmb") or {}).get("change_pct") or 0) for item in trends]
    trend_strength = min(100, int((max(changes) if changes else 0) * 35))
    high, low, end = rmb.get("high"), rmb.get("low"), rmb.get("end")
    volatility_pct = ((high - low) / end * 100) if high is not None and low is not None and end else 0
    volatility_risk = min(100, int(volatility_pct * 25))
    fx_change_pct = abs((rates[-1] - rates[0]) / rates[0] * 100) if len(rates) >= 2 and rates[0] else 0
    fx_impact = min(100, int(fx_change_pct * 40))
    event_risk = 0
    for item in news:
        text = f"{item.get('topic') or ''} {item.get('title') or ''}".lower()
        event_risk += 25 if any(key in text for key in ("fed", "fomc", "inflation", "cpi", "jobs", "payroll", "dollar", "yield")) else 12
    event_risk = min(100, event_risk)
    credibility = int(context.get("data_quality", {}).get("score", 0) or 0)
    overall = int(volatility_risk * 0.28 + event_risk * 0.24 + trend_strength * 0.22 + fx_impact * 0.12 + (100 - credibility) * 0.14)
    return {
        "overall_risk": max(0, min(100, overall)),
        "trend_strength": trend_strength,
        "volatility_risk": volatility_risk,
        "fx_impact": fx_impact,
        "event_risk": event_risk,
        "data_credibility": credibility,
        "volatility_pct": format_number(volatility_pct),
        "fx_change_pct": format_number(fx_change_pct, 4),
    }


def build_context(state, settings, *, trigger=None, depth=None, valid_depths, trend_periods, news_limit, source_health=None, now_factory=None):
    now_factory = now_factory or datetime.now
    depth = depth if depth in valid_depths else settings.get("risk_assistant_depth", "standard")
    depth = depth if depth in valid_depths else "standard"
    history_limit = {"quick": 120, "standard": 360, "deep": 1440}.get(depth, 360)
    selected_news_limit = {"quick": 3, "standard": news_limit, "deep": 10}.get(depth, news_limit)
    source_history = state["price_archive"] if depth == "deep" and state["price_archive"] else state["price_history"]
    history = list(source_history[-history_limit:])
    candles = list(state["klines_5min"][-72:])
    news = list(state["news_items"][:selected_news_limit])
    usd_change = state["price_usd"] - state["today_open_usd"] if state["price_usd"] is not None and state["today_open_usd"] else None
    rmb_change = state["price_rmb"] - state["today_open_rmb"] if state["price_rmb"] is not None and state["today_open_rmb"] else None
    now = now_factory()
    context = {
        "analysis_time": now.isoformat(timespec="seconds"),
        "analysis_depth": depth,
        "market": {
            "price_usd": format_number(state["price_usd"]), "price_rmb": format_number(state["price_rmb"]),
            "previous_usd": format_number(state["previous_usd"]), "previous_rmb": format_number(state["previous_rmb"]),
            "usdcny_rate": format_number(state["usdcny_rate"], 4),
            "gold_source": state["gold_price_source"], "gold_time": state["gold_price_time"],
            "gold_cached": state["gold_price_cached"], "gold_error": state["gold_price_error"],
            "rate_source": state["usdcny_rate_source"], "rate_time": state["usdcny_rate_time"],
            "rate_cached": state["usdcny_rate_cached"], "rate_error": state["usdcny_rate_error"],
            "last_fetch_ok": state["last_fetch_ok"], "last_fetch_error": state["last_fetch_error"],
            "last_fetch_time": state["last_fetch_time"],
        },
        "daily": {
            "date": state["today_date"],
            "open_usd": format_number(state["today_open_usd"]), "high_usd": format_number(state["today_high_usd"]),
            "low_usd": format_number(state["today_low_usd"]), "change_usd": format_number(usd_change),
            "pct_usd": format_number(usd_change / state["today_open_usd"] * 100 if usd_change is not None and state["today_open_usd"] else None),
            "open_rmb": format_number(state["today_open_rmb"]), "high_rmb": format_number(state["today_high_rmb"]),
            "low_rmb": format_number(state["today_low_rmb"]), "change_rmb": format_number(rmb_change),
            "pct_rmb": format_number(rmb_change / state["today_open_rmb"] * 100 if rmb_change is not None and state["today_open_rmb"] else None),
        },
        "history_summary": {
            "minutes": 60, "usd": summarize_price_series(history, "usd"),
            "rmb": summarize_price_series(history, "rmb"), "latest_points": history[-12:],
        },
        "multi_period_trends": build_multi_period_trends(history, trend_periods, now_factory=lambda: now),
        "kline_summary": {"period": "5min", "usd": summarize_klines(candles), "latest_candles": candles[-12:]},
        "news": [{key: item.get(key, "") for key in ("title", "source", "time", "topic", "summary")} for item in news],
    }
    if isinstance(trigger, dict):
        context["manual_trigger"] = {
            "source": str(trigger.get("source") or "manual"), "time": str(trigger.get("time") or ""),
            "type": str(trigger.get("type") or ""), "mode": str(trigger.get("mode") or ""),
            "message": str(trigger.get("message") or "")[:500],
        }
    context["market_quality"] = source_health.get("quality") if isinstance(source_health, dict) else {}
    context["sample_warning"] = "样本不足" if len(history) < 12 or len(candles) < 2 else ""
    context["data_quality"] = assess_data_quality(context, now_factory=lambda: now)
    context["risk_scorecard"] = build_risk_scorecard(context)
    return context


def build_context_from_runtime(
    runtime,
    settings,
    *,
    trigger=None,
    depth=None,
    valid_depths,
    trend_periods,
    news_limit,
    source_health=None,
    now_factory=None,
):
    with runtime.lock:
        state = {
            "price_archive": list(runtime.price_archive),
            "price_history": list(runtime.price_history),
            "klines_5min": list(runtime.klines_5min),
            "news_items": list(runtime.news_items),
            "price_usd": runtime.price_usd,
            "price_rmb": runtime.price_rmb,
            "previous_usd": runtime.previous_usd,
            "previous_rmb": runtime.previous_rmb,
            "usdcny_rate": runtime.usdcny_rate,
            "gold_price_source": runtime.gold_price_source,
            "gold_price_time": runtime.gold_price_time,
            "gold_price_cached": runtime.gold_price_cached,
            "gold_price_error": runtime.gold_price_error,
            "usdcny_rate_source": runtime.usdcny_rate_source,
            "usdcny_rate_time": runtime.usdcny_rate_time,
            "usdcny_rate_cached": runtime.usdcny_rate_cached,
            "usdcny_rate_error": runtime.usdcny_rate_error,
            "last_fetch_ok": runtime.last_fetch_ok,
            "last_fetch_error": runtime.last_fetch_error,
            "last_fetch_time": runtime.last_fetch_time,
            "today_date": runtime.today_date,
            "today_open_usd": runtime.today_open_usd,
            "today_high_usd": runtime.today_high_usd,
            "today_low_usd": runtime.today_low_usd,
            "today_open_rmb": runtime.today_open_rmb,
            "today_high_rmb": runtime.today_high_rmb,
            "today_low_rmb": runtime.today_low_rmb,
        }
    return build_context(
        state,
        settings,
        trigger=trigger,
        depth=depth,
        valid_depths=valid_depths,
        trend_periods=trend_periods,
        news_limit=news_limit,
        source_health=source_health,
        now_factory=now_factory,
    )


class RiskAnalysisHistoryStore:
    def __init__(self, json_path, history_limit=20, now_factory=None, logger=None):
        self.json_path = json_path
        self.history_limit = int(history_limit)
        self.now_factory = now_factory or datetime.now
        self.logger = logger or logging.getLogger(__name__)

    def _now_iso(self):
        return self.now_factory().isoformat(timespec="seconds")

    def normalize(self, items):
        if not isinstance(items, list):
            return []
        normalized = []
        for item in items:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            snapshot = item.get("snapshot") if isinstance(item.get("snapshot"), dict) else {}
            evidence_summary = item.get("evidence_summary") if isinstance(item.get("evidence_summary"), dict) else None
            if evidence_summary is None and isinstance(snapshot.get("evidence_summary"), dict):
                evidence_summary = snapshot.get("evidence_summary")
            if evidence_summary is None:
                evidence_summary = build_evidence_summary(snapshot)
            normalized.append({
                "id": str(item.get("id") or item.get("analysis_time") or self._now_iso()),
                "analysis_time": str(item.get("analysis_time") or ""),
                "provider": str(item.get("provider") or ""),
                "model": str(item.get("model") or ""),
                "content": content,
                "structured": item.get("structured") if isinstance(item.get("structured"), dict) else {},
                "snapshot": snapshot,
                "evidence_summary": evidence_summary,
                "usage": item.get("usage") if isinstance(item.get("usage"), dict) else None,
            })
            if len(normalized) >= self.history_limit:
                break
        return normalized

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
        tmp_path = self.json_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(wrap_item_payload(normalized), f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.json_path)
        return normalized

    def clear(self):
        return self.save([])

    def build_state(self, items):
        return {"items": list(items[:self.history_limit])}

    def build_entry(self, result, snapshot):
        now_iso = self._now_iso()
        return {
            "id": now_iso,
            "analysis_time": snapshot.get("analysis_time") or now_iso,
            "provider": result.get("provider", ""),
            "model": result.get("model", ""),
            "content": str(result.get("content") or "").strip(),
            "structured": result.get("structured") if isinstance(result.get("structured"), dict) else {},
            "snapshot": snapshot,
            "evidence_summary": snapshot.get("evidence_summary") if isinstance(snapshot.get("evidence_summary"), dict) else build_evidence_summary(snapshot),
            "usage": result.get("usage") if isinstance(result.get("usage"), dict) else None,
        }

    def add_entry(self, history, result, snapshot):
        entry = self.build_entry(result, snapshot)
        return self.normalize([entry] + list(history or [])), dict(entry)


def _as_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _count_value(value):
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _format_quality_summary(quality):
    if not isinstance(quality, dict):
        return ""
    reasons = quality.get("reasons") if isinstance(quality.get("reasons"), list) else []
    return quality.get("summary") or "；".join(str(item) for item in reasons if item) or quality.get("label") or quality.get("level") or ""


def build_evidence_summary(snapshot):
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    quality = snapshot.get("market_quality") if isinstance(snapshot.get("market_quality"), dict) and snapshot.get("market_quality") else snapshot.get("data_quality")
    quality = quality if isinstance(quality, dict) else {}
    history_points = _count_value(snapshot.get("history_points"))
    kline_points = _count_value(snapshot.get("kline_points"))
    news_count = _count_value(snapshot.get("news_count"))
    missing = []
    recovery = []
    if snapshot.get("price_rmb") is None and snapshot.get("price_usd") is None:
        missing.append("当前行情价格")
        recovery.append("点击重新获取行情数据")
    if history_points < 12:
        missing.append("历史价格样本不足")
        recovery.append("保持程序运行一段时间以积累实时价格")
    if kline_points < 2:
        missing.append("5分钟K线样本不足")
        recovery.append("等待至少两根5分钟K线生成")
    if news_count < 1:
        missing.append("近期资讯为空")
        recovery.append("刷新资讯或检查网络连接")
    return {
        "price_rmb": snapshot.get("price_rmb"),
        "price_usd": snapshot.get("price_usd"),
        "gold_source": snapshot.get("gold_source") or "",
        "gold_time": snapshot.get("gold_time") or "",
        "gold_cached": _as_bool(snapshot.get("gold_cached")),
        "gold_error": snapshot.get("gold_error") or "",
        "rate_source": snapshot.get("rate_source") or "",
        "rate_time": snapshot.get("rate_time") or "",
        "rate_cached": _as_bool(snapshot.get("rate_cached")),
        "rate_error": snapshot.get("rate_error") or "",
        "history_points": history_points,
        "kline_points": kline_points,
        "news_count": news_count,
        "quality_score": quality.get("score"),
        "quality_label": quality.get("label") or quality.get("level") or "",
        "quality_summary": _format_quality_summary(quality) or snapshot.get("sample_warning") or "",
        "missing": missing,
        "recovery": recovery,
    }


def build_snapshot(context):
    market = context.get("market", {})
    daily = context.get("daily", {})
    history = context.get("history_summary", {})
    snapshot = {
        "analysis_time": context.get("analysis_time"),
        "analysis_depth": context.get("analysis_depth", "standard"),
        "price_usd": market.get("price_usd"),
        "price_rmb": market.get("price_rmb"),
        "usdcny_rate": market.get("usdcny_rate"),
        "gold_source": market.get("gold_source"),
        "gold_time": market.get("gold_time"),
        "gold_cached": _as_bool(market.get("gold_cached")),
        "gold_error": market.get("gold_error") or "",
        "rate_source": market.get("rate_source"),
        "rate_time": market.get("rate_time"),
        "rate_cached": _as_bool(market.get("rate_cached")),
        "rate_error": market.get("rate_error") or "",
        "daily_pct_usd": daily.get("pct_usd"),
        "daily_pct_rmb": daily.get("pct_rmb"),
        "history_points": history.get("usd", {}).get("points", 0),
        "kline_points": context.get("kline_summary", {}).get("usd", {}).get("points", 0),
        "news_count": len(context.get("news", [])),
        "sample_warning": context.get("sample_warning", ""),
        "data_quality": context.get("data_quality", {}),
        "market_quality": context.get("market_quality", {}),
        "multi_period_trends": context.get("multi_period_trends", []),
        "risk_scorecard": context.get("risk_scorecard", {}),
        "manual_trigger": context.get("manual_trigger", {}),
    }
    snapshot["evidence_summary"] = build_evidence_summary(snapshot)
    return snapshot


def parse_sections(content, section_labels=RISK_SECTION_LABELS):
    sections = {key: [] for key, _label in section_labels}
    current_key = None
    for raw_line in str(content or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        clean = line.lstrip("#*-0123456789.、 ").strip()
        matched = False
        for key, label in section_labels:
            for separator in ("：", ":"):
                prefix = label + separator
                if clean.startswith(prefix):
                    current_key = key
                    value = clean[len(prefix):].strip()
                    if value:
                        sections[key].append(value)
                    matched = True
                    break
            if matched:
                break
        if matched:
            continue
        if current_key:
            sections[current_key].append(line)
    return {
        key: "\n".join(value).strip()
        for key, value in sections.items()
        if "\n".join(value).strip()
    }


def build_cache_key(snapshot):
    data = {
        "analysis_depth": snapshot.get("analysis_depth", "standard"),
        "price_usd": snapshot.get("price_usd"),
        "price_rmb": snapshot.get("price_rmb"),
        "usdcny_rate": snapshot.get("usdcny_rate"),
        "gold_time": snapshot.get("gold_time"),
        "gold_cached": snapshot.get("gold_cached"),
        "gold_error": snapshot.get("gold_error", ""),
        "rate_time": snapshot.get("rate_time"),
        "rate_cached": snapshot.get("rate_cached"),
        "rate_error": snapshot.get("rate_error", ""),
        "history_points": snapshot.get("history_points"),
        "kline_points": snapshot.get("kline_points"),
        "news_count": snapshot.get("news_count"),
        "sample_warning": snapshot.get("sample_warning", ""),
        "market_quality": snapshot.get("market_quality") or {},
        "manual_trigger": snapshot.get("manual_trigger") or {},
    }
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def find_recent_cache(history, snapshot, cache_minutes, now=None):
    if not cache_minutes:
        return None
    target_key = build_cache_key(snapshot)
    now = now or datetime.now()
    for item in history or []:
        if not isinstance(item, dict):
            continue
        item_snapshot = item.get("snapshot") if isinstance(item.get("snapshot"), dict) else {}
        if build_cache_key(item_snapshot) != target_key:
            continue
        item_time = parse_iso_datetime(item.get("analysis_time"))
        if not item_time:
            continue
        age_seconds = max(0, int((now - item_time).total_seconds()))
        if age_seconds <= int(cache_minutes) * 60:
            cached = dict(item)
            cached["cache_age_seconds"] = age_seconds
            return cached
    return None


def build_messages(context):
    depth = context.get("analysis_depth", "standard")
    depth_label = {"quick": "快速", "standard": "标准", "deep": "深度"}.get(depth, "标准")
    system_prompt = (
        "你是金价监控工具中的风险分析助手。"
        "请只做风险、趋势和观察依据分析，不提供交易动作、持有比例、收益承诺或保证性结论。"
        "如果数据样本不足或来源为缓存，需要直接指出限制。"
        "输出使用中文，结构包含：数据可信度、风险评分卡、多周期趋势、主要风险、观察依据、后续关注。"
        "请使用固定字段输出：风险等级、趋势方向、数据可信度、主要影响因素、观察价格区间、后续关注。"
    )
    user_prompt = (
        f"请基于以下实时上下文进行{depth_label}黄金价格风险与趋势分析。"
        "请优先说明风险评分卡、多周期趋势是否一致，以及数据可信度对结论的影响。"
        "仅输出风险研判，不输出具体操作指令。"
        "请严格使用以下标签开头：风险等级：、趋势方向：、数据可信度：、主要影响因素：、观察价格区间：、后续关注：。\n\n"
        f"{json.dumps(context, ensure_ascii=False, separators=(',', ':'))}"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def build_model_test_messages():
    return [
        {"role": "system", "content": "你是金价监控工具中的模型连通性测试助手。"},
        {"role": "user", "content": "请只回复：模型连接正常。"},
    ]


def selected_model_label(settings):
    settings = settings if isinstance(settings, dict) else {}
    provider = settings.get("risk_assistant_provider", "deepseek")
    if provider == "deepseek":
        return provider, settings.get("deepseek_model") or ""
    if provider == "openai_compatible":
        return provider, settings.get("openai_compatible_model") or ""
    return provider, ""


def build_error_diagnostic(message, settings=None, snapshot=None):
    message = str(message or "风险分析失败。").strip()
    settings = settings if isinstance(settings, dict) else {}
    provider, model = selected_model_label(settings)
    diagnostic = {
        "type": "unknown",
        "title": "风险分析失败",
        "reason": message,
        "impact": "风险分析未生成，本次不会写入分析历史。",
        "recovery": ["稍后重试；如果问题持续，请导出诊断报告核对配置和网络状态。"],
        "provider": provider,
        "model": model,
    }
    if snapshot:
        diagnostic["data_quality"] = (snapshot or {}).get("evidence_summary") or {}

    if "没有可用于风险分析的行情价格" in message:
        diagnostic.update({
            "type": "market_data_missing",
            "title": "缺少行情价格",
            "recovery": [
                "点击重新获取行情，等待当前金价返回后再分析。",
                "如果行情源持续异常，请查看数据状态中的行情源和缓存状态。",
            ],
        })
    elif "认证失败" in message or "API Key" in message:
        diagnostic.update({
            "type": "model_auth",
            "title": "模型服务认证失败",
            "recovery": [
                "在设置中确认当前模型提供商的 API Key 已保存。",
                "确认 API Key 具备调用所选模型生成接口的权限。",
                "重新点击测试模型，确认轻量生成测试是否通过。",
            ],
        })
    elif "无法连接模型服务" in message or "模型生成接口连接失败" in message:
        diagnostic.update({
            "type": "model_connection",
            "title": "模型生成接口连接失败",
            "recovery": [
                "在设置中重新点击测试模型，确认轻量生成测试是否通过。",
                "检查网络、代理或防火墙是否允许访问当前模型接口地址。",
                "确认接口地址是 OpenAI 兼容基础地址，例如 https://api.deepseek.com 或兼容服务的 /v1 地址。",
            ],
        })
    elif "请求超时" in message:
        diagnostic.update({
            "type": "model_timeout",
            "title": "模型生成接口超时",
            "recovery": [
                "稍后重试，或切换为快速分析模式降低生成耗时。",
                "检查网络代理稳定性，确认模型服务当前可用。",
            ],
        })
    elif "HTTP" in message:
        diagnostic.update({
            "type": "model_http",
            "title": "模型生成接口返回错误",
            "recovery": [
                "核对接口地址、模型名称和服务商返回的 HTTP 状态。",
                "如果使用兼容接口，确认服务端支持 /chat/completions。",
            ],
        })
    elif "返回内容为空" in message or "返回格式异常" in message:
        diagnostic.update({
            "type": "model_response",
            "title": "模型返回内容不可用",
            "recovery": [
                "重新点击测试模型，确认模型能返回普通文本。",
                "如使用兼容接口，确认返回结构包含 choices[0].message.content。",
            ],
        })
    elif "冷却" in message:
        diagnostic.update({
            "type": "cooldown",
            "title": "分析请求过于频繁",
            "impact": "本次请求未发送到模型服务，不会产生新的分析历史。",
            "recovery": ["等待提示中的剩余时间后再试，或在设置中调整分析冷却时间。"],
        })
    elif "已有风险分析正在进行" in message:
        diagnostic.update({
            "type": "busy",
            "title": "已有分析正在进行",
            "impact": "本次请求未发送到模型服务，不会产生新的分析历史。",
            "recovery": ["等待当前分析完成后再发起新的风险分析。"],
        })
    return diagnostic


def chat_completions_url(base_url):
    base_url = (base_url or "").rstrip("/")
    if base_url.endswith("/chat/completions"):
        return base_url
    return f"{base_url}/chat/completions"


def models_url(base_url):
    base_url = (base_url or "").rstrip("/")
    if base_url.endswith("/chat/completions"):
        base_url = base_url[: -len("/chat/completions")]
    return f"{base_url}/models"


class RiskModelClient:
    def __init__(
        self,
        request_client,
        default_settings,
        fallback_models=(),
        user_agent="GoldMonitor",
        request_timeout=4,
        assistant_timeout=20,
        max_tokens_default=1200,
        temperature=0.2,
        proxies=None,
        section_labels=RISK_SECTION_LABELS,
    ):
        self.request_client = request_client
        self.default_settings = default_settings
        self.fallback_models = tuple(fallback_models)
        self.user_agent = user_agent
        self.request_timeout = request_timeout
        self.assistant_timeout = assistant_timeout
        self.max_tokens_default = max_tokens_default
        self.temperature = temperature
        self.proxies = proxies
        self.section_labels = section_labels
        self.timeout_type = getattr(request_client, "Timeout", _NeverRaised)
        self.connection_error_type = getattr(request_client, "ConnectionError", _NeverRaised)
        self.http_error_type = getattr(request_client, "HTTPError", _NeverRaised)
        self.request_exception_type = getattr(request_client, "RequestException", _NeverRaised)

    def selected_model_config(self, settings, provider=None):
        provider = provider or settings.get("risk_assistant_provider", "deepseek")
        if provider == "deepseek":
            return (
                provider,
                settings.get("deepseek_base_url") or self.default_settings["deepseek_base_url"],
                settings.get("deepseek_model") or self.default_settings["deepseek_model"],
                settings.get("deepseek_api_key") or "",
            )
        if provider == "openai_compatible":
            return (
                provider,
                settings.get("openai_compatible_base_url") or "",
                settings.get("openai_compatible_model") or "",
                settings.get("openai_compatible_api_key") or "",
            )
        return provider, "", "", ""

    def fetch_model_options(self, settings, provider=None):
        provider = provider or settings.get("risk_assistant_provider", "deepseek")
        if provider == "deepseek":
            base_url = settings.get("deepseek_base_url") or self.default_settings["deepseek_base_url"]
            api_key = settings.get("deepseek_api_key") or ""
            fallback = list(self.fallback_models)
        elif provider == "openai_compatible":
            base_url = settings.get("openai_compatible_base_url") or ""
            api_key = settings.get("openai_compatible_api_key") or ""
            fallback = [settings.get("openai_compatible_model")] if settings.get("openai_compatible_model") else []
        else:
            return {"provider": provider, "models": [], "source": "unsupported", "error": "暂不支持当前模型提供商。"}

        if not base_url:
            return {"provider": provider, "models": fallback, "source": "fallback", "error": "请先配置模型接口地址。"}

        headers = {"User-Agent": self.user_agent}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            response = self.request_client.get(
                models_url(base_url),
                headers=headers,
                timeout=self.request_timeout,
                proxies=self.proxies,
            )
            response.raise_for_status()
            body = response.json()
            raw_models = body.get("data", []) if isinstance(body, dict) else []
            models = [
                str(item.get("id") or item.get("model") or "").strip()
                for item in raw_models
                if isinstance(item, dict) and str(item.get("id") or item.get("model") or "").strip()
            ]
            if models:
                return {"provider": provider, "models": models, "source": "api", "error": ""}
            return {"provider": provider, "models": fallback, "source": "fallback", "error": ""}
        except self.request_exception_type as exc:
            return {"provider": provider, "models": fallback, "source": "fallback", "error": f"模型列表获取失败：{exc}"}
        except (ValueError, TypeError):
            return {"provider": provider, "models": fallback, "source": "fallback", "error": "模型列表返回格式异常。"}

    def test_availability(self, settings, valid_providers=None):
        valid_providers = valid_providers or {"deepseek", "openai_compatible"}
        provider, _base_url, model, _api_key = self.selected_model_config(settings)
        if provider not in valid_providers:
            return {"ok": False, "provider": provider, "model": model, "message": "当前模型提供商暂不支持。"}
        provider, base_url, model, api_key = self.selected_model_config(settings)
        if not base_url:
            return {"ok": False, "provider": provider, "model": model, "message": "请先配置模型接口地址。"}
        if not model:
            return {"ok": False, "provider": provider, "model": model, "message": "请先选择或填写模型。"}
        if not api_key:
            return {"ok": False, "provider": provider, "model": model, "message": "请先配置当前模型提供商的 API Key。"}

        options = self.fetch_model_options(settings, provider)
        models = options.get("models", [])
        if options.get("source") == "api" and model in models:
            chat_result = self.test_chat_completion(settings, provider, base_url, model, api_key)
            chat_result["models"] = models
            return chat_result
        if options.get("source") == "api" and models:
            return {
                "ok": False,
                "provider": provider,
                "model": model,
                "models": models,
                "message": f"接口可访问，但模型列表未包含 {model}。",
            }
        chat_result = self.test_chat_completion(settings, provider, base_url, model, api_key)
        chat_result["models"] = models
        if chat_result.get("ok") and options.get("error"):
            chat_result["message"] = f"{chat_result['message']} 模型列表未确认：{options.get('error')}"
        return chat_result

    def build_messages(self, context):
        return build_messages(context)

    def build_chat_payload(self, settings, context, provider, model, messages=None, max_tokens=None):
        if max_tokens is None:
            max_tokens = settings.get("risk_assistant_max_tokens", self.max_tokens_default)
            depth = context.get("analysis_depth", "standard")
            if depth == "quick":
                max_tokens = min(max_tokens, 900)
            elif depth == "deep":
                max_tokens = max(max_tokens, 1800)
        payload = {
            "model": model,
            "messages": messages or self.build_messages(context),
            "temperature": self.temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if provider == "deepseek" and model == "deepseek-v4-pro":
            payload["thinking"] = {"type": "enabled"}
            payload["reasoning_effort"] = "medium"
        return payload

    def test_chat_completion(self, settings, provider, base_url, model, api_key):
        payload = self.build_chat_payload(
            settings,
            {"analysis_depth": "quick"},
            provider,
            model,
            messages=build_model_test_messages(),
            max_tokens=300,
        )
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": self.user_agent,
        }
        try:
            response = self.request_client.post(
                chat_completions_url(base_url),
                headers=headers,
                json=payload,
                timeout=self.assistant_timeout,
                proxies=self.proxies,
            )
            if response.status_code in (401, 403):
                return {"ok": False, "provider": provider, "model": model, "message": "模型服务认证失败，请检查 API Key。"}
            response.raise_for_status()
            body = response.json()
            choices = body.get("choices") if isinstance(body, dict) else None
            message = choices[0].get("message") if choices and isinstance(choices[0], dict) else {}
            content = str(message.get("content") or "").strip()
            if not content:
                return {"ok": False, "provider": provider, "model": model, "message": "模型生成接口返回内容为空。"}
            return {"ok": True, "provider": provider, "model": model, "message": f"模型生成测试正常，接口已返回 {model}。"}
        except self.timeout_type:
            return {"ok": False, "provider": provider, "model": model, "message": "模型生成接口请求超时，请稍后重试。"}
        except self.connection_error_type:
            return {"ok": False, "provider": provider, "model": model, "message": "模型生成接口连接失败，请检查网络、代理或接口地址。"}
        except self.http_error_type as exc:
            status = getattr(exc.response, "status_code", "")
            return {"ok": False, "provider": provider, "model": model, "message": f"模型生成接口请求失败：HTTP {status}"}
        except self.request_exception_type as exc:
            return {"ok": False, "provider": provider, "model": model, "message": f"模型生成接口请求失败：{exc}"}
        except (ValueError, KeyError, TypeError):
            return {"ok": False, "provider": provider, "model": model, "message": "模型生成接口返回格式异常。"}

    def call_chat_completion(self, settings, context, provider, base_url, model, api_key):
        if not api_key:
            return None, "请先配置当前模型提供商的 API Key。"
        if not base_url:
            return None, "请先配置当前模型提供商的接口地址。"
        if not model:
            return None, "请先选择或填写模型。"

        payload = self.build_chat_payload(settings, context, provider, model)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": self.user_agent,
        }
        try:
            response = self.request_client.post(
                chat_completions_url(base_url),
                headers=headers,
                json=payload,
                timeout=self.assistant_timeout,
                proxies=self.proxies,
            )
            if response.status_code in (401, 403):
                return None, "模型服务认证失败，请检查 API Key。"
            response.raise_for_status()
            body = response.json()
            choices = body.get("choices") if isinstance(body, dict) else None
            if not choices:
                return None, "模型服务返回内容为空。"
            message = choices[0].get("message") if isinstance(choices[0], dict) else {}
            content = str(message.get("content") or "").strip()
            if not content:
                return None, "模型服务返回内容为空。"
            return {
                "provider": provider,
                "model": model,
                "content": content,
                "structured": parse_sections(content, self.section_labels),
                "usage": body.get("usage") if isinstance(body, dict) else None,
            }, None
        except self.timeout_type:
            return None, "模型服务请求超时，请稍后重试。"
        except self.connection_error_type:
            return None, "无法连接模型服务，请检查网络。"
        except self.http_error_type as exc:
            status = getattr(exc.response, "status_code", "")
            return None, f"模型服务请求失败：HTTP {status}"
        except self.request_exception_type as exc:
            return None, f"模型服务请求失败：{exc}"
        except (ValueError, KeyError, TypeError):
            return None, "模型服务返回格式异常。"

    def call_deepseek(self, settings, context):
        return self.call_chat_completion(
            settings,
            context,
            "deepseek",
            settings.get("deepseek_base_url") or self.default_settings["deepseek_base_url"],
            settings.get("deepseek_model") or self.default_settings["deepseek_model"],
            settings.get("deepseek_api_key") or "",
        )

    def call_openai_compatible(self, settings, context):
        return self.call_chat_completion(
            settings,
            context,
            "openai_compatible",
            settings.get("openai_compatible_base_url") or "",
            settings.get("openai_compatible_model") or "",
            settings.get("openai_compatible_api_key") or "",
        )

    def run(self, settings, context):
        provider = settings.get("risk_assistant_provider", "deepseek")
        if provider == "deepseek":
            return self.call_deepseek(settings, context)
        if provider == "openai_compatible":
            return self.call_openai_compatible(settings, context)
        return None, "暂不支持当前风险分析模型提供商。"
