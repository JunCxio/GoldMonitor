def test_base_socket_runtime_registers_expected_handlers():
    from goldmonitor.socket_runtime import register_base_handlers

    registered = {}

    class Socket:
        def on(self, event):
            return lambda handler: registered.setdefault(event, handler)

        def emit(self, *args, **kwargs):
            pass

    register_base_handlers(
        Socket(),
        emit=lambda *args: None,
        authorize=lambda auth: True,
        build_init_state=lambda: {"ok": True},
        get_settings=lambda: {},
        save_settings=lambda settings: settings,
        public_settings=lambda: {},
        hide_window=lambda: None,
        exit_application=lambda: None,
        get_news_state=lambda: {},
        build_fetch_status=lambda *args, **kwargs: {},
        fetch_price=lambda: None,
        refresh_news=lambda: None,
        thread_factory=lambda **kwargs: None,
    )

    assert set(registered) == {"connect", "close_choice", "get_news", "refresh_price", "refresh_news"}
    assert registered["connect"]({"token": "ok"}) is None
