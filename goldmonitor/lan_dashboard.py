import ipaddress
import hashlib
import logging
import secrets
import socket
import threading
import time
from collections import defaultdict, deque

from flask import Flask, jsonify, redirect, render_template, request, session
from werkzeug.serving import make_server


LAN_DASHBOARD_DEFAULT_HOST = "0.0.0.0"
LAN_DASHBOARD_DEFAULT_PORT = 5050
LAN_DASHBOARD_PASSWORD_MIN_LENGTH = 12
LAN_DASHBOARD_ALERT_LIMIT = 12
LAN_DASHBOARD_RULE_LIMIT = 12


def normalize_lan_dashboard_host(value, default=LAN_DASHBOARD_DEFAULT_HOST):
    text = str(value or default).strip()
    if text == "0.0.0.0":
        return text
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return str(default)
    if address.version != 4 or address.is_multicast or address.is_unspecified:
        return str(default)
    if not (address.is_private or address.is_loopback):
        return str(default)
    return str(address)


def normalize_lan_dashboard_port(value, default=LAN_DASHBOARD_DEFAULT_PORT):
    try:
        port = int(float(value))
    except (TypeError, ValueError):
        port = int(default)
    return max(1024, min(65535, port))


def validate_lan_dashboard_settings(settings):
    settings = settings if isinstance(settings, dict) else {}
    if not settings.get("lan_dashboard_enabled"):
        return ""
    host = str(settings.get("lan_dashboard_host") or "").strip()
    if normalize_lan_dashboard_host(host, default="") != host:
        return "监听地址必须是本机私有 IPv4 地址、127.0.0.1 或 0.0.0.0"
    port = normalize_lan_dashboard_port(settings.get("lan_dashboard_port"))
    try:
        raw_port = int(float(settings.get("lan_dashboard_port")))
    except (TypeError, ValueError):
        raw_port = 0
    if port != raw_port:
        return "只读面板端口应在 1024 到 65535 之间"
    password = str(settings.get("lan_dashboard_password") or "")
    if len(password) < LAN_DASHBOARD_PASSWORD_MIN_LENGTH:
        return f"启用只读面板前需要设置至少 {LAN_DASHBOARD_PASSWORD_MIN_LENGTH} 位访问口令"
    return ""


def discover_private_ipv4_addresses():
    addresses = set()
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("10.255.255.255", 1))
            addresses.add(probe.getsockname()[0])
        finally:
            probe.close()
    except OSError:
        pass
    result = []
    for value in addresses:
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            continue
        if address.version == 4 and address.is_private and not address.is_loopback:
            result.append(str(address))
    return sorted(set(result), key=lambda value: tuple(int(part) for part in value.split(".")))


def lan_dashboard_urls(host, port, addresses=None):
    host = normalize_lan_dashboard_host(host)
    port = normalize_lan_dashboard_port(port)
    if host == "0.0.0.0":
        hosts = list(addresses if addresses is not None else discover_private_ipv4_addresses())
    else:
        hosts = [host]
    return [f"http://{item}:{port}/" for item in hosts]


def _number(value, digits=2):
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _safe_text(value, limit=240):
    return str(value or "").strip()[:limit]


def _rule_summary(rule):
    rule = rule if isinstance(rule, dict) else {}
    scope = rule.get("scope") if isinstance(rule.get("scope"), dict) else {}
    condition = rule.get("condition") if isinstance(rule.get("condition"), dict) else {}
    state = rule.get("state") if isinstance(rule.get("state"), dict) else {}
    return {
        "name": _safe_text(rule.get("name") or "未命名规则", 80),
        "kind": _safe_text(rule.get("kind"), 32),
        "status": _safe_text(state.get("status") or "watching", 32),
        "mode": _safe_text(scope.get("mode"), 16),
        "operator": _safe_text(condition.get("operator"), 16),
        "target": _number(condition.get("value"), 4),
        "triggered_at": _safe_text(state.get("last_triggered_at"), 40),
    }


def _alert_summary(entry):
    entry = entry if isinstance(entry, dict) else {}
    return {
        "timestamp": _safe_text(entry.get("timestamp"), 40),
        "time": _safe_text(entry.get("time"), 16),
        "type": _safe_text(entry.get("type") or "warning", 24),
        "title": _safe_text(entry.get("title") or "金价预警", 100),
        "message": _safe_text(entry.get("message"), 280),
        "handled": bool(entry.get("handled")),
        "acknowledged": bool(entry.get("acknowledged")),
    }


def build_lan_dashboard_snapshot(
    *,
    app_name,
    app_version,
    market,
    source_health,
    alert_rules,
    alert_entries,
    now_factory=None,
):
    market = market if isinstance(market, dict) else {}
    source_health = source_health if isinstance(source_health, dict) else {}
    alert_rules = alert_rules if isinstance(alert_rules, dict) else {}
    observation = market.get("market_observation")
    observation = observation if isinstance(observation, dict) else {}
    quality = source_health.get("quality")
    quality = quality if isinstance(quality, dict) else {}
    summary = alert_rules.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    rule_items = [
        _rule_summary(item)
        for item in list(alert_rules.get("items") or [])[:LAN_DASHBOARD_RULE_LIMIT]
        if isinstance(item, dict)
    ]
    alerts = [
        _alert_summary(item)
        for item in list(alert_entries or [])[:LAN_DASHBOARD_ALERT_LIMIT]
        if isinstance(item, dict)
    ]
    now = now_factory() if now_factory else time.strftime("%Y-%m-%dT%H:%M:%S")
    if hasattr(now, "isoformat"):
        now = now.isoformat(timespec="seconds")
    return {
        "app": {"name": str(app_name), "version": str(app_version)},
        "generated_at": str(now),
        "market": {
            "usd": _number(market.get("price_usd"), 2),
            "rmb": _number(market.get("price_rmb"), 2),
            "rate": _number(market.get("usdcny_rate"), 4),
            "previous_usd": _number(market.get("previous_usd"), 2),
            "previous_rmb": _number(market.get("previous_rmb"), 2),
            "gold_source": _safe_text(market.get("gold_price_source"), 80),
            "gold_time": _safe_text(market.get("gold_price_time"), 40),
            "gold_cached": bool(market.get("gold_price_cached")),
            "rate_source": _safe_text(market.get("usdcny_rate_source"), 80),
            "rate_time": _safe_text(market.get("usdcny_rate_time"), 40),
            "rate_cached": bool(market.get("usdcny_rate_cached")),
            "ok": bool(market.get("last_fetch_ok")),
        },
        "quality": {
            "level": _safe_text(
                observation.get("quality_level") or quality.get("level") or "unavailable",
                24,
            ),
            "label": _safe_text(quality.get("label") or "等待行情", 40),
            "score": _number(
                observation.get("quality_score")
                if observation.get("quality_score") is not None
                else quality.get("score"),
                1,
            ),
            "blockers": [
                _safe_text(item, 120)
                for item in list(
                    observation.get("blocked_reasons")
                    or quality.get("reasons")
                    or []
                )[:4]
                if item
            ],
        },
        "rules": {
            "total": int(alert_rules.get("total") or 0),
            "summary": {
                key: int(summary.get(key) or 0)
                for key in (
                    "watching",
                    "triggered",
                    "waiting_data",
                    "scheduled",
                    "expired",
                    "disabled",
                    "orphaned",
                )
            },
            "items": rule_items,
        },
        "alerts": alerts,
    }


class LoginRateLimiter:
    def __init__(self, *, limit=5, window_seconds=300, clock=time.monotonic):
        self.limit = max(1, int(limit))
        self.window_seconds = max(1, int(window_seconds))
        self.clock = clock
        self.lock = threading.Lock()
        self.attempts = defaultdict(deque)

    def allow(self, key):
        now = self.clock()
        with self.lock:
            attempts = self.attempts[str(key or "unknown")]
            while attempts and now - attempts[0] >= self.window_seconds:
                attempts.popleft()
            return len(attempts) < self.limit

    def record_failure(self, key):
        with self.lock:
            self.attempts[str(key or "unknown")].append(self.clock())

    def clear(self, key):
        with self.lock:
            self.attempts.pop(str(key or "unknown"), None)


def create_lan_dashboard_app(
    *,
    base_dir,
    app_name,
    app_version,
    password_provider,
    snapshot_provider,
    session_secret=None,
    rate_limiter=None,
):
    flask_app = Flask(
        f"{__name__}.readonly",
        template_folder=f"{base_dir}/templates",
        static_folder=None,
    )
    flask_app.secret_key = session_secret or secrets.token_urlsafe(48)
    flask_app.config.update(
        SESSION_COOKIE_NAME="goldmonitor_lan_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=False,
        PERMANENT_SESSION_LIFETIME=8 * 60 * 60,
    )
    limiter = rate_limiter or LoginRateLimiter()

    @flask_app.after_request
    def security_headers(response):
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; script-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'"
        )
        return response

    @flask_app.get("/")
    def index():
        if not session.get("lan_dashboard_authorized"):
            return render_template(
                "lan-login.html",
                app_name=app_name,
                app_version=app_version,
                error="",
            )
        return render_template(
            "lan-dashboard.html",
            app_name=app_name,
            app_version=app_version,
        )

    @flask_app.post("/login")
    def login():
        client_key = request.remote_addr or "unknown"
        if not limiter.allow(client_key):
            return render_template(
                "lan-login.html",
                app_name=app_name,
                app_version=app_version,
                error="尝试次数过多，请稍后再试。",
            ), 429
        expected = str(password_provider() or "")
        supplied = str(request.form.get("password") or "")
        if expected and secrets.compare_digest(supplied, expected):
            limiter.clear(client_key)
            session.clear()
            session.permanent = True
            session["lan_dashboard_authorized"] = True
            return redirect("/")
        limiter.record_failure(client_key)
        return render_template(
            "lan-login.html",
            app_name=app_name,
            app_version=app_version,
            error="访问口令不正确。",
        ), 401

    @flask_app.post("/logout")
    def logout():
        session.clear()
        return redirect("/")

    @flask_app.get("/api/dashboard")
    def api_dashboard():
        if not session.get("lan_dashboard_authorized"):
            return jsonify({"ok": False, "message": "需要登录"}), 401
        return jsonify(snapshot_provider())

    @flask_app.get("/assets/dashboard.css")
    def dashboard_css():
        return flask_app.send_static_file("dashboard.css")

    @flask_app.get("/assets/dashboard.js")
    def dashboard_js():
        return flask_app.send_static_file("dashboard.js")

    flask_app.static_folder = f"{base_dir}/static/lan-dashboard"
    return flask_app


class LanDashboardRuntime:
    def __init__(
        self,
        *,
        base_dir,
        app_name,
        app_version,
        settings_provider,
        snapshot_provider,
        server_factory=make_server,
        thread_factory=threading.Thread,
        address_provider=discover_private_ipv4_addresses,
        logger=logging,
    ):
        self.base_dir = base_dir
        self.app_name = app_name
        self.app_version = app_version
        self.settings_provider = settings_provider
        self.snapshot_provider = snapshot_provider
        self.server_factory = server_factory
        self.thread_factory = thread_factory
        self.address_provider = address_provider
        self.logger = logger
        self.lock = threading.RLock()
        self.server = None
        self.thread = None
        self.host = ""
        self.port = 0
        self.error = ""
        self.session_secret = secrets.token_urlsafe(48)
        self.password_fingerprint = ""

    def _password(self):
        return str(self.settings_provider().get("lan_dashboard_password") or "")

    def start(self, settings=None):
        settings = dict(settings or self.settings_provider())
        validation_error = validate_lan_dashboard_settings(settings)
        if validation_error:
            self.stop()
            with self.lock:
                self.error = validation_error
            return self.status(settings)
        host = normalize_lan_dashboard_host(settings.get("lan_dashboard_host"))
        port = normalize_lan_dashboard_port(settings.get("lan_dashboard_port"))
        password_fingerprint = hashlib.sha256(
            str(settings.get("lan_dashboard_password") or "").encode("utf-8")
        ).hexdigest()
        with self.lock:
            if (
                self.server is not None
                and self.host == host
                and self.port == port
                and self.password_fingerprint == password_fingerprint
            ):
                self.error = ""
                return self.status(settings)
        self.stop()
        server = None
        try:
            self.session_secret = secrets.token_urlsafe(48)
            dashboard_app = create_lan_dashboard_app(
                base_dir=self.base_dir,
                app_name=self.app_name,
                app_version=self.app_version,
                password_provider=self._password,
                snapshot_provider=self.snapshot_provider,
                session_secret=self.session_secret,
            )
            server = self.server_factory(host, port, dashboard_app, threaded=True)
            actual_port = int(getattr(server, "server_port", port))
            thread = self.thread_factory(
                target=server.serve_forever,
                name="GoldMonitor-LAN-Dashboard",
                daemon=True,
            )
            thread.start()
        except (OSError, RuntimeError, SystemExit) as exc:
            if server is not None:
                try:
                    server.server_close()
                except OSError:
                    pass
            message = (
                "端口已被占用或监听地址不可用"
                if isinstance(exc, SystemExit)
                else str(exc)
            )
            with self.lock:
                self.error = f"只读面板启动失败：{message}"
            self.logger.warning("局域网只读面板启动失败: %s", message)
            return self.status(settings)
        with self.lock:
            self.server = server
            self.thread = thread
            self.host = host
            self.port = actual_port
            self.password_fingerprint = password_fingerprint
            self.error = ""
        return self.status(settings)

    def stop(self):
        with self.lock:
            server = self.server
            thread = self.thread
            self.server = None
            self.thread = None
            self.host = ""
            self.port = 0
        if server is not None:
            try:
                server.shutdown()
                server.server_close()
            except OSError:
                pass
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2)

    def apply(self, settings=None):
        settings = dict(settings or self.settings_provider())
        if not settings.get("lan_dashboard_enabled"):
            self.stop()
            with self.lock:
                self.error = ""
            return self.status(settings)
        return self.start(settings)

    def status(self, settings=None):
        settings = dict(settings or self.settings_provider())
        with self.lock:
            running = self.server is not None
            host = self.host or normalize_lan_dashboard_host(
                settings.get("lan_dashboard_host")
            )
            port = self.port or normalize_lan_dashboard_port(
                settings.get("lan_dashboard_port")
            )
            error = self.error
        return {
            "enabled": bool(settings.get("lan_dashboard_enabled")),
            "running": running,
            "host": host,
            "port": port,
            "urls": lan_dashboard_urls(host, port, self.address_provider()),
            "password_configured": bool(settings.get("lan_dashboard_password")),
            "error": error,
        }
