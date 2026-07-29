import json
import logging
import os
import sqlite3
import smtplib
import subprocess
import socket
import sys
import threading
import time
from datetime import datetime, timedelta
import secrets
from types import ModuleType

import requests
from flask import Flask, jsonify, render_template, request, send_from_directory
from flask_socketio import SocketIO, emit
from goldmonitor import alert_rules as alert_rules_core
from goldmonitor import alert_runtime as alert_runtime_core
from goldmonitor import alert_profiles as alert_profiles_core
from goldmonitor import app_state as app_state_core
from goldmonitor import application_bootstrap as application_bootstrap_core
from goldmonitor import application_state_bootstrap as application_state_bootstrap_core
from goldmonitor import config_runtime as config_runtime_core
from goldmonitor import desktop_ui as desktop_ui_core
from goldmonitor import daily_digest as daily_digest_core
from goldmonitor import data_archive as data_archive_core
from goldmonitor import data_archive_runtime as data_archive_runtime_core
from goldmonitor import desktop_runtime as desktop_runtime_core
from goldmonitor import desktop_status as desktop_status_core
from goldmonitor import diagnostics_runtime as diagnostics_runtime_core
from goldmonitor import event_timeline as event_timeline_core
from goldmonitor import floating_controller as floating_controller_core
from goldmonitor import taskbar_controller as taskbar_controller_core
from goldmonitor import instance_runtime as instance_runtime_core
from goldmonitor import http_routes as http_routes_core
from goldmonitor import market_adapters as market_adapters_core
from goldmonitor import market_clients as market_clients_core
from goldmonitor import market_data as market_data_core
from goldmonitor import market_runtime as market_runtime_core
from goldmonitor import news as news_core
from goldmonitor import notifications as notifications_core
from goldmonitor import notification_runtime as notification_runtime_core
from goldmonitor import operations_runtime as operations_runtime_core
from goldmonitor import platform as platform_core
from goldmonitor import platform_runtime as platform_runtime_core
from goldmonitor import portfolio as portfolio_core
from goldmonitor import portfolio_alerts as portfolio_alerts_core
from goldmonitor import portfolio_runtime as portfolio_runtime_core
from goldmonitor import review_notes as review_notes_core
from goldmonitor import risk_analysis as risk_analysis_core
from goldmonitor import runtime_state as runtime_state_core
from goldmonitor import settings_store as settings_store_core
from goldmonitor import socket_bootstrap as socket_bootstrap_core
from goldmonitor import storage_manifest as storage_manifest_core
from goldmonitor import support_files as support_files_core
from goldmonitor import targets as targets_core
from goldmonitor import update_manager as update_manager_core
from goldmonitor import update_runtime as update_runtime_core
from goldmonitor.alert_log import AlertLogStore
from goldmonitor.diagnostics import build_health_summary
from goldmonitor.platform import platform_capabilities as build_platform_capabilities
from goldmonitor.platform import runtime_platform as detect_runtime_platform
from goldmonitor.price_history import PriceHistoryStore
from goldmonitor import price_history as price_history_core

# PyInstaller 打包后路径适配
if getattr(sys, "frozen", False):
    _basedir = sys._MEIPASS
else:
    _basedir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = Flask(
    __name__,
    template_folder=os.path.join(_basedir, "templates"),
    static_folder=None,
)
app.config["MAX_CONTENT_LENGTH"] = 256 * 1024 * 1024
socketio = SocketIO(app, async_mode="threading")

# ---------- 常量 ----------
APP_VERSION = "1.0.13"
APP_USER_MODEL_ID = "GoldMonitor.App"
DEFAULT_UPDATE_MANIFEST_URL = "https://github.com/JunCxio/GoldMonitor/releases/latest/download/version.json"
OFFICIAL_UPDATE_HOST = "github.com"
OFFICIAL_UPDATE_PATH_PREFIX = "/JunCxio/GoldMonitor/releases/"
OFFICIAL_UPDATE_ASSET_NAMES = {"GoldMonitorSetup.exe", "GoldMonitor-macOS.dmg"}
UPDATE_AUTO_CHECK_INTERVAL_HOURS = 6
GOLD_URL = "https://stooq.com/q/l/?s=xauusd&f=sd2t2ohlcven"
FOREX_URL = "https://stooq.com/q/l/?s=usdcny&f=sd2t2ohlcven"
SINA_GOLD_URL = "https://hq.sinajs.cn/rn=1&list=hf_XAU"
SINA_FOREX_URL = "https://hq.sinajs.cn/rn=1&list=fx_susdcny"
FRANKFURTER_FOREX_URL = "https://api.frankfurter.app/latest?from=USD&to=CNY"
GOLDPRICE_URL = "https://data-asg.goldprice.org/dbXRates/USD,CNY"
EASTMONEY_GOLD_URL = (
    "https://push2.eastmoney.com/api/qt/stock/get"
    "?secid=122.XAU&fields=f43,f44,f45,f46,f59&ut=fa5fd1943c7b386f172d6893dbfba10b"
)
OZ_TO_GRAM = 31.1035
REQ_PROXY = {"http": None, "https": None}
REQUEST_TIMEOUT = 4
APP_NAME = "金价监控"
HTTP_USER_AGENT = f"GoldMonitor/{APP_VERSION}"
BROWSER_USER_AGENT = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) GoldMonitor/{APP_VERSION}"
CACHE_RATE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5000
SOCKET_ACCESS_TOKEN = secrets.token_urlsafe(32)
RUN_KEY_NAME = "GoldMonitor"
RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
MACOS_BUNDLE_IDENTIFIER = "com.juncxio.goldmonitor"
MACOS_LAUNCH_AGENT_ID = MACOS_BUNDLE_IDENTIFIER


def _default_appdata_root():
    configured = os.environ.get("APPDATA")
    if configured:
        return configured
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    return os.path.expanduser("~")


def _runtime_platform():
    return detect_runtime_platform(sys.platform, os.name)


def platform_capabilities():
    return build_platform_capabilities(_runtime_platform())


def _applescript_string(value):
    text = str(value or "")
    text = text.replace("\\", "\\\\").replace('"', '\\"').replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\n", "\\n")
    return f'"{text}"'


def _run_macos_osascript(script, wait=False, timeout=4):
    if sys.platform != "darwin":
        return False
    try:
        args = ["osascript", "-e", script]
        if wait:
            subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout, check=False)
        else:
            subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
        return True
    except Exception:
        logging.warning("执行 macOS AppleScript 失败", exc_info=True)
        return False


APPDATA_DIR = os.path.join(_default_appdata_root(), "GoldMonitor")
SETTINGS_PATH = os.path.join(APPDATA_DIR, "settings.json")
THRESHOLDS_PATH = os.path.join(APPDATA_DIR, "thresholds.json")
ALERT_RULES_PATH = os.path.join(APPDATA_DIR, "alert_rules.json")
ALERT_PROFILES_PATH = os.path.join(APPDATA_DIR, "alert_profiles.json")
WATCH_TARGETS_PATH = os.path.join(APPDATA_DIR, "watch_targets.json")
PORTFOLIO_POSITIONS_PATH = os.path.join(APPDATA_DIR, "portfolio_positions.json")
PORTFOLIO_TRANSACTIONS_PATH = os.path.join(APPDATA_DIR, "portfolio_transactions.json")
PORTFOLIO_IMPORT_BACKUP_PATH = os.path.join(APPDATA_DIR, "portfolio_import_backup.json")
PORTFOLIO_ALERTS_PATH = os.path.join(APPDATA_DIR, "portfolio_alerts.json")
MARKET_CACHE_PATH = os.path.join(APPDATA_DIR, "market_cache.json")
SOURCE_METRICS_PATH = os.path.join(APPDATA_DIR, "source_metrics.json")
UPDATE_DIR = os.path.join(APPDATA_DIR, "updates")
EXPORT_DIR = os.path.join(APPDATA_DIR, "exports")
UPDATE_INSTALLER_NAME = "GoldMonitor-macOS.dmg" if sys.platform == "darwin" else "GoldMonitorSetup.exe"
NEWS_CACHE_PATH = os.path.join(APPDATA_DIR, "news.json")
RISK_ANALYSIS_HISTORY_PATH = os.path.join(APPDATA_DIR, "risk_analysis_history.json")
REVIEW_NOTES_PATH = os.path.join(APPDATA_DIR, "review_notes.json")
PRICE_HISTORY_PATH = os.path.join(APPDATA_DIR, "price_history.json")
APP_LOG_PATH = os.path.join(APPDATA_DIR, "GoldMonitor.log")
DAILY_DIGEST_STATE_PATH = os.path.join(APPDATA_DIR, "daily_digest_state.json")
SETTINGS_FILE_EXISTED_AT_STARTUP = os.path.isfile(SETTINGS_PATH)
try:
    with open(SETTINGS_PATH, "r", encoding="utf-8") as _settings_marker_file:
        _settings_marker_payload = json.load(_settings_marker_file)
except (OSError, json.JSONDecodeError):
    _settings_marker_payload = {}
SETTINGS_ONBOARDING_MARKER_PRESENT_AT_STARTUP = bool(
    isinstance(_settings_marker_payload, dict)
    and (
        "onboarding_started" in _settings_marker_payload
        or "onboarding_completed" in _settings_marker_payload
    )
)
NEWS_REFRESH_INTERVAL = 15 * 60
NEWS_LIMIT = 20
RISK_ANALYSIS_HISTORY_LIMIT = 20
PRICE_HISTORY_ARCHIVE_LIMIT = 20000
PRICE_HISTORY_EXPORT_LIMIT = 5000
PRICE_HISTORY_SAVE_INTERVAL_SECONDS = 60
ALERT_LOG_MEMORY_LIMIT = 50
ALERT_LOG_EXPORT_LIMIT = 1000
ALERT_LOG_DB_LIMIT = 5000
ALERT_RULE_SIMULATION_POINT_LIMIT = 30000
EVENT_TIMELINE_TYPES = (
    "price_summary",
    "alert",
    "risk_analysis",
    "news",
    "data_status",
    "review_note",
)
EVENT_TIMELINE_DEFAULT_MINUTES = 60
EVENT_TIMELINE_ALLOWED_MINUTES = (60, 240, 1440, 10080, 43200, 129600)
EVENT_TIMELINE_MAX_LIMIT = 500
EVENT_TIMELINE_DEFAULT_LIMIT = 300
REVIEW_REPORT_EXPORT_PREFIX = "GoldMonitor-review-report"
SOURCE_HEALTH_LIMIT = 20
SOURCE_METRICS_WINDOW = 50
SOURCE_COMPARISON_REFRESH_SECONDS = 60
SOURCE_COMPARISON_STALE_SECONDS = 5 * 60
SOURCE_COMPARISON_ANOMALY_PCT = 0.5
RISK_ASSISTANT_TIMEOUT = 20
RISK_ASSISTANT_MAX_TOKENS = 1200
RISK_ASSISTANT_TEMPERATURE = 0.2
RISK_ASSISTANT_NEWS_LIMIT = 5
RISK_ASSISTANT_TREND_PERIODS = (5, 15, 30, 60)
DEFAULT_EMAIL_SUBJECT_TEMPLATE = "[金价预警·{level}] {title}"
DEFAULT_EMAIL_BODY_TEMPLATE = """{message}

预警级别: {level}
时间: {time}
当前金价: {price_rmb} RMB/克 / {price_usd} USD/oz
汇率: {rate}

---
金价监控 GoldMonitor
此邮件由程序自动发送，请勿回复。"""
GDELT_NEWS_URL = (
    "https://api.gdeltproject.org/api/v2/doc/doc"
    "?query=(gold%20OR%20xauusd%20OR%20%22gold%20price%22%20OR%20%22central%20bank%20gold%22)"
    "&mode=artlist&format=json&maxrecords=20&sort=hybridrel"
)
NEWS_RSS_SOURCES = [
    {
        "name": "Federal Reserve",
        "kind": "fed",
        "url": "https://www.federalreserve.gov/feeds/press_all.xml",
    },
    {
        "name": "BLS",
        "kind": "macro",
        "url": "https://www.bls.gov/bls_latest.rss",
    },
]


def _configure_logging():
    try:
        os.makedirs(APPDATA_DIR, exist_ok=True)
        file_handler = logging.FileHandler(APP_LOG_PATH, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logging.basicConfig(
            level=logging.INFO,
            handlers=[file_handler],
        )
    except Exception:
        logging.basicConfig(level=logging.INFO)


_configure_logging()
NEWS_KEYWORDS = news_core.NEWS_KEYWORDS
MARKET_SOURCE_DEFAULT_ORDER = {
    "gold": ["sina_gold", "eastmoney_gold", "goldprice", "stooq_gold"],
    "forex": ["sina_forex", "frankfurter_forex", "stooq_forex"],
}
MARKET_SOURCE_HEALTH_KEYS = {
    ("gold", "新浪贵金属"): "sina_gold",
    ("gold", "东方财富"): "eastmoney_gold",
    ("gold", "GoldPrice"): "goldprice",
    ("gold", "Stooq 金价源"): "stooq_gold",
    ("forex", "新浪汇率"): "sina_forex",
    ("forex", "Frankfurter"): "frankfurter_forex",
    ("forex", "Stooq 汇率源"): "stooq_forex",
}
DEFAULT_SETTINGS = {
    "onboarding_started": False,
    "onboarding_completed": False,
    "onboarding_version": 1,
    "onboarding_completed_at": "",
    "startup_enabled": False,
    "startup_to_tray": True,
    "floating_price_enabled": True,
    "floating_price_windows_mode": "floating",
    "floating_price_position_saved": False,
    "floating_price_x": None,
    "floating_price_y": None,
    "floating_price_opacity": 94,
    "floating_price_display_mode": "rmb_usd",
    "floating_price_preset": "compact",
    "floating_price_snap_edge": True,
    "floating_price_always_on_top": False,
    "floating_price_hide_on_fullscreen": True,
    "floating_price_lock_position": False,
    "close_behavior": "ask",
    "close_remembered": False,
    "alert_sound_enabled": True,
    "alert_dialog_enabled": True,
    # 邮件通知
    "smtp_server": "",
    "smtp_port": "465",
    "smtp_encryption": "ssl",
    "smtp_sender": "",
    "smtp_password": "",
    "smtp_recipient": "",
    "webhook_enabled": False,
    "webhook_url": "",
    "webhook_warning_enabled": True,
    "webhook_critical_enabled": True,
    "webhook_volatility_enabled": True,
    "email_warning_enabled": True,
    "email_critical_enabled": True,
    "email_volatility_enabled": True,
    "alert_cooldown_minutes": 30,
    "alert_quiet_start": "",
    "alert_quiet_end": "",
    "email_subject_template": DEFAULT_EMAIL_SUBJECT_TEMPLATE,
    "email_body_template": DEFAULT_EMAIL_BODY_TEMPLATE,
    "daily_digest_enabled": False,
    "daily_digest_time": "20:00",
    "daily_digest_email_enabled": True,
    "daily_digest_webhook_enabled": False,
    # 风险分析助手
    "risk_assistant_enabled": True,
    "risk_assistant_provider": "deepseek",
    "risk_assistant_depth": "standard",
    "deepseek_base_url": "https://api.deepseek.com",
    "deepseek_model": "deepseek-v4-pro",
    "deepseek_api_key": "",
    "openai_compatible_base_url": "",
    "openai_compatible_model": "",
    "openai_compatible_api_key": "",
    "risk_assistant_max_tokens": RISK_ASSISTANT_MAX_TOKENS,
    "risk_assistant_cooldown_seconds": 15,
    "risk_assistant_cache_minutes": 10,
    "market_source_enabled": {
        category: list(keys)
        for category, keys in MARKET_SOURCE_DEFAULT_ORDER.items()
    },
    "market_source_order": {
        category: list(keys)
        for category, keys in MARKET_SOURCE_DEFAULT_ORDER.items()
    },
    "export_dir": "",
}
SECRET_SETTING_KEYS = ("smtp_password", "deepseek_api_key", "openai_compatible_api_key")
CREDENTIAL_SERVICE_NAME = "GoldMonitor"
CREDENTIAL_TARGET_PREFIX = "GoldMonitor:"
VALID_SMTP_ENCRYPTIONS = {"ssl", "tls"}
VALID_CLOSE_BEHAVIORS = {"ask", "minimize_to_tray", "exit"}
VALID_RISK_ASSISTANT_PROVIDERS = {"deepseek", "openai_compatible"}
VALID_RISK_ASSISTANT_DEPTHS = {"quick", "standard", "deep"}
VALID_FLOATING_DISPLAY_MODES = {"rmb_usd", "rmb_only", "usd_only"}
VALID_FLOATING_WINDOWS_MODES = {"floating", "taskbar", "both"}
VALID_FLOATING_PRESETS = set(desktop_ui_core.FLOATING_PRICE_PRESETS)
EXPORT_DIR_CHECK_ACTIONS = ["choose_export_dir", "use_default_export_dir", "open_export_dir"]
FLOATING_PRICE_PRESETS = desktop_ui_core.FLOATING_PRICE_PRESETS
DEEPSEEK_FALLBACK_MODELS = ("deepseek-v4-pro", "deepseek-v4-flash", "deepseek-chat", "deepseek-reasoner")
RISK_STRUCTURED_SECTION_LABELS = (
    ("risk_level", "风险等级"),
    ("trend_direction", "趋势方向"),
    ("data_credibility", "数据可信度"),
    ("main_factors", "主要影响因素"),
    ("watch_range", "观察价格区间"),
    ("follow_up", "后续关注"),
)
THRESHOLD_MODES = ("usd", "rmb")
THRESHOLD_TYPES = ("upper_warning", "upper_critical", "lower_warning", "lower_critical")
WATCH_TARGET_DIRECTIONS = ("rise_to", "fall_to")
WATCH_TARGET_NOTE_LIMIT = 200
DATA_ARCHIVE_UPLOAD_TTL_SECONDS = 15 * 60

# ---------- 运行时状态 ----------
runtime = runtime_state_core.create_runtime_state(
    default_port=DEFAULT_PORT,
    app_name=APP_NAME,
    threshold_modes=THRESHOLD_MODES,
    threshold_types=THRESHOLD_TYPES,
    source_health=market_data_core.SourceMetricsStore(
        SOURCE_METRICS_PATH,
        window_size=SOURCE_METRICS_WINDOW,
    ).load(),
)

_RUNTIME_STATE_ALIASES = {
    name: name
    for name in runtime_state_core.ApplicationRuntimeState.__dataclass_fields__
}
_RUNTIME_STATE_ALIASES.update({
    "_credential_test_store": "credential_test_store",
    "_alert_dialog_lock": "alert_dialog_lock",
    "_alert_dialog_active": "alert_dialog_active",
    "_daily_digest_scheduler_started": "daily_digest_scheduler_started",
    "_market_runtime_instance": "market_runtime_instance",
    "_portfolio_runtime_instance": "portfolio_runtime_instance",
    "_alert_runtime_instance": "alert_runtime_instance",
    "_floating_controller_instance": "floating_controller_instance",
    "_taskbar_controller_instance": "taskbar_controller_instance",
    "_window_instance": "window_instance",
    "_tray_icon": "tray_icon",
    "_macos_status_item": "macos_status_item",
    "_macos_status_delegate": "macos_status_delegate",
    "_macos_status_menu": "macos_status_menu",
    "_macos_status_menu_items": "macos_status_menu_items",
    "_window_hwnd": "window_hwnd",
    "_last_desktop_title": "last_desktop_title",
    "_desktop_runtime_active": "desktop_runtime_active",
    "_floating_hwnd": "floating_hwnd",
    "_floating_thread_started": "floating_thread_started",
    "_floating_window_ready": "floating_window_ready",
    "_floating_lock": "floating_lock",
    "_floating_primary_text": "floating_primary_text",
    "_floating_secondary_text": "floating_secondary_text",
    "_floating_status_text": "floating_status_text",
    "_floating_trend_state": "floating_trend_state",
    "_floating_source_state": "floating_source_state",
    "_floating_drag_state": "floating_drag_state",
    "_floating_positioned": "floating_positioned",
    "_taskbar_hwnd": "taskbar_hwnd",
    "_taskbar_thread_started": "taskbar_thread_started",
    "_taskbar_window_ready": "taskbar_window_ready",
    "_taskbar_lock": "taskbar_lock",
    "_taskbar_price_text": "taskbar_price_text",
    "_taskbar_price_value_text": "taskbar_price_value_text",
    "_taskbar_price_change_text": "taskbar_price_change_text",
    "_taskbar_trend_state": "taskbar_trend_state",
    "_taskbar_source_state": "taskbar_source_state",
    "_taskbar_layout_state": "taskbar_layout_state",
    "_background_fetch_started": "background_fetch_started",
    "_news_fetch_started": "news_fetch_started",
})


class _ApplicationModule(ModuleType):
    def __getattribute__(self, name):
        aliases = ModuleType.__getattribute__(self, "_RUNTIME_STATE_ALIASES")
        state_name = aliases.get(name)
        if state_name:
            state = ModuleType.__getattribute__(self, "runtime")
            return getattr(state, state_name)
        return ModuleType.__getattribute__(self, name)

    def __setattr__(self, name, value):
        aliases = ModuleType.__getattribute__(self, "_RUNTIME_STATE_ALIASES")
        state_name = aliases.get(name)
        if state_name:
            state = ModuleType.__getattribute__(self, "runtime")
            setattr(state, state_name, value)
            return
        ModuleType.__setattr__(self, name, value)


sys.modules[__name__].__class__ = _ApplicationModule


def _set_alert_dialog_active(value):
    runtime.alert_dialog_active = bool(value)


# ---------- 设置与系统集成 ----------
def _current_executable():
    return platform_core.current_executable(
        getattr(sys, "frozen", False),
        sys.executable,
        sys.argv[0],
    )


def _credential_target_name(key):
    return platform_runtime_core.credential_target_name(
        key,
        CREDENTIAL_TARGET_PREFIX,
    )


def _credential_store_override():
    return runtime.credential_test_store if isinstance(runtime.credential_test_store, dict) else None


def _read_windows_credential(key):
    return platform_runtime_core.read_windows_credential(
        key,
        os_name=os.name,
        target_name=lambda name: _credential_target_name(name),
        logger=logging,
    )


def _write_windows_credential(key, value):
    return platform_runtime_core.write_windows_credential(
        key,
        value,
        os_name=os.name,
        target_name=lambda name: _credential_target_name(name),
        logger=logging,
    )


def _delete_windows_credential(key):
    return platform_runtime_core.delete_windows_credential(
        key,
        os_name=os.name,
        target_name=lambda name: _credential_target_name(name),
    )


def _run_macos_security(args):
    return platform_runtime_core.run_macos_security(
        args,
        runner=subprocess.run,
    )


def _read_macos_credential(key):
    return platform_runtime_core.read_macos_credential(
        key,
        sys_platform=sys.platform,
        service_name=CREDENTIAL_SERVICE_NAME,
        run_security=lambda args: _run_macos_security(args),
    )


def _write_macos_credential(key, value):
    return platform_runtime_core.write_macos_credential(
        key,
        value,
        sys_platform=sys.platform,
        service_name=CREDENTIAL_SERVICE_NAME,
        run_security=lambda args: _run_macos_security(args),
        logger=logging,
    )


def _delete_macos_credential(key):
    return platform_runtime_core.delete_macos_credential(
        key,
        sys_platform=sys.platform,
        service_name=CREDENTIAL_SERVICE_NAME,
        run_security=lambda args: _run_macos_security(args),
    )


def read_credential_secret(key):
    return platform_runtime_core.read_credential_secret(
        key,
        store_override=lambda: _credential_store_override(),
        os_name=os.name,
        sys_platform=sys.platform,
        read_windows=lambda name: _read_windows_credential(name),
        read_macos=lambda name: _read_macos_credential(name),
    )


def write_credential_secret(key, value):
    return platform_runtime_core.write_credential_secret(
        key,
        value,
        store_override=lambda: _credential_store_override(),
        os_name=os.name,
        sys_platform=sys.platform,
        write_windows=(
            lambda name, secret: _write_windows_credential(name, secret)
        ),
        delete_windows=lambda name: _delete_windows_credential(name),
        write_macos=(
            lambda name, secret: _write_macos_credential(name, secret)
        ),
        delete_macos=lambda name: _delete_macos_credential(name),
    )


def _settings_options():
    return {
        "valid_smtp_encryptions": VALID_SMTP_ENCRYPTIONS,
        "valid_close_behaviors": VALID_CLOSE_BEHAVIORS,
        "valid_risk_assistant_providers": VALID_RISK_ASSISTANT_PROVIDERS,
        "valid_risk_assistant_depths": VALID_RISK_ASSISTANT_DEPTHS,
        "valid_floating_display_modes": VALID_FLOATING_DISPLAY_MODES,
        "valid_floating_windows_modes": VALID_FLOATING_WINDOWS_MODES,
        "valid_floating_presets": VALID_FLOATING_PRESETS,
        "default_email_subject_template": DEFAULT_EMAIL_SUBJECT_TEMPLATE,
        "default_email_body_template": DEFAULT_EMAIL_BODY_TEMPLATE,
        "risk_assistant_max_tokens": RISK_ASSISTANT_MAX_TOKENS,
        "market_source_defaults": MARKET_SOURCE_DEFAULT_ORDER,
    }


def _settings_store():
    return settings_store_core.SettingsFileStore(
        SETTINGS_PATH,
        defaults=DEFAULT_SETTINGS,
        options=_settings_options(),
        secret_keys=SECRET_SETTING_KEYS,
        read_secret=read_credential_secret,
        write_secret=write_credential_secret,
        credentials_required=os.name == "nt" or sys.platform == "darwin",
        logger=logging,
    )


def apply_stored_secrets(settings):
    return settings_store_core.apply_stored_secrets(settings, SECRET_SETTING_KEYS, read_credential_secret)


def persistable_settings_snapshot(settings, previous_settings=None):
    return settings_store_core.persistable_settings_snapshot(
        settings,
        SECRET_SETTING_KEYS,
        write_credential_secret,
        previous_settings=previous_settings,
        credentials_required=os.name == "nt" or sys.platform == "darwin",
        logger=logging,
    )


def _normalize_settings(raw):
    return settings_store_core.normalize_settings(raw, DEFAULT_SETTINGS, _settings_options())


def load_settings():

    data, error = _settings_store().load()
    runtime.last_settings_error = error or None
    return data


def save_settings(data=None):

    with runtime.settings_lock:
        if data is None:
            data = runtime.app_settings
        normalized = _settings_store().save(data, previous_settings=runtime.app_settings)
        runtime.app_settings = normalized
        runtime.last_settings_error = None
        return dict(runtime.app_settings)


def get_settings_snapshot():
    with runtime.settings_lock:
        return dict(runtime.app_settings)


def mask_secret(value):
    return settings_store_core.mask_secret(value)


def public_settings_snapshot(settings=None):
    snapshot = dict(settings or get_settings_snapshot())
    public = settings_store_core.build_public_settings_snapshot(
        snapshot,
        SECRET_SETTING_KEYS,
        platform=_runtime_platform(),
        platform_capabilities=platform_capabilities(),
    )
    public["export_dir_default"] = EXPORT_DIR
    public["export_dir_effective"] = resolve_export_dir(snapshot)
    public["export_dir_check"] = build_export_dir_check(snapshot)
    public["taskbar_price_state"] = dict(runtime.taskbar_layout_state)
    return public


def diagnostic_settings_snapshot(settings=None):
    return public_settings_snapshot(settings)


def _normalize_volatility_config(raw):
    return targets_core.normalize_volatility_config(raw)


def _normalize_thresholds(raw):
    return targets_core.normalize_thresholds(raw, runtime.thresholds, runtime.volatility_config)


def load_thresholds():
    return targets_core.ThresholdStore(
        THRESHOLDS_PATH,
        runtime.thresholds,
        current_volatility_config=runtime.volatility_config,
    ).load()


def save_thresholds(data=None):
    if data is None:
        data = runtime.thresholds
    return targets_core.ThresholdStore(
        THRESHOLDS_PATH,
        runtime.thresholds,
        current_volatility_config=runtime.volatility_config,
    ).save(data)


def _alert_rule_store(now_factory=None):
    return alert_rules_core.AlertRuleStore(
        ALERT_RULES_PATH,
        now_factory=now_factory or datetime.now,
        id_factory=alert_rules_core.generate_alert_rule_id,
    )


def _get_alert_runtime():
    if runtime.alert_runtime_instance is None:
        runtime.alert_runtime_instance = alert_runtime_core.AlertRuntime(
            runtime,
            rule_store_factory=lambda: _alert_rule_store(),
            load_thresholds=lambda: load_thresholds(),
            load_watch_targets=lambda: load_watch_targets(),
            load_portfolio_alerts=lambda: load_portfolio_alerts(),
            build_portfolio_state=lambda: build_portfolio_state(),
            normalize_volatility=lambda data: _normalize_volatility_config(data),
            save_watch_targets=lambda items=None: save_watch_targets(items),
            emit_event=lambda event, payload: socketio.emit(event, payload),
            emit_alert=lambda entry, title: emit_alert(entry, title),
            get_settings=lambda: get_settings_snapshot(),
            alert_log_reader=lambda limit=None: alert_log_export_entries(limit=limit),
            history_reader=lambda days, limit=1000: _analytics_price_history(days, limit),
            history_timestamp=lambda value: _history_timestamp(value),
            alert_log_export_limit=ALERT_LOG_EXPORT_LIMIT,
            simulation_point_limit=ALERT_RULE_SIMULATION_POINT_LIMIT,
            threshold_modes=THRESHOLD_MODES,
            threshold_types=THRESHOLD_TYPES,
            watch_target_note_limit=WATCH_TARGET_NOTE_LIMIT,
            now_factory=datetime.now,
            logger=logging,
        )
    return runtime.alert_runtime_instance


def _sync_legacy_alert_rule_views():

        return _get_alert_runtime().sync_legacy_views()


def load_alert_rules():

        return _get_alert_runtime().load_rules()


def save_alert_rules(items=None):

        return _get_alert_runtime().save_rules(items)


def get_alert_rules_state():
        return _get_alert_runtime().get_state()


def _find_alert_rule(rule_id):
        return _get_alert_runtime().find_rule(rule_id)


def _find_legacy_alert_rule(source, identifier=None, condition=None):
        return _get_alert_runtime().find_legacy_rule(source, identifier, condition)


def _persist_alert_rule_items(items):
    runtime.alert_rules = save_alert_rules(items)
    return get_alert_rules_state()


def upsert_alert_rule_entry(data):
        return _get_alert_runtime().upsert_rule(data)


def delete_alert_rule_entry(rule_id):
        return _get_alert_runtime().delete_rule(rule_id)


def toggle_alert_rule_entry(rule_id, enabled):
        return _get_alert_runtime().toggle_rule(rule_id, enabled)


def reset_alert_rule_entry(rule_id):
        return _get_alert_runtime().reset_rule(rule_id)


def duplicate_alert_rule_entry(rule_id):
        return _get_alert_runtime().duplicate_rule(rule_id)


def batch_update_alert_rules_entry(rule_ids, action):
        return _get_alert_runtime().batch_update_rules(rule_ids, action)


def _replace_legacy_threshold_rule(mode, threshold_type, value):
        return _get_alert_runtime().replace_legacy_threshold(mode, threshold_type, value)


def _replace_legacy_volatility_rule(data):
        return _get_alert_runtime().replace_legacy_volatility(data)


def _rules_for_legacy_threshold_snapshot(threshold_values, volatility):
        return _get_alert_runtime().rules_for_legacy_snapshot(threshold_values, volatility)


def _alert_profile_store():
    return alert_profiles_core.AlertProfileStore(
        ALERT_PROFILES_PATH,
        dict(runtime.thresholds),
        dict(runtime.volatility_config),
        get_settings_snapshot(),
        now_factory=datetime.now,
    )


def load_alert_profiles():
    return _alert_profile_store().load()


def save_alert_profiles(items=None):
    items = runtime.alert_profiles if items is None else items
    return _alert_profile_store().save(items)


def get_alert_profiles_state(items=None):
    current_items = runtime.alert_profiles if items is None else items
    return alert_profiles_core.alert_profiles_state(
        current_items,
        thresholds=dict(runtime.thresholds),
        volatility_config=dict(runtime.volatility_config),
        settings=get_settings_snapshot(),
    )


def _alert_profile_settings_update(applied_settings):
    if not isinstance(applied_settings, dict):
        return {}
    return {
        key: applied_settings[key]
        for key in alert_profiles_core.ALERT_PROFILE_SETTING_KEYS
        if key in applied_settings
    }


def save_alert_profile_settings(applied_settings):
    update = _alert_profile_settings_update(applied_settings)
    with runtime.settings_lock:
        current = dict(runtime.app_settings)
        current.update(update)
        return save_settings(current)


def _find_alert_profile(profile_id):
    target_id = str(profile_id or "").strip()
    for item in runtime.alert_profiles:
        if item.get("id") == target_id:
            return item
    return None


def _set_runtime_alert_profiles(items):

    runtime.alert_profiles = list(items or [])
    return runtime.alert_profiles


def _clear_alert_cooldown_state():

    runtime.alert_cooldown_state = {}


def _coerce_watch_target_bool(value, default=False):
        return _get_alert_runtime().coerce_watch_target_bool(value, default)


def _generate_watch_target_id():
        return _get_alert_runtime().generate_watch_target_id()


def normalize_watch_target(item, existing=None):
        return _get_alert_runtime().normalize_watch_target(item, existing)


def normalize_watch_targets(items):
        return _get_alert_runtime().normalize_watch_targets(items)


def load_watch_targets():
    return targets_core.WatchTargetStore(
        WATCH_TARGETS_PATH,
        now_factory=datetime.now,
        id_factory=_generate_watch_target_id,
    ).load()


def save_watch_targets(items=None):
    items = runtime.watch_targets if items is None else items
    return targets_core.WatchTargetStore(
        WATCH_TARGETS_PATH,
        now_factory=datetime.now,
        id_factory=_generate_watch_target_id,
    ).save(items)


def get_watch_targets_state():
        return _get_alert_runtime().watch_targets_state()


def _find_watch_target_index(target_id):
        return _get_alert_runtime().find_watch_target_index(target_id)


def upsert_watch_target(data):
        return _get_alert_runtime().upsert_watch_target(data)


def delete_watch_target(target_id):
        return _get_alert_runtime().delete_watch_target(target_id)


def toggle_watch_target(target_id, enabled):
        return _get_alert_runtime().toggle_watch_target(target_id, enabled)


def reset_watch_target(target_id):
        return _get_alert_runtime().reset_watch_target(target_id)


def _generate_review_note_id():
    return review_notes_core.generate_review_note_id()


def _review_note_store(now_factory=None):
    return review_notes_core.ReviewNoteStore(
        REVIEW_NOTES_PATH,
        now_factory=now_factory or datetime.now,
        id_factory=_generate_review_note_id,
    )


def load_review_notes():
    return _review_note_store().load()


def save_review_notes(items=None):
    items = runtime.review_notes if items is None else items
    return _review_note_store().save(items)


def get_review_notes_state():
    with runtime.review_notes_lock:
        return review_notes_core.review_notes_state(runtime.review_notes)


def upsert_review_note(data):

    with runtime.review_notes_lock:
        next_notes, note = review_notes_core.upsert_review_note(
            runtime.review_notes,
            data,
            now_factory=datetime.now,
            id_factory=_generate_review_note_id,
        )
        runtime.review_notes = save_review_notes(next_notes)
        return get_review_notes_state(), note


def delete_review_note_by_id(note_id):

    with runtime.review_notes_lock:
        next_notes, deleted = review_notes_core.delete_review_note(runtime.review_notes, note_id)
        if not deleted:
            return False, get_review_notes_state()
        runtime.review_notes = save_review_notes(next_notes)
        return True, get_review_notes_state()


def _watch_target_price_for_mode(mode):
        return _get_alert_runtime().watch_target_price(runtime, mode)


def _watch_target_triggered(target, current_price):
        return _get_alert_runtime().watch_target_triggered(target, current_price)


def _watch_target_alert_message(target, current_price):
        return _get_alert_runtime().watch_target_alert_message(target, current_price)


def check_watch_targets(now_str):

        return _get_alert_runtime().check_watch_targets(now_str)


def _portfolio_store():
    return portfolio_core.PortfolioPositionStore(
        PORTFOLIO_POSITIONS_PATH,
        now_factory=datetime.now,
        id_factory=portfolio_core.generate_portfolio_position_id,
    )


def _portfolio_transaction_store():
    return portfolio_core.PortfolioTransactionStore(
        PORTFOLIO_TRANSACTIONS_PATH,
        legacy_positions_path=PORTFOLIO_POSITIONS_PATH,
        now_factory=datetime.now,
        id_factory=portfolio_core.generate_portfolio_transaction_id,
        position_id_factory=portfolio_core.generate_portfolio_position_id,
    )


def _portfolio_alert_store():
    return portfolio_alerts_core.PortfolioAlertStore(
        PORTFOLIO_ALERTS_PATH,
        now_factory=datetime.now,
        id_factory=portfolio_alerts_core.generate_portfolio_alert_id,
    )


def load_portfolio_positions():
    return _portfolio_store().load()


def load_portfolio_transactions():
    return _portfolio_transaction_store().load()


def load_portfolio_alerts():
    return _portfolio_alert_store().load()


def save_portfolio_positions(items=None):
    items = runtime.portfolio_positions if items is None else items
    return _portfolio_store().save(items)


def save_portfolio_transactions(items=None):
    items = runtime.portfolio_transactions if items is None else items
    return _portfolio_transaction_store().save(items)


def empty_portfolio_import_backup():
    return portfolio_core.empty_import_backup()


def portfolio_import_backup_state(backup):
    return portfolio_core.import_backup_state(backup)


def load_portfolio_import_backup():
    return portfolio_core.load_import_backup(PORTFOLIO_IMPORT_BACKUP_PATH)


def save_portfolio_import_backup(snapshot, summary=None):
    return portfolio_core.save_import_backup(
        PORTFOLIO_IMPORT_BACKUP_PATH,
        snapshot,
        summary,
        now_factory=datetime.now,
        token_factory=lambda: secrets.token_hex(4),
    )


def clear_portfolio_import_backup():
    return portfolio_core.clear_import_backup(
        PORTFOLIO_IMPORT_BACKUP_PATH,
        now_factory=datetime.now,
    )


def save_portfolio_alerts(items=None):
    items = runtime.portfolio_alerts if items is None else items
    return _portfolio_alert_store().save(items)


def _current_portfolio_prices():
        return _get_portfolio_runtime().current_prices()


def _enrich_portfolio_alert(alert):
        return _get_portfolio_runtime().enrich_alert(alert)


def _attach_portfolio_alerts_to_state(state, alerts):
        return _get_portfolio_runtime().attach_alerts_to_state(state, alerts)


def _build_portfolio_state_from_snapshots(transactions, positions, prices, alerts=None):
        return _get_portfolio_runtime().build_state_from_snapshots(
            transactions, positions, prices, alerts
        )


def build_portfolio_state():
        return _get_portfolio_runtime().build_state()


def _portfolio_analytics_days(value):
        return _get_portfolio_runtime().analytics_days(value)


def _analytics_price_history(days, limit=1000):
    try:
        points = _price_history_store().filter_from_db(minutes=int(days) * 1440, limit=limit)
    except (OSError, sqlite3.Error, ValueError) as exc:
        logging.warning("读取持仓分析价格历史失败: %s", exc)
        points = []
    if points:
        return points
    cutoff = datetime.now() - timedelta(days=int(days))
    return [
        dict(item) for item in runtime.price_archive
        if _history_timestamp(item.get("timestamp"))
        and _history_timestamp(item.get("timestamp")) >= cutoff
    ][-limit:]


def _get_portfolio_runtime():
    if runtime.portfolio_runtime_instance is None:
        runtime.portfolio_runtime_instance = portfolio_runtime_core.PortfolioRuntime(
            runtime,
            save_positions=lambda items=None: save_portfolio_positions(items),
            save_transactions=lambda items=None: save_portfolio_transactions(items),
            save_import_backup=(
                lambda snapshot, summary=None:
                save_portfolio_import_backup(snapshot, summary)
            ),
            clear_import_backup=lambda: clear_portfolio_import_backup(),
            save_alerts=lambda items=None: save_portfolio_alerts(items),
            import_backup_state=lambda backup: portfolio_import_backup_state(backup),
            persist_alert_rules=lambda items: _persist_alert_rule_items(items),
            emit_event=lambda event, payload: socketio.emit(event, payload),
            emit_alert=lambda entry, title: emit_alert(entry, title),
            history_reader=lambda days, limit=1000: _analytics_price_history(days, limit),
            alert_log_reader=lambda limit=None: alert_log_export_entries(limit=limit),
            history_timestamp=lambda value: _history_timestamp(value),
            alert_log_export_limit=ALERT_LOG_EXPORT_LIMIT,
            now_factory=datetime.now,
        )
    return runtime.portfolio_runtime_instance


def build_portfolio_analytics_state(days=90, now=None):
        return _get_portfolio_runtime().build_analytics_state(days=days, now=now)


def _alert_rule_delivery_insight(rule, now=None):
        return _get_alert_runtime().delivery_insight(rule, now=now)


def build_alert_rule_insight(rule_id, days=30, now=None):
        return _get_alert_runtime().build_rule_insight(rule_id, days=days, now=now)


def build_alert_rule_simulation(rule_payload, days=30, now=None):
        return _get_alert_runtime().build_rule_simulation(rule_payload, days=days, now=now)


def _find_portfolio_position_index(position_id):
        return _get_portfolio_runtime().find_position_index(position_id)


def _find_portfolio_transaction_index(transaction_id):
        return _get_portfolio_runtime().find_transaction_index(transaction_id)


def _find_portfolio_alert_index(alert_id):
        return _get_portfolio_runtime().find_alert_index(alert_id)


def _find_portfolio_alert_index_by_position(position_id):
        return _get_portfolio_runtime().find_alert_index_by_position(position_id)


def upsert_portfolio_alert(data):
        return _get_portfolio_runtime().upsert_alert(data)


def reset_portfolio_alert(alert_id):
        return _get_portfolio_runtime().reset_alert(alert_id)


def delete_portfolio_alert(alert_id):
        return _get_portfolio_runtime().delete_alert(alert_id)


def check_portfolio_alerts(now_str):

        return _get_portfolio_runtime().check_alerts(now_str)


def check_alert_rules(now_str=None, now=None):

        return _get_alert_runtime().check_rules(now_str=now_str, now=now)


def upsert_portfolio_position(data):

        return _get_portfolio_runtime().upsert_position(data)


def delete_portfolio_position(position_id):

        return _get_portfolio_runtime().delete_position(position_id)


def upsert_portfolio_transaction(data):

        return _get_portfolio_runtime().upsert_transaction(data)


def delete_portfolio_transaction(transaction_id):

        return _get_portfolio_runtime().delete_transaction(transaction_id)


def import_portfolio_transactions_csv(content):

        return _get_portfolio_runtime().import_transactions_csv(content)


def undo_portfolio_import():

        return _get_portfolio_runtime().undo_import()


def preview_import_portfolio_transactions_csv(content):
        return _get_portfolio_runtime().preview_import(content)


def build_portfolio_csv(kind="positions"):
        return _get_portfolio_runtime().build_csv(kind)


def _startup_command():
    return platform_core.build_startup_command(_current_executable())


def _macos_launch_agent_path():
    return platform_core.macos_launch_agent_path(
        os.path.expanduser("~"),
        MACOS_LAUNCH_AGENT_ID,
    )


def _macos_startup_arguments():
    return platform_core.build_macos_startup_arguments(
        getattr(sys, "frozen", False),
        sys.executable,
        sys.argv[0],
    )


def _set_macos_startup_enabled(enabled):
    return platform_runtime_core.set_macos_startup_enabled(
        enabled,
        path=_macos_launch_agent_path(),
        launch_agent_id=MACOS_LAUNCH_AGENT_ID,
        startup_arguments=_macos_startup_arguments(),
        current_executable=_current_executable(),
        home_dir=os.path.expanduser("~"),
        build_payload=platform_core.build_macos_launch_agent_payload,
        runner=subprocess.run,
    )


def set_startup_enabled(enabled):
    if sys.platform == "darwin":
        return _set_macos_startup_enabled(enabled)
    supported, error = platform_core.startup_support_result(
        enabled,
        sys.platform,
        os.name,
    )
    if supported is not None:
        return supported, error
    return platform_runtime_core.set_windows_startup_enabled(
        enabled,
        run_key_path=RUN_KEY_PATH,
        run_key_name=RUN_KEY_NAME,
        startup_command=_startup_command(),
    )


def _apply_startup_setting(saved):
    ok, error = set_startup_enabled(saved["startup_enabled"])
    if not ok:
        saved = dict(saved)
        saved["startup_enabled"] = False
        saved = save_settings(saved)
    return saved, error


def apply_settings(data):
    saved = save_settings(data)
    saved, error = _apply_startup_setting(saved)
    apply_floating_price_settings(saved)
    return saved, error


def settings_payload_for_import(settings_payload):
    current = get_settings_snapshot()
    return settings_store_core.settings_payload_for_import(settings_payload, current, DEFAULT_SETTINGS, SECRET_SETTING_KEYS)


def apply_persisted_threshold_state(data):

    runtime.thresholds.update({key: data.get(key) for key in runtime.thresholds})
    runtime.volatility_config = _normalize_volatility_config(data.get("volatility_config"))


def is_socket_authorized(auth):
    if not isinstance(auth, dict):
        return False
    token = str(auth.get("token") or "")
    return bool(token) and secrets.compare_digest(token, SOCKET_ACCESS_TOKEN)


def compare_versions(left, right):
    return update_manager_core.compare_versions(left, right)


def _require_https_url(value, label):
    return update_manager_core.require_https_url(value, label)


def _require_official_update_url(value, label, allowed_names=None):
    return update_manager_core.require_official_update_url(
        value,
        label,
        allowed_names,
        official_host=OFFICIAL_UPDATE_HOST,
        official_path_prefix=OFFICIAL_UPDATE_PATH_PREFIX,
    )


def get_update_manifest_url():
    return DEFAULT_UPDATE_MANIFEST_URL


def _platform_update_key():
    return update_manager_core.platform_update_key(sys_platform=sys.platform, os_name=os.name)


def normalize_update_manifest(raw, base_url=None):
    return update_manager_core.normalize_update_manifest(
        raw,
        base_url=base_url,
        platform_key=_platform_update_key(),
        official_host=OFFICIAL_UPDATE_HOST,
        official_path_prefix=OFFICIAL_UPDATE_PATH_PREFIX,
        asset_names=OFFICIAL_UPDATE_ASSET_NAMES,
    )


def normalize_github_release_manifest(raw):
    return update_manager_core.normalize_github_release_manifest(
        raw,
        platform_key=_platform_update_key(),
        official_host=OFFICIAL_UPDATE_HOST,
        official_path_prefix=OFFICIAL_UPDATE_PATH_PREFIX,
        asset_names=OFFICIAL_UPDATE_ASSET_NAMES,
    )


def github_release_api_url_from_manifest(manifest_url):
    return update_manager_core.github_release_api_url_from_manifest(
        manifest_url,
        official_host=OFFICIAL_UPDATE_HOST,
        official_path_prefix=OFFICIAL_UPDATE_PATH_PREFIX,
    )


def _update_request_headers():
    return update_runtime_core.update_request_headers(HTTP_USER_AGENT)


def _get_update_json(url, request_get=None, timeout=REQUEST_TIMEOUT):
    return update_runtime_core.get_update_json(
        url,
        request_get=request_get or requests.get,
        timeout=timeout,
        headers=_update_request_headers(),
    )


def _update_fetch_error_message(manifest_error, api_error):
    return update_runtime_core.update_fetch_error_message(manifest_error, api_error)


def fetch_update_manifest(manifest_url=None, request_get=None):
    return update_runtime_core.fetch_update_manifest(
        manifest_url or get_update_manifest_url(),
        require_official_update_url=lambda *args, **kwargs: _require_official_update_url(
            *args,
            **kwargs,
        ),
        github_release_api_url_from_manifest=(
            lambda url: github_release_api_url_from_manifest(url)
        ),
        get_update_json=lambda url: _get_update_json(
            url,
            request_get=request_get,
        ),
        normalize_update_manifest=lambda raw, base_url=None: normalize_update_manifest(
            raw,
            base_url,
        ),
        normalize_github_release_manifest=lambda raw: normalize_github_release_manifest(raw),
    )


def get_update_status(expose_download=False):
    manifest_url = get_update_manifest_url()
    manifest = fetch_update_manifest(manifest_url)
    return update_manager_core.build_update_status(
        manifest,
        APP_VERSION,
        now=datetime.now(),
        expose_download=expose_download,
    )


PUBLIC_UPDATE_STATUS_KEYS = (
    "state",
    "current_version",
    "latest_version",
    "checked_at",
    "message",
    "notes",
    "progress_percent",
    "downloaded_bytes",
    "total_bytes",
)


def public_update_status(status=None):
    return update_runtime_core.public_update_status(
        status,
        PUBLIC_UPDATE_STATUS_KEYS,
    )


def record_update_status(status):
    return update_runtime_core.record_update_status(
        runtime.last_update_status,
        runtime.last_update_status_lock,
        status,
        PUBLIC_UPDATE_STATUS_KEYS,
    )


def get_last_update_status():
    return update_runtime_core.get_last_update_status(
        runtime.last_update_status,
        runtime.last_update_status_lock,
    )


def emit_update_status(status):
    safe_status = record_update_status(status)
    emit("update_status", safe_status)
    return safe_status


def download_update_installer(update_info, progress_callback=None):
    return update_runtime_core.download_update_installer(
        update_info,
        update_dir=UPDATE_DIR,
        installer_name=UPDATE_INSTALLER_NAME,
        request_get=lambda *args, **kwargs: requests.get(*args, **kwargs),
        proxies=REQ_PROXY,
        progress_callback=progress_callback,
    )


def launch_update_installer(installer_path):
    return update_runtime_core.launch_update_installer(
        installer_path,
        path_exists=lambda path: os.path.exists(path),
        build_installer_launch_plan=lambda path: update_manager_core.build_installer_launch_plan(
            path,
            os_name=os.name,
            sys_platform=sys.platform,
            create_new_process_group=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            detached_process=getattr(subprocess, "DETACHED_PROCESS", 0),
        ),
        popen=lambda *args, **kwargs: subprocess.Popen(*args, **kwargs),
    )


def read_log_tail(max_lines=120):
    return support_files_core.read_log_tail(APP_LOG_PATH, max_lines=max_lines)


def _json_payload_metadata(path):
    return support_files_core.json_payload_metadata(path)


def build_config_backup():
    return operations_runtime_core.build_config_backup(
        app_version=APP_VERSION,
        settings=get_settings_snapshot(),
        settings_defaults=DEFAULT_SETTINGS,
        secret_keys=SECRET_SETTING_KEYS,
        thresholds=runtime.thresholds,
        volatility_config=runtime.volatility_config,
        alert_profiles=get_alert_profiles_state().get("items", []),
        alert_rules=runtime.alert_rules,
        builder=support_files_core.build_config_backup,
        now_factory=datetime.now,
    )


def preview_config_backup(payload):
    return support_files_core.build_config_import_preview(
        payload,
        settings_defaults=DEFAULT_SETTINGS,
        threshold_keys=set(runtime.thresholds) | {"volatility_config"},
        secret_keys=SECRET_SETTING_KEYS,
    )


def resolve_export_dir(settings=None):
    return operations_runtime_core.resolve_export_dir(
        get_settings_snapshot() if settings is None else settings,
        EXPORT_DIR,
    )


def _probe_export_dir_writable(export_dir):
    return operations_runtime_core.probe_export_dir_writable(export_dir)


def build_export_dir_check(settings=None, probe_writer=None):
    return operations_runtime_core.build_export_dir_check(
        resolve_export_dir(settings),
        actions=EXPORT_DIR_CHECK_ACTIONS,
        probe_writer=probe_writer or _probe_export_dir_writable,
    )


def _export_dir_dialog_initial_dir(settings=None):
    return operations_runtime_core.export_dir_dialog_initial_dir(
        resolve_export_dir(settings),
        home_dir=os.path.expanduser("~"),
    )


def _normalize_export_dir_selection(selection):
    return operations_runtime_core.normalize_export_dir_selection(selection)


def build_export_dir_picker_payload(dialog, settings=None):
    return operations_runtime_core.build_export_dir_picker_payload(
        dialog,
        _export_dir_dialog_initial_dir(settings),
    )


def reset_last_export_status():

    with runtime.last_export_status_lock:
        runtime.last_export_status = {}


def get_last_export_status():
    with runtime.last_export_status_lock:
        return dict(runtime.last_export_status) if isinstance(runtime.last_export_status, dict) else {}


def _set_last_export_status(status):

    with runtime.last_export_status_lock:
        runtime.last_export_status = dict(status)


def _export_failure_category(exc):
    return operations_runtime_core.export_failure_category(exc)


def _export_failure_message(category, export_dir):
    return operations_runtime_core.export_failure_message(category, export_dir)


def _build_export_failure_status(filename, export_dir, exc):
    return operations_runtime_core.build_export_failure_status(
        filename,
        export_dir,
        exc,
        now_factory=datetime.now,
    )


def build_export_status_snapshot(settings=None):
    return operations_runtime_core.build_export_status_snapshot(
        build_export_dir_check(settings),
        get_last_export_status(),
    )


def build_export_error_payload(default_message):
    return operations_runtime_core.build_export_error_payload(
        default_message,
        get_last_export_status(),
        build_export_dir_check(),
    )


def build_open_exports_folder_error_payload(export_dir, exc):
    return operations_runtime_core.build_open_exports_folder_error_payload(
        export_dir,
        exc,
        directory_status=build_export_dir_check(),
        now_factory=datetime.now,
    )


def choose_export_dir_for_desktop():
    window = runtime.window_instance
    if not window:
        return {
            "ok": False,
            "message": "当前不是桌面窗口模式，请手动输入导出目录。",
        }
    try:
        import webview

        def open_folder_dialog(initial_dir):
            return window.create_file_dialog(webview.FOLDER_DIALOG, directory=initial_dir)

        return build_export_dir_picker_payload(open_folder_dialog)
    except Exception:
        logging.warning("打开导出目录选择器失败", exc_info=True)
        return {
            "ok": False,
            "message": "无法打开系统目录选择器，请手动输入导出目录。",
        }


def save_export_file(filename, content):
    return operations_runtime_core.save_export_file(
        filename,
        content,
        export_dir=resolve_export_dir(),
        writer=support_files_core.save_export_file,
        set_status=_set_last_export_status,
        now_factory=datetime.now,
    )


def _data_archive_paths():
    return {
        "settings": {"path": SETTINGS_PATH, "kind": "json", "label": "通用设置", "sensitive": True},
        "thresholds": {"path": THRESHOLDS_PATH, "kind": "json", "label": "预警阈值"},
        "alert_rules": {"path": ALERT_RULES_PATH, "kind": "json", "label": "统一预警规则"},
        "alert_profiles": {"path": ALERT_PROFILES_PATH, "kind": "json", "label": "预警策略模板"},
        "watch_targets": {"path": WATCH_TARGETS_PATH, "kind": "json", "label": "目标价观察清单"},
        "portfolio_positions": {"path": PORTFOLIO_POSITIONS_PATH, "kind": "json", "label": "持仓记录"},
        "portfolio_transactions": {"path": PORTFOLIO_TRANSACTIONS_PATH, "kind": "json", "label": "持仓流水"},
        "portfolio_import_backup": {"path": PORTFOLIO_IMPORT_BACKUP_PATH, "kind": "json", "label": "持仓导入备份"},
        "portfolio_alerts": {"path": PORTFOLIO_ALERTS_PATH, "kind": "json", "label": "持仓提醒"},
        "market_cache": {"path": MARKET_CACHE_PATH, "kind": "json", "label": "行情缓存"},
        "source_metrics": {"path": SOURCE_METRICS_PATH, "kind": "json", "label": "数据源滚动指标"},
        "news": {"path": NEWS_CACHE_PATH, "kind": "json", "label": "新闻缓存"},
        "risk_analysis_history": {"path": RISK_ANALYSIS_HISTORY_PATH, "kind": "json", "label": "风险分析历史"},
        "review_notes": {"path": REVIEW_NOTES_PATH, "kind": "json", "label": "复盘笔记"},
        "price_history": {"path": PRICE_HISTORY_PATH, "kind": "json", "label": "价格历史 JSON"},
        "daily_digest_state": {"path": DAILY_DIGEST_STATE_PATH, "kind": "json", "label": "每日摘要状态"},
        "price_history_db": {"path": _price_history_db_path(), "kind": "sqlite", "label": "价格历史数据库"},
        "alert_log_db": {"path": _alert_log_db_path(), "kind": "sqlite", "label": "告警记录数据库"},
    }


def _data_archive_manager(now_factory=None):
    return data_archive_core.DataArchiveManager(
        _data_archive_paths(),
        app_version=APP_VERSION,
        now_factory=now_factory or datetime.now,
    )


def _data_archive_filename(now=None):
    return operations_runtime_core.data_archive_filename(now or datetime.now())


def create_data_archive(now=None):
    now = now or datetime.now()
    return operations_runtime_core.create_data_archive(
        now=now,
        export_dir=resolve_export_dir(),
        settings=get_settings_snapshot(),
        archive_lock=runtime.data_archive_lock,
        manager=_data_archive_manager(now_factory=lambda: now),
        set_status=_set_last_export_status,
        directory_status=build_export_dir_check(),
    )


def _reload_application_data_from_disk():










    return _get_data_archive_runtime().reload_from_disk()


def _get_data_archive_runtime():
    if runtime.data_archive_runtime_instance is None:
        runtime.data_archive_runtime_instance = data_archive_runtime_core.DataArchiveRuntime(
            runtime,
            loaders={
                "settings": lambda: load_settings(),
                "portfolio_positions": lambda: load_portfolio_positions(),
                "portfolio_transactions": lambda: load_portfolio_transactions(),
                "portfolio_import_backup": lambda: load_portfolio_import_backup(),
                "alert_rules": lambda: load_alert_rules(),
                "sync_legacy_alert_rule_views": lambda: _sync_legacy_alert_rule_views(),
                "alert_profiles": lambda: load_alert_profiles(),
                "review_notes": lambda: load_review_notes(),
                "news": lambda: load_news_cache(),
                "risk_analysis_history": lambda: load_risk_analysis_history(),
                "alert_log": lambda: load_alert_log_archive(
                    limit=ALERT_LOG_MEMORY_LIMIT
                ),
                "price_history": lambda: load_price_history_archive(),
            },
            source_health_loader=lambda: market_data_core.SourceMetricsStore(
                SOURCE_METRICS_PATH,
                window_size=SOURCE_METRICS_WINDOW,
            ).load(),
            restore_price_history_state=lambda archive: restore_price_history_state(
                archive
            ),
            initialize_market_cache=lambda: initialize_market_cache(),
            get_settings=lambda: get_settings_snapshot(),
            save_settings=lambda settings: save_settings(settings),
            archive_manager=lambda: _data_archive_manager(),
            apply_floating_price_settings=(
                lambda settings: apply_floating_price_settings(settings)
            ),
        )
    return runtime.data_archive_runtime_instance


def restore_data_archive(archive_path):
    return _get_data_archive_runtime().restore(archive_path)


def _authorized_http_request():
    token = str(request.headers.get("X-GoldMonitor-Token") or "")
    return bool(token) and secrets.compare_digest(token, SOCKET_ACCESS_TOKEN)


def _cleanup_data_archive_uploads(now_monotonic=None):
    return operations_runtime_core.cleanup_uploads(
        runtime.data_archive_uploads,
        runtime.data_archive_upload_lock,
        DATA_ARCHIVE_UPLOAD_TTL_SECONDS,
        now_monotonic=now_monotonic,
        remove=os.remove,
    )


def _store_data_archive_upload(path, preview):
    return operations_runtime_core.store_upload(
        runtime.data_archive_uploads,
        runtime.data_archive_upload_lock,
        path,
        preview,
        cleanup=_cleanup_data_archive_uploads,
        token_factory=lambda: secrets.token_urlsafe(24),
        monotonic_factory=time.monotonic,
    )


def _consume_data_archive_upload(token):
    return operations_runtime_core.consume_upload(
        runtime.data_archive_uploads,
        runtime.data_archive_upload_lock,
        token,
        cleanup=_cleanup_data_archive_uploads,
    )


def open_exports_folder():
    return operations_runtime_core.open_exports_folder(
        resolve_export_dir(),
        build_plan=support_files_core.build_open_folder_plan,
        os_name=os.name,
        sys_platform=sys.platform,
        startfile=getattr(os, "startfile", None),
        popen=subprocess.Popen,
    )


def _normalize_alert_profiles_for_import(alert_profiles_payload):
    return config_runtime_core.normalize_alert_profiles_for_import(
        alert_profiles_payload,
        normalize=lambda payload: _alert_profile_store().normalize(
            payload,
            existing_items=runtime.alert_profiles,
        ),
    )


def _normalize_alert_rules_for_import(alert_rules_payload):
    return config_runtime_core.normalize_alert_rules_for_import(
        alert_rules_payload,
        normalize=alert_rules_core.normalize_alert_rules,
        now_factory=datetime.now,
        id_factory=alert_rules_core.generate_alert_rule_id,
    )


def _alert_profiles_payload_for_import(alert_profiles_payload):
    return config_runtime_core.prepare_alert_profiles_for_import(
        alert_profiles_payload,
        current_thresholds=dict(runtime.thresholds),
        current_volatility_config=dict(runtime.volatility_config),
        current_settings=get_settings_snapshot(),
    )


def _get_config_restore_service():
    if runtime.config_restore_service is None:
        runtime.config_restore_service = config_runtime_core.ConfigRestoreService(
            runtime,
            defaults=DEFAULT_SETTINGS,
            secret_keys=SECRET_SETTING_KEYS,
            paths=lambda: {
                "settings": SETTINGS_PATH,
                "alert_rules": ALERT_RULES_PATH,
                "alert_profiles": ALERT_PROFILES_PATH,
            },
            preview_backup=lambda payload: preview_config_backup(payload),
            settings_payload_for_import=(
                lambda payload: settings_payload_for_import(payload)
            ),
            save_settings=lambda settings: save_settings(settings),
            get_settings=lambda: get_settings_snapshot(),
            save_alert_rules=lambda items: save_alert_rules(items),
            get_alert_rules_state=lambda: get_alert_rules_state(),
            sync_legacy_views=lambda: _sync_legacy_alert_rule_views(),
            rules_for_legacy_snapshot=(
                lambda thresholds, volatility:
                _rules_for_legacy_threshold_snapshot(thresholds, volatility)
            ),
            normalize_alert_profiles=(
                lambda payload: _normalize_alert_profiles_for_import(payload)
            ),
            save_alert_profiles=lambda items: save_alert_profiles(items),
            prepare_alert_profiles=(
                lambda payload: _alert_profiles_payload_for_import(payload)
            ),
            get_alert_profiles_state=lambda: get_alert_profiles_state(),
            apply_startup_setting=lambda settings: _apply_startup_setting(settings),
            apply_settings=lambda settings: apply_settings(settings),
            apply_floating_settings=(
                lambda settings: apply_floating_price_settings(settings)
            ),
            public_settings=lambda settings: public_settings_snapshot(settings),
            emit_event=lambda event, payload: socketio.emit(event, payload),
            now_factory=datetime.now,
            logger=logging,
        )
    return runtime.config_restore_service


def _snapshot_config_import_files(restore_settings, restore_alert_rules, restore_alert_profiles):
        return _get_config_restore_service().snapshot_files(
            restore_settings, restore_alert_rules, restore_alert_profiles
        )


def _restore_config_import_files(snapshots):
    return config_runtime_core.restore_import_files(snapshots)


def _restore_config_import_state(
    previous_settings,
    previous_alert_rules,
    previous_alert_profiles,
    restore_settings,
    restore_alert_rules,
    restore_alert_profiles,
):

        return _get_config_restore_service().restore_state(
            previous_settings,
            previous_alert_rules,
            previous_alert_profiles,
            restore_settings,
            restore_alert_rules,
            restore_alert_profiles,
        )


def restore_config_backup(payload):

        return _get_config_restore_service().restore_backup(payload)


def reset_to_default_settings():

        return _get_config_restore_service().reset_defaults()


ONBOARDING_PREFERENCE_KEYS = {
    "startup_enabled",
    "startup_to_tray",
    "floating_price_enabled",
    "floating_price_display_mode",
    "close_behavior",
    "alert_sound_enabled",
    "alert_dialog_enabled",
    "alert_cooldown_minutes",
}


def start_onboarding():
    current = get_settings_snapshot()
    if current.get("onboarding_started"):
        return public_settings_snapshot(current)
    current["onboarding_started"] = True
    current["onboarding_version"] = 1
    return public_settings_snapshot(save_settings(current))


def complete_onboarding(preferences=None):
    current = get_settings_snapshot()
    if isinstance(preferences, dict):
        current.update({
            key: preferences[key]
            for key in ONBOARDING_PREFERENCE_KEYS
            if key in preferences
        })
    current["close_remembered"] = current.get("close_behavior") != "ask"
    current["onboarding_started"] = True
    current["onboarding_completed"] = True
    current["onboarding_version"] = 1
    current["onboarding_completed_at"] = datetime.now().isoformat(timespec="seconds")
    saved, startup_error = apply_settings(current)
    return {
        "ok": True,
        "settings": public_settings_snapshot(saved),
        "startup_error": startup_error or "",
        "message": "首次使用设置已保存。",
    }


def build_diagnostics_report():
    return _get_diagnostics_runtime().build_report()


def _get_diagnostics_runtime():
    if runtime.diagnostics_runtime_instance is None:
        runtime.diagnostics_runtime_instance = diagnostics_runtime_core.DiagnosticsRuntime(
            runtime,
            app_name=APP_NAME,
            app_version=APP_VERSION,
            paths_builder=lambda: {
                "appdata": APPDATA_DIR,
                "settings": SETTINGS_PATH,
                "thresholds": THRESHOLDS_PATH,
                "alert_rules": ALERT_RULES_PATH,
                "alert_profiles": ALERT_PROFILES_PATH,
                "watch_targets": WATCH_TARGETS_PATH,
                "portfolio_positions": PORTFOLIO_POSITIONS_PATH,
                "portfolio_transactions": PORTFOLIO_TRANSACTIONS_PATH,
                "portfolio_import_backup": PORTFOLIO_IMPORT_BACKUP_PATH,
                "portfolio_alerts": PORTFOLIO_ALERTS_PATH,
                "market_cache": MARKET_CACHE_PATH,
                "source_metrics": SOURCE_METRICS_PATH,
                "update_dir": UPDATE_DIR,
                "exports": resolve_export_dir(),
                "news": NEWS_CACHE_PATH,
                "risk_analysis_history": RISK_ANALYSIS_HISTORY_PATH,
                "review_notes": REVIEW_NOTES_PATH,
                "price_history": PRICE_HISTORY_PATH,
                "daily_digest_state": DAILY_DIGEST_STATE_PATH,
                "price_history_db": _price_history_db_path(),
                "alert_log_db": _alert_log_db_path(),
                "log": APP_LOG_PATH,
            },
            storage_manifest_builder=storage_manifest_core.build_storage_manifest,
            get_fetch_status=lambda: get_fetch_status(),
            get_source_health=lambda: get_source_health_state(),
            get_price_history=lambda **kwargs: build_price_history_state(**kwargs),
            get_watch_targets=lambda: get_watch_targets_state(),
            get_risk_history=lambda: get_risk_analysis_history_state(),
            get_alert_rules=lambda: get_alert_rules_state(),
            get_settings=lambda: diagnostic_settings_snapshot(),
            get_update_status=lambda: get_last_update_status(),
            read_logs=lambda: read_log_tail(),
            health_summary_builder=build_health_summary,
            get_export_status=lambda: build_export_status_snapshot(),
            default_settings=DEFAULT_SETTINGS,
            platform_name=sys.platform,
            now_factory=datetime.now,
        )
    return runtime.diagnostics_runtime_instance


def _diagnostics_report_payload(report=None):
    return diagnostics_runtime_core.diagnostics_report_payload(
        build_diagnostics_report() if report is None else report
    )


def _diagnostics_value(value, empty="未记录"):
    return diagnostics_runtime_core.diagnostics_value(value, empty)


def _diagnostics_source_label(source):
    return diagnostics_runtime_core.diagnostics_source_label(source)


def build_diagnostics_clipboard_text(report=None):
    return _get_diagnostics_runtime().build_clipboard_text(report)


def show_alert_dialog(title, message):
    return notification_runtime_core.show_alert_dialog(
        title,
        message,
        enabled=get_settings_snapshot().get("alert_dialog_enabled", True),
        active_lock=runtime.alert_dialog_lock,
        get_active=lambda: runtime.alert_dialog_active,
        set_active=_set_alert_dialog_active,
        sys_platform=sys.platform,
        os_name=os.name,
        applescript_string=_applescript_string,
        run_applescript=_run_macos_osascript,
        thread_factory=threading.Thread,
        logger=logging,
    )


def play_system_alert_sound(level):
    return notification_runtime_core.play_system_alert_sound(
        level,
        enabled=get_settings_snapshot().get("alert_sound_enabled", True),
        sys_platform=sys.platform,
        path_exists=os.path.exists,
        popen=subprocess.Popen,
        run_applescript=_run_macos_osascript,
    )


def select_related_news(title, items=None, limit=3):
    pool = items if items is not None else runtime.news_items
    return news_core.select_related_news(title, pool, limit=limit)


# ---------- 通知渠道 ----------

_alert_level_map = {"warning": "关注", "critical": "警告", "volatility": "波动"}


class _SafeFormatDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def _format_template(template, values, fallback):
    return notifications_core.format_template(template, values, fallback)


def _time_to_minutes(value):
    return notifications_core.time_to_minutes(value)


def is_alert_quiet_time(settings=None, now=None):
    settings = settings or get_settings_snapshot()
    return notifications_core.is_alert_quiet_time(settings, now=now)


def _alert_cooldown_key(entry):
    return notifications_core.alert_cooldown_key(entry)


def evaluate_alert_delivery(entry, settings=None, now=None):
    settings = settings or get_settings_snapshot()
    return notifications_core.evaluate_alert_delivery(entry, settings, runtime.alert_cooldown_state, now=now)


def build_alert_template_values(alert_type, title, message):
    with runtime.lock:
        market = {
            "price_usd": runtime.price_usd,
            "price_rmb": runtime.price_rmb,
            "usdcny_rate": runtime.usdcny_rate,
            "gold_price_source": runtime.gold_price_source,
            "usdcny_rate_source": runtime.usdcny_rate_source,
        }
    return notifications_core.build_alert_template_values(alert_type, title, message, market, _alert_level_map)


class EmailNotifier:
    """SMTP 邮件通知器"""

    @staticmethod
    def send(alert_type, title, message, timeout=10, blocking=False):
        return notification_runtime_core.send_email_alert(
            alert_type, title, message,
            get_settings=get_settings_snapshot,
            build_values=build_alert_template_values,
            smtp_module=smtplib,
            default_subject_template=DEFAULT_EMAIL_SUBJECT_TEMPLATE,
            default_body_template=DEFAULT_EMAIL_BODY_TEMPLATE,
            timeout=timeout,
            blocking=blocking,
            thread_factory=threading.Thread,
            logger=logging,
        )


class WebhookNotifier:
    """Webhook 通知器"""

    @staticmethod
    def send(alert_type, title, message, timeout=8, blocking=False):
        return notification_runtime_core.send_webhook_alert(
            alert_type, title, message,
            get_settings=get_settings_snapshot,
            build_values=build_alert_template_values,
            post=requests.post,
            require_https_url=_require_https_url,
            app_name="GoldMonitor",
            app_version=APP_VERSION,
            user_agent=HTTP_USER_AGENT,
            proxies=REQ_PROXY,
            timeout=timeout,
            blocking=blocking,
            thread_factory=threading.Thread,
            logger=logging,
        )


class DailyDigestEmailNotifier:
    @staticmethod
    def send(digest, timeout=10, blocking=False):
        return notification_runtime_core.send_daily_digest_email(
            digest,
            get_settings=get_settings_snapshot,
            smtp_module=smtplib,
            timeout=timeout,
            blocking=blocking,
            thread_factory=threading.Thread,
            logger=logging,
        )


class DailyDigestWebhookNotifier:
    @staticmethod
    def send(digest, timeout=8, blocking=False):
        return notification_runtime_core.send_daily_digest_webhook(
            digest,
            get_settings=get_settings_snapshot,
            post=requests.post,
            require_https_url=_require_https_url,
            user_agent=HTTP_USER_AGENT,
            proxies=REQ_PROXY,
            timeout=timeout,
            blocking=blocking,
            thread_factory=threading.Thread,
            logger=logging,
        )


def _notification_status(channel, label, status, message, **details):
    return notifications_core.notification_status(channel, label, status, message, **details)


def _notification_summary(notifications):
    return notifications_core.summarize_notifications(notifications)


def dispatch_alert(entry, title, blocking=True, on_update=None):
    """通知渠道分发: 根据设置决定哪些渠道发送"""
    settings = get_settings_snapshot()
    return notifications_core.dispatch_alert(
        entry,
        title,
        settings,
        email_sender=EmailNotifier.send,
        webhook_sender=WebhookNotifier.send,
        logger=logging,
        blocking=blocking,
        thread_factory=threading.Thread if not blocking else None,
        on_update=on_update,
    )


def _plan_alert_notifications(entry, settings=None):
    return notifications_core.plan_alert_notifications(entry, settings or get_settings_snapshot())


def _persist_alert_notification_update(alert_id, notifications):
    return notification_runtime_core.persist_alert_notification_update(
        alert_id,
        notifications,
        update_entry=_update_alert_log_entry_payload,
        emit=socketio.emit,
    )


def _deliver_alert_notifications(alert_id, entry, title, settings, notifications):
    return notifications_core.deliver_alert_notifications(
        entry,
        title,
        settings,
        email_sender=EmailNotifier.send,
        webhook_sender=WebhookNotifier.send,
        notifications=notifications,
        on_update=lambda items, item: _persist_alert_notification_update(alert_id, items),
        logger=logging,
    )


def _start_alert_notification_delivery(entry, title, settings=None):
    return notification_runtime_core.start_alert_notification_delivery(
        entry,
        title,
        get_settings=lambda: settings or get_settings_snapshot(),
        deliver=_deliver_alert_notifications,
        thread_factory=threading.Thread,
    )


def _daily_digest_state_store(now_factory=None):
    return daily_digest_core.DailyDigestStateStore(
        DAILY_DIGEST_STATE_PATH,
        now_factory=now_factory or datetime.now,
    )


def get_daily_digest_state():
    return _daily_digest_state_store().load()


def selected_daily_digest_channels(settings=None):
    return notification_runtime_core.selected_daily_digest_channels(
        settings or get_settings_snapshot()
    )


def build_daily_digest_snapshot(now=None):
    now = now or datetime.now()
    return notification_runtime_core.build_daily_digest_snapshot(
        now=now,
        build_timeline=build_event_timeline_state,
        build_portfolio=build_portfolio_state,
        get_source_health=get_source_health_state,
        timeline_max_limit=EVENT_TIMELINE_MAX_LIMIT,
        timeline_types=EVENT_TIMELINE_TYPES,
    )


def daily_digest_status_payload(now=None):
    now = now or datetime.now()
    return notification_runtime_core.daily_digest_status_payload(
        now=now,
        settings=get_settings_snapshot(),
        state=get_daily_digest_state(),
    )


def _dispatch_daily_digest(digest, settings, blocking=False):
    return notification_runtime_core.dispatch_daily_digest(
        digest,
        settings,
        email_sender=DailyDigestEmailNotifier.send,
        webhook_sender=DailyDigestWebhookNotifier.send,
        logger=logging,
    )


def run_daily_digest_once(now=None, force=False, manual=False, blocking=False):
    now = now or datetime.now()
    settings = get_settings_snapshot()
    return notification_runtime_core.run_daily_digest_once(
        now=now,
        force=force,
        manual=manual,
        settings=settings,
        lock=runtime.daily_digest_lock,
        state_store=_daily_digest_state_store(now_factory=lambda: now),
        build_digest=lambda value: build_daily_digest_snapshot(now=value),
        email_sender=DailyDigestEmailNotifier.send,
        webhook_sender=DailyDigestWebhookNotifier.send,
        emit_status=socketio.emit,
        status_payload=lambda value: daily_digest_status_payload(now=value),
        logger=logging,
    )


def emit_alert(entry, title):
    settings = get_settings_snapshot()
    return notification_runtime_core.emit_alert(
        entry,
        title,
        settings=settings,
        market_lock=runtime.lock,
        market_price=lambda mode: runtime.price_usd if mode == "usd" else runtime.price_rmb if mode == "rmb" else None,
        generate_id=_generate_alert_log_id,
        evaluate_delivery=evaluate_alert_delivery,
        plan_notifications=_plan_alert_notifications,
        select_news=select_related_news,
        alert_log=runtime.alert_log,
        alert_log_limit=ALERT_LOG_MEMORY_LIMIT,
        save_entry=save_alert_log_entry,
        emit=socketio.emit,
        start_delivery=_start_alert_notification_delivery,
        build_history_state=build_price_history_state,
        local_delivery_enabled=notifications_core.alert_local_delivery_enabled,
        send_desktop_notification=send_desktop_notification,
        play_system_alert_sound=play_system_alert_sound,
        show_alert_dialog=show_alert_dialog,
        now_factory=datetime.now,
        logger=logging,
    )


def initialize_market_cache():

    cached = load_valid_usdcny_cache()
    if cached:
        runtime.usdcny_rate = cached["value"]
        runtime.usdcny_rate_source = cached["source"]
        runtime.usdcny_rate_time = cached["timestamp"]
        runtime.usdcny_rate_cached = True
        runtime.usdcny_rate_error = "启动时使用缓存汇率"


def find_available_port(preferred=DEFAULT_PORT):
    return instance_runtime_core.find_available_port(
        preferred,
        host=DEFAULT_HOST,
        socket_factory=socket.socket,
    )


def local_app_url(host=DEFAULT_HOST, port=DEFAULT_PORT, path="/"):
    return instance_runtime_core.local_app_url(host, port, path)


def is_tcp_port_open(host, port, timeout=0.05):
    return instance_runtime_core.is_tcp_port_open(
        host,
        port,
        timeout=timeout,
        socket_factory=socket.socket,
    )


def is_goldmonitor_health_payload(payload):
    return instance_runtime_core.is_application_health_payload(payload, APP_NAME)


def find_existing_goldmonitor_instance(
    host=DEFAULT_HOST,
    preferred=DEFAULT_PORT,
    port_count=50,
    request_get=None,
    port_probe=None,
    timeout=0.2,
):
    return instance_runtime_core.find_existing_instance(
        host,
        preferred,
        app_name=APP_NAME,
        proxies=REQ_PROXY,
        request_get=request_get or requests.get,
        port_probe=port_probe or (lambda *args: is_tcp_port_open(*args)),
        port_count=port_count,
        timeout=timeout,
    )


def open_existing_goldmonitor_instance(
    host=DEFAULT_HOST,
    port=DEFAULT_PORT,
    desktop_mode=False,
    request_post=None,
    browser_open=None,
    timeout=0.5,
):
    if browser_open is None:
        import webbrowser
        browser_open = webbrowser.open
    return instance_runtime_core.open_existing_instance(
        host,
        port,
        desktop_mode=desktop_mode,
        proxies=REQ_PROXY,
        request_post=request_post or requests.post,
        browser_open=browser_open,
        timeout=timeout,
    )

# ---------- 数据获取 ----------
def _fetch_source_status(ok=None, cached=False, source="", error=""):
    return market_runtime_core.fetch_source_status(ok, cached, source, error)


def build_fetch_status(
    ok,
    message="",
    gold_ok=None,
    forex_ok=None,
    error="",
    retryable=True,
    gold_cached=False,
    forex_cached=False,
    gold_source="",
    forex_source="",
    gold_error="",
    forex_error="",
):
    return market_runtime_core.build_fetch_status(
        ok,
        message,
        gold_ok,
        forex_ok,
        error,
        retryable,
        gold_cached,
        forex_cached,
        gold_source,
        forex_source,
        gold_error,
        forex_error,
        now_factory=datetime.now,
    )


def _current_fetch_status_locked():
    return market_runtime_core.current_fetch_status(runtime, build_fetch_status)


def get_fetch_status():
    with runtime.lock:
        return _current_fetch_status_locked()


def _market_state_locked():
    return market_runtime_core.market_state_snapshot(runtime)


def record_source_health(name, category, ok, error="", started_at=None, cached=False):
    return market_runtime_core.record_runtime_source_health(
        runtime,
        name,
        category,
        ok,
        error=error,
        started_at=started_at,
        cached=cached,
        source_health_keys=MARKET_SOURCE_HEALTH_KEYS,
        source_health_limit=SOURCE_HEALTH_LIMIT,
        metrics_window=SOURCE_METRICS_WINDOW,
        metrics_store=lambda: market_data_core.SourceMetricsStore(
            SOURCE_METRICS_PATH,
            window_size=SOURCE_METRICS_WINDOW,
        ),
        state_builder=get_source_health_state,
        emit=socketio.emit,
        logger=logging,
    )


def get_source_health_state():
    with runtime.lock:
        health_snapshot = {name: dict(item) for name, item in runtime.source_health.items()}
    comparison = get_source_comparison_state()
    adapters = get_market_adapter_catalog(health_snapshot=health_snapshot)
    return market_runtime_core.build_source_health_state(
        health_snapshot,
        comparison=comparison,
        adapters=adapters,
        preferences=get_market_source_preferences(),
        fetch_status=get_fetch_status(),
        window_size=SOURCE_METRICS_WINDOW,
    )


def record_source_price_sample(name, data, cached=False):
    return market_runtime_core.record_runtime_source_price_sample(
        runtime,
        name,
        data,
        cached=cached,
        number_formatter=_format_number,
        now_factory=datetime.now,
    )


def build_source_comparison_state(samples=None):
    if samples is None:
        with runtime.lock:
            samples = [dict(item) for item in runtime.source_price_samples.values()]
    return market_data_core.build_source_comparison_state(
        samples,
        stale_seconds=SOURCE_COMPARISON_STALE_SECONDS,
        anomaly_pct=SOURCE_COMPARISON_ANOMALY_PCT,
    )


def get_source_comparison_state():
    with runtime.lock:
        if runtime.source_comparison_state:
            return json.loads(json.dumps(runtime.source_comparison_state, ensure_ascii=False))
    return build_source_comparison_state()


def _build_market_adapter_registry():
    """构建完整的内置行情源注册表。"""
    return market_clients_core.build_default_registry(
        fetch_sina_gold=lambda: fetch_sina_gold_result(),
        fetch_eastmoney_gold=lambda: fetch_eastmoney_gold_result(),
        fetch_goldprice=lambda: fetch_goldprice_data_result(),
        fetch_stooq_gold=lambda: fetch_gold_data_result(GOLD_URL, "Stooq 金价源"),
        fetch_sina_forex=lambda: fetch_sina_forex_result(),
        fetch_frankfurter_forex=lambda: fetch_frankfurter_forex_result(),
        fetch_stooq_forex=lambda: fetch_csv_price_result(FOREX_URL, "Stooq 汇率源"),
    )


def get_market_source_preferences(settings=None, strict=False, defaults=None):
    settings = settings if isinstance(settings, dict) else get_settings_snapshot()
    return market_adapters_core.normalize_source_preferences(
        settings.get("market_source_enabled"),
        settings.get("market_source_order"),
        defaults or MARKET_SOURCE_DEFAULT_ORDER,
        strict=strict,
    )


def build_market_adapter_registry():
    """按用户启停和排序配置构建运行时行情源注册表。"""
    registry = _build_market_adapter_registry()
    preferences = get_market_source_preferences(
        defaults=market_adapters_core.source_preference_defaults(registry),
    )
    configured, _normalized = market_adapters_core.configure_registry(
        registry,
        preferences["enabled"],
        preferences["order"],
        strict=True,
    )
    return configured


def _market_source_matches(descriptor, source_name):
    return market_runtime_core.market_source_matches(descriptor, source_name)


def get_market_adapter_catalog(health_snapshot=None):
    registry = _build_market_adapter_registry()
    preferences = get_market_source_preferences(
        defaults=market_adapters_core.source_preference_defaults(registry),
    )
    health_snapshot = health_snapshot if isinstance(health_snapshot, dict) else runtime.source_health
    return market_runtime_core.build_market_adapter_catalog(
        registry,
        preferences,
        health_snapshot,
        get_fetch_status(),
    )


def update_market_source_preferences(payload):
    if not isinstance(payload, dict):
        raise ValueError("数据源配置格式无效")
    preferences = market_adapters_core.normalize_source_preferences(
        payload.get("enabled"),
        payload.get("order"),
        MARKET_SOURCE_DEFAULT_ORDER,
        strict=True,
    )
    current = get_settings_snapshot()
    current["market_source_enabled"] = preferences["enabled"]
    current["market_source_order"] = preferences["order"]
    saved = save_settings(current)
    return get_market_source_preferences(saved, strict=True)


def reset_market_source_preferences():
    return update_market_source_preferences({
        "enabled": {
            category: list(keys)
            for category, keys in MARKET_SOURCE_DEFAULT_ORDER.items()
        },
        "order": {
            category: list(keys)
            for category, keys in MARKET_SOURCE_DEFAULT_ORDER.items()
        },
    })


def retry_market_source(source_key):
    adapter = _build_market_adapter_registry().get(source_key)
    if adapter is None:
        raise ValueError("未找到数据源")
    result = adapter.fetch()
    if result.value is not None and adapter.category == "gold":
        record_source_price_sample(adapter.cache_source, result.value)
    return {
        "ok": bool(result.ok),
        "key": adapter.key,
        "name": adapter.name,
        "category": adapter.category,
        "message": "数据源探测成功" if result.ok else (result.error or "数据源探测失败"),
        "source_health": get_source_health_state(),
    }


def refresh_source_comparison(primary_data=None, primary_source="", primary_cached=False):
    return market_runtime_core.refresh_runtime_source_comparison(
        runtime,
        primary_data,
        primary_source,
        primary_cached,
        record_sample=record_source_price_sample,
        registry_builder=build_market_adapter_registry,
        comparison_builder=build_source_comparison_state,
        refresh_seconds=SOURCE_COMPARISON_REFRESH_SECONDS,
        monotonic_factory=time.monotonic,
    )


def fetch_gold_data(url):
    """从 Stooq CSV 解析完整 OHLC 数据"""
    data, _error = fetch_gold_data_result(url)
    return data


def fetch_gold_data_result(url, source_label="数据源"):
    """从 Stooq CSV 解析完整 OHLC 数据，并返回用户可读的失败原因。"""
    category = "gold" if "金价" in source_label else "forex"
    result = market_clients_core.fetch_http_result(
        url,
        source_label,
        lambda payload: market_data_core.parse_stooq_ohlc_csv(payload, source_label),
        category=category,
        timeout=REQUEST_TIMEOUT,
        proxies=REQ_PROXY,
        requests_module=requests,
        fetcher=market_adapters_core.fetch_http_source,
        record_health=record_source_health,
    )
    return result.value, result.error


def fetch_csv_price(url):
    """从 Stooq CSV 仅解析收盘价"""
    data = fetch_gold_data(url)
    return data["close"] if data else None


def fetch_csv_price_result(url, source_label="数据源"):
    """从 Stooq CSV 解析收盘价，并返回用户可读的失败原因。"""
    data, error = fetch_gold_data_result(url, source_label)
    return (data["close"] if data else None), error


def _extract_quoted_payload(text):
    return market_data_core.extract_quoted_payload(text)


def _market_cache_store():
    return market_data_core.MarketCacheStore(
        MARKET_CACHE_PATH,
        max_age_seconds=CACHE_RATE_MAX_AGE_SECONDS,
    )


def _normalize_usdcny_cache(raw):
    return _market_cache_store().normalize_usdcny(raw)


def _normalize_xauusd_cache(raw):
    return _market_cache_store().normalize_xauusd(raw)


def _parse_iso_datetime(value):
    return market_data_core.parse_iso_datetime(value)


def load_usdcny_cache():
    return _market_cache_store().load_usdcny()


def _load_market_cache_payload():
    return _market_cache_store().load_payload()


def _write_market_cache_section(section, data):
    _market_cache_store().write_section(section, data)


def load_xauusd_cache():
    return _market_cache_store().load_xauusd()


def load_valid_xauusd_cache(max_age_seconds=CACHE_RATE_MAX_AGE_SECONDS):
    return _market_cache_store().load_valid_xauusd(max_age_seconds=max_age_seconds)


def load_valid_usdcny_cache(max_age_seconds=CACHE_RATE_MAX_AGE_SECONDS):
    return _market_cache_store().load_valid_usdcny(max_age_seconds=max_age_seconds)


def save_usdcny_cache(value, source, timestamp=None):
    return _market_cache_store().save_usdcny(value, source, timestamp=timestamp)


def save_xauusd_cache(data, source, timestamp=None):
    return _market_cache_store().save_xauusd(data, source, timestamp=timestamp)


def parse_sina_forex(text):
    return market_data_core.parse_sina_forex(text)


def fetch_sina_forex_result():
    result = market_clients_core.fetch_http_result(
        SINA_FOREX_URL,
        "新浪汇率",
        parse_sina_forex,
        category="forex",
        headers={
            "User-Agent": BROWSER_USER_AGENT,
            "Referer": "https://finance.sina.com.cn/",
        },
        timeout=REQUEST_TIMEOUT,
        proxies=REQ_PROXY,
        requests_module=requests,
        fetcher=market_adapters_core.fetch_http_source,
        record_health=record_source_health,
    )
    return result.value, result.error


def parse_frankfurter_forex(payload):
    return market_data_core.parse_frankfurter_forex(payload)


def fetch_frankfurter_forex_result():
    result = market_clients_core.fetch_http_result(
        FRANKFURTER_FOREX_URL,
        "Frankfurter",
        parse_frankfurter_forex,
        category="forex",
        response_type="json",
        headers={"User-Agent": HTTP_USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        proxies=REQ_PROXY,
        requests_module=requests,
        fetcher=market_adapters_core.fetch_http_source,
        record_health=record_source_health,
    )
    return result.value, result.error


def fetch_usdcny_rate_result():
    return market_clients_core.fetch_usdcny_rate_result(
        build_market_adapter_registry(),
        save_cache=save_usdcny_cache,
        load_valid_cache=load_valid_usdcny_cache,
        record_health=record_source_health,
        now_factory=datetime.now,
    )


def parse_sina_gold(text):
    return market_data_core.parse_sina_gold(text)


def fetch_sina_gold_result():
    result = market_clients_core.fetch_http_result(
        SINA_GOLD_URL,
        "新浪贵金属",
        parse_sina_gold,
        category="gold",
        headers={
            "User-Agent": BROWSER_USER_AGENT,
            "Referer": "https://finance.sina.com.cn/futures/quotes/XAU.shtml",
        },
        timeout=REQUEST_TIMEOUT,
        proxies=REQ_PROXY,
        requests_module=requests,
        fetcher=market_adapters_core.fetch_http_source,
        record_health=record_source_health,
    )
    return result.value, result.error


def parse_eastmoney_gold(payload):
    """解析东方财富 XAU 行情，返回 XAU/USD OHLC。"""
    return market_data_core.parse_eastmoney_gold(payload)


def fetch_eastmoney_gold_result():
    """从东方财富公开行情接口获取 XAU/USD，并返回用户可读的失败原因。"""
    result = market_clients_core.fetch_http_result(
        EASTMONEY_GOLD_URL,
        "东方财富",
        parse_eastmoney_gold,
        category="gold",
        response_type="json",
        headers={
            "User-Agent": HTTP_USER_AGENT,
            "Referer": "https://hf-wap.eastmoney.com/quote/stock/122.xau.html",
        },
        timeout=REQUEST_TIMEOUT,
        proxies=REQ_PROXY,
        requests_module=requests,
        fetcher=market_adapters_core.fetch_http_source,
        record_health=record_source_health,
    )
    return result.value, result.error


def parse_goldprice_rates(payload):
    """解析 GoldPrice.org 行情，返回 XAU/USD OHLC 和推导出的 USD/CNY 汇率。"""
    return market_data_core.parse_goldprice_rates(payload)


def fetch_goldprice_data_result():
    """从 GoldPrice.org 公开接口获取实时金价，并返回用户可读的失败原因。"""
    result = market_clients_core.fetch_http_result(
        GOLDPRICE_URL,
        "GoldPrice",
        parse_goldprice_rates,
        category="gold",
        response_type="json",
        headers={"User-Agent": HTTP_USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        proxies=REQ_PROXY,
        requests_module=requests,
        fetcher=market_adapters_core.fetch_http_source,
        record_health=record_source_health,
    )
    return result.value, result.auxiliary_rate, result.error


def fetch_market_data_result():
    """按优先级获取行情数据，避免单一接口失败导致应用一直无数据。"""
    return market_runtime_core.fetch_market_data_result(
        build_market_adapter_registry(),
        save_xauusd_cache=lambda data, source: save_xauusd_cache(data, source),
        save_usdcny_cache=lambda value, source, timestamp: save_usdcny_cache(
            value,
            source,
            timestamp,
        ),
        fetch_usdcny_rate_result=lambda: fetch_usdcny_rate_result(),
        load_valid_xauusd_cache=lambda: load_valid_xauusd_cache(),
        record_source_health=lambda *args, **kwargs: record_source_health(*args, **kwargs),
        now_factory=lambda: datetime.now(),
    )

# ---------- 桌面通知 ----------
def send_desktop_notification(title, body):
    return notification_runtime_core.send_desktop_notification(
        title,
        body,
        sys_platform=sys.platform,
        base_dir=_basedir,
        app_id=APP_USER_MODEL_ID,
        applescript_string=_applescript_string,
        run_applescript=_run_macos_osascript,
        path_exists=os.path.exists,
    )


# ---------- 资讯 ----------
def _is_relevant_news(text):
    return news_core.is_relevant_news(text, NEWS_KEYWORDS)


def classify_news_topic(text, source_kind=""):
    return news_core.classify_news_topic(text, source_kind)


def _parse_gdelt_time(value):
    return news_core.parse_gdelt_time(value, now_factory=datetime.now)


def _parse_rss_time(value):
    return news_core.parse_rss_time(value, now_factory=datetime.now)


def _news_key(item):
    return news_core.news_key(item)


def normalize_news_items(items, limit=NEWS_LIMIT):
    return news_core.normalize_news_items(items, limit=limit, now_factory=datetime.now)


def parse_gdelt_articles(payload):
    return news_core.parse_gdelt_articles(payload, limit=NEWS_LIMIT, now_factory=datetime.now)


def parse_rss_items(xml_text, source_name, source_kind):
    return news_core.parse_rss_items(xml_text, source_name, source_kind, limit=NEWS_LIMIT, now_factory=datetime.now)


def load_news_cache():
    return news_core.NewsCacheStore(NEWS_CACHE_PATH, limit=NEWS_LIMIT, now_factory=datetime.now).load()


def save_news_cache(items):
    return news_core.NewsCacheStore(NEWS_CACHE_PATH, limit=NEWS_LIMIT, now_factory=datetime.now).save(items)


def fetch_gold_news():
    return market_clients_core.fetch_gold_news(
        request_get=requests.get,
        gdelt_url=GDELT_NEWS_URL,
        rss_sources=NEWS_RSS_SOURCES,
        parse_gdelt=parse_gdelt_articles,
        parse_rss=parse_rss_items,
        normalize=normalize_news_items,
        timeout=REQUEST_TIMEOUT,
        proxies=REQ_PROXY,
    )


def refresh_gold_news(emit_update=True):
    return _get_news_runtime().refresh(emit_update=emit_update)


def _get_news_runtime():
    if runtime.news_runtime_instance is None:
        runtime.news_runtime_instance = news_core.NewsRuntime(
            runtime,
            fetch_news=lambda: fetch_gold_news(),
            save_cache=lambda items: save_news_cache(items),
            emit=socketio.emit,
            limit=NEWS_LIMIT,
            now_factory=datetime.now,
        )
    return runtime.news_runtime_instance


def get_news_state():
    return _get_news_runtime().state()


def _risk_history_store():
    return risk_analysis_core.RiskAnalysisHistoryStore(
        RISK_ANALYSIS_HISTORY_PATH,
        history_limit=RISK_ANALYSIS_HISTORY_LIMIT,
        logger=logging,
    )


def normalize_risk_analysis_history(items):
    return _risk_history_store().normalize(items)


def load_risk_analysis_history():
    return _risk_history_store().load()


def save_risk_analysis_history(items=None):
    items = runtime.risk_analysis_history if items is None else items
    return _risk_history_store().save(items)


def get_risk_analysis_history_state():
    with runtime.risk_history_lock:
        return _risk_history_store().build_state(runtime.risk_analysis_history)


def add_risk_analysis_history_entry(result, snapshot):

    with runtime.risk_history_lock:
        store = _risk_history_store()
        runtime.risk_analysis_history, entry = store.add_entry(runtime.risk_analysis_history, result, snapshot)
        try:
            store.save(runtime.risk_analysis_history)
        except OSError as exc:
            logging.warning("failed to save risk analysis history: %s", exc)
        return entry


def clear_risk_analysis_history_state():

    with runtime.risk_history_lock:
        runtime.risk_analysis_history = []
        try:
            _risk_history_store().clear()
        except OSError as exc:
            logging.warning("failed to clear risk analysis history: %s", exc)
        return _risk_history_store().build_state(runtime.risk_analysis_history)


def _price_history_store():
    return PriceHistoryStore(
        PRICE_HISTORY_PATH,
        archive_limit=PRICE_HISTORY_ARCHIVE_LIMIT,
        export_limit=PRICE_HISTORY_EXPORT_LIMIT,
        save_interval_seconds=PRICE_HISTORY_SAVE_INTERVAL_SECONDS,
        logger=logging,
    )


def normalize_price_history(items):
    return _price_history_store().normalize(items)


def _price_history_db_path():
    return _price_history_store().db_path()


def _connect_price_history_db():
    return _price_history_store().connect_db()


def _upsert_price_history_points(items):
    return _price_history_store().upsert_points(items)


def _load_price_history_from_db():
    return _price_history_store().load_from_db()


def _filter_price_history_from_db(minutes=None, limit=600):
    return _price_history_store().filter_from_db(minutes=minutes, limit=limit)


def _load_price_history_json_archive():
    return _price_history_store().load_json_archive()


def load_price_history_archive():
    return _price_history_store().load_archive()


def _write_price_history_json_archive(items):
    return _price_history_store().write_json_archive(items)


def save_price_history_archive(items=None):
    items = runtime.price_archive if items is None else items
    return _price_history_store().save_archive(items)


def add_price_history_entry(entry, force_save=False):

    runtime.price_archive, runtime.last_price_history_save_at, point = _price_history_store().add_entry(
        runtime.price_archive,
        runtime.last_price_history_save_at,
        entry,
        force_save=force_save,
    )
    if point is None:
        return


def _filter_price_archive(minutes=None, limit=600):
    with runtime.lock:
        items = list(runtime.price_archive)
    return _price_history_store().filter_archive(items, minutes=minutes, limit=limit)


def _event_time_from_alert(entry):
    return event_timeline_core.event_time_from_alert(entry, today_date=runtime.today_date)


def normalize_event_timeline_request(data=None):
    return event_timeline_core.normalize_event_timeline_request(
        data,
        event_types=EVENT_TIMELINE_TYPES,
        allowed_minutes=EVENT_TIMELINE_ALLOWED_MINUTES,
        default_minutes=EVENT_TIMELINE_DEFAULT_MINUTES,
        default_limit=EVENT_TIMELINE_DEFAULT_LIMIT,
        max_limit=EVENT_TIMELINE_MAX_LIMIT,
    )


def event_timeline_range(minutes):
    return event_timeline_core.event_timeline_range(minutes, now_factory=datetime.now)


def make_timeline_event(event_type, timestamp, title, summary, source, payload=None, event_id=None):
    return event_timeline_core.make_timeline_event(event_type, timestamp, title, summary, source, payload, event_id)


def build_event_price_summary(points):
    return event_timeline_core.build_event_price_summary(points)


def build_price_summary_timeline_event(points, start_time, end_time):
    return event_timeline_core.build_price_summary_timeline_event(points, start_time, end_time)


def _event_timeline_sources():
    with runtime.risk_history_lock:
        risk_items = list(runtime.risk_analysis_history[:RISK_ANALYSIS_HISTORY_LIMIT])
    with runtime.lock:
        current_news_items = list(runtime.news_items[:NEWS_LIMIT])
    with runtime.review_notes_lock:
        current_review_notes = list(runtime.review_notes)
    return {
        "alert_entries": alert_log_export_entries(limit=ALERT_LOG_EXPORT_LIMIT),
        "risk_items": risk_items,
        "news_items": current_news_items,
        "review_notes": current_review_notes,
        "fetch_status": get_fetch_status(),
        "source_health_state": get_source_health_state(),
        "source_comparison_state": get_source_comparison_state(),
        "today_date": runtime.today_date,
        "news_key": _news_key,
        "now_factory": datetime.now,
    }


def build_alert_timeline_events(start_time, end_time):
    return event_timeline_core.build_alert_timeline_events(
        start_time,
        end_time,
        alert_entries=alert_log_export_entries(limit=ALERT_LOG_EXPORT_LIMIT),
        today_date=runtime.today_date,
    )


def build_risk_timeline_events(start_time, end_time):
    with runtime.risk_history_lock:
        risk_items = list(runtime.risk_analysis_history[:RISK_ANALYSIS_HISTORY_LIMIT])
    return event_timeline_core.build_risk_timeline_events(start_time, end_time, risk_items=risk_items)


def build_news_timeline_events(start_time, end_time):
    with runtime.lock:
        items = list(runtime.news_items[:NEWS_LIMIT])
    return event_timeline_core.build_news_timeline_events(start_time, end_time, news_items=items, news_key=_news_key)


def build_data_status_timeline_events(start_time, end_time):
    return event_timeline_core.build_data_status_timeline_events(
        start_time,
        end_time,
        fetch_status=get_fetch_status(),
        source_health_state=get_source_health_state(),
        source_comparison_state=get_source_comparison_state(),
        now_factory=datetime.now,
    )


def build_event_timeline_events(start_time, end_time, types=None):
    return event_timeline_core.build_event_timeline_events(start_time, end_time, types, **_event_timeline_sources())


def build_event_timeline_state(minutes=None, limit=EVENT_TIMELINE_DEFAULT_LIMIT, types=None):
    points = _filter_price_archive(minutes=minutes, limit=PRICE_HISTORY_EXPORT_LIMIT)
    return event_timeline_core.build_event_timeline_state(
        minutes=minutes,
        limit=limit,
        types=types,
        price_points=points,
        **_event_timeline_sources(),
    )


def _build_price_event_state(items):
    return event_timeline_core.build_price_chart_events(items, build_event_timeline_events)


def alert_level_label(alert_type):
    return event_timeline_core.alert_level_label(alert_type)


def build_price_history_state(minutes=None, limit=600):
    with runtime.lock:
        items = list(runtime.price_archive)
    return _price_history_store().build_state(
        items,
        minutes=minutes,
        limit=limit,
        build_events=_build_price_event_state,
        format_number=_format_number,
    )


def build_price_history_csv(minutes=None):
    with runtime.lock:
        items = list(runtime.price_archive)
    return _price_history_store().build_csv(items, minutes=minutes)


def build_review_report(timeline_state):
    return event_timeline_core.build_review_report(timeline_state)


def save_review_report(content, filename=None):
    if not filename:
        filename = event_timeline_core.review_report_filename(prefix=REVIEW_REPORT_EXPORT_PREFIX)
    return save_export_file(filename, content)


def _alert_log_store():
    return AlertLogStore(
        APPDATA_DIR,
        memory_limit=ALERT_LOG_MEMORY_LIMIT,
        db_limit=ALERT_LOG_DB_LIMIT,
        export_limit=ALERT_LOG_EXPORT_LIMIT,
        logger=logging,
    )


def _alert_log_db_path():
    return _alert_log_store().db_path()


def _generate_alert_log_id():
    return AlertLogStore.generate_id()


def _coerce_alert_log_bool(value, default=False):
    return AlertLogStore.coerce_bool(value, default)


def normalize_alert_log_entry(entry, default_read=False):
    return _alert_log_store().normalize_entry(entry, default_read=default_read)


def _connect_alert_log_db():
    return _alert_log_store().connect_db()


def save_alert_log_entry(entry):
    return _alert_log_store().save_entry(entry)


def load_alert_log_archive(limit=ALERT_LOG_MEMORY_LIMIT):
    return _alert_log_store().load_archive(limit=limit)


def clear_alert_log_archive():
    return _alert_log_store().clear_archive()


def _apply_alert_log_status(entry, read=None, acknowledged=None):
    return _alert_log_store().apply_status(entry, read=read, acknowledged=acknowledged)


def _apply_alert_log_handling(entry, handled=None, note=None):
    return _alert_log_store().apply_handling(entry, handled=handled, note=note)


def _replace_alert_log_entry(updated):
    return AlertLogStore.replace_memory_entry(runtime.alert_log, updated)


def _update_alert_log_entry_payload(alert_id, updater):
    return _alert_log_store().update_entry_payload(alert_id, updater, memory_entries=runtime.alert_log)


def update_alert_log_status(alert_id, read=None, acknowledged=None):
    return _update_alert_log_entry_payload(
        alert_id,
        lambda entry: _apply_alert_log_status(entry, read=read, acknowledged=acknowledged),
    )


def update_alert_log_handling(alert_id, handled=None, note=None):
    return _update_alert_log_entry_payload(
        alert_id,
        lambda entry: _apply_alert_log_handling(entry, handled=handled, note=note),
    )


def _alert_resend_title(entry):
    return str(entry.get("title") or f"金价预警 - {alert_level_label(entry.get('type'))}")


def resend_alert_notification(alert_id, blocking=False, start_delivery=True):
    return notification_runtime_core.resend_alert_notification(
        alert_id,
        settings=get_settings_snapshot(),
        blocking=blocking,
        start_delivery=start_delivery,
        update_entry=_update_alert_log_entry_payload,
        plan_notifications=_plan_alert_notifications,
        summarize_notifications=_notification_summary,
        deliver_notifications=_deliver_alert_notifications,
        persist_update=_persist_alert_notification_update,
        start_notification_delivery=_start_alert_notification_delivery,
        title_builder=_alert_resend_title,
        now_factory=datetime.now,
    )


def alert_log_export_entries(limit=ALERT_LOG_EXPORT_LIMIT):
    return _alert_log_store().export_entries(runtime.alert_log, limit=limit)


def _format_alert_notifications(entry):
    return AlertLogStore.format_notifications(entry)


def build_alert_log_csv():
    return _alert_log_store().build_csv(runtime.alert_log)


def _history_number(value):
    return price_history_core.history_number(value)


def _history_timestamp(value):
    return price_history_core.history_timestamp(value)


def _kline_bucket_start(timestamp):
    return price_history_core.kline_bucket_start(timestamp)


def _ohlc(values):
    return price_history_core.ohlc(values)


def build_5min_klines(history_items, limit=96):
    return price_history_core.build_5min_klines(history_items, limit=limit)


def restore_price_history_state(archive):
    runtime.price_history = list((archive or [])[-360:])
    runtime.klines_5min = build_5min_klines(runtime.price_history, limit=96)


def _application_state_bootstrap():
    return application_state_bootstrap_core.ApplicationStateBootstrap(
        runtime=runtime,
        loaders={
            "settings": lambda: load_settings(),
            "alert_rules": lambda: load_alert_rules(),
            "alert_profiles": lambda: load_alert_profiles(),
            "review_notes": lambda: load_review_notes(),
            "portfolio_positions": lambda: load_portfolio_positions(),
            "portfolio_transactions": lambda: load_portfolio_transactions(),
            "portfolio_import_backup": lambda: load_portfolio_import_backup(),
            "news": lambda: load_news_cache(),
            "risk_analysis_history": lambda: load_risk_analysis_history(),
            "alert_log": lambda **kwargs: load_alert_log_archive(**kwargs),
            "price_history": lambda: load_price_history_archive(),
        },
        save_settings=lambda settings: save_settings(settings),
        sync_legacy_alert_rule_views=lambda: _sync_legacy_alert_rule_views(),
        restore_price_history_state=lambda archive: restore_price_history_state(
            archive
        ),
        initialize_market_cache=lambda: initialize_market_cache(),
        settings_file_existed_at_startup=SETTINGS_FILE_EXISTED_AT_STARTUP,
        onboarding_marker_present_at_startup=(
            SETTINGS_ONBOARDING_MARKER_PRESENT_AT_STARTUP
        ),
        alert_log_memory_limit=ALERT_LOG_MEMORY_LIMIT,
        now_factory=lambda: datetime.now(),
        logger=logging,
    )


def initialize_application_state():
    return _application_state_bootstrap().initialize()


def news_loop():
    return _get_news_runtime().run_loop(
        interval=NEWS_REFRESH_INTERVAL,
        sleep=time.sleep,
    )


def _format_number(value, digits=2):
    return risk_analysis_core.format_number(value, digits)


def _valid_market_price(value):
    return risk_analysis_core.valid_market_price(value)


def risk_analysis_market_data_error():
    with runtime.lock:
        return risk_analysis_core.market_data_error(runtime.price_usd, runtime.price_rmb)


def _summarize_price_series(points, field):
    return risk_analysis_core.summarize_price_series(points, field)


def _summarize_klines(candles):
    return risk_analysis_core.summarize_klines(candles)


def _parse_iso_datetime(value):
    return risk_analysis_core.parse_iso_datetime(value)


def _history_window(points, minutes):
    return risk_analysis_core.history_window(points, minutes, now_factory=datetime.now)


def _trend_direction(summary):
    return risk_analysis_core.trend_direction(summary)


def build_multi_period_trends(history):
    return risk_analysis_core.build_multi_period_trends(
        history,
        RISK_ASSISTANT_TREND_PERIODS,
        now_factory=datetime.now,
    )


def assess_risk_data_quality(context):
    return risk_analysis_core.assess_data_quality(context, now_factory=datetime.now)


def build_risk_scorecard(context):
    return risk_analysis_core.build_risk_scorecard(context)


def build_risk_analysis_context(trigger=None, depth=None):
    return risk_analysis_core.build_context_from_runtime(
        runtime,
        get_settings_snapshot(),
        trigger=trigger,
        depth=depth,
        valid_depths=VALID_RISK_ASSISTANT_DEPTHS,
        trend_periods=RISK_ASSISTANT_TREND_PERIODS,
        news_limit=RISK_ASSISTANT_NEWS_LIMIT,
        source_health=get_source_health_state(),
        now_factory=datetime.now,
    )


def _risk_model_client():
    return risk_analysis_core.RiskModelClient(
        request_client=requests,
        default_settings=DEFAULT_SETTINGS,
        fallback_models=DEEPSEEK_FALLBACK_MODELS,
        user_agent=HTTP_USER_AGENT,
        request_timeout=REQUEST_TIMEOUT,
        assistant_timeout=RISK_ASSISTANT_TIMEOUT,
        max_tokens_default=RISK_ASSISTANT_MAX_TOKENS,
        temperature=RISK_ASSISTANT_TEMPERATURE,
        proxies=REQ_PROXY,
        section_labels=RISK_STRUCTURED_SECTION_LABELS,
    )


def build_risk_analysis_snapshot(context):
    return risk_analysis_core.build_snapshot(context)


def parse_risk_analysis_sections(content):
    return risk_analysis_core.parse_sections(content, RISK_STRUCTURED_SECTION_LABELS)


def build_risk_analysis_cache_key(snapshot):
    return risk_analysis_core.build_cache_key(snapshot)


def find_recent_risk_analysis_cache(snapshot, cache_minutes):
    with runtime.risk_history_lock:
        return risk_analysis_core.find_recent_cache(runtime.risk_analysis_history, snapshot, cache_minutes)


def selected_risk_model_config(settings, provider=None):
    return _risk_model_client().selected_model_config(settings, provider)


def test_risk_model_availability(settings):
    return _risk_model_client().test_availability(settings, VALID_RISK_ASSISTANT_PROVIDERS)


def build_risk_analysis_messages(context):
    return risk_analysis_core.build_messages(context)


def _chat_completions_url(base_url):
    return risk_analysis_core.chat_completions_url(base_url)


def _models_url(base_url):
    return risk_analysis_core.models_url(base_url)


def fetch_risk_model_options(settings, provider=None):
    return _risk_model_client().fetch_model_options(settings, provider)


def call_openai_chat_completion(settings, context, provider, base_url, model, api_key):
    return _risk_model_client().call_chat_completion(settings, context, provider, base_url, model, api_key)


def call_deepseek_risk_analysis(settings, context):
    return _risk_model_client().call_deepseek(settings, context)


def call_openai_compatible_risk_analysis(settings, context):
    return _risk_model_client().call_openai_compatible(settings, context)


def run_risk_analysis(settings, context):
    return _risk_model_client().run(settings, context)


def build_risk_analysis_error_payload(message, settings=None, snapshot=None):
    payload = {
        "message": message,
        "diagnostic": risk_analysis_core.build_error_diagnostic(message, settings or get_settings_snapshot(), snapshot),
    }
    if snapshot is not None:
        payload["snapshot"] = snapshot
    return payload


# ---------- 行情运行时 ----------
def _market_runtime_state():
    return market_runtime_core.runtime_state_snapshot(runtime)


def _apply_market_runtime_state(state):
    market_runtime_core.commit_runtime_state(runtime, state)


def _aggregate_klines():
    """从 price_history 聚合 5 分钟 K 线。"""

    runtime.klines_5min = market_runtime_core.aggregate_klines(
        runtime.price_history,
        build_5min_klines,
        limit=96,
    )


runtime.market_runtime_instance = None


def _get_market_runtime():

    if runtime.market_runtime_instance is None:
        runtime.market_runtime_instance = market_runtime_core.MarketRuntime(
            state_getter=_market_runtime_state,
            state_committer=_apply_market_runtime_state,
            state_lock=runtime.lock,
            refresh_lock=runtime.price_refresh_lock,
            fetch_market_data_result=lambda: fetch_market_data_result(),
            refresh_source_comparison=lambda *args, **kwargs: refresh_source_comparison(
                *args,
                **kwargs,
            ),
            get_source_comparison_state=lambda: get_source_comparison_state(),
            aggregate_klines=lambda history: market_runtime_core.aggregate_klines(
                history,
                build_5min_klines,
                limit=96,
            ),
            add_price_history_entry=lambda entry: add_price_history_entry(entry),
            emit=lambda event, payload: socketio.emit(event, payload),
            build_fetch_status=lambda *args, **kwargs: build_fetch_status(*args, **kwargs),
            build_price_history_state=lambda **kwargs: build_price_history_state(**kwargs),
            format_price_title=lambda rmb, usd: format_price_title(rmb, usd),
            update_desktop_price_title=lambda title: update_desktop_price_title(title),
            update_floating_price=lambda rmb, usd, pct: update_floating_price(rmb, usd, pct),
            check_alert_rules=lambda *args, **kwargs: check_alert_rules(*args, **kwargs),
            now_factory=lambda: datetime.now(),
            ounce_to_gram=OZ_TO_GRAM,
        )
    return runtime.market_runtime_instance


def fetch_price_once():
    return _get_market_runtime().fetch_once()


def background_loop():
    market_runtime_core.background_loop(
        lambda: fetch_price_once(),
        interval=10,
        sleep=time.sleep,
    )


# ---------- 阈值检查 (多级) ----------
def _check_thresholds(mode, price, now_str):
    plan = targets_core.build_threshold_alert(
        mode,
        price,
        now_str,
        runtime.thresholds,
        runtime.alerted_flags,
        usdcny_rate=runtime.usdcny_rate,
        usdcny_rate_cached=runtime.usdcny_rate_cached,
        usdcny_rate_source=runtime.usdcny_rate_source,
    )
    if plan:
        emit_alert(plan["alert"], plan["title"])


# ---------- 波动率检查 ----------
def _check_volatility(now_str):

    plan, runtime.last_volatility_check = targets_core.build_volatility_alert(
        runtime.price_history,
        runtime.volatility_config,
        now_str,
        last_checked_at=runtime.last_volatility_check,
        now_factory=datetime.now,
    )
    if plan:
        emit_alert(plan["alert"], plan["title"])


def _price_api_state():
    with runtime.lock:
        return app_state_core.build_price_api_state(_market_state_locked())


def _health_api_state():
    return {
        "port": runtime.server_port,
        "desktop": bool(runtime.desktop_runtime_active),
    }


def _activate_application():
    if runtime.desktop_runtime_active:
        if sys.platform == "darwin":
            _call_macos_main(show_main_window)
        else:
            show_main_window()
    return {
        "ok": True,
        "desktop": bool(runtime.desktop_runtime_active),
        "port": runtime.server_port,
    }


def _build_socket_init_state():
    return app_state_core.build_runtime_socket_init_state(
        runtime,
        market_state=_market_state_locked,
        get_watch_targets=get_watch_targets_state,
        get_portfolio=build_portfolio_state,
        get_settings=public_settings_snapshot,
        get_fetch_status=_current_fetch_status_locked,
        get_source_health=get_source_health_state,
        get_source_comparison=get_source_comparison_state,
        get_price_history=build_price_history_state,
        get_alert_rules=get_alert_rules_state,
        get_alert_profiles=get_alert_profiles_state,
        get_daily_digest_status=daily_digest_status_payload,
        get_news=get_news_state,
        get_risk_history=get_risk_analysis_history_state,
    )


initialize_application_state()


_http_handlers = http_routes_core.register_http_routes(
    app,
    jsonify=jsonify,
    render_template=render_template,
    send_from_directory=send_from_directory,
    request=request,
    base_dir=_basedir,
    socket_access_token=SOCKET_ACCESS_TOKEN,
    app_name=APP_NAME,
    app_version=APP_VERSION,
    get_price_state=_price_api_state,
    get_health_state=_health_api_state,
    activate_application=_activate_application,
    authorized_request=_authorized_http_request,
    archive_manager=lambda: _data_archive_manager(),
    store_upload=_store_data_archive_upload,
    consume_upload=_consume_data_archive_upload,
    restore_archive=lambda path: restore_data_archive(path),
    emit=lambda event, payload: socketio.emit(event, payload),
    logger=logging,
)
index = _http_handlers["index"]
api_price = _http_handlers["api_price"]
api_health = _http_handlers["api_health"]
api_activate = _http_handlers["api_activate"]
api_preview_data_archive = _http_handlers["api_preview_data_archive"]
api_restore_data_archive = _http_handlers["api_restore_data_archive"]
favicon = _http_handlers["favicon"]
manifest = _http_handlers["manifest"]
service_worker = _http_handlers["service_worker"]
static_files = _http_handlers["static_files"]


def _broadcast_alert_rule_views(state=None):
    state = state or get_alert_rules_state()
    socketio.emit("alert_rules_updated", state)
    socketio.emit("thresholds_updated", dict(runtime.thresholds))
    socketio.emit("volatility_updated", dict(runtime.volatility_config))
    socketio.emit("watch_targets_updated", get_watch_targets_state())
    socketio.emit("portfolio_updated", build_portfolio_state())
    return state


def _restore_alert_profile_apply_state(
    previous_alert_rules,
    previous_settings,
    previous_alert_cooldown_state,
):

    rollback_ok = True
    try:
        runtime.alert_rules = save_alert_rules(previous_alert_rules)
    except alert_rules_core.AlertRuleStoreError:
        rollback_ok = False
        runtime.alert_rules = [dict(rule) for rule in previous_alert_rules]
        _sync_legacy_alert_rule_views()

    try:
        save_settings(previous_settings)
    except OSError:
        rollback_ok = False
        with runtime.settings_lock:
            runtime.app_settings.clear()
            runtime.app_settings.update(previous_settings)

    runtime.alert_cooldown_state = dict(previous_alert_cooldown_state)
    return rollback_ok


def _set_risk_analysis_last_started(value):

    runtime.risk_analysis_last_started = value


_base_socket_handlers = socket_bootstrap_core.register_socket_handlers(
    sys.modules[__name__]
)
on_connect = _base_socket_handlers["connect"]
on_close_choice = _base_socket_handlers["close_choice"]
on_get_news = _base_socket_handlers["get_news"]
on_refresh_price = _base_socket_handlers["refresh_price"]
on_refresh_news = _base_socket_handlers["refresh_news"]


def _set_window_instance(value):

    runtime.window_instance = value


def _set_tray_icon(value):

    runtime.tray_icon = value


def _set_window_hwnd(value):

    runtime.window_hwnd = value


def _set_background_fetch_started(value):

    runtime.background_fetch_started = bool(value)


def _set_news_fetch_started(value):

    runtime.news_fetch_started = bool(value)


def _set_daily_digest_scheduler_started(value):

    runtime.daily_digest_scheduler_started = bool(value)


def _set_floating_hwnd(value):

    runtime.floating_hwnd = value


def _set_floating_drag_state(value):

    runtime.floating_drag_state = value


def _set_floating_positioned(value):

    runtime.floating_positioned = bool(value)


def _set_macos_status_state(state):


    runtime.macos_status_item = state.get("status_item")
    runtime.macos_status_delegate = state.get("delegate")
    runtime.macos_status_menu = state.get("menu")
    runtime.macos_status_menu_items = dict(state.get("menu_items") or {})


def _set_last_desktop_title(value):

    runtime.last_desktop_title = str(value or APP_NAME)


def format_price_title(rmb=None, usd=None):
    if rmb is None and usd is None:
        with runtime.lock:
            rmb = runtime.price_rmb
            usd = runtime.price_usd
    return desktop_ui_core.format_price_title(APP_NAME, rmb=rmb, usd=usd)


def format_macos_status_title():
    settings = get_settings_snapshot()
    with runtime.lock:
        rmb = runtime.price_rmb
        usd = runtime.price_usd
    return desktop_ui_core.format_macos_status_title(settings, rmb, usd)


def _call_macos_main(callback):
    return desktop_status_core.call_macos_main(
        callback,
        sys_platform=sys.platform,
    )


def _refresh_macos_status_item():
    return desktop_status_core.refresh_macos_status_item(
        sys_platform=sys.platform,
        get_status_item=lambda: runtime.macos_status_item,
        get_menu_items=lambda: runtime.macos_status_menu_items,
        format_status_title=lambda: format_macos_status_title(),
        format_price_title=lambda: format_price_title(),
        get_settings=lambda: get_settings_snapshot(),
        call_main=lambda callback: _call_macos_main(callback),
    )


def create_macos_status_item():
    return desktop_status_core.create_macos_status_item(
        sys_platform=sys.platform,
        get_status_item=lambda: runtime.macos_status_item,
        set_status_state=_set_macos_status_state,
        show_window=lambda: show_main_window(),
        refresh_price=lambda: _refresh_price_from_tray_menu(),
        open_risk_analysis=lambda: _open_risk_analysis_from_tray_menu(),
        toggle_price=lambda: _toggle_floating_price_from_tray_menu(),
        exit_application=lambda: exit_app(),
        refresh_status=lambda: _refresh_macos_status_item(),
        logger=logging,
    )


def update_desktop_price_title(title=None):
    title = title or format_price_title()
    return desktop_status_core.update_desktop_price_title(
        title,
        last_title=lambda: runtime.last_desktop_title,
        set_last_title=_set_last_desktop_title,
        get_window=lambda: runtime.window_instance,
        get_tray_icon=lambda: runtime.tray_icon,
        refresh_status=lambda: _refresh_macos_status_item(),
    )


def _get_floating_controller():
    if runtime.floating_controller_instance is None:
        runtime.floating_controller_instance = (
            floating_controller_core.FloatingPriceController(
                runtime=runtime,
                default_settings=DEFAULT_SETTINGS,
                presets=FLOATING_PRICE_PRESETS,
                os_name=lambda: os.name,
                sys_platform=lambda: sys.platform,
                get_settings=lambda: get_settings_snapshot(),
                save_settings=lambda snapshot: save_settings(snapshot),
                public_settings_snapshot=(
                    lambda snapshot=None: public_settings_snapshot(snapshot)
                ),
                emit=lambda event, payload: socketio.emit(event, payload),
                show_main_window=lambda: show_main_window(),
                fetch_price_once=lambda: fetch_price_once(),
                refresh_macos_status_item=lambda: _refresh_macos_status_item(),
                start_background_task=(
                    lambda target: threading.Thread(
                        target=target,
                        daemon=True,
                    ).start()
                ),
                apply_display_settings=(
                    lambda settings: apply_floating_price_settings(settings)
                ),
                logger=logging,
            )
        )
    return runtime.floating_controller_instance


def _get_taskbar_controller():
    if runtime.taskbar_controller_instance is None:
        runtime.taskbar_controller_instance = taskbar_controller_core.TaskbarPriceController(
            runtime=runtime,
            os_name=lambda: os.name,
            get_settings=lambda: get_settings_snapshot(),
            save_settings=lambda snapshot: save_settings(snapshot),
            public_settings_snapshot=(
                lambda snapshot=None: public_settings_snapshot(snapshot)
            ),
            emit=lambda event, payload: socketio.emit(event, payload),
            show_main_window=lambda: show_main_window(),
            fetch_price_once=lambda: fetch_price_once(),
            start_background_task=(
                lambda target: threading.Thread(
                    target=target,
                    daemon=True,
                ).start()
            ),
            apply_display_settings=(
                lambda settings: apply_floating_price_settings(settings)
            ),
            logger=logging,
        )
    return runtime.taskbar_controller_instance


def format_floating_price_text(rmb=None, usd=None, pct=None):
    return _get_floating_controller().format_price_text(rmb, usd, pct)


def _is_floating_price_available():
    return _get_floating_controller().is_available()


def _floating_window_metrics():
    return _get_floating_controller().window_metrics()


def _floating_rect(rect_config, width, height):
    return _get_floating_controller().floating_rect(rect_config, width, height)


def _floating_window_size():
    return _get_floating_controller().window_size()


def _floating_window_radius():
    return _get_floating_controller().window_radius()


def _apply_floating_window_corner_preference(hwnd):
    return _get_floating_controller().apply_window_corner_preference(hwnd)


def _get_work_area(user32):
    return _get_floating_controller().get_work_area(user32)


def _clamp_floating_position(x, y, user32=None):
    return _get_floating_controller().clamp_position(x, y, user32)


def _default_floating_position(user32, width, height):
    return _get_floating_controller().default_position(user32, width, height)


def _snap_floating_position(x, y, user32=None):
    return _get_floating_controller().snap_position(x, y, user32)


def _resolve_floating_position(user32, width, height):
    return _get_floating_controller().resolve_position(user32, width, height)


def _save_floating_position(x, y):
    return _get_floating_controller().save_position(x, y)


def _position_floating_window(hwnd, user32=None, x=None, y=None):
    return _get_floating_controller().position_window(hwnd, user32, x, y)


def _invalidate_floating_window():
    return _get_floating_controller().invalidate_window()


def _set_floating_window_visible(visible):
    return _get_floating_controller().set_window_visible(visible)


def _set_floating_price_enabled(enabled):
    return _get_floating_controller().set_enabled(enabled)


def _apply_floating_opacity(hwnd=None, user32=None):
    return _get_floating_controller().apply_opacity(hwnd, user32)


def _refresh_price_from_floating_menu():
    return _get_floating_controller().refresh_price()


def _open_risk_analysis_from_floating_menu():
    return _get_floating_controller().open_risk_analysis("floating_price")


def _refresh_price_from_tray_menu():
    _refresh_price_from_floating_menu()


def _open_risk_analysis_from_tray_menu():
    return _get_floating_controller().open_risk_analysis("tray")


def _toggle_floating_price_from_tray_menu():
    settings = get_settings_snapshot()
    _set_floating_price_enabled(not bool(settings.get("floating_price_enabled", True)))


def _get_lparam_point(lparam):
    return _get_floating_controller().get_lparam_point(lparam)


def _floating_text_state():
    return _get_floating_controller().text_state()


def _floating_price_window_loop():
    return _get_floating_controller().run_window()


def _taskbar_price_window_loop():
    return _get_taskbar_controller().run_window()


def start_floating_price_window():
    return _get_floating_controller().start_window(
        worker=_floating_price_window_loop,
        available=lambda: _is_floating_price_available(),
    )


def start_taskbar_price_window():
    return _get_taskbar_controller().start_window(
        worker=_taskbar_price_window_loop,
    )


def apply_floating_price_settings(settings=None):
    _get_floating_controller().apply_settings(
        settings,
        worker=_floating_price_window_loop,
    )
    _get_taskbar_controller().apply_settings(
        settings,
        worker=_taskbar_price_window_loop,
    )
    return None


def update_floating_price(rmb=None, usd=None, pct=None):
    _get_floating_controller().update_price(
        rmb,
        usd,
        pct,
        worker=_floating_price_window_loop,
    )
    _get_taskbar_controller().update_price(
        rmb,
        usd,
        pct,
        worker=_taskbar_price_window_loop,
    )
    return None


def _find_main_window_hwnd():
    if os.name != "nt":
        return None
    try:
        import ctypes
        for title in (runtime.last_desktop_title, APP_NAME):
            hwnd = ctypes.windll.user32.FindWindowW(None, title)
            if hwnd:
                return hwnd
        return None
    except Exception:
        return None


def hide_main_window():
    return desktop_runtime_core.hide_main_window(
        get_window=lambda: runtime.window_instance,
        os_name=os.name,
        get_window_hwnd=lambda: runtime.window_hwnd,
        set_window_hwnd=_set_window_hwnd,
        find_window_hwnd=lambda: _find_main_window_hwnd(),
        ctypes_loader=lambda: __import__("ctypes"),
    )


def show_main_window():
    return desktop_runtime_core.show_main_window(
        get_window=lambda: runtime.window_instance,
        os_name=os.name,
        sys_platform=sys.platform,
        process_id=os.getpid(),
        run_macos_script=lambda script, wait=False: _run_macos_osascript(script, wait=wait),
        get_window_hwnd=lambda: runtime.window_hwnd,
        set_window_hwnd=_set_window_hwnd,
        find_window_hwnd=lambda: _find_main_window_hwnd(),
        ctypes_loader=lambda: __import__("ctypes"),
    )


def exit_app():
    return desktop_runtime_core.exit_application(
        get_tray_icon=lambda: runtime.tray_icon,
        process_exit=os._exit,
    )


def start_background_fetching():
    return desktop_runtime_core.start_thread_once(
        is_started=lambda: runtime.background_fetch_started,
        mark_started=_set_background_fetch_started,
        target=background_loop,
        thread_factory=threading.Thread,
    )


def start_news_fetching():
    return desktop_runtime_core.start_thread_once(
        is_started=lambda: runtime.news_fetch_started,
        mark_started=_set_news_fetch_started,
        target=news_loop,
        thread_factory=threading.Thread,
    )


def daily_digest_loop():
    return desktop_runtime_core.run_periodic_task(
        lambda: run_daily_digest_once(),
        interval=30,
        sleep=lambda seconds: time.sleep(seconds),
        logger=logging,
        error_message="执行每日摘要任务失败",
    )


def start_daily_digest_scheduler():
    return desktop_runtime_core.start_thread_once(
        is_started=lambda: runtime.daily_digest_scheduler_started,
        mark_started=_set_daily_digest_scheduler_started,
        target=daily_digest_loop,
        thread_factory=threading.Thread,
    )


def wait_for_server_ready(timeout=3.0):
    return instance_runtime_core.wait_for_server_ready(
        DEFAULT_HOST,
        runtime.server_port,
        timeout=timeout,
        socket_factory=socket.socket,
        clock=time.time,
        sleep=time.sleep,
    )


# ---------- 系统托盘 ----------
def create_tray_icon():
    return desktop_runtime_core.create_tray_icon(
        base_dir=_basedir,
        set_tray_icon=_set_tray_icon,
        show_window=lambda: show_main_window(),
        refresh_price=lambda: _refresh_price_from_tray_menu(),
        open_risk_analysis=lambda: _open_risk_analysis_from_tray_menu(),
        toggle_floating_price=lambda: _toggle_floating_price_from_tray_menu(),
        exit_application=lambda: exit_app(),
        format_title=lambda: format_price_title(),
        thread_factory=threading.Thread,
        sleep=lambda seconds: time.sleep(seconds),
    )


# ---------- 桌面原生窗口 ----------
class DesktopBridge(desktop_runtime_core.DesktopBridge):
    def __init__(self):
        super().__init__(lambda: choose_export_dir_for_desktop())


def start_desktop_window(start_hidden=False):
    """使用 pywebview 创建原生桌面窗口"""
    return desktop_runtime_core.start_desktop_window(
        app_name=APP_NAME,
        url=f"http://{DEFAULT_HOST}:{runtime.server_port}",
        base_dir=_basedir,
        start_hidden=start_hidden,
        os_name=os.name,
        sys_platform=sys.platform,
        bridge=DesktopBridge(),
        get_window=lambda: runtime.window_instance,
        set_window=_set_window_instance,
        set_window_hwnd=_set_window_hwnd,
        create_macos_status_item=lambda: create_macos_status_item(),
        get_settings_snapshot=lambda: get_settings_snapshot(),
        close_behavior_decision=(
            lambda snapshot, runtime_platform:
            platform_core.close_behavior_decision(snapshot, runtime_platform)
        ),
        hide_window=lambda: hide_main_window(),
        exit_application=lambda: exit_app(),
        emit=lambda event, payload: socketio.emit(event, payload),
        ctypes_loader=lambda: __import__("ctypes"),
    )


# ---------- 启动 ----------
def main():
    return application_bootstrap_core.run_application(
        argv=sys.argv,
        os_name=os.name,
        sys_platform=sys.platform,
        frozen=getattr(sys, "frozen", False),
        default_host=DEFAULT_HOST,
        default_port=DEFAULT_PORT,
        runtime=runtime,
        find_existing_instance=find_existing_goldmonitor_instance,
        local_app_url=local_app_url,
        open_existing_instance=open_existing_goldmonitor_instance,
        find_available_port=find_available_port,
        create_tray_icon=create_tray_icon,
        run_server=lambda host, port: socketio.run(
            app,
            debug=False,
            host=host,
            port=port,
            allow_unsafe_werkzeug=True,
        ),
        wait_for_server_ready=wait_for_server_ready,
        update_floating_price=update_floating_price,
        start_background_fetching=start_background_fetching,
        start_news_fetching=start_news_fetching,
        start_daily_digest_scheduler=start_daily_digest_scheduler,
        get_settings=get_settings_snapshot,
        start_desktop_window=start_desktop_window,
        thread_factory=threading.Thread,
        exit_process=sys.exit,
    )
