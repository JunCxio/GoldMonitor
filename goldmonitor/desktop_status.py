import logging


def _load_app_helper():
    from PyObjCTools import AppHelper

    return AppHelper


def call_macos_main(
    callback,
    *,
    sys_platform,
    app_helper_loader=_load_app_helper,
):
    if sys_platform != "darwin":
        return False
    try:
        app_helper_loader().callAfter(callback)
        return True
    except Exception:
        try:
            callback()
            return True
        except Exception:
            return False


def refresh_macos_status_item(
    *,
    sys_platform,
    get_status_item,
    get_menu_items,
    format_status_title,
    format_price_title,
    get_settings,
    call_main,
):
    status_item = get_status_item()
    if sys_platform != "darwin" or not status_item:
        return False

    def apply_status():
        try:
            button = status_item.button()
            if button:
                button.setTitle_(format_status_title())
                button.setToolTip_(format_price_title())
            toggle_item = get_menu_items().get("toggle_price")
            if toggle_item:
                enabled = get_settings().get("floating_price_enabled", True)
                toggle_item.setTitle_("隐藏菜单栏金价" if enabled else "显示菜单栏金价")
        except Exception:
            pass

    call_main(apply_status)
    return True


def _load_macos_status_types():
    from Foundation import NSObject
    from AppKit import NSMenu, NSMenuItem, NSStatusBar, NSVariableStatusItemLength

    return NSObject, NSMenu, NSMenuItem, NSStatusBar, NSVariableStatusItemLength


def create_macos_status_item(
    *,
    sys_platform,
    get_status_item,
    set_status_state,
    show_window,
    refresh_price,
    open_risk_analysis,
    toggle_price,
    exit_application,
    refresh_status,
    status_types_loader=_load_macos_status_types,
    logger=logging,
):
    if sys_platform != "darwin" or get_status_item():
        return None
    try:
        NSObject, NSMenu, NSMenuItem, NSStatusBar, variable_length = status_types_loader()

        class MacOSStatusDelegate(NSObject):
            def showWindow_(self, sender):
                show_window()

            def refreshPrice_(self, sender):
                refresh_price()

            def openRiskAnalysis_(self, sender):
                open_risk_analysis()

            def toggleMenuBarPrice_(self, sender):
                toggle_price()

            def quitApp_(self, sender):
                exit_application()

        delegate = MacOSStatusDelegate.alloc().init()
        menu = NSMenu.alloc().init()

        def add_item(title, action):
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, "")
            item.setTarget_(delegate)
            menu.addItem_(item)
            return item

        add_item("显示窗口", "showWindow:")
        add_item("刷新行情", "refreshPrice:")
        add_item("风险分析", "openRiskAnalysis:")
        toggle_item = add_item("隐藏菜单栏金价", "toggleMenuBarPrice:")
        menu.addItem_(NSMenuItem.separatorItem())
        add_item("退出", "quitApp:")

        status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(variable_length)
        status_item.setMenu_(menu)
        set_status_state({
            "delegate": delegate,
            "menu": menu,
            "status_item": status_item,
            "menu_items": {"toggle_price": toggle_item},
        })
        refresh_status()
        return status_item
    except Exception:
        logger.warning("macOS 菜单栏状态项启动失败", exc_info=True)
        return None


def update_desktop_price_title(
    title,
    *,
    last_title,
    set_last_title,
    get_window,
    get_tray_icon,
    refresh_status,
):
    if title == last_title():
        refresh_status()
        return title
    set_last_title(title)
    window = get_window()
    if window:
        try:
            window.set_title(title)
        except Exception:
            pass
    icon = get_tray_icon()
    if icon:
        try:
            icon.title = title
        except Exception:
            pass
    refresh_status()
    return title
