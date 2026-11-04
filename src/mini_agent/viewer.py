"""Static HTML trajectory viewer.

    python -m mini_agent view bench/results/mock      # writes bench/results/mock/viewer/

Pages are plain HTML and CSS with no JavaScript, generated from the JSONL
trajectories, so they open straight from disk. Every value from a trajectory is
escaped: tool outputs can contain anything, including HTML.
"""

from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any

from mini_agent.trajectory import read_trajectory

STYLE = """
:root { --bg:#ffffff; --fg:#1b1f24; --muted:#59636e; --card:#f6f8fa; --border:#d1d9e0;
  --add:#1a7f37; --add-bg:#dafbe1; --del:#cf222e; --del-bg:#ffebe9; --hunk:#8250df;
  --error:#cf222e; --ok:#1a7f37; }
@media (prefers-color-scheme: dark) { :root { --bg:#0d1117; --fg:#e6edf3; --muted:#9198a1;
  --card:#151b23; --border:#3d444d; --add:#3fb950; --add-bg:#12261e; --del:#f85149;
  --del-bg:#2d1214; --hunk:#ab7df8; --error:#f85149; --ok:#3fb950; } }
* { box-sizing: border-box; }
body { margin:0 auto; max-width:960px; padding:16px; background:var(--bg); color:var(--fg);
  font:15px/1.5 system-ui, sans-serif; }
h1 { font-size:1.4rem; } h2 { font-size:1.1rem; margin-top:2rem; }
.step h2 { margin-top:0; }
pre { background:var(--card); border:1px solid var(--border); border-radius:6px; padding:10px;
  overflow-x:auto; font:13px/1.45 ui-monospace, monospace; white-space:pre; }
.step { border:1px solid var(--border); border-radius:8px; padding:12px; margin:12px 0; }
.meta { color:var(--muted); font-size:0.85rem; }
.thought { font-style:italic; }
.obs.error { border-color:var(--error); }
.badge { display:inline-block; padding:1px 8px; border-radius:10px; font-size:0.8rem;
  border:1px solid currentColor; }
.pass { color:var(--ok); } .fail { color:var(--error); }
.add { color:var(--add); background:var(--add-bg); display:block; }
.del { color:var(--del); background:var(--del-bg); display:block; }
.hunk { color:var(--hunk); display:block; }
.note { border-left:3px solid var(--hunk); padding:4px 10px; color:var(--muted); }
table { border-collapse:collapse; width:100%; font-size:0.9rem; }
th, td { border-bottom:1px solid var(--border); padding:6px; text-align:left; }
.table-wrap { overflow-x:auto; }
a { color:var(--hunk); }
"""


def _page(title: str, body: str) -> str:
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{escape(title)}</title><style>{STYLE}</style></head>"
        f"<body>{body}</body></html>\n"
    )


def render_diff(diff: str) -> str:
    lines = []
    for line in diff.splitlines():
        if line.startswith(("+++", "---")):
            lines.append(f"<strong>{escape(line)}</strong>")
        elif line.startswith("@@"):
            lines.append(f'<span class="hunk">{escape(line)}</span>')
        elif line.startswith("+"):
            lines.append(f'<span class="add">{escape(line)}</span>')
        elif line.startswith("-"):
            lines.append(f'<span class="del">{escape(line)}</span>')
        else:
            lines.append(escape(line))
    return "<pre>" + "\n".join(lines) + "</pre>"


def _verdict(failure: str | None) -> str:
    if failure is None:
        return '<span class="badge pass">pass</span>'
    return f'<span class="badge fail">fail: {escape(failure)}</span>'


def _render_step(event: dict[str, Any]) -> str:
    usage = event["usage"]
    parts = [
        f"<section class='step'><h2>Step {event['step']}</h2>",
        f"<p class='meta'>context estimate {event['context_tokens_estimate']:,} tokens; "
        f"usage in/out {usage['input_tokens']:,}/{usage['output_tokens']:,}</p>",
    ]
    if event["text"]:
        parts.append(f"<p class='thought'>{escape(event['text'])}</p>")
    observations = {o["call_id"]: o for o in event["observations"]}
    for call in event["tool_calls"]:
        args = {k: v for k, v in call["args"].items() if k != "patch"}
        parts.append(f"<p><strong>{escape(call['name'])}</strong> {escape(json.dumps(args))}</p>")
        if call["name"] == "apply_patch" and "patch" in call["args"]:
            parts.append(render_diff(call["args"]["patch"]))
        observation = observations.get(call["id"])
        if observation is not None:
            css = "obs error" if observation["is_error"] else "obs"
            parts.append(f'<pre class="{css}">{escape(observation["output"])}</pre>')
    parts.append("</section>")
    return "".join(parts)


def render_trajectory(events: list[dict[str, Any]]) -> str:
    title = "Trajectory"
    body: list[str] = []
    for event in events:
        kind = event["type"]
        if kind == "run_start":
            strategy = event["config"]["strategy"]
            body.append(
                f"<p class='meta'>provider {escape(event['provider'])}, model "
                f"{escape(event['model'])}, strategy {escape(strategy)}</p>"
                f"<h2>Task</h2><pre>{escape(event['task'])}</pre>"
            )
        elif kind == "step":
            body.append(_render_step(event))
        elif kind == "context_summarised":
            body.append(
                f"<p class='note'>Before step {event['step']}: history summarised "
                f"({escape(event.get('summariser', 'extractive'))}), "
                f"{event['tokens_before']:,} to {event['tokens_after']:,} estimated tokens.</p>"
            )
            if event.get("summary"):
                body.append(f"<pre>{escape(event['summary'])}</pre>")
        elif kind == "run_end":
            body.append(
                f"<h2>Stop</h2><p>{escape(event['stop_reason'])} after {event['steps']} steps "
                f"({escape(str(event['finish_status']))})</p>"
            )
        elif kind == "evaluation":
            title = f"{event['task_id']} ({event['strategy']})"
            body.append(
                f"<h2>Evaluation {_verdict(event['failure'])}</h2>"
                f"<p>visible tests: {'pass' if event['visible_passed'] else 'fail'}, "
                f"hidden tests: {'pass' if event['hidden_passed'] else 'fail'}</p>"
                "<h2>Final diff</h2>"
                + (render_diff(event["final_diff"]) if event["final_diff"] else "<p>(none)</p>")
                + f"<h2>Hidden test output</h2><pre>{escape(event['hidden_output'])}</pre>"
            )
    return _page(title, f"<h1>{escape(title)}</h1>" + "".join(body))


def render_run(run_dir: Path) -> Path:
    """Write viewer/index.html plus one page per trajectory. Returns the index path."""
    out = run_dir / "viewer"
    rows = []
    for path in sorted((run_dir / "trajectories").glob("*/*.jsonl")):
        strategy, task_id = path.parent.name, path.stem
        events = read_trajectory(path)
        page = out / strategy / f"{task_id}.html"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(render_trajectory(events))
        evaluation = next((e for e in events if e["type"] == "evaluation"), None)
        end = next((e for e in events if e["type"] == "run_end"), {})
        verdict = _verdict(evaluation["failure"]) if evaluation else "(not evaluated)"
        rows.append(
            f'<tr><td><a href="{escape(strategy)}/{escape(task_id)}.html">{escape(task_id)}</a>'
            f"</td><td>{escape(strategy)}</td><td>{verdict}</td>"
            f"<td>{escape(str(end.get('stop_reason', '')))}</td>"
            f"<td>{end.get('steps', '')}</td></tr>"
        )
    table = (
        "<div class='table-wrap'><table><tr><th>task</th><th>strategy</th><th>result</th>"
        "<th>stop reason</th><th>steps</th></tr>" + "".join(rows) + "</table></div>"
    )
    banner = ""
    results = run_dir / "results.json"
    if results.is_file() and json.loads(results.read_text())["mode"] == "mock":
        banner = (
            "<p class='note'>Mock mode: scripted oracle with injected faults. These runs "
            "prove the harness works, not the agent's ability.</p>"
        )
    index = out / "index.html"
    index.write_text(_page("Benchmark runs", f"<h1>Benchmark runs</h1>{banner}{table}"))
    return index
