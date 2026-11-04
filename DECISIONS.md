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
