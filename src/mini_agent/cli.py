"""Command line interface.

python -m mini_agent demo                      # one task, mock provider, printed step by step
python -m mini_agent run --task 04_email_regex --strategy plan
python -m mini_agent bench                     # all tasks, both strategies, mock provider
python -m mini_agent bench --provider anthropic --out bench/results/live
"""

from __future__ import annotations

import argparse
import json
import tempfile
import textwrap
from pathlib import Path
from typing import Any

from mini_agent.agent import AgentConfig
from mini_agent.bench import MODES, compare_results, run_benchmark, run_task, summarise_results
from mini_agent.sandbox import DockerSandbox
from mini_agent.tasks import TASKS_DIR, Task, load_tasks
from mini_agent.trajectory import read_trajectory
from mini_agent.viewer import render_run, render_trajectory


def _indent(text: str, limit: int = 12) -> str:
    lines = text.splitlines() or [""]
    shown = lines[:limit] + (
        [f"... ({len(lines) - limit} more lines)"] if len(lines) > limit else []
    )
    return textwrap.indent("\n".join(shown), "      ")


def format_trajectory(events: list[dict[str, Any]]) -> str:
    """Human-readable rendering of a trajectory for the terminal."""
    out: list[str] = []
    for event in events:
        if event["type"] == "run_start":
            out.append(f"provider={event['provider']} model={event['model']}")
            out.append(f"task: {event['task']}\n")
        elif event["type"] == "step":
            out.append(f"[step {event['step']}] {event['text']}")
            results = {o["call_id"]: o for o in event["observations"]}
            for call in event["tool_calls"]:
                args = ", ".join(f"{k}={v!r}" for k, v in call["args"].items() if k != "patch")
                out.append(f"  -> {call['name']}({args})")
                if call["name"] == "apply_patch":
                    out.append(_indent(call["args"]["patch"]))
                observation = results.get(call["id"])
                if observation:
                    label = "ERROR" if observation["is_error"] else "ok"
                    out.append(f"  <- {label}")
                    out.append(_indent(observation["output"], limit=6))
        elif event["type"] == "context_summarised":
            out.append(
                f"[context] {event['summariser']} summary: {event['tokens_before']} -> "
                f"{event['tokens_after']} tokens"
            )
        elif event["type"] == "run_end":
            out.append(
                f"\nstopped: {event['stop_reason']} after {event['steps']} steps, "
                f"tokens in/out {event['usage']['input_tokens']}/{event['usage']['output_tokens']}"
            )
            if event["finish_summary"]:
                out.append(f"summary: {event['finish_summary']}")
        elif event["type"] == "evaluation":
            verdict = "PASS" if event["failure"] is None else f"FAIL ({event['failure']})"
            out.append(
                f"evaluation: visible tests {'pass' if event['visible_passed'] else 'fail'}, "
                f"hidden tests {'pass' if event['hidden_passed'] else 'fail'} -> {verdict}"
            )
    return "\n".join(out)


def _select(tasks: list[Task], ids: str | None) -> list[Task]:
    if not ids:
        return tasks
    wanted = ids.split(",")
    selected = [t for t in tasks if t.id in wanted or any(t.id.startswith(w) for w in wanted)]
    if not selected:
        raise SystemExit(f"No task matches {ids!r}.")
    return selected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mini_agent", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", aliases=["demo"], help="Run the agent on one task and print it")
    run.add_argument("--task", default="01_pagination_off_by_one", help="task id or prefix")
    run.add_argument("--out", type=Path, help="directory for the trajectory (default: temp)")

    bench = sub.add_parser("bench", help="Run the benchmark and write results")
    bench.add_argument("--tasks", help="comma-separated task ids or prefixes (default: all)")
    bench.add_argument("--out", type=Path, help="default: bench/results/<mock|live|replay>")
    bench.add_argument("--replay-dir", type=Path, help="recorded run to replay (--provider replay)")
    bench.add_argument("--samples", type=int, default=1, help="runs per task, for pass@k")
    bench.add_argument("--workers", type=int, default=1, help="tasks to run in parallel")
    bench.add_argument(
        "--compare-to",
        type=Path,
        help="exit with status 1 if results differ from this run directory (timings ignored)",
    )
    bench.add_argument(
        "--min-pass-rate",
        type=float,
        default=0.0,
        help="exit with status 1 if any strategy's pass@1 is below this (used by CI)",
    )

    view = sub.add_parser("view", help="Render a run directory or one .jsonl file as HTML")
    view.add_argument("path", type=Path)

    run.add_argument("--provider", choices=["mock", "anthropic"], default="mock")
    bench.add_argument("--provider", choices=list(MODES), default="mock")
    for command in (run, bench):
        command.add_argument("--max-steps", type=int, default=AgentConfig.max_steps)
        command.add_argument(
            "--summariser",
            choices=["extractive", "model"],
            default=AgentConfig.summariser,
            help="how old turns are summarised near the context limit",
        )
        command.add_argument(
            "--sandbox-image",
            help="run all tests inside this Docker image (no network); default: on the host",
        )
    run.add_argument("--strategy", choices=["direct", "plan"], default="direct")
    bench.add_argument("--strategy", choices=["direct", "plan", "both"], default="both")

    args = parser.parse_args(argv)
    if args.command == "view":
        if args.path.suffix == ".jsonl":
            page = args.path.with_suffix(".html")
            page.write_text(render_trajectory(read_trajectory(args.path)))
        else:
            page = render_run(args.path)
        print(f"wrote {page}")
        return 0

    config = AgentConfig(max_steps=args.max_steps, summariser=args.summariser)
    sandbox = DockerSandbox(args.sandbox_image) if args.sandbox_image else None
    tasks = load_tasks(TASKS_DIR)

    if args.command in ("run", "demo"):
        [task] = _select(tasks, args.task)[:1]
        out = args.out or Path(tempfile.mkdtemp(prefix="mini-agent-"))
        run_task(task, args.provider, args.strategy, out, config, sandbox=sandbox)
        path = out / "trajectories" / args.strategy / f"{task.id}.jsonl"
        print(format_trajectory(read_trajectory(path)))
        print(f"\ntrajectory: {path}")
        return 0

    strategies = ["direct", "plan"] if args.strategy == "both" else [args.strategy]
    tasks = _select(tasks, args.tasks)
    args.out = args.out or Path("bench/results") / MODES[args.provider]
    results = run_benchmark(
        tasks,
        args.provider,
        strategies,
        args.out,
        config,
        args.replay_dir,
        args.samples,
        args.workers,
        sandbox,
    )
    print((args.out / "results.md").read_text())
    print(f"{len(results)} runs written to {args.out}")
    rates = {s: summary["pass_at_1"] for s, summary in summarise_results(results).items()}
    below = {s: rate for s, rate in rates.items() if rate < args.min_pass_rate}
    if below:
        print(f"pass@1 below {args.min_pass_rate:.0%}: {below}")
        return 1
    if args.compare_to:
        expected = json.loads((args.compare_to / "results.json").read_text())
        actual = json.loads((args.out / "results.json").read_text())
        differences = compare_results(expected, actual)
        for difference in differences[:20]:
            print(f"differs from {args.compare_to}: {difference}")
        if differences:
            return 1
    return 0
