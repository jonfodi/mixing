"""Tool tests. Each tool is called directly with known input, the way the model would call it.
The checks: the logic is right, and what comes back gives the model what it needs to fix its next call. No model is called."""
import anthropic
import httpx2
import pytest
from anthropic.lib.tools import ToolError

import ableton
import llm
from fake_song import FakeSong
from organize import Split


@pytest.fixture
def song(monkeypatch):
    fake = FakeSong(["VOCALS", "DRUMS"])
    monkeypatch.setattr(ableton, "send", fake.send)
    monkeypatch.setattr(llm, "brief", {"theme": "", "decisions": []})
    monkeypatch.setattr(llm, "turns", [])
    monkeypatch.setattr(llm, "touched", set())
    monkeypatch.setattr(llm, "down", None)
    return fake


def test_read_track_unknown_stem_lists_the_real_ones(song):
    with pytest.raises(ToolError) as e:
        llm.read_track.call({"stem": "VOCAL"})
    assert "VOCALS, DRUMS" in str(e.value)


def test_read_track_shows_settings_as_ableton_does(song):
    song.add("VOCALS", "Reverb", **{"Decay Time": 2})
    assert "Decay Time = 2.0 s" in llm.read_track.call({"stem": "VOCALS"})


def test_apply_controls_marks_the_stem_and_reports_both_kinds(song):
    controls = [
        {"effect": "Reverb", "setting": "Decay Time", "value": "4 s", "reason": "space"},
        {"effect": "Reverb", "setting": "Size", "value": "big", "reason": "space"},
    ]
    result = llm.apply_controls.call({"stem": "VOCALS", "controls": controls})
    assert "applied: Reverb / Decay Time = 4.1 s" in result
    # The rejected line lists the real settings.
    assert "rejected: Reverb / Size = big" in result and "Decay Time" in result
    assert llm.touched == {"VOCALS"}


def test_record_feedback_saves_the_decision(song):
    assert llm.record_feedback.call({"liked": False, "what": "6 s reverb on VOCALS", "why": "too far away"}) == "saved"
    assert llm.brief["decisions"] == ["rejected: 6 s reverb on VOCALS (too far away)"]


def test_revert_with_no_earlier_turn_says_how_many_there_are(song):
    llm.turns.append({"before": ableton.snapshot(), "touched": llm.touched})
    with pytest.raises(ToolError) as e:
        llm.revert.call({"turns_back": 1})
    assert "0 earlier turns" in str(e.value)


def test_revert_puts_back_only_what_the_agent_changed(song):
    # Turn 1: the agent adds reverb to the vocals.
    llm.turns.append({"before": ableton.snapshot(), "touched": {"VOCALS"}})
    song.add("VOCALS", "Reverb")
    song.add("DRUMS", "Compressor")
    # Turn 2 starts. The compressor on the drums is the artist's own.
    llm.turns.append({"before": ableton.snapshot(), "touched": llm.touched})
    result = llm.revert.call({"turns_back": 1})
    assert song.tracks["VOCALS"] == []
    assert [d["name"] for d in song.tracks["DRUMS"]] == ["Compressor"]
    # Verify after write: the model is told what is on the track now.
    assert result.startswith("reverted 1 turn(s)") and "VOCALS:\nno effects" in result
    # If this turn fails later, rollback knows the revert touched the vocals.
    assert llm.touched == {"VOCALS"}


def test_organize_updates_the_theme_and_returns_the_asks(song, monkeypatch):
    monkeypatch.setattr(llm, "current", "make it lonely and add delay")
    monkeypatch.setattr(llm, "split", lambda m: Split(theme_material="make it lonely", asks=["add delay"]))
    monkeypatch.setattr(llm, "build_theme", lambda current, material: "Lonely.")
    assert llm.organize.call({}) == "Theme: Lonely.\n\nAsks:\n- add delay"
    assert llm.brief["theme"] == "Lonely."


def test_organize_failure_does_not_stop_the_turn(song, monkeypatch):
    def fail(message):
        raise anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com"))

    monkeypatch.setattr(llm, "split", fail)
    assert "Work from the artist's message as written" in llm.organize.call({})
