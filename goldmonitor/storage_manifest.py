import json
import os

from goldmonitor.support_files import json_payload_metadata


STORAGE_DEFINITIONS = (
    {"key": "appdata", "label": "应用数据目录", "kind": "directory", "schema": "directory"},
    {"key": "settings", "label": "通用设置", "kind": "json", "schema": "plain_json"},
    {"key": "thresholds", "label": "预警阈值", "kind": "json", "schema": "plain_json"},
    {
        "key": "alert_rules",
        "label": "统一预警规则",
        "kind": "json",
        "schema": "versioned_object",
        "expected_schema_version": 1,
    },
    {"key": "alert_profiles", "label": "预警策略模板", "kind": "json", "schema": "item_payload"},
    {"key": "watch_targets", "label": "目标价观察清单", "kind": "json", "schema": "item_payload"},
    {"key": "portfolio_positions", "label": "持仓记录", "kind": "json", "schema": "item_payload"},
    {"key": "portfolio_transactions", "label": "持仓流水", "kind": "json", "schema": "item_payload"},
    {"key": "portfolio_investment_plans", "label": "持仓定投计划", "kind": "json", "schema": "item_payload"},
    {"key": "portfolio_import_backup", "label": "持仓导入备份", "kind": "json", "schema": "plain_json"},
    {"key": "portfolio_alerts", "label": "持仓提醒", "kind": "json", "schema": "item_payload"},
    {"key": "market_cache", "label": "行情缓存", "kind": "json", "schema": "plain_json"},
    {
        "key": "source_metrics",
        "label": "数据源滚动指标",
        "kind": "json",
        "schema": "versioned_object",
        "expected_schema_version": 1,
    },
    {
        "key": "market_quality_history",
        "label": "行情质量历史",
        "kind": "json",
        "schema": "item_payload",
    },
    {
        "key": "market_quality_alert_state",
        "label": "行情质量通知状态",
        "kind": "json",
        "schema": "versioned_object",
        "expected_schema_version": 2,
    },
    {"key": "update_dir", "label": "更新下载目录", "kind": "directory", "schema": "directory"},
    {"key": "exports", "label": "导出目录", "kind": "directory", "schema": "directory"},
    {"key": "news", "label": "新闻缓存", "kind": "json", "schema": "item_payload"},
    {"key": "risk_analysis_history", "label": "风险分析历史", "kind": "json", "schema": "item_payload"},
    {"key": "review_notes", "label": "复盘笔记", "kind": "json", "schema": "item_payload"},
    {"key": "price_history", "label": "价格历史 JSON", "kind": "json", "schema": "item_payload"},
    {
        "key": "daily_digest_state",
        "label": "每日摘要状态",
        "kind": "json",
        "schema": "versioned_object",
        "expected_schema_version": 1,
    },
    {
        "key": "today_overview_state",
        "label": "今日概览查看状态",
        "kind": "json",
        "schema": "versioned_object",
        "expected_schema_version": 1,
    },
    {"key": "price_history_db", "label": "价格历史数据库", "kind": "sqlite", "schema": "sqlite"},
    {"key": "price_history_repair_backup", "label": "历史数据修复恢复点", "kind": "sqlite", "schema": "sqlite"},
    {"key": "alert_log_db", "label": "告警记录数据库", "kind": "sqlite", "schema": "sqlite"},
    {"key": "log", "label": "运行日志", "kind": "log", "schema": "text"},
)


def _base_entry(definition, path):
    return {
        "key": definition["key"],
        "label": definition["label"],
        "path": str(path or ""),
        "kind": definition["kind"],
        "schema": definition["schema"],
    }


def _plain_entry(definition, path):
    entry = _base_entry(definition, path)
    exists = bool(path and os.path.exists(path))
    entry.update({
        "exists": exists,
        "format": definition["schema"],
        "needs_migration": False,
    })
    return entry


def _item_payload_entry(definition, path):
    entry = _base_entry(definition, path)
    entry.update(json_payload_metadata(path))
    return entry


def _versioned_object_entry(definition, path):
    entry = _base_entry(definition, path)
    expected_version = int(definition.get("expected_schema_version") or 1)
    metadata = {
        "exists": False,
        "schema_version": 0,
        "expected_schema_version": expected_version,
        "format": "missing",
        "needs_migration": False,
    }
    if not path or not os.path.exists(path):
        entry.update(metadata)
        return entry
    metadata["exists"] = True
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if not isinstance(payload, dict):
            raise ValueError("versioned object must be a JSON object")
        raw_version = payload.get("schema_version", 0)
        try:
            version = int(raw_version)
        except (TypeError, ValueError):
            version = 0
        metadata.update({
            "schema_version": version,
            "format": "versioned_dict" if version > 0 else "legacy_dict",
            "needs_migration": version != expected_version,
        })
    except (OSError, json.JSONDecodeError, ValueError):
        metadata.update({
            "schema_version": 0,
            "format": "invalid",
            "needs_migration": True,
        })
    entry.update(metadata)
    return entry


def build_storage_manifest(paths):
    paths = paths if isinstance(paths, dict) else {}
    manifest = {}
    definitions_by_key = {item["key"]: item for item in STORAGE_DEFINITIONS}
    for key, path in paths.items():
        definition = definitions_by_key.get(key)
        if not definition:
            definition = {"key": key, "label": key, "kind": "file", "schema": "unknown"}
        if definition["schema"] == "item_payload":
            manifest[key] = _item_payload_entry(definition, path)
        elif definition["schema"] == "versioned_object":
            manifest[key] = _versioned_object_entry(definition, path)
        else:
            manifest[key] = _plain_entry(definition, path)
    return manifest
