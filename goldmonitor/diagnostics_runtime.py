import json
from datetime import datetime


def alert_rules_diagnostics(state):
    return {
        "schema_version": state.get("schema_version", 0),
        "total": state.get("total", 0),
        "summary": dict(state.get("summary") or {}),
        "by_kind": dict(state.get("by_kind") or {}),
        "migration": dict(state.get("migration") or {}),
        "invalid_count": state.get("invalid_count", 0),
        "load_error": state.get("load_error", ""),
    }


def build_diagnostics_report(
    *,
    app_name,
    app_version,
    paths,
    storage_manifest,
    fetch_status,
    source_health,
    price_history,
    watch_targets,
    risk_history_count,
    recent_alerts,
    alert_rules,
    settings,
    last_update_status,
    logs,
    health_summary_builder,
    now_factory=datetime.now,
):
    data_schemas = {
        key: dict(item)
        for key, item in sorted(storage_manifest.items())
        if item.get("schema") in {"item_payload", "versioned_object"}
    }
    report = {
        "app": app_name,
        "version": app_version,
        "generated_at": now_factory().isoformat(timespec="seconds"),
        "paths": paths,
        "health_summary": health_summary_builder(
            fetch_status=fetch_status,
            source_health=source_health,
            price_history=price_history,
            watch_targets=watch_targets,
            risk_history_count=risk_history_count,
            recent_alerts=recent_alerts,
            paths=paths,
            storage_manifest=storage_manifest,
        ),
        "storage_manifest": storage_manifest,
        "data_schemas": data_schemas,
        "settings": settings,
        "fetch_status": fetch_status,
        "source_health": source_health,
        "price_history": price_history,
        "watch_targets": watch_targets,
        "alert_rules": alert_rules_diagnostics(alert_rules),
        "risk_history_count": risk_history_count,
        "last_update_status": last_update_status,
        "recent_alerts": recent_alerts,
        "logs": logs,
    }
    return json.dumps(report, ensure_ascii=False, indent=2)


def diagnostics_report_payload(report):
    if isinstance(report, dict):
        return report
    if not isinstance(report, str):
        return {}
    try:
        payload = json.loads(report)
    except (TypeError, json.JSONDecodeError):
        return {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, json.JSONDecodeError):
            return {}
    return payload if isinstance(payload, dict) else {}


def diagnostics_value(value, empty="未记录"):
    if isinstance(value, bool):
        return "是" if value else "否"
    if value is None or value == "":
        return empty
    return str(value)


def diagnostics_source_label(source):
    source = source if isinstance(source, dict) else {}
    name = str(source.get("source") or "").strip() or "未记录"
    suffixes = []
    if source.get("cached"):
        suffixes.append("缓存")
    if source.get("ok") is False:
        suffixes.append("异常")
    error = str(source.get("error") or "").strip()
    text = name
    if suffixes:
        text += "（" + "、".join(suffixes) + "）"
    if error:
        text += "，错误：" + error
    return text


def build_diagnostics_clipboard_text(
    report,
    *,
    default_settings,
    platform_name,
    kline_count,
    fallback_export_status,
    fallback_update_status,
):
    payload = diagnostics_report_payload(report)
    fetch_status = payload.get("fetch_status") if isinstance(payload.get("fetch_status"), dict) else {}
    source_health = payload.get("source_health") if isinstance(payload.get("source_health"), dict) else {}
    quality = source_health.get("quality") if isinstance(source_health.get("quality"), dict) else {}
    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    taskbar_price = payload.get("taskbar_price") if isinstance(payload.get("taskbar_price"), dict) else {}
    price_history = payload.get("price_history") if isinstance(payload.get("price_history"), dict) else {}
    paths = payload.get("paths") if isinstance(payload.get("paths"), dict) else {}
    sources = fetch_status.get("sources") if isinstance(fetch_status.get("sources"), dict) else {}
    source_summary = source_health.get("summary") if isinstance(source_health.get("summary"), dict) else {}
    export_status = payload.get("export_status") if isinstance(payload.get("export_status"), dict) else fallback_export_status
    export_dir_status = export_status.get("directory") if isinstance(export_status.get("directory"), dict) else {}
    last_export = export_status.get("last_export") if isinstance(export_status.get("last_export"), dict) else {}
    update_status = payload.get("last_update_status") if isinstance(payload.get("last_update_status"), dict) else fallback_update_status
    rules_state = payload.get("alert_rules") if isinstance(payload.get("alert_rules"), dict) else {}
    update_message = update_status.get("message") or ("尚未检查更新" if not update_status else "更新状态未知")
    logs = payload.get("logs")
    log_count = len(logs) if isinstance(logs, list) else len(str(logs or "").splitlines()) if logs else 0

    provider = settings.get("risk_assistant_provider") or default_settings["risk_assistant_provider"]
    if provider == "deepseek":
        model = settings.get("deepseek_model") or default_settings["deepseek_model"]
    else:
        model = settings.get("openai_compatible_model") or default_settings["openai_compatible_model"]
    risk_enabled = "开启" if settings.get("risk_assistant_enabled") else "关闭"
    quality_label = quality.get("label") or "未评估"
    quality_score = quality.get("score")
    quality_text = f"{quality_label} / {quality_score}分" if quality_score is not None else quality_label
    quality_reasons = quality.get("reasons") if isinstance(quality.get("reasons"), list) else []
    export_dir_ok = export_dir_status.get("ok")
    export_dir_state = "可写" if export_dir_ok is True else "不可写" if export_dir_ok is False else "未检查"
    last_export_ok = last_export.get("ok")
    last_export_state = "成功" if last_export_ok is True else "失败" if last_export_ok is False else "未记录"
    windows_mode_labels = {
        "floating": "仅悬浮条",
        "taskbar": "仅任务栏价格",
        "both": "悬浮条和任务栏价格",
    }
    windows_mode = settings.get("floating_price_windows_mode", "floating")
    taskbar_target = str(
        settings.get("floating_price_taskbar_target") or "auto"
    )
    if taskbar_target == "auto":
        taskbar_target_label = "自动选择（优先主任务栏）"
    elif taskbar_target == "primary":
        taskbar_target_label = "主任务栏"
    elif taskbar_target.startswith("secondary:"):
        taskbar_target_label = f"副任务栏 {taskbar_target.split(':', 1)[1]}"
    elif taskbar_target.startswith("monitor:"):
        monitor_device = taskbar_target.split(":", 1)[1]
        monitor_name = monitor_device.rsplit("\\", 1)[-1].upper()
        taskbar_target_label = f"固定到 {monitor_name}"
    else:
        taskbar_target_label = value(taskbar_target)
    actual_monitor = taskbar_price.get("monitor_name") or taskbar_price.get(
        "monitor_device"
    )
    monitor_width = taskbar_price.get("monitor_width")
    monitor_height = taskbar_price.get("monitor_height")
    actual_monitor_label = diagnostics_value(actual_monitor)
    if actual_monitor and monitor_width and monitor_height:
        actual_monitor_label = f"{actual_monitor} / {monitor_width}×{monitor_height}"

    value = diagnostics_value
    lines = [
        "GoldMonitor 诊断摘要",
        f"生成时间: {value(payload.get('generated_at'))}",
        f"版本: {value(payload.get('version'))}",
        f"运行平台: {value(settings.get('platform') or platform_name)}",
        "",
        "行情状态",
        f"- 状态: {value(fetch_status.get('message'))}（{value(fetch_status.get('status'))}）",
        f"- 金价源: {diagnostics_source_label(sources.get('gold'))}",
        f"- 汇率源: {diagnostics_source_label(sources.get('forex'))}",
        f"- 行情质量: {quality_text}",
        f"- 数据源统计: 正常 {source_summary.get('ok', 0)}，异常 {source_summary.get('failed', 0)}，缓存 {source_summary.get('cached', 0)}",
        f"- 历史样本数: {price_history.get('total', 0)}",
        f"- 5 分钟 K 线样本数: {kline_count}",
        "",
        "风险分析",
        f"- 状态: {risk_enabled}",
        f"- 模型: {provider} / {model}",
        f"- 历史记录数: {payload.get('risk_history_count', 0)}",
        "",
        "预警规则",
        f"- 文件版本: {value(rules_state.get('schema_version'))}",
        f"- 规则数量: {rules_state.get('total', 0)}",
        f"- 无效规则: {rules_state.get('invalid_count', 0)}",
        f"- 迁移状态: {'已完成' if (rules_state.get('migration') or {}).get('completed') else '未完成'}",
        f"- 加载错误: {value(rules_state.get('load_error'), '无')}",
        "",
        "更新状态",
        f"- 当前版本: {value(update_status.get('current_version') or payload.get('version'))}",
        f"- 最新版本: {value(update_status.get('latest_version'))}",
        f"- 检查状态: {value(update_status.get('state'), '尚未检查')}",
        f"- 检查时间: {value(update_status.get('checked_at'))}",
        f"- 状态说明: {update_message}",
        "",
        "悬浮条与任务栏",
        f"- 状态: {'开启' if settings.get('floating_price_enabled') else '关闭'}",
        f"- Windows 显示位置: {windows_mode_labels.get(windows_mode, value(windows_mode))}",
        f"- 任务栏选择: {taskbar_target_label}",
        f"- 置顶: {'开启' if settings.get('floating_price_always_on_top') else '关闭'}",
        f"- 全屏自动隐藏: {'开启' if settings.get('floating_price_hide_on_fullscreen', True) else '关闭'}",
        f"- 位置锁定: {'开启' if settings.get('floating_price_lock_position') else '关闭'}",
        f"- 显示模式: {value(settings.get('floating_price_display_mode'))}",
        f"- 透明度: {value(settings.get('floating_price_opacity'))}",
        f"- 任务栏窗口状态: {value(taskbar_price.get('reason'))}",
        f"- 实际任务栏索引: {value(taskbar_price.get('taskbar_index'))}",
        f"- 实际显示器: {actual_monitor_label}",
        f"- 任务栏窗口区域: {value(taskbar_price.get('bounds'))}",
        "",
        "存储与日志",
        f"- 导出目录: {value(paths.get('exports'))}",
        f"- 数据目录: {value(paths.get('appdata'))}",
        f"- 最近日志: {log_count} 行",
        "",
        "导出状态",
        f"- 导出目录: {value(export_dir_status.get('path') or paths.get('exports'))}",
        f"- 目录状态: {export_dir_state}",
        f"- 最近导出: {last_export_state}",
    ]
    if last_export_ok is True:
        lines.append(f"- 最近保存路径: {value(last_export.get('saved_path'))}")
    elif last_export_ok is False:
        lines.append(f"- 最近失败原因: {value(last_export.get('message'))}")
    if quality_reasons:
        lines.extend(["", "数据质量提示", *[f"- {item}" for item in quality_reasons[:5]]])
    lines.extend([
        "",
        "排查建议",
        "- 若行情状态异常，先点击重新获取行情，并检查网络或数据源状态。",
        "- 若风险分析失败，先在设置中测试模型，并确认 API Key、模型和接口地址可用。",
        "- 如需完整原始结构，请使用“生成诊断”导出 JSON 文件。",
    ])
    return "\n".join(lines)


class DiagnosticsRuntime:
    def __init__(
        self,
        runtime,
        *,
        app_name,
        app_version,
        paths_builder,
        storage_manifest_builder,
        get_fetch_status,
        get_source_health,
        get_price_history,
        get_watch_targets,
        get_risk_history,
        get_alert_rules,
        get_settings,
        get_update_status,
        read_logs,
        health_summary_builder,
        get_export_status,
        default_settings,
        platform_name,
        now_factory=datetime.now,
    ):
        self.runtime = runtime
        self.app_name = app_name
        self.app_version = app_version
        self.paths_builder = paths_builder
        self.storage_manifest_builder = storage_manifest_builder
        self.get_fetch_status = get_fetch_status
        self.get_source_health = get_source_health
        self.get_price_history = get_price_history
        self.get_watch_targets = get_watch_targets
        self.get_risk_history = get_risk_history
        self.get_alert_rules = get_alert_rules
        self.get_settings = get_settings
        self.get_update_status = get_update_status
        self.read_logs = read_logs
        self.health_summary_builder = health_summary_builder
        self.get_export_status = get_export_status
        self.default_settings = default_settings
        self.platform_name = platform_name
        self.now_factory = now_factory

    def build_report(self):
        paths = self.paths_builder()
        risk_history = self.get_risk_history()
        report = build_diagnostics_report(
            app_name=self.app_name,
            app_version=self.app_version,
            paths=paths,
            storage_manifest=self.storage_manifest_builder(paths),
            fetch_status=self.get_fetch_status(),
            source_health=self.get_source_health(),
            price_history=self.get_price_history(limit=120),
            watch_targets=self.get_watch_targets(),
            risk_history_count=len(risk_history.get("items", [])),
            recent_alerts=list(self.runtime.alert_log[-20:]),
            alert_rules=self.get_alert_rules(),
            settings=self.get_settings(),
            last_update_status=self.get_update_status(),
            logs=self.read_logs(),
            health_summary_builder=self.health_summary_builder,
            now_factory=self.now_factory,
        )
        payload = json.loads(report)
        payload["export_status"] = self.get_export_status()
        payload["taskbar_price"] = dict(
            getattr(self.runtime, "taskbar_layout_state", {}) or {}
        )
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def build_clipboard_text(self, report=None):
        with self.runtime.lock:
            kline_count = len(self.runtime.klines_5min)
        return build_diagnostics_clipboard_text(
            self.build_report() if report is None else report,
            default_settings=self.default_settings,
            platform_name=self.platform_name,
            kline_count=kline_count,
            fallback_export_status=self.get_export_status(),
            fallback_update_status=self.get_update_status(),
        )
