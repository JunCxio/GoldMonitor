from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._payload


def test_find_existing_goldmonitor_instance_requires_health_identity():
    probed = []
    requested = []

    def fake_port_probe(host, port, timeout):
        probed.append((host, port, timeout))
        return port in {app.DEFAULT_PORT + 1, app.DEFAULT_PORT + 2}

    def fake_get(url, timeout, proxies=None):
        requested.append((url, timeout, proxies))
        if url == app.local_app_url(app.DEFAULT_HOST, app.DEFAULT_PORT + 1, "/api/health"):
            return FakeResponse({"app": "OtherApp", "version": "9.9.9"})
        if url == app.local_app_url(app.DEFAULT_HOST, app.DEFAULT_PORT + 2, "/api/health"):
            return FakeResponse({"app": app.APP_NAME, "version": app.APP_VERSION})
        raise AssertionError(f"unexpected request: {url}")

    assert app.find_existing_goldmonitor_instance(
        app.DEFAULT_HOST,
        app.DEFAULT_PORT,
        port_count=4,
        request_get=fake_get,
        port_probe=fake_port_probe,
        timeout=0.01,
    ) == app.DEFAULT_PORT + 2
    assert requested == [
        (app.local_app_url(app.DEFAULT_HOST, app.DEFAULT_PORT + 1, "/api/health"), 0.01, app.REQ_PROXY),
        (app.local_app_url(app.DEFAULT_HOST, app.DEFAULT_PORT + 2, "/api/health"), 0.01, app.REQ_PROXY),
    ]


def test_open_existing_goldmonitor_instance_activates_desktop_without_browser():
    posts = []
    opened = []

    def fake_post(url, timeout, proxies=None):
        posts.append((url, timeout, proxies))
        return FakeResponse({"ok": True, "desktop": True})

    assert app.open_existing_goldmonitor_instance(
        app.DEFAULT_HOST,
        app.DEFAULT_PORT,
        desktop_mode=True,
        request_post=fake_post,
        browser_open=opened.append,
        timeout=0.01,
    ) is True
    assert posts == [
        (app.local_app_url(app.DEFAULT_HOST, app.DEFAULT_PORT, "/api/activate"), 0.01, app.REQ_PROXY),
    ]
    assert opened == []


def test_open_existing_goldmonitor_instance_opens_browser_for_web_mode():
    posts = []
    opened = []

    def fake_post(url, timeout, proxies=None):
        posts.append((url, timeout, proxies))
        return FakeResponse({"ok": True, "desktop": False})

    assert app.open_existing_goldmonitor_instance(
        app.DEFAULT_HOST,
        app.DEFAULT_PORT,
        desktop_mode=False,
        request_post=fake_post,
        browser_open=opened.append,
        timeout=0.01,
    ) is True
    assert posts == [
        (app.local_app_url(app.DEFAULT_HOST, app.DEFAULT_PORT, "/api/activate"), 0.01, app.REQ_PROXY),
    ]
    assert opened == [app.local_app_url(app.DEFAULT_HOST, app.DEFAULT_PORT)]


def test_health_endpoint_identifies_goldmonitor_instance():
    client = app.app.test_client()

    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["app"] == app.APP_NAME
    assert payload["version"] == app.APP_VERSION
    assert payload["port"] == app.server_port
