"""The benchmark harness: run the agent on every task in isolation and score it.

For each (task, strategy):
1. copy the task repo into a fresh temp directory (hidden tests stay outside),
2. run the agent there, recording the trajectory as JSONL,
3. diff the workspace against the original repo,
4. restore the visible tests, add the hidden tests, run both,
5. classify the outcome with the failure taxonomy.
Then aggregate metrics per strategy and write results.json and results.md.
"""

from __future__ import annotations

import difflib
import json
import math
import os
import tempfile
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from mini_agent.agent import Agent, AgentConfig
from mini_agent.patch import parse_patch
from mini_agent.providers.anthropic import DEFAULT_MODEL, AnthropicProvider
from mini_agent.providers.base import Provider
from mini_agent.providers.replay import ReplayProvider
from mini_agent.providers.scripted import ScriptedProvider
from mini_agent.tasks import HIDDEN_DIR_NAME, Task, prepare_workspace, run_suite
from mini_agent.tools import IGNORED_NAMES, ToolBox
from mini_agent.trajectory import TrajectoryWriter, read_trajectory
from mini_agent.types import Usage
from mini_agent.workspace import Workspace

# USD per million tokens. Mock runs are priced as if they had used the default
# live model, and their token counts are chars/4 estimates. Cache writes are
# the 5-minute TTL price (1.25x input); cache reads are 0.05x input on this model.
PRICES_PER_MTOK = {
    DEFAULT_MODEL: {"input": 4.00, "output": 20.00, "cache_read": 0.20, "cache_write": 5.00},
}

# Which scripted behaviour each task gets in mock mode. Faults are injected on
# purpose so that every failure category shows up. See providers/scripted.py.
MOCK_BEHAVIOURS = {
    "03_median_even_length": "broken_patch_then_recover",
    "04_email_regex": "overfit",
    "07_async_lock_race": "broken_patch",
    "10_dict_mutation_cache": "wrong_file",
    "13_roman_subtractive": "give_up",
    "14_csv_quoted_fields": "broken_patch_then_recover",
    "17_date_range_inclusive": "budget",
}

FAILURE_CATEGORIES = (
    "provider_error",  # the model call itself failed (network, API error)
    "budget_exceeded",  # hit max steps or the token budget
    "broken_patch",  # tried to patch, but no patch ever applied
    "gave_up",  # stopped without trying a patch
    "wrong_file",  # changed files, none of which the reference fix touches
    "test_overfit",  # visible tests pass, hidden tests fail
    "incorrect_fix",  # right file, but the tests still fail
)
BUDGET_STOPS = {"max_steps", "token_budget"}

MOCK_BANNER = (
    "> **MOCK MODE.** These results come from the scripted oracle provider, which is "
    "given the reference solution and fails on purpose on some tasks. They only prove "
    "the harness works; they say nothing about the agent's real ability. Token counts "
    "are chars/4 estimates and costs are what those tokens would cost at "
    f"`{DEFAULT_MODEL}` prices."
)
LIVE_BANNER = "> **LIVE MODE.** Results from real model calls; tokens are API-reported."
REPLAY_BANNER = (
    "> **REPLAY MODE.** Model turns were replayed from recorded trajectories; tokens are "
    "the recorded ones. This re-checks the harness on a past run, not a new model run."
)
BANNERS = {"mock": MOCK_BANNER, "live": LIVE_BANNER, "replay": REPLAY_BANNER}
MODES = {"mock": "mock", "anthropic": "live", "replay": "replay"}


@dataclass
class TaskResult:
    task_id: str
    category: str
    strategy: str
    sample: int  # 1-based sample number when a task is run several times
    passed: bool
    visible_passed: bool
    hidden_passed: bool
    failure: str | None
    stop_reason: str
    steps: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cost_usd: float
    wall_seconds: float  # whole agent run
    model_seconds: float  # part of wall_seconds spent waiting for the model
    tool_seconds: float  # part of wall_seconds spent running tools
    changed_files: list[str]


def classify_failure(
    visible_passed: bool,
    hidden_passed: bool,
    stop_reason: str,
    changed_files: set[str],
    solution_files: set[str],
    failed_patches: int,
) -> str | None:
    """Put a run in exactly one failure category (None means it passed).

    The checks run in order, so earlier categories win: running out of budget
    is reported as such even if the agent also edited the wrong file.
    """
    if visible_passed and hidden_passed:
        return None
    if stop_reason == "provider_error":
        return "provider_error"
    if stop_reason in BUDGET_STOPS:
        return "budget_exceeded"
    if not changed_files:
        return "broken_patch" if failed_patches else "gave_up"
    if not changed_files & solution_files:
        return "wrong_file"
    if visible_passed:
        return "test_overfit"
    return "incorrect_fix"


def _files(root: Path) -> dict[str, Path]:
    return {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file() and not IGNORED_NAMES.intersection(path.relative_to(root).parts)
    }


def _lines(path: Path) -> list[str]:
    return path.read_text(errors="replace").splitlines(keepends=True)


def workspace_diff(original: Path, workspace: Path) -> tuple[str, set[str]]:
    """Unified diff of everything the agent changed, plus the changed paths."""
    before, after = _files(original), _files(workspace)
    chunks: list[str] = []
    changed: set[str] = set()
    for name in sorted(before.keys() | after.keys()):
        old = _lines(before[name]) if name in before else []
        new = _lines(after[name]) if name in after else []
        if old == new:
            continue
        changed.add(name)
        old_label = f"a/{name}" if name in before else "/dev/null"
        new_label = f"b/{name}" if name in after else "/dev/null"
        chunks.append("".join(difflib.unified_diff(old, new, old_label, new_label)))
    return "".join(chunks), changed


def count_failed_patches(events: list[dict[str, Any]]) -> int:
    failed = 0
    for event in events:
        if event["type"] != "step":
            continue
        results = {o["call_id"]: o for o in event["observations"]}
        for call in event["tool_calls"]:
            observation = results.get(call["id"])
            if call["name"] == "apply_patch" and observation and observation["is_error"]:
                failed += 1
    return failed


def trajectory_name(task: Task, sample: int, samples: int) -> str:
    return f"{task.id}.jsonl" if samples == 1 else f"{task.id}.s{sample}.jsonl"


def make_provider(
    provider: str, task: Task, strategy: str, replay_dir: Path | None, name: str
) -> Provider:
    if provider == "mock":
        behaviour = MOCK_BEHAVIOURS.get(task.id, "solve")
        return ScriptedProvider(task.solution_patch, behaviour, task.overfit_patch)
    if provider == "replay":
        assert replay_dir is not None, "replay needs a directory of recorded trajectories"
        return ReplayProvider.from_file(replay_dir / strategy / name)
    if provider == "anthropic":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise SystemExit("ANTHROPIC_API_KEY is not set; use --provider mock to run offline.")
        return AnthropicProvider(model=os.environ.get("MINI_AGENT_MODEL", DEFAULT_MODEL))
    raise ValueError(f"Unknown provider {provider!r}")


def cost_usd(model: str, usage: Usage) -> float:
    price = PRICES_PER_MTOK.get(model, PRICES_PER_MTOK[DEFAULT_MODEL])
    uncached = usage.input_tokens - usage.cache_read_tokens - usage.cache_write_tokens
    return (
        uncached * price["input"]
        + usage.cache_read_tokens * price["cache_read"]
        + usage.cache_write_tokens * price["cache_write"]
        + usage.output_tokens * price["output"]
    ) / 1_000_000


def run_task(
    task: Task,
    provider_name: str,
    strategy: str,
    out_dir: Path,
    config: AgentConfig,
    replay_dir: Path | None = None,
    sample: int = 1,
    samples: int = 1,
) -> TaskResult:
    name = trajectory_name(task, sample, samples)
    trajectory_path = out_dir / "trajectories" / strategy / name
    provider = make_provider(provider_name, task, strategy, replay_dir, name)
    run_config = AgentConfig(**{**asdict(config), "strategy": strategy})
    with tempfile.TemporaryDirectory(prefix=f"{task.id}-") as tmp:
        root = prepare_workspace(task, Path(tmp))
        started = time.perf_counter()
        with TrajectoryWriter(trajectory_path) as writer:
            agent = Agent(provider, ToolBox(Workspace(root)), run_config, writer)
            result = agent.run(task.description)
            wall_seconds = time.perf_counter() - started
            diff, changed = workspace_diff(task.repo_dir, root)
            visible = run_suite(root, "tests", task)
            hidden = run_suite(root, HIDDEN_DIR_NAME, task)
            events = read_trajectory(trajectory_path)
            failure = classify_failure(
                visible.passed,
                hidden.passed,
                result.stop_reason,
                changed,
                {p.path for p in parse_patch(task.solution_patch)},
                count_failed_patches(events),
            )
            writer.write(
                {
                    "type": "evaluation",
                    "task_id": task.id,
                    "strategy": strategy,
                    "visible_passed": visible.passed,
                    "hidden_passed": hidden.passed,
                    "failure": failure,
                    "final_diff": diff,
                    "visible_output": visible.output[-2000:],
                    "hidden_output": hidden.output[-2000:],
                }
            )
    return TaskResult(
        task_id=task.id,
        category=task.category,
        strategy=strategy,
        sample=sample,
        passed=failure is None,
        visible_passed=visible.passed,
        hidden_passed=hidden.passed,
        failure=failure,
        stop_reason=result.stop_reason,
        steps=result.steps,
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
        cache_read_tokens=result.usage.cache_read_tokens,
        cost_usd=cost_usd(provider.model, result.usage),
        wall_seconds=wall_seconds,
        model_seconds=result.model_seconds,
        tool_seconds=result.tool_seconds,
        changed_files=sorted(changed),
    )


def pass_at_k(n: int, c: int, k: int) -> float:
    """Unbiased estimate of P(at least one of k samples passes), from n samples with c passes.

    1 - C(n - c, k) / C(n, k): one minus the chance that k samples drawn without
    replacement from the n are all failures (Chen et al., 2021, the Codex paper).
    """
    if n - c < k:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def summarise_results(results: list[TaskResult]) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for strategy in dict.fromkeys(r.strategy for r in results):
        runs = [r for r in results if r.strategy == strategy]
        n = len(runs)
        tokens = [r.input_tokens + r.output_tokens for r in runs]
        per_task: dict[str, list[bool]] = {}
        for r in runs:
            per_task.setdefault(r.task_id, []).append(r.passed)
        samples = min(len(passes) for passes in per_task.values())
        pass_at = {
            str(k): sum(pass_at_k(len(p), sum(p), k) for p in per_task.values()) / len(per_task)
            for k in sorted({1, samples})
        }
        summary[strategy] = {
            "tasks": len(per_task),
            "samples_per_task": samples,
            "runs": n,
            "passed": sum(r.passed for r in runs),
            "pass_at_1": pass_at["1"],
            "pass_at_k": pass_at,
            "avg_steps": sum(r.steps for r in runs) / n,
            "total_tokens": sum(tokens),
            "cache_read_tokens": sum(r.cache_read_tokens for r in runs),
            "avg_tokens": sum(tokens) / n,
            "total_cost_usd": sum(r.cost_usd for r in runs),
            "avg_wall_seconds": sum(r.wall_seconds for r in runs) / n,
            "avg_model_seconds": sum(r.model_seconds for r in runs) / n,
            "avg_tool_seconds": sum(r.tool_seconds for r in runs) / n,
            "failures": dict(Counter(r.failure for r in runs if r.failure)),
        }
    return summary


def render_markdown(
    mode: str, summary: dict[str, dict[str, Any]], results: list[TaskResult]
) -> str:
    lines = [f"# Benchmark results ({mode})", "", BANNERS[mode]]
    lines += [
        "",
        "## Summary",
        "",
        "| strategy | pass@1 | pass@k | avg steps | total tokens | avg tokens | cost (USD) "
        "| avg wall (s) | avg model (s) | avg tools (s) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for strategy, s in summary.items():
        k = str(s["samples_per_task"])
        lines.append(
            f"| {strategy} | {s['passed']}/{s['runs']} ({s['pass_at_1']:.0%}) "
            f"| pass@{k} {s['pass_at_k'][k]:.0%} | {s['avg_steps']:.1f} "
            f"| {s['total_tokens']:,} | {s['avg_tokens']:,.0f} "
            f"| {s['total_cost_usd']:.2f} | {s['avg_wall_seconds']:.2f} "
            f"| {s['avg_model_seconds']:.2f} | {s['avg_tool_seconds']:.2f} |"
        )
    lines += ["", "## Failure taxonomy", "", "| category | " + " | ".join(summary) + " |"]
    lines.append("|---|" + "---|" * len(summary))
    for category in FAILURE_CATEGORIES:
        counts = [str(s["failures"].get(category, 0)) for s in summary.values()]
        lines.append(f"| {category} | " + " | ".join(counts) + " |")
    lines += [
        "",
        "## Per task",
        "",
        "| task | bug category | strategy | sample | result | stop reason | steps | tokens |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        outcome = "pass" if r.passed else f"fail: {r.failure}"
        lines.append(
            f"| {r.task_id} | {r.category} | {r.strategy} | {r.sample} | {outcome} "
            f"| {r.stop_reason} "
            f"| {r.steps} | {r.input_tokens + r.output_tokens:,} |"
        )
    return "\n".join(lines) + "\n"


TIMING_KEYS = {
    "wall_seconds",
    "model_seconds",
    "tool_seconds",
    "avg_wall_seconds",
    "avg_model_seconds",
    "avg_tool_seconds",
}


def compare_results(expected: Any, actual: Any, path: str = "") -> list[str]:
    """Differences between two results.json payloads, ignoring wall-clock timings.

    Used by CI to check that the committed mock results still match a fresh
    run: everything in mock mode is deterministic except how long it took.
    """
    if isinstance(expected, dict) and isinstance(actual, dict):
        differences = []
        for key in sorted(expected.keys() | actual.keys()):
            if key in TIMING_KEYS:
                continue
            child = f"{path}.{key}" if path else str(key)
            if key not in actual or key not in expected:
                differences.append(f"{child}: present in only one of the two")
            else:
                differences += compare_results(expected[key], actual[key], child)
        return differences
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return [f"{path}: expected {len(expected)} items, got {len(actual)}"]
        differences = []
        for i, (left, right) in enumerate(zip(expected, actual, strict=True)):
            differences += compare_results(left, right, f"{path}.{i}")
        return differences
    if expected != actual:
        return [f"{path}: expected {expected!r}, got {actual!r}"]
    return []


def run_benchmark(
    tasks: list[Task],
    provider_name: str,
    strategies: list[str],
    out_dir: Path,
    config: AgentConfig,
    replay_dir: Path | None = None,
    samples: int = 1,
    workers: int = 1,
) -> list[TaskResult]:
    jobs = [
        (task, strategy, sample)
        for strategy in strategies
        for task in tasks
        for sample in range(1, samples + 1)
    ]

    def run(job: tuple[Task, str, int]) -> TaskResult:
        task, strategy, sample = job
        return run_task(task, provider_name, strategy, out_dir, config, replay_dir, sample, samples)

    # Threads are enough: the work is waiting on pytest subprocesses and model calls,
    # and every run has its own provider, temp workspace and trajectory file.
    # `map` keeps results in job order, so reports do not depend on scheduling.
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(run, jobs))
    mode = MODES[provider_name]
    summary = summarise_results(results)
    payload = {
        "mode": mode,
        "provider": provider_name,
        "config": asdict(config),
        "strategies": summary,
        "results": [asdict(r) for r in results],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(payload, indent=2) + "\n")
    (out_dir / "results.md").write_text(render_markdown(mode, summary, results))
    return results
