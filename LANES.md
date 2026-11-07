# Lane contracts

Reference, not loaded into sessions. `bin/lane` encodes everything here; read it when `lane` is
unavailable, when a lane misbehaves, or when you change `lane` itself. Which lane and effort to use,
the brief format and the failure ladder are in `POLICY.md`. (This was the `codex-delegation` skill
until kit 2026-10-16.1. muse was retired on 2026-10-17.)

## `lane`

```bash
~/.claude/usage-optimizer/bin/lane <luna|terra|sol|astra|gemini|cursor|grok|haiku|sonnet|opus|glm> -C <abs dir> -b <brief file> -e <effort> \
    --class <mechanical|substantive|hard|design|review|research> [--tag <name>] [--pick <id>] [--off-catalog] \
    [--ro] [--resume <id>] [--timeout <sec>] [--dry-run]
~/.claude/usage-optimizer/bin/lane <haiku|sonnet|opus> --subagent -C <abs dir> -b <brief file> -e <effort> --class <class> [--pick <id>] [--ro]
~/.claude/usage-optimizer/bin/lane <haiku|sonnet|opus> --cloud -C <abs dir> -b <brief file> -e <effort> --class <class> [--pick <id>]
~/.claude/usage-optimizer/bin/lane codex-cloud -C <abs dir> -b <brief file> --class <class>
lane-stats pick --class <class> [--pair] [--exclude <lanes>] [--place <process|subagent|cloud>] [--dir <abs dir>] [--brief <file>] [--seed N] [--no-usage] [--json]
lane-stats review <run|last> --outcome accepted|fixed|rework|rejected [--fix-minutes N] [--note <text>]
lane-stats report [--by lane,effort,class] [--since YYYY-MM-DD] [--json]
lane-stats recommend [--class C] [--since YYYY-MM-DD] [--json]
lane-stats arms [--discover]
lane-stats export [--out FILE]
lane-stats import FILE
```

`lane-stats pick` prints the `lane` line to run; `lane-stats explore` is an alias of it. Run that line
with its `--pick` id, so the run is recorded as a pick. `recommend` shows which classes are `exploring`,
`leaning` or `locked` and writes `routing.json`. `export` and `import` pool reviewed runs between machines.

Places. Each lane in `arms.json` has a `places` list: `process` (a local `lane` process), `subagent` (`--subagent`)
and `cloud` (`--cloud`). Claude lanes run in all three; luna, terra, sol, astra, gemini and glm run in `process`
only; `codex-cloud` is `cloud` and stays manual. The places a machine allows are `LANES_PLACES` (comma-separated)
when set, else `explore.places` from the merged catalog (a machine-local override goes in `arms.local.json`), else all
three. `pick` draws only arms whose lane runs in an allowed place, in every draw (forced, floor and Thompson); the
skipped lanes are printed as one line (and as `skipped_places` under `--json`). `pick --place <place>` restricts one
pick to that place and must be an allowed one. The run line names the place: `--cloud` or `--subagent`, or no flag
for `process`. With no `--place`, a lane that cannot run as a process gets the first of its allowed places in
the order process, subagent, cloud. `picks.jsonl` records `place` (the `--place` value, or null).

It writes `brief.sent.md`, `run.log`, `meta.json` and `final.md` (the worker's whole final answer, for every lane
but glm; a Claude cloud run writes `report.md` instead) under `~/.local/state/lanes/runs/<stamp>-<lane>-<dir>/` (`$LANES_STATE` moves the state folder), reads the
provider's meter through `usage-status` before and after (`LANE_NO_USAGE=1` skips it), appends the run to
`ledger.jsonl` there, then prints one line —
`lane=… verdict=… exit=… session=…` — plus `git status --short` of the workspace. Verdicts:
OK · NOOP (did nothing) · QUOTA · PARTIAL (cut off mid-turn) · SANDBOX (shell refused, its gates
are predictions) · FAILED · DISABLED · TIMEOUT · BUSY (task headroom stayed below reserve; exit 70).
A verdict is still a claim: **read the diff.** A Claude lane's NOOP compares `git status --short` and HEAD
before and after, and an untracked file prints the same `?? path` line whatever it holds, so a resumed unit
that only edits files the killed run had already created reads NOOP after real work. Check the files' times
and contents, not the verdict (seen 2026-10-24, resuming runs killed by a memory reap).
NOOP also comes back when the work landed only in git-ignored paths, because `git status` does not list them. When a
unit writes to ignored output, check those paths, not the verdict.

The run also records its `arm` (lane, model and effort) and, for a picked run, `pick_id`. Codex meter
readings store the account's `plan`, so `lane-stats` can tell Pro Lite runs from Plus runs.

Codex runs read the session rollout named by `session_id` and record the observed model, input, cached input,
output and reasoning tokens, credits and list USD using the Codex rate card in `arms.json`. A missing rollout
or unpriced model is recorded in `usage.tokens_error` and does not change the run verdict.

Before a worker starts, `lane` checks task headroom across the cgroup hierarchy and reserves 150 tasks for Codex
or 40 for other lanes (`LANES_PIDS_RESERVE` overrides the reserve). Low headroom is polled every 10 seconds;
after `LANES_PIDS_WAIT` seconds the run is recorded as BUSY with exit 70. Dry runs print current headroom and reserve.

## Subagent runs (`--subagent`; from 2026-10-29.3)

A Claude arm can run as a Claude Code subagent of the main session instead of a `claude -p` process. It then costs this
machine no process of its own (a `claude -p` worker peaked at 0.5–1.2 GB), and it shows live in `/tasks` and
`claude agents`. Where to run what is Routing step 2 in POLICY.md.

1. `lane <arm> --subagent …` does everything a local Claude run does before launch: the arm check, ETA, meters,
   git state and the worker rules. It writes the full brief to `<run>/prompt.md`, whose first line is
   `lane-run: <run>`, and prints one JSON line: `{"subagent_type": "lane-<lane>-<effort>", "description": …, "prompt": …}`.
2. Claude launches it with the Agent tool, in the background, passing that `subagent_type` and `prompt` unchanged.
   The prompt only points at `prompt.md`, so the brief costs the main session nothing to resend.
3. When the subagent stops, the `SubagentStop` hook (`lane hook subagent-stop`, installed with the matcher
   `^lane-`) finishes the run:
   - tokens and list $ from the subagent's transcript (each API message once, priced from `providers.claude.prices`
     in arms.json);
   - the verdict from the workspace's git state, as for a local Claude run;
   - text warnings, meters after, `final.md` and the ledger line, with `place: "subagent"`.
   It warns when the transcript shows another effort than the arm's.
4. `turn-meter` takes the run's list $ out of the main session's turn cost, since Claude Code counts subagent spend in
   the session's total, and lists it as `claude subagents N runs $X`.

- **The definitions.** Each `lane-<lane>-<effort>` agent (`agents/`, generated by `tools/make-lane-agents.py` from
  arms.json) fixes the arm's model and effort and skips CLAUDE.md, so the worker sees the brief, not the policy.
- **Recovery.** A run whose hook never fired (the session closed first) stays without a verdict; `lane --recover <run>`
  finds its transcript under `~/.claude/projects` and finishes it.
- **The session must stay open.** Background subagents carry over when Claude Code restarts, but not past a reboot.
  An unattended run belongs in a process or in the cloud.
- **Memory.** A subagent's transcript stays in the orchestrating session's memory until that session closes: one
  10-hour session with a 36 MB transcript held 1.2 GB. Keep tool output small, and at a clean break move the work to a
  fresh session through a written handoff file rather than `--resume` of the large transcript.

## Cloud runs (`--cloud`, `codex-cloud`; from 2026-10-29.3)

A cloud run works like a local one (`lane` blocks until it ends, leaves the worker's changes uncommitted in the
workspace, prints the same summary line and records `"place": "cloud"` and a `cloud` block in `meta.json`), but the
worker runs in the vendor's Linux VM, so it needs no local memory and skips the memory and task-headroom waits.
When to use it is Routing step 2 in POLICY.md.

**Before it starts**, `lane` refuses (exit 8) unless the workspace is a git work tree on a branch with nothing
uncommitted (untracked files count: a Windows bundle would carry uncommitted tracked files, `.env` included) and an
`origin` remote; a Claude run also needs `origin` on GitHub, and when GitHub lists the apps of the repository's
organization (`gh api orgs/<org>/installations`) the Claude app must be among them: without it the session runs
from a bundle, cannot push, and used to time out after 600 s (seven runs on 2026-10-31). With the app,
`claude --cloud` uploads nothing: the session clones `origin` at the newest commit `origin/<branch>` holds and works
on its own `claude/<slug>` branch, so commits not yet pushed and uncommitted changes never reach it (2026-10-31: a
brief committed locally on top of a pushed commit never arrived, and the session stopped after 22 s). A user-owned repository
cannot be checked this way and passes; `LANES_CLOUD_SKIP_APP_CHECK=1` skips the check, and each time the check cannot
know, `lane` prints one note with the reason. It pushes the branch to `origin`, retrying twice, and a push that fails
while `origin` already holds the same commit counts (two runs started together on one repository race to push it).
Runs on one branch share it: each records its claim under `~/.local/state/lanes/cloud-bases/`, and a branch `lane`
created on `origin` is deleted by the last run to finish, and only while it still points at a commit `lane` pushed. A
failed run's reason is in its `meta.json` (`error`) and at the end of `run.log`.

**Claude (`lane haiku|sonnet|opus --cloud`).** `lane` adds a git contract to the brief and starts
`claude --cloud "<brief>" --model <m> --effort <e> --permission-mode auto` through `bin/lane-term`, because
`claude --cloud` refuses to run without a terminal. Without a mode the cloud session starts in accept-edits; auto is
the user's choice (2026-10-31), and `LANES_CLOUD_PERMISSION_MODE` overrides it. Cloud sessions ignore
`bypassPermissions`: a probe launched with it showed Accept edits in the app, while its auto twin showed Auto
(2026-10-31). Any script that starts `claude --cloud` itself must pass `--permission-mode auto` too. `lane-term` answers Claude Code's folder-trust prompt for the run's own workspace (the local
`claude -p` lanes skip that prompt altogether) and the "Allow external CLAUDE.md file imports?" prompt that the
kit's own import line raises in a new folder (it keeps the preselected No), and stops once `Resume with:` appears.
Scripting an interactive `claude` has three traps, all seen on 2026-10-30:
- **Keys can be lost.** Keys sent on a dialog's first paint can be lost to a redraw that resets the choice to
  "No, exit", so `lane` sends about 2 s of no-op Left presses first.
- **The prompt can be dropped.** In a plain interactive session, a prompt given on the command line is dropped
  after the imports dialog; type it once the input footer (`shift+tab to cycle`) shows. `--cloud "<task>"` keeps
  its task: cloud runs on 2026-10-31 received theirs, a 5 KB brief included, so a script passes the whole brief as
  the prompt, never as a file in a commit it has not pushed.
- **Commas and `=` split the keys.** `lane-term` splits keys on commas and the answer on the last `=`, so typed
  text needs neither. The worker pushes an empty
`lane: start <run>` commit first and `lane: done <run>` last (`... PARTIAL: <reason>` if it could not finish) on
its own branch; `lane` polls `git ls-remote origin` every `LANES_CLOUD_POLL` seconds (default 30), applies
`git diff <start> <done>` to the workspace (from the start marker, so a session that cloned another commit than the
pushed base returns only its own work; `lane` warns when it did), deletes the session's branch, and gives NOOP for an empty diff, PARTIAL
for a PARTIAL marker, else OK. No start marker within `LANES_CLOUD_START_TIMEOUT` (600 s) is FAILED: usually the
Claude GitHub App is missing on a repository the check above could not see (a user-owned one), so the session ran
from an uploaded bundle and could not push; the session URL shows what it did instead. `lane` stops waiting but the
session may go on, so the error ends with "the session may still be running; stop or archive it in the Claude app:
<url>" and the `cloud` block records `"left_running": true` beside `url` and `session_id` (`lane main start`
prints the same sentence after its own START timeout). A file git ignores never reaches the diff, because the
session's `git add` skips it: step 2 of the prompt asks the session to add a file the brief asks for with
`git add -f` and name it in the report, and on a NOOP verdict (Claude and Codex) `lane` checks the paths the brief
names with `git check-ignore`; ignored ones give a `warning: NOOP: ... names paths git ignores (...)` line and
`cloud.ignored_paths` in `meta.json`, and the verdict stays NOOP.
`LANES_CLOUD_KEEP=1` keeps the branches. The session URL is in the run's `meta.json`.
The worker writes its full report into the done commit's body, and `lane` saves it as `report.md` in the run
directory, with its path as `report` in the `cloud` block (from 2026-10-31.6; a done commit without a body leaves no
report). Read reports there: the session's event log (the remote-trigger tool's run log) cuts each message at about
2,000 characters, so the end of a return contract read from it is lost.
A cloud run splits its work across subagents (from 2026-10-31.7). Step 2 of the prompt tells the session to use
subagents (the Agent tool) for as much of the work as splits off: reading and searching files, edits to separate
files, independent test modules. It starts them in one message so they run in parallel, and gives each a narrow,
self-contained brief. The session keeps the plan, the review of every subagent's result and the commits. Step 3 asks
the report for a line `Subagents: <n>` (0 when none) and one short line per subagent. The VM has room (4 vCPU, 16 GB),
and a subagent keeps file dumps out of the main context, where re-reading context is about 55% of Claude spend
(FINDINGS §17). The subagents run on the arm's own model: the prompt passes the lane name as the Agent tool's model,
and a read-only search may use haiku, so the arm's numbers stay honest. When the done commit body has the
`Subagents:` line, the count is recorded as `cloud.subagents` in `meta.json` and as `subagents` in the ledger row;
before 2026-10-31.7, or without the line, there is no key. A verify run (below) gets neither this paragraph nor the
`Subagents:` line: its report must be the commands' verbatim output, which a subagent's summary would paraphrase.
`lane haiku|sonnet|opus --cloud --verify -C <dir> -b <brief> -e <effort>` runs a verifier there instead of a unit,
so test suites run in the cloud VM, not on a short-of-memory PC. Step 2 of the prompt becomes: run each command the
brief lists, from the repository root, in order, with the brief's timeouts, change and commit nothing but the two
markers, and report per command the command, its exit code and the last 40 lines of its combined output verbatim;
the done subject is `lane: done <run>`, or `... PARTIAL: <k> of <n> commands failed`. `lane` never applies the diff:
an empty one is the normal case (OK, or PARTIAL from the marker, never NOOP), and a non-empty one stays in
`cloud.diff` with `warning: verify run changed files; cloud.diff kept, not applied`. The report is printed after the
`lane: cloud report saved to` line. It needs no `--class` or `--pick`; the tag defaults to `verify` and `meta.json`
and the ledger get `"verify": true`. A verify run is not a unit and is never reviewed: `lane-stats` (pick, recommend,
report, eta, review) and turn-meter's "Finished, not reviewed" list skip it, while its spend still counts in
turn-meter's cost totals. `--verify` without `--cloud`, or with a Codex lane, exits 2.
Each provider (claude, codex, gemini) has a usage mode, `saving`, `default` or `utilization` (from 2026-10-31.8). The
setting is the first of `USAGE_OPTIMIZER_MODE`, the first word of `~/.config/lanes/mode` (the folder `LANES_CONFIG`
names, as for `cloud.json`) and `explore.mode` in `arms.json` (shipped `auto` from 2026-10-31.12, `utilization` from .8 to .11); any other value warns and
counts as `default`, and a fixed setting applies to every provider. `auto` picks per provider from the week's pace,
projected = used % / elapsed share of the week (floor 0.05): at or over `explore.modes.saving_pct` (110) is `saving`,
at or under `utilization_pct` (90) is `utilization`, else, or with no reading, `default`; `lane` uses the meter
reading it takes before the run. `lane` prints `lane: mode <mode> (setting <mode>|auto)` on stderr and records
`mode` in `meta.json` and the ledger row. In a Claude cloud run step 2 follows the mode: `default` is the subagent
step above; `utilization` splits the task into as many independent parts as it has, all started at once on the
arm's model, with a test suite split by module, for the shortest time to a usable result; `saving` uses haiku
subagents only to read and search, makes the edits in the session and runs the suite once, at the end. Every mode
keeps the `Subagents:` line. A verify run in `utilization` runs independent commands at the same time and splits a
whole-suite command into up to 4 shards by test module, each reported (and counted in the PARTIAL subject) as its
own command; `default` and `saving` keep the step above. The shards replace the whole-suite run (from 2026-10-31.11):
on 2026-10-31 a session ran both at once in one checkout, and two runs removing the same temporary test file gave a
false PARTIAL (the suite passed alone, 473 tests). The shards must not overlap (from 2026-10-31.15): the release
.14 verify split by glob patterns, `test_[i-m]*.py` and `test_l*.py`, so the `test_l` modules ran twice and the shard
counts summed to 873 where the suite holds 637. Lane now lists the test files of the committed tree once and writes
the shards into a script in the prompt, so each file is in exactly one shard. The session runs that script (it does not
write its own launch line, which once left shards unstarted), lists each shard's files in the report, and checks that
the counts add up. `lane-stats` prices a provider's runs by its mode
(`pace.low_factor` in `utilization`, `pace.high_factor` in `saving`, 1.0 in `default`), and `lane-stats mode
[--json]` shows each provider's mode and why.
- One-time setup (the user's): install the Claude GitHub App on each repository that should run in the cloud
  (claude.ai/code, or github.com/apps/claude, then pick the repositories). With "All repositories", GitHub gives the
  App each new repository at once, but claude.ai's repository picker may not list a new one until the installation
  is saved again (anthropics/claude-code#97337, open on 2026-10-31). `claude --cloud` from a terminal, so `lane
  --cloud` and `lane main`, names the repository from the checkout and does not go through that picker (reported in
  the issue; not yet seen on a kit run).
- Facts behind the design (research note §7–§8): `--model` reaches the session; a session seeded from a bundle
  (only while the App is missing) cannot push, and neither `--teleport` nor `claude -p --cloud <id>` (it only queues a follow-up) returns its work;
  `stream-json` is refused for cloud follow-ups.
- Nothing steers a running session from here (a peer session, 2026-10-31; inferred, not proven). A peer message
  (`SendMessage`) to a session in another permission mode is held for that session's user to approve, and a local
  lead in bypass mode and a cloud session in auto mode differ: the lead's messages reported success, yet none
  appeared in 12 minutes of the cloud session's log while its markers waited on the answers. So a brief carries
  everything the worker needs, and a worker that would need an answer ends with its PARTIAL marker naming the
  question instead of waiting. To answer one mid-run, approve the message in the cloud session's chat or answer
  through git (a commit on its branch that it fetches).
- The VM's proxy refuses some hosts: the Debian mirror `deb.debian.org` returned 403 (2026-10-31). A Dockerfile
  step `apt-get upgrade` cannot run there, so an image scan (Trivy) of a cloud build reports more vulnerabilities
  than the same image built where the upgrade ran. Build and scan images locally, or read a cloud scan as an upper
  bound.
- A cloud session cannot be stopped or archived from a local session: `claude stop` and `claude agents` see only this
  machine's sessions, and the remote-trigger tool only reads. Archive finished sessions in the Claude app. Whether an
  idle cloud session spends usage is not measured.
- A cloud VM's default toolchain can be older than the CI pin: one VM had npm 10.9.4 and `npm ci` refused a lockfile
  written by npm 11. Put the CI's tool versions in the brief and install them before the gates.
- If a repository's agent instructions say workers never push, a cloud run's branch push and its marker commits break
  that rule and each push waits for the owner. Add one standing line there allowing the run's own branches (never main
  or release branches) before the first cloud run.

**Codex (`lane codex-cloud`).** `codex cloud exec --env <env> --branch <branch> -` with the brief on stdin, then
`codex cloud status <task>` every `LANES_CLOUD_POLL` seconds until it exits 0, then `codex cloud diff <task>` applied
to the workspace. The model is Codex Cloud's own (no flag chooses it), so the arm is `manual` and the picker never
sends a unit there. One-time setup (the user's):
- Install the GitHub App "ChatGPT Codex Connector" (github.com/apps/chatgpt-codex-connector) on every owner whose
  repositories Codex may use: the personal account and each organization; in an organization an owner approves it.
- Create and publish an environment for the repository at chatgpt.com/codex/settings/environments (internet for the
  agent: package-manager domains, called "Common dependencies" on older pages). One still marked Unpublished
  cannot run tasks.

Without a `cloud.json` entry, `lane` passes the repository's own `owner/repo` as the environment: `codex cloud exec
--env` takes an environment's name as well as its id, and the one environment on this account was named after its
repository (2026-10-31). An environment with another name goes in `~/.config/lanes/cloud.json`,
`{"codex_envs": {"<owner>/<repo>": "<environment name or id>"}}`, or in `LANES_CODEX_CLOUD_ENV` for one run. When
Codex finds no such environment it starts no task, and `lane` fails with Codex's reason and these steps. The CLI has
no command that lists environments (`codex cloud` offers exec, status, list, apply and diff), but its terminal app
does: `o` (Set Env) opens a picker that shows each environment's name with its id, so
`lane-term --cwd "$(mktemp -d)" --answer "Set Env=text:o" -- codex cloud` reads them without a browser (from a
temporary folder, so the `error.log` the picker can write lands there, not in a workspace). The environment is chosen
per repository, so a GitHub remote is looked up by its own entry or name; the single `codex_env` serves only remotes
not on GitHub (one environment for every repository would run a task in the wrong one and apply its diff here). It
first ran end to end on 2026-10-31: a small task finished OK in 146 s, status polling and the diff apply worked, the new file
landed uncommitted, and origin was unchanged. No model or effort can be chosen: the open-source client's
create-task request carries only the environment, the branch, a QA flag, the text input and best-of-n, so a
`-c model=` override never reaches the server (codex-rs `cloud-tasks-client`, read 2026-10-31; an open issue asks
for model and effort flags). Asked, the agent named its model as GPT-5.6 Sol, an older Sol than the sol lane's;
that is a self-report, not proof. That run's VM had 3 vCPU and about 18 GB RAM (Pro Lite), Linux, Python 3.14, and
internet access, and the checkout was a local branch named `work`. The agent can read image files committed to the
repository (a `view_image` tool), but a CLI task cannot attach images. Codex's weekly meter read the same before and
after, so a small task costs under 1% of a Pro Lite week.

In a second environment it again named its model GPT-5.6 Sol. On one image-reading evaluation (38 comic pages,
2026-10-31) it named the key speaker in 83 of 113 cases, against 113 for opus medium and 112 for gemini low, and
retold the whole story from the images at 96 of 113 against opus medium's 112. Each run took about 5 minutes, and the
two runs moved Codex's weekly meter by 1 point.

Seen on 2026-10-31: after `lane codex-cloud`, and after opening the terminal app's environment picker, `codex cloud`
left an `error.log` in its working directory. It holds the ChatGPT account id and request lines; it made the next
cloud run's clean-tree check fail and could have been committed. `lane` now runs `codex cloud status` and
`codex cloud diff` in the run directory, and when an `error.log` appears in the workspace during a run, it moves it
to `codex-error.log` in the run directory and prints a warning (or, if the move fails, a warning to delete it). An
`error.log` that was there before the run is left alone. `codex cloud exec` still runs in the workspace.

### Mirrors, side sessions and `lane main` (from 2026-10-31.15)

**Two kinds of cloud session.** A *mirror* is a project's main cloud session: one standing session per repository,
started by `lane main`, in auto mode. It plans, splits work into units, runs Claude units as its own subagents,
reviews every diff (a Haiku second reader tries to refute it), runs the gates in its VM and reports each unit's
outcome so the picker learns. The local session on the owner's PC keeps the picks (made with the full ledger), the
Codex and gemini lanes (their logins never leave the PC), the meters, kit installs, publishing, memory and the owner's
approvals for hosted actions. A *side session* is a worker: `lane <claude lane> --cloud`, as described above. When a
repository has a live mirror, its Claude units belong to the mirror (see "Side sessions" below). Where to use which is
Routing step 2 in POLICY.md. The mirror's rules are POLICY.md's section "Main cloud sessions", which `lane main`
copies into the session's prompt.

**Session labels.** The Claude app titles a session from the start of its first prompt, and a brief's own text made
titles that did not say what kind of session it was. So `lane` puts a typed label on the first line of every prompt it
sends to a cloud session, then one blank line, then the prompt as before. The owner (or a handover request) can name a
kind by its first line:
- `Kit mirror - acme/shop`: the project's main cloud session, started by `lane main`.
- `Kit side session - acme/shop - <unit>`: a `lane <claude lane> --cloud` worker started with `--side` while a mirror is
  live.
- `Kit verify - acme/shop - <run id>`: `lane <claude lane> --cloud --verify`.
- `Kit worker - acme/shop - <unit>`: any other `lane <claude lane> --cloud` worker, and a `lane codex-cloud` task (the
  label is the first line of the text sent to `codex cloud exec`).

`acme/shop` is the origin's `owner/repo` (the checkout folder's name when the origin cannot be named). `<unit>` is the
run's `--tag`, or the run id when there is none. The line is ASCII, one line, at most 100 characters. Two other remote
kinds are not kit labels: a *Codex Cloud task* (chatgpt.com/codex) is what the `codex-cloud` lane starts, and appears
there under the worker label; a *Remote Control session* is a Claude Code session running on the owner's own PC that
the phone or claude.ai drives, so it has no VM, no `lane` prompt and no label. The label is a convention the app's
title generator usually follows, not a guarantee: a session may still get a different title.

**How the kit reaches the session.** These facts come from code.claude.com/docs/en/cloud-environments, read on
2026-10-31, and from probes in a cloud session the same day.
- **Only an attached repository is reachable when it is private.** The GitHub proxy of a cloud session serves API
  requests and source archives (`github.com/.../archive/`, `codeload.github.com`) only for the repositories attached to
  that session. For any other repository these routes give 403 "is not enabled for this session", even a public one.
  From a session that did not attach it, `git clone` over https of a public repository worked, and so did fetching a
  file of a public repository from `raw.githubusercontent.com`. A private repository, such as a private kit repository,
  is reachable only from a session it is attached to (`raw.githubusercontent.com` gives 404 for it). `claude --cloud`
  attaches one repository, the project's.
- **An environment cannot add it either.** An environment has Network access, Setup script, Environment variables and
  Network secrets. There is no Repositories setting (an earlier text of this section said there was; it was wrong). A
  setup script runs as root before Claude Code starts, without the environment's variables or network secrets. It is
  cached for about 7 days and is limited to 64 KB. A `~/.claude/CLAUDE.md` it writes loads as user instructions. A setup
  script can still install the kit when it can reach a kit source (the setup script paragraph below says how).
- **Hooks come from the repository.** In hosted VMs, hooks run only from the repository's `.claude/settings.json` and
  from server-managed settings, not from `~/.claude/settings.json`. So a hook written into the home folder never runs
  there.
- **A rebuilt VM starts fresh.** Anything installed in the home folder is gone after a rebuild, so the install must be
  able to run again.

The route that ships follows from these facts. From 2026-11-02.1 the mirror first attaches the kit's own repository
read-only (`lane main` names it in the prompt, from the origin of the checkout `install.sh` recorded, or
`LANES_KIT_REPO`; empty turns it off), clones it and runs its `install.sh`, and installs again when the update notice
names a newer release; the branch below is the fallback. `lane main` pushes a lean copy of the installed kit to the branch
`lane-main/kit` of the project repository, at start and on `--picks`, because the VM is sure to reach that repository,
private or not. The copy leaves out the knowledge pack (`skills/` holds only a README), the raw findings data and
compiled caches, and its `LEAN.md` says why; an unchanged kit pushes nothing, and a push never forces. `--no-kit` opts
out and is remembered for the repository: a start saves the choice, `--picks` reuses it, and a start without `--no-kit`
turns the push back on. In a public repository that branch is public too, which is the owner's choice. A kit installed
before 2026-10-31.18 has no `install.sh` to copy, so `lane` warns and pushes nothing: reinstall the kit, then run `lane
main --picks <repo>`. The mirror's start prompt installs the kit from that branch when `~/.claude/usage-optimizer` is
missing, and prints the install's exit status. `cloud-notify install` adds a SessionStart hook in the repository that
reinstalls it for the mirror when the VM was rebuilt, because only repository hooks run there. The hook acts only for
the mirror: its `.claude/main-session` marker, or, after a rebuild has removed that git-ignored marker too, a transcript
whose first prompts are the mirror's and carry no worker phrase; workers and side sessions never install. If the branch
is missing or the install is refused, the mirror says so in its first reply and goes on with the policy its prompt
carries (below).

**A setup script (from 2026-10-31.18).** `~/.claude/usage-optimizer/bin/cloud-setup --print > cloud-setup.sh` on the
owner's PC prints the script with the kit repository filled in from the recorded checkout's origin (`--repo OWNER/NAME`
and `--ref BRANCH` set it by hand). Paste it, or load the file, into the environment's Setup script (the cloud
environment menu in the session's title bar, then Edit, then Setup script). The committed file names no repository, so
the kit holds no account name. The script clones the kit repository (`--depth 1`, the default branch unless `--ref`)
into `/opt/usage-optimizer/kit`; if that fails, it takes `lane-main/kit` from a project clone under `/home/user`; then
it runs `install.sh --no-view`. It logs each step to `/var/log/usage-optimizer-setup.log` with lines that start
"usage-optimizer setup:", and it always exits 0, so a failed fetch never stops a session from starting. The environment
snapshots the VM after the script and reuses it for about 7 days, so the script runs again only when the cache is
rebuilt (a changed script or allowed-hosts list, or expiry). A new session's kit is therefore as old as the cache. To
update inside a session, run `bash ~/.claude/usage-optimizer/bin/cloud-setup` again: it fetches again from the source it
used and reinstalls. Every session in that environment gets the kit, workers included; a worker's prompt already tells
it to ignore the policy's delegation rules. The mirror's start step 3 then finds the kit installed and skips its own
install, and the repository's SessionStart hook still covers the mirror on a VM that lacks it. The installer writes
`~/.claude/settings.json` before Claude Code starts, so the 250k `autoCompactWindow` is in force from the session's
first turn; a kit installed after start was not picked up until settings were written to the repository's
`.claude/settings.local.json` (observed on 2026-10-31). Not yet known: whether git can reach a private kit repository
during the setup script, and whether the project clone exists yet when it runs. The log of the first session that uses
the script answers both.

**Android builds (from 2026-11-01.4).** `cloud-setup --print --android` prints a script that also installs the Android
command-line tools (version 15859902, SHA-256 checked against developer.android.com), accepts the SDK licences,
installs the SDK packages (default `platform-tools platforms;android-35 build-tools;35.0.0`; choose others with
`--android-packages "..."`, which implies `--android`), writes `/etc/profile.d/android-sdk.sh`, links `sdkmanager`,
`avdmanager` and `adb` into `/usr/local/bin`, puts `ANDROID_HOME`, `ANDROID_SDK_ROOT` and `JAVA_HOME` in the `env` of
`~/.claude/settings.json`, and runs each project clone's `gradlew --version` so the Gradle distribution is in the
snapshot. The image already has OpenJDK 21 with Gradle and Maven, so the JDK step usually skips. For a React Native or
Expo app with native modules, add the NDK and CMake, for example `--android-packages "platform-tools
platforms;android-35 build-tools;35.0.0 ndk;27.1.12297006 cmake;3.22.1"` (match the versions your
`android/build.gradle` names). Two limits from Anthropic's docs (cloud-environments, checked 2026-11-01) shape it:
- **Network.** The default Trusted level allows maven.google.com, services.gradle.org, plugins.gradle.org and Maven
  Central but not dl.google.com, which serves the tools and every SDK package. Set the environment's network access
  to Custom, keep the default list, and add `dl.google.com`.
- **Five minutes.** The environment is snapshotted only when the setup script ends within about five minutes;
  otherwise every new session runs it again from a fresh VM. The script keeps a budget
  (`USAGE_OPTIMIZER_SETUP_BUDGET`, default 270 s), fetches Gradle in parallel with the SDK, skips a part that would
  overrun it, and logs the elapsed time. A skipped part finishes in a session with
  `bash /opt/usage-optimizer/kit/bin/cloud-setup`.

**A cloud meter (from 2026-11-01.4).** A cloud VM has no statusline, so the kit there had no Claude reading and `auto`
could not pace. Now `usage-status`, in a cloud session (`CLAUDE_CODE_REMOTE=true`), runs one probe when the reading is
missing or older than `USAGE_OPTIMIZER_CLOUD_PROBE_MIN` minutes (default 15; `0` or `off` disables): `claude -p --model
claude-haiku-5-5 --setting-sources project,local --strict-mcp-config --output-format stream-json --verbose --max-turns 1
"Reply with the single word OK."` in an empty folder, the argv `lane-bench` already uses. It reads the last
`rate_limit_event` and writes `claude-latest.json` in the statusline's shape with `"source": "probe"`, appending a
changed reading to `claude-rate.jsonl`; a failed probe changes nothing, and a lock (stale after 3 minutes) stops two at
once. `usage-status --probe-claude [--max-age MIN] [--quiet]` runs it anywhere. The `turn-meter` prompt and Stop hooks
start it detached, at most once per 5 minutes, and never wait. `_kit_mode` uses a cloud reading under 6 hours old
(reason `auto, cloud probe reading`). One probe costs about 1-2 cents list. Not yet seen live: a `claude -p` inside a
cloud VM; the first mirror's `usage-status` line shows whether it works, and without it the pick-table rule stands.

In a cloud session, the PreCompact hook allows Claude Code's soft-threshold compaction by default. Setting
`USAGE_OPTIMIZER_COMPACT_GATE=on` explicitly restores the mid-turn gate and its hard ceiling there; `off` disables
the gate everywhere. Local sessions retain the gate by default.

The install step belongs in the mirror's start prompt from `lane main`, which is the owner's own launch. Never send it
in a message relayed from another session. On 2026-10-31 such messages were held until the owner approved them, and in
auto mode the classifier blocked the mirrors' own `bash install.sh`, because it writes into `~/.claude`. If the install
is still refused at start, the mirror says so in its first reply, so the owner can decide what to do.

**The prompt carries the policy.** `lane main` builds the prompt from a fixed head (the protocol and the mechanics
that must match the code) plus two sections of POLICY.md, cut out by the tool: "Main cloud sessions" and "Briefs".
The policy therefore never drifts from the file, and the mirror has its rules before the installed POLICY.md loads
(from the next compaction or VM restart). The text is folded to ASCII for the command line (dashes, curly quotes, the
ellipsis and the math signs have a plain form); any other non-ASCII character in those two sections stops `lane main`
with exit 8 and names the character. The whole prompt must stay under 30,000 characters. It holds no token, no login
and no notification topic. The installed kit holds no ledger, so the picks stay as below.

**How the session gets its picks (design ii).** The local session pushes only aggregates to one branch per
repository, `lane-main/picks`, as a single file `picks.json`: per class, each arm the picker could choose now, with its
review counts and outcomes, usable rate, cost points, minutes and `p_pick` (the picker's own probability for the arm,
which already holds the 20% exploration floor), plus each provider's plan, mode and the weekly reset through which
that mode is current. No run ids, tags, paths, hostnames or briefs go in, and the raw ledger never enters git. The
mirror refreshes the file at its start and before each unit. From 2026-11-01.4 it reads its own Claude meter first
("A cloud meter", above), and that reading wins over the table's mode. Without one it uses Claude's published mode only
through that reset; an expired table falls back to `saving` until a newer table arrives. It draws an arm for each unit with a one-line
python snippet. Why not ask the local session for each pick (design i)? The mirror must work
while the PC is off, and design (i) would block every unit on a local round trip and on a held message (see "Seen on
2026-10-31" below). A picker inside the VM stays in IMPROVING.md's backlog as an upgrade.

**Commands.** `lane` here is `~/.claude/usage-optimizer/bin/lane`. REPO is a repository key (lower-case `owner/repo`
from `origin`) or the path of a checkout. A remote not on GitHub (tests, with `LANES_CLOUD_ANY_REMOTE=1`) has the key
`local/<name of the remote>`.

```bash
lane main -C ~/work/shop -b brief.md [--model opus] [-e xhigh] [--exclude gemini] [--replace] [--timeout SEC] [--dry-run]   # start
lane main --list [--json]
lane main --watch acme/shop [--timeout SEC] [--poll SEC]
lane main --picks acme/shop [--exclude LANES] [--dry-run]
lane main --return acme/shop docs-pass -C ~/work/shop-docs-pass [--verdict OK]
lane main --forget acme/shop
lane main --write-files ~/work/shop
```

- **Start** (`lane main -C DIR -b BRIEF`). The defaults are opus at `xhigh`. It runs the same checks as `--cloud` (clean
  tree, a branch, `origin`, the GitHub App check). The brief travels in the session's prompt, so it needs no commit:
  keep a handover outside the checkout, or list its folder in `.git/info/exclude`, since an untracked file fails the
  clean-tree check and a committed one would publish it. It refuses (exit 8) when the repository already has a live mirror,
  unless `--replace`, which keeps the old entry as `replaced` and reminds you to archive the old session in the Claude
  app. It pushes the base branch, builds and pushes the picks branch (a failure there warns and goes on), and starts
  `claude --cloud "<prompt>" --model M --effort E --permission-mode auto` through `lane-term`, with the same answers and
  `LANES_CLOUD_PERMISSION_MODE` as a worker. Then it waits for a new branch whose history holds the commit
  `orch: START <main id>`, records the session in `mains.json` and prints the session link, the branch and the next
  command. The main id is `<YYYYMMDD-HHMMSS>-main`. The `-b` file is appended last, under "PROJECT BRIEF", as written (UTF-8, like a worker's brief; only the kit's own
  text is folded to ASCII). With no
  START marker within `LANES_CLOUD_START_TIMEOUT` it prints the session URL, exits 4 and writes no entry. `--dry-run`
  prints the preflight result, the repository key, whether a live mirror exists and the prompt length, writes the prompt
  to `main-prompt-<main id>.md` in the state folder, and launches and pushes nothing.
- **`--list`** prints `repo status model/effort since branch url`, one line per live mirror (`no main cloud sessions`
  when empty). `--json` prints all of `mains.json`, replaced entries included.
- **`--watch`** is one poll that ends when something happens (below).
- **`--picks`** runs `lane-stats main-picks`, adds the kit release and repository key, and pushes the file as the next
  commit on `lane-main/picks` (subject `lane: picks <UTC time>`) with git plumbing only (`hash-object`, `mktree`,
  `commit-tree`). It never touches the working tree or the index and never forces a push. Run it after a batch of
  reviews, so the mirror's next draw uses fresh numbers; the start does it once.
- **`--exclude LANES`** (start and `--picks`, comma-separated) leaves those lanes out of the pick table
  (`lane-stats main-picks --exclude`; picks.json lists them under `excluded`). Pass `--exclude gemini` when you start
  the mirror of a private repository or one holding personal data: gemini's consumer terms let Google keep what it is
  sent. The start saves the value in the entry, and a later `--picks` without `--exclude` reuses it. A name the catalog
  has no lane for stops `lane main`, `lane-stats main-picks` and `lane-stats pick` with exit 2 before anything runs: a
  misspelt `gemni` would otherwise exclude nothing and leave gemini drawn. The table also
  holds only arms whose lane runs in a place this machine allows (`explore.places`, `LANES_PLACES`), so a machine that
  allows only cloud and subagent runs hands its mirrors no Codex or gemini units at all.
- **`--return`** hands a local result back (below).
- **`--forget`** deletes the entry. The session itself stays until it is archived in the Claude app.
- **`--write-files DIR`** sets a checkout up for the mirror (below).
- **State.** `mains.json` sits in the state folder (`$LANES_STATE`, else `~/.local/state/lanes/`), written through a
  temporary file of its own, flushed to disk, then `os.replace`; a change to it (start, `--forget`, `--watch` saving
  `last_seen`) holds the lock file `mains.json.lock` (a lock older than 30 s is a dead writer's and is taken over), and
  a watch writes only into the entry of its own main id. An entry holds the main id, `status` (`live` or `replaced`), the session id and
  URL, the branch, the checkout, the remote, the model and effort, the start time, `last_seen` (the sha of the branch
  tip last read) and the older entries under `previous`.
- **Exit codes.** 0 done. 2 usage error (also an unknown or forgotten REPO for `--watch`). 4 FAILED (no START marker in
  time). 8 REFUSED (a live mirror and no `--replace`, a failed preflight, a bad unit name, an unregistered REPO, an
  over-long prompt, a character the prompt cannot carry). 124 `--watch` timed out (`no marker in N seconds`).

**The markers.** The mirror talks to the local session in commits on its own branch (the `claude/...` branch the
session creates), so no message is ever held for approval. The subject line is exactly one of these. Markers carry
statistics only: never brief text, findings, file contents or personal data.

| Subject | Body | Meaning |
|---|---|---|
| `orch: START <main id>` | none | Empty commit; the session's first action. |
| `orch: STATUS <n>: <title>` | short plain message, no secrets | Something the local session should know. `replace me` as the title means the mirror hit its compaction ceiling. |
| `orch: READY <n>: <title>` | what it holds, and what was merged | Finished work; the mirror may already have merged it into the default branch (the owner's standing authorization). |
| `orch: LOCAL lane <unit> <arm> <brief path> class=<class>` | none | Hand-off. The brief is committed in the same commit at `.lane-main/briefs/<unit>.md`. `class=` (from 2026-10-31.16) is the class the mirror drew the arm from; a mirror started earlier sends none. |
| `orch: REVIEW <unit> <outcome> arm=<arm> class=<class> min=<minutes> tok=<in>/<out> usd=<list usd> [fix=<minutes>] [via=local]` | none | One per reviewed unit. |

`<n>` counts the STATUS and READY markers together, from 1. A unit is 1 to 48 characters of `A-Za-z0-9._-`; the
mirror is told to start and end it with a letter or digit, and `lane` refuses a Windows device name (`CON`, `NUL`,
`COM1` ...) because the brief is saved as `<unit>.md`. An arm is `lane/effort`, for example `sonnet/high` (from
2026-11-01): commit subjects carry no model ids, since every cloud session's system prompt forbids them, so `lane
main --watch` and `lane-stats import-orch` take the model from the one catalog arm with that lane and effort. A
subagent marker whose lane and effort match no single catalog arm is not imported (`unknown arm`; a `via=local`
marker names its run by tag instead), and the watch shows such a LOCAL marker as BAD; the full `lane/model/effort`,
which earlier mirrors write, is still read. Each part is at most 64 characters. Only with `via=local` may the arm be
`-`. The outcome is `accepted`, `fixed`, `rework` or `rejected`. The class is `mechanical`,
`substantive`, `hard`, `design`, `review` or `research`. `min`, `usd` and `fix` are non-negative decimals, `tok` is
two non-negative integers, and any `key=value` value may be `-` when unknown. `via=local` marks a unit the local
session ran; the default is `via=subagent`.

The local session answers in two places the mirror reads with `git ls-remote` and `git fetch`:
- **The picks branch** `lane-main/picks` (above), fast-forward pushes only.
- **A result branch** `lane-result/<main id>/<unit>` for each hand-off. Its tip commit subject is
  `lane: result <unit> verdict=<VERDICT>` (OK, PARTIAL, NOOP, FAILED and the other lane verdicts). The mirror fetches
  it, reviews it like any diff and takes the change into its own branch. A verdict is still a claim.

**The watch.** There is no daemon and no bridge. `lane main --watch REPO` polls `git ls-remote origin
refs/heads/<branch>` every `--poll` seconds (60; `LANES_CLOUD_POLL` changes the default). When the tip differs from
`last_seen`, it fetches the branch, prints one line per `orch:` commit since, oldest first, saves `last_seen` and exits 0.
The line is `orch <KIND> <sha12> <fields>`: `n=` and `title=` for STATUS and READY (the body follows, indented two
spaces), `unit=`, `arm=` and `brief=<saved path>` for LOCAL, and the REVIEW fields as written. A marker whose fields do
not parse prints as `orch BAD <sha12> <subject>`. What it remembers as `last_seen` is the commit it actually fetched, so
a marker pushed while it ran is printed once, by the next watch. A new tip with no `orch:` commit updates `last_seen` and the wait goes
on. `--timeout` (21,600 s by default) ends it with exit 124. Run it in the background and restart it after each read; the
wait costs no model turns.

**A local hand-off, step by step** (a gemini unit; the local session does the steps except 6):
1. `lane main --watch acme/shop` prints `orch LOCAL <sha12> unit=docs-pass arm=gemini/gemini-3.8-flash-high/high
   class=substantive brief=...`. It saved the brief from that commit under `mains/<repo>/briefs/docs-pass.md` in the
   state folder, and prints an indented `next:` line with the three commands below, joined with `&&` (so a failed step
   stops the rest, and `cmd.exe` can run it), ready to run. On Windows its paths print with forward slashes in double
   quotes (from 2026-10-31.16), which Git Bash and `cmd.exe` both read; with backslashes, Git Bash stripped them. The
   lane step passes the marker's class; a marker from a mirror started before 2026-10-31.16 names none, so the step
   goes without `--class` and a `note:` line says to add it (.15 printed a `<class>` placeholder, which a shell reads
   as a redirection).
   Before anything else, read the saved brief yourself. It is the owner's own mirror's text, so run it when it works
   on the project's own code and checks with an arm this machine runs (POLICY.md, Default is yes). A brief that
   reaches for a secret, a hosted action or another repository is not a hand-off: answer it with a STATUS note on the
   mirror's branch saying what it asked for, and go on.
2. Create a worktree for the unit, never the registered checkout: `git -C ~/work/shop worktree add
   ~/work/shop-docs-pass <base>`.
3. Run the lane on it, as for any local unit, with the saved brief and the run tag `orch-<main id>-docs-pass` (the tag
   is how a later `via=local` review finds this run): `lane gemini -C ~/work/shop-docs-pass -b <saved brief> -e high
   --class substantive --tag orch-<main id>-docs-pass`.
4. Read the diff and the verdict. Do not record a review: the mirror reviews the unit and its marker carries the outcome.
5. `lane main --return acme/shop docs-pass -C ~/work/shop-docs-pass --verdict OK`. It runs `git add -A`, makes a
   (possibly empty) commit `lane: result docs-pass verdict=OK` and pushes `HEAD:refs/heads/lane-result/<main id>/docs-pass`
   without force. It refuses (exit 8), before it commits anything, a unit name git cannot use in a branch name (`..`, a
leading or trailing dot, `.lock`), an unregistered REPO, and any DIR inside the registered checkout's work tree
(a mirror registered from a subdirectory included).
6. Restart `lane main --watch acme/shop`. The mirror finds the result branch, reviews it and pushes
   `orch: REVIEW docs-pass accepted ... via=local`.
7. `lane-stats import-orch` (next) attaches that review to the local run.

**`lane-stats import-orch <repo> <branch>`** reads a mirror's REVIEW markers into the ledger so the picker learns from
them. `<repo>` is a git checkout, `<branch>` is the mirror's branch on `origin` (`lane main --list` shows it). It
fetches the branch (`--no-fetch` skips that and reads `refs/remotes/origin/<branch>`), reads the commits oldest first
and takes the main id from the `orch: START` commit (none: exit 2). For each well-formed REVIEW it works once per commit
sha, so running it twice adds nothing:
- `via=subagent` (the default): a new run directory `runs/orch-<sha12>/` with `place: "cloud-main"`, the tag
  `orch-<main id>-<unit>`, the arm, class, verdict OK, the minutes and token and list-dollar figures from the marker, and
  the review (outcome and fix minutes).
- `via=local`: no new run. The review attaches to the latest local run with the tag `orch-<main id>-<unit>`; with none it
  prints a warning and counts the marker as skipped.

It prints `imported N runs, M reviews attached, K skipped (reasons)`. A malformed marker is skipped and counted, never
guessed, and nothing else from the branch is stored. Run it after each watch that printed REVIEW lines, then restart
`--watch`.

**A cloud session starts no other session (from 2026-10-31.18).** On 2026-10-31 mirrors called the session tool
`create_session` with no repository and no prompt, which left empty cloud sessions in the owner's list. The
utilization notice had told every session to put its units in a few cloud sessions, and mirrors hold the session
tools. Now a cloud session (`CLAUDE_CODE_REMOTE=true`) starts no other session: the project hook `cloud-notify
guard` denies `create_session`, `create_trigger` with `create_new_session_on_fire`, and a Bash command that runs
`claude --cloud` or `codex cloud exec` (text that only quotes them, such as a heredoc body or a commit message, is
allowed) in every cloud session, and `lane --cloud`, the `codex-cloud` lane and a real `lane main` start exit 8
inside one (dry runs still work). The Bash check reads the command as a shell does (quotes, comments, heredocs,
redirections, `$(...)`, wrappers such as `sudo` and `xargs`, and scripts fed to a shell); it is a guardrail, not a
sandbox, so a launch hidden behind a variable, an alias, `$((...))` or another program is not caught. The
mode notice tells a cloud session to run its units as parallel subagents and to start no other session. A project
that already has the hook gets the guard only when `cloud-notify install --repo <checkout>` runs again and the
result is committed and pushed; a running mirror may not load it until its VM restarts. Setting
`USAGE_OPTIMIZER_SESSION_GUARD=off` in the environment turns the guard and the `lane` refusals off. Side sessions
stay the local session's to start.

**Side sessions.** When the repository's `mains.json` entry is `live` (an unreadable `mains.json` counts as unknown, so
the refusal stays until the file is repaired or the call carries `--side`), `lane <claude lane> --cloud` exits 8 right after
the cloud preflight (dry runs included), names the mirror's URL, and says to run the unit as a subagent of the mirror.
Add `--side "<reason>"` (1 to 200 characters; it is a usage error without `--cloud`) when the unit needs its own VM (a
heavy suite, more memory than the mirror can share, a meter probe that must run alone) or the mirror is stopped or past
its compaction ceiling. The reason is stored as `cloud.side_reason` in `meta.json` and shown in the dry run. A `--verify`
run never needs the flag, and with no live mirror a given `--side` is ignored with a note on stderr. A worker's prompt
now says that its session is a worker and that the kit's policy and tools are held by the project's main session (local,
or a cloud mirror).

**Providers that are absent.** A provider can be turned off for the picker: set `USAGE_OPTIMIZER_PLAN_<PROVIDER>=none`
(`CODEX`, `GEMINI`, `CLAUDE` or `CLINE`), or put `{"codex": "none"}` in `plans.json` in the config folder. `pick`,
`recommend` and `eta` then skip that provider's arms, and `picks.json` lists none of them and shows `"none"` as the
plan. With Codex absent the mirror's hand-offs are for gemini only. `lane main` never calls the Codex CLI, so nothing
breaks while it is logged out.

**Setting a checkout up.** `lane main --write-files DIR` copies the kit's `agents/lane-haiku-*.md`, `lane-sonnet-*.md`
and `lane-opus-*.md` into `DIR/.claude/agents/`, so the mirror can start `lane-<lane>-<effort>` subagents. It skips
identical files, reports changed ones, warns when git ignores `.claude/agents`, and never runs git or edits CLAUDE.md.
It prints the lines to add to the repository's CLAUDE.md, or AGENTS.md if that is the repository's instruction
file (they allow the mirror's own branch, its `orch:` marker pushes and its merges into the default branch, never
release branches; without them, each push waits for the owner). A repository that already gates its default branch
(a push script, CI on the exact commit, a fresh approval per push) keeps its own rules: leave the merge line out,
and its mirror stops at READY. It also points to `cloud-notify install --repo DIR`, which sets up the phone
notifications. The owner commits the result.

**Moving an existing mirror.** Archive the old session in the Claude app (the CLI cannot). Then start the new one with
the old one's state in the project brief: `lane main -C <checkout> -b <hand-over brief> --replace`. The hand-over brief
names the old branch, the units finished and the units still open. `--forget` alone drops the entry without starting
anything.

**Seen on 2026-10-31.**
- Claude's 5h meter moved for an Opus cloud session's own work and for `claude -p` inside the VM, so the cloud-session
  credit did not visibly pay first. Count a mirror's work against the plan.
- Claude caps how many cloud sessions run at once; no number is published. A mirror that fans out to subagents uses one.
- Idle sessions cost nothing (the owner's note of 2026-10-31, not a measurement made while building this). It replaces
  "not measured" in the note on stopping cloud sessions above.
- The Claude app can stop and archive a cloud session; the CLI cannot.
- A message from a local session in bypass mode to a cloud session in auto mode is held for the owner's approval, and
  a cloud session cannot message a local one. Git is the channel, which is why the markers exist.

**Warnings before a start.** `lane main` (a real start and `--dry-run`) checks the commit the VM will clone, not the
working files, and prints a warning on stderr for each gap: the notify hook or `.claude/settings.json` is not committed,
the committed settings do not register the hook, no `.claude/agents/lane-*.md` is committed, or git ignores one of
these files in the checkout (a modified or untracked one already stops the start: the cloud preflight needs a clean
tree, and an ignored file is the gap a clean tree can hide). The VM clones only what is committed, so a hook that is
installed but not committed never notifies the owner's phone. Each warning names its fix (`cloud-notify install --repo` or
`lane main --write-files`, then commit and push); the start goes on, because the files may be deliberately absent.

## Sessions view (`mods/sessions`)

The Sessions pane (`/sessions`) marks lane runs from the lane registry, which `lane` writes and the pane only reads:

- A mirror is the entry for a repository in `~/.local/state/lanes/mains.json` (`{"version": 1, "mains": {...}}`): its
  `session_id`, `url` and `checkout`. A session whose id it holds shows the role `mirror`.
- A side or verify cloud run has a `runs/<run id>/meta.json` with a `cloud` block holding its `session_id` (also
  copied to the top level). A run with `verify: true` shows the role `verify`, and one whose `cloud.side_reason` is
  set (`--side`) shows `side`. Other sessions show no role. The pane reads the 200 newest run folders, under
  `$LANES_STATE` when it is set, and rereads them at most once a minute.

When the sessions API cannot be read, the pane falls back to `claude agents` and the same registry, so the roles still
show. The registry is never written from the pane.

## Cloud notifications (`cloud-notify`)

The main Claude Code cloud session can send a push to a phone through ntfy when it stops, hits an error or needs
input. `bin/cloud-notify` is one stdlib file; `cloud-notify install --repo DIR` copies it to
`.claude/hooks/cloud-notify.py` and registers its hooks there. One of those hooks, `cloud-notify guard`, is not a
notification: it denies session creation in every cloud session of the repository (Mirrors, side sessions and
`lane main`).

Setup, once per cloud environment (the owner's: account settings):
1. Pick a long random ntfy topic. The topic is the password: anyone who knows it can read and send. Subscribe to it
   in the ntfy app, or at ntfy.sh.
2. In the cloud environment's settings, add the environment variable `USAGE_OPTIMIZER_NTFY_TOPIC` with the topic as
   its value. Never commit or print the value. Under Network access, add ntfy.sh (or your own server) to the allowed
   domains. A running session picks the variable up when its VM restarts; a new session has it at once.

Setup, once per repository (before its mirror starts):
3. Run `cloud-notify install --repo <checkout>` (`lane main --write-files` prints the line; from 2026-10-31.16 it starts
   with the kit's python on Windows, where Git Bash resolves the `python3` shebang to the Microsoft Store stub).
4. Commit `.claude/settings.json`, `.claude/hooks/cloud-notify.py` and `.gitignore`, and push them on the branch the
   mirror will start from: the VM clones what is pushed. They hold no secret, so a public repository can carry them.
5. A mirror runs `python3 .claude/hooks/cloud-notify.py mark-main` itself (its prompt says so; only the main session
   creates the untracked marker `.claude/main-session`). To test, ask it to run
   `python3 .claude/hooks/cloud-notify.py push --title Test --message Hello`.

Behaviour:
- The hook sends only in a cloud session (`CLAUDE_CODE_REMOTE` is true), from the main session (the marker exists),
  and when the topic is set. Each hook command ends with `|| true`, so a failure never blocks a tool call or a stop.
- At most one push per event kind (stop, error, input) every 60 seconds. A new prompt starts those windows over, and
  two kinds in one turn both send.
- The push body is the event kind and the repository name only, never transcript, question or error text.
- Events from inside a subagent are not sent: the hook ignores any payload with a non-empty `agent_id`. The hooks
  documentation (https://code.claude.com/docs/en/hooks) does not confirm whether a settings-level Stop hook fires when
  a subagent finishes, so the kit does not rely on that case.
- Other settings: `USAGE_OPTIMIZER_NTFY_SERVER` (default https://ntfy.sh), `USAGE_OPTIMIZER_NOTIFY=off`, and
  `USAGE_OPTIMIZER_NOTIFY_DRY_RUN=1` (prints the request with the topic masked).
- The guard runs in line, not async, so it can deny the call; `USAGE_OPTIMIZER_NOTIFY=off` does not turn it off
  (`USAGE_OPTIMIZER_SESSION_GUARD=off` does).

## Billing of cloud runs (2026-10-31)

Measured with the meters read before and after each run:
- a lane-started Opus cloud session, whose own work ($28.86 Opus list, six subagents) moved Claude's 5h meter by 6
  points and its weekly meter by 2;
- `claude -p` inside the cloud VM ($8.55 Sonnet list) moved the 5h meter by 3 points.

Other sessions ran in the same minutes, so both are upper bounds. The cloud-session credit did not visibly pay first.
Until a clean idle block (no other session running) settles it, treat a cloud run's meter cost as a local run's, and
do not choose cloud for the credit (POLICY.md, Routing step 2).

## Arms catalog

`arms.json` (installed to `~/.claude/usage-optimizer/arms.json`) lists the arms: one arm is one lane, model and
effort. Each entry has a `status`, `classes`, a sampling `weight`, and the priors `prior_pct` and `prior_usable`.
Status is `active` (sampled by `pick`), `manual` (never sampled; a fallback), `retired` (with a `reason`) or
`disabled` (off until a stated condition holds, with a `reason`: the fable arms). There are 29 active arms. The
retired ones are sol `max` and haiku `max`, which score below their `xhigh` on Artificial Analysis v1.5 at a higher
price, and terra `xhigh` and `max`, which cost more than a stronger sol arm (FINDINGS §12). An entry whose classes
were cut carries `classes_reason`: luna `low` and `medium` serve mechanical work only, and terra `low` serves
mechanical, review and research.

An arm may also carry `measured`, one block per class, written by `lane-bench priors --write` from our own
suite runs. When an arm has a block for the class being picked (with `n` at least `explore.measured_min_n`),
`lane-stats` uses its `usable` as the prior at weight `explore.measured_weight` and shrinks with
`explore.measured_shrink`, and its `pct_week` as the cost, tier `bench`, scaled by `plan_scale` when the block's
`plan` differs. Our own reviewed runs and attributed history still take over as they accumulate.

Two `explore` blocks are settings rather than arms. `explore.advisor` holds the Fable advisor: its lane and
model, whether it is `active` (with `inactive_reason`), the default effort of each role, and `weekly_list_usd`, the
Fable list dollars its role calls may spend in 7 days (POLICY.md, Advisor). An `explore` block in
`arms.local.json` replaces the shipped block whole, so a local `explore.advisor` carries every key, `roles`
included. `explore.main_session` is the one
place for the main session's model and effort: install.sh sets `model` and `effortLevel` from it when they are
absent, moves a setting still at a value in `previous_models` / `previous_efforts` to the new one, and leaves any
other value alone; `lane main` starts a mirror on its model without the `[...]` suffix. The Claude window also
carries `model_weight_week`, the weekly weight per list dollar (Sonnet 1, Opus 0.67, Fable 1.69; FINDINGS section 1).

`lane` refuses an arm that is absent, retired or disabled unless `--off-catalog` is passed. Machine-local arms and
overrides go in `~/.config/lanes/arms.local.json`, matched by lane, model and effort. `lane-stats arms`
prints the catalog; `lane-stats arms --discover` also lists Codex and agy models that are not in it yet.
It skips models Codex hides (`codex-auto-review`, `gpt-reserve`), files each model under the lane its family
names (`gpt-5.6-terra` under terra), copies that lane's active arms at the efforts the model offers, and scales
their cost prior by the rate card's output price. A family no lane names gets no suggested arms: it needs a lane
of its own in a kit release.

Run every real unit as a backgrounded Bash call (`run_in_background: true`), several in one tool
block for a wave; each completion arrives as a notification. Never poll, never tail.

## Window epochs and plan dollars

- `arms.json` `providers.codex.window_epochs` lists dated changes to a provider's weekly window: `plan`, `from` (UTC),
  `scale` (a multiplier on the base window), and `source`. The first entry is the Pro Lite doubling: scale 2.0 from
  2026-10-29T16:56:07Z. Plus is not reported doubled.
- `plan_scale` gives the base windows (Pro Lite 1.0, Plus 5.8 in Pro Lite units) and is applied first. `lane-stats`
  turns each run's weekly % into a share of today's window on today's plan. An epoch's scale applies only to runs read
  on or after its `from` time, so older runs keep the window they were read against.
- Points are plan dollars (`explore.points_basis`): a run's share of the window, divided by 100, times the plan's
  monthly price divided by 4.345 weeks, times the mode's pace factor. Reports show the dollar figure as `plan$`
  (`plan$/usable`) only when the provider or plan has a price. `$list` is always the API list value, so the two differ.
- A provider or plan with no price (cline; Codex 'pro') falls back to scarcity: share × scarcity × Claude's plan dollars
  per 1% of its week.
- After a plan change, set `providers.<provider>.prior_plan` in `~/.config/lanes/arms.local.json`, and the plan's
  `plan_prices` entry if it is not listed. `lane` records the plan on every run.

## Kit update (`kit-update`)

- `kit-update check` reads the default branch of the recorded checkout's `origin` (`git ls-remote --symref origin HEAD`)
  and fetches it into the private ref `refs/usage-optimizer/update/<branch>`, so the user's `refs/remotes/origin/*` are
  left as they were. It compares that branch's POLICY.md version with the installed one, and records the result in
  `$LANES_STATE/kit-update.json` (default `~/.local/state/lanes`).
- The statusline runs the check in the background at most every 6 hours. A bundle install records no checkout, so
  there is nothing to fetch.
- The first check that finds a newer release writes a kit notice with the update commands to `$LANES_STATE/notices/`,
  and pushes it once through `cloud-notify` when that is installed. The notice is removed once the installed release
  catches up. `turn-meter` prints at most five notices per prompt and counts the rest.
- A check that cannot run (no checkout, no git, offline) records why and exits 0. `USAGE_OPTIMIZER_UPDATE_CHECK=off`
  turns it off.

## Per-lane contracts (raw forms for when `lane` is unavailable)

### luna — `codex exec` (ChatGPT Pro Lite; Plus from the November billing date)

```bash
codex exec --skip-git-repo-check -m gpt-6-luna -C <dir> -s workspace-write \
  -c approval_policy='"never"' -c model_reasoning_effort='"medium"' -o <final.md> - < brief.md
codex exec <same flags> resume <session-id> - < fix.md        # continue that worker
```

- Pin `-m gpt-6-luna` always (newer codex-cli defaults to a Sol model with far smaller limits);
  `gpt-5.6-luna` is the only fallback. codex-cli < 0.156.1 gets a 400 that reads like an account
  refusal. `lane` runs `~/.config/lanes/bin/codex` when that executable exists, else PATH — put a
  ≥ 0.156.1 client there (terra needs ≥ 0.159.0, sol and astra ≥ 0.159.1) if PATH still has an older pin.
- `approval_policy="never"` is mandatory; otherwise it waits forever on an invisible prompt.
- Flags go before `resume`; `-` reads the brief from stdin (a prompt argument needs `< /dev/null`).
- Session id: `session id: <uuid>` in the header, wrapped in ANSI bold even in a log file (strip
  `\x1b[...m` before grepping). Resume by id, never `--last` (machine-global).
- Quota: Codex exits 0 with `task_complete` even when stopped by quota, so `lane` decides QUOTA from the
  session rollout's `codex_error_info: "usage_limit_exceeded"`; without a readable rollout it falls back
  to a log-tail line that starts with `ERROR:` and names the usage limit, ignoring lines of the worker's
  own `final.md`. Gemini quota matches word-anchored phrases and a standalone `429` only.
- `-s read-only` refuses writes everywhere, `/tmp` included: ask for pipelines and file:line, not
  helper scripts. The sandbox confines writes, not reads.
- The weekly meter moves in whole percents and its reset time drifts by a second between reads, so
  one run's share is coarse: `lane-stats` splits each wave's step by token weight, and the numbers
  firm up over many runs (first wave, 2026-10-17: sol 156k + luna 180k tokens moved it 0% → 1%).
- Effort travels as a request parameter, not prompt text. `xhigh` and `max` render identical
  prompts, yet `max` reasons deeper: Codex's model catalog lists it as a separate level for both
  lunas. A misspelled effort silently downgrades.

### terra — `codex exec -m gpt-6.1-terra` (the same ChatGPT window)

```bash
lane terra -C <dir> -b brief.md -e low --class review    # low | medium | high; xhigh and max are retired
```

- The luna contract applies; needs codex-cli ≥ 0.159.0 (OpenAI, 2026-10-26). Draws 10x luna (half of sol)
  per token: rate card per 1M tokens input/cached/output is 25/1.25/125 credits. Codex lists low to max.
- A tier (2026-10-26) between luna and sol, on Plus and Pro. Plus allows about 35–285 local messages per 5
  hours, against sol's 15–160 and luna's 350–3,000.
- Review (Suite R, 2026-10-28): low, medium and high all found 35 of 38 planted defects, as many as sol xhigh,
  at 0.70–0.91 credits an item (sol xhigh 2.91). Unmatched findings rise with effort (0.43 an item at low, 0.95
  at xhigh), so use low. Code: Artificial Analysis puts it 4–8 points behind sol at the same effort, about sol
  one effort lower at matched cost; `xhigh` and `max` are retired because sol `medium` and `xhigh` beat them
  for less. FINDINGS §12.
- Its review priors are measured (`measured.review` on low, medium and high); the rest are sol's scaled by the
  per-effort ratios (`lanes.terra.prior_basis` in `arms.json`) until reviewed runs replace them.
- **It quits long units early (2026-10-28, 3 of 3 runs).** Given a long update unit (carry a 3,300-line upstream
  diff into 1–3 workflow files, 16–91 checklist items), terra high (twice) and medium (once) stopped after 3–4
  minutes with an honest partial ("the update is incomplete") and `lane` still said OK. A per-item checklist and
  "this unit is long, there is no earlier deadline" in the brief did not change it; sol xhigh finished two of
  them on retry with the same briefs, in about 30 minutes each. Until reviewed runs say otherwise, give terra short units (a
  few items each) and send long ones to sol; read the first line of `final.md`, not only the verdict.

### sol — `codex exec -m gpt-6.1-sol` (the same ChatGPT window)

```bash
lane sol -C <dir> -b brief.md -e xhigh           # low | medium | high | xhigh; max is retired in the catalog
```

- Everything in the luna contract applies: same CLI, flags, session id, quota text, sandbox.
- Needs codex-cli ≥ 0.159.1; `lane` checks. It draws on luna's weekly window (Pro Lite has only a weekly
  one; Plus adds a 5h one) at Sol's credit rates (20× luna per fresh or output token, 10× per cached), but
  reads ~6× fewer tokens per task, so a unit costs ≈ 3–4× a luna run.
- Artificial Analysis coding agents (10-04): low 57 at $0.50 a task, medium 61 at $0.70, xhigh 63
  at $1.04, max 60 at $1.55. On Pro 5x (2026-10-05) `xhigh` is the default; `medium` for a tight brief.
- `max` is a retired catalog entry: it scores below `xhigh` at a higher price, so `lane` refuses it unless
  `--off-catalog` is passed.
- Codex moves from Pro Lite to Plus at the November billing date. On Plus there is a 5h window and a weekly
  one. luna is the plentiful lane; sol and astra are scarce, and terra sits between. On real units sol cost
  27 credits per usable unit (FINDINGS §13), so a Plus week holds about 50 of them: keep sol for open-ended
  code and rescues.

### astra — `codex exec -m gpt-6-astra` (the same ChatGPT window)

```bash
lane astra -C <dir> -b brief.md -e xhigh --class design --tag pair-3
```

- The luna contract applies; needs codex-cli ≥ 0.159.1. Draws 100x luna (5x sol) per token: rate card
  per 1M tokens input/cached/output is 250/25/1,250 credits, against sol's 50/2.5/250 and luna's 2.5/0.25/12.5.
- Artificial Analysis (v1.5, max only): 62 at $7.47 a task, off the frontier. Its value is a second
  frontier perspective on pairs, not cost.

### haiku, sonnet and opus — `claude -p` (the Claude plan)

```bash
claude -p --model claude-haiku-5-5 --effort xhigh --output-format json --setting-sources project,local   --strict-mcp-config --permission-mode acceptEdits --allowedTools Bash Read Edit Write Glob Grep   --disallowedTools Agent Workflow WebSearch WebFetch --append-system-prompt "<worker block>" < brief.md
claude -p --resume <session-id> <same flags> < fix.md          # continue that worker
```

- opus is the same contract with `--model claude-opus-5-5`; its catalog efforts are medium, high, xhigh
  and max. It is the dearest worker: Artificial Analysis v1.5 puts Opus 5.5 max at 66 for $13.04 a task
  (list). Those are priors; `lane-stats report` shows what our own runs cost.

- **Never `--bare`:** it ignores the subscription login and bills `ANTHROPIC_API_KEY` instead.
- The workspace must be outside `~/.claude`: Claude Code treats everything there as sensitive and
  refuses headless edits (the run ends NOOP). `lane` refuses such a workspace for these lanes.
- Each run carries Claude Code's own context, about 80k mostly cached tokens even for a one-line
  edit (Haiku smoke run, 2026-10-17: 79k tokens, $0.0025 at list).
- Use full model ids: the `haiku` alias can still mean Haiku 4.5 off the first-party API.
- Drop `CLAUDECODE` and `CLAUDE_CODE_*` from the child environment; a nested Claude Code misbehaves.
- The JSON result carries `session_id`, `result`, `total_cost_usd` (list price, not what the plan
  charges) and `usage`. The plan's meter is not readable headlessly (`claude -p /usage` is sent to the
  model as a prompt), so the reading comes from the statusline log.
- `--ro` allows only Read, Glob, Grep and Bash; Bash can still write, so read-only is a brief rule here.
- `--web` allows WebSearch and WebFetch (codex: `-c web_search="live"`); `--ro --web` still denies file edits. gemini and glm refuse it.
- haiku: `xhigh` (41, 24% TB at $0.61). `max` is a retired catalog entry: it scores 36 at $2.58 a task, below
  `xhigh`, so `lane` refuses it unless `--off-catalog` is passed.
  sonnet: `medium` 46 at $0.62, `xhigh` 63 at $3.33, `max` 68 at $14.19.

### fable — the advisor (`lane fable --role`; the Claude plan)

```bash
lane fable --subagent --role plan -C <abs dir> -b <brief> --class design   # effort from explore.advisor.roles
lane fable --subagent --role user -e high -C <abs dir> -b <brief> --class review   # a run the user asked for
lane fable --role user --off-catalog -e high -C <abs dir> -b <brief> --class review   # the same while disabled
lane-stats advisor                          # the advisor's state, 7-day spend against budget, outcomes per role
```

- **Disabled (2026-11-01, the owner):** only Fable 5.1 is accessible, and a Fable 5.5 is not confirmed. The three
  arms carry status `disabled`, so `lane` refuses every fable run (exit 8), `--role user` included, unless
  `--off-catalog` is also passed; `tools/make-lane-agents.py` writes no `lane-fable-*` agent, so such a run is a
  process (no `--subagent`). The bullets below describe the lane once the switch rule (POLICY.md, Advisor) enables
  it.
- The opus contract with `--model claude-fable-5-1`. Once enabled, its arms are `manual`: `pick` never
  draws them and a run takes no `--pick`. Places are process and subagent; `--cloud` and `--verify` refuse, and
  `lane main` gives a mirror no `lane-fable-*` agent, since the budget lives in the local ledger.
- `--role` is required: `plan`, `ladder`, `final-review`, `tiebreak` or `user`. It is recorded as `role` in the run's
  meta.json, so `lane-stats report --by role` compares the roles. Without `-e` the effort comes from
  `explore.advisor.roles`; `user` needs `-e`.
- The gate, before anything launches: while `explore.advisor.active` is false, every role but `user` exits 8; so
  does a role call once the last 7 days' role calls (every role but `user`) have spent `weekly_list_usd`. The gate
  counts this machine's ledger; `lane-stats advisor` also counts runs imported from other machines. Otherwise
  `lane` prints `lane: advisor budget $X of $Y used in the last 7 days` and goes on.
- `lane-stats` prices a Fable run at `model_weight_week` fable/opus (about 2.5x) of the calibrated Claude rate,
  which comes mostly from Opus main sessions.

### gemini — `agy` (Google AI Pro)

```bash
cd <dir> && agy --sandbox --dangerously-skip-permissions --add-dir <dir> --output-format json \
  --model gemini-3.8-flash-high --print-timeout 25m --print="$(cat brief.md)"
```

- `--add-dir` is mandatory; `--print` must use `=`; `--mode plan` for read-only; continue with
  `--conversation <id>`.
- Default print timeout (5 min) cuts the turn and still exits 0 — keep `--print-timeout 25m` and
  grep for `print timeout`.
- agy may defer work to background tasks and kill them at turn end (`status: SUCCESS`, nothing on
  disk). Every brief carries the foreground-only execution block (`lane` appends it).
- `Eligibility check failed` in a ~100-byte log is a transient 503: retry once.
- Never wrap it in `nohup setsid … &` when the harness already backgrounds the call.
- Free quota meter: `agy --output-format json --print=/usage` (≈3 s; no tokens).
- Models on Google AI Pro here (`agy models`, 2026-10-17): gemini-3.8-flash low/medium/high, plus Claude
  Sonnet/Opus 4.6 and GPT-OSS 120B, which Google removes on 2026-11-02.
- Handed 38 page images and nothing else, gemini low answered twice that it could not view them; 21 images alone
  worked, and the same 38 images with a transcript worked (2026-10-31). The cause is not known: the image count, the
  total size or the prompt's shape. Split image sets of more than about 20, and check the answer before using it.

### cursor — `cursor-agent` (Cursor subscription)

```bash
cursor-agent -p --output-format json --model grok-4.7-medium --trust --workspace <dir> --force < brief.md
```

- `lane cursor` passes the brief on stdin, never as an argument. `LANES_CURSOR_AGENT_BIN` overrides the executable;
  the fallback is `%LOCALAPPDATA%/cursor-agent/cursor-agent.cmd` on Windows or `~/.local/bin/cursor-agent` elsewhere.
  On Windows that `.cmd` chains cmd.exe, PowerShell (`cursor-agent.ps1`) and node, so `lane` starts the newest dated
  `versions/<YYYY.MM.DD-commit>/node.exe index.js` directly, as the `.ps1` would (it skips the staged-update step,
  which the next interactive start runs).
- Writing runs use `--force`; `--ro` uses `--mode ask`. JSON records `session_id` and usage tokens, but Cursor has
  no account-wide meter or list-cost field. Catalog arms exclude Cursor's `(NO ZDR)` entries and every Claude model.
- **The plan covers some models only** (2026-11-07): GPT-5.6 Sol answered "not included in your weekly usage Buy
  credits or switch to a Grok model", so its arms are retired; composer-2.5 and grok-4.7 run. That answer is QUOTA.
- **No composer** (the owner's call, 2026-11-07): the composer-2.5 arm is retired and the lane's default model is
  `grok-4.7-medium`; its arms are grok-4.7 low to xhigh. A composer run needs `--off-catalog`.
- **Cursor's CLI loads Claude Code's hooks** (`~/.claude/settings.json`): on 2026-11-07 the owner's PreToolUse guards
  (cloud-only tests, release checks) blocked every shell command a cursor worker tried, so it wrote its tests without
  running them. Name what it cannot run in the brief, and run the verifier yourself (in the cloud).

### grok — `grok` (Grok Build subscription)

```bash
grok --prompt-file brief.sent.md --output-format json --cwd <dir> -m grok-4.7 --reasoning-effort medium --always-approve
```

- `lane grok` writes the prompt file in the run record. Writing runs use `--always-approve`; `--ro` uses
  `--permission-mode plan`. `grok-4.7-build-fast` is nominal low effort and deliberately receives no effort flag.
- `LANES_GROK_BIN` overrides the executable; its fallback is `~/.grok/bin/grok` (or `.exe` on Windows). The JSON
  record keeps `sessionId`, tokens and `total_cost_usd`, but never the CLI's `thought` field.

### glm — `cline` (free OAuth lane)

```bash
cline -P cline -m z-ai/glm-5.3-flash -c <dir> --auto-approve true -t 900 "$(cat brief.md)"
```

- `-P cline` is mandatory: another configured provider may sit on a billable key.

## Orchestration lessons

- **Cloud runs share their repository (2026-10-31).** Two cloud runs started 2 s apart on one repository raced to
  push the same base branch, and one came back REFUSED; and the first run to finish would have deleted a branch it
  created while the other still used it. `lane` now retries, counts a push whose commit is already there, and leaves
  the branch to the last run (LANES.md "Cloud runs").
- **A fetch can move its ref and still fail (2026-10-31).** A cloud run read the done marker from the moved ref but
  kept the commit it had seen before, so its diff was empty and it reported NOOP although the work was on the branch.
  Read a ref's sha and subject in one call. A cloud NOOP is a claim like any other: the branch's commits (or
  `git fsck --unreachable` after cleanup) show what the session pushed.
- **Check the GitHub App before launch, not after 600 s (2026-10-31).** Seven design runs on one repository waited out the
  start-marker timeout because its organization had no Claude app; the cloud sessions kept running after `lane`
  gave up. `lane` now checks the organization's apps first.

- **Background session folders.** On 2026-10-07, a restart lost two review files and a build directory.
  Keep briefs, launchers, status files, logs, reviews and builds in a durable project folder; list them
  before a restart.
- **Stopping work does not undo it.** On 2026-10-01, one edit and one queued build survived a workflow
  stop. Check the diff and job queue together, and have the next worker report changes it did not make.
- **Concurrency uses the five-hour window too.** On 2026-09-05, four workflows of about 15 agents each
  started within 25 minutes, exhausted the Claude session window in about 40 minutes, and every agent
  died where it stood. Stagger launches; run at most two heavy workflows at once.
- **Review loops need a stop rule.** Across 68 gated units on 2026-10-02, 74% of verdicts were must-fix
  and 40 never had a clean round. Clean rounds occurred 31% of the time with one reviewer, 9% with two
  and 0% with four or more; rounds three and later cost about 22 agent-hours a week. Tag findings
  blocker, major or style; stop when no blockers remain. Round two is one re-checker of round-one
  blockers only; use at most two rounds and two reviewers.
- **Units that start a service.** A server or database may use the full tool ceiling; this happened in a
  four-package replay on 2026-08-05. Check that the lane can start and wait for the service, or do setup
  in orchestration or a wrapper.
- **Watch long jobs through their output.** On 2026-08-21, a running job had no log after 25 minutes
  because its scheduler delivered the log only at job end. Watch files the job writes while it runs.
- **Classify provider failures from provider signals.** On 2026-09-13, searching all output treated a
  successful call as quota because its session id contained `429`, stopping a 211-call run at 173. On
  2026-10-22, echoed test code led the kit's lane to mark a finished Codex unit QUOTA. Use exit status
  and the provider's own error signal; `lane` now follows this rule. See the luna contract.
- **A reaped background shell leaves its work running.** On 2026-10-22, Claude Code stopped an idle
  session's background install because the machine was critically low on memory, and the `npm install`
  it had started kept running (about 900 MB) after the shell was gone. A background `lane` run can be
  reaped the same way. Before rerunning, check whether the run is still going (no `ended_at` in its
  `meta.json`, `run.log` still growing); if its wrapper died, finish it with `lane --recover <run>`.
  Seen again on 2026-10-29: the notice said both background lane runs were "stopped", but one had already
  finished OK and the other's `lane.py` and `codex exec` ran on. On Windows,
  `Get-CimInstance Win32_Process -Filter "Name='codex.exe'"` (or `python.exe`) shows them with their command lines.
  Starting Claude Code with `CLAUDE_CODE_DISABLE_BG_SHELL_PRESSURE_REAP=1` in its environment turns the
  reaping off; setting it from inside a session has no effect.
- **Automation tools reach the subscriptions only through the CLIs, and should go through `lane`.**
  n8n's AI nodes call the providers' APIs with keys, a separate per-token bill, as does any tool whose
  model node takes an API key. To stay on the plans, a workflow runs the logged-in CLIs. Have it run
  `lane` rather than `claude -p` or `codex exec` directly: the run is then recorded, picked and reviewed
  like any other, uses the per-lane contract (quota signals, the Codex sandbox wrapper, Claude's workspace
  rule), and its spend is matched to the meters it moves. On Windows start `python lane.py` from the kit's
  `bin/`: Node can't spawn the `.cmd` wrapper without a shell (2026-10-22, an n8n "CLI Model" node design).
- **An n8n node built that way works (2026-10-23, n8n 2.44.5 on Windows).** It runs `lane-stats pick --json`
  and then `lane`, reads the answer from the run's `final.md` and its cost from `meta.json`, records outcomes
  with `lane-stats review` and reads headroom with `usage-status --json`. A read-only haiku low run came back
  OK in 4 s for $0.004 list. What it took, and what running it taught:
  - Load a locally built node by copying its compiled files under n8n's own install folder and naming that
    folder in `N8N_CUSTOM_EXTENSIONS` (its type becomes `CUSTOM.<name>`). Loaded from its repo, its
    `require('n8n-workflow')` finds the repo's dev copy instead of n8n's.
  - n8n 2.x warns that running outside its Docker image is deprecated. A container doesn't have the host's
    logged-in CLIs, and mounting their credential stores into one widens what they can reach, so keep n8n on
    the host while that's allowed.
  - A run started from a workflow still needs a review. An n8n Form page after the run shows the answer and
    takes the outcome, so a person grades it and the picker learns from it.
  - To watch and stop runs, run them inside the editor's process. A run started with *Execute workflow* updates
    node by node on the canvas, but only that browser tab gets the updates: n8n pushes node events only to the
    tab that started the run. A run Claude starts through a Webhook trigger (`responseMode: onReceived`) shows
    under *Executions* as running, and with `EXECUTIONS_DATA_SAVE_ON_PROGRESS=true` each node's data is saved
    the moment it finishes. Stopping a run reaches the node's cancel signal. A fake `lane` cancelled by a 15 s
    workflow timeout, which takes the same path as Stop, had its whole process tree killed. Insights counts
    webhook and CLI runs, but not runs started from the editor.
  - `n8n execute --id=<workflow>` runs a workflow headless and exits, and the run is saved for playback, but
    the editor can't stop it. Measured: the editor idles at 450–470 MB, and a headless run peaks at about
    510 MB for its 15–50 s. During a luna run that is more than the lane and the Codex CLI together (about
    280 MB).
  - Every n8n process starts a task broker on port 5679, so a headless run beside the editor or beside
    another run needs its own `N8N_RUNNERS_BROKER_PORT`. Port 0 doesn't work, because n8n gives its runner
    the configured port, not the bound one.
  - `N8N_DISABLED_MODULES` turns off the modules one local user doesn't need, such as enterprise sign-in,
    source control, chat and AI agents. It cuts the editor's start time from 24 s to 16 s. Turning off
    Insights too took idle memory from 447 to 396 MB, but that loses the run dashboard, so keep Insights on.
    Keep `mcp` on as well (next bullet). With `oauth-server` off, its settings page shows a harmless 404 for
    the OAuth client list.
  - **n8n's own MCP server lets Claude drive n8n as a user does (2026-10-24).** The `mcp` module serves
    `/mcp-server/http` from inside the editor's process, so it adds no process. Its tools can:
    - find, read, create (from code), update and validate workflows;
    - run and test workflows, and publish or unpublish them;
    - restore old versions, and read executions.

    Its builder also knows locally loaded nodes (`CUSTOM.<name>`). Turn the server on in Settings >
    Instance-level MCP. A workflow is visible to it only when its settings have `availableInMCP: true`, and a
    run it starts shows under *Executions* like any other.

    It has no tool to stop or retry a run, but the public REST API does: `POST /api/v1/executions/{id}/stop` and
    `/retry`, with a key from Settings > n8n API. That API's `PUT /workflows/{id}` followed by
    `POST /workflows/{id}/publish` also updates a published workflow without the restart `import:workflow`
    needs. Verified: a run started over MCP and stopped through the API partway through ended `canceled`.
  - n8n shows an existing MCP token masked, so a copy of it fails with 401. Only a freshly rotated token is
    shown in full. Give Claude Code the server with a `headersHelper` that reads the token from a file, which
    keeps the token out of Claude's config and out of the conversation. If the server wasn't up when the
    session started, it stays failed until `/mcp` reconnects it. Until then, a small JSON-RPC client on the
    same endpoint (`initialize`, then `tools/call`) reaches the same tools.
  - **Building workflows as code, then deploying them (2026-10-24, workflow SDK 0.37).** Workers wrote the
    workflows as SDK source; a build step validates and compiles them, and a deploy step pushes them. Running
    them live found what neither the validator nor the workers' own tests caught:
    - A Basic LLM Chain with a Structured Output Parser (version 1.3 or later) returns the parsed object under
      `output`, so a later node reads `$json.output.<field>`; without a parser the reply is `$json.text`. Two of
      four worker-built workflows read `$json.text.<field>`, which would have been empty on every run.
    - For a one-label classifier, use a chain with a parser and one check node that turns any answer off the
      list into a fallback label. n8n's Text Classifier gives one output per label and no label field, so it
      needs one Set node per label (34 nodes became 17, and 16 became 9), and a bad reply stops the run where
      an evaluation needs it scored as wrong.
    - The SDK's `.group()` stage frames reach n8n only if the push sends them, and n8n accepts a group only
      when it has one entry and one exit, leaving from a leaf node. A stage that branches (headroom's two
      outputs, a rule match against a model call) can't be one; the push then sends `nodeGroups: []` (leaving
      the key out keeps the stored groups) and the stage stickies frame the stages instead. A build step that
      rewrites node ids must remap the groups' member ids too.
    - The public API refuses an `id` when it creates a workflow, so workflows that call each other by id are
      created with `n8n import:workflow` (which keeps it) and then updated and published through the API.
      Publishing fails for a workflow whose only triggers are manual or disabled; save it unpublished.
    - n8n 2.x leaves out the Local File Trigger by default, so a folder-watching start becomes a form that
      names the file. `N8N_RESTRICT_FILE_ACCESS_TO` takes `;`-separated folders; add the lane runs folder if a
      workflow reads a run's `meta.json`.
    - One evaluation run reads at most 1,000 data-table rows (`MAX_ROWS` in the Evaluation Trigger). A larger
      set runs in batches: delete the rows that already have a result, then start the next run.
    - Measured through the CLI Chat Model, one classification call (prompt, `lane`, both meter reads) took
      7–12 s on haiku low for about $0.0016 list, 27 s on luna low and 41 s on gemini low.
    - `lane` refuses an arm outside the catalog before it makes a run folder, so a caller sees only "no run
      folder" (sonnet low failed this way in 0.4 s). A node's effort list can't know the catalog, so a build step
      should check every fixed lane and effort against `arms.json` and the local additions. The same build step
      should check that every `$("Node name")` in an expression names a node: n8n's validator passes a wrong name,
      and the run fails only when it reaches that node.
    - `lane`'s summary line is a contract: `lane --web` appends ` web` after `class=`, and a node that anchored its
      pattern at the class read every web run as failed, taking the answer's last line (a source URL) for the
      verdict. Parse the line so flags may follow the class. Each side's tests passed; only a live web run met
      both.
- **Claude workers kept auto-memory (fixed 2026-10-24).** Every git worktree of a repository shares
  `~/.claude/projects/<repository>/memory/`, so two workers building in linked worktrees of one repository wrote
  notes there (outside their brief's scope), and those notes would load into the user's own later sessions in
  that repository as if they were the user's memories. `lane` now starts Claude lanes with
  `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`; `--bare` would also turn memory off but drops the OAuth login.
- **A finished run could crash on its last write (Windows, fixed 2026-10-24).** `lane` writes `meta.json.tmp`
  and renames it over `meta.json`; Windows refuses the rename ("Access is denied") while another process has
  either file open, and Python opens files without delete sharing. `lane-stats` and `turn-meter` read every
  run's `meta.json`, and a virus scanner opens new files. Three of 1,325 runs died this way after the model
  had answered (verdict OK in the `.tmp`), so the caller saw no summary line and the call was lost; two of
  them finished in the same second. `lane` now retries the rename for up to five seconds. A run folder
  holding a `meta.json.tmp` is one of these.
- **Git deletes through a junction (Windows, 2026-10-24).** Worktrees that share one heavy install (a runtime,
  `node_modules`) through directory junctions must lose the junctions before `git worktree remove`. Git for
  Windows treats a junction as a plain directory, so it deleted the shared install's files in name order (361
  packages) until a path past 260 characters stopped it, and its error ("Filename too long") names only the
  worktree. Unlink each junction alone (`[IO.Directory]::Delete(<path>, $false)` or `cmd /c rmdir <path>`, never
  a recursive delete), check that no reparse point is left, then remove the worktree, and check the unlink step's
  own exit status: a missing `pwsh` piped into `tail` exits 0. To repair, delete the half-deleted package folder
  first (npm treats a folder whose `package.json` survived as installed), then `npm install` from the lockfile. It
  restored every package but also re-resolved part of the tree (66 changed, 132 removed), so judge the result by
  loading the code (every n8n node file loaded), not by `npm ls`, which also flags n8n's own peer conflicts.
- **The Codex sandbox on Windows refuses a nested process (2026-10-24).** Inside a Codex lane the shell starts
  `node` normally, but a Node script calling `spawnSync(process.execPath, …)` gets `EPERM`, so a verifier that
  runs a helper subprocess fails for every Codex arm while the Claude lanes pass. luna then stopped at a 94-line
  draft with a parse error it had seen. Give such a verifier an in-process path that it takes when the spawn
  errors, and check that both paths print the same output; until it has one, a Codex arm's failure on that unit
  is the harness's, not the model's.
- **Codex on Windows reads UTF-8 as ANSI (2026-10-24).** Its shell is Windows PowerShell 5.1, whose `Get-Content`
  decodes a UTF-8 file without a byte-order mark in the ANSI code page. A worker that read a spec that way and
  copied its text into output wrote `Â·` for `·` and `â€“` for `–` in 31 of 58 names, and its own tests passed.
  Tell Codex workers on Windows to read with `Get-Content -Encoding UTF8` or Python's `encoding="utf-8"`, and make
  the verifier reject the signatures (`Â` or `Ã` before a byte 0x80–0xBF, `â€`, U+FFFD).
- **PowerShell writes a byte-order mark or UTF-16 (2026-10-28).** `Set-Content -Encoding UTF8` starts the file
  with a byte-order mark and `Out-File` writes UTF-16. On Suite R terra wrote 103 of 116 `findings.jsonl` files
  with a mark, and a reader that opens them as plain UTF-8 fails on the first line (the grader scored them as
  missing). Write through `apply_patch` or `[IO.File]::WriteAllText(<path>, <text>, [Text.UTF8Encoding]::new($false))`,
  and read machine files with `utf-8-sig`.
- **`exec_command` returns after about 10 s (2026-10-28).** That is normal: strong models poll the running
  command. On a busy host PowerShell took up to 15.7 s just to start, terra low read the empty output as done and
  ended its turn before writing, and 4 of 24 findings files were lost. Ask every worker to read back each file it
  wrote before it finishes.
- **`lane` now handles these itself (2026-10-28).** On Windows every Codex brief gets a rule after the process
  rule: read and write UTF-8 without a mark, wait for a command that returned early and read back every file,
  and run a step directly when a child process fails with EPERM. After the run `lane` compares each changed text
  file with `HEAD` (or, outside git, each file newer than the run's start) and prints `warning: <file>: …` for a
  newly gained byte-order mark, UTF-16 or garbled characters; the list is `text_warnings` in `meta.json`. A
  warning is not a verdict: read the file. Luna's four failures on real units here split into two that quit early
  (medium and high, after 12 and 20 tool calls) and these two harness cases (FINDINGS §13).
- **A Claude lane on Windows can save whole files with CRLF (2026-10-30).** A sonnet medium run that edited
  `bin/claude-statusline` left all 817 of its lines ending in CRLF and wrote its new test file the same way, while
  every test passed. Where git normalises (`* text=auto`, `core.autocrlf=input`) the commit is still LF, but the
  working copy and any repository without normalisation see every line changed. From 2026-10-29.3 `lane` warns
  `changed to CRLF line endings` (or `new file with …`) unless git itself checks the file out with CRLF
  (`core.autocrlf=true` or an `eol=crlf` attribute). Convert the file back before committing.
- **Hook test JSON and git chains on Windows (2026-10-31).** To feed a hook test JSON, pass it from Python with
  `subprocess` input: piping it from a PowerShell function delivered empty stdin. Likewise, a worktree-isolated
  Claude Code session refuses a Bash command that chains git with other commands or carries `;` inside a quoted
  argument: run git alone and put multi-step work in a saved script.
- **`lane-bench` on Windows (2026-10-28).** `Popen` cannot start the kit's extensionless `#!` scripts, so
  `lane-bench` starts each helper through its `.cmd` wrapper, `sys.executable` or Git Bash, and kills a run's
  process tree with `taskkill /T /F` (`os.killpg` does not exist there). `export` reads the graded summary in
  Python where `jq` is missing or on Windows (whose `timeout` is a different program), with the same fields as the
  `jq` query. All of its tests pass on Windows.
- **`pick` read no live usage on Windows (found and fixed 2026-10-29).** An installed tool is `bin/<tool>.py`
  behind the bash wrapper `bin/<tool>`; `lane-stats` started `python bin/usage-status`, which is the wrapper, got
  a SyntaxError and fell back to no data without a word. Every pick on Windows before 2026-10-29.1 therefore used
  pace factor 1 and never skipped a provider at its limit. Tools now start a sibling's `.py` when it exists.
- **Every run prints its ETA (2026-10-29).** `lane: eta ~14 min (p80 25; measured, 9 runs)` comes from
  `lane-stats eta` before the worker starts (`LANE_NO_ETA=1` skips it), and the run's end prints the time it took
  against it. Wait for a background run once, after about its ETA. A tagged run (a bench item, a classification
  call) is estimated only from runs with the same tag: those take 0.1–1.2 minutes against 4–30 for a real unit.
- **Every run waits for memory (2026-10-29.2).** On 2026-10-24 parallel builds on one machine ran it out of memory
  and a reap killed 6 jobs. `lane` now records `peak_mem_mb` for the worker and everything it starts (a Windows
  Job Object's peak commit; on Linux the summed RSS of the worker's session, sampled), and before launching it
  checks that the free RAM, less the reserve and the runs that have only just started, covers the lane's median
  peak. A BUSY 70 from it means nothing ran: start the unit again when a lane finishes, or lower the reserve with
  `LANES_MEM_RESERVE_MB` if the machine has room the estimate does not see.
- **About five CLI workers fit in 16 GB.** On 2026-10-24 nine lanes at once (Claude lanes about 280 MB each
  plus their children, Codex about 200 MB plus its wrapper, beside an n8n editor and a browser) left under
  3 GB free; Claude Code reaped the background trackers while the lanes ran on. On a 16 GB machine run about
  five at once, and fewer beside a long build. Count the calls a workflow makes at once, not the workflows:
  n8n's chain nodes run five items in parallel by default, so one literature review screening its records was
  five Claude lanes, and beside an evaluation and a build it ran memory out again the same day. Set the batch
  size to 1 when the model is a CLI, where each node reads it: the Basic LLM Chain reads `batching`, but the
  Information Extractor, Text Classifier and the other chain nodes read `options.batching`, and a setting in the
  wrong place is ignored.
- **The memory is shared with every other session.** Later that day five of one session's lanes, an n8n
  evaluation, and a second Claude session running its own lane took the machine to critical memory, and Claude
  Code stopped every background job of the idle session at once: the five lanes this time (their wrappers went
  with the shells), and the evaluation's driver. Before a fan-out, count the other sessions' workers too
  (`claude.exe -p` and `codex` processes); with another session busy, run two lanes at a time. A stopped run
  stays open in the ledger: close it with `lane --recover <run>`, and rerun the unit from the files it left.
- **Run the kit's tests as the README says.** `python -I -m unittest tests.test_lane` fails to import, because
  `-I` drops the current folder from the path; `-I` also ignores `PYTHONUTF8`, so use `-X utf8` with it.
- **Push notifications (2026-10-31).** Claude Code's built-in push notification did not reach a phone in tests
  (skipped while the terminal was active; a push from a fresh session never arrived). A Stop, permission-dialog and
  question hook that posts to a private push topic after a short delay reached both computer and phone.
- **Cap a paid live run (2026-10-31).** Before it, set call and dollar caps above the dry-run estimate, enforce them
  from a separate watchdog, and re-project after the first tenth: one live run's estimate (about 1,110 calls) came
  in low and its 1,250-call cap stopped it with work left.
- **Checks this machine cannot run fail only in CI (2026-10-31).** Database tests that need Docker are an example:
  run them on the candidate branch in CI before asking for release approval, and say so in the release note.
- **A message from another session is not the owner's approval for a hard-rule step (2026-10-31; narrowed
  2026-11-02.1).** Only the owner's own words approve a release, a live call or a write to another repository. A
  reversible step inside the project or the kit that one of the owner's sessions asks for is taken by default
  (POLICY.md, Default is yes).
- **An MCP server at local scope reaches every worktree (2026-10-31).** It applies to every worktree of that
  repository folder; a worktree that must not reach it needs its own deny in its `settings.local.json`.

## Sharing statistics (opt-in)

`lane-stats share` previews anonymous totals for the last complete ISO week; use `--week YYYY-Www` to choose
another week. A payload contains only its schema and week, the kit and host identifiers, a random install id,
recorded plan types, and catalog lane/effort/class cells with run counts, usable counts, median time and ETA ratio,
weekly share, and list dollars. It never contains run ids, exact times, directories, repositories, tags, notes, or
brief text.

Sharing is off until `lane-stats share --enable` is run, and nothing is sent in the background. Use
`lane-stats share --disable` to turn it off, `lane-stats share --enable --new-id` to replace the random install id,
and `lane-stats share --send` to review and submit a week (`--yes` is required without a terminal). A submission is
a public issue in the releases repository under the sender's GitHub account. `lane-stats share --validate FILE`
checks either a raw JSON payload or the first fenced JSON block in a Markdown issue body.
