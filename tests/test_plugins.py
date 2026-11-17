"""Plugins, kit skills and the session check that the core is installed."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import test_install_platform as install_platform

_SPEC = importlib.util.spec_from_file_location("make_plugins", os.path.join(ROOT, "tools", "make-plugins.py"))
make_plugins = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(make_plugins)
SKILL_NAMES = ("kit-status", "kit-dispatch", "kit-waste", "kit-review", "kit-hillclimb")


def read_text(path):
    with open(path, encoding="utf-8", newline="") as stream:
        return stream.read()


def frontmatter(text):
    if not text.startswith("---\n"):
        raise AssertionError("SKILL.md does not start with frontmatter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise AssertionError("SKILL.md frontmatter is not closed")
    fields = {}
    for line in text[4:end].splitlines():
        if not line.strip():
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields


def find_sh():
    bash = install_platform.find_bash()
    if bash:
        candidate = os.path.join(os.path.dirname(bash), "sh.exe" if os.name == "nt" else "sh")
        if os.path.exists(candidate):
            return candidate
    return shutil.which("sh")


SH = find_sh()


class MakePluginsTests(unittest.TestCase):
    def test_semver_joins_month_and_day(self):
        self.assertEqual(make_plugins.plugin_semver("2026-11-17.2"), "2026.1117.2")
        self.assertEqual(make_plugins.plugin_semver("2026-01-05.1"), "2026.0105.1")

    def test_check_passes_and_versions_match(self):
        result = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "make-plugins.py"), "--check"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        files, found = make_plugins.differences(ROOT)
        self.assertEqual(found, [])
        parsed = {}
        for name, text in files.items():
            self.assertTrue(text.endswith("\n"), name)
            if name.endswith(".json"):
                parsed[name] = json.loads(text)
        claude = parsed["plugins/claude-code/.claude-plugin/plugin.json"]
        codex = parsed["plugins/codex/.codex-plugin/plugin.json"]
        self.assertEqual(claude["version"], codex["version"])
        self.assertEqual(claude["version"], make_plugins.plugin_semver(make_plugins.kit_version(
            os.path.join(ROOT, "POLICY.md"))))
        self.assertEqual(claude["homepage"], "https://github.com/hieunguyen7337/coding-tool-optimizer")
        self.assertEqual(parsed["plugins/claude-code/hooks/hooks.json"]["hooks"]["SessionStart"][0]["hooks"][0]["timeout"], 10)
        self.assertEqual(files["plugins/claude-code/skills/kit-setup/SKILL.md"],
                         files["plugins/codex/skills/kit-setup/SKILL.md"])
        self.assertEqual(files["plugins/claude-code/hooks/core-check.sh"],
                         read_text(os.path.join(ROOT, "plugins", "src", "core-check.sh")))

    def test_check_exits_1_when_output_is_stale(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = temp.name
        shutil.copy(os.path.join(ROOT, "POLICY.md"), os.path.join(root, "POLICY.md"))
        shutil.copytree(os.path.join(ROOT, "plugins", "src"), os.path.join(root, "plugins", "src"))
        tool = os.path.join(ROOT, "tools", "make-plugins.py")
        wrote = subprocess.run([sys.executable, tool, "--root", root],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", check=False)
        self.assertEqual(wrote.returncode, 0, wrote.stdout + wrote.stderr)
        path = os.path.join(root, "plugins", "claude-code", ".claude-plugin", "plugin.json")
        text = read_text(path).replace("2026.", "1999.", 1)
        with open(path, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        result = subprocess.run([sys.executable, tool, "--check", "--root", root],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", check=False)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("would update plugins/claude-code/.claude-plugin/plugin.json", result.stdout)


class SkillTests(unittest.TestCase):
    def test_each_skill_names_itself_and_says_when_not_to_use_it(self):
        folders = [os.path.join(ROOT, "skills", name) for name in SKILL_NAMES]
        folders.append(os.path.join(ROOT, "plugins", "src", "kit-setup"))
        for folder in folders:
            name = os.path.basename(folder)
            text = read_text(os.path.join(folder, "SKILL.md"))
            fields = frontmatter(text)
            self.assertEqual(set(fields), {"name", "description"}, name)
            self.assertEqual(fields["name"], name)
            self.assertLessEqual(len(fields["description"]), 300, name)
            self.assertIn("Do not", fields["description"], name)
            self.assertLessEqual(len(text.splitlines()), 60, name)


@unittest.skipIf(SH is None, "sh is not installed")
class CoreCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = os.path.realpath(self.temp.name)
        self.version = read_text(os.path.join(ROOT, "plugins", "claude-code", "kit-version")).strip()

    def tearDown(self):
        self.temp.cleanup()

    def write_policy(self, text):
        directory = os.path.join(self.home, ".claude", "usage-optimizer")
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, "POLICY.md"), "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)

    def run_check(self):
        environment = dict(os.environ)
        environment["HOME"] = self.home
        environment["USERPROFILE"] = self.home
        script = os.path.join(ROOT, "plugins", "claude-code", "hooks", "core-check.sh")
        return subprocess.run([SH, script], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              encoding="utf-8", errors="replace", env=environment, check=False)

    def context(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        data = json.loads(result.stdout)
        output = data["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "SessionStart")
        self.assertTrue(output["additionalContext"])
        return output["additionalContext"]

    def test_current_core_prints_nothing(self):
        self.write_policy("Coding Tool Optimizer version: {}. Installed.\n".format(self.version))
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_newer_core_prints_nothing(self):
        self.write_policy("Coding Tool Optimizer version: 2099-01-01.1. Installed.\n")
        result = self.run_check()
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.returncode, 0)

    def test_missing_core_prints_context(self):
        text = self.context(self.run_check())
        self.assertIn("not installed", text)
        self.assertIn("kit-setup", text)

    def test_older_core_prints_context(self):
        self.write_policy("Coding Tool Optimizer version: 2020-01-01.1. Installed.\n")
        text = self.context(self.run_check())
        self.assertIn("older", text)
        self.assertIn("2020-01-01.1", text)
        self.assertIn("kit-setup", text)

    def test_former_version_line_is_accepted(self):
        self.write_policy("Claude Usage Optimizer version: {}. Kept for older installs.\n".format(self.version))
        result = self.run_check()
        self.assertEqual(result.stdout, "")
        self.write_policy("Claude Usage Optimizer version: 2020-01-02.3. Kept for older installs.\n")
        text = self.context(self.run_check())
        self.assertIn("2020-01-02.3", text)

    def test_current_name_wins_over_the_former_line(self):
        self.write_policy(
            "Claude Usage Optimizer version: 2020-01-01.1. Old.\n"
            "Coding Tool Optimizer version: {}. Installed.\n".format(self.version))
        result = self.run_check()
        self.assertEqual(result.stdout, "")


class InstallSkillTests(unittest.TestCase):
    def setUp(self):
        self.case = install_platform.InstallPlatformTests()
        self.case.setUp()

    def tearDown(self):
        self.case.tearDown()

    def test_dry_run_lists_the_skill_for_each_platform(self):
        codex = self.case.install("--platform", "codex", "--dry-run")
        self.assertIn(".agents/skills/kit-status", codex.stdout.replace("\\", "/"))
        self.assertFalse(os.path.exists(os.path.join(self.case.home, ".agents", "skills", "kit-status")))
        claude = self.case.install("--platform", "claude-code", "--dry-run")
        self.assertIn(".claude/skills/kit-status", claude.stdout.replace("\\", "/"))
        self.assertIn("claude plugin marketplace add hieunguyen7337/coding-tool-optimizer", claude.stdout)
        self.assertIn("claude plugin install coding-tool-optimizer@coding-tool-optimizer", claude.stdout)

    def test_codex_install_keeps_other_skills_and_retires_only_unshipped_kit_skills(self):
        agents = os.path.join(self.case.home, ".agents", "skills")
        os.makedirs(os.path.join(agents, "codex-delegation"))
        with open(os.path.join(agents, "codex-delegation", "SKILL.md"), "w", encoding="utf-8", newline="\n") as stream:
            stream.write("keep\n")
        os.makedirs(os.path.join(agents, "kit-retired"))
        with open(os.path.join(agents, "kit-retired", "SKILL.md"), "w", encoding="utf-8", newline="\n") as stream:
            stream.write("old\n")
        os.makedirs(os.path.join(agents, "kit-setup"))
        with open(os.path.join(agents, "kit-setup", "SKILL.md"), "w", encoding="utf-8", newline="\n") as stream:
            stream.write("plugin\n")
        self.case.install("--platform", "codex")
        installed = os.path.join(agents, "kit-status", "SKILL.md")
        self.assertEqual(read_text(installed), read_text(os.path.join(ROOT, "skills", "kit-status", "SKILL.md")))
        self.assertEqual(read_text(os.path.join(agents, "codex-delegation", "SKILL.md")), "keep\n")
        self.assertEqual(read_text(os.path.join(agents, "kit-setup", "SKILL.md")), "plugin\n")
        self.assertFalse(os.path.exists(os.path.join(agents, "kit-retired")))


if __name__ == "__main__":
    unittest.main()
