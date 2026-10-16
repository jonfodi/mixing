"""Keeps the theme of the song. Finding the theme is the core skill of the product,
so it has its own prompt that can be tested and improved without touching the rest of the agent."""
import time

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

# The theme is where quality matters most, so the strongest model writes it.
MODEL = "claude-opus-5-5"

SYSTEM = """You keep the theme of a song for a music artist and their mix engineer.

The theme is the message or emotion the artist wants the listener to feel. Every mix decision serves it. It is not a list of effects or settings.

You get the current theme and new material the artist just wrote. Return the updated theme.

- Keep what still holds. Add what is new. When the artist changes their mind, the new words win. Drop what they took back.
- Use the artist's own words and images where you can. Do not invent feelings they did not express.
- Name the core emotion first. Then the story or image behind it. Then how it should move through the song, if they said.
- When the artist holds two feelings at once, such as "sad but hopeful", keep both.
- Write 1 to 4 short sentences in plain language. No effect names. No audio terms.
- If the new material says nothing new about meaning or feeling, return the current theme unchanged."""


class Theme(BaseModel):
    theme: str


client = anthropic.Anthropic(timeout=60.0)


def build(current, material):
    start = time.monotonic()
    response = client.beta.messages.parse(
        model=MODEL, max_tokens=16000, system=SYSTEM,
        messages=[{"role": "user", "content": f"Current theme:\n{current or '(none yet)'}\n\nNew material:\n{material}"}],
        output_format=Theme,
        # If Opus declines, the API reruns the request on a fallback model inside the same call.
        betas=["server-side-fallback-2026-07-01"], fallbacks="default",
    )
    ms = round((time.monotonic() - start) * 1000)
    print(f"    [theme · {MODEL} · {ms} ms · in {response.usage.input_tokens} out {response.usage.output_tokens}]")
    # A refusal has no parsed output. Keep the theme we had.
    return response.parsed_output.theme if response.parsed_output else current
