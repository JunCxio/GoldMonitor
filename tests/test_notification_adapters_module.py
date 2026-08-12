import threading


def test_desktop_notification_adapter_binds_macos_channels():
    from goldmonitor.notification_adapters import DesktopNotificationAdapter

    scripts = []
    active = {"value": False}

    class ImmediateThread:
        def __init__(self, target, daemon=False):
            self.target = target

        def start(self):
            self.target()

    adapter = DesktopNotificationAdapter(
        get_settings=lambda: {
            "alert_dialog_enabled": True,
            "alert_sound_enabled": True,
        },
        active_lock=lambda: threading.Lock(),
        get_active=lambda: active["value"],
        set_active=lambda value: active.update(value=value),
        base_dir=lambda: "/app",
        app_id="GoldMonitor.App",
        applescript_string=lambda value: f'"{value}"',
        run_applescript=lambda script, **kwargs: scripts.append((script, kwargs)),
        sys_platform=lambda: "darwin",
        os_name=lambda: "posix",
        path_exists=lambda path: False,
        thread_factory=ImmediateThread,
    )

    adapter.send("标题", "内容")
    assert adapter.play_sound("warning") is True
    assert adapter.show_dialog("预警", "价格变化") is True

    assert scripts[0] == (
        'display notification "内容" with title "标题"',
        {"wait": False},
    )
    assert scripts[1] == ("beep", {"wait": False})
    assert scripts[2][1] == {"wait": True, "timeout": 3600}
    assert active["value"] is False


def test_email_notification_adapter_sends_alert_and_digest():
    from goldmonitor.notification_adapters import EmailNotificationAdapter

    sent = []

    class FakeServer:
        def login(self, sender, password):
            sent.append(("login", sender, password))

        def sendmail(self, sender, recipients, message):
            sent.append(("message", sender, recipients, message))

        def quit(self):
            sent.append(("quit",))

    class FakeSmtp:
        @staticmethod
        def SMTP_SSL(server, port, timeout):
            sent.append(("connect", server, port, timeout))
            return FakeServer()

    settings = {
        "smtp_server": "smtp.example.com",
        "smtp_port": "465",
        "smtp_encryption": "ssl",
        "smtp_sender": "sender@example.com",
        "smtp_password": "secret",
        "smtp_recipient": "receiver@example.com",
    }
    adapter = EmailNotificationAdapter(
        get_settings=lambda: settings,
        build_alert_values=lambda alert_type, title, message: {
            "level": "关注",
            "title": title,
            "message": message,
        },
        smtp_module=lambda: FakeSmtp,
        default_subject_template="[{level}] {title}",
        default_body_template="{message}",
    )

    assert adapter.send_alert(
        "warning",
        "价格提醒",
        "已达到目标",
        blocking=True,
    ) is None
    assert adapter.send_digest(
        {"subject": "每日摘要", "message": "摘要内容"},
        blocking=True,
    ) is None

    assert [item[0] for item in sent].count("connect") == 2
    assert [item[0] for item in sent].count("message") == 2


def test_webhook_notification_adapter_preserves_alert_and_digest_payloads():
    from goldmonitor.notification_adapters import WebhookNotificationAdapter

    posted = []

    class Response:
        @staticmethod
        def raise_for_status():
            return None

    def post(url, **kwargs):
        posted.append((url, kwargs))
        return Response()

    adapter = WebhookNotificationAdapter(
        get_settings=lambda: {
            "webhook_enabled": True,
            "webhook_url": "https://notify.example/hook",
        },
        build_alert_values=lambda alert_type, title, message: {
            "level": "警告",
            "time": "2026-08-11 12:00:00",
            "price_usd": "2,388.50",
            "price_rmb": "552.30",
            "rate": "7.1234",
            "gold_source": "黄金源",
            "rate_source": "汇率源",
        },
        post=post,
        require_https_url=lambda url, label: None,
        app_name="GoldMonitor",
        app_version="1.0.17",
        user_agent="GoldMonitor/1.0.17",
        proxies={"http": None, "https": None},
    )

    assert adapter.send_alert(
        "critical",
        "价格预警",
        "价格异常",
        blocking=True,
    ) is None
    assert adapter.send_digest(
        {"payload": {"type": "daily_digest", "summary": "摘要"}},
        blocking=True,
    ) is None

    assert posted[0][1]["json"]["title"] == "价格预警"
    assert posted[0][1]["json"]["version"] == "1.0.17"
    assert posted[1][1]["json"] == {
        "type": "daily_digest",
        "summary": "摘要",
    }
