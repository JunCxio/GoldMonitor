from pathlib import Path
import sys

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app


WINDOWS_ASSET_URL = "https://github.com/JunCxio/GoldMonitor/releases/download/v1.0.0/GoldMonitorSetup.exe"
MACOS_ASSET_URL = "https://github.com/JunCxio/GoldMonitor/releases/download/v1.0.0/GoldMonitor-macOS.dmg"


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._payload

    def raise_for_status(self):
        if not self.ok:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def release_api_payload():
    return {
        "tag_name": "v1.0.0",
        "name": "GoldMonitor v1.0.0",
        "body": "首次正式发布。",
        "assets": [
            {
                "name": "GoldMonitorSetup.exe",
                "browser_download_url": WINDOWS_ASSET_URL,
                "digest": "sha256:" + "a" * 64,
            },
            {
                "name": "GoldMonitor-macOS.dmg",
                "browser_download_url": MACOS_ASSET_URL,
                "digest": "sha256:" + "b" * 64,
            },
        ],
    }


def test_fetch_update_manifest_falls_back_to_github_release_api_when_asset_download_fails():
    calls = []
    original_platform_key = app._platform_update_key
    app._platform_update_key = lambda: "windows"

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        if url == app.DEFAULT_UPDATE_MANIFEST_URL:
            raise requests.ConnectionError("release asset cdn is blocked")
        if url == "https://api.github.com/repos/JunCxio/GoldMonitor/releases/latest":
            return FakeResponse(release_api_payload())
        raise AssertionError(f"unexpected url: {url}")

    try:
        manifest = app.fetch_update_manifest(app.DEFAULT_UPDATE_MANIFEST_URL, request_get=fake_get)
    finally:
        app._platform_update_key = original_platform_key

    assert manifest == {
        "version": "1.0.0",
        "url": WINDOWS_ASSET_URL,
        "notes": "首次正式发布。",
        "sha256": "a" * 64,
    }
    assert [url for url, _kwargs in calls] == [
        app.DEFAULT_UPDATE_MANIFEST_URL,
        "https://api.github.com/repos/JunCxio/GoldMonitor/releases/latest",
    ]
    assert all("proxies" not in kwargs for _url, kwargs in calls)


def test_fetch_update_manifest_reports_required_github_hosts_when_all_sources_fail():
    def fake_get(url, **kwargs):
        raise requests.ConnectionError(f"blocked: {url}")

    try:
        app.fetch_update_manifest(app.DEFAULT_UPDATE_MANIFEST_URL, request_get=fake_get)
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("fetch_update_manifest should report network failure")

    assert "github.com" in message
    assert "api.github.com" in message
    assert "release-assets.githubusercontent.com" in message
