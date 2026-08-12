import socket
import time


def find_available_port(preferred, *, host, socket_factory=socket.socket):
    for port in range(int(preferred), int(preferred) + 50):
        with socket_factory(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.2)
            if probe.connect_ex((host, port)) == 0:
                continue
        with socket_factory(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind((host, port))
                return port
            except OSError:
                continue
    with socket_factory(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((host, 0))
        return probe.getsockname()[1]


def local_app_url(host, port, path="/"):
    normalized_path = path or "/"
    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"
    return f"http://{host}:{int(port)}{normalized_path}"


def is_tcp_port_open(host, port, timeout=0.05, socket_factory=socket.socket):
    with socket_factory(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(timeout)
        return probe.connect_ex((host, int(port))) == 0


def is_application_health_payload(payload, app_name):
    return (
        isinstance(payload, dict)
        and payload.get("app") == app_name
        and isinstance(payload.get("version"), str)
        and bool(payload.get("version"))
    )


def find_existing_instance(
    host,
    preferred,
    *,
    app_name,
    proxies,
    request_get,
    port_probe,
    port_count=50,
    timeout=0.2,
):
    for port in range(int(preferred), int(preferred) + max(1, int(port_count))):
        try:
            if port_probe and not port_probe(host, port, timeout):
                continue
        except Exception:
            continue
        try:
            response = request_get(
                local_app_url(host, port, "/api/health"),
                timeout=timeout,
                proxies=proxies,
            )
            if (
                getattr(response, "status_code", 0) == 200
                and is_application_health_payload(response.json(), app_name)
            ):
                return port
        except Exception:
            continue
    return None


def open_existing_instance(
    host,
    port,
    *,
    desktop_mode,
    proxies,
    request_post,
    browser_open,
    timeout=0.5,
):
    activated = False
    try:
        response = request_post(
            local_app_url(host, port, "/api/activate"),
            timeout=timeout,
            proxies=proxies,
        )
        payload = response.json() if getattr(response, "ok", False) else {}
        activated = bool(isinstance(payload, dict) and payload.get("ok"))
    except Exception:
        activated = False

    if desktop_mode and activated:
        return True

    try:
        browser_open(local_app_url(host, port))
        return True
    except Exception:
        return activated


def wait_for_server_ready(
    host,
    port,
    *,
    timeout=3.0,
    socket_factory=socket.socket,
    clock=time.time,
    sleep=time.sleep,
):
    deadline = clock() + timeout
    while clock() < deadline:
        with socket_factory(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.1)
            if probe.connect_ex((host, int(port))) == 0:
                return True
        sleep(0.05)
    return False


class InstanceRuntime:
    def __init__(
        self,
        state,
        *,
        default_host,
        default_port,
        app_name,
        proxies,
        socket_factory,
        request_get,
        request_post,
        browser_open,
        clock=time.time,
        sleep=time.sleep,
    ):
        self.state = state
        self.default_host = default_host
        self.default_port = default_port
        self.app_name = app_name
        self.proxies = proxies
        self.socket_factory = socket_factory
        self.request_get = request_get
        self.request_post = request_post
        self.browser_open = browser_open
        self.clock = clock
        self.sleep = sleep

    def find_available_port(self, preferred=None):
        return find_available_port(
            self.default_port if preferred is None else preferred,
            host=self.default_host,
            socket_factory=self.socket_factory(),
        )

    def local_app_url(self, host=None, port=None, path="/"):
        return local_app_url(
            self.default_host if host is None else host,
            self.default_port if port is None else port,
            path,
        )

    def is_tcp_port_open(self, host, port, timeout=0.05):
        return is_tcp_port_open(
            host,
            port,
            timeout=timeout,
            socket_factory=self.socket_factory(),
        )

    def is_application_health_payload(self, payload):
        return is_application_health_payload(payload, self.app_name)

    def find_existing_instance(
        self,
        host=None,
        preferred=None,
        *,
        port_count=50,
        request_get_override=None,
        port_probe=None,
        timeout=0.2,
    ):
        return find_existing_instance(
            self.default_host if host is None else host,
            self.default_port if preferred is None else preferred,
            app_name=self.app_name,
            proxies=self.proxies,
            request_get=request_get_override or self.request_get(),
            port_probe=port_probe or self.is_tcp_port_open,
            port_count=port_count,
            timeout=timeout,
        )

    def open_existing_instance(
        self,
        host=None,
        port=None,
        *,
        desktop_mode=False,
        request_post_override=None,
        browser_open_override=None,
        timeout=0.5,
    ):
        return open_existing_instance(
            self.default_host if host is None else host,
            self.default_port if port is None else port,
            desktop_mode=desktop_mode,
            proxies=self.proxies,
            request_post=request_post_override or self.request_post(),
            browser_open=browser_open_override or self.browser_open(),
            timeout=timeout,
        )

    def wait_for_server_ready(self, timeout=3.0):
        return wait_for_server_ready(
            self.default_host,
            self.state.server_port,
            timeout=timeout,
            socket_factory=self.socket_factory(),
            clock=self.clock,
            sleep=self.sleep,
        )
