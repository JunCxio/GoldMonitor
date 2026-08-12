from contextlib import ExitStack


class DataArchiveRuntime:
    def __init__(
        self,
        runtime,
        *,
        loaders,
        source_health_loader,
        restore_price_history_state,
        initialize_market_cache,
        get_settings,
        save_settings,
        archive_manager,
        apply_floating_price_settings,
    ):
        self.runtime = runtime
        self.loaders = loaders
        self.source_health_loader = source_health_loader
        self.restore_price_history_state = restore_price_history_state
        self.initialize_market_cache = initialize_market_cache
        self.get_settings = get_settings
        self.save_settings = save_settings
        self.archive_manager = archive_manager
        self.apply_floating_price_settings = apply_floating_price_settings

    def reload_from_disk(self):
        runtime = self.runtime
        runtime.app_settings = self.loaders["settings"]()
        runtime.portfolio_positions = self.loaders["portfolio_positions"]()
        runtime.portfolio_transactions = self.loaders["portfolio_transactions"]()
        runtime.portfolio_import_backup = self.loaders["portfolio_import_backup"]()
        runtime.alert_rules = self.loaders["alert_rules"]()
        self.loaders["sync_legacy_alert_rule_views"]()
        runtime.alert_profiles = self.loaders["alert_profiles"]()
        runtime.review_notes = self.loaders["review_notes"]()
        runtime.news_items = self.loaders["news"]()
        runtime.news_last_updated = None
        runtime.news_last_error = ""
        runtime.risk_analysis_history = self.loaders["risk_analysis_history"]()
        runtime.source_health = self.source_health_loader()
        runtime.alert_log = self.loaders["alert_log"]()
        runtime.price_archive = self.loaders["price_history"]()
        self.restore_price_history_state(runtime.price_archive)

        latest_price = runtime.price_archive[-1] if runtime.price_archive else {}
        runtime.price_usd = latest_price.get("usd")
        runtime.price_rmb = latest_price.get("rmb")
        runtime.previous_usd = runtime.price_usd
        runtime.previous_rmb = runtime.price_rmb
        runtime.usdcny_rate = latest_price.get("rate")
        runtime.usdcny_rate_source = ""
        runtime.usdcny_rate_time = None
        runtime.usdcny_rate_cached = False
        runtime.usdcny_rate_error = ""
        runtime.gold_price_source = ""
        runtime.gold_price_time = None
        runtime.gold_price_cached = False
        runtime.gold_price_error = ""
        self.initialize_market_cache()

        runtime.today_date = None
        runtime.today_open_usd = None
        runtime.today_high_usd = None
        runtime.today_low_usd = None
        runtime.today_open_rmb = None
        runtime.today_high_rmb = None
        runtime.today_low_rmb = None
        runtime.alert_cooldown_state = {}
        runtime.alerted_flags = {}

    def restore(self, archive_path):
        previous_settings = self.get_settings()

        def apply_restored_state(_manifest, _preview):
            self.reload_from_disk()

        def rollback_restored_state():
            try:
                self.save_settings(previous_settings)
            finally:
                self.reload_from_disk()

        runtime = self.runtime
        with runtime.data_archive_lock, ExitStack() as stack:
            for state_lock in (
                runtime.price_refresh_lock,
                runtime.risk_analysis_lock,
                runtime.daily_digest_lock,
                runtime.today_overview_lock,
                runtime.lock,
                runtime.settings_lock,
                runtime.risk_history_lock,
                runtime.review_notes_lock,
            ):
                stack.enter_context(state_lock)
            result = self.archive_manager().restore(
                archive_path,
                apply_callback=apply_restored_state,
                rollback_callback=rollback_restored_state,
            )
        self.apply_floating_price_settings(self.get_settings())
        return result
