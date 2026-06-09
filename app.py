import csv
import hashlib
import io
import json
import logging
import math
import os
import sqlite3
import smtplib
import subprocess
import socket
import sys
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.utils import formatdate, parsedate_to_datetime
from urllib.parse import urljoin, urlparse
import secrets

import requests
from flask import Flask, jsonify, render_template, request, send_from_directory
from flask_socketio import SocketIO, emit

# PyInstaller 打包后路径适配
if getattr(sys, "frozen", False):
    _basedir = sys._MEIPASS
else:
    _basedir = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, template_folder=os.path.join(_basedir, "templates"))
socketio = SocketIO(app, async_mode="threading")

# ---------- 常量 ----------
APP_VERSION = "1.3.2"
APP_USER_MODEL_ID = "GoldMonitor.App"
DEFAULT_UPDATE_MANIFEST_URL = "https://github.com/JunCxio/GoldMonitor/releases/latest/download/version.json"
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


def _default_appdata_root():
    configured = os.environ.get("APPDATA")
    if configured:
        return configured
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    return os.path.expanduser("~")


APPDATA_DIR = os.path.join(_default_appdata_root(), "GoldMonitor")
SETTINGS_PATH = os.path.join(APPDATA_DIR, "settings.json")
THRESHOLDS_PATH = os.path.join(APPDATA_DIR, "thresholds.json")
MARKET_CACHE_PATH = os.path.join(APPDATA_DIR, "market_cache.json")
UPDATE_DIR = os.path.join(APPDATA_DIR, "updates")
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
NEWS_KEYWORDS = (
    "gold", "xau", "xauusd", "bullion", "precious metal", "fed", "fomc",
    "interest rate", "inflation", "cpi", "jobs", "nonfarm", "payroll",
    "dollar", "yield", "central bank", "黄金", "金价", "通胀", "美元",
)
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
    "update_manifest_url": DEFAULT_UPDATE_MANIFEST_URL,
    "update_auto_check_interval_hours": 6,
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
VALID_SMTP_ENCRYPTIONS = {"ssl", "tls"}
VALID_CLOSE_BEHAVIORS = {"ask", "minimize_to_tray", "exit"}
VALID_RISK_ASSISTANT_PROVIDERS = {"deepseek", "openai_compatible"}
VALID_RISK_ASSISTANT_DEPTHS = {"quick", "standard", "deep"}
VALID_FLOATING_DISPLAY_MODES = {"rmb_usd", "rmb_only", "usd_only"}
VALID_FLOATING_PRESETS = {"minimal", "compact", "standard"}
FLOATING_PRICE_PRESETS = {
    "minimal": {
        "size": (178, 40),
        "radius": 10,
        "title_font": -13,
        "meta_font": -9,
        "status_font": -8,
        "title_rect": (8, 2, -8, 20),
        "meta_rect": (8, 19, -8, -2),
        "status_rect": None,
    },
    "compact": {
        "size": (220, 52),
        "radius": 14,
        "title_font": -15,
        "meta_font": -10,
        "status_font": -9,
        "title_rect": (10, 3, -9, 21),
        "meta_rect": (10, 21, -9, 36),
        "status_rect": (10, 36, -9, -3),
    },
    "standard": {
        "size": (292, 78),
        "radius": 18,
        "title_font": -17,
        "meta_font": -12,
        "status_font": -11,
        "title_rect": (14, 7, -14, 30),
        "meta_rect": (14, 31, -14, 52),
        "status_rect": (14, 54, -14, -6),
    },
}
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


# ---------- 设置与系统集成 ----------
def _current_executable():
    if getattr(sys, "frozen", False):
        return sys.executable
    return os.path.abspath(sys.argv[0])


def _normalize_settings(raw):
    data = dict(DEFAULT_SETTINGS)
    if isinstance(raw, dict):
        data.update(raw)

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
    if data.get("floating_price_display_mode") not in VALID_FLOATING_DISPLAY_MODES:
        data["floating_price_display_mode"] = "rmb_usd"
    if data.get("floating_price_preset") not in VALID_FLOATING_PRESETS:
        data["floating_price_preset"] = DEFAULT_SETTINGS["floating_price_preset"]
    data["floating_price_snap_edge"] = bool(data.get("floating_price_snap_edge", True))
    data["close_remembered"] = bool(data.get("close_remembered"))
    data["alert_sound_enabled"] = bool(data.get("alert_sound_enabled"))
    data["alert_dialog_enabled"] = bool(data.get("alert_dialog_enabled"))
    data["update_manifest_url"] = str(data.get("update_manifest_url") or DEFAULT_UPDATE_MANIFEST_URL).strip()
    data["update_auto_check_interval_hours"] = bounded_int(data.get("update_auto_check_interval_hours", 6), 6, 1, 168)
    if data.get("close_behavior") not in VALID_CLOSE_BEHAVIORS:
        data["close_behavior"] = DEFAULT_SETTINGS["close_behavior"]
        data["close_remembered"] = False
    # 邮件通知
    data["smtp_server"] = str(data.get("smtp_server") or "").strip()
    data["smtp_port"] = str(data.get("smtp_port") or "465").strip()
    if data.get("smtp_encryption") not in VALID_SMTP_ENCRYPTIONS:
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
    data["email_subject_template"] = str(data.get("email_subject_template") or DEFAULT_EMAIL_SUBJECT_TEMPLATE)
    data["email_body_template"] = str(data.get("email_body_template") or DEFAULT_EMAIL_BODY_TEMPLATE)
    # 风险分析助手
    data["risk_assistant_enabled"] = bool(data.get("risk_assistant_enabled", True))
    if data.get("risk_assistant_provider") not in VALID_RISK_ASSISTANT_PROVIDERS:
        data["risk_assistant_provider"] = "deepseek"
    if data.get("risk_assistant_depth") not in VALID_RISK_ASSISTANT_DEPTHS:
        data["risk_assistant_depth"] = "standard"
    data["deepseek_base_url"] = str(data.get("deepseek_base_url") or DEFAULT_SETTINGS["deepseek_base_url"]).strip().rstrip("/")
    if not data["deepseek_base_url"]:
        data["deepseek_base_url"] = DEFAULT_SETTINGS["deepseek_base_url"]
    data["deepseek_model"] = str(data.get("deepseek_model") or DEFAULT_SETTINGS["deepseek_model"]).strip()
    data["deepseek_api_key"] = str(data.get("deepseek_api_key") or "").strip()
    data["openai_compatible_base_url"] = str(data.get("openai_compatible_base_url") or "").strip().rstrip("/")
    data["openai_compatible_model"] = str(data.get("openai_compatible_model") or "").strip()
    data["openai_compatible_api_key"] = str(data.get("openai_compatible_api_key") or "").strip()
    try:
        max_tokens = int(float(data.get("risk_assistant_max_tokens", RISK_ASSISTANT_MAX_TOKENS)))
    except (TypeError, ValueError):
        max_tokens = RISK_ASSISTANT_MAX_TOKENS
    data["risk_assistant_max_tokens"] = max(300, min(4000, max_tokens))
    try:
        cooldown = int(float(data.get("risk_assistant_cooldown_seconds", 15)))
    except (TypeError, ValueError):
        cooldown = 15
    data["risk_assistant_cooldown_seconds"] = max(0, min(300, cooldown))
    try:
        cache_minutes = int(float(data.get("risk_assistant_cache_minutes", 10)))
    except (TypeError, ValueError):
        cache_minutes = 10
    data["risk_assistant_cache_minutes"] = max(0, min(60, cache_minutes))
    return data


def load_settings():
    global last_settings_error
    os.makedirs(APPDATA_DIR, exist_ok=True)
    loaded = {}
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            last_settings_error = str(exc)
            loaded = {}

    data = _normalize_settings(loaded)
    try:
        save_settings(data)
    except OSError as exc:
        last_settings_error = str(exc)
    return data


def save_settings(data=None):
    global app_settings, last_settings_error
    with settings_lock:
        if data is None:
            data = app_settings
        normalized = _normalize_settings(data)
        os.makedirs(APPDATA_DIR, exist_ok=True)
        tmp_path = SETTINGS_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(normalized, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, SETTINGS_PATH)
        app_settings = normalized
        last_settings_error = None
        return dict(app_settings)


def get_settings_snapshot():
    with settings_lock:
        return dict(app_settings)


def mask_secret(value):
    value = str(value or "")
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * 8}{value[-4:]}"


def public_settings_snapshot(settings=None):
    snapshot = dict(settings or get_settings_snapshot())
    api_key = snapshot.pop("deepseek_api_key", "")
    snapshot["deepseek_api_key_configured"] = bool(api_key)
    snapshot["deepseek_api_key_masked"] = mask_secret(api_key)
    compatible_key = snapshot.pop("openai_compatible_api_key", "")
    snapshot["openai_compatible_api_key_configured"] = bool(compatible_key)
    snapshot["openai_compatible_api_key_masked"] = mask_secret(compatible_key)
    return snapshot


def diagnostic_settings_snapshot(settings=None):
    snapshot = public_settings_snapshot(settings)
    smtp_password = snapshot.pop("smtp_password", "")
    snapshot["smtp_password_configured"] = bool(smtp_password)
    snapshot["smtp_password_masked"] = mask_secret(smtp_password)
    return snapshot


def _normalize_volatility_config(raw):
    data = {"percent": None, "minutes": 10, "enabled": False}
    if isinstance(raw, dict):
        try:
            percent = float(raw["percent"]) if raw.get("percent") not in (None, "") else None
            data["percent"] = percent if percent is not None and math.isfinite(percent) and percent > 0 else None
        except (TypeError, ValueError):
            data["percent"] = None
        try:
            data["minutes"] = max(1, int(raw.get("minutes", 10)))
        except (TypeError, ValueError):
            data["minutes"] = 10
        data["enabled"] = bool(raw.get("enabled")) and data["percent"] is not None
    return data


def _normalize_thresholds(raw):
    data = dict(thresholds)
    if isinstance(raw, dict):
        for key in data:
            value = raw.get(key)
            if value in (None, ""):
                data[key] = None
                continue
            try:
                data[key] = float(value)
            except (TypeError, ValueError):
                data[key] = None
        data["volatility_config"] = _normalize_volatility_config(raw.get("volatility_config", volatility_config))
    else:
        data["volatility_config"] = _normalize_volatility_config(volatility_config)
    return data


def load_thresholds():
    if not os.path.exists(THRESHOLDS_PATH):
        return _normalize_thresholds({})
    try:
        with open(THRESHOLDS_PATH, "r", encoding="utf-8") as f:
            return _normalize_thresholds(json.load(f))
    except (OSError, json.JSONDecodeError):
        return _normalize_thresholds({})


def save_thresholds(data=None):
    if data is None:
        data = thresholds
    normalized = _normalize_thresholds(data)
    os.makedirs(APPDATA_DIR, exist_ok=True)
    tmp_path = THRESHOLDS_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, THRESHOLDS_PATH)
    return normalized


def _startup_command():
    exe = _current_executable()
    return f'"{exe}" --startup'


def set_startup_enabled(enabled):
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
    def parts(value):
        normalized = []
        for part in str(value or "0").split("."):
            digits = "".join(ch for ch in part if ch.isdigit())
            normalized.append(int(digits or 0))
        return normalized

    left_parts = parts(left)
    right_parts = parts(right)
    max_len = max(len(left_parts), len(right_parts))
    left_parts.extend([0] * (max_len - len(left_parts)))
    right_parts.extend([0] * (max_len - len(right_parts)))
    if left_parts > right_parts:
        return 1
    if left_parts < right_parts:
        return -1
    return 0


def _require_https_url(value, label):
    parsed = urlparse(str(value or "").strip())
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"{label}必须使用 HTTPS 地址")


def _platform_update_key():
    if sys.platform == "darwin":
        return "macos"
    if os.name == "nt":
        return "windows"
    return ""


def normalize_update_manifest(raw, base_url=None):
    if not isinstance(raw, dict):
        raise ValueError("更新清单格式无效")

    version = str(raw.get("version") or "").strip()
    notes = str(raw.get("notes") or "").strip()
    download_url = str(raw.get("url") or raw.get("download_url") or "").strip()
    sha256 = str(raw.get("sha256") or "").strip().lower()
    downloads = raw.get("downloads")
    platform_key = _platform_update_key()

    if isinstance(downloads, dict) and platform_key:
        platform_payload = downloads.get(platform_key)
        if platform_payload is None and platform_key != "windows":
            raise ValueError("当前平台暂无可用更新包")
        if isinstance(platform_payload, dict):
            download_url = str(platform_payload.get("url") or platform_payload.get("download_url") or "").strip()
            sha256 = str(platform_payload.get("sha256") or "").strip().lower()

    if base_url and download_url:
        download_url = urljoin(base_url, download_url)

    if not version:
        raise ValueError("更新清单缺少版本号")
    if not download_url:
        raise ValueError("更新清单缺少安装包地址")
    _require_https_url(download_url, "更新安装包")
    if not sha256:
        raise ValueError("更新清单缺少安装包 sha256")
    if sha256 and (len(sha256) != 64 or any(ch not in "0123456789abcdef" for ch in sha256)):
        raise ValueError("更新清单 sha256 格式无效")

    return {
        "version": version,
        "url": download_url,
        "notes": notes,
        "sha256": sha256,
    }


def fetch_update_manifest(manifest_url):
    manifest_url = str(manifest_url or "").strip()
    if not manifest_url:
        raise ValueError("未配置更新源")
    _require_https_url(manifest_url, "更新源")
    response = requests.get(manifest_url, timeout=REQUEST_TIMEOUT, proxies=REQ_PROXY)
    response.raise_for_status()
    return normalize_update_manifest(response.json(), manifest_url)


def get_update_status():
    manifest_url = get_settings_snapshot().get("update_manifest_url", "")
    status = {
        "current_version": APP_VERSION,
        "manifest_url": manifest_url,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }
    if not manifest_url:
        status.update({
            "state": "not_configured",
            "message": "未配置更新源，请先在设置中填写版本清单地址。",
        })
        return status

    manifest = fetch_update_manifest(manifest_url)
    has_update = compare_versions(manifest["version"], APP_VERSION) > 0
    status.update({
        "state": "available" if has_update else "latest",
        "latest_version": manifest["version"],
        "notes": manifest["notes"],
        "url": manifest["url"] if has_update else "",
        "sha256": manifest["sha256"] if has_update else "",
        "message": "发现新版本。" if has_update else "当前已是最新版本。",
    })
    return status


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
    if os.name == "nt":
        args = [
            installer_path,
            "/CURRENTUSER",
            "/SILENT",
            "/CLOSEAPPLICATIONS",
            "/RESTARTAPPLICATIONS",
        ]
        subprocess.Popen(args, close_fds=True)

        def _exit_later():
            time.sleep(1)
            os._exit(0)

        threading.Thread(target=_exit_later, daemon=True).start()
        return

    if sys.platform == "darwin":
        subprocess.Popen(["open", installer_path], close_fds=True)
        return

    subprocess.Popen([installer_path], close_fds=True)


def read_log_tail(max_lines=120):
    if not os.path.exists(APP_LOG_PATH):
        return []
    try:
        with open(APP_LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return [line.rstrip("\n") for line in lines[-max_lines:]]
    except OSError:
        return []


def build_config_backup():
    return {
        "app": "GoldMonitor",
        "version": APP_VERSION,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "settings": get_settings_snapshot(),
        "thresholds": {
            **{key: thresholds.get(key) for key in thresholds},
            "volatility_config": dict(volatility_config),
        },
    }


def restore_config_backup(payload):
    if not isinstance(payload, dict):
        raise ValueError("备份文件格式无效")
    settings_payload = payload.get("settings")
    thresholds_payload = payload.get("thresholds")
    if not isinstance(settings_payload, dict) and not isinstance(thresholds_payload, dict):
        raise ValueError("备份中没有可导入的配置")
    imported = []
    if isinstance(settings_payload, dict):
        updated, startup_error = apply_settings(settings_payload)
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
    report = {
        "app": APP_NAME,
        "version": APP_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "paths": {
            "appdata": APPDATA_DIR,
            "settings": SETTINGS_PATH,
            "thresholds": THRESHOLDS_PATH,
            "market_cache": MARKET_CACHE_PATH,
            "price_history": PRICE_HISTORY_PATH,
            "price_history_db": _price_history_db_path(),
            "log": APP_LOG_PATH,
        },
        "settings": diagnostic_settings_snapshot(),
        "fetch_status": get_fetch_status(),
        "source_health": get_source_health_state(),
        "price_history": build_price_history_state(limit=120),
        "risk_history_count": len(get_risk_analysis_history_state().get("items", [])),
        "recent_alerts": list(alert_log[-20:]),
        "logs": read_log_tail(),
    }
    return json.dumps(report, ensure_ascii=False, indent=2)


def show_alert_dialog(title, message):
    if not get_settings_snapshot().get("alert_dialog_enabled", True):
        return

    def _show():
        try:
            import ctypes
            MB_OK = 0x00000000
            MB_ICONWARNING = 0x00000030
            MB_TOPMOST = 0x00040000
            MB_SETFOREGROUND = 0x00010000
            ctypes.windll.user32.MessageBoxW(None, message, title, MB_OK | MB_ICONWARNING | MB_TOPMOST | MB_SETFOREGROUND)
        except Exception:
            pass

    threading.Thread(target=_show, daemon=True).start()


def play_system_alert_sound(level):
    if not get_settings_snapshot().get("alert_sound_enabled", True):
        return
    try:
        import winsound
        sound = "SystemHand" if level == "critical" else "SystemExclamation"
        winsound.PlaySound(sound, winsound.SND_ALIAS | winsound.SND_ASYNC)
    except Exception:
        pass


def select_related_news(title, items=None, limit=3):
    pool = items if items is not None else news_items
    title_text = str(title or "")
    preferred = []
    fallback = []
    for item in pool:
        topic = item.get("topic", "")
        haystack = f"{item.get('title', '')} {item.get('summary', '')}".lower()
        if "利率" in title_text and topic == "利率":
            preferred.append(item)
        elif "波动" in title_text and topic in {"美元", "通胀", "利率"}:
            preferred.append(item)
        elif any(keyword in haystack for keyword in ("gold", "xau", "黄金", "金价")):
            preferred.append(item)
        else:
            fallback.append(item)
    return (preferred + fallback)[:limit]


# ---------- 通知渠道 ----------

_alert_level_map = {"warning": "关注", "critical": "警告", "volatility": "波动"}


class _SafeFormatDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def _format_template(template, values, fallback):
    text = str(template or fallback)
    try:
        return text.format_map(_SafeFormatDict(values))
    except Exception:
        return str(fallback).format_map(_SafeFormatDict(values))


def _time_to_minutes(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        hour_text, minute_text = text.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except (ValueError, TypeError):
        return None
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return hour * 60 + minute
    return None


def is_alert_quiet_time(settings=None, now=None):
    settings = settings or get_settings_snapshot()
    start = _time_to_minutes(settings.get("alert_quiet_start"))
    end = _time_to_minutes(settings.get("alert_quiet_end"))
    if start is None or end is None or start == end:
        return False
    now = now or datetime.now()
    current = now.hour * 60 + now.minute
    if start < end:
        return start <= current < end
    return current >= start or current < end


def _alert_cooldown_key(entry):
    return ":".join([
        str(entry.get("type") or "warning"),
        str(entry.get("mode") or "all"),
    ])


def evaluate_alert_delivery(entry, settings=None, now=None):
    if entry.get("force_notify"):
        return {"deliver": True, "reason": ""}
    settings = settings or get_settings_snapshot()
    now = now or datetime.now()
    if is_alert_quiet_time(settings, now):
        return {"deliver": False, "reason": "quiet_time"}
    cooldown_minutes = int(settings.get("alert_cooldown_minutes", 0) or 0)
    if cooldown_minutes <= 0:
        return {"deliver": True, "reason": ""}
    key = _alert_cooldown_key(entry)
    last_time = alert_cooldown_state.get(key)
    if last_time and (now - last_time).total_seconds() < cooldown_minutes * 60:
        remaining = int(cooldown_minutes * 60 - (now - last_time).total_seconds())
        return {"deliver": False, "reason": "cooldown", "remaining_seconds": max(1, remaining)}
    alert_cooldown_state[key] = now
    return {"deliver": True, "reason": ""}


def build_alert_template_values(alert_type, title, message):
    with lock:
        values = {
            "title": title,
            "message": message,
            "level": _alert_level_map.get(alert_type, alert_type),
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "price_usd": f"{price_usd:,.2f}" if price_usd is not None else "--",
            "price_rmb": f"{price_rmb:,.2f}" if price_rmb is not None else "--",
            "rate": f"{usdcny_rate:.4f}" if usdcny_rate is not None else "--",
            "gold_source": gold_price_source or "--",
            "rate_source": usdcny_rate_source or "--",
        }
    return values


class EmailNotifier:
    """SMTP 邮件通知器"""

    @staticmethod
    def send(alert_type, title, message, timeout=10, blocking=False):
        settings = get_settings_snapshot()
        server = settings.get("smtp_server", "").strip()
        port_str = settings.get("smtp_port", "465").strip()
        encryption = settings.get("smtp_encryption", "ssl")
        sender = settings.get("smtp_sender", "").strip()
        password = settings.get("smtp_password", "")
        recipient = settings.get("smtp_recipient", "").strip()

        if not (server and port_str and sender and password and recipient):
            return "SMTP 配置不完整，跳过邮件发送"

        try:
            port = int(port_str)
        except ValueError:
            return f"SMTP 端口格式无效: {port_str}"

        values = build_alert_template_values(alert_type, title, message)
        level_label = values["level"]
        subject = _format_template(
            settings.get("email_subject_template"),
            values,
            DEFAULT_EMAIL_SUBJECT_TEMPLATE,
        )
        body = _format_template(
            settings.get("email_body_template"),
            values,
            DEFAULT_EMAIL_BODY_TEMPLATE,
        )

        try:
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = sender
            msg["To"] = recipient
            msg["Date"] = formatdate(localtime=True)
        except Exception as exc:
            return f"构建邮件失败: {exc}"

        def _send():
            try:
                if encryption == "ssl":
                    server_obj = smtplib.SMTP_SSL(server, port, timeout=timeout)
                else:
                    server_obj = smtplib.SMTP(server, port, timeout=timeout)
                    server_obj.starttls()
                server_obj.login(sender, password)
                server_obj.sendmail(sender, [recipient], msg.as_string())
                server_obj.quit()
                return None
            except Exception as exc:
                return str(exc)

        if blocking:
            error = _send()
            return error  # None on success, error string on failure

        def _send_async():
            error = _send()
            if error:
                logging.warning("邮件通知发送失败: %s", error)

        threading.Thread(target=_send_async, daemon=True).start()
        return None  # None 表示成功入队


class WebhookNotifier:
    """Webhook 通知器"""

    @staticmethod
    def send(alert_type, title, message, timeout=8, blocking=False):
        settings = get_settings_snapshot()
        if not settings.get("webhook_enabled", False):
            return "Webhook 通知未启用"
        url = settings.get("webhook_url", "").strip()
        if not url:
            return "Webhook 地址未配置，跳过发送"
        try:
            _require_https_url(url, "Webhook 地址")
        except ValueError as exc:
            return str(exc)

        values = build_alert_template_values(alert_type, title, message)
        payload = {
            "app": "GoldMonitor",
            "version": APP_VERSION,
            "type": alert_type,
            "level": values["level"],
            "title": title,
            "message": message,
            "time": values["time"],
            "price_usd": values["price_usd"],
            "price_rmb": values["price_rmb"],
            "rate": values["rate"],
            "gold_source": values["gold_source"],
            "rate_source": values["rate_source"],
        }

        def _send():
            try:
                response = requests.post(
                    url,
                    json=payload,
                    headers={"User-Agent": HTTP_USER_AGENT, "Content-Type": "application/json"},
                    timeout=timeout,
                    proxies=REQ_PROXY,
                )
                response.raise_for_status()
                return None
            except Exception as exc:
                return str(exc)

        if blocking:
            return _send()

        def _send_async():
            error = _send()
            if error:
                logging.warning("Webhook 通知发送失败: %s", error)

        threading.Thread(target=_send_async, daemon=True).start()
        return None


def dispatch_alert(entry, title):
    """通知渠道分发: 根据设置决定哪些渠道发送"""
    alert_type = entry.get("type", "warning")
    settings = get_settings_snapshot()

    # 邮件通知 — 按级别独立开关
    key_map = {"warning": "email_warning_enabled", "critical": "email_critical_enabled", "volatility": "email_volatility_enabled"}
    key = key_map.get(alert_type, "email_warning_enabled")
    if settings.get(key, True):
        error = EmailNotifier.send(alert_type, title, entry["message"])
        if error:
            logging.warning("邮件通知跳过: %s", error)

    webhook_key_map = {
        "warning": "webhook_warning_enabled",
        "critical": "webhook_critical_enabled",
        "volatility": "webhook_volatility_enabled",
    }
    if settings.get("webhook_enabled", False) and settings.get(webhook_key_map.get(alert_type, "webhook_warning_enabled"), True):
        error = WebhookNotifier.send(alert_type, title, entry["message"])
        if error:
            logging.warning("Webhook 通知跳过: %s", error)


def emit_alert(entry, title):
    settings = get_settings_snapshot()
    delivery = evaluate_alert_delivery(entry, settings)
    if not delivery.get("deliver"):
        reason = delivery.get("reason", "")
        entry["notification_muted"] = True
        entry["notification_reason"] = reason
        if reason == "quiet_time":
            entry["notification_message"] = "当前处于静默时段，仅记录提醒。"
        elif reason == "cooldown":
            entry["notification_message"] = "提醒冷却中，仅记录本次触发。"
    entry["related_news"] = select_related_news(title)
    entry["timestamp"] = datetime.now().isoformat(timespec="seconds")
    alert_log.append(entry)
    while len(alert_log) > 50:
        alert_log.pop(0)
    socketio.emit("alert", entry)
    history_state = build_price_history_state(limit=240)
    history_state["scope"] = "live"
    socketio.emit("price_history_updated", history_state)
    if delivery.get("deliver"):
        send_desktop_notification(title, entry["message"])
        play_system_alert_sound(entry.get("type", "warning"))
        show_alert_dialog(title, f"{entry['message']}\n\n时间: {entry['time']}")
        dispatch_alert(entry, title)


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
    elapsed_ms = None
    if started_at is not None:
        elapsed_ms = int(max(0, (time.monotonic() - started_at) * 1000))
    with lock:
        current = source_health.get(name, {
            "name": name,
            "category": category,
            "ok_count": 0,
            "fail_count": 0,
        })
        current.update({
            "name": name,
            "category": category,
            "ok": bool(ok),
            "cached": bool(cached),
            "error": str(error or ""),
            "last_checked": datetime.now().isoformat(timespec="seconds"),
            "elapsed_ms": elapsed_ms,
        })
        if ok:
            current["ok_count"] = int(current.get("ok_count", 0)) + 1
        else:
            current["fail_count"] = int(current.get("fail_count", 0)) + 1
        source_health[name] = current
        if len(source_health) > SOURCE_HEALTH_LIMIT:
            oldest = sorted(source_health.values(), key=lambda item: item.get("last_checked", ""))[0]
            source_health.pop(oldest.get("name"), None)
    socketio.emit("source_health_updated", get_source_health_state())


def get_source_health_state():
    with lock:
        items = sorted(
            [dict(item) for item in source_health.values()],
            key=lambda item: (item.get("category", ""), item.get("name", "")),
        )
    summary = {
        "total": len(items),
        "ok": sum(1 for item in items if item.get("ok")),
        "failed": sum(1 for item in items if item.get("ok") is False),
        "cached": sum(1 for item in items if item.get("cached")),
    }
    return {
        "items": items,
        "summary": summary,
        "comparison": get_source_comparison_state(),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


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
    now = datetime.now()
    items = []
    for sample in samples:
        checked_at = _parse_iso_datetime(sample.get("checked_at"))
        age_seconds = None
        if checked_at:
            age_seconds = max(0, int((now - checked_at).total_seconds()))
        stale = age_seconds is None or age_seconds > SOURCE_COMPARISON_STALE_SECONDS
        item = dict(sample)
        item["age_seconds"] = age_seconds
        item["stale"] = stale
        item["available"] = bool(item.get("usd")) and not item.get("cached") and not stale
        items.append(item)
    items.sort(key=lambda item: item.get("name", ""))
    comparable = [item for item in items if item.get("available")]
    state = {
        "items": items,
        "summary": {
            "total": len(items),
            "compared": len(comparable),
            "spread_usd": None,
            "spread_pct": None,
            "threshold_pct": SOURCE_COMPARISON_ANOMALY_PCT,
        },
        "status": "insufficient",
        "message": "可对比数据源不足",
        "updated_at": now.isoformat(timespec="seconds"),
    }
    if len(comparable) >= 2:
        low = min(comparable, key=lambda item: item.get("usd"))
        high = max(comparable, key=lambda item: item.get("usd"))
        spread_usd = round(float(high["usd"]) - float(low["usd"]), 4)
        midpoint = (float(high["usd"]) + float(low["usd"])) / 2
        spread_pct = round(spread_usd / midpoint * 100, 4) if midpoint else 0
        state["summary"].update({
            "spread_usd": spread_usd,
            "spread_pct": spread_pct,
            "low_source": low.get("name"),
            "high_source": high.get("name"),
        })
        if spread_pct >= SOURCE_COMPARISON_ANOMALY_PCT:
            state["status"] = "anomaly"
            state["message"] = f"数据源价差 {spread_pct:.2f}% ，建议核对行情源"
        else:
            state["status"] = "normal"
            state["message"] = f"数据源价差 {spread_pct:.2f}% ，处于正常范围"
    return state


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
        reader = csv.reader(io.StringIO(resp.text))
        rows = list(reader)
        if len(rows) < 1:
            error = f"{source_label}返回为空"
            record_source_health(source_label, "gold" if "金价" in source_label else "forex", False, error, started_at)
            return None, error
        # 格式: Symbol,Date,Time,Open,High,Low,Close,,Name
        r = rows[0]
        if len(r) < 7:
            error = f"{source_label}返回格式异常"
            record_source_health(source_label, "gold" if "金价" in source_label else "forex", False, error, started_at)
            return None, error
        record_source_health(source_label, "gold" if "金价" in source_label else "forex", True, "", started_at)
        return {
            "date": r[1],
            "time": r[2],
            "open": float(r[3]),
            "high": float(r[4]),
            "low": float(r[5]),
            "close": float(r[6]),
        }, ""
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
    raw = str(text or "")
    try:
        return raw.split('"', 2)[1]
    except IndexError:
        return ""


def _normalize_usdcny_cache(raw):
    if not isinstance(raw, dict):
        return None
    try:
        value = float(raw.get("value"))
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    timestamp = str(raw.get("timestamp") or "").strip()
    if not timestamp:
        return None
    return {
        "value": value,
        "source": str(raw.get("source") or "缓存汇率").strip(),
        "timestamp": timestamp,
        "cached": True,
    }


def _normalize_xauusd_cache(raw):
    if not isinstance(raw, dict):
        return None
    try:
        close = float(raw.get("close"))
    except (TypeError, ValueError):
        return None
    if close <= 0:
        return None
    timestamp = str(raw.get("timestamp") or "").strip()
    if not timestamp:
        return None

    def number_or_default(key, default):
        try:
            value = float(raw.get(key))
        except (TypeError, ValueError):
            return default
        return value if value > 0 else default

    return {
        "date": str(raw.get("date") or datetime.now().strftime("%Y-%m-%d")),
        "time": str(raw.get("time") or datetime.now().strftime("%H:%M:%S")),
        "open": number_or_default("open", close),
        "high": number_or_default("high", close),
        "low": number_or_default("low", close),
        "close": close,
        "source": str(raw.get("source") or "缓存金价").strip(),
        "timestamp": timestamp,
        "cached": True,
    }


def _parse_iso_datetime(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo:
            parsed = parsed.replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


def load_usdcny_cache():
    if not os.path.exists(MARKET_CACHE_PATH):
        return None
    try:
        with open(MARKET_CACHE_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    cache = payload.get("usdcny") if isinstance(payload, dict) else None
    return _normalize_usdcny_cache(cache)


def _load_market_cache_payload():
    if not os.path.exists(MARKET_CACHE_PATH):
        return {}
    try:
        with open(MARKET_CACHE_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_market_cache_section(section, data):
    os.makedirs(os.path.dirname(MARKET_CACHE_PATH), exist_ok=True)
    payload = _load_market_cache_payload()
    payload[section] = data
    tmp_path = MARKET_CACHE_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, MARKET_CACHE_PATH)


def load_xauusd_cache():
    payload = _load_market_cache_payload()
    cache = payload.get("xauusd")
    return _normalize_xauusd_cache(cache)


def load_valid_xauusd_cache(max_age_seconds=CACHE_RATE_MAX_AGE_SECONDS):
    cached = load_xauusd_cache()
    if not cached:
        return None
    parsed_time = _parse_iso_datetime(cached["timestamp"])
    if not parsed_time:
        return None
    age = datetime.now() - parsed_time
    if age.total_seconds() < 0 or age.total_seconds() > max_age_seconds:
        return None
    return cached


def load_valid_usdcny_cache(max_age_seconds=CACHE_RATE_MAX_AGE_SECONDS):
    cached = load_usdcny_cache()
    if not cached:
        return None
    parsed_time = _parse_iso_datetime(cached["timestamp"])
    if not parsed_time:
        return None
    age = datetime.now() - parsed_time
    if age.total_seconds() < 0 or age.total_seconds() > max_age_seconds:
        return None
    return cached


def save_usdcny_cache(value, source, timestamp=None):
    rate = _normalize_usdcny_cache({
        "value": value,
        "source": source,
        "timestamp": timestamp or datetime.now().isoformat(),
    })
    if not rate:
        raise ValueError("invalid USD/CNY rate cache")
    _write_market_cache_section("usdcny", {
        "value": rate["value"],
        "source": rate["source"],
        "timestamp": rate["timestamp"],
    })
    return {
        "value": rate["value"],
        "source": rate["source"],
        "timestamp": rate["timestamp"],
        "cached": False,
    }


def save_xauusd_cache(data, source, timestamp=None):
    if not isinstance(data, dict):
        raise ValueError("invalid XAU/USD cache")
    now_iso = timestamp or datetime.now().isoformat()
    cache = _normalize_xauusd_cache({
        "date": data.get("date"),
        "time": data.get("time"),
        "open": data.get("open"),
        "high": data.get("high"),
        "low": data.get("low"),
        "close": data.get("close"),
        "source": source,
        "timestamp": now_iso,
    })
    if not cache:
        raise ValueError("invalid XAU/USD cache")
    _write_market_cache_section("xauusd", {
        "date": cache["date"],
        "time": cache["time"],
        "open": cache["open"],
        "high": cache["high"],
        "low": cache["low"],
        "close": cache["close"],
        "source": cache["source"],
        "timestamp": cache["timestamp"],
    })
    return {
        "date": cache["date"],
        "time": cache["time"],
        "open": cache["open"],
        "high": cache["high"],
        "low": cache["low"],
        "close": cache["close"],
        "source": cache["source"],
        "timestamp": cache["timestamp"],
        "cached": False,
    }


def parse_sina_forex(text):
    try:
        quoted = _extract_quoted_payload(text)
        parts = quoted.split(",")
        if len(parts) < 2:
            return None, "新浪汇率返回格式异常"
        rate = float(parts[1])
    except (IndexError, TypeError, ValueError):
        return None, "新浪汇率返回格式异常"
    return (rate, "") if rate > 0 else (None, "新浪汇率返回无效")


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
    try:
        rate = float(payload["rates"]["CNY"])
    except (KeyError, TypeError, ValueError):
        return None, "Frankfurter 返回格式异常"
    return (rate, "") if rate > 0 else (None, "Frankfurter 返回无效汇率")


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
    quoted = _extract_quoted_payload(text)
    parts = [part.strip() for part in quoted.split(",") if part.strip()]
    numeric_values = []
    for part in parts:
        try:
            value = float(part)
        except ValueError:
            continue
        if value > 0:
            numeric_values.append(value)

    if not numeric_values:
        return None, "新浪贵金属未返回金价"

    close = numeric_values[0]
    open_price = numeric_values[3] if len(numeric_values) > 3 else close
    high_price = max(numeric_values[:6]) if len(numeric_values) >= 2 else close
    low_price = min(numeric_values[:6]) if len(numeric_values) >= 2 else close
    time_text = next((part for part in parts if ":" in part), datetime.now().strftime("%H:%M:%S"))
    now = datetime.now()
    return {
        "date": now.strftime("%Y-%m-%d"),
        "time": time_text,
        "open": open_price,
        "high": high_price,
        "low": low_price,
        "close": close,
    }, ""


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
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return None, "东方财富返回格式异常"

    scale_power = data.get("f59", 2)
    try:
        scale = 10 ** int(scale_power)
    except (TypeError, ValueError):
        scale = 100

    def field_value(key):
        value = data.get(key)
        if value in (None, "-", ""):
            return None
        return round(float(value) / scale, 4)

    close = field_value("f43")
    if close is None:
        return None, "东方财富未返回金价"

    now = datetime.now()
    parsed = {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "open": field_value("f46") or close,
        "high": field_value("f44") or close,
        "low": field_value("f45") or close,
        "close": close,
    }
    return parsed, ""


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
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return None, None, "GoldPrice 返回格式异常"

    rates = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        curr = str(item.get("curr") or "").upper()
        try:
            price = float(item.get("xauPrice"))
        except (TypeError, ValueError):
            continue
        if curr:
            rates[curr] = price

    usd_price = rates.get("USD")
    cny_price = rates.get("CNY")
    if usd_price is None:
        return None, None, "GoldPrice 未返回美元金价"

    cny_rate = round(cny_price / usd_price, 6) if cny_price and usd_price else None
    now = datetime.now()
    data = {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "open": usd_price,
        "high": usd_price,
        "low": usd_price,
        "close": usd_price,
    }
    return data, cny_rate, ""


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
    lowered = str(text or "").lower()
    return any(keyword in lowered for keyword in NEWS_KEYWORDS)


def classify_news_topic(text, source_kind=""):
    lowered = str(text or "").lower()
    if any(word in lowered for word in ("fomc", "federal reserve", "fed", "interest rate", "rate decision", "利率")):
        return "利率"
    if any(word in lowered for word in ("cpi", "inflation", "通胀")):
        return "通胀"
    if any(word in lowered for word in ("dollar", "usd", "yield", "美元", "美债")):
        return "美元"
    if any(word in lowered for word in ("central bank", "reserve", "央行")):
        return "央行"
    if any(word in lowered for word in ("gold", "xau", "bullion", "黄金", "金价")):
        return "黄金"
    if source_kind in {"fed", "macro"}:
        return "宏观"
    return "市场"


def _parse_gdelt_time(value):
    raw = str(value or "").strip()
    if len(raw) >= 15 and raw[8] == "T":
        try:
            return datetime.strptime(raw[:15], "%Y%m%dT%H%M%S").isoformat()
        except ValueError:
            pass
    return datetime.now().isoformat()


def _parse_rss_time(value):
    try:
        return parsedate_to_datetime(value).isoformat()
    except Exception:
        return datetime.now().isoformat()


def _news_key(item):
    url = str(item.get("url") or "").strip().lower()
    if url:
        return url
    return str(item.get("title") or "").strip().lower()


def normalize_news_items(items, limit=NEWS_LIMIT):
    seen = set()
    normalized = []
    for item in items:
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        if not title or not url:
            continue
        key = _news_key(item)
        if key in seen:
            continue
        seen.add(key)
        normalized.append({
            "title": title[:180],
            "url": url,
            "source": str(item.get("source") or "Public Source").strip(),
            "time": str(item.get("time") or datetime.now().isoformat()),
            "topic": str(item.get("topic") or classify_news_topic(title)),
            "summary": str(item.get("summary") or "").strip()[:260],
        })

    def sort_key(item):
        try:
            parsed = datetime.fromisoformat(item["time"].replace("Z", "+00:00"))
            if parsed.tzinfo:
                parsed = parsed.replace(tzinfo=None)
            return parsed
        except ValueError:
            return datetime.min

    normalized.sort(key=sort_key, reverse=True)
    return normalized[:limit]


def parse_gdelt_articles(payload):
    articles = payload.get("articles", []) if isinstance(payload, dict) else []
    items = []
    for article in articles:
        if not isinstance(article, dict):
            continue
        title = str(article.get("title") or "").strip()
        url = str(article.get("url") or "").strip()
        source = str(article.get("domain") or article.get("sourceCountry") or "GDELT").strip()
        text = f"{title} {source}"
        if not _is_relevant_news(text):
            continue
        items.append({
            "title": title,
            "url": url,
            "source": source,
            "time": _parse_gdelt_time(article.get("seendate")),
            "topic": classify_news_topic(text),
            "summary": "",
        })
    return normalize_news_items(items)


def parse_rss_items(xml_text, source_name, source_kind):
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items

    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = (item.findtext("description") or "").strip()
        text = f"{title} {description}"
        if not _is_relevant_news(text):
            continue
        items.append({
            "title": title,
            "url": link,
            "source": source_name,
            "time": _parse_rss_time(item.findtext("pubDate")),
            "topic": classify_news_topic(text, source_kind),
            "summary": description,
        })
    return normalize_news_items(items)


def load_news_cache():
    if not os.path.exists(NEWS_CACHE_PATH):
        return []
    try:
        with open(NEWS_CACHE_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if isinstance(payload, dict):
            return normalize_news_items(payload.get("items", []))
        if isinstance(payload, list):
            return normalize_news_items(payload)
    except (OSError, json.JSONDecodeError):
        return []
    return []


def save_news_cache(items):
    os.makedirs(APPDATA_DIR, exist_ok=True)
    payload = {
        "updated_at": datetime.now().isoformat(),
        "items": normalize_news_items(items),
    }
    tmp_path = NEWS_CACHE_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, NEWS_CACHE_PATH)


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


def normalize_risk_analysis_history(items):
    if not isinstance(items, list):
        return []
    normalized = []
    for item in items:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        normalized.append({
            "id": str(item.get("id") or item.get("analysis_time") or datetime.now().isoformat(timespec="seconds")),
            "analysis_time": str(item.get("analysis_time") or ""),
            "provider": str(item.get("provider") or ""),
            "model": str(item.get("model") or ""),
            "content": content,
            "structured": item.get("structured") if isinstance(item.get("structured"), dict) else {},
            "snapshot": item.get("snapshot") if isinstance(item.get("snapshot"), dict) else {},
            "usage": item.get("usage") if isinstance(item.get("usage"), dict) else None,
        })
        if len(normalized) >= RISK_ANALYSIS_HISTORY_LIMIT:
            break
    return normalized


def load_risk_analysis_history():
    if not os.path.exists(RISK_ANALYSIS_HISTORY_PATH):
        return []
    try:
        with open(RISK_ANALYSIS_HISTORY_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if isinstance(payload, dict):
            return normalize_risk_analysis_history(payload.get("items", []))
        return normalize_risk_analysis_history(payload)
    except (OSError, json.JSONDecodeError):
        return []


def save_risk_analysis_history(items=None):
    items = risk_analysis_history if items is None else items
    normalized = normalize_risk_analysis_history(items)
    os.makedirs(APPDATA_DIR, exist_ok=True)
    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "items": normalized,
    }
    tmp_path = RISK_ANALYSIS_HISTORY_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, RISK_ANALYSIS_HISTORY_PATH)
    return normalized


def get_risk_analysis_history_state():
    with risk_history_lock:
        return {"items": list(risk_analysis_history[:RISK_ANALYSIS_HISTORY_LIMIT])}


def add_risk_analysis_history_entry(result, snapshot):
    global risk_analysis_history
    entry = {
        "id": datetime.now().isoformat(timespec="seconds"),
        "analysis_time": snapshot.get("analysis_time") or datetime.now().isoformat(timespec="seconds"),
        "provider": result.get("provider", ""),
        "model": result.get("model", ""),
        "content": result.get("content", ""),
        "structured": result.get("structured") if isinstance(result.get("structured"), dict) else {},
        "snapshot": snapshot,
        "usage": result.get("usage") if isinstance(result.get("usage"), dict) else None,
    }
    with risk_history_lock:
        risk_analysis_history = normalize_risk_analysis_history([entry] + risk_analysis_history)
        try:
            save_risk_analysis_history(risk_analysis_history)
        except OSError as exc:
            logging.warning("failed to save risk analysis history: %s", exc)
        return dict(entry)


def clear_risk_analysis_history_state():
    global risk_analysis_history
    with risk_history_lock:
        risk_analysis_history = []
        try:
            save_risk_analysis_history(risk_analysis_history)
        except OSError as exc:
            logging.warning("failed to clear risk analysis history: %s", exc)
        return get_risk_analysis_history_state()


def normalize_price_history(items):
    if not isinstance(items, list):
        return []
    normalized = []
    for item in items:
        if not isinstance(item, dict):
            continue
        timestamp = str(item.get("timestamp") or "").strip()
        if not timestamp:
            continue
        parsed = _parse_iso_datetime(timestamp)
        if not parsed:
            continue

        def optional_float(key):
            value = item.get(key)
            if value in (None, ""):
                return None
            try:
                number = float(value)
            except (TypeError, ValueError):
                return None
            return number if math.isfinite(number) else None

        normalized.append({
            "usd": optional_float("usd"),
            "rmb": optional_float("rmb"),
            "rate": optional_float("rate"),
            "time": str(item.get("time") or parsed.strftime("%H:%M:%S")),
            "timestamp": parsed.isoformat(timespec="seconds"),
        })
    normalized.sort(key=lambda item: item.get("timestamp", ""))
    return normalized[-PRICE_HISTORY_ARCHIVE_LIMIT:]


def _price_history_db_path():
    base, _ext = os.path.splitext(PRICE_HISTORY_PATH)
    return base + ".sqlite3"


def _connect_price_history_db():
    path = _price_history_db_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            timestamp TEXT PRIMARY KEY,
            time TEXT NOT NULL,
            usd REAL,
            rmb REAL,
            rate REAL
        )
    """)
    return conn


def _upsert_price_history_points(items):
    normalized = normalize_price_history(items)
    if not normalized:
        return []
    with _connect_price_history_db() as conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO price_history(timestamp, time, usd, rmb, rate)
            VALUES(:timestamp, :time, :usd, :rmb, :rate)
            """,
            normalized,
        )
        conn.execute(
            """
            DELETE FROM price_history
            WHERE timestamp NOT IN (
                SELECT timestamp FROM price_history
                ORDER BY timestamp DESC
                LIMIT ?
            )
            """,
            (PRICE_HISTORY_ARCHIVE_LIMIT,),
        )
    return normalized


def _load_price_history_from_db():
    path = _price_history_db_path()
    if not os.path.exists(path):
        return []
    with _connect_price_history_db() as conn:
        rows = conn.execute(
            """
            SELECT usd, rmb, rate, time, timestamp
            FROM price_history
            ORDER BY timestamp ASC
            LIMIT ?
            """,
            (PRICE_HISTORY_ARCHIVE_LIMIT,),
        ).fetchall()
    return normalize_price_history([
        {"usd": row[0], "rmb": row[1], "rate": row[2], "time": row[3], "timestamp": row[4]}
        for row in rows
    ])


def _filter_price_history_from_db(minutes=None, limit=600):
    path = _price_history_db_path()
    if not os.path.exists(path):
        return []
    params = []
    where = ""
    if minutes:
        latest_items = _load_price_history_from_db()
        latest_time = _parse_iso_datetime(latest_items[-1].get("timestamp")) if latest_items else datetime.now()
        cutoff = (latest_time or datetime.now()) - timedelta(minutes=int(minutes))
        where = "WHERE timestamp >= ?"
        params.append(cutoff.isoformat(timespec="seconds"))
    params.append(int(limit or PRICE_HISTORY_EXPORT_LIMIT))
    with _connect_price_history_db() as conn:
        rows = conn.execute(
            f"""
            SELECT usd, rmb, rate, time, timestamp
            FROM price_history
            {where}
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    rows.reverse()
    return normalize_price_history([
        {"usd": row[0], "rmb": row[1], "rate": row[2], "time": row[3], "timestamp": row[4]}
        for row in rows
    ])


def _load_price_history_json_archive():
    if not os.path.exists(PRICE_HISTORY_PATH):
        return []
    try:
        with open(PRICE_HISTORY_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if isinstance(payload, dict):
            return normalize_price_history(payload.get("items", []))
        return normalize_price_history(payload)
    except (OSError, json.JSONDecodeError):
        return []


def load_price_history_archive():
    try:
        db_items = _load_price_history_from_db()
        if db_items:
            return db_items
    except (OSError, sqlite3.Error) as exc:
        logging.warning("价格历史数据库读取失败: %s", exc)

    json_items = _load_price_history_json_archive()
    if json_items:
        try:
            _upsert_price_history_points(json_items)
        except (OSError, sqlite3.Error) as exc:
            logging.warning("价格历史迁移到 SQLite 失败: %s", exc)
    return json_items


def _write_price_history_json_archive(items):
    normalized = normalize_price_history(items)
    os.makedirs(APPDATA_DIR, exist_ok=True)
    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "items": normalized,
    }
    tmp_path = PRICE_HISTORY_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, PRICE_HISTORY_PATH)
    return normalized


def save_price_history_archive(items=None):
    items = price_archive if items is None else items
    normalized = normalize_price_history(items)
    try:
        _upsert_price_history_points(normalized)
    except (OSError, sqlite3.Error) as exc:
        logging.warning("价格历史写入 SQLite 失败: %s", exc)
    _write_price_history_json_archive(normalized)
    return normalized


def add_price_history_entry(entry, force_save=False):
    global price_archive, last_price_history_save_at
    normalized = normalize_price_history([entry])
    if not normalized:
        return
    point = normalized[0]
    price_archive.append(point)
    if len(price_archive) > PRICE_HISTORY_ARCHIVE_LIMIT:
        price_archive = price_archive[-PRICE_HISTORY_ARCHIVE_LIMIT:]
    try:
        _upsert_price_history_points([point])
    except (OSError, sqlite3.Error) as exc:
        logging.warning("价格历史增量写入 SQLite 失败: %s", exc)
    now_monotonic = time.monotonic()
    if force_save or now_monotonic - last_price_history_save_at >= PRICE_HISTORY_SAVE_INTERVAL_SECONDS:
        try:
            price_archive = _write_price_history_json_archive(price_archive)
            last_price_history_save_at = now_monotonic
        except OSError as exc:
            logging.warning("价格历史保存失败: %s", exc)


def _filter_price_archive(minutes=None, limit=600):
    with lock:
        items = list(price_archive)
    if len(items) < int(limit or 0):
        try:
            db_items = _filter_price_history_from_db(minutes=minutes, limit=limit)
            if db_items:
                return db_items
        except (OSError, sqlite3.Error) as exc:
            logging.warning("价格历史数据库查询失败: %s", exc)
    if minutes:
        latest_time = _parse_iso_datetime(items[-1].get("timestamp")) if items else datetime.now()
        cutoff = (latest_time or datetime.now()) - timedelta(minutes=int(minutes))
        items = [
            item for item in items
            if (_parse_iso_datetime(item.get("timestamp")) or cutoff) >= cutoff
        ]
    if limit:
        items = items[-int(limit):]
    return items


def _event_time_from_alert(entry):
    timestamp = entry.get("timestamp")
    parsed = _parse_iso_datetime(timestamp)
    if parsed:
        return parsed
    raw_time = str(entry.get("time") or "").strip()
    if raw_time and today_date:
        parsed = _parse_iso_datetime(f"{today_date}T{raw_time}")
        if parsed:
            return parsed
    return None


def _build_price_event_state(items):
    if not items:
        return []
    parsed_points = [
        _parse_iso_datetime(item.get("timestamp"))
        for item in items
    ]
    parsed_points = [item for item in parsed_points if item]
    if not parsed_points:
        return []
    start_time = min(parsed_points)
    end_time = max(parsed_points)
    events = []

    for entry in list(alert_log[-50:]):
        event_time = _event_time_from_alert(entry)
        if not event_time or event_time < start_time or event_time > end_time:
            continue
        events.append({
            "type": "alert",
            "level": entry.get("type", "warning"),
            "mode": entry.get("mode", ""),
            "timestamp": event_time.isoformat(timespec="seconds"),
            "time": entry.get("time", event_time.strftime("%H:%M:%S")),
            "label": alert_level_label(entry.get("type")),
            "message": str(entry.get("message") or "")[:180],
        })

    with risk_history_lock:
        risk_items = list(risk_analysis_history[:RISK_ANALYSIS_HISTORY_LIMIT])
    for entry in risk_items:
        snapshot = entry.get("snapshot") if isinstance(entry.get("snapshot"), dict) else {}
        event_time = _parse_iso_datetime(entry.get("analysis_time") or snapshot.get("analysis_time"))
        if not event_time or event_time < start_time or event_time > end_time:
            continue
        structured = entry.get("structured") if isinstance(entry.get("structured"), dict) else {}
        label = "风险分析"
        if structured.get("risk_level"):
            label = f"风险 {structured.get('risk_level')}"
        events.append({
            "type": "risk",
            "level": "analysis",
            "timestamp": event_time.isoformat(timespec="seconds"),
            "time": event_time.strftime("%H:%M:%S"),
            "label": label[:40],
            "message": str(entry.get("content") or "")[:180],
        })

    events.sort(key=lambda item: item.get("timestamp", ""))
    return events[-100:]


def alert_level_label(alert_type):
    if alert_type == "critical":
        return "关键预警"
    if alert_type == "volatility":
        return "波动预警"
    return "价格预警"


def build_price_history_state(minutes=None, limit=600):
    items = _filter_price_archive(minutes, limit)

    def series_stats(field):
        values = [item.get(field) for item in items if item.get(field) is not None]
        if not values:
            return {"points": 0, "start": None, "end": None, "high": None, "low": None, "change": None, "change_pct": None}
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

    return {
        "items": items,
        "stats": {
            "usd": series_stats("usd"),
            "rmb": series_stats("rmb"),
        },
        "total": len(items),
        "minutes": minutes,
        "events": _build_price_event_state(items),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


def build_price_history_csv(minutes=None):
    items = _filter_price_archive(minutes, PRICE_HISTORY_EXPORT_LIMIT)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["timestamp", "time", "usd_per_oz", "rmb_per_gram", "usdcny_rate"])
    for item in items:
        writer.writerow([
            item.get("timestamp", ""),
            item.get("time", ""),
            item.get("usd", ""),
            item.get("rmb", ""),
            item.get("rate", ""),
        ])
    return output.getvalue(), len(items)


def news_loop():
    while True:
        refresh_gold_news(emit_update=True)
        time.sleep(NEWS_REFRESH_INTERVAL)


news_items = load_news_cache()
risk_analysis_history = load_risk_analysis_history()
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


def build_risk_analysis_snapshot(context):
    market = context.get("market", {})
    daily = context.get("daily", {})
    history = context.get("history_summary", {})
    return {
        "analysis_time": context.get("analysis_time"),
        "analysis_depth": context.get("analysis_depth", "standard"),
        "price_usd": market.get("price_usd"),
        "price_rmb": market.get("price_rmb"),
        "usdcny_rate": market.get("usdcny_rate"),
        "gold_source": market.get("gold_source"),
        "gold_time": market.get("gold_time"),
        "rate_source": market.get("rate_source"),
        "rate_time": market.get("rate_time"),
        "daily_pct_usd": daily.get("pct_usd"),
        "daily_pct_rmb": daily.get("pct_rmb"),
        "history_points": history.get("usd", {}).get("points", 0),
        "kline_points": context.get("kline_summary", {}).get("usd", {}).get("points", 0),
        "news_count": len(context.get("news", [])),
        "sample_warning": context.get("sample_warning", ""),
        "data_quality": context.get("data_quality", {}),
        "multi_period_trends": context.get("multi_period_trends", []),
        "risk_scorecard": context.get("risk_scorecard", {}),
        "manual_trigger": context.get("manual_trigger", {}),
    }


def parse_risk_analysis_sections(content):
    sections = {key: [] for key, _ in RISK_STRUCTURED_SECTION_LABELS}
    current_key = None
    for raw_line in str(content or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        clean = line.lstrip("#*-0123456789.、 ").strip()
        matched = False
        for key, label in RISK_STRUCTURED_SECTION_LABELS:
            for separator in ("：", ":"):
                prefix = label + separator
                if clean.startswith(prefix):
                    current_key = key
                    value = clean[len(prefix):].strip()
                    if value:
                        sections[key].append(value)
                    matched = True
                    break
            if matched:
                break
        if matched:
            continue
        if current_key:
            sections[current_key].append(line)
    return {
        key: "\n".join(value).strip()
        for key, value in sections.items()
        if "\n".join(value).strip()
    }


def build_risk_analysis_cache_key(snapshot):
    data = {
        "analysis_depth": snapshot.get("analysis_depth", "standard"),
        "price_usd": snapshot.get("price_usd"),
        "price_rmb": snapshot.get("price_rmb"),
        "usdcny_rate": snapshot.get("usdcny_rate"),
        "gold_time": snapshot.get("gold_time"),
        "rate_time": snapshot.get("rate_time"),
        "history_points": snapshot.get("history_points"),
        "kline_points": snapshot.get("kline_points"),
        "news_count": snapshot.get("news_count"),
        "sample_warning": snapshot.get("sample_warning", ""),
        "manual_trigger": snapshot.get("manual_trigger") or {},
    }
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def find_recent_risk_analysis_cache(snapshot, cache_minutes):
    if not cache_minutes:
        return None
    target_key = build_risk_analysis_cache_key(snapshot)
    now = datetime.now()
    with risk_history_lock:
        for item in risk_analysis_history:
            item_snapshot = item.get("snapshot") if isinstance(item.get("snapshot"), dict) else {}
            if build_risk_analysis_cache_key(item_snapshot) != target_key:
                continue
            item_time = _parse_iso_datetime(item.get("analysis_time"))
            if not item_time:
                continue
            age_seconds = max(0, int((now - item_time).total_seconds()))
            if age_seconds <= cache_minutes * 60:
                cached = dict(item)
                cached["cache_age_seconds"] = age_seconds
                return cached
    return None


def selected_risk_model_config(settings, provider=None):
    provider = provider or settings.get("risk_assistant_provider", "deepseek")
    if provider == "deepseek":
        return (
            provider,
            settings.get("deepseek_base_url") or DEFAULT_SETTINGS["deepseek_base_url"],
            settings.get("deepseek_model") or DEFAULT_SETTINGS["deepseek_model"],
            settings.get("deepseek_api_key") or "",
        )
    if provider == "openai_compatible":
        return (
            provider,
            settings.get("openai_compatible_base_url") or "",
            settings.get("openai_compatible_model") or "",
            settings.get("openai_compatible_api_key") or "",
        )
    return provider, "", "", ""


def test_risk_model_availability(settings):
    provider, base_url, model, api_key = selected_risk_model_config(settings)
    if provider not in VALID_RISK_ASSISTANT_PROVIDERS:
        return {"ok": False, "provider": provider, "model": model, "message": "当前模型提供商暂不支持。"}
    if not base_url:
        return {"ok": False, "provider": provider, "model": model, "message": "请先配置模型接口地址。"}
    if not model:
        return {"ok": False, "provider": provider, "model": model, "message": "请先选择或填写模型。"}
    if not api_key:
        return {"ok": False, "provider": provider, "model": model, "message": "请先配置当前模型提供商的 API Key。"}

    options = fetch_risk_model_options(settings, provider)
    models = options.get("models", [])
    if options.get("source") == "api" and model in models:
        return {
            "ok": True,
            "provider": provider,
            "model": model,
            "models": models,
            "message": f"模型连接正常，接口已返回 {model}。",
        }
    if options.get("source") == "api":
        return {
            "ok": False,
            "provider": provider,
            "model": model,
            "models": models,
            "message": f"接口可访问，但模型列表未包含 {model}。",
        }
    return {
        "ok": False,
        "provider": provider,
        "model": model,
        "models": models,
        "message": options.get("error") or "模型列表获取失败，无法确认当前模型是否可用。",
    }


def build_risk_analysis_messages(context):
    depth = context.get("analysis_depth", "standard")
    depth_label = {"quick": "快速", "standard": "标准", "deep": "深度"}.get(depth, "标准")
    system_prompt = (
        "你是金价监控工具中的风险分析助手。"
        "请只做风险、趋势和观察依据分析，不提供交易动作、持有比例、收益承诺或保证性结论。"
        "如果数据样本不足或来源为缓存，需要直接指出限制。"
        "输出使用中文，结构包含：数据可信度、风险评分卡、多周期趋势、主要风险、观察依据、后续关注。"
        "请使用固定字段输出：风险等级、趋势方向、数据可信度、主要影响因素、观察价格区间、后续关注。"
    )
    user_prompt = (
        f"请基于以下实时上下文进行{depth_label}黄金价格风险与趋势分析。"
        "请优先说明风险评分卡、多周期趋势是否一致，以及数据可信度对结论的影响。"
        "仅输出风险研判，不输出具体操作指令。"
        "请严格使用以下标签开头：风险等级：、趋势方向：、数据可信度：、主要影响因素：、观察价格区间：、后续关注：。\n\n"
        f"{json.dumps(context, ensure_ascii=False, separators=(',', ':'))}"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _chat_completions_url(base_url):
    base_url = (base_url or "").rstrip("/")
    if base_url.endswith("/chat/completions"):
        return base_url
    return f"{base_url}/chat/completions"


def _models_url(base_url):
    base_url = (base_url or "").rstrip("/")
    if base_url.endswith("/chat/completions"):
        base_url = base_url[: -len("/chat/completions")]
    return f"{base_url}/models"


def fetch_risk_model_options(settings, provider=None):
    provider = provider or settings.get("risk_assistant_provider", "deepseek")
    if provider == "deepseek":
        base_url = settings.get("deepseek_base_url") or DEFAULT_SETTINGS["deepseek_base_url"]
        api_key = settings.get("deepseek_api_key") or ""
        fallback = list(DEEPSEEK_FALLBACK_MODELS)
    elif provider == "openai_compatible":
        base_url = settings.get("openai_compatible_base_url") or ""
        api_key = settings.get("openai_compatible_api_key") or ""
        fallback = [settings.get("openai_compatible_model")] if settings.get("openai_compatible_model") else []
    else:
        return {"provider": provider, "models": [], "source": "unsupported", "error": "暂不支持当前模型提供商。"}

    if not base_url:
        return {"provider": provider, "models": fallback, "source": "fallback", "error": "请先配置模型接口地址。"}

    headers = {"User-Agent": HTTP_USER_AGENT}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        response = requests.get(
            _models_url(base_url),
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            proxies=REQ_PROXY,
        )
        response.raise_for_status()
        body = response.json()
        raw_models = body.get("data", []) if isinstance(body, dict) else []
        models = [
            str(item.get("id") or item.get("model") or "").strip()
            for item in raw_models
            if isinstance(item, dict) and str(item.get("id") or item.get("model") or "").strip()
        ]
        if models:
            return {"provider": provider, "models": models, "source": "api", "error": ""}
        return {"provider": provider, "models": fallback, "source": "fallback", "error": ""}
    except requests.RequestException as exc:
        return {"provider": provider, "models": fallback, "source": "fallback", "error": f"模型列表获取失败：{exc}"}
    except (ValueError, TypeError):
        return {"provider": provider, "models": fallback, "source": "fallback", "error": "模型列表返回格式异常。"}


def call_openai_chat_completion(settings, context, provider, base_url, model, api_key):
    if not api_key:
        return None, "请先配置当前模型提供商的 API Key。"
    if not base_url:
        return None, "请先配置当前模型提供商的接口地址。"
    if not model:
        return None, "请先选择或填写模型。"

    max_tokens = settings.get("risk_assistant_max_tokens", RISK_ASSISTANT_MAX_TOKENS)
    depth = context.get("analysis_depth", "standard")
    if depth == "quick":
        max_tokens = min(max_tokens, 900)
    elif depth == "deep":
        max_tokens = max(max_tokens, 1800)
    payload = {
        "model": model,
        "messages": build_risk_analysis_messages(context),
        "temperature": RISK_ASSISTANT_TEMPERATURE,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if provider == "deepseek" and model == "deepseek-v4-pro":
        payload["thinking"] = {"type": "enabled"}
        payload["reasoning_effort"] = "medium"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": HTTP_USER_AGENT,
    }
    try:
        response = requests.post(
            _chat_completions_url(base_url),
            headers=headers,
            json=payload,
            timeout=RISK_ASSISTANT_TIMEOUT,
            proxies=REQ_PROXY,
        )
        if response.status_code in (401, 403):
            return None, "模型服务认证失败，请检查 API Key。"
        response.raise_for_status()
        body = response.json()
        choices = body.get("choices") if isinstance(body, dict) else None
        if not choices:
            return None, "模型服务返回内容为空。"
        message = choices[0].get("message") if isinstance(choices[0], dict) else {}
        content = str(message.get("content") or "").strip()
        if not content:
            return None, "模型服务返回内容为空。"
        return {
            "provider": provider,
            "model": model,
            "content": content,
            "structured": parse_risk_analysis_sections(content),
            "usage": body.get("usage") if isinstance(body, dict) else None,
        }, None
    except requests.Timeout:
        return None, "模型服务请求超时，请稍后重试。"
    except requests.ConnectionError:
        return None, "无法连接模型服务，请检查网络。"
    except requests.HTTPError as exc:
        status = getattr(exc.response, "status_code", "")
        return None, f"模型服务请求失败：HTTP {status}"
    except requests.RequestException as exc:
        return None, f"模型服务请求失败：{exc}"
    except (ValueError, KeyError, TypeError):
        return None, "模型服务返回格式异常。"


def call_deepseek_risk_analysis(settings, context):
    return call_openai_chat_completion(
        settings,
        context,
        "deepseek",
        settings.get("deepseek_base_url") or DEFAULT_SETTINGS["deepseek_base_url"],
        settings.get("deepseek_model") or DEFAULT_SETTINGS["deepseek_model"],
        settings.get("deepseek_api_key") or "",
    )


def call_openai_compatible_risk_analysis(settings, context):
    return call_openai_chat_completion(
        settings,
        context,
        "openai_compatible",
        settings.get("openai_compatible_base_url") or "",
        settings.get("openai_compatible_model") or "",
        settings.get("openai_compatible_api_key") or "",
    )


def run_risk_analysis(settings, context):
    provider = settings.get("risk_assistant_provider", "deepseek")
    if provider == "deepseek":
        return call_deepseek_risk_analysis(settings, context)
    if provider == "openai_compatible":
        return call_openai_compatible_risk_analysis(settings, context)
    return None, "暂不支持当前风险分析模型提供商。"


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
    if price is None:
        return

    unit = "$" if mode == "usd" else "¥"
    mode_label = "国际金价" if mode == "usd" else "国内金价"

    levels = [
        ("upper_warning", "warning", "上涨关注"),
        ("upper_critical", "critical", "突破上限"),
        ("lower_warning", "warning", "下跌关注"),
        ("lower_critical", "critical", "跌破下限"),
    ]

    for key_suffix, level, label in levels:
        key = f"{key_suffix}_{mode}"
        val = thresholds.get(key)
        if val is None:
            continue

        is_upper = "upper" in key_suffix
        triggered = (is_upper and price >= val) or (not is_upper and price <= val)

        if triggered:
            if alerted_flags.get(key):
                return
            alerted_flags[key] = True

            rate_note = ""
            if mode == "rmb" and usdcny_rate:
                rate_kind = "缓存汇率" if usdcny_rate_cached else "实时汇率"
                rate_note = f"；{rate_kind} {usdcny_rate:.4f}"
                if usdcny_rate_source:
                    rate_note += f"（{usdcny_rate_source}）"
            msg = f"[{mode_label}] {label}: {unit}{price:,.2f} (阈值 {unit}{val:,.2f}{rate_note})"
            alert_entry = {
                "time": now_str, "type": level, "mode": mode, "message": msg,
            }
            emit_alert(alert_entry, f"金价预警 - {label}")
            return
        else:
            if alerted_flags.get(key):
                alerted_flags[key] = False


# ---------- 波动率检查 ----------
def _check_volatility(now_str):
    global last_volatility_check
    if not volatility_config.get("enabled") or volatility_config["percent"] is None:
        return

    pct = volatility_config["percent"]
    minutes = volatility_config.get("minutes", 10)
    points_needed = max(1, int(minutes * 60 / 10))  # 每 10 秒一个点

    if len(price_history) < points_needed:
        return

    # 避免频繁检查
    now = datetime.now()
    if last_volatility_check and (now - last_volatility_check).seconds < 60:
        return
    last_volatility_check = now

    window = price_history[-points_needed:]
    usd_prices = [p["usd"] for p in window if p["usd"] is not None]
    if len(usd_prices) < points_needed:
        return

    start_price = usd_prices[0]
    end_price = usd_prices[-1]
    if start_price == 0:
        return

    change_pct = abs((end_price - start_price) / start_price * 100)
    if change_pct >= pct:
        direction = "上涨" if end_price > start_price else "下跌"
        msg = f"[波动预警] {minutes}分钟内{direction} {change_pct:.2f}% (${start_price:,.2f} → ${end_price:,.2f})"
        alert_entry = {"time": now_str, "type": "volatility", "mode": "usd", "message": msg}
        emit_alert(alert_entry, "金价波动预警")


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


@socketio.on("get_settings")
def on_get_settings():
    emit("settings_updated", public_settings_snapshot())


@socketio.on("update_settings")
def on_update_settings(data):
    if not isinstance(data, dict):
        emit("settings_error", {"message": "设置格式无效"})
        return

    current = get_settings_snapshot()
    allowed = set(DEFAULT_SETTINGS)
    incoming = {k: v for k, v in data.items() if k in allowed}
    if "deepseek_api_key" in incoming:
        key_value = str(incoming.get("deepseek_api_key") or "").strip()
        if key_value:
            incoming["deepseek_api_key"] = key_value
        elif data.get("deepseek_api_key_clear"):
            incoming["deepseek_api_key"] = ""
        else:
            incoming.pop("deepseek_api_key", None)
    if "openai_compatible_api_key" in incoming:
        key_value = str(incoming.get("openai_compatible_api_key") or "").strip()
        if key_value:
            incoming["openai_compatible_api_key"] = key_value
        elif data.get("openai_compatible_api_key_clear"):
            incoming["openai_compatible_api_key"] = ""
        else:
            incoming.pop("openai_compatible_api_key", None)
    current.update(incoming)
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


@socketio.on("export_config")
def on_export_config():
    emit("config_backup_ready", {
        "filename": f"GoldMonitor-config-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json",
        "content": json.dumps(build_config_backup(), ensure_ascii=False, indent=2),
    })


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
    emit("diagnostics_ready", {
        "filename": f"GoldMonitor-diagnostics-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json",
        "content": build_diagnostics_report(),
    })


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
            "message": "检查更新失败，请确认更新源和网络连接。",
        })


@socketio.on("install_update")
def on_install_update(data=None):
    try:
        status = get_update_status()
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
    if rmb is not None and usd is not None:
        return f"{APP_NAME} ¥{rmb:,.2f}/克 | ${usd:,.2f}/oz"
    if rmb is not None:
        return f"{APP_NAME} ¥{rmb:,.2f}/克"
    if usd is not None:
        return f"{APP_NAME} ${usd:,.2f}/oz"
    return APP_NAME


def update_desktop_price_title(title=None):
    global _last_desktop_title
    title = title or format_price_title()
    if title == _last_desktop_title:
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


def format_floating_price_text(rmb=None, usd=None, pct=None):
    display_mode = get_settings_snapshot().get("floating_price_display_mode", "rmb_usd")
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

    trend = ""
    trend_state = "neutral"
    if pct is not None:
        try:
            pct_value = float(pct)
            if math.isfinite(pct_value):
                trend = f"{pct_value:+.2f}%"
                if pct_value > 0:
                    trend_state = "up"
                elif pct_value < 0:
                    trend_state = "down"
        except (TypeError, ValueError):
            trend = ""

    time_label = "等待更新"
    parsed_time = _parse_iso_datetime(fetch_time)
    if parsed_time:
        time_label = parsed_time.strftime("%H:%M")

    if not fetch_ok and fetch_error:
        source_state = "error"
        source_label = "异常"
    elif gold_cached or rate_cached:
        source_state = "cached"
        source_label = "缓存"
    elif fetch_ok:
        source_state = "live"
        source_label = "实时"
    else:
        source_state = "waiting"
        source_label = "等待"

    status = f"{time_label} · {source_name} · {source_label}"
    if rmb is None and usd is None:
        return "黄金 --", "等待行情数据", status, "neutral", source_state

    if display_mode == "usd_only" and usd is not None:
        primary = f"黄金 ${usd:,.2f}/oz"
        return primary, trend or "双击打开主窗口", status, trend_state, source_state

    if rmb is not None:
        primary = f"黄金 ¥{rmb:,.2f}/克"
        if display_mode == "rmb_only" and trend:
            secondary = trend
        elif display_mode == "rmb_only":
            secondary = "双击打开主窗口"
        elif usd is not None and trend:
            secondary = f"${usd:,.2f}/oz  {trend}"
        elif usd is not None:
            secondary = f"${usd:,.2f}/oz"
        elif trend:
            secondary = trend
        else:
            secondary = "双击打开主窗口"
        return primary, secondary, status, trend_state, source_state

    if usd is not None:
        primary = f"黄金 ${usd:,.2f}/oz"
        return primary, trend or "双击打开主窗口", status, trend_state, source_state

    return "黄金 --", "等待行情数据", status, "neutral", source_state


def _is_floating_price_available():
    return _desktop_runtime_active and os.name == "nt"


def _floating_window_metrics():
    preset = get_settings_snapshot().get("floating_price_preset", DEFAULT_SETTINGS["floating_price_preset"])
    if preset not in FLOATING_PRICE_PRESETS:
        preset = DEFAULT_SETTINGS["floating_price_preset"]
    return FLOATING_PRICE_PRESETS[preset]


def _floating_rect(rect_config, width, height):
    if not rect_config:
        return None
    left, top, right, bottom = rect_config
    if right < 0:
        right = width + right
    if bottom < 0:
        bottom = height + bottom
    return left, top, right, bottom


def _floating_window_size():
    return _floating_window_metrics()["size"]


def _floating_window_radius():
    return _floating_window_metrics()["radius"]


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
        width, height = _floating_window_size()
        left, top, right, bottom = _get_work_area(user32)
        min_x = left + 8
        min_y = top + 8
        max_x = max(min_x, right - width - 8)
        max_y = max(min_y, bottom - height - 8)
        return max(min_x, min(int(x), max_x)), max(min_y, min(int(y), max_y))
    except Exception:
        return int(x), int(y)


def _default_floating_position(user32, width, height):
    left, top, right, bottom = _get_work_area(user32)
    return right - width - 16, bottom - height - 16


def _snap_floating_position(x, y, user32=None):
    settings = get_settings_snapshot()
    if not settings.get("floating_price_snap_edge", True):
        return x, y
    try:
        import ctypes

        user32 = user32 or ctypes.windll.user32
        width, height = _floating_window_size()
        left, top, right, bottom = _get_work_area(user32)
        distances = [
            (abs(x - left), left + 8, y),
            (abs((right - width) - x), right - width - 8, y),
            (abs(y - top), x, top + 8),
            (abs((bottom - height) - y), x, bottom - height - 8),
        ]
        distance, snap_x, snap_y = min(distances, key=lambda item: item[0])
        if distance <= 28:
            return _clamp_floating_position(snap_x, snap_y, user32)
    except Exception:
        pass
    return x, y


def _resolve_floating_position(user32, width, height):
    settings = get_settings_snapshot()
    x = settings.get("floating_price_x")
    y = settings.get("floating_price_y")
    if not settings.get("floating_price_position_saved") or x is None or y is None:
        x, y = _default_floating_position(user32, width, height)
    return _clamp_floating_position(x, y, user32)


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
    behavior = snapshot.get("close_behavior", "ask")
    if snapshot.get("close_remembered") and behavior != "ask":
        return behavior

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
            if os.name != "nt":
                exit_app()
                return False

            snapshot = get_settings_snapshot()
            behavior = snapshot.get("close_behavior", "ask")
            if snapshot.get("close_remembered") and behavior != "ask":
                if behavior == "exit":
                    exit_app()
                else:
                    hide_main_window()
                return False

            if behavior == "exit":
                exit_app()
                return False

            if behavior == "minimize_to_tray":
                hide_main_window()
                return False

            socketio.emit("show_close_dialog", {
                "close_behavior": behavior,
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
        start_hidden = os.name == "nt" and startup_mode and get_settings_snapshot().get("startup_to_tray", True)
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
