# Setup prompts

Paste the prompt for the agent you use: Claude Code, Codex CLI or Amp. Each one installs the same kit (policy, worker
lanes, meters) from the public GitHub repository and adds that agent's own adapter, and each one stops after a dry run
until you say "go". On a machine with several agents, install once per agent; each run keeps the platforms already
there.

## Claude Code

Set up this machine's Claude Code with the Coding Tool Optimizer, from
https://github.com/hieunguyen7337/coding-tool-optimizer. It is a shared usage policy, a dispatcher for worker lanes on
the plans I already pay for, and a usage meter.

**1. Get the release.** Download two files from the repository's latest GitHub Release into a new scratch folder:
- https://github.com/hieunguyen7337/coding-tool-optimizer/releases/latest/download/coding-tool-optimizer-bundle.sh
- https://github.com/hieunguyen7337/coding-tool-optimizer/releases/latest/download/SHA256SUMS

Check the bundle's sha256 against its line in `SHA256SUMS` (`sha256sum`, or `shasum -a 256` on macOS). If it does
not match, stop and tell me.

**2. Inspect it before running anything.** Show me its header, `sed -n '1,/^DEST=/p' <bundle>`: the version, the
generation time and every file it writes, with its sha256. It extracts to `~/claude-usage-optimizer` (in a dry run
too), checks every file's sha256, and then runs `~/claude-usage-optimizer/install.sh`. The installer touches only
these:
- `~/.claude/CLAUDE.md`: one import line;
- `~/.claude/settings.json`, after a backup: keys are added only where absent, except the four view
  keys (`verbose: false`, `viewMode: "default"`, `tui: "fullscreen"`, `outputStyle: "Mobile"`), which
  are set unless I changed one by hand after an earlier install. `--no-view` skips them and the mod. It also adds
  the kit's hooks (`turn-meter hook` as `UserPromptSubmit` and as `Stop`, and the compaction hooks);
- `~/.claude/agents/`, `~/.claude/skills/mobile-view/` (the
  mobile-view mod), the kit's other mods and `kit-*` skills in `~/.claude/skills/`, and
  `~/.claude/output-styles/Mobile.md`: existing files are backed up before they're replaced;
- `~/.claude/usage-optimizer/`;
- symlinks in `~/.local/bin` (on Windows, bash and `.cmd` wrappers instead);
- `~/.config/lanes/`.

**3. Dry run.** Run `bash <bundle> --dry-run` and summarise what it would change. Then wait for my "go".

**4. Install.** On my "go", run `bash <bundle>`. Then verify:
- `grep -c '^@~/.claude/usage-optimizer/POLICY.md' ~/.claude/CLAUDE.md` prints 1;
- `~/.claude/usage-optimizer/bin/usage-status --no-agy` runs;
- `~/.claude/usage-optimizer/bin/lane luna -C <a scratch git repo you create> -b <a one-line brief file> -e medium --dry-run`
  prints the argv it would run;
- `~/.claude/usage-optimizer/bin/claude-prompts --latest --text` lists the questions of this session;
- `~/.claude/settings.json` has a `turn-meter hook` command under both `UserPromptSubmit` and `Stop`. Then
  send one prompt in this session and run `~/.claude/usage-optimizer/bin/turn-meter report`: it should show
  a row for that turn. This runs no worker lane;
- `claude plugin validate ~/.claude/skills/mobile-view` passes. Tell me to restart Claude Code to see
  the mobile view (`.` in an empty prompt lists my questions, Esc goes back, `/mobile-view off` turns it off).

**5. Report the installer's checklist.**
- Which CLIs are missing or too old: codex ≥ 0.156.1 (≥ 0.159.0 for terra, ≥ 0.159.1 for the sol and astra lanes);
  agy, amp, grok, cursor-agent and cline are optional worker lanes.
- Which logins and account switches I still need to do.

Give me the exact commands, but don't install CLIs, log in, or change account settings yourself.

**Ground rules**
- Don't run any worker lane for real: no model calls through codex, agy, claude, amp, grok, cursor-agent or cline.
- Don't change anything else on this machine.
- Never read or print credential files.
- If I name project-specific secret folders, add their absolute paths to
  `~/.config/lanes/mask.local`. Don't search for credentials yourself.
- If this machine needs its own rules, such as different lanes or local dispatchers, propose them
  for `~/.claude/CLAUDE.md` above the import line. Never edit `~/.claude/usage-optimizer/POLICY.md`: it's shared,
  and the next update overwrites it.

**Machine notes**
- On Windows, run the bundle from Git Bash (Claude Code's Bash tool); WSL isn't needed, and a copy
  installed inside WSL would not reach a natively installed Claude Code. The installer needs a working
  Python 3.8+ (`python3`, `python` or `py -3`), puts each tool's source at `~/.claude/usage-optimizer/bin/<tool>.py`
  behind bash and `.cmd` wrappers, and there is no credential mask: `lane` refuses glm
  unless `--no-mask`.
- macOS is untested. `lane`'s credential mask there uses `sandbox-exec`; show me any problem the dry run reports.
- If `~/claude-usage-optimizer` on this machine is a git checkout, it is a source checkout of the kit: the bundle
  refuses to extract over it. Stop and tell me; don't set `USAGE_OPTIMIZER_DIR` or touch the checkout.
- Never start `cline`, even for `--version`: it updates itself in a new window. The installer reads its
  version without starting it.
- If this machine has an older install under the name claude-kit (`~/.claude/kit`), the installer moves it
  over: it re-points the CLAUDE.md import and the statusline, and moves `~/.claude/kit` into its backup
  folder. Tell me the old `~/claude-kit` folder can then be deleted; don't delete it yourself.

Later updates use this same prompt. Re-running the bundle is safe.

## Codex CLI

Set up this machine's Codex CLI with the Coding Tool Optimizer, from
https://github.com/hieunguyen7337/coding-tool-optimizer: a shared usage policy for you as the main session, hooks that
meter each turn, worker lanes on the plans I already pay for, and usage meters.

**1. Get the release.** Download two files from the repository's latest GitHub Release into a new scratch folder:
- https://github.com/hieunguyen7337/coding-tool-optimizer/releases/latest/download/coding-tool-optimizer-bundle.sh
- https://github.com/hieunguyen7337/coding-tool-optimizer/releases/latest/download/SHA256SUMS

Check the bundle's sha256 against its line in `SHA256SUMS` (`sha256sum`, or `shasum -a 256` on macOS). If it does
not match, stop and tell me. Show me its header, `sed -n '1,/^DEST=/p' <bundle>`: the version and every file it
writes. It extracts to `~/claude-usage-optimizer` (in a dry run too) and runs that folder's `install.sh` with the
arguments you give it.

**2. Dry run.** Run `bash <bundle> --dry-run --platform codex` and summarise what it would change. Then wait for my
"go". It touches only these:
- `$CODEX_HOME/AGENTS.md` (`~/.codex/AGENTS.md` by default): one generated block between
  `<!-- usage-optimizer:start -->` and `<!-- usage-optimizer:end -->`, the kit's policy for Codex, under Codex's
  size limit. Anything else in that file stays;
- `hooks.json` in the same folder, after a backup: the kit's turn-start, turn-end and compaction hooks;
- `agents/kit-*.toml` in the same folder: the kit's sub-agent roles (a retired `kit-*` role is backed up, then
  removed; other roles stay);
- `~/.agents/skills/kit-*`: the kit's skills (other skills there stay);
- `~/.claude/usage-optimizer/`: the kit's files (the path is historical; Claude Code is not needed);
- `~/.local/bin` (on Windows, bash and `.cmd` wrappers) and `~/.config/lanes/`.

**3. Install.** On my "go", run `bash <bundle> --platform codex`. Then verify:
- `$CODEX_HOME/AGENTS.md` holds the block once (`grep -c 'usage-optimizer:start'` prints 1);
- `~/.claude/usage-optimizer/bin/usage-status --no-agy` runs and shows the ChatGPT window;
- `~/.claude/usage-optimizer/bin/lane luna -C <a scratch git repo you create> -b <a one-line brief file> -e medium --dry-run`
  prints the argv it would run.

Then tell me to open `/hooks` in Codex, trust the kit's hooks once, and start a new Codex session. After my next
prompt there, `~/.claude/usage-optimizer/bin/turn-meter report --last 1` should show a row for that turn.

**4. Report the installer's checklist.** Which CLIs are missing or too old (codex ≥ 0.156.1; agy, claude, amp,
grok and cursor-agent are optional worker lanes), and which logins I still need to do. Give me the exact commands,
but don't install CLIs, log in, or change account settings yourself.

**Ground rules**
- Don't run any worker lane for real: no model calls through codex, agy, claude, amp, grok or cursor-agent.
- Don't change `config.toml` or anything else on this machine. If `AGENTS.override.md` exists, tell me: Codex
  reads it before `AGENTS.md`, so the installer leaves it alone.
- Never read or print credential files (`~/.codex/auth.json` included).
- If this machine needs its own rules, propose them for `$CODEX_HOME/AGENTS.md` outside the kit's block.
- On Windows, run the bundle from Git Bash (`bash` on PATH) with Python 3.8+ (`python3`, `python` or `py -3`).
- Codex support is not yet checked against a live Codex session: report anything that does not behave as written.

Later updates use this same prompt. Re-running the bundle is safe.

## Amp

Set up this machine's Amp with the Coding Tool Optimizer, from https://github.com/hieunguyen7337/coding-tool-optimizer:
a shared usage policy for you as the main session, a plugin that meters each turn and shows a status item, worker
lanes on the plans I already pay for, and usage meters.

**1. Get the release.** Download two files from the repository's latest GitHub Release into a new scratch folder:
- https://github.com/hieunguyen7337/coding-tool-optimizer/releases/latest/download/coding-tool-optimizer-bundle.sh
- https://github.com/hieunguyen7337/coding-tool-optimizer/releases/latest/download/SHA256SUMS

Check the bundle's sha256 against its line in `SHA256SUMS` (`sha256sum`, or `shasum -a 256` on macOS). If it does
not match, stop and tell me. Show me its header, `sed -n '1,/^DEST=/p' <bundle>`: the version and every file it
writes. It extracts to `~/claude-usage-optimizer` (in a dry run too) and runs that folder's `install.sh` with the
arguments you give it.

**2. Dry run.** Run `bash <bundle> --dry-run --platform amp` and summarise what it would change. Then wait for my
"go". It touches only these:
- `~/.config/amp/AGENTS.md`, after a backup: a heading and two import lines for the kit's Amp notes and policy;
- `~/.config/amp/plugins/usage-optimizer.ts` and `usage-optimizer.paths.json`: the plugin;
- `~/.agents/skills/kit-*`: the kit's skills (other skills there stay);
- `~/.claude/usage-optimizer/`: the kit's files (the path is historical; Claude Code is not needed);
- `~/.local/bin` (on Windows, bash and `.cmd` wrappers) and `~/.config/lanes/`.

**3. Install.** On my "go", run `bash <bundle> --platform amp`. Then verify:
- `~/.claude/usage-optimizer/bin/usage-status --no-agy` runs and shows Amp's credits;
- `~/.claude/usage-optimizer/bin/lane luna -C <a scratch git repo you create> -b <a one-line brief file> -e medium --dry-run`
  prints the argv it would run;
- `grep -c 'usage-optimizer' ~/.config/amp/AGENTS.md` prints at least 1.

Then tell me to restart Amp or run `plugins: reload`, check that the kit's status item shows, and ask you in a new
thread which Coding Tool Optimizer version your instructions name.

**4. Report the installer's checklist.** Which CLIs are missing or too old (amp; codex, agy, claude, grok and
cursor-agent are optional worker lanes), and which logins I still need to do. Give me the exact commands, but don't
install CLIs, log in, or change account settings yourself.

**Ground rules**
- Don't run any worker lane for real: no model calls through codex, agy, claude, grok or cursor-agent.
- Don't change `~/.config/amp/settings.json`, `~/.config/AGENTS.md` or anything else on this machine.
- Never read or print credential files or Amp's secrets store.
- If this machine needs its own rules, propose them for `~/.config/amp/AGENTS.md` above the kit's imports.
- On Windows, run the bundle from Git Bash (`bash` on PATH) with Python 3.8+ (`python3`, `python` or `py -3`).

Later updates use this same prompt. Re-running the bundle is safe.
