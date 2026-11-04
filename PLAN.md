# PLAN

Tick each milestone when its success criterion (see SPEC.md) passes and the
commit is pushed.

- [x] M0 Scaffold: pyproject, package skeleton, CI, Dockerfile, LICENSE, .env.example
- [x] M1 Workspace + tools + patch applier (path traversal and timeouts tested)
- [x] M2 Providers (scripted, replay, anthropic) + agent loop + stop conditions
- [x] M3 Context management (estimate, truncation, summarisation)
- [x] M4 20 benchmark tasks with visible + hidden tests and reference patches
- [x] M5 Harness, metrics, failure taxonomy, strategies, committed mock results
- [x] M6 Trajectory viewer, README, LEARNING, ADRs, SUMMARY, final review
- [x] Senior-reviewer pass (read every file, fixed bugs, re-ran everything)

## Follow-up items ("What I'd do next")

- [x] Prompt caching in the live provider, cache tokens priced separately
- [x] Retries and timeout for the live provider (delegated to the SDK)
- [x] pass@k with repeated samples and the unbiased estimator
- [x] Parallel task execution (`--workers`)
- [x] Optional model-written summaries with extractive fallback
- [x] CI check that committed mock results are up to date
- [x] Per-step timing: model latency vs tool time
- [x] Optional Docker sandbox for `run_tests` (and for scoring)
- [ ] Run the live benchmark and commit results (blocked, see below)

## Blockers

- **Live benchmark run:** needs `ANTHROPIC_API_KEY` and network access to the
  API, neither of which exists in the build environment. Everything needed is
  in place: `python -m mini_agent bench --provider anthropic --workers 4`
  writes `bench/results/live/` (labelled LIVE).
