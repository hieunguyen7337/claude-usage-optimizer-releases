# Cloud sessions for Codex and Claude Code as worker lanes (main session, Opus, 2026-10-29)

Sources read on 2026-10-29 (the vendor pages carry no dates). Two web researchers gathered them; the main session
re-read the load-bearing pages and checked each CLI's own `--help` (codex-cli 0.165.0, Claude Code 2.1.312).
The question: can workers run in the vendors' clouds instead of on this machine, whose memory (16 GB) caps how
many local workers run at once, and does that cost anything beyond the plan meters?

## 1. Usage: the same meters

- **Codex.** "Local messages and cloud chats share your plan's usage allowance." "Cloud tasks may use more of your
  allowance than local messages." The page publishes per-plan estimates only for local messages, and the old
  local-vs-cloud task table is gone, so a cloud task's weight is unknown until measured.
  https://learn.chatgpt.com/docs/pricing.md
- **Claude.** A cloud session "counts toward your plan's usage limits alongside the rest of your Claude and Claude
  Code usage, and there's no separate charge for the cloud VM"; parallel sessions use the limits proportionately.
  https://code.claude.com/docs/en/claude-code-on-the-web
- **Claude routines** (now "cloud scheduled tasks") "draw down subscription usage the same way interactive
  sessions do". https://code.claude.com/docs/en/routines
- **Promotional credit, Claude.** When cloud sessions left research preview on 2026-09-23, Anthropic gave Pro
  subscribers $100 and Max subscribers $250 of credit for cloud sessions only, for subscriptions active that day:
  claimed by 2026-10-07 (claude.ai/code or `/claim-credit`), spent before plan usage, and any balance expires on
  2026-11-04 (some posts say 11-05). Anthropic: "If you hit a limit locally, keep going in the cloud until your credit
  runs out." Whether it covers routines is unconfirmed (one blog says it does not). An earlier promotion (Pro $250,
  Max $1,000, Claude Code on the web) ended 2025-11-22. BleepingComputer 2026-09-25,
  https://bleepingcomputer.com/news/artificial-intelligence/anthropic-rolls-out-up-to-250-in-free-claude-code-credits-but-only-for-cloud-sessions
  (main session re-read it); @ClaudeDevs on X 2026-09-24 (search snippet only).
- **No standing free pool.** Claude's "usage credits" are prepaid overage at API rates, and the monthly API credits
  of Max and Team plans do not apply to Claude Code. OpenAI has no current free cloud credit: it granted $200 to Plus
  and Pro users who had used cloud tasks in the month before 2025-11-07 (expired), and past the plan limits cloud
  tasks are paid with purchased ChatGPT credits. https://support.claude.com/en/articles/12429409,
  https://learn.chatgpt.com/docs/pricing

## 2. The VMs

| Vendor | Plan | vCPU | RAM | Disk |
|---|---|---|---|---|
| Codex | Plus | 2 | 8 GiB | 8 GiB |
| Codex | Pro, Business, Enterprise | 4 | 16 GiB | 32 GiB |
| Claude | every plan (approximate, "may change") | 4 | 16 GB | 30 GB |

Both are Linux and clone the repository from GitHub (GitLab and GitHub Enterprise Server are unsupported for
Codex; Claude can upload a local bundle instead). Codex keeps a task's VM state recoverable for 7 days; a Claude
VM pauses when idle and is reclaimed later, keeping the conversation but not running commands.
https://learn.chatgpt.com/docs/environments/cloud-environments, https://code.claude.com/docs/en/cloud-environments

## 3. Limits besides usage

- Claude: an organization-level limit on cloud sessions running at once (no number published; a run "can fail to
  start" when it is reached), and per routine 30 runs an hour from Run now and API fires combined; 100 API fires an
  hour per account. Claude Code changelog 2.1.302; https://code.claude.com/docs/en/routines
- Codex: no published concurrency limit or maximum task duration.

## 4. Starting a worker from a script

- **Codex works end to end.** `codex cloud exec --env <id or label> [--branch <b>] [--attempts N] <prompt | ->`
  returns at once and prints the task URL; the branch must be on GitHub. `codex cloud status <id>` exits 0 only when
  the task is ready; `codex cloud diff <id>` prints the diff and `codex cloud apply <id>` applies it;
  `codex cloud list --json` gives each task's `environment_id`. There is no model or effort flag and no page says
  which model cloud tasks run, and no command lists environments (openai/codex issue 24777).
  https://learn.chatgpt.com/docs/cli/reference
- **Claude: a pseudo-terminal or a routine.** `claude --cloud "<task>"` refuses to run without a terminal ("--cloud
  requires an interactive terminal"), and `winpty` fails when the caller has no console. Run under a ConPTY
  pseudo-console (Windows' `CreatePseudoConsole`, the way terminal emulators host a program, with the child's std
  handles set invalid so it takes the console's), Claude Code 2.1.312 created the session, printed "Created cloud
  session", the `https://claude.ai/code/session_…` URL and a `claude --teleport <id>` line, and exited after 8 s
  with no prompt (measured 2026-10-29, §7). `claude -p "<message>" --cloud <session id> --output-format json` only
  sends a follow-up to an existing session. The other scripted route on Pro and Max is a routine with an API trigger: a POST to
  `https://api.anthropic.com/v1/claude_code/routines/<trigger id>/fire` (bearer token, beta header
  `experimental-cc-routine-2026-04-01`, body `{"text": "<brief>"}`) returns the session id and URL. The text
  reaches the routine wrapped as untrusted data, so the routine's saved prompt must say to act on it. Model, effort
  and repositories are fixed per routine, and the trigger and its token are created on the web only. Results come
  back as a pushed `claude/` branch. Self-hosted environments (`--environment ccpool_…`), which do allow a scripted
  create, are Team and Enterprise only. https://code.claude.com/docs/en/routines,
  https://code.claude.com/docs/en/self-hosted-environments-testing

## 5. Data

- A Claude cloud session follows the same data policy as local Claude Code (the consumer training setting applies).
  Without a GitHub remote or the Claude GitHub App, `claude --cloud` uploads a bundle; on native Windows that bundle
  includes uncommitted changes to tracked files whatever their name, `.env` included (macOS, Linux and WSL filter
  credential-like files). A cloud lane must push a branch, or upload a bundle only from a tree with no uncommitted
  changes (`git status --porcelain` empty), as the §7 probe did. With both, it uploads nothing and the session
  clones from GitHub (§8, observed 2026-10-31).
  https://code.claude.com/docs/en/claude-code-on-the-web, https://code.claude.com/docs/en/data-usage
- Codex cloud tasks follow the ChatGPT data controls (community summary of a help article; not verified first-hand);
  OpenAI support said on 2026-06-02 that log retention "is still under discussion".

## 6. What it means for the kit

Cloud gives workers memory and CPU this machine lacks, a Linux harness (half of luna's Windows failures were the
harness, FINDINGS §13), and isolation from local credentials, but no extra allowance: the meters, not the VMs,
still bound how many runs go at once. The main session stays local. `lane --cloud` (Claude) and `lane codex-cloud`
run units there from 2026-10-29.3 (LANES.md "Cloud runs"); what is still to measure is in IMPROVING §10.

## 7. Measured: one Claude cloud probe (2026-10-29)

One session on Max 20x, started from a clean kit worktree under ConPTY, asked to run `date -u; cat /proc/uptime;
nproc; free -m; time python3 -m unittest tests.test_lane_stats; date -u` and change nothing.

| Seconds after launch | Event (session event log) |
|---|---|
| 0 | `claude --cloud` started on this PC |
| 7.8 | session created, prompt recorded (repository uploaded as a seed bundle: no GitHub App for this repo) |
| 7.9 | sandbox allocated |
| 10.4 | repository cloned from the bundle; no setup script; Claude Code started on a warm spare VM (uptime 51 s) |
| 12.0 | Claude Code ready, model `claude-opus-5-5` (the account default) |
| 15.9 | first command ran |
| 27.1 | reply finished (2 turns, 15 s of session time) |

- **VM:** 4 vCPU, 16,091 MB RAM (15,668 MB available), no swap.
- **Speed:** the same 56-test module took 6.9 s in the cloud and 33.8 s on this PC (Windows, 8 logical CPUs), 4.9x
  faster. The module starts many subprocesses, and process start-up is slower on Windows [INFERRED].
- **Reading a session:** the session's event log (prompt, provisioning steps, each tool call and result, the reply)
  is readable by session id from a Claude Code session (its remote-trigger tool, `get_run_log`), not only for
  routine runs.
- **Not measured:** getting a diff back, a setup script, a GitHub clone instead of a bundle, a cold VM with no warm
  spare, how many sessions run at once, the meter weight of a cloud session against a local one.

## 8. Measured: model choice and the way back (2026-10-29)

A second probe (a throwaway one-file repository with no GitHub remote) asked a session to edit a file, add one,
commit and not push. What it showed:

- **`--model` reaches the session.** `claude --cloud "<task>" --model claude-haiku-5-5 --effort low` started a session
  whose event log says `model=claude-haiku-5-5`; the log does not show the effort. Launch to the first command was
  6.6 s from session creation, again on a warm spare.
- **A new folder asks for trust first.** In a folder Claude Code has not been told to trust, `claude --cloud` stops at
  "Quick safety check: Is this a project you created or one you trust?" with "No, exit" preselected, and starts
  nothing until answered (Down, Enter). Trust is per folder: a trusted parent does not cover a new subfolder.
- **Nothing comes back from a bundle-seeded session by itself.** Its commit stayed in the VM. `claude --teleport <id>`
  validated the session, fetched its logs, "checked out" its branch and resumed the conversation locally, but the
  local repository was unchanged, since there was no remote branch to fetch; the local transcript it wrote held only
  a title, the remote turns being shown on screen only. `claude -p "<msg>" --cloud <id> --output-format json` queues
  a follow-up and returns at once with `{"ok", "session_id", "url"}`, no reply; `--output-format stream-json` is
  refused for cloud follow-ups. The follow-up did run, and its exact command output is in the session's event log,
  which only Claude Code's own tools can read with the user's sign-in.
- **So the way back is git through GitHub.** With the Claude GitHub App the session clones from GitHub and can push
  its own branch; `lane --cloud` has the worker push marker commits (`lane: start <run>`, `lane: done <run>`) and
  watches the remote for them (LANES.md "Cloud runs").
- **With the App, unpushed work stays behind** (a peer session, 2026-10-31). Once the App was on the repository's
  organization, `claude --cloud` uploaded no bundle. It printed that the branch was not on GitHub, so the session
  would start from the newest commit beneath it that `origin/<branch>` has, and that commits origin lacks and any
  uncommitted changes stay on this machine. The session cloned from GitHub and made its own `claude/<slug>` branch.
  A brief committed locally on top of a pushed commit never arrived: the session found no brief and stopped after
  22 s. The same brief passed whole as the prompt (about 5 KB) ran. So push the branch first, and pass the brief
  as the prompt, not as a file in an unpushed commit; `lane --cloud` does both.
- **Peer messages do not reach a cloud session in another mode** (a peer session, 2026-10-31; inferred from one
  log). The `SendMessage` tool says a session in another permission mode holds peer messages for its user's
  approval. A local lead in bypass mode messaged a cloud orchestrator in auto mode for 12 minutes: each send
  reported success, none appeared in the orchestrator's log, its turns began only with its own subagents'
  hand-backs, and its markers kept waiting on answers already sent. A one-way channel to a cloud session is then
  the owner approving each message in the cloud chat, or git.
- **The VM's proxy refuses some package hosts** (a peer session, 2026-10-31). `deb.debian.org` returned 403, so a
  Dockerfile's `apt-get upgrade` failed in the VM, and a Trivy scan of the image it built counted vulnerabilities
  that the upgrade would have fixed.
- **Environment.** A `claude` started from inside a Claude Code session inherits that session's variables; with them
  the local client turns transcript saving off ("inherited CLAUDE_CODE_CHILD_SESSION marker"). `lane` drops
  `CLAUDECODE` and `CLAUDE_CODE_*` for every Claude child, as it already did for `claude -p`.
- **A "remote" subagent ran locally.** On 2026-10-30 an Agent-tool subagent started with `isolation: "remote"` (Haiku)
  answered normally, but its transcript shows it ran on this machine, in a temporary git worktree
  (`.claude/worktrees/agent-<id>`, removed afterwards): 8 CPUs, no `free` (Git Bash), and HEAD at GitHub's `master`,
  not the session's unpushed branch. So remote subagents are not available to this account (the tool calls them
  gated) and the request falls back without saying so; and a worktree subagent starts from the remote default
  branch, so it does not see unpushed commits. The `worktree.baseRef` setting (`"head"`) bases subagent worktrees
  on the local HEAD instead (code.claude.com/docs/en/worktrees, read 2026-10-30).
- **Local subagents as workers** (Claude Code docs, read 2026-10-30; one transcript checked).
  - An agent definition can fix `model` (a full id), `effort`, `isolation: worktree`, `background`, `maxTurns` and
    `omitClaudeMd` (sub-agents page).
  - `SubagentStop` receives `agent_id`, `agent_type`, `agent_transcript_path` and `last_assistant_message`; it
    cannot answer the parent, but a hook can write files (hooks page).
  - `/tasks` and `claude agents` show running subagents. Background subagents carry over when Claude Code
    restarts, but not past a reboot.
  - A subagent transcript records each message's model, its `effort` and its token usage, with cache writes split
    into 5-minute and 1-hour, but no cost. The docs call the format internal. Pricing therefore uses the
    published list prices.
  - So `lane --subagent` (2026-10-29.3) runs Claude arms in the main process and keeps the run record in the hook.
- **Credit.** The account's usage page showed the cloud credit at $249 of $250 after the first probe (15 s of Opus),
  so cloud sessions draw on it; the page says the credit does not apply to Projects or Scheduled tasks.

## Unverified

The weight of a Codex cloud task against a local one; the model a Codex cloud task runs; per-plan concurrency for
either vendor; whether `--attempts N` costs N times as much; whether `--effort` reaches a Claude cloud session;
whether a peer message reaches a cloud session in the sender's own permission mode; which other hosts the VM's
proxy refuses.
