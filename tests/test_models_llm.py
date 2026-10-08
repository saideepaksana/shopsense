import pytest
from pydantic import BaseModel

import shopsense.llm as llm_module
from shopsense.llm import (
    FakeLLM,
    LLMOutputError,
    LLMUnavailableError,
    OpenAICompatibleLLM,
    complete_json,
)
from shopsense.models import Action, Intent, Plan
from shopsense.telemetry import MeteredLLM


def test_models_and_complete_json():
    assert Intent(intent="cancel_order", order_id="bad").order_id is None
    assert len(Plan(decision="deny", rationale="x" * 400).rationale) == 300
    fake = FakeLLM(['```json\n{"value": 3}\n```'])

    class Output(BaseModel):
        value: int

    assert complete_json(fake, "", "", Output, 0).value == 3
    assert len(fake.calls) == 1


def test_complete_json_retries_and_fails():
    class Output(BaseModel):
        value: int

    fake = FakeLLM(["bad", '{"value": 4}'])
    assert complete_json(fake, "", "input", Output, 1).value == 4
    with pytest.raises(LLMOutputError):
        complete_json(FakeLLM(["bad", "still bad"]), "", "", Output, 1)


class _Message:
    content = '{"ok": true}'


class _Response:
    def __init__(self):
        self.choices = [type("Choice", (), {"message": _Message()})()]


class _Completions:
    def __init__(self, errors=()):
        self.errors = list(errors)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.errors:
            error = self.errors.pop(0)
            raise error
        return _Response()


class _Client:
    def __init__(self, completions):
        self.chat = type("Chat", (), {"completions": completions})()


def test_llm_retries_and_min_interval(monkeypatch):
    class RetryError(Exception):
        pass

    monkeypatch.setattr(llm_module, "RateLimitError", RetryError)
    sleeps = []
    now = iter([0.0, 0.0, 0.0, 0.0])
    monkeypatch.setattr(llm_module.time, "monotonic", lambda: next(now))
    monkeypatch.setattr(llm_module.time, "sleep", sleeps.append)
    completions = _Completions([RetryError(), RetryError()])
    llm = OpenAICompatibleLLM(
        "", "", "model", False, min_interval_seconds=2, client=_Client(completions)
    )

    assert llm.complete("", "") == '{"ok": true}'
    assert sleeps == [2, 4]


def test_llm_enforces_min_interval(monkeypatch):
    times = iter([0.0, 0.0, 0.5, 0.5])
    sleeps = []
    monkeypatch.setattr(llm_module.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(llm_module.time, "sleep", sleeps.append)
    completions = _Completions()
    llm = OpenAICompatibleLLM(
        "", "", "model", False, min_interval_seconds=2, client=_Client(completions)
    )

    llm.complete("", "")
    llm.complete("", "")
    assert sleeps == [1.5]


def test_llm_permanent_failure_raises_unavailable(monkeypatch):
    class RetryError(Exception):
        pass

    monkeypatch.setattr(llm_module, "RateLimitError", RetryError)
    monkeypatch.setattr(llm_module.time, "sleep", lambda _: None)
    completions = _Completions([RetryError()] * 5)
    llm = OpenAICompatibleLLM("", "", "model", False, client=_Client(completions))

    with pytest.raises(LLMUnavailableError):
        llm.complete("", "")


def test_json_mode_falls_back_after_bad_request():
    class BadRequest(Exception):
        status_code = 400

    completions = _Completions([BadRequest()])
    llm = OpenAICompatibleLLM("", "", "model", True, client=_Client(completions))
    assert llm.complete("", "") == '{"ok": true}'
    assert "response_format" in completions.calls[0]
    assert "response_format" not in completions.calls[1]
    assert llm.complete("", "") == '{"ok": true}'
    assert "response_format" not in completions.calls[2]


def test_llm_uses_configured_temperature():
    completions = _Completions()
    llm = OpenAICompatibleLLM("", "", "model", False, temperature=0.7, client=_Client(completions))

    llm.complete("", "")

    assert completions.calls[0]["temperature"] == 0.7


def test_metered_llm_tracks_character_usage():
    fake = FakeLLM(["answer"])
    metered = MeteredLLM(fake)

    assert metered.complete("system", "user") == "answer"
    assert metered.usage() == {
        "calls": 1,
        "prompt_characters": 10,
        "completion_characters": 6,
    }


def test_action_coerces_numeric_amount():
    action = Action.model_validate({"tool": "issue_refund", "args": {"amount_minor": "199700"}})
    assert action.args["amount_minor"] == 199700


def test_action_rejects_boolean_amount():
    with pytest.raises(ValueError, match="amount_minor must be an integer"):
        Action.model_validate({"tool": "issue_refund", "args": {"amount_minor": True}})
