from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


WINDOWS_ASSET_URL = "https://github.com/JunCxio/GoldMonitor/releases/download/v1.0.1/GoldMonitorSetup.exe"
MACOS_ASSET_URL = "https://github.com/JunCxio/GoldMonitor/releases/download/v1.0.2/GoldMonitor-macOS.dmg"


def fixed_now():
    return datetime(2026, 6, 8, 12, 0, 0)


def test_version_compare_and_manifest_normalization_use_official_release_contract():
    from goldmonitor.update_manager import compare_versions, normalize_update_manifest

    assert compare_versions("1.2.0", "1.1.9") == 1
    assert compare_versions("1.0.0", "1.0") == 0
    assert compare_versions("1.0.0", "1.0.1") == -1

    manifest = normalize_update_manifest({
        "version": "1.0.1",
        "url": WINDOWS_ASSET_URL,
        "notes": "test release",
        "sha256": "A" * 64,
    }, platform_key="windows")
    assert manifest == {
        "version": "1.0.1",
        "url": WINDOWS_ASSET_URL,
        "notes": "test release",
        "sha256": "a" * 64,
    }

    platform_manifest = normalize_update_manifest({
        "version": "1.0.2",
        "url": WINDOWS_ASSET_URL,
        "sha256": "b" * 64,
        "downloads": {
            "windows": {"url": WINDOWS_ASSET_URL, "sha256": "b" * 64},
            "macos": {"url": MACOS_ASSET_URL, "sha256": "c" * 64},
        },
    }, platform_key="macos")
    assert platform_manifest["url"] == MACOS_ASSET_URL
    assert platform_manifest["sha256"] == "c" * 64

    for payload in (
        {"version": "1.0.1", "url": "http://example.com/GoldMonitorSetup.exe", "sha256": "a" * 64},
        {"version": "1.0.1", "url": "https://example.com/GoldMonitorSetup.exe", "sha256": "a" * 64},
        {"version": "1.0.1", "url": WINDOWS_ASSET_URL},
        {"version": "1.0.1", "url": WINDOWS_ASSET_URL, "sha256": "bad"},
    ):
        try:
            normalize_update_manifest(payload, platform_key="windows")
        except ValueError:
            pass
        else:
            raise AssertionError(f"manifest should be rejected: {payload}")


def test_update_status_hides_backend_only_download_metadata_until_install():
    from goldmonitor.update_manager import build_update_status

    manifest = {
        "version": "9.9.9",
        "url": WINDOWS_ASSET_URL,
        "notes": "new release",
        "sha256": "a" * 64,
    }

    public_status = build_update_status(manifest, "1.4.2", now=fixed_now(), expose_download=False)
    assert public_status["state"] == "available"
    assert public_status["checked_at"] == "2026-06-08T12:00:00"
    assert "url" not in public_status
    assert "sha256" not in public_status

    install_status = build_update_status(manifest, "1.4.2", now=fixed_now(), expose_download=True)
    assert install_status["url"] == WINDOWS_ASSET_URL
    assert install_status["sha256"] == "a" * 64

    latest = build_update_status({"version": "1.4.2", "url": WINDOWS_ASSET_URL, "notes": "", "sha256": "a" * 64}, "1.4.2", now=fixed_now())
    assert latest["state"] == "latest"
    assert latest["message"] == "当前已是最新版本。"


def test_installer_launch_plan_keeps_interactive_per_user_update_options():
    from goldmonitor.update_manager import build_installer_launch_plan

    plan = build_installer_launch_plan(
        "/tmp/GoldMonitorSetup.exe",
        os_name="nt",
        sys_platform="win32",
        create_new_process_group=1,
        detached_process=2,
    )
    assert plan["args"] == ["/tmp/GoldMonitorSetup.exe", "/CURRENTUSER", "/CLOSEAPPLICATIONS"]
    assert plan["kwargs"]["close_fds"] is True
    assert plan["kwargs"]["cwd"] == "/tmp"
    assert plan["kwargs"]["creationflags"] == 3
    assert "/SILENT" not in plan["args"]
    assert "/RESTARTAPPLICATIONS" not in plan["args"]

    mac_plan = build_installer_launch_plan("/tmp/GoldMonitor-macOS.dmg", os_name="posix", sys_platform="darwin")
    assert mac_plan == {"args": ["open", "/tmp/GoldMonitor-macOS.dmg"], "kwargs": {"close_fds": True}}


if __name__ == "__main__":
    failures = []
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            try:
                value()
            except Exception as exc:
                failures.append((name, exc))
    if failures:
        for name, exc in failures:
            print(f"{name}: {type(exc).__name__}: {exc}")
        raise SystemExit(1)
    print("update manager module checks passed.")
