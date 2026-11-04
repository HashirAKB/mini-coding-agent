# Learning guide

This guide teaches the concepts behind this repo from first principles, gives a
reading order through the code, traces one task end to end, and ends with
interview questions and hands-on exercises. Every claim points at a file you can
open.

---

## Part 1. Concepts from first principles

### 1.1 What an "agent" is here

A language model on its own maps text to text. It cannot read your files or
run your tests. An **agent** is a program that puts the model in a loop with
**tools**:

1. Send the model the goal and everything that has happened so far.
2. The model answers with some text (its "thought") and, optionally, requests
   to call tools with arguments.
3. The program runs those tools and collects their outputs ("observations").
4. The program appends the model's turn and the observations to the history
   and goes back to step 1.

That is the whole idea. The model decides *what* to do; the program decides
*whether it is allowed*, *does it*, and *when to stop*. See the docstring at
the top of `src/mini_agent/agent.py`.

The model has no memory between calls. "Memory" is just the history the
program re-sends on every call, which is why context management matters.

### 1.2 Tool calling

A tool is described to the model by a **name**, a **description** and a
**JSON schema** for its arguments (`TOOL_SPECS` in `tools.py`). The model does
not run anything. It emits a structured request such as
`{"name": "read_file", "input": {"path": "calc.py"}}` with an id. The program:

- **validates** the arguments (the model can and will send wrong ones;
  `validate_args` in `tools.py`),
- **executes** the tool in a constrained environment (`Workspace.resolve`
  rejects any path outside the working copy),
- returns a **tool result** tied to the same id, flagged `is_error` if it
  failed.

Two design rules make tools model-friendly:

- **Errors are observations, not exceptions.** `ToolBox.execute` never raises.
  A rejected patch comes back as text the model can read and act on. That is
  what makes self-correction possible.
- **Outputs are bounded.** `read_file` pages long files, `search` caps
  matches, and the loop truncates anything longer than
  `max_observation_chars`. An unbounded tool can blow the context in one call.

On the wire (Anthropic Messages API, `providers/anthropic.py`) the assistant
turn contains `tool_use` blocks and the next user message contains the
matching `tool_result` blocks, all results of one turn in a single message.

### 1.3 Context windows

The model can only read a fixed number of tokens per request (its context
window), and you pay for every input token on every call. Because the full
history is re-sent each step, cost grows roughly with the square of the number
of steps: step *n* re-sends the *n - 1* turns before it.

This repo manages context at two levels (`context.py`):

- **Per observation: truncation.** Keep the head and tail of a long output
  (headers and the final test summary are usually the useful parts) and insert
  a marker saying how much was cut and how to get it back ("use read_file with
  start_line"). The marker matters: silently cut output misleads the model.
- **Per request: summarisation.** When the estimated request size passes 75%
  of the budget, old turns are replaced by a one-line-per-tool-call digest,
  appended to the task message (`split_history`, `extractive_summary`,
  `rebuild_history`). With `--summariser model` the agent instead asks the
  model for the summary in a separate request and falls back to the digest if
  that fails. The last few turns are kept verbatim because
  the agent usually needs the exact text of what it just read.

Token counting is estimated as characters / 4 (`estimate_tokens`). It is
offline and deterministic; real counts come back from the API in live mode.

A subtle constraint on current Claude models: each **thinking block** is bound
to the exact history before it. If you edit history and re-send an old
thinking block, the API rejects the request. So the summariser drops thinking
blocks from the turns it keeps (`_without_thinking`), and the system prompt and
tool list never change during a run. Conversations are otherwise
**append-only**.

### 1.4 Stop conditions

An agent loop must always terminate. This one stops when
(`Agent._loop` in `agent.py`):

| stop reason | trigger | why it exists |
|---|---|---|
| `finished` | model calls `finish(status="done")` | explicit success signal |
| `gave_up` | model calls `finish(status="give_up")` | honest failure is better than flailing |
| `no_tool_call` | a reply with no tool call (except the plan turn) | the model thinks it is done talking |
| `max_steps` | step counter reaches the limit | bounds time and loops |
| `token_budget` | summed tokens reach the budget | bounds money |
| `provider_error` | the model call raised (network, API error) | one bad call ends one run, not the benchmark |

Note the order inside the loop: the budget is checked *before* each model call,
so a run never starts a call it cannot afford. `finish` is an explicit tool
rather than "stop when the model stops calling tools" because an explicit
status lets the harness tell "done" from "gave up".

### 1.5 Evaluation design

A benchmark answers "how often does the agent solve the task, and why does it
fail when it does?" Pitfalls this harness guards against (`bench.py`,
`tasks.py`):

- **Leakage / cheating.** Hidden tests are never in the agent's workspace. The
  visible tests are restored from the original before scoring, so editing them
  cannot fake a pass.
- **Overfitting.** A fix that special-cases the visible inputs passes the
  visible tests and fails the hidden ones; that is reported as `test_overfit`.
  Task `04_email_regex` ships an `overfit.patch` that proves the detector works.
- **Broken benchmark.** `tests/test_bench_tasks.py` checks that every task
  fails before and passes after its reference fix. A task that cannot be
  solved, or is solved by the buggy code, would silently distort pass@1.
- **Isolation.** Each run gets a fresh temp copy, so runs cannot affect each
  other.
- **Explaining failures.** `classify_failure` assigns exactly one label using
  ordered rules over facts the harness observes (the workspace diff, rejected
  patches, the stop reason), not the agent's own claims.
- **Metrics.** pass@1 (share of tasks solved on the single attempt), average
  steps, tokens, cost and wall time, per strategy. With `--samples n`, pass@k
  uses the unbiased estimator `1 - C(n-c, k) / C(n, k)` per task (`bench.pass_at_k`):
  the chance that k samples drawn from the n you ran include at least one pass.
  One sample per task is noisy for a stochastic model; several samples let you
  separate "can it ever solve this" (pass@k) from "does it usually" (pass@1).
- **Honesty about the mock.** The mock provider is handed the answer, so its
  75% is a property of the script. It proves the plumbing, not ability.

---

## Part 2. File reading order

Read in this order; each file builds on the previous ones.

| # | file | what it teaches |
|---|---|---|
| 1 | `src/mini_agent/types.py` | The neutral data model: `Message`, `ToolCall`, `ToolResult`, `ModelResponse`, `Usage`. Why `raw` exists. |
| 2 | `src/mini_agent/workspace.py` | Path confinement in 10 lines: resolve, then `is_relative_to`. Why resolving first defeats `..` and symlinks. |
| 3 | `src/mini_agent/patch.py` | The unified diff format, tolerant parsing, exact matching, all-or-nothing writes, model-facing error messages. |
| 4 | `src/mini_agent/tools.py` | Tool schemas, argument validation, bounded outputs, subprocess timeouts, errors as observations. |
| 5 | `src/mini_agent/prompts.py` | The two strategies and why the system prompt never changes mid-run. |
| 6 | `src/mini_agent/providers/base.py` | The one-method `Provider` protocol. |
| 7 | `src/mini_agent/agent.py` | The loop, the stop conditions, where context management and truncation plug in. |
| 8 | `src/mini_agent/context.py` | Token estimates, truncation with a re-read pointer, summarisation invariants. |
| 9 | `src/mini_agent/providers/scripted.py` | A reactive policy written as a generator; fault injection. |
| 10 | `src/mini_agent/providers/replay.py` | Turning a recorded trajectory back into model turns. |
| 11 | `src/mini_agent/providers/anthropic.py` | Mapping to the Messages API: tool_use / tool_result blocks, replaying raw thinking blocks, usage with cache tokens. |
| 12 | `src/mini_agent/trajectory.py` | JSONL event log. |
| 13 | `src/mini_agent/tasks.py` | Task format, workspace preparation, running suites, hidden-test handling. |
| 14 | `src/mini_agent/bench.py` | The harness: isolation, workspace diff, taxonomy, metrics, reports. |
| 15 | `src/mini_agent/viewer.py` | Rendering untrusted text safely into HTML. |
| 16 | `src/mini_agent/cli.py` | How it is all wired together. |
| 17 | `tests/` | Start with `test_agent.py` (stop conditions) and `test_bench_tasks.py` (benchmark validity). |

---

## Part 3. One task traced end to end

Command: `python -m mini_agent demo --task 03` (task `03_median_even_length`,
mock provider, behaviour `broken_patch_then_recover`).

1. **CLI** (`cli.py: main`) loads all tasks with `load_tasks`, selects the one
   whose id starts with `03`, and calls `run_task(task, "mock", "direct", out,
   config)`.
2. **Provider** (`bench.py: make_provider`) looks up `MOCK_BEHAVIOURS` and
   builds `ScriptedProvider(solution_patch, "broken_patch_then_recover")`. The
   provider parses the patch to learn which file to read
   (`numstats/central.py`).
3. **Isolation** (`tasks.py: prepare_workspace`) copies `bench/tasks/03.../repo`
   into a fresh temp dir. The `hidden/` folder is not copied.
4. **Recording**: a `TrajectoryWriter` opens
   `trajectories/direct/03_median_even_length.jsonl`. The agent writes
   `run_start` with the provider, model, config, system prompt and task text.
5. **Step 1** (`agent.py: _loop`): budget check passes;
   `_manage_context` estimates about 675 tokens (well under 75% of 100,000, so
   no summary); `provider.complete` returns "Let me see what is in the
   repository." with a `list_dir(".")` call. `ToolBox.execute` validates the
   args, `Workspace.resolve(".")` is inside the root, the output is
   `numstats/` and `tests/`. The step is recorded; the assistant turn and the
   tool result are appended.
6. **Step 2**: `read_file("numstats/central.py")` returns the 4 numbered lines,
   showing `return ordered[len(ordered) // 2]`.
7. **Step 3**: `run_tests()` runs `python -m pytest -q` in the workspace with a
   timeout and returns `exit code 1` and the assertion `assert 3 == 2.5`. A
   failing test is a normal observation, not an error.
8. **Step 4**: the policy sends a deliberately corrupted patch (its removed line
   has `  # stale` appended). `patch.apply_patch` parses it, `_find_hunk` finds
   no match even ignoring trailing whitespace, and `PatchError` is raised
   before anything is written. `ToolBox.apply_patch` prefixes "Patch rejected,
   no files were changed." and `execute` returns it with `is_error=True`.
9. **Step 5**: the policy's generator resumes, sees the error in
   `self.last_results`, and re-reads the file. This is the self-correction
   path a real model takes.
10. **Step 6**: the correct patch applies: `modified numstats/central.py (+4 -1)`.
11. **Step 7**: `run_tests()` returns `exit code 0`.
12. **Step 8**: `finish(status="done")`. The loop sees a successful `finish`
    and returns `AgentResult(stop_reason="finished", steps=8, ...)`; `run_end`
    is recorded.
13. **Scoring** (`bench.py: run_task`): `workspace_diff` compares the temp dir
    with the original repo and finds `numstats/central.py` changed. `run_suite`
    restores `tests/` from the original and runs it (pass), then copies
    `hidden/` in as `hidden_tests/` and runs it (pass). `count_failed_patches`
    reads the trajectory and finds 1 rejected patch, but `classify_failure`
    returns `None` because both suites passed. An `evaluation` event with the
    final diff is appended.
14. **Output**: the CLI prints the trajectory with `format_trajectory`. `python
    -m mini_agent view <dir>` turns the same JSONL into HTML.

---

## Part 4. Interview questions with model answers

**1. Walk me through your agent loop.**
`agent.py: _loop`. Each step: check the token budget, estimate the request size
and summarise old turns if it is above 75% of the limit, call the provider with
the fixed system prompt, the history and the tool specs, append the assistant
turn, run each tool call through `ToolBox.execute`, truncate each output, record
the step to JSONL, and stop on `finish`. A reply with no tool call stops the run
(except the plan turn in the plan strategy). After `max_steps` it stops with
`max_steps`; if the provider raises, it stops with `provider_error`.

**2. How do you stop an agent from touching files outside its sandbox?**
Every path goes through `Workspace.resolve`: join with the root, call
`Path.resolve()` (collapses `..`, follows symlinks), then require
`is_relative_to(root)`. Checking the resolved path is the key point; string
checks for `..` miss symlinks. Tests cover `..`, absolute paths, `~` and a
symlink pointing outside. I'm explicit that this only protects the file tools:
`run_tests` executes model-written code, so real isolation is the Docker image.

**3. What happens when the model sends a bad patch?**
`patch.py` computes every change in memory first, so a failing hunk writes
nothing. The error names the file and hunk, shows the lines it expected, and
tells the model to re-read with `read_file`. `ToolBox.execute` returns it as a
`ToolResult` with `is_error=True` instead of raising, so the model sees it next
turn. The `broken_patch_then_recover` test shows the loop recovering.

**4. Why write your own diff applier?**
Three reasons: model-facing error messages, tolerance where models are sloppy
(wrong `@@` counts, trailing whitespace) but strictness where it matters (the
content must match), and atomic application across files. It is tested against
all 20 reference solutions.

**5. How do you manage the context window?**
Two levels in `context.py`. Each observation is capped by `truncate_output`
(head and tail plus a marker with a re-read hint). The whole request is
estimated with chars/4; above 75% of the budget, `summarise_history` replaces
old turns with a one-line-per-call digest appended to the task, keeping the
last 4 assistant turns verbatim. It cuts only at turn boundaries so tool_use and
tool_result stay paired.

**6. Why drop thinking blocks when you summarise?**
On current Claude models a thinking block is bound to the history before it.
After summarising, that history changed, and replaying the block is rejected.
Text and tool calls are kept, so the visible record survives. Outside of
summarisation the conversation is append-only and raw blocks are sent back
unchanged via `Message.raw`.

**7. How do you know the benchmark itself is correct?**
`tests/test_bench_tasks.py` runs every task: visible and hidden tests must fail
on the buggy code and pass after `solution.patch`, applied with the agent's own
patch tool. The overfit patch must pass visible and fail hidden tests.

**8. How do you detect overfitting and test tampering?**
Hidden tests live outside the workspace and are copied in only for scoring.
Visible tests are restored from the original before scoring. Visible pass with
hidden fail is labelled `test_overfit`.

**9. Explain your failure taxonomy.**
`classify_failure`, ordered rules: passed; provider error (an infrastructure
failure, never blamed on the agent); budget stop; nothing changed (broken
patch if any patch was rejected, otherwise gave up); changed files don't
overlap the reference fix (wrong file); visible pass but hidden fail (overfit);
otherwise incorrect fix. One label per failure, computed from the workspace diff
and trajectory, not from what the agent says.

**10. Your mock gets 75%. What does that tell you?**
Only that the harness works. The scripted provider is handed the reference fix
and fails on purpose on 7 tasks to exercise every category. CI asserts 75%, so
a drop means a harness regression. Model ability needs live runs.

**11. Why a provider interface instead of calling the SDK directly?**
It keeps the loop testable offline and vendor-neutral. The interface is one
method. Mock, replay and live providers all fit; the live one is the only file
that imports the SDK, and it imports it lazily.

**12. What does the replay provider give you?**
Determinism for real runs. A recorded live trajectory can be replayed through
the current harness offline, for debugging or as a regression test after tool
or evaluation changes, at zero cost.

**13. Direct vs plan-then-act: how is it implemented and what would you expect?**
`prompts.py`: the plan strategy adds an instruction to reply with a numbered
plan before the first tool call; the loop treats that first no-tool reply as
the plan and appends "now carry it out". One system prompt and tool list for
the whole run keeps it append-only. Expect a small token overhead; any accuracy
benefit has to be measured live, and on 20 easy tasks the difference may be
noise.

**14. Why is cost quadratic in steps, and what would you do about it?**
Each call re-sends the whole history, so total input tokens is the sum over
steps of the history length. Mitigations: truncation and summarisation, prompt
caching of the append-only prefix (`cache_control` in `providers/anthropic.py`,
cache reads billed at 0.05x input), and fewer steps via better
tools (for example `read_file` returning only the needed range).

**15. What are the weaknesses of this benchmark?**
20 small single-bug tasks, mostly single-file; `wrong_file` assumes the
reference fix's files are the only right ones; pass@1 on one sample has high
variance; mock mode measures nothing about ability; no live results committed.

---

## Part 5. Hands-on exercises

**Exercise 1. Add a cost budget stop condition.**
Stop the run when the estimated USD cost passes `max_cost_usd`.
*Hints:* `AgentConfig` in `agent.py`; the token budget check at the top of
`_loop` is the pattern; `bench.cost_usd` already prices tokens (consider moving
it so `agent.py` does not import `bench.py`). Test it like
`test_stop_when_token_budget_is_exhausted`.

**Exercise 2. Add a `write_file` tool and compare it with `apply_patch`.**
*Hints:* add a `ToolSpec` and handler in `tools.py`, resolve the path through
`Workspace`, update `test_every_spec_has_a_json_schema`. Then think about why
whole-file writes are risky for large files and what that does to tokens.

**Exercise 3. Add a new benchmark task.**
Pick a bug (for example an off-by-one in `str.split` with `maxsplit`). Create
`bench/tasks/21_.../` with `task.json`, `repo/<pkg>/`, `repo/tests/`, `hidden/`
and a `solution.patch` made with `diff -u` (paths `a/<pkg>/x.py`,
`b/<pkg>/x.py`).
*Hints:* `tests/test_bench_tasks.py` will validate it; update the "20 tasks"
assertion and the CI pass-rate threshold.

**Exercise 4. Make summarisation smarter.**
Keep the full text of the most recent `read_file` output for each file even
when its turn is summarised.
*Hints:* `summarise_history` in `context.py`; keep the invariants tested in
`tests/test_context.py` (task first, alternation, pairing, no thinking blocks).

**Exercise 5. Add a new failure category.**
Label runs that edited test files as `edited_tests`.
*Hints:* `workspace_diff` already returns changed paths; add the rule in
`classify_failure` at the right position (think about which label should win),
add it to `FAILURE_CATEGORIES`, and add a row to `test_failure_taxonomy`.
