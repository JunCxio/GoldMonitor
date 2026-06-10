import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app

WINDOWS_ASSET_URL = "https://github.com/JunCxio/GoldMonitor/releases/download/v1.0.1/GoldMonitorSetup.exe"
MACOS_ASSET_URL = "https://github.com/JunCxio/GoldMonitor/releases/download/v1.0.2/GoldMonitor-macOS.dmg"


if app.compare_versions("1.2.0", "1.1.9") <= 0:
    raise SystemExit("1.2.0 must be newer than 1.1.9")

if app.compare_versions("1.0.0", "1.0") != 0:
    raise SystemExit("1.0.0 and 1.0 must compare as the same version")

if app.compare_versions("1.0.0", "1.0.1") >= 0:
    raise SystemExit("1.0.0 must be older than 1.0.1")

manifest = app.normalize_update_manifest({
    "version": "1.0.1",
    "url": WINDOWS_ASSET_URL,
    "notes": "test release",
    "sha256": "A" * 64,
})

if manifest["version"] != "1.0.1":
    raise SystemExit("manifest version was not normalized")

if manifest["url"] != WINDOWS_ASSET_URL:
    raise SystemExit("manifest download url was not normalized")

if manifest["sha256"] != "a" * 64:
    raise SystemExit("manifest sha256 must be lower-cased")

original_platform_key = app._platform_update_key
try:
    app._platform_update_key = lambda: "macos"
    platform_manifest = app.normalize_update_manifest({
        "version": "1.0.2",
        "url": WINDOWS_ASSET_URL,
        "sha256": "b" * 64,
        "downloads": {
            "windows": {
                "url": WINDOWS_ASSET_URL,
                "sha256": "b" * 64,
            },
            "macos": {
                "url": MACOS_ASSET_URL,
                "sha256": "c" * 64,
            },
        },
    })
finally:
    app._platform_update_key = original_platform_key

if platform_manifest["url"] != MACOS_ASSET_URL:
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
        "sha256": "a" * 64,
    })
except ValueError:
    pass
else:
    raise SystemExit("manifest download url must require the official GitHub Release")

try:
    app.normalize_update_manifest({
        "version": "1.0.1",
        "url": WINDOWS_ASSET_URL,
    })
except ValueError:
    pass
else:
    raise SystemExit("manifest must require installer sha256")

try:
    app.fetch_update_manifest("http://github.com/JunCxio/GoldMonitor/releases/latest/download/version.json")
except ValueError:
    pass
else:
    raise SystemExit("update manifest source must require HTTPS")

try:
    app.fetch_update_manifest("https://example.com/version.json")
except ValueError:
    pass
else:
    raise SystemExit("update manifest source must require the official GitHub Release")

original_fetch_update_manifest = app.fetch_update_manifest
original_settings = dict(app.app_settings)
captured_manifest_urls = []
try:
    app.app_settings["update_manifest_url"] = "https://example.com/version.json"

    def fake_fetch_update_manifest(manifest_url=None):
        captured_manifest_urls.append(manifest_url)
        return {
            "version": "9.9.9",
            "url": WINDOWS_ASSET_URL,
            "notes": "",
            "sha256": "a" * 64,
        }

    app.fetch_update_manifest = fake_fetch_update_manifest
    update_status = app.get_update_status()
    install_status = app.get_update_status(expose_download=True)
finally:
    app.fetch_update_manifest = original_fetch_update_manifest
    app.app_settings.clear()
    app.app_settings.update(original_settings)

if captured_manifest_urls != [app.DEFAULT_UPDATE_MANIFEST_URL, app.DEFAULT_UPDATE_MANIFEST_URL]:
    raise SystemExit(f"update status must use the built-in manifest url, got: {captured_manifest_urls}")

if any(key in update_status for key in ("manifest_url", "url", "sha256")):
    raise SystemExit("frontend update status must not expose update source or installer metadata")

if install_status.get("url") != WINDOWS_ASSET_URL or install_status.get("sha256") != "a" * 64:
    raise SystemExit("install update status must keep backend-only installer metadata")

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
