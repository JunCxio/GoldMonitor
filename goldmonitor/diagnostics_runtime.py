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
    price_history_maintenance,
    watch_targets,
    risk_history_count,
    recent_alerts,
    alert_rules,
    settings,
    last_update_status,
    logs,
    health_summary_builder,
    background_tasks=None,
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
            background_tasks=background_tasks,
        ),
        "storage_manifest": storage_manifest,
        "data_schemas": data_schemas,
        "settings": settings,
        "fetch_status": fetch_status,
        "source_health": source_health,
        "price_history": price_history,
        "price_history_maintenance": price_history_maintenance,
        "watch_targets": watch_targets,
        "alert_rules": alert_rules_diagnostics(alert_rules),
        "background_tasks": background_tasks or {},
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


def diagnostics_task_state_label(state):
    return {
        "waiting": "等待首次运行",
        "running": "运行中",
        "ok": "正常",
        "error": "失败",
        "disabled": "停用",
        "idle": "已检查",
    }.get(str(state or ""), diagnostics_value(state, "未知"))


def diagnostics_history_maintenance_status_label(status):
    return {
        "healthy": "数据状态正常",
        "attention": "发现可处理问题",
        "unavailable": "数据库暂不可维护",
        "empty": "尚无历史数据",
    }.get(str(status or ""), diagnostics_value(status, "未检查"))


def diagnostics_history_repair_action_label(action):
    return {
        "clean_invalid_records": "清理无效明细",
        "rebuild_rollups": "重建汇总数据",
        "sync_json_and_rebuild": "同步 JSON 并重建",
    }.get(str(action or ""), diagnostics_value(action, "未知操作"))


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
    background_tasks = payload.get("background_tasks") if isinstance(payload.get("background_tasks"), dict) else {}
    scheduled_tasks = background_tasks.get("tasks") if isinstance(background_tasks.get("tasks"), list) else []
    task_summary = background_tasks.get("summary") if isinstance(background_tasks.get("summary"), dict) else {}
    history_maintenance = payload.get("price_history_maintenance") if isinstance(payload.get("price_history_maintenance"), dict) else {}
    history_database = history_maintenance.get("database") if isinstance(history_maintenance.get("database"), dict) else {}
    history_raw = history_database.get("raw") if isinstance(history_database.get("raw"), dict) else {}
    history_comparison = history_maintenance.get("comparison") if isinstance(history_maintenance.get("comparison"), dict) else {}
    history_backup = history_maintenance.get("repair_backup") if isinstance(history_maintenance.get("repair_backup"), dict) else {}
    history_issues = history_maintenance.get("issues") if isinstance(history_maintenance.get("issues"), list) else []
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
    value = diagnostics_value
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
    ]
    if history_maintenance:
        if not history_database.get("exists"):
            database_state = "尚未创建"
        elif history_database.get("integrity_ok"):
            database_state = "完整性检查通过"
        else:
            database_state = "完整性检查未通过"
        if history_backup.get("available"):
            backup_state = (
                "可用，"
                f"{diagnostics_history_repair_action_label(history_backup.get('action'))}前创建，"
                f"时间 {value(history_backup.get('created_at'))}"
            )
        elif history_backup.get("exists"):
            backup_state = "文件存在但不可恢复"
        else:
            backup_state = "无"
        lines.extend([
            "",
            "历史数据维护",
            "- 状态: "
            + diagnostics_history_maintenance_status_label(
                history_maintenance.get("status")
            ),
            f"- SQLite 数据库: {database_state}",
            "- 数据库明细: "
            f"有效 {int(history_raw.get('valid') or 0)} 条，"
            f"无效时间 {int(history_raw.get('invalid_timestamp') or 0)} 条，"
            f"缺少价格 {int(history_raw.get('missing_price') or 0)} 条",
            "- 汇总差异: "
            f"缺失 {int(history_comparison.get('rollup_missing') or 0)} 个，"
            f"不一致 {int(history_comparison.get('rollup_mismatched') or 0)} 个，"
            f"多余 {int(history_comparison.get('rollup_unexpected') or 0)} 个",
            "- JSON 可补充: "
            f"时间点 {int(history_comparison.get('missing_in_database') or 0)} 个，"
            f"空缺字段 {int(history_comparison.get('supplementable_fields') or 0)} 个",
            f"- 最近修复恢复点: {backup_state}",
        ])
        if history_issues:
            lines.extend(
                f"- 问题 {index}: {value(issue)}"
                for index, issue in enumerate(history_issues[:5], start=1)
            )
    lines.extend([
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
        "后台任务",
        f"- 任务数量: {task_summary.get('total', len(scheduled_tasks))}",
        f"- 最近失败: {task_summary.get('error', 0)}",
        f"- 需要处理: {task_summary.get('attention', 0)}",
        f"- 调度延迟: {task_summary.get('delayed', 0)}",
        f"- 提醒阈值: 连续失败 {background_tasks.get('failure_alert_threshold', 3)} 次",
        f"- 延迟阈值: 超过计划时间 {background_tasks.get('schedule_delay_grace_seconds', 60)} 秒",
    ])
    for task in scheduled_tasks:
        if not isinstance(task, dict):
            continue
        label = value(task.get("label") or task.get("name"), "未命名任务")
        task_state = diagnostics_task_state_label(task.get("state"))
        failures = int(task.get("consecutive_failures") or 0)
        delay_seconds = int(task.get("schedule_delay_seconds") or 0)
        message = value(task.get("last_message"), "等待首次运行")
        schedule_note = (
            f"，调度延迟 {delay_seconds} 秒"
            if task.get("schedule_delayed")
            else ""
        )
        lines.append(
            f"- {label}: {task_state}，连续失败 {failures} 次{schedule_note}，最近结果：{message}"
        )
        queue = task.get("queue") if isinstance(task.get("queue"), dict) else {}
        if task.get("name") == "notification_retry" and queue:
            if queue.get("available") is False:
                lines.append("- 通知重试队列: 状态读取失败")
            else:
                lines.append(
                    "- 通知重试队列: "
                    f"待重试 {int(queue.get('pending_count') or 0)} 条，"
                    f"可立即处理 {int(queue.get('eligible_count') or 0)} 条，"
                    f"达到上限 {int(queue.get('exhausted_count') or 0)} 条，"
                    f"已过期 {int(queue.get('expired_count') or 0)} 条，"
                    f"不可重试 {int(queue.get('non_retryable_count') or 0)} 条，"
                    f"自动重试{'开启' if queue.get('enabled') else '关闭'}"
                )
    lines.extend([
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
    ])
    if last_export_ok is True:
        lines.append(f"- 最近保存路径: {value(last_export.get('saved_path'))}")
    elif last_export_ok is False:
        lines.append(f"- 最近失败原因: {value(last_export.get('message'))}")
    if quality_reasons:
        lines.extend(["", "数据质量提示", *[f"- {item}" for item in quality_reasons[:5]]])
    if (
        int(task_summary.get("attention") or 0)
        or int(task_summary.get("delayed") or 0)
        or int(task_summary.get("queue_attention") or 0)
    ):
        lines.extend([
            "",
            "后台任务提示",
            "- 打开设置中的“运维与数据”，查看异常任务的最近结果、下次运行时间并执行立即检查。",
        ])
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
        get_price_history_maintenance,
        get_watch_targets,
        get_risk_history,
        get_alert_rules,
        get_settings,
        get_update_status,
        read_logs,
        health_summary_builder,
        get_export_status,
        get_background_tasks,
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
        self.get_price_history_maintenance = get_price_history_maintenance
        self.get_watch_targets = get_watch_targets
        self.get_risk_history = get_risk_history
        self.get_alert_rules = get_alert_rules
        self.get_settings = get_settings
        self.get_update_status = get_update_status
        self.read_logs = read_logs
        self.health_summary_builder = health_summary_builder
        self.get_export_status = get_export_status
        self.get_background_tasks = get_background_tasks
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
            price_history_maintenance=self.get_price_history_maintenance(),
            watch_targets=self.get_watch_targets(),
            risk_history_count=len(risk_history.get("items", [])),
            recent_alerts=list(self.runtime.alert_log[-20:]),
            alert_rules=self.get_alert_rules(),
            settings=self.get_settings(),
            last_update_status=self.get_update_status(),
            logs=self.read_logs(),
            health_summary_builder=self.health_summary_builder,
            background_tasks=self.get_background_tasks(),
            now_factory=self.now_factory,
        )
        payload = json.loads(report)
        payload["market_observation"] = dict(
            getattr(self.runtime, "market_observation", {}) or {}
        )
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
