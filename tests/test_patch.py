from pathlib import Path

import pytest

from mini_agent.patch import PatchError, apply_patch, parse_patch
from mini_agent.types import ToolError
from mini_agent.workspace import Workspace
from tests.conftest import CALC_FIX


def test_parse_single_file_patch() -> None:
    [file_patch] = parse_patch(CALC_FIX)
    assert file_patch.old_path == "calc.py"
    assert file_patch.new_path == "calc.py"
    [hunk] = file_patch.hunks
    assert hunk.old_start == 4
    assert hunk.removed_count == 1 and hunk.added_count == 1


def test_apply_modifies_file(workspace: Workspace) -> None:
    summary = apply_patch(workspace, CALC_FIX)
    assert "calc.py" in summary
    assert "return sum(values) / len(values)" in (workspace.root / "calc.py").read_text()


def test_apply_tolerates_wrong_line_numbers_and_counts(workspace: Workspace) -> None:
    # Models often get the @@ numbers wrong; we only use them as a hint.
    patch = CALC_FIX.replace("@@ -4,3 +4,3 @@", "@@ -1,9 +1,2 @@")
    apply_patch(workspace, patch)
    assert "/ len(values)\n" in (workspace.root / "calc.py").read_text()


def test_apply_creates_and_deletes_files(workspace: Workspace) -> None:
    create = "--- /dev/null\n+++ b/notes/new.txt\n@@ -0,0 +1,2 @@\n+hello\n+world\n"
    apply_patch(workspace, create)
    assert (workspace.root / "notes" / "new.txt").read_text() == "hello\nworld\n"
    delete = "--- a/notes/new.txt\n+++ /dev/null\n@@ -1,2 +0,0 @@\n-hello\n-world\n"
    apply_patch(workspace, delete)
    assert not (workspace.root / "notes" / "new.txt").exists()


def test_context_mismatch_gives_helpful_error(workspace: Workspace) -> None:
    patch = CALC_FIX.replace("(len(values) - 1)\n+", "(len(vals) - 1)\n+")
    with pytest.raises(PatchError) as info:
        apply_patch(workspace, patch)
    message = str(info.value)
    assert "hunk 1" in message and "calc.py" in message
    assert "read_file" in message  # tells the model how to recover


def test_failed_patch_changes_nothing(workspace: Workspace) -> None:
    good = CALC_FIX
    bad = "--- a/tests/test_calc.py\n+++ b/tests/test_calc.py\n@@ -1 +1 @@\n-nope\n+x\n"
    before = (workspace.root / "calc.py").read_text()
    with pytest.raises(PatchError):
        apply_patch(workspace, good + bad)
    assert (workspace.root / "calc.py").read_text() == before


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("", "empty"),
        ("just some prose", "---"),
        ("--- a/calc.py\n+++ b/calc.py\n", "no hunks"),
        ("--- a/calc.py\n+++ b/calc.py\n@@ bogus @@\n", "hunk header"),
    ],
)
def test_malformed_patches_are_rejected(text: str, fragment: str) -> None:
    with pytest.raises(PatchError, match=fragment):
        parse_patch(text)


def test_patch_cannot_escape_workspace(workspace: Workspace) -> None:
    patch = "--- /dev/null\n+++ b/../evil.py\n@@ -0,0 +1 @@\n+boom\n"
    with pytest.raises(ToolError, match="outside the workspace"):
        apply_patch(workspace, patch)
    assert not (workspace.root.parent / "evil.py").exists()


def test_modify_missing_file_is_an_error(workspace: Workspace) -> None:
    patch = "--- a/nope.py\n+++ b/nope.py\n@@ -1 +1 @@\n-a\n+b\n"
    with pytest.raises(PatchError, match="does not exist"):
        apply_patch(workspace, patch)


def test_create_existing_file_is_an_error(workspace: Workspace) -> None:
    patch = "--- /dev/null\n+++ b/calc.py\n@@ -0,0 +1 @@\n+x\n"
    with pytest.raises(PatchError, match="already exists"):
        apply_patch(workspace, patch)


def test_git_style_headers_are_ignored(workspace: Workspace, repo: Path) -> None:
    patch = "diff --git a/calc.py b/calc.py\nindex 123..456 100644\n" + CALC_FIX
    apply_patch(workspace, patch)
    assert "/ len(values)\n" in (repo / "calc.py").read_text()
