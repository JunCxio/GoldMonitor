import json


def test_report_builder_filters_storage_schema_and_rule_runtime_state():
    from goldmonitor.diagnostics_runtime import build_diagnostics_report

    report = json.loads(build_diagnostics_report(
        app_name="金价监控",
        app_version="1.0.9",
        paths={"appdata": "/tmp/data"},
        storage_manifest={
            "settings": {"schema": "versioned_object", "exists": True},
            "log": {"schema": "text", "exists": True},
        },
        fetch_status={},
        source_health={},
        price_history={},
        price_history_maintenance={
            "status": "attention",
            "issues": ["发现历史数据差异。"],
        },
        watch_targets={},
        risk_history_count=0,
        recent_alerts=[],
        alert_rules={"schema_version": 2, "items": [{"state": {"triggered": True}}], "total": 1},
        settings={},
        last_update_status={},
        logs=[],
        background_tasks={
            "summary": {"total": 3, "error": 1, "attention": 1},
            "tasks": [{"name": "news", "state": "error"}],
        },
        health_summary_builder=lambda **kwargs: {"status": "ok"},
    ))

    assert report["data_schemas"] == {
        "settings": {"schema": "versioned_object", "exists": True},
    }
    assert report["alert_rules"]["schema_version"] == 2
    assert "items" not in report["alert_rules"]
    assert report["background_tasks"]["summary"]["attention"] == 1
    assert report["price_history_maintenance"]["status"] == "attention"


def test_clipboard_summary_uses_fallback_status_and_masks_raw_structure():
    from goldmonitor.diagnostics_runtime import build_diagnostics_clipboard_text

    text = build_diagnostics_clipboard_text(
        {
            "generated_at": "2026-07-28T12:00:00",
            "version": "1.0.9",
            "settings": {
                "platform": "macos",
                "risk_assistant_enabled": True,
                "risk_assistant_provider": "deepseek",
                "deepseek_model": "deepseek-v4-pro",
                "floating_price_taskbar_target": r"monitor:\\.\display2",
            },
            "taskbar_price": {
                "reason": "visible",
                "taskbar_index": 1,
                "monitor_name": "DISPLAY2",
                "monitor_width": 2560,
                "monitor_height": 1440,
            },
            "fetch_status": {"message": "行情正常", "status": "ready", "sources": {}},
            "source_health": {"summary": {}, "quality": {"label": "数据可信", "score": 100}},
            "price_history": {"total": 12},
            "market_quality_summary": {
                "stored_events": 8,
                "windows": {
                    "24h": {
                        "availability_pct": 92.5,
                        "incident_count": 2,
                        "abnormal_seconds": 300,
                    },
                    "7d": {
                        "availability_pct": 97.0,
                        "incident_count": 4,
                        "abnormal_seconds": 900,
                    },
                },
            },
            "price_history_maintenance": {
                "status": "attention",
                "database": {
                    "exists": True,
                    "integrity_ok": True,
                    "raw": {
                        "valid": 10,
                        "invalid_timestamp": 1,
                        "missing_price": 2,
                    },
                },
                "comparison": {
                    "rollup_missing": 3,
                    "rollup_mismatched": 4,
                    "rollup_unexpected": 5,
                    "missing_in_database": 6,
                    "supplementable_fields": 7,
                },
                "repair_backup": {
                    "exists": True,
                    "available": True,
                    "action": "rebuild_rollups",
                    "created_at": "2026-08-14T10:30:00",
                },
                "issues": ["汇总数据存在差异。"],
            },
            "paths": {"appdata": "/data", "exports": "/exports"},
            "background_tasks": {
                "failure_alert_threshold": 3,
                "schedule_delay_grace_seconds": 60,
                "summary": {
                    "total": 3,
                    "error": 1,
                    "attention": 1,
                    "delayed": 1,
                    "queue_attention": 1,
                },
                "tasks": [
                    {
                        "name": "news",
                        "label": "资讯刷新",
                        "state": "error",
                        "consecutive_failures": 3,
                        "schedule_delayed": True,
                        "schedule_delay_seconds": 75,
                        "last_message": "资讯刷新失败",
                    },
                    {
                        "name": "notification_retry",
                        "label": "通知重试",
                        "state": "disabled",
                        "consecutive_failures": 0,
                        "last_message": "自动重试未开启",
                        "queue": {
                            "available": True,
                            "enabled": False,
                            "pending_count": 2,
                            "eligible_count": 1,
                            "exhausted_count": 1,
                            "expired_count": 1,
                            "non_retryable_count": 1,
                            "stopped_count": 3,
                        },
                    },
                ],
            },
        },
        default_settings={
            "risk_assistant_provider": "deepseek",
            "deepseek_model": "deepseek-v4-pro",
            "openai_compatible_model": "",
        },
        platform_name="darwin",
        kline_count=6,
        fallback_export_status={"directory": {"ok": True, "path": "/exports"}, "last_export": {}},
        fallback_update_status={},
    )

    assert "5 分钟 K 线样本数: 6" in text
    assert "行情质量: 数据可信 / 100分" in text
    assert "已保存质量状态段: 8" in text
    assert "最近 24 小时: 可信区间占比 92.5%，异常 2 段，异常时长 300 秒" in text
    assert "最近 7 天: 可信区间占比 97.0%，异常 4 段，异常时长 900 秒" in text
    assert "目录状态: 可写" in text
    assert "任务栏选择: 固定到 DISPLAY2" in text
    assert "实际显示器: DISPLAY2 / 2560×1440" in text
    assert "后台任务" in text
    assert "需要处理: 1" in text
    assert "调度延迟: 1" in text
    assert "延迟阈值: 超过计划时间 60 秒" in text
    assert "资讯刷新: 失败，连续失败 3 次，调度延迟 75 秒" in text
    assert "通知重试队列: 待重试 2 条，可立即处理 1 条，达到上限 1 条，已过期 1 条，不可重试 1 条，自动重试关闭" in text
    assert "后台任务提示" in text
    assert "历史数据维护" in text
    assert "状态: 发现可处理问题" in text
    assert "SQLite 数据库: 完整性检查通过" in text
    assert "有效 10 条，无效时间 1 条，缺少价格 2 条" in text
    assert "缺失 3 个，不一致 4 个，多余 5 个" in text
    assert "时间点 6 个，空缺字段 7 个" in text
    assert "重建汇总数据前创建" in text
    assert "问题 1: 汇总数据存在差异。" in text


def test_clipboard_summary_accepts_unknown_taskbar_target():
    from goldmonitor.diagnostics_runtime import build_diagnostics_clipboard_text

    text = build_diagnostics_clipboard_text(
        {
            "settings": {
                "floating_price_taskbar_target": "custom-target",
            },
        },
        default_settings={
            "risk_assistant_provider": "deepseek",
            "deepseek_model": "deepseek-v4-pro",
            "openai_compatible_model": "",
        },
        platform_name="win32",
        kline_count=0,
        fallback_export_status={},
        fallback_update_status={},
    )

    assert "任务栏选择: custom-target" in text
