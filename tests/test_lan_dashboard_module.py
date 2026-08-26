from datetime import datetime


def _snapshot():
    return {
        "app": {"name": "金价监控", "version": "1.0.27"},
        "generated_at": "2026-08-26T18:00:00",
        "market": {"rmb": 720.1, "usd": 3456.7, "rate": 7.2},
        "quality": {"level": "normal", "label": "可信", "score": 96},
        "rules": {"total": 0, "summary": {}, "items": []},
        "alerts": [],
    }


def test_build_lan_dashboard_snapshot_exposes_only_read_only_whitelist():
    from goldmonitor.lan_dashboard import build_lan_dashboard_snapshot

    payload = build_lan_dashboard_snapshot(
        app_name="金价监控",
        app_version="1.0.27",
        market={
            "price_usd": 3456.78,
            "price_rmb": 720.12,
            "usdcny_rate": 7.2012,
            "gold_price_source": "测试源",
            "market_observation": {
                "quality_level": "normal",
                "quality_score": 96,
                "blocked_reasons": [],
                "secret": "不得暴露",
            },
        },
        source_health={
            "quality": {"label": "可信", "score": 96},
            "adapters": {"gold": [{"error": "内部错误"}]},
        },
        alert_rules={
            "total": 1,
            "summary": {"watching": 1},
            "items": [{
                "id": "rule-secret-id",
                "name": "价格观察",
                "kind": "price_threshold",
                "scope": {"mode": "rmb", "position_id": "private-position"},
                "condition": {"operator": "gte", "value": 730},
                "delivery": {"channels": ["email"], "webhook": "secret"},
                "state": {"status": "watching"},
            }],
        },
        alert_entries=[{
            "id": "alert-secret-id",
            "title": "价格提醒",
            "message": "当前价格达到观察线",
            "timestamp": "2026-08-26T17:50:00",
            "type": "warning",
            "handling_note": "私人处理备注",
            "notification_error": "内部通知错误",
        }],
        now_factory=lambda: datetime(2026, 8, 26, 18, 0, 0),
    )

    assert payload["market"]["rmb"] == 720.12
    assert payload["quality"] == {
        "level": "normal",
        "label": "可信",
        "score": 96.0,
        "blockers": [],
    }
    assert payload["rules"]["items"][0]["name"] == "价格观察"
    serialized = str(payload)
    for forbidden in (
        "rule-secret-id",
        "private-position",
        "webhook",
        "alert-secret-id",
        "私人处理备注",
        "内部通知错误",
        "不得暴露",
    ):
        assert forbidden not in serialized


def test_lan_dashboard_routes_require_login_and_register_no_write_api(tmp_path):
    from goldmonitor.lan_dashboard import create_lan_dashboard_app

    base_dir = tmp_path
    (base_dir / "templates").mkdir()
    (base_dir / "static" / "lan-dashboard").mkdir(parents=True)
    source_root = __import__("pathlib").Path(__file__).resolve().parents[1]
    for name in ("lan-login.html", "lan-dashboard.html"):
        (base_dir / "templates" / name).write_text(
            (source_root / "templates" / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    for name in ("dashboard.css", "dashboard.js"):
        (base_dir / "static" / "lan-dashboard" / name).write_text(
            (source_root / "static" / "lan-dashboard" / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    app = create_lan_dashboard_app(
        base_dir=str(base_dir),
        app_name="金价监控",
        app_version="1.0.27",
        password_provider=lambda: "long-test-password",
        snapshot_provider=_snapshot,
        session_secret="test-session-secret",
    )
    client = app.test_client()

    response = client.get("/api/dashboard")
    assert response.status_code == 401
    assert client.post("/api/dashboard").status_code == 405
    assert client.post("/login", data={"password": "wrong"}).status_code == 401
    assert client.post(
        "/login",
        data={"password": "long-test-password"},
        follow_redirects=False,
    ).status_code == 302
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    assert response.get_json()["market"]["rmb"] == 720.1
    assert client.get_cookie("goldmonitor_lan_session") is not None
    assert client.get("/api/settings").status_code == 404
    assert client.post("/logout").status_code == 302
    assert client.get("/api/dashboard").status_code == 401
    assert client.get_cookie("goldmonitor_lan_session") is None
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_lan_dashboard_setting_validation_and_url_resolution():
    from goldmonitor.lan_dashboard import (
        lan_dashboard_urls,
        normalize_lan_dashboard_host,
        normalize_lan_dashboard_port,
        validate_lan_dashboard_settings,
    )

    assert normalize_lan_dashboard_host("192.168.10.5") == "192.168.10.5"
    assert normalize_lan_dashboard_host("8.8.8.8") == "0.0.0.0"
    assert normalize_lan_dashboard_port("70000") == 65535
    assert lan_dashboard_urls("0.0.0.0", 5050, ["192.168.10.5"]) == [
        "http://192.168.10.5:5050/"
    ]
    assert "至少 12 位" in validate_lan_dashboard_settings({
        "lan_dashboard_enabled": True,
        "lan_dashboard_host": "192.168.10.5",
        "lan_dashboard_port": 5050,
        "lan_dashboard_password": "short",
    })
    assert validate_lan_dashboard_settings({
        "lan_dashboard_enabled": True,
        "lan_dashboard_host": "0.0.0.0",
        "lan_dashboard_port": 5050,
        "lan_dashboard_password": "long-test-password",
    }) == ""


def test_lan_dashboard_runtime_starts_and_stops_real_read_only_server(tmp_path):
    from pathlib import Path

    from goldmonitor.lan_dashboard import LanDashboardRuntime

    source_root = Path(__file__).resolve().parents[1]
    (tmp_path / "templates").mkdir()
    (tmp_path / "static" / "lan-dashboard").mkdir(parents=True)
    for name in ("lan-login.html", "lan-dashboard.html"):
        (tmp_path / "templates" / name).write_text(
            (source_root / "templates" / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    for name in ("dashboard.css", "dashboard.js"):
        (tmp_path / "static" / "lan-dashboard" / name).write_text(
            (source_root / "static" / "lan-dashboard" / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    class FakeServer:
        server_port = 5050

        def __init__(self):
            self.served = False
            self.closed = False

        def serve_forever(self):
            self.served = True

        def shutdown(self):
            pass

        def server_close(self):
            self.closed = True

    class FakeThread:
        def __init__(self, target, **_kwargs):
            self.target = target
            self.started = False

        def start(self):
            self.started = True
            self.target()

        def is_alive(self):
            return False

        def join(self, timeout=None):
            pass

    server = FakeServer()
    port = 5050
    settings = {
        "lan_dashboard_enabled": True,
        "lan_dashboard_host": "127.0.0.1",
        "lan_dashboard_port": port,
        "lan_dashboard_password": "long-test-password",
    }
    runtime = LanDashboardRuntime(
        base_dir=str(tmp_path),
        app_name="金价监控",
        app_version="1.0.27",
        settings_provider=lambda: dict(settings),
        snapshot_provider=_snapshot,
        server_factory=lambda host, port, app, threaded: server,
        thread_factory=FakeThread,
        address_provider=lambda: [],
    )
    try:
        status = runtime.apply(settings)
        assert status["running"] is True
        assert status["urls"] == [f"http://127.0.0.1:{port}/"]
        assert server.served is True
    finally:
        runtime.stop()
    assert runtime.status(settings)["running"] is False
    assert server.closed is True


def test_lan_dashboard_frontend_contract_has_no_remote_write_controls():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    template = (root / "templates" / "lan-dashboard.html").read_text(encoding="utf-8")
    script = (root / "static" / "lan-dashboard" / "dashboard.js").read_text(encoding="utf-8")
    assert "/api/dashboard" in script
    assert "setInterval(refresh, 10000)" in script
    for forbidden in (
        "socket.io",
        "update_settings",
        "save_alert_rule",
        "data-archive",
        "risk_analysis",
    ):
        assert forbidden not in template + script


def test_lan_dashboard_runtime_turns_bind_exit_into_status_error(tmp_path):
    from goldmonitor.lan_dashboard import LanDashboardRuntime

    settings = {
        "lan_dashboard_enabled": True,
        "lan_dashboard_host": "127.0.0.1",
        "lan_dashboard_port": 5050,
        "lan_dashboard_password": "long-test-password",
    }
    runtime = LanDashboardRuntime(
        base_dir=str(tmp_path),
        app_name="金价监控",
        app_version="1.0.27",
        settings_provider=lambda: dict(settings),
        snapshot_provider=_snapshot,
        server_factory=lambda *args, **kwargs: (_ for _ in ()).throw(SystemExit(1)),
        address_provider=lambda: [],
    )

    status = runtime.apply(settings)

    assert status["running"] is False
    assert "端口已被占用" in status["error"]
