import json
import socket

from _Framework.ControlSurface import ControlSurface

PORT = 9001


def create_instance(c_instance):
    return SoundBridge(c_instance)


class SoundBridge(ControlSurface):
    def __init__(self, c_instance):
        super().__init__(c_instance)
        # TCP, because macOS caps one UDP packet at 9216 bytes and a track list is bigger.
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", PORT))
        self._sock.listen()
        self._sock.setblocking(False)

    # Live calls this about every 100 ms on its main thread, the only safe place to change the song.
    # Each connection carries one request line and one reply line.
    def update_display(self):
        super().update_display()
        try:
            conn, _ = self._sock.accept()
        except BlockingIOError:
            return
        with conn:
            conn.settimeout(1)
            try:
                reply = self._handle(json.loads(conn.makefile("rb").readline()))
            except Exception as e:
                reply = {"error": repr(e)}
            conn.sendall(json.dumps(reply).encode() + b"\n")

    def _handle(self, msg):
        tracks = self.song().tracks
        if msg["cmd"] == "tracks":
            return [
                {
                    "name": t.name,
                    "devices": [
                        {
                            "name": d.name,
                            "parameters": [
                                {"name": p.name, "value": p.value, "min": p.min, "max": p.max, "display": p.str_for_value(p.value)}
                                for p in d.parameters
                            ],
                        }
                        for d in t.devices
                    ],
                }
                for t in tracks
            ]
        # Every audio effect in Ableton's browser, by the name insert accepts.
        if msg["cmd"] == "effects":
            return [item.name for item in self.application().browser.audio_effects.children]
        # The track the artist last clicked in Ableton.
        if msg["cmd"] == "selected":
            return self.song().view.selected_track.name
        track = next(t for t in tracks if t.name == msg["track"])
        if msg["cmd"] == "insert":
            track.insert_device(msg["device"])
            return {"ok": True}
        # Rollback removes effects the agent added.
        if msg["cmd"] == "delete":
            track.delete_device(msg["device"])
            return {"ok": True}
        param = next(p for p in track.devices[msg["device"]].parameters if p.name == msg["param"])
        if msg["cmd"] == "set":
            param.value = msg["value"]
            return {"ok": True}
        # The text Ableton shows for 201 evenly spaced values, so the adapter can convert real units.
        if msg["cmd"] == "displays":
            values = [param.min + (param.max - param.min) * i / 200 for i in range(201)]
            return [[v, param.str_for_value(v)] for v in values]
        return {"error": "unknown cmd"}

    def disconnect(self):
        self._sock.close()
        super().disconnect()
