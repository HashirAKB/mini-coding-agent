# Summary

## What was built

- A coding agent written from scratch in Python 3.11+: a hand-written loop
  (model call, tool calls, observations, repeat) with six stop conditions
  (finished, gave up, no tool call, max steps, token budget, provider error).
- Six tools confined to a temporary working copy: `list_dir`, `read_file`
  (line ranges, paging), `search` (regex, capped), `apply_patch` (own unified
  diff applier, all or nothing, model-facing errors), `run_tests` (pytest with a
  timeout) and `finish`. Path traversal via `..`, absolute paths, `~` and
  symlinks is blocked and tested.
- Context management: chars/4 token estimates per request, head-and-tail
  truncation of large outputs with a re-read hint, and keep-tail summarisation
  of old turns near the limit (thinking blocks dropped from retained turns).
- A provider interface with three implementations: a scripted oracle with
  injected faults, a replay provider for recorded trajectories, and a live
  provider using the official Anthropic SDK.
- A benchmark of 20 small buggy Python packages (off-by-one, edge cases, bad
  regex, mutable default argument, two async bugs, aliasing, closures, floating
  point and more), each with visible tests, hidden tests kept outside the
  agent's workspace, and a reference patch.
- A harness that runs each task in isolation, records JSONL trajectories,
  restores visible tests and adds hidden ones before scoring, reports pass@1,
  average steps, tokens, cost and wall time per strategy, and labels every
  failure (provider error, budget exceeded, broken patch, gave up, wrong file,
  test overfit, incorrect fix).
- A direct vs plan-then-act strategy comparison, a static HTML trajectory
  viewer, a CLI, over 100 tests, CI (lint, typecheck, tests, mock benchmark with a
  pass-rate gate) and a Dockerfile.

## What is mocked and what is real

| part | status |
|---|---|
| Agent loop, tools, patch applier, context management | real, fully tested |
| Benchmark tasks, isolation, hidden-test scoring, taxonomy, metrics | real, fully tested |
| Model in tests, CI, demo and committed results | **mock** (scripted oracle that is given the reference fix) |
| Token counts and cost in committed results | **estimated** (chars/4, priced at `claude-opus-5-5` rates) |
| Live Claude provider | real code, tested only against a fake client; never called against the real API here |
| Live benchmark results | **not produced** (no API access in the build environment) |

The committed 75% pass@1 is fixed by construction. It proves the harness works
and nothing about the agent's ability.

## Known gaps

- No live run yet, so the strategy comparison has no real numbers.
- The live request shape (adaptive thinking, effort, server-side fallback beta
  header) is unverified against the real API.
- `run_tests` runs agent-written code on the host unless you use Docker.
- Tasks are small and mostly single-file; pass@1 from one sample is noisy.
- `wrong_file` assumes the reference fix's files are the only correct ones.
- Tasks run sequentially.

## Resume bullets (honest)

- Built a coding agent from scratch in Python (no agent frameworks) with a
  provider-agnostic tool-calling loop, sandboxed file and test tools, a custom
  unified diff applier with model-facing errors, and context management
  (output truncation and history summarisation), covered by over 100 tests.
- Designed a SWE-bench-style evaluation harness over 20 buggy Python packages
  with hidden tests to detect overfitting, per-task isolation, JSONL
  trajectories, pass@1, token and cost metrics, and a seven-way failure taxonomy.
- Made the whole system run offline and deterministically with a scripted mock
  model and trajectory replay, and wired the mock benchmark into GitHub Actions
  CI as a regression gate.
- Built a static HTML trajectory viewer and documented the design in ADRs and a
  study guide, including how history editing interacts with thinking-block
  replay on current Claude models.
