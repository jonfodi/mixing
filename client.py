import json
import socket
import sys


def send(msg):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(2)
    sock.sendto(json.dumps(msg).encode(), ("127.0.0.1", 9001))
    reply = json.loads(sock.recv(1 << 20))
    sock.close()
    if isinstance(reply, dict) and "error" in reply:
        raise RuntimeError(reply["error"])
    return reply


# usage: python3 client.py '{"cmd": "tracks"}'
if __name__ == "__main__":
    print(json.dumps(send(json.loads(sys.argv[1])), indent=2))
