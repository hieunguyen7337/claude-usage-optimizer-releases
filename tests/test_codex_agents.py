"""Codex sub-agent roles: the generator, and install.sh --platform codex."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_install_platform as install_platform

try:
    import tomllib
except ImportError:
    tomllib = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "tools", "make-codex-agents.py")
COMMITTED = os.path.join(ROOT, "platforms", "codex", "agents")
NAMES = ("kit-editor.toml", "kit-hard.toml", "kit-reader.toml")


def read(path):
    with open(path, encoding="utf-8", newline="") as stream:
        return stream.read()


class CodexAgentGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.out = os.path.join(self.temp.name, "agents")
        os.makedirs(self.out)

    def tearDown(self):
        self.temp.cleanup()

    def run_tool(self, *args, arms=None, out=None):
        command = [sys.executable, TOOL, "--out", out or self.out]
        if arms:
            command.extend(["--arms", arms])
        command.extend(args)
        return subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              encoding="utf-8", check=False)

    def test_committed_catalog_writes_exactly_the_three_roles(self):
        result = self.run_tool(arms=os.path.join(ROOT, "arms.json"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(os.listdir(self.out)), list(NAMES))
        with open(os.path.join(ROOT, "arms.json"), encoding="utf-8") as stream:
            catalog = json.load(stream)
        lanes = catalog["lanes"]
        for role in catalog["explore"]["codex_subagents"]:
            text = read(os.path.join(self.out, role["name"] + ".toml"))
            self.assertNotIn(lanes["astra"]["model"], text)
            self.assertIn("Never spawn astra.", text)
            self.assertIn("[OBSERVED path:line]", text)
            self.assertIn("[INFERRED]", text)
            self.assertIn("fresh brief", text)
            self.assertIn("parent's full context", text)
            self.assertIn("60 lines", text)
            if tomllib is not None:
                parsed = tomllib.loads(text)
                self.assertEqual(parsed["name"], role["name"])
                self.assertEqual(parsed["model"], lanes[role["lane"]]["model"])
                self.assertEqual(parsed["model_reasoning_effort"], role["effort"])
                self.assertEqual(parsed["description"], role["description"])
                self.assertNotEqual(parsed["model"], lanes["astra"]["model"])
            committed = read(os.path.join(COMMITTED, role["name"] + ".toml"))
            self.assertEqual(text, committed, role["name"])
        reader = read(os.path.join(self.out, "kit-reader.toml"))
        self.assertIn("Never edit files.", reader)
        self.assertIn("You spawn nothing.", reader)
        editor = read(os.path.join(self.out, "kit-editor.toml"))
        self.assertIn("You may spawn only kit-reader.", editor)
        hard = read(os.path.join(self.out, "kit-hard.toml"))
        self.assertIn("You may spawn only kit-reader, kit-editor.", hard)

    def test_model_comes_from_the_lane_not_a_second_copy(self):
        arms = os.path.join(self.temp.name, "arms.json")
        with open(arms, "w", encoding="utf-8") as stream:
            json.dump({
                "lanes": {"terra": {"model": "example-terra"}, "sol": {"model": "example-sol"}},
                "explore": {"codex_subagents": [{
                    "name": "kit-reader", "lane": "terra", "effort": "low",
                    "description": "read-only research and review", "may_spawn": [],
                }]},
            }, stream)
        result = self.run_tool(arms=arms)
        self.assertEqual(result.returncode, 0, result.stderr)
        text = read(os.path.join(self.out, "kit-reader.toml"))
        self.assertIn('model = "example-terra"\n', text)
        self.assertNotIn("gpt-", text)

    def test_stale_kit_file_is_removed_and_other_files_stay(self):
        for name in ("kit-old.toml", "notes.txt"):
            with open(os.path.join(self.out, name), "w", encoding="utf-8") as stream:
                stream.write("x\n")
        result = self.run_tool(arms=os.path.join(ROOT, "arms.json"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(os.listdir(self.out)), list(NAMES) + ["notes.txt"])

    def test_check_passes_on_committed_files(self):
        result = subprocess.run([sys.executable, TOOL, "--check"], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, encoding="utf-8", check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_check_fails_when_a_file_is_stale_and_writes_nothing(self):
        os.makedirs(self.out, exist_ok=True)
        for name in NAMES:
            shutil.copyfile(os.path.join(COMMITTED, name), os.path.join(self.out, name))
        path = os.path.join(self.out, "kit-reader.toml")
        original = read(path)
        with open(path, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(original + "\n")
        result = self.run_tool("--check", arms=os.path.join(ROOT, "arms.json"))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("would update kit-reader.toml", result.stdout)
        self.assertEqual(read(path), original + "\n")


@unittest.skipIf(install_platform.BASH is None, "Git Bash (or bash) is not installed")
class CodexAgentInstallTests(unittest.TestCase):
    def setUp(self):
        self.host = install_platform.InstallPlatformTests()
        self.host.setUp()

    def tearDown(self):
        self.host.tearDown()

    def role_path(self, name):
        return os.path.join(self.host.codex_home, "agents", name)

    def test_dry_run_lists_the_role_files_and_writes_nothing(self):
        before = install_platform.snapshot(self.host.home)
        result = self.host.install("--dry-run", "--platform", "codex")
        self.assertEqual(install_platform.snapshot(self.host.home), before)
        for name in NAMES:
            self.assertIn(name, result.stdout)
        self.assertIn("DRY-RUN:", result.stdout)
        self.assertFalse(os.path.exists(self.role_path("kit-reader.toml")))

    def test_install_writes_the_roles_backs_up_a_change_and_leaves_other_files(self):
        self.host.install("--platform", "codex")
        for name in NAMES:
            self.assertEqual(install_platform.read_bytes(self.role_path(name)),
                             install_platform.read_bytes(os.path.join(COMMITTED, name)))
        other = self.role_path("custom.toml")
        with open(other, "w", encoding="utf-8", newline="\n") as stream:
            stream.write('name = "custom"\n')
        retired = self.role_path("kit-old.toml")
        with open(retired, "w", encoding="utf-8", newline="\n") as stream:
            stream.write('name = "retired"\n')
        with open(self.role_path("kit-reader.toml"), "w", encoding="utf-8", newline="\n") as stream:
            stream.write('name = "edited"\n')
        result = self.host.install("--platform", "codex")
        self.assertIn("Different, backing up and replacing:", result.stdout)
        self.assertIn("Removing retired Codex role:", result.stdout)
        self.assertEqual(install_platform.read_bytes(self.role_path("kit-reader.toml")),
                         install_platform.read_bytes(os.path.join(COMMITTED, "kit-reader.toml")))
        self.assertEqual(install_platform.read_text(other), 'name = "custom"\n')
        self.assertFalse(os.path.exists(retired))
        backup_root = self.host.backups()[-1]
        self.assertEqual(install_platform.read_text(
            os.path.join(backup_root, "codex", "agents", "kit-reader.toml")), 'name = "edited"\n')
        self.assertEqual(install_platform.read_text(
            os.path.join(backup_root, "codex", "agents", "kit-old.toml")), 'name = "retired"\n')
        config = os.path.join(self.host.codex_home, "config.toml")
        self.assertFalse(os.path.exists(config))


if __name__ == "__main__":
    unittest.main()
