import copy
import io
import json

import pytest

import ableton
import client
import llm
from client import BridgeDown


class Conn:
    def __init__(self, reply):
        self.reply = reply

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def sendall(self, data):
        pass

    def makefile(self, mode):
        return io.BytesIO(self.reply)


@pytest.fixture
def bridge(monkeypatch):
    """A fake Ableton. Each connection takes the next outcome: an exception to raise, raw bytes, or a reply."""
    outcomes = []
    connects = []

    def connect(addr, timeout):
        connects.append(addr)
        o = outcomes.pop(0)
        if isinstance(o, Exception):
            raise o
        return Conn(o if isinstance(o, bytes) else json.dumps(o).encode() + b"\n")

    monkeypatch.setattr(client.socket, "create_connection", connect)
    monkeypatch.delenv("BRIDGE_FAIL_AT", raising=False)
    return outcomes, connects


def test_dropped_call_is_retried(bridge):
    outcomes, connects = bridge
    outcomes += [TimeoutError(), ["VOCALS"]]
    assert client.send({"cmd": "tracks"}) == ["VOCALS"]
    assert len(connects) == 2


def test_insert_is_not_retried(bridge):
    outcomes, connects = bridge
    outcomes += [TimeoutError(), {"ok": True}]
    with pytest.raises(BridgeDown):
        client.send({"cmd": "insert", "track": "VOCALS", "device": "Reverb"})
    assert len(connects) == 1


def test_repeated_failure_is_bridge_down(bridge):
    outcomes, connects = bridge
    outcomes += [ConnectionRefusedError(), ConnectionRefusedError()]
    with pytest.raises(BridgeDown):
        client.send({"cmd": "tracks"})
    assert len(connects) == 2


def test_empty_reply_is_bridge_down(bridge):
    outcomes, _ = bridge
    outcomes += [b"", b""]
    with pytest.raises(BridgeDown):
        client.send({"cmd": "tracks"})


def test_ableton_error_goes_to_the_model(bridge):
    outcomes, connects = bridge
    outcomes += [{"error": "not a stock effect"}]
    with pytest.raises(RuntimeError):
        client.send({"cmd": "insert", "track": "VOCALS", "device": "Nope"})
    assert len(connects) == 1


def test_fault_injection(monkeypatch):
    monkeypatch.setattr(client, "calls", 0)
    monkeypatch.setenv("BRIDGE_FAIL_AT", "1")
    with pytest.raises(BridgeDown):
        client.send({"cmd": "tracks"})


def test_bridge_down_stops_the_turn(monkeypatch):
    def down(stem, controls):
        raise BridgeDown("timed out")

    monkeypatch.setattr(ableton, "apply", down)
    monkeypatch.setattr(llm, "down", None)
    control = {"effect": "Reverb", "setting": "Decay Time", "value": "4 s", "reason": "space"}
    result = llm.apply_controls.call({"stem": "VOCALS", "controls": [control]})
    assert result.startswith("stopped")
    assert isinstance(llm.down, BridgeDown)


class FakeAbleton:
    """Tracks as {stem: [effect]}. Each effect has a name and parameters with a name and a raw value."""

    def __init__(self, tracks):
        self.tracks = tracks

    def send(self, msg):
        if msg["cmd"] == "tracks":
            return [{"name": n, "devices": copy.deepcopy(d)} for n, d in self.tracks.items()]
        devices = self.tracks[msg["track"]]
        if msg["cmd"] == "delete":
            del devices[msg["device"]]
        if msg["cmd"] == "set":
            next(p for p in devices[msg["device"]]["parameters"] if p["name"] == msg["param"])["value"] = msg["value"]
        return {"ok": True}


def effect(name, **values):
    return {"name": name, "parameters": [{"name": k, "value": v} for k, v in values.items()]}


@pytest.fixture
def song(monkeypatch):
    fake = FakeAbleton({"VOCALS": [effect("EQ Eight", Gain=0.5)], "DRUMS": [effect("Compressor", Ratio=0.2)]})
    monkeypatch.setattr(ableton, "send", fake.send)
    monkeypatch.setattr(llm, "touched", set())
    return fake


def test_rollback_removes_added_effects_and_restores_values(song):
    before = ableton.snapshot()
    song.tracks["VOCALS"].append(effect("Reverb", Decay=0.9))
    song.tracks["VOCALS"][0]["parameters"][0]["value"] = 0.8
    llm.touched.add("VOCALS")
    assert llm.rollback(before) == "I put the track back the way it was."
    assert song.tracks["VOCALS"] == [effect("EQ Eight", Gain=0.5)]


def test_rollback_leaves_untouched_stems_alone(song):
    before = ableton.snapshot()
    song.tracks["VOCALS"].append(effect("Reverb", Decay=0.9))
    # The artist turns a dial on DRUMS by hand during the turn.
    song.tracks["DRUMS"][0]["parameters"][0]["value"] = 0.7
    llm.touched.add("VOCALS")
    llm.rollback(before)
    assert song.tracks["DRUMS"] == [effect("Compressor", Ratio=0.7)]


def test_rollback_stops_when_effects_were_moved(song):
    before = ableton.snapshot()
    song.tracks["VOCALS"].insert(0, effect("Utility", Gain=0.1))
    llm.touched.add("VOCALS")
    assert llm.rollback(before) == "Some changes from this turn may still be on the track."


def test_rollback_reports_when_ableton_is_down(song, monkeypatch):
    before = ableton.snapshot()
    llm.touched.add("VOCALS")

    def down(msg):
        raise BridgeDown("timed out")

    monkeypatch.setattr(ableton, "send", down)
    assert llm.rollback(before) == "Some changes from this turn may still be on the track."


def test_nothing_touched_means_nothing_to_roll_back(song):
    assert llm.rollback(ableton.snapshot()) == "Nothing on the track was changed."
