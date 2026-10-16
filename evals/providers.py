"""promptfoo calls this to run organize on one test case. It returns the output and what it cost."""
import contextlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import organize

# Dollars per million tokens: input and output.
PRICES = {"claude-haiku-5-5": (0.10, 0.50)}


def call_organize(prompt, options, context):
    responses = []
    parse = organize.client.messages.parse

    # Keep the response, so the cost comes from what the API reported.
    def keep(**kw):
        responses.append(parse(**kw))
        return responses[-1]

    organize.client.messages.parse = keep
    try:
        # organize prints a trace line. stdout belongs to promptfoo, so it goes to stderr.
        with contextlib.redirect_stdout(sys.stderr):
            out = organize.split(context["vars"]["message"])
    finally:
        del organize.client.messages.parse
    u = responses[0].usage
    i, o = PRICES[organize.MODEL]
    return {
        "output": out.model_dump(),
        "cost": (u.input_tokens * i + u.output_tokens * o) / 1e6,
        "tokenUsage": {"prompt": u.input_tokens, "completion": u.output_tokens},
    }
