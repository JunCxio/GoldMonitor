import json
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_release_asset_verification_accepts_matching_manifest_and_assets():
    from scripts.verify_release_assets import sha256_of, verify_release_payload

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        windows_asset = tmp / "GoldMonitorSetup.exe"
        macos_asset = tmp / "GoldMonitor-macOS.dmg"
        windows_asset.write_bytes(b"windows-installer")
        macos_asset.write_bytes(b"macos-dmg")
        windows_sha = sha256_of(windows_asset)
        macos_sha = sha256_of(macos_asset)

        release = {
            "tag_name": "v9.8.7",
            "draft": False,
            "prerelease": False,
            "html_url": "https://example.test/release",
            "assets": [
                {"name": "GoldMonitorSetup.exe", "size": windows_asset.stat().st_size},
                {"name": "GoldMonitor-macOS.dmg", "size": macos_asset.stat().st_size},
                {"name": "version.json", "size": 2},
            ],
        }
        manifest = {
            "version": "9.8.7",
            "url": "https://github.com/owner/repo/releases/download/v9.8.7/GoldMonitorSetup.exe",
            "sha256": windows_sha,
            "notes": "release notes",
            "downloads": {
                "windows": {
                    "url": "https://github.com/owner/repo/releases/download/v9.8.7/GoldMonitorSetup.exe",
                    "sha256": windows_sha,
                },
                "macos": {
                    "url": "https://github.com/owner/repo/releases/download/v9.8.7/GoldMonitor-macOS.dmg",
                    "sha256": macos_sha,
                },
            },
        }

        result = verify_release_payload("v9.8.7", release, manifest, {
            "GoldMonitorSetup.exe": windows_asset,
            "GoldMonitor-macOS.dmg": macos_asset,
        })

        assert result["version"] == "9.8.7"
        assert result["release_url"] == "https://example.test/release"
        assert result["assets"]["GoldMonitorSetup.exe"]["size"] == windows_asset.stat().st_size
        assert result["assets"]["GoldMonitorSetup.exe"]["sha256"] == manifest["downloads"]["windows"]["sha256"]
        assert result["assets"]["GoldMonitor-macOS.dmg"]["sha256"] == manifest["downloads"]["macos"]["sha256"]


def test_release_asset_verification_rejects_incomplete_release():
    from scripts.verify_release_assets import ReleaseVerificationError, verify_release_payload

    release = {
        "tag_name": "v1.0.0",
        "draft": False,
        "prerelease": False,
        "assets": [{"name": "version.json", "size": 2}],
    }
    manifest = {
        "version": "1.0.0",
        "url": "https://github.com/owner/repo/releases/download/v1.0.0/GoldMonitorSetup.exe",
        "sha256": "abc",
        "downloads": {
            "windows": {
                "url": "https://github.com/owner/repo/releases/download/v1.0.0/GoldMonitorSetup.exe",
                "sha256": "abc",
            },
            "macos": {
                "url": "https://github.com/owner/repo/releases/download/v1.0.0/GoldMonitor-macOS.dmg",
                "sha256": "def",
            },
        },
    }

    try:
        verify_release_payload("v1.0.0", release, manifest, {})
    except ReleaseVerificationError as exc:
        assert "Missing release asset" in str(exc)
    else:
        raise AssertionError("missing release assets must fail verification")


def test_cli_can_verify_local_release_fixture_without_network():
    from scripts.verify_release_assets import main, sha256_of

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        release_path = tmp / "release.json"
        manifest_path = tmp / "version.json"
        windows_asset = tmp / "GoldMonitorSetup.exe"
        macos_asset = tmp / "GoldMonitor-macOS.dmg"
        windows_asset.write_bytes(b"windows")
        macos_asset.write_bytes(b"macos")
        windows_sha = sha256_of(windows_asset)
        macos_sha = sha256_of(macos_asset)

        release_path.write_text(json.dumps({
            "tag_name": "v1.2.3",
            "draft": False,
            "prerelease": False,
            "html_url": "https://example.test/v1.2.3",
            "assets": [
                {"name": "GoldMonitorSetup.exe", "size": windows_asset.stat().st_size},
                {"name": "GoldMonitor-macOS.dmg", "size": macos_asset.stat().st_size},
                {"name": "version.json", "size": 2},
            ],
        }), encoding="utf-8")
        manifest_path.write_text(json.dumps({
            "version": "1.2.3",
            "url": "https://github.com/owner/repo/releases/download/v1.2.3/GoldMonitorSetup.exe",
            "sha256": windows_sha,
            "downloads": {
                "windows": {
                    "url": "https://github.com/owner/repo/releases/download/v1.2.3/GoldMonitorSetup.exe",
                    "sha256": windows_sha,
                },
                "macos": {
                    "url": "https://github.com/owner/repo/releases/download/v1.2.3/GoldMonitor-macOS.dmg",
                    "sha256": macos_sha,
                },
            },
            "notes": "notes",
        }), encoding="utf-8")

        exit_code = main([
            "--tag", "v1.2.3",
            "--release-json", str(release_path),
            "--manifest-json", str(manifest_path),
            "--asset-dir", str(tmp),
        ])

        assert exit_code == 0
