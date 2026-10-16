import re

from client import send


def number(text):
    """Ableton or LLM value text to a number: '2.67 kHz' -> 2670, '832 ms' -> 0.832, '35 %' -> 35. None if not a number."""
    m = re.match(r"\s*(-?[\d.]+)\s*(k?)(\w*)", text)
    if not m:
        return None
    n = float(m[1]) * (1000 if m[2] else 1)
    return n / 1000 if m[3] == "ms" else n


def stems():
    return [t["name"] for t in send({"cmd": "tracks"})]


def available():
    """Every audio effect Ableton can insert, by name."""
    return send({"cmd": "effects"})


def effects(stem):
    for t in send({"cmd": "tracks"}):
        if t["name"] == stem:
            return t["devices"]
    raise LookupError(f"no stem named {stem}")


def set_control(stem, effect, setting, value):
    names = [d["name"] for d in effects(stem)]
    if effect not in names:
        # Ableton raises an error for anything that is not a stock effect.
        send({"cmd": "insert", "track": stem, "device": effect})
        names = [d["name"] for d in effects(stem)]
    index = names.index(effect)
    settings = [p["name"] for p in effects(stem)[index]["parameters"]]
    if setting not in settings:
        raise LookupError(f"no setting named {setting}. Settings are: {', '.join(settings)}")
    target = {"track": stem, "device": index, "param": setting}
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


def state(stem):
    """A stem's effects and settings, written the way Ableton shows them."""
    lines = []
    for d in effects(stem):
        lines.append(d["name"])
        lines += [f"  {p['name']} = {p['display']}" for p in d["parameters"]]
    return "\n".join(lines) or "no effects"


def apply(stem, controls):
    """Carry out each control on a stem. Returns one line per rejected control."""
    rejected = []
    for c in controls:
        try:
            set_control(stem, c["effect"], c["setting"], c["value"])
        except (LookupError, RuntimeError) as e:
            rejected.append(f"{c['effect']} / {c['setting']} = {c['value']}: {e}")
    return rejected
