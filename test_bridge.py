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
