"""The agent's working copy and the rule that keeps file access inside it."""

from __future__ import annotations

from pathlib import Path

from mini_agent.types import ToolError


class Workspace:
    """A directory the agent may read and write. Nothing outside it is reachable."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def resolve(self, path: str) -> Path:
        """Turn a model-supplied path into an absolute path inside the workspace.

        `Path.resolve()` collapses `..` and follows symlinks, so checking the
        *resolved* path catches `../x`, absolute paths and symlinks that point
        outside the root. `~` is not expanded, so `~/x` stays a harmless
        relative name, but we reject it anyway to give the model a clear error.
        """
        if path.startswith("~"):
            raise ToolError(f"Path '{path}' is outside the workspace.")
        candidate = (self.root / path).resolve()
        if not candidate.is_relative_to(self.root):
            raise ToolError(f"Path '{path}' is outside the workspace.")
        return candidate

    def relative(self, path: Path) -> str:
        """Display form of a path: relative to the root, with forward slashes."""
        return path.relative_to(self.root).as_posix()
