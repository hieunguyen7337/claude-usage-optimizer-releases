# Plan: a public kit for Claude Code, Codex CLI and Amp (drafted 2026-11-02)

Status: plan. Phase 0 is in progress (P1, P3, P4 done; P2 and P5 next); which later phase comes first waits for the
owner's decision 4 (section 7). Facts about Codex
CLI and Amp come from their public docs as read on 2026-11-02 (sources in section 7). Recheck them before building
each phase: both products change monthly.

## 1. Goal and rules

Anyone can install the kit from a public link and get these, whichever agent they use as the main session:
- the lane dispatcher;
- the arm picker;
- the meters;
- the time estimates.

The source repository stays private. A release, the page and an installed kit hold no private information:
- no names, accounts, paths or project names;
- no client work;
- no session or artifact identifiers other than the kit's own public page.

The rules that already hold stay:
- **Statistics, never raw data.** The kit ships measured statistics, never transcripts or run logs.
- **Machine facts stay on the machine.** They go in `~/.claude/CLAUDE.md` above the import line, or in
  `~/.config/lanes/`.
- **Capability tests need the user's yes,** and usage tests run freely.

## 2. Phase 0: a public-safe release (in progress)

1. **P1, done (2026-11-01.5, page v66).** Drop the private knowledge pack from the bundle. Move its README and IMPROVING text to
   `private/` (git only, never shipped). Owner installs from the git checkout keep the skill. `check-release` gains
   a `private` check against a local pattern list (`~/.config/lanes/private-patterns.txt`, never shipped).
2. **P2. Move the owner's own facts out of POLICY.md into a machine-local overlay.** These are plan moves,
   cloud-credit dates, the owner's mode choices, mirror authorizations and "the owner's call" lines. Measured
   findings stay, written as "measured on one Claude Max 20x and Codex Pro Lite account", because they are the
   kit's value. The public text describes rules; the overlay says what this machine chose. `install.sh` writes an
   empty overlay stub on a fresh machine.
3. **P3, done (2026-11-01.6). A public install route.** Before it, a stranger installed by asking their own Claude
   to read the page, and Codex and Amp users had no way to read a claude.ai artifact at all. Now a public
   releases-only repository holds each release (the shipped files, a GitHub Release with the bundle, the evidence
   and checksums), published from the private repo by `tools/publish-public.py` after `check-release` passes with
   the `private` check (IMPROVING.md, release steps). The page keeps working for Claude users, and `bin/cloud-setup`
   falls back to the public repository when a cloud VM cannot reach the private one.
4. **P4, done (2026-11-01.6). A licence.** MIT (section 7). A contributor note waits until the repository takes
   contributions.
5. **P5. A first-run test as a stranger.** Install from the public route into a fresh user profile, or a cloud VM
   with no kit, and run the dry run, the installer and `usage-status`. Fix whatever assumes this PC.

## 3. Phase 1: a host-neutral core

Split the kit into a core that any host runs and one adapter per host.

| Part | Core (any host) | Claude Code adapter (today) | Codex CLI adapter | Amp adapter |
|---|---|---|---|---|
| Policy | rules text, rendered per host | `~/.claude/CLAUDE.md` import of POLICY.md | `~/.codex/AGENTS.md`, flattened, at most 32 KiB (default cap) | `~/.config/amp/AGENTS.md` (path unverified) |
| Per-turn meter | `turn-meter` records | UserPromptSubmit + Stop hooks | UserPromptSubmit + Stop hooks (`~/.codex/hooks.json`); tokens read from `transcript_path` | plugin `agent.start` / `agent.end` (experimental API) |
| Compaction help | re-inject lanes in flight | PreCompact + SessionStart | PreCompact + SessionStart (`source: compact`) | none found |
| Status line | `claude-statusline` text | `statusLine` command | built-in items only (`[tui] status_line`); no script line | `createStatusItem` (experimental) |
| Workers | `lane`, `lane-stats`, arms catalog | subagents `lane-<lane>-<effort>` | per-agent TOML in `~/.codex/agents/` for Codex arms; other lanes by `lane` process | `lane` process; subagent models unverified |
| Plan meters | `usage-status` | statusline cache plus a probe | the kit's app-server read (undocumented, works today) | none documented; manual credit entry |

Work:
1. **A policy renderer.** `tools/render-policy.py --host claude|codex|amp` writes the host's file. For Codex it
   writes a condensed policy of at most about 24 KiB: rules and routing only, with LANES.md and FINDINGS.md as
   files to read on demand. POLICY.md is 59,883 bytes today, nearly twice the Codex cap.
2. **`install.sh --host <host>`.** The default stays `claude`. Each host's adapter files live in `hosts/<host>/`.
3. **`turn-meter` from transcripts.** It reads cost from the host's transcript when the host gives no session cost.
   Codex rollouts carry `token_count` events; prices come from the catalog.

## 4. Phase 2: Codex CLI as the main session

1. Render the condensed policy into `~/.codex/AGENTS.md`. Check that it stays under `project_doc_max_bytes`.
2. Register `turn-meter hook` on UserPromptSubmit and Stop in `~/.codex/hooks.json`, and the compaction pair on
   PreCompact and SessionStart. Codex hooks are on by default; a repo's `.codex/` loads only when trusted.
3. Generate `~/.codex/agents/lane-<arm>.toml` for the Codex arms (model and `model_reasoning_effort` per file).
   Claude and gemini arms run through `lane` as processes.
4. Status: map what fits into the built-in items, five-hour-limit and weekly-limit. Leave the rest to
   `usage-status`, since there is no command-backed line (openai/codex issue 17827).
5. A Claude meter for Codex users who also hold a Claude plan: the same small Haiku probe the cloud uses
   (2026-11-01.4).
6. Measure: one week of real units with Codex as the main session. Compare turn cost and time against Claude as
   the main session, as a usage test.

## 5. Phase 3: Amp

1. **First as a worker lane** (cheap, stable). `amp -x --stream-json` gives per-message token usage and a result
   with `duration_ms`. Add an `amp` lane with priors from public benchmarks and let forced exploration measure it.
   Price: Amp sells credits with no documented balance read, so the lane uses scarcity pricing until the user enters
   a price per credit.
2. **Then as a main session,** once its plugin API is no longer experimental:
   - `session.start`, `agent.start`, `agent.end` and `tool.call` map to the kit's hooks;
   - `createStatusItem` shows the ETA;
   - AGENTS.md carries the rendered policy.
3. Check first: the AGENTS.md path, per-subagent models, and whether `amp -x` draws only on paid credits. Those
   docs pages needed a sign-in on 2026-11-02.

## 6. Phase 4: opt-in usage sharing

**Decided 2026-11-02 (the owner delegated the choice): shared statistics land as public GitHub issues on the public
releases repository.** Each submission is one issue labelled `stats`, with one week's allowlisted totals as JSON. A
GitHub Actions workflow there validates it with `lane-stats share --validate` and labels it `stats-valid`, or labels
it `stats-invalid`, comments and closes it. Why GitHub issues rather than the page's database:
- Codex CLI and Amp users can reach GitHub but not a claude.ai artifact.
- Every submission is public, so the sender sees exactly what was shared, and anyone can recompute the community
  priors from the same issues.
- GitHub provides sign-in, spam handling and moderation, so the kit runs no server and holds no data.
- The cost: an issue shows the sender's GitHub account. The payload names nothing else, and sending is optional.

How it works (P4a, done in 2026-11-01.6: the client and the repository files; P4b, later, the pooling):
1. `lane-stats share` previews last week's payload; nothing is sent.
2. `lane-stats share --enable` opts in (creates a random install id; `--new-id` rotates it, `--disable` opts out).
3. `lane-stats share --send` shows the payload again, asks y/N, and posts it with `gh issue create`. Without `gh`
   it writes the issue body to a file and prints the issue-form link: data never goes in a URL. A week is sent once.
4. P4b: at each release, `tools/community-priors.py` reads the `stats-valid` issues, keeps one submission per install
   and week, and writes community priors that rank between public benchmarks and the user's own measured runs.

The design rules below still hold. The installer does not ask (cloud VMs and scripts have no prompt); the kit
page and LANES.md say how to opt in.

- **Off by default.** `lane-stats share --disable` stops it at any time.
- **What is shared:** weekly totals per arm and class, namely runs, reviewed, usable rate, median minutes, ETA
  ratio, weekly % per usable unit and list $ per usable unit, plus plan type, host and kit version. Arms with fewer
  than 3 runs are dropped. An install id is random and rotatable.
- **Never shared:** run ids, timestamps finer than a week, repository names, paths, briefs, notes, tags, model
  output or transcripts.
- **No background sending.**
  - `lane-stats share` (or `--preview`) prints the exact JSON and sends nothing.
  - `lane-stats share --send` posts it after a y/N, or writes the issue body to a file for the issue form.
  - The payload is built from an allowlist of numeric fields, and the `private` pattern check also runs on it.
- **Where it goes:** issues on the public releases repository (decided above). Anyone with a GitHub account may
  open one; the workflow closes any that fail validation, and GitHub's own spam handling and moderation apply.
- **What it buys:** pooled totals become community priors in `arms.json`. They rank between public benchmarks and
  the user's own measured runs, so a new install's picker starts from real usage rather than benchmarks.
- **No transcript upload.** Transcripts hold code, secrets and other people's data. No redaction is reliable, and
  collecting them would make the collector answerable for all of it. A bug report can carry a short excerpt the user
  has checked.

## 7. Decisions for the owner, and sources

Decisions:
1. Public releases-only repository: yes (owner, 2026-11-02). It is `claude-usage-optimizer-releases` under the
   owner's GitHub account, so its address shows that account name; a neutral organisation can take it over later
   (GitHub redirects old links).
2. Licence: MIT (owner said go, 2026-11-02), held by "Claude Usage Optimizer contributors", with no personal name.
3. Shared statistics: public GitHub issues on the releases repository (section 6; the owner delegated the choice).
4. Open: which first after Phase 0, Codex CLI as host (Phase 2) or the Amp worker lane (Phase 3, step 1)?

Sources (read 2026-11-02):
- learn.chatgpt.com/docs/agent-configuration/agents-md, /docs/hooks, /docs/agent-configuration/subagents,
  /docs/pricing;
- github.com/openai/codex issue 17827;
- ampcode.com/manual/plugin-api, ampcode.com/news/streaming-json (2025-09-09),
  ampcode.com/news/amp-free-is-ad-free (2026-03-30), ampcode.com/security.

Secondary sources (Codex exec JSONL fields, rollout files, Amp transcripts) disagreed in places. Treat those fields
as unverified until checked against a real run.
