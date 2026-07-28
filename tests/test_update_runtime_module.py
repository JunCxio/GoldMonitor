import hashlib
from pathlib import Path
import sys
import threading


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from goldmonitor import update_runtime


def test_update_fetch_falls_back_to_release_api_and_reports_combined_failure():
    calls = []
    manifest_url = "https://github.com/example/project/releases/latest/download/version.json"
    api_url = "https://api.github.com/repos/example/project/releases/latest"

    def get_update_json(url):
        calls.append(url)
        if url == manifest_url:
            raise OSError("资源下载失败")
        return {"tag_name": "v1.1.0"}

    result = update_runtime.fetch_update_manifest(
        manifest_url,
        require_official_update_url=lambda *_args, **_kwargs: None,
        github_release_api_url_from_manifest=lambda _url: api_url,
        get_update_json=get_update_json,
        normalize_update_manifest=lambda raw, base_url: raw,
        normalize_github_release_manifest=lambda raw: {"version": raw["tag_name"].lstrip("v")},
    )

    assert result == {"version": "1.1.0"}
    assert calls == [manifest_url, api_url]

    try:
        update_runtime.fetch_update_manifest(
            manifest_url,
            require_official_update_url=lambda *_args, **_kwargs: None,
            github_release_api_url_from_manifest=lambda _url: api_url,
            get_update_json=lambda url: (_ for _ in ()).throw(OSError(url)),
            normalize_update_manifest=lambda raw, base_url: raw,
            normalize_github_release_manifest=lambda raw: raw,
        )
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("all update sources failing must raise ValueError")
    assert "github.com" in message
    assert "api.github.com" in message


def test_update_status_store_keeps_only_public_fields():
    store = {}
    lock = threading.RLock()
    allowed = ("state", "message", "progress_percent")
    saved = update_runtime.record_update_status(
        store,
        lock,
        {
            "state": "available",
            "message": "发现新版本。",
            "progress_percent": 25,
            "url": "https://example.invalid/installer.exe",
            "sha256": "a" * 64,
        },
        allowed,
    )

    assert saved == {
        "state": "available",
        "message": "发现新版本。",
        "progress_percent": 25,
    }
    assert update_runtime.get_last_update_status(store, lock) == saved


def test_update_download_validates_checksum_and_reports_progress(tmp_path):
    content = b"goldmonitor-installer"
    progress = []

    class Response:
        headers = {"content-length": str(len(content))}

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size):
            assert chunk_size == 1024 * 128
            return [content[:5], b"", content[5:]]

    installer_path = update_runtime.download_update_installer(
        {
            "url": "https://example.invalid/GoldMonitorSetup.exe",
            "sha256": hashlib.sha256(content).hexdigest(),
        },
        update_dir=str(tmp_path),
        installer_name="GoldMonitorSetup.exe",
        request_get=lambda *args, **kwargs: Response(),
        proxies={"http": None, "https": None},
        progress_callback=lambda received, total: progress.append((received, total)),
    )

    assert Path(installer_path).read_bytes() == content
    assert progress[-1] == (len(content), len(content))


def test_update_launch_uses_validated_plan_without_forcing_process_exit(tmp_path):
    installer = tmp_path / "GoldMonitorSetup.exe"
    installer.write_bytes(b"installer")
    launched = []

    update_runtime.launch_update_installer(
        str(installer),
        path_exists=lambda path: Path(path).exists(),
        build_installer_launch_plan=lambda path: {
            "args": [path, "/CURRENTUSER", "/CLOSEAPPLICATIONS"],
            "kwargs": {"close_fds": True},
        },
        popen=lambda args, **kwargs: launched.append((args, kwargs)),
    )

    assert launched == [
        ([str(installer), "/CURRENTUSER", "/CLOSEAPPLICATIONS"], {"close_fds": True}),
    ]
