import math
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from goldmonitor.market_observation import gold_market_is_open
from goldmonitor.time_utils import to_local_naive


CUSTOM_KEY = re.compile(r"custom_[0-9a-f]{32}\Z")
FIELD_PATH = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*\Z")


def normalize_custom_sources(raw, strict=False):
    if not isinstance(raw, list):
        if strict:
            raise ValueError("自定义数据源格式无效")
        return []
    if len(raw) > 10:
        if strict:
            raise ValueError("自定义数据源最多配置 10 个")
        raw = raw[:10]
    result = []
    seen = set()
    for item in raw:
        try:
            if not isinstance(item, dict):
                raise ValueError("自定义数据源格式无效")
            source = {field: str(item.get(field) or "").strip() for field in (
                "key", "name", "url", "price_path", "time_path"
            )}
            url = urlsplit(source["url"])
            if not CUSTOM_KEY.fullmatch(source["key"]) or source["key"] in seen:
                raise ValueError("自定义数据源标识无效")
            if not source["name"] or len(source["name"]) > 40:
                raise ValueError("数据源名称须为 1 至 40 个字符")
            if (url.scheme != "https" or not url.hostname or url.username or url.password
                    or url.fragment or len(source["url"]) > 2048):
                raise ValueError("数据源地址须为有效的 HTTPS 地址")
            if not FIELD_PATH.fullmatch(source["price_path"]):
                raise ValueError("金价字段路径无效")
            if not FIELD_PATH.fullmatch(source["time_path"]):
                raise ValueError("报价时间字段路径无效")
            if source["name"] in seen:
                raise ValueError("数据源名称重复")
            result.append(source)
            seen.update((source["key"], source["name"]))
        except (ValueError, TypeError) as exc:
            if strict:
                raise ValueError(str(exc)) from exc
    return result


def _field(payload, path):
    value = payload
    for part in path.split("."):
        if isinstance(value, dict):
            value = value[part]
        elif isinstance(value, list) and part.isdigit():
            value = value[int(part)]
        else:
            raise KeyError(part)
    return value


def parse_custom_gold(payload, source, now=None):
    name = source["name"]
    try:
        raw_price = _field(payload, source["price_path"])
        if isinstance(raw_price, bool):
            raise ValueError("invalid price")
        price = float(raw_price)
        raw_time = _field(payload, source["time_path"])
        if ((isinstance(raw_time, (int, float)) and not isinstance(raw_time, bool))
                or (isinstance(raw_time, str) and raw_time.isdigit())):
            seconds = float(raw_time)
            quoted_at = datetime.fromtimestamp(
                seconds / 1000 if seconds > 10**11 else seconds,
                tz=timezone.utc,
            ).astimezone().replace(tzinfo=None)
        else:
            quoted_at = to_local_naive(raw_time)
    except (KeyError, IndexError, TypeError, ValueError, OverflowError, OSError):
        return None, f"{name}返回字段或报价时间无效"
    if not math.isfinite(price) or price <= 0 or quoted_at is None:
        return None, f"{name}返回无效金价或报价时间"
    now = to_local_naive(now or datetime.now())
    age_seconds = (now - quoted_at).total_seconds()
    if age_seconds < -60:
        return None, f"{name}行情时间异常"
    if gold_market_is_open(now) and age_seconds > 300:
        return None, f"{name}行情已过期"
    return {
        "date": quoted_at.strftime("%Y-%m-%d"),
        "time": quoted_at.strftime("%H:%M:%S"),
        "timestamp": quoted_at.isoformat(timespec="seconds"),
        "open": price,
        "high": price,
        "low": price,
        "close": price,
    }, ""
