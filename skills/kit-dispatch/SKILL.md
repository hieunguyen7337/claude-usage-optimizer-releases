---
name: kit-dispatch
description: Hand one ready unit to a worker and record the review. Use when the brief has all four parts. Do not use it to read meters, install the kit, or start a pair the owner has not approved.
---

# Kit dispatch

Hand one unit to one worker. You still read the diff and run the verifier.

Write the brief in four parts first (the kit policy, Briefs). If any part is missing, the unit is not ready:

1. Goal: what done means, in one or two sentences.
2. Files in scope and files out of scope.
3. Constraints, including the verifier command.
4. Return contract: files changed, file:line, the verifier's real output, and anything unresolved.

Then:

1. `~/.claude/usage-optimizer/bin/lane-stats pick --class CLASS --dir DIR --brief FILE`
   `CLASS` is `mechanical`, `substantive`, `hard`, `design`, `review`, or `research`. `--dir` is the absolute work directory. `--brief` is the brief file.
2. Run the printed `lane` line (the line that starts with `run`). Do not choose an arm yourself.
3. Read the diff. Run the verifier yourself. A worker's "tests pass" is a claim.
4. `~/.claude/usage-optimizer/bin/lane-stats review RUN --outcome OUTCOME`
   `OUTCOME` is `accepted`, `fixed`, `rework`, or `rejected`. `fixed` means you merged it after a small fix of your own. `--fix-minutes N` records that fix. `--note TEXT` adds a short note.

A pair (`--pair`) is a capability test. Run one only when the owner has approved it, and pass that approval as `--approved`. Record the outcome right after the review. A run with no review is not data.
