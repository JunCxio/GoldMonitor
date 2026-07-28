import threading
import time

from flask import request
from flask_socketio import emit


def register_risk_analysis_handlers(
    socketio,
    *,
    get_settings_snapshot,
    valid_providers,
    build_error_payload,
    market_data_error,
    build_context,
    build_snapshot,
    find_recent_cache,
    get_last_started,
    set_last_started,
    analysis_lock,
    run_analysis,
    add_history_entry,
    get_history_state,
    clear_history_state,
    fetch_model_options,
    test_model_availability,
    monotonic_factory=time.monotonic,
):
    @socketio.on("request_risk_analysis")
    def on_request_risk_analysis(data=None):
        settings = get_settings_snapshot()
        if not settings.get("risk_assistant_enabled", True):
            emit("risk_analysis_error", build_error_payload(
                "风险分析助手已关闭，请先在设置中启用。",
                settings,
            ))
            return

        provider = settings.get("risk_assistant_provider", "deepseek")
        if provider not in valid_providers:
            emit("risk_analysis_error", build_error_payload(
                "暂不支持当前模型提供商。",
                settings,
            ))
            return

        provider_key = (
            settings.get("deepseek_api_key")
            if provider == "deepseek"
            else settings.get("openai_compatible_api_key")
        )
        if not provider_key:
            emit("risk_analysis_error", build_error_payload(
                "请先在设置中配置当前模型提供商的 API Key。",
                settings,
            ))
            return

        data_error = market_data_error()
        if data_error:
            emit("risk_analysis_error", build_error_payload(data_error, settings))
            return

        trigger = data.get("trigger") if isinstance(data, dict) else None
        force = bool(data.get("force")) if isinstance(data, dict) else False
        context = build_context(
            trigger=trigger,
            depth=settings.get("risk_assistant_depth", "standard"),
        )
        snapshot = build_snapshot(context)
        cache_minutes = settings.get("risk_assistant_cache_minutes", 0)
        if not force:
            cached = find_recent_cache(snapshot, cache_minutes)
            if cached:
                emit("risk_analysis_cache_hit", {
                    "ok": True,
                    "provider": cached.get("provider"),
                    "model": cached.get("model"),
                    "content": cached.get("content"),
                    "structured": cached.get("structured", {}),
                    "usage": cached.get("usage"),
                    "snapshot": cached.get("snapshot", snapshot),
                    "history_entry": cached,
                    "cache_age_seconds": cached.get("cache_age_seconds", 0),
                    "trigger": trigger,
                    "message": "已找到最近同一行情分析，可直接查看，也可以选择重新分析。",
                })
                return

        cooldown = settings.get("risk_assistant_cooldown_seconds", 0)
        now_monotonic = monotonic_factory()
        last_started = get_last_started()
        if cooldown and last_started and now_monotonic - last_started < cooldown:
            remaining = max(1, int(cooldown - (now_monotonic - last_started)))
            emit("risk_analysis_error", build_error_payload(
                f"分析冷却中，请 {remaining} 秒后再试。",
                settings,
                snapshot,
            ))
            return

        if not analysis_lock.acquire(blocking=False):
            emit("risk_analysis_error", build_error_payload(
                "已有风险分析正在进行，请稍后再试。",
                settings,
                snapshot,
            ))
            return

        set_last_started(now_monotonic)
        sid = request.sid
        emit("risk_analysis_status", {"running": True, "message": "正在生成风险分析..."})

        def analyze():
            try:
                result, error = run_analysis(settings, context)
                if error:
                    socketio.emit(
                        "risk_analysis_error",
                        build_error_payload(error, settings, snapshot),
                        room=sid,
                    )
                    return
                history_entry = add_history_entry(result, snapshot)
                socketio.emit("risk_analysis_result", {
                    "ok": True,
                    "provider": result.get("provider"),
                    "model": result.get("model"),
                    "content": result.get("content"),
                    "structured": result.get("structured", {}),
                    "usage": result.get("usage"),
                    "snapshot": snapshot,
                    "history_entry": history_entry,
                }, room=sid)
                socketio.emit(
                    "risk_analysis_history_updated",
                    get_history_state(),
                    room=sid,
                )
            finally:
                socketio.emit(
                    "risk_analysis_status",
                    {"running": False, "message": ""},
                    room=sid,
                )
                analysis_lock.release()

        threading.Thread(target=analyze, daemon=True).start()

    @socketio.on("get_risk_model_options")
    def on_get_risk_model_options(data=None):
        settings = get_settings_snapshot()
        provider = settings.get("risk_assistant_provider", "deepseek")
        if isinstance(data, dict) and data.get("provider") in valid_providers:
            provider = data.get("provider")
        emit("risk_model_options_updated", fetch_model_options(settings, provider))

    @socketio.on("test_risk_model")
    def on_test_risk_model():
        emit("risk_model_test_result", test_model_availability(get_settings_snapshot()))

    @socketio.on("get_risk_analysis_history")
    def on_get_risk_analysis_history():
        emit("risk_analysis_history_updated", get_history_state())

    @socketio.on("clear_risk_analysis_history")
    def on_clear_risk_analysis_history():
        emit("risk_analysis_history_updated", clear_history_state())
