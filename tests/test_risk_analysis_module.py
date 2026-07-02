import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class FakeRequestException(Exception):
    pass


class FakeTimeout(FakeRequestException):
    pass


class FakeConnectionError(FakeRequestException):
    pass


class FakeHTTPError(FakeRequestException):
    def __init__(self, response=None):
        super().__init__("http error")
        self.response = response


class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise FakeHTTPError(self)

    def json(self):
        return self._body


class FakeRequests:
    RequestException = FakeRequestException
    Timeout = FakeTimeout
    ConnectionError = FakeConnectionError
    HTTPError = FakeHTTPError

    def __init__(self):
        self.get_calls = []
        self.post_calls = []
        self.next_post_exception = None
        self.next_models_response = FakeResponse(body={"data": [{"id": "deepseek-v4-pro"}, {"model": "deepseek-chat"}]})
        self.next_chat_response = FakeResponse(body={
            "choices": [{
                "message": {
                    "content": (
                        "风险等级：中等\n"
                        "趋势方向：震荡偏强\n"
                        "数据可信度：较高\n"
                        "主要影响因素：美元指数与通胀预期\n"
                        "观察价格区间：2320-2360\n"
                        "后续关注：FOMC 表态"
                    )
                }
            }],
            "usage": {"total_tokens": 128},
        })

    def get(self, *args, **kwargs):
        self.get_calls.append({"args": args, "kwargs": kwargs})
        return self.next_models_response

    def post(self, *args, **kwargs):
        self.post_calls.append({"args": args, "kwargs": kwargs})
        if self.next_post_exception:
            raise self.next_post_exception
        return self.next_chat_response


def fixed_now():
    return datetime(2026, 6, 8, 12, 0, 0)


def test_risk_history_store_persists_versioned_payload_and_clears():
    from goldmonitor.risk_analysis import RiskAnalysisHistoryStore

    with tempfile.TemporaryDirectory() as tmp_dir:
        path = str(Path(tmp_dir) / "risk_analysis_history.json")
        store = RiskAnalysisHistoryStore(path, history_limit=2, now_factory=fixed_now)
        snapshot = {
            "analysis_time": "2026-06-08T11:59:00",
            "price_rmb": 542.1,
            "evidence_summary": {
                "quality_score": 72,
                "quality_label": "样本有限",
                "history_points": 18,
                "kline_points": 4,
                "missing": ["近期资讯为空"],
            },
        }
        result = {
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "content": " 风险等级：中等 ",
            "structured": {"risk_level": "中等"},
            "usage": {"total_tokens": 128},
        }

        history, entry = store.add_entry([], result, snapshot)
        assert entry["id"] == "2026-06-08T12:00:00"
        assert entry["analysis_time"] == "2026-06-08T11:59:00"
        assert entry["content"] == "风险等级：中等"
        assert entry["evidence_summary"]["quality_score"] == 72
        assert entry["evidence_summary"]["missing"] == ["近期资讯为空"]
        assert history == [entry]

        saved = store.save(history + [
            {"content": "第二条", "analysis_time": "2026-06-08T11:58:00"},
            {"content": "第三条", "analysis_time": "2026-06-08T11:57:00"},
            {"content": ""},
        ])
        assert [item["content"] for item in saved] == ["风险等级：中等", "第二条"]

        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        assert payload["schema_version"] == 1
        assert len(payload["items"]) == 2
        assert store.load() == saved

        Path(path).write_text(json.dumps([{"content": "legacy", "analysis_time": "2026-06-08T11:56:00"}], ensure_ascii=False), encoding="utf-8")
        assert store.load()[0]["content"] == "legacy"

        assert store.clear() == []
        assert store.load() == []


def test_risk_snapshot_sections_and_cache_are_stable():
    from goldmonitor.risk_analysis import (
        build_cache_key,
        build_snapshot,
        find_recent_cache,
        parse_sections,
    )

    context = {
        "analysis_time": "2026-06-08T12:00:00",
        "analysis_depth": "standard",
        "market": {
            "price_usd": 2350.2,
            "price_rmb": 542.3,
            "usdcny_rate": 7.19,
            "gold_source": "stooq",
            "gold_time": "2026-06-08T11:59:00",
            "gold_cached": True,
            "gold_error": "",
            "rate_source": "frankfurter",
            "rate_time": "2026-06-08T11:58:00",
            "rate_cached": False,
            "rate_error": "",
        },
        "daily": {"pct_usd": 0.25, "pct_rmb": 0.3},
        "history_summary": {"usd": {"points": 24}},
        "kline_summary": {"usd": {"points": 6}},
        "news": [{"title": "Gold holds near highs"}],
        "sample_warning": "",
        "data_quality": {"score": 90},
        "market_quality": {"level": "stale", "score": 60, "label": "使用缓存", "reasons": ["正在使用缓存行情"]},
        "multi_period_trends": [{"minutes": 15, "direction": "up"}],
        "risk_scorecard": {"overall_risk": 42},
        "manual_trigger": {"source": "manual"},
    }
    snapshot = build_snapshot(context)
    assert snapshot["history_points"] == 24
    assert snapshot["news_count"] == 1
    assert snapshot["gold_cached"] is True
    assert snapshot["rate_cached"] is False
    assert snapshot["market_quality"]["level"] == "stale"
    assert snapshot["risk_scorecard"] == {"overall_risk": 42}
    assert snapshot["evidence_summary"]["gold_source"] == "stooq"
    assert snapshot["evidence_summary"]["gold_cached"] is True
    assert snapshot["evidence_summary"]["history_points"] == 24
    assert snapshot["evidence_summary"]["kline_points"] == 6
    assert snapshot["evidence_summary"]["quality_score"] == 60
    assert snapshot["evidence_summary"]["missing"] == []

    structured = parse_sections("风险等级：中等\n补充说明\n趋势方向: 震荡偏强")
    assert structured["risk_level"] == "中等\n补充说明"
    assert structured["trend_direction"] == "震荡偏强"

    same_market = dict(snapshot)
    same_market["analysis_time"] = "2026-06-08T12:05:00"
    assert build_cache_key(snapshot) == build_cache_key(same_market)
    changed_quality = dict(snapshot)
    changed_quality["market_quality"] = {"level": "anomaly", "score": 50, "label": "价差异常"}
    assert build_cache_key(snapshot) != build_cache_key(changed_quality)

    cached = find_recent_cache(
        [{"analysis_time": "2026-06-08T11:58:30", "snapshot": same_market, "content": "cached"}],
        snapshot,
        cache_minutes=3,
        now=datetime(2026, 6, 8, 12, 0, 0),
    )
    assert cached["cache_age_seconds"] == 90
    assert cached["content"] == "cached"
    assert find_recent_cache([cached], snapshot, cache_minutes=1, now=datetime(2026, 6, 8, 12, 0, 0)) is None


def test_risk_model_client_fetches_models_and_builds_chat_payload():
    from goldmonitor.risk_analysis import RiskModelClient

    fake_requests = FakeRequests()
    client = RiskModelClient(
        request_client=fake_requests,
        default_settings={
            "deepseek_base_url": "https://api.deepseek.com",
            "deepseek_model": "deepseek-v4-pro",
        },
        fallback_models=("deepseek-v4-pro", "deepseek-chat"),
        user_agent="GoldMonitor/test",
        request_timeout=4,
        assistant_timeout=20,
        max_tokens_default=1200,
        temperature=0.2,
        proxies={"http": None, "https": None},
    )
    settings = {
        "risk_assistant_provider": "deepseek",
        "deepseek_base_url": "https://api.deepseek.com/chat/completions",
        "deepseek_model": "deepseek-v4-pro",
        "deepseek_api_key": "sk-risk-secret",
        "risk_assistant_max_tokens": 1500,
    }

    options = client.fetch_model_options(settings, "deepseek")
    assert options["source"] == "api"
    assert "deepseek-v4-pro" in options["models"]
    assert fake_requests.get_calls[0]["args"][0] == "https://api.deepseek.com/models"
    assert fake_requests.get_calls[0]["kwargs"]["headers"]["Authorization"] == "Bearer sk-risk-secret"

    result, error = client.call_deepseek(settings, {"analysis_depth": "quick", "market": {"price_rmb": 542.3}})
    assert error is None
    assert result["provider"] == "deepseek"
    assert result["structured"]["trend_direction"] == "震荡偏强"
    payload = fake_requests.post_calls[0]["kwargs"]["json"]
    assert payload["model"] == "deepseek-v4-pro"
    assert payload["max_tokens"] == 900
    assert payload["thinking"] == {"type": "enabled"}
    assert fake_requests.post_calls[0]["args"][0] == "https://api.deepseek.com/chat/completions"


def test_risk_model_test_checks_chat_completion_not_only_model_list():
    from goldmonitor.risk_analysis import RiskModelClient

    fake_requests = FakeRequests()
    fake_requests.next_post_exception = FakeConnectionError("chat endpoint refused")
    client = RiskModelClient(
        request_client=fake_requests,
        default_settings={
            "deepseek_base_url": "https://api.deepseek.com",
            "deepseek_model": "deepseek-v4-pro",
        },
        fallback_models=("deepseek-v4-pro", "deepseek-chat"),
        user_agent="GoldMonitor/test",
        request_timeout=4,
        assistant_timeout=20,
        max_tokens_default=1200,
        temperature=0.2,
        proxies={"http": None, "https": None},
    )
    settings = {
        "risk_assistant_provider": "deepseek",
        "deepseek_base_url": "https://api.deepseek.com",
        "deepseek_model": "deepseek-v4-pro",
        "deepseek_api_key": "sk-risk-secret",
        "risk_assistant_max_tokens": 1200,
    }

    diagnostic = client.test_availability(settings)

    assert diagnostic["ok"] is False
    assert "模型生成接口连接失败" in diagnostic["message"]
    assert fake_requests.get_calls
    assert fake_requests.post_calls


def test_risk_error_diagnostic_explains_model_connection_recovery():
    from goldmonitor.risk_analysis import build_error_diagnostic

    diagnostic = build_error_diagnostic(
        "无法连接模型服务，请检查网络。",
        settings={
            "risk_assistant_provider": "deepseek",
            "deepseek_model": "deepseek-v4-pro",
        },
    )

    assert diagnostic["type"] == "model_connection"
    assert diagnostic["title"] == "模型生成接口连接失败"
    assert diagnostic["provider"] == "deepseek"
    assert diagnostic["model"] == "deepseek-v4-pro"
    assert "风险分析未生成" in diagnostic["impact"]
    assert any("代理" in item or "网络" in item for item in diagnostic["recovery"])
    assert any("测试模型" in item for item in diagnostic["recovery"])


if __name__ == "__main__":
    failures = []
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            try:
                value()
            except Exception as exc:
                failures.append((name, exc))
    if failures:
        for name, exc in failures:
            print(f"{name}: {type(exc).__name__}: {exc}")
        raise SystemExit(1)
    print("risk analysis module checks passed.")
