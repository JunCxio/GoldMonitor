import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path


REQUIRED_ASSETS = ("GoldMonitorSetup.exe", "GoldMonitor-macOS.dmg", "version.json")


class ReleaseVerificationError(RuntimeError):
    pass


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Verify GoldMonitor GitHub Release assets and update manifest.")
    parser.add_argument("--tag", required=True, help="Release tag, for example v1.4.3.")
    parser.add_argument("--repository", default="", help="GitHub repository in owner/name form.")
    parser.add_argument("--release-json", default="", help="Local release JSON fixture path.")
    parser.add_argument("--manifest-json", default="", help="Local version.json fixture path.")
    parser.add_argument("--asset-dir", default="", help="Directory containing local release assets.")
    parser.add_argument("--download-dir", default="", help="Directory for downloaded assets.")
    parser.add_argument("--keep-downloads", action="store_true", help="Keep downloaded assets after verification.")
    return parser.parse_args(argv)


def sha256_of(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _fetch_json(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)


def _download_file(url, target):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "GoldMonitor-release-verifier"})
    with urllib.request.urlopen(request, timeout=180) as response:
        with target.open("wb") as fh:
            shutil.copyfileobj(response, fh, length=1024 * 1024)
    return target


def _release_asset_map(release):
    return {asset.get("name"): asset for asset in release.get("assets", []) if isinstance(asset, dict)}


def _expected_version(tag):
    if not tag.startswith("v") or len(tag) == 1:
        raise ReleaseVerificationError(f"Invalid release tag: {tag}")
    return tag[1:]


def _expected_download_url(tag, asset_name):
    return f"/releases/download/{tag}/{asset_name}"


def _require_manifest_download(manifest, platform, tag, asset_name):
    downloads = manifest.get("downloads")
    if not isinstance(downloads, dict):
        raise ReleaseVerificationError("version.json is missing downloads.")
    entry = downloads.get(platform)
    if not isinstance(entry, dict):
        raise ReleaseVerificationError(f"version.json is missing downloads.{platform}.")
    url = entry.get("url")
    sha256 = entry.get("sha256")
    if not url or _expected_download_url(tag, asset_name) not in url:
        raise ReleaseVerificationError(f"downloads.{platform}.url does not point to {asset_name}: {url}")
    if not sha256:
        raise ReleaseVerificationError(f"downloads.{platform}.sha256 is missing.")
    return url, sha256


def verify_release_payload(tag, release, manifest, asset_paths):
    version = _expected_version(tag)
    if release.get("tag_name") != tag:
        raise ReleaseVerificationError(f"Release tag mismatch: expected {tag}, got {release.get('tag_name')}")
    if release.get("draft"):
        raise ReleaseVerificationError("Release must not be draft.")
    if release.get("prerelease"):
        raise ReleaseVerificationError("Release must not be prerelease.")

    assets = _release_asset_map(release)
    for asset_name in REQUIRED_ASSETS:
        if asset_name not in assets:
            raise ReleaseVerificationError(f"Missing release asset: {asset_name}")

    if manifest.get("version") != version:
        raise ReleaseVerificationError(f"version.json version mismatch: expected {version}, got {manifest.get('version')}")

    root_url = manifest.get("url")
    if not root_url or _expected_download_url(tag, "GoldMonitorSetup.exe") not in root_url:
        raise ReleaseVerificationError(f"version.json root url does not point to GoldMonitorSetup.exe: {root_url}")

    windows_url, windows_expected_sha = _require_manifest_download(
        manifest, "windows", tag, "GoldMonitorSetup.exe"
    )
    macos_url, macos_expected_sha = _require_manifest_download(
        manifest, "macos", tag, "GoldMonitor-macOS.dmg"
    )
    if manifest.get("sha256") != windows_expected_sha:
        raise ReleaseVerificationError("version.json top-level sha256 must match downloads.windows.sha256.")
    if manifest.get("url") != windows_url:
        raise ReleaseVerificationError("version.json top-level url must match downloads.windows.url.")

    result = {
        "tag": tag,
        "version": version,
        "release_url": release.get("html_url", ""),
        "assets": {},
    }
    for asset_name, expected_sha in (
        ("GoldMonitorSetup.exe", windows_expected_sha),
        ("GoldMonitor-macOS.dmg", macos_expected_sha),
    ):
        path = asset_paths.get(asset_name)
        if not path:
            raise ReleaseVerificationError(f"Missing local asset for SHA256 verification: {asset_name}")
        path = Path(path)
        if not path.exists():
            raise ReleaseVerificationError(f"Local asset does not exist: {path}")
        actual_sha = sha256_of(path)
        if actual_sha != expected_sha:
            raise ReleaseVerificationError(
                f"{asset_name} SHA256 mismatch: expected {expected_sha}, got {actual_sha}"
            )
        result["assets"][asset_name] = {
            "path": str(path),
            "size": path.stat().st_size,
            "sha256": actual_sha,
        }
    return result


def _load_release(args):
    if args.release_json:
        return _read_json(args.release_json)
    if not args.repository:
        raise ReleaseVerificationError("--repository is required when --release-json is not provided.")
    return _fetch_json(f"https://api.github.com/repos/{args.repository}/releases/tags/{args.tag}")


def _load_manifest(args, release):
    if args.manifest_json:
        return _read_json(args.manifest_json)
    assets = _release_asset_map(release)
    version_asset = assets.get("version.json")
    if not version_asset or not version_asset.get("browser_download_url"):
        raise ReleaseVerificationError("version.json asset download URL was not found.")
    return _fetch_json(version_asset["browser_download_url"])


def _asset_paths(args, release, manifest, download_dir):
    paths = {}
    if args.asset_dir:
        asset_dir = Path(args.asset_dir)
        for asset_name in ("GoldMonitorSetup.exe", "GoldMonitor-macOS.dmg"):
            paths[asset_name] = asset_dir / asset_name
        return paths

    assets = _release_asset_map(release)
    downloads = manifest.get("downloads", {})
    url_by_asset = {
        "GoldMonitorSetup.exe": downloads.get("windows", {}).get("url"),
        "GoldMonitor-macOS.dmg": downloads.get("macos", {}).get("url"),
    }
    for asset_name in ("GoldMonitorSetup.exe", "GoldMonitor-macOS.dmg"):
        asset = assets.get(asset_name, {})
        url = url_by_asset.get(asset_name) or asset.get("browser_download_url")
        if not url:
            raise ReleaseVerificationError(f"No download URL for {asset_name}.")
        print(f"Downloading {asset_name} from {url}", flush=True)
        paths[asset_name] = _download_file(url, Path(download_dir) / asset_name)
    return paths


def _run(args):
    release = _load_release(args)
    manifest = _load_manifest(args, release)
    temp_dir = None
    download_dir = args.download_dir
    if not download_dir and not args.asset_dir:
        temp_dir = tempfile.TemporaryDirectory()
        download_dir = temp_dir.name
    try:
        result = verify_release_payload(
            args.tag,
            release,
            manifest,
            _asset_paths(args, release, manifest, download_dir),
        )
    finally:
        if temp_dir and not args.keep_downloads:
            temp_dir.cleanup()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def main(argv=None):
    args = parse_args(argv)
    try:
        return _run(args)
    except ReleaseVerificationError as exc:
        print(f"Release asset verification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
