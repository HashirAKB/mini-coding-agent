from pathlib import Path

from mini_agent.agent import Agent, AgentConfig
from mini_agent.context import (
    SUMMARY_HEADER,
    estimate_message_tokens,
    estimate_tokens,
    summarise_history,
    truncate_output,
)
from mini_agent.providers.scripted import ScriptedProvider
from mini_agent.tools import ToolBox
from mini_agent.trajectory import TrajectoryWriter, read_trajectory
from mini_agent.types import Message, ToolCall, ToolResult
from mini_agent.workspace import Workspace
from tests.conftest import CALC_FIX


def test_estimate_tokens_is_chars_over_four_rounded_up() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcde") == 2


def test_message_estimate_counts_calls_and_results() -> None:
    plain = estimate_message_tokens(Message("user", text="x" * 40))
    with_result = estimate_message_tokens(
        Message("user", text="x" * 40, tool_results=[ToolResult("1", "y" * 400)])
    )
    assert with_result - plain == 100


def test_truncate_leaves_short_output_alone() -> None:
    assert truncate_output("short", max_chars=100, hint="h") == "short"


def test_truncate_keeps_head_and_tail_and_says_how_to_reread() -> None:
    text = "\n".join(f"line {i}" for i in range(1000))
    out = truncate_output(text, max_chars=500, hint="Use read_file with start_line.")
    assert len(out) < 700
    assert out.startswith("line 0\n")
    assert out.endswith("line 999")
    assert "truncated" in out and "Use read_file with start_line." in out


def conversation(turns: int) -> list[Message]:
    messages = [Message("user", text="TASK: fix mean()")]
    for i in range(turns):
        call = ToolCall(f"c{i}", "read_file", {"path": f"f{i}.py"})
        raw = [
            {"type": "thinking", "thinking": "", "signature": "s"},
            {"type": "tool_use", "id": call.id, "name": call.name, "input": call.args},
        ]
        messages.append(Message("assistant", f"thought {i}", [call], raw=raw))
        failed = i == 1
        messages.append(Message("user", tool_results=[ToolResult(call.id, f"out {i}", failed)]))
    return messages


def test_summarise_keeps_task_and_recent_turns() -> None:
    messages = conversation(10)
    summarised = summarise_history(messages, keep_recent_turns=3)
    assert summarised[0].role == "user"
    assert summarised[0].text.startswith("TASK: fix mean()")
    assert SUMMARY_HEADER in summarised[0].text
    assert "read_file" in summarised[0].text and "f0.py" in summarised[0].text
    assert "error" in summarised[0].text  # failed step 2 is called out
    # 3 recent assistant turns plus the tool results of each = 6 messages.
    assert len(summarised) == 7
    assert summarised[1].text == "thought 7"


def test_summarise_preserves_alternation_and_tool_pairing() -> None:
    summarised = summarise_history(conversation(10), keep_recent_turns=3)
    roles = [m.role for m in summarised]
    assert roles == ["user", "assistant"] * (len(roles) // 2) + ["user"] * (len(roles) % 2)
    for assistant, user in zip(summarised[1::2], summarised[2::2], strict=False):
        assert [c.id for c in assistant.tool_calls] == [r.call_id for r in user.tool_results]


def test_summarise_strips_thinking_from_retained_turns() -> None:
    summarised = summarise_history(conversation(10), keep_recent_turns=3)
    for message in summarised:
        if message.raw is not None:
            assert all(block["type"] != "thinking" for block in message.raw)
            assert any(block["type"] == "tool_use" for block in message.raw)


def test_summarise_is_a_no_op_when_history_is_short() -> None:
    messages = conversation(2)
    assert summarise_history(messages, keep_recent_turns=3) == messages


def test_loop_summarises_when_near_the_limit(tmp_path: Path, workspace: Workspace) -> None:
    path = tmp_path / "run.jsonl"
    config = AgentConfig(max_steps=15, context_limit_tokens=1500, keep_recent_turns=2)
    with TrajectoryWriter(path) as writer:
        agent = Agent(ScriptedProvider(CALC_FIX, "budget"), ToolBox(workspace), config, writer)
        result = agent.run("fix it")
    events = read_trajectory(path)
    summaries = [e for e in events if e["type"] == "context_summarised"]
    assert summaries, "expected at least one summarisation"
    assert all(e["tokens_after"] < e["tokens_before"] for e in summaries)
    assert result.stop_reason == "max_steps"
    assert len(result.messages) < 2 * config.max_steps


def test_loop_truncates_large_observations(workspace: Workspace) -> None:
    (workspace.root / "calc.py").write_text("x = 1\n" * 3000)
    config = AgentConfig(max_observation_chars=1000, max_steps=3)
    agent = Agent(
        ScriptedProvider(CALC_FIX, "budget"), ToolBox(workspace, max_read_lines=5000), config
    )
    result = agent.run("fix it")
    outputs = [r.output for m in result.messages for r in m.tool_results]
    assert any("truncated" in output for output in outputs)
    assert all(len(output) < 1300 for output in outputs)
