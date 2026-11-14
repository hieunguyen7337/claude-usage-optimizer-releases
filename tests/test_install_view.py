import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WINDOWS = os.name == "nt"


def find_bash():
    # On Windows `bash` on PATH may be WSL's, which cannot see this checkout's Windows paths.
    if WINDOWS:
        for candidate in (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files (x86)\Git\bin\bash.exe"):
            if os.path.exists(candidate):
                return candidate
        return None
    return shutil.which("bash")


BASH = find_bash()
GIT = shutil.which("git")


def same_path(first, second):
    return os.path.normcase(os.path.realpath(first)) == os.path.normcase(os.path.realpath(second))


def is_checkout(folder):
    if GIT is None:
        return False
    result = subprocess.run([GIT, "-C", folder, "rev-parse", "--show-toplevel"], stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, encoding="utf-8", timeout=60, check=False)
    return result.returncode == 0 and same_path(result.stdout.strip(), folder)


ROOT_IS_CHECKOUT = is_checkout(ROOT)
SEED = {"verbose": True, "tui": "fullscreen", "permissions": {"defaultMode": "bypassPermissions"}}


@unittest.skipIf(BASH is None, "Git Bash (or bash) is not installed")
class InstallViewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = self.temp.name
        self.claude = os.path.join(self.home, ".claude")
        os.makedirs(self.claude)
        self.settings_path = os.path.join(self.claude, "settings.json")
        with open(self.settings_path, "w", encoding="utf-8") as stream:
            json.dump(SEED, stream, indent=2)
        self.prefix = os.path.join(self.claude, "usage-optimizer")
        self.mod = os.path.join(self.claude, "skills", "mobile-view")

    def tearDown(self):
        self.temp.cleanup()

    def install(self, *args, env_extra=None, source=ROOT):
        env = dict(os.environ)
        env.update({"HOME": self.home, "USERPROFILE": self.home, "USAGE_OPTIMIZER_SKIP_CLI_CHECK": "1"})
        env.update(env_extra or {})
        env.pop("CLAUDE_CONFIG_DIR", None)
        result = subprocess.run(
            [BASH, source.replace("\\", "/") + "/install.sh", *args],
            cwd=self.home, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            encoding="utf-8", errors="replace", timeout=300, check=False,
        )
        self.assertEqual(result.returncode, 0, "install.sh failed:\n%s\n%s" % (result.stdout, result.stderr))
        return result

    def settings(self):
        with open(self.settings_path, encoding="utf-8") as stream:
            return json.load(stream)

    def test_install_sets_the_view_and_installs_the_mod(self):
        result = self.install()
        settings = self.settings()
        self.assertIs(settings["verbose"], False)
        self.assertEqual(settings["viewMode"], "default")
        self.assertEqual(settings["tui"], "fullscreen")
        self.assertEqual(settings["outputStyle"], "Mobile")
        self.assertEqual(settings["permissions"], SEED["permissions"])
        self.assertEqual(settings["model"], "opus[1m]")
        self.assertEqual(settings["effortLevel"], "xhigh")
        self.assertEqual(settings["autoCompactWindow"], 250000)
        self.assertEqual(settings["statusLine"]["refreshInterval"], 10)
        self.assertIn("settings.json: verbose: true -> false", result.stdout)
        self.assertIn('settings.json: outputStyle: (absent) -> "Mobile"', result.stdout)
        self.assertNotIn("settings.json: tui", result.stdout)

        backups = glob.glob(os.path.join(self.claude, "backups", "usage-optimizer-*", "settings.json"))
        self.assertEqual(len(backups), 1)
        with open(backups[0], encoding="utf-8") as stream:
            self.assertIs(json.load(stream)["verbose"], True)

        for relative in (".claude-plugin/plugin.json", "hooks/hooks.json", "hooks/register.tsx", "hooks/format.ts",
                         "hooks/prompts.ts", "types/index.d.ts"):
            with open(os.path.join(ROOT, "mods", "mobile-view", relative), "rb") as source, \
                    open(os.path.join(self.mod, relative), "rb") as installed:
                self.assertEqual(source.read(), installed.read(), relative)
        self.assertFalse(os.path.exists(os.path.join(self.mod, "tests")))

        with open(os.path.join(self.mod, "install-paths.json"), encoding="utf-8") as stream:
            paths = json.load(stream)
        self.assertTrue(os.path.exists(paths["python"]), paths)
        self.assertTrue(os.path.exists(paths["promptsScript"]), paths)
        self.assertTrue(paths["promptsScript"].endswith("claude-prompts.py" if WINDOWS else "bin/claude-prompts"))
        with open(os.path.join(ROOT, "POLICY.md"), encoding="utf-8") as stream:
            self.assertIn("version: %s." % paths["kitVersion"], stream.read())

        with open(os.path.join(ROOT, "output-styles", "Mobile.md"), "rb") as source, \
                open(os.path.join(self.claude, "output-styles", "Mobile.md"), "rb") as installed:
            self.assertEqual(source.read(), installed.read())

        installed_script = "lane-stats.py" if WINDOWS else "lane-stats"
        self.assertTrue(os.path.exists(os.path.join(self.prefix, "bin", installed_script)))
        tools = ["claude-prompts", "lane-stats"] + (["claude-prompts.cmd", "lane-stats.cmd"] if WINDOWS else [])
        for tool in tools:
            self.assertTrue(os.path.exists(os.path.join(self.prefix, "bin", tool)), tool)
            self.assertTrue(os.path.lexists(os.path.join(self.home, ".local", "bin", tool)), tool)

        with open(os.path.join(self.claude, "CLAUDE.md"), encoding="utf-8") as stream:
            self.assertIn("@~/.claude/usage-optimizer/POLICY.md", stream.read().splitlines())
        with open(os.path.join(self.prefix, "view-settings.applied.json"), encoding="utf-8") as stream:
            self.assertEqual(json.load(stream), {"verbose": False, "viewMode": "default", "tui": "fullscreen", "outputStyle": "Mobile"})

    def test_the_sessions_mod_installs_beside_mobile_view_without_its_tests(self):
        self.install()
        sessions = os.path.join(self.claude, "skills", "sessions")
        for relative in (".claude-plugin/plugin.json", "hooks/hooks.json", "hooks/actions.ts", "types/index.d.ts"):
            with open(os.path.join(ROOT, "mods", "sessions", relative), "rb") as source, \
                    open(os.path.join(sessions, relative), "rb") as installed:
                self.assertEqual(source.read(), installed.read(), relative)
        self.assertFalse(os.path.exists(os.path.join(sessions, "tests")))

    def test_install_copies_improving_guide_and_briefs(self):
        self.install()
        for relative in ("IMPROVING.md", "improve/audit-brief.md", "improve/release-brief.md"):
            with open(os.path.join(ROOT, relative), "rb") as source, \
                    open(os.path.join(self.prefix, relative), "rb") as installed:
                self.assertEqual(source.read(), installed.read(), relative)

    def test_compiled_caches_stay_out_of_the_install(self):
        # A checkout where the tests ran holds bin/__pycache__ (git-ignored); install.sh used to copy it with bin/.
        cache = os.path.join(ROOT, "bin", "__pycache__")
        os.makedirs(cache, exist_ok=True)
        # A per-process name, so two test runs in one checkout (a sharded verify) never remove each other's file.
        name = "install-test-sentinel-{}.pyc".format(os.getpid())
        sentinel = os.path.join(cache, name)
        with open(sentinel, "wb"):
            pass
        try:
            self.install()
        finally:
            os.remove(sentinel)
        self.assertFalse(os.path.exists(os.path.join(self.prefix, "bin", "__pycache__", name)))
        self.assertTrue(os.path.exists(os.path.join(self.prefix, "bin", "turn-meter.py" if WINDOWS else "turn-meter")))

    def test_installed_helper_lists_prompts(self):
        self.install()
        transcript = os.path.join(self.home, "s.jsonl")
        with open(transcript, "w", encoding="utf-8") as stream:
            stream.write(json.dumps({"type": "user", "uuid": "a", "parentUuid": None, "origin": {"kind": "human"},
                                     "timestamp": "2026-10-13T01:00:00Z", "message": {"role": "user", "content": "hello there"}}) + "\n")
        with open(os.path.join(self.mod, "install-paths.json"), encoding="utf-8") as stream:
            paths = json.load(stream)
        result = subprocess.run([paths["python"], "-I", "-X", "utf8", paths["promptsScript"], "--transcript", transcript],
                                stdout=subprocess.PIPE, encoding="utf-8", timeout=60, check=True)
        self.assertEqual([prompt["title"] for prompt in json.loads(result.stdout)["prompts"]], ["hello there"])

    def test_rerun_changes_nothing(self):
        self.install()
        with open(self.settings_path, encoding="utf-8") as stream:
            before = stream.read()
        result = self.install()
        with open(self.settings_path, encoding="utf-8") as stream:
            self.assertEqual(stream.read(), before)
        self.assertNotIn("settings.json: ", result.stdout)
        view_lines = [line for line in result.stdout.splitlines() if "mobile-view/" in line or "Mobile.md" in line]
        self.assertEqual(len(view_lines), 8, view_lines)
        self.assertTrue(all(line.startswith("Identical, skipping: ") for line in view_lines), view_lines)

    def test_turn_meter_hooks_merge_idempotently_and_preserve_existing_hooks(self):
        settings = self.settings()
        settings["hooks"] = {
            "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "echo keep prompt"}]}],
            "Stop": [{"hooks": [{"type": "command", "command": "echo keep stop"}]}],
        }
        with open(self.settings_path, "w", encoding="utf-8") as stream:
            json.dump(settings, stream, indent=2)
        first = self.install()
        self.assertIn("settings.json: hooks.UserPromptSubmit +=", first.stdout)
        self.assertIn("settings.json: hooks.Stop +=", first.stdout)
        self.install()
        merged = self.settings()["hooks"]
        for event in ("UserPromptSubmit", "Stop"):
            entries = merged[event]
            self.assertEqual(len(entries), 2, event)
            self.assertEqual(entries[0]["hooks"][0]["command"], "echo keep " + ("prompt" if event == "UserPromptSubmit" else "stop"))
            installed = entries[1]["hooks"][0]
            self.assertRegex(installed["command"], r"turn-meter(\.py)? hook$")
            self.assertEqual(installed["timeout"], 5)
        with open(os.path.join(self.prefix, "arms.json"), encoding="utf-8") as stream:
            self.assertEqual(json.load(stream)["providers"]["claude"]["prior_pct_per_usd"], 0.069)
        self.assertTrue(os.path.exists(os.path.join(self.prefix, "bin", "turn-meter")))

    def test_dry_run_previews_turn_meter_hooks(self):
        result = self.install("--dry-run")
        self.assertIn("DRY-RUN: settings.json would gain hooks.UserPromptSubmit +=", result.stdout)
        self.assertIn("DRY-RUN: settings.json would gain hooks.Stop +=", result.stdout)

    def test_subagent_stop_hook_is_added_once_and_dry_run_shows_it(self):
        dry = self.install("--dry-run")
        self.assertIn("DRY-RUN: settings.json would gain hooks.SubagentStop +=", dry.stdout)
        self.assertNotIn("SubagentStop", self.settings().get("hooks", {}))
        first = self.install()
        self.assertIn("settings.json: hooks.SubagentStop +=", first.stdout)
        self.install()
        entries = self.settings()["hooks"]["SubagentStop"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["matcher"], "^lane-")
        self.assertEqual(entries[0]["hooks"][0]["type"], "command")
        self.assertEqual(entries[0]["hooks"][0]["timeout"], 30)
        command = entries[0]["hooks"][0]["command"]
        if WINDOWS:
            self.assertRegex(command, r".+ [^ ]*/bin/lane\.py hook subagent-stop$")
        else:
            self.assertEqual(command, self.prefix.replace("\\", "/") + "/bin/lane hook subagent-stop")

    def assert_hook_command(self, command, tool, args):
        if WINDOWS:
            # The Python that runs the tool is the one install-paths.json names; the script sits under the prefix.
            with open(os.path.join(self.mod, "install-paths.json"), encoding="utf-8") as stream:
                python = json.load(stream)["python"]
            self.assertTrue(command.startswith(python + " "), command)
            self.assertRegex(command, r" [^ ]*/bin/%s\.py %s$" % (re.escape(tool), re.escape(args)))
        else:
            self.assertEqual(command, self.prefix.replace("\\", "/") + "/bin/%s %s" % (tool, args))

    def test_compaction_hooks_and_the_250k_window_merge_once(self):
        # A default left at the old 450k moves to 250k; the four compaction hooks are added, and a rerun adds none.
        settings = self.settings()
        settings["autoCompactWindow"] = 450000
        with open(self.settings_path, "w", encoding="utf-8") as stream:
            json.dump(settings, stream, indent=2)
        dry = self.install("--dry-run")
        self.assertIn("DRY-RUN: settings.json would change autoCompactWindow: 450000 -> 250000", dry.stdout)
        for event in ("PreCompact", "SessionStart", "PostCompact", "SubagentStop"):
            self.assertIn("DRY-RUN: settings.json would gain hooks.%s +=" % event, dry.stdout)
        self.assertEqual(self.settings()["autoCompactWindow"], 450000)
        self.assertNotIn("PreCompact", self.settings().get("hooks", {}))

        first = self.install()
        self.assertIn("settings.json: autoCompactWindow: 450000 -> 250000", first.stdout)
        self.assertEqual(self.settings()["autoCompactWindow"], 250000)
        hooks = self.settings()["hooks"]
        expected = {
            "PreCompact": ("turn-meter", "compact-gate", "auto", 10),
            "PostCompact": ("turn-meter", "hook", None, 10),
            "SubagentStop": ("lane", "hook subagent-stop", "^lane-", 30),
        }
        expected_session_start = [
            ("turn-meter", "resume-context", "compact", 10),
            ("claude-statusline", "session-start", "startup|resume|compact", 10),
        ]
        self.assertEqual(len(hooks["SessionStart"]), len(expected_session_start), "SessionStart")
        checks = [(event, spec, hooks[event][0]) for event, spec in expected.items()]
        checks += [("SessionStart", spec, entry) for spec, entry in zip(expected_session_start, hooks["SessionStart"])]
        for event, (tool, args, matcher, timeout), entry in checks:
            if event != "SessionStart":
                self.assertEqual(len(hooks[event]), 1, event)
            if matcher is None:
                self.assertNotIn("matcher", entry, event)
            else:
                self.assertEqual(entry["matcher"], matcher, event)
            self.assertEqual(entry["hooks"][0]["type"], "command", event)
            self.assertEqual(entry["hooks"][0]["timeout"], timeout, event)
            self.assert_hook_command(entry["hooks"][0]["command"], tool, args)

        with open(self.settings_path, encoding="utf-8") as stream:
            before = stream.read()
        second = self.install()
        with open(self.settings_path, encoding="utf-8") as stream:
            self.assertEqual(stream.read(), before)
        self.assertNotIn("settings.json: ", second.stdout)

    def source_with_main_session(self, main_session):
        # A copy of the kit whose arms.json carries this explore.main_session (None: the block removed).
        source = os.path.join(self.home, "kit-source")
        shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(".git", "tests", "dist", "__pycache__",
                                                                    ".tmp-tests", ".claude"))
        path = os.path.join(source, "arms.json")
        with open(path, encoding="utf-8") as stream:
            arms = json.load(stream)
        if main_session is None:
            arms["explore"].pop("main_session", None)
        else:
            arms["explore"]["main_session"] = main_session
        with open(path, "w", encoding="utf-8") as stream:
            json.dump(arms, stream, indent=2)
        return source

    def write_settings(self, **values):
        settings = self.settings()
        settings.update(values)
        with open(self.settings_path, "w", encoding="utf-8") as stream:
            json.dump(settings, stream, indent=2)

    def test_main_session_comes_from_arms_json_not_the_fragment(self):
        with open(os.path.join(ROOT, "settings.fragment.json"), encoding="utf-8") as stream:
            fragment = json.load(stream)
        self.assertNotIn("model", fragment["set_if_absent"])
        self.assertNotIn("effortLevel", fragment["set_if_absent"])
        source = self.source_with_main_session({"model": "claude-test-9", "effort": "high",
                                                "previous_models": [], "previous_efforts": []})
        dry = self.install("--dry-run", source=source)
        self.assertIn('DRY-RUN: settings.json would gain model = "claude-test-9"', dry.stdout)
        self.assertIn('DRY-RUN: settings.json would gain effortLevel = "high"', dry.stdout)
        self.assertNotIn("model", self.settings())
        self.install(source=source)
        self.assertEqual((self.settings()["model"], self.settings()["effortLevel"]), ("claude-test-9", "high"))

    def test_main_session_at_a_previous_kit_value_moves_and_any_other_value_is_kept(self):
        source = self.source_with_main_session({"model": "claude-test-9", "effort": "max",
                                                "previous_models": ["opus[1m]"], "previous_efforts": ["xhigh"]})
        self.write_settings(model="opus[1m]", effortLevel="medium")
        dry = self.install("--dry-run", source=source)
        self.assertIn('DRY-RUN: settings.json would change model: "opus[1m]" -> "claude-test-9"', dry.stdout)
        self.assertNotIn("effortLevel", dry.stdout)
        result = self.install(source=source)
        self.assertIn('settings.json: model: "opus[1m]" -> "claude-test-9"', result.stdout)
        self.assertNotIn("effortLevel", result.stdout)
        self.assertEqual((self.settings()["model"], self.settings()["effortLevel"]), ("claude-test-9", "medium"))

        self.write_settings(model="sonnet", effortLevel="xhigh")
        result = self.install(source=source)
        self.assertEqual((self.settings()["model"], self.settings()["effortLevel"]), ("sonnet", "max"))
        self.assertNotIn("settings.json: model", result.stdout)
        self.assertIn('settings.json: effortLevel: "xhigh" -> "max"', result.stdout)

    def test_no_main_session_in_arms_json_falls_back_and_says_so(self):
        source = self.source_with_main_session(None)
        dry = self.install("--dry-run", source=source)
        self.assertIn("no explore.main_session", dry.stderr)
        self.assertIn('DRY-RUN: settings.json would gain model = "opus[1m]"', dry.stdout)
        result = self.install(source=source)
        self.assertIn("no explore.main_session", result.stderr)
        self.assertEqual((self.settings()["model"], self.settings()["effortLevel"]), ("opus[1m]", "xhigh"))

    def test_a_soft_threshold_set_by_hand_is_kept(self):
        settings = self.settings()
        settings["autoCompactWindow"] = 300000
        with open(self.settings_path, "w", encoding="utf-8") as stream:
            json.dump(settings, stream, indent=2)
        result = self.install()
        self.assertEqual(self.settings()["autoCompactWindow"], 300000)
        self.assertNotIn("autoCompactWindow", result.stdout)

    def test_a_value_changed_by_hand_is_kept_until_reset(self):
        self.install()
        settings = self.settings()
        settings["verbose"] = True
        with open(self.settings_path, "w", encoding="utf-8") as stream:
            json.dump(settings, stream, indent=2)
        result = self.install()
        self.assertIs(self.settings()["verbose"], True)
        self.assertIn("verbose = true was kept", result.stderr)
        self.assertIn("--reset-view", result.stderr)

        result = self.install("--reset-view")
        self.assertIs(self.settings()["verbose"], False)
        self.assertIn("settings.json: verbose: true -> false", result.stdout)

    def test_no_view_leaves_the_view_alone(self):
        result = self.install("--no-view")
        settings = self.settings()
        self.assertIs(settings["verbose"], True)
        self.assertNotIn("viewMode", settings)
        self.assertNotIn("outputStyle", settings)
        self.assertFalse(os.path.exists(self.mod))
        self.assertFalse(os.path.exists(os.path.join(self.claude, "output-styles")))
        self.assertFalse(os.path.exists(os.path.join(self.prefix, "view-settings.applied.json")))
        self.assertIn("Mobile view skipped (--no-view)", result.stdout)
        self.assertTrue(os.path.exists(os.path.join(self.prefix, "bin", "claude-prompts")))

    def test_cline_is_never_started(self):
        # Starting cline launches its self-update; three installs in a row once left it half-replaced.
        npm = os.path.join(self.home, "npm")
        os.makedirs(os.path.join(npm, "node_modules", "cline"))
        marker = os.path.join(self.home, "cline-was-started")
        with open(os.path.join(npm, "cline"), "w", encoding="utf-8", newline="\n") as stream:
            stream.write('#!/bin/sh\necho started > "%s"\necho 9.9.9\n' % marker.replace("\\", "/"))
        os.chmod(os.path.join(npm, "cline"), 0o755)
        with open(os.path.join(npm, "node_modules", "cline", "package.json"), "w", encoding="utf-8") as stream:
            json.dump({"name": "cline", "version": "1.2.3"}, stream)
        # Only the fake cline, Python and the shell's own tools: no real CLI can be found and started.
        tools = os.path.join(os.path.dirname(os.path.dirname(BASH)), "usr", "bin") if WINDOWS else "/usr/bin:/bin"
        path = os.pathsep.join([npm, os.path.dirname(os.path.realpath(sys.executable)), tools])
        result = self.install("--dry-run", env_extra={"PATH": path, "USAGE_OPTIMIZER_SKIP_CLI_CHECK": ""})
        self.assertRegex(result.stdout, r"\ncline +found +1\.2\.3\n")
        self.assertRegex(result.stdout, r"\nclaude +missing")
        self.assertFalse(os.path.exists(marker), "install.sh started cline")

    def test_kit_statusline_gets_a_refresh_interval_and_keeps_one_set_by_hand(self):
        # The statusline re-runs every 10 s so the turn's ETA counts down. An install from before that has none.
        self.install()
        settings = self.settings()
        del settings["statusLine"]["refreshInterval"]
        with open(self.settings_path, "w", encoding="utf-8") as stream:
            json.dump(settings, stream, indent=2)
        dry = self.install("--dry-run")
        self.assertIn("DRY-RUN: settings.json would change statusLine.refreshInterval: (absent) -> 10", dry.stdout)
        self.assertNotIn("existing statusLine", dry.stderr)
        self.assertNotIn("refreshInterval", self.settings()["statusLine"])

        first = self.install()
        self.assertIn("settings.json: statusLine.refreshInterval: (absent) -> 10", first.stdout)
        self.assertNotIn("existing statusLine", first.stderr)
        self.assertEqual(self.settings()["statusLine"]["refreshInterval"], 10)

        settings = self.settings()
        settings["statusLine"]["refreshInterval"] = 30
        with open(self.settings_path, "w", encoding="utf-8") as stream:
            json.dump(settings, stream, indent=2)
        kept = self.install()
        self.assertNotIn("refreshInterval", kept.stdout)
        self.assertNotIn("existing statusLine", kept.stderr)
        self.assertEqual(self.settings()["statusLine"]["refreshInterval"], 30)

    def test_someone_elses_statusline_is_untouched_and_still_warned_about(self):
        settings = self.settings()
        settings["statusLine"] = {"type": "command", "command": "/usr/local/bin/their-statusline", "padding": 0}
        with open(self.settings_path, "w", encoding="utf-8") as stream:
            json.dump(settings, stream, indent=2)
        result = self.install()
        self.assertEqual(self.settings()["statusLine"], {"type": "command", "command": "/usr/local/bin/their-statusline", "padding": 0})
        self.assertIn("Warning: an existing statusLine was preserved", result.stderr)
        self.assertNotIn("refreshInterval", result.stdout)

    def source_record(self):
        with open(os.path.join(self.prefix, "source.json"), encoding="utf-8") as stream:
            return json.load(stream)

    @unittest.skipUnless(ROOT_IS_CHECKOUT, "the kit under test is not a git checkout")
    def test_an_install_from_a_checkout_records_it_and_a_dry_run_does_not(self):
        dry = self.install("--dry-run")
        self.assertIn("DRY-RUN: record the source checkout ", dry.stdout)
        self.assertFalse(os.path.exists(self.prefix))
        result = self.install()
        record = self.source_record()
        self.assertEqual(set(record), {"checkout", "installed_at"})
        self.assertTrue(same_path(record["checkout"], ROOT), record)
        self.assertRegex(record["installed_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertIn("Recorded the source checkout for update checks: ", result.stdout)
        self.assertIn("kit-update check", result.stdout)
        self.assertTrue(os.path.exists(os.path.join(self.prefix, "bin", "kit-update.py" if WINDOWS else "kit-update")))
        self.assertTrue(os.path.lexists(os.path.join(self.home, ".local", "bin", "kit-update")))

    @unittest.skipIf(GIT is None, "git is not installed")
    def test_an_install_from_a_linked_worktree_records_the_main_working_tree(self):
        # A linked worktree is removed on its own schedule; the checkout recorded must outlive it.
        main = os.path.join(self.home, "kit-main")
        worktree = os.path.join(self.home, "kit-worktree")
        shutil.copytree(ROOT, main, ignore=shutil.ignore_patterns(".git", "tests", "dist", "__pycache__", ".tmp-tests"))
        env = dict(os.environ, HOME=self.home, USERPROFILE=self.home)

        def git(*args):
            return subprocess.run([GIT, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                                   "-c", "init.defaultBranch=main", *args], cwd=main, env=env, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, encoding="utf-8", timeout=120, check=True).stdout

        git("init", "-q")
        git("add", "-A")
        git("commit", "-q", "-m", "Kit")
        git("worktree", "add", "-q", worktree)
        self.install(source=worktree)
        record = self.source_record()
        self.assertTrue(same_path(record["checkout"], main), record)
        self.assertFalse(same_path(record["checkout"], worktree), record)

        git("worktree", "remove", "--force", worktree)
        self.assertFalse(os.path.exists(worktree))
        self.assertTrue(same_path(git("-C", record["checkout"], "rev-parse", "--show-toplevel").strip(), main))

    @unittest.skipIf(GIT is None, "git is not installed")
    def test_an_install_from_an_unpacked_bundle_records_nothing(self):
        # A bundle unpacks the kit without .git; unpacked inside another repository (a home kept in git) it is
        # still no checkout of the kit.
        copy = os.path.join(self.home, "claude-usage-optimizer")
        shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(".git", "tests", "dist", "__pycache__", ".tmp-tests"))
        result = self.install(source=copy)
        self.assertFalse(os.path.exists(os.path.join(self.prefix, "source.json")))
        self.assertIn("Updates: not checked", result.stdout)
        subprocess.run([GIT, "init", "-q", self.home], check=True, timeout=60,
                       env=dict(os.environ, HOME=self.home, USERPROFILE=self.home))
        self.install(source=copy)
        self.assertFalse(os.path.exists(os.path.join(self.prefix, "source.json")))

    def test_the_installed_copy_of_install_sh_refuses_to_run(self):
        # The kit now carries install.sh (lane main's lean kit branch needs it); run from the prefix, it would copy
        # the kit onto itself, so it stops with exit 1 before it changes anything.
        self.install()
        installed = os.path.join(self.prefix, "install.sh")
        with open(os.path.join(ROOT, "install.sh"), "rb") as source, open(installed, "rb") as copy:
            self.assertEqual(source.read(), copy.read())
        with open(self.settings_path, encoding="utf-8") as stream:
            before = stream.read()
        env = dict(os.environ, HOME=self.home, USERPROFILE=self.home, USAGE_OPTIMIZER_SKIP_CLI_CHECK="1")
        env.pop("CLAUDE_CONFIG_DIR", None)
        for args in ([], ["--dry-run"]):
            with self.subTest(args=args):
                result = subprocess.run([BASH, self.prefix.replace("\\", "/") + "/install.sh"] + args, cwd=self.home,
                                        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8",
                                        errors="replace", timeout=300, check=False)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("is the installed copy of the kit", result.stderr)
        with open(self.settings_path, encoding="utf-8") as stream:
            self.assertEqual(stream.read(), before)

    def test_dry_run_writes_nothing(self):
        with open(self.settings_path, encoding="utf-8") as stream:
            before = stream.read()
        result = self.install("--dry-run")
        with open(self.settings_path, encoding="utf-8") as stream:
            self.assertEqual(stream.read(), before)
        self.assertFalse(os.path.exists(self.mod))
        self.assertFalse(os.path.exists(self.prefix))
        self.assertFalse(os.path.exists(os.path.join(self.claude, "output-styles")))
        self.assertIn("DRY-RUN: settings.json would change verbose: true -> false", result.stdout)
        self.assertIn('DRY-RUN: settings.json would change viewMode: (absent) -> "default"', result.stdout)


if __name__ == "__main__":
    unittest.main()
