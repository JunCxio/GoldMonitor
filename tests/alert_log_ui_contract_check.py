from pathlib import Path


root = Path(__file__).resolve().parents[1]
template = (root / "templates" / "index.html").read_text(encoding="utf-8")
js = (root / "static" / "app.js").read_text(encoding="utf-8")
css = (root / "static" / "app.css").read_text(encoding="utf-8")


for forbidden in (
    'value="pending"',
    'id="alertDetail"',
    "选择一条警报查看详情",
    "确认</button>",
    "未确认",
    "已确认",
    "处理状态",
    "读取状态",
    "function acknowledgeAlert",
    "function renderAlertDetail",
    "selectedAlertId",
    "acknowledged ?",
):
    if forbidden in template or forbidden in js:
        raise SystemExit(f"alert log UI must not expose acknowledgement/detail workflow: {forbidden}")


for required in (
    'id="alertLogModeTabs"',
    "setAlertLogView('all')",
    "setAlertLogView('new')",
    "setAlertLogView('unhandled')",
    "setAlertLogView('handled')",
    "setAlertLogView('failed')",
    "未处理",
    "通知失败",
    'id="alertLogMenu"',
    "toggleAlertLogMenu",
    "renderAlertLog",
    "analyzeAlertFromLog",
    "alert-log-shell",
    "source-health-summary",
    "source-health-details",
):
    if required not in template and required not in js and required not in css:
        raise SystemExit(f"alert log UI missing compact monitor flow anchor: {required}")


print("alert log UI contract checks passed.")
