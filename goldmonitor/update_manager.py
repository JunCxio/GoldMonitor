import os
import sys
from datetime import datetime
from urllib.parse import urljoin, urlparse


DEFAULT_UPDATE_MANIFEST_URL = "https://github.com/JunCxio/GoldMonitor/releases/latest/download/version.json"
OFFICIAL_UPDATE_HOST = "github.com"
OFFICIAL_UPDATE_PATH_PREFIX = "/JunCxio/GoldMonitor/releases/"
OFFICIAL_UPDATE_ASSET_NAMES = {"GoldMonitorSetup.exe", "GoldMonitor-macOS.dmg"}


def compare_versions(left, right):
    def parts(value):
        normalized = []
        for part in str(value or "0").split("."):
            digits = "".join(ch for ch in part if ch.isdigit())
            normalized.append(int(digits or 0))
        return normalized

    left_parts = parts(left)
    right_parts = parts(right)
    max_len = max(len(left_parts), len(right_parts))
    left_parts.extend([0] * (max_len - len(left_parts)))
    right_parts.extend([0] * (max_len - len(right_parts)))
    if left_parts > right_parts:
        return 1
    if left_parts < right_parts:
        return -1
    return 0


def require_https_url(value, label):
    parsed = urlparse(str(value or "").strip())
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise ValueError(f"{label}必须使用 HTTPS 地址")


def require_official_update_url(
    value,
    label,
    allowed_names=None,
    official_host=OFFICIAL_UPDATE_HOST,
    official_path_prefix=OFFICIAL_UPDATE_PATH_PREFIX,
):
    require_https_url(value, label)
    parsed = urlparse(str(value or "").strip())
    host = parsed.netloc.lower()
    path = parsed.path
    if host != official_host or not path.lower().startswith(official_path_prefix.lower()):
        raise ValueError(f"{label}必须使用官方 GitHub Release 地址")
    if allowed_names is not None:
        name = path.rsplit("/", 1)[-1]
        if name not in allowed_names:
            raise ValueError(f"{label}文件名无效")


def platform_update_key(sys_platform=None, os_name=None):
    sys_platform = sys.platform if sys_platform is None else sys_platform
    os_name = os.name if os_name is None else os_name
    if sys_platform == "darwin":
        return "macos"
    if os_name == "nt":
        return "windows"
    return ""


def normalize_update_manifest(
    raw,
    base_url=None,
    platform_key=None,
    official_host=OFFICIAL_UPDATE_HOST,
    official_path_prefix=OFFICIAL_UPDATE_PATH_PREFIX,
    asset_names=OFFICIAL_UPDATE_ASSET_NAMES,
):
    if not isinstance(raw, dict):
        raise ValueError("更新清单格式无效")

    version = str(raw.get("version") or "").strip()
    notes = str(raw.get("notes") or "").strip()
    download_url = str(raw.get("url") or raw.get("download_url") or "").strip()
    sha256 = str(raw.get("sha256") or "").strip().lower()
    downloads = raw.get("downloads")
    platform_key = platform_update_key() if platform_key is None else platform_key

    if isinstance(downloads, dict) and platform_key:
        platform_payload = downloads.get(platform_key)
        if platform_payload is None and platform_key != "windows":
            raise ValueError("当前平台暂无可用更新包")
        if isinstance(platform_payload, dict):
            download_url = str(platform_payload.get("url") or platform_payload.get("download_url") or "").strip()
            sha256 = str(platform_payload.get("sha256") or "").strip().lower()

    if base_url and download_url:
        download_url = urljoin(base_url, download_url)

    if not version:
        raise ValueError("更新清单缺少版本号")
    if not download_url:
        raise ValueError("更新清单缺少安装包地址")
    require_official_update_url(
        download_url,
        "更新安装包",
        asset_names,
        official_host=official_host,
        official_path_prefix=official_path_prefix,
    )
    if not sha256:
        raise ValueError("更新清单缺少安装包 sha256")
    if sha256 and (len(sha256) != 64 or any(ch not in "0123456789abcdef" for ch in sha256)):
        raise ValueError("更新清单 sha256 格式无效")

    return {
        "version": version,
        "url": download_url,
        "notes": notes,
        "sha256": sha256,
    }


def build_update_status(manifest, current_version, now=None, expose_download=False):
    now = now or datetime.now()
    status = {
        "current_version": current_version,
        "checked_at": now.isoformat(timespec="seconds"),
    }

    has_update = compare_versions(manifest["version"], current_version) > 0
    status.update({
        "state": "available" if has_update else "latest",
        "latest_version": manifest["version"],
        "notes": manifest["notes"],
        "message": "发现新版本。" if has_update else "当前已是最新版本。",
    })
    if has_update and expose_download:
        status.update({
            "url": manifest["url"],
            "sha256": manifest["sha256"],
        })
    return status


def build_installer_launch_plan(
    installer_path,
    os_name=None,
    sys_platform=None,
    create_new_process_group=0,
    detached_process=0,
):
    os_name = os.name if os_name is None else os_name
    sys_platform = sys.platform if sys_platform is None else sys_platform
    if os_name == "nt":
        return {
            "args": [
                installer_path,
                "/CURRENTUSER",
                "/CLOSEAPPLICATIONS",
            ],
            "kwargs": {
                "close_fds": True,
                "cwd": os.path.dirname(installer_path) or None,
                "creationflags": create_new_process_group | detached_process,
            },
        }

    if sys_platform == "darwin":
        return {"args": ["open", installer_path], "kwargs": {"close_fds": True}}

    return {"args": [installer_path], "kwargs": {"close_fds": True}}
