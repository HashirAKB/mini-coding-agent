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
