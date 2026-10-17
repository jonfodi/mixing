"""Instruction tests. Did the agent do what the artist asked?
One full turn per case against a fake Ableton. Only the asks are checked. The theme has no answer key.
Run: pytest -m eval test_instructions.py"""
import time

import pytest

import ableton
import llm
from fake_song import FakeSong

pytestmark = pytest.mark.eval

STEMS = ["VOCALS", "DRUMS", "BASS"]
# A turn includes the organize and theme calls, so this is the wait the artist feels.
MAX_SECONDS = 60


def get(mix, stem, effect, setting):
    return mix[stem].get(effect, {}).get(setting)


# Each check takes the mix before and after the turn and returns True or False.
def up(stem, effect, *settings):
    """At least one setting went up. Adding the effect counts as up."""
    def check(before, after):
        if effect not in after[stem]:
            return False
        if effect not in before[stem]:
            return True
        return any(get(after, stem, effect, s) > get(before, stem, effect, s) for s in settings)
    return check


def down(stem, effect, *settings):
    """At least one setting went down."""
    return lambda before, after: any(get(after, stem, effect, s) < get(before, stem, effect, s) for s in settings)


def within(stem, effect, setting, low, high):
    """The setting stays inside a range. A forbidden range is the other side of this."""
    return lambda before, after: low <= get(after, stem, effect, setting) <= high


def has(stem, effect):
    return lambda before, after: effect in after[stem]


def unchanged(stem):
    return lambda before, after: before[stem] == after[stem]


def either(*checks):
    return lambda before, after: any(c(before, after) for c in checks)


CASES = {
    "more reverb on the vocals": (
        {"VOCALS": [("Reverb", {"Decay Time": 2, "Dry/Wet": 20})]},
        {"vocal reverb went up": up("VOCALS", "Reverb", "Decay Time", "Dry/Wet"),
         "drums untouched": unchanged("DRUMS"), "bass untouched": unchanged("BASS")},
    ),
    "compress the drums harder. don't touch the vocals": (
        {"DRUMS": [("Compressor", {"Ratio": 2, "Threshold": -10})], "VOCALS": [("Reverb", {"Decay Time": 3})]},
        {"drums compressed harder": either(up("DRUMS", "Compressor", "Ratio"), down("DRUMS", "Compressor", "Threshold")),
         "vocals untouched": unchanged("VOCALS")},
    ),
    "turn the bass down a little": (
        {"BASS": [("Utility", {"Gain": 0})]},
        {"bass went down": down("BASS", "Utility", "Gain"),
         "only a little": within("BASS", "Utility", "Gain", -6, 0)},
    ),
    "much less reverb on the vocals, they sound too far away": (
        {"VOCALS": [("Reverb", {"Decay Time": 8, "Dry/Wet": 60})]},
        {"vocal reverb went down": down("VOCALS", "Reverb", "Decay Time", "Dry/Wet"),
         "drums untouched": unchanged("DRUMS")},
    ),
    "it should feel lonely, like the last person awake. add some delay to the vocals": (
        {},
        {"vocals have delay": has("VOCALS", "Delay"),
         "drums untouched": unchanged("DRUMS"), "bass untouched": unchanged("BASS")},
    ),
}


@pytest.fixture
def song(monkeypatch):
    fake = FakeSong(STEMS)
    monkeypatch.setattr(ableton, "send", fake.send)
    monkeypatch.setattr(llm, "brief", {"theme": "", "decisions": []})
    monkeypatch.setattr(llm, "turns", [])
    llm.system_prompt.cache_clear()
    return fake


@pytest.mark.parametrize("message", CASES)
def test_does_what_was_asked(song, message):
    start, checks = CASES[message]
    for stem, effects in start.items():
        for effect, settings in effects:
            song.add(stem, effect, **settings)
    before = song.mix()
    t = time.monotonic()
    llm.turn([], message)
    seconds = time.monotonic() - t
    after = song.mix()
    failed = [name for name, check in checks.items() if not check(before, after)]
    print(f"\n{llm.MODEL} · {message}: {len(checks) - len(failed)}/{len(checks)} asks done · {seconds:.0f} s")
    assert not failed, f"not done: {failed}. before {before} after {after}"
    assert seconds < MAX_SECONDS
