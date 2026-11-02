# Improving the kit

## 1. The rule

Every lesson learned from using the kit goes into the kit and is published in the next release. The kit keeps
the statistics and main findings, plus the methods, tools, templates and general lessons needed to build on
them. It also keeps the resources to test new models, research and methods as they appear; those change every
week. This is how the kit improves itself over time.

## 2. What the kit keeps

Keep aggregated statistics, main findings, methods, tools, templates and lessons that help any machine using
the kit. Never ship Suite R items or another suite's item code, reviewer finding text, raw transcripts or
session extracts, per-run ledgers, personal data, project or paper names, hostnames, user ids or home paths.
Rewrite a useful machine lesson in general terms, such as “a high-performance computing (HPC) login node”
or “a research project”. A fact that is true only on one machine belongs in that machine's
`~/.claude/CLAUDE.md`.

**The full lab archive.** What the kit leaves out is kept in the owner's private GitHub repository `usage-lab`
(about 820 MB in 40,000 files): Suite R's items and answer keys, every run's raw output, the rescoring and
verification work, the meter probes, the briefs, the lane state and the memory notes behind the findings. The
kit's source, with its full commit history, is the private repository `claude-usage-optimizer`. With `gh` logged
in as the owner, `gh repo clone usage-lab` and `gh repo clone claude-usage-optimizer` fetch them. Clone the
archive only to continue evaluation work on that data, such as rerunning or rescoring Suite R; to take one part,
clone with `-- --filter=blob:none --sparse` and `git sparse-checkout set <folder>`. Its `README.md` maps the
folders. Whatever comes from it stays out of the kit.

On Windows, add `-c core.autocrlf=false` to the clone: the archive pins no line endings, and Git for Windows
otherwise checks every file out with CRLF (a patterns file with CRLF matches nothing). Git Bash also rewrites an
argument that starts with `/` into a Windows path, so `sparse-checkout set /README.md /memory/` stores
`C:/Program Files/Git/README.md` and the checkout comes out empty: prefix it with `MSYS_NO_PATHCONV=1` and check
with `git sparse-checkout list`.

To refresh the archive, stage it outside the lab with hard links (`cp -al` copies nothing), leave out build
clones whose commits are already in the source repository, commit where heavy CPU is allowed (on a shared login
node, in a batch job), and push. Before every push, scan for credentials in one combined pass
(`grep -rIlE -f <patterns>`) and attribute the hits afterwards: one pass per pattern over 820 MB took more than
15 minutes. Anchor short prefixes such as `sk-` as `(^|[^A-Za-z0-9_-])sk-`, or they match inside words like
`task-…`. Run `git status --ignored` to see what a copied `.gitignore` drops. The archive's `machine/tools/`
holds the staging and scan scripts. A document connector such as Google Drive can't carry an archive, because
its uploads pass through the conversation as inline text.

## 3. Where a lesson goes

| Lesson type | Home |
|---|---|
| Routing rule | `POLICY.md` |
| Lane quirk or orchestration lesson | `LANES.md` |
| Meter fact | `measure/*.md` |
| Measured result | `findings/FINDINGS.md` and a matching `findings/<topic>/` data directory |
| Method | `measure/*.md` or `findings/public-research/` |
| Tool or its behavior | `bin/` and `tests/` |
| Machine-only fact | That machine's `~/.claude/CLAUDE.md` |

A lesson about mirror cloud sessions goes to the "Main cloud sessions" section of `POLICY.md` when it changes what the
main session does, and to LANES.md "Mirrors, side sessions and `lane main`" when it is a quirk or a limit. The policy
section is copied into the session's prompt by `lane main`, so keep it short and ASCII: any other character stops the
command (exit 8).

## 4. Sweep for lessons

Run a lessons sweep after a substantial task, with the weekly `lane-stats recommend`, and before every release
on every machine. Use `improve/audit-brief.md` as a read-only `research` lane unit over memory notes, machine
rules and lab notes. Give it the lane class `research` and a descriptive tag. Search only named directories and
depths from the brief. Classify each candidate as KIT-MISSING, KIT-PARTIAL, PRESENT, EXCLUDED, MACHINE,
PROJECT, SUPERSEDED or OBSOLETE. Cite every claim with `[OBSERVED path:line]` or `[INFERRED]`; report absent
targets and count every class. Each kit-wide lesson ships in the next release.

With the weekly sweep, run `turn-meter census --json` on every machine and add the results up. Work that never
went through `lane` (interactive Codex or Claude sessions, other tools) still draws on the meters, and the census is
the only kit view of it: a heavy model used by hand (astra, 18.9 h in the week to 2026-10-30) or a pattern a lane
could take over shows up there first.

## 5. New models

Follow Explore steps 6 and 9 in `POLICY.md` in order. First run `lane-stats arms --discover`, then add the new
model's arms with its predecessor's classes. Forced exploration gives each arm real units. After the user
approves a capability test, rerun the kit's suite with `lane-bench`, then write measured priors with
`lane-bench priors`. Retire the predecessor only when `lane-stats recommend` shows the new arm is at least as
good in every class it serves. Keep the exploration floor so later changes can still be found.

A model that could take the main session's seat (a new Fable) follows the switch rule in `POLICY.md`, Advisor,
instead, once it is confirmed accessible: manual arms in its own lane, a usage test, then a capability test the user
approves, then the advisor, and the main seat last.

## 6. New public research

Read both `findings/public.json` and `findings/public-research/` when updating public evidence. Each numeric
row in `public.json` records `lane`, `model`, `effort`, `metric`, `value`, `source`, `date` and `url`. The dated
research notes group results by task and benchmark; their tables record the benchmark and version, date,
model, effort, score, cost when reported, who ran it and a source link. They also record conflicts, gaps and
unverified results. Preserve those distinctions when adding evidence.

Compare public evidence with our reviewed results using `lane-bench compare`. In the current comparison,
public benchmark prices rank our review cost well (Spearman rank correlation, a measure of ranking agreement,
0.96 for v1.5 and 0.98 for v2.0), while public scores rank our recall only by tier: the v1.5 index 0.22 (18 arms),
the per-effort Intelligence Index v5.0 0.57 (37 arms), the v2.0 index 0.81 on nine max arms, mostly because luna and
terra sit below the rest (`lane-bench compare --outcomes findings/suite-r/outcomes.jsonl`, 2026-10-31; it writes its
tables to `findings/suite-r/results/`, so delete that folder unless the tables are meant to change). Trust public
prices as a starting point, not public scores as a substitute for our own measured quality.

## 7. New methods and suites

Use `measure/SUITE.md` to define a suite and `measure/ADJUDICATE.md` to resolve findings. Regrade with
`lane-bench rescore` and refresh measured priors with `lane-bench priors --score v2`. When Codex is at its
weekly ceiling, `lane-bench run --codex-at-limit wait` forces a live reading and waits instead of skipping;
`--codex-wait-max-h` bounds that wait.

Suspect the harness before the model. If an arm returns all zeros, a suspiciously round rate or an implausibly
low number, inspect raw model output first. A 2026-09-15/16 pilot found 16 harness defects; seven produced
believable numbers rather than obvious failures. Examples included a parser that recognized one code-fence
form and scored valid code as 0.0, a field that was `None` by construction but averaged as 0.0 beside 41
solved tasks, and a smoke gate that reused an id and graded the previous build.

The harness includes your own scripts. On Windows, Python writes CRLF to a redirected stdout, so a shell loop over
its output keeps a trailing `\r` on every line: all 73 lane-bench tests then "errored" as unknown names
(2026-10-23). Strip `\r` before looping.

Run each arm's assembled command end to end on a synthetic fixture before using real data. Unit tests alone
missed two first-run failures on 2026-09-04.

The next measurements already proposed in `findings/FINDINGS.md` §§9–10 are a multi-task suite and lead ×
executor pairs measured by role. The single-task suite does not settle performance on other task types, and
hybrid roles need their own evidence.

## 8. Building a release

1. Bump the version line in `POLICY.md`. Bump `catalog_version` in `arms.json` only when the catalog changes.
2. Run the tests and confirm `lane-stats arms` loads the catalog, in the cloud (from 2026-10-31.6): commit the
   candidate, `git worktree add` a clean copy (`lane` refuses untracked files), and run
   `lane haiku --cloud --verify -e low -C <copy> -b <brief>` with a brief listing the full suite (900 s) and
   `python3 bin/lane-stats arms`. To test a `lane` that is not installed yet, start the checkout's own copy as
   `python <checkout>/bin/lane …`: Git Bash on Windows has no `python3`, so its `#!` line fails. Since 2026-10-28
   every test passes on Windows too (§10), and `test_bench` runs whole in under a minute; on Windows run only the
   modules a Windows-only change touches, each with a timeout. `test_install_view` passes
   but runs the installer many times through Git Bash: its 11 tests took 14 minutes on a busy Windows machine, so
   give it a 20-minute timeout rather than read a cut-off run as a hang.
3. Build the bundle with `bash tools/make-bundle.sh`, then the page with `python3 -I tools/make-page.py`. The builder
   also writes `dist/claude-usage-optimizer-evidence.sh`, the Suite R rescore evidence that leaves the bundle for its
   size; what each file leaves out is one list, in `tools/release_bundle.py` (`EXCLUDED`, `EVIDENCE_FILES`), which
   the builder and `check-release` both read (`findings/bundle-size-plan.md`). In a
   fresh clone, pass `--url <artifact url>` once: `dist/.artifact-url` is not tracked, and without it the page
   keeps a URL placeholder instead of the link. Check that `grep -c <artifact id> dist/index.html` is above 0.
4. Run `python3 -I tools/check-release.py [--kit DIR] [--bundle PATH] [--page PATH] [--patterns FILE] [--max-bytes N]`.
   It checks `version`, `catalog`, `json`, `bundle` size (at most 16,000,000 bytes), `fresh` (bundle matches
   the tree), `evidence` (the evidence file: the same size limit, every listed file, fresh), `patterns`, `eol` and
   `untracked`, the content checks over both files; exit 0 means clean and exit 1 means at least one FAIL.
   `untracked` fails on a shipped file that git does not track, because `make-bundle.sh` ships untracked,
   non-ignored files. Release 2026-10-29.3 was first built with a Codex CLI `error.log` holding an account id,
   which a warning let through; `.gitignore` now ignores `error.log`.
   `eol` fails on a file git stores with LF whose working copy has CRLF. Editors on Windows save CRLF, and
   `.gitattributes` normalises it on commit, so `git diff` shows nothing; but the bundle carries working-tree
   bytes, and `fresh` compares the bundle with that same tree. Release 2026-10-24.1 first shipped two Python
   files with CRLF this way and was rebuilt from a clean `git worktree add --detach <dir> <commit>`. Convert
   such files to LF; if `git status` still lists them with no diff, `git add` them. Patterns are
   regexes for project names, hosts and home paths in a local, never-shipped file, defaulting to
   `~/.config/lanes/release-patterns.local`. A `!glob` line excludes paths. A hit prints only
   `path:line pattern#N`. `private` (from 2026-11-01.5) reads a second never-shipped list,
   `USAGE_OPTIMIZER_PRIVATE_PATTERNS` or else `~/.config/lanes/private-patterns.txt`: the owner's own names,
   accounts, paths and project names, one regex per line. It scans every shipped and evidence file and the page,
   prints only `path:line pattern#N`, and fails the release on any hit; a missing list is one WARN. The page is
   public, so private material lives under `private/` in git, which never ships: a skill in `private/skills/<name>/`
   installs only from a checkout. The bundle was 15.6 MB at 2026-10-31.16, about 380 KB under the limit, and
   `check-release.py` warns from 94% (15,040,000 bytes); `findings/bundle-size-plan.md` proposes where to win room.
5. Preview installation with `bash install.sh --dry-run` and run `improve/release-brief.md` before publishing.

Build workers write JSON only through the tool's own output or `--write`; never rewrite it with `jq` or a
heredoc. Check `[.. | objects | select(has("measured") and .measured==null)] | length` is 0. Recompute
before/after tables from `git show HEAD:` because a worker's table can repeat the new value on both sides.

`tools/make-bundle.sh` includes untracked, non-ignored files. Keep scratch workspaces git-ignored and install
from the clone that built the bundle. If a commit is requested, use the neutral identity `kit <kit@localhost>`,
never a personal address.

## 9. Publishing from any machine

Before publishing from a machine other than the last publisher, compare the live bundle with that machine's
source and merge differences first:

```bash
python3 -I tools/diff-bundle.py <live bundle> [--kit DIR] [--extract DIR]
```

This comparison never runs the bundle: exit 0 means identical, 1 means differences and 2 means an error.

**Taking over on another machine.** That machine's old kit folder may be a bundle extract or a checkout of an
older release; never build or publish from it, or the release reverts every later one. Find its release's commit
(`git log --oneline -S'version: <its version>' -- POLICY.md`), compare the folder with it (`git archive <commit>`
into a scratch folder, then `diff -rq --strip-trailing-cr`), port anything newer onto a fresh clone as commits,
and only then put the clone in its place. On Windows the folder that is a running session's working directory
cannot be renamed (`Device or resource busy`): move its contents aside, then move the clone's contents, `.git`
included, into it. `.gitattributes` pins LF, so a Windows clone matches the bundle byte for byte. `python3` may
be the Microsoft Store stub, which cannot run; use the Python that `install.sh --dry-run` reports.
Publish both `.sh` files, the bundle and the evidence file, as `contentType: "text/plain"` to the same Artifact
URL. The publish refuses any file
that contains U+FFFD (the replacement character), so write such characters in source as escapes (`"\ufffd"`):
release 2026-10-28.1 was refused once for a literal one in `bin/lane`'s garbled-text pattern, and 2026-10-29.1
once for one in this very note. Claude's Edit and Write tools decode a backslash-u escape in their input, so the
escape typed into a tool call lands on disk as the character itself; write it with a script, or check the bytes.
`tools/check-release.py` fails (`replacement`) on U+FFFD in the page or any shipped file.

**The public releases repository** (from 2026-11-01.6). After the page, publish the same release to the public
releases repository named in `arms.json` (`explore.share.repo`): keep a clone of it in `dist/public` (git-ignored),
on its default branch, then run `python3 -I tools/publish-public.py --clone dist/public` (a dry run) and the same
with `--push`. The push refuses unless `check-release` passes with `OK private`, the clone is clean and its origin is
the releases repository, and the tag `v<version>` is new. It commits the shipped files, `LICENSE`, the
`public-repo/` files (the README preface, the statistics issue form and its workflow), tags, pushes without force
and creates a GitHub Release with the bundle, the evidence file and `SHA256SUMS`. Codex CLI and Amp users install
from there, and `bin/cloud-setup` falls back to it when a cloud VM cannot reach the private kit repository.

On other machines, rerun the setup prompt. Pool reviewed runs with `lane-stats export` and `lane-stats import`; the per-run ledger never
ships.

## 10. Backlog

- **Lane recipes, planned and not built:** `lane recipe <id>` should read roles, protocol and limits from
  `arms.json`, run the roles as stages, record one run and cost per role, and sample by class. The hybrid
  stage needs this.
- **Review cost attribution, planned and not built:** attribute review cost to the unit that caused it, by
  tag, so the picker charges a cheap lane for the Opus review that it causes.
- **Multi-task suite:** measure more task types with task-specific checks and effort curves, as proposed in
  `findings/FINDINGS.md` §9.
- **Lead × executor pairs:** measure each role's contribution on a connected set of pairs and check the fit
  on held-out pairs, as proposed in `findings/FINDINGS.md` §10.
- **Windows portability, found 2026-10-23, closed 2026-10-28.** Fixed 2026-10-24: `test_lane`'s four (cgroup
  paths strip `/` on every system; cleanup clears read-only `.git` objects) and `test_release_tools`' six (Git
  Bash through `find_bash()`, `sys.executable`, the bundle edited as bytes, no mode bits). Fixed 2026-10-28:
  `lane-bench`'s 17 (helpers start through their `.cmd` wrapper, Python or Git Bash; runs stop by process tree;
  `export` reads the graded summary in Python without `jq`) and one each in `test_knowledge` and `test_measure`
  (paths print with `/` on every system). Found and fixed 2026-10-29: on a Windows install each tool is
  `bin/<tool>.py` behind a bash wrapper `bin/<tool>`, so a tool that starts a sibling with
  `python bin/<sibling>` runs the wrapper and gets a SyntaxError. `lane-stats pick` did this with `usage-status`,
  failed silently, and so never applied pace factors or the at-limit skips on Windows. A tool that starts a sibling
  takes `<sibling>.py` when it exists, as `lane` already did.
- **Time as a value to optimise.** Since 2026-10-29 every run and turn logs its time and ETA, but the picker
  chooses on usable rate and cost only. Once `eta×` shows the estimates are sound, consider a time term (for
  example Claude's waiting minutes priced in points) for units on a deadline.
- **Cloud runs, still open** (built in 2026-10-29.3: `lane <claude lane> --cloud`, `lane codex-cloud`, `bin/lane-term`;
  LANES.md "Cloud runs"; research note §7–§8). Measure, as cloud runs accumulate: a cloud run's meter weight against
  the same arm run locally (the same model and effort, so `lane-stats report` by `place` once the ledger field
  has data); the start-up on a cold VM and with a setup script; how many Claude cloud sessions run at once before
  a launch is refused; and the time from the worker's done push to the applied diff. `codex-cloud` first ran end to end
  on 2026-10-31: that run checked the task-URL parsing, the status polling and the diff apply, and all three worked
  (LANES.md, "Codex"). Still open: what `codex cloud status` prints for a failed task, which that run did not show;
  until then its arm stays manual.
  Add a time term to the picker only after cloud runs show whether placement changes usable rate (Linux harness,
  4 vCPU) as well as time. If a repository cannot use the Claude GitHub App, the only other return path is the
  session's event log, which only an in-process Claude Code tool can read; reading it with the user's OAuth
  token from a script is not an option (the kit never reads credentials).
- **Subagent runs, still open** (built in 2026-10-29.3: `lane --subagent`, `lane hook subagent-stop`, the
  `lane-<lane>-<effort>` agents; LANES.md "Subagent runs"). Measure, on the first real runs:
  - how much the main Claude Code process grows while subagents run, against the 0.5–1.2 GB a `claude -p` worker
    peaked at (two runs);
  - whether every run's transcript shows the arm's effort (the hook warns when it doesn't);
  - whether the usable rate of an arm differs between `place` subagent and local (the subagent sees the session's
    hooks and permissions but not its CLAUDE.md);
  - how many background subagents run at once before Claude Code queues or refuses one;
  - what the agent list costs: the 12 definitions sit in every session's tool description.

  If subagents hold up, make `--subagent` what `lane-stats pick` prints for Claude arms when it is called from a
  Claude Code session.
- **Memory needs per class.** `peak_mem_mb` is recorded per run from 2026-10-29.2 and the need is taken per lane.
  A unit that builds or installs (npm, a large test suite) peaks far above one that edits text; once enough runs
  carry the field, check whether lane x class predicts the peak better than lane alone, as the ETA's tiers do.
- **lane-bench cost in plan dollars, open.** `lane-bench` still prices cost points with provider scarcity weights
  (`bin/lane-bench`: the pooled cost points and the per-item points; `tests/test_bench.py` sets scarcity values),
  as `lane-stats` did before its plan-dollar change. Move it to plan dollars: the window share through
  `window_epochs` and `plan_scale`, times the plan's price per week (`arms.json` `explore.points_basis`). Until then
  its cost axis mixes scarcity with prices, so its cost-per-recall ranking is not in plan dollars.
- **Mirror cloud sessions, to pilot** (built in 2026-10-31.15: `lane main`, `lane-stats main-picks`, `lane-stats
  import-orch`; LANES.md "Mirrors, side sessions and `lane main`"). Run one mirror on one project for a few days and
  record in `findings/` what it cost (list dollars and the share of Claude's week, against the same units as local
  subagents), how good its reviews were (how often its Haiku second reader's objection held, how often the local
  session found a defect the mirror had accepted) and how long units took. Imported runs carry `place: "cloud-main"`,
  so a report by place shows them apart from local runs.
- **Route 1(a), still untested.** Try once, from a running mirror, to clone the private kit repository. The session's
  own scope text says it cannot, but nobody has tried. If it can, install the kit in the VM so the mirror runs
  `lane-stats pick` itself, with its own copy of the pooled runs (`lane-stats export` and `import`), instead of reading
  `picks.json`. This is a picker in the VM, not the per-pick round trip that design (i) means in LANES.md.
- **Hand-off time in the markers.** Once enough Codex and gemini hand-offs exist, extend the REVIEW markers with the
  hand-off's own time (the wait for the local run, apart from the mirror's review), so a hand-off unit's ETA is
  measured, not guessed.

## 11. Release lessons

**2026-11-02.3.**
- *Wait on what was pushed, not on a branch tip.* One verify run waited 52 minutes with its report already on GitHub:
  lane read only the tip of the first branch it saw, so a later commit, a move to a `claude/…` branch or one failed
  fetch hid the done marker. lane now looks for the marker in every changed branch's history and marks a branch seen
  only after reading it.
- *A local place setting can silently drop a whole provider.* `explore.places` of cloud and subagent left no Codex
  arm to pick (codex-cloud is manual), so mirrors ran Claude only while Codex sat in utilization. `main-picks` and
  `mode` now print a warning when that happens.
- *Fast-forward a checkout before `lane --cloud`.* A checkout behind its remote cannot push the cloud base branch, and
  the run is REFUSED (exit 8) before any session starts.
- *Attaching a repository is what opens it.* In a project's cloud session the private kit repository fails to clone
  until `add_repo` attaches it read-only, then clones; the environment's setup script still installs the public
  release, so a new setup script must be uploaded after each release that changes it.

**2026-11-02.2.**
- *A Button holds only strings and Text.* The engine refuses a tree with a Box inside a Button, and the whole list
  stops drawing. The text functions' own tests cannot see it; a test that mounts the pane can.
- *One session, two ids.* The sessions API names a session `cse_…`, and `mains.json` stores the same session as
  `session_…` with the same suffix, so no listed mirror was ever tagged. Compare session ids without their prefix.
- *A layout change reaches every test that finds drawn text.* The layout brief named the view's tests, and the pane
  and signals tests, which look for row and footer text in the mounted pane, failed in the cloud verify. A brief that
  changes what is drawn names every test file that matches drawn text.

**2026-11-01.3.**
- *Measure a cloud session's cost from its own transcripts, and the meter from a clean window.* The sessions list API
  (`GET /v1/code/sessions`) gives each session a lifetime `usage.cost_usd` at list price. It updates only now and
  then, and bridge sessions have none. The mirror's own report (every transcript in its VM, priced with the catalog)
  came within 2% of it and split it by hour, model and subagent. Hourly meter peaks against local plus cloud list $,
  over hours when nothing else ran, settled whether cloud costs more per list dollar. It does not (POLICY, Known).
- *Every reading from many writers needs a freshness rule.* All sessions' statuslines write one `claude-latest.json`,
  and an idle session's rate limits are as old as its last model call. Take a reading as fresh only when its source
  has just done the thing that produces it (here, its cost moved). Read the max across live sources, never the last
  write, before calling a fall.
- *A mode handed to another machine needs an expiry.* A mirror cannot read the meter, so it kept the utilization
  mode it was started with through the next weekly reset and spent about 20 points. A handed-over mode now carries
  the reset it was computed for, and past that reset the conservative mode applies.
- *A gate tuned for a person at the keyboard can cost money in a loop.* The compaction gate waits for "the next
  turn", and a cloud loop never has one, so its context sat at the 350k ceiling. Check each hook's assumption about
  a human in the loop before it ships to cloud sessions.
- *A mod pane is never full-screen.* Claude Code seats a pane inline above the prompt (a third by default, or as many
  `rows` as the layout spares) or docks it beside a fullscreen transcript (`columns`, at most 45% of the width). The
  engine's own agent view is a different surface, and no mod surface matches it. Ask for the most (`rows` and
  `columns` from the viewport) and say where the limit is.

**2026-11-01.2.**
- *A release built from master drops what was only installed.* 2026-11-01.1 was built from master, which never got
  release .17 (installed on the owner's PC, never published or pushed), so installing it removed .17's mirror merge
  grant. 2026-11-01.2 brings .17's three commits back. Before building a release, compare the installed POLICY
  version with the branch's, and bring a newer installed release's commits onto the branch first.
- *A verify brief discovers `tests` as the start directory, with no `-t .`.* `tests/` is not a package, so
  `python3 -m unittest discover -s tests -t .` runs nothing; the first cloud verify of 2026-11-01.1 failed that way.
- *GNU `sha256sum` escapes a path that holds a backslash.* It prefixes the line with `\`, so extracting a bundle into
  a `USAGE_OPTIMIZER_DIR` written with backslashes fails its hash check. Pass forward slashes; the default `$HOME`
  path is fine.
- *`test_measure` needs UTF-8 on Windows.* `analyze_cprobes.py` prints "Δ", which cp1252 cannot encode; run it with
  `PYTHONUTF8=1`. Linux is unaffected.
- *A Codex Cloud verify runs the suite one file at a time.* In Codex Cloud's VM a whole `unittest discover` hung
  inside a test's `git commit` (`test_lane_stats_orch`) until the task was cut off. Run each test file under
  `timeout 300` with stdin from `/dev/null` and git told never to wait (`GIT_EDITOR=true`, and `GIT_CONFIG_COUNT`
  with `GIT_CONFIG_KEY_n`/`GIT_CONFIG_VALUE_n` turning off commit and tag signing and pointing `core.hooksPath` at
  `/dev/null`); the same file then passed, 56 tests in 68 s. `lane codex-cloud` brings back only the diff, so the
  brief has Codex write the output to a file at the repository root, which is deleted after reading.
- *`test_long_commands_are_read_in_linear_time` has a 1 s wall-clock limit,* which Codex Cloud's VM missed (1.25 s for
  a 100,000-line heredoc) while the Claude VM passes it. A miss there alone is the VM's speed, not a regression.

**2026-11-01.1.**
- *A claim about a vendor setting is checked against the vendor's docs before it ships.* LANES.md told the owner to
  add the kit repository under a cloud environment's "Repositories" setting; that row never existed, and a session
  reaches a private repository only when it is attached (API and archive requests for any other repository get 403;
  a probe the same day found that `git clone` of an unattached public repository works). The kit now reaches a
  mirror as a lean copy of the installed kit on the project's `lane-main/kit` branch, which the session can fetch.
- *A setup script's result is a snapshot, so its "latest" is the cache's.* `cloud-setup` installs the kit from the
  environment's setup script, before Claude Code starts, which also puts the 250k compaction window in force from
  the first turn. The environment reuses the script's result for about 7 days, so a session's kit can be that old;
  running the script again in the session updates it. The committed script names no repository: `--print` fills it
  in from the recorded checkout, so the kit carries no account name.
- *Two parsers of one marker share one grammar (or one test table).* `lane-stats` read `tok=-`, `tok=-/-` and
  `tok=12/-`, but `lane main`'s check accepted only digits, so a REVIEW marker one tool counted the other called
  malformed. Both now take `-` or `<in|->/<out|->`, and one test runs the same cases through both.
- *A rebuilt VM starts without what the last one installed.* The kit, the git-ignored `.claude/main-session` marker
  and `~/.claude` are gone after a rebuild, so the mirror's start steps install the kit whenever
  `~/.claude/usage-optimizer` is missing, and the `SessionStart` hook tells a mirror from a worker by the marker or,
  when that is gone, by the transcript's first prompts.
- *A hook's own timeouts add up to less than the hook's.* The reinstall hook's fetch and install timeouts summed past
  its 120 s limit, so a slow install would have been killed with no message; they are now 20 s and 70 s, and a test
  holds the sum under the limit.
- *A pipeline that ends in `tail` exits 0.* The mirror's install line ended in `| tail -n 5`, so a failed fetch or
  install looked like success. It now logs to a file, prints `kit install exit N`, then the log's last lines.
- *A kit that installs copies must carry its installer.* The installed kit had no `install.sh`, so nothing could
  rebuild it from that copy; the installer now copies itself and refuses to run from its own install prefix.
- *An archive from a branch is data.* The hook extracts only plain files and folders inside its target, never links
  or paths with `..`, since anyone who can push the branch can shape the archive.
- *A rule written for the local session reaches every session that loads the kit.* The utilization notice told each
  session to put its units in a few cloud sessions; mirrors, which hold the session tools, took it as their own and
  started empty cloud sessions. A rule only the local session may follow now says so, a cloud session gets its own
  notice text, and a project hook and a `lane` check stop a cloud session from starting another.
- *A command check must read the text as the shell does.* The first Bash check split words with shlex: a comment
  holding an apostrophe, a quoted `#` or a `<<` inside arithmetic hid a `claude --cloud` that followed, and one long
  argument took quadratic time. A Haiku second reader found each case. A one-pass scanner that reads quotes, comments,
  heredocs, redirections and substitutions as the shell does replaced it, and a test bounds its time on long input.
- *A marker grammar has to fit every session's own rules.* A mirror's system prompt forbids model ids in commit
  messages, so it wrote REVIEW arms as `lane/effort`, and `import-orch`, which wanted `lane/model/effort`, dropped
  three reviews as malformed. Markers now carry `lane/effort` and the catalog supplies the model; a marker that
  matches no single arm is skipped, never guessed.
- *A stronger model joins as an advisor before it takes a seat.* The main session's bill is mostly re-read context,
  so its model's weekly weight decides most of the week; a stronger but dearer model earns its place first on a few
  measured jobs (planning hard units, the last rung of the failure ladder, final review of high-stakes diffs, tie
  breaks), called with a fresh brief and a budget. The `fable` lane is that advisor, disabled while only Fable 5.1
  is accessible and it trails Opus, and `explore.main_session` makes the later switch one line in arms.json
  (POLICY.md, Advisor).

**2026-10-31.17.**
- *A launch line the session writes itself fails where it cannot see it.* In a `--cloud --verify` run a Haiku session
  wrote its own parallel launch line and set a variable inside the first backgrounded group only, so shards 2 to 4
  got a broken log path and never started: 908 s instead of about 223 s. `lane` now lists the committed test files
  itself (`git ls-tree -z`, split by size) and puts one complete sh script in the prompt, every variable set before
  the first `&`, which the session runs unchanged.
- *Read git paths with -z.* Without it git quotes a path with non-ASCII characters, a pattern on the plain name
  misses it, and that test module ran in no shard while every shard reported rc=0. A second reader found it by
  committing `tests/test_café.py` in a scratch repository.
- *A check placed after a refusal never runs.* The new `lane main` warning for a modified or untracked notify file
  could not fire: `cloud_preflight` already refuses a dirty tree, and the test called the function directly. A clean
  tree can still hide a file git ignores, so that is what the warning checks now, and its test runs the real start.
- *A session title comes from the first prompt line.* Brief text gave titles that did not say what kind of session
  it was. Every prompt `lane` sends to a cloud session now starts with `Kit mirror|side session|verify|worker - ...`.
- *An ignored output comes back as an empty diff.* A cloud session commits with plain `git add`, which skips a
  file git ignores, so the unit ended as NOOP with no hint. The work steps now ask for `git add -f` on a file the
  brief asks for, and a NOOP checks the brief's paths with one `git check-ignore --stdin` and says which are ignored.
- *Giving up is not stopping.* When `lane` stops waiting for a start marker the cloud session goes on; the run
  record now holds `left_running` and the error says to stop or archive it, with its link.
- *A sample of program output comes from the program.* The install page still showed `turn ≈` after the status
  line had moved to `ETA ~`; the sample is now taken from a real `claude-statusline` run, and its version is
  `{{VERSION}}`, which `make-page.py` fills.
- *A test of a Linux-only script skips on Windows.* The shard script checks that `git rev-parse --show-toplevel`
  starts with `/`; Git for Windows prints `C:/...`, so its test failed on Windows only. The script runs in the
  cloud VM, so the test now skips on Windows with that reason instead of the check accepting drive paths.
- *An owner's standing grant goes into the kit, not into each repository.* Two mirrors merged into their default
  branch on the owner's word in chat, and each wrote its own exception into the repository's instruction file. The
  owner then authorized every mirror to merge its reviewed work (2026-10-31), so POLICY and the mirror's start prompt
  say so; workers and side sessions still never push the default branch.
- *A repository's own push rules win over a kit-wide grant.* One project moves its default branch only through a push
  script that needs a green CI run on that exact commit and a fresh owner approval per push. A mirror merging on the
  kit's grant would have skipped both, so the grant now yields to the repository's own rules (instruction file, push
  script, branch protection), and there the mirror stops at READY.
- *Count the bundle per file, not per folder.* Each file costs about 476 bytes of heredoc and hash lines, so a pack
  of many small files costs more than its size; section 8 still said 2.1 MB of headroom when 0.38 MB was left.

**2026-10-31.16.**
- *A test kit must match the installed layout, not the checkout's.* `lane main` ran `python bin/lane-stats`, which on
  a Windows install is a bash wrapper beside the real `lane-stats.py`, so every mirror start and `--picks` there
  failed with a SyntaxError and the mirror fell back to Claude-only picks. The test kit wrote the same Python fake at
  both names, which hid it. It now writes a bash wrapper at the bare name, as install.sh does, and every sibling tool
  is found through one helper that tries `<tool>.py` first. A mirror's first live start on Windows found it.
- *Printed commands name the shell they target.* On Windows `lane main` prints `&&` chains for Git Bash or cmd.exe;
  backslash paths broke in Git Bash, and a bare `cloud-notify` hit Git Bash's `python3` Store stub. Paths now print
  with forward slashes in double quotes, and Python tools start with the kit's python.
- *A line called ready to run holds no placeholder.* The LOCAL hand-off's `next:` line carried `--class <class>`,
  which both shells read as a redirection, after its first step had already made a worktree; the marker had no class
  to give. The mirror now writes `class=` in LOCAL, and a marker without one gets no `--class` and a note.

**2026-10-31.15.**
- *Choose only what can run.* The picker drew luna max, a Codex arm that runs only as a local process, on a machine
  whose hook allows only cloud and subagent runs. Each lane now lists the places it runs, a machine lists the places it
  allows, and every draw (forced, floor, Thompson) and every mirror pick table sees only arms runnable there.
- *A peer session's brief is data.* A mirror's `orch: LOCAL` hand-off is another session's text; the local session
  reads it before running it and asks the owner when it reaches outside the project.
- *Exclusions travel with the table.* A mirror draws from picks.json with no ledger and no judgement about data
  terms, so a private repository's exclusions (`--exclude gemini`) are applied when the table is built, and a lane name
  the catalog lacks is refused rather than silently excluding nothing.
- *A test's stand-ins must win on every OS.* The mirror unit's tests wrote extensionless fake `claude` and `git`
  launchers. Windows finds only PATHEXT names, so on this machine `lane main`'s start tests ran the real
  `claude --cloud` on the owner's account (each exited in about a second with no session). Harnesses write `.cmd`
  launchers on Windows and check in setUp that every CLI the code resolves is the test's own; a hook that guards
  Claude's Bash commands never sees what a test's subprocesses start.
- *Count the shards.* Overlapping shard patterns ran part of the suite twice and still reported ALL PASS; a verify
  report's shard counts must add up to the suite.
- *Doc versions follow the release that ships them.* The mirror unit was written for .14 but shipped in .15; its
  "from" lines were moved when it merged.

**2026-10-31.14.**
- *Price the work in the plan's dollars.* Scarcity weights (codex 0.3, claude 1.0) hid that Pro Lite's price per %
  changed when its week doubled. Cost points are now the share of today's window times the plan's price
  (LANES.md, "Window epochs and plan dollars").
- *Record a plan change as a dated epoch.* A change to a plan's allowance is an entry in `window_epochs` with its
  date and source, so runs read before it keep their window and later runs are rescaled (`arms.json`).
- *Check which pool pays before routing on it.* The cloud-session credit was assumed to pay first. On 2026-10-31 it
  did not visibly do so, so routing no longer counts it (LANES.md, "Billing of cloud runs").
- *The window-change log needs no lock.* A reader skips a line that does not parse and keeps one event per fall.
- *Cap what reaches the session.* Kit notices are shown at most five per prompt, with the rest counted, so a burst
  cannot fill a session's context.
- *A hook sees only what its payload says.* cloud-notify ignores any event with an `agent_id` (a subagent's), and the
  hooks documentation does not confirm whether a settings-level Stop hook fires when a subagent finishes, so the
  kit does not rely on it.
- *Read the host's limits before sizing a setup step.* A cloud environment is snapshotted only when its setup script
  ends within about five minutes, and the Trusted network list leaves out dl.google.com. The first Android step had
  per-part timeouts of 30+ minutes and assumed the SDK host was open; the budget and the Custom-network note came
  from reading cloud-environments before release (LANES.md, "Android builds").
- *A cloud session needs its own meter.* A mode handed over from the PC goes stale; a cheap probe in the VM
  (one Haiku call every 15 minutes at most) lets `auto` pace there (LANES.md, "A cloud meter").
- *Policy text is also prompt text.* The Main cloud sessions and Briefs sections go into every mirror's start
  prompt, which must stay under 30,000 characters with a 15,000-character brief. The 2026-11-01.4 mode paragraph
  pushed it to 30,153, and only the cloud verify caught it. After editing either section, run
  `test_lane_main -k fits` (one file, about 20 s) before the release; 2026-11-01.4 left 405 characters spare.
