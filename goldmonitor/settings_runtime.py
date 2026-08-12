import logging

from goldmonitor import settings_store as settings_store_core


class SettingsRuntime:
    def __init__(
        self,
        state,
        *,
        settings_path,
        defaults,
        options,
        secret_keys,
        read_secret,
        write_secret,
        credentials_required,
        platform_name,
        platform_capabilities,
        default_export_dir,
        resolve_export_dir,
        build_export_dir_check,
        taskbar_discovery_state,
        logger=logging,
    ):
        self.state = state
        self.settings_path = settings_path
        self.defaults = defaults
        self.options = options
        self.secret_keys = tuple(secret_keys)
        self.read_secret = read_secret
        self.write_secret = write_secret
        self.credentials_required = bool(credentials_required)
        self.platform_name = platform_name
        self.platform_capabilities = platform_capabilities
        self.default_export_dir = default_export_dir
        self.resolve_export_dir = resolve_export_dir
        self.build_export_dir_check = build_export_dir_check
        self.taskbar_discovery_state = taskbar_discovery_state
        self.logger = logger

    def store(self):
        return settings_store_core.SettingsFileStore(
            self.settings_path,
            defaults=self.defaults,
            options=self.options,
            secret_keys=self.secret_keys,
            read_secret=self.read_secret,
            write_secret=self.write_secret,
            credentials_required=self.credentials_required,
            logger=self.logger,
        )

    def apply_stored_secrets(self, settings):
        return settings_store_core.apply_stored_secrets(
            settings,
            self.secret_keys,
            self.read_secret,
        )

    def persistable_snapshot(self, settings, previous_settings=None):
        return settings_store_core.persistable_settings_snapshot(
            settings,
            self.secret_keys,
            self.write_secret,
            previous_settings=previous_settings,
            credentials_required=self.credentials_required,
            logger=self.logger,
        )

    def normalize(self, raw):
        return settings_store_core.normalize_settings(
            raw,
            self.defaults,
            self.options,
        )

    def load(self):
        data, error = self.store().load()
        self.state.last_settings_error = error or None
        return data

    def save(self, data=None):
        with self.state.settings_lock:
            if data is None:
                data = self.state.app_settings
            normalized = self.store().save(
                data,
                previous_settings=self.state.app_settings,
            )
            self.state.app_settings = normalized
            self.state.last_settings_error = None
            return dict(self.state.app_settings)

    def snapshot(self):
        with self.state.settings_lock:
            return dict(self.state.app_settings)

    def public_snapshot(self, settings=None):
        snapshot = dict(settings or self.snapshot())
        public = settings_store_core.build_public_settings_snapshot(
            snapshot,
            self.secret_keys,
            platform=self.platform_name(),
            platform_capabilities=self.platform_capabilities(),
        )
        public["export_dir_default"] = self.default_export_dir
        public["export_dir_effective"] = self.resolve_export_dir(snapshot)
        public["export_dir_check"] = self.build_export_dir_check(snapshot)
        taskbar_state = dict(self.taskbar_discovery_state() or {})
        taskbar_state.update(dict(self.state.taskbar_layout_state or {}))
        public["taskbar_price_state"] = taskbar_state
        return public
