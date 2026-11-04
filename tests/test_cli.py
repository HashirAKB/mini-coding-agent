from pathlib import Path

import pytest

from mini_agent.cli import main


def test_demo_prints_a_trajectory(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["demo", "--out", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "[step 1]" in out and "-> apply_patch" in out
    assert "evaluation: visible tests pass, hidden tests pass -> PASS" in out


def test_bench_enforces_min_pass_rate(tmp_path: Path) -> None:
    args = ["bench", "--tasks", "13_roman", "--strategy", "direct", "--out", str(tmp_path)]
    assert main([*args, "--min-pass-rate", "0.5"]) == 1  # this task gives up in mock mode
    assert main(args) == 0


def test_anthropic_provider_requires_a_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="ANTHROPIC_API_KEY"):
        main(["run", "--provider", "anthropic", "--out", str(tmp_path)])


def test_replay_provider_reproduces_a_recorded_bench(tmp_path: Path) -> None:
    recorded = tmp_path / "recorded"
    replayed = tmp_path / "replayed"
    common = ["bench", "--tasks", "01_,03_", "--strategy", "direct"]
    assert main([*common, "--out", str(recorded)]) == 0
    assert (
        main(
            [
                *common,
                "--provider",
                "replay",
                "--replay-dir",
                str(recorded / "trajectories"),
                "--out",
                str(replayed),
            ]
        )
        == 0
    )
    report = (replayed / "results.md").read_text()
    assert "REPLAY MODE" in report and "2/2" in report


def test_view_renders_a_run(tmp_path: Path) -> None:
    assert main(["bench", "--tasks", "01_", "--strategy", "direct", "--out", str(tmp_path)]) == 0
    assert main(["view", str(tmp_path)]) == 0
    assert (tmp_path / "viewer" / "direct" / "01_pagination_off_by_one.html").is_file()
    jsonl = tmp_path / "trajectories" / "direct" / "01_pagination_off_by_one.jsonl"
    assert main(["view", str(jsonl)]) == 0
    assert jsonl.with_suffix(".html").is_file()
