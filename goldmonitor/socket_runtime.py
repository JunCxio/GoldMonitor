import logging
import threading


def register_base_handlers(
    socketio,
    *,
    emit,
    authorize,
    build_init_state,
    get_settings,
    save_settings,
    public_settings,
    hide_window,
    exit_application,
    get_news_state,
    build_fetch_status,
    fetch_price,
    refresh_news,
    thread_factory=threading.Thread,
):
    def on_connect(auth=None):
        if not authorize(auth):
            return False
        emit("init_state", build_init_state())

    def on_close_choice(data):
        data = data if isinstance(data, dict) else {}
        choice = data.get("choice")
        remember = bool(data.get("remember"))
        if choice not in ("minimize_to_tray", "exit", "cancel"):
            return
        if remember and choice in ("minimize_to_tray", "exit"):
            snapshot = get_settings()
            snapshot["close_behavior"] = choice
            snapshot["close_remembered"] = True
            try:
                save_settings(snapshot)
            except OSError:
                pass
            socketio.emit("settings_updated", public_settings())
        if choice == "minimize_to_tray":
            hide_window()
        elif choice == "exit":
            exit_application()

    def on_get_news():
        emit("news_updated", get_news_state())

    def on_refresh_price():
        emit("fetch_status", build_fetch_status(
            False,
            "正在重新获取行情数据...",
            retryable=False,
        ))
        thread_factory(target=fetch_price, daemon=True).start()

    def on_refresh_news():
        emit("news_updated", {**get_news_state(), "loading": True})
        thread_factory(target=refresh_news, daemon=True).start()

    handlers = {
        "connect": on_connect,
        "close_choice": on_close_choice,
        "get_news": on_get_news,
        "refresh_price": on_refresh_price,
        "refresh_news": on_refresh_news,
    }
    for event, handler in handlers.items():
        socketio.on(event)(handler)
    return handlers
