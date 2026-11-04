"""Context window bookkeeping: how big is the conversation?"""

from __future__ import annotations

import json
from collections.abc import Sequence

from mini_agent.tools import ToolSpec
from mini_agent.types import Message

# Rule of thumb for English text and code: about 4 characters per token.
# It is offline and deterministic; live runs also record the API's real counts.
CHARS_PER_TOKEN = 4
MESSAGE_OVERHEAD_TOKENS = 4  # role markers and block framing


def estimate_tokens(text: str) -> int:
    return (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN


def estimate_message_tokens(message: Message) -> int:
    parts = [message.text]
    parts += [call.name + json.dumps(call.args) for call in message.tool_calls]
    parts += [result.output for result in message.tool_results]
    return MESSAGE_OVERHEAD_TOKENS + sum(estimate_tokens(part) for part in parts)


def estimate_request_tokens(
    system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]
) -> int:
    tool_text = "".join(
        spec.name + spec.description + json.dumps(spec.input_schema) for spec in tools
    )
    return (
        estimate_tokens(system)
        + estimate_tokens(tool_text)
        + sum(estimate_message_tokens(message) for message in messages)
    )
