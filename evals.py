import json
import subprocess
from datetime import datetime
from pathlib import Path

import core
import llm


def names(effects):
    return [d["name"] for d in effects]


def value(effects, effect, setting):
    return core.number(next(p["display"] for d in effects if d["name"] == effect for p in d["parameters"] if p["name"] == setting))


# A step is a turn (message, check) or a pause with instructions for the tester.
# A check gets the reply and the track's effects before and after the turn. None means only the tester grades it.
TESTS = [
    ("nothing to guess from: a question only", [
        ("make it better", lambda r, before, after: not r["controls"]),
    ]),
    ("vague but worth a try: controls, plus a question about the warmth", [
        ("make it warmer", lambda r, before, after: bool(r["controls"])),
    ]),
    ("exact request: one EQ, no question", [
        ("cut 300 Hz on this track by 3 dB", lambda r, before, after: len({c["effect"] for c in r["controls"]}) == 1 and "EQ" in r["controls"][0]["effect"]),
    ]),
    ("too much: the same reverb turned down, no new effect", [
        ("more reverb", None),
        ("too much", lambda r, before, after: names(before) == names(after) and any("Reverb" in c["effect"] for c in r["controls"])),
    ]),
    ("knob turned by hand: starts from the new value", [
        ("add some delay", None),
        "In Ableton, turn the Delay's Feedback by hand.",
        ("a little more", lambda r, before, after: value(after, "Delay", "Feedback") > value(before, "Delay", "Feedback")),
    ]),
    ("answering a question: uses the answer", [
        ("make it better", None),
        ("it feels too clean, I want it to sound like an old tape", lambda r, before, after: bool(r["controls"])),
    ]),
]


def track():
    return core.effects(core.send({"cmd": "selected"}))


def run(name, steps):
    print(f"\n=== {name} ===")
    input("Reset the track: close the project without saving, open it, click the test track. Press Enter when done.")
    history, turns = [], []
    for step in steps:
        if isinstance(step, str):
            input(f"{step} Press Enter when done.")
            continue
        message, check = step
        print(f"\n> {message}")
        before = track()
        reply, rejected = llm.turn(history, message)
        after = track()
        passed = None
        if check:
            try:
                passed = bool(check(reply, before, after))
            except Exception:
                passed = False
            print(f"\ncheck: {'pass' if passed else 'fail'}")
        grade = {"g": "good", "b": "bad"}.get(input("\nListen. Good or bad? (g/b, Enter to skip) ").strip().lower())
        why = input("Why? ") if grade else ""
        turns.append({"message": message, "reply": reply, "rejected": rejected, "check": passed, "grade": grade, "why": why})
    return {"name": name, "turns": turns}


def totals(run):
    turns = [t for test in run["tests"] for t in test["turns"]]
    checked = [t["check"] for t in turns if t["check"] is not None]
    graded = [t["grade"] for t in turns if t["grade"]]
    return f"behavior {sum(checked)} of {len(checked)} passed, sound {graded.count('good')} of {len(graded)} good"


folder = Path(__file__).with_name("results")
folder.mkdir(exist_ok=True)
previous = sorted(folder.glob("*.json"))
commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
results = {
    "date": datetime.now().isoformat(timespec="minutes"),
    "model": llm.MODEL,
    "commit": commit,
    "instructions": llm.SYSTEM,
    "tests": [run(name, steps) for name, steps in TESTS],
}
path = folder / f"{datetime.now():%Y-%m-%d_%H%M}.json"
path.write_text(json.dumps(results, indent=2))

print(f"\nsaved {path.name}")
print(f"this run:     {totals(results)}")
if previous:
    print(f"{previous[-1].name}: {totals(json.loads(previous[-1].read_text()))}")
