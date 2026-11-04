"""Shared fixtures: a tiny sample repo copied into a fresh temp directory."""

from pathlib import Path

import pytest

from mini_agent.workspace import Workspace

CALC_SOURCE = """\
def add(a, b):
    return a + b


def mean(values):
    return sum(values) / (len(values) - 1)
"""

CALC_TEST = """\
from calc import add, mean


def test_add():
    assert add(2, 3) == 5


def test_mean():
    assert mean([1, 2, 3]) == 2
"""

CALC_FIX = """\
--- a/calc.py
+++ b/calc.py
@@ -4,3 +4,3 @@


 def mean(values):
-    return sum(values) / (len(values) - 1)
+    return sum(values) / len(values)
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A two-file repo with an off-by-one bug in `mean`."""
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    (root / "calc.py").write_text(CALC_SOURCE)
    (root / "tests" / "test_calc.py").write_text(CALC_TEST)
    return root


@pytest.fixture
def workspace(repo: Path) -> Workspace:
    return Workspace(repo)
