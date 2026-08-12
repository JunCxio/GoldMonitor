import logging
import threading
from datetime import datetime

from goldmonitor import alert_delivery_runtime as alert_delivery_runtime_core
from goldmonitor import notification_delivery as notification_delivery_core
from goldmonitor import notification_policy as notification_policy_core
from goldmonitor import notification_transport as notification_transport_core


class AlertNotificationRuntime:
    def __init__(
        self,
        state,
        *,
        get_settings,
        generate_id,
        select_news,
        save_entry,
        update_entry,
        emit,
        build_history_state,
        send_desktop_notification,
        play_system_alert_sound,
        show_alert_dialog,
        email_sender,
        webhook_sender,
        alert_level_map,
        alert_log_limit,
        now_factory=datetime.now,
        thread_factory=threading.Thread,
        logger=logging,
    ):
        self.state = state
        self.get_settings = get_settings
        self.generate_id = generate_id
        self.select_news = select_news
        self.save_entry = save_entry
        self.update_entry = update_entry
        self.emit = emit
        self.build_history_state = build_history_state
        self.send_desktop_notification = send_desktop_notification
        self.play_system_alert_sound = play_system_alert_sound
        self.show_alert_dialog = show_alert_dialog
        self.email_sender = email_sender
        self.webhook_sender = webhook_sender
        self.alert_level_map = dict(alert_level_map)
        self.alert_log_limit = alert_log_limit
        self.now_factory = now_factory
        self.thread_factory = thread_factory
        self.logger = logger

    def settings_snapshot(self, settings=None):
        return dict(self.get_settings() if settings is None else settings)

    def build_template_values(self, alert_type, title, message):
        with self.state.lock:
            market = {
                "price_usd": self.state.price_usd,
                "price_rmb": self.state.price_rmb,
                "usdcny_rate": self.state.usdcny_rate,
                "gold_price_source": self.state.gold_price_source,
                "usdcny_rate_source": self.state.usdcny_rate_source,
            }
        return notification_transport_core.build_alert_template_values(
            alert_type,
            title,
            message,
            market,
            self.alert_level_map,
        )

    def evaluate_delivery(self, entry, settings=None, now=None):
        return notification_policy_core.evaluate_alert_delivery(
            entry,
            self.settings_snapshot(settings or self.get_settings()),
            self.state.alert_cooldown_state,
            now=now,
        )

    def dispatch(self, entry, title, blocking=True, on_update=None):
        return notification_delivery_core.dispatch_alert(
            entry,
            title,
            self.settings_snapshot(),
            email_sender=self.email_sender,
            webhook_sender=self.webhook_sender,
            logger=self.logger,
            blocking=blocking,
            thread_factory=None if blocking else self.thread_factory,
            on_update=on_update,
        )

    def plan_notifications(self, entry, settings=None):
        return notification_delivery_core.plan_alert_notifications(
            entry,
            self.settings_snapshot(settings or self.get_settings()),
        )

    def persist_notification_update(self, alert_id, notifications):
        return alert_delivery_runtime_core.persist_alert_notification_update(
            alert_id,
            notifications,
            update_entry=self.update_entry,
            emit=self.emit,
        )

    def deliver_notifications(
        self,
        alert_id,
        entry,
        title,
        settings,
        notifications,
        *,
        persist_update=None,
    ):
        persist_update = persist_update or self.persist_notification_update
        return notification_delivery_core.deliver_alert_notifications(
            entry,
            title,
            settings,
            email_sender=self.email_sender,
            webhook_sender=self.webhook_sender,
            notifications=notifications,
            on_update=lambda items, item: persist_update(alert_id, items),
            logger=self.logger,
        )

    def start_delivery(self, entry, title, settings=None, *, deliver=None):
        deliver = deliver or self.deliver_notifications
        return alert_delivery_runtime_core.start_alert_notification_delivery(
            entry,
            title,
            get_settings=lambda: self.settings_snapshot(
                settings or self.get_settings()
            ),
            deliver=deliver,
            thread_factory=self.thread_factory,
        )

    def emit_alert(
        self,
        entry,
        title,
        *,
        evaluate_delivery=None,
        plan_notifications=None,
        start_delivery=None,
    ):
        evaluate_delivery = evaluate_delivery or self.evaluate_delivery
        plan_notifications = plan_notifications or self.plan_notifications
        start_delivery = start_delivery or self.start_delivery
        return alert_delivery_runtime_core.emit_alert(
            entry,
            title,
            settings=self.settings_snapshot(),
            market_lock=self.state.lock,
            market_price=lambda mode: (
                self.state.price_usd
                if mode == "usd"
                else self.state.price_rmb if mode == "rmb" else None
            ),
            generate_id=self.generate_id,
            evaluate_delivery=evaluate_delivery,
            plan_notifications=plan_notifications,
            select_news=self.select_news,
            alert_log=self.state.alert_log,
            alert_log_limit=self.alert_log_limit,
            save_entry=self.save_entry,
            emit=self.emit,
            start_delivery=start_delivery,
            build_history_state=self.build_history_state,
            local_delivery_enabled=(
                notification_delivery_core.alert_local_delivery_enabled
            ),
            send_desktop_notification=self.send_desktop_notification,
            play_system_alert_sound=self.play_system_alert_sound,
            show_alert_dialog=self.show_alert_dialog,
            now_factory=self.now_factory,
            logger=self.logger,
        )
