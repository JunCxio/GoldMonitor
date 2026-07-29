from types import SimpleNamespace


def test_call_macos_main_uses_app_helper_and_falls_back_to_direct_call():
    from goldmonitor.desktop_status import call_macos_main

    calls = []
    helper = SimpleNamespace(callAfter=lambda callback: calls.append("scheduled"))

    assert call_macos_main(
        lambda: calls.append("callback"),
        sys_platform="darwin",
        app_helper_loader=lambda: helper,
    ) is True
    assert calls == ["scheduled"]

    assert call_macos_main(
        lambda: calls.append("fallback"),
        sys_platform="darwin",
        app_helper_loader=lambda: (_ for _ in ()).throw(RuntimeError("missing")),
    ) is True
    assert calls[-1] == "fallback"

    assert call_macos_main(
        lambda: calls.append("ignored"),
        sys_platform="win32",
        app_helper_loader=lambda: helper,
    ) is False
    assert "ignored" not in calls


def test_refresh_status_updates_title_tooltip_and_toggle_label():
    from goldmonitor.desktop_status import refresh_macos_status_item

    button_calls = []
    toggle_calls = []
    button = SimpleNamespace(
        setTitle_=lambda value: button_calls.append(("title", value)),
        setToolTip_=lambda value: button_calls.append(("tooltip", value)),
    )
    status_item = SimpleNamespace(button=lambda: button)
    toggle_item = SimpleNamespace(setTitle_=toggle_calls.append)
    scheduled = []

    result = refresh_macos_status_item(
        sys_platform="darwin",
        get_status_item=lambda: status_item,
        get_menu_items=lambda: {"toggle_price": toggle_item},
        format_status_title=lambda: "¥528.10",
        format_price_title=lambda: "金价监控 ¥528.10/克",
        get_settings=lambda: {"floating_price_enabled": False},
        call_main=lambda callback: scheduled.append(callback) or callback(),
    )

    assert result is True
    assert len(scheduled) == 1
    assert button_calls == [
        ("title", "¥528.10"),
        ("tooltip", "金价监控 ¥528.10/克"),
    ]
    assert toggle_calls == ["显示菜单栏金价"]


def test_create_status_item_builds_menu_and_keeps_delegate_alive():
    from goldmonitor.desktop_status import create_macos_status_item

    actions = []
    states = []

    class ObjCObject:
        @classmethod
        def alloc(cls):
            return cls()

        def init(self):
            return self

    class Menu(ObjCObject):
        def __init__(self):
            self.items = []

        def addItem_(self, item):
            self.items.append(item)

    class MenuItem(ObjCObject):
        def initWithTitle_action_keyEquivalent_(self, title, action, key):
            self.title = title
            self.action = action
            self.key = key
            self.target = None
            return self

        def setTarget_(self, target):
            self.target = target

        @classmethod
        def separatorItem(cls):
            item = cls()
            item.title = None
            return item

    class StatusItem:
        def setMenu_(self, menu):
            self.menu = menu

    class StatusBar:
        @classmethod
        def systemStatusBar(cls):
            return cls()

        def statusItemWithLength_(self, length):
            self.length = length
            return StatusItem()

    status_item = create_macos_status_item(
        sys_platform="darwin",
        get_status_item=lambda: None,
        set_status_state=states.append,
        show_window=lambda: actions.append("show"),
        refresh_price=lambda: actions.append("refresh"),
        open_risk_analysis=lambda: actions.append("risk"),
        toggle_price=lambda: actions.append("toggle"),
        exit_application=lambda: actions.append("exit"),
        refresh_status=lambda: actions.append("status"),
        status_types_loader=lambda: (ObjCObject, Menu, MenuItem, StatusBar, 99),
    )

    assert status_item is states[0]["status_item"]
    assert [item.title for item in states[0]["menu"].items] == [
        "显示窗口",
        "刷新行情",
        "风险分析",
        "隐藏菜单栏金价",
        None,
        "退出",
    ]
    delegate = states[0]["delegate"]
    delegate.showWindow_(None)
    delegate.refreshPrice_(None)
    delegate.openRiskAnalysis_(None)
    delegate.toggleMenuBarPrice_(None)
    delegate.quitApp_(None)
    assert actions == ["status", "show", "refresh", "risk", "toggle", "exit"]


def test_desktop_title_update_skips_duplicate_but_always_refreshes_status():
    from goldmonitor.desktop_status import update_desktop_price_title

    calls = []
    window = SimpleNamespace(set_title=lambda title: calls.append(("window", title)))
    icon = SimpleNamespace(title="old")
    state = {"title": "金价监控"}

    update_desktop_price_title(
        "金价监控 ¥528.10/克",
        last_title=lambda: state["title"],
        set_last_title=lambda value: state.update(title=value),
        get_window=lambda: window,
        get_tray_icon=lambda: icon,
        refresh_status=lambda: calls.append("refresh"),
    )
    update_desktop_price_title(
        "金价监控 ¥528.10/克",
        last_title=lambda: state["title"],
        set_last_title=lambda value: state.update(title=value),
        get_window=lambda: window,
        get_tray_icon=lambda: icon,
        refresh_status=lambda: calls.append("refresh"),
    )

    assert state["title"] == "金价监控 ¥528.10/克"
    assert icon.title == "金价监控 ¥528.10/克"
    assert calls == [
        ("window", "金价监控 ¥528.10/克"),
        "refresh",
        "refresh",
    ]
