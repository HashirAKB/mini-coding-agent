# ADR 0002: Our own unified diff applier as the only edit tool

## Status
Accepted

## Context
The agent needs one way to change files. Options: whole-file writes, a
search/replace tool, or unified diffs. Diffs are compact, reviewable, and the
format models see most in training data. But `patch` and `git apply` give
terse errors, depend on exact `@@` line counts that models often get wrong, and
can leave a half-applied change behind.

## Decision
`patch.py` parses and applies unified diffs itself:
- `@@` numbers are a hint for where to look; counts are recomputed from the
  hunk body.
- Context and removed lines must match the file (trailing whitespace is
  forgiven). When several places match, the one closest to the hint wins.
- All hunks of all files are computed in memory first; files are written only
  if every hunk matched (all or nothing).
- Errors name the file and hunk, show the expected lines, and tell the model
  to re-read the file.

## Consequences
- The agent can recover from its own bad patches (see the
  `broken_patch_then_recover` mock behaviour and the M2 tests).
- Every reference solution in the benchmark is applied with this code in the
  test suite, so the applier is exercised on 20 real diffs.
- We do not support renames, binary files or fuzzy content matching.
