"""The one interface every model provider implements."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from mini_agent.tools import ToolSpec
from mini_agent.types import Message, ModelResponse


class Provider(Protocol):
    name: str  # "scripted", "replay", "anthropic"
    model: str  # model id, used for cost estimates and reporting

    def complete(
        self, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> ModelResponse:
        """Given the full conversation, return the model's next turn."""
        ...
