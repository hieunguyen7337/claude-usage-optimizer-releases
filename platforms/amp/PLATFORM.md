# Claude Usage Optimizer on Amp

You are reading the kit's policy inside Amp (ampcode.com). The policy below was written for Claude Code; this page
maps it. Where the two disagree, this page wins on Amp.

1. **You are the main session.** Wherever the policy says "Claude" or "the main session", it means you, whatever
   model Amp runs you on. Your jobs are the same: plan, brief, review every diff, decide, talk to the owner. Written
   units go to worker lanes through `lane-stats pick` and `lane`.
2. **Where lane runs go.** Amp has no Claude Code subagents. When `lane-stats pick` prints `--subagent` (Claude arms,
   and `amp` arms on Anthropic or OpenAI models), `lane <lane> --subagent ...` prepares the run and prints
   `{"tool": "kit_lane_run", "run_id": "<id>"}`: call the plugin tool `kit_lane_run` with that run id. It runs the
   worker as a child agent thread on the arm's model and effort, waits up to the lane timeout, and records the run
   (`lane hook amp-run-end`); its answer comes back as the tool result. The call blocks your turn, so start parallel
   units as several tool calls in one message. If a call dies, `lane --recover <id>` marks the run from git state.
   Codex, gemini, cursor, grok and glm arms run as processes (`lane` with no place flag); `--cloud` starts a Claude
   Code cloud session from this machine. Amp's own Task tool is fine for short reads and searches; it runs on your
   thread's model.
3. **Which wallet pays.** Amp bills the model you run on: a linked subscription (Claude plan, ChatGPT) draws that
   provider's window, which the kit meters as usual; Amp credits cost list price. `amp usage` and
   `amp threads usage <thread> --details` print dollars; the kit reads who paid from that report's Model Routing table
   (its `Cost:` line counts Amp credits only, so a subscription-routed thread shows $0.00 there). Set
   `providers.amp.billed_to` in `~/.config/lanes/arms.local.json` only to override it (`claude` or `codex`).
   `usage-status` prints an `Amp:` line (credits left, last 7 days' recorded spend by source), read from
   `amp usage --details` at most every 15 minutes, since Amp allows 60 usage lookups an hour.
4. **Cost and time lines.** The kit's Amp plugin records each turn (`turn-meter hook --platform amp`). End every
   report with the Cost and Time lines from `turn-meter current --platform amp`. On credits the cost line is dollars
   with no window percent. In a one-shot `amp -x` run the plugin can finish loading after the turn has started; that
   turn is then recorded at its end only, with no start time or cost of its own (seen 2026-11-13). Interactive
   sessions load the plugin before the first prompt.
5. **Compaction.** In the `kit` agent mode (pick it in Amp's model selector) Amp compacts at 250k tokens, the kit's
   Claude Code setting; other modes compact at about 90% of the context window. There is no hook before a compaction:
   ignore the policy's compaction gate and `/compact` advice, and keep a short handoff note (plan, task list,
   identifiers) in a file before long work, since a compaction can land mid-task.
6. **The `kit` mode and what Amp lacks.** The plugin registers the `kit` mode on the main model and effort of
   `explore.main_session` (`lane hook amp-mode`), for Amp's interactive mode picker; `amp -x --mode kit` is refused by
   Amp's server, which takes only its built-in modes there (seen 2026-11-13), so a one-shot run passes `--model`
   instead. Amp's plugin API has no subagent pin any more, so Task workers in it
   run on the main model, not Sonnet: send written units to lanes. No two-row statusline (one status item: ETA, cost,
   meters, kit release), no mobile view, no sessions pane, no compact-at-rest, no cloud mirrors of your own
   (`lane main` starts Claude Code mirrors, which still work from this machine).
7. **The `amp` lane** (`lane amp`) runs Amp itself as a worker. Its arms are manual: use them only when the owner
   names them, or a pair test the owner approved. A worker started by `lane` sets `KIT_LANE_RUN`, and the plugin
   stays silent there.
8. **Data.** Anthropic and OpenAI models through Amp follow Amp's minimal-retention terms (no training unless opted
   in): private code is allowed, as for cursor. GLM and xAI routes take non-sensitive work only, as glm and grok do.
9. **Everything else** in the policy (approvals, capability tests, briefs, review, meters, modes, reset credits) holds
   unchanged.
