import os


def normalize_alert_profiles_for_import(payload, *, normalize):
    return normalize(payload) if isinstance(payload, list) else None


def normalize_alert_rules_for_import(payload, *, normalize, now_factory, id_factory):
    if not isinstance(payload, list):
        return None
    normalized, invalid_count = normalize(
        payload,
        now_factory=now_factory,
        id_factory=id_factory,
    )
    if invalid_count:
        raise ValueError("备份中的预警规则包含无效或重复数据")
    return normalized


def prepare_alert_profiles_for_import(
    payload,
    *,
    current_thresholds,
    current_volatility_config,
    current_settings,
):
    if not isinstance(payload, list):
        return []
    prepared = []
    for item in payload:
        if not isinstance(item, dict):
            prepared.append(item)
            continue
        next_item = dict(item)
        raw_thresholds = next_item.get("thresholds")
        next_item["thresholds"] = {
            **current_thresholds,
            **(raw_thresholds if isinstance(raw_thresholds, dict) else {}),
        }
        raw_volatility = next_item.get("volatility_config")
        next_item["volatility_config"] = {
            **current_volatility_config,
            **(raw_volatility if isinstance(raw_volatility, dict) else {}),
        }
        raw_settings = next_item.get("settings")
        next_item["settings"] = {
            **current_settings,
            **(raw_settings if isinstance(raw_settings, dict) else {}),
        }
        prepared.append(next_item)
    return prepared


def snapshot_import_files(paths):
    snapshots = {}
    for path in paths:
        try:
            with open(path, "rb") as file_handle:
                snapshots[path] = {"exists": True, "content": file_handle.read()}
        except FileNotFoundError:
            snapshots[path] = {"exists": False, "content": b""}
    return snapshots


def restore_import_files(snapshots):
    rollback_ok = True
    for path, snapshot in snapshots.items():
        try:
            if snapshot.get("exists"):
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                with open(path, "wb") as file_handle:
                    file_handle.write(snapshot.get("content", b""))
            elif os.path.exists(path):
                os.remove(path)
        except OSError:
            rollback_ok = False
    return rollback_ok
