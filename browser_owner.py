"""Small localhost client for the one Firefox owner."""
import json
import socket

def request(action, **values):
    with socket.create_connection(("127.0.0.1", 8766), timeout=10) as conn:
        conn.sendall((json.dumps({"action": action, **values}) + "\n").encode())
        reply = json.loads(conn.makefile(encoding="utf-8").readline())
    if not reply.get("ok"):
        raise RuntimeError(reply.get("error", "Firefox owner failed"))
    return reply.get("result")
