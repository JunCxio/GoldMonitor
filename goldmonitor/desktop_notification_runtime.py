import logging
import os
import subprocess
import threading


def send_desktop_notification(
    title,
    body,
    *,
    sys_platform,
    base_dir,
    app_id,
    applescript_string,
    run_applescript,
    path_exists=os.path.exists,
    notify_loader=None,
):
    if sys_platform == "darwin":
        script = (
            "display notification "
            + applescript_string(body)
            + " with title "
            + applescript_string(title)
        )
        run_applescript(script, wait=False)
        return
    try:
        if notify_loader is None:
            from win11toast import notify
        else:
            notify = notify_loader()
        icon = os.path.join(base_dir, "static", "icon.ico")
        if not path_exists(icon):
            icon = os.path.join(base_dir, "static", "icon-64.png")
        notify(title, body, app_id=app_id, icon=icon)
    except Exception:
        pass


def show_alert_dialog(
    title,
    message,
    *,
    enabled,
    active_lock,
    get_active,
    set_active,
    sys_platform,
    os_name,
    applescript_string,
    run_applescript,
    thread_factory=threading.Thread,
    logger=logging,
):
    if not enabled:
        return False
    with active_lock:
        if get_active():
            logger.info("告警弹窗已存在，跳过新的系统消息框。")
            return False
        set_active(True)

    def show():
        try:
            if sys_platform == "darwin":
                script = (
                    "display alert "
                    + applescript_string(title)
                    + " message "
                    + applescript_string(message)
                    + ' as warning buttons {"知道了"} default button "知道了"'
                )
                run_applescript(script, wait=True, timeout=3600)
            elif os_name == "nt":
                import ctypes

                flags = 0x00000000 | 0x00000030 | 0x00040000 | 0x00010000
                ctypes.windll.user32.MessageBoxW(None, message, title, flags)
        except Exception:
            pass
        finally:
            with active_lock:
                set_active(False)

    thread_factory(target=show, daemon=True).start()
    return True


def play_system_alert_sound(
    level,
    *,
    enabled,
    sys_platform,
    path_exists=os.path.exists,
    popen=subprocess.Popen,
    run_applescript=None,
    winsound_loader=None,
):
    if not enabled:
        return False
    if sys_platform == "darwin":
        try:
            sound = "Basso" if level == "critical" else "Glass"
            path = f"/System/Library/Sounds/{sound}.aiff"
            if path_exists(path):
                popen(
                    ["afplay", path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                )
            elif run_applescript:
                run_applescript("beep", wait=False)
        except Exception:
            pass
        return True
    try:
        if winsound_loader is None:
            import winsound
        else:
            winsound = winsound_loader()
        sound = "SystemHand" if level == "critical" else "SystemExclamation"
        winsound.PlaySound(sound, winsound.SND_ALIAS | winsound.SND_ASYNC)
    except Exception:
        pass
    return True
