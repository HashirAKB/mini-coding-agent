import json
from pathlib import Path

import pytest

from mini_agent.agent import AgentConfig
from mini_agent.bench import (
    FAILURE_CATEGORIES,
    classify_failure,
    run_benchmark,
    summarise_results,
    workspace_diff,
)
from mini_agent.tasks import TASKS_DIR, load_tasks

SOLUTION = {"pkg/core.py"}


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        (dict(visible=True, hidden=True, stop="finished", changed=SOLUTION, failed=0), None),
        (
            dict(visible=False, hidden=False, stop="provider_error", changed=SOLUTION, failed=0),
            "provider_error",
        ),
        (
            dict(visible=False, hidden=False, stop="max_steps", changed=set(), failed=0),
            "budget_exceeded",
        ),
        (
            dict(visible=False, hidden=False, stop="token_budget", changed=SOLUTION, failed=0),
            "budget_exceeded",
        ),
        (
            dict(visible=False, hidden=False, stop="gave_up", changed=set(), failed=2),
            "broken_patch",
        ),
        (dict(visible=False, hidden=False, stop="gave_up", changed=set(), failed=0), "gave_up"),
        (
            dict(visible=False, hidden=False, stop="no_tool_call", changed=set(), failed=0),
            "gave_up",
        ),
        (
            dict(visible=False, hidden=False, stop="finished", changed={"README.md"}, failed=0),
            "wrong_file",
        ),
        (
            dict(visible=True, hidden=False, stop="finished", changed=SOLUTION, failed=0),
            "test_overfit",
        ),
        (
            dict(visible=False, hidden=False, stop="finished", changed=SOLUTION, failed=1),
            "incorrect_fix",
        ),
    ],
)
def test_failure_taxonomy(kwargs: dict, expected: str | None) -> None:  # type: ignore[type-arg]
    result = classify_failure(
        visible_passed=kwargs["visible"],
        hidden_passed=kwargs["hidden"],
        stop_reason=kwargs["stop"],
        changed_files=kwargs["changed"],
        solution_files=SOLUTION,
        failed_patches=kwargs["failed"],
    )
    assert result == expected
    assert expected is None or expected in FAILURE_CATEGORIES


def test_workspace_diff(tmp_path: Path) -> None:
    before, after = tmp_path / "before", tmp_path / "after"
    for root in (before, after):
        (root / "pkg").mkdir(parents=True)
        (root / "pkg" / "a.py").write_text("x = 1\n")
    (after / "pkg" / "a.py").write_text("x = 2\n")
    (after / "new.txt").write_text("hi\n")
    (after / "pkg" / "__pycache__").mkdir()
    (after / "pkg" / "__pycache__" / "a.pyc").write_bytes(b"\0")
    diff, changed = workspace_diff(before, after)
    assert changed == {"pkg/a.py", "new.txt"}
    assert "-x = 1" in diff and "+x = 2" in diff and "+++ b/new.txt" in diff


def test_mock_benchmark_exercises_every_failure_category(tmp_path: Path) -> None:
    wanted = {
        "01_pagination_off_by_one": None,  # solve
        "03_median_even_length": None,  # broken patch, then recovers
        "04_email_regex": "test_overfit",
        "07_async_lock_race": "broken_patch",
        "10_dict_mutation_cache": "wrong_file",
        "13_roman_subtractive": "gave_up",
        "17_date_range_inclusive": "budget_exceeded",
    }
    tasks = [task for task in load_tasks(TASKS_DIR) if task.id in wanted]
    results = run_benchmark(tasks, "mock", ["direct"], tmp_path, AgentConfig(max_steps=8))
    assert {r.task_id: r.failure for r in results} == wanted
    assert all(r.steps > 0 and r.input_tokens > 0 and r.wall_seconds > 0 for r in results)

    for task_id in wanted:
        events = [
            json.loads(line)
            for line in (tmp_path / "trajectories" / "direct" / f"{task_id}.jsonl")
            .read_text()
            .splitlines()
        ]
        assert events[0]["type"] == "run_start"
        assert events[-1]["type"] == "evaluation"

    summary = json.loads((tmp_path / "results.json").read_text())
    assert summary["mode"] == "mock"
    assert summary["strategies"]["direct"]["pass_at_1"] == pytest.approx(2 / 7)
    report = (tmp_path / "results.md").read_text()
    assert "MOCK" in report and "only prove" in report


def test_both_strategies_run_and_are_compared(tmp_path: Path) -> None:
    tasks = [load_tasks(TASKS_DIR)[0]]
    results = run_benchmark(tasks, "mock", ["direct", "plan"], tmp_path, AgentConfig())
    summary = summarise_results(results)
    assert set(summary) == {"direct", "plan"}
    assert summary["plan"]["avg_steps"] == summary["direct"]["avg_steps"] + 1  # the plan turn
    assert "| plan |" in (tmp_path / "results.md").read_text()


def test_cost_prices_cache_reads_and_writes_separately() -> None:
    from mini_agent.bench import cost_usd
    from mini_agent.types import Usage

    plain = cost_usd("claude-opus-5-5", Usage(1_000_000, 0))
    assert plain == pytest.approx(4.00)
    cached = cost_usd("claude-opus-5-5", Usage(1_000_000, 0, cache_read_tokens=1_000_000))
    assert cached == pytest.approx(0.20)
    written = cost_usd("claude-opus-5-5", Usage(1_000_000, 0, cache_write_tokens=1_000_000))
    assert written == pytest.approx(5.00)
    assert cost_usd("claude-opus-5-5", Usage(0, 1_000_000)) == pytest.approx(20.00)


@pytest.mark.parametrize(
    "n, c, k, expected",
    [
        (5, 1, 1, 0.2),
        (5, 1, 5, 1.0),
        (5, 0, 3, 0.0),
        (5, 5, 1, 1.0),
        (4, 2, 2, 1 - 1 / 6),  # 1 - C(2,2)/C(4,2)
        (10, 3, 4, 1 - 35 / 210),  # 1 - C(7,4)/C(10,4)
    ],
)
def test_unbiased_pass_at_k(n: int, c: int, k: int, expected: float) -> None:
    from mini_agent.bench import pass_at_k

    assert pass_at_k(n, c, k) == pytest.approx(expected)


def test_several_samples_per_task(tmp_path: Path) -> None:
    tasks = [t for t in load_tasks(TASKS_DIR) if t.id.startswith(("01_", "13_"))]
    results = run_benchmark(tasks, "mock", ["direct"], tmp_path, AgentConfig(), samples=3)
    assert len(results) == 6
    assert sorted({r.sample for r in results}) == [1, 2, 3]
    assert (tmp_path / "trajectories" / "direct" / "01_pagination_off_by_one.s2.jsonl").is_file()
    summary = summarise_results(results)["direct"]
    # The scripted mock is deterministic, so every sample agrees: pass@k == pass@1.
    assert summary["pass_at_1"] == pytest.approx(0.5)
    assert summary["pass_at_k"] == {"1": pytest.approx(0.5), "3": pytest.approx(0.5)}
    assert "pass@3" in (tmp_path / "results.md").read_text()


def test_parallel_workers_give_the_same_results_in_the_same_order(tmp_path: Path) -> None:
    tasks = [t for t in load_tasks(TASKS_DIR) if t.id[:2] in {"01", "04", "07", "13"}]
    serial = run_benchmark(tasks, "mock", ["direct"], tmp_path / "serial", AgentConfig())
    parallel = run_benchmark(
        tasks, "mock", ["direct"], tmp_path / "parallel", AgentConfig(), workers=4
    )

    def key(r: object) -> tuple[object, ...]:
        return (r.task_id, r.sample, r.passed, r.failure, r.steps, r.input_tokens)  # type: ignore[attr-defined]

    assert [key(r) for r in parallel] == [key(r) for r in serial]


def test_compare_results_ignores_environment_dependent_fields() -> None:
    from mini_agent.bench import compare_results

    expected = {
        "mode": "mock",
        "strategies": {"direct": {"pass_at_1": 0.75, "avg_wall_seconds": 0.7}},
        "results": [{"task_id": "a", "passed": True, "wall_seconds": 0.5}],
    }
    same_but_slower = {
        "mode": "mock",
        "strategies": {"direct": {"pass_at_1": 0.75, "avg_wall_seconds": 9.9}},
        "results": [{"task_id": "a", "passed": True, "wall_seconds": 3.0, "input_tokens": 9}],
    }
    expected["results"][0]["input_tokens"] = 8  # type: ignore[index]
    assert compare_results(expected, same_but_slower) == []
    regressed = {
        "mode": "mock",
        "strategies": {"direct": {"pass_at_1": 0.70, "avg_wall_seconds": 0.7}},
        "results": [{"task_id": "a", "passed": False, "wall_seconds": 0.5}],
    }
    differences = compare_results(expected, regressed)
    assert "strategies.direct.pass_at_1: expected 0.75, got 0.7" in differences
    assert "results.0.passed: expected True, got False" in differences


def test_committed_mock_results_match_a_fresh_run_on_a_sample(tmp_path: Path) -> None:
    """Spot-check two tasks against the committed results (CI checks all of them)."""
    from mini_agent.bench import compare_results

    committed = json.loads(
        (Path(__file__).parents[1] / "bench/results/mock/results.json").read_text()
    )
    tasks = [t for t in load_tasks(TASKS_DIR) if t.id[:2] in {"03", "10"}]
    run_benchmark(tasks, "mock", ["direct"], tmp_path, AgentConfig())
    fresh = json.loads((tmp_path / "results.json").read_text())
    wanted = [
        r
        for r in committed["results"]
        if r["strategy"] == "direct" and r["task_id"][:2] in {"03", "10"}
    ]
    assert compare_results({"results": wanted}, {"results": fresh["results"]}) == []
