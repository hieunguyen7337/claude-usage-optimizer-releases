import glob
import json
import os
import subprocess
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "tools", "make-lane-agents.py")

HAIKU_HIGH = """---
name: lane-haiku-high
description: Kit worker arm haiku high (claude-haiku-5-5). Only for prompts printed by `lane --subagent`.
model: claude-haiku-5-5
effort: high
omitClaudeMd: true
---

You are a worker for the Claude Usage Optimizer kit. Your prompt names a brief file: read it in full first and
follow it exactly. Work only in the directory the brief names. Your final message is your report.
"""


class LaneAgentsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.out = os.path.join(self.temp.name, "agents")
        os.makedirs(self.out)
        self.arms = os.path.join(self.temp.name, "arms.json")
        self.write_arms([
            {"lane": "haiku", "model": "claude-haiku-5-5", "effort": "high", "status": "active"},
            {"lane": "haiku", "model": "claude-haiku-5-5", "effort": "low", "status": "retired"},
            {"lane": "sol", "model": "gpt-6.1-sol", "effort": "high", "status": "active"},
        ])

    def tearDown(self):
        self.temp.cleanup()

    def write_arms(self, arms):
        with open(self.arms, "w", encoding="utf-8") as stream:
            json.dump({"arms": arms}, stream)

    def run_tool(self, *args, arms=None, out=None):
        return subprocess.run([sys.executable, TOOL, "--arms", arms or self.arms, "--out", out or self.out, *args],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", check=False)

    def names(self):
        return sorted(os.listdir(self.out))

    def test_file_content_for_one_arm(self):
        self.assertEqual(self.run_tool().returncode, 0)
        with open(os.path.join(self.out, "lane-haiku-high.md"), encoding="utf-8", newline="") as stream:
            self.assertEqual(stream.read(), HAIKU_HIGH)

    def test_retired_and_non_claude_arms_get_no_file(self):
        self.run_tool()
        self.assertEqual(self.names(), ["lane-haiku-high.md"])

    def test_fable_manual_arms_get_files_and_other_manual_arms_do_not(self):
        self.write_arms([
            {"lane": "fable", "model": "claude-fable-5-1", "effort": "high", "status": "manual"},
            {"lane": "fable", "model": "claude-fable-5-1", "effort": "low", "status": "retired"},
            {"lane": "opus", "model": "claude-opus-5-5", "effort": "low", "status": "manual"},
        ])
        self.run_tool()
        self.assertEqual(self.names(), ["lane-fable-high.md"])
        with open(os.path.join(self.out, "lane-fable-high.md"), encoding="utf-8", newline="") as stream:
            self.assertEqual(stream.read(), HAIKU_HIGH.replace("haiku-5-5", "fable-5-1").replace("haiku", "fable"))

    def test_committed_arms_give_the_current_agents_and_the_fable_5_2_agents(self):
        out = os.path.join(self.temp.name, "fresh")
        os.makedirs(out)
        self.assertEqual(self.run_tool(arms=os.path.join(ROOT, "arms.json"), out=out).returncode, 0)
        committed = sorted(os.path.basename(path) for path in glob.glob(os.path.join(ROOT, "agents", "lane-*.md")))
        self.assertEqual(sorted(os.listdir(out)), committed)
        # Fable 5.2's arms are manual or active (the owner, 2026-11-10), so their agents ship; 5.1's stay disabled.
        self.assertEqual([name for name in committed if name.startswith("lane-fable-")],
                         ["lane-fable-high.md", "lane-fable-medium.md", "lane-fable-xhigh.md"])
        with open(os.path.join(ROOT, "agents", "lane-fable-xhigh.md"), encoding="utf-8") as stream:
            self.assertIn("model: claude-fable-5-2", stream.read())
        self.assertIn("lane-opus-xhigh.md", committed)
        for name in committed:
            with open(os.path.join(out, name), "rb") as fresh, open(os.path.join(ROOT, "agents", name), "rb") as kept:
                self.assertEqual(fresh.read(), kept.read(), name)

    def test_stale_lane_file_is_removed_and_other_agents_are_kept(self):
        for name in ("lane-opus-low.md", "scout.md"):
            with open(os.path.join(self.out, name), "w", encoding="utf-8") as stream:
                stream.write("x\n")
        self.run_tool()
        self.assertEqual(self.names(), ["lane-haiku-high.md", "scout.md"])

    def test_check_passes_on_committed_files(self):
        result = subprocess.run([sys.executable, TOOL, "--check"], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, encoding="utf-8", check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_check_fails_after_an_arms_change_and_writes_nothing(self):
        self.run_tool()
        self.write_arms([{"lane": "haiku", "model": "claude-haiku-5-5", "effort": "medium", "status": "active"}])
        result = self.run_tool("--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("lane-haiku-medium.md", result.stdout)
        self.assertIn("lane-haiku-high.md", result.stdout)
        self.assertEqual(self.names(), ["lane-haiku-high.md"])


if __name__ == "__main__":
    unittest.main()
