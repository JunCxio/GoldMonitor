import json
import time
from dataclasses import dataclass, field, replace
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


def source_preference_defaults(registry):
    if not isinstance(registry, MarketAdapterRegistry):
        raise TypeError("registry must be a MarketAdapterRegistry")
    categories = []
    for descriptor in registry.catalog():
        category = descriptor["category"]
        if category not in categories:
            categories.append(category)
    return {
        category: [item["key"] for item in registry.catalog(category)]
        for category in categories
    }


def normalize_source_preferences(enabled, order, defaults, strict=False):
    defaults = defaults if isinstance(defaults, dict) else {}
    normalized_defaults = {
        str(category): [str(key) for key in keys if str(key)]
        for category, keys in defaults.items()
        if isinstance(keys, (list, tuple))
    }
    if strict:
        if enabled is not None and not isinstance(enabled, dict):
            raise ValueError("数据源启用配置格式无效")
        if order is not None and not isinstance(order, dict):
            raise ValueError("数据源排序配置格式无效")
        unknown_categories = (
            set(enabled or {}) | set(order or {})
        ) - set(normalized_defaults)
        if unknown_categories:
            raise ValueError("包含未知的数据源分类")

    enabled = enabled if isinstance(enabled, dict) else {}
    order = order if isinstance(order, dict) else {}
    normalized_order = {}
    normalized_enabled = {}
    category_labels = {"gold": "金价", "forex": "汇率"}

    for category, default_keys in normalized_defaults.items():
        known = set(default_keys)
        raw_order = order.get(category)
        if raw_order is not None and not isinstance(raw_order, (list, tuple)):
            if strict:
                raise ValueError(f"{category_labels.get(category, category)}数据源排序格式无效")
            raw_order = []
        ordered = []
        for raw_key in raw_order or []:
            key = str(raw_key or "").strip()
            if key not in known:
                if strict:
                    raise ValueError(f"包含未知的{category_labels.get(category, category)}数据源")
                continue
            if key not in ordered:
                ordered.append(key)
        ordered.extend(key for key in default_keys if key not in ordered)
        normalized_order[category] = ordered

        if category in enabled:
            raw_enabled = enabled.get(category)
            if not isinstance(raw_enabled, (list, tuple)):
                if strict:
                    raise ValueError(f"{category_labels.get(category, category)}数据源启用配置格式无效")
                raw_enabled = []
            enabled_keys = []
            for raw_key in raw_enabled:
                key = str(raw_key or "").strip()
                if key not in known:
                    if strict:
                        raise ValueError(f"包含未知的{category_labels.get(category, category)}数据源")
                    continue
                if key not in enabled_keys:
                    enabled_keys.append(key)
        else:
            enabled_keys = list(default_keys)

        if not enabled_keys:
            if strict:
                raise ValueError(f"{category_labels.get(category, category)}数据源至少启用一个")
            enabled_keys = list(default_keys)
        normalized_enabled[category] = [key for key in ordered if key in enabled_keys]

    return {
        "enabled": normalized_enabled,
        "order": normalized_order,
    }


def configure_registry(registry, enabled=None, order=None, strict=False):
    defaults = source_preference_defaults(registry)
    preferences = normalize_source_preferences(enabled, order, defaults, strict=strict)
    configured = []
    for category, ordered_keys in preferences["order"].items():
        enabled_keys = set(preferences["enabled"].get(category) or [])
        for index, key in enumerate(ordered_keys):
            adapter = registry.get(key)
            if adapter is None or key not in enabled_keys:
                continue
            configured.append(replace(adapter, priority=(index + 1) * 10))
    return MarketAdapterRegistry(configured), preferences


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
