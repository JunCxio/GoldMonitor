import hashlib
import json
import logging
import math
import os
import plistlib
import sqlite3
import smtplib
import subprocess
import socket
import sys
import threading
import time
from datetime import datetime, timedelta
import secrets

import requests
from flask import Flask, jsonify, render_template, request, send_from_directory
from flask_socketio import SocketIO, emit
from goldmonitor import desktop_ui as desktop_ui_core
from goldmonitor import event_timeline as event_timeline_core
from goldmonitor import market_data as market_data_core
from goldmonitor import news as news_core
from goldmonitor import notifications as notifications_core
from goldmonitor import platform as platform_core
from goldmonitor import portfolio as portfolio_core
from goldmonitor import risk_analysis as risk_analysis_core
from goldmonitor import settings_store as settings_store_core
from goldmonitor import support_files as support_files_core
from goldmonitor import targets as targets_core
from goldmonitor import update_manager as update_manager_core
from goldmonitor.alert_log import AlertLogStore
from goldmonitor.data_contracts import item_payload_metadata, unwrap_item_payload, wrap_item_payload
from goldmonitor.diagnostics import build_health_summary
from goldmonitor.platform import platform_capabilities as build_platform_capabilities
from goldmonitor.platform import runtime_platform as detect_runtime_platform
from goldmonitor.price_history import PriceHistoryStore

# PyInstaller 打包后路径适配
if getattr(sys, "frozen", False):
    _basedir = sys._MEIPASS
else:
    _basedir = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, template_folder=os.path.join(_basedir, "templates"))
socketio = SocketIO(app, async_mode="threading")

# ---------- 常量 ----------
APP_VERSION = "1.0.1"
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
WATCH_TARGETS_PATH = os.path.join(APPDATA_DIR, "watch_targets.json")
PORTFOLIO_POSITIONS_PATH = os.path.join(APPDATA_DIR, "portfolio_positions.json")
PORTFOLIO_TRANSACTIONS_PATH = os.path.join(APPDATA_DIR, "portfolio_transactions.json")
MARKET_CACHE_PATH = os.path.join(APPDATA_DIR, "market_cache.json")
UPDATE_DIR = os.path.join(APPDATA_DIR, "updates")
EXPORT_DIR = os.path.join(APPDATA_DIR, "exports")
UPDATE_INSTALLER_NAME = "GoldMonitor-macOS.dmg" if sys.platform == "darwin" else "GoldMonitorSetup.exe"
NEWS_CACHE_PATH = os.path.join(APPDATA_DIR, "news.json")
RISK_ANALYSIS_HISTORY_PATH = os.path.join(APPDATA_DIR, "risk_analysis_history.json")
PRICE_HISTORY_PATH = os.path.join(APPDATA_DIR, "price_history.json")
APP_LOG_PATH = os.path.join(APPDATA_DIR, "GoldMonitor.log")
NEWS_REFRESH_INTERVAL = 15 * 60
NEWS_LIMIT = 20
RISK_ANALYSIS_HISTORY_LIMIT = 20
PRICE_HISTORY_ARCHIVE_LIMIT = 20000
PRICE_HISTORY_EXPORT_LIMIT = 5000
PRICE_HISTORY_SAVE_INTERVAL_SECONDS = 60
ALERT_LOG_MEMORY_LIMIT = 50
ALERT_LOG_EXPORT_LIMIT = 1000
ALERT_LOG_DB_LIMIT = 5000
EVENT_TIMELINE_TYPES = ("price_summary", "alert", "risk_analysis", "news", "data_status")
EVENT_TIMELINE_DEFAULT_MINUTES = 60
EVENT_TIMELINE_ALLOWED_MINUTES = (60, 240, 1440, 10080)
EVENT_TIMELINE_MAX_LIMIT = 500
EVENT_TIMELINE_DEFAULT_LIMIT = 300
REVIEW_REPORT_EXPORT_PREFIX = "GoldMonitor-review-report"
SOURCE_HEALTH_LIMIT = 20
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
DEFAULT_SETTINGS = {
    "startup_enabled": False,
    "startup_to_tray": True,
    "floating_price_enabled": True,
    "floating_price_position_saved": False,
    "floating_price_x": None,
    "floating_price_y": None,
    "floating_price_opacity": 94,
    "floating_price_display_mode": "rmb_usd",
    "floating_price_preset": "compact",
    "floating_price_snap_edge": True,
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
}
SECRET_SETTING_KEYS = ("smtp_password", "deepseek_api_key", "openai_compatible_api_key")
CREDENTIAL_SERVICE_NAME = "GoldMonitor"
CREDENTIAL_TARGET_PREFIX = "GoldMonitor:"
VALID_SMTP_ENCRYPTIONS = {"ssl", "tls"}
VALID_CLOSE_BEHAVIORS = {"ask", "minimize_to_tray", "exit"}
VALID_RISK_ASSISTANT_PROVIDERS = {"deepseek", "openai_compatible"}
VALID_RISK_ASSISTANT_DEPTHS = {"quick", "standard", "deep"}
VALID_FLOATING_DISPLAY_MODES = {"rmb_usd", "rmb_only", "usd_only"}
VALID_FLOATING_PRESETS = set(desktop_ui_core.FLOATING_PRICE_PRESETS)
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

# ---------- 全局状态 ----------
lock = threading.RLock()
settings_lock = threading.RLock()
risk_history_lock = threading.RLock()
price_usd = None
price_rmb = None
previous_usd = None
previous_rmb = None
usdcny_rate = None
usdcny_rate_source = ""
usdcny_rate_time = None
usdcny_rate_cached = False
usdcny_rate_error = ""
gold_price_source = ""
gold_price_time = None
gold_price_cached = False
gold_price_error = ""
price_history = []  # [{usd, rmb, rate, time, timestamp}]
price_archive = []
klines_5min = []    # [{open, high, low, close, time, timestamp}]
last_price_history_save_at = 0.0
last_fetch_ok = False
last_fetch_error = ""
last_fetch_time = None
price_refresh_lock = threading.Lock()

# 日内统计
today_date = None
today_open_usd = None
today_high_usd = None
today_low_usd = None
today_open_rmb = None
today_high_rmb = None
today_low_rmb = None

# 多级阈值: {upper_warning_usd, upper_critical_usd, lower_warning_usd, lower_critical_usd, ...}
thresholds = {}
for m in THRESHOLD_MODES:
    for t in THRESHOLD_TYPES:
        thresholds[f"{t}_{m}"] = None

# 波动率预警
volatility_config = {"percent": None, "minutes": 10, "enabled": False}
last_volatility_check = None
watch_targets = []
portfolio_positions = []
portfolio_transactions = []

# 警报去重: 记录每个阈值是否已经触发过 (避免每10秒重复报警)
alerted_flags = {}  # key: "upper_critical_rmb" -> True/False
alert_cooldown_state = {}

alert_log = []
news_items = []
news_last_updated = None
news_last_error = ""
risk_analysis_history = []
app_settings = {}
last_settings_error = None
server_port = DEFAULT_PORT
risk_analysis_lock = threading.Lock()
risk_analysis_last_started = 0.0
source_health = {}
source_price_samples = {}
source_comparison_state = {}
last_source_comparison_probe_at = 0.0
_credential_test_store = None
_alert_dialog_lock = threading.Lock()
_alert_dialog_active = False


# ---------- 设置与系统集成 ----------
def _current_executable():
    return platform_core.current_executable(
        getattr(sys, "frozen", False),
        sys.executable,
        sys.argv[0],
    )


def _credential_target_name(key):
    return f"{CREDENTIAL_TARGET_PREFIX}{key}"


def _credential_store_override():
    return _credential_test_store if isinstance(_credential_test_store, dict) else None


def _read_windows_credential(key):
    if os.name != "nt":
        return ""
    try:
        import ctypes
        from ctypes import wintypes

        CRED_TYPE_GENERIC = 1

        class FILETIME(ctypes.Structure):
            _fields_ = [
                ("dwLowDateTime", wintypes.DWORD),
                ("dwHighDateTime", wintypes.DWORD),
            ]

        class CREDENTIALW(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD),
                ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR),
                ("LastWritten", FILETIME),
                ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR),
                ("UserName", wintypes.LPWSTR),
            ]

        credential_ptr = ctypes.POINTER(CREDENTIALW)()
        advapi32 = ctypes.windll.advapi32
        if not advapi32.CredReadW(_credential_target_name(key), CRED_TYPE_GENERIC, 0, ctypes.byref(credential_ptr)):
            return ""
        try:
            credential = credential_ptr.contents
            if not credential.CredentialBlob or not credential.CredentialBlobSize:
                return ""
            raw = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
            return raw.decode("utf-16-le", errors="ignore")
        finally:
            advapi32.CredFree(credential_ptr)
    except Exception:
        logging.warning("读取系统凭据失败: %s", key, exc_info=True)
        return ""


def _write_windows_credential(key, value):
    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        CRED_TYPE_GENERIC = 1
        CRED_PERSIST_LOCAL_MACHINE = 2

        class FILETIME(ctypes.Structure):
            _fields_ = [
                ("dwLowDateTime", wintypes.DWORD),
                ("dwHighDateTime", wintypes.DWORD),
            ]

        class CREDENTIALW(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD),
                ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR),
                ("LastWritten", FILETIME),
                ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR),
                ("UserName", wintypes.LPWSTR),
            ]

        raw = str(value or "").encode("utf-16-le")
        blob = ctypes.create_string_buffer(raw)
        credential = CREDENTIALW()
        credential.Flags = 0
        credential.Type = CRED_TYPE_GENERIC
        credential.TargetName = _credential_target_name(key)
        credential.Comment = "GoldMonitor 本机敏感配置"
        credential.CredentialBlobSize = len(raw)
        credential.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
        credential.Persist = CRED_PERSIST_LOCAL_MACHINE
        credential.AttributeCount = 0
        credential.Attributes = None
        credential.TargetAlias = None
        credential.UserName = key
        return bool(ctypes.windll.advapi32.CredWriteW(ctypes.byref(credential), 0))
    except Exception:
        logging.warning("写入系统凭据失败: %s", key, exc_info=True)
        return False


def _delete_windows_credential(key):
    if os.name != "nt":
        return True
    try:
        import ctypes

        CRED_TYPE_GENERIC = 1
        ctypes.windll.advapi32.CredDeleteW(_credential_target_name(key), CRED_TYPE_GENERIC, 0)
        return True
    except Exception:
        return True


def _run_macos_security(args):
    try:
        completed = subprocess.run(
            ["security", *args],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return completed.returncode, completed.stdout, completed.stderr
    except Exception as exc:
        return 1, "", str(exc)


def _read_macos_credential(key):
    if sys.platform != "darwin":
        return ""
    code, stdout, _stderr = _run_macos_security([
        "find-generic-password",
        "-s", CREDENTIAL_SERVICE_NAME,
        "-a", key,
        "-w",
    ])
    if code != 0:
        return ""
    return stdout.rstrip("\n")


def _write_macos_credential(key, value):
    if sys.platform != "darwin":
        return False
    code, _stdout, stderr = _run_macos_security([
        "add-generic-password",
        "-s", CREDENTIAL_SERVICE_NAME,
        "-a", key,
        "-w", str(value or ""),
        "-U",
    ])
    if code != 0:
        logging.warning("写入 macOS Keychain 失败: %s %s", key, stderr.strip())
    return code == 0


def _delete_macos_credential(key):
    if sys.platform != "darwin":
        return True
    _run_macos_security([
        "delete-generic-password",
        "-s", CREDENTIAL_SERVICE_NAME,
        "-a", key,
    ])
    return True


def read_credential_secret(key):
    store = _credential_store_override()
    if store is not None:
        return str(store.get(key) or "")
    if os.name == "nt":
        return _read_windows_credential(key)
    if sys.platform == "darwin":
        return _read_macos_credential(key)
    return ""


def write_credential_secret(key, value):
    store = _credential_store_override()
    if store is not None:
        if value:
            store[key] = str(value)
        else:
            store.pop(key, None)
        return True
    if os.name == "nt":
        return _write_windows_credential(key, value) if value else _delete_windows_credential(key)
    if sys.platform == "darwin":
        return _write_macos_credential(key, value) if value else _delete_macos_credential(key)
    return False


def _settings_options():
    return {
        "valid_smtp_encryptions": VALID_SMTP_ENCRYPTIONS,
        "valid_close_behaviors": VALID_CLOSE_BEHAVIORS,
        "valid_risk_assistant_providers": VALID_RISK_ASSISTANT_PROVIDERS,
        "valid_risk_assistant_depths": VALID_RISK_ASSISTANT_DEPTHS,
        "valid_floating_display_modes": VALID_FLOATING_DISPLAY_MODES,
        "valid_floating_presets": VALID_FLOATING_PRESETS,
        "default_email_subject_template": DEFAULT_EMAIL_SUBJECT_TEMPLATE,
        "default_email_body_template": DEFAULT_EMAIL_BODY_TEMPLATE,
        "risk_assistant_max_tokens": RISK_ASSISTANT_MAX_TOKENS,
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
    global last_settings_error
    data, error = _settings_store().load()
    last_settings_error = error or None
    return data


def save_settings(data=None):
    global app_settings, last_settings_error
    with settings_lock:
        if data is None:
            data = app_settings
        normalized = _settings_store().save(data, previous_settings=app_settings)
        app_settings = normalized
        last_settings_error = None
        return dict(app_settings)


def get_settings_snapshot():
    with settings_lock:
        return dict(app_settings)


def mask_secret(value):
    return settings_store_core.mask_secret(value)


def public_settings_snapshot(settings=None):
    snapshot = dict(settings or get_settings_snapshot())
    return settings_store_core.build_public_settings_snapshot(
        snapshot,
        SECRET_SETTING_KEYS,
        platform=_runtime_platform(),
        platform_capabilities=platform_capabilities(),
    )


def diagnostic_settings_snapshot(settings=None):
    return public_settings_snapshot(settings)


def _normalize_volatility_config(raw):
    return targets_core.normalize_volatility_config(raw)


def _normalize_thresholds(raw):
    return targets_core.normalize_thresholds(raw, thresholds, volatility_config)


def load_thresholds():
    return targets_core.ThresholdStore(
        THRESHOLDS_PATH,
        thresholds,
        current_volatility_config=volatility_config,
    ).load()


def save_thresholds(data=None):
    if data is None:
        data = thresholds
    return targets_core.ThresholdStore(
        THRESHOLDS_PATH,
        thresholds,
        current_volatility_config=volatility_config,
    ).save(data)


def _coerce_watch_target_bool(value, default=False):
    return targets_core.coerce_watch_target_bool(value, default)


def _generate_watch_target_id():
    return targets_core.generate_watch_target_id()


def normalize_watch_target(item, existing=None):
    return targets_core.normalize_watch_target(
        item,
        existing=existing,
        now_factory=datetime.now,
        id_factory=_generate_watch_target_id,
        note_limit=WATCH_TARGET_NOTE_LIMIT,
    )


def normalize_watch_targets(items):
    return targets_core.normalize_watch_targets(items, now_factory=datetime.now, id_factory=_generate_watch_target_id)


def load_watch_targets():
    return targets_core.WatchTargetStore(
        WATCH_TARGETS_PATH,
        now_factory=datetime.now,
        id_factory=_generate_watch_target_id,
    ).load()


def save_watch_targets(items=None):
    items = watch_targets if items is None else items
    return targets_core.WatchTargetStore(
        WATCH_TARGETS_PATH,
        now_factory=datetime.now,
        id_factory=_generate_watch_target_id,
    ).save(items)


def get_watch_targets_state():
    with lock:
        items = [dict(item) for item in watch_targets]
    return targets_core.watch_targets_state(items)


def _find_watch_target_index(target_id):
    return targets_core.find_watch_target_index(watch_targets, target_id)


def upsert_watch_target(data):
    global watch_targets
    target_id = str((data or {}).get("id") or "").strip() if isinstance(data, dict) else ""
    with lock:
        index = _find_watch_target_index(target_id)
        existing = watch_targets[index] if index >= 0 else None
        target = normalize_watch_target(data, existing=existing)
        if index >= 0:
            watch_targets[index] = target
        else:
            watch_targets.append(target)
        watch_targets = save_watch_targets(watch_targets)
        return get_watch_targets_state()


def delete_watch_target(target_id):
    global watch_targets
    with lock:
        index = _find_watch_target_index(target_id)
        if index < 0:
            return False, get_watch_targets_state()
        watch_targets.pop(index)
        watch_targets = save_watch_targets(watch_targets)
        return True, get_watch_targets_state()


def toggle_watch_target(target_id, enabled):
    global watch_targets
    with lock:
        index = _find_watch_target_index(target_id)
        if index < 0:
            return False, get_watch_targets_state()
        updated = dict(watch_targets[index])
        updated["enabled"] = _coerce_watch_target_bool(enabled, updated.get("enabled", True))
        updated["updated_at"] = datetime.now().isoformat(timespec="seconds")
        watch_targets[index] = normalize_watch_target(updated, existing=watch_targets[index])
        watch_targets = save_watch_targets(watch_targets)
        return True, get_watch_targets_state()


def reset_watch_target(target_id):
    global watch_targets
    with lock:
        index = _find_watch_target_index(target_id)
        if index < 0:
            return False, get_watch_targets_state()
        updated = dict(watch_targets[index])
        updated["triggered"] = False
        updated["triggered_at"] = ""
        updated["last_trigger_price"] = None
        updated["updated_at"] = datetime.now().isoformat(timespec="seconds")
        watch_targets[index] = normalize_watch_target(updated, existing=watch_targets[index])
        watch_targets = save_watch_targets(watch_targets)
        return True, get_watch_targets_state()


def _watch_target_price_for_mode(mode):
    if mode == "usd":
        return price_usd
    if mode == "rmb":
        return price_rmb
    return None


def _watch_target_triggered(target, current_price):
    return targets_core.watch_target_triggered(target, current_price)


def _watch_target_alert_message(target, current_price):
    return targets_core.build_watch_target_alert_message(target, current_price)


def check_watch_targets(now_str):
    global watch_targets
    with lock:
        watch_targets, triggered_entries = targets_core.check_watch_targets(
            watch_targets,
            prices={"usd": price_usd, "rmb": price_rmb},
            now_factory=datetime.now,
        )
        if not triggered_entries:
            return []
        watch_targets = save_watch_targets(watch_targets)
        state = get_watch_targets_state()

    socketio.emit("watch_targets_updated", state)
    for item in triggered_entries:
        target = item["target"]
        current_price = item["current_price"]
        alert_entry = {
            "time": now_str,
            "type": "warning",
            "mode": target.get("mode"),
            "message": _watch_target_alert_message(target, current_price),
            "source": "watch_target",
            "watch_target_id": target.get("id"),
        }
        emit_alert(alert_entry, "目标价观察提醒")
    return [item["target"] for item in triggered_entries]


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


def load_portfolio_positions():
    return _portfolio_store().load()


def load_portfolio_transactions():
    return _portfolio_transaction_store().load()


def save_portfolio_positions(items=None):
    items = portfolio_positions if items is None else items
    return _portfolio_store().save(items)


def save_portfolio_transactions(items=None):
    items = portfolio_transactions if items is None else items
    return _portfolio_transaction_store().save(items)


def _current_portfolio_prices():
    return {"rmb": price_rmb, "usd": price_usd}


def _build_portfolio_state_from_snapshots(transactions, positions, prices):
    if transactions:
        return portfolio_core.build_portfolio_state_from_transactions(transactions, prices)
    return portfolio_core.build_portfolio_state(positions, prices)


def build_portfolio_state():
    with lock:
        transactions = [dict(item) for item in portfolio_transactions]
        positions = [dict(item) for item in portfolio_positions]
        prices = _current_portfolio_prices()
    return _build_portfolio_state_from_snapshots(transactions, positions, prices)


def _find_portfolio_position_index(position_id):
    return portfolio_core.find_portfolio_position_index(portfolio_positions, position_id)


def _find_portfolio_transaction_index(transaction_id):
    return portfolio_core.find_portfolio_transaction_index(portfolio_transactions, transaction_id)


def upsert_portfolio_position(data):
    global portfolio_positions, portfolio_transactions
    position_id = str((data or {}).get("id") or "").strip() if isinstance(data, dict) else ""
    with lock:
        if portfolio_transactions:
            position = portfolio_core.normalize_portfolio_position(data, now_factory=datetime.now)
            transaction_data = {
                "position_id": position["id"],
                "name": position["name"],
                "type": "buy",
                "mode": position["mode"],
                "price": position["entry_price"],
                "quantity": position["quantity"],
                "fee": 0,
                "trade_date": position["entry_date"],
                "note": position["note"],
            }
            existing_transactions = [item for item in portfolio_transactions if item.get("position_id") == position["id"]]
            if existing_transactions:
                transaction_data["id"] = existing_transactions[0].get("id")
            transaction = portfolio_core.normalize_portfolio_transaction(transaction_data, now_factory=datetime.now)
            next_transactions = [item for item in portfolio_transactions if item.get("position_id") != position["id"]]
            next_transactions.append(transaction)
            portfolio_core.validate_portfolio_transactions(next_transactions)
            saved_transactions = save_portfolio_transactions(next_transactions)
            portfolio_transactions = saved_transactions
            prices = _current_portfolio_prices()
            return portfolio_core.build_portfolio_state_from_transactions([dict(item) for item in saved_transactions], prices)

        index = _find_portfolio_position_index(position_id)
        existing = portfolio_positions[index] if index >= 0 else None
        position = portfolio_core.normalize_portfolio_position(data, existing=existing, now_factory=datetime.now)
        next_positions = list(portfolio_positions)
        if index >= 0:
            next_positions[index] = position
        else:
            next_positions.append(position)
        portfolio_positions = save_portfolio_positions(next_positions)
        return build_portfolio_state()


def delete_portfolio_position(position_id):
    global portfolio_positions, portfolio_transactions
    with lock:
        if portfolio_transactions:
            position_id = str(position_id or "").strip()
            next_transactions = [item for item in portfolio_transactions if item.get("position_id") != position_id]
            if len(next_transactions) == len(portfolio_transactions):
                return False, build_portfolio_state()
            portfolio_core.validate_portfolio_transactions(next_transactions)
            saved_transactions = save_portfolio_transactions(next_transactions)
            portfolio_transactions = saved_transactions
            prices = _current_portfolio_prices()
            return True, portfolio_core.build_portfolio_state_from_transactions([dict(item) for item in saved_transactions], prices)

        index = _find_portfolio_position_index(position_id)
        if index < 0:
            return False, build_portfolio_state()
        next_positions = list(portfolio_positions)
        next_positions.pop(index)
        portfolio_positions = save_portfolio_positions(next_positions)
        return True, build_portfolio_state()


def upsert_portfolio_transaction(data):
    global portfolio_transactions
    transaction_id = str((data or {}).get("id") or "").strip() if isinstance(data, dict) else ""
    with lock:
        index = _find_portfolio_transaction_index(transaction_id)
        existing = portfolio_transactions[index] if index >= 0 else None
        transaction = portfolio_core.normalize_portfolio_transaction(data, existing=existing, now_factory=datetime.now)
        next_transactions = list(portfolio_transactions)
        if index >= 0:
            next_transactions[index] = transaction
        else:
            next_transactions.append(transaction)
        portfolio_core.validate_portfolio_transactions(next_transactions)
        saved_transactions = save_portfolio_transactions(next_transactions)
        portfolio_transactions = saved_transactions
        prices = _current_portfolio_prices()
        return portfolio_core.build_portfolio_state_from_transactions([dict(item) for item in saved_transactions], prices)


def delete_portfolio_transaction(transaction_id):
    global portfolio_transactions
    with lock:
        index = _find_portfolio_transaction_index(transaction_id)
        if index < 0:
            return False, build_portfolio_state()
        next_transactions = list(portfolio_transactions)
        next_transactions.pop(index)
        portfolio_core.validate_portfolio_transactions(next_transactions)
        saved_transactions = save_portfolio_transactions(next_transactions)
        portfolio_transactions = saved_transactions
        prices = _current_portfolio_prices()
        return True, portfolio_core.build_portfolio_state_from_transactions([dict(item) for item in saved_transactions], prices)


def build_portfolio_csv(kind="positions"):
    with lock:
        transactions = [dict(item) for item in portfolio_transactions]
        positions = [dict(item) for item in portfolio_positions]
        prices = _current_portfolio_prices()
    if transactions:
        if kind == "transactions":
            return portfolio_core.build_portfolio_transactions_csv(transactions)
        return portfolio_core.build_portfolio_positions_csv(transactions, prices)
    if kind == "transactions":
        legacy_transactions = portfolio_core.transactions_from_positions(positions, now_factory=datetime.now)
        return portfolio_core.build_portfolio_transactions_csv(legacy_transactions)
    return portfolio_core.build_portfolio_csv(positions, prices)


def _startup_command():
    exe = _current_executable()
    return platform_core.build_startup_command(exe)


def _macos_launch_agent_path():
    return platform_core.macos_launch_agent_path(os.path.expanduser("~"), MACOS_LAUNCH_AGENT_ID)


def _macos_startup_arguments():
    return platform_core.build_macos_startup_arguments(
        getattr(sys, "frozen", False),
        sys.executable,
        sys.argv[0],
    )


def _set_macos_startup_enabled(enabled):
    path = _macos_launch_agent_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if enabled:
            payload = platform_core.build_macos_launch_agent_payload(
                MACOS_LAUNCH_AGENT_ID,
                _macos_startup_arguments(),
                _current_executable(),
                os.path.expanduser("~"),
            )
            with open(path, "wb") as f:
                plistlib.dump(payload, f, sort_keys=False)
            subprocess.run(["launchctl", "unload", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3, check=False)
            subprocess.run(["launchctl", "load", "-w", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3, check=False)
        else:
            subprocess.run(["launchctl", "unload", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3, check=False)
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
        return True, None
    except Exception as exc:
        return False, str(exc)


def set_startup_enabled(enabled):
    if sys.platform == "darwin":
        return _set_macos_startup_enabled(enabled)
    supported, error = platform_core.startup_support_result(enabled, sys.platform, os.name)
    if supported is not None:
        return supported, error
    try:
        import winreg

        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, RUN_KEY_NAME, 0, winreg.REG_SZ, _startup_command())
            else:
                try:
                    winreg.DeleteValue(key, RUN_KEY_NAME)
                except FileNotFoundError:
                    pass
        return True, None
    except Exception as exc:
        return False, str(exc)


def apply_settings(data):
    saved = save_settings(data)
    ok, error = set_startup_enabled(saved["startup_enabled"])
    if not ok:
        saved["startup_enabled"] = False
        saved = save_settings(saved)
    apply_floating_price_settings(saved)
    return saved, error


def settings_payload_for_import(settings_payload):
    current = get_settings_snapshot()
    return settings_store_core.settings_payload_for_import(settings_payload, current, DEFAULT_SETTINGS, SECRET_SETTING_KEYS)


def apply_persisted_threshold_state(data):
    global volatility_config
    thresholds.update({key: data.get(key) for key in thresholds})
    volatility_config = _normalize_volatility_config(data.get("volatility_config"))


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


def fetch_update_manifest(manifest_url=None):
    manifest_url = str(manifest_url or get_update_manifest_url()).strip()
    if not manifest_url:
        raise ValueError("未配置更新源")
    _require_official_update_url(manifest_url, "更新源", {"version.json"})
    response = requests.get(manifest_url, timeout=REQUEST_TIMEOUT, proxies=REQ_PROXY)
    response.raise_for_status()
    return normalize_update_manifest(response.json(), manifest_url)


def get_update_status(expose_download=False):
    manifest_url = get_update_manifest_url()
    manifest = fetch_update_manifest(manifest_url)
    return update_manager_core.build_update_status(
        manifest,
        APP_VERSION,
        now=datetime.now(),
        expose_download=expose_download,
    )


def download_update_installer(update_info, progress_callback=None):
    os.makedirs(UPDATE_DIR, exist_ok=True)
    installer_path = os.path.join(UPDATE_DIR, UPDATE_INSTALLER_NAME)
    response = requests.get(update_info["url"], stream=True, timeout=60, proxies=REQ_PROXY)
    response.raise_for_status()
    try:
        total_bytes = int(response.headers.get("content-length") or 0)
    except (TypeError, ValueError):
        total_bytes = 0

    digest = hashlib.sha256()
    tmp_path = installer_path + ".tmp"
    received_bytes = 0
    with open(tmp_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=1024 * 128):
            if chunk:
                f.write(chunk)
                digest.update(chunk)
                received_bytes += len(chunk)
                if progress_callback:
                    progress_callback(received_bytes, total_bytes)

    expected = update_info.get("sha256")
    actual = digest.hexdigest()
    if expected and actual != expected:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise ValueError("安装包校验失败")

    os.replace(tmp_path, installer_path)
    return installer_path


def launch_update_installer(installer_path):
    if not os.path.exists(installer_path):
        raise FileNotFoundError(installer_path)
    plan = update_manager_core.build_installer_launch_plan(
        installer_path,
        os_name=os.name,
        sys_platform=sys.platform,
        create_new_process_group=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        detached_process=getattr(subprocess, "DETACHED_PROCESS", 0),
    )
    subprocess.Popen(plan["args"], **plan["kwargs"])


def read_log_tail(max_lines=120):
    return support_files_core.read_log_tail(APP_LOG_PATH, max_lines=max_lines)


def _json_payload_metadata(path):
    return support_files_core.json_payload_metadata(path)


def build_config_backup():
    return support_files_core.build_config_backup(
        APP_VERSION,
        public_settings_snapshot(),
        {
            **{key: thresholds.get(key) for key in thresholds},
            "volatility_config": dict(volatility_config),
        },
        now_factory=datetime.now,
    )


def save_export_file(filename, content):
    return support_files_core.save_export_file(EXPORT_DIR, filename, content)


def open_exports_folder():
    os.makedirs(EXPORT_DIR, exist_ok=True)
    plan = support_files_core.build_open_folder_plan(EXPORT_DIR, os_name=os.name, sys_platform=sys.platform)
    if plan["kind"] == "startfile":
        os.startfile(plan["path"])  # type: ignore[attr-defined]
        return
    subprocess.Popen(plan["args"], **plan["kwargs"])


def restore_config_backup(payload):
    if not isinstance(payload, dict):
        raise ValueError("备份文件格式无效")
    settings_payload = payload.get("settings")
    thresholds_payload = payload.get("thresholds")
    if not isinstance(settings_payload, dict) and not isinstance(thresholds_payload, dict):
        raise ValueError("备份中没有可导入的配置")
    imported = []
    if isinstance(settings_payload, dict):
        updated, startup_error = apply_settings(settings_payload_for_import(settings_payload))
        if startup_error:
            logging.warning("导入配置时自启动设置失败: %s", startup_error)
        imported.append("settings")
        socketio.emit("settings_updated", public_settings_snapshot(updated))
    if isinstance(thresholds_payload, dict):
        normalized = save_thresholds(thresholds_payload)
        apply_persisted_threshold_state(normalized)
        imported.append("thresholds")
        socketio.emit("thresholds_updated", thresholds)
        socketio.emit("volatility_updated", volatility_config)
    return {"ok": True, "imported": imported}


def reset_to_default_settings():
    global alert_cooldown_state
    saved_settings, startup_error = apply_settings(dict(DEFAULT_SETTINGS))
    normalized_thresholds = save_thresholds({})
    apply_persisted_threshold_state(normalized_thresholds)
    alert_cooldown_state = {}
    socketio.emit("settings_updated", public_settings_snapshot(saved_settings))
    socketio.emit("thresholds_updated", thresholds)
    socketio.emit("volatility_updated", volatility_config)
    return {"ok": True, "startup_error": startup_error or ""}


def build_diagnostics_report():
    paths = {
        "appdata": APPDATA_DIR,
        "settings": SETTINGS_PATH,
        "thresholds": THRESHOLDS_PATH,
        "watch_targets": WATCH_TARGETS_PATH,
        "market_cache": MARKET_CACHE_PATH,
        "price_history": PRICE_HISTORY_PATH,
        "price_history_db": _price_history_db_path(),
        "alert_log_db": _alert_log_db_path(),
        "log": APP_LOG_PATH,
    }
    fetch_status = get_fetch_status()
    source_health_state = get_source_health_state()
    price_history_state = build_price_history_state(limit=120)
    watch_targets_state = get_watch_targets_state()
    risk_history_count = len(get_risk_analysis_history_state().get("items", []))
    recent_alerts = list(alert_log[-20:])
    report = {
        "app": APP_NAME,
        "version": APP_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "paths": paths,
        "health_summary": build_health_summary(
            fetch_status=fetch_status,
            source_health=source_health_state,
            price_history=price_history_state,
            watch_targets=watch_targets_state,
            risk_history_count=risk_history_count,
            recent_alerts=recent_alerts,
            paths=paths,
        ),
        "data_schemas": {
            "watch_targets": _json_payload_metadata(WATCH_TARGETS_PATH),
            "news": _json_payload_metadata(NEWS_CACHE_PATH),
            "risk_analysis_history": _json_payload_metadata(RISK_ANALYSIS_HISTORY_PATH),
            "price_history": _json_payload_metadata(PRICE_HISTORY_PATH),
        },
        "settings": diagnostic_settings_snapshot(),
        "fetch_status": fetch_status,
        "source_health": source_health_state,
        "price_history": price_history_state,
        "watch_targets": watch_targets_state,
        "risk_history_count": risk_history_count,
        "recent_alerts": recent_alerts,
        "logs": read_log_tail(),
    }
    return json.dumps(report, ensure_ascii=False, indent=2)


def show_alert_dialog(title, message):
    if not get_settings_snapshot().get("alert_dialog_enabled", True):
        return
    global _alert_dialog_active
    with _alert_dialog_lock:
        if _alert_dialog_active:
            logging.info("告警弹窗已存在，跳过新的系统消息框。")
            return
        _alert_dialog_active = True

    def _show():
        global _alert_dialog_active
        try:
            if sys.platform == "darwin":
                script = (
                    "display alert "
                    + _applescript_string(title)
                    + " message "
                    + _applescript_string(message)
                    + ' as warning buttons {"知道了"} default button "知道了"'
                )
                _run_macos_osascript(script, wait=True, timeout=3600)
            elif os.name == "nt":
                import ctypes
                MB_OK = 0x00000000
                MB_ICONWARNING = 0x00000030
                MB_TOPMOST = 0x00040000
                MB_SETFOREGROUND = 0x00010000
                ctypes.windll.user32.MessageBoxW(None, message, title, MB_OK | MB_ICONWARNING | MB_TOPMOST | MB_SETFOREGROUND)
        except Exception:
            pass
        finally:
            with _alert_dialog_lock:
                _alert_dialog_active = False

    threading.Thread(target=_show, daemon=True).start()


def play_system_alert_sound(level):
    if not get_settings_snapshot().get("alert_sound_enabled", True):
        return
    if sys.platform == "darwin":
        try:
            sound = "Basso" if level == "critical" else "Glass"
            path = f"/System/Library/Sounds/{sound}.aiff"
            if os.path.exists(path):
                subprocess.Popen(["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
            else:
                _run_macos_osascript("beep", wait=False)
        except Exception:
            pass
        return
    try:
        import winsound
        sound = "SystemHand" if level == "critical" else "SystemExclamation"
        winsound.PlaySound(sound, winsound.SND_ALIAS | winsound.SND_ASYNC)
    except Exception:
        pass


def select_related_news(title, items=None, limit=3):
    pool = items if items is not None else news_items
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
    return notifications_core.evaluate_alert_delivery(entry, settings, alert_cooldown_state, now=now)


def build_alert_template_values(alert_type, title, message):
    with lock:
        market = {
            "price_usd": price_usd,
            "price_rmb": price_rmb,
            "usdcny_rate": usdcny_rate,
            "gold_price_source": gold_price_source,
            "usdcny_rate_source": usdcny_rate_source,
        }
    return notifications_core.build_alert_template_values(alert_type, title, message, market, _alert_level_map)


class EmailNotifier:
    """SMTP 邮件通知器"""

    @staticmethod
    def send(alert_type, title, message, timeout=10, blocking=False):
        settings = get_settings_snapshot()
        values = build_alert_template_values(alert_type, title, message)
        return notifications_core.send_email_notification(
            settings,
            alert_type,
            title,
            message,
            values,
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
        settings = get_settings_snapshot()
        values = build_alert_template_values(alert_type, title, message)
        return notifications_core.send_webhook_notification(
            settings,
            alert_type,
            title,
            message,
            values,
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


def _notification_status(channel, label, status, message):
    return notifications_core.notification_status(channel, label, status, message)


def dispatch_alert(entry, title):
    """通知渠道分发: 根据设置决定哪些渠道发送"""
    settings = get_settings_snapshot()
    return notifications_core.dispatch_alert(
        entry,
        title,
        settings,
        email_sender=EmailNotifier.send,
        webhook_sender=WebhookNotifier.send,
        logger=logging,
    )


def emit_alert(entry, title):
    settings = get_settings_snapshot()
    entry["title"] = str(title or "")
    delivery = evaluate_alert_delivery(entry, settings)
    if not delivery.get("deliver"):
        reason = delivery.get("reason", "")
        entry["notification_muted"] = True
        entry["notification_reason"] = reason
        if reason == "quiet_time":
            entry["notification_message"] = "当前处于静默时段，仅记录提醒。"
        elif reason == "cooldown":
            entry["notification_message"] = "提醒冷却中，仅记录本次触发。"
        entry["notifications"] = [
            _notification_status("all", "通知", "muted", entry.get("notification_message", "仅记录提醒")),
        ]
    else:
        entry["notifications"] = dispatch_alert(entry, title)
    entry["related_news"] = select_related_news(title)
    entry["timestamp"] = datetime.now().isoformat(timespec="seconds")
    alert_log.append(entry)
    while len(alert_log) > ALERT_LOG_MEMORY_LIMIT:
        alert_log.pop(0)
    try:
        save_alert_log_entry(entry)
    except (OSError, sqlite3.Error) as exc:
        logging.warning("告警记录保存失败: %s", exc)
    socketio.emit("alert", entry)
    history_state = build_price_history_state(limit=240)
    history_state["scope"] = "live"
    socketio.emit("price_history_updated", history_state)
    if delivery.get("deliver"):
        send_desktop_notification(title, entry["message"])
        play_system_alert_sound(entry.get("type", "warning"))
        show_alert_dialog(title, f"{entry['message']}\n\n时间: {entry['time']}")


def initialize_market_cache():
    global usdcny_rate, usdcny_rate_source, usdcny_rate_time, usdcny_rate_cached, usdcny_rate_error
    cached = load_valid_usdcny_cache()
    if cached:
        usdcny_rate = cached["value"]
        usdcny_rate_source = cached["source"]
        usdcny_rate_time = cached["timestamp"]
        usdcny_rate_cached = True
        usdcny_rate_error = "启动时使用缓存汇率"


app_settings = load_settings()
apply_persisted_threshold_state(load_thresholds())
watch_targets = load_watch_targets()
portfolio_positions = load_portfolio_positions()
portfolio_transactions = load_portfolio_transactions()


def find_available_port(preferred=DEFAULT_PORT):
    for port in range(preferred, preferred + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.2)
            if probe.connect_ex((DEFAULT_HOST, port)) == 0:
                continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind((DEFAULT_HOST, port))
                return port
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((DEFAULT_HOST, 0))
        return probe.getsockname()[1]


# ---------- 数据获取 ----------
def build_fetch_status(ok, message="", gold_ok=None, forex_ok=None, error="", retryable=True):
    failed = []
    if gold_ok is False:
        failed.append("金价源")
    if forex_ok is False:
        failed.append("汇率源")
    source_text = "、".join(failed)
    base = message or ("行情数据正常" if ok else "行情数据获取失败")
    if source_text and source_text not in base:
        base = f"{source_text}: {base}"
    if error:
        base = f"{base}（{error}）"
    return {
        "ok": bool(ok),
        "message": base,
        "gold_ok": gold_ok,
        "forex_ok": forex_ok,
        "error": error,
        "retryable": bool(retryable),
        "time": datetime.now().strftime("%H:%M:%S"),
    }


def _current_fetch_status_locked():
    if price_usd is None:
        return build_fetch_status(
            False,
            "正在等待首次行情数据返回",
            error=last_fetch_error,
            retryable=True,
        )
    return build_fetch_status(
        last_fetch_ok,
        "行情数据正常" if last_fetch_ok else "行情数据获取失败",
        error=last_fetch_error,
        retryable=True,
    )


def get_fetch_status():
    with lock:
        return _current_fetch_status_locked()


def record_source_health(name, category, ok, error="", started_at=None, cached=False):
    if not name:
        return
    with lock:
        market_data_core.record_source_health(
            source_health,
            name,
            category,
            ok,
            error=error,
            started_at=started_at,
            cached=cached,
            limit=SOURCE_HEALTH_LIMIT,
        )
    socketio.emit("source_health_updated", get_source_health_state())


def get_source_health_state():
    with lock:
        health_snapshot = {name: dict(item) for name, item in source_health.items()}
    return market_data_core.build_source_health_state(
        health_snapshot,
        comparison=get_source_comparison_state(),
    )


def record_source_price_sample(name, data, cached=False):
    if not name or not isinstance(data, dict):
        return
    try:
        close = float(data.get("close"))
    except (TypeError, ValueError):
        return
    if not math.isfinite(close) or close <= 0:
        return
    with lock:
        source_price_samples[name] = {
            "name": name,
            "usd": round(close, 4),
            "open": _format_number(data.get("open")),
            "high": _format_number(data.get("high")),
            "low": _format_number(data.get("low")),
            "source_time": data.get("timestamp") or data.get("time") or "",
            "checked_at": datetime.now().isoformat(timespec="seconds"),
            "cached": bool(cached or data.get("cached")),
        }


def build_source_comparison_state(samples=None):
    if samples is None:
        with lock:
            samples = [dict(item) for item in source_price_samples.values()]
    return market_data_core.build_source_comparison_state(
        samples,
        stale_seconds=SOURCE_COMPARISON_STALE_SECONDS,
        anomaly_pct=SOURCE_COMPARISON_ANOMALY_PCT,
    )


def get_source_comparison_state():
    with lock:
        if source_comparison_state:
            return json.loads(json.dumps(source_comparison_state, ensure_ascii=False))
    return build_source_comparison_state()


def refresh_source_comparison(primary_data=None, primary_source="", primary_cached=False):
    global source_comparison_state, last_source_comparison_probe_at
    if primary_data is not None and primary_source:
        record_source_price_sample(primary_source, primary_data, cached=primary_cached)

    now_monotonic = time.monotonic()
    should_probe = now_monotonic - last_source_comparison_probe_at >= SOURCE_COMPARISON_REFRESH_SECONDS
    if should_probe:
        last_source_comparison_probe_at = now_monotonic
        probes = [
            ("新浪贵金属", lambda: fetch_sina_gold_result()[0]),
            ("东方财富", lambda: fetch_eastmoney_gold_result()[0]),
            ("GoldPrice", lambda: fetch_goldprice_data_result()[0]),
            ("Stooq", lambda: fetch_gold_data_result(GOLD_URL, "Stooq 金价源")[0]),
        ]
        for name, getter in probes:
            if name == primary_source:
                continue
            try:
                data = getter()
            except Exception:
                data = None
            if data is not None:
                record_source_price_sample(name, data)

    state = build_source_comparison_state()
    with lock:
        source_comparison_state = state
    return state


def fetch_gold_data(url):
    """从 Stooq CSV 解析完整 OHLC 数据"""
    data, _error = fetch_gold_data_result(url)
    return data


def fetch_gold_data_result(url, source_label="数据源"):
    """从 Stooq CSV 解析完整 OHLC 数据，并返回用户可读的失败原因。"""
    started_at = time.monotonic()
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT, proxies=REQ_PROXY)
        resp.raise_for_status()
        data, error = market_data_core.parse_stooq_ohlc_csv(resp.text, source_label)
        if error:
            record_source_health(source_label, "gold" if "金价" in source_label else "forex", False, error, started_at)
            return None, error
        record_source_health(source_label, "gold" if "金价" in source_label else "forex", True, "", started_at)
        return data, ""
    except requests.Timeout:
        error = f"{source_label}请求超时"
    except requests.ConnectionError:
        error = f"{source_label}网络连接失败"
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else "未知"
        error = f"{source_label}HTTP错误 {code}"
    except requests.RequestException as exc:
        error = f"{source_label}请求失败: {exc}"
    except (ValueError, IndexError):
        error = f"{source_label}返回格式异常"
    record_source_health(source_label, "gold" if "金价" in source_label else "forex", False, error, started_at)
    return None, error


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
    started_at = time.monotonic()
    try:
        resp = requests.get(
            SINA_FOREX_URL,
            timeout=REQUEST_TIMEOUT,
            proxies=REQ_PROXY,
            headers={
                "User-Agent": BROWSER_USER_AGENT,
                "Referer": "https://finance.sina.com.cn/",
            },
        )
        resp.raise_for_status()
        rate, error = parse_sina_forex(resp.text)
        record_source_health("新浪汇率", "forex", rate is not None, error, started_at)
        return rate, error
    except requests.Timeout:
        error = "新浪汇率请求超时"
    except requests.ConnectionError:
        error = "新浪汇率网络连接失败"
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else "未知"
        error = f"新浪汇率HTTP错误 {code}"
    except requests.RequestException as exc:
        error = f"新浪汇率请求失败: {exc}"
    record_source_health("新浪汇率", "forex", False, error, started_at)
    return None, error


def parse_frankfurter_forex(payload):
    return market_data_core.parse_frankfurter_forex(payload)


def fetch_frankfurter_forex_result():
    started_at = time.monotonic()
    try:
        resp = requests.get(
            FRANKFURTER_FOREX_URL,
            timeout=REQUEST_TIMEOUT,
            proxies=REQ_PROXY,
            headers={"User-Agent": HTTP_USER_AGENT},
        )
        resp.raise_for_status()
        rate, error = parse_frankfurter_forex(resp.json())
        record_source_health("Frankfurter", "forex", rate is not None, error, started_at)
        return rate, error
    except requests.Timeout:
        error = "Frankfurter 请求超时"
    except requests.ConnectionError:
        error = "Frankfurter 网络连接失败"
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else "未知"
        error = f"Frankfurter HTTP错误 {code}"
    except requests.RequestException as exc:
        error = f"Frankfurter 请求失败: {exc}"
    except (ValueError, json.JSONDecodeError):
        error = "Frankfurter 返回格式异常"
    record_source_health("Frankfurter", "forex", False, error, started_at)
    return None, error


def fetch_usdcny_rate_result():
    errors = []
    for source, fetcher in (
        ("新浪", fetch_sina_forex_result),
        ("Frankfurter", fetch_frankfurter_forex_result),
    ):
        rate, error = fetcher()
        if rate is not None:
            now_iso = datetime.now().isoformat()
            try:
                return save_usdcny_cache(rate, source, now_iso), ""
            except (OSError, ValueError) as exc:
                return {
                    "value": rate,
                    "source": source,
                    "timestamp": now_iso,
                    "cached": False,
                }, f"汇率缓存保存失败: {exc}"
        if error:
            errors.append(error)

    stooq_rate, stooq_error = fetch_csv_price_result(FOREX_URL, "Stooq 汇率源")
    if stooq_rate is not None:
        now_iso = datetime.now().isoformat()
        try:
            return save_usdcny_cache(stooq_rate, "Stooq", now_iso), ""
        except (OSError, ValueError) as exc:
            return {
                "value": stooq_rate,
                "source": "Stooq",
                "timestamp": now_iso,
                "cached": False,
            }, f"汇率缓存保存失败: {exc}"
    if stooq_error:
        errors.append(stooq_error)

    cached = load_valid_usdcny_cache()
    if cached:
        record_source_health("缓存汇率", "forex", True, "实时汇率源不可用，使用缓存", None, cached=True)
        return cached, "；".join(errors)
    return None, "；".join(errors) or "所有汇率源均不可用"


def parse_sina_gold(text):
    return market_data_core.parse_sina_gold(text)


def fetch_sina_gold_result():
    started_at = time.monotonic()
    try:
        resp = requests.get(
            SINA_GOLD_URL,
            timeout=REQUEST_TIMEOUT,
            proxies=REQ_PROXY,
            headers={
                "User-Agent": BROWSER_USER_AGENT,
                "Referer": "https://finance.sina.com.cn/futures/quotes/XAU.shtml",
            },
        )
        resp.raise_for_status()
        data, error = parse_sina_gold(resp.text)
        record_source_health("新浪贵金属", "gold", data is not None, error, started_at)
        return data, error
    except requests.Timeout:
        error = "新浪贵金属请求超时"
    except requests.ConnectionError:
        error = "新浪贵金属网络连接失败"
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else "未知"
        error = f"新浪贵金属HTTP错误 {code}"
    except requests.RequestException as exc:
        error = f"新浪贵金属请求失败: {exc}"
    record_source_health("新浪贵金属", "gold", False, error, started_at)
    return None, error


def parse_eastmoney_gold(payload):
    """解析东方财富 XAU 行情，返回 XAU/USD OHLC。"""
    return market_data_core.parse_eastmoney_gold(payload)


def fetch_eastmoney_gold_result():
    """从东方财富公开行情接口获取 XAU/USD，并返回用户可读的失败原因。"""
    started_at = time.monotonic()
    try:
        resp = requests.get(
            EASTMONEY_GOLD_URL,
            timeout=REQUEST_TIMEOUT,
            proxies=REQ_PROXY,
            headers={
                "User-Agent": HTTP_USER_AGENT,
                "Referer": "https://hf-wap.eastmoney.com/quote/stock/122.xau.html",
            },
        )
        resp.raise_for_status()
        data, error = parse_eastmoney_gold(resp.json())
        record_source_health("东方财富", "gold", data is not None, error, started_at)
        return data, error
    except requests.Timeout:
        error = "东方财富请求超时"
    except requests.ConnectionError:
        error = "东方财富网络连接失败"
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else "未知"
        error = f"东方财富HTTP错误 {code}"
    except requests.RequestException as exc:
        error = f"东方财富请求失败: {exc}"
    except (ValueError, json.JSONDecodeError):
        error = "东方财富返回格式异常"
    record_source_health("东方财富", "gold", False, error, started_at)
    return None, error


def parse_goldprice_rates(payload):
    """解析 GoldPrice.org 行情，返回 XAU/USD OHLC 和推导出的 USD/CNY 汇率。"""
    return market_data_core.parse_goldprice_rates(payload)


def fetch_goldprice_data_result():
    """从 GoldPrice.org 公开接口获取实时金价，并返回用户可读的失败原因。"""
    started_at = time.monotonic()
    try:
        resp = requests.get(
            GOLDPRICE_URL,
            timeout=REQUEST_TIMEOUT,
            proxies=REQ_PROXY,
            headers={"User-Agent": HTTP_USER_AGENT},
        )
        resp.raise_for_status()
        data, rate, error = parse_goldprice_rates(resp.json())
        record_source_health("GoldPrice", "gold", data is not None, error, started_at)
        return data, rate, error
    except requests.Timeout:
        error = "GoldPrice 请求超时"
    except requests.ConnectionError:
        error = "GoldPrice 网络连接失败"
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else "未知"
        error = f"GoldPrice HTTP错误 {code}"
    except requests.RequestException as exc:
        error = f"GoldPrice 请求失败: {exc}"
    except (ValueError, json.JSONDecodeError):
        error = "GoldPrice 返回格式异常"
    record_source_health("GoldPrice", "gold", False, error, started_at)
    return None, None, error


def fetch_market_data_result():
    """按优先级获取行情数据，避免单一接口失败导致应用一直无数据。"""
    sina_data, sina_error = fetch_sina_gold_result()
    if sina_data is not None:
        try:
            save_xauusd_cache(sina_data, "新浪贵金属")
        except (OSError, ValueError):
            pass
        rate_info, forex_error = fetch_usdcny_rate_result()
        return sina_data, rate_info, "新浪贵金属", "", forex_error

    eastmoney_data, eastmoney_error = fetch_eastmoney_gold_result()
    if eastmoney_data is not None:
        try:
            save_xauusd_cache(eastmoney_data, "东方财富")
        except (OSError, ValueError):
            pass
        rate_info, forex_error = fetch_usdcny_rate_result()
        return eastmoney_data, rate_info, "东方财富", "", forex_error

    goldprice_data, goldprice_rate, goldprice_error = fetch_goldprice_data_result()
    if goldprice_data is not None:
        try:
            save_xauusd_cache(goldprice_data, "GoldPrice")
        except (OSError, ValueError):
            pass
        if goldprice_rate is not None:
            now_iso = datetime.now().isoformat()
            try:
                rate_info = save_usdcny_cache(goldprice_rate, "GoldPrice", now_iso)
                return goldprice_data, rate_info, "GoldPrice", "", ""
            except (OSError, ValueError) as exc:
                return goldprice_data, {
                    "value": goldprice_rate,
                    "source": "GoldPrice",
                    "timestamp": now_iso,
                    "cached": False,
                }, "GoldPrice", "", f"汇率缓存保存失败: {exc}"
        rate_info, forex_error = fetch_usdcny_rate_result()
        return goldprice_data, rate_info, "GoldPrice", "", forex_error

    stooq_data, stooq_gold_error = fetch_gold_data_result(GOLD_URL, "Stooq 金价源")
    if stooq_data is not None:
        try:
            save_xauusd_cache(stooq_data, "Stooq")
        except (OSError, ValueError):
            pass
        rate_info, forex_error = fetch_usdcny_rate_result()
        return stooq_data, rate_info, "Stooq", "", forex_error

    errors = [error for error in (sina_error, eastmoney_error, goldprice_error, stooq_gold_error) if error]
    rate_info, forex_error = fetch_usdcny_rate_result()
    cached_gold = load_valid_xauusd_cache()
    gold_error = "；".join(errors) or "所有金价接口均不可用"
    if cached_gold:
        cache_source = cached_gold.get("source") or "缓存金价"
        record_source_health("缓存金价", "gold", True, gold_error, None, cached=True)
        return cached_gold, rate_info, f"缓存金价（{cache_source}）", gold_error, forex_error
    return None, rate_info, "", gold_error, forex_error


# ---------- 桌面通知 ----------
def send_desktop_notification(title, body):
    if sys.platform == "darwin":
        script = (
            "display notification "
            + _applescript_string(body)
            + " with title "
            + _applescript_string(title)
        )
        _run_macos_osascript(script, wait=False)
        return
    try:
        from win11toast import notify
        notification_icon = os.path.join(_basedir, "static", "icon.ico")
        if not os.path.exists(notification_icon):
            notification_icon = os.path.join(_basedir, "static", "icon-64.png")
        notify(title, body, app_id=APP_USER_MODEL_ID, icon=notification_icon)
    except Exception:
        pass


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
    items = []
    gdelt_response = requests.get(GDELT_NEWS_URL, timeout=REQUEST_TIMEOUT, proxies=REQ_PROXY)
    gdelt_response.raise_for_status()
    items.extend(parse_gdelt_articles(gdelt_response.json()))

    for source in NEWS_RSS_SOURCES:
        try:
            response = requests.get(source["url"], timeout=REQUEST_TIMEOUT, proxies=REQ_PROXY)
            response.raise_for_status()
            items.extend(parse_rss_items(response.text, source["name"], source["kind"]))
        except Exception:
            continue
    return normalize_news_items(items)


def refresh_gold_news(emit_update=True):
    global news_items, news_last_updated, news_last_error
    try:
        fetched = fetch_gold_news()
        with lock:
            if fetched:
                news_items = fetched
                news_last_updated = datetime.now().isoformat()
                news_last_error = ""
                save_news_cache(news_items)
            elif not news_items:
                news_last_error = "暂未获取到相关资讯"
        if emit_update:
            socketio.emit("news_updated", get_news_state())
        return True
    except Exception:
        with lock:
            news_last_error = "资讯获取失败，请稍后重试。"
        if emit_update:
            socketio.emit("news_updated", get_news_state())
        return False


def get_news_state():
    with lock:
        return {
            "items": list(news_items[:NEWS_LIMIT]),
            "updated_at": news_last_updated,
            "error": news_last_error,
        }


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
    items = risk_analysis_history if items is None else items
    return _risk_history_store().save(items)


def get_risk_analysis_history_state():
    with risk_history_lock:
        return _risk_history_store().build_state(risk_analysis_history)


def add_risk_analysis_history_entry(result, snapshot):
    global risk_analysis_history
    with risk_history_lock:
        store = _risk_history_store()
        risk_analysis_history, entry = store.add_entry(risk_analysis_history, result, snapshot)
        try:
            store.save(risk_analysis_history)
        except OSError as exc:
            logging.warning("failed to save risk analysis history: %s", exc)
        return entry


def clear_risk_analysis_history_state():
    global risk_analysis_history
    with risk_history_lock:
        risk_analysis_history = []
        try:
            _risk_history_store().clear()
        except OSError as exc:
            logging.warning("failed to clear risk analysis history: %s", exc)
        return _risk_history_store().build_state(risk_analysis_history)


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
    items = price_archive if items is None else items
    return _price_history_store().save_archive(items)


def add_price_history_entry(entry, force_save=False):
    global price_archive, last_price_history_save_at
    price_archive, last_price_history_save_at, point = _price_history_store().add_entry(
        price_archive,
        last_price_history_save_at,
        entry,
        force_save=force_save,
    )
    if point is None:
        return


def _filter_price_archive(minutes=None, limit=600):
    with lock:
        items = list(price_archive)
    return _price_history_store().filter_archive(items, minutes=minutes, limit=limit)


def _event_time_from_alert(entry):
    return event_timeline_core.event_time_from_alert(entry, today_date=today_date)


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
    with risk_history_lock:
        risk_items = list(risk_analysis_history[:RISK_ANALYSIS_HISTORY_LIMIT])
    with lock:
        current_news_items = list(news_items[:NEWS_LIMIT])
    return {
        "alert_entries": alert_log_export_entries(limit=ALERT_LOG_EXPORT_LIMIT),
        "risk_items": risk_items,
        "news_items": current_news_items,
        "fetch_status": get_fetch_status(),
        "source_health_state": get_source_health_state(),
        "source_comparison_state": get_source_comparison_state(),
        "today_date": today_date,
        "news_key": _news_key,
        "now_factory": datetime.now,
    }


def build_alert_timeline_events(start_time, end_time):
    return event_timeline_core.build_alert_timeline_events(
        start_time,
        end_time,
        alert_entries=alert_log_export_entries(limit=ALERT_LOG_EXPORT_LIMIT),
        today_date=today_date,
    )


def build_risk_timeline_events(start_time, end_time):
    with risk_history_lock:
        risk_items = list(risk_analysis_history[:RISK_ANALYSIS_HISTORY_LIMIT])
    return event_timeline_core.build_risk_timeline_events(start_time, end_time, risk_items=risk_items)


def build_news_timeline_events(start_time, end_time):
    with lock:
        items = list(news_items[:NEWS_LIMIT])
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
    with lock:
        items = list(price_archive)
    return _price_history_store().build_state(
        items,
        minutes=minutes,
        limit=limit,
        build_events=_build_price_event_state,
        format_number=_format_number,
    )


def build_price_history_csv(minutes=None):
    with lock:
        items = list(price_archive)
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


def _replace_alert_log_entry(updated):
    return AlertLogStore.replace_memory_entry(alert_log, updated)


def _update_alert_log_entry_payload(alert_id, updater):
    return _alert_log_store().update_entry_payload(alert_id, updater, memory_entries=alert_log)


def update_alert_log_status(alert_id, read=None, acknowledged=None):
    return _update_alert_log_entry_payload(
        alert_id,
        lambda entry: _apply_alert_log_status(entry, read=read, acknowledged=acknowledged),
    )


def _alert_resend_title(entry):
    return str(entry.get("title") or f"金价预警 - {alert_level_label(entry.get('type'))}")


def resend_alert_notification(alert_id):
    def updater(entry):
        updated = dict(entry)
        updated["notifications"] = dispatch_alert(updated, _alert_resend_title(updated))
        updated["notification_muted"] = False
        updated["notification_reason"] = ""
        updated["notification_message"] = ""
        updated["last_notification_resend_at"] = datetime.now().isoformat(timespec="seconds")
        return updated

    return _update_alert_log_entry_payload(alert_id, updater)


def alert_log_export_entries(limit=ALERT_LOG_EXPORT_LIMIT):
    return _alert_log_store().export_entries(alert_log, limit=limit)


def _format_alert_notifications(entry):
    return AlertLogStore.format_notifications(entry)


def build_alert_log_csv():
    return _alert_log_store().build_csv(alert_log)


def news_loop():
    while True:
        refresh_gold_news(emit_update=True)
        time.sleep(NEWS_REFRESH_INTERVAL)


news_items = load_news_cache()
risk_analysis_history = load_risk_analysis_history()
alert_log = load_alert_log_archive(limit=ALERT_LOG_MEMORY_LIMIT)
price_archive = load_price_history_archive()
if price_archive:
    price_history = list(price_archive[-360:])
initialize_market_cache()


def _format_number(value, digits=2):
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _summarize_price_series(points, field):
    values = [p.get(field) for p in points if p.get(field) is not None]
    if not values:
        return {
            "points": 0,
            "start": None,
            "end": None,
            "high": None,
            "low": None,
            "change": None,
            "change_pct": None,
        }
    start = values[0]
    end = values[-1]
    change = end - start
    return {
        "points": len(values),
        "start": _format_number(start),
        "end": _format_number(end),
        "high": _format_number(max(values)),
        "low": _format_number(min(values)),
        "change": _format_number(change),
        "change_pct": _format_number(change / start * 100 if start else 0),
    }


def _summarize_klines(candles):
    if not candles:
        return {
            "points": 0,
            "latest": None,
            "high": None,
            "low": None,
            "direction": "样本不足",
        }
    closes = [c.get("close") for c in candles if c.get("close") is not None]
    highs = [c.get("high") for c in candles if c.get("high") is not None]
    lows = [c.get("low") for c in candles if c.get("low") is not None]
    latest = candles[-1]
    if len(closes) < 2:
        direction = "样本不足"
    elif closes[-1] > closes[0]:
        direction = "上行"
    elif closes[-1] < closes[0]:
        direction = "下行"
    else:
        direction = "震荡"
    return {
        "points": len(candles),
        "latest": {
            "time": latest.get("time"),
            "open": _format_number(latest.get("open")),
            "high": _format_number(latest.get("high")),
            "low": _format_number(latest.get("low")),
            "close": _format_number(latest.get("close")),
        },
        "high": _format_number(max(highs) if highs else None),
        "low": _format_number(min(lows) if lows else None),
        "direction": direction,
    }


def _parse_iso_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def _history_window(points, minutes):
    if not points:
        return []
    latest_time = _parse_iso_datetime(points[-1].get("timestamp")) or datetime.now()
    cutoff = latest_time - timedelta(minutes=minutes)
    filtered = [
        item for item in points
        if (_parse_iso_datetime(item.get("timestamp")) or latest_time) >= cutoff
    ]
    if filtered:
        return filtered
    fallback_points = max(2, int(minutes * 6))
    return points[-fallback_points:]


def _trend_direction(summary):
    if summary.get("points", 0) < 2 or summary.get("change_pct") is None:
        return "样本不足"
    pct = summary.get("change_pct") or 0
    if abs(pct) < 0.03:
        return "震荡"
    return "上行" if pct > 0 else "下行"


def build_multi_period_trends(history):
    trends = []
    for minutes in RISK_ASSISTANT_TREND_PERIODS:
        window = _history_window(history, minutes)
        usd_summary = _summarize_price_series(window, "usd")
        rmb_summary = _summarize_price_series(window, "rmb")
        trends.append({
            "minutes": minutes,
            "points": len(window),
            "usd": usd_summary,
            "rmb": rmb_summary,
            "direction_usd": _trend_direction(usd_summary),
            "direction_rmb": _trend_direction(rmb_summary),
        })
    return trends


def assess_risk_data_quality(context):
    market = context.get("market", {})
    history = context.get("history_summary", {}).get("usd", {})
    kline = context.get("kline_summary", {}).get("usd", {})
    news_count = len(context.get("news", []))
    score = 100
    issues = []

    if market.get("price_usd") is None:
        score -= 35
        issues.append("国际金价缺失")
    if market.get("price_rmb") is None:
        score -= 25
        issues.append("人民币金价缺失")
    if market.get("gold_cached"):
        score -= 15
        issues.append("金价来自缓存")
    if market.get("rate_cached"):
        score -= 10
        issues.append("汇率来自缓存")
    if not market.get("last_fetch_ok"):
        score -= 10
        issues.append("最近一次行情刷新异常")

    history_points = history.get("points", 0)
    if history_points < 12:
        score -= 15
        issues.append("历史价格样本偏少")
    elif history_points < 60:
        score -= 6
        issues.append("历史样本不足 10 分钟")

    if kline.get("points", 0) < 2:
        score -= 10
        issues.append("5分钟K线样本不足")
    if news_count == 0:
        score -= 5
        issues.append("近期资讯为空")

    now = datetime.now()
    gold_time = _parse_iso_datetime(market.get("gold_time"))
    rate_time = _parse_iso_datetime(market.get("rate_time"))
    if gold_time and (now - gold_time).total_seconds() > 15 * 60:
        score -= 8
        issues.append("金价更新时间超过 15 分钟")
    if rate_time and (now - rate_time).total_seconds() > 60 * 60:
        score -= 5
        issues.append("汇率更新时间超过 1 小时")

    score = max(0, min(100, score))
    if score >= 85:
        level = "高"
    elif score >= 65:
        level = "中"
    else:
        level = "低"
    return {
        "score": score,
        "level": level,
        "issues": issues,
        "summary": "；".join(issues) if issues else "数据状态良好",
    }


def build_risk_scorecard(context):
    trends = context.get("multi_period_trends", [])
    history = context.get("history_summary", {})
    news = context.get("news", [])
    quality = context.get("data_quality", {})
    rmb_60 = history.get("rmb", {})
    rate_points = [p.get("rate") for p in history.get("latest_points", []) if p.get("rate") is not None]

    trend_changes = [
        abs((item.get("rmb") or {}).get("change_pct") or 0)
        for item in trends
        if (item.get("rmb") or {}).get("change_pct") is not None
    ]
    trend_strength = min(100, int((max(trend_changes) if trend_changes else 0) * 35))

    high = rmb_60.get("high")
    low = rmb_60.get("low")
    end = rmb_60.get("end")
    volatility_pct = ((high - low) / end * 100) if high is not None and low is not None and end else 0
    volatility_risk = min(100, int(volatility_pct * 25))

    if len(rate_points) >= 2 and rate_points[0]:
        fx_change_pct = abs((rate_points[-1] - rate_points[0]) / rate_points[0] * 100)
    else:
        fx_change_pct = 0
    fx_impact = min(100, int(fx_change_pct * 40))

    event_risk = 0
    for item in news:
        topic = str(item.get("topic") or "").lower()
        title = str(item.get("title") or "").lower()
        if any(key in f"{topic} {title}" for key in ("fed", "fomc", "inflation", "cpi", "jobs", "payroll", "dollar", "yield")):
            event_risk += 25
        else:
            event_risk += 12
    event_risk = min(100, event_risk)

    data_credibility = int(quality.get("score", 0) or 0)
    overall_risk = int(
        volatility_risk * 0.28
        + event_risk * 0.24
        + trend_strength * 0.22
        + fx_impact * 0.12
        + (100 - data_credibility) * 0.14
    )
    return {
        "overall_risk": max(0, min(100, overall_risk)),
        "trend_strength": trend_strength,
        "volatility_risk": volatility_risk,
        "fx_impact": fx_impact,
        "event_risk": event_risk,
        "data_credibility": data_credibility,
        "volatility_pct": _format_number(volatility_pct),
        "fx_change_pct": _format_number(fx_change_pct, 4),
    }


def build_risk_analysis_context(trigger=None, depth=None):
    depth = depth if depth in VALID_RISK_ASSISTANT_DEPTHS else get_settings_snapshot().get("risk_assistant_depth", "standard")
    if depth not in VALID_RISK_ASSISTANT_DEPTHS:
        depth = "standard"
    history_limit = {"quick": 120, "standard": 360, "deep": 1440}.get(depth, 360)
    news_limit = {"quick": 3, "standard": RISK_ASSISTANT_NEWS_LIMIT, "deep": 10}.get(depth, RISK_ASSISTANT_NEWS_LIMIT)
    with lock:
        source_history = price_archive if depth == "deep" and price_archive else price_history
        history = list(source_history[-history_limit:])
        candles = list(klines_5min[-72:])
        news = list(news_items[:news_limit])
        daily_change_usd = price_usd - today_open_usd if price_usd is not None and today_open_usd else None
        daily_change_rmb = price_rmb - today_open_rmb if price_rmb is not None and today_open_rmb else None
        context = {
            "analysis_time": datetime.now().isoformat(timespec="seconds"),
            "analysis_depth": depth,
            "market": {
                "price_usd": _format_number(price_usd),
                "price_rmb": _format_number(price_rmb),
                "previous_usd": _format_number(previous_usd),
                "previous_rmb": _format_number(previous_rmb),
                "usdcny_rate": _format_number(usdcny_rate, 4),
                "gold_source": gold_price_source,
                "gold_time": gold_price_time,
                "gold_cached": gold_price_cached,
                "gold_error": gold_price_error,
                "rate_source": usdcny_rate_source,
                "rate_time": usdcny_rate_time,
                "rate_cached": usdcny_rate_cached,
                "rate_error": usdcny_rate_error,
                "last_fetch_ok": last_fetch_ok,
                "last_fetch_error": last_fetch_error,
                "last_fetch_time": last_fetch_time,
            },
            "daily": {
                "date": today_date,
                "open_usd": _format_number(today_open_usd),
                "high_usd": _format_number(today_high_usd),
                "low_usd": _format_number(today_low_usd),
                "change_usd": _format_number(daily_change_usd),
                "pct_usd": _format_number(daily_change_usd / today_open_usd * 100 if daily_change_usd is not None and today_open_usd else None),
                "open_rmb": _format_number(today_open_rmb),
                "high_rmb": _format_number(today_high_rmb),
                "low_rmb": _format_number(today_low_rmb),
                "change_rmb": _format_number(daily_change_rmb),
                "pct_rmb": _format_number(daily_change_rmb / today_open_rmb * 100 if daily_change_rmb is not None and today_open_rmb else None),
            },
            "history_summary": {
                "minutes": 60,
                "usd": _summarize_price_series(history, "usd"),
                "rmb": _summarize_price_series(history, "rmb"),
                "latest_points": history[-12:],
            },
            "multi_period_trends": build_multi_period_trends(history),
            "kline_summary": {
                "period": "5min",
                "usd": _summarize_klines(candles),
                "latest_candles": candles[-12:],
            },
            "news": [
                {
                    "title": item.get("title", ""),
                    "source": item.get("source", ""),
                    "time": item.get("time"),
                    "topic": item.get("topic", ""),
                    "summary": item.get("summary", ""),
                }
                for item in news
            ],
        }
    if isinstance(trigger, dict):
        context["manual_trigger"] = {
            "source": str(trigger.get("source") or "manual"),
            "time": str(trigger.get("time") or ""),
            "type": str(trigger.get("type") or ""),
            "mode": str(trigger.get("mode") or ""),
            "message": str(trigger.get("message") or "")[:500],
        }
    context["sample_warning"] = "样本不足" if len(history) < 12 or len(candles) < 2 else ""
    context["data_quality"] = assess_risk_data_quality(context)
    context["risk_scorecard"] = build_risk_scorecard(context)
    return context


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
    with risk_history_lock:
        return risk_analysis_core.find_recent_cache(risk_analysis_history, snapshot, cache_minutes)


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


# ---------- K线聚合 ----------
def _aggregate_klines():
    """从 price_history 聚合 5 分钟 K 线"""
    global klines_5min
    if len(price_history) < 2:
        return

    now = datetime.now()
    bucket_minute = (now.minute // 5) * 5
    bucket_label = now.replace(minute=bucket_minute, second=0, microsecond=0)

    recent = price_history[-30:]  # 最近 5 分钟数据
    usd_prices = [p["usd"] for p in recent if p["usd"] is not None]
    if not usd_prices:
        return

    candle = {
        "open": usd_prices[0],
        "high": max(usd_prices),
        "low": min(usd_prices),
        "close": usd_prices[-1],
        "time": bucket_label.strftime("%H:%M"),
        "timestamp": bucket_label.isoformat(),
    }

    if klines_5min and klines_5min[-1]["time"] == candle["time"]:
        klines_5min[-1] = candle
    else:
        klines_5min.append(candle)
    if len(klines_5min) > 96:  # 保留 8 小时
        klines_5min = klines_5min[-96:]


# ---------- 后台轮询 ----------
def fetch_price_once():
    global price_usd, price_rmb, previous_usd, previous_rmb
    global usdcny_rate, price_history, alert_log, last_fetch_ok, last_fetch_error, last_fetch_time
    global usdcny_rate_source, usdcny_rate_time, usdcny_rate_cached, usdcny_rate_error
    global gold_price_source, gold_price_time, gold_price_cached, gold_price_error
    global today_date, today_open_usd, today_high_usd, today_low_usd
    global today_open_rmb, today_high_rmb, today_low_rmb

    if not price_refresh_lock.acquire(blocking=False):
        socketio.emit("fetch_status", build_fetch_status(False, "已有行情刷新正在进行", retryable=False))
        return False
    try:
        data, rate_info, source_name, gold_error, forex_error = fetch_market_data_result()
        now = datetime.now()
        now_str = now.strftime("%H:%M:%S")
        now_iso = now.isoformat()
        today_str = now.strftime("%Y-%m-%d")
        source_comparison = refresh_source_comparison(
            data,
            source_name,
            primary_cached=bool(data.get("cached")) if isinstance(data, dict) else False,
        ) if data is not None else get_source_comparison_state()

        with lock:
            if data is not None:
                cny_rate = rate_info.get("value") if isinstance(rate_info, dict) else None
                rate_source = rate_info.get("source", "") if isinstance(rate_info, dict) else ""
                rate_time = rate_info.get("timestamp") if isinstance(rate_info, dict) else None
                rate_cached = bool(rate_info.get("cached")) if isinstance(rate_info, dict) else False
                source_name = source_name or data.get("source", "")
                gold_cached = bool(data.get("cached")) or str(source_name).startswith("缓存金价")
                gold_time = data.get("timestamp") if gold_cached else now_iso
                status_ok = not gold_cached and (cny_rate is not None or usdcny_rate is not None)
                last_fetch_ok = status_ok
                if status_ok:
                    last_fetch_error = ""
                elif gold_cached:
                    last_fetch_error = gold_error or "实时金价源暂不可用，正在使用缓存金价"
                else:
                    last_fetch_error = forex_error or "汇率源暂未返回，人民币价格暂不可用"
                last_fetch_time = now_iso
                gold_price_source = source_name
                gold_price_time = gold_time
                gold_price_cached = gold_cached
                gold_price_error = gold_error or ""
                if cny_rate:
                    usdcny_rate = cny_rate
                    usdcny_rate_source = rate_source
                    usdcny_rate_time = rate_time
                    usdcny_rate_cached = rate_cached
                    usdcny_rate_error = forex_error or ""
                previous_usd = price_usd
                previous_rmb = price_rmb
                price_usd = data["close"]

                if usdcny_rate:
                    price_rmb = round(price_usd * usdcny_rate / OZ_TO_GRAM, 2)
                if previous_rmb is None:
                    previous_rmb = price_rmb

                # --- 日内统计 ---
                if today_date != today_str:
                    today_date = today_str
                    today_open_usd = data["open"]
                    today_high_usd = data["high"]
                    today_low_usd = data["low"]
                    if usdcny_rate:
                        today_open_rmb = round(today_open_usd * usdcny_rate / OZ_TO_GRAM, 2)
                        today_high_rmb = round(data["high"] * usdcny_rate / OZ_TO_GRAM, 2)
                        today_low_rmb = round(data["low"] * usdcny_rate / OZ_TO_GRAM, 2)
                else:
                    if today_open_usd is None:
                        today_open_usd = data["open"]
                    today_high_usd = max(today_high_usd or 0, data["high"])
                    today_low_usd = min(today_low_usd or float("inf"), data["low"])
                    if usdcny_rate:
                        today_high_rmb = round(today_high_usd * usdcny_rate / OZ_TO_GRAM, 2)
                        today_low_rmb = round(today_low_usd * usdcny_rate / OZ_TO_GRAM, 2)
                        if today_open_rmb is None:
                            today_open_rmb = round(today_open_usd * usdcny_rate / OZ_TO_GRAM, 2)

                # --- 计算日内涨跌 ---
                daily_change_usd = round(price_usd - today_open_usd, 2) if today_open_usd else 0
                daily_pct_usd = round(daily_change_usd / today_open_usd * 100, 2) if today_open_usd else 0
                daily_change_rmb = round(price_rmb - today_open_rmb, 2) if price_rmb and today_open_rmb else 0
                daily_pct_rmb = round(daily_change_rmb / today_open_rmb * 100, 2) if today_open_rmb and today_open_rmb != 0 else 0

                # --- 更新历史 ---
                history_entry = {
                    "usd": price_usd, "rmb": price_rmb, "rate": usdcny_rate,
                    "time": now_str, "timestamp": now_iso,
                }
                price_history.append(history_entry)
                if len(price_history) > 360:  # 保留 1 小时
                    price_history = price_history[-360:]
                add_price_history_entry(history_entry)

                _aggregate_klines()

                # --- 涨跌 ---
                chg_usd = round(price_usd - previous_usd, 2) if previous_usd else 0
                pct_usd = round(chg_usd / previous_usd * 100, 2) if previous_usd else 0
                chg_rmb = round(price_rmb - previous_rmb, 2) if price_rmb and previous_rmb else 0
                pct_rmb = round(chg_rmb / previous_rmb * 100, 2) if previous_rmb and price_rmb else 0

                if previous_rmb is None and price_rmb is not None:
                    previous_rmb = price_rmb

                # 构建日内统计
                daily_stats = {
                    "open_usd": today_open_usd,
                    "high_usd": today_high_usd,
                    "low_usd": today_low_usd,
                    "open_rmb": today_open_rmb,
                    "high_rmb": today_high_rmb,
                    "low_rmb": today_low_rmb,
                    "change_usd": daily_change_usd,
                    "pct_usd": daily_pct_usd,
                    "change_rmb": daily_change_rmb,
                    "pct_rmb": daily_pct_rmb,
                }

                # --- 推送价格更新 ---
                socketio.emit("price_update", {
                    "usd": price_usd, "rmb": price_rmb, "rate": usdcny_rate,
                    "gold_source": gold_price_source,
                    "gold_time": gold_price_time,
                    "gold_cached": gold_price_cached,
                    "gold_error": gold_price_error,
                    "rate_source": usdcny_rate_source,
                    "rate_time": usdcny_rate_time,
                    "rate_cached": usdcny_rate_cached,
                    "rate_error": usdcny_rate_error,
                    "previous_usd": previous_usd, "previous_rmb": previous_rmb,
                    "change_usd": chg_usd, "change_pct_usd": pct_usd,
                    "change_rmb": chg_rmb, "change_pct_rmb": pct_rmb,
                    "time": now_str, "timestamp": now_iso,
                    "daily": daily_stats,
                    "source_comparison": source_comparison,
                })
                desktop_title = format_price_title(price_rmb, price_usd)
                update_desktop_price_title(desktop_title)
                update_floating_price(price_rmb, price_usd, pct_rmb)

                # --- 检查阈值 ---
                _check_thresholds("usd", price_usd, now_str)
                if price_rmb is not None:
                    _check_thresholds("rmb", price_rmb, now_str)
                check_watch_targets(now_str)

                # --- 检查波动率 ---
                _check_volatility(now_str)
                if cny_rate:
                    rate_message = (
                        f"使用缓存汇率 {cny_rate:.4f}（{rate_source}）"
                        if rate_cached else f"汇率已更新 {cny_rate:.4f}（{rate_source}）"
                    )
                else:
                    rate_message = "汇率暂未更新"
                gold_message = (
                    f"使用缓存金价（{source_name}）"
                    if gold_cached else f"金价已更新（{source_name}）"
                )
                socketio.emit("fetch_status", build_fetch_status(
                    status_ok,
                    f"{gold_message}，{rate_message}",
                    gold_ok=not gold_cached,
                    forex_ok=cny_rate is not None,
                    error="" if status_ok else last_fetch_error,
                    retryable=True,
                ))
                history_state = build_price_history_state(limit=240)
                history_state["scope"] = "live"
                socketio.emit("price_history_updated", history_state)
                return True
            else:
                last_fetch_ok = False
                last_fetch_error = gold_error or "Stooq 金价接口无响应或返回格式异常"
                last_fetch_time = now_iso
                status = build_fetch_status(
                    False,
                    "无法获取金价数据，请检查网络或稍后重试",
                    gold_ok=False,
                    forex_ok=rate_info is not None,
                    error=last_fetch_error,
                    retryable=True,
                )
                socketio.emit("fetch_error", status)
                socketio.emit("fetch_status", status)
                return False
    finally:
        price_refresh_lock.release()


def background_loop():
    while True:
        fetch_price_once()

        time.sleep(10)


# ---------- 阈值检查 (多级) ----------
def _check_thresholds(mode, price, now_str):
    plan = targets_core.build_threshold_alert(
        mode,
        price,
        now_str,
        thresholds,
        alerted_flags,
        usdcny_rate=usdcny_rate,
        usdcny_rate_cached=usdcny_rate_cached,
        usdcny_rate_source=usdcny_rate_source,
    )
    if plan:
        emit_alert(plan["alert"], plan["title"])


# ---------- 波动率检查 ----------
def _check_volatility(now_str):
    global last_volatility_check
    plan, last_volatility_check = targets_core.build_volatility_alert(
        price_history,
        volatility_config,
        now_str,
        last_checked_at=last_volatility_check,
        now_factory=datetime.now,
    )
    if plan:
        emit_alert(plan["alert"], plan["title"])


# ---------- Flask 路由 ----------
@app.route("/")
def index():
    return render_template("index.html", socket_access_token=SOCKET_ACCESS_TOKEN)


@app.route("/api/price")
def api_price():
    with lock:
        return jsonify({
            "usd": price_usd, "rmb": price_rmb, "rate": usdcny_rate,
            "gold_source": gold_price_source,
            "gold_time": gold_price_time,
            "gold_cached": gold_price_cached,
            "gold_error": gold_price_error,
            "rate_source": usdcny_rate_source,
            "rate_time": usdcny_rate_time,
            "rate_cached": usdcny_rate_cached,
            "rate_error": usdcny_rate_error,
            "previous_usd": previous_usd, "previous_rmb": previous_rmb,
            "time": price_history[-1]["time"] if price_history else None,
            "ok": last_fetch_ok,
            "klines_5min": klines_5min[-72:],
        })


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(os.path.join(_basedir, "static"), "icon-64.png", mimetype="image/png")


@app.route("/manifest.json")
def manifest():
    return send_from_directory(_basedir, "manifest.json")


@app.route("/sw.js")
def service_worker():
    return send_from_directory(_basedir, "sw.js", mimetype="application/javascript")


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(os.path.join(_basedir, "static"), filename)


# ---------- Socket.IO 事件 ----------
@socketio.on("connect")
def on_connect(auth=None):
    if not is_socket_authorized(auth):
        return False

    with lock:
        state = {
            "usd": price_usd, "rmb": price_rmb, "rate": usdcny_rate,
            "gold_source": gold_price_source,
            "gold_time": gold_price_time,
            "gold_cached": gold_price_cached,
            "gold_error": gold_price_error,
            "rate_source": usdcny_rate_source,
            "rate_time": usdcny_rate_time,
            "rate_cached": usdcny_rate_cached,
            "rate_error": usdcny_rate_error,
            "previous_usd": previous_usd, "previous_rmb": previous_rmb,
            "history": price_history[-60:],
            "klines_5min": klines_5min[-72:],
            "thresholds": dict(thresholds),
            "volatility_config": dict(volatility_config),
            "watch_targets": get_watch_targets_state(),
            "portfolio": build_portfolio_state(),
            "settings": public_settings_snapshot(),
            "alert_log": alert_log[-20:],
            "ok": last_fetch_ok,
            "fetch_status": _current_fetch_status_locked(),
            "source_health": get_source_health_state(),
            "source_comparison": get_source_comparison_state(),
            "price_history_state": build_price_history_state(limit=240),
            "daily": {
                "open_usd": today_open_usd, "high_usd": today_high_usd, "low_usd": today_low_usd,
                "open_rmb": today_open_rmb, "high_rmb": today_high_rmb, "low_rmb": today_low_rmb,
            },
        }
    state["news"] = get_news_state()
    state["risk_analysis_history"] = get_risk_analysis_history_state()
    emit("init_state", state)


@socketio.on("set_threshold")
def on_set_threshold(data):
    if not isinstance(data, dict):
        emit("threshold_error", {"message": "阈值格式无效"})
        return

    with lock:
        mode = data.get("mode", "rmb")
        ttype = data.get("type")       # "upper_warning", "upper_critical", etc.
        value = data.get("value")
        if mode not in THRESHOLD_MODES or ttype not in THRESHOLD_TYPES:
            emit("threshold_error", {"message": "阈值类型无效"})
            return
        key = f"{ttype}_{mode}"

        try:
            if value in (None, ""):
                thresholds[key] = None
            else:
                thresholds[key] = float(value)
        except (ValueError, TypeError):
            emit("threshold_error", {"message": "请输入有效的数字"})
            return

        alerted_flags.pop(key, None)  # 重置去重标记
        try:
            save_thresholds(thresholds)
        except OSError:
            emit("threshold_error", {"message": "阈值保存失败，请检查配置目录权限。"})
            return

        socketio.emit("thresholds_updated", thresholds)

        cur = price_usd if mode == "usd" else price_rmb
        if cur is not None:
            _check_thresholds(mode, cur, datetime.now().strftime("%H:%M:%S"))


@socketio.on("clear_threshold")
def on_clear_threshold(data):
    if not isinstance(data, dict):
        emit("threshold_error", {"message": "阈值格式无效"})
        return

    mode = data.get("mode", "rmb")
    ttype = data.get("type")
    if mode not in THRESHOLD_MODES or (ttype != "all" and ttype not in THRESHOLD_TYPES):
        emit("threshold_error", {"message": "阈值类型无效"})
        return

    with lock:
        if ttype == "all":
            for prefix in THRESHOLD_TYPES:
                thresholds[f"{prefix}_{mode}"] = None
        else:
            thresholds[f"{ttype}_{mode}"] = None
        try:
            save_thresholds(thresholds)
        except OSError:
            emit("threshold_error", {"message": "阈值保存失败，请检查配置目录权限。"})
            return
        socketio.emit("thresholds_updated", thresholds)


@socketio.on("set_volatility")
def on_set_volatility(data):
    global volatility_config
    if not isinstance(data, dict):
        emit("threshold_error", {"message": "波动率预警格式无效"})
        return

    with lock:
        pct = data.get("percent")
        mins = data.get("minutes", 10)
        enabled = data.get("enabled", False)
        normalized = _normalize_volatility_config({
            "percent": pct,
            "minutes": mins,
            "enabled": enabled,
        })
        if bool(enabled):
            try:
                raw_minutes = int(mins)
            except (TypeError, ValueError):
                raw_minutes = 0
            if normalized["percent"] is None or raw_minutes < 1:
                emit("threshold_error", {"message": "请输入有效的波动率预警数字"})
                return
        volatility_config = normalized
        try:
            saved_thresholds = save_thresholds({
                **thresholds,
                "volatility_config": volatility_config,
            })
        except ValueError:
            emit("threshold_error", {"message": "请输入有效的数字"})
            return
        except OSError:
            emit("threshold_error", {"message": "波动率预警保存失败，请检查配置目录权限。"})
            return
        volatility_config = saved_thresholds["volatility_config"]
        socketio.emit("volatility_updated", volatility_config)


@socketio.on("set_watch_target")
def on_set_watch_target(data):
    try:
        state = upsert_watch_target(data)
    except ValueError as exc:
        emit("watch_target_error", {"message": str(exc)})
        return
    except OSError:
        emit("watch_target_error", {"message": "观察清单保存失败，请检查配置目录权限。"})
        return
    socketio.emit("watch_targets_updated", state)


@socketio.on("delete_watch_target")
def on_delete_watch_target(data=None):
    target_id = data.get("id") if isinstance(data, dict) else None
    try:
        ok, state = delete_watch_target(target_id)
    except OSError:
        emit("watch_target_error", {"message": "观察清单保存失败，请检查配置目录权限。"})
        return
    if not ok:
        emit("watch_target_error", {"message": "未找到观察项"})
        return
    socketio.emit("watch_targets_updated", state)


@socketio.on("get_portfolio")
def on_get_portfolio():
    emit("portfolio_updated", build_portfolio_state())


@socketio.on("save_portfolio_position")
def on_save_portfolio_position(data):
    try:
        state = upsert_portfolio_position(data)
    except ValueError as exc:
        emit("portfolio_error", {"message": str(exc)})
        return
    except OSError:
        emit("portfolio_error", {"message": "持仓保存失败，请检查配置目录权限。"})
        return
    socketio.emit("portfolio_updated", state)


@socketio.on("delete_portfolio_position")
def on_delete_portfolio_position(data=None):
    position_id = data.get("id") if isinstance(data, dict) else None
    try:
        ok, state = delete_portfolio_position(position_id)
    except OSError:
        emit("portfolio_error", {"message": "持仓保存失败，请检查配置目录权限。"})
        return
    if not ok:
        emit("portfolio_error", {"message": "未找到持仓记录"})
        emit("portfolio_updated", state)
        return
    socketio.emit("portfolio_updated", state)


@socketio.on("save_portfolio_transaction")
def on_save_portfolio_transaction(data):
    try:
        state = upsert_portfolio_transaction(data)
    except ValueError as exc:
        emit("portfolio_error", {"message": str(exc)})
        return
    except OSError:
        emit("portfolio_error", {"message": "持仓流水保存失败，请检查配置目录权限。"})
        return
    socketio.emit("portfolio_updated", state)


@socketio.on("delete_portfolio_transaction")
def on_delete_portfolio_transaction(data=None):
    transaction_id = data.get("id") if isinstance(data, dict) else None
    try:
        ok, state = delete_portfolio_transaction(transaction_id)
    except ValueError as exc:
        emit("portfolio_error", {"message": str(exc)})
        return
    except OSError:
        emit("portfolio_error", {"message": "持仓流水保存失败，请检查配置目录权限。"})
        return
    if not ok:
        emit("portfolio_error", {"message": "未找到持仓流水"})
        emit("portfolio_updated", state)
        return
    socketio.emit("portfolio_updated", state)


@socketio.on("export_portfolio")
def on_export_portfolio(data=None):
    kind = data.get("kind") if isinstance(data, dict) else "positions"
    if kind not in {"positions", "transactions"}:
        kind = "positions"
    suffix = "transactions" if kind == "transactions" else "positions"
    filename = f"GoldMonitor-portfolio-{suffix}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"
    try:
        content, count = build_portfolio_csv(kind)
        saved_path = save_export_file(filename, content)
        emit("portfolio_exported", {
            "ok": True,
            "kind": kind,
            "filename": filename,
            "saved_path": saved_path,
            "count": count,
        })
    except OSError as exc:
        emit("portfolio_export_error", {"message": f"持仓导出失败: {exc}"})


@socketio.on("toggle_watch_target")
def on_toggle_watch_target(data=None):
    if not isinstance(data, dict):
        emit("watch_target_error", {"message": "观察项格式无效"})
        return
    try:
        ok, state = toggle_watch_target(data.get("id"), data.get("enabled"))
    except (ValueError, OSError):
        emit("watch_target_error", {"message": "观察清单保存失败，请检查配置目录权限。"})
        return
    if not ok:
        emit("watch_target_error", {"message": "未找到观察项"})
        return
    socketio.emit("watch_targets_updated", state)


@socketio.on("reset_watch_target")
def on_reset_watch_target(data=None):
    target_id = data.get("id") if isinstance(data, dict) else None
    try:
        ok, state = reset_watch_target(target_id)
    except (ValueError, OSError):
        emit("watch_target_error", {"message": "观察清单保存失败，请检查配置目录权限。"})
        return
    if not ok:
        emit("watch_target_error", {"message": "未找到观察项"})
        return
    socketio.emit("watch_targets_updated", state)


@socketio.on("get_settings")
def on_get_settings():
    emit("settings_updated", public_settings_snapshot())


@socketio.on("update_settings")
def on_update_settings(data):
    if not isinstance(data, dict):
        emit("settings_error", {"message": "设置格式无效"})
        return

    current = get_settings_snapshot()
    secret_clear_flags = {
        "smtp_password": "smtp_password_clear",
        "deepseek_api_key": "deepseek_api_key_clear",
        "openai_compatible_api_key": "openai_compatible_api_key_clear",
    }
    current = settings_store_core.merge_settings_update(
        current,
        data,
        allowed_keys=set(DEFAULT_SETTINGS),
        secret_clear_flags=secret_clear_flags,
    )
    try:
        updated, startup_error = apply_settings(current)
    except OSError:
        emit("settings_error", {"message": "设置保存失败，请检查配置目录权限。"})
        emit("settings_updated", public_settings_snapshot())
        return
    if startup_error:
        emit("settings_error", {"message": "开机自启动设置失败，请检查系统权限。"})
    socketio.emit("settings_updated", public_settings_snapshot(updated))


@socketio.on("request_risk_analysis")
def on_request_risk_analysis(data=None):
    global risk_analysis_last_started
    settings = get_settings_snapshot()
    if not settings.get("risk_assistant_enabled", True):
        emit("risk_analysis_error", {"message": "风险分析助手已关闭，请先在设置中启用。"})
        return
    provider = settings.get("risk_assistant_provider", "deepseek")
    if provider not in VALID_RISK_ASSISTANT_PROVIDERS:
        emit("risk_analysis_error", {"message": "暂不支持当前模型提供商。"})
        return
    provider_key = settings.get("deepseek_api_key") if provider == "deepseek" else settings.get("openai_compatible_api_key")
    if not provider_key:
        emit("risk_analysis_error", {"message": "请先在设置中配置当前模型提供商的 API Key。"})
        return
    trigger = data.get("trigger") if isinstance(data, dict) else None
    force = bool(data.get("force")) if isinstance(data, dict) else False
    context = build_risk_analysis_context(trigger=trigger, depth=settings.get("risk_assistant_depth", "standard"))
    snapshot = build_risk_analysis_snapshot(context)
    cache_minutes = settings.get("risk_assistant_cache_minutes", 0)
    if not force:
        cached = find_recent_risk_analysis_cache(snapshot, cache_minutes)
        if cached:
            emit("risk_analysis_cache_hit", {
                "ok": True,
                "provider": cached.get("provider"),
                "model": cached.get("model"),
                "content": cached.get("content"),
                "structured": cached.get("structured", {}),
                "usage": cached.get("usage"),
                "snapshot": cached.get("snapshot", snapshot),
                "history_entry": cached,
                "cache_age_seconds": cached.get("cache_age_seconds", 0),
                "trigger": trigger,
                "message": "已找到最近同一行情分析，可直接查看，也可以选择重新分析。",
            })
            return
    cooldown = settings.get("risk_assistant_cooldown_seconds", 0)
    now_monotonic = time.monotonic()
    if cooldown and risk_analysis_last_started and now_monotonic - risk_analysis_last_started < cooldown:
        remaining = max(1, int(cooldown - (now_monotonic - risk_analysis_last_started)))
        emit("risk_analysis_error", {"message": f"分析冷却中，请 {remaining} 秒后再试。"})
        return
    if not risk_analysis_lock.acquire(blocking=False):
        emit("risk_analysis_error", {"message": "已有风险分析正在进行，请稍后再试。"})
        return

    risk_analysis_last_started = now_monotonic
    sid = request.sid
    emit("risk_analysis_status", {"running": True, "message": "正在生成风险分析..."})

    def _analyze():
        try:
            result, error = run_risk_analysis(settings, context)
            if error:
                socketio.emit("risk_analysis_error", {"message": error, "snapshot": snapshot}, room=sid)
                return
            history_entry = add_risk_analysis_history_entry(result, snapshot)
            socketio.emit("risk_analysis_result", {
                "ok": True,
                "provider": result.get("provider"),
                "model": result.get("model"),
                "content": result.get("content"),
                "structured": result.get("structured", {}),
                "usage": result.get("usage"),
                "snapshot": snapshot,
                "history_entry": history_entry,
            }, room=sid)
            socketio.emit("risk_analysis_history_updated", get_risk_analysis_history_state(), room=sid)
        finally:
            socketio.emit("risk_analysis_status", {"running": False, "message": ""}, room=sid)
            risk_analysis_lock.release()

    threading.Thread(target=_analyze, daemon=True).start()


@socketio.on("get_risk_model_options")
def on_get_risk_model_options(data=None):
    settings = get_settings_snapshot()
    provider = settings.get("risk_assistant_provider", "deepseek")
    if isinstance(data, dict) and data.get("provider") in VALID_RISK_ASSISTANT_PROVIDERS:
        provider = data.get("provider")
    emit("risk_model_options_updated", fetch_risk_model_options(settings, provider))


@socketio.on("test_risk_model")
def on_test_risk_model():
    emit("risk_model_test_result", test_risk_model_availability(get_settings_snapshot()))


@socketio.on("get_risk_analysis_history")
def on_get_risk_analysis_history():
    emit("risk_analysis_history_updated", get_risk_analysis_history_state())


@socketio.on("clear_risk_analysis_history")
def on_clear_risk_analysis_history():
    emit("risk_analysis_history_updated", clear_risk_analysis_history_state())


@socketio.on("test_email")
def on_test_email():
    """发送测试邮件，验证 SMTP 配置是否正确"""
    settings = get_settings_snapshot()
    server = settings.get("smtp_server", "").strip()
    sender = settings.get("smtp_sender", "").strip()
    recipient = settings.get("smtp_recipient", "").strip()

    if not (server and sender and recipient):
        emit("test_email_result", {"ok": False, "message": "SMTP 配置不完整，请先填写服务器、发件邮箱和收件邮箱。"})
        return

    def _test():
        error = EmailNotifier.send(
            alert_type="warning",
            title="测试邮件 - 金价监控",
            message="这是一封测试邮件。\n\n如果您收到此邮件，说明 SMTP 配置正确，金价预警通知将正常工作。",
            timeout=10,
            blocking=True,
        )
        if error:
            socketio.emit("test_email_result", {"ok": False, "message": f"发送失败: {error}"})
        else:
            socketio.emit("test_email_result", {"ok": True, "message": "测试邮件发送成功！请检查收件箱（如未收到请查看垃圾邮件文件夹）。"})

    threading.Thread(target=_test, daemon=True).start()


@socketio.on("test_webhook")
def on_test_webhook():
    """发送测试 Webhook，验证通知地址是否正确"""
    settings = get_settings_snapshot()
    if not settings.get("webhook_enabled", False):
        emit("test_webhook_result", {"ok": False, "message": "Webhook 通知未启用，请先打开开关。"})
        return
    if not settings.get("webhook_url", "").strip():
        emit("test_webhook_result", {"ok": False, "message": "Webhook 地址未配置，请先填写 HTTPS 地址。"})
        return

    def _test():
        error = WebhookNotifier.send(
            alert_type="warning",
            title="测试 Webhook - 金价监控",
            message="这是一条测试 Webhook，用于验证金价预警通知配置。",
            timeout=8,
            blocking=True,
        )
        if error:
            socketio.emit("test_webhook_result", {"ok": False, "message": f"发送失败: {error}"})
        else:
            socketio.emit("test_webhook_result", {"ok": True, "message": "测试 Webhook 发送成功。"})

    threading.Thread(target=_test, daemon=True).start()


@socketio.on("close_choice")
def on_close_choice(data):
    if not isinstance(data, dict):
        data = {}

    choice = data.get("choice")
    remember = bool(data.get("remember"))
    if choice not in ("minimize_to_tray", "exit", "cancel"):
        return

    if remember and choice in ("minimize_to_tray", "exit"):
        snapshot = get_settings_snapshot()
        snapshot["close_behavior"] = choice
        snapshot["close_remembered"] = True
        try:
            save_settings(snapshot)
        except OSError:
            pass
        socketio.emit("settings_updated", public_settings_snapshot())

    if choice == "minimize_to_tray":
        hide_main_window()
    elif choice == "exit":
        exit_app()


@socketio.on("get_news")
def on_get_news():
    emit("news_updated", get_news_state())


@socketio.on("refresh_price")
def on_refresh_price():
    emit("fetch_status", build_fetch_status(False, "正在重新获取行情数据...", retryable=False))
    threading.Thread(target=fetch_price_once, daemon=True).start()


@socketio.on("refresh_news")
def on_refresh_news():
    emit("news_updated", {
        **get_news_state(),
        "loading": True,
    })
    threading.Thread(target=refresh_gold_news, daemon=True).start()


@socketio.on("get_source_health")
def on_get_source_health():
    emit("source_health_updated", get_source_health_state())


@socketio.on("get_price_history")
def on_get_price_history(data=None):
    minutes = None
    limit = 600
    period = None
    scope = "history"
    if isinstance(data, dict):
        period = str(data.get("period") or "").strip() or None
        scope = str(data.get("scope") or "history").strip() or "history"
        try:
            minutes = int(data.get("minutes")) if data.get("minutes") else None
        except (TypeError, ValueError):
            minutes = None
        try:
            limit = max(1, min(PRICE_HISTORY_EXPORT_LIMIT, int(data.get("limit", limit))))
        except (TypeError, ValueError):
            limit = 600
    state = build_price_history_state(minutes=minutes, limit=limit)
    state["period"] = period
    state["scope"] = scope
    emit("price_history_updated", state)


@socketio.on("get_event_timeline")
def on_get_event_timeline(data=None):
    try:
        request_args = normalize_event_timeline_request(data)
        state = build_event_timeline_state(**request_args)
        emit("event_timeline_updated", state)
    except Exception as exc:
        logging.warning("事件时间轴生成失败: %s", exc)
        emit("event_timeline_error", {"message": "事件时间轴加载失败，请稍后重试。"})


@socketio.on("export_review_report")
def on_export_review_report(data=None):
    try:
        request_args = normalize_event_timeline_request(data)
        state = build_event_timeline_state(**request_args)
        content = build_review_report(state)
        filename = event_timeline_core.review_report_filename(prefix=REVIEW_REPORT_EXPORT_PREFIX)
        saved_path = save_review_report(content, filename)
        emit("review_report_exported", {
            "ok": True,
            "filename": filename,
            "saved_path": saved_path,
            "count": state.get("summary", {}).get("total", 0),
        })
    except OSError as exc:
        emit("review_report_error", {"message": f"复盘报告导出失败: {exc}"})
    except Exception as exc:
        logging.warning("复盘报告导出失败: %s", exc)
        emit("review_report_error", {"message": "复盘报告导出失败，请稍后重试。"})


@socketio.on("export_price_history")
def on_export_price_history(data=None):
    minutes = None
    if isinstance(data, dict):
        try:
            minutes = int(data.get("minutes")) if data.get("minutes") else None
        except (TypeError, ValueError):
            minutes = None
    content, count = build_price_history_csv(minutes=minutes)
    emit("price_history_export_ready", {
        "filename": f"GoldMonitor-price-history-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv",
        "content": content,
        "count": count,
    })


@socketio.on("export_alert_log")
def on_export_alert_log():
    filename = f"GoldMonitor-alert-log-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"
    try:
        content, count = build_alert_log_csv()
        saved_path = save_export_file(filename, content)
        emit("alert_log_exported", {
            "ok": True,
            "filename": filename,
            "saved_path": saved_path,
            "count": count,
        })
    except OSError as exc:
        emit("alert_log_export_error", {"message": f"告警记录导出失败: {exc}"})


@socketio.on("clear_alert_log")
def on_clear_alert_log():
    ok = clear_alert_log_archive()
    if ok:
        alert_log.clear()
    socketio.emit("alert_log_cleared", {"ok": ok})


@socketio.on("update_alert_log_status")
def on_update_alert_log_status(data=None):
    if not isinstance(data, dict):
        emit("alert_log_status_error", {"message": "告警记录状态参数无效"})
        return
    ok, entry = update_alert_log_status(
        data.get("id"),
        read=data.get("read") if "read" in data else None,
        acknowledged=data.get("acknowledged") if "acknowledged" in data else None,
    )
    if not ok:
        emit("alert_log_status_error", {"message": "未找到对应告警记录"})
        return
    socketio.emit("alert_log_status_updated", {"ok": True, "entry": entry})


@socketio.on("resend_alert_notification")
def on_resend_alert_notification(data=None):
    if not isinstance(data, dict):
        emit("alert_notification_resend_error", {"message": "告警通知重发参数无效"})
        return
    ok, entry = resend_alert_notification(data.get("id"))
    if not ok:
        emit("alert_notification_resend_error", {"message": "未找到对应告警记录"})
        return
    socketio.emit("alert_notification_resent", {"ok": True, "entry": entry})


@socketio.on("export_config")
def on_export_config():
    filename = f"GoldMonitor-config-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    try:
        content = json.dumps(build_config_backup(), ensure_ascii=False, indent=2)
        saved_path = save_export_file(filename, content)
        emit("config_backup_ready", {
            "ok": True,
            "filename": filename,
            "content": content,
            "saved_path": saved_path,
        })
    except OSError:
        emit("config_backup_ready", {"ok": False, "message": "配置导出失败，请检查导出目录权限。"})


@socketio.on("import_config")
def on_import_config(data=None):
    try:
        payload = data.get("payload") if isinstance(data, dict) else data
        if isinstance(payload, str):
            payload = json.loads(payload)
        result = restore_config_backup(payload)
        emit("config_import_result", {**result, "message": "配置导入完成。"})
    except (ValueError, json.JSONDecodeError) as exc:
        emit("config_import_result", {"ok": False, "message": str(exc)})
    except OSError:
        emit("config_import_result", {"ok": False, "message": "配置导入失败，请检查配置目录权限。"})


@socketio.on("reset_settings")
def on_reset_settings():
    try:
        result = reset_to_default_settings()
        emit("settings_reset_result", {**result, "message": "已恢复默认设置。"})
    except OSError:
        emit("settings_reset_result", {"ok": False, "message": "恢复默认设置失败，请检查配置目录权限。"})


@socketio.on("get_diagnostics")
def on_get_diagnostics():
    filename = f"GoldMonitor-diagnostics-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    try:
        content = json.dumps(build_diagnostics_report(), ensure_ascii=False, indent=2)
        saved_path = save_export_file(filename, content)
        emit("diagnostics_ready", {
            "ok": True,
            "filename": filename,
            "content": content,
            "saved_path": saved_path,
        })
    except OSError:
        emit("diagnostics_ready", {"ok": False, "message": "诊断报告导出失败，请检查导出目录权限。"})


@socketio.on("open_exports_folder")
def on_open_exports_folder():
    try:
        open_exports_folder()
        emit("exports_folder_opened", {"ok": True, "message": f"已打开导出目录：{EXPORT_DIR}"})
    except Exception:
        emit("exports_folder_opened", {"ok": False, "message": f"无法自动打开导出目录：{EXPORT_DIR}"})


@socketio.on("test_alert")
def on_test_alert(data=None):
    alert_type = "warning"
    if isinstance(data, dict) and data.get("type") in {"warning", "critical", "volatility"}:
        alert_type = data.get("type")
    now_str = datetime.now().strftime("%H:%M:%S")
    entry = {
        "time": now_str,
        "type": alert_type,
        "mode": "rmb",
        "message": "这是一条手动测试提醒，用于验证弹窗、声音和邮件通知配置。",
        "force_notify": True,
    }
    emit_alert(entry, "金价监控测试提醒")
    emit("test_alert_result", {"ok": True, "message": "测试提醒已触发。"})


@socketio.on("check_update")
def on_check_update():
    try:
        emit("update_status", get_update_status())
    except ValueError as exc:
        emit("update_status", {
            "state": "error",
            "current_version": APP_VERSION,
            "message": str(exc),
        })
    except Exception:
        emit("update_status", {
            "state": "error",
            "current_version": APP_VERSION,
            "message": "检查更新失败，请确认网络连接后重试。",
        })


@socketio.on("install_update")
def on_install_update(data=None):
    try:
        status = get_update_status(expose_download=True)
        if status.get("state") != "available":
            emit("update_status", status)
            return
        update_info = {
            "version": status["latest_version"],
            "url": status["url"],
            "notes": status.get("notes", ""),
            "sha256": status["sha256"],
        }
        emit("update_status", {
            "state": "downloading",
            "current_version": APP_VERSION,
            "latest_version": update_info["version"],
            "message": "正在下载更新安装包...",
            "progress_percent": 0,
        })

        def emit_progress(received_bytes, total_bytes):
            percent = int(received_bytes / total_bytes * 100) if total_bytes else None
            socketio.emit("update_status", {
                "state": "downloading",
                "current_version": APP_VERSION,
                "latest_version": update_info["version"],
                "message": "正在下载更新安装包...",
                "downloaded_bytes": received_bytes,
                "total_bytes": total_bytes,
                "progress_percent": percent,
            }, room=request.sid)

        try:
            installer_path = download_update_installer(update_info, progress_callback=emit_progress)
        except TypeError:
            installer_path = download_update_installer(update_info)
        emit("update_status", {
            "state": "installing",
            "current_version": APP_VERSION,
            "latest_version": update_info["version"],
            "message": "安装包已下载，正在启动更新程序。",
            "progress_percent": 100,
        })
        launch_update_installer(installer_path)
        emit("update_status", {
            "state": "installer_opened",
            "current_version": APP_VERSION,
            "latest_version": update_info["version"],
            "message": "安装程序已打开，请按提示完成更新。安装过程中当前程序可能会被关闭。",
            "progress_percent": 100,
        })
    except ValueError as exc:
        emit("update_status", {
            "state": "error",
            "current_version": APP_VERSION,
            "message": str(exc),
        })
    except Exception:
        emit("update_status", {
            "state": "error",
            "current_version": APP_VERSION,
            "message": "更新失败，请稍后重试或手动下载安装包。",
        })


# ---------- 共享状态 (托盘与窗口通信) ----------
_window_instance = None
_tray_icon = None
_macos_status_item = None
_macos_status_delegate = None
_macos_status_menu = None
_macos_status_menu_items = {}
_window_hwnd = None
_last_desktop_title = APP_NAME
_desktop_runtime_active = False
_floating_hwnd = None
_floating_thread_started = False
_floating_window_ready = threading.Event()
_floating_lock = threading.RLock()
_floating_primary_text = "黄金 --"
_floating_secondary_text = "等待行情数据"
_floating_status_text = "等待更新"
_floating_trend_state = "neutral"
_floating_source_state = "waiting"
_floating_drag_state = None
_floating_positioned = False
_background_fetch_started = False
_news_fetch_started = False


def format_price_title(rmb=None, usd=None):
    if rmb is None and usd is None:
        with lock:
            rmb = price_rmb
            usd = price_usd
    return desktop_ui_core.format_price_title(APP_NAME, rmb=rmb, usd=usd)


def format_macos_status_title():
    settings = get_settings_snapshot()
    with lock:
        rmb = price_rmb
        usd = price_usd
    return desktop_ui_core.format_macos_status_title(settings, rmb, usd)


def _call_macos_main(callback):
    if sys.platform != "darwin":
        return
    try:
        from PyObjCTools import AppHelper
        AppHelper.callAfter(callback)
    except Exception:
        try:
            callback()
        except Exception:
            pass


def _refresh_macos_status_item():
    if sys.platform != "darwin" or not _macos_status_item:
        return

    def _apply():
        try:
            button = _macos_status_item.button()
            if button:
                button.setTitle_(format_macos_status_title())
                button.setToolTip_(format_price_title())
            toggle_item = _macos_status_menu_items.get("toggle_price")
            if toggle_item:
                enabled = get_settings_snapshot().get("floating_price_enabled", True)
                toggle_item.setTitle_("隐藏菜单栏金价" if enabled else "显示菜单栏金价")
        except Exception:
            pass

    _call_macos_main(_apply)


def create_macos_status_item():
    global _macos_status_item, _macos_status_delegate, _macos_status_menu, _macos_status_menu_items
    if sys.platform != "darwin" or _macos_status_item:
        return
    try:
        from Foundation import NSObject
        from AppKit import NSMenu, NSMenuItem, NSStatusBar, NSVariableStatusItemLength

        class MacOSStatusDelegate(NSObject):
            def showWindow_(self, sender):
                show_main_window()

            def refreshPrice_(self, sender):
                _refresh_price_from_tray_menu()

            def openRiskAnalysis_(self, sender):
                _open_risk_analysis_from_tray_menu()

            def toggleMenuBarPrice_(self, sender):
                _toggle_floating_price_from_tray_menu()

            def quitApp_(self, sender):
                exit_app()

        delegate = MacOSStatusDelegate.alloc().init()
        menu = NSMenu.alloc().init()

        def add_item(title, action):
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, "")
            item.setTarget_(delegate)
            menu.addItem_(item)
            return item

        add_item("显示窗口", "showWindow:")
        add_item("刷新行情", "refreshPrice:")
        add_item("风险分析", "openRiskAnalysis:")
        toggle_item = add_item("隐藏菜单栏金价", "toggleMenuBarPrice:")
        menu.addItem_(NSMenuItem.separatorItem())
        add_item("退出", "quitApp:")

        status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        status_item.setMenu_(menu)

        _macos_status_delegate = delegate
        _macos_status_menu = menu
        _macos_status_item = status_item
        _macos_status_menu_items = {"toggle_price": toggle_item}
        _refresh_macos_status_item()
    except Exception:
        logging.warning("macOS 菜单栏状态项启动失败", exc_info=True)


def update_desktop_price_title(title=None):
    global _last_desktop_title
    title = title or format_price_title()
    if title == _last_desktop_title:
        _refresh_macos_status_item()
        return
    _last_desktop_title = title
    window = _window_instance
    if window:
        try:
            window.set_title(title)
        except Exception:
            pass
    icon = _tray_icon
    if icon:
        try:
            icon.title = title
        except Exception:
            pass
    _refresh_macos_status_item()


def format_floating_price_text(rmb=None, usd=None, pct=None):
    settings = get_settings_snapshot()
    if rmb is None and usd is None:
        with lock:
            rmb = price_rmb
            usd = price_usd
            fetch_time = last_fetch_time
            source_name = gold_price_source or "行情源"
            gold_cached = bool(gold_price_cached)
            rate_cached = bool(usdcny_rate_cached)
            fetch_ok = bool(last_fetch_ok)
            fetch_error = last_fetch_error or gold_price_error or usdcny_rate_error
    else:
        fetch_time = last_fetch_time
        source_name = gold_price_source or "行情源"
        gold_cached = bool(gold_price_cached)
        rate_cached = bool(usdcny_rate_cached)
        fetch_ok = bool(last_fetch_ok)
        fetch_error = last_fetch_error or gold_price_error or usdcny_rate_error

    return desktop_ui_core.format_floating_price_text(
        settings,
        rmb=rmb,
        usd=usd,
        pct=pct,
        fetch_time=fetch_time,
        source_name=source_name,
        gold_cached=gold_cached,
        rate_cached=rate_cached,
        fetch_ok=fetch_ok,
        fetch_error=fetch_error,
    )


def _is_floating_price_available():
    return _desktop_runtime_active and os.name == "nt"


def _floating_window_metrics():
    return desktop_ui_core.floating_window_metrics(
        get_settings_snapshot(),
        default_preset=DEFAULT_SETTINGS["floating_price_preset"],
        presets=FLOATING_PRICE_PRESETS,
    )


def _floating_rect(rect_config, width, height):
    return desktop_ui_core.floating_rect(rect_config, width, height)


def _floating_window_size():
    return desktop_ui_core.floating_window_size(
        get_settings_snapshot(),
        default_preset=DEFAULT_SETTINGS["floating_price_preset"],
        presets=FLOATING_PRICE_PRESETS,
    )


def _floating_window_radius():
    return desktop_ui_core.floating_window_radius(
        get_settings_snapshot(),
        default_preset=DEFAULT_SETTINGS["floating_price_preset"],
        presets=FLOATING_PRICE_PRESETS,
    )


def _apply_floating_window_corner_preference(hwnd):
    if not hwnd or os.name != "nt":
        return
    try:
        import ctypes

        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWCP_ROUND_SMALL = 3
        value = ctypes.c_int(DWMWCP_ROUND_SMALL)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd),
            ctypes.c_uint(DWMWA_WINDOW_CORNER_PREFERENCE),
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
    except Exception:
        pass


def _get_work_area(user32):
    try:
        import ctypes
        from ctypes import wintypes

        rect = wintypes.RECT()
        SPI_GETWORKAREA = 0x0030
        if user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
            return rect.left, rect.top, rect.right, rect.bottom
    except Exception:
        pass
    return 0, 0, 1280, 720


def _clamp_floating_position(x, y, user32=None):
    try:
        import ctypes

        user32 = user32 or ctypes.windll.user32
        return desktop_ui_core.clamp_floating_position(x, y, _floating_window_size(), _get_work_area(user32))
    except Exception:
        return int(x), int(y)


def _default_floating_position(user32, width, height):
    return desktop_ui_core.default_floating_position(_get_work_area(user32), width, height)


def _snap_floating_position(x, y, user32=None):
    settings = get_settings_snapshot()
    if not settings.get("floating_price_snap_edge", True):
        return x, y
    try:
        import ctypes

        user32 = user32 or ctypes.windll.user32
        return desktop_ui_core.snap_floating_position(
            x,
            y,
            _floating_window_size(),
            _get_work_area(user32),
            enabled=True,
        )
    except Exception:
        pass
    return x, y


def _resolve_floating_position(user32, width, height):
    return desktop_ui_core.resolve_floating_position(
        get_settings_snapshot(),
        (width, height),
        _get_work_area(user32),
    )


def _save_floating_position(x, y):
    try:
        x, y = _clamp_floating_position(x, y)
        x, y = _snap_floating_position(x, y)
        snapshot = get_settings_snapshot()
        if (
            snapshot.get("floating_price_position_saved")
            and snapshot.get("floating_price_x") == x
            and snapshot.get("floating_price_y") == y
        ):
            return x, y
        snapshot["floating_price_position_saved"] = True
        snapshot["floating_price_x"] = x
        snapshot["floating_price_y"] = y
        save_settings(snapshot)
        socketio.emit("settings_updated", public_settings_snapshot())
        return x, y
    except Exception:
        logging.warning("桌面金价悬浮条位置保存失败", exc_info=True)
    return x, y


def _position_floating_window(hwnd, user32=None, x=None, y=None):
    global _floating_positioned
    if not hwnd:
        return
    try:
        import ctypes

        user32 = user32 or ctypes.windll.user32
        user32.SetWindowPos.restype = ctypes.c_bool
        user32.SetWindowPos.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        ]
        width, height = _floating_window_size()
        if x is None or y is None:
            x, y = _resolve_floating_position(user32, width, height)
        else:
            x, y = _clamp_floating_position(x, y, user32)
        SWP_NOACTIVATE = 0x0010
        SWP_NOOWNERZORDER = 0x0200
        HWND_TOPMOST = ctypes.c_void_p(-1 & ((1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1))
        ok = user32.SetWindowPos(
            hwnd,
            HWND_TOPMOST,
            int(x),
            int(y),
            int(width),
            int(height),
            SWP_NOACTIVATE | SWP_NOOWNERZORDER,
        )
        _floating_positioned = bool(ok)
        if not ok:
            raise OSError(ctypes.get_last_error(), "SetWindowPos failed")
    except Exception:
        logging.warning("桌面金价悬浮条定位失败", exc_info=True)


def _invalidate_floating_window():
    hwnd = _floating_hwnd
    if not hwnd or os.name != "nt":
        return
    try:
        import ctypes

        user32 = ctypes.windll.user32
        user32.InvalidateRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool]
        user32.InvalidateRect(hwnd, None, True)
    except Exception:
        pass


def _set_floating_window_visible(visible):
    global _floating_positioned
    hwnd = _floating_hwnd
    if not hwnd or os.name != "nt":
        return
    try:
        import ctypes

        user32 = ctypes.windll.user32
        user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
        SW_HIDE = 0
        SW_SHOWNOACTIVATE = 4
        if visible:
            if not _floating_positioned:
                _position_floating_window(hwnd, user32)
            _apply_floating_opacity(hwnd, user32)
            user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
            _invalidate_floating_window()
        else:
            user32.ShowWindow(hwnd, SW_HIDE)
    except Exception:
        pass


def _set_floating_price_enabled(enabled):
    try:
        snapshot = get_settings_snapshot()
        if snapshot.get("floating_price_enabled", True) == bool(enabled):
            _set_floating_window_visible(bool(enabled))
            return
        snapshot["floating_price_enabled"] = bool(enabled)
        save_settings(snapshot)
        apply_floating_price_settings(snapshot)
        socketio.emit("settings_updated", public_settings_snapshot(snapshot))
    except Exception:
        logging.warning("桌面金价悬浮条显示状态更新失败", exc_info=True)


def _apply_floating_opacity(hwnd=None, user32=None):
    hwnd = hwnd or _floating_hwnd
    if not hwnd or os.name != "nt":
        return
    try:
        import ctypes

        user32 = user32 or ctypes.windll.user32
        LWA_ALPHA = 0x00000002
        opacity = get_settings_snapshot().get("floating_price_opacity", 94)
        alpha = max(1, min(255, int(int(opacity) / 100 * 255)))
        user32.SetLayeredWindowAttributes(hwnd, 0, alpha, LWA_ALPHA)
    except Exception:
        pass


def _refresh_price_from_floating_menu():
    threading.Thread(target=fetch_price_once, daemon=True).start()


def _open_risk_analysis_from_floating_menu():
    show_main_window()
    socketio.emit("open_risk_analysis", {"run": True, "source": "floating_price"})


def _refresh_price_from_tray_menu():
    _refresh_price_from_floating_menu()


def _open_risk_analysis_from_tray_menu():
    show_main_window()
    socketio.emit("open_risk_analysis", {"run": True, "source": "tray"})


def _toggle_floating_price_from_tray_menu():
    settings = get_settings_snapshot()
    _set_floating_price_enabled(not bool(settings.get("floating_price_enabled", True)))


def _get_lparam_point(lparam):
    value = int(lparam)
    x = value & 0xFFFF
    y = (value >> 16) & 0xFFFF
    if x >= 0x8000:
        x -= 0x10000
    if y >= 0x8000:
        y -= 0x10000
    return x, y


def _floating_price_window_loop():
    global _floating_hwnd, _floating_drag_state
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        kernel32 = ctypes.windll.kernel32

        LRESULT = ctypes.c_ssize_t
        WNDPROC = ctypes.WINFUNCTYPE(
            LRESULT,
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        user32.DefWindowProcW.restype = LRESULT
        user32.DefWindowProcW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            wintypes.HMENU,
            wintypes.HINSTANCE,
            wintypes.LPVOID,
        ]
        user32.LoadCursorW.restype = wintypes.HANDLE
        user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        class WNDCLASSW(ctypes.Structure):
            _fields_ = [
                ("style", wintypes.UINT),
                ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HANDLE),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HANDLE),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        class PAINTSTRUCT(ctypes.Structure):
            _fields_ = [
                ("hdc", wintypes.HDC),
                ("fErase", wintypes.BOOL),
                ("rcPaint", wintypes.RECT),
                ("fRestore", wintypes.BOOL),
                ("fIncUpdate", wintypes.BOOL),
                ("rgbReserved", wintypes.BYTE * 32),
            ]

        user32.BeginPaint.restype = wintypes.HDC
        user32.BeginPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PAINTSTRUCT)]
        user32.EndPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PAINTSTRUCT)]
        user32.DrawTextW.argtypes = [
            wintypes.HDC,
            wintypes.LPCWSTR,
            ctypes.c_int,
            ctypes.POINTER(wintypes.RECT),
            wintypes.UINT,
        ]
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        user32.SetCapture.argtypes = [wintypes.HWND]
        user32.SetCapture.restype = wintypes.HWND
        user32.ReleaseCapture.argtypes = []
        user32.ReleaseCapture.restype = wintypes.BOOL
        user32.CreatePopupMenu.restype = wintypes.HMENU
        user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
        user32.TrackPopupMenu.restype = ctypes.c_int
        user32.TrackPopupMenu.argtypes = [
            wintypes.HMENU,
            wintypes.UINT,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            ctypes.c_void_p,
        ]
        user32.DestroyMenu.argtypes = [wintypes.HMENU]
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        gdi32.SetTextColor.argtypes = [wintypes.HDC, wintypes.COLORREF]
        gdi32.SetBkMode.argtypes = [wintypes.HDC, ctypes.c_int]
        gdi32.CreateSolidBrush.restype = wintypes.HANDLE
        gdi32.CreateSolidBrush.argtypes = [wintypes.COLORREF]
        gdi32.CreatePen.restype = wintypes.HANDLE
        gdi32.CreatePen.argtypes = [ctypes.c_int, ctypes.c_int, wintypes.COLORREF]
        gdi32.SelectObject.restype = wintypes.HANDLE
        gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
        gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
        gdi32.CreateFontW.restype = wintypes.HANDLE
        gdi32.CreateFontW.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPCWSTR,
        ]
        gdi32.RoundRect.argtypes = [
            wintypes.HDC,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]

        WM_PAINT = 0x000F
        WM_LBUTTONDOWN = 0x0201
        WM_LBUTTONUP = 0x0202
        WM_LBUTTONDBLCLK = 0x0203
        WM_MOUSEMOVE = 0x0200
        WM_RBUTTONUP = 0x0205
        WM_CONTEXTMENU = 0x007B
        WM_CAPTURECHANGED = 0x0215
        WM_DISPLAYCHANGE = 0x007E
        WM_DESTROY = 0x0002
        MF_STRING = 0x0000
        MF_SEPARATOR = 0x0800
        TPM_RIGHTBUTTON = 0x0002
        TPM_RETURNCMD = 0x0100
        FLOATING_MENU_OPEN = 1001
        FLOATING_MENU_HIDE = 1002
        FLOATING_MENU_REFRESH = 1003
        FLOATING_MENU_RISK = 1004
        MK_LBUTTON = 0x0001
        DT_SINGLELINE = 0x0020
        DT_VCENTER = 0x0004
        DT_END_ELLIPSIS = 0x8000
        TRANSPARENT = 1
        PS_SOLID = 0
        DEFAULT_CHARSET = 1
        OUT_DEFAULT_PRECIS = 0
        CLIP_DEFAULT_PRECIS = 0
        CLEARTYPE_QUALITY = 5
        DEFAULT_PITCH = 0
        FF_DONTCARE = 0
        CS_DBLCLKS = 0x0008

        def rgb(red, green, blue):
            return red | (green << 8) | (blue << 16)

        def draw_window(hwnd):
            width, height = _floating_window_size()
            metrics = _floating_window_metrics()
            radius = metrics["radius"]
            ps = PAINTSTRUCT()
            hdc = user32.BeginPaint(hwnd, ctypes.byref(ps))
            if not hdc:
                return
            try:
                bg = gdi32.CreateSolidBrush(rgb(21, 21, 38))
                border_pen = gdi32.CreatePen(PS_SOLID, 1, rgb(62, 58, 78))
                old_brush = gdi32.SelectObject(hdc, bg)
                old_pen = gdi32.SelectObject(hdc, border_pen)
                gdi32.RoundRect(hdc, 0, 0, width, height, radius, radius)
                gdi32.SelectObject(hdc, old_brush)
                gdi32.SelectObject(hdc, old_pen)
                gdi32.DeleteObject(bg)
                gdi32.DeleteObject(border_pen)

                with _floating_lock:
                    primary = _floating_primary_text
                    secondary = _floating_secondary_text
                    status = _floating_status_text
                    trend_state = _floating_trend_state
                    source_state = _floating_source_state

                gdi32.SetBkMode(hdc, TRANSPARENT)
                title_font = gdi32.CreateFontW(
                    metrics["title_font"], 0, 0, 0, 700, 0, 0, 0, DEFAULT_CHARSET,
                    OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY,
                    DEFAULT_PITCH | FF_DONTCARE, "Microsoft YaHei UI",
                )
                meta_font = gdi32.CreateFontW(
                    metrics["meta_font"], 0, 0, 0, 500, 0, 0, 0, DEFAULT_CHARSET,
                    OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY,
                    DEFAULT_PITCH | FF_DONTCARE, "Microsoft YaHei UI",
                )
                status_font = gdi32.CreateFontW(
                    metrics["status_font"], 0, 0, 0, 500, 0, 0, 0, DEFAULT_CHARSET,
                    OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY,
                    DEFAULT_PITCH | FF_DONTCARE, "Microsoft YaHei UI",
                )

                title_rect_values = _floating_rect(metrics["title_rect"], width, height)
                meta_rect_values = _floating_rect(metrics["meta_rect"], width, height)
                status_rect_values = _floating_rect(metrics.get("status_rect"), width, height)
                title_rect = wintypes.RECT(*title_rect_values)
                meta_rect = wintypes.RECT(*meta_rect_values)
                status_rect = wintypes.RECT(*status_rect_values) if status_rect_values else None
                trend_color = rgb(232, 184, 48)
                if trend_state == "up":
                    trend_color = rgb(224, 85, 106)
                elif trend_state == "down":
                    trend_color = rgb(76, 175, 132)
                status_color = rgb(160, 158, 174)
                if source_state == "live":
                    status_color = rgb(130, 204, 166)
                elif source_state == "cached":
                    status_color = rgb(232, 184, 48)
                elif source_state == "error":
                    status_color = rgb(224, 85, 106)

                old_font = gdi32.SelectObject(hdc, title_font)
                gdi32.SetTextColor(hdc, trend_color)
                user32.DrawTextW(
                    hdc,
                    primary,
                    -1,
                    ctypes.byref(title_rect),
                    DT_SINGLELINE | DT_VCENTER | DT_END_ELLIPSIS,
                )
                gdi32.SelectObject(hdc, meta_font)
                gdi32.SetTextColor(hdc, rgb(205, 202, 214))
                user32.DrawTextW(
                    hdc,
                    secondary,
                    -1,
                    ctypes.byref(meta_rect),
                    DT_SINGLELINE | DT_VCENTER | DT_END_ELLIPSIS,
                )
                if status_rect is not None:
                    gdi32.SelectObject(hdc, status_font)
                    gdi32.SetTextColor(hdc, status_color)
                    user32.DrawTextW(
                        hdc,
                        status,
                        -1,
                        ctypes.byref(status_rect),
                        DT_SINGLELINE | DT_VCENTER | DT_END_ELLIPSIS,
                    )
                gdi32.SelectObject(hdc, old_font)
                gdi32.DeleteObject(title_font)
                gdi32.DeleteObject(meta_font)
                gdi32.DeleteObject(status_font)
            finally:
                user32.EndPaint(hwnd, ctypes.byref(ps))

        def show_floating_context_menu(hwnd):
            point = wintypes.POINT()
            if not user32.GetCursorPos(ctypes.byref(point)):
                return
            menu = user32.CreatePopupMenu()
            if not menu:
                return
            try:
                user32.AppendMenuW(menu, MF_STRING, FLOATING_MENU_OPEN, "打开主界面")
                user32.AppendMenuW(menu, MF_STRING, FLOATING_MENU_RISK, "风险分析")
                user32.AppendMenuW(menu, MF_STRING, FLOATING_MENU_REFRESH, "刷新行情")
                user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
                user32.AppendMenuW(menu, MF_STRING, FLOATING_MENU_HIDE, "隐藏悬浮条")
                user32.SetForegroundWindow(hwnd)
                command = user32.TrackPopupMenu(
                    menu,
                    TPM_RIGHTBUTTON | TPM_RETURNCMD,
                    point.x,
                    point.y,
                    0,
                    hwnd,
                    None,
                )
            finally:
                user32.DestroyMenu(menu)
            if command == FLOATING_MENU_OPEN:
                show_main_window()
            elif command == FLOATING_MENU_HIDE:
                _set_floating_price_enabled(False)
            elif command == FLOATING_MENU_REFRESH:
                _refresh_price_from_floating_menu()
            elif command == FLOATING_MENU_RISK:
                _open_risk_analysis_from_floating_menu()

        @WNDPROC
        def wnd_proc(hwnd, msg, wparam, lparam):
            global _floating_drag_state
            if msg == WM_PAINT:
                draw_window(hwnd)
                return 0
            if msg == WM_LBUTTONDOWN:
                try:
                    point_x, point_y = _get_lparam_point(lparam)
                    rect = wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    _floating_drag_state = {
                        "offset_x": point_x,
                        "offset_y": point_y,
                        "start_x": rect.left,
                        "start_y": rect.top,
                        "moved": False,
                    }
                    user32.SetCapture(hwnd)
                except Exception:
                    _floating_drag_state = None
                return 0
            if msg == WM_MOUSEMOVE and _floating_drag_state and (int(wparam) & MK_LBUTTON):
                try:
                    cursor = wintypes.POINT()
                    if user32.GetCursorPos(ctypes.byref(cursor)):
                        new_x = cursor.x - _floating_drag_state["offset_x"]
                        new_y = cursor.y - _floating_drag_state["offset_y"]
                        x, y = _clamp_floating_position(new_x, new_y, user32)
                        if (
                            abs(x - _floating_drag_state["start_x"]) > 3
                            or abs(y - _floating_drag_state["start_y"]) > 3
                        ):
                            _floating_drag_state["moved"] = True
                        _position_floating_window(hwnd, user32, x, y)
                except Exception:
                    pass
                return 0
            if msg == WM_LBUTTONUP:
                try:
                    user32.ReleaseCapture()
                except Exception:
                    pass
                drag_state = _floating_drag_state
                _floating_drag_state = None
                if drag_state and drag_state.get("moved"):
                    try:
                        rect = wintypes.RECT()
                        if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                            saved_x, saved_y = _save_floating_position(rect.left, rect.top)
                            _position_floating_window(hwnd, user32, saved_x, saved_y)
                    except Exception:
                        pass
                return 0
            if msg == WM_LBUTTONDBLCLK:
                _floating_drag_state = None
                try:
                    user32.ReleaseCapture()
                except Exception:
                    pass
                show_main_window()
                return 0
            if msg in (WM_RBUTTONUP, WM_CONTEXTMENU):
                show_floating_context_menu(hwnd)
                return 0
            if msg == WM_CAPTURECHANGED:
                _floating_drag_state = None
                return 0
            if msg == WM_DISPLAYCHANGE:
                _position_floating_window(hwnd, user32)
                return 0
            if msg == WM_DESTROY:
                return 0
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        hinstance = kernel32.GetModuleHandleW(None)
        class_name = "GoldMonitorFloatingPriceWindow"
        wc = WNDCLASSW()
        wc.style = CS_DBLCLKS
        wc.lpfnWndProc = wnd_proc
        wc.hInstance = hinstance
        wc.hCursor = user32.LoadCursorW(None, ctypes.c_void_p(32649))
        wc.lpszClassName = class_name
        user32.RegisterClassW(ctypes.byref(wc))

        width, height = _floating_window_size()
        x, y = _resolve_floating_position(user32, width, height)
        WS_EX_TOPMOST = 0x00000008
        WS_EX_TOOLWINDOW = 0x00000080
        WS_EX_LAYERED = 0x00080000
        WS_EX_NOACTIVATE = 0x08000000
        WS_POPUP = 0x80000000
        LWA_ALPHA = 0x00000002

        hwnd = user32.CreateWindowExW(
            WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_LAYERED | WS_EX_NOACTIVATE,
            class_name,
            "金价悬浮条",
            WS_POPUP,
            int(x),
            int(y),
            int(width),
            int(height),
            None,
            None,
            hinstance,
            None,
        )
        if not hwnd:
            return

        _floating_hwnd = hwnd
        _apply_floating_window_corner_preference(hwnd)
        _apply_floating_opacity(hwnd, user32)
        if get_settings_snapshot().get("floating_price_enabled", True):
            _set_floating_window_visible(True)
        _floating_window_ready.set()

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
    except Exception:
        logging.warning("桌面金价悬浮条启动失败", exc_info=True)
        _floating_window_ready.set()


def start_floating_price_window():
    global _floating_thread_started
    if not _is_floating_price_available():
        return
    with _floating_lock:
        if _floating_thread_started:
            return
        _floating_thread_started = True
        threading.Thread(target=_floating_price_window_loop, daemon=True).start()


def apply_floating_price_settings(settings=None):
    if sys.platform == "darwin":
        _refresh_macos_status_item()
        return
    if not _is_floating_price_available():
        return
    settings = settings or get_settings_snapshot()
    enabled = bool(settings.get("floating_price_enabled", True))
    if enabled:
        start_floating_price_window()
        if _floating_hwnd:
            _position_floating_window(_floating_hwnd)
            _apply_floating_opacity(_floating_hwnd)
            _invalidate_floating_window()
        _set_floating_window_visible(True)
    else:
        _set_floating_window_visible(False)


def update_floating_price(rmb=None, usd=None, pct=None):
    global _floating_primary_text, _floating_secondary_text, _floating_status_text
    global _floating_trend_state, _floating_source_state
    primary, secondary, status, trend_state, source_state = format_floating_price_text(rmb, usd, pct)
    with _floating_lock:
        _floating_primary_text = primary
        _floating_secondary_text = secondary
        _floating_status_text = status
        _floating_trend_state = trend_state
        _floating_source_state = source_state

    if not _is_floating_price_available():
        return

    settings = get_settings_snapshot()
    if settings.get("floating_price_enabled", True):
        start_floating_price_window()
        if not _floating_hwnd:
            _floating_window_ready.wait(0.5)
        _set_floating_window_visible(True)
        _invalidate_floating_window()
    else:
        _set_floating_window_visible(False)


def _find_main_window_hwnd():
    if os.name != "nt":
        return None
    try:
        import ctypes
        for title in (_last_desktop_title, APP_NAME):
            hwnd = ctypes.windll.user32.FindWindowW(None, title)
            if hwnd:
                return hwnd
        return None
    except Exception:
        return None


def hide_main_window():
    global _window_hwnd
    window = _window_instance
    if window:
        try:
            window.hide()
        except Exception:
            pass

    if os.name == "nt":
        try:
            import ctypes
            SW_HIDE = 0
            hwnd = _window_hwnd or _find_main_window_hwnd()
            if hwnd:
                _window_hwnd = hwnd
                ctypes.windll.user32.ShowWindow(hwnd, SW_HIDE)
        except Exception:
            pass


def show_main_window():
    global _window_hwnd
    window = _window_instance
    if window:
        try:
            window.show()
            window.restore()
        except Exception:
            pass

    if os.name == "nt":
        try:
            import ctypes
            SW_RESTORE = 9
            hwnd = _window_hwnd or _find_main_window_hwnd()
            if hwnd:
                _window_hwnd = hwnd
                ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception:
            pass


def exit_app():
    icon = _tray_icon
    if icon:
        try:
            icon.stop()
        except Exception:
            pass
    os._exit(0)


def start_background_fetching():
    global _background_fetch_started
    if _background_fetch_started:
        return
    _background_fetch_started = True
    threading.Thread(target=background_loop, daemon=True).start()


def start_news_fetching():
    global _news_fetch_started
    if _news_fetch_started:
        return
    _news_fetch_started = True
    threading.Thread(target=news_loop, daemon=True).start()


def wait_for_server_ready(timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.1)
            if probe.connect_ex((DEFAULT_HOST, server_port)) == 0:
                return True
        time.sleep(0.05)
    return False


# ---------- 系统托盘 ----------
def create_tray_icon():
    global _window_instance, _tray_icon
    try:
        from PIL import Image
        import pystray

        icon_path = os.path.join(_basedir, "static", "icon-64.png")
        if os.path.exists(icon_path):
            icon_img = Image.open(icon_path)
        else:
            from PIL import ImageDraw
            icon_img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            ImageDraw.Draw(icon_img).ellipse([4, 4, 60, 60], fill="#e8b830")

        def on_show(icon, item):
            show_main_window()

        def on_refresh(icon, item):
            _refresh_price_from_tray_menu()

        def on_risk_analysis(icon, item):
            _open_risk_analysis_from_tray_menu()

        def on_toggle_floating(icon, item):
            _toggle_floating_price_from_tray_menu()

        def on_quit(icon, item):
            exit_app()

        menu = (
            pystray.MenuItem("显示窗口", on_show, default=True),
            pystray.MenuItem("刷新行情", on_refresh),
            pystray.MenuItem("风险分析", on_risk_analysis),
            pystray.MenuItem("切换悬浮条", on_toggle_floating),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", on_quit),
        )

        icon = pystray.Icon("gold_monitor", icon_img, "金价监控", menu)
        _tray_icon = icon

        def update_tooltip():
            while True:
                try:
                    icon.title = format_price_title()
                except Exception:
                    pass
                time.sleep(5)

        threading.Thread(target=update_tooltip, daemon=True).start()
        icon.run()
    except Exception:
        pass


def ask_close_choice():
    snapshot = get_settings_snapshot()
    decision = platform_core.close_behavior_decision(snapshot, _runtime_platform())
    if decision != "ask":
        return decision

    try:
        import ctypes
        from ctypes import wintypes

        class TASKDIALOG_BUTTON(ctypes.Structure):
            _fields_ = [
                ("nButtonID", ctypes.c_int),
                ("pszButtonText", wintypes.LPCWSTR),
            ]

        class TASKDIALOGCONFIG(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.UINT),
                ("hwndParent", wintypes.HWND),
                ("hInstance", wintypes.HINSTANCE),
                ("dwFlags", wintypes.DWORD),
                ("dwCommonButtons", wintypes.DWORD),
                ("pszWindowTitle", wintypes.LPCWSTR),
                ("hMainIcon", wintypes.HANDLE),
                ("pszMainInstruction", wintypes.LPCWSTR),
                ("pszContent", wintypes.LPCWSTR),
                ("cButtons", wintypes.UINT),
                ("pButtons", ctypes.POINTER(TASKDIALOG_BUTTON)),
                ("nDefaultButton", ctypes.c_int),
                ("cRadioButtons", wintypes.UINT),
                ("pRadioButtons", ctypes.c_void_p),
                ("nDefaultRadioButton", ctypes.c_int),
                ("pszVerificationText", wintypes.LPCWSTR),
                ("pszExpandedInformation", wintypes.LPCWSTR),
                ("pszExpandedControlText", wintypes.LPCWSTR),
                ("pszCollapsedControlText", wintypes.LPCWSTR),
                ("hFooterIcon", wintypes.HANDLE),
                ("pszFooter", wintypes.LPCWSTR),
                ("pfCallback", ctypes.c_void_p),
                ("lpCallbackData", ctypes.c_void_p),
                ("cxWidth", wintypes.UINT),
            ]

        TDF_ALLOW_DIALOG_CANCELLATION = 0x0008
        TDF_SIZE_TO_CONTENT = 0x01000000
        ID_MINIMIZE = 1001
        ID_EXIT = 1002
        ID_CANCEL = 1003
        buttons = (TASKDIALOG_BUTTON * 3)(
            TASKDIALOG_BUTTON(ID_MINIMIZE, "最小化到托盘"),
            TASKDIALOG_BUTTON(ID_EXIT, "退出程序"),
            TASKDIALOG_BUTTON(ID_CANCEL, "取消"),
        )
        selected = ctypes.c_int(ID_CANCEL)
        selected_radio = ctypes.c_int(0)
        verification_checked = wintypes.BOOL(False)

        config = TASKDIALOGCONFIG()
        config.cbSize = ctypes.sizeof(TASKDIALOGCONFIG)
        config.dwFlags = TDF_ALLOW_DIALOG_CANCELLATION | TDF_SIZE_TO_CONTENT
        config.pszWindowTitle = "关闭金价监控"
        config.pszMainInstruction = "是否最小化到桌面右下角托盘并继续监控？"
        config.pszContent = "最小化后程序会继续监控金价；也可以选择直接退出程序。"
        config.cButtons = len(buttons)
        config.pButtons = buttons
        config.nDefaultButton = ID_MINIMIZE
        config.pszVerificationText = "不再提示，记住本次选择"
        ctypes.windll.comctl32.TaskDialogIndirect(
            ctypes.byref(config),
            ctypes.byref(selected),
            ctypes.byref(selected_radio),
            ctypes.byref(verification_checked),
        )

        if selected.value == ID_MINIMIZE:
            choice = "minimize_to_tray"
        elif selected.value == ID_EXIT:
            choice = "exit"
        else:
            choice = "cancel"

        if choice in ("minimize_to_tray", "exit") and verification_checked.value:
            snapshot["close_behavior"] = choice
            snapshot["close_remembered"] = True
            save_settings(snapshot)
            socketio.emit("settings_updated", public_settings_snapshot())
        return choice
    except Exception:
        return "minimize_to_tray"


# ---------- 桌面原生窗口 ----------
def start_desktop_window(start_hidden=False):
    """使用 pywebview 创建原生桌面窗口"""
    global _window_instance, _window_hwnd
    try:
        import webview
        if sys.platform == "darwin":
            create_macos_status_item()

        def on_shown():
            global _window_hwnd
            if os.name != "nt":
                return
            # 窗口显示后: 最大化 + 设置金块图标
            try:
                import ctypes
                user32 = ctypes.windll.user32
                hwnd = user32.FindWindowW(None, APP_NAME)
                if hwnd:
                    _window_hwnd = hwnd
                    # 设置图标
                    icon_path = os.path.join(_basedir, "static", "icon.ico")
                    if os.path.exists(icon_path):
                        hicon = user32.LoadImageW(None, icon_path, 1, 64, 64, 0x10)
                        if hicon:
                            user32.SendMessageW(hwnd, 0x0080, 0, hicon)
                            user32.SendMessageW(hwnd, 0x0080, 1, hicon)
                    if start_hidden and _window_instance:
                        hide_main_window()
                    else:
                        # 最大化窗口 (SW_MAXIMIZE=3)
                        user32.ShowWindow(hwnd, 3)
            except Exception:
                pass

        def on_closing():
            if sys.platform == "darwin":
                snapshot = get_settings_snapshot()
                decision = platform_core.close_behavior_decision(snapshot, "macos")
                if decision == "exit":
                    exit_app()
                    return False

                if decision == "minimize_to_tray":
                    hide_main_window()
                    return False

                socketio.emit("show_close_dialog", {
                    "close_behavior": snapshot.get("close_behavior", "ask"),
                    "close_remembered": bool(snapshot.get("close_remembered")),
                })
                return False

            if os.name != "nt":
                exit_app()
                return False

            snapshot = get_settings_snapshot()
            decision = platform_core.close_behavior_decision(snapshot, "windows")
            if decision == "exit":
                exit_app()
                return False

            if decision == "minimize_to_tray":
                hide_main_window()
                return False

            socketio.emit("show_close_dialog", {
                "close_behavior": snapshot.get("close_behavior", "ask"),
                "close_remembered": bool(snapshot.get("close_remembered")),
            })
            return False

        _window_instance = webview.create_window(
            title=APP_NAME,
            url=f"http://{DEFAULT_HOST}:{server_port}",
            width=1200,
            height=780,
            min_size=(860, 500),
            hidden=start_hidden,
            resizable=True,
            easy_drag=False,
            on_top=False,
            maximized=not start_hidden,  # 启动即最大化
        )

        _window_instance.events.shown += on_shown
        _window_instance.events.closing += on_closing

        if os.name == "nt":
            webview.start(gui="edgechromium")
        else:
            webview.start()

    except Exception:
        pass


# ---------- 启动 ----------
if __name__ == "__main__":
    macos_packaged_app = sys.platform == "darwin" and getattr(sys, "frozen", False)
    desktop_mode = (
        "--desktop" in sys.argv
        or (os.name == "nt" and "--web" not in sys.argv)
        or (macos_packaged_app and "--web" not in sys.argv)
    )
    startup_mode = "--startup" in sys.argv
    server_port = find_available_port(DEFAULT_PORT)
    _desktop_runtime_active = desktop_mode

    if os.name == "nt":
        tray_thread = threading.Thread(target=create_tray_icon, daemon=True)
        tray_thread.start()

    if desktop_mode:
        # 桌面模式：在后台线程启动 Flask，前台显示原生窗口
        print("金价监控 - 桌面模式")
        flask_thread = threading.Thread(
            target=lambda: socketio.run(app, debug=False, host=DEFAULT_HOST, port=server_port,
                                        allow_unsafe_werkzeug=True),
            daemon=True,
        )
        flask_thread.start()
        wait_for_server_ready()
        update_floating_price()
        start_background_fetching()
        start_news_fetching()
        start_hidden = (os.name == "nt" or sys.platform == "darwin") and startup_mode and get_settings_snapshot().get("startup_to_tray", True)
        start_desktop_window(start_hidden=start_hidden)
    else:
        # Web 模式 (--web): Flask 主线程 + 浏览器
        start_background_fetching()
        start_news_fetching()
        web_url = f"http://{DEFAULT_HOST}:{server_port}"
        print(f"金价监控服务已启动 -> {web_url}")
        try:
            import webbrowser
            webbrowser.open(web_url)
        except Exception:
            pass
        socketio.run(app, debug=False, host=DEFAULT_HOST, port=server_port,
                     allow_unsafe_werkzeug=True)
