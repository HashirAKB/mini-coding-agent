"""ScriptedProvider: a deterministic stand-in for a model, used by tests and the demo.

It is an *oracle with injected faults*: it knows the task's reference solution
and plays one of a few fixed behaviours, some of which fail on purpose. That
lets the whole harness (tools, loop, evaluation, failure taxonomy, viewer) run
offline and deterministically.

It proves the harness works. It says nothing about how well a real model
would do, because it is handed the answer.

The policy is written as a generator: each `yield` is one model turn. Between
turns the agent runs the tools, and the policy reads the latest observations
from `self.last_results`, so it reacts to what actually happened (for example
retrying after a rejected patch).
"""

from __future__ import annotations

import itertools
from collections.abc import Iterator, Sequence

from mini_agent.context import estimate_request_tokens, estimate_tokens
from mini_agent.patch import parse_patch
from mini_agent.prompts import PLAN_INSTRUCTION, SUMMARISER_SYSTEM
from mini_agent.tools import ToolSpec
from mini_agent.types import Message, ModelResponse, ToolCall, ToolResult, Usage

BEHAVIOURS = (
    "solve",  # explore, reproduce, apply the reference fix, verify, finish
    "broken_patch_then_recover",  # first patch has stale context, then recovers
    "broken_patch",  # every patch is malformed, then gives up
    "wrong_file",  # edits an unrelated file and claims success
    "give_up",  # explores, then gives up
    "overfit",  # applies a patch that only special-cases the visible tests
    "budget",  # keeps exploring forever, never finishes
)

Turn = tuple[str, list[ToolCall]]  # (thought text, tool calls)


def corrupt_patch(patch: str) -> str:
    """Make a patch fail to apply by changing its first removed line (stale context)."""
    lines = patch.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("-") and not line.startswith("---"):
            lines[i] = line + "  # stale"
            break
    return "\n".join(lines) + "\n"


WRONG_FILE_PATCH = """\
--- /dev/null
+++ b/FIX_NOTES.md
@@ -0,0 +1,2 @@
+# Notes
+Investigated the bug; the code looks correct to me.
"""


class ScriptedProvider:
    name = "scripted"

    def __init__(
        self,
        solution_patch: str,
        behaviour: str = "solve",
        overfit_patch: str | None = None,
        model: str = "scripted-oracle",
    ) -> None:
        if behaviour not in BEHAVIOURS:
            raise ValueError(f"Unknown behaviour {behaviour!r}; choose from {BEHAVIOURS}")
        if behaviour == "overfit" and overfit_patch is None:
            raise ValueError("The 'overfit' behaviour needs an overfit_patch.")
        self.solution_patch = solution_patch
        self.behaviour = behaviour
        self.overfit_patch = overfit_patch
        self.model = model
        self.files = sorted({p.path for p in parse_patch(solution_patch)})
        self.last_results: list[ToolResult] = []
        self._turns: Iterator[Turn] | None = None
        self._ids = itertools.count(1)

    def complete(
        self, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> ModelResponse:
        if system == SUMMARISER_SYSTEM:
            return self._summary(messages)
        self.last_results = messages[-1].tool_results if messages else []
        if self._turns is None:
            self._turns = self._policy(plan_first=PLAN_INSTRUCTION in system)
        text, calls = next(self._turns)
        output = text + "".join(call.name + str(call.args) for call in calls)
        usage = Usage(estimate_request_tokens(system, messages, tools), estimate_tokens(output))
        return ModelResponse(text, calls, usage, stop_reason="tool_use" if calls else "end_turn")

    def _summary(self, messages: Sequence[Message]) -> ModelResponse:
        """A canned stand-in for a model-written summary (it does not use the policy)."""
        text = messages[0].text
        calls = [line for line in text.splitlines() if line.startswith("CALL ")]
        summary = f"- (scripted summary) {len(calls)} earlier tool calls, last: {calls[-1][5:]}"
        usage = Usage(estimate_tokens(SUMMARISER_SYSTEM + text), estimate_tokens(summary))
        return ModelResponse(summary, [], usage, stop_reason="end_turn")

    # ---- helpers ---------------------------------------------------------------

    def _call(self, name: str, **args: object) -> ToolCall:
        return ToolCall(id=f"call_{next(self._ids)}", name=name, args=dict(args))

    def _last_failed(self) -> bool:
        return any(result.is_error for result in self.last_results)

    def _tests_passed(self) -> bool:
        return any(result.output.startswith("exit code 0") for result in self.last_results)

    def _finish(self, status: str, summary: str) -> Turn:
        return ("Wrapping up.", [self._call("finish", status=status, summary=summary)])

    # ---- the policy ------------------------------------------------------------

    def _policy(self, plan_first: bool) -> Iterator[Turn]:
        if plan_first:
            yield (
                "Plan:\n1. Explore the package.\n2. Run the tests to reproduce.\n"
                "3. Patch the root cause.\n4. Re-run the tests and finish.",
                [],
            )
        yield ("Let me see what is in the repository.", [self._call("list_dir", path=".")])
        reads = [self._call("read_file", path=path) for path in self.files]
        yield ("Reading the code that looks relevant.", reads)
        yield ("Running the tests to reproduce the bug.", [self._call("run_tests")])
        yield from getattr(self, f"_{self.behaviour}")()

    def _verify_and_finish(self) -> Iterator[Turn]:
        yield ("Re-running the tests.", [self._call("run_tests")])
        if self._tests_passed():
            yield self._finish("done", "Fixed the bug; all tests pass.")
        else:
            yield self._finish("give_up", "Tests still fail after my fix.")

    def _solve(self) -> Iterator[Turn]:
        yield (
            "I see the bug; applying a fix.",
            [self._call("apply_patch", patch=self.solution_patch)],
        )
        yield from self._verify_and_finish()

    def _broken_patch_then_recover(self) -> Iterator[Turn]:
        broken = corrupt_patch(self.solution_patch)
        yield ("Applying a fix.", [self._call("apply_patch", patch=broken)])
        if self._last_failed():
            reads = [self._call("read_file", path=path) for path in self.files]
            yield ("The patch did not apply; re-reading the file.", reads)
            yield (
                "Retrying with exact context.",
                [self._call("apply_patch", patch=self.solution_patch)],
            )
        yield from self._verify_and_finish()

    def _broken_patch(self) -> Iterator[Turn]:
        broken = corrupt_patch(self.solution_patch)
        yield ("Applying a fix.", [self._call("apply_patch", patch=broken)])
        yield ("Trying the patch again.", [self._call("apply_patch", patch=broken)])
        yield self._finish("give_up", "I could not get the patch to apply.")

    def _wrong_file(self) -> Iterator[Turn]:
        yield ("Recording my findings.", [self._call("apply_patch", patch=WRONG_FILE_PATCH)])
        yield ("Checking the tests.", [self._call("run_tests")])
        yield self._finish("done", "Done.")

    def _give_up(self) -> Iterator[Turn]:
        yield self._finish("give_up", "I do not understand the failure.")

    def _overfit(self) -> Iterator[Turn]:
        assert self.overfit_patch is not None
        yield (
            "Making the failing case pass.",
            [self._call("apply_patch", patch=self.overfit_patch)],
        )
        yield from self._verify_and_finish()

    def _budget(self) -> Iterator[Turn]:
        while True:
            for path in self.files:
                yield ("Let me read that again.", [self._call("read_file", path=path)])
