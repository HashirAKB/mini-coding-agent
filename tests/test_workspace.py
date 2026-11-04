import os
from pathlib import Path

import pytest

from mini_agent.types import ToolError
from mini_agent.workspace import Workspace


def test_resolves_paths_inside_root(workspace: Workspace) -> None:
    assert workspace.resolve("calc.py") == workspace.root / "calc.py"
    assert workspace.resolve("tests/../calc.py") == workspace.root / "calc.py"
    assert workspace.resolve(".") == workspace.root


@pytest.mark.parametrize("bad", ["../secret.txt", "tests/../../x", "/etc/passwd", "~/.ssh/id_rsa"])
def test_rejects_paths_outside_root(workspace: Workspace, bad: str) -> None:
    with pytest.raises(ToolError, match="outside the workspace"):
        workspace.resolve(bad)


def test_rejects_symlink_escaping_root(workspace: Workspace, tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("top secret")
    os.symlink(secret, workspace.root / "link.txt")
    with pytest.raises(ToolError, match="outside the workspace"):
        workspace.resolve("link.txt")


def test_relative_display(workspace: Workspace) -> None:
    assert workspace.relative(workspace.root / "tests" / "test_calc.py") == "tests/test_calc.py"
