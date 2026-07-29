import logging

from flask_socketio import emit


def register_history_review_handlers(
    socketio,
    *,
    price_history_export_limit,
    build_price_history_state,
    normalize_timeline_request,
    build_timeline_state,
    upsert_review_note,
    delete_review_note,
    build_review_report,
    review_report_filename,
    save_review_report,
    build_export_error_payload,
    build_price_history_csv,
    now_factory,
):
    @socketio.on("get_price_history")
    def on_get_price_history(data=None):
        minutes = None
        limit = 600
        period = None
        scope = "history"
        if isinstance(data, dict):
            period = str(data.get("period") or "").strip() or None
            scope = str(data.get("scope") or "history").strip() or "history"
            try:
                minutes = int(data.get("minutes")) if data.get("minutes") else None
            except (TypeError, ValueError):
                minutes = None
            try:
                limit = max(
                    1,
                    min(price_history_export_limit, int(data.get("limit", limit))),
                )
            except (TypeError, ValueError):
                limit = 600
        state = build_price_history_state(minutes=minutes, limit=limit)
        state["period"] = period
        state["scope"] = scope
        emit("price_history_updated", state)

    @socketio.on("get_event_timeline")
    def on_get_event_timeline(data=None):
        try:
            request_args = normalize_timeline_request(data)
            state = build_timeline_state(**request_args)
            emit("event_timeline_updated", state)
        except Exception as exc:
            logging.warning("事件时间轴生成失败: %s", exc)
            emit("event_timeline_error", {
                "message": "事件时间轴加载失败，请稍后重试。",
            })

    @socketio.on("save_review_note")
    def on_save_review_note(data=None):
        try:
            state, note = upsert_review_note(data)
        except ValueError as exc:
            emit("review_note_error", {"message": str(exc)})
            return
        except OSError:
            emit("review_note_error", {
                "message": "复盘笔记保存失败，请检查配置目录权限。",
            })
            return
        emit("review_note_saved", {"ok": True, "note": note, "state": state})
        socketio.emit("review_notes_updated", state)

    @socketio.on("delete_review_note")
    def on_delete_review_note(data=None):
        note_id = data.get("id") if isinstance(data, dict) else ""
        try:
            deleted, state = delete_review_note(note_id)
        except ValueError as exc:
            emit("review_note_error", {"message": str(exc)})
            return
        except OSError:
            emit("review_note_error", {
                "message": "复盘笔记删除失败，请检查配置目录权限。",
            })
            return
        if not deleted:
            emit("review_note_error", {"message": "未找到复盘笔记。"})
            return
        emit("review_note_deleted", {
            "ok": True,
            "id": str(note_id),
            "state": state,
        })
        socketio.emit("review_notes_updated", state)

    @socketio.on("export_review_report")
    def on_export_review_report(data=None):
        try:
            request_args = normalize_timeline_request(data)
            state = build_timeline_state(**request_args)
            content = build_review_report(state)
            filename = review_report_filename()
            saved_path = save_review_report(content, filename)
            emit("review_report_exported", {
                "ok": True,
                "filename": filename,
                "saved_path": saved_path,
                "count": state.get("summary", {}).get("total", 0),
            })
        except OSError as exc:
            emit(
                "review_report_error",
                build_export_error_payload(f"复盘报告导出失败: {exc}"),
            )
        except Exception as exc:
            logging.warning("复盘报告导出失败: %s", exc)
            emit("review_report_error", {
                "message": "复盘报告导出失败，请稍后重试。",
            })

    @socketio.on("export_price_history")
    def on_export_price_history(data=None):
        minutes = None
        if isinstance(data, dict):
            try:
                minutes = int(data.get("minutes")) if data.get("minutes") else None
            except (TypeError, ValueError):
                minutes = None
        content, count = build_price_history_csv(minutes=minutes)
        emit("price_history_export_ready", {
            "filename": (
                "GoldMonitor-price-history-"
                f"{now_factory().strftime('%Y%m%d-%H%M%S')}.csv"
            ),
            "content": content,
            "count": count,
        })
