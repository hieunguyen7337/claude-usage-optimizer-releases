import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUSLINE = os.path.join(ROOT, "bin", "claude-statusline")
POLICY = "Claude Usage Optimizer version: {}. Installed at `~/.claude/usage-optimizer/`.\n"
YELLOW = "\x1b[33m"
CYAN = "\x1b[36m"


class StatuslineVersionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self.usage = os.path.join(self.root, "usage")
        self.state = os.path.join(self.root, "state")
        self.policy = os.path.join(self.root, "POLICY.md")
        self.write_policy("2026-10-29.3")
        os.makedirs(os.path.join(self.state, "turns", "open"))
        with open(os.path.join(self.state, "turns", "open", "s1.json"), "w", encoding="utf-8") as handle:
            json.dump({"session_id": "s1", "cost_start_usd": 1.0}, handle)
        with open(os.path.join(self.state, "claude-calibration.json"), "w", encoding="utf-8") as handle:
            json.dump({"pct_per_usd": 0.04}, handle)
        self.env = dict(os.environ)
        self.env.update({"CLAUDE_USAGE_DIR": self.usage, "LANES_STATE": self.state, "HOME": self.root,
                         "USERPROFILE": self.root, "USAGE_OPTIMIZER_CODEX": "off",
                         "USAGE_OPTIMIZER_POLICY": self.policy, "NO_COLOR": "1"})
        for key in ("COLUMNS", "USAGE_OPTIMIZER_KIT_LABEL", "USAGE_OPTIMIZER_COLOR", "CLAUDE_CONFIG_DIR",
                    "USAGE_OPTIMIZER_UPDATE_CHECK"):
            self.env.pop(key, None)

    def write_policy(self, version):
        with open(self.policy, "w", encoding="utf-8") as handle:
            handle.write("# Claude Usage Optimizer: usage policy\n\n" + POLICY.format(version))

    def session_path(self, name="s1"):
        return os.path.join(self.usage, "sessions", name + ".json")

    def stored(self, name="s1"):
        with open(self.session_path(name), encoding="utf-8") as handle:
            return json.load(handle)

    def row1(self, cost=2.0, **env):
        data = {"session_id": "s1", "model": {"display_name": "Opus 5.5"}, "effort": {"level": "xhigh"},
                "context_window": {"context_window_size": 450000, "used_percentage": 71,
                                   "current_usage": {"input_tokens": 321000, "cache_creation_input_tokens": 0,
                                                     "cache_read_input_tokens": 0}},
                "cost": {"total_cost_usd": cost}}
        run_env = dict(self.env, **env)
        if env.get("NO_COLOR") == "":
            run_env.pop("NO_COLOR")
        result = subprocess.run([sys.executable, "-X", "utf8", STATUSLINE], input=json.dumps(data), text=True,
                                encoding="utf-8", stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env=run_env, timeout=15, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.splitlines()[0]

    def test_label_from_policy_and_session_record(self):
        line = self.row1()
        self.assertTrue(line.endswith(" · Usage Optimizer 2026-10-29.3"), line)
        self.assertEqual(self.stored()["kit_version"], "2026-10-29.3")

    def test_version_carries_over_and_mismatch_shows_both(self):
        self.row1(cost=2.0)
        self.write_policy("2026-10-29.4")
        line = self.row1(cost=3.0)
        self.assertTrue(line.endswith(" · Usage Optimizer 2026-10-29.3 → 2026-10-29.4"), line)
        self.assertEqual(self.stored()["kit_version"], "2026-10-29.3")
        self.assertNotIn("\x1b", line)

    def test_mismatch_arrow_is_yellow_with_colour(self):
        self.row1()
        self.write_policy("2026-10-29.4")
        line = self.row1(cost=3.0, NO_COLOR="", USAGE_OPTIMIZER_COLOR="on")
        self.assertIn("Usage Optimizer 2026-10-29.3 " + YELLOW + "→ 2026-10-29.4\x1b[0m", line)

    def test_record_without_field_gets_installed_version(self):
        os.makedirs(os.path.dirname(self.session_path()))
        with open(self.session_path(), "w", encoding="utf-8") as handle:
            json.dump({"session_id": "s1", "total_cost_usd": 1.5}, handle)
        line = self.row1(cost=2.0)
        self.assertTrue(line.endswith("Usage Optimizer 2026-10-29.3"), line)
        self.assertEqual(self.stored()["kit_version"], "2026-10-29.3")

    def test_fitting_steps(self):
        self.row1()
        self.write_policy("2026-10-29.4")
        steps = []
        for columns in (200, 86, 73, 63, 57, 34, 12):
            steps.append((columns, self.row1(COLUMNS=str(columns))))
        by_columns = dict(steps)
        full = "Opus 5.5 · xhigh · ctx 321k/450k (71%)"
        self.assertRegex(by_columns[200], r"^" + re.escape(full) + r" · turn .* · Usage Optimizer 2026-10-29\.3 → 2026-10-29\.4$")
        self.assertEqual(by_columns[86], full + " · Usage Optimizer 2026-10-29.3 → 2026-10-29.4")
        self.assertEqual(by_columns[73], full + " · UO 2026-10-29.3 → 2026-10-29.4")
        self.assertEqual(by_columns[63], full + " · UO 10-29.3 → 10-29.4")
        self.assertEqual(by_columns[57], "Opus 5.5 · xhigh · ctx 321k/450k · UO 10-29.3 → 10-29.4")
        self.assertEqual(by_columns[34], "Opus 5.5 · xhigh · ctx 321k/450k")

    def test_label_off(self):
        self.assertNotIn("Optimizer", self.row1(USAGE_OPTIMIZER_KIT_LABEL="off"))

    def test_missing_or_unmatched_policy_drops_segment(self):
        os.unlink(self.policy)
        line = self.row1()
        self.assertNotIn("Optimizer", line)
        self.assertTrue(line.startswith("Opus 5.5"), line)
        self.assertNotIn("kit_version", self.stored())
        with open(self.policy, "w", encoding="utf-8") as handle:
            handle.write("nothing useful here\n")
        self.assertNotIn("Optimizer", self.row1(cost=3.0))

    def write_update(self, latest, installed, **fields):
        # The cache bin/kit-update writes; the statusline only reads it.
        record = {"checked_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
                  "installed": installed, "latest": latest, "checkout": "/nowhere", "error": None,
                  "announced": latest}
        record.update(fields)
        with open(os.path.join(self.state, "kit-update.json"), "w", encoding="utf-8") as handle:
            json.dump(record, handle)

    def test_a_newer_published_release_follows_the_version_wide_and_narrow(self):
        self.write_policy("2026-10-31.13")
        self.write_update("2026-11-01.1", "2026-10-31.13")
        self.assertTrue(self.row1().endswith(" · Usage Optimizer 2026-10-31.13 ⇡ 2026-11-01.1"))
        full = "Opus 5.5 · xhigh · ctx 321k/450k (71%)"
        for text in (full + " · Usage Optimizer 2026-10-31.13 ⇡ 2026-11-01.1",
                     full + " · UO 2026-10-31.13 ⇡ 2026-11-01.1",
                     full + " · UO 10-31.13 ⇡ 11-01.1",
                     "Opus 5.5 · xhigh · ctx 321k/450k · UO 10-31.13 ⇡ 11-01.1"):
            # Claude Code keeps 2 columns spare, so the line is fitted to COLUMNS - 2.
            self.assertEqual(self.row1(COLUMNS=str(len(text) + 2)), text)

    def test_the_loaded_release_and_the_published_one_both_show(self):
        self.write_policy("2026-10-31.5")
        self.row1(cost=2.0)
        self.write_policy("2026-10-31.6")
        self.write_update("2026-11-01.1", "2026-10-31.6")
        self.assertTrue(self.row1(cost=3.0).endswith(" · Usage Optimizer 2026-10-31.5 → 2026-10-31.6 ⇡ 2026-11-01.1"))
        narrow = "Opus 5.5 · xhigh · ctx 321k/450k (71%) · UO 10-31.5 → 10-31.6 ⇡ 11-01.1"
        self.assertEqual(self.row1(cost=3.0, COLUMNS=str(len(narrow) + 2)), narrow)
        coloured = self.row1(cost=3.0, NO_COLOR="", USAGE_OPTIMIZER_COLOR="on")
        self.assertIn("Usage Optimizer 2026-10-31.5 " + YELLOW + "→ 2026-10-31.6\x1b[0m " + CYAN + "⇡ 2026-11-01.1\x1b[0m",
                      coloured)
        self.assertNotIn("\x1b", self.row1(cost=3.0, USAGE_OPTIMIZER_COLOR="on"))
        self.assertNotIn("\x1b", self.row1(cost=3.0, NO_COLOR="", USAGE_OPTIMIZER_COLOR="off"))

    def test_no_arrow_unless_the_published_release_is_newer_than_the_installed_one(self):
        self.write_policy("2026-10-31.13")
        for latest in ("2026-10-31.13", "2026-10-31.12", None, "junk"):
            with self.subTest(latest=latest):
                self.write_update(latest, "2026-10-31.13")
                self.assertTrue(self.row1().endswith(" · Usage Optimizer 2026-10-31.13"))
        self.write_update(None, "2026-10-31.13", error="git fetch origin main failed (exit 128)")
        self.assertTrue(self.row1().endswith(" · Usage Optimizer 2026-10-31.13"))
        # Updated since the last check: the arrow goes at once, before the next check runs.
        self.write_update("2026-11-01.1", "2026-10-31.13")
        self.write_policy("2026-11-01.1")
        self.assertNotIn("⇡", self.row1(cost=3.0))

    def test_the_off_switches_hide_the_published_release(self):
        self.write_policy("2026-10-31.13")
        self.write_update("2026-11-01.1", "2026-10-31.13")
        self.assertTrue(self.row1(USAGE_OPTIMIZER_UPDATE_CHECK="off").endswith(" · Usage Optimizer 2026-10-31.13"))
        self.assertNotIn("Optimizer", self.row1(USAGE_OPTIMIZER_KIT_LABEL="off"))

    def session_start(self, payload, raw=None):
        result = subprocess.run([sys.executable, "-X", "utf8", STATUSLINE, "session-start"],
                                input=raw if raw is not None else json.dumps(payload), text=True,
                                encoding="utf-8", stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env=self.env, timeout=15, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def write_record(self, name="s1"):
        os.makedirs(os.path.join(self.usage, "sessions"), exist_ok=True)
        record = {"session_id": name, "total_cost_usd": 2.0, "observed_at": "2026-10-29T10:00:00Z",
                  "model": "Opus 5.5", "kit_version": "2026-10-29.3"}
        with open(self.session_path(name), "w", encoding="utf-8") as handle:
            json.dump(record, handle)
        return record

    def test_session_start_resume_or_compact_moves_the_record_to_the_installed_version(self):
        for source in ("resume", "compact"):
            with self.subTest(source=source):
                record = self.write_record()
                self.write_policy("2026-10-31.6")
                self.session_start({"session_id": "s1", "source": source})
                record["kit_version"] = "2026-10-31.6"
                self.assertEqual(self.stored(), record)
                self.assertEqual(self.row1(cost=2.0).count("→"), 0)

    def test_session_start_ignores_other_sources(self):
        self.write_record()
        self.write_policy("2026-10-31.6")
        with open(self.session_path(), "rb") as handle:
            before = handle.read()
        self.session_start({"session_id": "s1", "source": "clear"})
        with open(self.session_path(), "rb") as handle:
            self.assertEqual(handle.read(), before)

    def test_session_start_never_creates_a_record(self):
        self.write_policy("2026-10-31.6")
        self.session_start({"session_id": "s1", "source": "startup"})
        self.assertFalse(os.path.exists(self.session_path()))

    def test_session_start_survives_bad_input(self):
        self.write_policy("2026-10-31.6")
        self.session_start(None, raw="not json")
        self.session_start({"session_id": "../s1", "source": "resume"})
        self.session_start({"session_id": "a/b", "source": "resume"})
        self.assertFalse(os.path.exists(os.path.join(self.usage, "sessions")))


if __name__ == "__main__":
    unittest.main()
