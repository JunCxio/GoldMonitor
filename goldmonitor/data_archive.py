import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime


ARCHIVE_SCHEMA_VERSION = 1
ARCHIVE_APP_NAME = "GoldMonitor"
ARCHIVE_MANIFEST_NAME = "manifest.json"
MAX_ARCHIVE_FILES = 64
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 512 * 1024 * 1024


class DataArchiveError(ValueError):
    pass


def _sha256_bytes(content):
    return hashlib.sha256(content).hexdigest()


def _safe_archive_name(key, path):
    filename = os.path.basename(str(path or "")) or f"{key}.data"
    return f"data/{key}/{filename}"


def _sqlite_snapshot(source_path, destination_path):
    source = sqlite3.connect(source_path, timeout=10)
    destination = sqlite3.connect(destination_path, timeout=10)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()


def _sqlite_integrity_check(path):
    connection = sqlite3.connect(path, timeout=10)
    try:
        result = connection.execute("PRAGMA quick_check").fetchone()
    finally:
        connection.close()
    if not result or str(result[0]).lower() != "ok":
        raise DataArchiveError(f"SQLite 文件完整性校验失败: {os.path.basename(path)}")


def _remove_sqlite_sidecars(path):
    for suffix in ("-wal", "-shm"):
        try:
            os.remove(path + suffix)
        except FileNotFoundError:
            pass


class DataArchiveManager:
    def __init__(self, paths, app_version, now_factory=None):
        self.paths = {
            str(key): {
                "path": str(value.get("path") or ""),
                "kind": str(value.get("kind") or "file"),
                "label": str(value.get("label") or key),
                "sensitive": bool(value.get("sensitive")),
            }
            for key, value in dict(paths or {}).items()
            if isinstance(value, dict) and str(value.get("path") or "")
        }
        self.app_version = str(app_version or "")
        self.now_factory = now_factory or datetime.now

    def create(self, destination_path, content_overrides=None):
        overrides = {
            str(key): value if isinstance(value, bytes) else str(value).encode("utf-8")
            for key, value in dict(content_overrides or {}).items()
        }
        destination_path = os.path.abspath(str(destination_path or ""))
        if not destination_path:
            raise DataArchiveError("归档保存路径无效")
        os.makedirs(os.path.dirname(destination_path) or ".", exist_ok=True)
        temporary_path = destination_path + ".tmp"
        workspace = tempfile.mkdtemp(prefix="goldmonitor-archive-")
        files = []
        try:
            with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                for key, definition in self.paths.items():
                    source_path = definition["path"]
                    present = key in overrides or os.path.isfile(source_path)
                    entry = {
                        "key": key,
                        "label": definition["label"],
                        "kind": definition["kind"],
                        "present": present,
                        "sensitive": definition["sensitive"],
                        "archive_name": "",
                        "size": 0,
                        "sha256": "",
                    }
                    if present:
                        archive_name = _safe_archive_name(key, source_path)
                        if key in overrides:
                            content = overrides[key]
                        elif definition["kind"] == "sqlite":
                            snapshot_path = os.path.join(workspace, f"{key}.sqlite3")
                            _sqlite_snapshot(source_path, snapshot_path)
                            with open(snapshot_path, "rb") as file_handle:
                                content = file_handle.read()
                        else:
                            with open(source_path, "rb") as file_handle:
                                content = file_handle.read()
                        entry.update({
                            "archive_name": archive_name,
                            "size": len(content),
                            "sha256": _sha256_bytes(content),
                        })
                        archive.writestr(archive_name, content)
                    files.append(entry)

                manifest = {
                    "schema_version": ARCHIVE_SCHEMA_VERSION,
                    "app": ARCHIVE_APP_NAME,
                    "version": self.app_version,
                    "exported_at": self.now_factory().isoformat(timespec="seconds"),
                    "contains_sensitive_data": any(item["present"] and item["sensitive"] for item in files),
                    "files": files,
                }
                archive.writestr(
                    ARCHIVE_MANIFEST_NAME,
                    json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
                )
            os.replace(temporary_path, destination_path)
        except Exception:
            try:
                os.remove(temporary_path)
            except FileNotFoundError:
                pass
            raise
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

        return {
            "path": destination_path,
            "filename": os.path.basename(destination_path),
            "files": sum(1 for item in files if item["present"]),
            "bytes": sum(int(item["size"]) for item in files if item["present"]),
            "contains_sensitive_data": manifest["contains_sensitive_data"],
            "manifest": manifest,
        }

    def _read_and_validate(self, archive_path, extract_dir=None):
        try:
            archive = zipfile.ZipFile(archive_path, "r")
        except (OSError, zipfile.BadZipFile) as exc:
            raise DataArchiveError("归档文件不是有效的 ZIP 文件") from exc

        with archive:
            infos = archive.infolist()
            if len(infos) > MAX_ARCHIVE_FILES:
                raise DataArchiveError("归档文件数量超过限制")
            filenames = [info.filename for info in infos]
            if len(filenames) != len(set(filenames)):
                raise DataArchiveError("归档包含重复文件路径")
            total_uncompressed = sum(max(0, int(info.file_size)) for info in infos)
            if total_uncompressed > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                raise DataArchiveError("归档解压后大小超过限制")
            try:
                manifest = json.loads(archive.read(ARCHIVE_MANIFEST_NAME).decode("utf-8"))
            except KeyError as exc:
                raise DataArchiveError("归档缺少清单文件") from exc
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise DataArchiveError("归档清单格式无效") from exc

            if not isinstance(manifest, dict):
                raise DataArchiveError("归档清单格式无效")
            raw_version = manifest.get("schema_version")
            if isinstance(raw_version, bool) or not isinstance(raw_version, int) or raw_version <= 0:
                raise DataArchiveError("归档版本无效")
            if raw_version > ARCHIVE_SCHEMA_VERSION:
                raise DataArchiveError(
                    f"归档版本 {raw_version} 高于当前支持版本 {ARCHIVE_SCHEMA_VERSION}"
                )
            if manifest.get("app") != ARCHIVE_APP_NAME:
                raise DataArchiveError("归档不属于 GoldMonitor")
            raw_files = manifest.get("files")
            if not isinstance(raw_files, list) or not raw_files:
                raise DataArchiveError("归档清单没有数据文件")

            members = {info.filename: info for info in infos}
            validated = []
            seen_keys = set()
            for raw_entry in raw_files:
                if not isinstance(raw_entry, dict):
                    raise DataArchiveError("归档文件清单项无效")
                key = str(raw_entry.get("key") or "")
                if key not in self.paths:
                    raise DataArchiveError(f"归档包含当前版本不支持的数据项: {key or '未知'}")
                if key in seen_keys:
                    raise DataArchiveError(f"归档包含重复数据项: {key}")
                seen_keys.add(key)
                present = bool(raw_entry.get("present"))
                entry = dict(raw_entry)
                entry["key"] = key
                entry["present"] = present
                if not present:
                    entry.update({"archive_name": "", "size": 0, "sha256": ""})
                    validated.append(entry)
                    continue

                archive_name = str(raw_entry.get("archive_name") or "")
                expected_name = _safe_archive_name(key, self.paths[key]["path"])
                if archive_name != expected_name or archive_name not in members:
                    raise DataArchiveError(f"归档数据项路径无效: {key}")
                declared_size = raw_entry.get("size")
                if isinstance(declared_size, bool) or not isinstance(declared_size, int) or declared_size < 0:
                    raise DataArchiveError(f"归档数据项大小无效: {key}")
                if members[archive_name].file_size != declared_size:
                    raise DataArchiveError(f"归档数据项大小不匹配: {key}")
                content = archive.read(archive_name)
                if _sha256_bytes(content) != str(raw_entry.get("sha256") or ""):
                    raise DataArchiveError(f"归档数据项校验失败: {key}")
                if extract_dir:
                    extracted_path = os.path.join(extract_dir, key)
                    with open(extracted_path, "wb") as file_handle:
                        file_handle.write(content)
                    if self.paths[key]["kind"] == "sqlite":
                        _sqlite_integrity_check(extracted_path)
                    elif self.paths[key]["kind"] == "json":
                        try:
                            json.loads(content.decode("utf-8"))
                        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                            raise DataArchiveError(f"归档 JSON 数据无效: {key}") from exc
                    entry["extracted_path"] = extracted_path
                validated.append(entry)

            missing_keys = sorted(set(self.paths) - seen_keys)
            if missing_keys:
                raise DataArchiveError("归档缺少数据项: " + "、".join(missing_keys))
            expected_members = {ARCHIVE_MANIFEST_NAME} | {
                item["archive_name"] for item in validated if item["present"]
            }
            if set(members) != expected_members:
                raise DataArchiveError("归档包含清单之外的文件")

        present_entries = [item for item in validated if item["present"]]
        return manifest, validated, {
            "ok": True,
            "restorable": bool(present_entries),
            "schema_version": manifest["schema_version"],
            "expected_schema_version": ARCHIVE_SCHEMA_VERSION,
            "source_app_version": str(manifest.get("version") or ""),
            "exported_at": str(manifest.get("exported_at") or ""),
            "contains_sensitive_data": any(
                item["present"] and self.paths[item["key"]]["sensitive"]
                for item in validated
            ),
            "files": len(present_entries),
            "bytes": sum(int(item.get("size") or 0) for item in present_entries),
            "items": [
                {
                    "key": item["key"],
                    "label": self.paths[item["key"]]["label"],
                    "kind": self.paths[item["key"]]["kind"],
                    "present": item["present"],
                    "size": int(item.get("size") or 0),
                    "sensitive": self.paths[item["key"]]["sensitive"],
                }
                for item in validated
            ],
            "message": f"归档校验通过，可恢复 {len(present_entries)} 项数据",
        }

    def preview(self, archive_path):
        workspace = tempfile.mkdtemp(prefix="goldmonitor-archive-preview-")
        try:
            _, _, preview = self._read_and_validate(archive_path, extract_dir=workspace)
            return preview
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

    def restore(self, archive_path, apply_callback=None, rollback_callback=None):
        appdata_dir = os.path.commonpath([
            os.path.dirname(os.path.abspath(definition["path"])) or "."
            for definition in self.paths.values()
        ])
        if not os.path.isdir(appdata_dir):
            os.makedirs(appdata_dir, exist_ok=True)
        workspace = tempfile.mkdtemp(prefix=".goldmonitor-restore-", dir=appdata_dir)
        extract_dir = os.path.join(workspace, "extracted")
        rollback_dir = os.path.join(workspace, "rollback")
        os.makedirs(extract_dir, exist_ok=True)
        os.makedirs(rollback_dir, exist_ok=True)
        snapshots = {}
        try:
            manifest, entries, preview = self._read_and_validate(archive_path, extract_dir=extract_dir)
            for key, definition in self.paths.items():
                target_path = definition["path"]
                existed = os.path.isfile(target_path)
                snapshot_path = os.path.join(rollback_dir, key)
                snapshots[key] = {"existed": existed, "path": snapshot_path}
                if not existed:
                    continue
                if definition["kind"] == "sqlite":
                    _sqlite_snapshot(target_path, snapshot_path)
                else:
                    shutil.copy2(target_path, snapshot_path)

            entries_by_key = {item["key"]: item for item in entries}
            for key, definition in self.paths.items():
                target_path = definition["path"]
                os.makedirs(os.path.dirname(target_path) or ".", exist_ok=True)
                entry = entries_by_key.get(key)
                if entry and entry["present"]:
                    replacement_path = target_path + ".restore-tmp"
                    shutil.copy2(entry["extracted_path"], replacement_path)
                    os.replace(replacement_path, target_path)
                else:
                    try:
                        os.remove(target_path)
                    except FileNotFoundError:
                        pass
                if definition["kind"] == "sqlite":
                    _remove_sqlite_sidecars(target_path)

            if callable(apply_callback):
                apply_callback(manifest, preview)
        except Exception:
            for key, definition in self.paths.items():
                snapshot = snapshots.get(key)
                if not snapshot:
                    continue
                target_path = definition["path"]
                try:
                    if snapshot["existed"]:
                        replacement_path = target_path + ".rollback-tmp"
                        shutil.copy2(snapshot["path"], replacement_path)
                        os.replace(replacement_path, target_path)
                    else:
                        try:
                            os.remove(target_path)
                        except FileNotFoundError:
                            pass
                    if definition["kind"] == "sqlite":
                        _remove_sqlite_sidecars(target_path)
                except OSError:
                    pass
            if callable(rollback_callback):
                rollback_callback()
            raise
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

        return {
            **preview,
            "ok": True,
            "restored": preview["files"],
            "message": f"已恢复 {preview['files']} 项本地数据",
        }
