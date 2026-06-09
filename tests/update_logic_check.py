import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


if app.compare_versions("1.2.0", "1.1.9") <= 0:
    raise SystemExit("1.2.0 must be newer than 1.1.9")

if app.compare_versions("1.0.0", "1.0") != 0:
    raise SystemExit("1.0.0 and 1.0 must compare as the same version")

if app.compare_versions("1.0.0", "1.0.1") >= 0:
    raise SystemExit("1.0.0 must be older than 1.0.1")

manifest = app.normalize_update_manifest({
    "version": "1.0.1",
    "url": "https://example.com/GoldMonitorSetup.exe",
    "notes": "test release",
    "sha256": "A" * 64,
})

if manifest["version"] != "1.0.1":
    raise SystemExit("manifest version was not normalized")

if manifest["url"] != "https://example.com/GoldMonitorSetup.exe":
    raise SystemExit("manifest download url was not normalized")

if manifest["sha256"] != "a" * 64:
    raise SystemExit("manifest sha256 must be lower-cased")

original_platform_key = app._platform_update_key
try:
    app._platform_update_key = lambda: "macos"
    platform_manifest = app.normalize_update_manifest({
        "version": "1.0.2",
        "url": "https://example.com/GoldMonitorSetup.exe",
        "sha256": "b" * 64,
        "downloads": {
            "windows": {
                "url": "https://example.com/GoldMonitorSetup.exe",
                "sha256": "b" * 64,
            },
            "macos": {
                "url": "https://example.com/GoldMonitor-macOS.dmg",
                "sha256": "c" * 64,
            },
        },
    })
finally:
    app._platform_update_key = original_platform_key

if platform_manifest["url"] != "https://example.com/GoldMonitor-macOS.dmg":
    raise SystemExit("macOS update manifest must select the DMG download")

if platform_manifest["sha256"] != "c" * 64:
    raise SystemExit("macOS update manifest must select the DMG sha256")

try:
    app.normalize_update_manifest({
        "version": "1.0.1",
        "url": "http://example.com/GoldMonitorSetup.exe",
        "sha256": "a" * 64,
    })
except ValueError:
    pass
else:
    raise SystemExit("manifest download url must require HTTPS")

try:
    app.normalize_update_manifest({
        "version": "1.0.1",
        "url": "https://example.com/GoldMonitorSetup.exe",
    })
except ValueError:
    pass
else:
    raise SystemExit("manifest must require installer sha256")

try:
    app.fetch_update_manifest("http://example.com/manifest.json")
except ValueError:
    pass
else:
    raise SystemExit("update manifest source must require HTTPS")

original_os_name = app.os.name
original_popen = app.subprocess.Popen
original_exit = app.os._exit
captured_popen = []
fake_installer_path = str(Path(__file__).resolve())
try:
    app.os.name = "nt"

    def fake_popen(args, **kwargs):
        captured_popen.append((args, kwargs))

    def fake_exit(code):
        raise SystemExit(f"updater must not force-exit the current process, got {code}")

    app.subprocess.Popen = fake_popen
    app.os._exit = fake_exit
    app.launch_update_installer(fake_installer_path)
finally:
    app.os.name = original_os_name
    app.subprocess.Popen = original_popen
    app.os._exit = original_exit

if not captured_popen:
    raise SystemExit("updater must launch the installer")

installer_args, popen_kwargs = captured_popen[0]
if "/SILENT" in installer_args:
    raise SystemExit("updater must show the installer instead of running silently")
if "/RESTARTAPPLICATIONS" in installer_args:
    raise SystemExit("updater must not rely on restart manager relaunches")
if "/CURRENTUSER" not in installer_args or "/CLOSEAPPLICATIONS" not in installer_args:
    raise SystemExit(f"updater must pass per-user close-app installer options, got: {installer_args}")
if not popen_kwargs.get("close_fds"):
    raise SystemExit("updater must detach installer file descriptors")

print("update logic checks passed.")
