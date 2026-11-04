"""Integration tests for the agent loop: one per stop condition, plus recovery."""

from pathlib import Path

from mini_agent.agent import Agent, AgentConfig
from mini_agent.providers.replay import ReplayProvider
from mini_agent.providers.scripted import ScriptedProvider
from mini_agent.tools import ToolBox
from mini_agent.trajectory import TrajectoryWriter, read_trajectory
from mini_agent.types import Message, ModelResponse, ToolCall, Usage
from mini_agent.workspace import Workspace
from tests.conftest import CALC_FIX, CALC_SOURCE, CALC_TEST

TASK = "mean() divides by the wrong number. Fix it."


class FixedProvider:
    """Returns the same canned response forever (for stop-condition tests)."""

    name = "fixed"
    model = "fixed"

    def __init__(self, response: ModelResponse) -> None:
        self.response = response
        self.calls = 0

    def complete(self, system: str, messages: list[Message], tools: object) -> ModelResponse:
        self.calls += 1
        return self.response


def make_agent(workspace: Workspace, provider: object, **config: object) -> Agent:
    return Agent(provider, ToolBox(workspace), AgentConfig(**config))  # type: ignore[arg-type]


def test_scripted_agent_fixes_the_bug(workspace: Workspace, repo: Path) -> None:
    result = make_agent(workspace, ScriptedProvider(CALC_FIX)).run(TASK)
    assert result.stop_reason == "finished"
    assert result.finish_status == "done"
    assert "/ len(values)\n" in (repo / "calc.py").read_text()
    assert result.usage.total > 0


def test_stop_when_model_makes_no_tool_call(workspace: Workspace) -> None:
    provider = FixedProvider(ModelResponse("I think it is fine.", [], Usage(10, 5)))
    result = make_agent(workspace, provider).run(TASK)
    assert result.stop_reason == "no_tool_call"
    assert result.steps == 1


def test_stop_at_max_steps(workspace: Workspace) -> None:
    looping = ModelResponse("Looking...", [ToolCall("c", "list_dir", {})], Usage(10, 5))
    provider = FixedProvider(looping)
    result = make_agent(workspace, provider, max_steps=4).run(TASK)
    assert result.stop_reason == "max_steps"
    assert result.steps == 4 and provider.calls == 4


def test_stop_when_token_budget_is_exhausted(workspace: Workspace) -> None:
    expensive = ModelResponse("Hmm", [ToolCall("c", "list_dir", {})], Usage(900, 100))
    provider = FixedProvider(expensive)
    result = make_agent(workspace, provider, max_total_tokens=2500).run(TASK)
    assert result.stop_reason == "token_budget"
    assert provider.calls == 3  # 1000, 2000, 3000 >= 2500 -> stop before a 4th call


def test_give_up_is_its_own_stop_reason(workspace: Workspace) -> None:
    result = make_agent(workspace, ScriptedProvider(CALC_FIX, behaviour="give_up")).run(TASK)
    assert result.stop_reason == "gave_up"
    assert result.finish_status == "give_up"


def test_agent_recovers_from_a_broken_patch(workspace: Workspace, repo: Path) -> None:
    provider = ScriptedProvider(CALC_FIX, behaviour="broken_patch_then_recover")
    result = make_agent(workspace, provider).run(TASK)
    assert result.stop_reason == "finished"
    assert "/ len(values)\n" in (repo / "calc.py").read_text()
    errors = [r for m in result.messages for r in m.tool_results if r.is_error]
    assert errors and "Patch rejected" in errors[0].output


def test_unknown_tool_is_reported_and_loop_continues(workspace: Workspace) -> None:
    bad = ModelResponse("", [ToolCall("c", "delete_everything", {})], Usage(1, 1))
    result = make_agent(workspace, FixedProvider(bad), max_steps=2).run(TASK)
    observation = result.messages[2].tool_results[0]
    assert observation.is_error and "Unknown tool" in observation.output
    assert result.stop_reason == "max_steps"


def test_plan_strategy_plans_before_acting(workspace: Workspace) -> None:
    result = make_agent(workspace, ScriptedProvider(CALC_FIX), strategy="plan").run(TASK)
    assert result.stop_reason == "finished"
    first_reply = result.messages[1]
    assert first_reply.role == "assistant" and not first_reply.tool_calls
    assert "Plan" in first_reply.text


def test_trajectory_is_recorded_and_replays(tmp_path: Path, repo: Path) -> None:
    path = tmp_path / "run.jsonl"
    with TrajectoryWriter(path) as writer:
        agent = Agent(ScriptedProvider(CALC_FIX), ToolBox(Workspace(repo)), AgentConfig(), writer)
        original = agent.run(TASK)
    events = read_trajectory(path)
    assert [e["type"] for e in events][0] == "run_start"
    assert events[-1]["type"] == "run_end"
    assert sum(e["type"] == "step" for e in events) == original.steps

    # Replay on a fresh copy of the buggy repo: same tool calls, same outcome.
    fresh = tmp_path / "fresh"
    (fresh / "tests").mkdir(parents=True)
    (fresh / "calc.py").write_text(CALC_SOURCE)
    (fresh / "tests" / "test_calc.py").write_text(CALC_TEST)
    replayed = make_agent(Workspace(fresh), ReplayProvider.from_file(path)).run(TASK)
    assert replayed.stop_reason == original.stop_reason
    assert replayed.steps == original.steps
    assert "/ len(values)\n" in (fresh / "calc.py").read_text()


class FailingProvider:
    name = "failing"
    model = "failing"

    def complete(self, system: str, messages: list[Message], tools: object) -> ModelResponse:
        raise ConnectionError("API unreachable")


def test_provider_errors_end_the_run_instead_of_crashing(
    tmp_path: Path, workspace: Workspace
) -> None:
    path = tmp_path / "run.jsonl"
    with TrajectoryWriter(path) as writer:
        result = Agent(FailingProvider(), ToolBox(workspace), AgentConfig(), writer).run(TASK)  # type: ignore[arg-type]
    assert result.stop_reason == "provider_error"
    assert "ConnectionError: API unreachable" in result.finish_summary
    assert read_trajectory(path)[-1]["stop_reason"] == "provider_error"


class SlowProvider(FixedProvider):
    def complete(self, system: str, messages: list[Message], tools: object) -> ModelResponse:
        import time

        time.sleep(0.05)
        return super().complete(system, messages, tools)


def test_steps_record_model_and_tool_time(tmp_path: Path, workspace: Workspace) -> None:
    run_tests = ModelResponse("", [ToolCall("c", "run_tests", {})], Usage(1, 1))
    path = tmp_path / "run.jsonl"
    with TrajectoryWriter(path) as writer:
        agent = Agent(SlowProvider(run_tests), ToolBox(workspace), AgentConfig(max_steps=2), writer)  # type: ignore[arg-type]
        result = agent.run(TASK)
    steps = [e for e in read_trajectory(path) if e["type"] == "step"]
    assert all(s["model_seconds"] >= 0.05 and s["tool_seconds"] > 0 for s in steps)
    assert result.model_seconds == sum(s["model_seconds"] for s in steps)
    assert result.tool_seconds == sum(s["tool_seconds"] for s in steps)
