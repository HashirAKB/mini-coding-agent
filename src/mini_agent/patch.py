"""A small unified diff parser and applier.

Why write our own instead of shelling out to `patch` or `git apply`?
1. Error messages are written for the model: they say which hunk failed and
   how to recover, which is what lets the agent fix its own mistakes.
2. Line numbers and counts in `@@` headers are treated as hints. Models often
   get them wrong while getting the actual lines right.
3. It is all-or-nothing: if any hunk fails, no file is touched.

Supported: modify, create (`--- /dev/null`) and delete (`+++ /dev/null`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from mini_agent.types import ToolError
from mini_agent.workspace import Workspace

HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


class PatchError(ToolError):
    """The patch is malformed or does not match the files."""


@dataclass
class Hunk:
    old_start: int
    lines: list[str]  # each line keeps its prefix: " " context, "-" removed, "+" added

    @property
    def old_lines(self) -> list[str]:
        return [line[1:] for line in self.lines if line[0] in " -"]

    @property
    def new_lines(self) -> list[str]:
        return [line[1:] for line in self.lines if line[0] in " +"]

    @property
    def removed_count(self) -> int:
        return sum(1 for line in self.lines if line[0] == "-")

    @property
    def added_count(self) -> int:
        return sum(1 for line in self.lines if line[0] == "+")


@dataclass
class FilePatch:
    old_path: str | None  # None means the file is being created
    new_path: str | None  # None means the file is being deleted
    hunks: list[Hunk] = field(default_factory=list)

    @property
    def path(self) -> str:
        path = self.new_path or self.old_path
        assert path is not None
        return path


def _header_path(line: str) -> str | None:
    """`--- a/pkg/x.py\t2024-01-01` -> `pkg/x.py`; `/dev/null` -> None."""
    path = line[4:].split("\t")[0].strip()
    if path == "/dev/null":
        return None
    if path.startswith(("a/", "b/")):
        path = path[2:]
    return path


def _is_file_header(lines: list[str], i: int) -> bool:
    return lines[i].startswith("--- ") and i + 1 < len(lines) and lines[i + 1].startswith("+++ ")


def parse_patch(text: str) -> list[FilePatch]:
    if not text.strip():
        raise PatchError("The patch is empty.")
    lines = text.splitlines()
    patches: list[FilePatch] = []
    i = 0
    while i < len(lines):
        if not _is_file_header(lines, i):
            i += 1  # skip "diff --git", "index ...", prose, etc.
            continue
        current = FilePatch(_header_path(lines[i]), _header_path(lines[i + 1]))
        patches.append(current)
        i += 2
        while i < len(lines) and not _is_file_header(lines, i):
            line = lines[i]
            if line.startswith("@@"):
                match = HUNK_HEADER.match(line)
                if not match:
                    raise PatchError(
                        f"Bad hunk header {line!r} in {current.path}. "
                        "Expected the form '@@ -12,3 +12,4 @@'."
                    )
                current.hunks.append(Hunk(old_start=int(match.group(1)), lines=[]))
            elif current.hunks and (line == "" or line[0] in " -+"):
                # An empty line is a blank context line whose leading space was stripped.
                current.hunks[-1].lines.append(line or " ")
            # Anything else ("\ No newline at end of file", "diff --git") is ignored.
            i += 1
    if not patches:
        raise PatchError(
            "No file headers found. A unified diff starts with '--- a/path' and '+++ b/path'."
        )
    for file_patch in patches:
        if not file_patch.hunks:
            raise PatchError(f"The patch for {file_patch.path} has no hunks ('@@ ... @@' lines).")
    return patches


def _find_hunk(lines: list[str], old: list[str], expected: int, start: int) -> int | None:
    """Index where `old` occurs in `lines` (at or after `start`), closest to `expected`."""
    candidates = [
        i for i in range(start, len(lines) - len(old) + 1) if lines[i : i + len(old)] == old
    ]
    if not candidates:
        # Second chance: ignore trailing whitespace, a very common model slip.
        stripped = [line.rstrip() for line in lines]
        wanted = [line.rstrip() for line in old]
        candidates = [
            i
            for i in range(start, len(lines) - len(old) + 1)
            if stripped[i : i + len(old)] == wanted
        ]
    if not candidates:
        return None
    return min(candidates, key=lambda i: abs(i - expected))


def _apply_hunks(path: str, original: list[str], hunks: list[Hunk]) -> list[str]:
    result = list(original)
    cursor = 0  # hunks must apply in order and must not overlap
    offset = 0  # how far earlier hunks shifted later line numbers
    for number, hunk in enumerate(hunks, start=1):
        old = hunk.old_lines
        expected = max(hunk.old_start - 1, 0) + offset
        if not old:  # pure insertion: trust the line number
            index: int | None = min(max(expected, cursor), len(result))
        else:
            index = _find_hunk(result, old, expected, cursor)
        if index is None:
            preview = "\n".join(old[:8])
            raise PatchError(
                f"hunk {number} for {path} does not match the file. "
                f"These lines were expected but not found:\n{preview}\n"
                f"Re-read the file with read_file and copy context lines exactly."
            )
        result[index : index + len(old)] = hunk.new_lines
        cursor = index + len(hunk.new_lines)
        offset += len(hunk.new_lines) - len(old)
    return result


def apply_patch(workspace: Workspace, text: str) -> str:
    """Apply a unified diff to the workspace. Returns a short summary for the model."""
    patches = parse_patch(text)
    # Phase 1: compute every new file content in memory. Nothing is written yet.
    new_contents: dict[Path, str | None] = {}  # None means delete
    summary: list[str] = []
    for file_patch in patches:
        target = workspace.resolve(file_patch.path)
        if file_patch.old_path is None:
            if target.exists() or new_contents.get(target) is not None:
                raise PatchError(f"Cannot create {file_patch.path}: it already exists.")
            lines: list[str] = []
            for hunk in file_patch.hunks:
                lines.extend(hunk.new_lines)
            new_contents[target] = "\n".join(lines) + "\n"
            summary.append(f"created {file_patch.path}")
            continue
        if target in new_contents:
            current = new_contents[target]
        elif target.is_file():
            current = target.read_text()
        else:
            current = None
        if current is None:
            raise PatchError(f"Cannot modify {file_patch.path}: the file does not exist.")
        if file_patch.new_path is None:
            new_contents[target] = None
            summary.append(f"deleted {file_patch.path}")
            continue
        updated = _apply_hunks(file_patch.path, current.splitlines(), file_patch.hunks)
        new_contents[target] = "\n".join(updated) + "\n" if updated else ""
        added = sum(h.added_count for h in file_patch.hunks)
        removed = sum(h.removed_count for h in file_patch.hunks)
        summary.append(f"modified {file_patch.path} (+{added} -{removed})")
    # Phase 2: every hunk matched, so write everything.
    for target, content in new_contents.items():
        if content is None:
            target.unlink()
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
    return "Patch applied: " + ", ".join(summary)
