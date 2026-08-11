import logging

from goldmonitor import platform as platform_core
from goldmonitor import platform_runtime as platform_runtime_core


class PlatformIntegrationRuntime:
    def __init__(
        self,
        state,
        *,
        credential_target_prefix,
        credential_service_name,
        macos_launch_agent_id,
        run_key_path,
        run_key_name,
        is_frozen,
        executable,
        argv0,
        os_name,
        sys_platform,
        home_dir,
        runner,
        logger=logging,
    ):
        self.state = state
        self.credential_target_prefix = credential_target_prefix
        self.credential_service_name = credential_service_name
        self.macos_launch_agent_id = macos_launch_agent_id
        self.run_key_path = run_key_path
        self.run_key_name = run_key_name
        self.is_frozen = is_frozen
        self.executable = executable
        self.argv0 = argv0
        self.os_name = os_name
        self.sys_platform = sys_platform
        self.home_dir = home_dir
        self.runner = runner
        self.logger = logger

    def current_executable(self):
        return platform_core.current_executable(
            self.is_frozen(),
            self.executable(),
            self.argv0(),
        )

    def credential_target_name(self, key):
        return platform_runtime_core.credential_target_name(
            key,
            self.credential_target_prefix,
        )

    def credential_store_override(self):
        store = self.state.credential_test_store
        return store if isinstance(store, dict) else None

    def read_windows_credential(self, key):
        return platform_runtime_core.read_windows_credential(
            key,
            os_name=self.os_name(),
            target_name=self.credential_target_name,
            logger=self.logger,
        )

    def write_windows_credential(self, key, value):
        return platform_runtime_core.write_windows_credential(
            key,
            value,
            os_name=self.os_name(),
            target_name=self.credential_target_name,
            logger=self.logger,
        )

    def delete_windows_credential(self, key):
        return platform_runtime_core.delete_windows_credential(
            key,
            os_name=self.os_name(),
            target_name=self.credential_target_name,
        )

    def run_macos_security(self, args):
        return platform_runtime_core.run_macos_security(
            args,
            runner=self.runner(),
        )

    def read_macos_credential(self, key):
        return platform_runtime_core.read_macos_credential(
            key,
            sys_platform=self.sys_platform(),
            service_name=self.credential_service_name,
            run_security=self.run_macos_security,
        )

    def write_macos_credential(self, key, value):
        return platform_runtime_core.write_macos_credential(
            key,
            value,
            sys_platform=self.sys_platform(),
            service_name=self.credential_service_name,
            run_security=self.run_macos_security,
            logger=self.logger,
        )

    def delete_macos_credential(self, key):
        return platform_runtime_core.delete_macos_credential(
            key,
            sys_platform=self.sys_platform(),
            service_name=self.credential_service_name,
            run_security=self.run_macos_security,
        )

    def read_credential_secret(
        self,
        key,
        *,
        read_windows=None,
        read_macos=None,
    ):
        return platform_runtime_core.read_credential_secret(
            key,
            store_override=self.credential_store_override,
            os_name=self.os_name(),
            sys_platform=self.sys_platform(),
            read_windows=read_windows or self.read_windows_credential,
            read_macos=read_macos or self.read_macos_credential,
        )

    def write_credential_secret(
        self,
        key,
        value,
        *,
        write_windows=None,
        delete_windows=None,
        write_macos=None,
        delete_macos=None,
    ):
        return platform_runtime_core.write_credential_secret(
            key,
            value,
            store_override=self.credential_store_override,
            os_name=self.os_name(),
            sys_platform=self.sys_platform(),
            write_windows=write_windows or self.write_windows_credential,
            delete_windows=delete_windows or self.delete_windows_credential,
            write_macos=write_macos or self.write_macos_credential,
            delete_macos=delete_macos or self.delete_macos_credential,
        )

    def credentials_required(self):
        return self.os_name() == "nt" or self.sys_platform() == "darwin"

    def startup_command(self):
        return platform_core.build_startup_command(self.current_executable())

    def macos_launch_agent_path(self):
        return platform_core.macos_launch_agent_path(
            self.home_dir(),
            self.macos_launch_agent_id,
        )

    def macos_startup_arguments(self):
        return platform_core.build_macos_startup_arguments(
            self.is_frozen(),
            self.executable(),
            self.argv0(),
        )

    def set_macos_startup_enabled(self, enabled):
        return platform_runtime_core.set_macos_startup_enabled(
            enabled,
            path=self.macos_launch_agent_path(),
            launch_agent_id=self.macos_launch_agent_id,
            startup_arguments=self.macos_startup_arguments(),
            current_executable=self.current_executable(),
            home_dir=self.home_dir(),
            build_payload=platform_core.build_macos_launch_agent_payload,
            runner=self.runner(),
        )

    def set_startup_enabled(
        self,
        enabled,
        *,
        set_macos_startup=None,
        startup_command=None,
    ):
        sys_platform = self.sys_platform()
        os_name = self.os_name()
        if sys_platform == "darwin":
            setter = set_macos_startup or self.set_macos_startup_enabled
            return setter(enabled)
        supported, error = platform_core.startup_support_result(
            enabled,
            sys_platform,
            os_name,
        )
        if supported is not None:
            return supported, error
        return platform_runtime_core.set_windows_startup_enabled(
            enabled,
            run_key_path=self.run_key_path,
            run_key_name=self.run_key_name,
            startup_command=(startup_command or self.startup_command)(),
        )
