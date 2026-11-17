---
name: kit-setup
description: Install or update the Coding Tool Optimizer core. Use when the owner asks to set the kit up, or when a session says the core is missing or older than the plugin. Do not dispatch work from this skill, and do not run the installer before the owner has seen the dry run.
---

# Kit setup

Install or update the core (tools, settings, hooks, policy). This skill does not copy those hooks. `install.sh` does.

1. Detect the agent. If `AMP_CURRENT_THREAD_ID` is set, the platform is `amp`. Otherwise if `CLAUDECODE` is set, the platform is `claude-code`. Otherwise ask the owner which of `claude-code`, `codex` or `amp` this session is. Codex sets no marker this kit knows.
2. The checkout is `~/coding-tool-optimizer`. If that directory is missing, run `git clone https://github.com/hieunguyen7337/coding-tool-optimizer ~/coding-tool-optimizer`. If it is already a checkout, run `git -C ~/coding-tool-optimizer pull`.
3. Show the owner this dry run and wait for a yes. `PLATFORM` is the value from step 1.
   `bash ~/coding-tool-optimizer/install.sh --platform PLATFORM --dry-run`
4. On a yes, run the same command without `--dry-run`.
5. Verify with `~/.claude/usage-optimizer/bin/usage-status`.

Never read a credential file, including `auth.json` and any file whose name contains `credential`. Never pass a secret to the installer.
