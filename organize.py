"""Splits what the artist writes into theme material and concrete asks.
One narrow job with its own prompt, so it can be tested and improved on its own."""
import time

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

# Splitting text is a narrow job, so the cheap model does it.
MODEL = "claude-haiku-5-5"

SYSTEM = """You sort what a music artist writes about their song into two parts.

Theme material: anything about what the song means or how it should feel. Feelings, stories, images, memories, the message, how the audience should react, other songs named for their mood. Copy the artist's own words. Do not summarize or interpret.

Asks: concrete things the artist wants done to the sound or wants to try. An effect, a setting, a part of the mix, an instrument. Write each ask as one short instruction in the artist's words.

One sentence can belong to both. "Add tape delay because it should feel nostalgic" gives the ask "add tape delay" and the theme material "it should feel nostalgic".

Leave theme material empty when there is none. Leave asks empty when there are none. Ignore greetings and small talk."""


class Split(BaseModel):
    theme_material: str
    asks: list[str]


client = anthropic.Anthropic(timeout=60.0)


def split(message):
    start = time.monotonic()
    response = client.messages.parse(
        model=MODEL, max_tokens=16000, system=SYSTEM,
        messages=[{"role": "user", "content": message}], output_format=Split,
    )
    ms = round((time.monotonic() - start) * 1000)
    print(f"    [organize · {MODEL} · {ms} ms · in {response.usage.input_tokens} out {response.usage.output_tokens}]")
    # A refusal has no parsed output. Treat it as nothing found.
    return response.parsed_output or Split(theme_material="", asks=[])
