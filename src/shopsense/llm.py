import json
import time
from typing import Protocol, TypeVar

from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class LLM(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class OpenAICompatibleLLM:
    def __init__(
        self,
        base_url,
        api_key,
        model,
        json_mode,
        min_interval_seconds=0,
        timeout_seconds=60,
        temperature=0,
        client=None,
    ):
        self.client = client or OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout_seconds,
        )
        self.model = model
        self.json_mode = json_mode
        self.min_interval_seconds = min_interval_seconds
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self._last_call_at = None
        self._json_mode_rejected = False

    def complete(self, system, user):
        self._wait_for_min_interval()
        args = self._build_request(system, user)
        return self._send_with_retries(args)

    def _wait_for_min_interval(self):
        now = time.monotonic()
        if self._last_call_at is not None:
            remaining = self.min_interval_seconds - (now - self._last_call_at)
            if remaining > 0:
                time.sleep(remaining)
        self._last_call_at = time.monotonic()

    def _build_request(self, system, user):
        args = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if self.json_mode and not self._json_mode_rejected:
            args["response_format"] = {"type": "json_object"}
        return args

    def _send_with_retries(self, args):
        for attempt in range(5):
            try:
                response = self.client.chat.completions.create(**args)
                return response.choices[0].message.content or ""
            except Exception as exc:
                if self._is_json_format_error(exc, args):
                    self._json_mode_rejected = True
                    args.pop("response_format", None)
                    continue
                if not isinstance(
                    exc,
                    (
                        RateLimitError,
                        APIConnectionError,
                        APITimeoutError,
                        InternalServerError,
                    ),
                ):
                    raise
                if attempt == 4:
                    raise LLMUnavailableError(str(exc)) from exc
                time.sleep(2 ** (attempt + 1))
        raise LLMUnavailableError("LLM request failed")

    @staticmethod
    def _is_json_format_error(exc, args):
        return "response_format" in args and getattr(exc, "status_code", None) == 400


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, system, user):
        self.calls.append((system, user))
        if not self.responses:
            raise AssertionError("FakeLLM responses exhausted")
        return self.responses.pop(0)


class LLMOutputError(Exception):
    pass


class LLMUnavailableError(Exception):
    pass


def complete_json(llm, system, user, model, retries):
    message = user
    last = None
    for _ in range(retries + 1):
        try:
            raw = llm.complete(system, message)
            start, end = raw.find("{"), raw.rfind("}")
            if start < 0 or end < start:
                raise ValueError("no JSON object found")
            return model.model_validate(json.loads(raw[start : end + 1]))
        except LLMUnavailableError:
            raise
        except (ValueError, TypeError, ValidationError) as exc:
            last = exc
            message = (
                f"{user}\nYour previous reply was invalid: {exc}. Return only the JSON object."
            )
    raise LLMOutputError(str(last))


def build_llm(settings):
    if not settings.llm_api_key or not settings.llm_model:
        raise RuntimeError("LLM_API_KEY and LLM_MODEL must be set")
    return OpenAICompatibleLLM(
        settings.llm_base_url,
        settings.llm_api_key,
        settings.llm_model,
        settings.llm_json_mode,
        settings.llm_min_interval_seconds,
        settings.llm_timeout_seconds,
        settings.llm_temperature,
    )
