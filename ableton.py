import re

from client import send


def number(text):
    """Ableton or LLM value text to a number: '2.67 kHz' -> 2670, '832 ms' -> 0.832, '35 %' -> 35. None if not a number."""
    m = re.match(r"\s*(-?[\d.]+)\s*(k?)(\w*)", text)
    if not m:
        return None
    n = float(m[1]) * (1000 if m[2] else 1)
    return n / 1000 if m[3] == "ms" else n


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


def snapshot():
    """Every stem's effects with the raw value of each setting. Taken before the agent changes anything."""
    return {t["name"]: t["devices"] for t in send({"cmd": "tracks"})}


def values(devices):
    return [(d["name"], [p["value"] for p in d["parameters"]]) for d in devices]


def reconcile(stem, devices):
    """Put a stem back to its snapshot. Ableton is the source of truth, so this compares two reads and never trusts a log.
    Returns True when a fresh read matches the snapshot."""
    now = effects(stem)
    # The artist moved or removed an effect. Putting values back could land on the wrong effect, so stop.
    if [d["name"] for d in now[:len(devices)]] != [d["name"] for d in devices]:
        return False
    # Ableton adds effects at the end, so anything past the snapshot was added this turn.
    for i in reversed(range(len(devices), len(now))):
        send({"cmd": "delete", "track": stem, "device": i})
    for i, d in enumerate(devices):
        for old, cur in zip(d["parameters"], now[i]["parameters"]):
            if cur["value"] != old["value"]:
                send({"cmd": "set", "track": stem, "device": i, "param": old["name"], "value": old["value"]})
    return values(effects(stem)) == values(devices)


def apply(stem, controls):
    """Carry out each control on a stem. Returns one line per applied control with the value Ableton now shows,
    and one line per rejected control with the reason."""
    done, rejected = [], []
    for c in controls:
        try:
            set_control(stem, c["effect"], c["setting"], c["value"])
            done.append(c)
        except (LookupError, RuntimeError) as e:
            rejected.append(f"{c['effect']} / {c['setting']} = {c['value']}: {e}")
    # Verify after write: report what Ableton shows, not what we asked for. One read covers every control.
    # Reversed so the first effect with a name wins, the same one set_control changed.
    now = {d["name"]: d for d in reversed(effects(stem))} if done else {}
    applied = [
        f"{c['effect']} / {c['setting']} = {next(p['display'] for p in now[c['effect']]['parameters'] if p['name'] == c['setting'])}"
        for c in done
    ]
    return applied, rejected
