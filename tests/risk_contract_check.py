import json
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


def authorized_client():
    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    if not client.is_connected():
        raise SystemExit("authorized socket client must connect")
    client.get_received()
    return client


def assert_event(received, name):
    if name not in [event.get("name") for event in received]:
        raise SystemExit(f"expected socket event {name}, got {received}")


def find_event(received, name):
    for event in received:
        if event.get("name") == name:
            args = event.get("args") or []
            return args[0] if args else {}
    return None


def wait_for_event(client, name, timeout=2):
    deadline = time.time() + timeout
    seen = []
    while time.time() < deadline:
        received = client.get_received()
        seen.extend(received)
        event = find_event(received, name)
        if event is not None:
            return event
        time.sleep(0.05)
    raise SystemExit(f"expected socket event {name}, got {seen}")


def collect_events(client, duration=0.3):
    deadline = time.time() + duration
    events = []
    while time.time() < deadline:
        events.extend(client.get_received())
        time.sleep(0.05)
    return events


with tempfile.TemporaryDirectory() as tmp_dir:
    original_thresholds_path = app.THRESHOLDS_PATH
    original_thresholds = dict(app.thresholds)
    original_volatility_config = dict(app.volatility_config)
    app.THRESHOLDS_PATH = str(Path(tmp_dir) / "thresholds.json")
    app.thresholds.clear()
    app.thresholds.update({key: None for key in original_thresholds if "_" in key})
    app.volatility_config = {"percent": None, "minutes": 10, "enabled": False}

    client = authorized_client()
    try:
        client.emit("set_threshold", {"mode": "badmode", "type": "unexpected", "value": "123"})
        assert_event(client.get_received(), "threshold_error")
        if "unexpected_badmode" in app.thresholds:
            raise SystemExit("invalid threshold keys must not enter runtime state")
        if Path(app.THRESHOLDS_PATH).exists():
            persisted = json.loads(Path(app.THRESHOLDS_PATH).read_text(encoding="utf-8"))
            if "unexpected_badmode" in persisted:
                raise SystemExit("invalid threshold keys must not be persisted")

        client.emit("set_volatility", {"percent": "0", "minutes": "0", "enabled": True})
        assert_event(client.get_received(), "threshold_error")
        if app.volatility_config != {"percent": None, "minutes": 10, "enabled": False}:
            raise SystemExit(f"invalid volatility config changed runtime state: {app.volatility_config}")

        client.emit("set_volatility", {"percent": "1.5", "minutes": "15", "enabled": True})
        assert_event(client.get_received(), "volatility_updated")
        persisted = json.loads(Path(app.THRESHOLDS_PATH).read_text(encoding="utf-8"))
        expected_volatility = {"percent": 1.5, "minutes": 15, "enabled": True}
        if app.volatility_config != expected_volatility:
            raise SystemExit("runtime volatility config must use normalized values")
        if persisted["volatility_config"] != expected_volatility:
            raise SystemExit("persisted volatility config must match runtime values")
    finally:
        client.disconnect()
        app.THRESHOLDS_PATH = original_thresholds_path
        app.thresholds.clear()
        app.thresholds.update(original_thresholds)
        app.volatility_config = original_volatility_config


client = authorized_client()
original_get_update_status = app.get_update_status
original_download_update_installer = app.download_update_installer
original_launch_update_installer = app.launch_update_installer
captured = []
try:
    def fake_update_status():
        return {
            "state": "available",
            "current_version": app.APP_VERSION,
            "latest_version": "9.9.9",
            "url": "https://trusted.example/GoldMonitorSetup.exe",
            "notes": "",
            "sha256": "b" * 64,
        }

    def fake_download(update_info):
        captured.append(update_info)
        return "C:\\tmp\\GoldMonitorSetup.exe"

    def fake_launch(installer_path):
        captured.append({"launched": installer_path})

    app.get_update_status = fake_update_status
    app.download_update_installer = fake_download
    app.launch_update_installer = fake_launch
    client.emit("install_update", {
        "version": "99.0.0",
        "url": "https://evil.example/EvilSetup.exe",
        "sha256": "c" * 64,
    })
    received = client.get_received()
    assert_event(received, "update_status")

    if not captured or captured[0]["url"] != "https://trusted.example/GoldMonitorSetup.exe":
        raise SystemExit(f"install_update must use backend update status, got: {captured}")
finally:
    client.disconnect()
    app.get_update_status = original_get_update_status
    app.download_update_installer = original_download_update_installer
    app.launch_update_installer = original_launch_update_installer


original_settings = dict(app.app_settings)
original_smtp_ssl = app.smtplib.SMTP_SSL
original_warning = app.logging.warning
warning_event = threading.Event()
warnings = []

class FailingSMTP:
    def __init__(self, *args, **kwargs):
        pass

    def login(self, *args, **kwargs):
        raise RuntimeError("SMTP login failed")

    def quit(self):
        pass


try:
    app.app_settings = app._normalize_settings({
        "smtp_server": "smtp.example.com",
        "smtp_port": "465",
        "smtp_encryption": "ssl",
        "smtp_sender": "sender@example.com",
        "smtp_password": "secret",
        "smtp_recipient": "recipient@example.com",
    })
    app.smtplib.SMTP_SSL = FailingSMTP

    def capture_warning(message, *args, **kwargs):
        rendered = message % args if args else message
        warnings.append(rendered)
        warning_event.set()

    app.logging.warning = capture_warning
    error = app.EmailNotifier.send("warning", "测试邮件", "测试内容", timeout=1, blocking=False)
    if error is not None:
        raise SystemExit(f"non-blocking email send should queue work, got: {error}")
    if not warning_event.wait(2):
        raise SystemExit("async email failure must be logged")
    if not any("SMTP login failed" in item for item in warnings):
        raise SystemExit(f"async email failure log must include the SMTP error, got: {warnings}")
finally:
    app.app_settings = original_settings
    app.smtplib.SMTP_SSL = original_smtp_ssl
    app.logging.warning = original_warning


original_settings = dict(app.app_settings)
original_appdata_dir = app.APPDATA_DIR
original_settings_path = app.SETTINGS_PATH
original_set_startup_enabled = app.set_startup_enabled
original_post = app.requests.post
original_get = app.requests.get
original_run_risk_analysis = app.run_risk_analysis
original_risk_history = list(app.risk_analysis_history)
original_risk_history_path = app.RISK_ANALYSIS_HISTORY_PATH
original_risk_analysis_last_started = app.risk_analysis_last_started
original_history = list(app.price_history)
original_klines = list(app.klines_5min)
original_news = list(app.news_items)
original_price_state = {
    "price_usd": app.price_usd,
    "price_rmb": app.price_rmb,
    "previous_usd": app.previous_usd,
    "previous_rmb": app.previous_rmb,
    "usdcny_rate": app.usdcny_rate,
    "gold_price_source": app.gold_price_source,
    "gold_price_time": app.gold_price_time,
    "gold_price_cached": app.gold_price_cached,
    "gold_price_error": app.gold_price_error,
    "usdcny_rate_source": app.usdcny_rate_source,
    "usdcny_rate_time": app.usdcny_rate_time,
    "usdcny_rate_cached": app.usdcny_rate_cached,
    "usdcny_rate_error": app.usdcny_rate_error,
    "last_fetch_ok": app.last_fetch_ok,
    "last_fetch_error": app.last_fetch_error,
    "last_fetch_time": app.last_fetch_time,
    "today_date": app.today_date,
    "today_open_usd": app.today_open_usd,
    "today_high_usd": app.today_high_usd,
    "today_low_usd": app.today_low_usd,
    "today_open_rmb": app.today_open_rmb,
    "today_high_rmb": app.today_high_rmb,
    "today_low_rmb": app.today_low_rmb,
}


class FakeRiskResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body or {
            "choices": [{"message": {"content": "风险等级：中等\n趋势方向：震荡偏强\n数据可信度：样本有限\n主要影响因素：测试因素\n观察价格区间：关注 540-546\n后续关注：等待更多样本"}}],
            "usage": {"total_tokens": 128},
        }

    def raise_for_status(self):
        if self.status_code >= 400:
            raise app.requests.HTTPError(response=self)

    def json(self):
        return self._body


class FakeModelsResponse:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {
            "data": [
                {"id": "deepseek-v4-pro"},
                {"id": "deepseek-v4-flash"},
            ]
        }


risk_tmp = None
try:
    with tempfile.TemporaryDirectory() as tmp_dir:
        app.APPDATA_DIR = tmp_dir
        app.SETTINGS_PATH = str(Path(tmp_dir) / "settings.json")
        app.set_startup_enabled = lambda enabled: (True, None)
        secret = "sk-test-secret-123456"
        app.app_settings = app._normalize_settings({
            "risk_assistant_enabled": True,
            "risk_assistant_provider": "deepseek",
            "deepseek_base_url": "https://api.deepseek.com",
            "deepseek_model": "deepseek-chat",
            "deepseek_api_key": secret,
            "openai_compatible_api_key": "sk-compatible-secret",
        })
        public = app.public_settings_snapshot()
        if public.get("deepseek_api_key") is not None:
            raise SystemExit("public settings must not expose deepseek_api_key")
        if public.get("openai_compatible_api_key") is not None:
            raise SystemExit("public settings must not expose openai_compatible_api_key")
        if not public.get("deepseek_api_key_configured"):
            raise SystemExit("public settings must expose DeepSeek key configured state")
        if not public.get("openai_compatible_api_key_configured"):
            raise SystemExit("public settings must expose compatible key configured state")
        if secret in json.dumps(public, ensure_ascii=False):
            raise SystemExit("public settings must not include raw DeepSeek API key")
        if "sk-compatible-secret" in json.dumps(public, ensure_ascii=False):
            raise SystemExit("public settings must not include raw compatible API key")

        client = authorized_client()
        try:
            client.emit("get_settings")
            settings_event = wait_for_event(client, "settings_updated")
            rendered_settings = json.dumps(settings_event, ensure_ascii=False)
            if "deepseek_api_key" in settings_event:
                raise SystemExit("settings_updated must not include raw deepseek_api_key")
            if secret in rendered_settings:
                raise SystemExit("settings_updated must not leak raw DeepSeek API key")

            client.emit("update_settings", {"deepseek_model": "deepseek-chat", "deepseek_api_key": ""})
            wait_for_event(client, "settings_updated")
            if app.app_settings.get("deepseek_api_key") != secret:
                raise SystemExit("empty DeepSeek API key update must keep the existing key")

            client.emit("update_settings", {"deepseek_api_key": "", "deepseek_api_key_clear": True})
            wait_for_event(client, "settings_updated")
            if app.app_settings.get("deepseek_api_key"):
                raise SystemExit("deepseek_api_key_clear must clear the stored key")
        finally:
            client.disconnect()

    app.price_usd = 2350.12
    app.price_rmb = 543.21
    app.previous_usd = 2340.00
    app.previous_rmb = 540.00
    app.usdcny_rate = 7.19
    app.gold_price_source = "test-source"
    app.gold_price_time = "2026-06-08T12:00:00"
    app.gold_price_cached = False
    app.gold_price_error = ""
    app.usdcny_rate_source = "test-rate"
    app.usdcny_rate_time = "2026-06-08T12:00:00"
    app.usdcny_rate_cached = False
    app.usdcny_rate_error = ""
    app.last_fetch_ok = True
    app.last_fetch_error = ""
    app.last_fetch_time = "2026-06-08T12:00:00"
    app.today_date = "2026-06-08"
    app.today_open_usd = 2330.00
    app.today_high_usd = 2360.00
    app.today_low_usd = 2320.00
    app.today_open_rmb = 538.00
    app.today_high_rmb = 546.00
    app.today_low_rmb = 536.00
    app.price_history = [
        {"usd": 2330 + idx, "rmb": 538 + idx * 0.2, "rate": 7.19, "time": f"12:{idx:02d}", "timestamp": f"2026-06-08T12:{idx:02d}:00"}
        for idx in range(12)
    ]
    app.klines_5min = [
        {"open": 2330, "high": 2345, "low": 2328, "close": 2340, "time": "12:00", "timestamp": "2026-06-08T12:00:00"},
        {"open": 2340, "high": 2356, "low": 2339, "close": 2350, "time": "12:05", "timestamp": "2026-06-08T12:05:00"},
    ]
    app.news_items = [{"title": "Gold holds near highs", "source": "Test", "time": "2026-06-08T11:00:00", "topic": "gold", "summary": "Market watches rates."}]
    risk_tmp = tempfile.TemporaryDirectory()
    app.APPDATA_DIR = risk_tmp.name
    app.RISK_ANALYSIS_HISTORY_PATH = str(Path(risk_tmp.name) / "risk_analysis_history.json")
    app.risk_analysis_history = []
    app.risk_analysis_last_started = 0.0

    context = app.build_risk_analysis_context({
        "source": "alert",
        "time": "12:09:00",
        "type": "warning",
        "mode": "rmb",
        "message": "test alert",
    })
    context_text = json.dumps(context, ensure_ascii=False)
    for required in (
        "analysis_time",
        "price_usd",
        "price_rmb",
        "usdcny_rate",
        "history_summary",
        "kline_summary",
        "news",
        "data_quality",
        "multi_period_trends",
        "risk_scorecard",
        "manual_trigger",
    ):
        if required not in context_text:
            raise SystemExit(f"risk analysis context missing {required}")
    snapshot = app.build_risk_analysis_snapshot(context)
    for required in ("data_quality", "multi_period_trends", "risk_scorecard"):
        if required not in snapshot:
            raise SystemExit(f"risk analysis snapshot missing {required}")

    get_calls = []

    def fake_get(*args, **kwargs):
        get_calls.append({"args": args, "kwargs": kwargs})
        return FakeModelsResponse()

    app.requests.get = fake_get
    model_options = app.fetch_risk_model_options(app._normalize_settings({
        "risk_assistant_provider": "deepseek",
        "deepseek_base_url": "https://api.deepseek.com",
        "deepseek_api_key": "sk-risk-secret",
    }), "deepseek")
    if model_options.get("source") != "api" or "deepseek-v4-pro" not in model_options.get("models", []):
        raise SystemExit(f"DeepSeek model options must come from /models when available, got: {model_options}")
    if not get_calls or not str(get_calls[0]["args"][0]).endswith("/models"):
        raise SystemExit(f"DeepSeek model options must request /models, got: {get_calls}")
    diagnostic = app.test_risk_model_availability(app._normalize_settings({
        "risk_assistant_provider": "deepseek",
        "deepseek_base_url": "https://api.deepseek.com",
        "deepseek_model": "deepseek-v4-pro",
        "deepseek_api_key": "sk-risk-secret",
    }))
    if not diagnostic.get("ok"):
        raise SystemExit(f"model diagnostic must succeed when /models returns the selected model, got: {diagnostic}")

    captured_payloads = []

    def fake_post(*args, **kwargs):
        captured_payloads.append({"args": args, "kwargs": kwargs})
        return FakeRiskResponse()

    app.requests.post = fake_post
    app.app_settings = app._normalize_settings({
        "risk_assistant_enabled": True,
        "risk_assistant_provider": "deepseek",
        "deepseek_base_url": "https://api.deepseek.com",
        "deepseek_model": "deepseek-v4-pro",
        "deepseek_api_key": "sk-risk-secret",
        "risk_assistant_max_tokens": 900,
        "risk_assistant_cooldown_seconds": 0,
        "risk_assistant_cache_minutes": 10,
    })
    client = authorized_client()
    try:
        client.emit("request_risk_analysis", {})
        result = wait_for_event(client, "risk_analysis_result")
        if "震荡偏强" not in result.get("content", ""):
            raise SystemExit(f"risk analysis result missing mocked content: {result}")
        if result.get("structured", {}).get("trend_direction") != "震荡偏强":
            raise SystemExit(f"risk analysis result must include parsed structured fields, got: {result}")
        if not captured_payloads:
            raise SystemExit("manual request_risk_analysis must call DeepSeek")
        payload_text = json.dumps(captured_payloads[0]["kwargs"].get("json", {}), ensure_ascii=False)
        if "买入" in payload_text or "卖出" in payload_text or "仓位" in payload_text:
            raise SystemExit("risk analysis prompt must avoid explicit trade instruction terms")
        payload = captured_payloads[0]["kwargs"].get("json", {})
        if payload.get("model") != "deepseek-v4-pro":
            raise SystemExit(f"DeepSeek request must use selected v4 model, got: {payload}")
        if payload.get("max_tokens") != 900:
            raise SystemExit(f"risk assistant must honor max token setting, got: {payload}")
        if payload.get("thinking", {}).get("type") != "enabled":
            raise SystemExit("deepseek-v4-pro request must enable thinking mode")
        result_snapshot = result.get("snapshot", {})
        for required in ("data_quality", "multi_period_trends", "risk_scorecard"):
            if required not in result_snapshot:
                raise SystemExit(f"risk analysis result snapshot missing {required}")
        first_payload_count = len(captured_payloads)
        client.emit("request_risk_analysis", {})
        cache_hit = wait_for_event(client, "risk_analysis_cache_hit")
        if len(captured_payloads) != first_payload_count:
            raise SystemExit("same-snapshot risk analysis must use cache without another model call")
        if cache_hit.get("structured", {}).get("trend_direction") != "震荡偏强":
            raise SystemExit(f"cache hit must return structured analysis, got: {cache_hit}")
        client.emit("request_risk_analysis", {"force": True})
        wait_for_event(client, "risk_analysis_result")
        if len(captured_payloads) != first_payload_count + 1:
            raise SystemExit("forced risk analysis must bypass cache and call the model again")
        client.emit("test_risk_model")
        model_test = wait_for_event(client, "risk_model_test_result")
        if not model_test.get("ok"):
            raise SystemExit(f"test_risk_model socket event must report success, got: {model_test}")
    finally:
        client.disconnect()

    persisted_history = app.load_risk_analysis_history()
    if len(persisted_history) < 2:
        raise SystemExit(f"risk analysis result must be persisted to local history, got: {persisted_history}")
    if not app.get_risk_analysis_history_state().get("items"):
        raise SystemExit("risk analysis history state must expose saved entries")
    cleared_history = app.clear_risk_analysis_history_state()
    if cleared_history.get("items") or app.load_risk_analysis_history():
        raise SystemExit("clear_risk_analysis_history_state must remove saved history entries")

    captured_payloads.clear()
    compatible_result, compatible_error = app.call_openai_compatible_risk_analysis(app._normalize_settings({
        "risk_assistant_provider": "openai_compatible",
        "openai_compatible_base_url": "https://compatible.example/v1",
        "openai_compatible_model": "risk-model",
        "openai_compatible_api_key": "sk-compatible-secret",
    }), context)
    if compatible_error or compatible_result.get("provider") != "openai_compatible":
        raise SystemExit(f"compatible provider must use the shared OpenAI-compatible call path, got: {compatible_result}, {compatible_error}")
    if not captured_payloads or captured_payloads[-1]["kwargs"].get("json", {}).get("model") != "risk-model":
        raise SystemExit(f"compatible provider must send the configured model, got: {captured_payloads}")

    def failing_post(*args, **kwargs):
        return FakeRiskResponse(status_code=401, body={})

    app.requests.post = failing_post
    error_result, error = app.call_deepseek_risk_analysis(app.app_settings, context)
    if error_result is not None or "认证失败" not in error:
        raise SystemExit(f"DeepSeek 401 must return an auth error, got: {error_result}, {error}")

    app.app_settings = app._normalize_settings({
        "risk_assistant_enabled": True,
        "risk_assistant_provider": "deepseek",
        "deepseek_base_url": "https://api.deepseek.com",
        "deepseek_model": "deepseek-v4-pro",
        "deepseek_api_key": "sk-risk-secret",
        "risk_assistant_cooldown_seconds": 60,
    })
    app.risk_analysis_last_started = time.monotonic()
    client = authorized_client()
    try:
        client.emit("request_risk_analysis", {})
        cooldown_error = wait_for_event(client, "risk_analysis_error")
        if "冷却" not in cooldown_error.get("message", ""):
            raise SystemExit(f"repeated risk analysis must be blocked by cooldown, got: {cooldown_error}")
    finally:
        client.disconnect()

    manual_calls = []

    def capture_run(settings, context):
        manual_calls.append((settings, context))
        return {"provider": "deepseek", "model": "deepseek-chat", "content": "ok", "usage": None}, None

    app.run_risk_analysis = capture_run
    app._check_thresholds("usd", app.price_usd, "12:10:00")
    app._check_volatility("12:10:00")
    if manual_calls:
        raise SystemExit("threshold or volatility checks must not trigger risk analysis automatically")
finally:
    app.app_settings = original_settings
    app.APPDATA_DIR = original_appdata_dir
    app.SETTINGS_PATH = original_settings_path
    app.RISK_ANALYSIS_HISTORY_PATH = original_risk_history_path
    app.set_startup_enabled = original_set_startup_enabled
    app.requests.post = original_post
    app.requests.get = original_get
    app.run_risk_analysis = original_run_risk_analysis
    app.risk_analysis_history = original_risk_history
    app.risk_analysis_last_started = original_risk_analysis_last_started
    app.price_history = original_history
    app.klines_5min = original_klines
    app.news_items = original_news
    for name, value in original_price_state.items():
        setattr(app, name, value)
    if risk_tmp is not None:
        risk_tmp.cleanup()


original_settings = dict(app.app_settings)
original_appdata_dir = app.APPDATA_DIR
original_settings_path = app.SETTINGS_PATH
original_thresholds_path = app.THRESHOLDS_PATH
original_price_history_path = app.PRICE_HISTORY_PATH
original_price_archive = list(app.price_archive)
original_source_health = dict(app.source_health)
original_alert_cooldown_state = dict(app.alert_cooldown_state)

try:
    with tempfile.TemporaryDirectory() as tmp_dir:
        app.APPDATA_DIR = tmp_dir
        app.SETTINGS_PATH = str(Path(tmp_dir) / "settings.json")
        app.THRESHOLDS_PATH = str(Path(tmp_dir) / "thresholds.json")
        app.PRICE_HISTORY_PATH = str(Path(tmp_dir) / "price_history.json")
        app.price_archive = []
        app.source_health = {}
        app.alert_cooldown_state = {}
        app.app_settings = app._normalize_settings({
            "smtp_password": "smtp-secret",
            "risk_assistant_depth": "deep",
            "floating_price_opacity": "88",
            "floating_price_display_mode": "usd_only",
            "floating_price_snap_edge": False,
            "alert_cooldown_minutes": "45",
            "alert_quiet_start": "22:00",
            "alert_quiet_end": "07:30",
            "email_subject_template": "[{level}] {title}",
            "email_body_template": "{message}\n{price_rmb}",
        })
        if app.app_settings["risk_assistant_depth"] != "deep":
            raise SystemExit("risk assistant depth must be normalized and saved")
        if app.app_settings["floating_price_opacity"] != 88:
            raise SystemExit("floating price opacity must be normalized")
        if app.app_settings["alert_quiet_start"] != "22:00" or app.app_settings["alert_quiet_end"] != "07:30":
            raise SystemExit("alert quiet hours must be normalized")

        app.record_source_health("测试行情源", "gold", False, "测试失败", time.monotonic())
        health = app.get_source_health_state()
        if not health.get("items") or health["items"][0].get("name") != "测试行情源":
            raise SystemExit(f"source health must expose recorded source state, got: {health}")

        point = {
            "usd": 2350.12,
            "rmb": 543.21,
            "rate": 7.19,
            "time": "12:00:00",
            "timestamp": "2026-06-08T12:00:00",
        }
        app.add_price_history_entry(point, force_save=True)
        if not Path(app.PRICE_HISTORY_PATH).exists():
            raise SystemExit("price history must be persisted to disk")
        history_state = app.build_price_history_state(limit=10)
        if history_state.get("total") != 1 or history_state["stats"]["rmb"]["end"] != 543.21:
            raise SystemExit(f"price history state must summarize saved points, got: {history_state}")
        csv_text, count = app.build_price_history_csv()
        if count != 1 or "usd_per_oz" not in csv_text or "2350.12" not in csv_text:
            raise SystemExit(f"price history CSV export is invalid: {csv_text}")

        diagnostics = app.build_diagnostics_report()
        if "smtp-secret" in diagnostics:
            raise SystemExit("diagnostics report must not include raw SMTP password")
        if "smtp_password_masked" not in diagnostics:
            raise SystemExit("diagnostics report must include masked SMTP password state")

        client = authorized_client()
        try:
            client.emit("get_source_health")
            assert_event(client.get_received(), "source_health_updated")
            client.emit("get_price_history", {"limit": 10})
            assert_event(client.get_received(), "price_history_updated")
            client.emit("export_price_history", {})
            export_event = wait_for_event(client, "price_history_export_ready")
            if "2350.12" not in export_event.get("content", ""):
                raise SystemExit(f"price history export event must include CSV content, got: {export_event}")
        finally:
            client.disconnect()
finally:
    app.app_settings = original_settings
    app.APPDATA_DIR = original_appdata_dir
    app.SETTINGS_PATH = original_settings_path
    app.THRESHOLDS_PATH = original_thresholds_path
    app.PRICE_HISTORY_PATH = original_price_history_path
    app.price_archive = original_price_archive
    app.source_health = original_source_health
    app.alert_cooldown_state = original_alert_cooldown_state


print("risk contract checks passed.")
