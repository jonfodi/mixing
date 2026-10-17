import pytest

import llm


def pytest_addoption(parser):
    # Run the same eval tests on another model to compare: pytest -m eval --model claude-sonnet-5-5
    parser.addoption("--model", help="the main agent's model. Default: MODEL from .env")


@pytest.fixture(autouse=True)
def model(request, monkeypatch):
    if m := request.config.getoption("--model"):
        monkeypatch.setattr(llm, "MODEL", m)
