"""Small localhost client for the one Firefox owner."""
import json
import socket
import time

def request(action, **values):
    deadline = time.monotonic() + 60
    while True:
        try:
            conn = socket.create_connection(("127.0.0.1", 8766), timeout=10)
            break
        except OSError:
            if time.monotonic() >= deadline:
                raise RuntimeError("Firefox is still starting. Close Firefox, restart the Hub, then try Sign in again.")
            time.sleep(1)
    with conn:
        conn.sendall((json.dumps({"action": action, **values}) + "\n").encode())
        reply = json.loads(conn.makefile(encoding="utf-8").readline())
    if not reply.get("ok"):
        raise RuntimeError(reply.get("error", "Firefox owner failed"))
    return reply.get("result")
