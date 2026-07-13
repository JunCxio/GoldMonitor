import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional

import requests


class _NeverRaised(Exception):
    pass


def _exception_type(requests_module, name):
    exception_type = getattr(requests_module, name, None)
    if exception_type is None:
        exception_type = getattr(getattr(requests_module, "exceptions", None), name, None)
    return exception_type if isinstance(exception_type, type) else _NeverRaised


def _source_message(source_label, message):
    label = str(source_label or "数据源").strip() or "数据源"
    separator = " " if label[-1].isascii() and label[-1].isalnum() else ""
    return f"{label}{separator}{message}"


@dataclass(frozen=True)
class AdapterFetchResult:
    value: Any = None
    auxiliary_rate: Optional[float] = None
    error: str = ""
    started_at: Optional[float] = None

    def __post_init__(self):
        object.__setattr__(self, "error", str(self.error or ""))

    @property
    def ok(self):
        return self.value is not None and not self.error


def _normalize_fetch_output(output, started_at, source_label):
    if isinstance(output, AdapterFetchResult):
        if output.started_at is not None:
            return output
        return AdapterFetchResult(
            value=output.value,
            auxiliary_rate=output.auxiliary_rate,
            error=output.error,
            started_at=started_at,
        )
    if isinstance(output, (tuple, list)) and len(output) == 2:
        value, error = output
        return AdapterFetchResult(value=value, error=error, started_at=started_at)
    if isinstance(output, (tuple, list)) and len(output) == 3:
        value, auxiliary_rate, error = output
        return AdapterFetchResult(
            value=value,
            auxiliary_rate=auxiliary_rate,
            error=error,
            started_at=started_at,
        )
    return AdapterFetchResult(
        error=_source_message(source_label, "返回格式异常"),
        started_at=started_at,
    )


@dataclass(frozen=True)
class MarketSourceAdapter:
    key: str
    name: str
    category: str
    priority: int
    cache_source: str
    provides_forex_rate: bool
    fetcher: Callable[..., Any] = field(repr=False, compare=False)

    def __post_init__(self):
        for field_name in ("key", "name", "category", "cache_source"):
            value = str(getattr(self, field_name) or "").strip()
            if not value:
                raise ValueError(f"market adapter {field_name} must not be empty")
            object.__setattr__(self, field_name, value)
        try:
            priority = int(self.priority)
        except (TypeError, ValueError) as exc:
            raise ValueError("market adapter priority must be an integer") from exc
        object.__setattr__(self, "priority", priority)
        object.__setattr__(self, "provides_forex_rate", bool(self.provides_forex_rate))
        if not callable(self.fetcher):
            raise ValueError("market adapter fetcher must be callable")

    def fetch(self, *args, monotonic=None, **kwargs):
        clock = monotonic or time.monotonic
        started_at = clock()
        try:
            output = self.fetcher(*args, **kwargs)
        except Exception as exc:
            return AdapterFetchResult(
                error=_source_message(self.name, f"获取失败: {exc}"),
                started_at=started_at,
            )
        return _normalize_fetch_output(output, started_at, self.name)

    def descriptor(self):
        return {
            "key": self.key,
            "name": self.name,
            "category": self.category,
            "priority": self.priority,
            "cache_source": self.cache_source,
            "provides_forex_rate": self.provides_forex_rate,
        }


class MarketAdapterRegistry:
    def __init__(self, adapters: Iterable[MarketSourceAdapter] = ()):
        self._entries = []
        self._by_key = {}
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter):
        if not isinstance(adapter, MarketSourceAdapter):
            raise TypeError("adapter must be a MarketSourceAdapter")
        if adapter.key in self._by_key:
            raise ValueError(f"duplicate market adapter key: {adapter.key}")
        entry = (len(self._entries), adapter)
        self._entries.append(entry)
        self._by_key[adapter.key] = adapter
        return adapter

    def get(self, key):
        return self._by_key.get(str(key or "").strip())

    def category_adapters(self, category):
        category = str(category or "").strip()
        entries = [entry for entry in self._entries if entry[1].category == category]
        entries.sort(key=lambda entry: (entry[1].priority, entry[0]))
        return [adapter for _index, adapter in entries]

    def catalog(self, category=None):
        if category is None:
            entries = sorted(self._entries, key=lambda entry: (entry[1].priority, entry[0]))
            adapters = [adapter for _index, adapter in entries]
        else:
            adapters = self.category_adapters(category)
        return [adapter.descriptor() for adapter in adapters]


def fetch_http_source(
    url,
    source_label,
    parser,
    response_type="text",
    *,
    headers=None,
    timeout=10,
    proxies=None,
    requests_module=None,
    monotonic=None,
):
    requests_module = requests_module or requests
    clock = monotonic or time.monotonic
    started_at = clock()
    timeout_type = _exception_type(requests_module, "Timeout")
    connection_type = _exception_type(requests_module, "ConnectionError")
    http_type = _exception_type(requests_module, "HTTPError")
    request_type = _exception_type(requests_module, "RequestException")

    try:
        response = requests_module.get(
            url,
            headers=headers,
            timeout=timeout,
            proxies=proxies,
        )
        response.raise_for_status()
        normalized_type = str(response_type or "text").strip().lower()
        if normalized_type == "text":
            payload = response.text
        elif normalized_type == "json":
            payload = response.json()
        else:
            raise ValueError("unsupported response type")
        return _normalize_fetch_output(parser(payload), started_at, source_label)
    except timeout_type:
        error = _source_message(source_label, "请求超时")
    except connection_type:
        error = _source_message(source_label, "网络连接失败")
    except http_type as exc:
        response = getattr(exc, "response", None)
        code = getattr(response, "status_code", "未知") if response is not None else "未知"
        error = _source_message(source_label, f"HTTP错误 {code}")
    except (json.JSONDecodeError, ValueError, TypeError, IndexError):
        error = _source_message(source_label, "返回格式异常")
    except request_type as exc:
        error = _source_message(source_label, f"请求失败: {exc}")
    return AdapterFetchResult(error=error, started_at=started_at)
