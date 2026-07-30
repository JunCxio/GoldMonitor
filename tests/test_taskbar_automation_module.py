from types import SimpleNamespace


def _rect(left, top, right, bottom):
    return SimpleNamespace(Left=left, Top=top, Right=right, Bottom=bottom)


def test_taskbar_automation_collects_visible_interactive_bounds():
    from goldmonitor.taskbar_automation import get_taskbar_occupied_rects

    elements = [
        SimpleNamespace(
            Current=SimpleNamespace(
                IsOffscreen=False,
                ControlType=SimpleNamespace(ProgrammaticName="ControlType.Button"),
                BoundingRectangle=_rect(820, 1042, 868, 1078),
            )
        ),
        SimpleNamespace(
            Current=SimpleNamespace(
                IsOffscreen=False,
                ControlType=SimpleNamespace(ProgrammaticName="ControlType.ListItem"),
                BoundingRectangle=_rect(1720, 1042, 1760, 1078),
            )
        ),
        SimpleNamespace(
            Current=SimpleNamespace(
                IsOffscreen=False,
                ControlType=SimpleNamespace(ProgrammaticName="ControlType.Pane"),
                BoundingRectangle=_rect(0, 1040, 1920, 1080),
            )
        ),
        SimpleNamespace(
            Current=SimpleNamespace(
                IsOffscreen=True,
                ControlType=SimpleNamespace(ProgrammaticName="ControlType.Button"),
                BoundingRectangle=_rect(900, 1042, 948, 1078),
            )
        ),
    ]

    class ElementCollection(list):
        @property
        def Count(self):
            return len(self)

    root = SimpleNamespace(
        FindAll=lambda scope, condition: ElementCollection(elements),
    )
    automation_element = SimpleNamespace(FromHandle=lambda hwnd: root)
    loader = lambda: (
        lambda value: value,
        automation_element,
        SimpleNamespace(TrueCondition=True),
        SimpleNamespace(Descendants=1),
    )

    assert get_taskbar_occupied_rects(
        42,
        (0, 1040, 1920, 1080),
        os_name="nt",
        automation_loader=loader,
    ) == [
        (820, 1042, 868, 1078),
        (1720, 1042, 1760, 1078),
    ]


def test_taskbar_automation_rejects_invalid_or_insufficient_bounds():
    from goldmonitor.taskbar_automation import normalize_taskbar_automation_rect

    taskbar_rect = (0, 1040, 1920, 1080)

    assert normalize_taskbar_automation_rect(
        _rect(100, 1042, 148, 1078),
        taskbar_rect,
    ) == (100, 1042, 148, 1078)
    assert normalize_taskbar_automation_rect(
        _rect(0, 1040, 1200, 1080),
        taskbar_rect,
    ) is None
    assert normalize_taskbar_automation_rect(
        _rect(100, 900, 148, 950),
        taskbar_rect,
    ) is None
