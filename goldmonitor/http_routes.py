import logging
import os
import sqlite3
import tempfile

from goldmonitor import data_archive as data_archive_core


def register_http_routes(
    flask_app,
    *,
    jsonify,
    render_template,
    send_from_directory,
    request,
    base_dir,
    socket_access_token,
    app_name,
    app_version,
    get_price_state,
    get_health_state,
    activate_application,
    authorized_request,
    archive_manager,
    store_upload,
    consume_upload,
    restore_archive,
    emit,
    logger=logging,
):
    def index():
        return render_template(
            "index.html",
            socket_access_token=socket_access_token,
            app_version=app_version,
        )

    def api_price():
        return jsonify(get_price_state())

    def api_health():
        return jsonify({"app": app_name, "version": app_version, **get_health_state()})

    def api_activate():
        return jsonify(activate_application())

    def api_preview_data_archive():
        if not authorized_request():
            return jsonify({"ok": False, "message": "未授权的数据归档请求"}), 403
        uploaded = request.files.get("archive")
        if uploaded is None or not str(uploaded.filename or "").strip():
            return jsonify({"ok": False, "message": "请选择数据归档文件"}), 400
        file_descriptor, upload_path = tempfile.mkstemp(prefix="goldmonitor-restore-", suffix=".zip")
        os.close(file_descriptor)
        try:
            uploaded.save(upload_path)
            preview = archive_manager().preview(upload_path)
            return jsonify({**preview, "restore_token": store_upload(upload_path, preview)})
        except data_archive_core.DataArchiveError as exc:
            _remove_upload(upload_path)
            logger.warning("数据归档预检失败: %s", exc)
            return jsonify({
                "ok": False,
                "restorable": False,
                "message": "数据归档校验失败，请确认文件来自 GoldMonitor 且未损坏",
            }), 400
        except OSError as exc:
            _remove_upload(upload_path)
            logger.warning("读取数据归档失败: %s", exc)
            return jsonify({
                "ok": False,
                "restorable": False,
                "message": "读取数据归档失败，请检查文件后重试",
            }), 400

    def api_restore_data_archive():
        if not authorized_request():
            return jsonify({"ok": False, "message": "未授权的数据归档请求"}), 403
        payload = request.get_json(silent=True)
        token = str(payload.get("restore_token") or "") if isinstance(payload, dict) else ""
        upload = consume_upload(token)
        if not upload:
            return jsonify({"ok": False, "message": "归档预检已失效，请重新选择文件"}), 400
        archive_path = str(upload.get("path") or "")
        try:
            result = restore_archive(archive_path)
            emit("data_archive_restored", result)
            return jsonify(result)
        except (data_archive_core.DataArchiveError, OSError, sqlite3.Error) as exc:
            logger.warning("完整数据恢复失败: %s", exc)
            return jsonify({
                "ok": False,
                "message": "数据恢复失败，原数据已回滚。请检查归档文件后重试。",
            }), 400
        except Exception:
            logger.exception("完整数据恢复失败")
            return jsonify({
                "ok": False,
                "message": "数据恢复失败，原数据已回滚。请检查运行日志。",
            }), 500
        finally:
            _remove_upload(archive_path)

    def favicon():
        return send_from_directory(os.path.join(base_dir, "static"), "icon-64.png", mimetype="image/png")

    def manifest():
        return send_from_directory(base_dir, "manifest.json")

    def service_worker():
        return send_from_directory(base_dir, "sw.js", mimetype="application/javascript")

    def static_files(filename):
        return send_from_directory(os.path.join(base_dir, "static"), filename)

    handlers = {
        "index": index,
        "api_price": api_price,
        "api_health": api_health,
        "api_activate": api_activate,
        "api_preview_data_archive": api_preview_data_archive,
        "api_restore_data_archive": api_restore_data_archive,
        "favicon": favicon,
        "manifest": manifest,
        "service_worker": service_worker,
        "static_files": static_files,
    }
    routes = (
        ("/", "index", ["GET"]),
        ("/api/price", "api_price", ["GET"]),
        ("/api/health", "api_health", ["GET"]),
        ("/api/activate", "api_activate", ["POST"]),
        ("/api/data-archive/preview", "api_preview_data_archive", ["POST"]),
        ("/api/data-archive/restore", "api_restore_data_archive", ["POST"]),
        ("/favicon.ico", "favicon", ["GET"]),
        ("/manifest.json", "manifest", ["GET"]),
        ("/sw.js", "service_worker", ["GET"]),
        ("/static/<path:filename>", "static_files", ["GET"]),
    )
    for rule, endpoint, methods in routes:
        flask_app.add_url_rule(rule, endpoint=endpoint, view_func=handlers[endpoint], methods=methods)
    return handlers


def _remove_upload(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
