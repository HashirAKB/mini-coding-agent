"""Trajectories: one JSON object per line (JSONL), one file per run.

JSONL is append-only, so a crash mid-run still leaves a readable file, and a
run can be inspected with nothing more than `head` or `jq`.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import TracebackType
from typing import Any, TextIO


class TrajectoryWriter:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._file: TextIO = path.open("w")

    def write(self, event: dict[str, Any]) -> None:
        self._file.write(json.dumps(event) + "\n")
        self._file.flush()

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> TrajectoryWriter:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


def read_trajectory(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
