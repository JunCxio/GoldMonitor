from pathlib import Path


source = Path("app.py").read_text(encoding="utf-8")
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

if "time.sleep(1)" in main_block:
    raise SystemExit("desktop startup must not use a fixed one-second sleep before showing the window")

print("startup contract checks passed.")
