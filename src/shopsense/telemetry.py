import time
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Recorder:
    events: list[dict] = field(default_factory=list)

    def record(self, name: str, duration_ms: float) -> None:
        self.events.append({"name": name, "duration_ms": duration_ms})

    def summary(self) -> dict[str, float | int]:
        return {
            "event_count": len(self.events),
            "duration_ms": sum(event["duration_ms"] for event in self.events),
        }


def traced(recorder: Recorder | None, name: str, handler: Callable):
    if recorder is None:
        return handler

    def wrapped(state):
        started = time.perf_counter()
        try:
            return handler(state)
        finally:
            recorder.record(name, (time.perf_counter() - started) * 1000)

    return wrapped


class MeteredLLM:
    def __init__(self, llm, recorder: Recorder | None = None) -> None:
        self.llm = llm
        self.recorder = recorder
        self.calls = 0
        self.prompt_characters = 0
        self.completion_characters = 0

    def complete(self, system: str, user: str) -> str:
        self.calls += 1
        self.prompt_characters += len(system) + len(user)
        response = self.llm.complete(system, user)
        self.completion_characters += len(response)
        if self.recorder:
            self.recorder.record("llm.complete", 0)
        return response

    def usage(self) -> dict[str, int]:
        return {
            "calls": self.calls,
            "prompt_characters": self.prompt_characters,
            "completion_characters": self.completion_characters,
        }
