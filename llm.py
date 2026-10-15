import json
import os
import subprocess
import tempfile
from pathlib import Path

import core

env = Path(__file__).with_name(".env")
for line in env.read_text().splitlines() if env.exists() else []:
    if "=" in line and not line.startswith("#"):
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())

# haiku is cheap for checking the wiring. Use opus to judge taste.
MODEL = os.environ.get("MODEL", "haiku")

SYSTEM = """You are a mix engineer working in an artist's Ableton Live 12 project.

The artist tells you what they want. It may be a feeling, a story, a reference song, a part of the sound, or an exact effect setting.

Find the theme behind their words: the message or emotion they want to communicate. Then choose controls that communicate it. Every control should trace back to the theme.

You are mixing one track. You can use any stock Ableton Live 12 audio effect. Name each effect and setting exactly as Ableton shows them. Write each value the way Ableton displays it, with its unit, for example: Reverb, Decay Time, 3 s. For a setting that is a choice, write the choice as Ableton shows it.

In reason, say in plain words how the control serves the theme.

Each turn you see the conversation so far and the effects on the track now. Build on them. Do not start over.

In message, talk to the artist. You may ask them a question, with or without controls."""

SCHEMA = {
    "type": "object",
    "properties": {
        "message": {"type": "string"},
        "controls": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "effect": {"type": "string"},
                    "setting": {"type": "string"},
                    "value": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["effect", "setting", "value", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["message", "controls"],
    "additionalProperties": False,
}


history = []
print("What do you want the song to feel like? Press Enter on an empty line to stop.")
while message := input("\n> "):
    prompt = "\n".join(history + [f"Track now:\n{core.state()}", f"Artist: {message}"])
    # Runs through the claude command on the artist's subscription. An empty folder keeps it from reading this project's CLAUDE.md.
    result = json.loads(subprocess.run(
        ["claude", "-p", prompt,
         "--model", MODEL, "--output-format", "json", "--json-schema", json.dumps(SCHEMA),
         "--system-prompt", SYSTEM, "--tools", "", "--strict-mcp-config", "--no-session-persistence"],
        capture_output=True, text=True, check=True, cwd=tempfile.mkdtemp(),
    ).stdout)
    if result["is_error"]:
        raise SystemExit(result.get("result"))
    reply = result["structured_output"]

    print(f"\n{reply['message']}")
    for c in reply["controls"]:
        print(f"\n{c['effect']} / {c['setting']} = {c['value']}\n  {c['reason']}")
    rejected = core.apply(reply["controls"])
    for r in rejected:
        print(f"\nrejected: {r}")
    history += [f"Artist: {message}", f"You: {json.dumps(reply)}"] + [f"Rejected: {r}" for r in rejected]
