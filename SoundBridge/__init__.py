import json
import socket

from _Framework.ControlSurface import ControlSurface

PORT = 9001


def create_instance(c_instance):
    return SoundBridge(c_instance)


class SoundBridge(ControlSurface):
    def __init__(self, c_instance):
        super().__init__(c_instance)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind(("127.0.0.1", PORT))
        self._sock.setblocking(False)

    # Live calls this about every 100 ms on its main thread, the only safe place to change the song.
    def update_display(self):
        super().update_display()
        try:
            data, addr = self._sock.recvfrom(65536)
        except BlockingIOError:
            return
        try:
            reply = self._handle(json.loads(data))
        except Exception as e:
            reply = {"error": repr(e)}
        self._sock.sendto(json.dumps(reply).encode(), addr)

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
        # The track the artist last clicked in Ableton.
        if msg["cmd"] == "selected":
            return self.song().view.selected_track.name
        track = next(t for t in tracks if t.name == msg["track"])
        if msg["cmd"] == "insert":
            track.insert_device(msg["device"])
            return {"ok": True}
        param = next(p for p in track.devices[msg["device"]].parameters if p.name == msg["param"])
        if msg["cmd"] == "set":
            param.value = msg["value"]
            return {"ok": True}
        # The text Ableton shows for 201 evenly spaced values, so the core can convert real units.
        if msg["cmd"] == "displays":
            values = [param.min + (param.max - param.min) * i / 200 for i in range(201)]
            return [[v, param.str_for_value(v)] for v in values]
        return {"error": "unknown cmd"}

    def disconnect(self):
        self._sock.close()
        super().disconnect()
