from pathlib import Path


source = Path("app.py").read_text(encoding="utf-8")
desktop_runtime_source = Path("goldmonitor/desktop_runtime.py").read_text(encoding="utf-8")
platform_runtime_source = Path("goldmonitor/platform_runtime.py").read_text(encoding="utf-8")
mac_launcher = Path("GoldMonitor.command").read_text(encoding="utf-8")
mac_script = Path("scripts/start_mac.sh").read_text(encoding="utf-8")
main_marker = 'if __name__ == "__main__":'
if main_marker not in source:
    raise SystemExit("app.py must have a main entrypoint")

main_block = source.split(main_marker, 1)[1]

for forbidden in ("fetch_gold_data(", "fetch_csv_price("):
    if forbidden in main_block:
        raise SystemExit(f"main entrypoint must not synchronously call {forbidden}")

start_background = main_block.find("start_background_fetching()")
start_window = main_block.find("start_desktop_window(")

if start_background < 0:
    raise SystemExit("main entrypoint must start background data fetching")

if start_window < 0:
    raise SystemExit("desktop entrypoint must create the pywebview window")

if 'macos_packaged_app = sys.platform == "darwin" and getattr(sys, "frozen", False)' not in main_block:
    raise SystemExit("startup must detect packaged macOS app bundles")

if 'or (macos_packaged_app and "--web" not in sys.argv)' not in main_block:
    raise SystemExit("packaged macOS app must default to desktop mode")

if 'if os.name == "nt":\n        tray_thread = threading.Thread(target=create_tray_icon, daemon=True)' not in main_block:
    raise SystemExit("Windows tray startup must still use the tray icon thread")

if 'start_hidden = (os.name == "nt" or sys.platform == "darwin") and startup_mode' not in main_block:
    raise SystemExit("startup hidden mode must support Windows tray and macOS menu bar")

if 'from goldmonitor import desktop_runtime as desktop_runtime_core' not in source:
    raise SystemExit("app.py must delegate desktop lifecycle orchestration to desktop_runtime")

if 'return desktop_runtime_core.start_desktop_window(' not in source:
    raise SystemExit("app.py must keep a compatible desktop window wrapper")

if 'webview.start(gui="edgechromium")' not in desktop_runtime_source or 'webview.start()' not in desktop_runtime_source:
    raise SystemExit("desktop window must choose the pywebview backend by platform")

if 'runtime_platform = "macos"' not in desktop_runtime_source:
    raise SystemExit("macOS desktop close must support hiding to menu bar")

if 'create_macos_status_item()' not in source:
    raise SystemExit("macOS desktop mode must create a menu bar status item")

if 'MACOS_LAUNCH_AGENT_ID' not in source or 'plistlib.dump' not in platform_runtime_source:
    raise SystemExit("macOS startup must use a user LaunchAgent")

if 'exec "$ROOT_DIR/scripts/start_mac.sh"' not in mac_launcher:
    raise SystemExit("macOS launcher must delegate to scripts/start_mac.sh")

if "exec .venv/bin/python app.py --web" not in mac_script:
    raise SystemExit("macOS startup script must run the app in browser mode")

if 'Library/Application Support' not in mac_script:
    raise SystemExit("macOS startup script must use the macOS application support directory")

if "time.sleep(1)" in main_block:
    raise SystemExit("desktop startup must not use a fixed one-second sleep before showing the window")

print("startup contract checks passed.")
