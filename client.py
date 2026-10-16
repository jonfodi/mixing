import json
import os
import socket
import sys

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed


class BridgeDown(Exception):
    """Ableton did not answer. A timeout, a refused connection, and an empty reply all become this."""


calls = 0


def _send_once(msg):
    global calls
    calls += 1
    # Fault injection for demos and tests: every call from this number on fails.
    fail_at = os.environ.get("BRIDGE_FAIL_AT")
    if fail_at and calls >= int(fail_at):
        raise BridgeDown("fault injection")
    try:
        # One request line and one reply line per connection. TCP carries a reply of any size.
        with socket.create_connection(("127.0.0.1", 9001), timeout=2) as sock:
            sock.sendall(json.dumps(msg).encode() + b"\n")
            return json.loads(sock.makefile("rb").readline())
    except (OSError, ValueError) as e:
        raise BridgeDown(repr(e)) from e


# One retry for a dropped call. A second failure is not transient.
_retry_once = retry(retry=retry_if_exception_type(BridgeDown), stop=stop_after_attempt(2), wait=wait_fixed(0.5), reraise=True)


def send(msg):
    # insert is the one command that is not idempotent. A second insert adds a second effect.
    reply = _send_once(msg) if msg["cmd"] == "insert" else _retry_once(_send_once)(msg)
    if isinstance(reply, dict) and "error" in reply:
        raise RuntimeError(reply["error"])
    return reply


# usage: python3 client.py '{"cmd": "tracks"}'
if __name__ == "__main__":
    print(json.dumps(send(json.loads(sys.argv[1])), indent=2))
