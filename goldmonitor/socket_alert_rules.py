import logging

from flask_socketio import emit


def register_alert_rule_handlers(
    socketio,
    *,
    alert_rule_error,
    alert_rule_store_error,
    get_alert_rules_state,
    upsert_alert_rule_entry,
    delete_alert_rule_entry,
    toggle_alert_rule_entry,
    duplicate_alert_rule_entry,
    reset_alert_rule_entry,
    batch_update_alert_rules_entry,
    build_alert_rule_insight,
    build_alert_rule_simulation,
    broadcast_alert_rule_views,
    find_alert_rule,
):
    @socketio.on("get_alert_rules")
    def on_get_alert_rules():
        state = get_alert_rules_state()
        emit("alert_rules_updated", state)
        emit("alert_rule_migration_status", {
            "migration": state.get("migration", {}),
            "invalid_count": state.get("invalid_count", 0),
            "load_error": state.get("load_error", ""),
        })

    @socketio.on("save_alert_rule")
    def on_save_alert_rule(data=None):
        try:
            state, rule = upsert_alert_rule_entry(data)
        except (ValueError, alert_rule_error) as exc:
            emit("alert_rule_error", {"message": str(exc)})
            return
        except alert_rule_store_error:
            emit("alert_rule_error", {"message": "预警规则保存失败，请检查配置目录权限。"})
            return
        emit("alert_rule_saved", {"ok": True, "rule": rule})
        broadcast_alert_rule_views(state)

    @socketio.on("delete_alert_rule")
    def on_delete_alert_rule(data=None):
        rule_id = data.get("id") if isinstance(data, dict) else ""
        try:
            deleted, state = delete_alert_rule_entry(rule_id)
        except alert_rule_store_error:
            emit("alert_rule_error", {"message": "预警规则删除失败，请检查配置目录权限。"})
            return
        if not deleted:
            emit("alert_rule_error", {"message": "未找到预警规则。"})
            return
        emit("alert_rule_deleted", {"ok": True, "id": str(rule_id or "")})
        broadcast_alert_rule_views(state)

    @socketio.on("toggle_alert_rule")
    def on_toggle_alert_rule(data=None):
        rule_id = data.get("id") if isinstance(data, dict) else ""
        enabled = data.get("enabled") if isinstance(data, dict) else None
        try:
            updated, state = toggle_alert_rule_entry(rule_id, enabled)
        except alert_rule_store_error:
            emit("alert_rule_error", {"message": "预警规则状态保存失败，请检查配置目录权限。"})
            return
        if not updated:
            emit("alert_rule_error", {"message": "未找到预警规则。"})
            return
        emit("alert_rule_toggled", {
            "ok": True,
            "id": str(rule_id or ""),
            "enabled": bool((find_alert_rule(rule_id) or {}).get("enabled")),
        })
        broadcast_alert_rule_views(state)

    @socketio.on("duplicate_alert_rule")
    def on_duplicate_alert_rule(data=None):
        rule_id = data.get("id") if isinstance(data, dict) else ""
        try:
            duplicated, state, rule = duplicate_alert_rule_entry(rule_id)
        except alert_rule_store_error:
            emit("alert_rule_error", {"message": "预警规则复制失败，请检查配置目录权限。"})
            return
        if not duplicated:
            emit("alert_rule_error", {"message": "未找到预警规则。"})
            return
        emit("alert_rule_duplicated", {"ok": True, "rule": rule})
        broadcast_alert_rule_views(state)

    @socketio.on("reset_alert_rule_state")
    def on_reset_alert_rule_state(data=None):
        rule_id = data.get("id") if isinstance(data, dict) else ""
        try:
            reset, state = reset_alert_rule_entry(rule_id)
        except alert_rule_store_error:
            emit("alert_rule_error", {"message": "预警规则重置失败，请检查配置目录权限。"})
            return
        if not reset:
            emit("alert_rule_error", {"message": "未找到预警规则。"})
            return
        emit("alert_rule_reset", {"ok": True, "id": str(rule_id or "")})
        broadcast_alert_rule_views(state)

    @socketio.on("batch_update_alert_rules")
    def on_batch_update_alert_rules(data=None):
        data = data if isinstance(data, dict) else {}
        action = data.get("action")
        rule_ids = data.get("ids")
        try:
            state, affected_ids = batch_update_alert_rules_entry(rule_ids, action)
        except alert_rule_error as exc:
            emit("alert_rule_error", {"message": str(exc)})
            return
        except alert_rule_store_error:
            emit("alert_rule_error", {"message": "批量保存预警规则失败，请检查配置目录权限。"})
            return
        emit("alert_rules_batch_updated", {
            "ok": True,
            "action": str(action or ""),
            "ids": affected_ids,
            "count": len(affected_ids),
        })
        broadcast_alert_rule_views(state)

    @socketio.on("get_alert_rule_insight")
    def on_get_alert_rule_insight(data=None):
        data = data if isinstance(data, dict) else {}
        insight = build_alert_rule_insight(data.get("id"), days=data.get("days", 30))
        if not insight:
            emit("alert_rule_error", {"message": "未找到预警规则。"})
            return
        emit("alert_rule_insight", insight)

    @socketio.on("simulate_alert_rule")
    def on_simulate_alert_rule(data=None):
        data = data if isinstance(data, dict) else {}
        request_id = str(data.get("request_id") or "")[:80]
        try:
            result = build_alert_rule_simulation(data.get("rule"), days=data.get("days", 30))
        except alert_rule_error as exc:
            emit("alert_rule_simulation_error", {"request_id": request_id, "message": str(exc)})
            return
        except Exception:
            logging.exception("预警规则历史模拟失败")
            emit("alert_rule_simulation_error", {
                "request_id": request_id,
                "message": "历史模拟失败，请检查持仓流水与历史行情后重试。",
            })
            return
        emit("alert_rule_simulation", {"request_id": request_id, **result})
