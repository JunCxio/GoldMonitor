import time


def wait_for_event(client, name, timeout=1.0):
    deadline = time.time() + timeout
    seen = []
    while time.time() < deadline:
        received = client.get_received()
        seen.extend(received)
        for event in received:
            if event.get("name") == name:
                args = event.get("args") or []
                return args[0] if args else {}
        time.sleep(0.02)
    raise AssertionError(f"expected socket event {name}, got {seen}")


def test_request_risk_analysis_rejects_without_market_price(monkeypatch, tmp_path):
    import app

    monkeypatch.setattr(app, "app_settings", app._normalize_settings({
        "risk_assistant_enabled": True,
        "risk_assistant_provider": "deepseek",
        "deepseek_base_url": "https://api.deepseek.com",
        "deepseek_model": "deepseek-v4-pro",
        "deepseek_api_key": "sk-risk-secret",
        "risk_assistant_cooldown_seconds": 0,
        "risk_assistant_cache_minutes": 0,
    }))
    monkeypatch.setattr(app, "price_usd", None)
    monkeypatch.setattr(app, "price_rmb", None)
    monkeypatch.setattr(app, "risk_analysis_history", [])
    monkeypatch.setattr(app, "risk_analysis_last_started", 0.0)
    monkeypatch.setattr(app, "RISK_ANALYSIS_HISTORY_PATH", str(tmp_path / "risk_analysis_history.json"))

    model_calls = []

    def capture_run(settings, context):
        model_calls.append((settings, context))
        return {"provider": "deepseek", "model": "deepseek-v4-pro", "content": "ok", "usage": None}, None

    monkeypatch.setattr(app, "run_risk_analysis", capture_run)

    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    try:
        client.get_received()
        client.emit("request_risk_analysis", {})
        error = wait_for_event(client, "risk_analysis_error")
    finally:
        client.disconnect()

    assert "当前没有可用于风险分析的行情价格" in error.get("message", "")
    assert model_calls == []
