import re

from client import send


def number(text):
    """Ableton or LLM value text to a number: '2.67 kHz' -> 2670, '832 ms' -> 0.832, '35 %' -> 35. None if not a number."""
    m = re.match(r"\s*(-?[\d.]+)\s*(k?)(\w*)", text)
    if not m:
        return None
    n = float(m[1]) * (1000 if m[2] else 1)
    return n / 1000 if m[3] == "ms" else n


def effects(track):
    return next(t for t in send({"cmd": "tracks"}) if t["name"] == track)["devices"]


def set_control(track, effect, setting, value):
    names = [d["name"] for d in effects(track)]
    if effect not in names:
        # Ableton raises an error for anything that is not a stock effect.
        send({"cmd": "insert", "track": track, "device": effect})
        names = [d["name"] for d in effects(track)]
    index = names.index(effect)
    settings = [p["name"] for p in effects(track)[index]["parameters"]]
    if setting not in settings:
        raise LookupError(f"no setting named {setting}. Settings are: {', '.join(settings)}")
    target = {"track": track, "device": index, "param": setting}
    # Ableton's 0 to 1 scale is uneven, so pick the sampled value whose display text is closest.
    samples = send({"cmd": "displays", **target})
    want = number(value)
    if want is None:
        matches = [raw for raw, text in samples if text.lower() == value.lower()]
        if not matches:
            raise LookupError(f"not a choice. Choices are: {', '.join(dict.fromkeys(t for _, t in samples))}")
        raw = matches[0]
    else:
        numeric = [(raw, number(text)) for raw, text in samples if number(text) is not None]
        low, high = min(n for _, n in numeric), max(n for _, n in numeric)
        if not low <= want <= high:
            raise LookupError(f"outside the range {samples[0][1]} to {samples[-1][1]}")
        raw = min(numeric, key=lambda s: abs(s[1] - want))[0]
    send({"cmd": "set", "value": raw, **target})


def apply(controls):
    """Carry out each control on the track selected in Ableton. Returns one line per rejected control."""
    track = send({"cmd": "selected"})
    rejected = []
    for c in controls:
        try:
            set_control(track, c["effect"], c["setting"], c["value"])
        except (LookupError, RuntimeError) as e:
            rejected.append(f"{c['effect']} / {c['setting']} = {c['value']}: {e}")
    return rejected
