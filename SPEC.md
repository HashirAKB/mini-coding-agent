# SPEC: Mini Coding Agent + Benchmark

## Goal

Build a small coding agent from scratch in Python (no agent frameworks) and a
SWE-bench-style harness that measures it. The code is meant to be read and
studied: every component is small enough to understand in one sitting.

## Scope

1. **Agent loop**: call the model, parse tool calls, execute them, append the
   observations, repeat until the model calls `finish`, the step limit is hit,
   or the token budget is exhausted.
2. **Tools** (all confined to a temporary working copy of the task repo):
   `list_dir`, `read_file` (line ranges), `search` (regex), `apply_patch`
   (unified diff, validated, clear errors back to the model), `run_tests`
   (pytest with a timeout), `finish`.
3. **Sandboxing of file access**: every path is resolved and must stay inside
   the workspace root; `..`, absolute paths and symlinks pointing outside are
   rejected. Subprocesses have timeouts.
4. **Context management**: token estimate per turn, truncation of large tool
   outputs with a pointer telling the model how to re-read, and summarisation
   of old turns when the conversation nears the context limit.
5. **Providers**: one `Provider` interface.
   - `ScriptedProvider` (mock): a deterministic policy that plays the agent's
     role using the task's reference solution plus injected faults. It reacts
     to observations, so it really exercises the loop, tools and harness.
   - `ReplayProvider` (mock): replays the model responses stored in a recorded
     trajectory JSONL file.
   - `AnthropicProvider` (live): used only when `ANTHROPIC_API_KEY` is set.
6. **Benchmark**: 20 small, self-contained buggy Python packages. Each has a
   task description, visible failing tests, hidden tests kept outside the
   agent's workspace, and a reference `solution.patch`.
7. **Harness**: runs each task in an isolated temp copy; writes one JSONL
   trajectory per task; computes pass@1, average steps, tokens, cost and wall
   time; classifies failures (wrong file, broken patch, gave up, test overfit,
   budget exceeded, incorrect fix).
8. **Strategies**: `direct` vs `plan` (plan-then-act). Meaningful only in live
   mode; in mock mode we only prove the comparison runs end to end.
9. **Trajectory viewer**: static HTML rendering of a run, step by step
   (thought, tool call, observation, diff).

## Non-goals

- Competing with real SWE-bench agents or running real SWE-bench tasks.
- Security-grade sandboxing. `run_tests` executes code the agent wrote; the
  path checks protect the host filesystem from the *file tools*, not from
  arbitrary code. Real isolation comes from running the harness in Docker.
- Multi-language repos, a shell tool, parallel task execution, a web server
  for the viewer, streaming output.

## Honesty rule for numbers

**Mock-mode benchmark numbers only prove that the harness works.** The scripted
policy has access to the reference solution and its failures are injected on
purpose so that every failure category is exercised. They say nothing about
the agent's real ability. Every results table in this repo is labelled
`mock` or `live`.

## Architecture

```
src/mini_agent/
  types.py        Message, ToolCall, ToolResult, ModelResponse, Usage
  workspace.py    Workspace: path confinement (resolve + is_relative_to)
  patch.py        Unified diff parser and all-or-nothing applier
  tools.py        Tool specs (JSON schema) + implementations + dispatcher
  sandbox.py      Runs pytest on the host or in a no-network Docker container
  context.py      Token estimate, output truncation, history summarisation
  prompts.py      System prompts for the direct and plan strategies
  agent.py        The agent loop and stop conditions
  providers/
    base.py       Provider protocol
    scripted.py   ScriptedProvider (mock policy with fault injection)
    replay.py     ReplayProvider (replays a recorded trajectory)
    anthropic.py  AnthropicProvider (official SDK, lazy import)
  trajectory.py   JSONL trajectory writer/reader
  tasks.py        Task loading, workspace preparation, running test suites
  bench.py        Isolated runs, hidden-test evaluation, metrics,
                  failure taxonomy, results writing
  viewer.py       Static HTML trajectory viewer
  cli.py          `python -m mini_agent demo | run | bench | view`
bench/tasks/<id>/ task.json, repo/ (package + visible tests),
                  hidden/ (hidden tests), solution.patch
bench/results/    committed mock results (JSON, Markdown, JSONL, HTML)
tests/            unit + integration tests
docs/adr/         architecture decision records
```

Agent loop (one step): estimate tokens, summarise history if over the
threshold, call the provider, record the response, execute each tool call,
truncate each observation, append results, check stop conditions.

Evaluation: after the agent stops, the harness restores the original visible
tests (so editing tests cannot fake a pass), copies in the hidden tests, and
runs both suites in the workspace.

## Tech choices

| Choice | Reason |
|---|---|
| Python 3.11+, stdlib first | Fewest moving parts; the agent itself needs no third-party runtime package. |
| pytest (runtime dependency) | The benchmark tasks and the `run_tests` tool are pytest suites. |
| Own unified diff applier | Teaches the format, gives model-friendly error messages, no reliance on a `patch` binary. |
| Anthropic official SDK, optional extra `[live]` | Live mode only; lazily imported so mock mode needs zero keys and zero network. |
| Default live model `claude-opus-5-5` | Current default Claude model; priced $4 / $20 per MTok for cost estimates. |
| Token estimate = chars / 4 | Offline and deterministic; live runs report real usage from the API. |
| Extractive (rule-based) summariser | Deterministic and testable offline; an LLM summariser is listed as future work. |
| JSONL trajectories | Append-only, streamable, one event per line, trivial to diff and replay. |
| Static HTML viewer, no JS framework | Opens from disk, no build step. |
| ruff + mypy + pytest | Standard, fast lint/typecheck/test for CI. |
| Docker image based on python:3.11-slim | Real isolation for running agent-written code. |

## Milestones

| # | Milestone | Verifiable success criterion |
|---|---|---|
| M0 | Scaffold: pyproject, package skeleton, CI workflow, Dockerfile, LICENSE, .env.example | `ruff check`, `ruff format --check`, `mypy src`, `pytest` all pass locally; CI file runs the same commands. |
| M1 | Workspace + tools + patch applier | Unit tests pass for every tool, including path traversal (`..`, absolute, symlink) rejection, malformed and non-matching patches, regex errors, and a `run_tests` timeout. |
| M2 | Providers + agent loop + stop conditions | Integration test: ScriptedProvider fixes a toy repo end to end; separate tests hit each stop condition (finish, no tool call, max steps, token budget); ReplayProvider reproduces a recorded run; AnthropicProvider request/response mapping tested with a fake client. |
| M3 | Context management | Unit tests for token estimate, truncation (with re-read pointer) and summarisation (keeps task, keeps recent turns, keeps role alternation, keeps tool call/result pairing); integration test shows summarisation triggering inside the loop. |
| M4 | 20 benchmark tasks | A test asserts, for every task: visible tests fail on the buggy repo, hidden tests fail on the buggy repo, and after applying `solution.patch` with our own applier both suites pass. |
| M5 | Harness, metrics, taxonomy, strategies | `python -m mini_agent bench` writes per-task JSONL, `results.json` and `results.md` for both strategies; a test covers every failure category; committed mock results exist. |
| M6 | Viewer, docs, final review | Viewer HTML generated for the committed run; README, LEARNING, ADRs, SUMMARY present; CI green; history check prints nothing. |

## Risks

| Risk | Mitigation |
|---|---|
| Mock numbers mistaken for real ability | Labelled everywhere; README and SUMMARY state it explicitly. |
| Patch applier bugs | Tested against all 20 reference solutions plus targeted unit tests. |
| Flaky or slow subprocess tests | Small tasks, timeouts, `-p no:cacheprovider`, no network in tests. |
| Live API shape drift | Live provider isolated in one file; mapping tested with a fake client; cannot be verified without a key (stated as a known gap). |
| Client-side summarisation vs thinking-block preservation on current Claude models | Raw assistant content (including thinking blocks) is replayed unchanged in append-only turns; when history is summarised, thinking blocks are dropped from the retained turns (the API allows this; replaying them after an edit is rejected). See ADR. |
| Agent-written code escaping the workspace | Documented non-goal; run the harness in Docker for real isolation. |

## Deviations

- **`bench.py` split in two.** Task loading and test-suite execution live in
  `tasks.py`; `bench.py` holds the harness (runs, metrics, taxonomy, reports).
  One module was getting long and mixed two concerns.
- **`replay` mode label.** Besides `mock` and `live`, results from
  `--provider replay` are labelled `replay`, since replayed turns are neither a
  new live run nor scripted.
- **Extra failure category `incorrect_fix`** (right file, tests still fail),
  so that every failed run gets exactly one label.
- **Extra stop reason and failure category `provider_error`.** Found in the
  review pass: an exception from the model call (network, rate limit, an
  exhausted replay) used to crash the whole benchmark. It now ends only that
  run and is reported separately, so infrastructure failures are never counted
  as agent failures.
- **Docker image not built in the build environment.** At first the local
  Docker daemon could pull no base image (Docker Hub answered `429 Too Many
  Requests`); later the pull worked, but `pip install` inside the build cannot
  verify this environment's TLS proxy. Per the offline rule no workaround was
  attempted in the Dockerfile; CI's `docker` job builds the image, runs a mock
  benchmark inside it and runs the sandbox tests against it. The sandbox itself
  was verified locally with a throwaway image built from pre-downloaded wheels.
