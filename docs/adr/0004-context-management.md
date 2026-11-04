# ADR 0004: Context management by truncation plus keep-tail summarisation

## Status
Accepted

## Context
A coding agent's context grows every step: file contents, test logs, diffs.
Two problems: single outputs that are huge (a long file, a noisy test log), and
a history that slowly approaches the context limit. Current Claude models also
bind each thinking block to the exact history before it; editing that history
and replaying the block is rejected by the API.

## Decision
- **Per observation:** `truncate_output` keeps the head (2/3 of the budget)
  and tail (1/3) and inserts a marker with the number of omitted lines and a
  tool-specific hint (for example "use read_file with start_line"). `read_file`
  also pages long files itself.
- **Per request:** the loop estimates the request size (chars/4). Above 75% of
  `context_limit_tokens`, `summarise_history` replaces all but the last 4
  assistant turns with a rule-based digest (one line per tool call: name,
  arguments, ok/error, first output line) appended to the task message.
- Retained turns keep their text and tool calls but drop thinking blocks.
- The summary is cut only at turn boundaries, so every `tool_use` keeps its
  `tool_result` and roles keep alternating.

## Consequences
- Deterministic and free (no model call), fully unit-tested offline.
- The digest loses detail an LLM summary could keep (why a hypothesis was
  rejected). Listed as future work.
- chars/4 can be off by 20 to 30 percent for code. The limit is a working
  budget well below the model's real window, so the estimate only needs to be
  roughly right; live runs record real token counts from the API.
