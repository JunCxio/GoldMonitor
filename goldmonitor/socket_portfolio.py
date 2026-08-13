import logging
import sqlite3

from flask_socketio import emit


def register_portfolio_handlers(
    socketio,
    *,
    build_portfolio_state,
    upsert_portfolio_position,
    delete_portfolio_position,
    upsert_portfolio_transaction,
    delete_portfolio_transaction,
    preview_import_portfolio_transactions_csv,
    import_portfolio_transactions_csv,
    undo_portfolio_import,
    portfolio_import_backup_state,
    get_portfolio_import_backup,
    upsert_portfolio_alert,
    reset_portfolio_alert,
    delete_portfolio_alert,
    get_portfolio_investment_plan_state,
    preview_portfolio_investment_schedule,
    upsert_portfolio_investment_plan,
    delete_portfolio_investment_plan,
    toggle_portfolio_investment_plan,
    skip_portfolio_investment_plan,
    execute_portfolio_investment_plan,
    build_portfolio_investment_executions_csv,
    broadcast_alert_rule_views,
    build_portfolio_csv,
    save_export_file,
    build_export_error_payload,
    build_portfolio_analytics_state,
    now_factory,
):
    @socketio.on("get_portfolio")
    def on_get_portfolio():
        emit("portfolio_updated", build_portfolio_state())

    @socketio.on("save_portfolio_position")
    def on_save_portfolio_position(data):
        try:
            state = upsert_portfolio_position(data)
        except ValueError as exc:
            emit("portfolio_error", {"message": str(exc)})
            return
        except OSError:
            emit("portfolio_error", {"message": "持仓保存失败，请检查配置目录权限。"})
            return
        socketio.emit("portfolio_updated", state)

    @socketio.on("delete_portfolio_position")
    def on_delete_portfolio_position(data=None):
        position_id = data.get("id") if isinstance(data, dict) else None
        try:
            ok, state = delete_portfolio_position(position_id)
        except OSError:
            emit("portfolio_error", {"message": "持仓保存失败，请检查配置目录权限。"})
            return
        if not ok:
            emit("portfolio_error", {"message": "未找到持仓记录"})
            emit("portfolio_updated", state)
            return
        broadcast_alert_rule_views()

    @socketio.on("save_portfolio_transaction")
    def on_save_portfolio_transaction(data):
        try:
            state = upsert_portfolio_transaction(data)
        except ValueError as exc:
            emit("portfolio_error", {"message": str(exc)})
            return
        except OSError:
            emit("portfolio_error", {"message": "持仓流水保存失败，请检查配置目录权限。"})
            return
        socketio.emit("portfolio_updated", state)

    @socketio.on("delete_portfolio_transaction")
    def on_delete_portfolio_transaction(data=None):
        transaction_id = data.get("id") if isinstance(data, dict) else None
        try:
            ok, state = delete_portfolio_transaction(transaction_id)
        except ValueError as exc:
            emit("portfolio_error", {"message": str(exc)})
            return
        except OSError:
            emit("portfolio_error", {"message": "持仓流水保存失败，请检查配置目录权限。"})
            return
        if not ok:
            emit("portfolio_error", {"message": "未找到持仓流水"})
            emit("portfolio_updated", state)
            return
        socketio.emit("portfolio_updated", state)

    @socketio.on("get_portfolio_investment_plans")
    def on_get_portfolio_investment_plans():
        emit(
            "portfolio_investment_plans_updated",
            get_portfolio_investment_plan_state(),
        )

    @socketio.on("save_portfolio_investment_plan")
    def on_save_portfolio_investment_plan(data=None):
        try:
            plan, state = upsert_portfolio_investment_plan(data)
        except ValueError as exc:
            emit("portfolio_investment_plan_error", {"message": str(exc)})
            return
        except OSError:
            emit("portfolio_investment_plan_error", {
                "message": "定投计划保存失败，请检查配置目录权限。",
            })
            return
        emit("portfolio_investment_plan_saved", {"ok": True, "plan": plan})
        socketio.emit("portfolio_investment_plans_updated", state)

    @socketio.on("delete_portfolio_investment_plan")
    def on_delete_portfolio_investment_plan(data=None):
        plan_id = data.get("id") if isinstance(data, dict) else None
        try:
            ok, state = delete_portfolio_investment_plan(plan_id)
        except OSError:
            emit("portfolio_investment_plan_error", {
                "message": "定投计划删除失败，请检查配置目录权限。",
            })
            return
        if not ok:
            emit("portfolio_investment_plan_error", {"message": "未找到定投计划"})
            return
        socketio.emit("portfolio_investment_plans_updated", state)

    @socketio.on("toggle_portfolio_investment_plan")
    def on_toggle_portfolio_investment_plan(data=None):
        payload = data if isinstance(data, dict) else {}
        try:
            _plan, state = toggle_portfolio_investment_plan(
                payload.get("id"),
                payload.get("enabled") is True,
            )
        except ValueError as exc:
            emit("portfolio_investment_plan_error", {"message": str(exc)})
            return
        except OSError:
            emit("portfolio_investment_plan_error", {
                "message": "定投计划状态保存失败，请检查配置目录权限。",
            })
            return
        socketio.emit("portfolio_investment_plans_updated", state)

    @socketio.on("preview_portfolio_investment_schedule")
    def on_preview_portfolio_investment_schedule(data=None):
        payload = data if isinstance(data, dict) else {}
        try:
            result = preview_portfolio_investment_schedule(payload)
        except ValueError as exc:
            result = {
                "ok": False,
                "id": str(payload.get("id") or "new"),
                "request_id": str(payload.get("request_id") or ""),
                "items": [],
                "message": str(exc),
            }
        emit("portfolio_investment_schedule_preview", result)

    @socketio.on("execute_portfolio_investment_plan")
    def on_execute_portfolio_investment_plan(data=None):
        plan_id = data.get("id") if isinstance(data, dict) else None
        try:
            result = execute_portfolio_investment_plan(plan_id)
        except ValueError as exc:
            emit("portfolio_investment_plan_error", {"message": str(exc)})
            return
        except OSError:
            emit("portfolio_investment_plan_error", {
                "message": "定投执行失败，请检查配置目录权限。",
            })
            return
        emit("portfolio_investment_plan_executed", result)
        emit(
            "portfolio_investment_plans_updated",
            get_portfolio_investment_plan_state(),
        )

    @socketio.on("skip_portfolio_investment_plan")
    def on_skip_portfolio_investment_plan(data=None):
        payload = data if isinstance(data, dict) else {}
        try:
            result = skip_portfolio_investment_plan(
                payload.get("id"),
                payload.get("scheduled_at"),
            )
        except ValueError as exc:
            emit("portfolio_investment_plan_error", {"message": str(exc)})
            return
        except OSError:
            emit("portfolio_investment_plan_error", {
                "message": "定投跳过状态保存失败，请检查配置目录权限。",
            })
            return
        emit("portfolio_investment_plan_skipped", result)
        socketio.emit("portfolio_investment_plans_updated", result["state"])

    @socketio.on("export_portfolio_investment_executions")
    def on_export_portfolio_investment_executions(data=None):
        plan_id = data.get("id") if isinstance(data, dict) else None
        try:
            content, count, plan = build_portfolio_investment_executions_csv(plan_id)
            filename = (
                "GoldMonitor-investment-executions-"
                f"{now_factory().strftime('%Y%m%d-%H%M%S')}.csv"
            )
            saved_path = save_export_file(filename, content)
            emit("portfolio_investment_executions_exported", {
                "ok": True,
                "plan_id": plan.get("id"),
                "plan_name": plan.get("name"),
                "filename": filename,
                "saved_path": saved_path,
                "count": count,
            })
        except ValueError as exc:
            emit("portfolio_investment_executions_export_error", {
                "message": str(exc),
            })
        except OSError as exc:
            emit(
                "portfolio_investment_executions_export_error",
                build_export_error_payload(f"定投执行记录导出失败: {exc}"),
            )

    @socketio.on("preview_import_portfolio_transactions")
    def on_preview_import_portfolio_transactions(data=None):
        content = data.get("content") if isinstance(data, dict) else ""
        payload = preview_import_portfolio_transactions_csv(content)
        request_id = data.get("request_id") if isinstance(data, dict) else ""
        if request_id:
            payload["request_id"] = str(request_id)
        emit("portfolio_import_previewed", payload)

    @socketio.on("import_portfolio_transactions")
    def on_import_portfolio_transactions(data=None):
        content = data.get("content") if isinstance(data, dict) else ""
        try:
            state, imported_count = import_portfolio_transactions_csv(content)
        except ValueError as exc:
            emit("portfolio_error", {"message": str(exc)})
            return
        except OSError:
            emit("portfolio_error", {"message": "持仓流水导入失败，请检查配置目录权限。"})
            return
        emit("portfolio_imported", {
            "ok": True,
            "kind": "transactions",
            "count": imported_count,
            "summary": state.get("import_summary") or {"count": imported_count},
            "import_backup": (
                state.get("import_backup")
                or portfolio_import_backup_state(get_portfolio_import_backup())
            ),
        })
        socketio.emit("portfolio_updated", state)

    @socketio.on("undo_portfolio_import")
    def on_undo_portfolio_import():
        try:
            ok, state = undo_portfolio_import()
        except OSError:
            emit("portfolio_error", {"message": "撤销导入失败，请检查配置目录权限。"})
            return
        if not ok:
            emit("portfolio_import_undo_error", {
                "ok": False,
                "kind": "transactions",
                "code": "no_backup",
                "message": "没有可撤销的导入批次。",
                "import_backup": (
                    state.get("import_backup")
                    if isinstance(state, dict)
                    else portfolio_import_backup_state(get_portfolio_import_backup())
                ),
            })
            emit("portfolio_updated", state)
            return
        emit("portfolio_import_undone", {
            "ok": True,
            "kind": "transactions",
            "import_backup": (
                state.get("import_backup")
                or portfolio_import_backup_state(get_portfolio_import_backup())
            ),
        })
        socketio.emit("portfolio_updated", state)

    @socketio.on("save_portfolio_alert")
    def on_save_portfolio_alert(data):
        try:
            upsert_portfolio_alert(data)
        except ValueError as exc:
            emit("portfolio_error", {"message": str(exc)})
            return
        except OSError:
            emit("portfolio_error", {"message": "持仓提醒保存失败，请检查配置目录权限。"})
            return
        broadcast_alert_rule_views()

    @socketio.on("reset_portfolio_alert")
    def on_reset_portfolio_alert(data=None):
        alert_id = data.get("id") if isinstance(data, dict) else None
        try:
            ok, state = reset_portfolio_alert(alert_id)
        except (ValueError, OSError):
            emit("portfolio_error", {"message": "持仓提醒保存失败，请检查配置目录权限。"})
            return
        if not ok:
            emit("portfolio_error", {"message": "未找到持仓提醒"})
            emit("portfolio_updated", state)
            return
        broadcast_alert_rule_views()

    @socketio.on("delete_portfolio_alert")
    def on_delete_portfolio_alert(data=None):
        alert_id = data.get("id") if isinstance(data, dict) else None
        try:
            ok, state = delete_portfolio_alert(alert_id)
        except OSError:
            emit("portfolio_error", {"message": "持仓提醒保存失败，请检查配置目录权限。"})
            return
        if not ok:
            emit("portfolio_error", {"message": "未找到持仓提醒"})
            emit("portfolio_updated", state)
            return
        broadcast_alert_rule_views()

    @socketio.on("export_portfolio")
    def on_export_portfolio(data=None):
        kind = data.get("kind") if isinstance(data, dict) else "positions"
        if kind not in {"positions", "transactions", "review"}:
            kind = "positions"
        suffix = kind if kind in {"transactions", "review"} else "positions"
        extension = "md" if kind == "review" else "csv"
        filename = (
            f"GoldMonitor-portfolio-{suffix}-"
            f"{now_factory().strftime('%Y%m%d-%H%M%S')}.{extension}"
        )
        try:
            content, count = build_portfolio_csv(kind)
            saved_path = save_export_file(filename, content)
            emit("portfolio_exported", {
                "ok": True,
                "kind": kind,
                "filename": filename,
                "saved_path": saved_path,
                "count": count,
            })
        except OSError as exc:
            emit("portfolio_export_error", build_export_error_payload(f"持仓导出失败: {exc}"))

    @socketio.on("get_portfolio_analytics")
    def on_get_portfolio_analytics(data=None):
        days = data.get("days") if isinstance(data, dict) else 90
        try:
            emit("portfolio_analytics_updated", build_portfolio_analytics_state(days=days))
        except (ValueError, OSError, sqlite3.Error) as exc:
            logging.warning("生成持仓分析失败: %s", exc)
            emit("portfolio_analytics_error", {
                "message": "持仓收益与预警分析生成失败，请稍后重试。",
            })
