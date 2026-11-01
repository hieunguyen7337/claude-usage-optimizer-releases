import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUSLINE = os.path.join(ROOT, "bin", "claude-statusline")
YELLOW = "\x1b[33m"
RED = "\x1b[31m"
RESET = "\x1b[0m"


class StatuslineCompactTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        # The soft threshold is autoCompactWindow in the settings the status line reads.
        os.makedirs(os.path.join(self.root, ".claude"))
        with open(os.path.join(self.root, ".claude", "settings.json"), "w", encoding="utf-8") as handle:
            json.dump({"autoCompactWindow": 200000}, handle)
        self.env = dict(os.environ)
        self.env.update({"CLAUDE_USAGE_DIR": os.path.join(self.root, "usage"),
                         "LANES_STATE": os.path.join(self.root, "state"), "HOME": self.root,
                         "USERPROFILE": self.root, "USAGE_OPTIMIZER_CODEX": "off",
                         "USAGE_OPTIMIZER_KIT_LABEL": "off", "USAGE_OPTIMIZER_TURNS": "off",
                         "NO_COLOR": "1"})
        for key in ("COLUMNS", "USAGE_OPTIMIZER_COLOR", "USAGE_OPTIMIZER_COMPACT_GATE",
                    "USAGE_OPTIMIZER_COMPACT_HARD", "CLAUDE_CONFIG_DIR"):
            self.env.pop(key, None)

    def row1(self, used=150000, **env):
        data = {"session_id": "s1", "model": {"display_name": "Opus 5.5"}, "effort": {"level": "xhigh"},
                "context_window": {"context_window_size": 1000000, "used_percentage": 15,
                                   "current_usage": {"input_tokens": used, "cache_creation_input_tokens": 0,
                                                     "cache_read_input_tokens": 0}}}
        run_env = dict(self.env, **env)
        if env.get("NO_COLOR") == "":
            run_env.pop("NO_COLOR")
        result = subprocess.run([sys.executable, "-X", "utf8", STATUSLINE], input=json.dumps(data), text=True,
                                encoding="utf-8", stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env=run_env, timeout=15, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.splitlines()[0]

    def test_below_the_soft_threshold_is_unchanged(self):
        self.assertEqual(self.row1(), "Opus 5.5 · xhigh · ctx 150k/200k (75%)")

    def test_above_the_soft_threshold_says_it_compacts_between_turns(self):
        line = self.row1(used=260000)
        self.assertEqual(line, "Opus 5.5 · xhigh · ctx 260k/200k, compacts between turns")
        coloured = self.row1(used=260000, NO_COLOR="", USAGE_OPTIMIZER_COLOR="on")
        self.assertEqual(coloured, "Opus 5.5 · xhigh · " + YELLOW + "ctx 260k/200k, compacts between turns" + RESET)

    def test_at_the_hard_ceiling_the_segment_is_red(self):
        line = self.row1(used=350000, NO_COLOR="", USAGE_OPTIMIZER_COLOR="on")
        self.assertEqual(line, "Opus 5.5 · xhigh · " + RED + "ctx 350k/200k, compacts between turns" + RESET)
        raised = self.row1(used=360000, NO_COLOR="", USAGE_OPTIMIZER_COLOR="on", USAGE_OPTIMIZER_COMPACT_HARD="500000")
        self.assertIn(YELLOW + "ctx 360k/200k, compacts between turns", raised)

    def test_narrow_variant_drops_the_note_and_stays_yellow(self):
        line = self.row1(used=260000, COLUMNS="40", NO_COLOR="", USAGE_OPTIMIZER_COLOR="on")
        self.assertEqual(line, "Opus 5.5 · xhigh · " + YELLOW + "ctx 260k/200k" + RESET)
        hard = self.row1(used=360000, COLUMNS="40", NO_COLOR="", USAGE_OPTIMIZER_COLOR="on")
        self.assertEqual(hard, "Opus 5.5 · xhigh · " + RED + "ctx 360k/200k" + RESET)

    def test_gate_off_keeps_the_old_segment(self):
        self.assertEqual(self.row1(used=260000, USAGE_OPTIMIZER_COMPACT_GATE="off"),
                         "Opus 5.5 · xhigh · ctx 260k/200k (130%)")
        self.assertEqual(self.row1(used=360000, USAGE_OPTIMIZER_COMPACT_GATE="off", COLUMNS="40"),
                         "Opus 5.5 · xhigh · ctx 360k/200k")


if __name__ == "__main__":
    unittest.main()
