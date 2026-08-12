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
            "paths": {"appdata": "/data", "exports": "/exports"},
            "background_tasks": {
                "failure_alert_threshold": 3,
                "summary": {"total": 3, "error": 1, "attention": 1},
                "tasks": [{
                    "label": "资讯刷新",
                    "state": "error",
                    "consecutive_failures": 3,
                    "last_message": "资讯刷新失败",
                }],
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
    assert "目录状态: 可写" in text
    assert "任务栏选择: 固定到 DISPLAY2" in text
    assert "实际显示器: DISPLAY2 / 2560×1440" in text
    assert "后台任务" in text
    assert "需要处理: 1" in text
    assert "资讯刷新: 失败，连续失败 3 次" in text
    assert "后台任务提示" in text
