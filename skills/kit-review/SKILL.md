---
name: kit-review
description: Weigh review findings by each reviewer arm's tier before applying them. Use when a review lists findings to accept or decline. Do not use it to run the worker or to install the kit.
---

# Kit review

Weigh findings. The tier decides the default, not the wording.

1. `~/.claude/usage-optimizer/bin/lane-stats reviewers` gives each arm a tier (`--json` for one object, `--min-findings N` to change when live precision takes over).
   - `higher-signal`: apply a verified finding by default. Decline it only for an explicit direction, a repo convention, or a pattern the reviewer did not see.
   - `lower-signal`: start sceptical. Act only on a concrete correctness, contract or security flaw with a path that fires.
   - `unknown`: no data. Treat it as lower-signal, and record `--findings` on its reviews.
2. Decline a finding, at any tier, when there is no reachable path, when it is a defensive check for a state that cannot happen, when it is a speculative abstraction, or when it adds complexity without changing an outcome. Decline nits by default.
3. Record what you applied: `~/.claude/usage-optimizer/bin/lane-stats review RUN --outcome OUTCOME --findings APPLIED/TOTAL`
   `APPLIED` and `TOTAL` are non-negative integers, `APPLIED` is at most `TOTAL`, and `0/0` is allowed. `OUTCOME` is `accepted`, `fixed`, `rework`, or `rejected` (`kit-dispatch`).

If `lane-stats reviewers --help` fails, this core has no reviewers command. Say the core needs an update (`kit-setup`).
