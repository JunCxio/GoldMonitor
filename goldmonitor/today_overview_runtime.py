from datetime import datetime

from goldmonitor import today_overview as today_overview_core


class TodayOverviewRuntime:
    def __init__(
        self,
        state,
        *,
        state_path,
        get_alert_entries,
        get_alert_rules,
        get_source_health,
        get_fetch_status,
        build_portfolio,
        get_risk_history,
        get_review_notes,
        now_factory=datetime.now,
    ):
        self.state = state
        self.state_path = state_path
        self.get_alert_entries = get_alert_entries
        self.get_alert_rules = get_alert_rules
        self.get_source_health = get_source_health
        self.get_fetch_status = get_fetch_status
        self.build_portfolio = build_portfolio
        self.get_risk_history = get_risk_history
        self.get_review_notes = get_review_notes
        self.now_factory = now_factory

    def state_store(self, now_factory=None):
        return today_overview_core.TodayOverviewStateStore(
            self.state_path(),
            now_factory=now_factory or self.now_factory,
        )

    @staticmethod
    def _state_items(value):
        if isinstance(value, dict):
            return value.get("items") if isinstance(value.get("items"), list) else []
        return value if isinstance(value, list) else []

    def get_view_state(self):
        with self.state.today_overview_lock:
            return self.state_store().load()

    def build(self, now=None):
        now = now or self.now_factory()
        view_state = self.get_view_state()
        source_health = self.get_source_health()
        source_health = source_health if isinstance(source_health, dict) else {}
        return today_overview_core.build_today_overview(
            alert_entries=self.get_alert_entries(),
            alert_rules=self.get_alert_rules(),
            market_quality=source_health.get("quality"),
            fetch_status=self.get_fetch_status(),
            portfolio_state=self.build_portfolio(),
            risk_items=self._state_items(self.get_risk_history()),
            review_notes=self._state_items(self.get_review_notes()),
            last_viewed_at=view_state.get("last_viewed_at", ""),
            now=now,
        )

    def mark_viewed(self, now=None):
        now = now or self.now_factory()
        with self.state.today_overview_lock:
            view_state = self.state_store(now_factory=lambda: now).mark_viewed(now)
        return {
            "view_state": view_state,
            "overview": self.build(now=now),
        }
