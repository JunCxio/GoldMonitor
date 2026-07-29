from pathlib import Path


entry_source = Path("app.py").read_text(encoding="utf-8")
source = Path("goldmonitor/application.py").read_text(encoding="utf-8")
bootstrap_source = Path("goldmonitor/application_bootstrap.py").read_text(encoding="utf-8")
desktop_runtime_source = Path("goldmonitor/desktop_runtime.py").read_text(encoding="utf-8")
platform_runtime_source = Path("goldmonitor/platform_runtime.py").read_text(encoding="utf-8")
mac_launcher = Path("GoldMonitor.command").read_text(encoding="utf-8")
mac_script = Path("scripts/start_mac.sh").read_text(encoding="utf-8")
main_marker = "def main():"
if main_marker not in source:
    raise SystemExit("application module must expose a main entrypoint")

if "application.main()" not in entry_source:
    raise SystemExit("app.py must delegate execution to the application module")

if "sys.modules[__name__] = application" not in entry_source:
    raise SystemExit("app.py must preserve the import compatibility surface")

main_block = source.split(main_marker, 1)[1]

for forbidden in ("fetch_gold_data(", "fetch_csv_price("):
    if forbidden in main_block:
        raise SystemExit(f"main entrypoint must not synchronously call {forbidden}")

if "application_bootstrap_core.run_application(" not in main_block:
    raise SystemExit("main entrypoint must delegate startup orchestration")

start_background = bootstrap_source.find("start_background_fetching()")
start_window = bootstrap_source.find("start_desktop_window(")

if start_background < 0:
    raise SystemExit("main entrypoint must start background data fetching")

if start_window < 0:
    raise SystemExit("desktop entrypoint must create the pywebview window")

if 'macos_packaged_app = sys_platform == "darwin" and bool(frozen)' not in bootstrap_source:
    raise SystemExit("startup must detect packaged macOS app bundles")

if 'or (macos_packaged_app and "--web" not in arguments)' not in bootstrap_source:
    raise SystemExit("packaged macOS app must default to desktop mode")

if 'if os_name == "nt":\n        thread_factory(target=create_tray_icon, daemon=True).start()' not in bootstrap_source:
    raise SystemExit("Windows tray startup must still use the tray icon thread")

if 'os_name == "nt" or sys_platform == "darwin"' not in bootstrap_source or 'and startup_mode and get_settings().get("startup_to_tray", True)' not in bootstrap_source:
    raise SystemExit("startup hidden mode must support Windows tray and macOS menu bar")

if 'from goldmonitor import desktop_runtime as desktop_runtime_core' not in source:
    raise SystemExit("application module must delegate desktop lifecycle orchestration to desktop_runtime")

if 'return desktop_runtime_core.start_desktop_window(' not in source:
    raise SystemExit("application module must keep a compatible desktop window wrapper")

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

if "time.sleep(1)" in bootstrap_source:
    raise SystemExit("desktop startup must not use a fixed one-second sleep before showing the window")

print("startup contract checks passed.")
