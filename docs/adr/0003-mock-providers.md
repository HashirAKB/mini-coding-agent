# ADR 0003: Mock mode is a scripted oracle with injected faults, plus replay

## Status
Accepted

## Context
Without an API key we still need to run the loop, tools, evaluation, failure
taxonomy and viewer end to end, deterministically, in tests and CI. A fake
"smart" agent would be a second agent to maintain, and its scores would still
mean nothing.

## Decision
- `ScriptedProvider` receives the task's reference patch and plays one of seven
  behaviours: solve, broken patch then recover, broken patch, wrong file, give
  up, overfit, and never finish. `bench.MOCK_BEHAVIOURS` assigns faults to 7 of
  the 20 tasks so every failure category appears.
- The policy is a generator that reads the latest tool results, so it reacts to
  real observations (it re-reads the file after a rejected patch).
- `ReplayProvider` replays the model turns stored in any trajectory, so a
  recorded live run can be re-run offline.
- Every mock report carries a banner saying the numbers only prove the harness
  works.

## Consequences
- Mock pass@1 is fixed by construction (15/20). CI asserts it, which turns the
  mock benchmark into a regression test for the harness.
- Mock token counts are chars/4 estimates and mock "cost" is what those tokens
  would cost at live prices. Both are labelled.
- Nothing in mock mode measures model ability. That needs live runs.
