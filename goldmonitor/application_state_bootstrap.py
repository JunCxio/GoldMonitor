import logging
from datetime import datetime


class ApplicationStateBootstrap:
    def __init__(
        self,
        *,
        runtime,
        loaders,
        save_settings,
        sync_legacy_alert_rule_views,
        restore_price_history_state,
        initialize_market_cache,
        settings_file_existed_at_startup,
        onboarding_marker_present_at_startup,
        alert_log_memory_limit,
        now_factory=datetime.now,
        logger=logging,
    ):
        self.runtime = runtime
        self.loaders = loaders
        self.save_settings = save_settings
        self.sync_legacy_alert_rule_views = sync_legacy_alert_rule_views
        self.restore_price_history_state = restore_price_history_state
        self.initialize_market_cache = initialize_market_cache
        self.settings_file_existed_at_startup = settings_file_existed_at_startup
        self.onboarding_marker_present_at_startup = (
            onboarding_marker_present_at_startup
        )
        self.alert_log_memory_limit = alert_log_memory_limit
        self.now_factory = now_factory
        self.logger = logger

    def initialize(self):
        self._load_configuration_state()
        self._load_history_state()
        return self.runtime

    def _load_configuration_state(self):
        self.runtime.app_settings = self.loaders["settings"]()
        self._migrate_existing_settings_onboarding_state()
        self.runtime.alert_rules = self.loaders["alert_rules"]()
        self.sync_legacy_alert_rule_views()
        self.runtime.alert_profiles = self.loaders["alert_profiles"]()
        self.runtime.review_notes = self.loaders["review_notes"]()
        self.runtime.portfolio_positions = self.loaders["portfolio_positions"]()
        self.runtime.portfolio_transactions = self.loaders["portfolio_transactions"]()
        self.runtime.portfolio_investment_plans = self.loaders[
            "portfolio_investment_plans"
        ]()
        self.runtime.portfolio_import_backup = self.loaders[
            "portfolio_import_backup"
        ]()
        self.sync_legacy_alert_rule_views()

    def _migrate_existing_settings_onboarding_state(self):
        if (
            not self.settings_file_existed_at_startup
            or self.onboarding_marker_present_at_startup
        ):
            return
        self.runtime.app_settings["onboarding_started"] = True
        self.runtime.app_settings["onboarding_completed"] = True
        self.runtime.app_settings["onboarding_version"] = 1
        self.runtime.app_settings["onboarding_completed_at"] = self.now_factory().isoformat(
            timespec="seconds"
        )
        try:
            self.runtime.app_settings = self.save_settings(self.runtime.app_settings)
        except OSError as exc:
            self.logger.warning("首次使用状态迁移保存失败: %s", exc)

    def _load_history_state(self):
        self.runtime.news_items = self.loaders["news"]()
        self.runtime.risk_analysis_history = self.loaders["risk_analysis_history"]()
        self.runtime.alert_log = self.loaders["alert_log"](
            limit=self.alert_log_memory_limit
        )
        self.runtime.market_quality_history = self.loaders[
            "market_quality_history"
        ]()
        self.runtime.price_archive = self.loaders["price_history"]()
        self.restore_price_history_state(self.runtime.price_archive)
        self.initialize_market_cache()
