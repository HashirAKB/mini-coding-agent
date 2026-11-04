"""The agent loop.

    messages = [task]
    repeat:
        response = model(system, messages, tools)       # think + choose tools
        results  = [run(tool_call) for each tool call]  # act
        messages += [response, results]                 # observe
    until finish / no tool call / max steps / token budget / provider error

Everything else in this package exists to make one of those lines safe,
bounded or measurable.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

from mini_agent.context import (
    DEFAULT_HINT,
    TRUNCATION_HINTS,
    estimate_request_tokens,
    extractive_summary,
    rebuild_history,
    render_turns,
    split_history,
    truncate_output,
)
from mini_agent.prompts import PLAN_ACK, STRATEGIES, SUMMARISER_SYSTEM, task_prompt
from mini_agent.providers.base import Provider
from mini_agent.tools import TOOL_SPECS, ToolBox
from mini_agent.trajectory import TrajectoryWriter
from mini_agent.types import Message, ModelResponse, ToolResult, Usage


@dataclass
class AgentConfig:
    max_steps: int = 30
    max_total_tokens: int = 400_000  # input + output, summed over all model calls
    strategy: str = "direct"  # "direct" or "plan"
    context_limit_tokens: int = 100_000  # our working budget for one request
    summarise_at: float = 0.75  # summarise old turns above this share of the limit
    keep_recent_turns: int = 4  # assistant turns kept verbatim when summarising
    summariser: str = "extractive"  # "extractive" (rules, free) or "model" (one extra call)
    max_observation_chars: int = 8_000  # longer tool outputs are truncated


@dataclass
class AgentResult:
    stop_reason: str
    steps: int
    usage: Usage
    finish_status: str | None = None
    finish_summary: str = ""
    messages: list[Message] = field(default_factory=list)
    model_seconds: float = 0.0  # time spent waiting for the provider
    tool_seconds: float = 0.0  # time spent running tools


class Agent:
    def __init__(
        self,
        provider: Provider,
        toolbox: ToolBox,
        config: AgentConfig | None = None,
        trajectory: TrajectoryWriter | None = None,
    ) -> None:
        self.provider = provider
        self.toolbox = toolbox
        self.config = config or AgentConfig()
        self.trajectory = trajectory
        self.system = STRATEGIES[self.config.strategy]

    def _record(self, event: dict[str, Any]) -> None:
        if self.trajectory is not None:
            self.trajectory.write(event)

    def run(self, task: str) -> AgentResult:
        messages = [Message("user", text=task_prompt(task))]
        usage = Usage()
        self._record(
            {
                "type": "run_start",
                "provider": self.provider.name,
                "model": self.provider.model,
                "config": asdict(self.config),
                "system": self.system,
                "task": messages[0].text,
            }
        )
        result = self._loop(messages, usage)
        self._record(
            {
                "type": "run_end",
                "stop_reason": result.stop_reason,
                "steps": result.steps,
                "usage": asdict(result.usage),
                "finish_status": result.finish_status,
                "finish_summary": result.finish_summary,
            }
        )
        return result

    def _loop(self, messages: list[Message], usage: Usage) -> AgentResult:
        timings = {"model": 0.0, "tools": 0.0}

        def stop(
            reason: str, step: int, status: str | None = None, summary: str = ""
        ) -> AgentResult:
            return AgentResult(
                reason, step, usage, status, summary, messages, timings["model"], timings["tools"]
            )

        for step in range(1, self.config.max_steps + 1):
            if usage.total >= self.config.max_total_tokens:
                return stop("token_budget", step - 1)

            context_tokens = self._manage_context(step, messages, usage)
            started = time.perf_counter()
            try:
                response = self.provider.complete(self.system, messages, TOOL_SPECS)
            except Exception as error:  # network, rate limit, bad request, exhausted replay
                # One failed call should end this run, not the whole benchmark.
                return stop("provider_error", step - 1, None, f"{type(error).__name__}: {error}")
            model_seconds = time.perf_counter() - started
            timings["model"] += model_seconds
            usage.add(response.usage)
            messages.append(
                Message("assistant", response.text, response.tool_calls, raw=response.raw)
            )

            if not response.tool_calls:
                self._record_step(step, context_tokens, response, [], model_seconds, 0.0)
                if self.config.strategy == "plan" and step == 1:
                    messages.append(Message("user", text=PLAN_ACK))  # the plan turn
                    continue
                return stop("no_tool_call", step)

            results: list[ToolResult] = []
            finish_args: dict[str, Any] | None = None
            started = time.perf_counter()
            for call in response.tool_calls:
                result = self.toolbox.execute(call)
                hint = TRUNCATION_HINTS.get(call.name, DEFAULT_HINT)
                limit = self.config.max_observation_chars
                result.output = truncate_output(result.output, limit, hint)
                results.append(result)
                if call.name == "finish" and not result.is_error:
                    finish_args = call.args
            tool_seconds = time.perf_counter() - started
            timings["tools"] += tool_seconds
            self._record_step(step, context_tokens, response, results, model_seconds, tool_seconds)

            if finish_args is not None:
                reason = "finished" if finish_args["status"] == "done" else "gave_up"
                return stop(reason, step, finish_args["status"], finish_args["summary"])
            messages.append(Message("user", tool_results=results))

        return stop("max_steps", self.config.max_steps)

    def _manage_context(self, step: int, messages: list[Message], usage: Usage) -> int:
        """Summarise old turns if the next request would be too big. Returns its size."""
        tokens = estimate_request_tokens(self.system, messages, TOOL_SPECS)
        if tokens <= self.config.context_limit_tokens * self.config.summarise_at:
            return tokens
        split = split_history(messages, self.config.keep_recent_turns)
        if split is None:
            return tokens  # nothing old enough to summarise
        old, recent = split
        event: dict[str, Any] = {"type": "context_summarised", "step": step}
        summary = ""
        if self.config.summariser == "model":
            summary, event["fallback_reason"] = self._model_summary(old, event, usage)
        event["summariser"] = "model" if summary else "extractive"
        summary = summary or extractive_summary(old)
        messages[:] = rebuild_history(messages[0], summary, recent)
        after = estimate_request_tokens(self.system, messages, TOOL_SPECS)
        self._record({**event, "tokens_before": tokens, "tokens_after": after, "summary": summary})
        return after

    def _model_summary(
        self, old: list[Message], event: dict[str, Any], usage: Usage
    ) -> tuple[str, str]:
        """Ask the model to summarise `old` in a separate request.

        Returns (summary, fallback_reason). An empty summary means "use the
        extractive one", so a failed or empty summary call never breaks the run.
        """
        request = [Message("user", text=render_turns(old))]
        try:
            response = self.provider.complete(SUMMARISER_SYSTEM, request, [])
        except Exception as error:
            return "", f"{type(error).__name__}: {error}"
        usage.add(response.usage)  # summaries cost tokens too
        event["usage"] = asdict(response.usage)
        if not response.text.strip():
            return "", "empty summary"
        return response.text.strip(), ""

    def _record_step(
        self,
        step: int,
        context_tokens: int,
        response: ModelResponse,
        results: list[ToolResult],
        model_seconds: float,
        tool_seconds: float,
    ) -> None:
        self._record(
            {
                "type": "step",
                "step": step,
                "context_tokens_estimate": context_tokens,
                "text": response.text,
                "tool_calls": [asdict(call) for call in response.tool_calls],
                "observations": [asdict(result) for result in results],
                "usage": asdict(response.usage),
                "model_stop_reason": response.stop_reason,
                "model_seconds": model_seconds,
                "tool_seconds": tool_seconds,
                "raw": response.raw,
            }
        )
