import os
import time
from typing import TypedDict

import anthropic
from anthropic import beta_tool
from anthropic.lib.tools import ToolError
from dotenv import load_dotenv

import ableton
from client import BridgeDown

# Settings typed in the terminal win over .env.
load_dotenv()

# haiku is cheap for checking the wiring. Use opus to judge taste.
MODEL = os.environ.get("MODEL", "claude-haiku-5-5")
MAX_STEPS = 8

SYSTEM = """You are a mix engineer working in an artist's Ableton Live 12 project.

The artist tells you what they want. It may be a feeling, a story, a reference song, a part of the sound, or an exact effect setting.

Find the theme behind their words: the message or emotion they want to communicate. Then choose controls that communicate it. Every control should trace back to the theme.

When you are done, reply to the artist. Say in plain words what you changed and why. You may ask them a question.

Use only effects from the list you are given. Name each setting exactly as Ableton shows it. Write each value the way Ableton displays it, with its unit, for example: Reverb, Decay Time, 3 s. For a setting that is a choice, write the choice as Ableton shows it.

The artist may turn dials by hand between turns. Read before you change an effect already on it. Build on what is there. Do not start over."""


# The tools. The docstrings are what the model reads. Each tool hands its work to the Ableton adapter.

DOWN = "Ableton stopped responding. Check Ableton and try again."

# Set when Ableton stops answering. The model cannot fix that, so the turn ends after this step.
down = None
# Stems the agent changed this turn. Rollback puts back only these, so the artist's hand edits elsewhere survive.
touched = set()


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
    """Set controls on one stem. Returns any controls Ableton rejected, with the reason. Fix them if you can.

    Args:
        stem: the stem's name, exactly as listed.
        controls: each one an effect, a setting, a value, and a reason. In reason, say in plain words how the control serves the theme.
    """
    touched.add(stem)
    try:
        rejected = ableton.apply(stem, controls)
    except BridgeDown as e:
        return stop(e)
    return "\n".join(f"rejected: {r}" for r in rejected) or "all applied"


# The SDK retries twice on its own. 60 s stops a hung request from freezing the program. The default is 10 minutes.
client = anthropic.Anthropic(timeout=60.0)



def turn(history, message):
    """One artist turn. The runner sends the messages to the model, runs any tools it asks for, and repeats until it replies.
    history is the whole conversation as messages. The model remembers nothing, so every request sends all of it.
    Adds this turn's messages to history. Returns the reply and one step per model call."""
    global down
    down = None
    touched.clear()
    steps = []
    try:
        # The snapshot is what the track looked like before the agent touched it. Its keys are the stems.
        before = ableton.snapshot()
        known = f"Effects you can use: {', '.join(ableton.available())}\n\nStems: {', '.join(before)}"
    except BridgeDown:
        # Ableton is down before the model is called, so the turn costs nothing.
        print(f"\n{DOWN}")
        return DOWN, steps
    history.append({"role": "user", "content": f"{known}\n\n{message}"})
    runner = client.beta.messages.tool_runner(
        model=MODEL, max_tokens=16000, system=SYSTEM,
        # The model thinks before each step. summarized sends back a readable summary of that thinking.
        thinking={"type": "adaptive", "display": "summarized"},
        tools=[read_track, apply_controls], messages=history, max_iterations=MAX_STEPS,
    )
    start = time.monotonic()
    try:
        for response in runner:
            ms = round((time.monotonic() - start) * 1000)
            # Runs the tools the model asked for. None if it asked for none.
            results = runner.generate_tool_call_response()
            # The runner keeps its own copy of the messages, so we keep ours for the next turn.
            history.append({"role": "assistant", "content": response.content})
            if results:
                history.append(results)
            calls = [b for b in response.content if b.type == "tool_use"]
            outputs = [r["content"] for r in results["content"]] if results else []
            step = {
                "thinking": "".join(b.thinking for b in response.content if b.type == "thinking"),
                "tools": [{"name": c.name, "input": c.input, "result": o} for c, o in zip(calls, outputs)],
                "usage": response.usage.to_dict(),
                "ms": ms,
            }
            steps.append(step)
            print(f"\nstep {len(steps)} · {ms} ms · in {step['usage']['input_tokens']} out {step['usage']['output_tokens']}")
            if step["thinking"]:
                print(f"  thinking: {step['thinking']}")
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
    history = []
    print("What do you want the song to feel like? Press Enter on an empty line to stop.")
    while message := input("\n> "):
        turn(history, message)
