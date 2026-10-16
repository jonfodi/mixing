"""Rule checks on the full agent. Each one is true or false. They call the real model, so plain pytest skips them.
Run: pytest -m eval"""
import copy

import pytest

import ableton
import llm

pytestmark = pytest.mark.eval

# Each setting: lowest value, highest value, unit. A raw value of 0 to 1 maps evenly onto that range.
SPECS = {
    "Reverb": {"Decay Time": (0.2, 60, "s"), "Dry/Wet": (0, 100, "%")},
    "Compressor": {"Threshold": (-70, 6, "dB"), "Ratio": (1, 20, ""), "Attack": (0.1, 100, "ms")},
    "Saturator": {"Drive": (0, 36, "dB"), "Dry/Wet": (0, 100, "%")},
    "Utility": {"Gain": (-35, 35, "dB")},
}

# Dollars per million tokens: input, output. Cache reads cost 10% of input. Cache writes cost 125%.
PRICES = {"claude-haiku-5-5": (0.10, 0.50), "claude-opus-5-5": (4, 20)}


def display(effect, setting, raw):
    low, high, unit = SPECS[effect][setting]
    return f"{low + (high - low) * raw:.1f} {unit}".strip()


class FakeSong:
    """A fake Ableton that understands every command the adapter sends."""

    def __init__(self, stems):
        self.tracks = {s: [] for s in stems}

    def send(self, msg):
        cmd = msg["cmd"]
        if cmd == "effects":
            return list(SPECS)
        if cmd == "tracks":
            return [{"name": n, "devices": copy.deepcopy(d)} for n, d in self.tracks.items()]
        devices = self.tracks[msg["track"]]
        if cmd == "insert":
            if msg["device"] not in SPECS:
                return {"error": "not a stock effect"}
            name = msg["device"]
            devices.append({"name": name, "parameters": [
                {"name": s, "value": 0.5, "display": display(name, s, 0.5)} for s in SPECS[name]]})
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


@pytest.fixture
def song(monkeypatch):
    fake = FakeSong(["VOCALS", "DRUMS", "BASS"])
    monkeypatch.setattr(ableton, "send", fake.send)
    # Fresh agent state for every test.
    monkeypatch.setattr(llm, "brief", {"theme": "", "decisions": []})
    monkeypatch.setattr(llm, "turns", [])
    llm.system_prompt.cache_clear()
    return fake


def cost(steps):
    i, o = PRICES[llm.MODEL]
    return sum(
        (s["usage"]["input_tokens"] * i + s["usage"].get("cache_read_input_tokens", 0) * i * 0.1
         + (s["usage"].get("cache_creation_input_tokens") or 0) * i * 1.25 + s["usage"]["output_tokens"] * o) / 1e6
        for s in steps
    )


def called(steps, name):
    return [t for s in steps for t in s["tools"] if t["name"] == name]


def check_limits(steps):
    """Every turn must finish inside the step cap and the cost cap. Cost here is the main agent only."""
    assert len(steps) < llm.MAX_STEPS
    assert cost(steps) < 0.01


def test_feeling_calls_organize(song):
    _, steps = llm.turn([], "make the vocals feel lonely, like the last person awake in the city")
    assert called(steps, "organize")
    assert llm.brief["theme"]
    check_limits(steps)


def test_short_followup_skips_organize(song):
    history = []
    llm.turn(history, "make the vocals feel lonely, like the last person awake in the city")
    _, steps = llm.turn(history, "a bit more")
    assert not called(steps, "organize")
    check_limits(steps)


def test_applied_controls_are_real(song):
    _, steps = llm.turn([], "add a long reverb to the vocals and compress the drums")
    results = "\n".join(str(t["result"]) for t in called(steps, "apply_controls"))
    assert "applied:" in results
    # Only real effects end up on the track.
    for devices in song.tracks.values():
        assert {d["name"] for d in devices} <= set(SPECS)
    check_limits(steps)


def test_reaction_is_recorded(song):
    history = []
    llm.turn(history, "add a long reverb to the vocals")
    _, steps = llm.turn(history, "I hate that reverb. it sounds too far away")
    feedback = called(steps, "record_feedback")
    assert feedback and feedback[0]["input"]["liked"] is False
    check_limits(steps)


def test_rejected_idea_stays_out(song):
    llm.brief["decisions"].append("rejected: reverb on VOCALS (it sounds too far away)")
    _, steps = llm.turn([], "make the vocals feel more emotional and bigger")
    assert "Reverb" not in [d["name"] for d in song.tracks["VOCALS"]]
    check_limits(steps)
