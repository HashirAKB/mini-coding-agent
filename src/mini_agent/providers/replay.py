"""ReplayProvider: returns the model turns stored in a recorded trajectory, in order.

Use it to re-run a recorded live session offline (for debugging the harness,
regression-testing tool changes, or demos) without calling any API.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from mini_agent.tools import ToolSpec
from mini_agent.trajectory import read_trajectory
from mini_agent.types import Message, ModelResponse, ToolCall, Usage


class ReplayExhausted(RuntimeError):
    """The agent asked for more turns than the recording contains."""


class ReplayProvider:
    name = "replay"

    def __init__(self, responses: list[ModelResponse], model: str = "replay") -> None:
        self.responses = responses
        self.model = model
        self._next = 0

    @classmethod
    def from_file(cls, path: Path) -> ReplayProvider:
        events = read_trajectory(path)
        model = next((e["model"] for e in events if e["type"] == "run_start"), "replay")
        steps = [e for e in events if e["type"] == "step"]
        return cls([response_from_event(step) for step in steps], model=model)

    def complete(
        self, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> ModelResponse:
        if self._next >= len(self.responses):
            raise ReplayExhausted(f"Recording has only {len(self.responses)} turns.")
        response = self.responses[self._next]
        self._next += 1
        return response


def response_from_event(step: dict[str, Any]) -> ModelResponse:
    return ModelResponse(
        text=step["text"],
        tool_calls=[ToolCall(c["id"], c["name"], c["args"]) for c in step["tool_calls"]],
        usage=Usage(step["usage"]["input_tokens"], step["usage"]["output_tokens"]),
        stop_reason=step.get("model_stop_reason", ""),
        raw=step.get("raw"),
    )
