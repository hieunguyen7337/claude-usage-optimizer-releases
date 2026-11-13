# Claude Usage Optimizer on Amp

You are reading the kit's policy inside Amp (ampcode.com). The policy below was written for Claude Code; this page
maps it. Where the two disagree, this page wins on Amp.

1. **You are the main session.** Wherever the policy says "Claude" or "the main session", it means you, whatever
   model Amp runs you on. Your jobs are the same: plan, brief, review every diff, decide, talk to the owner. Written
   units go to worker lanes through `lane-stats pick` and `lane`.
2. **Where lane runs go.** Amp has no Claude Code subagents, so a picked Claude arm runs as a process (`lane` with
   no place flag) or in the cloud (`--cloud`, which starts a Claude Code cloud session from this machine). Pass
   `--subagent` only if `lane-stats pick` printed it; with `KIT_PLATFORM=amp` set it never does. Amp's own Task tool
   is fine for short reads and searches, as Claude Code subagents are; it runs on your thread's model.
3. **Which wallet pays.** Amp bills the model you run on: a linked subscription (Claude plan, ChatGPT) draws that
   provider's window, which the kit meters as usual; Amp credits cost list price. `amp usage` and
   `amp threads usage <thread> --details` print dollars; the kit reads who paid from that report's Model Routing table
   (its `Cost:` line counts Amp credits only, so a subscription-routed thread shows $0.00 there). Set
   `providers.amp.billed_to` in `~/.config/lanes/arms.local.json` only to override it (`claude` or `codex`).
4. **Cost and time lines.** The kit's Amp plugin records each turn (`turn-meter hook --platform amp`). End every
   report with the Cost and Time lines from `turn-meter current --platform amp`. On credits the cost line is dollars
   with no window percent. In a one-shot `amp -x` run the plugin can finish loading after the turn has started; that
   turn is then recorded at its end only, with no start time or cost of its own (seen 2026-11-13). Interactive
   sessions load the plugin before the first prompt.
5. **Compaction.** Amp compacts by itself at about 90% of the context window, and there is no hook before it. Ignore
   the policy's compaction gate and `/compact` advice; keep a short handoff note (plan, task list, identifiers) in a
   file before long work, since a compaction can land mid-task.
6. **What Amp lacks here.** No two-row statusline (the plugin shows one status item: ETA, cost, meters, kit
   release), no mobile view, no sessions pane, no compact-at-rest, no cloud mirrors of your own (`lane main` starts
   Claude Code mirrors, which still work from this machine).
7. **The `amp` lane** (`lane amp`) runs Amp itself as a worker. Its arms are manual: use them only when the owner
   names them, or a pair test the owner approved. A worker started by `lane` sets `KIT_LANE_RUN`, and the plugin
   stays silent there.
8. **Data.** Anthropic and OpenAI models through Amp follow Amp's minimal-retention terms (no training unless opted
   in): private code is allowed, as for cursor. GLM and xAI routes take non-sensitive work only, as glm and grok do.
9. **Everything else** in the policy (approvals, capability tests, briefs, review, meters, modes, reset credits) holds
   unchanged.
