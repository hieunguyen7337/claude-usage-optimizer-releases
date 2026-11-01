Set up this machine's Claude Code with my Claude Usage Optimizer, from <ARTIFACT_URL>. It is a shared usage policy,
a dispatcher for my worker lanes, and a usage meter.

**1. Get the bundle.** Use your Artifact tool: `action: "read"`, url <ARTIFACT_URL>, path `claude-usage-optimizer-bundle.sh`.
Note where it saves the file.
- If you have no Artifact tool, stop and ask me for the file. I'll copy it from the page, or
  `scp` it from my server.

**2. Inspect it before running anything.**
- Show me its header, `sed -n '1,/^DEST=/p' <file>`: the version, generation time and every file it
  writes, with its sha256.
- Check the sha256 of the whole file against the one on the page, if I give it to you.

It extracts to `~/claude-usage-optimizer` (in a dry run too), verifies every file's sha256, and then runs
`~/claude-usage-optimizer/install.sh`.
The installer touches only these:
- `~/.claude/CLAUDE.md`: one import line;
- `~/.claude/settings.json`, after a backup: keys are added only where absent, except the four view
  keys (`verbose: false`, `viewMode: "default"`, `tui: "fullscreen"`, `outputStyle: "Mobile"`), which
  are set unless I changed one by hand after an earlier install. `--no-view` skips them and the mod. It also adds
  two hooks, `turn-meter hook` as `UserPromptSubmit` and as `Stop`;
- `~/.claude/agents/`, `~/.claude/skills/mobile-view/` (the
  mobile-view mod) and `~/.claude/output-styles/Mobile.md`: existing files are backed up before
  they're replaced;
- `~/.claude/usage-optimizer/`;
- symlinks in `~/.local/bin` (on Windows, bash and `.cmd` wrappers instead);
- `~/.config/lanes/`.

**3. Dry run.** Run `bash <file> --dry-run` and summarise what it would change. Then wait for my "go".

**4. Install.** On my "go", run `bash <file>`. Then verify:
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
- Which CLIs are missing or too old: codex ≥ 0.156.1 (≥ 0.159.0 for terra, ≥ 0.159.1 for the sol and astra lanes), agy, cline.
- Which logins and account switches I still need to do.

Give me the exact commands, but don't install CLIs, log in, or change account settings yourself.

**Ground rules**
- Don't run any worker lane for real: no model calls through codex, agy, claude or cline.
- Don't change anything else on this machine.
- Never read or print credential files.
- If I name project-specific secret folders, add their absolute paths to
  `~/.config/lanes/mask.local`. Don't search for credentials yourself.
- If this machine needs its own rules, such as different lanes or local dispatchers, propose them
  for `~/.claude/CLAUDE.md` above the import line. Never edit `~/.claude/usage-optimizer/POLICY.md`: it's shared,
  and the next update overwrites it.

**Machine notes**
- On macOS, `lane`'s credential mask uses `sandbox-exec` and is untested. Show me any problem the
  dry run reports.
- On Windows, run the bundle from Git Bash (Claude Code's Bash tool); WSL isn't needed, and a copy
  installed inside WSL would not reach a natively installed Claude Code. The installer needs a working
  Python 3.8+ (`python3`, `python` or `py -3`), puts each tool's source at `~/.claude/usage-optimizer/bin/<tool>.py`
  behind bash and `.cmd` wrappers, and there is no credential mask: `lane` refuses glm
  unless `--no-mask`.
- If `~/claude-usage-optimizer` on this machine is a git checkout, it is the kit's source: the bundle
  refuses to extract over it. Stop and tell me; don't set `USAGE_OPTIMIZER_DIR` or touch the checkout.
- Never start `cline`, even for `--version`: it updates itself in a new window. The installer reads its
  version without starting it.
- If this machine has it under its old name, claude-kit (`~/.claude/kit`), the installer moves it
  over: it re-points the CLAUDE.md import and the statusline, and moves `~/.claude/kit` into its backup
  folder. Tell me the old `~/claude-kit` folder can then be deleted; don't delete it yourself.

Without Claude Code, clone `https://github.com/hieunguyen7337/claude-usage-optimizer-releases` and run
`bash install.sh`, or download a bundle from its Releases page and verify it against `SHA256SUMS`.

Later updates use this same prompt. Re-running the bundle is safe.
