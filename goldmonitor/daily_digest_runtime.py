import logging
from datetime import datetime

from goldmonitor import daily_digest as daily_digest_core
from goldmonitor import notification_runtime as notification_runtime_core


class DailyDigestRuntime:
    def __init__(
        self,
        state,
        *,
        state_path,
        get_settings,
        build_timeline,
        build_portfolio,
        get_source_health,
        email_sender,
        webhook_sender,
        emit,
        timeline_max_limit,
        timeline_types,
        now_factory=datetime.now,
        logger=logging,
    ):
        self.state = state
        self.state_path = state_path
        self.get_settings = get_settings
        self.build_timeline = build_timeline
        self.build_portfolio = build_portfolio
        self.get_source_health = get_source_health
        self.email_sender = email_sender
        self.webhook_sender = webhook_sender
        self.emit = emit
        self.timeline_max_limit = timeline_max_limit
        self.timeline_types = tuple(timeline_types)
        self.now_factory = now_factory
        self.logger = logger

    def settings_snapshot(self, settings=None):
        return dict(self.get_settings() if settings is None else settings)

    def state_store(self, now_factory=None):
        return daily_digest_core.DailyDigestStateStore(
            self.state_path(),
            now_factory=now_factory or self.now_factory,
        )

    def get_state(self):
        return self.state_store().load()

    def selected_channels(self, settings=None):
        return notification_runtime_core.selected_daily_digest_channels(
            self.settings_snapshot(settings or self.get_settings())
        )

    def build_snapshot(self, now=None):
        now = now or self.now_factory()
        return notification_runtime_core.build_daily_digest_snapshot(
            now=now,
            build_timeline=self.build_timeline,
            build_portfolio=self.build_portfolio,
            get_source_health=self.get_source_health,
            timeline_max_limit=self.timeline_max_limit,
            timeline_types=self.timeline_types,
        )

    def status_payload(self, now=None):
        now = now or self.now_factory()
        return notification_runtime_core.daily_digest_status_payload(
            now=now,
            settings=self.settings_snapshot(),
            state=self.get_state(),
        )

    def dispatch(self, digest, settings=None, blocking=False):
        return notification_runtime_core.dispatch_daily_digest(
            digest,
            self.settings_snapshot(settings),
            email_sender=self.email_sender,
            webhook_sender=self.webhook_sender,
            logger=self.logger,
        )

    def run_once(
        self,
        now=None,
        force=False,
        manual=False,
        blocking=False,
        *,
        build_digest=None,
        status_payload=None,
    ):
        now = now or self.now_factory()
        build_digest = build_digest or self.build_snapshot
        status_payload = status_payload or self.status_payload
        return notification_runtime_core.run_daily_digest_once(
            now=now,
            force=force,
            manual=manual,
            settings=self.settings_snapshot(),
            lock=self.state.daily_digest_lock,
            state_store=self.state_store(now_factory=lambda: now),
            build_digest=build_digest,
            email_sender=self.email_sender,
            webhook_sender=self.webhook_sender,
            emit_status=self.emit,
            status_payload=status_payload,
            logger=self.logger,
        )
