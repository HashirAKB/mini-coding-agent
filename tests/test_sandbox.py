"""Docker sandbox for running agent-written code.

Unit tests check the docker command we build and the plumbing through ToolBox.
The integration test runs a real container and is skipped unless Docker and the
image named by MINI_AGENT_SANDBOX_IMAGE are available (CI's docker job sets it).
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from mini_agent.sandbox import DockerSandbox
from mini_agent.tasks import TASKS_DIR, load_tasks, prepare_workspace, run_suite
from mini_agent.tools import ToolBox
from mini_agent.types import ToolCall
from mini_agent.workspace import Workspace


def test_docker_command_isolates_the_run(tmp_path: Path) -> None:
    sandbox = DockerSandbox(image="mini-agent", memory="512m", cpus="1")
    command = sandbox.command(["python", "-m", "pytest", "-q"], tmp_path, name="run-1")
    assert command[:3] == ["docker", "run", "--rm"]
    assert command[3:5] == ["--network", "none"]
    assert "--name" in command and "run-1" in command
    assert f"{tmp_path.resolve()}:/work" in command
    assert command[command.index("-w") + 1] == "/work"
    assert command[command.index("--memory") + 1] == "512m"
    assert command[-5:] == ["mini-agent", "python", "-m", "pytest", "-q"]


class RecordingSandbox:
    """Runs on the host, but records what it was asked to do."""

    def __init__(self) -> None:
        self.commands: list[list[str]] = []
        self.killed: list[str] = []

    def command(self, args: list[str], root: Path, name: str) -> list[str]:
        self.commands.append(args)
        return args

    def kill(self, name: str) -> None:
        self.killed.append(name)


def test_run_tests_goes_through_the_sandbox(workspace: Workspace) -> None:
    sandbox = RecordingSandbox()
    box = ToolBox(workspace, sandbox=sandbox)
    result = box.execute(ToolCall("1", "run_tests", {"path": "tests"}))
    assert "exit code 1" in result.output
    # Paths are passed relative to the workspace, so they mean the same inside a container.
    assert sandbox.commands[0][-1] == "tests"
    assert sandbox.commands[0][:3] == ["python", "-m", "pytest"]


def test_timeout_kills_the_container(workspace: Workspace) -> None:
    (workspace.root / "tests" / "test_slow.py").write_text(
        "import time\n\ndef test_slow():\n    time.sleep(30)\n"
    )
    sandbox = RecordingSandbox()
    box = ToolBox(workspace, test_timeout=1.0, sandbox=sandbox)
    result = box.execute(ToolCall("1", "run_tests", {"path": "tests/test_slow.py"}))
    assert result.is_error and "timed out" in result.output
    assert len(sandbox.killed) == 1


def _docker_image_available() -> bool:
    image = os.environ.get("MINI_AGENT_SANDBOX_IMAGE")
    if not image or not shutil.which("docker"):
        return False
    inspect = subprocess.run(["docker", "image", "inspect", image], capture_output=True)
    return inspect.returncode == 0


@pytest.mark.skipif(not _docker_image_available(), reason="needs docker and a sandbox image")
def test_real_container_runs_the_suites(tmp_path: Path) -> None:
    sandbox = DockerSandbox(image=os.environ["MINI_AGENT_SANDBOX_IMAGE"])
    task = load_tasks(TASKS_DIR)[0]
    root = prepare_workspace(task, tmp_path)
    box = ToolBox(Workspace(root), sandbox=sandbox)
    assert "exit code 1" in box.execute(ToolCall("1", "run_tests", {})).output
    assert not run_suite(root, "hidden_tests", task, sandbox).passed
    (root / "tests" / "test_network.py").write_text(
        "import socket\n\nimport pytest\n\n\n"
        "def test_no_network():\n"
        "    with pytest.raises(OSError):\n"
        "        socket.create_connection(('1.1.1.1', 53), timeout=2)\n"
    )
    isolated = box.execute(ToolCall("2", "run_tests", {"path": "tests/test_network.py"}))
    assert "exit code 0" in isolated.output, isolated.output
