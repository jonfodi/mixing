"""Path tests. Given a mocked state, does the agent take the step we expect next?
The model is real. Every tool result is fake, so nothing reaches Ableton or a subagent.
Run: pytest -m eval test_paths.py"""
import pytest

import ableton
import llm
from fake_song import FakeSong

pytestmark = pytest.mark.eval

STEMS = ["VOCALS", "DRUMS", "BASS"]

# What each tool would return. A test can swap any of these.
MOCKS = {
    "organize": "Theme: lonely, like the last person awake in the city.\n\nAsks:\nnone",
    "read_track": "no effects",
    "apply_controls": "applied: done",
    "record_feedback": "saved",
    "revert": "reverted 1 turn(s).",
}

# A finished earlier turn: the agent put a long reverb on the vocals.
REVERB_TURN = [
    {"role": "user", "content": "Turn 1.\n\nTheme so far: none yet\n\nDecisions:\nnone yet\n\nStems: VOCALS, DRUMS, BASS\n\nadd a long reverb to the vocals"},
    {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_01", "name": "apply_controls", "input": {
        "stem": "VOCALS", "controls": [{"effect": "Reverb", "setting": "Decay Time", "value": "6 s", "reason": "space around the voice"}]}}]},
    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_01", "content": "applied: Reverb / Decay Time = 6.1 s"}]},
    {"role": "assistant", "content": "I added a 6 s reverb to the vocals to give them space."},
]


@pytest.fixture(autouse=True)
def state(monkeypatch):
    monkeypatch.setattr(ableton, "send", FakeSong(STEMS).send)
    monkeypatch.setattr(llm, "brief", {"theme": "", "decisions": []})
    monkeypatch.setattr(llm, "turns", [])
    llm.system_prompt.cache_clear()


def run(message, stop, history=(), mocks=None, limit=5):
    """Run the agent with fake tool results until it calls a tool in stop or replies. Returns every tool call in order."""
    mocks = {**MOCKS, **(mocks or {})}
    llm.turns.extend([None] * (len(history) // 4 + 1))
    messages = [*history, {"role": "user", "content": f"{llm.header(STEMS)}\n\n{message}"}]
    calls = []
    for _ in range(limit):
        response = llm.client.beta.messages.create(
            model=llm.MODEL, max_tokens=16000, system=llm.system_prompt(),
            tools=[t.to_dict() for t in llm.TOOLS], thinking={"type": "adaptive"}, messages=messages,
        )
        uses = [b for b in response.content if b.type == "tool_use"]
        calls += uses
        if not uses or any(u.name in stop for u in uses):
            break
        messages += [
            {"role": "assistant", "content": response.content},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": u.id, "content": mocks[u.name]} for u in uses]},
        ]
    return calls


@pytest.mark.parametrize("message", [
    "make the vocals feel lonely, like the last person awake in the city",
    "this song is about leaving home for the first time",
    "add some delay because it should feel like a memory",
])
def test_feeling_calls_organize_first(message):
    calls = run(message, stop={"organize", "apply_controls"})
    assert calls[0].name == "organize"


@pytest.mark.parametrize("message", ["a bit more", "too much, dial it back"])
def test_short_followup_skips_organize(message):
    llm.brief["theme"] = "Lonely, like the last person awake in the city."
    calls = run(message, stop={"apply_controls", "revert"}, history=REVERB_TURN,
                mocks={"read_track": "Reverb\n  Decay Time = 6.1 s\n  Dry/Wet = 50.0 %"})
    assert "organize" not in [c.name for c in calls]


def test_reaction_is_recorded_as_rejected():
    calls = run("I hate that reverb. it sounds too far away", stop={"record_feedback"}, history=REVERB_TURN)
    feedback = [c for c in calls if c.name == "record_feedback"]
    assert feedback and feedback[0].input["liked"] is False


def test_rejected_idea_stays_out():
    llm.brief["decisions"].append("rejected: reverb on VOCALS (it sounds too far away)")
    calls = run("make the vocals feel more emotional and bigger", stop={"apply_controls"})
    applied = [c for c in calls if c.name == "apply_controls" and c.input["stem"] == "VOCALS"]
    assert applied, "the agent never changed the vocals"
    assert all(ctl["effect"] != "Reverb" for c in applied for ctl in c.input["controls"])
