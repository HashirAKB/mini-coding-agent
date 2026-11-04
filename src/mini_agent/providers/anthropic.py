"""AnthropicProvider: the live provider, used only when ANTHROPIC_API_KEY is set.

It translates our neutral Message list into the Messages API wire format and
back. Two details matter for agents on current Claude models:

- The assistant's content blocks (including `thinking` blocks) are kept in
  `raw` and sent back unchanged on later requests. Dropping or editing them
  degrades reasoning, and replaying edited ones is rejected by the API.
- Tool results go back as `tool_result` blocks in the next user message, all
  results of one turn in a single message.

Prompt caching: an agent re-sends its whole history on every step, so almost
all input tokens of step n were already sent at step n - 1. With top-level
`cache_control` the API caches the longest prefix it has seen and bills those
tokens at a small fraction of the input price. Because the conversation is
append-only, the prefix stays valid from step to step; a summarisation resets
it once.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from mini_agent.tools import ToolSpec
from mini_agent.types import Message, ModelResponse, ToolCall, Usage

DEFAULT_MODEL = "claude-opus-5-5"


def to_wire_messages(messages: Sequence[Message]) -> list[dict[str, Any]]:
    wire: list[dict[str, Any]] = []
    for message in messages:
        if message.role == "assistant":
            if message.raw is not None:
                content: Any = message.raw
            else:
                content = [{"type": "text", "text": message.text}] if message.text else []
                content += [
                    {"type": "tool_use", "id": c.id, "name": c.name, "input": c.args}
                    for c in message.tool_calls
                ]
        elif message.tool_results:
            content = [
                {
                    "type": "tool_result",
                    "tool_use_id": r.call_id,
                    "content": r.output,
                    "is_error": r.is_error,
                }
                for r in message.tool_results
            ]
            if message.text:  # text must come after the tool_result blocks
                content.append({"type": "text", "text": message.text})
        else:
            content = message.text
        wire.append({"role": message.role, "content": content})
    return wire


def to_wire_tools(tools: Sequence[ToolSpec]) -> list[dict[str, Any]]:
    return [
        {"name": t.name, "description": t.description, "input_schema": t.input_schema}
        for t in tools
    ]


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        max_tokens: int = 16000,
        effort: str = "high",
        server_fallback: bool = True,
        prompt_caching: bool = True,
        client: Any = None,
    ) -> None:
        if client is None:
            import anthropic  # imported lazily: mock mode must not need the SDK

            client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        self.client = client
        self.model = model
        self.max_tokens = max_tokens
        self.effort = effort
        self.server_fallback = server_fallback
        self.prompt_caching = prompt_caching

    def complete(
        self, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> ModelResponse:
        extra: dict[str, Any] = {}
        if self.server_fallback:
            # If a safety classifier declines a turn, let the API retry it on a
            # fallback model instead of returning a bare refusal.
            extra = {
                "extra_headers": {"anthropic-beta": "server-side-fallback-2026-07-01"},
                "extra_body": {"fallbacks": "default"},
            }
        if self.prompt_caching:
            extra["cache_control"] = {"type": "ephemeral"}
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            tools=to_wire_tools(tools),
            messages=to_wire_messages(messages),
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort},
            **extra,
        )
        text = "\n".join(b.text for b in response.content if b.type == "text")
        calls = [
            ToolCall(b.id, b.name, dict(b.input)) for b in response.content if b.type == "tool_use"
        ]
        usage = response.usage
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
        return ModelResponse(
            text=text,
            tool_calls=calls,
            usage=Usage(
                input_tokens=usage.input_tokens + cache_read + cache_write,
                output_tokens=usage.output_tokens,
                cache_read_tokens=cache_read,
                cache_write_tokens=cache_write,
            ),
            stop_reason=response.stop_reason or "",
            raw=[b.model_dump(mode="json", exclude_none=True) for b in response.content],
        )
