import logging
import os
import plistlib
import subprocess


def credential_target_name(key, prefix):
    return f"{prefix}{key}"


def _load_windows_credential_types():
    import ctypes
    from ctypes import wintypes

    return ctypes, wintypes


def read_windows_credential(
    key,
    *,
    os_name,
    target_name,
    ctypes_loader=_load_windows_credential_types,
    logger=logging,
):
    if os_name != "nt":
        return ""
    try:
        ctypes, wintypes = ctypes_loader()

        class FileTime(ctypes.Structure):
            _fields_ = [
                ("dwLowDateTime", wintypes.DWORD),
                ("dwHighDateTime", wintypes.DWORD),
            ]

        class Credential(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD),
                ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR),
                ("LastWritten", FileTime),
                ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR),
                ("UserName", wintypes.LPWSTR),
            ]

        credential_ptr = ctypes.POINTER(Credential)()
        advapi32 = ctypes.windll.advapi32
        if not advapi32.CredReadW(target_name(key), 1, 0, ctypes.byref(credential_ptr)):
            return ""
        try:
            credential = credential_ptr.contents
            if not credential.CredentialBlob or not credential.CredentialBlobSize:
                return ""
            raw = ctypes.string_at(
                credential.CredentialBlob,
                credential.CredentialBlobSize,
            )
            return raw.decode("utf-16-le", errors="ignore")
        finally:
            advapi32.CredFree(credential_ptr)
    except Exception:
        logger.warning("读取系统凭据失败", exc_info=True)
        return ""


def write_windows_credential(
    key,
    value,
    *,
    os_name,
    target_name,
    ctypes_loader=_load_windows_credential_types,
    logger=logging,
):
    if os_name != "nt":
        return False
    try:
        ctypes, wintypes = ctypes_loader()

        class FileTime(ctypes.Structure):
            _fields_ = [
                ("dwLowDateTime", wintypes.DWORD),
                ("dwHighDateTime", wintypes.DWORD),
            ]

        class Credential(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD),
                ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR),
                ("LastWritten", FileTime),
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
        credential = Credential()
        credential.Flags = 0
        credential.Type = 1
        credential.TargetName = target_name(key)
        credential.Comment = "GoldMonitor 本机敏感配置"
        credential.CredentialBlobSize = len(raw)
        credential.CredentialBlob = ctypes.cast(
            blob,
            ctypes.POINTER(ctypes.c_ubyte),
        )
        credential.Persist = 2
        credential.AttributeCount = 0
        credential.Attributes = None
        credential.TargetAlias = None
        credential.UserName = key
        return bool(ctypes.windll.advapi32.CredWriteW(ctypes.byref(credential), 0))
    except Exception:
        logger.warning("写入系统凭据失败", exc_info=True)
        return False


def delete_windows_credential(
    key,
    *,
    os_name,
    target_name,
    ctypes_loader=_load_windows_credential_types,
):
    if os_name != "nt":
        return True
    try:
        ctypes, _wintypes = ctypes_loader()
        ctypes.windll.advapi32.CredDeleteW(target_name(key), 1, 0)
        return True
    except Exception:
        return True


def run_macos_security(args, *, runner=subprocess.run):
    try:
        completed = runner(
            ["security", *args],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return completed.returncode, completed.stdout, completed.stderr
    except Exception as exc:
        return 1, "", str(exc)


def read_macos_credential(
    key,
    *,
    sys_platform,
    service_name,
    run_security,
):
    if sys_platform != "darwin":
        return ""
    code, stdout, _stderr = run_security([
        "find-generic-password",
        "-s", service_name,
        "-a", key,
        "-w",
    ])
    return stdout.rstrip("\n") if code == 0 else ""


def write_macos_credential(
    key,
    value,
    *,
    sys_platform,
    service_name,
    run_security,
    logger=logging,
):
    if sys_platform != "darwin":
        return False
    code, _stdout, _stderr = run_security([
        "add-generic-password",
        "-s", service_name,
        "-a", key,
        "-w", str(value or ""),
        "-U",
    ])
    if code != 0:
        logger.warning("写入 macOS Keychain 失败")
    return code == 0


def delete_macos_credential(
    key,
    *,
    sys_platform,
    service_name,
    run_security,
):
    if sys_platform != "darwin":
        return True
    run_security([
        "delete-generic-password",
        "-s", service_name,
        "-a", key,
    ])
    return True


def read_credential_secret(
    key,
    *,
    store_override,
    os_name,
    sys_platform,
    read_windows,
    read_macos,
):
    store = store_override()
    if store is not None:
        return str(store.get(key) or "")
    if os_name == "nt":
        return read_windows(key)
    if sys_platform == "darwin":
        return read_macos(key)
    return ""


def write_credential_secret(
    key,
    value,
    *,
    store_override,
    os_name,
    sys_platform,
    write_windows,
    delete_windows,
    write_macos,
    delete_macos,
):
    store = store_override()
    if store is not None:
        if value:
            store[key] = str(value)
        else:
            store.pop(key, None)
        return True
    if os_name == "nt":
        return write_windows(key, value) if value else delete_windows(key)
    if sys_platform == "darwin":
        return write_macos(key, value) if value else delete_macos(key)
    return False


def set_macos_startup_enabled(
    enabled,
    *,
    path,
    launch_agent_id,
    startup_arguments,
    current_executable,
    home_dir,
    build_payload,
    runner=subprocess.run,
):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if enabled:
            payload = build_payload(
                launch_agent_id,
                startup_arguments,
                current_executable,
                home_dir,
            )
            with open(path, "wb") as file_handle:
                plistlib.dump(payload, file_handle, sort_keys=False)
            runner(
                ["launchctl", "unload", path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
                check=False,
            )
            runner(
                ["launchctl", "load", "-w", path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
                check=False,
            )
        else:
            runner(
                ["launchctl", "unload", path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
                check=False,
            )
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
        return True, None
    except Exception as exc:
        return False, str(exc)


def _load_winreg():
    import winreg

    return winreg


def set_windows_startup_enabled(
    enabled,
    *,
    run_key_path,
    run_key_name,
    startup_command,
    winreg_loader=_load_winreg,
):
    try:
        winreg = winreg_loader()
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            run_key_path,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            if enabled:
                winreg.SetValueEx(
                    key,
                    run_key_name,
                    0,
                    winreg.REG_SZ,
                    startup_command,
                )
            else:
                try:
                    winreg.DeleteValue(key, run_key_name)
                except FileNotFoundError:
                    pass
        return True, None
    except Exception as exc:
        return False, str(exc)
