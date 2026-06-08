import multiprocessing
from pathlib import Path
import sys


def worker(queue):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import app

    unauthorized = app.socketio.test_client(app.app)
    if unauthorized.is_connected():
        unauthorized.disconnect()
        queue.put(["unauthorized_connected"])
        return

    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    try:
        received = client.get_received()
        event_names = [event.get("name") for event in received]
        queue.put(event_names)
    finally:
        client.disconnect()


if __name__ == "__main__":
    queue = multiprocessing.Queue()
    process = multiprocessing.Process(target=worker, args=(queue,))
    process.start()
    process.join(5)

    if process.is_alive():
        process.terminate()
        process.join(2)
        raise SystemExit("socket connect timed out while waiting for init_state")

    if process.exitcode != 0:
        raise SystemExit(f"socket connect worker exited with code {process.exitcode}")

    events = queue.get(timeout=1)
    if "unauthorized_connected" in events:
        raise SystemExit("socket connect must reject clients without the access token")

    if "init_state" not in events:
        raise SystemExit(f"socket connect did not emit init_state: {events}")

    print("socket connect checks passed.")
