"""A fake Ableton that understands every command the adapter sends. Tests use it in place of the bridge."""
import copy

import ableton

# Each setting: lowest value, highest value, unit. A raw value of 0 to 1 maps evenly onto that range.
SPECS = {
    "Reverb": {"Decay Time": (0.2, 60, "s"), "Dry/Wet": (0, 100, "%")},
    "Delay": {"Feedback": (0, 95, "%"), "Dry/Wet": (0, 100, "%")},
    "Compressor": {"Threshold": (-70, 6, "dB"), "Ratio": (1, 20, ""), "Attack": (0.1, 100, "ms")},
    "Saturator": {"Drive": (0, 36, "dB"), "Dry/Wet": (0, 100, "%")},
    "Auto Filter": {"Frequency": (20, 20000, "Hz")},
    "Utility": {"Gain": (-35, 35, "dB")},
}


def display(effect, setting, raw):
    low, high, unit = SPECS[effect][setting]
    return f"{low + (high - low) * raw:.1f} {unit}".strip()


class FakeSong:
    def __init__(self, stems):
        self.tracks = {s: [] for s in stems}

    def add(self, stem, effect, **settings):
        """Put an effect on a stem before the test. Settings are in real units. Unset ones start halfway."""
        params = []
        for name, (low, high, _) in SPECS[effect].items():
            raw = (settings[name] - low) / (high - low) if name in settings else 0.5
            params.append({"name": name, "value": raw, "display": display(effect, name, raw)})
        self.tracks[stem].append({"name": effect, "parameters": params})

    def mix(self):
        """The track as numbers in real units: {stem: {effect: {setting: number}}}."""
        return {
            stem: {d["name"]: {p["name"]: ableton.number(p["display"]) for p in d["parameters"]} for d in devices}
            for stem, devices in self.tracks.items()
        }

    def send(self, msg):
        cmd = msg["cmd"]
        if cmd == "effects":
            return list(SPECS)
        if cmd == "tracks":
            return [{"name": n, "devices": copy.deepcopy(d)} for n, d in self.tracks.items()]
        devices = self.tracks[msg["track"]]
        if cmd == "insert":
            if msg["device"] not in SPECS:
                raise RuntimeError("not a stock effect")
            self.add(msg["track"], msg["device"])
            return {"ok": True}
        if cmd == "delete":
            del devices[msg["device"]]
            return {"ok": True}
        device = devices[msg["device"]]
        param = next(p for p in device["parameters"] if p["name"] == msg["param"])
        if cmd == "set":
            param["value"] = msg["value"]
            param["display"] = display(device["name"], param["name"], msg["value"])
            return {"ok": True}
        if cmd == "displays":
            return [[i / 200, display(device["name"], param["name"], i / 200)] for i in range(201)]
