import logging

from goldmonitor import desktop_ui as desktop_ui_core
from goldmonitor import floating_runtime as floating_runtime_core


class FloatingPriceController:
    TOGGLE_SETTING_KEYS = {
        "floating_price_lock_position",
        "floating_price_hide_on_fullscreen",
        "floating_price_always_on_top",
    }

    def __init__(
        self,
        *,
        runtime,
        default_settings,
        presets,
        os_name,
        sys_platform,
        get_settings,
        save_settings,
        public_settings_snapshot,
        emit,
        show_main_window,
        fetch_price_once,
        refresh_macos_status_item,
        start_background_task,
        logger=logging,
    ):
        self.runtime = runtime
        self.default_settings = default_settings
        self.presets = presets
        self.os_name = os_name
        self.sys_platform = sys_platform
        self.get_settings = get_settings
        self.save_settings = save_settings
        self.public_settings_snapshot = public_settings_snapshot
        self.emit = emit
        self.show_main_window = show_main_window
        self.fetch_price_once = fetch_price_once
        self.refresh_macos_status_item = refresh_macos_status_item
        self.start_background_task = start_background_task
        self.logger = logger

    def format_price_text(self, rmb=None, usd=None, pct=None):
        settings = self.get_settings()
        if rmb is None and usd is None:
            with self.runtime.lock:
                rmb = self.runtime.price_rmb
                usd = self.runtime.price_usd
                state = self._market_status_state()
        else:
            state = self._market_status_state()

        return desktop_ui_core.format_floating_price_text(
            settings,
            rmb=rmb,
            usd=usd,
            pct=pct,
            **state,
        )

    def _market_status_state(self):
        return {
            "fetch_time": self.runtime.last_fetch_time,
            "source_name": self.runtime.gold_price_source or "行情源",
            "gold_cached": bool(self.runtime.gold_price_cached),
            "rate_cached": bool(self.runtime.usdcny_rate_cached),
            "fetch_ok": bool(self.runtime.last_fetch_ok),
            "fetch_error": (
                self.runtime.last_fetch_error
                or self.runtime.gold_price_error
                or self.runtime.usdcny_rate_error
            ),
        }

    def is_available(self):
        return self.runtime.desktop_runtime_active and self.os_name() == "nt"

    def window_metrics(self):
        return desktop_ui_core.floating_window_metrics(
            self.get_settings(),
            default_preset=self.default_settings["floating_price_preset"],
            presets=self.presets,
        )

    @staticmethod
    def floating_rect(rect_config, width, height):
        return desktop_ui_core.floating_rect(rect_config, width, height)

    def window_size(self):
        return desktop_ui_core.floating_window_size(
            self.get_settings(),
            default_preset=self.default_settings["floating_price_preset"],
            presets=self.presets,
        )

    def window_radius(self):
        return desktop_ui_core.floating_window_radius(
            self.get_settings(),
            default_preset=self.default_settings["floating_price_preset"],
            presets=self.presets,
        )

    def apply_window_corner_preference(self, hwnd):
        return floating_runtime_core.apply_window_corner_preference(
            hwnd,
            os_name=self.os_name(),
        )

    @staticmethod
    def get_work_area(user32):
        return floating_runtime_core.get_work_area(user32)

    def clamp_position(self, x, y, user32=None):
        try:
            import ctypes

            user32 = user32 or ctypes.windll.user32
            return floating_runtime_core.clamp_window_position(
                x,
                y,
                window_size=self.window_size,
                work_area=lambda: self.get_work_area(user32),
            )
        except Exception:
            return int(x), int(y)

    def default_position(self, user32, width, height):
        return desktop_ui_core.default_floating_position(
            self.get_work_area(user32),
            width,
            height,
        )

    def snap_position(self, x, y, user32=None):
        try:
            import ctypes

            user32 = user32 or ctypes.windll.user32
            return floating_runtime_core.snap_window_position(
                x,
                y,
                settings=self.get_settings,
                window_size=self.window_size,
                work_area=lambda: self.get_work_area(user32),
            )
        except Exception:
            return x, y

    def resolve_position(self, user32, width, height):
        return floating_runtime_core.resolve_window_position(
            settings=self.get_settings,
            width=width,
            height=height,
            work_area=lambda: self.get_work_area(user32),
        )

    def save_position(self, x, y):
        return floating_runtime_core.save_window_position(
            x,
            y,
            clamp_position=lambda px, py: self.clamp_position(px, py),
            snap_position=lambda px, py: self.snap_position(px, py),
            get_settings=self.get_settings,
            save_settings=self.save_settings,
            emit_settings_updated=lambda: self.emit(
                "settings_updated",
                self.public_settings_snapshot(),
            ),
            logger=self.logger,
        )

    def position_window(self, hwnd, user32=None, x=None, y=None):
        if not hwnd:
            return None
        try:
            import ctypes

            user32 = user32 or ctypes.windll.user32
            return floating_runtime_core.position_window(
                hwnd,
                user32=user32,
                x=x,
                y=y,
                window_size=self.window_size,
                resolve_position=self.resolve_position,
                clamp_position=self.clamp_position,
                get_settings=self.get_settings,
                set_positioned=self.set_positioned,
                logger=self.logger,
            )
        except Exception:
            self.logger.warning("桌面金价悬浮条定位失败", exc_info=True)
            return None

    def invalidate_window(self):
        return floating_runtime_core.invalidate_window(
            self.runtime.floating_hwnd,
            os_name=self.os_name(),
        )

    def set_window_visible(self, visible):
        return floating_runtime_core.set_window_visible(
            visible,
            hwnd=self.runtime.floating_hwnd,
            os_name=self.os_name(),
            get_positioned=lambda: self.runtime.floating_positioned,
            position_window=self.position_window,
            apply_opacity=self.apply_opacity,
            invalidate_window=self.invalidate_window,
            should_suppress=self.should_hide_for_fullscreen,
        )

    def should_hide_for_fullscreen(self, hwnd, user32):
        return floating_runtime_core.should_hide_for_fullscreen(
            hwnd,
            user32=user32,
            get_settings=self.get_settings,
        )

    def sync_visibility(self):
        settings = self.get_settings()
        return self.set_window_visible(
            bool(settings.get("floating_price_enabled", True))
        )

    def set_enabled(self, enabled):
        return floating_runtime_core.set_enabled(
            enabled,
            get_settings=self.get_settings,
            save_settings=self.save_settings,
            set_window_visible=self.set_window_visible,
            apply_settings=self.apply_settings,
            public_settings_snapshot=self.public_settings_snapshot,
            emit=self.emit,
            logger=self.logger,
        )

    def apply_opacity(self, hwnd=None, user32=None):
        return floating_runtime_core.apply_window_opacity(
            hwnd or self.runtime.floating_hwnd,
            os_name=self.os_name(),
            get_settings=self.get_settings,
            user32=user32,
        )

    def refresh_price(self):
        self.start_background_task(self.fetch_price_once)

    def open_risk_analysis(self, source="floating_price"):
        self.show_main_window()
        self.emit("open_risk_analysis", {"run": True, "source": source})

    def toggle_setting(self, key):
        if key not in self.TOGGLE_SETTING_KEYS:
            raise ValueError(f"unsupported floating setting: {key}")
        snapshot = self.get_settings()
        snapshot[key] = not bool(snapshot.get(key, False))
        saved = self.save_settings(snapshot) or snapshot
        self.apply_settings(saved)
        self.emit("settings_updated", self.public_settings_snapshot(saved))
        return bool(saved.get(key))

    def reset_position(self):
        snapshot = self.get_settings()
        snapshot["floating_price_position_saved"] = False
        snapshot["floating_price_x"] = None
        snapshot["floating_price_y"] = None
        saved = self.save_settings(snapshot) or snapshot
        self.runtime.floating_positioned = False
        if self.runtime.floating_hwnd:
            self.position_window(self.runtime.floating_hwnd)
            self.sync_visibility()
        self.emit("settings_updated", self.public_settings_snapshot(saved))
        return None

    @staticmethod
    def get_lparam_point(lparam):
        return floating_runtime_core.get_lparam_point(lparam)

    def text_state(self):
        with self.runtime.floating_lock:
            return {
                "primary": self.runtime.floating_primary_text,
                "secondary": self.runtime.floating_secondary_text,
                "status": self.runtime.floating_status_text,
                "trend_state": self.runtime.floating_trend_state,
                "source_state": self.runtime.floating_source_state,
            }

    def run_window(self):
        return floating_runtime_core.run_floating_price_window(
            window_size=self.window_size,
            window_metrics=self.window_metrics,
            floating_rect=self.floating_rect,
            get_text_state=self.text_state,
            clamp_position=self.clamp_position,
            position_window=self.position_window,
            save_position=self.save_position,
            resolve_position=self.resolve_position,
            set_window_handle=self.set_window_handle,
            apply_corner_preference=self.apply_window_corner_preference,
            apply_opacity=self.apply_opacity,
            set_window_visible=self.set_window_visible,
            window_enabled=lambda: self.get_settings().get(
                "floating_price_enabled",
                True,
            ),
            set_ready=self.runtime.floating_window_ready.set,
            show_main_window=self.show_main_window,
            set_enabled=self.set_enabled,
            refresh_price=self.refresh_price,
            open_risk_analysis=self.open_risk_analysis,
            get_drag_state=lambda: self.runtime.floating_drag_state,
            set_drag_state=self.set_drag_state,
            is_topmost=lambda: desktop_ui_core.floating_window_z_order(
                self.get_settings()
            ) == "topmost",
            get_settings=self.get_settings,
            toggle_setting=self.toggle_setting,
            reset_position=self.reset_position,
            is_position_locked=lambda: bool(
                self.get_settings().get("floating_price_lock_position", False)
            ),
            sync_visibility=self.sync_visibility,
            logger=self.logger,
        )

    def start_window(self, worker=None, available=None):
        available = available or self.is_available
        if not available():
            return None
        with self.runtime.floating_lock:
            if self.runtime.floating_thread_started:
                return None
            self.runtime.floating_thread_started = True
            self.start_background_task(worker or self.run_window)
        return None

    def apply_settings(self, settings=None, worker=None):
        if self.sys_platform() == "darwin":
            self.refresh_macos_status_item()
            return None
        if not self.is_available():
            return None
        settings = settings or self.get_settings()
        enabled = bool(settings.get("floating_price_enabled", True))
        if enabled:
            self.start_window(worker=worker)
            if self.runtime.floating_hwnd:
                self.position_window(self.runtime.floating_hwnd)
                self.apply_opacity(self.runtime.floating_hwnd)
                self.invalidate_window()
            self.set_window_visible(True)
        else:
            self.set_window_visible(False)
        return None

    def update_price(self, rmb=None, usd=None, pct=None, worker=None):
        primary, secondary, status, trend_state, source_state = self.format_price_text(
            rmb,
            usd,
            pct,
        )
        with self.runtime.floating_lock:
            self.runtime.floating_primary_text = primary
            self.runtime.floating_secondary_text = secondary
            self.runtime.floating_status_text = status
            self.runtime.floating_trend_state = trend_state
            self.runtime.floating_source_state = source_state

        if not self.is_available():
            return None

        settings = self.get_settings()
        if settings.get("floating_price_enabled", True):
            self.start_window(worker=worker)
            if not self.runtime.floating_hwnd:
                self.runtime.floating_window_ready.wait(0.5)
            self.set_window_visible(True)
            self.invalidate_window()
        else:
            self.set_window_visible(False)
        return None

    def set_window_handle(self, value):
        self.runtime.floating_hwnd = value

    def set_drag_state(self, value):
        self.runtime.floating_drag_state = value

    def set_positioned(self, value):
        self.runtime.floating_positioned = bool(value)
