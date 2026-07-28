from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from goldmonitor import instance_runtime


class FakeResponse:
    def __init__(self, payload, status_code=200, ok=True):
        self._payload = payload
        self.status_code = status_code
        self.ok = ok

    def json(self):
        return self._payload


def test_local_url_and_health_identity_are_strict():
    assert instance_runtime.local_app_url("127.0.0.1", 5000) == "http://127.0.0.1:5000/"
    assert instance_runtime.local_app_url("127.0.0.1", 5000, "api/health") == (
        "http://127.0.0.1:5000/api/health"
    )
    assert instance_runtime.is_application_health_payload(
        {"app": "金价监控", "version": "1.0.9"},
        "金价监控",
    ) is True
    assert instance_runtime.is_application_health_payload(
        {"app": "其他程序", "version": "1.0.9"},
        "金价监控",
    ) is False


def test_existing_instance_requires_open_port_and_matching_health_payload():
    calls = []

    def request_get(url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith(":5001/api/health"):
            return FakeResponse({"app": "其他程序", "version": "9.9.9"})
        return FakeResponse({"app": "金价监控", "version": "1.0.9"})

    found = instance_runtime.find_existing_instance(
        "127.0.0.1",
        5000,
        app_name="金价监控",
        proxies={"http": None, "https": None},
        request_get=request_get,
        port_probe=lambda _host, port, _timeout: port in {5001, 5002},
        port_count=4,
        timeout=0.01,
    )

    assert found == 5002
    assert [url for url, _kwargs in calls] == [
        "http://127.0.0.1:5001/api/health",
        "http://127.0.0.1:5002/api/health",
    ]


def test_existing_instance_activation_respects_desktop_and_web_modes():
    opened = []

    def request_post(url, **kwargs):
        return FakeResponse({"ok": True, "desktop": True})

    assert instance_runtime.open_existing_instance(
        "127.0.0.1",
        5000,
        desktop_mode=True,
        proxies=None,
        request_post=request_post,
        browser_open=opened.append,
    ) is True
    assert opened == []

    assert instance_runtime.open_existing_instance(
        "127.0.0.1",
        5000,
        desktop_mode=False,
        proxies=None,
        request_post=request_post,
        browser_open=opened.append,
    ) is True
    assert opened == ["http://127.0.0.1:5000/"]


def test_port_selection_and_server_wait_use_injected_socket_factory():
    class FakeSocket:
        def __init__(self, connect_result=1):
            self.connect_result = connect_result
            self.bound = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def settimeout(self, timeout):
            self.timeout = timeout

        def connect_ex(self, address):
            return self.connect_result

        def bind(self, address):
            self.bound = address

        def getsockname(self):
            return self.bound

    sockets = iter([FakeSocket(1), FakeSocket(1)])
    selected = instance_runtime.find_available_port(
        5000,
        host="127.0.0.1",
        socket_factory=lambda *_args: next(sockets),
    )
    assert selected == 5000

    assert instance_runtime.wait_for_server_ready(
        "127.0.0.1",
        5000,
        socket_factory=lambda *_args: FakeSocket(0),
        clock=lambda: 0.0,
        sleep=lambda _seconds: None,
    ) is True
