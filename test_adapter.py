"""Whether a control lands on the track. This is the adapter's job, so no model is called."""
import pytest

import ableton
from fake_song import FakeSong


@pytest.fixture
def song(monkeypatch):
    fake = FakeSong(["VOCALS"])
    monkeypatch.setattr(ableton, "send", fake.send)
    return fake


def control(effect, setting, value):
    return {"effect": effect, "setting": setting, "value": value, "reason": "test"}


def test_control_is_applied_and_reported(song):
    applied, rejected = ableton.apply("VOCALS", [control("Reverb", "Decay Time", "4 s")])
    assert not rejected
    # Verify after write reports the nearest step Ableton holds.
    assert applied == ["Reverb / Decay Time = 4.1 s"]
    assert song.mix()["VOCALS"]["Reverb"]["Decay Time"] == 4.1


def test_unknown_effect_is_rejected(song):
    _, rejected = ableton.apply("VOCALS", [control("Space Echo", "Time", "1 s")])
    assert "not a stock effect" in rejected[0]
    assert song.tracks["VOCALS"] == []


def test_unknown_setting_lists_the_real_ones(song):
    _, rejected = ableton.apply("VOCALS", [control("Reverb", "Size", "big")])
    assert "Decay Time" in rejected[0]


def test_out_of_range_is_rejected(song):
    _, rejected = ableton.apply("VOCALS", [control("Reverb", "Decay Time", "90 s")])
    assert "outside the range" in rejected[0]


def test_existing_effect_is_reused(song):
    song.add("VOCALS", "Reverb", **{"Decay Time": 2})
    ableton.apply("VOCALS", [control("Reverb", "Decay Time", "6 s")])
    assert [d["name"] for d in song.tracks["VOCALS"]] == ["Reverb"]
