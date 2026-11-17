---
name: kit-waste
description: Find unused agents, skills and MCP servers, overpowered sub-agents and cache rewrites. Use when the owner asks what is wasting tokens. Do not use it to delete anything before the owner agrees.
---

# Kit waste

Find waste. Change nothing until the owner agrees.

1. `~/.claude/usage-optimizer/bin/turn-meter waste [--days N] [--json] [--platform claude-code|codex|all]`
   It lists unused agents, skills and MCP servers, sessions whose cache was rewritten far more than it was read, overpowered sub-agents, and old models and fast mode. It writes nothing.
2. `~/.claude/usage-optimizer/bin/turn-meter prune` is a dry run. It prints what it would remove and does not remove it.
3. `turn-meter prune --apply` removes what the dry run showed. `turn-meter prune --restore` puts back the last apply. Run either only after the owner agrees, and only for the items they named.

If `turn-meter prune --help` fails, this core has no prune command. Say the core needs an update (`kit-setup`) and do not invent a removal.

Never read a credential file. Never prune a skill, agent or server the owner did not name.
