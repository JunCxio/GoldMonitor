import os
from functools import lru_cache


TASKBAR_INTERACTIVE_CONTROL_TYPES = {
    "ControlType.Button",
    "ControlType.CheckBox",
    "ControlType.Hyperlink",
    "ControlType.ListItem",
    "ControlType.MenuItem",
    "ControlType.RadioButton",
    "ControlType.SplitButton",
    "ControlType.TabItem",
}


@lru_cache(maxsize=1)
def _load_windows_automation():
    import clr

    clr.AddReference("UIAutomationClient")
    from System import IntPtr
    from System.Windows.Automation import AutomationElement, Condition, TreeScope

    return IntPtr, AutomationElement, Condition, TreeScope


def normalize_taskbar_automation_rect(rect, taskbar_rect):
    if rect is None or taskbar_rect is None:
        return None
    try:
        values = (
            int(rect.Left),
            int(rect.Top),
            int(rect.Right),
            int(rect.Bottom),
        )
    except (AttributeError, TypeError, ValueError, OverflowError):
        return None

    left, top, right, bottom = values
    taskbar_left, taskbar_top, taskbar_right, taskbar_bottom = taskbar_rect
    if right <= left or bottom <= top:
        return None
    if right <= taskbar_left or left >= taskbar_right:
        return None
    if bottom <= taskbar_top or top >= taskbar_bottom:
        return None

    taskbar_width = taskbar_right - taskbar_left
    taskbar_height = taskbar_bottom - taskbar_top
    if right - left > taskbar_width // 2:
        return None
    if bottom - top > taskbar_height * 2:
        return None
    return (
        max(taskbar_left, left),
        max(taskbar_top, top),
        min(taskbar_right, right),
        min(taskbar_bottom, bottom),
    )


def get_taskbar_occupied_rects(
    taskbar_hwnd,
    taskbar_rect,
    *,
    os_name=None,
    automation_loader=_load_windows_automation,
):
    if (os_name or os.name) != "nt" or not taskbar_hwnd or not taskbar_rect:
        return None
    try:
        IntPtr, AutomationElement, Condition, TreeScope = automation_loader()
        root = AutomationElement.FromHandle(IntPtr(int(taskbar_hwnd)))
        if root is None:
            return None
        elements = root.FindAll(TreeScope.Descendants, Condition.TrueCondition)
        rectangles = []
        seen = set()
        for index in range(int(elements.Count)):
            current = elements[index].Current
            if bool(current.IsOffscreen):
                continue
            control_type = str(current.ControlType.ProgrammaticName)
            if control_type not in TASKBAR_INTERACTIVE_CONTROL_TYPES:
                continue
            rect = normalize_taskbar_automation_rect(
                current.BoundingRectangle,
                taskbar_rect,
            )
            if rect and rect not in seen:
                seen.add(rect)
                rectangles.append(rect)
        return sorted(rectangles) if len(rectangles) >= 2 else None
    except Exception:
        return None
