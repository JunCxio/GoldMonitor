from datetime import datetime

from goldmonitor import risk_analysis as risk_analysis_core


class RiskAnalysisRuntime:
    def __init__(
        self,
        state,
        *,
        get_settings,
        get_source_health,
        request_client,
        default_settings,
        fallback_models,
        user_agent,
        request_timeout,
        assistant_timeout,
        max_tokens_default,
        temperature,
        proxies,
        section_labels,
        valid_providers,
        valid_depths,
        trend_periods,
        news_limit,
        now_factory=datetime.now,
    ):
        self.state = state
        self.get_settings = get_settings
        self.get_source_health = get_source_health
        self.request_client = request_client
        self.default_settings = default_settings
        self.fallback_models = tuple(fallback_models)
        self.user_agent = user_agent
        self.request_timeout = request_timeout
        self.assistant_timeout = assistant_timeout
        self.max_tokens_default = max_tokens_default
        self.temperature = temperature
        self.proxies = proxies
        self.section_labels = tuple(section_labels)
        self.valid_providers = set(valid_providers)
        self.valid_depths = set(valid_depths)
        self.trend_periods = tuple(trend_periods)
        self.news_limit = news_limit
        self.now_factory = now_factory

    def market_data_error(self):
        with self.state.lock:
            return risk_analysis_core.market_data_error(
                self.state.price_usd,
                self.state.price_rmb,
            )

    def build_context(self, trigger=None, depth=None):
        return risk_analysis_core.build_context_from_runtime(
            self.state,
            self.get_settings(),
            trigger=trigger,
            depth=depth,
            valid_depths=self.valid_depths,
            trend_periods=self.trend_periods,
            news_limit=self.news_limit,
            source_health=self.get_source_health(),
            now_factory=self.now_factory,
        )

    def model_client(self):
        return risk_analysis_core.RiskModelClient(
            request_client=self.request_client(),
            default_settings=self.default_settings,
            fallback_models=self.fallback_models,
            user_agent=self.user_agent,
            request_timeout=self.request_timeout,
            assistant_timeout=self.assistant_timeout,
            max_tokens_default=self.max_tokens_default,
            temperature=self.temperature,
            proxies=self.proxies,
            section_labels=self.section_labels,
        )

    def build_snapshot(self, context):
        return risk_analysis_core.build_snapshot(context)

    def parse_sections(self, content):
        return risk_analysis_core.parse_sections(content, self.section_labels)

    def build_cache_key(self, snapshot):
        return risk_analysis_core.build_cache_key(snapshot)

    def find_recent_cache(self, snapshot, cache_minutes):
        with self.state.risk_history_lock:
            return risk_analysis_core.find_recent_cache(
                self.state.risk_analysis_history,
                snapshot,
                cache_minutes,
                now=self.now_factory(),
            )

    def selected_model_config(self, settings, provider=None, client=None):
        return (client or self.model_client()).selected_model_config(
            settings,
            provider,
        )

    def test_model_availability(self, settings, client=None):
        return (client or self.model_client()).test_availability(
            settings,
            self.valid_providers,
        )

    def build_messages(self, context):
        return risk_analysis_core.build_messages(context)

    def fetch_model_options(self, settings, provider=None, client=None):
        return (client or self.model_client()).fetch_model_options(
            settings,
            provider,
        )

    def call_chat_completion(
        self,
        settings,
        context,
        provider,
        base_url,
        model,
        api_key,
        client=None,
    ):
        return (client or self.model_client()).call_chat_completion(
            settings,
            context,
            provider,
            base_url,
            model,
            api_key,
        )

    def call_deepseek(self, settings, context, client=None):
        return (client or self.model_client()).call_deepseek(settings, context)

    def call_openai_compatible(self, settings, context, client=None):
        return (client or self.model_client()).call_openai_compatible(
            settings,
            context,
        )

    def run(self, settings, context, client=None):
        return (client or self.model_client()).run(settings, context)

    def build_error_payload(self, message, settings=None, snapshot=None):
        payload = {
            "message": message,
            "diagnostic": risk_analysis_core.build_error_diagnostic(
                message,
                settings or self.get_settings(),
                snapshot,
            ),
        }
        if snapshot is not None:
            payload["snapshot"] = snapshot
        return payload

    def get_last_started(self):
        return self.state.risk_analysis_last_started

    def set_last_started(self, value):
        self.state.risk_analysis_last_started = value
