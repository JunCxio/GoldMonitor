import hashlib
import os


def update_request_headers(user_agent):
    return {
        "Accept": "application/json",
        "User-Agent": user_agent,
    }


def get_update_json(url, *, request_get, timeout, headers):
    response = request_get(url, timeout=timeout, headers=headers)
    response.raise_for_status()
    return response.json()


def update_fetch_error_message(manifest_error, api_error):
    detail = str(api_error or manifest_error or "").strip()
    suffix = f" 原因: {detail}" if detail else ""
    return (
        "检查更新失败：无法访问 GitHub 更新服务。请确认当前网络允许访问 "
        "github.com、api.github.com 和 release-assets.githubusercontent.com，或检查系统代理/VPN。"
        f"{suffix}"
    )


def fetch_update_manifest(
    manifest_url,
    *,
    require_official_update_url,
    github_release_api_url_from_manifest,
    get_update_json,
    normalize_update_manifest,
    normalize_github_release_manifest,
):
    manifest_url = str(manifest_url or "").strip()
    if not manifest_url:
        raise ValueError("未配置更新源")
    require_official_update_url(manifest_url, "更新源", {"version.json"})
    api_url = github_release_api_url_from_manifest(manifest_url)
    try:
        return normalize_update_manifest(get_update_json(manifest_url), manifest_url)
    except Exception as manifest_error:
        try:
            return normalize_github_release_manifest(get_update_json(api_url))
        except Exception as api_error:
            raise ValueError(update_fetch_error_message(manifest_error, api_error)) from api_error


def public_update_status(status, allowed_keys):
    status = status if isinstance(status, dict) else {}
    return {key: status[key] for key in allowed_keys if key in status}


def record_update_status(status_store, status_lock, status, allowed_keys):
    snapshot = public_update_status(status, allowed_keys)
    with status_lock:
        status_store.clear()
        status_store.update(snapshot)
    return dict(snapshot)


def get_last_update_status(status_store, status_lock):
    with status_lock:
        return dict(status_store)


def download_update_installer(
    update_info,
    *,
    update_dir,
    installer_name,
    request_get,
    proxies,
    progress_callback=None,
    chunk_size=1024 * 128,
):
    os.makedirs(update_dir, exist_ok=True)
    installer_path = os.path.join(update_dir, installer_name)
    response = request_get(
        update_info["url"],
        stream=True,
        timeout=60,
        proxies=proxies,
    )
    response.raise_for_status()
    try:
        total_bytes = int(response.headers.get("content-length") or 0)
    except (TypeError, ValueError):
        total_bytes = 0

    digest = hashlib.sha256()
    tmp_path = installer_path + ".tmp"
    received_bytes = 0
    with open(tmp_path, "wb") as file_handle:
        for chunk in response.iter_content(chunk_size=chunk_size):
            if not chunk:
                continue
            file_handle.write(chunk)
            digest.update(chunk)
            received_bytes += len(chunk)
            if progress_callback:
                progress_callback(received_bytes, total_bytes)

    expected = update_info.get("sha256")
    actual = digest.hexdigest()
    if expected and actual != expected:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise ValueError("安装包校验失败")

    os.replace(tmp_path, installer_path)
    return installer_path


def launch_update_installer(
    installer_path,
    *,
    path_exists,
    build_installer_launch_plan,
    popen,
):
    if not path_exists(installer_path):
        raise FileNotFoundError(installer_path)
    plan = build_installer_launch_plan(installer_path)
    popen(plan["args"], **plan["kwargs"])
