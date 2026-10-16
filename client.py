import json
import socket
import sys


def send(msg):
    # One request line and one reply line per connection. TCP carries a reply of any size.
    with socket.create_connection(("127.0.0.1", 9001), timeout=2) as sock:
        sock.sendall(json.dumps(msg).encode() + b"\n")
        reply = json.loads(sock.makefile("rb").readline())
    if isinstance(reply, dict) and "error" in reply:
        raise RuntimeError(reply["error"])
    return reply


# usage: python3 client.py '{"cmd": "tracks"}'
if __name__ == "__main__":
    print(json.dumps(send(json.loads(sys.argv[1])), indent=2))
