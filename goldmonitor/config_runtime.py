import os

from goldmonitor import alert_rules as alert_rules_core
from goldmonitor import support_files as support_files_core
from goldmonitor import targets as targets_core


def normalize_alert_profiles_for_import(payload, *, normalize):
    return normalize(payload) if isinstance(payload, list) else None


def normalize_alert_rules_for_import(payload, *, normalize, now_factory, id_factory):
    if not isinstance(payload, list):
        return None
    normalized, invalid_count = normalize(
        payload,
        now_factory=now_factory,
        id_factory=id_factory,
    )
    if invalid_count:
        raise ValueError("备份中的预警规则包含无效或重复数据")
    return normalized


def prepare_alert_profiles_for_import(
    payload,
    *,
    current_thresholds,
    current_volatility_config,
    current_settings,
):
    if not isinstance(payload, list):
        return []
    prepared = []
    for item in payload:
        if not isinstance(item, dict):
            prepared.append(item)
            continue
        next_item = dict(item)
        raw_thresholds = next_item.get("thresholds")
        next_item["thresholds"] = {
            **current_thresholds,
            **(raw_thresholds if isinstance(raw_thresholds, dict) else {}),
        }
        raw_volatility = next_item.get("volatility_config")
        next_item["volatility_config"] = {
            **current_volatility_config,
            **(raw_volatility if isinstance(raw_volatility, dict) else {}),
        }
        raw_settings = next_item.get("settings")
        next_item["settings"] = {
            **current_settings,
            **(raw_settings if isinstance(raw_settings, dict) else {}),
        }
        prepared.append(next_item)
    return prepared


def snapshot_import_files(paths):
    snapshots = {}
    for path in paths:
        try:
            with open(path, "rb") as file_handle:
                snapshots[path] = {"exists": True, "content": file_handle.read()}
        except FileNotFoundError:
            snapshots[path] = {"exists": False, "content": b""}
    return snapshots


def restore_import_files(snapshots):
    rollback_ok = True
    for path, snapshot in snapshots.items():
        try:
            if snapshot.get("exists"):
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                with open(path, "wb") as file_handle:
                    file_handle.write(snapshot.get("content", b""))
            elif os.path.exists(path):
                os.remove(path)
        except OSError:
            rollback_ok = False
    return rollback_ok


class ConfigRestoreService:
    def __init__(
        self,
        state,
        *,
        defaults,
        secret_keys,
        paths,
        preview_backup,
        settings_payload_for_import,
        save_settings,
        get_settings,
        save_alert_rules,
        get_alert_rules_state,
        sync_legacy_views,
        rules_for_legacy_snapshot,
        normalize_alert_profiles,
        save_alert_profiles,
        prepare_alert_profiles,
        get_alert_profiles_state,
        apply_startup_setting,
        apply_settings,
        apply_floating_settings,
        public_settings,
        emit_event,
        now_factory,
        logger,
    ):
        self.state = state
        self.defaults = dict(defaults)
        self.secret_keys = tuple(secret_keys)
        self.paths = paths
        self.preview_backup = preview_backup
        self.settings_payload_for_import = settings_payload_for_import
        self.save_settings = save_settings
        self.get_settings = get_settings
        self.save_alert_rules = save_alert_rules
        self.get_alert_rules_state = get_alert_rules_state
        self.sync_legacy_views = sync_legacy_views
        self.rules_for_legacy_snapshot = rules_for_legacy_snapshot
        self.normalize_alert_profiles = normalize_alert_profiles
        self.save_alert_profiles = save_alert_profiles
        self.prepare_alert_profiles = prepare_alert_profiles
        self.get_alert_profiles_state = get_alert_profiles_state
        self.apply_startup_setting = apply_startup_setting
        self.apply_settings = apply_settings
        self.apply_floating_settings = apply_floating_settings
        self.public_settings = public_settings
        self.emit_event = emit_event
        self.now_factory = now_factory
        self.logger = logger

    def normalize_rules(self, payload):
        return normalize_alert_rules_for_import(
            payload,
            normalize=alert_rules_core.normalize_alert_rules,
            now_factory=self.now_factory,
            id_factory=alert_rules_core.generate_alert_rule_id,
        )

    def snapshot_files(self, restore_settings, restore_rules, restore_profiles):
        configured_paths = self.paths()
        selected = []
        if restore_settings:
            selected.append(configured_paths["settings"])
        if restore_rules:
            selected.append(configured_paths["alert_rules"])
        if restore_profiles:
            selected.append(configured_paths["alert_profiles"])
        return snapshot_import_files(selected)

    def restore_state(
        self,
        previous_settings,
        previous_rules,
        previous_profiles,
        restore_settings,
        restore_rules,
        restore_profiles,
    ):
        rollback_ok = True
        if restore_settings:
            try:
                self.save_settings(previous_settings)
            except OSError:
                rollback_ok = False
                with self.state.settings_lock:
                    self.state.app_settings.clear()
                    self.state.app_settings.update(previous_settings)

        if restore_rules:
            try:
                self.state.alert_rules = self.save_alert_rules(previous_rules)
            except alert_rules_core.AlertRuleStoreError:
                rollback_ok = False
                self.state.alert_rules = [dict(rule) for rule in previous_rules]
                self.sync_legacy_views()

        if restore_profiles:
            try:
                self.state.alert_profiles = self.save_alert_profiles(previous_profiles)
            except OSError:
                rollback_ok = False
                self.state.alert_profiles = list(previous_profiles)
        return rollback_ok

    def restore_backup(self, payload):
        normalized_payload, backup_metadata = support_files_core.normalize_config_backup(
            payload
        )
        preview = self.preview_backup(payload)
        if not preview.get("importable"):
            raise ValueError(preview.get("message") or "备份中没有可导入的配置")

        importable_sections = set(preview.get("sections") or [])
        raw_settings_payload = normalized_payload.get("settings")
        accepted_setting_keys = set(self.defaults)
        if backup_metadata.get("schema_version") != 0:
            accepted_setting_keys -= set(self.secret_keys)
        settings_payload = None
        if "settings" in importable_sections and isinstance(raw_settings_payload, dict):
            filtered_settings = {
                key: value
                for key, value in raw_settings_payload.items()
                if key in accepted_setting_keys
            }
            if filtered_settings:
                settings_payload = filtered_settings
        thresholds_payload = (
            normalized_payload.get("thresholds")
            if "thresholds" in importable_sections
            else None
        )
        profiles_payload = (
            normalized_payload.get("alert_profiles")
            if "alert_profiles" in importable_sections
            else None
        )
        rules_payload = (
            normalized_payload.get("alert_rules")
            if "alert_rules" in importable_sections
            else None
        )

        normalized_profiles = self.normalize_alert_profiles(profiles_payload)
        normalized_rules = self.normalize_rules(rules_payload)
        has_profiles = bool(normalized_profiles)
        has_rules = bool(normalized_rules)
        if (
            not isinstance(settings_payload, dict)
            and not isinstance(thresholds_payload, dict)
            and not has_profiles
            and not has_rules
        ):
            raise ValueError("备份中没有可导入的配置")

        previous_settings = self.get_settings()
        previous_rules = [dict(rule) for rule in self.state.alert_rules]
        previous_profiles = list(self.state.alert_profiles)
        restore_settings = isinstance(settings_payload, dict)
        restore_rules = has_rules or isinstance(thresholds_payload, dict)
        restore_profiles = bool(normalized_profiles)
        file_snapshots = self.snapshot_files(
            restore_settings,
            restore_rules,
            restore_profiles,
        )

        imported = []
        updated_settings = None
        settings_event = None
        thresholds_event = None
        volatility_event = None
        profiles_event = None
        rules_event = None
        try:
            if isinstance(settings_payload, dict):
                updated_settings = self.save_settings(
                    self.settings_payload_for_import(settings_payload)
                )
                imported.append("settings")
            if has_rules:
                self.state.alert_rules = self.save_alert_rules(normalized_rules)
                imported.append("alert_rules")
                rules_event = self.get_alert_rules_state()
                thresholds_event = dict(self.state.thresholds)
                volatility_event = dict(self.state.volatility_config)
            elif isinstance(thresholds_payload, dict):
                normalized_thresholds = targets_core.normalize_thresholds(
                    thresholds_payload,
                    self.state.thresholds,
                    self.state.volatility_config,
                )
                next_rules = self.rules_for_legacy_snapshot(
                    normalized_thresholds,
                    normalized_thresholds.get("volatility_config"),
                )
                self.state.alert_rules = self.save_alert_rules(next_rules)
                imported.append("thresholds")
                rules_event = self.get_alert_rules_state()
                thresholds_event = dict(self.state.thresholds)
                volatility_event = dict(self.state.volatility_config)
            if normalized_profiles:
                self.state.alert_profiles = self.save_alert_profiles(
                    self.prepare_alert_profiles(profiles_payload)
                )
                imported.append("alert_profiles")
                profiles_event = self.get_alert_profiles_state()
            if updated_settings is not None:
                updated_settings, startup_error = self.apply_startup_setting(
                    updated_settings
                )
                if startup_error:
                    self.logger.warning(
                        "导入配置时自启动设置失败: %s",
                        startup_error,
                    )
                settings_event = self.public_settings(updated_settings)
        except OSError:
            rollback_ok = self.restore_state(
                previous_settings,
                previous_rules,
                previous_profiles,
                restore_settings,
                restore_rules,
                restore_profiles,
            )
            files_rollback_ok = restore_import_files(file_snapshots)
            if not rollback_ok or not files_rollback_ok:
                self.logger.warning(
                    "配置导入失败后回滚未完全成功，请检查配置目录权限。"
                )
            raise

        if updated_settings is not None:
            self.apply_floating_settings(updated_settings)
        if settings_event is not None:
            self.emit_event("settings_updated", settings_event)
        if thresholds_event is not None:
            self.emit_event("thresholds_updated", thresholds_event)
            self.emit_event("volatility_updated", volatility_event)
        if rules_event is not None:
            self.emit_event("alert_rules_updated", rules_event)
        if profiles_event is not None:
            self.emit_event("alert_profiles_updated", profiles_event)
        return {"ok": True, "imported": imported}

    def reset_defaults(self):
        saved_settings, startup_error = self.apply_settings(dict(self.defaults))
        next_rules = [
            dict(rule)
            for rule in self.state.alert_rules
            if (rule.get("legacy") or {}).get("source")
            not in {"threshold", "volatility"}
        ]
        self.state.alert_rules = self.save_alert_rules(next_rules)
        self.state.alert_cooldown_state = {}
        self.emit_event("settings_updated", self.public_settings(saved_settings))
        self.emit_event("thresholds_updated", self.state.thresholds)
        self.emit_event("volatility_updated", self.state.volatility_config)
        self.emit_event("alert_rules_updated", self.get_alert_rules_state())
        return {"ok": True, "startup_error": startup_error or ""}
