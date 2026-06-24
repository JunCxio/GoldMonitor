import json
import logging
import os


def optional_int(value):
    if value in (None, ""):
        return None
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return number if -100000 <= number <= 100000 else None


def bounded_int(value, default, minimum, maximum):
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def normalize_hhmm(value):
    text = str(value or "").strip()
    if not text:
        return ""
    parts = text.split(":")
    if len(parts) != 2:
        return ""
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return ""
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return f"{hour:02d}:{minute:02d}"
    return ""


def normalize_settings(raw, defaults, options=None):
    options = options or {}
    data = dict(defaults)
    if isinstance(raw, dict):
        data.update(raw)

    data["startup_enabled"] = bool(data.get("startup_enabled"))
    data["startup_to_tray"] = bool(data.get("startup_to_tray"))
    data["floating_price_enabled"] = bool(data.get("floating_price_enabled", True))
    data["floating_price_position_saved"] = bool(data.get("floating_price_position_saved", False))
    data["floating_price_x"] = optional_int(data.get("floating_price_x"))
    data["floating_price_y"] = optional_int(data.get("floating_price_y"))
    if data["floating_price_x"] is None or data["floating_price_y"] is None:
        data["floating_price_position_saved"] = False
        data["floating_price_x"] = None
        data["floating_price_y"] = None
    elif not data["floating_price_position_saved"]:
        data["floating_price_x"] = None
        data["floating_price_y"] = None
    data["floating_price_opacity"] = bounded_int(data.get("floating_price_opacity", 94), 94, 50, 100)
    if data.get("floating_price_display_mode") not in options.get("valid_floating_display_modes", set()):
        data["floating_price_display_mode"] = "rmb_usd"
    if data.get("floating_price_preset") not in options.get("valid_floating_presets", set()):
        data["floating_price_preset"] = defaults["floating_price_preset"]
    data["floating_price_snap_edge"] = bool(data.get("floating_price_snap_edge", True))
    data["close_remembered"] = bool(data.get("close_remembered"))
    data["alert_sound_enabled"] = bool(data.get("alert_sound_enabled"))
    data["alert_dialog_enabled"] = bool(data.get("alert_dialog_enabled"))
    data.pop("update_manifest_url", None)
    data.pop("update_auto_check_interval_hours", None)
    if data.get("close_behavior") not in options.get("valid_close_behaviors", set()):
        data["close_behavior"] = defaults["close_behavior"]
        data["close_remembered"] = False

    data["smtp_server"] = str(data.get("smtp_server") or "").strip()
    data["smtp_port"] = str(data.get("smtp_port") or "465").strip()
    if data.get("smtp_encryption") not in options.get("valid_smtp_encryptions", set()):
        data["smtp_encryption"] = "ssl"
    data["smtp_sender"] = str(data.get("smtp_sender") or "").strip()
    data["smtp_password"] = str(data.get("smtp_password") or "")
    data["smtp_recipient"] = str(data.get("smtp_recipient") or "").strip()
    data["webhook_enabled"] = bool(data.get("webhook_enabled", False))
    data["webhook_url"] = str(data.get("webhook_url") or "").strip()
    data["webhook_warning_enabled"] = bool(data.get("webhook_warning_enabled", True))
    data["webhook_critical_enabled"] = bool(data.get("webhook_critical_enabled", True))
    data["webhook_volatility_enabled"] = bool(data.get("webhook_volatility_enabled", True))
    data["email_warning_enabled"] = bool(data.get("email_warning_enabled", True))
    data["email_critical_enabled"] = bool(data.get("email_critical_enabled", True))
    data["email_volatility_enabled"] = bool(data.get("email_volatility_enabled", True))
    data["alert_cooldown_minutes"] = bounded_int(data.get("alert_cooldown_minutes", 30), 30, 0, 240)
    data["alert_quiet_start"] = normalize_hhmm(data.get("alert_quiet_start"))
    data["alert_quiet_end"] = normalize_hhmm(data.get("alert_quiet_end"))
    data["email_subject_template"] = str(
        data.get("email_subject_template") or options.get("default_email_subject_template") or defaults.get("email_subject_template", "")
    )
    data["email_body_template"] = str(
        data.get("email_body_template") or options.get("default_email_body_template") or defaults.get("email_body_template", "")
    )

    data["risk_assistant_enabled"] = bool(data.get("risk_assistant_enabled", True))
    if data.get("risk_assistant_provider") not in options.get("valid_risk_assistant_providers", set()):
        data["risk_assistant_provider"] = "deepseek"
    if data.get("risk_assistant_depth") not in options.get("valid_risk_assistant_depths", set()):
        data["risk_assistant_depth"] = "standard"
    data["deepseek_base_url"] = str(data.get("deepseek_base_url") or defaults["deepseek_base_url"]).strip().rstrip("/")
    if not data["deepseek_base_url"]:
        data["deepseek_base_url"] = defaults["deepseek_base_url"]
    data["deepseek_model"] = str(data.get("deepseek_model") or defaults["deepseek_model"]).strip()
    data["deepseek_api_key"] = str(data.get("deepseek_api_key") or "").strip()
    data["openai_compatible_base_url"] = str(data.get("openai_compatible_base_url") or "").strip().rstrip("/")
    data["openai_compatible_model"] = str(data.get("openai_compatible_model") or "").strip()
    data["openai_compatible_api_key"] = str(data.get("openai_compatible_api_key") or "").strip()

    max_tokens_default = int(options.get("risk_assistant_max_tokens") or defaults.get("risk_assistant_max_tokens", 1200))
    data["risk_assistant_max_tokens"] = bounded_int(
        data.get("risk_assistant_max_tokens", max_tokens_default),
        max_tokens_default,
        300,
        4000,
    )
    data["risk_assistant_cooldown_seconds"] = bounded_int(
        data.get("risk_assistant_cooldown_seconds", 15),
        15,
        0,
        300,
    )
    data["risk_assistant_cache_minutes"] = bounded_int(
        data.get("risk_assistant_cache_minutes", 10),
        10,
        0,
        60,
    )
    return data


def apply_stored_secrets(settings, secret_keys, read_secret):
    merged = dict(settings)
    for key in secret_keys:
        if merged.get(key):
            continue
        stored = read_secret(key) if read_secret else ""
        if stored:
            merged[key] = stored
    return merged


def persistable_settings_snapshot(
    settings,
    secret_keys,
    write_secret,
    previous_settings=None,
    credentials_required=False,
    logger=None,
):
    persisted = dict(settings)
    previous_settings = previous_settings or {}
    credential_failures = []
    logger = logger or logging.getLogger(__name__)
    for key in secret_keys:
        secret = str(persisted.get(key) or "")
        if not secret:
            if previous_settings.get(key) and write_secret:
                write_secret(key, "")
            persisted[key] = ""
            continue
        if write_secret and write_secret(key, secret):
            persisted[key] = ""
        elif credentials_required:
            credential_failures.append(key)
        else:
            logger.warning("系统凭据不可用，保留兼容配置字段: %s", key)
    if credential_failures:
        raise OSError("系统凭据写入失败: " + ", ".join(credential_failures))
    return persisted


def mask_secret(value):
    value = str(value or "")
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * 8}{value[-4:]}"


def build_public_settings_snapshot(settings, secret_keys, platform=None, platform_capabilities=None):
    snapshot = dict(settings or {})
    if platform is not None:
        snapshot["platform"] = platform
    if platform_capabilities is not None:
        snapshot["platform_capabilities"] = platform_capabilities
    for key in secret_keys:
        secret = snapshot.pop(key, "")
        snapshot[f"{key}_configured"] = bool(secret)
        snapshot[f"{key}_masked"] = mask_secret(secret)
    return snapshot


def merge_settings_update(current, data, allowed_keys, secret_clear_flags):
    merged = dict(current or {})
    incoming = {key: value for key, value in (data or {}).items() if key in allowed_keys}
    for secret_key, clear_flag in secret_clear_flags.items():
        if secret_key not in incoming:
            continue
        key_value = str(incoming.get(secret_key) or "").strip()
        if key_value:
            incoming[secret_key] = key_value
        elif data.get(clear_flag):
            incoming[secret_key] = ""
        else:
            incoming.pop(secret_key, None)
    merged.update(incoming)
    return merged


def settings_payload_for_import(settings_payload, current_settings, defaults, secret_keys):
    imported = dict(defaults)
    if isinstance(settings_payload, dict):
        imported.update({key: value for key, value in settings_payload.items() if key in defaults})
    for key in secret_keys:
        if not isinstance(settings_payload, dict) or key not in settings_payload:
            imported[key] = current_settings.get(key, "")
    return imported


class SettingsFileStore:
    def __init__(
        self,
        settings_path,
        defaults,
        options=None,
        secret_keys=(),
        read_secret=None,
        write_secret=None,
        credentials_required=False,
        logger=None,
    ):
        self.settings_path = settings_path
        self.defaults = defaults
        self.options = options or {}
        self.secret_keys = tuple(secret_keys)
        self.read_secret = read_secret or (lambda _key: "")
        self.write_secret = write_secret or (lambda _key, _value: False)
        self.credentials_required = bool(credentials_required)
        self.logger = logger or logging.getLogger(__name__)

    def normalize(self, raw):
        return normalize_settings(raw, self.defaults, self.options)

    def apply_stored_secrets(self, settings):
        return apply_stored_secrets(settings, self.secret_keys, self.read_secret)

    def persistable_snapshot(self, settings, previous_settings=None):
        return persistable_settings_snapshot(
            settings,
            self.secret_keys,
            self.write_secret,
            previous_settings=previous_settings,
            credentials_required=self.credentials_required,
            logger=self.logger,
        )

    def load_raw(self):
        if not os.path.exists(self.settings_path):
            return {}, ""
        try:
            with open(self.settings_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            return payload if isinstance(payload, dict) else {}, ""
        except (OSError, json.JSONDecodeError) as exc:
            return {}, str(exc)

    def save(self, data, previous_settings=None):
        normalized = self.normalize(data)
        persisted = self.persistable_snapshot(normalized, previous_settings=previous_settings)
        os.makedirs(os.path.dirname(self.settings_path) or ".", exist_ok=True)
        tmp_path = self.settings_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(persisted, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.settings_path)
        return normalized

    def load(self):
        os.makedirs(os.path.dirname(self.settings_path) or ".", exist_ok=True)
        loaded, error = self.load_raw()
        data = self.apply_stored_secrets(self.normalize(loaded))
        save_error = ""
        try:
            self.save(data, previous_settings={})
        except OSError as exc:
            save_error = str(exc)
        return data, error or save_error
