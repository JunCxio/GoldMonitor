import hashlib
import os
from datetime import datetime

from goldmonitor import update_manager as update_manager_core


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


class UpdateRuntime:
    def __init__(
        self,
        state,
        *,
        current_version,
        manifest_url,
        official_host,
        official_path_prefix,
        official_asset_names,
        update_dir,
        installer_name,
        user_agent,
        request_timeout,
        proxies,
        os_name,
        sys_platform,
        request_get,
        path_exists,
        popen,
        create_new_process_group,
        detached_process,
        emit,
        public_status_keys,
        now_factory=datetime.now,
    ):
        self.state = state
        self.current_version = current_version
        self.manifest_url = manifest_url
        self.official_host = official_host
        self.official_path_prefix = official_path_prefix
        self.official_asset_names = official_asset_names
        self.update_dir = update_dir
        self.installer_name = installer_name
        self.user_agent = user_agent
        self.request_timeout = request_timeout
        self.proxies = proxies
        self.os_name = os_name
        self.sys_platform = sys_platform
        self.request_get = request_get
        self.path_exists = path_exists
        self.popen = popen
        self.create_new_process_group = create_new_process_group
        self.detached_process = detached_process
        self.emit = emit
        self.public_status_keys = tuple(public_status_keys)
        self.now_factory = now_factory

    def compare_versions(self, left, right):
        return update_manager_core.compare_versions(left, right)

    def require_https_url(self, value, label):
        return update_manager_core.require_https_url(value, label)

    def require_official_update_url(self, value, label, allowed_names=None):
        return update_manager_core.require_official_update_url(
            value,
            label,
            allowed_names,
            official_host=self.official_host,
            official_path_prefix=self.official_path_prefix,
        )

    def get_manifest_url(self):
        return self.manifest_url

    def platform_update_key(self):
        return update_manager_core.platform_update_key(
            sys_platform=self.sys_platform(),
            os_name=self.os_name(),
        )

    def normalize_update_manifest(self, raw, base_url=None, *, platform_key=None):
        return update_manager_core.normalize_update_manifest(
            raw,
            base_url=base_url,
            platform_key=(
                self.platform_update_key()
                if platform_key is None
                else platform_key
            ),
            official_host=self.official_host,
            official_path_prefix=self.official_path_prefix,
            asset_names=self.official_asset_names,
        )

    def normalize_github_release_manifest(self, raw, *, platform_key=None):
        return update_manager_core.normalize_github_release_manifest(
            raw,
            platform_key=(
                self.platform_update_key()
                if platform_key is None
                else platform_key
            ),
            official_host=self.official_host,
            official_path_prefix=self.official_path_prefix,
            asset_names=self.official_asset_names,
        )

    def github_release_api_url_from_manifest(self, manifest_url):
        return update_manager_core.github_release_api_url_from_manifest(
            manifest_url,
            official_host=self.official_host,
            official_path_prefix=self.official_path_prefix,
        )

    def request_headers(self):
        return update_request_headers(self.user_agent)

    def get_update_json(self, url, *, request_get_override=None, timeout=None):
        return get_update_json(
            url,
            request_get=request_get_override or self.request_get,
            timeout=self.request_timeout if timeout is None else timeout,
            headers=self.request_headers(),
        )

    def fetch_update_manifest(
        self,
        manifest_url=None,
        *,
        request_get_override=None,
        platform_key=None,
        require_official_update_url=None,
        github_release_api_url_from_manifest=None,
        get_json=None,
        normalize_manifest=None,
        normalize_github_manifest=None,
    ):
        selected_platform = (
            self.platform_update_key()
            if platform_key is None
            else platform_key
        )
        return fetch_update_manifest(
            manifest_url or self.get_manifest_url(),
            require_official_update_url=(
                require_official_update_url or self.require_official_update_url
            ),
            github_release_api_url_from_manifest=(
                github_release_api_url_from_manifest
                or self.github_release_api_url_from_manifest
            ),
            get_update_json=(
                get_json
                or (
                    lambda url: self.get_update_json(
                        url,
                        request_get_override=request_get_override,
                    )
                )
            ),
            normalize_update_manifest=(
                normalize_manifest
                or (
                    lambda raw, base_url=None: self.normalize_update_manifest(
                        raw,
                        base_url,
                        platform_key=selected_platform,
                    )
                )
            ),
            normalize_github_release_manifest=(
                normalize_github_manifest
                or (
                    lambda raw: self.normalize_github_release_manifest(
                        raw,
                        platform_key=selected_platform,
                    )
                )
            ),
        )

    def get_update_status(
        self,
        expose_download=False,
        *,
        get_manifest_url=None,
        fetch_manifest=None,
    ):
        manifest_url = (get_manifest_url or self.get_manifest_url)()
        manifest = (fetch_manifest or self.fetch_update_manifest)(manifest_url)
        return update_manager_core.build_update_status(
            manifest,
            self.current_version,
            now=self.now_factory(),
            expose_download=expose_download,
        )

    def public_update_status(self, status=None):
        return public_update_status(status, self.public_status_keys)

    def record_update_status(self, status):
        return record_update_status(
            self.state.last_update_status,
            self.state.last_update_status_lock,
            status,
            self.public_status_keys,
        )

    def get_last_update_status(self):
        return get_last_update_status(
            self.state.last_update_status,
            self.state.last_update_status_lock,
        )

    def emit_update_status(self, status):
        safe_status = self.record_update_status(status)
        self.emit("update_status", safe_status)
        return safe_status

    def download_update_installer(self, update_info, progress_callback=None):
        return download_update_installer(
            update_info,
            update_dir=self.update_dir,
            installer_name=self.installer_name,
            request_get=self.request_get,
            proxies=self.proxies,
            progress_callback=progress_callback,
        )

    def launch_update_installer(self, installer_path):
        return launch_update_installer(
            installer_path,
            path_exists=self.path_exists,
            build_installer_launch_plan=(
                lambda path: update_manager_core.build_installer_launch_plan(
                    path,
                    os_name=self.os_name(),
                    sys_platform=self.sys_platform(),
                    create_new_process_group=self.create_new_process_group(),
                    detached_process=self.detached_process(),
                )
            ),
            popen=self.popen,
        )
