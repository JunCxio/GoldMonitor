import logging

from goldmonitor import desktop_ui as desktop_ui_core
from goldmonitor import floating_runtime as floating_runtime_core
from goldmonitor import taskbar_runtime as taskbar_runtime_core


class TaskbarPriceController:
    WINDOWS_MODES = {"floating", "taskbar", "both"}

    def __init__(
        self,
        *,
        runtime,
        os_name,
        get_settings,
        save_settings,
        public_settings_snapshot,
        emit,
        show_main_window,
        fetch_price_once,
        start_background_task,
        apply_display_settings=None,
        logger=logging,
    ):
        self.runtime = runtime
        self.os_name = os_name
        self.get_settings = get_settings
        self.save_settings = save_settings
        self.public_settings_snapshot = public_settings_snapshot
        self.emit = emit
        self.show_main_window = show_main_window
        self.fetch_price_once = fetch_price_once
        self.start_background_task = start_background_task
        self.apply_display_settings = apply_display_settings or self.apply_settings
        self.logger = logger

    def is_available(self):
        return self.runtime.desktop_runtime_active and self.os_name() == "nt"

    @staticmethod
    def mode_enabled(settings):
        return settings.get("floating_price_windows_mode", "floating") in {
            "taskbar",
            "both",
        }

    def text_state(self):
        with self.runtime.taskbar_lock:
            return {
                "text": self.runtime.taskbar_price_text,
                "price": self.runtime.taskbar_price_value_text,
                "change": self.runtime.taskbar_price_change_text,
                "trend_state": self.runtime.taskbar_trend_state,
                "source_state": self.runtime.taskbar_source_state,
            }

    def update_text(self, rmb=None, usd=None, pct=None):
        settings = self.get_settings()
        if rmb is None and usd is None:
            with self.runtime.lock:
                rmb = self.runtime.price_rmb
                usd = self.runtime.price_usd
        price_state = desktop_ui_core.format_taskbar_price_state(
            settings,
            rmb=rmb,
            usd=usd,
            pct=pct,
        )
        if not self.runtime.last_fetch_ok and (
            self.runtime.last_fetch_error
            or self.runtime.gold_price_error
            or self.runtime.usdcny_rate_error
        ):
            source_state = "error"
        elif self.runtime.gold_price_cached or self.runtime.usdcny_rate_cached:
            source_state = "cached"
        elif self.runtime.last_fetch_ok:
            source_state = "live"
        else:
            source_state = "waiting"
        with self.runtime.taskbar_lock:
            self.runtime.taskbar_price_text = price_state["text"]
            self.runtime.taskbar_price_value_text = price_state["price"]
            self.runtime.taskbar_price_change_text = price_state["change"]
            self.runtime.taskbar_trend_state = price_state["trend_state"]
            self.runtime.taskbar_source_state = source_state
        return price_state["text"]

    def set_layout_state(self, value):
        with self.runtime.taskbar_lock:
            target = dict(self.runtime.taskbar_target_state or {})
            target_state = {
                "taskbar_kind": target.get("kind"),
                "taskbar_index": target.get("index"),
                "taskbar_count": target.get("count", 0),
                "taskbar_class_name": target.get("class_name"),
            }
            self.runtime.taskbar_layout_state = {
                **{key: item for key, item in target_state.items() if item is not None},
                **dict(value or {}),
                "restart_count": self.runtime.taskbar_restart_count,
            }

    def layout_state(self):
        with self.runtime.taskbar_lock:
            return dict(self.runtime.taskbar_layout_state)

    def layout(self):
        try:
            import ctypes

            _target, layout, state = taskbar_runtime_core.select_taskbar_layout(
                user32=ctypes.windll.user32,
                shell32=ctypes.windll.shell32,
                text_state=self.text_state(),
            )
            return layout, state
        except Exception:
            return None, {"visible": False, "reason": "layout_error"}

    @staticmethod
    def should_hide_for_fullscreen(hwnd, user32):
        return floating_runtime_core.is_foreground_window_fullscreen(
            hwnd,
            user32=user32,
        )

    def invalidate_window(self):
        with self.runtime.taskbar_lock:
            hwnd = self.runtime.taskbar_hwnd
        return taskbar_runtime_core.invalidate_window(
            hwnd,
            os_name=self.os_name(),
        )

    def set_window_visible(self, visible):
        return taskbar_runtime_core.set_taskbar_window_visible(
            visible,
            hwnd=self.runtime.taskbar_hwnd,
            os_name=self.os_name(),
            layout_provider=self.layout,
            should_suppress=self.should_hide_for_fullscreen,
            set_layout_state=self.set_layout_state,
            get_layout_state=self.layout_state,
            invalidate=self.invalidate_window,
        )

    def sync_visibility(self):
        settings = self.get_settings()
        visible = bool(settings.get("floating_price_enabled", True)) and self.mode_enabled(
            settings
        )
        return self.set_window_visible(visible)

    def set_enabled(self, enabled):
        return floating_runtime_core.set_enabled(
            enabled,
            get_settings=self.get_settings,
            save_settings=self.save_settings,
            set_window_visible=self.set_window_visible,
            apply_settings=self.apply_display_settings,
            public_settings_snapshot=self.public_settings_snapshot,
            emit=self.emit,
            logger=self.logger,
        )

    def set_windows_mode(self, mode):
        if mode not in self.WINDOWS_MODES:
            raise ValueError(f"unsupported Windows price mode: {mode}")
        snapshot = self.get_settings()
        if snapshot.get("floating_price_windows_mode", "floating") == mode:
            self.apply_display_settings(snapshot)
            return mode
        snapshot["floating_price_windows_mode"] = mode
        saved = self.save_settings(snapshot) or snapshot
        self.apply_display_settings(saved)
        self.emit("settings_updated", self.public_settings_snapshot(saved))
        return saved.get("floating_price_windows_mode", mode)

    def refresh_price(self):
        self.start_background_task(self.fetch_price_once)

    def open_risk_analysis(self, source="taskbar_price"):
        self.show_main_window()
        self.emit("open_risk_analysis", {"run": True, "source": source})

    def run_window(self):
        try:
            return taskbar_runtime_core.run_taskbar_price_window(
                set_window_handle=self.set_window_handle,
                set_taskbar_target=self.set_taskbar_target,
                set_lifecycle_state=self.set_lifecycle_state,
                set_ready=self.runtime.taskbar_window_ready.set,
                clear_ready=self.runtime.taskbar_window_ready.clear,
                get_text_state=self.text_state,
                window_enabled=lambda: bool(
                    self.get_settings().get("floating_price_enabled", True)
                )
                and self.mode_enabled(self.get_settings()),
                sync_visibility=self.sync_visibility,
                show_main_window=self.show_main_window,
                set_enabled=self.set_enabled,
                refresh_price=self.refresh_price,
                open_risk_analysis=self.open_risk_analysis,
                get_settings=self.get_settings,
                set_windows_mode=self.set_windows_mode,
                logger=self.logger,
            )
        finally:
            with self.runtime.taskbar_lock:
                self.runtime.taskbar_hwnd = None
                self.runtime.taskbar_owner_hwnd = None
                self.runtime.taskbar_target_state = {}
                self.runtime.taskbar_thread_started = False
                self.runtime.taskbar_window_ready.clear()

    def start_window(self, worker=None):
        if not self.is_available():
            return None
        with self.runtime.taskbar_lock:
            if self.runtime.taskbar_thread_started:
                return None
            self.runtime.taskbar_window_ready.clear()
            self.runtime.taskbar_thread_started = True
            self.start_background_task(worker or self.run_window)
        return None

    def apply_settings(self, settings=None, worker=None):
        if not self.is_available():
            return None
        settings = settings or self.get_settings()
        visible = bool(settings.get("floating_price_enabled", True)) and self.mode_enabled(
            settings
        )
        if visible:
            self.start_window(worker=worker)
            if not self.runtime.taskbar_hwnd:
                self.runtime.taskbar_window_ready.wait(0.5)
            self.set_window_visible(True)
            self.invalidate_window()
        else:
            self.set_window_visible(False)
        return None

    def update_price(self, rmb=None, usd=None, pct=None, worker=None):
        self.update_text(rmb, usd, pct)
        if not self.is_available():
            return None
        settings = self.get_settings()
        if bool(settings.get("floating_price_enabled", True)) and self.mode_enabled(settings):
            self.start_window(worker=worker)
            if not self.runtime.taskbar_hwnd:
                self.runtime.taskbar_window_ready.wait(0.5)
            self.set_window_visible(True)
            self.invalidate_window()
        else:
            self.set_window_visible(False)
        return None

    def set_window_handle(self, value):
        with self.runtime.taskbar_lock:
            self.runtime.taskbar_hwnd = value

    def set_taskbar_target(self, target):
        target = dict(target or {})
        with self.runtime.taskbar_lock:
            self.runtime.taskbar_owner_hwnd = target.get("hwnd")
            self.runtime.taskbar_target_state = {
                key: target[key]
                for key in ("kind", "index", "count", "class_name")
                if key in target
            }

    def taskbar_target(self):
        with self.runtime.taskbar_lock:
            if not self.runtime.taskbar_owner_hwnd:
                return None
            return {
                "hwnd": self.runtime.taskbar_owner_hwnd,
                **dict(self.runtime.taskbar_target_state or {}),
            }

    def set_lifecycle_state(self, reason, **details):
        with self.runtime.taskbar_lock:
            increment_restart = bool(details.pop("increment_restart", False))
            if increment_restart:
                self.runtime.taskbar_restart_count += 1
            if "restart_count" in details:
                self.runtime.taskbar_restart_count = max(
                    0,
                    int(details["restart_count"]),
                )
            target = dict(self.runtime.taskbar_target_state or {})
            target_state = {
                "taskbar_kind": target.get("kind"),
                "taskbar_index": target.get("index"),
                "taskbar_count": target.get("count", 0),
                "taskbar_class_name": target.get("class_name"),
            }
            self.runtime.taskbar_layout_state = {
                **{key: item for key, item in target_state.items() if item is not None},
                **details,
                "visible": False,
                "reason": reason,
                "restart_count": self.runtime.taskbar_restart_count,
            }
