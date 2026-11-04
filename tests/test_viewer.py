import json
from pathlib import Path

from mini_agent.viewer import render_diff, render_run, render_trajectory

EVENTS = [
    {
        "type": "run_start",
        "provider": "mock",
        "model": "m",
        "task": "Fix <b>it</b>",
        "config": {"strategy": "direct"},
        "system": "s",
    },
    {
        "type": "step",
        "step": 1,
        "text": "Looking",
        "context_tokens_estimate": 10,
        "tool_calls": [
            {
                "id": "a",
                "name": "apply_patch",
                "args": {"patch": "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n"},
            }
        ],
        "observations": [{"call_id": "a", "output": "<script>alert(1)</script>", "is_error": True}],
        "usage": {"input_tokens": 5, "output_tokens": 1},
        "model_stop_reason": "tool_use",
        "raw": None,
    },
    {"type": "context_summarised", "step": 2, "tokens_before": 900, "tokens_after": 300},
    {
        "type": "run_end",
        "stop_reason": "finished",
        "steps": 1,
        "usage": {"input_tokens": 5, "output_tokens": 1},
        "finish_status": "done",
        "finish_summary": "",
    },
    {
        "type": "evaluation",
        "task_id": "t1",
        "strategy": "direct",
        "visible_passed": True,
        "hidden_passed": False,
        "failure": "test_overfit",
        "final_diff": "+added\n",
        "visible_output": "",
        "hidden_output": "1 failed",
    },
]


def test_trajectory_page_shows_each_part_and_escapes_html() -> None:
    page = render_trajectory(EVENTS)
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page
    assert "Fix &lt;b&gt;it&lt;/b&gt;" in page
    assert "Step 1" in page and "apply_patch" in page
    assert 'class="obs error"' in page
    assert "900" in page and "300" in page  # summarisation marker
    assert "test_overfit" in page


def test_diff_lines_are_classified() -> None:
    html = render_diff("--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n same\n")
    assert '<span class="del">-old</span>' in html
    assert '<span class="add">+new</span>' in html
    assert '<span class="hunk">@@ -1 +1 @@</span>' in html


def test_render_run_writes_index_and_pages(tmp_path: Path) -> None:
    trajectories = tmp_path / "trajectories" / "direct"
    trajectories.mkdir(parents=True)
    (trajectories / "t1.jsonl").write_text("\n".join(json.dumps(e) for e in EVENTS) + "\n")
    index = render_run(tmp_path)
    assert index == tmp_path / "viewer" / "index.html"
    text = index.read_text()
    assert 'href="direct/t1.html"' in text and "test_overfit" in text
    assert (tmp_path / "viewer" / "direct" / "t1.html").is_file()
