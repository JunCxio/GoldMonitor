import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
listener.bind((app.DEFAULT_HOST, 0))
occupied_port = listener.getsockname()[1]
listener.listen(1)
try:
    selected = app.find_available_port(occupied_port)
    if selected == occupied_port:
        raise SystemExit("find_available_port selected an occupied port")
finally:
    listener.close()

print(f"selected available port {selected}")
