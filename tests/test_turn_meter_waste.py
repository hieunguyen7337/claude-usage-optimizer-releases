"""Tests for `turn-meter waste`, on temporary copies of tests/fixtures/waste only.

Every store the command reads (CLAUDE_CONFIG_DIR, ~/.claude.json, CODEX_HOME, the lanes catalog's local file, Amp and
Antigravity, LANES_STATE) is pointed into a temporary directory, so this PC's own ~/.claude, ~/.codex and
~/.local/state are never read.
"""
import contextlib
import datetime as dt
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import shutil
import tempfile
import unittest
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
METER = os.path.join(ROOT, "bin", "turn-meter")
FIXTURES = os.path.join(ROOT, "tests", "fixtures", "waste")
UTC = dt.timezone.utc
_meter_loader = importlib.machinery.SourceFileLoader("turn_meter_waste_test", METER)
_meter_spec = importlib.util.spec_from_loader(_meter_loader.name, _meter_loader)
meter = importlib.util.module_from_spec(_meter_spec)
_meter_loader.exec_module(meter)

# The CRLF agent is written at run time (a committed CRLF file fails the release check).
CRLF_AGENT = ["---", "name: crlf-agent", "description: |", "  hello world", "---", "BODY-MARKER", ""]


def _iso(moment):
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class WasteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="waste-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.now = dt.datetime.now(UTC).replace(microsecond=0)
        self.base = self.now - dt.timedelta(hours=6)
        self.home = os.path.join(self.tmp, "home")
        self.config = os.path.join(self.home, ".claude")
        self.codex = os.path.join(self.home, ".codex")
        self.project_dir = os.path.join(self.tmp, "work", "proj")
        self.projects = os.path.join(self.config, "projects", "proj")
        for folder in (self.home, self.config, self.projects, os.path.join(self.codex, "sessions", "2026", "11"),
                       os.path.join(self.project_dir, ".claude", "agents")):
            os.makedirs(folder, exist_ok=True)
        self.env = {
            "HOME": self.home, "USERPROFILE": self.home, "CLAUDE_CONFIG_DIR": self.config, "CODEX_HOME": self.codex,
            "LANES_ARMS": os.path.join(ROOT, "arms.json"),
            "LANES_ARMS_LOCAL": os.path.join(self.tmp, "no-arms.local.json"),
            "LANES_STATE": os.path.join(self.tmp, "state"), "CLAUDE_USAGE_DIR": os.path.join(self.tmp, "usage"),
            "TURN_METER_AMP_THREADS": os.path.join(self.tmp, "amp-threads"),
            "TURN_METER_AGY_HOME": os.path.join(self.tmp, "agy"),
            "XDG_DATA_HOME": os.path.join(self.tmp, "xdg"),
        }
        for key in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "PYTHONUTF8"):
            if key in os.environ:
                self.env[key] = os.environ[key]

    # ---- fixture copies ----------------------------------------------------------------------------------------

    def _fill(self, text):
        cwd = json.dumps(self.project_dir)[1:-1]
        text = text.replace("__CWD__", cwd).replace("__OLD__", _iso(self.now - dt.timedelta(days=30)))
        text = text.replace("__TS__", _iso(self.now - dt.timedelta(hours=1)))
        return re.sub(r"__TS(\d+)__", lambda m: _iso(self.base + dt.timedelta(minutes=int(m.group(1)))), text)

    def _copy(self, source, target):
        with open(os.path.join(FIXTURES, source), encoding="utf-8") as handle:
            text = self._fill(handle.read())
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)

    def _sessions(self, names=("s1", "s2", "s3", "s4", "s5", "nodate", "old")):
        for name in names:
            self._copy(os.path.join("sessions", name + ".jsonl"), os.path.join(self.projects, name + ".jsonl"))

    def _inventory(self):
        for name in os.listdir(os.path.join(FIXTURES, "agents")):
            self._copy(os.path.join("agents", name), os.path.join(self.config, "agents", name))
        with open(os.path.join(self.config, "agents", "crlf-agent.md"), "w", encoding="utf-8",
                  newline="\r\n") as handle:
            handle.write("\n".join(CRLF_AGENT))
        for name in os.listdir(os.path.join(FIXTURES, "skills")):
            self._copy(os.path.join("skills", name, "SKILL.md"), os.path.join(self.config, "skills", name, "SKILL.md"))
        self._copy("settings.json", os.path.join(self.config, "settings.json"))
        self._copy("claude.json", os.path.join(self.home, ".claude.json"))
        self._copy(os.path.join("project-agents", "proj-agent.md"),
                   os.path.join(self.project_dir, ".claude", "agents", "proj-agent.md"))

    def _cache(self, names):
        for name in names:
            self._copy(os.path.join("cache", name + ".jsonl"), os.path.join(self.projects, "cache-" + name + ".jsonl"))

    def _codex_rollouts(self, names):
        for name in names:
            self._copy(os.path.join("codex", "rollout-" + name + ".jsonl"),
                       os.path.join(self.codex, "sessions", "2026", "11", "rollout-" + name + ".jsonl"))

    def _fast(self, names):
        for name in names:
            self._copy(os.path.join("fast", name + ".jsonl"), os.path.join(self.projects, "fast-" + name + ".jsonl"))

    def _report(self, platform="all", days=7):
        with mock.patch.dict(os.environ, self.env, clear=True):
            return meter._waste_report(days, platform, self.now)

    def _command(self, argv, extra_env=None):
        env = dict(self.env, **(extra_env or {}))
        out = io.StringIO()
        with mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(out):
            code = meter._main(argv)
        return code, out.getvalue()

    # ---- unused ------------------------------------------------------------------------------------------------

    def test_unused_lists_unused_agents_once_with_action_and_skips_used_ones(self):
        self._inventory()
        self._sessions()
        # A project agent with the same name as a user agent: still one row, the user one (found first).
        with open(os.path.join(self.project_dir, ".claude", "agents", "dup.md"), "w", encoding="utf-8") as handle:
            handle.write("---\nname: unused-agent\ndescription: \"a much longer project description here\"\n---\n")
        unused = self._report()["unused"]
        self.assertIsNone(unused["skipped"])
        rows = [(item["kind"], item["name"]) for item in unused["items"]]
        self.assertEqual(len(rows), len(set(rows)), rows)
        names = {item["name"]: item for item in unused["items"] if item["kind"] == "agent"}
        for used in ("used-agent", "used-task-agent", "undated-agent"):
            self.assertNotIn(used, names)
        for unused_name in ("unused-agent", "old-only-agent", "noname-agent", "crlf-agent", "proj-agent"):
            self.assertIn(unused_name, names)
        row = names["unused-agent"]
        self.assertEqual(row["scope"], "user")
        self.assertEqual(row["description_tokens"], 2)
        self.assertTrue(row["action"].startswith("disable agent unused-agent: unused in "), row["action"])
        self.assertIn("about 2 tokens per request", row["action"])
        skills = {item["name"] for item in unused["items"] if item["kind"] == "skill"}
        self.assertEqual(skills, {"unused-skill"})
        mcps = {item["name"] for item in unused["items"] if item["kind"] == "mcp"}
        self.assertNotIn("used-server", mcps)
        self.assertIn("ghost-server", mcps)
        self.assertIn("settings-server", mcps)

    def test_crlf_agent_name_comes_from_frontmatter(self):
        path = os.path.join(self.tmp, "renamed-file.md")
        with open(path, "w", encoding="utf-8", newline="\r\n") as handle:
            handle.write("\n".join(CRLF_AGENT))
        with open(path, "rb") as handle:
            self.assertIn(b"\r\n", handle.read())
        name, description = meter._waste_frontmatter(meter._waste_read_text(path))
        self.assertEqual(name, "crlf-agent")
        self.assertEqual(description, "hello world")
        # Through the inventory too: the file name differs from the frontmatter name.
        os.makedirs(os.path.join(self.config, "agents"), exist_ok=True)
        shutil.copyfile(path, os.path.join(self.config, "agents", "renamed-file.md"))
        with mock.patch.dict(os.environ, self.env, clear=True):
            items = meter._waste_inventory(set())
        self.assertIn(("agent", "crlf-agent"), [(item["kind"], item["name"]) for item in items])

    def test_unused_needs_enough_evidence(self):
        self._inventory()
        self._sessions(("s2",))
        unused = self._report()["unused"]
        self.assertIn("need 10 prompts", unused["skipped"])
        self.assertEqual(unused["items"], [])

    # ---- cache rehydration -------------------------------------------------------------------------------------

    def test_cache_rehydration_flags_claude_over_threshold_only(self):
        self._cache(("cold", "below"))
        cache = self._report(platform="claude-code")["cache_rehydration"]
        self.assertIsNone(cache["skipped"])
        sessions = {item["session"]: item for item in cache["sessions"]}
        self.assertIn("cache-cold", sessions)
        self.assertNotIn("cache-below", sessions)
        flagged = sessions["cache-cold"]
        self.assertEqual(flagged["threshold"], 2.35)
        self.assertGreaterEqual(flagged["ratio"], 2.35)
        self.assertTrue(flagged["action"].startswith("compact before idle gaps"))
        self.assertEqual([turn["cache_tokens"] for turn in flagged["cold_turns"]], [85000])

    def test_cache_rehydration_flags_codex_at_two(self):
        self._codex_rollouts(("flag", "below"))
        cache = self._report(platform="codex")["cache_rehydration"]
        self.assertIsNone(cache["skipped"])
        flagged = [item for item in cache["sessions"] if "flag" in item["session"]]
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0]["threshold"], 2.0)
        self.assertEqual(flagged[0]["platform"], "codex")
        self.assertFalse([item for item in cache["sessions"] if "below" in item["session"]])

    # ---- fast mode and old models ------------------------------------------------------------------------------

    def test_fast_mode_share_and_old_models(self):
        self._fast(("mixed",))
        old = self._report(platform="claude-code")["old_models"]
        self.assertIsNone(old["skipped"])
        fast = old["fast_mode"]
        self.assertIsNone(fast["skipped"])
        self.assertEqual(fast["field"], "usage.speed")
        self.assertAlmostEqual(fast["share"], 0.25, places=3)
        self.assertTrue(fast["action"].startswith("fast mode is 25.0% of list cost"), fast["action"])
        seen = {item["model"]: item for item in old["items"]}
        self.assertEqual(seen["claude-opus-4-6"]["newest"], "claude-opus-5-5")
        self.assertEqual(seen["claude-fable-5-1"]["newest"], "claude-fable-5-2")
        self.assertNotIn("claude-sonnet-5-5", seen)
        self.assertTrue(seen["claude-opus-4-6"]["action"].startswith("switch claude-opus-4-6 to claude-opus-5-5"))
        code, text = self._command(["waste", "--days", "7", "--platform", "claude-code"])
        self.assertEqual(code, 0)
        self.assertIn("fast mode is 25.0% of list cost", text)
        self.assertIn("switch claude-opus-4-6 to claude-opus-5-5", text)

    def test_fast_mode_and_old_models_give_skipped_reasons(self):
        self._fast(("tier",))
        old = self._report(platform="claude-code")["old_models"]
        self.assertIn("service_tier is present", old["fast_mode"]["skipped"])
        self.assertIsNone(old["fast_mode"]["action"])
        shutil.rmtree(self.projects)
        os.makedirs(self.projects)
        old = self._report(platform="claude-code")["old_models"]
        self.assertEqual(old["skipped"], "no models in the window")
        self.assertEqual(old["fast_mode"]["skipped"], "no fast-mode field in transcripts")
        code, text = self._command(["waste", "--days", "7", "--platform", "claude-code"])
        self.assertEqual(code, 0)
        self.assertIn("skipped: no models in the window", text)
        self.assertIn("fast mode skipped: no fast-mode field in transcripts", text)

    # ---- output and failure modes ------------------------------------------------------------------------------

    def test_json_prints_one_object_with_a_key_per_section(self):
        self._inventory()
        self._sessions()
        self._cache(("cold",))
        self._codex_rollouts(("flag",))
        code, text = self._command(["waste", "--days", "7", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(len(text.strip().splitlines()), 1)
        value = json.loads(text)
        self.assertIsInstance(value, dict)
        for key in meter.WASTE_KEYS:
            self.assertIn(key, value)
            self.assertIn("skipped", value[key])
        self.assertEqual(value["schema"], 1)
        self.assertFalse(value["off"])

    def test_off_switch_prints_skipped_report_and_exits_zero(self):
        self._inventory()
        self._sessions()
        code, text = self._command(["waste", "--days", "7"], {"TURN_METER_WASTE": "off"})
        self.assertEqual(code, 0)
        self.assertIn("skipped: TURN_METER_WASTE=off", text)
        code, text = self._command(["waste", "--json"], {"TURN_METER_WASTE": "off"})
        self.assertEqual(code, 0)
        value = json.loads(text)
        self.assertTrue(value["off"])
        for key in meter.WASTE_KEYS:
            self.assertEqual(value[key]["skipped"], "TURN_METER_WASTE=off")

    def test_exception_inside_report_still_exits_zero_with_skipped_report(self):
        self._inventory()
        self._sessions()
        with mock.patch.object(meter, "_waste_scan", side_effect=RuntimeError("boom")):
            code, text = self._command(["waste", "--json"])
        self.assertEqual(code, 0)
        value = json.loads(text)
        for key in meter.WASTE_KEYS:
            self.assertEqual(value[key]["skipped"], "error: RuntimeError")
        with mock.patch.object(meter, "_waste_report", side_effect=ValueError("boom")):
            code, text = self._command(["waste"])
        self.assertEqual(code, 0)
        self.assertIn("skipped: error: ValueError", text)
        with mock.patch.object(meter, "_waste_inventory", side_effect=OSError("boom")):
            code, text = self._command(["waste", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(text)["unused"]["skipped"], "error: inventory")


if __name__ == "__main__":
    unittest.main()
