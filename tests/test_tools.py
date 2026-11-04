from pathlib import Path

from mini_agent.tools import TOOL_SPECS, ToolBox
from mini_agent.types import ToolCall
from mini_agent.workspace import Workspace
from tests.conftest import CALC_FIX


def run(box: ToolBox, name: str, **args: object):  # type: ignore[no-untyped-def]
    return box.execute(ToolCall(id="t1", name=name, args=dict(args)))


def test_every_spec_has_a_json_schema() -> None:
    names = {spec.name for spec in TOOL_SPECS}
    assert names == {"list_dir", "read_file", "search", "apply_patch", "run_tests", "finish"}
    for spec in TOOL_SPECS:
        assert spec.input_schema["type"] == "object"
        assert spec.description


def test_list_dir(workspace: Workspace) -> None:
    result = run(ToolBox(workspace), "list_dir", path=".")
    assert not result.is_error
    assert result.output.splitlines() == ["calc.py", "tests/"]


def test_read_file_with_line_numbers_and_range(workspace: Workspace) -> None:
    result = run(ToolBox(workspace), "read_file", path="calc.py", start_line=5, end_line=6)
    assert result.output.splitlines()[1:] == [
        "   5 | def mean(values):",
        "   6 |     return sum(values) / (len(values) - 1)",
    ]
    assert "lines 5-6 of 6" in result.output


def test_read_file_pages_long_files(workspace: Workspace) -> None:
    (workspace.root / "big.py").write_text("".join(f"x{i} = {i}\n" for i in range(500)))
    result = run(ToolBox(workspace, max_read_lines=100), "read_file", path="big.py")
    assert "lines 1-100 of 500" in result.output
    assert "start_line=101" in result.output  # pointer to continue


def test_read_file_errors(workspace: Workspace) -> None:
    box = ToolBox(workspace)
    assert run(box, "read_file", path="missing.py").is_error
    assert run(box, "read_file", path="tests").is_error
    traversal = run(box, "read_file", path="../../etc/passwd")
    assert traversal.is_error and "outside the workspace" in traversal.output


def test_search_finds_matches(workspace: Workspace) -> None:
    result = run(ToolBox(workspace), "search", pattern=r"def \w+\(")
    assert "calc.py:1: def add(a, b):" in result.output
    assert "tests/test_calc.py:4: def test_add():" in result.output


def test_search_invalid_regex_is_reported(workspace: Workspace) -> None:
    result = run(ToolBox(workspace), "search", pattern="(unclosed")
    assert result.is_error and "Invalid regex" in result.output


def test_search_caps_results(workspace: Workspace) -> None:
    (workspace.root / "many.txt").write_text("hit\n" * 300)
    result = run(ToolBox(workspace, max_search_results=10), "search", pattern="hit")
    assert result.output.count("many.txt:") == 10
    assert "290 more" in result.output


def test_apply_patch_and_run_tests(workspace: Workspace) -> None:
    box = ToolBox(workspace)
    before = run(box, "run_tests")
    assert "exit code 1" in before.output and "1 failed" in before.output
    assert not run(box, "apply_patch", patch=CALC_FIX).is_error
    after = run(box, "run_tests")
    assert "exit code 0" in after.output and "2 passed" in after.output


def test_apply_patch_error_is_returned_not_raised(workspace: Workspace) -> None:
    result = run(ToolBox(workspace), "apply_patch", patch="not a diff")
    assert result.is_error and "Patch rejected" in result.output


def test_run_tests_timeout(workspace: Workspace) -> None:
    (workspace.root / "tests" / "test_slow.py").write_text(
        "import time\n\ndef test_slow():\n    time.sleep(30)\n"
    )
    result = run(ToolBox(workspace, test_timeout=1.0), "run_tests", path="tests/test_slow.py")
    assert result.is_error and "timed out" in result.output


def test_run_tests_path_is_confined(workspace: Workspace, tmp_path: Path) -> None:
    result = run(ToolBox(workspace), "run_tests", path="../")
    assert result.is_error and "outside the workspace" in result.output


def test_unknown_tool_and_bad_arguments(workspace: Workspace) -> None:
    box = ToolBox(workspace)
    assert "Unknown tool" in run(box, "rm_rf").output
    missing = run(box, "read_file")
    assert missing.is_error and "path" in missing.output
    wrong_type = run(box, "read_file", path="calc.py", start_line="one")
    assert wrong_type.is_error and "start_line" in wrong_type.output
