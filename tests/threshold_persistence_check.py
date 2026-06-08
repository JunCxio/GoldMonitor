import tempfile
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


with tempfile.TemporaryDirectory() as tmp_dir:
    original_path = app.THRESHOLDS_PATH
    try:
        app.THRESHOLDS_PATH = str(Path(tmp_dir) / "thresholds.json")
        expected = dict(app.thresholds)
        expected["upper_warning_rmb"] = 888.88
        expected["lower_critical_usd"] = 1800.0
        expected["volatility_config"] = {
            "percent": 1.5,
            "minutes": 15,
            "enabled": True,
        }
        app.save_thresholds(expected)
        loaded = app.load_thresholds()
    finally:
        app.THRESHOLDS_PATH = original_path

if loaded["upper_warning_rmb"] != 888.88:
    raise SystemExit("RMB threshold did not persist")

if loaded["lower_critical_usd"] != 1800.0:
    raise SystemExit("USD threshold did not persist")

if loaded["volatility_config"] != {"percent": 1.5, "minutes": 15, "enabled": True}:
    raise SystemExit("volatility threshold config did not persist")

for key in app.thresholds:
    if key not in loaded:
        raise SystemExit(f"missing persisted threshold key: {key}")

print("threshold persistence checks passed.")
