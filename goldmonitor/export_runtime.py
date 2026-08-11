from datetime import datetime

from goldmonitor import operations_runtime as operations_runtime_core


class ExportRuntime:
    def __init__(
        self,
        state,
        *,
        get_settings,
        default_export_dir,
        check_actions,
        home_dir,
        writer,
        now_factory=datetime.now,
    ):
        self.state = state
        self.get_settings = get_settings
        self.default_export_dir = default_export_dir
        self.check_actions = check_actions
        self.home_dir = home_dir
        self.writer = writer
        self.now_factory = now_factory

    def resolve_export_dir(self, settings=None):
        return operations_runtime_core.resolve_export_dir(
            self.get_settings() if settings is None else settings,
            self.default_export_dir(),
        )

    def probe_export_dir_writable(self, export_dir):
        return operations_runtime_core.probe_export_dir_writable(export_dir)

    def build_export_dir_check(self, settings=None, probe_writer=None):
        return operations_runtime_core.build_export_dir_check(
            self.resolve_export_dir(settings),
            actions=self.check_actions(),
            probe_writer=probe_writer or self.probe_export_dir_writable,
        )

    def export_dir_dialog_initial_dir(self, settings=None):
        return operations_runtime_core.export_dir_dialog_initial_dir(
            self.resolve_export_dir(settings),
            home_dir=self.home_dir(),
        )

    def normalize_export_dir_selection(self, selection):
        return operations_runtime_core.normalize_export_dir_selection(selection)

    def build_export_dir_picker_payload(self, dialog, settings=None):
        return operations_runtime_core.build_export_dir_picker_payload(
            dialog,
            self.export_dir_dialog_initial_dir(settings),
        )

    def reset_last_export_status(self):
        with self.state.last_export_status_lock:
            self.state.last_export_status = {}

    def get_last_export_status(self):
        with self.state.last_export_status_lock:
            status = self.state.last_export_status
            return dict(status) if isinstance(status, dict) else {}

    def set_last_export_status(self, status):
        with self.state.last_export_status_lock:
            self.state.last_export_status = dict(status)

    def export_failure_category(self, exc):
        return operations_runtime_core.export_failure_category(exc)

    def export_failure_message(self, category, export_dir):
        return operations_runtime_core.export_failure_message(category, export_dir)

    def build_export_failure_status(self, filename, export_dir, exc):
        return operations_runtime_core.build_export_failure_status(
            filename,
            export_dir,
            exc,
            now_factory=self.now_factory,
        )

    def build_export_status_snapshot(self, settings=None):
        return operations_runtime_core.build_export_status_snapshot(
            self.build_export_dir_check(settings),
            self.get_last_export_status(),
        )

    def build_export_error_payload(self, default_message):
        return operations_runtime_core.build_export_error_payload(
            default_message,
            self.get_last_export_status(),
            self.build_export_dir_check(),
        )

    def build_open_exports_folder_error_payload(self, export_dir, exc):
        return operations_runtime_core.build_open_exports_folder_error_payload(
            export_dir,
            exc,
            directory_status=self.build_export_dir_check(),
            now_factory=self.now_factory,
        )

    def save_export_file(self, filename, content):
        return operations_runtime_core.save_export_file(
            filename,
            content,
            export_dir=self.resolve_export_dir(),
            writer=self.writer,
            set_status=self.set_last_export_status,
            now_factory=self.now_factory,
        )
