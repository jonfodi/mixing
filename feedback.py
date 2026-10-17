"""Scores how the artist felt, from saved sessions, and compares versions.
Run: python feedback.py"""
import json
from collections import defaultdict

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel

import store
from ableton import values

load_dotenv()

# Reading one reaction is a narrow job, so the cheap model does it.
MODEL = "claude-haiku-5-5"

# Dollars per million tokens: input and output. Cache reads cost 10% of input. Cache writes cost 125%.
PRICES = {"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2, 10), "claude-opus-5-5": (4, 20)}

SYSTEM = """You read one exchange between a mix engineer and a music artist.
The engineer changed the song and said what it did. Then the artist wrote back.

Score how the artist feels about the engineer's last change.
-1: unhappy. They reject it, undo it, or complain.
0: neutral. They move on to a new request without reacting.
1: happy. They like it or build on it.

Judge only the artist's reaction. Do not judge the engineer's work."""


class Score(BaseModel):
    sentiment: float
    reason: str


client = anthropic.Anthropic(timeout=60.0)


def tool_calls(steps, name):
    return [t for s in steps for t in s["tools"] if t["name"] == name]


def cost(model, steps):
    """The main agent's cost for one turn. organize and theme are not in steps, so they are not counted."""
    i, o = PRICES[model]
    return sum(
        (u["input_tokens"] * i + (u.get("cache_read_input_tokens") or 0) * i * 0.1
         + (u.get("cache_creation_input_tokens") or 0) * i * 1.25 + u["output_tokens"] * o) / 1e6
        for u in (s["usage"] for s in steps)
    )


def hand_fixes(turn, next_turn):
    """Stems the agent touched that the artist changed by hand before the next turn."""
    after = json.loads(turn["after"] or "null")
    before = json.loads(next_turn["before"])
    if after is None:
        return 0
    return sum(values(after.get(s, [])) != values(before.get(s, [])) for s in json.loads(turn["touched"]))


def sentiment(db, turn, previous):
    """The model grader. Each score is saved, so a turn is never paid for twice."""
    saved = db.execute("select sentiment from scores where session = ? and n = ?", (turn["session"], turn["n"])).fetchone()
    if saved:
        return saved["sentiment"]
    response = client.messages.parse(
        model=MODEL, max_tokens=2000, system=SYSTEM, output_format=Score,
        messages=[{"role": "user", "content": f"Engineer:\n{previous['reply']}\n\nArtist:\n{turn['message']}"}],
    )
    score = response.parsed_output
    db.execute("insert into scores values (?, ?, ?, ?)", (turn["session"], turn["n"], score.sentiment, score.reason))
    db.commit()
    return score.sentiment


def report(db):
    groups = defaultdict(lambda: defaultdict(list))
    for session in db.execute("select * from sessions").fetchall():
        turns = db.execute("select * from turns where session = ? order by n", (session["id"],)).fetchall()
        if not turns:
            continue
        g = groups[(session["version"], session["model"], session["variant"])]
        g["turns"].append(len(turns))
        for i, t in enumerate(turns):
            steps = json.loads(t["steps"])
            g["cost"].append(cost(session["model"], steps))
            g["seconds"].append(t["seconds"])
            feedback = tool_calls(steps, "record_feedback")
            g["liked"].append(sum(f["input"]["liked"] for f in feedback))
            g["rejected"].append(sum(not f["input"]["liked"] for f in feedback))
            g["reverts"].append(len(tool_calls(steps, "revert")))
            # The first message is a request. Every later message is a reaction to the turn before it.
            if i > 0:
                g["hand fixes"].append(hand_fixes(turns[i - 1], t))
                g["sentiment"].append(sentiment(db, t, turns[i - 1]))

    columns = ["sessions", "turns/session", "$/turn", "s/turn", "liked", "rejected", "reverts", "hand fixes", "sentiment"]
    print(f"{'version':<24}{'model':<18}{'variant':<9}" + "".join(f"{c:>15}" for c in columns))
    for (version, model, variant), g in groups.items():
        sentiments = g["sentiment"]
        row = [
            len(g["turns"]), sum(g["turns"]) / len(g["turns"]),
            sum(g["cost"]) / len(g["cost"]), sum(g["seconds"]) / len(g["seconds"]),
            sum(g["liked"]), sum(g["rejected"]), sum(g["reverts"]), sum(g["hand fixes"]),
            sum(sentiments) / len(sentiments) if sentiments else float("nan"),
        ]
        print(f"{version:<24}{model:<18}{variant:<9}" + "".join(f"{v:>15.3g}" if isinstance(v, float) else f"{v:>15}" for v in row))


if __name__ == "__main__":
    report(store.connect())
