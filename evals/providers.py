"""promptfoo calls these to run one module on one test case. Each returns the output and what it cost."""
import contextlib
import json
import sys
from pathlib import Path

import anthropic
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))
import organize
import theme

# Dollars per million tokens: input and output.
PRICES = {"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2, 10), "claude-opus-5-5": (4, 20)}


def run(module, fn, *args):
    """Run a module and keep its response, so the cost comes from what the API reported."""
    responses = []
    # theme uses the beta client for the refusal fallback. organize does not.
    target = module.client.beta.messages if module is theme else module.client.messages
    parse = target.parse

    def keep(**kw):
        responses.append(parse(**kw))
        return responses[-1]

    target.parse = keep
    try:
        # The modules print a trace line. stdout belongs to promptfoo, so it goes to stderr.
        with contextlib.redirect_stdout(sys.stderr):
            out = fn(*args)
    finally:
        del target.parse
    u = responses[0].usage
    i, o = PRICES[module.MODEL]
    cost = (u.input_tokens * i + u.output_tokens * o) / 1e6
    return {"output": out, "cost": cost, "tokenUsage": {"prompt": u.input_tokens, "completion": u.output_tokens}}


def call_organize(prompt, options, context):
    r = run(organize, organize.split, context["vars"]["message"])
    r["output"] = r["output"].model_dump()
    return r


def call_theme(prompt, options, context):
    v = context["vars"]
    return run(theme, theme.build, v.get("current", ""), v["material"])


# The grader runs on a different model than the theme module, so a model does not grade its own work.
GRADER = "claude-sonnet-5-5"
grader = anthropic.Anthropic(timeout=60.0)


class Grade(BaseModel):
    reason: str
    score: float
    passed: bool


def call_grader(prompt, options, context):
    """promptfoo sends the rubric and the output in prompt. It expects JSON with reason, score, and pass."""
    response = grader.messages.parse(
        model=GRADER, max_tokens=4000, output_format=Grade,
        messages=[{"role": "user", "content": prompt}],
    )
    g = response.parsed_output
    u = response.usage
    i, o = PRICES[GRADER]
    return {
        "output": json.dumps({"reason": g.reason, "score": g.score, "pass": g.passed}),
        "cost": (u.input_tokens * i + u.output_tokens * o) / 1e6,
    }
