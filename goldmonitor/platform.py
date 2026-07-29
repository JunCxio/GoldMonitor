import os
import posixpath
import sys


def current_executable(frozen=None, executable=None, argv0=None):
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    executable = sys.executable if executable is None else executable
    argv0 = sys.argv[0] if argv0 is None else argv0
    if frozen:
        return executable
    return os.path.abspath(argv0)


def runtime_platform(sys_platform=None, os_name=None):
    sys_platform = sys.platform if sys_platform is None else sys_platform
    os_name = os.name if os_name is None else os_name
    if sys_platform == "darwin":
        return "macos"
    if os_name == "nt":
        return "windows"
    return "other"


def platform_capabilities(platform=None):
    platform = platform or runtime_platform()
    return {
        "platform": platform,
        "has_system_tray": platform == "windows",
        "has_menu_bar_status": platform == "macos",
        "floating_price_mode": "floating_window" if platform == "windows" else ("menu_bar" if platform == "macos" else "none"),
        "has_taskbar_price": platform == "windows",
        "can_start_hidden": platform in {"windows", "macos"},
        "can_system_notify": platform in {"windows", "macos"},
        "can_system_alert_dialog": platform in {"windows", "macos"},
        "can_system_sound": platform in {"windows", "macos"},
    }


def build_startup_command(executable):
    return f'"{executable}" --startup'


def macos_launch_agent_path(home_dir, launch_agent_id):
    return posixpath.join(home_dir, "Library", "LaunchAgents", f"{launch_agent_id}.plist")


def build_macos_startup_arguments(frozen=None, executable=None, argv0=None):
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    executable = sys.executable if executable is None else executable
    argv0 = sys.argv[0] if argv0 is None else argv0
    if frozen:
        return [executable, "--startup"]
    return [executable, posixpath.abspath(argv0), "--startup"]


def build_macos_launch_agent_payload(launch_agent_id, program_arguments, executable, home_dir):
    working_directory = posixpath.dirname(executable) or home_dir
    return {
        "Label": launch_agent_id,
        "ProgramArguments": list(program_arguments),
        "RunAtLoad": True,
        "KeepAlive": False,
        "WorkingDirectory": working_directory,
    }


def startup_support_result(enabled, sys_platform=None, os_name=None):
    platform = runtime_platform(sys_platform=sys_platform, os_name=os_name)
    if platform in {"macos", "windows"}:
        return None, None
    return (True, None) if not enabled else (False, "当前平台不支持开机自启动")


def close_behavior_decision(settings, platform=None):
    settings = settings if isinstance(settings, dict) else {}
    behavior = settings.get("close_behavior", "ask")
    remembered = bool(settings.get("close_remembered"))
    if remembered and behavior != "ask":
        return behavior
    if behavior in {"exit", "minimize_to_tray"}:
        return behavior
    if platform == "other":
        return "exit"
    return "ask"
