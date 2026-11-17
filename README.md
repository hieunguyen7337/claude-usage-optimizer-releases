# Coding Tool Optimizer: a usage optimizer for AI coding agents

Coding Tool Optimizer is for anyone who runs several AI coding agents and pays for several subscriptions. It started
on Claude Code as Claude Usage Optimizer, which is where the `~/.claude/usage-optimizer` install path comes from.

- **Routes work across the plans you already pay for.** Your main agent plans, reviews and decides. One dispatcher,
  `lane`, sends each written unit to a worker on Claude, ChatGPT (Codex CLI), Google AI Pro (Gemini), Cursor, Grok or
  Amp, through that provider's own CLI and your own login.
- **Meters each plan.** `usage-status` shows what is left in the Claude and ChatGPT windows, the Gemini quota and
  Amp's credits. Cursor and Grok have no account-wide meter, so their cost is recorded or estimated run by run.
- **Records every run.** Usage, list-price cost, time and peak memory go into a ledger, and so does your review of
  whether the result was usable.
- **Learns the cheapest arm.** `lane-stats` compares each model and effort by usable results against usage and time,
  and picks the next one to run.

## Quick start

Pick the agent you work in. Each path installs the same kit (policy, worker lanes, meters) plus that agent's adapter,
and each starts with a dry run that changes nothing. The setup prompts are in [SETUP_PROMPT.md](SETUP_PROMPT.md):
paste the one for your agent into it, or run the commands yourself from a clone of this repository.

- **Codex CLI:** the "Codex CLI" prompt, or `bash install.sh --dry-run --platform codex`, then
  `bash install.sh --platform codex`. Trust the kit's hooks once in `/hooks`, then start a new Codex session. Codex
  gets no custom status line: add its own `five-hour-limit` and `weekly-limit` items to `tui.status_line`.
  [What it changes](#install-for-codex).
- **Amp:** the "Amp" prompt, or `bash install.sh --dry-run --platform amp`, then `bash install.sh --platform amp`.
  Run `plugins: reload` or restart Amp; the kit's status item appears. [What it changes](#install-for-amp).
- **Claude Code:** the "Claude Code" prompt (it fetches the bundle from the kit page), or `bash install.sh --dry-run`,
  then `bash install.sh`. Restart open sessions. [What it changes](#install-for-claude-code).

On Windows, run the installer from Git Bash with Python 3.8 or newer. The kit's files go to
`~/.claude/usage-optimizer/` whichever agent you use; Claude Code is not needed.

After the install, work as usual. The policy tells your agent to plan, send each written unit to a worker lane
(`lane-stats pick`, then `lane`), review every diff, and end each report with a Cost line and a Time line. Three
commands to know: `usage-status` (what is left in every plan), `lane-stats report` (what each worker arm delivered)
and `turn-meter report` (each turn's cost and time).

## Which agents it runs in

The main session can be Claude Code, Amp or Codex CLI. Claude Code has the fullest support. Codex CLI support is built
and tested offline, and is not yet checked against a live Codex session.

| | Claude Code | Amp | Codex CLI |
|---|---|---|---|
| Policy | Imported into `~/.claude/CLAUDE.md` | Imported through `~/.config/amp/AGENTS.md` | A generated block in `$CODEX_HOME/AGENTS.md`, under Codex's size limit |
| Turn meter (each turn's cost and time) | Hooks | Plugin | Hooks, trusted once in `/hooks` |
| Statusline | Two lines: session, running turn, quota windows | One status item: ETA, cost, meters, kit release | None from the kit; Codex's own limit items |
| Worker lanes | As a process, a subagent or a cloud run | As a process; Claude arms and some `amp` arms run inside the Amp thread | As a process |
| Cloud runs | Yes (`lane --cloud`) | Claude Code cloud sessions, started from this machine | Claude arms with `--cloud` |
| Mods (mobile view, sessions pane, compact-at-rest, prompt-fix, loop-guard) | Yes | No | No |

## What the kit decides for you

The kit is strict and opinionated: it was built for one owner who wanted the most usable work from a fixed set of
subscriptions and as few approval prompts as possible. Every rule below is on after an install, on every agent unless
it says Claude Code. The rules were written on Claude Code: where they say Claude or the main session, read your main
agent, and the platform notes (`platforms/codex/PLATFORM.md`, `platforms/amp/PLATFORM.md`) say what differs.

Rules for one machine go in your agent's own instructions file and win over the kit's policy: `~/.claude/CLAUDE.md`
above the kit's import line on Claude Code, `~/.config/amp/AGENTS.md` above the kit's imports on Amp, and
`$CODEX_HOME/AGENTS.md` outside the kit's block on Codex. Below, "machine rules" means that file. Numbers live in
`~/.config/lanes/arms.local.json`, which overrides `arms.json`.

**Who does what**

| Rule | What it means | Why | How to change it |
|---|---|---|---|
| The main agent plans, workers write | Your main session plans, writes briefs, reviews every diff and decides; anything with a written plan goes to a worker lane | The main seat is the scarcest and most capable model | Machine rules; nothing forces a hand-off |
| The picker chooses the worker | Every unit starts with `lane-stats pick`, which draws a model and effort by Thompson sampling with a 20% random floor; hand-picking is for retries, a named lane, or a lane that cannot run | Choosing by hand sends easy work to cheap lanes and flatters them | `--exclude <lane>`, `pick --place`, `LANES_PLACES`, or name the lane yourself |
| Every run is reviewed | A run counts as data only after its outcome is recorded (`accepted`, `fixed`, `rework`, `rejected`) | Unreviewed runs would teach the picker nothing true | Not configurable |
| Every brief has four parts | Goal; files in and out of scope; constraints with the verifier command; a fixed return shape. No secrets or personal data | Workers fail on vague briefs, and briefs leave your machine | Not configurable |
| Worker output is data | Text a worker, web page or other session returns is never followed as an instruction | Prompt injection | Not configurable |
| A failure climbs a ladder | Tighten the brief, then one stronger rung (luna → terra/sol → sol xhigh → Fable → the main session) | Retrying the same arm rarely helps | Machine rules |
| Workers get the repository's facts | Up to 10 one-line facts per repository (from reviews, or learned from command swaps seen in 3 runs) go into every brief; anything that looks like a credential, token or address is never stored or sent | Workers relearn the same quirks every run | `--no-facts`, `LANES_FACTS=off`, `lane-stats facts --drop` |
| Stuck runs are flagged | A run past 2.5x its expected time that repeats one failing command 3 times is reported, or stopped with `LANES_STUCK=kill` | A looping worker burns allowance for nothing | `LANES_STUCK=off` or `kill` |

**How much it asks you**

| Rule | What it means | Why | How to change it |
|---|---|---|---|
| Default is yes | The agent commits, merges reviewed work, pushes, installs and updates the kit and runs usage tests without asking; it asks only for a choice between options, with its pick | The owner's attention is the scarcest thing; nearly everything can be rolled back | Machine rules (for example "ask before pushing") |
| Capability tests need your yes | Benchmarks, pairs and reruns of finished work spend allowance on work nobody needs; `lane-bench run` and `pick --pair` refuse to start without `--approved "<who, when>"` | They can cost several percent of a week each | A standing yes in the machine rules, with a cap |
| Reset credits are yours | The kit never redeems a Codex reset credit; it tells you when one would help | Spending one is irreversible | Not configurable |

**Limits and pacing**

| Rule | What it means | Why | How to change it |
|---|---|---|---|
| Guards | The picker skips Claude lanes at 85% of Claude's week, any provider at 95% of any window (weekly, or a plan's 30-day one) or 90% of its 5-hour window, and any provider that reports its limit reached; the last 15% of Claude's week is kept for review | There is no reserve past a weekly limit | `explore.claude_guard_pct` and the thresholds in `arms.local.json` |
| Pace on every weekly bar | The Claude Code statusline shows how much of each week has passed beside how much is used, `wk 23% (pace 31%)`, and says `hot` when use runs 10 points ahead | A week spent early stops work before the reset | `USAGE_OPTIMIZER_PACE=off` |
| Modes | Each provider runs in *saving*, *default* or *utilization* by how its week is pacing (projected use at reset ≥ 110% or ≤ 90%); the mode sets how much runs in parallel and how cost is weighed | Allowance left at a reset is lost; allowance spent early stops work | `USAGE_OPTIMIZER_MODE` or `~/.config/lanes/mode` (`auto`, `saving`, `default`, `utilization`) |
| Memory guard | A local worker starts only when free RAM, less a reserve, covers its measured peak; otherwise `lane` waits and returns BUSY | One PC runs many CLIs at once | `LANES_MEM_RESERVE_MB`, `LANES_MEM_NEED_MB`, `LANES_MEM_CHECK=off` |
| The main model is fixed | On Claude Code the main loop runs Opus at xhigh, subagents default to Sonnet, and the model is never switched mid-session with `/model`; on Codex and Amp the kit leaves the model to you, and the same rule against switching mid-session applies | A switch re-reads the whole context uncached | `explore.main_session` in `arms.json` |
| Fable is an advisor | The strongest Claude model plans hard units, reviews releases and breaks ties, within a weekly list-dollar budget and a guard on its own cap | It weighs about 3.3x Opus per dollar on the week | `explore.advisor` (`active`, `weekly_list_usd`, `fable_guard_pct`) |

**Context and the session**

The compaction rules, the loop guard, the spell-check and the mobile view are Claude Code features (its settings and mods). Codex and Amp compact by themselves; their turns are metered by the kit's hooks or plugin.

| Rule | What it means | Why | How to change it |
|---|---|---|---|
| Compaction between answers (Claude Code) | Claude Code compacts past 250k tokens; the kit compacts right after an answer at 90% of that, or earlier when a typical turn would cross 250k, holds a mid-turn compaction until the next turn unless the context reaches 350k, and re-injects the lanes in flight afterwards | About half of all spend is re-reading context | `USAGE_OPTIMIZER_COMPACT_NEAR`, `USAGE_OPTIMIZER_COMPACT_AHEAD`, `USAGE_OPTIMIZER_COMPACT_HARD`, `USAGE_OPTIMIZER_COMPACT_GATE` |
| Compaction before the cache expires (Claude Code) | After 50 idle minutes at 40% of the window or more, the kit compacts while the prompt cache is still warm | A prompt after the hour-long cache expires re-reads everything uncached | `USAGE_OPTIMIZER_IDLE_COMPACT=off`, `_MIN`, `_PCT` |
| Repeated failures are redirected (Claude Code) | The third identical failing tool call in a turn gets a note telling the agent to change approach; nothing is blocked | A loop of the same failure burns a turn | `USAGE_OPTIMIZER_LOOP_GUARD=off` |
| Waste is reported, not removed | `turn-meter waste` lists unused agents, skills and MCP servers, idle-gap cache rewrites, heavy subagents on light work and old models | Every loaded tool costs tokens on every request | Nothing changes until you act on it |
| One timeline, no model call | `lane-stats timeline` merges a tagged lead log (`lane-stats note "[decision] …"`), lane runs, reviews and cloud-session markers into one list of events | A day's work, failures and blockers at a glance, without paying a model to narrate it | Notes are optional; `--since` and `--json` shape the view |
| A per-model compaction window is flagged (Claude Code) | The statusline uses the window that applies to the session's model; `usage-status` and the installer warn when `modelSettings` overrides 250k | A hidden 350k override made compactions land near 320k for a week | Remove the override, or keep it knowingly |
| Every turn is metered | Each turn's list cost, time and the meters before and after are logged, and every report ends with a Cost line and a Time line | Cost and time are the two things to learn | `USAGE_OPTIMIZER_TURNS=off` |
| The mode is announced | Each session is told the mode and its rules at its next prompt, and again when it changes | Running sessions follow it without a restart | `USAGE_OPTIMIZER_MODE_NOTICE=off` |
| Typed prompts are spell-checked (Claude Code) | One Haiku call fixes spelling and grammar slips in each typed prompt; the row shows the corrected text and lists the changes | Typos cost turns | `USAGE_OPTIMIZER_PROMPT_FIX=off` |
| The mobile view (Claude Code) | Tool calls fold to one line and the agent narrates its work in plain sentences | The owner reads sessions from a phone | `install.sh --no-view`, or switch the output style |

**Data and accounts**

| Rule | What it means | Why | How to change it |
|---|---|---|---|
| Consumer-terms lanes get public work only | Gemini's consumer terms (Google AI Pro) let Google keep and review what it is sent, and Grok's are not yet confirmed, so both get only open-source code and public research; pass `--exclude gemini,grok` for private code | Their data terms | `--exclude` per pick, or disable their arms in `arms.local.json` |
| Cursor only with privacy mode | Never a `(NO ZDR)` model, and never a Claude model through Cursor | Data retention and double billing | Not configurable |
| One person, one account | The kit never pools or rotates several Claude subscriptions | Anthropic's terms forbid routing others' requests through plan credentials | Not configurable |
| Training toggles off | ChatGPT, Antigravity and Claude data-training settings stay off | Your code stays yours | Your accounts' settings |

**How it changes itself**

| Rule | What it means | Why | How to change it |
|---|---|---|---|
| The kit improves itself | Every lesson (a lane quirk, a meter fix, a measured result) becomes the next release and is published; machine-only facts stay in that machine's rules | One machine's lesson helps every machine | `USAGE_OPTIMIZER_UPDATE_CHECK=off` stops the update notice |
| Benchmarks are only the prior | Public scores place a model's tier; the kit's own reviewed runs decide between arms | Scores move with the harness, version and task | `lane-bench priors` writes measured priors |

## This repository

This repository holds the kit's published releases only. A release tool rewrites it at each release, so pull
requests cannot be merged here. Each release is one commit, a `v<version>` tag and a GitHub Release carrying the
bundle, the evidence file and `SHA256SUMS`.

- **Install:** clone this repository and run `bash install.sh` (add `--dry-run` first to see what it changes), or
  download the bundle from the latest release, check it against `SHA256SUMS`, and run it with `bash`. On Windows, run
  it from Git Bash.
- **Share statistics (optional):** `lane-stats share` previews one week of anonymous totals; `lane-stats share
  --enable` and then `--send` post them here as a public issue through the "Weekly statistics" form. A workflow
  checks each submission. Sharing is off until you turn it on, and an issue shows your GitHub account.
- **Licence:** MIT (see `LICENSE`).

## Install for Claude Code

Run `bash install.sh --dry-run` first, then `bash install.sh`. Without `--platform`, the installer keeps the platforms
this machine already has, and Claude Code otherwise. The main things the installer touches:

- `~/.claude/CLAUDE.md`: one import line for the policy;
- `~/.claude/settings.json`: the kit's hooks and settings, merged in;
- `~/.claude/agents/` and `~/.claude/skills/`: the kit's subagents and mods;
- `~/.claude/usage-optimizer/` and `~/.config/lanes/`: the kit's files and settings, as every install does.

It backs up what it replaces. Restart any open Claude Code sessions so they load the new settings. The kit's own
README, below, lists the hooks.

## Install for Amp

Run `bash install.sh --dry-run --platform amp` first, then `bash install.sh --platform amp`. The installer touches:

- `~/.config/amp/AGENTS.md`: a heading and two import lines, which point at the kit's `PLATFORM.md` and `POLICY.md`
  under `~/.claude/usage-optimizer/`. An existing file is backed up first;
- `~/.config/amp/plugins/usage-optimizer.ts` and `usage-optimizer.paths.json`: the plugin, which records each turn and
  shows one status item;
- `~/.claude/usage-optimizer/` and `~/.config/lanes/`: the kit's files and settings, as every install does.

It leaves alone `~/.config/amp/settings.json`, which Amp does not need for the kit, `~/.config/AGENTS.md`, which other
agents read, and Claude Code's own files under `~/.claude`. Restart Amp, or run `plugins: reload`, to load the plugin.

## Install for Codex

Run `bash install.sh --dry-run --platform codex` first, then `bash install.sh --platform codex`. The installer touches:

- `$CODEX_HOME/AGENTS.md` (`~/.codex/AGENTS.md` by default): one generated block, between
  `<!-- usage-optimizer:start -->` and `<!-- usage-optimizer:end -->`, holding the policy under Codex's size limit;
- `hooks.json` in the same folder: the kit's hook entries (turn start, turn end, compaction), after a backup;
- `~/.claude/usage-optimizer/` and `~/.config/lanes/`: the kit's files and settings, as every install does.

It leaves alone `config.toml`, and `AGENTS.override.md` if it exists: Codex reads that file before `AGENTS.md`, so the
installer warns instead of changing it. Trust the hooks once in `/hooks`. Codex support is new and is not yet checked
against a live Codex session.

The kit's own README follows.

---

# Coding Tool Optimizer: a usage optimizer for AI coding agents

Coding Tool Optimizer routes coding work across the AI subscriptions you already pay for: Claude, ChatGPT (Codex),
Google AI Pro (Gemini), Cursor, Grok and Amp. The main session runs in Claude Code, Amp or Codex CLI and spends its
plan on planning, review and judgement. Execution and read-only legwork go to cheaper worker lanes, and the remaining
quota of every metered plan is visible.

Every run's usage, cost, time and reviewed outcome is recorded, so the kit learns which model and effort gives a
usable result for the least usage. Claude Code has the fullest support, and the `~/.claude/usage-optimizer` path
comes from there (the kit was called Claude Usage Optimizer until 2026-11-16); [Platforms](#platforms) says what Amp
and Codex CLI get.
[IMPROVING.md](IMPROVING.md) explains how lessons become published kit improvements.

| Path | What it is |
|---|---|
| `POLICY.md` | The shared usage policy. Imported into `~/.claude/CLAUDE.md` as `@~/.claude/usage-optimizer/POLICY.md`; Amp and Codex CLI read it through their `AGENTS.md` (see [Platforms](#platforms)) |
| `IMPROVING.md` | How the kit records lessons, updates its research and methods, and builds and publishes releases |
| `improve/` | Reusable audit and release briefs |
| `bin/lane` | One dispatcher for fourteen lanes on seven CLIs: luna, terra, sol, astra and codex-cloud/codex, haiku, sonnet, opus and fable/claude, gemini/agy, cursor/cursor-agent, grok, glm/cline, amp. It checks each arm against the catalog, encodes each CLI's failure modes, masks credentials, prints a verdict, and records every run's usage, time, ETA and peak memory in a ledger; it waits for memory before launching. A Claude arm can also run as a subagent of the main session (`--subagent`) or in a cloud VM (`--cloud`, and `codex-cloud`) |
| `bin/lane-stats` | Turns the run ledger into decisions: `pick` chooses the next arm to run (with its ETA), `review` records each run's outcome, `report` shows the usable rate against usage, time and peak memory per lane, effort and class, `recommend` shows which classes have locked in, `arms` lists the catalog, `eta` estimates a run's wall-clock time, `export` and `import` pool runs across machines |
| `bin/lane-mask` | The Linux credential mask (mount namespace) that `lane` uses. Windows has no mask |
| `bin/lane-term` | Runs one command in a fresh pseudo-terminal (ConPTY on Windows, a pty elsewhere), types scripted answers to its prompts, stops it once a given text appears, and saves what the terminal showed. For programs that refuse to run without a terminal, such as `claude --cloud` |
| `bin/usage-status` | Headroom across Claude, Codex and Gemini, an Amp line (credits left and recent recorded spend), and this machine's memory: how many more workers of each provider fit. Codex is read live from its app-server and falls back to the newest rollout when needed |
| `bin/turn-meter` | Records every turn's list-price cost, time and the meters before and after it. The installer runs it as the `UserPromptSubmit` and `Stop` hook; `eta` records Claude's own estimate of the time left, and `current` (time so far and to go), `report` (by turn or session) and `calibrate` (cost and estimate accuracy) read the record; `census` counts every Claude Code and Codex session on the machine, kit or not |
| `bin/claude-statusline` | A two-line statusline with session context, the running turn's time and share, and the kit's name and version (`Coding Tool Optimizer 2026-10-29.3`, or the release whose policy the session last loaded and the newer one installed) on line one, and grouped Claude/Codex quota windows on line two; colors usage by level, fits the terminal width, and logs Claude's rate limits for `usage-status` |
| `bin/claude-prompts` | Lists the questions typed in a session (`--latest`, `--session-id ID` or `--transcript PATH`; `--text` for people, JSON otherwise). Behind the mobile view's question list (`>`) |
| `mods/mobile-view/` | A Claude Code mod that makes the terminal read like the Claude mobile app (see [Mobile view](#mobile-view)). Installed to `~/.claude/skills/mobile-view/` |
| `mods/sessions/` | A Claude Code mod that opens the Sessions pane (see [Sessions view](#sessions-view)): every local and cloud session grouped by repository, with a session view and its keys. Installed to `~/.claude/skills/sessions/`, with or without `--no-view` |
| `mods/compact-at-rest/` | A Claude Code mod that compacts the conversation right after an answer once the context reaches 90% of `autoCompactWindow`, rather than mid-turn (`USAGE_OPTIMIZER_COMPACT_NEAR` sets the percent, `USAGE_OPTIMIZER_COMPACT_AT_REST=off` turns it off). Installed to `~/.claude/skills/compact-at-rest/`, with or without `--no-view` |
| `mods/prompt-fix/` | A Claude Code mod that fixes spelling and grammar slips in each prompt you type (or send from the phone) with one Haiku call at low effort, sends the corrected prompt on, draws it in the prompt's own transcript row (kept for the last 300 corrections, so a resumed session shows them too), and adds a dim line `✎ Corrected: correcr → correct`. It leaves commands, short replies, prompts over 4,000 characters, code, paths and identifiers alone, and keeps the prompt as typed when the reply changes more than a quarter of the words, the line breaks or a code block. The model is told what was changed. `USAGE_OPTIMIZER_PROMPT_FIX=off` turns it off. Installed to `~/.claude/skills/prompt-fix/` |
| `output-styles/Mobile.md` | The output style that goes with it: a sentence of narration around each batch of tool calls, no long code in replies, a self-contained final answer |
| `agents/` | `scout`, `digest`, `verifier` and `researcher` subagents (Sonnet, except verifier), and one `lane-<lane>-<effort>` worker per Claude arm for `lane --subagent`, generated from `arms.json` by `tools/make-lane-agents.py` |
| `arms.json` | The arms catalog: each arm is one lane, model and effort, with its status, classes, weight and priors. Machine-local arms go in `~/.config/lanes/arms.local.json`. Installed to `~/.claude/usage-optimizer/arms.json` |
| `LANES.md` | Each lane's raw CLI contract and gotchas, for when `bin/lane` is unavailable. Installed to `~/.claude/usage-optimizer/LANES.md` |
| `settings.fragment.json` | Settings merged into `~/.claude/settings.json`: most only where a key is absent; the view keys (`view_overwrite`) are set, unless you changed one by hand after an earlier install |
| `install.sh` | An idempotent installer that backs up what it replaces. `--dry-run` shows the plan |
| `tools/make-bundle.sh` | Builds `dist/coding-tool-optimizer-bundle.sh`, a single self-extracting file for other machines, and `dist/coding-tool-optimizer-evidence.sh`, the Suite R rescore evidence (FINDINGS section 8) that the kit runs without |
| `SETUP_PROMPT.md` | The setup prompts to paste into Claude Code, Codex CLI or Amp on another machine |

`bin/lane-bench` is the kit's own benchmark. `run` runs a review suite across lane arms under the task-limit and meter gates. It is a capability test, so it runs only when the user approves it, and it refuses to start without `--approved "<who, when>"`. `grade` and `stats` score the runs (recall with Wilson and bootstrap intervals, false alarms, usable rate, cost against the weekly window), `compare` sets the arms against the public numbers in `findings/public.json`, and `priors` writes measured priors into an `arms.local.json`. The suite format and the rules for planted defects are in `measure/SUITE.md`. The kit ships tools and no suite items.

## Measurements and findings

- `measure/`: reproducible Claude and Codex meter probes and fits; see [the commands](measure/README.md).
- `findings/`: [measured plan sizes, weights and evidence](findings/FINDINGS.md), also in JSON.
- `lane-bench`: measure model × effort on your own review suite and write measured priors. Running a suite needs the user's approval. Its `run` works on Linux, macOS and Windows: since 2026-10-28 it starts `lane` and `usage-status` through their `.cmd` wrappers or Python on Windows and stops a run's whole process tree (before that every Windows run exited 127). `export` uses `jq` where it is installed and Python elsewhere. `lane-bench summary` lists every model and effort, with capability and usage side by side ([ours](findings/suite-r/by-arm.md)).

## Platforms

The kit runs on three agents. Claude Code is the full kit: the statusline, the mobile view, the sessions pane,
compaction and every lane. Amp and Codex CLI get the same policy and meter through thin adapters over the same core.

- **Claude Code (full):** everything in this README.
- **Amp:** the policy is imported through `~/.config/amp/AGENTS.md`; a plugin records each turn and shows one status
  item (ETA, cost, meters and the kit release); the `amp` worker lane runs Amp as a process. Its arms are `manual`:
  the picker never draws them, so name one to run it.
- **Codex CLI:** the policy is written into `$CODEX_HOME/AGENTS.md` as a block generated under Codex's size limit;
  hooks record each turn. It is built offline and not yet checked against a live Codex session. Trust the hooks once
  in `/hooks`.

Install one with `bash install.sh --platform amp` or `--platform codex`, after `--dry-run` to see the plan. Without
`--platform`, the installer keeps the platforms this machine already has, and Claude Code otherwise.

### Plugins and skills

Claude Code: `claude plugin marketplace add hieunguyen7337/coding-tool-optimizer`, then
`claude plugin install coding-tool-optimizer@coding-tool-optimizer`. Codex CLI:
`codex plugin marketplace add hieunguyen7337/coding-tool-optimizer`, then `/plugins`.

The plugin carries the `kit-setup` skill. On Claude Code it also checks at session start that the core
is installed and not older than the plugin. It does not install the core and it does not copy the core's
hooks. `install.sh` still installs the tools, settings, hooks and policy, and these skills:

- `kit-status` reads the meters and the mode before a fan-out or a long task.
- `kit-dispatch` hands one briefed unit to a worker and records the review.
- `kit-waste` lists unused agents, skills and MCP servers, and prunes only with the owner's yes.
- `kit-review` weighs findings by reviewer tier.
- `kit-hillclimb` runs a blind hill-climb after the owner approves that capability test.

## Install

Paste the prompt for your agent (Claude Code, Codex CLI or Amp) from [SETUP_PROMPT.md](SETUP_PROMPT.md) into it; the
[kit page](https://claude.ai/artifact/Bwk5gZVa365EMF8jSjN9d5) shows the same prompts behind an agent switch.

With any agent or shell, clone the public releases repository and run the installer:

```bash
git clone https://github.com/hieunguyen7337/coding-tool-optimizer
cd coding-tool-optimizer && bash install.sh
```

Alternatively, download the bundle from that repository's
[Releases page](https://github.com/hieunguyen7337/coding-tool-optimizer/releases) and verify it
against `SHA256SUMS` before running it. The kit is MIT-licensed; see [LICENSE](LICENSE).

### Install or update from an existing checkout

```bash
./install.sh --dry-run && ./install.sh          # from a checkout
bash coding-tool-optimizer-bundle.sh --dry-run && bash coding-tool-optimizer-bundle.sh   # from the bundle
```

Re-running is safe. Once installed, restart any open Claude Code sessions so they load the new
settings. The installer adds these hooks to `~/.claude/settings.json`, each only once:

| Event | Command | What it does |
|---|---|---|
| `UserPromptSubmit`, `Stop` | `turn-meter hook` | Records each turn in `~/.local/state/lanes/turns.jsonl` (`USAGE_OPTIMIZER_TURNS=off` turns it off) |
| `PreCompact` (`auto`) | `turn-meter compact-gate` | Holds a mid-turn compaction until the next turn, below the 350k hard ceiling (`USAGE_OPTIMIZER_COMPACT_GATE=off`, `USAGE_OPTIMIZER_COMPACT_HARD`) |
| `SessionStart` (`compact`) | `turn-meter resume-context` | After a compaction, tells Claude which lane runs are in flight or awaiting review |
| `SessionStart` (`startup`, `resume`, `compact`) | `claude-statusline session-start` | Points the statusline's kit version at the installed release when a session restarts or compacts, since both reload the policy |
| `PostCompact` | `turn-meter hook` | Logs the compaction to `compactions.jsonl` (`turn-meter compactions` reports it) |
| `SubagentStop` (`^lane-`) | `lane hook subagent-stop` | Finishes the record of a `lane --subagent` run |

It also moves `autoCompactWindow` from the kit's old 450k default to 250k. A value you set yourself is left alone.

The installer reports each worker CLI's version but never starts `cline`: starting it, even
for `--version`, runs `npm update -g cline` in a new window, and updates from installs run close
together overwrite each other and break cline. Its version is read from npm's `package.json` instead.

On Windows, run both commands from Git Bash. The installer finds a working Python (the Microsoft
Store `python3` stub is skipped), keeps each Python tool at `~/.claude/usage-optimizer/bin/<tool>.py` behind bash
and `.cmd` wrappers in `~/.claude/usage-optimizer/bin` and `~/.local/bin`, and points the statusline at Python
explicitly. `lane` unwraps `.cmd` launchers so `cmd.exe` never re-parses a brief.

Machine-local configuration lives outside the optimizer, in `~/.config/lanes/`:
- `mask.local`: extra paths to hide from masked workers.
- `bin/`: lane-only executables. `lane` looks here before PATH, so luna and sol can use a current
  `codex` while an older research CLI stays first on PATH. Install creates the folder empty (mode 700)
  and never writes into it. The masked lane (glm) refuses a binary from this folder because
  `~/.config/lanes` is on the mask list. `usage-status` and the statusline read the Codex meter with
  the same binary: `USAGE_OPTIMIZER_CODEX_BIN` if set, else `codex` in that folder, else `codex` on
  PATH.

Reset times in the statusline and `usage-status` use the machine's time zone. A server kept on UTC
can show another zone instead: set `USAGE_OPTIMIZER_TZ` to an IANA name (e.g. `Australia/Brisbane`) in
the `env` block of that machine's `~/.claude/settings.json`.

**Codex meter.** `usage-status` makes a read-only `codex app-server` rate-limit request and caches
it in `CLAUDE_USAGE_DIR` (default `~/.claude/usage`); the statusline renders that cache and refreshes
it in the background. `USAGE_OPTIMIZER_CODEX_BIN` selects the Codex executable, `CODEX_HOME` selects
its state directory (default `~/.codex`), `USAGE_OPTIMIZER_CODEX_TIMEOUT` sets the live-read deadline
(default 30 seconds for background refreshes, 15 seconds for synchronous reads), and `USAGE_OPTIMIZER_CODEX_TTL` sets cache freshness (default 300 seconds,
minimum 60). Set `USAGE_OPTIMIZER_CODEX_LIVE=0` for rollout-only `usage-status`, or
`USAGE_OPTIMIZER_CODEX=off` to hide the statusline segment.
Set `NO_COLOR` (any value) or `USAGE_OPTIMIZER_COLOR=off` to disable statusline colors.

Rules for one particular machine go in `~/.claude/CLAUDE.md`, above the import line.

## Mobile view

The terminal reads like the Claude mobile app: your questions, the sentences Claude writes between
steps and its final answer are shown in full, while tool calls and their output fold away.

- Each tool call is one line: `● Bash  Swipe up, look for the wake prompt  ✗ exit 1`. Click a line
  to show the call and its output in place; click it again to fold it.
- Code blocks longer than 12 lines in Claude's replies fold to `▸ python · 30 lines hidden`; the
  `▸ show code` button under the reply opens them.
- Every question carries its number (`#3`). `>` typed into an empty prompt opens the list of them (the
  footer says so: `← for agents · > for questions`), with the keyboard in a filter box under the newest
  question. Type to filter (`12` or `#12` picks one by number), Enter jumps to the newest match, and Esc
  goes back to the prompt. ↑ walks up the questions with `❯` on the chosen one, Enter
  (or a click) jumps the transcript back to it, and ↓ past the newest returns to the box. In a list taller
  than the pane, ↑↓ still move `❯` and the list scrolls to keep it in view; the wheel and PgUp/PgDn scroll. A question
  from before a compaction is no longer in a reopened session's transcript, so Enter shows its text in
  the list instead (Enter again folds it). The `✕` in the list's corner and ctrl+x x also close it; if
  the list loses the keyboard (you clicked elsewhere), ctrl+x tab, a click or `>` gives it back.
- `>` opens the list over a dim suggested prompt too (Tab or → still takes the suggestion). Claude Code
  places a pane opened by a key alone on a terminal 144 columns wide, or 110 once you have opened the
  list yourself. So on a narrower terminal the first `>` is typed and says to press Enter, which opens
  the list; after that `>` alone works, in later sessions too (narrower than 110, Enter is needed each time).
  To start a message with `>`, type a space first. `>` typed anywhere else in a message is just a greater-than sign.
- Ctrl+O still shows the full transcript. `/mobile-view off` returns to Claude Code's own rendering
  (remembered across sessions); `/mobile-view on` brings the mobile view back.
- The phone view through Remote Control is unchanged; the mod only draws the terminal.

The installer sets these keys in `~/.claude/settings.json` (it backs the file up first and prints
each change): `verbose: false` (verbose prints every command and its output), `viewMode: "default"`
(not the focus view, which hides the text between tool calls), `tui: "fullscreen"` (needed for
clickable rows and the side list) and `outputStyle: "Mobile"`. A key you change by hand afterwards is
kept on later runs; `install.sh --reset-view` sets them again, and `install.sh --no-view` leaves the
whole mobile view alone. Two plugin options tune the mod: `codeLines` (fold code blocks longer than
this, default 12) and `maxGroupLines` (tool rows listed per batch before `… +N more`, default 8); they
appear in the `/config` menu and are stored under `pluginConfigs` in settings.

To remove it: `claude plugin disable mobile-view@skills-dir`, or delete `~/.claude/skills/mobile-view/`
and `~/.claude/output-styles/Mobile.md`, then change the view keys back in `~/.claude/settings.json`
(the installer's backup in `~/.claude/backups/usage-optimizer-<time>/settings.json` has the old values)
and run future installs with `--no-view`.

Developing the mod: `claude plugin validate --strict mods/mobile-view` and `claude plugin test mods/mobile-view`.
The Python tests run with `PYTHONUTF8=1 python -m unittest discover tests` (UTF-8 mode is needed on Windows).

## Sessions view

`/sessions` opens the Sessions pane, and so does `.` in an empty prompt (where Claude Code cannot place a pane from a
key alone, as with the Questions view's `>`, the `.` is typed and Enter opens the pane); the footer hint says
`. for sessions`. The pane asks for the whole terminal, and Claude Code gives a mod pane at most 45% of the width
beside a fullscreen transcript, or as many rows as the layout spares above the prompt; the engine's own agent view is
the only full-screen view. A session the API lists but refuses to open (HTTP 403) shows its row's details, the API's
reason and its claude.ai link. Claude Code reads a 403 naming `untrusted_device` as a session bound to the
computer that started it: only that computer or a device enrolled with `/login` may read it, and a mod's request
carries no device proof, so such a session opens only in the Claude app. A 403 naming `session_stale_relogin` asks for
`/login`, then `r`. The pane lists every session of
your account, local and cloud, grouped by the repository each works on (sessions with none are under Other). Each row
shows its state (working, needs you, review ready, idle, offline, archived), title, kind, branch, age, unread, context
use, model and effort, and its kit role (mirror, side or verify) where the kit's registry knows one. In the list, the
arrows choose a row, Enter opens it, `a` shows or hides inactive sessions, `r` refreshes and `Esc` closes the pane.
Inactive means archived, or a Remote Control session whose local session has ended (the API keeps listing those);
as in the Claude app, they are hidden by default. A cloud session whose VM sleeps stays listed, since it can resume.

The list reads the API's sessions up to 200 (four pages of 50, following the cursor). When more may exist past them,
the status line under the list says `showing the newest N`, N being the sessions read. "Needs you" covers a session
whose newest events hold a held peer message or a permission wait, as well as the states the API reports: the list
reads the newest 20 events of up to 8 sessions per refresh (those not read yet, or changed since: their last event,
else their last update), and the band above the prompt uses the same states. An open session reads its newest 100
events, so its view can find a hold the list's 20 do not reach. A disconnected session shows offline whatever its
events last held.

A row opens its session view: a header (title, repository, branch with head, dirty and unpushed, state, model,
permission mode, context), the transcript folded like the mobile view (one line per tool call, thinking hidden, a
subagent's lines under the call that started them), a composer and the action keys. `Esc` goes back to the list.

- The composer sends a message with Enter (Tab reaches it; while you type there, no action key fires): to a local
  session through the session itself, to a cloud session with `claude -p --cloud`. The text leaves the box only when
  the send succeeds and you have not changed it meanwhile; a failed send keeps it there, with the reason in the notice.
- `p` reads the 100 events before the ones the view shows, and again for each press until the start of the session
  ("No older events" once there are none) or the 2000 events the view keeps. The 4 s refresh of the open session
  keeps the cursor of the oldest page read.
- `o` opens the session in the Claude app, and `c` copies its resume command (`claude --teleport <id>` for a cloud
  session, `claude attach <id>` for a local one).
- `b` fetches the branch from origin and shows `git diff --stat` against the base, when a local checkout is known.
- `r` refreshes now.
- `i` interrupts, `y` approves a held message (shown only when the session needs you), and `m` changes the permission
  mode; these three open the session in the Claude app for now.
- `x` archives through the sessions API. `d` deletes permanently after a second `d` within 10 seconds; when the
  delete endpoint is unavailable, the pane opens the session in the Claude app and asks you to delete it there.

The pane reads the list every 15 seconds and an open session every 4 seconds, twice as long after an error (up to two
minutes), and only while it is open. The sessions API behind it is undocumented: it is the one the Claude app and
Claude Code's RemoteTrigger tool use. When the list call fails for any reason (an HTTP error, no answer, no credential
or an unreadable reply), the pane falls back to local and kit sessions (`ListAgents` and the kit's registry) and says
so under the list.

The setting `band` (Claude Code's plugin options, default off) adds one line above the prompt when a session needs you
(a held message or a permission wait). While the pane is closed it reads the list every two minutes, for that line only.

Developing the mod: `claude plugin validate --strict mods/sessions` and `claude plugin test mods/sessions`.

## Publishing a new version

1. Bump the version line in `POLICY.md`; bump `catalog_version` only when the catalog changes.
2. Run the tests, confirm `lane-stats arms` loads, then run `tools/make-bundle.sh`,
   `python3 -I tools/make-page.py` and `python3 -I tools/check-release.py`. Preview with
   `bash install.sh --dry-run`.
3. When publishing from a machine other than the last publisher, compare the live bundle with the source
   using `python3 -I tools/diff-bundle.py <live bundle> [--kit DIR] [--extract DIR]` and merge differences
   before publishing.
4. Publish the `.sh` bundle as `contentType: "text/plain"` to the same Artifact URL.
5. On every other machine, re-run the setup prompt. See [IMPROVING.md](IMPROVING.md) for the full release,
   research and lessons process.
