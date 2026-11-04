"""Plain data types shared by every part of the agent.

The agent works with these neutral types; each provider converts them to and
from its own wire format. Keeping them provider-neutral is what lets the mock
and live providers be swapped freely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["user", "assistant"]


class ToolError(Exception):
    """An error caused by the model's tool call. Its message is shown to the model."""


@dataclass
class ToolCall:
    """The model asking us to run one tool."""

    id: str
    name: str
    args: dict[str, Any]


@dataclass
class ToolResult:
    """What we send back for one ToolCall (the "observation")."""

    call_id: str
    output: str
    is_error: bool = False


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class ModelResponse:
    """One model turn: optional text ("thought") plus zero or more tool calls."""

    text: str
    tool_calls: list[ToolCall]
    usage: Usage
    stop_reason: str = ""
    # Provider-specific content blocks (e.g. Anthropic thinking blocks) that must
    # be sent back unchanged on later requests. None for providers that need nothing.
    raw: list[dict[str, Any]] | None = None


@dataclass
class Message:
    """One entry in the conversation history.

    An assistant message carries text and tool calls; the following user
    message carries the tool results. The first user message carries the task.
    """

    role: Role
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    raw: list[dict[str, Any]] | None = None
