# Codex fixtures (unit C1)

No live Codex was run for these. Everything is built from documented shapes, and each source is named below.
C4 replaces them with a real capture when a Codex run is available.

## Hook payloads (`hook-*.json`)

Field names come from `plans/amp-codex/dossier.md` section 5 (line 155), which records the Codex hook input
as taken from the Codex docs (learn.chatgpt.com/docs). That is secondhand: no payload was captured.

- `session_id`, `transcript_path`, `cwd`, `hook_event_name`, `model`, `turn_id`: dossier section 5 (the general input
  list, applied to every event). `[INFERRED]` for the per-event use.
- `prompt`: dossier section 5, on UserPromptSubmit.
- `last_assistant_message`: dossier section 5, on Stop.
- Event names `SessionStart`, `UserPromptSubmit`, `Stop`, `PreCompact`: `plans/amp-codex/probe/P2.md` R13, which
  confirms them from the generated app-server schema (`ManagedHooksRequirements`). P2 also records that the stdin
  fields are NOT in that schema, so the field names above remain `[INFERRED]` until C4.
- No `trigger` field on `hook-precompact.json`: the dossier does not list one. The compact gate does not read it.
- No `source` field on `hook-sessionstart.json`: not listed either. The hook ignores SessionStart.
- `transcript_path` values are placeholders. The tests point them at `rollout-min.jsonl`.

## Rollout (`rollout-min.jsonl`)

A synthetic rollout, four events, ending in a `token_count` event (the brief's minimum is three).

- `type` plus `payload` on each line, `turn_context` with `payload.model`, and `event_msg` with `payload.type`
  `token_count` carrying `info.total_token_usage` with the keys `input_tokens`, `cached_input_tokens`,
  `output_tokens`, `reasoning_output_tokens`: `bin/lane` `codex_usage` (around line 2902), and the census reader
  `bin/turn-meter` `_census_codex`. `[OBSERVED]` in the kit's own parsers.
- `session_meta` with `id`, `originator`, `cli_version`: `originator` is `[OBSERVED]` in `_census_codex`; `id` and
  `cli_version` are `[INFERRED]`.
- `info.last_token_usage`: `[INFERRED]`. Not read by `codex_usage`. The compact gate uses it for the context size.
- `event_msg` with `payload.type` `task_started`: `[INFERRED]` from the Codex turn-event names. The compact gate uses
  it to tell a turn is open. `task_complete` and `turn_aborted` close a turn; neither is in this file.
- The numbers are round values chosen for the test. The model `gpt-6-luna` is priced from `arms.json`
  `providers.codex.rate_card` (input 2.5, cached input 0.25, output 12.5 per million credits) at `usd_per_credit` 0.04.
  Priced from the final `total_token_usage`: 2.875 credits, $0.115 list.
