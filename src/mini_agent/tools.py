"""The agent's tools: their JSON schemas (what the model sees) and implementations.

Every tool receives model-supplied arguments, so every tool:
- validates its arguments and raises ToolError with a readable message,
- resolves paths through Workspace (no escaping the working copy),
- bounds its output (pages for read_file, a cap for search),
- never raises to the caller: ToolBox.execute turns errors into observations.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from mini_agent.patch import apply_patch
from mini_agent.types import ToolCall, ToolError, ToolResult
from mini_agent.workspace import Workspace

IGNORED_NAMES = {"__pycache__", ".pytest_cache", ".git", ".mypy_cache", ".ruff_cache"}


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        "list_dir",
        "List the entries of a directory in the repository. Directories end with '/'.",
        _schema({"path": {"type": "string", "description": "Directory, default '.'"}}, []),
    ),
    ToolSpec(
        "read_file",
        "Read a text file with line numbers. Use start_line/end_line (1-based, inclusive) "
        "to read part of a long file.",
        _schema(
            {
                "path": {"type": "string"},
                "start_line": {"type": "integer", "minimum": 1},
                "end_line": {"type": "integer", "minimum": 1},
            },
            ["path"],
        ),
    ),
    ToolSpec(
        "search",
        "Search file contents with a Python regular expression. Returns 'path:line: text'.",
        _schema(
            {
                "pattern": {"type": "string"},
                "path": {"type": "string", "description": "File or directory, default '.'"},
            },
            ["pattern"],
        ),
    ),
    ToolSpec(
        "apply_patch",
        "Apply a unified diff (with '--- a/path', '+++ b/path' and '@@' hunks) to the "
        "repository. Context lines must match the current file exactly. Either every hunk "
        "applies or nothing changes.",
        _schema({"patch": {"type": "string"}}, ["patch"]),
    ),
    ToolSpec(
        "run_tests",
        "Run pytest in the repository (optionally on one test file or directory) and return "
        "its output and exit code.",
        _schema({"path": {"type": "string"}}, []),
    ),
    ToolSpec(
        "finish",
        "Stop working. Use status 'done' when the fix is complete and tests pass, or "
        "'give_up' if you cannot fix it.",
        _schema(
            {
                "status": {"type": "string", "enum": ["done", "give_up"]},
                "summary": {"type": "string"},
            },
            ["status", "summary"],
        ),
    ),
]
SPECS_BY_NAME = {spec.name: spec for spec in TOOL_SPECS}
JSON_TYPES: dict[str, type | tuple[type, ...]] = {"string": str, "integer": int}


def validate_args(spec: ToolSpec, args: dict[str, Any]) -> None:
    """A deliberately tiny JSON-schema check: required keys, known keys, basic types."""
    properties: dict[str, Any] = spec.input_schema["properties"]
    for name in spec.input_schema["required"]:
        if name not in args:
            raise ToolError(f"{spec.name}: missing required argument '{name}'.")
    for name, value in args.items():
        if name not in properties:
            raise ToolError(f"{spec.name}: unknown argument '{name}'.")
        expected = properties[name]["type"]
        if not isinstance(value, JSON_TYPES[expected]) or isinstance(value, bool):
            raise ToolError(f"{spec.name}: argument '{name}' must be a {expected}.")
        if "enum" in properties[name] and value not in properties[name]["enum"]:
            raise ToolError(f"{spec.name}: '{name}' must be one of {properties[name]['enum']}.")


class ToolBox:
    """Executes tool calls against one workspace."""

    def __init__(
        self,
        workspace: Workspace,
        test_timeout: float = 60.0,
        max_read_lines: int = 200,
        max_search_results: int = 50,
    ) -> None:
        self.workspace = workspace
        self.test_timeout = test_timeout
        self.max_read_lines = max_read_lines
        self.max_search_results = max_search_results
        self._handlers: dict[str, Callable[..., str]] = {
            "list_dir": self.list_dir,
            "read_file": self.read_file,
            "search": self.search,
            "apply_patch": self.apply_patch,
            "run_tests": self.run_tests,
            "finish": self.finish,
        }

    def execute(self, call: ToolCall) -> ToolResult:
        """Run one tool call. Errors become observations so the model can react to them."""
        spec = SPECS_BY_NAME.get(call.name)
        if spec is None:
            known = ", ".join(SPECS_BY_NAME)
            return ToolResult(call.id, f"Unknown tool '{call.name}'. Known: {known}.", True)
        try:
            validate_args(spec, call.args)
            return ToolResult(call.id, self._handlers[call.name](**call.args))
        except ToolError as error:
            return ToolResult(call.id, str(error), is_error=True)

    # ---- individual tools ------------------------------------------------------

    def list_dir(self, path: str = ".") -> str:
        directory = self.workspace.resolve(path)
        if not directory.is_dir():
            raise ToolError(f"list_dir: '{path}' is not a directory.")
        entries = [
            child.name + ("/" if child.is_dir() else "")
            for child in sorted(directory.iterdir())
            if child.name not in IGNORED_NAMES
        ]
        return "\n".join(entries) or "(empty directory)"

    def read_file(self, path: str, start_line: int = 1, end_line: int | None = None) -> str:
        target = self.workspace.resolve(path)
        if not target.is_file():
            raise ToolError(f"read_file: '{path}' is not a file.")
        try:
            lines = target.read_text().splitlines()
        except UnicodeDecodeError as error:
            raise ToolError(f"read_file: '{path}' is not a UTF-8 text file.") from error
        if start_line < 1:
            raise ToolError("read_file: start_line must be 1 or more (lines are 1-based).")
        if end_line is not None and end_line < start_line:
            raise ToolError("read_file: end_line must not be smaller than start_line.")
        total = len(lines)
        if total == 0:
            return f"{path} (empty file)"
        if start_line > total:
            raise ToolError(f"read_file: start_line {start_line} is past the end ({total} lines).")
        last = min(end_line or total, total, start_line + self.max_read_lines - 1)
        body = "\n".join(f"{n:4d} | {lines[n - 1]}" for n in range(start_line, last + 1))
        header = f"{path} (lines {start_line}-{last} of {total})"
        if last < (end_line or total):
            body += f"\n[... more lines; call read_file with start_line={last + 1} to continue]"
        return f"{header}\n{body}"

    def search(self, pattern: str, path: str = ".") -> str:
        try:
            regex = re.compile(pattern)
        except re.error as error:
            raise ToolError(f"Invalid regex {pattern!r}: {error}") from error
        root = self.workspace.resolve(path)
        if not root.exists():
            raise ToolError(f"search: '{path}' does not exist.")
        files = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file())
        matches: list[str] = []
        for file in files:
            if IGNORED_NAMES.intersection(file.relative_to(self.workspace.root).parts):
                continue
            if not file.resolve().is_relative_to(self.workspace.root):
                continue  # a symlink pointing outside the workspace
            try:
                text = file.read_text()
            except UnicodeDecodeError:
                continue  # skip binary files
            for number, line in enumerate(text.splitlines(), start=1):
                if regex.search(line):
                    matches.append(f"{self.workspace.relative(file)}:{number}: {line}")
        if not matches:
            return f"No matches for {pattern!r}."
        shown = matches[: self.max_search_results]
        hidden = len(matches) - len(shown)
        if hidden:
            shown.append(f"[... {hidden} more matches not shown; narrow the pattern or path]")
        return "\n".join(shown)

    def apply_patch(self, patch: str) -> str:
        try:
            return apply_patch(self.workspace, patch)
        except ToolError as error:
            raise ToolError(f"Patch rejected, no files were changed. {error}") from error

    def run_tests(self, path: str | None = None) -> str:
        command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
        if path is not None:
            command.append(self.workspace.resolve(path).as_posix())
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        try:
            completed = subprocess.run(
                command,
                cwd=self.workspace.root,
                capture_output=True,
                text=True,
                timeout=self.test_timeout,
                env=env,
            )
        except subprocess.TimeoutExpired as error:
            raise ToolError(
                f"run_tests timed out after {self.test_timeout:.0f}s. "
                "Look for infinite loops or blocking calls."
            ) from error
        output = (completed.stdout + completed.stderr).strip()
        return f"exit code {completed.returncode}\n{output}"

    def finish(self, status: str, summary: str) -> str:
        # The agent loop reacts to `finish`; the tool itself only acknowledges it.
        return f"Finished with status '{status}'."
