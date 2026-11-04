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


# ---- truncation of large tool outputs ----------------------------------------

TRUNCATION_HINTS = {
    "read_file": "Use read_file with start_line/end_line to see the omitted lines.",
    "search": "Narrow the regex or the path to see fewer matches.",
    "run_tests": "Run one test file with run_tests(path=...) for shorter output.",
}
DEFAULT_HINT = "Ask for a smaller piece of output."


def truncate_output(text: str, max_chars: int, hint: str = DEFAULT_HINT) -> str:
    """Keep the head and tail of a long output and say how to get the rest.

    Head and tail, because the start of an output (headers, first lines of a
    file) and its end (test summary, last error) are usually the informative
    parts. The marker tells the model that something is missing and how to
    re-read it, so it is never silently misled.
    """
    if len(text) <= max_chars:
        return text
    lines = text.splitlines()
    head: list[str] = []
    tail: list[str] = []
    head_budget, tail_budget = (max_chars * 2) // 3, max_chars // 3
    for line in lines:
        if sum(len(x) + 1 for x in head) + len(line) > head_budget:
            break
        head.append(line)
    for line in reversed(lines[len(head) :]):
        if sum(len(x) + 1 for x in tail) + len(line) > tail_budget:
            break
        tail.insert(0, line)
    omitted_lines = len(lines) - len(head) - len(tail)
    omitted_chars = len(text) - sum(len(x) + 1 for x in head + tail)
    marker = f"[... truncated {omitted_lines} lines ({omitted_chars} characters). {hint}]"
    return "\n".join([*head, marker, *tail])


# ---- summarisation of old turns ----------------------------------------------

SUMMARY_HEADER = "[Summary of earlier steps, older turns were removed to save context]"
THINKING_BLOCK_TYPES = {"thinking", "redacted_thinking"}


def _first_line(text: str, limit: int = 120) -> str:
    line = text.strip().splitlines()[0] if text.strip() else ""
    return line if len(line) <= limit else line[: limit - 3] + "..."


def _describe_call(name: str, args: dict[str, object]) -> str:
    if name == "apply_patch":
        return "apply_patch(...)"  # the diff itself is too long for a summary
    shown = ", ".join(f"{key}={value!r}" for key, value in args.items())
    return f"{name}({shown})"


def _digest(assistant: Message, results: Message | None) -> str:
    outcomes = {r.call_id: r for r in results.tool_results} if results else {}
    lines = [f"- thought: {_first_line(assistant.text)}"] if assistant.text.strip() else []
    for call in assistant.tool_calls:
        result = outcomes.get(call.id)
        status = "no result" if result is None else ("error" if result.is_error else "ok")
        detail = _first_line(result.output) if result is not None else ""
        lines.append(f"- {_describe_call(call.name, call.args)} -> {status}: {detail}")
    return "\n".join(lines)


def _without_thinking(message: Message) -> Message:
    if message.raw is None:
        return message
    kept = [block for block in message.raw if block.get("type") not in THINKING_BLOCK_TYPES]
    return Message(message.role, message.text, message.tool_calls, message.tool_results, kept)


def split_history(
    messages: list[Message], keep_recent_turns: int
) -> tuple[list[Message], list[Message]] | None:
    """Split [task, *turns] into (old turns, recent turns), cutting before an assistant turn.

    Returns None when there are not more than `keep_recent_turns` turns, i.e.
    nothing old enough to summarise. Cutting just before an assistant message
    keeps every tool call together with its results.
    """
    assistant_positions = [i for i, m in enumerate(messages) if m.role == "assistant"]
    if len(assistant_positions) <= keep_recent_turns:
        return None
    cut = assistant_positions[-keep_recent_turns] if keep_recent_turns else len(messages)
    return messages[1:cut], messages[cut:]


def extractive_summary(old: list[Message]) -> str:
    """One line per thought and per tool call: what was called and whether it worked."""
    digests = []
    for i, message in enumerate(old):
        if message.role == "assistant":
            following = old[i + 1] if i + 1 < len(old) else None
            digests.append(_digest(message, following))
        elif message.text and not message.tool_results:
            digests.append(f"- user: {_first_line(message.text)}")
    return "\n".join(digests)


def render_turns(old: list[Message], max_output_chars: int = 1_500) -> str:
    """Old turns as plain text, for a model to summarise (outputs are capped)."""
    lines: list[str] = []
    for message in old:
        if message.role == "assistant":
            if message.text.strip():
                lines.append(f"ASSISTANT: {message.text.strip()}")
            lines += [f"CALL {_describe_call(c.name, c.args)}" for c in message.tool_calls]
        else:
            if message.text.strip():
                lines.append(f"USER: {message.text.strip()}")
            for result in message.tool_results:
                label = "[error]" if result.is_error else "[ok]"
                lines.append(f"RESULT {label}\n{truncate_output(result.output, max_output_chars)}")
    return "\n".join(lines)


def rebuild_history(task: Message, summary: str, recent: list[Message]) -> list[Message]:
    """[task + summary, *recent], with thinking blocks dropped from the recent turns."""
    first = Message("user", text=f"{task.text}\n\n{SUMMARY_HEADER}\n{summary}")
    return [first, *[_without_thinking(m) for m in recent]]


def summarise_history(messages: list[Message], keep_recent_turns: int) -> list[Message]:
    """Replace old turns with a short extractive summary appended to the task message.

    Shape before: [task, a1, r1, a2, r2, ..., aN, rN]   (a = assistant, r = results)
    Shape after:  [task + summary of a1..r(N-k), a(N-k+1), r(N-k+1), ..., aN, rN]

    Invariants (each is tested):
    - The task text is never lost: it stays at the start of the first message.
    - Roles still alternate user/assistant, and each retained assistant turn is
      still followed by the results of its own tool calls.
    - Thinking blocks are dropped from retained turns: they were produced with
      the full history present, and the API rejects replaying them once the
      history before them has changed. Text and tool calls are kept.

    The agent can use a model-written summary instead (AgentConfig.summariser);
    it uses the same split_history / rebuild_history steps.
    """
    split = split_history(messages, keep_recent_turns)
    if split is None:
        return messages
    old, recent = split
    return rebuild_history(messages[0], extractive_summary(old), recent)
