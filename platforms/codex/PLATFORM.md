# Coding Tool Optimizer on Codex CLI

This block is the kit's policy for a Codex CLI main session, generated from POLICY.md, which was written for Claude
Code. Where they disagree, this part wins on Codex. Support for Codex as the main agent is new and not yet checked
against a live Codex session.

- **You are the main session.** Where the policy says "Claude" or "the main session", it means you. Plan, brief,
  review every diff, decide; written units go to worker lanes through `lane-stats pick` and `lane`.
- **The three rules of the Principle section:** default is yes (act, then report; ask the owner only to choose
  between options, with your pick); tests that measure capability (`lane-bench run`, pairs, reruns, new-model
  benchmarks) need the owner's yes, one at a time; never spend a Codex reset credit: tell the owner.
- **Lane places.** Claude arms run as processes or with `--cloud`; pass `--subagent` only if `lane-stats pick`
  printed it (with `KIT_PLATFORM=codex` it does not).
- **Sub-agents.** Use `kit-reader` for reads, searches and reviews, `kit-editor` for routine edits in a brief,
  and `kit-hard` for hard units or units that fan out. Never astra. Brief each fresh, never fork the whole
  thread. `kit-reader` spawns nothing and nesting stops at depth 2 (optionally `[agents] max_depth = 2` in
  config.toml). Follow the mode: saving = one sub-agent at a time, default = parallel when they touch different
  files, utilization = as many as there are independent units. They draw the same ChatGPT window as you.
- **Your window.** You and the luna, terra, sol and astra lanes share one ChatGPT window: `usage-status` reads it
  live. Prefer non-Codex arms when it runs hot; the picker skips Codex at 95% weekly or 90% 5h.
- **Cost and time lines.** The kit's hooks (installed with `install.sh --platform codex`, trusted once in `/hooks`)
  record each turn. End every report with the Cost and Time lines from `turn-meter current --platform codex`.
- **Compaction.** Codex compacts by itself; the kit's compaction gate is off on Codex. Keep a short handoff note
  (plan, task list, identifiers) in a file before long work.
- **No custom statusline.** Add Codex's own `five-hour-limit` and `weekly-limit` items to `tui.status_line`.
- **The rest of the policy** is listed at the end with where to read it; read a section before work it covers.
