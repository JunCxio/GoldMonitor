import logging

from flask_socketio import emit


def register_today_overview_handlers(
    socketio,
    *,
    build_today_overview,
    mark_today_overview_viewed,
):
    @socketio.on("get_today_overview")
    def on_get_today_overview():
        try:
            emit("today_overview_updated", build_today_overview())
        except Exception as exc:
            logging.warning("今日概览加载失败: %s", exc)
            emit("today_overview_error", {
                "message": "今日概览加载失败，请稍后重试。",
            })

    @socketio.on("mark_today_overview_viewed")
    def on_mark_today_overview_viewed():
        try:
            result = mark_today_overview_viewed()
        except (OSError, ValueError):
            emit("today_overview_error", {
                "message": "今日概览查看状态保存失败，请检查配置目录权限。",
            })
            return
        socketio.emit("today_overview_updated", result["overview"])
        emit("today_overview_viewed", {
            "ok": True,
            "view_state": result["view_state"],
        })
