# ADR 0005: Hidden tests, restored visible tests and an ordered failure taxonomy

## Status
Accepted

## Context
"The tests pass" is easy to fake: edit the test, or special-case the inputs
the visible tests use. A benchmark also needs to say *why* runs fail, not just
how often.

## Decision
- Each task has visible tests (in the repo the agent sees) and hidden tests
  (kept outside it, never copied in during the run).
- After the run the harness diffs the workspace against the original repo,
  restores the original visible tests, copies in the hidden tests, and runs
  both suites.
- `classify_failure` gives each failed run exactly one label, checking in
  order: budget exceeded, broken patch (no change, a patch was rejected), gave
  up (no change, no patch tried), wrong file (no changed file overlaps the
  reference fix), test overfit (visible pass, hidden fail), incorrect fix.
- A test asserts, for all 20 tasks, that both suites fail before and pass
  after the reference fix, and that the overfit patch is caught.

## Consequences
- Editing tests cannot produce a pass, and overfitting shows up as its own
  category.
- "Wrong file" depends on the reference fix's file list. A valid fix in a
  different file would be mislabelled (it would still pass if the tests pass,
  since passing is checked first).
- Labels are rules over observable facts, so they are cheap and reproducible,
  but coarser than a human or LLM reading the trajectory.
