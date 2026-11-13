# Claude Usage Optimizer: a usage optimizer for AI coding agents

Claude Usage Optimizer is for anyone who runs several AI coding agents and pays for several subscriptions. It started
on Claude Code, which is where the name and the `~/.claude/usage-optimizer` install path come from.

- **Routes work across the plans you already pay for.** Your main agent plans, reviews and decides. One dispatcher,
  `lane`, sends each written unit to a worker on Claude, ChatGPT (Codex CLI), Google AI Pro (Gemini), Cursor, Grok or
  Amp, through that provider's own CLI and your own login.
- **Meters each plan.** `usage-status` shows what is left in the Claude and ChatGPT windows, the Gemini quota and
  Amp's credits. Cursor and Grok have no account-wide meter, so their cost is recorded or estimated run by run.
- **Records every run.** Usage, list-price cost, time and peak memory go into a ledger, and so does your review of
  whether the result was usable.
- **Learns the cheapest arm.** `lane-stats` compares each model and effort by usable results against usage and time,
  and picks the next one to run.

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
| Mods (mobile view, sessions pane, compact-at-rest) | Yes | No | No |

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

# Claude Usage Optimizer: a usage optimizer for AI coding agents

Claude Usage Optimizer routes coding work across the AI subscriptions you already pay for: Claude, ChatGPT (Codex),
Google AI Pro (Gemini), Cursor, Grok and Amp. The main session runs in Claude Code, Amp or Codex CLI and spends its
plan on planning, review and judgement. Execution and read-only legwork go to cheaper worker lanes, and the remaining
quota of every metered plan is visible.

Every run's usage, cost, time and reviewed outcome is recorded, so the kit learns which model and effort gives a
usable result for the least usage. Claude Code has the fullest support, and the name and the
`~/.claude/usage-optimizer` path come from there; [Platforms](#platforms) says what Amp and Codex CLI get.
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
| `bin/claude-statusline` | A two-line statusline with session context, the running turn's time and share, and the kit's name and version (`Usage Optimizer 2026-10-29.3`, or the release whose policy the session last loaded and the newer one installed) on line one, and grouped Claude/Codex quota windows on line two; colors usage by level, fits the terminal width, and logs Claude's rate limits for `usage-status` |
| `bin/claude-prompts` | Lists the questions typed in a session (`--latest`, `--session-id ID` or `--transcript PATH`; `--text` for people, JSON otherwise). Behind the mobile view's question list (`>`) |
| `mods/mobile-view/` | A Claude Code mod that makes the terminal read like the Claude mobile app (see [Mobile view](#mobile-view)). Installed to `~/.claude/skills/mobile-view/` |
| `mods/sessions/` | A Claude Code mod that opens the Sessions pane (see [Sessions view](#sessions-view)): every local and cloud session grouped by repository, with a session view and its keys. Installed to `~/.claude/skills/sessions/`, with or without `--no-view` |
| `mods/compact-at-rest/` | A Claude Code mod that compacts the conversation right after an answer once the context reaches 90% of `autoCompactWindow`, rather than mid-turn (`USAGE_OPTIMIZER_COMPACT_NEAR` sets the percent, `USAGE_OPTIMIZER_COMPACT_AT_REST=off` turns it off). Installed to `~/.claude/skills/compact-at-rest/`, with or without `--no-view` |
| `output-styles/Mobile.md` | The output style that goes with it: a sentence of narration around each batch of tool calls, no long code in replies, a self-contained final answer |
| `agents/` | `scout`, `digest`, `verifier` and `researcher` subagents (Sonnet, except verifier), and one `lane-<lane>-<effort>` worker per Claude arm for `lane --subagent`, generated from `arms.json` by `tools/make-lane-agents.py` |
| `arms.json` | The arms catalog: each arm is one lane, model and effort, with its status, classes, weight and priors. Machine-local arms go in `~/.config/lanes/arms.local.json`. Installed to `~/.claude/usage-optimizer/arms.json` |
| `LANES.md` | Each lane's raw CLI contract and gotchas, for when `bin/lane` is unavailable. Installed to `~/.claude/usage-optimizer/LANES.md` |
| `settings.fragment.json` | Settings merged into `~/.claude/settings.json`: most only where a key is absent; the view keys (`view_overwrite`) are set, unless you changed one by hand after an earlier install |
| `install.sh` | An idempotent installer that backs up what it replaces. `--dry-run` shows the plan |
| `tools/make-bundle.sh` | Builds `dist/claude-usage-optimizer-bundle.sh`, a single self-extracting file for other machines, and `dist/claude-usage-optimizer-evidence.sh`, the Suite R rescore evidence (FINDINGS section 8) that the kit runs without |
| `SETUP_PROMPT.md` | The prompt to paste into Claude Code on another machine |

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

## Install

With Claude Code, ask Claude to read the [kit page](https://claude.ai/artifact/Bwk5gZVa365EMF8jSjN9d5)
and follow [SETUP_PROMPT.md](SETUP_PROMPT.md).

With any agent or shell, clone the public releases repository and run the installer:

```bash
git clone https://github.com/hieunguyen7337/claude-usage-optimizer-releases
cd claude-usage-optimizer-releases && bash install.sh
```

Alternatively, download the bundle from that repository's
[Releases page](https://github.com/hieunguyen7337/claude-usage-optimizer-releases/releases) and verify it
against `SHA256SUMS` before running it. The kit is MIT-licensed; see [LICENSE](LICENSE).

### Install or update from an existing checkout

```bash
./install.sh --dry-run && ./install.sh          # from a checkout
bash claude-usage-optimizer-bundle.sh --dry-run && bash claude-usage-optimizer-bundle.sh   # from the bundle
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
