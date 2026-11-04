"""Where pytest runs: on the host (default) or inside a throwaway Docker container.

`run_tests` and the harness's evaluation both execute code the agent wrote.
The path checks in Workspace only protect the file tools, so for real
isolation use DockerSandbox: no network, capped memory and CPU, and only the
workspace mounted.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class Sandbox(Protocol):
    def command(self, args: list[str], root: Path, name: str) -> list[str]:
        """Wrap `args` (run with `root` as working directory) into the real command."""
        ...

    def kill(self, name: str) -> None:
        """Stop a run that timed out."""
        ...


@dataclass(frozen=True)
class DockerSandbox:
    image: str  # must contain Python and pytest, e.g. this project's own image
    memory: str = "1g"
    cpus: str = "1"

    def command(self, args: list[str], root: Path, name: str) -> list[str]:
        return [
            "docker", "run", "--rm",
            "--network", "none",
            "--name", name,
            "--memory", self.memory,
            "--cpus", self.cpus,
            "-e", "PYTHONDONTWRITEBYTECODE=1",
            "-v", f"{root.resolve()}:/work",
            "-w", "/work",
            "--entrypoint", "",
            self.image, *args,
        ]  # fmt: skip

    def kill(self, name: str) -> None:
        # Killing the docker client on timeout does not stop the container.
        subprocess.run(["docker", "kill", name], capture_output=True)


def run_pytest(
    root: Path, target: str | None, timeout: float, sandbox: Sandbox | None = None
) -> subprocess.CompletedProcess[str] | None:
    """Run pytest in `root` on `target` (relative to root). Returns None on timeout."""
    args = ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    if target is not None:
        args.append(target)
    name = f"mini-agent-{uuid.uuid4().hex[:12]}"
    command = sandbox.command(args, root, name) if sandbox else [sys.executable, *args[1:]]
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        return subprocess.run(
            command, cwd=root, capture_output=True, text=True, timeout=timeout, env=env
        )
    except subprocess.TimeoutExpired:
        if sandbox is not None:
            sandbox.kill(name)
        return None
