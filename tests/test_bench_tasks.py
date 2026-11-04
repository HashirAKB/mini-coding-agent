"""Validates the benchmark itself: every task must be solvable and must detect overfitting."""

from pathlib import Path

import pytest

from mini_agent.bench import TASKS_DIR, load_tasks, prepare_workspace, run_suite
from mini_agent.patch import apply_patch
from mini_agent.workspace import Workspace

TASKS = load_tasks(TASKS_DIR)


def test_there_are_twenty_well_formed_tasks() -> None:
    assert len(TASKS) == 20
    assert len({task.id for task in TASKS}) == 20
    for task in TASKS:
        assert task.title and task.category and task.description
        assert task.solution_patch.startswith("--- a/")
        assert not (task.repo_dir / "hidden").exists()  # hidden tests live outside the repo


@pytest.mark.parametrize("task", TASKS, ids=[task.id for task in TASKS])
def test_task_fails_before_and_passes_after_reference_fix(task, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    root = prepare_workspace(task, tmp_path)
    assert not run_suite(root, "tests").passed, "visible tests must fail on the buggy code"
    assert not run_suite(root, "hidden_tests", task).passed, "hidden tests must fail too"

    apply_patch(Workspace(root), task.solution_patch)
    visible = run_suite(root, "tests")
    hidden = run_suite(root, "hidden_tests", task)
    assert visible.passed, visible.output
    assert hidden.passed, hidden.output


def test_overfit_patches_pass_visible_but_fail_hidden(tmp_path: Path) -> None:
    overfit_tasks = [task for task in TASKS if task.overfit_patch]
    assert overfit_tasks
    for task in overfit_tasks:
        assert task.overfit_patch is not None
        root = prepare_workspace(task, tmp_path / task.id)
        apply_patch(Workspace(root), task.overfit_patch)
        assert run_suite(root, "tests").passed
        assert not run_suite(root, "hidden_tests", task).passed
