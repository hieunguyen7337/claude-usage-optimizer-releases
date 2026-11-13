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

**Without Claude Code.** The prompt above needs Claude Code's Artifact tool. For Amp or Codex CLI, paste one of
these into that agent instead. Both use the public releases repository, not the artifact.

Amp session:

```
Set up this machine's Amp with my Claude Usage Optimizer: a shared usage policy, a plugin that meters each turn,
and a worker lane for Amp. Use https://github.com/hieunguyen7337/claude-usage-optimizer-releases.

1. Clone that repository. Check the release against its SHA256SUMS (from its latest GitHub Release) and say
   which files you checked. If they do not match, stop and tell me.
2. Run `bash install.sh --dry-run --platform amp` in the clone and summarise what it would change. Then wait
   for my "go".
3. On my "go", run `bash install.sh --platform amp`.
4. Verify: restart Amp or run `plugins: reload`, and check that the status item shows. Then run
   `amp -x "State the Claude Usage Optimizer version in your instructions"`.

Don't log in to Amp, don't change its settings file, and don't run a worker lane for real. Report what does not
behave as written.
```

Codex CLI session:

```
Set up this machine's Codex CLI with my Claude Usage Optimizer: a shared usage policy, hooks that meter each turn,
and a worker lane. Use https://github.com/hieunguyen7337/claude-usage-optimizer-releases.

1. Clone that repository. Check the release against its SHA256SUMS (from its latest GitHub Release) and say
   which files you checked. If they do not match, stop and tell me.
2. Run `bash install.sh --dry-run --platform codex` in the clone and summarise what it would change. Then wait
   for my "go".
3. On my "go", run `bash install.sh --platform codex`.
4. Verify: open `/hooks` in Codex and trust the kit's hooks once. Then send one prompt and check that the turn
   is recorded with `~/.claude/usage-optimizer/bin/turn-meter report`.

Don't log in to Codex, don't change `config.toml`, and don't run a worker lane for real. Codex support is not yet
checked against a live Codex session, so report anything that does not behave as written.
```

Later updates use this same prompt. Re-running the bundle is safe.
