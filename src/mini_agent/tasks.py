"""Benchmark tasks and how to evaluate a workspace against them."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from mini_agent.sandbox import Sandbox, run_pytest


def default_tasks_dir() -> Path:
    """$MINI_AGENT_TASKS_DIR, else the source checkout's bench/tasks, else ./bench/tasks."""
    if "MINI_AGENT_TASKS_DIR" in os.environ:
        return Path(os.environ["MINI_AGENT_TASKS_DIR"])
    checkout = Path(__file__).resolve().parents[2] / "bench" / "tasks"
    return checkout if checkout.is_dir() else Path.cwd() / "bench" / "tasks"


TASKS_DIR = default_tasks_dir()
HIDDEN_DIR_NAME = "hidden_tests"
EVAL_TIMEOUT_SECONDS = 120.0


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    category: str
    description: str
    path: Path  # bench/tasks/<id>
    solution_patch: str
    overfit_patch: str | None = None

    @property
    def repo_dir(self) -> Path:
        return self.path / "repo"

    @property
    def hidden_dir(self) -> Path:
        return self.path / "hidden"


def load_tasks(tasks_dir: Path = TASKS_DIR) -> list[Task]:
    tasks = []
    for path in sorted(p for p in tasks_dir.iterdir() if (p / "task.json").is_file()):
        meta = json.loads((path / "task.json").read_text())
        overfit = path / "overfit.patch"
        tasks.append(
            Task(
                id=meta["id"],
                title=meta["title"],
                category=meta["category"],
                description=meta["description"],
                path=path,
                solution_patch=(path / "solution.patch").read_text(),
                overfit_patch=overfit.read_text() if overfit.is_file() else None,
            )
        )
    return tasks


def prepare_workspace(task: Task, parent: Path) -> Path:
    """Copy the task's repo (never its hidden tests) into a fresh directory."""
    root = parent / "workspace"
    shutil.copytree(task.repo_dir, root)
    return root


@dataclass
class SuiteResult:
    passed: bool
    output: str


def run_suite(
    root: Path, suite: str, task: Task | None = None, sandbox: Sandbox | None = None
) -> SuiteResult:
    """Run one test suite in `root`.

    For "tests" the original visible tests are restored first, so an agent
    that edited the tests cannot fake a pass. For "hidden_tests" the hidden
    tests are copied in from the task directory (they were never visible).
    """
    target = root / suite
    if suite == HIDDEN_DIR_NAME:
        assert task is not None, "hidden tests need the task"
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(task.hidden_dir, target)
    elif task is not None:
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(task.repo_dir / suite, target)
    completed = run_pytest(root, suite, EVAL_TIMEOUT_SECONDS, sandbox)
    if completed is None:
        return SuiteResult(False, f"timed out after {EVAL_TIMEOUT_SECONDS:.0f}s")
    return SuiteResult(completed.returncode == 0, completed.stdout + completed.stderr)
