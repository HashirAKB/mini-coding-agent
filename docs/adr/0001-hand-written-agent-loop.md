# ADR 0001: A hand-written agent loop with a provider interface

## Status
Accepted

## Context
The project exists to show and measure how a coding agent works. Agent
frameworks and SDK tool runners hide the loop: when to stop, what goes back to
the model after a tool error, how the context is kept small. Those are exactly
the parts worth learning and measuring. The build environment also has no
network access to any model API, so everything must run offline.

## Decision
- `agent.py` holds a plain `for step in range(max_steps)` loop: check the
  budget, manage context, call the provider, run each tool call, record the
  step, stop on `finish`, on a reply with no tool call, at `max_steps`, or
  when the token budget is spent.
- The loop only talks to a `Provider` protocol (`complete(system, messages,
  tools) -> ModelResponse`) using neutral types from `types.py`.
- Three providers: `ScriptedProvider` and `ReplayProvider` (offline), and
  `AnthropicProvider` (live, official SDK, imported lazily).

## Consequences
- The whole system builds, tests and demos with zero API keys.
- Swapping or adding a model vendor touches one file.
- Provider-specific state (thinking blocks) needs a neutral escape hatch:
  `Message.raw` carries the provider's own content blocks back unchanged.
- We own the loop's bugs; the tests cover each stop condition.
