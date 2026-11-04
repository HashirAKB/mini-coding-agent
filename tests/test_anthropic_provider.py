"""The live provider is tested offline with a fake client that records requests."""

from dataclasses import dataclass, field
from typing import Any

from mini_agent.providers.anthropic import AnthropicProvider, to_wire_messages
from mini_agent.tools import TOOL_SPECS
from mini_agent.types import Message, ToolCall, ToolResult


@dataclass
class FakeBlock:
    data: dict[str, Any]

    def __getattr__(self, name: str) -> Any:
        return self.data[name]

    def model_dump(self, **_: Any) -> dict[str, Any]:
        return dict(self.data)


@dataclass
class FakeUsage:
    input_tokens: int = 120
    output_tokens: int = 30
    cache_read_input_tokens: int = 50
    cache_creation_input_tokens: int = 0


@dataclass
class FakeResponse:
    content: list[FakeBlock]
    stop_reason: str = "tool_use"
    usage: FakeUsage = field(default_factory=FakeUsage)


class FakeMessages:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.requests: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> FakeResponse:
        self.requests.append(kwargs)
        return self.response


class FakeClient:
    def __init__(self, response: FakeResponse) -> None:
        self.messages = FakeMessages(response)


def test_wire_format_of_a_conversation() -> None:
    thinking = {"type": "thinking", "thinking": "", "signature": "sig"}
    messages = [
        Message("user", text="Fix the bug."),
        Message(
            "assistant",
            text="Reading.",
            tool_calls=[ToolCall("t1", "read_file", {"path": "a.py"})],
            raw=[thinking, {"type": "tool_use", "id": "t1", "name": "read_file", "input": {}}],
        ),
        Message("user", tool_results=[ToolResult("t1", "boom", is_error=True)]),
        Message("assistant", text="No raw here.", tool_calls=[ToolCall("t2", "list_dir", {})]),
    ]
    wire = to_wire_messages(messages)
    assert wire[0] == {"role": "user", "content": "Fix the bug."}
    assert wire[1]["content"][0] == thinking  # raw blocks are replayed unchanged
    assert wire[2]["content"] == [
        {"type": "tool_result", "tool_use_id": "t1", "content": "boom", "is_error": True}
    ]
    assert wire[3]["content"] == [
        {"type": "text", "text": "No raw here."},
        {"type": "tool_use", "id": "t2", "name": "list_dir", "input": {}},
    ]


def test_request_and_response_mapping() -> None:
    response = FakeResponse(
        [
            FakeBlock({"type": "thinking", "thinking": "", "signature": "s"}),
            FakeBlock({"type": "text", "text": "Let me look."}),
            FakeBlock(
                {"type": "tool_use", "id": "tu1", "name": "list_dir", "input": {"path": "."}}
            ),
        ]
    )
    client = FakeClient(response)
    provider = AnthropicProvider(client=client, model="claude-opus-5-5")
    result = provider.complete("system prompt", [Message("user", text="hi")], TOOL_SPECS)

    request = client.messages.requests[0]
    assert request["model"] == "claude-opus-5-5"
    assert request["system"] == "system prompt"
    assert {tool["name"] for tool in request["tools"]} == {spec.name for spec in TOOL_SPECS}
    assert request["thinking"] == {"type": "adaptive"}

    assert result.text == "Let me look."
    assert result.tool_calls == [ToolCall("tu1", "list_dir", {"path": "."})]
    assert result.usage.input_tokens == 170  # uncached + cache reads
    assert result.usage.output_tokens == 30
    assert result.raw is not None and result.raw[0]["type"] == "thinking"
    assert result.stop_reason == "tool_use"


def test_prompt_caching_is_requested_and_cache_usage_is_tracked() -> None:
    usage = FakeUsage(input_tokens=100, cache_read_input_tokens=900, cache_creation_input_tokens=50)
    client = FakeClient(
        FakeResponse([FakeBlock({"type": "text", "text": "ok"})], "end_turn", usage)
    )
    result = AnthropicProvider(client=client).complete("s", [Message("user", text="hi")], [])
    assert client.messages.requests[0]["cache_control"] == {"type": "ephemeral"}
    assert result.usage.input_tokens == 1050  # every input token, cached or not
    assert result.usage.cache_read_tokens == 900
    assert result.usage.cache_write_tokens == 50


def test_caching_can_be_switched_off() -> None:
    client = FakeClient(FakeResponse([FakeBlock({"type": "text", "text": "ok"})], "end_turn"))
    AnthropicProvider(client=client, prompt_caching=False).complete("s", [], [])
    assert "cache_control" not in client.messages.requests[0]


def test_sdk_client_gets_retry_and_timeout_settings(monkeypatch: Any) -> None:
    import sys
    import types

    created: dict[str, Any] = {}

    class FakeAnthropic:
        def __init__(self, **kwargs: Any) -> None:
            created.update(kwargs)

    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=FakeAnthropic))
    AnthropicProvider(max_retries=7, timeout_seconds=42.0)
    assert created == {"max_retries": 7, "timeout": 42.0}
