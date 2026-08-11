import logging
import os
import subprocess
import sys
import threading

from goldmonitor import notification_runtime as notification_runtime_core


class DesktopNotificationAdapter:
    def __init__(
        self,
        *,
        get_settings,
        active_lock,
        get_active,
        set_active,
        base_dir,
        app_id,
        applescript_string,
        run_applescript,
        sys_platform=lambda: sys.platform,
        os_name=lambda: os.name,
        path_exists=os.path.exists,
        popen=subprocess.Popen,
        notify_loader=None,
        winsound_loader=None,
        thread_factory=threading.Thread,
        logger=logging,
    ):
        self.get_settings = get_settings
        self.active_lock = active_lock
        self.get_active = get_active
        self.set_active = set_active
        self.base_dir = base_dir
        self.app_id = app_id
        self.applescript_string = applescript_string
        self.run_applescript = run_applescript
        self.sys_platform = sys_platform
        self.os_name = os_name
        self.path_exists = path_exists
        self.popen = popen
        self.notify_loader = notify_loader
        self.winsound_loader = winsound_loader
        self.thread_factory = thread_factory
        self.logger = logger

    def send(self, title, body):
        return notification_runtime_core.send_desktop_notification(
            title,
            body,
            sys_platform=self.sys_platform(),
            base_dir=self.base_dir(),
            app_id=self.app_id,
            applescript_string=self.applescript_string,
            run_applescript=self.run_applescript,
            path_exists=self.path_exists,
            notify_loader=self.notify_loader,
        )

    def show_dialog(self, title, message):
        return notification_runtime_core.show_alert_dialog(
            title,
            message,
            enabled=self.get_settings().get("alert_dialog_enabled", True),
            active_lock=self.active_lock(),
            get_active=self.get_active,
            set_active=self.set_active,
            sys_platform=self.sys_platform(),
            os_name=self.os_name(),
            applescript_string=self.applescript_string,
            run_applescript=self.run_applescript,
            thread_factory=self.thread_factory,
            logger=self.logger,
        )

    def play_sound(self, level):
        return notification_runtime_core.play_system_alert_sound(
            level,
            enabled=self.get_settings().get("alert_sound_enabled", True),
            sys_platform=self.sys_platform(),
            path_exists=self.path_exists,
            popen=self.popen,
            run_applescript=self.run_applescript,
            winsound_loader=self.winsound_loader,
        )


class EmailNotificationAdapter:
    def __init__(
        self,
        *,
        get_settings,
        build_alert_values,
        smtp_module,
        default_subject_template,
        default_body_template,
        thread_factory=threading.Thread,
        logger=logging,
    ):
        self.get_settings = get_settings
        self.build_alert_values = build_alert_values
        self.smtp_module = smtp_module
        self.default_subject_template = default_subject_template
        self.default_body_template = default_body_template
        self.thread_factory = thread_factory
        self.logger = logger

    def send_alert(
        self,
        alert_type,
        title,
        message,
        timeout=10,
        blocking=False,
    ):
        return notification_runtime_core.send_email_alert(
            alert_type,
            title,
            message,
            get_settings=self.get_settings,
            build_values=self.build_alert_values,
            smtp_module=self.smtp_module(),
            default_subject_template=self.default_subject_template,
            default_body_template=self.default_body_template,
            timeout=timeout,
            blocking=blocking,
            thread_factory=self.thread_factory,
            logger=self.logger,
        )

    def send_digest(self, digest, timeout=10, blocking=False):
        return notification_runtime_core.send_daily_digest_email(
            digest,
            get_settings=self.get_settings,
            smtp_module=self.smtp_module(),
            timeout=timeout,
            blocking=blocking,
            thread_factory=self.thread_factory,
            logger=self.logger,
        )


class WebhookNotificationAdapter:
    def __init__(
        self,
        *,
        get_settings,
        build_alert_values,
        post,
        require_https_url,
        app_name,
        app_version,
        user_agent,
        proxies,
        thread_factory=threading.Thread,
        logger=logging,
    ):
        self.get_settings = get_settings
        self.build_alert_values = build_alert_values
        self.post = post
        self.require_https_url = require_https_url
        self.app_name = app_name
        self.app_version = app_version
        self.user_agent = user_agent
        self.proxies = proxies
        self.thread_factory = thread_factory
        self.logger = logger

    def send_alert(
        self,
        alert_type,
        title,
        message,
        timeout=8,
        blocking=False,
    ):
        return notification_runtime_core.send_webhook_alert(
            alert_type,
            title,
            message,
            get_settings=self.get_settings,
            build_values=self.build_alert_values,
            post=self.post,
            require_https_url=self.require_https_url,
            app_name=self.app_name,
            app_version=self.app_version,
            user_agent=self.user_agent,
            proxies=self.proxies,
            timeout=timeout,
            blocking=blocking,
            thread_factory=self.thread_factory,
            logger=self.logger,
        )

    def send_digest(self, digest, timeout=8, blocking=False):
        return notification_runtime_core.send_daily_digest_webhook(
            digest,
            get_settings=self.get_settings,
            post=self.post,
            require_https_url=self.require_https_url,
            user_agent=self.user_agent,
            proxies=self.proxies,
            timeout=timeout,
            blocking=blocking,
            thread_factory=self.thread_factory,
            logger=self.logger,
        )


class NotificationAdapters:
    def __init__(self, *, desktop, email, webhook):
        self.desktop = desktop
        self.email = email
        self.webhook = webhook
