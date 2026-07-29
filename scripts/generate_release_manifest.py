import argparse
import hashlib
import json
import re
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Generate release metadata for GitHub Releases.")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--release-dir", default="release")
    return parser.parse_args()


def read_version(repo_root: Path) -> str:
    source = (repo_root / "goldmonitor" / "application.py").read_text(encoding="utf-8")
    match = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', source)
    if not match:
        raise RuntimeError("APP_VERSION was not found.")
    return match.group(1)


def read_release_notes(repo_root: Path, version: str) -> str:
    changelog = (repo_root / "CHANGELOG.md").read_text(encoding="utf-8")
    escaped_version = re.escape(version)
    match = re.search(rf"(?ms)^##\s+{escaped_version}\s*\r?\n(?P<notes>.*?)(?=^##\s+|\Z)", changelog)
    if not match or not match.group("notes").strip():
        raise RuntimeError(f"CHANGELOG.md is missing release notes for version {version}.")
    return match.group("notes").strip()


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    release_dir = (repo_root / args.release_dir).resolve()
    version = read_version(repo_root)
    expected_tag = f"v{version}"
    if args.tag != expected_tag:
        raise RuntimeError(f"Tag {args.tag} does not match APP_VERSION {version}.")

    windows_asset = release_dir / "GoldMonitorSetup.exe"
    macos_asset = release_dir / "GoldMonitor-macOS.dmg"
    if not windows_asset.exists():
        raise RuntimeError(f"Missing release asset: {windows_asset}")
    if not macos_asset.exists():
        raise RuntimeError(f"Missing release asset: {macos_asset}")

    windows_sha = sha256_of(windows_asset)
    macos_sha = sha256_of(macos_asset)
    notes = read_release_notes(repo_root, version)
    base_url = f"https://github.com/{args.repository}/releases/download/{args.tag}"

    manifest = {
        "version": version,
        "url": f"{base_url}/GoldMonitorSetup.exe",
        "sha256": windows_sha,
        "notes": notes,
        "downloads": {
            "windows": {
                "url": f"{base_url}/GoldMonitorSetup.exe",
                "sha256": windows_sha,
            },
            "macos": {
                "url": f"{base_url}/GoldMonitor-macOS.dmg",
                "sha256": macos_sha,
            },
        },
    }
    (release_dir / "version.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    release_notes = "\n".join([
        f"GoldMonitor {version}",
        "",
        notes,
        "",
        "Windows installer: GoldMonitorSetup.exe",
        f"Windows SHA256: {windows_sha}",
        "macOS disk image: GoldMonitor-macOS.dmg",
        f"macOS SHA256: {macos_sha}",
        "Update manifest: version.json",
    ])
    (release_dir / "release-notes.md").write_text(release_notes + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
