---
name: kit-hillclimb
description: Run the blind hill-climb on an artifact, with reviewers from another model family. Use only after the owner approves that capability test. Do not use it for an ordinary review or without that approval.
---

# Kit hill-climb

A capability test. It spends quota on blind reviews. Start it only after the owner approves, and pass that approval as `--approved`.

Your agent, or a worker, edits the artifact between rounds. A reviewer must be from another model family than the builder. Families are `claude`, `openai`, `google` and `xai`. A same-family review does not gate.

1. `~/.claude/usage-optimizer/bin/lane-bench hillclimb init WORKDIR --feedback TEXT --dimension NAME --dimension NAME --approved NOTE`
   `--feedback` is the owner's words. Repeat `--dimension` for 2 to 5 names. Optional: `--before FILE`, `--ref FILE`, `--rounds N` (default 4), `--bar N` (default 9), `--budget-usd USD` (default 5), `--builder-family` (default `claude`).
2. Edit, then `~/.claude/usage-optimizer/bin/lane-bench hillclimb snapshot WORKDIR FILE [FILE ...]`.
3. `~/.claude/usage-optimizer/bin/lane-bench hillclimb review WORKDIR --lane LANE -e EFFORT`
   `EFFORT` is `low`, `medium`, `high`, `xhigh` or `max`. Pick a lane from another family than the builder (the help names `sol` and `gemini`). `--family` names the family when the kit does not know the lane. `--allow-same-family` records a review that does not gate. Do not show the reviewer the bar, earlier scores or the round number.
4. `~/.claude/usage-optimizer/bin/lane-bench hillclimb status WORKDIR` (`--json` for one object). Stop at the round cap, the score bar or the budget.

If `lane-bench hillclimb --help` fails, this core has no hill-climb command. Say the core needs an update (`kit-setup`).
