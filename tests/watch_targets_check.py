import json
import tempfile
from datetime import datetime
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


with tempfile.TemporaryDirectory() as tmp_dir:
    original_path = app.WATCH_TARGETS_PATH
    original_alert_rules_path = app.ALERT_RULES_PATH
    original_targets = list(app.watch_targets)
    original_alert_rules = [dict(rule) for rule in app.alert_rules]
    original_price_usd = app.price_usd
    original_price_rmb = app.price_rmb
    original_market_observation = dict(app.market_observation)
    original_alert_log = list(app.alert_log)
    original_emit_alert = app.emit_alert
    original_run_risk_analysis = app.run_risk_analysis
    try:
        app.WATCH_TARGETS_PATH = str(Path(tmp_dir) / "watch_targets.json")
        app.ALERT_RULES_PATH = str(Path(tmp_dir) / "alert_rules.json")
        app.watch_targets = []

        if app.load_watch_targets() != []:
            raise SystemExit("missing watch target file must load as an empty list")

        target = app.normalize_watch_target({
            "mode": "rmb",
            "direction": "fall_to",
            "price": "688.8",
            "note": "预算观察价" * 80,
        })
        if not target["id"].startswith("target-"):
            raise SystemExit(f"watch target id must be generated, got: {target['id']}")
        if target["mode"] != "rmb" or target["direction"] != "fall_to":
            raise SystemExit(f"watch target mode or direction was not normalized: {target}")
        if target["price"] != 688.8:
            raise SystemExit(f"watch target price was not normalized: {target}")
        if len(target["note"]) != app.WATCH_TARGET_NOTE_LIMIT:
            raise SystemExit("watch target note must be limited")

        saved = app.save_watch_targets([target])
        loaded = app.load_watch_targets()
        if loaded != saved:
            raise SystemExit(f"watch target save/load roundtrip failed: {loaded} != {saved}")

        payload = json.loads(Path(app.WATCH_TARGETS_PATH).read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or "items" not in payload:
            raise SystemExit(f"watch target file must use an items payload, got: {payload}")

        edited = app.normalize_watch_target(
            {
                **loaded[0],
                "price": 690,
                "triggered": True,
                "triggered_at": "2026-06-12T10:00:00",
                "last_trigger_price": 688.8,
            },
            existing={
                **loaded[0],
                "triggered": True,
                "triggered_at": "2026-06-12T09:00:00",
                "last_trigger_price": 688.8,
            },
        )
        if edited["triggered"] or edited["triggered_at"] or edited["last_trigger_price"] is not None:
            raise SystemExit(f"price or direction edits must reset trigger state, got: {edited}")

        app.save_watch_targets([
            edited,
            {"id": "bad-mode", "mode": "bad", "direction": "fall_to", "price": 1},
            {"id": "bad-direction", "mode": "rmb", "direction": "bad", "price": 1},
            {"id": "bad-price", "mode": "rmb", "direction": "fall_to", "price": 0},
        ])
        loaded = app.load_watch_targets()
        if len(loaded) != 1 or loaded[0]["id"] != edited["id"]:
            raise SystemExit(f"invalid watch target rows must be skipped, got: {loaded}")

        app.watch_targets = loaded
        state = app.get_watch_targets_state()
        if state["total"] != 1 or state["enabled"] != 1 or state["triggered"] != 0:
            raise SystemExit(f"watch target state summary is incorrect: {state}")

        diagnostics = json.loads(app.build_diagnostics_report())
        if diagnostics["paths"].get("watch_targets") != app.WATCH_TARGETS_PATH:
            raise SystemExit("diagnostics must include watch target path")
        if diagnostics["watch_targets"]["total"] != 1:
            raise SystemExit("diagnostics must include watch target summary")

        for invalid in (
            {"mode": "bad", "direction": "fall_to", "price": 1},
            {"mode": "rmb", "direction": "bad", "price": 1},
            {"mode": "rmb", "direction": "fall_to", "price": -1},
            "not-a-dict",
        ):
            try:
                app.normalize_watch_target(invalid)
            except ValueError:
                continue
            raise SystemExit(f"invalid watch target must raise ValueError: {invalid}")

        app.alert_rules = []
        app._sync_legacy_alert_rule_views()
        socket_client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
        if not socket_client.is_connected():
            raise SystemExit("authorized socket client must connect for watch target checks")
        init_events = socket_client.get_received()
        init_state = next((event["args"][0] for event in init_events if event["name"] == "init_state"), None)
        if init_state is None or "watch_targets" not in init_state:
            raise SystemExit(f"init_state must include watch targets, got: {init_events}")

        socket_client.emit("set_watch_target", {
            "mode": "usd",
            "direction": "rise_to",
            "price": "2400",
            "note": "突破观察",
        })
        received = socket_client.get_received()
        updated = next((event["args"][0] for event in received if event["name"] == "watch_targets_updated"), None)
        if not updated or updated["total"] != 1:
            raise SystemExit(f"set_watch_target must broadcast updated state, got: {received}")
        socket_target = updated["items"][0]

        socket_client.emit("toggle_watch_target", {"id": socket_target["id"], "enabled": False})
        received = socket_client.get_received()
        toggled = next((event["args"][0] for event in received if event["name"] == "watch_targets_updated"), None)
        if not toggled or toggled["enabled"] != 0:
            raise SystemExit(f"toggle_watch_target must update enabled count, got: {received}")

        socket_client.emit("reset_watch_target", {"id": socket_target["id"]})
        received = socket_client.get_received()
        reset = next((event["args"][0] for event in received if event["name"] == "watch_targets_updated"), None)
        if not reset or reset["triggered"] != 0:
            raise SystemExit(f"reset_watch_target must broadcast state, got: {received}")

        socket_client.emit("delete_watch_target", {"id": socket_target["id"]})
        received = socket_client.get_received()
        deleted = next((event["args"][0] for event in received if event["name"] == "watch_targets_updated"), None)
        if not deleted or deleted["total"] != 0:
            raise SystemExit(f"delete_watch_target must remove item, got: {received}")

        socket_client.emit("set_watch_target", {"mode": "bad", "direction": "rise_to", "price": "1"})
        received = socket_client.get_received()
        if not any(event["name"] == "watch_target_error" for event in received):
            raise SystemExit(f"invalid socket payload must emit watch_target_error, got: {received}")
        socket_client.disconnect()

        emitted_alerts = []

        def capture_alert(entry, title):
            emitted_alerts.append((dict(entry), title))
            app.alert_log.append(dict(entry))

        def fail_risk_analysis(*args, **kwargs):
            raise SystemExit("watch target checks must not trigger risk analysis automatically")

        app.emit_alert = capture_alert
        app.run_risk_analysis = fail_risk_analysis
        app.price_usd = 2401.0
        app.price_rmb = 688.0
        app.market_observation = {
            "source": "测试金价",
            "received_at": datetime.now().isoformat(timespec="seconds"),
            "quality_level": "normal",
            "quality_score": 100,
            "usable_for_alert": True,
            "blocked_reasons": [],
        }
        app.alert_rules = []
        app._sync_legacy_alert_rule_views()
        app.upsert_watch_target({
            "mode": "usd",
            "direction": "rise_to",
            "price": 2400,
            "note": "突破观察",
            "enabled": True,
        })
        app.upsert_watch_target({
            "mode": "rmb",
            "direction": "fall_to",
            "price": 690,
            "note": "预算观察价",
            "enabled": False,
        })
        triggered = app.check_alert_rules("12:00:00")
        if len(triggered) != 1 or triggered[0]["rule"].get("kind") != "watch_target":
            raise SystemExit(f"only enabled matching watch target should trigger, got: {triggered}")
        if len(emitted_alerts) != 1:
            raise SystemExit(f"watch target trigger must emit one alert, got: {emitted_alerts}")
        alert_entry, alert_title = emitted_alerts[0]
        if alert_title != "目标价观察提醒" or alert_entry.get("source") != "watch_target":
            raise SystemExit(f"watch target alert metadata is incorrect: {emitted_alerts}")
        if not app.watch_targets[0]["triggered"] or app.watch_targets[0]["last_trigger_price"] != 2401.0:
            raise SystemExit(f"triggered watch target state was not persisted: {app.watch_targets}")

        triggered_again = app.check_alert_rules("12:00:10")
        if triggered_again or len(emitted_alerts) != 1:
            raise SystemExit("triggered watch target must not repeat before reset")

        ok, _state = app.reset_watch_target(app.watch_targets[0]["id"])
        if not ok:
            raise SystemExit("reset_watch_target must find existing item")
        triggered_after_reset = app.check_alert_rules("12:00:20")
        if len(triggered_after_reset) != 1 or len(emitted_alerts) != 2:
            raise SystemExit("reset watch target should be able to trigger again")
    finally:
        app.WATCH_TARGETS_PATH = original_path
        app.ALERT_RULES_PATH = original_alert_rules_path
        app.alert_rules = original_alert_rules
        app.watch_targets = original_targets
        app.price_usd = original_price_usd
        app.price_rmb = original_price_rmb
        app.market_observation = original_market_observation
        app.alert_log = original_alert_log
        app.emit_alert = original_emit_alert
        app.run_risk_analysis = original_run_risk_analysis

print("watch targets checks passed.")
