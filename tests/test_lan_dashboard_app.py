from pathlib import Path


def test_settings_socket_applies_lan_dashboard_without_exposing_password(
    monkeypatch,
    tmp_path,
):
    from goldmonitor import application as app

    class FakeLanRuntime:
        def __init__(self):
            self.applied = []

        def apply(self, settings):
            self.applied.append(dict(settings))
            return self.status(settings)

        def status(self, settings=None):
            settings = dict(settings or {})
            enabled = bool(settings.get("lan_dashboard_enabled"))
            return {
                "enabled": enabled,
                "running": enabled,
                "host": settings.get("lan_dashboard_host") or "0.0.0.0",
                "port": int(settings.get("lan_dashboard_port") or 5050),
                "urls": ["http://192.168.1.20:5050/"] if enabled else [],
                "password_configured": bool(
                    settings.get("lan_dashboard_password")
                ),
                "error": "",
            }

        def stop(self):
            pass

    fake_runtime = FakeLanRuntime()
    monkeypatch.setattr(app, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    monkeypatch.setattr(app.runtime, "app_settings", dict(app.DEFAULT_SETTINGS))
    monkeypatch.setattr(app.runtime, "credential_test_store", {})
    monkeypatch.setattr(app.runtime, "lan_dashboard_runtime_instance", fake_runtime)
    monkeypatch.setattr(app, "set_startup_enabled", lambda enabled: (True, ""))
    monkeypatch.setattr(app, "apply_floating_price_settings", lambda settings: None)
    monkeypatch.setattr(
        app.lan_dashboard_core,
        "discover_private_ipv4_addresses",
        lambda: ["192.168.1.20"],
    )

    client = app.socketio.test_client(
        app.app,
        auth={"token": app.SOCKET_ACCESS_TOKEN},
    )
    client.get_received()
    client.emit("update_settings", {
        "lan_dashboard_enabled": True,
        "lan_dashboard_host": "0.0.0.0",
        "lan_dashboard_port": 5050,
        "lan_dashboard_password": "long-test-password",
    })
    events = client.get_received()
    settings = next(
        event["args"][0]
        for event in events
        if event["name"] == "settings_updated"
    )

    assert settings["lan_dashboard_enabled"] is True
    assert settings["lan_dashboard_password_configured"] is True
    assert settings["lan_dashboard_status"]["running"] is True
    assert settings["lan_dashboard_status"]["urls"] == [
        "http://192.168.1.20:5050/"
    ]
    assert "lan_dashboard_password" not in settings
    assert fake_runtime.applied[-1]["lan_dashboard_password"] == (
        "long-test-password"
    )
    persisted = Path(app.SETTINGS_PATH).read_text(encoding="utf-8")
    assert "long-test-password" not in persisted
    assert app.runtime.credential_test_store["lan_dashboard_password"] == (
        "long-test-password"
    )
    client.disconnect()


def test_settings_socket_rejects_enabling_lan_dashboard_without_password(
    monkeypatch,
    tmp_path,
):
    from goldmonitor import application as app

    monkeypatch.setattr(app, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    monkeypatch.setattr(app.runtime, "app_settings", dict(app.DEFAULT_SETTINGS))
    monkeypatch.setattr(app.runtime, "credential_test_store", {})
    monkeypatch.setattr(app, "set_startup_enabled", lambda enabled: (True, ""))
    monkeypatch.setattr(app, "apply_floating_price_settings", lambda settings: None)

    client = app.socketio.test_client(
        app.app,
        auth={"token": app.SOCKET_ACCESS_TOKEN},
    )
    client.get_received()
    client.emit("update_settings", {
        "lan_dashboard_enabled": True,
        "lan_dashboard_host": "0.0.0.0",
        "lan_dashboard_port": 5050,
        "lan_dashboard_password": "short",
    })
    events = client.get_received()
    error = next(
        event["args"][0]
        for event in events
        if event["name"] == "settings_error"
    )
    assert "至少 12 位" in error["message"]
    assert app.runtime.app_settings["lan_dashboard_enabled"] is False
    client.disconnect()
