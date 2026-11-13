import glob
import hashlib
import json
import os
import sys
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WINDOWS = os.name == "nt"
SEED = {"verbose": True, "tui": "fullscreen", "permissions": {"defaultMode": "bypassPermissions"}}
TOOLS = ["lane", "lane-stats", "lane-bench", "usage-status", "claude-statusline", "claude-prompts", "turn-meter",
         "kit-update"]
STAMP = re.compile(r"usage-optimizer-\d{8}T\d{6}Z(?:-\d\d)?")
# The lines that name each file the installer copies. The golden compares everything else.
PER_FILE = ("Absent, installing:", "Identical, skipping:", "Different, backing up and replacing:", "Installing mod ")

# What a flagless run printed on 2026-11-13 (before --platform), with the two lines the platform list adds:
# "Platforms: ..." and "Recorded the platform list in ...". Paths are <HOME>, <SOURCE>, <PY>, <OS>.
GOLDEN_FLAGLESS_OUTPUT = """Operating system: <OS>
Python: <PY>
Platforms: claude-code (default)

CLI check skipped (USAGE_OPTIMIZER_SKIP_CLI_CHECK=1)

Copying Claude Usage Optimizer to <HOME>/.claude/usage-optimizer
Recorded the source checkout for update checks: <SOURCE>
Recorded the platform list in <HOME>/.claude/usage-optimizer/platforms.installed

Installing agent files

Installing skill files

Installing mods

Installing the mobile view (mod and output style)

Updating CLAUDE.md

Merging settings.json
settings.json: hooks.UserPromptSubmit += {"hooks": [{"type": "command", "command": "<HOME>/.claude/usage-optimizer/bin/turn-meter hook", "timeout": 5}]}
settings.json: hooks.Stop += {"hooks": [{"type": "command", "command": "<HOME>/.claude/usage-optimizer/bin/turn-meter hook", "timeout": 5}]}
settings.json: hooks.PreCompact += {"matcher": "auto", "hooks": [{"type": "command", "command": "<HOME>/.claude/usage-optimizer/bin/turn-meter compact-gate", "timeout": 10}]}
settings.json: hooks.SessionStart += {"matcher": "compact", "hooks": [{"type": "command", "command": "<HOME>/.claude/usage-optimizer/bin/turn-meter resume-context", "timeout": 10}]}
settings.json: hooks.SessionStart += {"matcher": "startup|resume|compact", "hooks": [{"type": "command", "command": "<HOME>/.claude/usage-optimizer/bin/claude-statusline session-start", "timeout": 10}]}
settings.json: hooks.PostCompact += {"hooks": [{"type": "command", "command": "<HOME>/.claude/usage-optimizer/bin/turn-meter hook", "timeout": 10}]}
settings.json: hooks.SubagentStop += {"matcher": "^lane-", "hooks": [{"type": "command", "command": "<HOME>/.claude/usage-optimizer/bin/lane hook subagent-stop", "timeout": 30}]}
settings.json: verbose: true -> false
settings.json: viewMode: (absent) -> "default"
settings.json: outputStyle: (absent) -> "Mobile"
settings.json merged and validated.

Installing tools on PATH

Preparing ~/.config/lanes

Final checklist
Missing CLIs: none
Logins: codex login; agy login.
Account switches: ChatGPT data controls off; Antigravity training off; Claude model-training setting off; Claude extra usage: check it (the policy assumes it is off, so there is no reserve).
Verify: ~/.claude/usage-optimizer/bin/usage-status --no-agy
Verify: ~/.claude/usage-optimizer/bin/lane luna -C <dir> -b <brief> -e medium --dry-run
Verify: ~/.claude/usage-optimizer/bin/claude-prompts --latest --text (your questions in the newest session)
Updates: the statusline checks the origin of <SOURCE> every 6 hours and names a newer release;
  check now with ~/.claude/usage-optimizer/bin/kit-update check (USAGE_OPTIMIZER_UPDATE_CHECK=off turns it off).
Verify: claude plugin list shows sessions@skills-dir (the Sessions pane: /sessions, or . in an empty prompt)
Verify: claude plugin validate <HOME>/.claude/skills/mobile-view; claude plugin list shows mobile-view@skills-dir
Mobile view: restart Claude Code. Tool calls show one line each (click one to expand it), long code
  blocks fold, > in an empty prompt lists your questions (Esc goes back), /mobile-view off shows the stock view.
Restart Claude Code sessions to load the new settings."""

# Files a flagless run writes that do not come from a copy of the kit tree: the Claude Code files, the bookkeeping
# files, ~/.config/lanes and the PATH links. platforms.installed is the one new file the platform list adds.
FIXED_FLAGLESS_FILES = [
    ".claude/CLAUDE.md",
    ".claude/settings.json",
    ".claude/output-styles/Mobile.md",
    ".claude/skills/mobile-view/install-paths.json",
    ".claude/usage-optimizer/source.json",
    ".claude/usage-optimizer/view-settings.applied.json",
    ".claude/usage-optimizer/platforms.installed",
    ".claude/backups/usage-optimizer-<STAMP>/CLAUDE.md",
    ".claude/backups/usage-optimizer-<STAMP>/settings.json",
    ".config/lanes/mask.local",
] + [".local/bin/" + tool for tool in TOOLS]


def find_bash():
    # On Windows `bash` on PATH may be WSL's, which cannot see this checkout's Windows paths.
    if WINDOWS:
        for candidate in (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files (x86)\Git\bin\bash.exe"):
            if os.path.exists(candidate):
                return candidate
        return None
    return shutil.which("bash")


BASH = find_bash()


def read_bytes(path):
    with open(path, "rb") as stream:
        return stream.read()


def read_text(path):
    with open(path, encoding="utf-8") as stream:
        return stream.read()


def files_under(base):
    """Relative posix paths of the files under `base`, compiled caches left out."""
    found = []
    for current, dirs, names in os.walk(base):
        dirs[:] = [name for name in dirs if name != "__pycache__"]
        for name in names:
            if not name.endswith(".pyc"):
                found.append(os.path.relpath(os.path.join(current, name), base).replace(os.sep, "/"))
    return sorted(found)


def kit_items():
    """KIT_ITEMS as install.sh lists them, read from install.sh so this list is never copied."""
    match = re.search(r"^KIT_ITEMS=\(([^)]*)\)", read_text(os.path.join(ROOT, "install.sh")), re.MULTILINE)
    return match.group(1).split()


def normalized_output(text, home):
    text = text.replace(home, "<HOME>").replace(os.path.realpath(ROOT), "<SOURCE>").replace(ROOT, "<SOURCE>")
    text = re.sub(r"^Python: .*$", "Python: <PY>", text, flags=re.MULTILINE)
    text = re.sub(r"^Operating system: .*$", "Operating system: <OS>", text, flags=re.MULTILINE)
    text = STAMP.sub("usage-optimizer-<STAMP>", text)
    return [line for line in text.splitlines() if not line.startswith(PER_FILE)]


def stable_snapshot(home):
    """snapshot, without source.json: every run rewrites it with the time of the install, by design."""
    result = snapshot(home)
    result.pop(".claude/usage-optimizer/source.json", None)
    return result


def snapshot(home):
    """Every path under home: a file's digest, a symlink's target, or "dir"."""
    result = {}
    for current, dirs, names in os.walk(home):
        for name in dirs + names:
            full = os.path.join(current, name)
            key = os.path.relpath(full, home).replace(os.sep, "/")
            if os.path.islink(full):
                result[key] = "link:" + os.readlink(full)
            elif os.path.isdir(full):
                result[key] = "dir"
            else:
                result[key] = hashlib.sha256(read_bytes(full)).hexdigest()
    return result


@unittest.skipIf(BASH is None, "Git Bash (or bash) is not installed")

def slashes(path):
    return path.replace("\\", "/")

class InstallPlatformTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = os.path.realpath(self.temp.name)
        self.claude = os.path.join(self.home, ".claude")
        os.makedirs(self.claude)
        self.settings_path = os.path.join(self.claude, "settings.json")
        with open(self.settings_path, "w", encoding="utf-8") as stream:
            json.dump(SEED, stream, indent=2)
        self.prefix = os.path.join(self.claude, "usage-optimizer")
        self.codex_home = os.path.join(self.home, ".codex")
        self.amp_dir = os.path.join(self.home, ".config", "amp")

    def tearDown(self):
        self.temp.cleanup()

    def run_install(self, *args, env=None):
        environment = dict(os.environ)
        environment.update({"HOME": self.home, "USERPROFILE": self.home, "CODEX_HOME": self.codex_home,
                            "USAGE_OPTIMIZER_SKIP_CLI_CHECK": "1"})
        environment.pop("CLAUDE_CONFIG_DIR", None)
        environment.update(env or {})
        return subprocess.run(
            [BASH, ROOT.replace("\\", "/") + "/install.sh", *args],
            cwd=self.home, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            encoding="utf-8", errors="replace", timeout=900 if os.name == "nt" else 300, check=False,
        )

    def install(self, *args, env=None, expect=0):
        result = self.run_install(*args, env=env)
        self.assertEqual(result.returncode, expect, "install.sh %s exited %s:\n%s\n%s"
                         % (" ".join(args), result.returncode, result.stdout, result.stderr))
        return result

    def settings(self):
        return json.loads(read_text(self.settings_path))

    def backups(self):
        return sorted(glob.glob(os.path.join(self.claude, "backups", "usage-optimizer-*")))

    def expected_flagless_files(self):
        expected = set(FIXED_FLAGLESS_FILES)
        for item in kit_items():
            base = os.path.join(ROOT, item)
            if os.path.isfile(base):
                expected.add(".claude/usage-optimizer/" + item)
            elif os.path.isdir(base):
                expected.update(".claude/usage-optimizer/%s/%s" % (item, rel) for rel in files_under(base))
        for parts in (("skills",), ("private", "skills")):
            packs = os.path.join(ROOT, *parts)
            if not os.path.isdir(packs):
                continue
            for pack in sorted(os.listdir(packs)):
                if os.path.isdir(os.path.join(packs, pack)):
                    for rel in files_under(os.path.join(packs, pack)):
                        expected.add(".claude/usage-optimizer/skills/%s/%s" % (pack, rel))
                        expected.add(".claude/skills/%s/%s" % (pack, rel))
        for agent in glob.glob(os.path.join(ROOT, "agents", "*.md")):
            expected.add(".claude/agents/" + os.path.basename(agent))
        for mod in sorted(glob.glob(os.path.join(ROOT, "mods", "*"))):
            name = os.path.basename(mod)
            for rel in files_under(mod):
                parts = rel.split("/")
                if parts[0] in ("tests", "node_modules") or rel.startswith(".claude-plugin/types/") \
                        or "node_modules" in parts or parts[-1] == "tsconfig.json":
                    continue
                expected.add(".claude/skills/%s/%s" % (name, rel))
        return expected

    # ----- the flagless run is today's run -------------------------------------------------------------------------

    @unittest.skipUnless(os.path.isdir(os.path.join(ROOT, ".git")), "the kit under test is not a git checkout")
    def test_flagless_run_prints_todays_output_and_writes_todays_paths(self):
        result = self.install(env={"CODEX_HOME": ""})
        self.assertEqual(normalized_output(result.stdout, self.home), GOLDEN_FLAGLESS_OUTPUT.splitlines())

        written = {STAMP.sub("usage-optimizer-<STAMP>", key) for key, value in snapshot(self.home).items()
                   if value != "dir" and "__pycache__" not in key}
        self.assertEqual(written, self.expected_flagless_files())
        for item in kit_items():
            base = os.path.join(ROOT, item)
            installed = os.path.join(self.prefix, item)
            if os.path.isfile(base):
                self.assertEqual(read_bytes(base), read_bytes(installed), item)
            elif os.path.isdir(base):
                for rel in files_under(base):
                    self.assertEqual(read_bytes(os.path.join(base, rel)), read_bytes(os.path.join(installed, rel)))

    def test_flagless_run_writes_nothing_for_amp_or_codex(self):
        self.install(env={"CODEX_HOME": ""})
        self.assertFalse(os.path.exists(self.amp_dir))
        self.assertFalse(os.path.exists(self.codex_home))
        self.assertFalse(os.path.exists(os.path.join(self.prefix, "platforms")))
        self.assertEqual(read_text(os.path.join(self.prefix, "platforms.installed")), "claude-code\n")

    # ----- amp ------------------------------------------------------------------------------------------------------

    def test_amp_installs_the_adapter_and_leaves_amp_settings_and_claude_settings_alone(self):
        before_settings = read_bytes(self.settings_path)
        result = self.install("--platform", "amp")
        self.assertEqual(read_bytes(self.settings_path), before_settings)
        self.assertFalse(os.path.exists(os.path.join(self.amp_dir, "settings.json")))
        self.assertFalse(os.path.exists(os.path.join(self.home, ".config", "AGENTS.md")))
        self.assertFalse(os.path.exists(os.path.join(self.claude, "CLAUDE.md")))
        self.assertFalse(os.path.exists(os.path.join(self.claude, "agents")))

        plugin = os.path.join(self.amp_dir, "plugins", "usage-optimizer.ts")
        self.assertEqual(read_bytes(plugin), read_bytes(os.path.join(ROOT, "platforms", "amp", "usage-optimizer.ts")))
        self.assertEqual(read_bytes(os.path.join(self.prefix, "platforms", "amp", "PLATFORM.md")),
                         read_bytes(os.path.join(ROOT, "platforms", "amp", "PLATFORM.md")))

        with open(os.path.join(self.amp_dir, "plugins", "usage-optimizer.paths.json"), encoding="utf-8") as stream:
            paths = json.load(stream)
        self.assertEqual(sorted(paths), ["prefix", "python"])
        self.assertEqual(slashes(paths["prefix"]), slashes(self.prefix))
        self.assertTrue(os.path.exists(paths["python"]), paths)

        self.assertEqual(read_text(os.path.join(self.amp_dir, "AGENTS.md")).splitlines(), [
            "# Claude Usage Optimizer on Amp (shared across machines; edit its source, not this line)",
            "@~/.claude/usage-optimizer/platforms/amp/PLATFORM.md",
            "@~/.claude/usage-optimizer/POLICY.md",
        ])
        self.assertIn("restart Amp or run `plugins: reload`", result.stdout)
        self.assertEqual(read_text(os.path.join(self.prefix, "platforms.installed")), "amp\n")

    def test_amp_run_twice_changes_nothing_and_makes_no_backup(self):
        self.install("--platform", "amp")
        first = stable_snapshot(self.home)
        second = self.install("--platform", "amp")
        self.assertEqual(stable_snapshot(self.home), first)
        self.assertEqual(self.backups(), [])
        self.assertIn("Amp policy imports already present; skipping.", second.stdout)
        # Git Bash prints its own spelling of the path (/tmp/... on Windows), so match the tail.
        self.assertRegex(second.stdout, r"Identical, skipping: \S*/\.config/amp/plugins/usage-optimizer\.ts")

    def test_amp_keeps_other_text_in_agents_md_and_adds_only_the_missing_import(self):
        os.makedirs(self.amp_dir)
        agents = os.path.join(self.amp_dir, "AGENTS.md")
        with open(agents, "w", encoding="utf-8") as stream:
            stream.write("# my notes\n@~/.claude/usage-optimizer/POLICY.md\n")
        self.install("--platform", "amp")
        text = read_text(agents)
        self.assertTrue(text.startswith("# my notes\n@~/.claude/usage-optimizer/POLICY.md\n"))
        self.assertEqual(text.count("@~/.claude/usage-optimizer/POLICY.md"), 1)
        self.assertEqual(text.count("@~/.claude/usage-optimizer/platforms/amp/PLATFORM.md"), 1)
        backup = os.path.join(self.backups()[0], "amp", "AGENTS.md")
        self.assertEqual(read_text(backup), "# my notes\n@~/.claude/usage-optimizer/POLICY.md\n")

    def test_amp_plugin_changed_by_hand_is_backed_up_and_replaced(self):
        self.install("--platform", "amp")
        plugin = os.path.join(self.amp_dir, "plugins", "usage-optimizer.ts")
        with open(plugin, "w", encoding="utf-8") as stream:
            stream.write("// edited by hand\n")
        self.install("--platform", "amp")
        self.assertEqual(read_bytes(plugin), read_bytes(os.path.join(ROOT, "platforms", "amp", "usage-optimizer.ts")))
        backup = os.path.join(self.backups()[0], "amp", "plugins", "usage-optimizer.ts")
        self.assertEqual(read_text(backup), "// edited by hand\n")

    # ----- codex ----------------------------------------------------------------------------------------------------

    def turn_meter_command(self, args):
        # On Windows the hooks name Python and turn-meter.py with forward slashes; elsewhere the bash wrapper.
        if os.name == "nt":
            return "{} {}/bin/turn-meter.py {}".format(slashes(sys.executable), slashes(self.prefix), args)
        return os.path.join(self.prefix, "bin", "turn-meter") + " " + args

    def codex_block(self):
        kit = read_text(os.path.join(ROOT, "platforms", "codex", "AGENTS.kit.md")).rstrip("\n")
        return "<!-- usage-optimizer:start -->\n" + kit + "\n<!-- usage-optimizer:end -->\n"

    def test_codex_writes_the_block_and_the_three_hooks_and_leaves_config_alone(self):
        os.makedirs(self.codex_home)
        config = os.path.join(self.codex_home, "config.toml")
        with open(config, "w", encoding="utf-8") as stream:
            stream.write('model = "gpt-6"\n')
        result = self.install("--platform", "codex")

        self.assertEqual(read_text(config), 'model = "gpt-6"\n')
        self.assertEqual(read_bytes(os.path.join(self.prefix, "platforms", "codex", "PLATFORM.md")),
                         read_bytes(os.path.join(ROOT, "platforms", "codex", "PLATFORM.md")))
        self.assertEqual(read_text(os.path.join(self.codex_home, "AGENTS.md")), self.codex_block())
        hooks = json.loads(read_text(os.path.join(self.codex_home, "hooks.json")))
        self.assertEqual(sorted(hooks["hooks"]), ["PreCompact", "Stop", "UserPromptSubmit"])
        expected = {
            "UserPromptSubmit": ("hook --platform codex", 5),
            "Stop": ("hook --platform codex", 5),
            "PreCompact": ("compact-gate --platform codex", 10),
        }
        for event, (args, timeout) in expected.items():
            handler = hooks["hooks"][event][0]["hooks"][0]
            self.assertEqual(handler, {"type": "command",
                                       "command": self.turn_meter_command(args),
                                       "timeout": timeout})
        self.assertEqual(sorted(hooks), ["hooks"])
        self.assertIn("/hooks", result.stdout)
        self.assertIn('tui.status_line = ["model-with-reasoning", "context-used", "five-hour-limit", "weekly-limit"]',
                      result.stdout)
        self.assertIn("unverified against a live Codex session", result.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".config", "AGENTS.md")))

    def test_codex_replaces_an_older_block_and_keeps_the_text_around_it(self):
        os.makedirs(self.codex_home)
        agents = os.path.join(self.codex_home, "AGENTS.md")
        with open(agents, "w", encoding="utf-8") as stream:
            stream.write("# my notes\n\n<!-- usage-optimizer:start -->\nold block\n<!-- usage-optimizer:end -->\n\n"
                         "after the block\n")
        self.install("--platform", "codex")
        text = read_text(agents)
        self.assertTrue(text.startswith("# my notes\n\n"))
        self.assertTrue(text.endswith("\n\nafter the block\n"))
        self.assertNotIn("old block", text)
        self.assertEqual(text.count("<!-- usage-optimizer:start -->"), 1)
        self.assertIn(self.codex_block(), text)
        self.assertEqual(read_text(os.path.join(self.backups()[0], "codex", "AGENTS.md")).count("old block"), 1)

    def test_codex_hooks_keep_other_hooks_and_a_second_run_adds_nothing(self):
        os.makedirs(self.codex_home)
        hooks_path = os.path.join(self.codex_home, "hooks.json")
        other = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "/opt/other/bin/tool hook",
                                                "timeoutSec": 3}]}]}, "keep": 1}
        with open(hooks_path, "w", encoding="utf-8") as stream:
            json.dump(other, stream)
        self.install("--platform", "codex")
        hooks = json.loads(read_text(hooks_path))
        self.assertEqual(hooks["keep"], 1)
        self.assertEqual([group["hooks"][0]["command"] for group in hooks["hooks"]["Stop"]],
                         ["/opt/other/bin/tool hook", self.turn_meter_command("hook --platform codex")])
        self.assertEqual(json.loads(read_text(os.path.join(self.backups()[0], "codex", "hooks.json"))), other)

        first = snapshot(self.codex_home)
        second = self.install("--platform", "codex")
        self.assertEqual(snapshot(self.codex_home), first)
        self.assertIn("Codex hooks.json already has the turn-meter hooks; skipping.", second.stdout)
        self.assertIn("Codex AGENTS.md already has the current usage-optimizer block; skipping.", second.stdout)
        self.assertEqual(len(self.backups()), 1)

    def test_codex_warns_about_an_agents_override_file(self):
        os.makedirs(self.codex_home)
        with open(os.path.join(self.codex_home, "AGENTS.override.md"), "w", encoding="utf-8") as stream:
            stream.write("# override\n")
        result = self.install("--platform", "codex")
        self.assertIn("AGENTS.override.md exists; Codex reads it instead of AGENTS.md", result.stderr)
        self.assertEqual(read_text(os.path.join(self.codex_home, "AGENTS.override.md")), "# override\n")

    def test_codex_invalid_hooks_json_stops_before_anything_is_written(self):
        os.makedirs(self.codex_home)
        with open(os.path.join(self.codex_home, "AGENTS.md"), "w", encoding="utf-8") as stream:
            stream.write("# plain\n")
        with open(os.path.join(self.codex_home, "hooks.json"), "w", encoding="utf-8") as stream:
            stream.write("not json\n")
        before = snapshot(self.codex_home)
        result = self.install("--platform", "codex", expect=1)
        self.assertIn("is not valid JSON", result.stderr)
        self.assertEqual(snapshot(self.codex_home), before)
        with open(os.path.join(self.codex_home, "AGENTS.md"), encoding="utf-8") as stream:
            self.assertEqual(stream.read(), "# plain\n")

    def test_codex_unmatched_marker_stops_before_anything_is_written(self):
        os.makedirs(self.codex_home)
        with open(os.path.join(self.codex_home, "AGENTS.md"), "w", encoding="utf-8") as stream:
            stream.write("<!-- usage-optimizer:start -->\nno end marker\n")
        before = snapshot(self.codex_home)
        result = self.install("--platform", "codex", expect=1)
        self.assertIn("unmatched or repeated", result.stderr)
        self.assertEqual(snapshot(self.codex_home), before)

    def test_codex_home_defaults_to_dot_codex_under_home(self):
        self.install("--platform", "codex", env={"CODEX_HOME": ""})
        self.assertTrue(os.path.isfile(os.path.join(self.home, ".codex", "hooks.json")))
        self.assertTrue(os.path.isfile(os.path.join(self.home, ".codex", "AGENTS.md")))

    # ----- dry run, the saved list, and bad input -------------------------------------------------------------------

    def test_dry_run_prints_each_platforms_actions_and_writes_nothing(self):
        os.makedirs(self.codex_home)
        with open(os.path.join(self.codex_home, "config.toml"), "w", encoding="utf-8") as stream:
            stream.write("model = 'x'\n")
        before = snapshot(self.home)
        result = self.install("--dry-run", "--platform", "amp,codex")
        self.assertEqual(snapshot(self.home), before)
        self.assertIn("Platforms: amp,codex (--platform)", result.stdout)
        self.assertIn("DRY-RUN: append the Amp heading", result.stdout)
        self.assertIn("DRY-RUN: cp -p", result.stdout)
        self.assertIn("DRY-RUN: Codex AGENTS.md: add the usage-optimizer block", result.stdout)
        self.assertIn("DRY-RUN: Codex hooks.json would gain UserPromptSubmit", result.stdout)
        self.assertIn("DRY-RUN: write", result.stdout)
        self.assertIn("DRY-RUN: record the platform list amp,codex", result.stdout)
        self.assertNotIn("DRY-RUN: merge settings", result.stdout)
        self.assertNotIn("settings.json: ", result.stdout)

    def test_the_saved_list_is_used_by_a_later_run_without_the_flag(self):
        self.install("--platform", "codex,amp,codex")
        self.assertEqual(read_text(os.path.join(self.prefix, "platforms.installed")), "amp,codex\n")
        before_settings = read_bytes(self.settings_path)
        result = self.install()
        self.assertIn("Platforms: amp,codex (saved in", result.stdout)
        self.assertEqual(read_bytes(self.settings_path), before_settings)
        self.assertFalse(os.path.exists(os.path.join(self.claude, "CLAUDE.md")))
        self.assertIn("Codex hooks.json already has the turn-meter hooks; skipping.", result.stdout)

        self.install("--platform", "claude-code")
        self.assertEqual(read_text(os.path.join(self.prefix, "platforms.installed")), "claude-code\n")
        self.assertIn("settings.json merged and validated.", self.install().stdout)

    def test_a_bad_platform_name_is_refused_before_anything_is_written(self):
        before = snapshot(self.home)
        for value in ("amp,bogus", "", ",", "amp,,codex"):
            result = self.install("--platform", value, expect=2)
            self.assertRegex(result.stderr, "unknown platform|no platform given")
        self.assertEqual(snapshot(self.home), before)

    def test_a_missing_value_for_platform_is_a_usage_error(self):
        self.install("--platform", expect=2)

    def test_a_corrupt_saved_list_stops_the_run(self):
        os.makedirs(self.prefix)
        with open(os.path.join(self.prefix, "platforms.installed"), "w", encoding="utf-8") as stream:
            stream.write("amp,nope\n")
        result = self.install(expect=1)
        self.assertIn("holds an invalid platform list", result.stderr)

    def test_spaces_and_repeats_are_normalised_and_saved_in_order(self):
        self.install("--platform", " codex , amp ,codex")
        self.assertEqual(read_text(os.path.join(self.prefix, "platforms.installed")), "amp,codex\n")


if __name__ == "__main__":
    unittest.main()
