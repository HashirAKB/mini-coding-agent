# Decisions log

Decisions taken without the owner available. Each entry: decision, alternatives
considered, why.

## D1. Push directly to `main`
- **Decision:** all work is committed and pushed to `main`.
- **Alternatives:** a feature branch plus pull requests.
- **Why:** explicit instruction from the project owner.

## D2. Hand-written agent loop instead of the SDK tool runner
- **Decision:** the loop in `agent.py` is written by hand; the Anthropic SDK is
  used only for a single `messages.create` call per step.
- **Alternatives:** the SDK's tool runner helper, or an agent framework.
- **Why:** the project exists to show how the loop works. A runner would hide
  the exact parts (stop conditions, context management, error feedback) that
  the project is meant to teach and measure.

## D3. `python -m` for every tool in Makefile and CI
- **Decision:** call `python -m pytest`, `python -m ruff`, `python -m mypy`.
- **Alternatives:** bare `pytest` / `ruff` / `mypy` executables.
- **Why:** in this environment a globally installed `pytest` lives in a
  separate virtualenv and cannot import the package. `python -m` always uses
  the interpreter the package was installed into.

## D4. The scripted mock is an oracle with injected faults
- **Decision:** `ScriptedProvider` is given the reference solution and plays
  one of seven fixed behaviours (solve, recover from a broken patch, broken
  patch, wrong file, give up, overfit, run out of budget).
- **Alternatives:** a heuristic "fake model" that tries to find bugs by itself;
  only replaying recorded live runs.
- **Why:** a heuristic agent would be a second, worse agent to maintain and its
  numbers would still be meaningless. Recorded live runs cannot exist without
  an API key. An oracle with faults exercises every code path and every
  failure category deterministically, and it is obviously not a measure of
  ability, which keeps the reporting honest.

## D5. Plan-then-act keeps one system prompt and one tool list
- **Decision:** the `plan` strategy uses its own system prompt from the first
  request on, and the planning turn is just the first turn (no tool call),
  followed by a short "now carry it out" user message.
- **Alternatives:** a separate planning call with no tools and a different
  system prompt, whose output is pasted into the acting conversation.
- **Why:** the conversation stays append-only. Changing the system prompt or
  the tool list mid-conversation breaks prompt caching and invalidates thinking
  blocks on current Claude models.

## D6. Server-side refusal fallback is on by default in live mode
- **Decision:** the live provider sends `fallbacks: "default"` with the
  `server-side-fallback-2026-07-01` beta header (via the SDK's `extra_headers`
  and `extra_body`), switchable with `server_fallback=False`.
- **Alternatives:** no fallback (a refusal simply ends the run as
  `no_tool_call`).
- **Why:** recommended default for current Claude models; a false-positive
  refusal on a harmless coding task would otherwise be scored as a failure of
  the agent. Not verifiable offline, listed as a known gap.

## D7. Extractive keep-tail summarisation, thinking stripped from kept turns
- **Decision:** when the estimated request size passes 75% of the context
  budget, old turns are replaced by a rule-based digest (one line per tool call
  with ok/error and the first line of its output) appended to the task
  message. The last 4 assistant turns are kept verbatim minus their thinking
  blocks.
- **Alternatives:** ask the model to write the summary; "simple compaction"
  (summary only, keep nothing); server-side compaction.
- **Why:** deterministic and testable offline, costs no tokens, and keeps the
  most recent observations exact (the agent usually needs the last file it
  read). Stripping thinking blocks from kept turns is required because the API
  rejects thinking blocks whose preceding history was edited. An LLM-written
  summary is listed under "What I'd do next".

## D8. Mock is the default provider everywhere
- **Decision:** every command defaults to `--provider mock`. Live mode needs an
  explicit `--provider anthropic` and fails fast if `ANTHROPIC_API_KEY` is unset.
- **Alternatives:** switch to live automatically when a key is present.
- **Why:** a benchmark run makes hundreds of model calls; nobody should spend
  money by accident because a key happened to be in their shell.

## D9. Failure taxonomy is decided by ordered rules over observable facts
- **Decision:** `classify_failure` checks, in order: passed, budget stop, no
  file changed (broken patch if a patch was rejected, else gave up), no
  changed file overlaps the reference fix (wrong file), visible pass but hidden
  fail (overfit), otherwise incorrect fix. "Changed files" comes from diffing
  the workspace against the original repo, not from the agent's claims.
- **Alternatives:** let an LLM judge label failures; allow several labels.
- **Why:** deterministic, cheap, testable, and every label has a one-line
  definition. One label per run keeps the counts summing to the failures.
  `incorrect_fix` was added as a catch-all so every failure gets a label.

## D10. Mock benchmark has a pass-rate gate in CI
- **Decision:** CI runs the mock benchmark with `--min-pass-rate 0.75`.
- **Alternatives:** only check that the benchmark runs.
- **Why:** the scripted oracle's expected score is known (15/20). A drop means
  a regression in tools, patching, evaluation or tasks, which is exactly what
  the mock run is for.

## D11. Vendor names appear only where they name the API being called
- **Decision:** "Anthropic" and "Claude" appear only where the code talks to
  that API (`AnthropicProvider`, `providers/anthropic.py`, `ANTHROPIC_API_KEY`,
  model ids, notes on how that API treats thinking blocks). No commit, comment
  or document credits AI assistance.
- **Alternatives:** rename the provider to something vendor-neutral such as
  `LiveProvider`.
- **Why:** the spec itself names `AnthropicProvider` and `ANTHROPIC_API_KEY`;
  the no-mention rule is about authorship attribution, and hiding which API
  the live provider calls would make the code harder to understand.

## D12. Top-level automatic prompt caching in live mode
- **Decision:** the live provider sends top-level `cache_control:
  {"type": "ephemeral"}` on every request (switchable off) and records cache
  read and write tokens separately; `cost_usd` prices each kind at its own rate.
- **Alternatives:** manual `cache_control` breakpoints on the last message
  block; no caching.
- **Why:** an agent loop re-sends a growing, append-only prefix every step,
  which is the best case for caching. The automatic form needs no block
  bookkeeping and keeps the provider code short. Without separate cache
  accounting, cost reports would be overstated by up to 20x on cached tokens.

## D13. Retries are delegated to the SDK
- **Decision:** `AnthropicProvider` passes `max_retries=5` and a 600 s timeout
  to the SDK client; there is no retry wrapper of our own.
- **Alternatives:** a provider-agnostic `RetryingProvider` with hand-written
  exponential backoff.
- **Why:** the SDK already implements backoff with jitter and honours
  `retry-after`. A second layer would multiply retries (5 x 5) and wait times.
  Mock providers never fail transiently, so nothing else needs retries.

## D14. pass@k via repeated samples and the unbiased estimator
- **Decision:** `--samples N` repeats each (task, strategy) N times; the
  summary reports pass@1 and pass@N using `1 - C(n-c, k)/C(n, k)` per task.
  Trajectories of repeated samples are named `<task>.s<i>.jsonl`; with one
  sample the name stays `<task>.jsonl`.
- **Alternatives:** the naive estimate "1 if any of k runs passed".
- **Why:** the naive estimate is biased upward and has high variance; the
  combinatorial estimator is the standard one from the Codex paper and is
  exact for k = n.

## D15. Parallelism with a thread pool
- **Decision:** `run_benchmark(workers=N)` uses `ThreadPoolExecutor.map`.
- **Alternatives:** a process pool; asyncio.
- **Why:** runs spend their time in pytest subprocesses and network calls, so
  the GIL is not the bottleneck; threads need no pickling and share nothing
  mutable (each run owns its provider, workspace and trajectory file). `map`
  preserves job order, so results files are identical to a serial run except
  for wall times.

## D16. Model-written summaries as an opt-in with a guaranteed fallback
- **Decision:** `AgentConfig.summariser = "model"` sends the old turns (rendered
  as text, outputs capped) to the same provider with a dedicated system prompt
  and no tools, in a separate request. Its usage counts towards the run's
  budget. A failure or empty answer falls back to the extractive digest and the
  reason is recorded. The scripted mock returns a canned summary; replay
  returns the recorded ones.
- **Alternatives:** summarise inside the main conversation (ask the agent to
  summarise itself); server-side compaction.
- **Why:** a separate request keeps the main conversation append-only and its
  system prompt and tools stable. The fallback keeps summarisation from ever
  being a new way for a run to fail. Server-side compaction is tied to one
  vendor and cannot be exercised offline.

## D17. CI compares a fresh mock run with the committed results
- **Decision:** `bench --compare-to DIR` diffs the new `results.json` against
  `DIR/results.json`, ignoring `wall_seconds` and `avg_wall_seconds`, and exits
  1 on any difference. CI runs it against `bench/results/mock`.
- **Alternatives:** regenerate results in CI and commit them automatically;
  compare only pass@1.
- **Why:** mock runs are deterministic apart from timing, so an exact
  comparison catches any behaviour change (steps, tokens, labels, config) and
  forces the committed numbers to be regenerated together with the change.
  Bots committing to main would blur authorship.

## D18. Docker sandbox as an opt-in, shared by the tool and the evaluator
- **Decision:** `sandbox.run_pytest` is the single place pytest is launched.
  With a `DockerSandbox` it runs `docker run --rm --network none --memory 1g
  --cpus 1 -v workspace:/work`, and on timeout it runs `docker kill` on the
  container's unique name. Test paths are passed relative to the workspace so
  they mean the same inside and outside the container.
- **Alternatives:** sandbox only the agent's `run_tests`; run the whole
  harness inside one container (already possible with the Dockerfile);
  seccomp/nsjail.
- **Why:** both the agent's test runs and the final scoring execute
  agent-written code, so both need isolation. One helper removed duplicated
  subprocess code. Opt-in because Docker is not available everywhere and the
  mock benchmark only runs trusted reference patches.
