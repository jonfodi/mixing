import functools
import os
import sqlite3
import sys
import time
from typing import TypedDict

import anthropic
from anthropic import beta_tool
from anthropic.lib.tools import ToolError
from dotenv import load_dotenv

import ableton
import store
from client import BridgeDown
from organize import split
from theme import build as build_theme

# Settings typed in the terminal win over .env.
load_dotenv()

# haiku is cheap for checking the wiring. Use opus to judge taste.
MODEL = os.environ.get("MODEL", "claude-haiku-5-5")
MAX_STEPS = 8

SYSTEM = """You are a mix engineer working in an artist's Ableton Live 12 project.

The artist tells you what they want. It may be a feeling, a story, a reference song, a part of the sound, or an exact effect setting.

The theme is the message or emotion they want to communicate. The theme so far is at the top of each message. When the artist says anything about feeling, story, or meaning, call organize first. It updates the theme and gives back their concrete asks. Then choose controls that communicate the theme. Every control should trace back to it.

When you are done, reply to the artist. Say in plain words what you changed and why. You may ask them a question.

Use only effects from the list you are given. Name each setting exactly as Ableton shows it. Write each value the way Ableton displays it, with its unit, for example: Reverb, Decay Time, 3 s. For a setting that is a choice, write the choice as Ableton shows it.

Decisions at the top of each message list what the artist liked and rejected. Never bring back something they rejected unless they ask for it.

The artist may turn dials by hand between turns. Read before you change an effect already on it. Build on what is there. Do not start over."""


# The tools. The docstrings are what the model reads. Each tool hands its work to the Ableton adapter.

DOWN = "Ableton stopped responding. Check Ableton and try again."

# Set when Ableton stops answering. The model cannot fix that, so the turn ends after this step.
down = None
# Stems the agent changed this turn. Rollback puts back only these, so the artist's hand edits elsewhere survive.
touched = set()
# What the agent knows about the song across turns. Only the theme module writes the theme.
brief = {"theme": "", "decisions": []}
# One entry per turn: the snapshot from its start and the stems it touched. revert reads these.
turns = []


def show_brief():
    decisions = "\n".join(f"- {d}" for d in brief["decisions"]) or "none yet"
    return f"Theme so far: {brief['theme'] or 'none yet'}\n\nDecisions:\n{decisions}"
# The artist's message this turn. organize reads it here so the model never has to copy it.
current = ""


def stop(e):
    global down
    down = e
    return "stopped: Ableton is not responding."


def rollback(before):
    """Put every touched stem back to the snapshot from the start of the turn. Returns what to tell the artist."""
    if not touched:
        return "Nothing on the track was changed."
    try:
        if all([ableton.reconcile(stem, before[stem]) for stem in touched & before.keys()]):
            return "I put the track back the way it was."
    except (BridgeDown, RuntimeError):
        pass
    return "Some changes from this turn may still be on the track."


class Control(TypedDict):
    effect: str
    setting: str
    value: str
    reason: str


@beta_tool
def organize() -> str:
    """Sort the artist's message into theme material and concrete asks, and update the song's theme from it.
    Call it when the artist says anything about feeling, story, or meaning, even alongside concrete asks.
    Skip it for short follow-ups like "a bit more". Returns the updated theme and the asks."""
    # The agent decides when to call this. Inside, the steps are fixed: split, then update the theme if there is material.
    try:
        s = split(current)
        if s.theme_material:
            brief["theme"] = build_theme(brief["theme"], s.theme_material)
    except anthropic.APIError as e:
        # The main agent can still act on the message as written, so this does not stop the turn.
        return f"organize failed ({type(e).__name__}). Work from the artist's message as written."
    asks = "\n".join(f"- {a}" for a in s.asks) or "none"
    return f"Theme: {brief['theme'] or 'none yet'}\n\nAsks:\n{asks}"


@beta_tool
def record_feedback(liked: bool, what: str, why: str) -> str:
    """Save what the artist liked or rejected so later turns respect it. Call it whenever the artist reacts to a change.

    Args:
        liked: true if the artist liked it. false if they rejected it.
        what: the change, specific enough to recognize later. For example: 6 s reverb on VOCALS.
        why: the artist's reason in their words, or "no reason given".
    """
    brief["decisions"].append(f"{'liked' if liked else 'rejected'}: {what} ({why})")
    return "saved"


@beta_tool
def revert(turns_back: int = 1) -> str:
    """Put the track back to how it was before an earlier turn. Use it when the artist wants to undo, go back, or return to an earlier version.

    Args:
        turns_back: how many turns to undo. 1 undoes the last turn.
    """
    # This turn is turns[-1], so the earlier turns are everything before it.
    if not 1 <= turns_back < len(turns):
        raise ToolError(f"there are {len(turns) - 1} earlier turns to undo")
    past = turns[-1 - turns_back:-1]
    target = past[0]["before"]
    # Only the stems those turns changed. Hand edits on other stems survive.
    stems = set().union(*(t["touched"] for t in past)) & target.keys()
    if not stems:
        return "nothing to undo. those turns changed nothing on the track."
    # If this turn fails later, rollback puts back what was there before the revert.
    touched.update(stems)
    try:
        ok = all([ableton.reconcile(s, target[s]) for s in stems])
        # Verify after write: tell the model what is on the track now.
        now = "\n\n".join(f"{s}:\n{ableton.state(s)}" for s in sorted(stems))
    except BridgeDown as e:
        return stop(e)
    status = "reverted" if ok else "could not fully revert because an effect was moved by hand"
    return f"{status} {turns_back} turn(s). Now on the track:\n\n{now}"


@beta_tool
def read_track(stem: str) -> str:
    """See the effects on one stem and their settings now.

    Args:
        stem: the stem's name, exactly as listed.
    """
    try:
        return ableton.state(stem)
    except LookupError as e:
        # A ToolError goes back to the model as an error it can fix.
        raise ToolError(str(e))
    except BridgeDown as e:
        return stop(e)


@beta_tool
def apply_controls(stem: str, controls: list[Control]) -> str:
    """Set controls on one stem. Returns each applied control with the value Ableton now shows, and each rejected control with the reason. Fix rejected ones if you can.

    Args:
        stem: the stem's name, exactly as listed.
        controls: each one an effect, a setting, a value, and a reason. In reason, say in plain words how the control serves the theme.
    """
    touched.add(stem)
    try:
        applied, rejected = ableton.apply(stem, controls)
    except BridgeDown as e:
        return stop(e)
    return "\n".join([f"applied: {a}" for a in applied] + [f"rejected: {r}" for r in rejected])


# The SDK retries twice on its own. 60 s stops a hung request from freezing the program. The default is 10 minutes.
client = anthropic.Anthropic(timeout=60.0)


# Stock effects do not change during a session, so they sit in the system prompt where they cache.
# functools.cache keeps the first result. A failed fetch is not kept, so the next turn tries again.
@functools.cache
def system_prompt():
    return f"{SYSTEM}\n\nEffects you can use: {', '.join(ableton.available())}"


TOOLS = [organize, read_track, apply_controls, record_feedback, revert]


def header(stems):
    """Only what changes between turns. The stems stay here because the artist can add or rename tracks."""
    return f"Turn {len(turns)}.\n\n{show_brief()}\n\nStems: {', '.join(stems)}"


def turn(history, message):
    """One artist turn. The runner sends the messages to the model, runs any tools it asks for, and repeats until it replies.
    history is the whole conversation as messages. The model remembers nothing, so every request sends all of it.
    Adds this turn's messages to history. Returns the reply and one step per model call."""
    global down, current, touched
    down = None
    current = message
    # A new set each turn, because turns keeps every turn's set for revert.
    touched = set()
    steps = []
    try:
        # The snapshot is what the track looked like before the agent touched it. Its keys are the stems.
        before = ableton.snapshot()
        turns.append({"before": before, "touched": touched})
        system = system_prompt()
        known = header(before)
    except BridgeDown:
        # Ableton is down before the model is called, so the turn costs nothing.
        print(f"\n{DOWN}")
        return DOWN, steps
    history.append({"role": "user", "content": f"{known}\n\n{message}"})
    runner = client.beta.messages.tool_runner(
        model=MODEL, max_tokens=16000, system=system,
        # Automatic caching: the cache point moves to the end of the request on every step,
        # so each step reuses everything the last one sent.
        cache_control={"type": "ephemeral"},
        # The model thinks before each step. summarized sends back a readable summary of that thinking.
        thinking={"type": "adaptive", "display": "summarized"},
        tools=TOOLS, messages=history, max_iterations=MAX_STEPS,
    )
    start = time.monotonic()
    try:
        for response in runner:
            ms = round((time.monotonic() - start) * 1000)
            thinking = "".join(b.thinking for b in response.content if b.type == "thinking")
            # Printed before the tools run, so subagent lines show up under their step.
            # in is the new part at full price. cached is reused from the last request at about 10% of the price.
            u = response.usage
            print(f"\nstep {len(steps) + 1} · {ms} ms · in {u.input_tokens} cached {u.cache_read_input_tokens} out {u.output_tokens}")
            if thinking:
                print(f"  thinking: {thinking}")
            # Runs the tools the model asked for. None if it asked for none.
            results = runner.generate_tool_call_response()
            # The runner keeps its own copy of the messages, so we keep ours for the next turn.
            history.append({"role": "assistant", "content": response.content})
            if results:
                history.append(results)
            calls = [b for b in response.content if b.type == "tool_use"]
            outputs = [r["content"] for r in results["content"]] if results else []
            step = {
                "thinking": thinking,
                "tools": [{"name": c.name, "input": c.input, "result": o} for c, o in zip(calls, outputs)],
                "usage": response.usage.to_dict(),
                "ms": ms,
            }
            steps.append(step)
            for t in step["tools"]:
                print(f"  {t['name']}({t['input']})")
                print("    -> " + str(t["result"]).replace("\n", "\n       "))
            if down:
                break
            start = time.monotonic()
    except anthropic.APIError as e:
        # The SDK already retried. The history stays valid, so the artist can just try again.
        reply = f"I could not reach Claude ({type(e).__name__}). {rollback(before)} Try again in a moment."
    else:
        reply = "".join(b.text for b in response.content if b.type == "text")
        if down:
            reply = f"Ableton stopped responding. {rollback(before)} Check Ableton and try again."
        elif response.stop_reason == "tool_use":
            reply = f"I stopped after {MAX_STEPS} steps without finishing. Tell me what you hear."
    print(f"\n{reply}")
    return reply, steps


if __name__ == "__main__":
    db = store.connect()
    if "--resume" in sys.argv:
        session, history, brief, turns = store.load(db)
        print(f"Resumed session {session} after turn {len(turns)}.\n\n{show_brief()}")
    else:
        history = []
        # VARIANT tags the session for an A/B comparison in feedback.py.
        session = store.start(db, MODEL, os.environ.get("VARIANT", "A"))
    print("What do you want the song to feel like? Press Enter on an empty line to stop.")
    while message := input("\n> "):
        n = len(turns)
        start = time.monotonic()
        reply, steps = turn(history, message)
        # No new snapshot means Ableton was down before the model was called. There is nothing to save.
        if len(turns) == n:
            continue
        try:
            # The track as the agent left it. The next turn's snapshot shows what the artist changed by hand.
            after = ableton.snapshot()
        except BridgeDown:
            after = None
        try:
            store.save_turn(db, session, len(turns), message, reply, steps, turns[-1], after, brief, history, time.monotonic() - start)
        except sqlite3.Error as e:
            # The data matters more than the session, so the session stops. This turn is printed so it is not lost.
            print(f"\nI could not save this session ({e}). Nothing after this turn would be kept, so I stopped.")
            print("Fix the disk and run with --resume. This turn as JSON:\n")
            print(store.dump({"session": session, "message": message, "reply": reply, "steps": steps, "turn": turns[-1], "after": after, "brief": brief}))
            sys.exit(1)
