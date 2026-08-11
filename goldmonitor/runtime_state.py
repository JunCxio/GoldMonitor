import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ApplicationRuntimeState:
    lock: Any = field(default_factory=threading.RLock)
    settings_lock: Any = field(default_factory=threading.RLock)
    risk_history_lock: Any = field(default_factory=threading.RLock)
    last_update_status_lock: Any = field(default_factory=threading.RLock)
    last_export_status_lock: Any = field(default_factory=threading.RLock)
    daily_digest_lock: Any = field(default_factory=threading.Lock)
    review_notes_lock: Any = field(default_factory=threading.RLock)
    data_archive_lock: Any = field(default_factory=threading.Lock)
    data_archive_upload_lock: Any = field(default_factory=threading.Lock)
    price_refresh_lock: Any = field(default_factory=threading.Lock)
    risk_analysis_lock: Any = field(default_factory=threading.Lock)
    alert_dialog_lock: Any = field(default_factory=threading.Lock)
    floating_window_ready: Any = field(default_factory=threading.Event)
    floating_lock: Any = field(default_factory=threading.RLock)
    taskbar_window_ready: Any = field(default_factory=threading.Event)
    taskbar_lock: Any = field(default_factory=threading.RLock)

    price_usd: Optional[float] = None
    price_rmb: Optional[float] = None
    previous_usd: Optional[float] = None
    previous_rmb: Optional[float] = None
    usdcny_rate: Optional[float] = None
    usdcny_rate_source: str = ""
    usdcny_rate_time: Optional[str] = None
    usdcny_rate_cached: bool = False
    usdcny_rate_error: str = ""
    gold_price_source: str = ""
    gold_price_time: Optional[str] = None
    gold_price_cached: bool = False
    gold_price_error: str = ""
    price_history: List[Dict[str, Any]] = field(default_factory=list)
    price_archive: List[Dict[str, Any]] = field(default_factory=list)
    klines_5min: List[Dict[str, Any]] = field(default_factory=list)
    last_price_history_save_at: float = 0.0
    last_fetch_ok: bool = False
    last_fetch_error: str = ""
    last_fetch_time: Optional[str] = None

    today_date: Optional[str] = None
    today_open_usd: Optional[float] = None
    today_high_usd: Optional[float] = None
    today_low_usd: Optional[float] = None
    today_open_rmb: Optional[float] = None
    today_high_rmb: Optional[float] = None
    today_low_rmb: Optional[float] = None

    thresholds: Dict[str, Optional[float]] = field(default_factory=dict)
    volatility_config: Dict[str, Any] = field(
        default_factory=lambda: {"percent": None, "minutes": 10, "enabled": False}
    )
    alert_profiles: List[Dict[str, Any]] = field(default_factory=list)
    alert_rules: List[Dict[str, Any]] = field(default_factory=list)
    alert_rule_migration_status: Dict[str, Any] = field(default_factory=dict)
    alert_rules_load_error: str = ""
    alert_rules_invalid_count: int = 0
    last_volatility_check: Any = None
    watch_targets: List[Dict[str, Any]] = field(default_factory=list)
    review_notes: List[Dict[str, Any]] = field(default_factory=list)
    portfolio_positions: List[Dict[str, Any]] = field(default_factory=list)
    portfolio_transactions: List[Dict[str, Any]] = field(default_factory=list)
    portfolio_import_backup: Dict[str, Any] = field(default_factory=dict)
    portfolio_alerts: List[Dict[str, Any]] = field(default_factory=list)
    alerted_flags: Dict[str, bool] = field(default_factory=dict)
    alert_cooldown_state: Dict[str, Any] = field(default_factory=dict)
    alert_log: List[Dict[str, Any]] = field(default_factory=list)

    news_items: List[Dict[str, Any]] = field(default_factory=list)
    news_last_updated: Optional[str] = None
    news_last_error: str = ""
    risk_analysis_history: List[Dict[str, Any]] = field(default_factory=list)
    app_settings: Dict[str, Any] = field(default_factory=dict)
    last_settings_error: Optional[str] = None
    server_port: int = 5000
    risk_analysis_last_started: float = 0.0
    source_health: Dict[str, Any] = field(default_factory=dict)
    source_price_samples: Dict[str, Any] = field(default_factory=dict)
    source_comparison_state: Dict[str, Any] = field(default_factory=dict)
    last_source_comparison_probe_at: float = 0.0
    last_update_status: Dict[str, Any] = field(default_factory=dict)
    last_export_status: Dict[str, Any] = field(default_factory=dict)
    credential_test_store: Any = None
    alert_dialog_active: bool = False
    daily_digest_scheduler_started: bool = False
    data_archive_uploads: Dict[str, Any] = field(default_factory=dict)
    market_runtime_instance: Any = None
    portfolio_runtime_instance: Any = None
    alert_runtime_instance: Any = None
    config_restore_service: Any = None
    data_archive_runtime_instance: Any = None
    news_runtime_instance: Any = None
    diagnostics_runtime_instance: Any = None
    alert_notification_runtime_instance: Any = None
    daily_digest_runtime_instance: Any = None
    floating_controller_instance: Any = None
    taskbar_controller_instance: Any = None

    window_instance: Any = None
    tray_icon: Any = None
    macos_status_item: Any = None
    macos_status_delegate: Any = None
    macos_status_menu: Any = None
    macos_status_menu_items: Dict[str, Any] = field(default_factory=dict)
    window_hwnd: Any = None
    last_desktop_title: str = ""
    desktop_runtime_active: bool = False
    floating_hwnd: Any = None
    floating_thread_started: bool = False
    floating_primary_text: str = "黄金 --"
    floating_secondary_text: str = "等待行情数据"
    floating_status_text: str = "等待更新"
    floating_trend_state: str = "neutral"
    floating_source_state: str = "waiting"
    floating_drag_state: Any = None
    floating_positioned: bool = False
    taskbar_hwnd: Any = None
    taskbar_owner_hwnd: Any = None
    taskbar_thread_started: bool = False
    taskbar_price_text: str = "金价 --"
    taskbar_price_value_text: str = "--"
    taskbar_price_change_text: str = ""
    taskbar_trend_state: str = "neutral"
    taskbar_source_state: str = "waiting"
    taskbar_target_state: Dict[str, Any] = field(default_factory=dict)
    taskbar_restart_count: int = 0
    taskbar_layout_state: Dict[str, Any] = field(default_factory=dict)
    background_fetch_started: bool = False
    news_fetch_started: bool = False


def create_runtime_state(
    *,
    default_port: int,
    app_name: str,
    threshold_modes,
    threshold_types,
    source_health,
) -> ApplicationRuntimeState:
    thresholds = {
        f"{threshold_type}_{mode}": None
        for mode in threshold_modes
        for threshold_type in threshold_types
    }
    return ApplicationRuntimeState(
        server_port=default_port,
        last_desktop_title=app_name,
        thresholds=thresholds,
        source_health=source_health,
    )
