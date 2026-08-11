import threading
from datetime import datetime
from types import SimpleNamespace


def _state():
    return SimpleNamespace(
        lock=threading.RLock(),
        risk_history_lock=threading.RLock(),
        risk_analysis_history=[],
        risk_analysis_last_started=0.0,
        price_archive=[],
        price_history=[],
        klines_5min=[],
        news_items=[],
        price_usd=2350.0,
        price_rmb=540.0,
        previous_usd=2348.0,
        previous_rmb=539.5,
        usdcny_rate=7.2,
        gold_price_source="测试金价源",
        gold_price_time="2026-08-11T11:58:00",
        gold_price_cached=False,
        gold_price_error="",
        usdcny_rate_source="测试汇率源",
        usdcny_rate_time="2026-08-11T11:58:00",
        usdcny_rate_cached=False,
        usdcny_rate_error="",
        last_fetch_ok=True,
        last_fetch_error="",
        last_fetch_time="2026-08-11T11:58:00",
        today_date="2026-08-11",
        today_open_usd=2340.0,
        today_high_usd=2355.0,
        today_low_usd=2338.0,
        today_open_rmb=538.0,
        today_high_rmb=541.0,
        today_low_rmb=537.0,
    )


def _runtime(state=None, **overrides):
    from goldmonitor.risk_analysis_runtime import RiskAnalysisRuntime

    state = state or _state()
    options = {
        "get_settings": lambda: {"risk_assistant_depth": "standard"},
        "get_source_health": lambda: {
            "quality": {"score": 95, "label": "数据可信"},
        },
        "request_client": lambda: SimpleNamespace(),
        "default_settings": {
            "deepseek_base_url": "https://api.deepseek.com",
            "deepseek_model": "deepseek-chat",
        },
        "fallback_models": ("deepseek-chat",),
        "user_agent": "GoldMonitor/test",
        "request_timeout": 4,
        "assistant_timeout": 20,
        "max_tokens_default": 1200,
        "temperature": 0.2,
        "proxies": {"http": None, "https": None},
        "section_labels": (
            ("risk_level", "风险等级"),
            ("trend_direction", "趋势方向"),
        ),
        "valid_providers": {"deepseek", "openai_compatible"},
        "valid_depths": {"quick", "standard", "deep"},
        "trend_periods": (5, 15),
        "news_limit": 5,
        "now_factory": lambda: datetime(2026, 8, 11, 12, 0, 0),
    }
    options.update(overrides)
    return RiskAnalysisRuntime(state, **options)


def test_risk_analysis_runtime_builds_context_snapshot_and_diagnostic():
    runtime = _runtime()

    context = runtime.build_context(
        {"source": "manual", "message": "测试触发"},
        "standard",
    )
    snapshot = runtime.build_snapshot(context)
    error = runtime.build_error_payload(
        "无法连接模型服务，请检查网络。",
        {
            "risk_assistant_provider": "deepseek",
            "deepseek_model": "deepseek-chat",
        },
        snapshot,
    )

    assert runtime.market_data_error() == ""
    assert context["market"]["price_usd"] == 2350.0
    assert context["manual_trigger"]["message"] == "测试触发"
    assert snapshot["market_quality"]["score"] == 95
    assert error["diagnostic"]["type"] == "model_connection"
    assert error["snapshot"] == snapshot


def test_risk_analysis_runtime_owns_cache_and_last_started_state():
    state = _state()
    runtime = _runtime(state)
    snapshot = {"analysis_depth": "standard", "price_usd": 2350.0}
    state.risk_analysis_history = [{
        "analysis_time": "2026-08-11T11:59:00",
        "snapshot": dict(snapshot),
        "content": "缓存分析",
    }]

    cached = runtime.find_recent_cache(snapshot, 5)
    runtime.set_last_started(123.5)

    assert cached["content"] == "缓存分析"
    assert cached["cache_age_seconds"] == 60
    assert runtime.get_last_started() == 123.5


def test_risk_analysis_runtime_delegates_model_operations():
    calls = []
    client = SimpleNamespace(
        selected_model_config=(
            lambda settings, provider=None: (provider, "url", "model", "key")
        ),
        test_availability=lambda settings, providers: {
            "ok": True,
            "providers": providers,
        },
        fetch_model_options=lambda settings, provider=None: {
            "provider": provider,
            "models": ["model"],
        },
        call_deepseek=lambda settings, context: (calls.append("deepseek") or ({
            "provider": "deepseek",
        }, None)),
        call_openai_compatible=(
            lambda settings, context: (calls.append("compatible") or ({
                "provider": "openai_compatible",
            }, None))
        ),
        call_chat_completion=lambda *args: (calls.append("chat") or ({}, None)),
        run=lambda settings, context: (calls.append("run") or ({"ok": True}, None)),
    )
    runtime = _runtime()
    runtime.model_client = lambda: client

    assert runtime.selected_model_config({}, "deepseek")[0] == "deepseek"
    assert runtime.test_model_availability({})["ok"] is True
    assert runtime.fetch_model_options({}, "deepseek")["models"] == ["model"]
    runtime.call_chat_completion({}, {}, "deepseek", "url", "model", "key")
    runtime.call_deepseek({}, {})
    runtime.call_openai_compatible({}, {})
    runtime.run({}, {})

    assert calls == ["chat", "deepseek", "compatible", "run"]
