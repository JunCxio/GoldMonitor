import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


if app.compare_versions("1.2.0", "1.1.9") <= 0:
    raise SystemExit("1.2.0 must be newer than 1.1.9")

if app.compare_versions("1.0.0", "1.0") != 0:
    raise SystemExit("1.0.0 and 1.0 must compare as the same version")

if app.compare_versions("1.0.0", "1.0.1") >= 0:
    raise SystemExit("1.0.0 must be older than 1.0.1")

manifest = app.normalize_update_manifest({
    "version": "1.0.1",
    "url": "https://example.com/GoldMonitorSetup.exe",
    "notes": "test release",
    "sha256": "A" * 64,
})

if manifest["version"] != "1.0.1":
    raise SystemExit("manifest version was not normalized")

if manifest["url"] != "https://example.com/GoldMonitorSetup.exe":
    raise SystemExit("manifest download url was not normalized")

if manifest["sha256"] != "a" * 64:
    raise SystemExit("manifest sha256 must be lower-cased")

try:
    app.normalize_update_manifest({
        "version": "1.0.1",
        "url": "http://example.com/GoldMonitorSetup.exe",
        "sha256": "a" * 64,
    })
except ValueError:
    pass
else:
    raise SystemExit("manifest download url must require HTTPS")

try:
    app.normalize_update_manifest({
        "version": "1.0.1",
        "url": "https://example.com/GoldMonitorSetup.exe",
    })
except ValueError:
    pass
else:
    raise SystemExit("manifest must require installer sha256")

try:
    app.fetch_update_manifest("http://example.com/manifest.json")
except ValueError:
    pass
else:
    raise SystemExit("update manifest source must require HTTPS")

print("update logic checks passed.")
