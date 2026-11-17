"""Per-model autoCompactWindow: usage-status warns, and install.sh warns without changing it.

Neither test reads the real ~/.claude. usage-status gets CLAUDE_CONFIG_DIR; install.sh gets HOME.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USAGE = os.path.join(ROOT, "bin", "usage-status")
WINDOWS = os.name == "nt"

OPUS = ("Compaction: claude-opus-5-5 compacts at 350k, not the kit's 250k "
        "(settings.json modelSettings); remove it to use 250k")
HAIKU = ("Compaction: claude-haiku-5-5 compacts at 100k, not the kit's 250k "
         "(settings.json modelSettings); remove it to use 250k")
SUFFIX = ("Compaction: claude-sonnet-5-5[1m] compacts at 180k, not the kit's 250k "
          "(settings.json modelSettings); remove it to use 250k")

MODEL_SETTINGS = {
    "claude-opus-5-5": {"autoCompactWindow": 350000},
    "claude-sonnet-5-5": {"autoCompactWindow": 250000},
    "claude-haiku-5-5": {"autoCompactWindow": 100000},
    "claude-fable-5": {"autoCompactWindow": 0},
    "claude-bool": {"autoCompactWindow": True},
    "not-an-entry": "nope",
    "claude-sonnet-5-5[1m]": {"autoCompactWindow": "180000"},
}


def find_bash():
    # On Windows `bash` on PATH may be WSL's, which cannot see this checkout's Windows paths.
    if WINDOWS:
        for candidate in (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files (x86)\Git\bin\bash.exe"):
            if os.path.exists(candidate):
                return candidate
        return None
    return shutil.which("bash")


BASH = find_bash()


def write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle)
        handle.write("\n")


def compaction_lines(text):
    return [line for line in text.splitlines() if line.startswith("Compaction:")]


class UsageStatusCompactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = self.temp.name
        self.home = os.path.join(root, "home")
        self.config = os.path.join(root, "config")
        self.usage_dir = os.path.join(root, "usage")
        self.state = os.path.join(root, "state")
        for path in (self.home, self.config, self.usage_dir, self.state, os.path.join(root, "codex")):
            os.makedirs(path)
        # A decoy under HOME/.claude. The command must read CLAUDE_CONFIG_DIR, not this file.
        write_json(os.path.join(self.home, ".claude", "settings.json"), {
            "autoCompactWindow": 250000,
            "modelSettings": {"decoy-model": {"autoCompactWindow": 999000}},
        })
        self.env = dict(os.environ, HOME=self.home, USERPROFILE=self.home, TMPDIR=root,
                        CLAUDE_USAGE_DIR=self.usage_dir, CODEX_HOME=os.path.join(root, "codex"),
                        CLAUDE_CONFIG_DIR=self.config, LANES_STATE=self.state,
                        USAGE_OPTIMIZER_CODEX_LIVE="0",
                        USAGE_OPTIMIZER_CODEX_BIN=os.path.join(root, "no-codex"),
                        USAGE_OPTIMIZER_AMP="off", USAGE_OPTIMIZER_CLOUD_PROBE_MIN="off",
                        NO_COLOR="1", LANES_MEM_FAKE="6451:16300", PYTHONUTF8="1")

    def write_settings(self, payload):
        write_json(os.path.join(self.config, "settings.json"), payload)

    def run_usage(self, *flags, env=None):
        result = subprocess.run([sys.executable, USAGE, "--no-agy", "--no-codex-live", *flags],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                encoding="utf-8", env=env or self.env, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return result

    def test_a_differing_window_is_warned_and_listed(self):
        self.write_settings({"autoCompactWindow": 250000, "modelSettings": MODEL_SETTINGS})
        data = json.loads(self.run_usage("--json").stdout)
        self.assertEqual(data["compaction_overrides"], [
            {"model": "claude-opus-5-5", "window": 350000},
            {"model": "claude-haiku-5-5", "window": 100000},
            {"model": "claude-sonnet-5-5[1m]", "window": 180000},
        ])
        text = self.run_usage()
        self.assertEqual(compaction_lines(text.stdout), [OPUS, HAIKU, SUFFIX])
        self.assertNotIn("decoy-model", text.stdout)
        lines = text.stdout.splitlines()
        compact_at = lines.index(OPUS)
        local_at = next(index for index, line in enumerate(lines) if line.startswith("Local:"))
        self.assertLess(compact_at, local_at)
        self.assertTrue(lines[-1].startswith("Hint: "))
        brief = self.run_usage("--brief")
        self.assertEqual(compaction_lines(brief.stdout), [OPUS, HAIKU, SUFFIX])
        self.assertTrue(brief.stdout.splitlines()[-1].startswith("Hint: "))

    def test_no_override_adds_no_line_and_no_json_field(self):
        self.write_settings({"autoCompactWindow": 250000, "modelSettings": {
            "claude-sonnet-5-5": {"autoCompactWindow": 250000},
            "claude-fable-5": {"autoCompactWindow": -1},
        }})
        data = json.loads(self.run_usage("--json").stdout)
        self.assertNotIn("compaction_overrides", data)
        self.assertEqual(compaction_lines(self.run_usage().stdout), [])

        self.write_settings({"modelSettings": {"claude-opus-5-5": {"autoCompactWindow": 350000}}})
        data = json.loads(self.run_usage("--json").stdout)
        self.assertNotIn("compaction_overrides", data)
        self.assertEqual(compaction_lines(self.run_usage().stdout), [])

    def test_missing_or_bad_settings_stay_quiet(self):
        self.assertNotIn("compaction_overrides", json.loads(self.run_usage("--json").stdout))
        self.assertEqual(compaction_lines(self.run_usage().stdout), [])
        with open(os.path.join(self.config, "settings.json"), "w", encoding="utf-8", newline="\n") as handle:
            handle.write("{")
        self.assertNotIn("compaction_overrides", json.loads(self.run_usage("--json").stdout))
        self.assertEqual(compaction_lines(self.run_usage().stdout), [])
        write_json(os.path.join(self.config, "settings.json"), [])
        self.assertEqual(compaction_lines(self.run_usage().stdout), [])

    def test_unset_config_dir_reads_home_dot_claude(self):
        env = dict(self.env)
        del env["CLAUDE_CONFIG_DIR"]
        write_json(os.path.join(self.home, ".claude", "settings.json"), {
            "autoCompactWindow": 250000,
            "modelSettings": {"claude-opus-5-5": {"autoCompactWindow": 350000}},
        })
        text = self.run_usage(env=env)
        self.assertEqual(compaction_lines(text.stdout), [OPUS])


@unittest.skipIf(BASH is None, "Git Bash (or bash) is not installed")
class InstallCompactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = self.temp.name
        self.claude = os.path.join(self.home, ".claude")
        os.makedirs(self.claude)
        self.settings_path = os.path.join(self.claude, "settings.json")
        self.env = dict(os.environ, HOME=self.home, USERPROFILE=self.home,
                        USAGE_OPTIMIZER_SKIP_CLI_CHECK="1")
        self.env.pop("CLAUDE_CONFIG_DIR", None)

    def write_settings(self, payload):
        write_json(self.settings_path, payload)

    def settings(self):
        with open(self.settings_path, encoding="utf-8") as handle:
            return json.load(handle)

    def install(self, *args):
        result = subprocess.run(
            [BASH, ROOT.replace("\\", "/") + "/install.sh", *args],
            cwd=self.home, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            encoding="utf-8", errors="replace", timeout=300, check=False,
        )
        self.assertEqual(result.returncode, 0, "install.sh failed:\n%s\n%s" % (result.stdout, result.stderr))
        return result

    def test_an_override_is_kept_and_warned_against_the_merged_window(self):
        # 450000 is an old kit default, so the merge moves the top-level window to 250000.
        # The warning names that final window. The per-model values stay as they were.
        payload = {"verbose": True, "tui": "fullscreen",
                   "permissions": {"defaultMode": "bypassPermissions"},
                   "autoCompactWindow": 450000, "modelSettings": MODEL_SETTINGS}
        self.write_settings(payload)
        with open(self.settings_path, encoding="utf-8") as handle:
            before = handle.read()
        dry = self.install("--dry-run")
        with open(self.settings_path, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), before)
        self.assertEqual(compaction_lines(dry.stderr), [OPUS, HAIKU, SUFFIX])
        self.assertEqual(compaction_lines(dry.stdout), [])
        self.assertEqual(self.settings()["autoCompactWindow"], 450000)

        result = self.install()
        self.assertEqual(compaction_lines(result.stderr), [OPUS, HAIKU, SUFFIX])
        self.assertEqual(compaction_lines(result.stdout), [])
        self.assertIn("settings.json: autoCompactWindow: 450000 -> 250000", result.stdout)
        settings = self.settings()
        self.assertEqual(settings["autoCompactWindow"], 250000)
        self.assertEqual(settings["modelSettings"], MODEL_SETTINGS)


if __name__ == "__main__":
    unittest.main()
