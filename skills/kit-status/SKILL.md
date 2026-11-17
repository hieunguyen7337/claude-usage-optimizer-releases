---
name: kit-status
description: Read the meters and the dispatch mode before a fan-out or a long task. Use when you are about to start several workers or a long session. Do not use it to pick an arm, record a review, or install the kit.
---

# Kit status

Read this before a fan-out or a long task. It changes nothing.

1. `~/.claude/usage-optimizer/bin/usage-status` prints plan headroom for each metered provider, and local memory. `--brief` caps it at six lines, `--no-local` skips the memory line, and `--json` prints one JSON document.
2. `~/.claude/usage-optimizer/bin/lane-stats mode` prints one line per provider: `saving`, `default`, or `utilization`. `--json` prints one object. `--no-usage` skips the live reading. Utilization starts independent units together. Saving runs one unit at a time. Default runs units in parallel only when they touch different files.

Guards, from those readings:

- A provider at its limit is skipped. Do not hand it a unit. The status command names a window that is out or tight.
- Keep the last share of Claude's week for review and decisions. When the status command says that week is at its guard, send reading and mechanical work to other lanes. The picker skips that provider once the guard is reached.

Do not start a worker from this skill. Hand one unit off with `kit-dispatch`.
