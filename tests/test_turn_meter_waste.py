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
import sys
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

    def _write(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(self._fill(text))

    def _rollout(self, name, events):
        text = "\n".join(json.dumps(event, separators=(",", ":")) for event in events) + "\n"
        self._write(os.path.join(self.codex, "sessions", "2026", "11", "rollout-" + name + ".jsonl"), text)

    def _spawn(self, parent, depth, nickname=None, role=None):
        return {"subagent": {"thread_spawn": {
            "parent_thread_id": parent, "depth": depth, "agent_path": "agents/x.md",
            "agent_nickname": nickname, "agent_role": role}}}

    def _meta(self, source, thread_id, origin="codex_exec", ts="__TS0__"):
        return {"timestamp": ts, "type": "session_meta",
                "payload": {"id": thread_id, "originator": origin, "source": source}}

    def _turn(self, model, ts="__TS0__"):
        return {"timestamp": ts, "type": "turn_context", "payload": {"model": model}}

    def _tokens(self, output, ts="__TS1__"):
        return {"timestamp": ts, "type": "event_msg", "payload": {"type": "token_count", "info": {"last_token_usage": {
            "input_tokens": 0, "cached_input_tokens": 0, "output_tokens": output, "reasoning_output_tokens": 0}}}}

    def _call(self, kind, call_id, ts="__TS0__", ident_key="call_id"):
        return {"timestamp": ts, "type": "response_item",
                "payload": {"type": kind, ident_key: call_id, "name": "tool"}}

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

    # ---- codex sub-agents, amp, agy ---------------------------------------------------------------------------

    def test_subagent_action_flags_astra_always_and_sol_only_when_light(self):
        self.assertEqual(meter._waste_subagent_action("gpt-6-astra", 8, 5000), "astra is never a sub-agent model")
        self.assertEqual(meter._waste_subagent_action("gpt-6.1-sol", 5, 1999), "a smaller model probably fits")
        self.assertEqual(meter._waste_subagent_action("claude-opus-4-6", 5, 1999), "a smaller model probably fits")
        self.assertIsNone(meter._waste_subagent_action("gpt-6.1-sol", 6, 100))
        self.assertIsNone(meter._waste_subagent_action("gpt-6.1-sol", 2, 2000))
        self.assertIsNone(meter._waste_subagent_action("claude-haiku-4-5", 1, 100))
        self.assertIsNone(meter._waste_subagent_action("gpt-6-luna", 1, 10))
        spawn = meter._waste_codex_spawn({"id": "t", "originator": "codex_exec", "source": "exec"})
        self.assertIsNone(spawn)
        spawn = meter._waste_codex_spawn({"id": " child ", "originator": "codex_exec", "source": {"subagent": {
            "thread_spawn": {"parent_thread_id": " P1 ", "depth": True, "agent_nickname": "", "agent_role": "helper"}}}})
        self.assertEqual(spawn["parent"], "P1")
        self.assertIsNone(spawn["depth"])
        self.assertEqual(spawn["nickname"], "helper")
        self.assertEqual(spawn["thread_id"], "child")

    def test_codex_subagents_are_their_own_place_and_astra_is_always_overpowered(self):
        parent = [self._meta("exec", "parent-thread"), self._turn("gpt-6-astra"), self._tokens(10),
                  self._call("function_call", "parent-tool")]
        astra = [self._meta(self._spawn("P1", 1, "scout"), "child-astra"), self._turn("gpt-6-astra"),
                 self._tokens(5000)]
        for index in range(6):
            astra.append(self._call("function_call", "c{}".format(index)))
        astra.append(self._call("function_call", "c-id", ident_key="id"))
        astra.append(self._call("custom_tool_call", "custom-1"))
        astra.append(self._call("function_call", "c0"))
        astra.append(self._call("function_call_output", "c0"))
        sol = [self._meta(self._spawn("P1", 2, None, "helper"), "child-sol"), self._turn("gpt-6.1-sol"),
               self._tokens(100), self._call("function_call", "s0"), self._call("function_call", "s1")]
        heavy = [self._meta(self._spawn("P2", 3, "builder"), "child-heavy"), self._turn("gpt-6.1-sol"),
                 self._tokens(100)]
        heavy.extend(self._call("function_call", "h{}".format(index)) for index in range(6))
        bound = [self._meta(self._spawn("P2", 1, "edge"), "child-bound"), self._turn("gpt-6.1-sol"),
                 self._tokens(2000), self._call("function_call", "b0"), self._call("function_call", "b1")]
        luna = [self._meta(self._spawn("P2", True, None, "lookup"), "child-luna"), self._turn("gpt-6-luna"),
                self._tokens(10), self._call("function_call", "l0")]
        bare = [self._meta(self._spawn("P1", 1, "bare"), "child-bare"), self._turn("gpt-6-astra"),
                {"timestamp": "__TS1__", "type": "event_msg", "payload": {"type": "other"}}]
        old = [self._meta(self._spawn("P9", 9, "stale"), "child-old", ts="__OLD__"),
               self._turn("gpt-6-astra", "__OLD__"), self._tokens(5000, "__OLD__")]
        for name, events in (("parent", parent), ("astra", astra), ("sol", sol), ("heavy", heavy),
                             ("bound", bound), ("luna", luna), ("bare", bare), ("old", old)):
            self._rollout(name, events)
        report = self._report()
        codex = report["agents"]["codex"]
        self.assertEqual(codex["codex_exec"]["sessions"], 1)
        self.assertEqual(codex["codex_exec"]["turns"], 1)
        self.assertEqual(codex["codex_exec"]["models"], {"gpt-6-astra": 1})
        self.assertAlmostEqual(codex["codex_exec"]["active_seconds"], 60.0)
        place = codex["subagent"]
        self.assertEqual(place["sessions"], 6)
        self.assertEqual(place["turns"], 6)
        self.assertEqual(place["max_depth"], 3)
        self.assertEqual(place["parents"], ["P1", "P2"])
        self.assertAlmostEqual(place["active_seconds"], 360.0)
        self.assertEqual(place["models"], {"gpt-6-astra": 2, "gpt-6.1-sol": 3, "gpt-6-luna": 1})
        self.assertNotIn("child-old", json.dumps(codex))
        items = {item["agent_id"]: item for item in report["overpowered_subagents"]["items"]}
        self.assertEqual(set(items), {"child-bare", "child-astra", "child-sol"})
        self.assertEqual(items["child-astra"]["action"], "astra is never a sub-agent model")
        self.assertEqual(items["child-astra"]["session"], "P1")
        self.assertEqual(items["child-astra"]["model"], "gpt-6-astra")
        self.assertEqual(items["child-astra"]["agent_type"], "scout")
        self.assertEqual(items["child-astra"]["tool_calls"], 8)
        self.assertEqual(items["child-astra"]["output_tokens"], 5000)
        self.assertAlmostEqual(items["child-astra"]["list_usd"], 0.25, places=6)
        self.assertEqual(items["child-astra"]["platform"], "codex")
        self.assertEqual(items["child-bare"]["action"], "astra is never a sub-agent model")
        self.assertIsNone(items["child-bare"]["list_usd"])
        self.assertEqual(items["child-bare"]["tool_calls"], 0)
        self.assertEqual(items["child-sol"]["action"], "a smaller model probably fits")
        self.assertEqual(items["child-sol"]["agent_type"], "helper")
        self.assertEqual(items["child-sol"]["tool_calls"], 2)
        self.assertEqual(items["child-sol"]["output_tokens"], 100)
        self.assertAlmostEqual(items["child-sol"]["list_usd"], 0.001, places=6)
        self.assertIsNone(report["overpowered_subagents"]["skipped"])
        text = meter._waste_text(report)
        self.assertIn("codex subagent", text)
        self.assertIn("depth 3  parents 2", text)
        self.assertIn("astra is never a sub-agent model", text)
        self.assertIn("amp: skipped (no Amp thread store)", text)
        self.assertIn("agy: skipped (no Antigravity store)", text)
        code, command_text = self._command(["waste", "--days", "7"])
        self.assertEqual(code, 0)
        self.assertIn("depth 3  parents 2", command_text)
        claude_only = self._report(platform="claude-code")
        self.assertEqual(claude_only["agents"]["codex"]["subagent"]["sessions"], 6)
        self.assertEqual(claude_only["overpowered_subagents"]["items"], [])
        self.assertIn("no transcripts in the window", claude_only["overpowered_subagents"]["skipped"])

    def test_claude_opus_subagent_still_flags_only_light_work(self):
        def line(model, output, tools, name):
            content = [{"type": "tool_use", "name": "Read", "id": "t{}".format(index), "input": {}}
                       for index in range(tools)]
            return {"timestamp": "__TS0__", "type": "assistant", "subagent_type": "explore", "message": {
                "id": name, "model": model, "usage": {
                    "input_tokens": 10, "output_tokens": output, "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0}, "content": content}}
        folder = os.path.join(self.projects, "sess", "subagents")
        for name, model, output, tools in (
                ("agent-opus", "claude-opus-4-6", 1999, 5),
                ("agent-six", "claude-opus-4-6", 100, 6),
                ("agent-big", "claude-opus-4-6", 2000, 1),
                ("agent-haiku", "claude-haiku-4-5", 100, 1)):
            self._write(os.path.join(folder, name + ".jsonl"), json.dumps(line(model, output, tools, name)) + "\n")
        items = self._report(platform="claude-code")["overpowered_subagents"]["items"]
        self.assertEqual([item["agent_id"] for item in items], ["agent-opus"])
        self.assertEqual(items[0]["tool_calls"], 5)
        self.assertEqual(items[0]["output_tokens"], 1999)
        self.assertEqual(items[0]["action"], "a smaller model probably fits")
        self.assertEqual(items[0]["agent_type"], "explore")
        self.assertNotIn("platform", items[0])

    def test_amp_local_threads_count_models_and_output_and_do_not_call_the_cli(self):
        root = self.env["TURN_METER_AMP_THREADS"]
        os.makedirs(root)
        log = os.path.join(self.tmp, "amp-should-not-run.log")
        self.env["LANES_AMP_BIN"] = os.path.join(self.tmp, "no-such-amp")
        self.env["WASTE_AMP_LOG"] = log
        threads = {
            "in-a.json": {"created": "__TS0__", "model": "amp-a", "messages": [
                {"meta": {"sentAt": "__TS1__"}, "usage": {"timestamp": "__TS1__", "output_tokens": 15}},
                {"usage": {"outputTokens": 0, "timestamp": "__TS1__"}}]},
            "in-b.json": {"created": "__TS0__", "messages": [
                {"meta": {"sentAt": "__TS1__", "modelId": "amp-b"}, "usage": {"output_tokens": 0}}]},
            "old.json": {"created": "__OLD__", "model": "amp-old", "messages": [
                {"usage": {"output_tokens": 999, "timestamp": "__OLD__"}}]},
        }
        for name, body in threads.items():
            self._write(os.path.join(root, name), json.dumps(body))
        amp = self._report()["agents"]["amp"]
        self.assertEqual(amp["status"], "read")
        self.assertIsNone(amp["skipped"])
        self.assertEqual(amp["sessions"], 2)
        self.assertEqual(amp["models"], {"amp-a": 1, "amp-b": 1})
        self.assertEqual(amp["output_tokens"], 15)
        self.assertAlmostEqual(amp["active_hours"], round(120 / 3600.0, 4))
        self.assertFalse(os.path.exists(log))
        text = meter._waste_text(self._report())
        self.assertIn("amp", text)
        self.assertIn("out 15", text)
        self.assertIn("amp-a 1", text)
        bare = os.path.join(self.tmp, "amp-no-tokens")
        os.makedirs(bare)
        self._write(os.path.join(bare, "t.json"), json.dumps(
            {"created": "__TS0__", "model": "amp-a", "messages": [{"meta": {"sentAt": "__TS1__"}}]}))
        self.env["TURN_METER_AMP_THREADS"] = bare
        amp = self._report()["agents"]["amp"]
        self.assertEqual(amp["sessions"], 1)
        self.assertEqual(amp["models"], {"amp-a": 1})
        self.assertIsNone(amp["output_tokens"])

    def _amp_cli_env(self, mode):
        script = os.path.join(self.tmp, "fake-amp-list.py")
        with open(script, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join([
                "import os, sys, time",
                "log = os.environ.get('WASTE_AMP_LOG')",
                "mode = os.environ.get('WASTE_AMP_MODE', '')",
                "open(log, 'a', encoding='utf-8').write(' '.join(sys.argv[1:]) + '\\n')",
                "if mode == 'fail':",
                "    sys.exit(2)",
                "if mode == 'hang':",
                "    time.sleep(30)",
                "if mode == 'urls':",
                "    print('one  1mo ago  https://ampcode.com/threads/T-abc')",
                "    print('two  2d ago   https://ampcode.com/threads/T-def extra')",
                "    print('dup  1mo ago  https://ampcode.com/threads/T-abc')",
                ""]))
        if os.name == "nt":
            wrapper = os.path.join(self.tmp, "amp.cmd")
            body = '@echo off\r\n"{}" "{}" %*\r\n'.format(sys.executable, script)
        else:
            wrapper = os.path.join(self.tmp, "amp")
            body = '#!/bin/sh\nexec "{}" "{}" "$@"\n'.format(sys.executable, script)
        with open(wrapper, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(body)
        os.chmod(wrapper, 0o700)
        env = {key: value for key, value in self.env.items()
               if key not in ("TURN_METER_AMP_THREADS", "AMP_THREADS_DIR", "AMP_DATA_DIR")}
        env["LANES_AMP_BIN"] = wrapper
        env["WASTE_AMP_LOG"] = os.path.join(self.tmp, "amp-cli.log")
        env["WASTE_AMP_MODE"] = mode
        if os.path.exists(env["WASTE_AMP_LOG"]):
            os.remove(env["WASTE_AMP_LOG"])
        return env

    def _amp_cli_report(self, mode, timeout=None):
        env = self._amp_cli_env(mode)
        if timeout is not None:
            env["USAGE_OPTIMIZER_AMP_TIMEOUT"] = timeout
        with mock.patch.dict(os.environ, env, clear=True):
            report = meter._waste_report(7, "all", self.now)
        try:
            with open(env["WASTE_AMP_LOG"], encoding="utf-8") as handle:
                calls = [line.strip() for line in handle if line.strip()]
        except OSError:
            calls = []
        return report["agents"]["amp"], calls

    def test_amp_cli_list_is_used_only_without_a_local_store_and_is_not_guessed(self):
        amp, calls = self._amp_cli_report("urls")
        self.assertEqual(calls, ["threads list --include-archived"])
        self.assertEqual(amp["status"], "not read")
        self.assertEqual(amp["sessions"], 0)
        self.assertIn("returned 2 threads", amp["skipped"])
        self.assertIn("no absolute timestamps", amp["skipped"])
        self.assertIsNone(amp["output_tokens"])
        text = "amp: skipped ({})".format(amp["skipped"])
        self.assertIn(text, meter._waste_text(self._report_with_amp("urls")))
        amp, calls = self._amp_cli_report("empty")
        self.assertEqual(calls, ["threads list --include-archived"])
        self.assertEqual(amp["status"], "read")
        self.assertIsNone(amp["skipped"])
        self.assertEqual(amp["sessions"], 0)
        self.assertIn("returned no threads", amp["note"])
        amp, _calls = self._amp_cli_report("fail")
        self.assertEqual(amp["skipped"], "amp threads list failed")
        missing = dict(self._amp_cli_env("urls"), LANES_AMP_BIN=os.path.join(self.tmp, "missing-amp"))
        with mock.patch.dict(os.environ, missing, clear=True):
            amp = meter._waste_report(7, "all", self.now)["agents"]["amp"]
        self.assertEqual(amp["skipped"], "amp could not be started")
        amp, _calls = self._amp_cli_report("hang", timeout="1")
        self.assertEqual(amp["skipped"], "amp threads list timed out")

    def _report_with_amp(self, mode):
        env = self._amp_cli_env(mode)
        with mock.patch.dict(os.environ, env, clear=True):
            return meter._waste_report(7, "all", self.now)

    def test_agy_jsonl_counts_sessions_and_does_not_invent_models(self):
        root = self.env["TURN_METER_AGY_HOME"]
        logs = os.path.join(root, "brain", "conv-full", ".system_generated", "logs")
        full = [
            {"created_at": "__TS0__", "type": "PLANNER_RESPONSE", "step_index": 1, "output_tokens": 10,
             "model": "gemini-test"},
            {"created_at": "__TS0__", "type": "GENERIC", "step_index": 1, "output_tokens": 30},
            {"created_at": "__TS1__", "type": "GENERIC", "step_index": 2, "output_tokens": 7},
            {"created_at": "__TS1__", "type": "GENERIC", "output_tokens": 5},
            {"created_at": "__TS1__", "type": "GENERIC", "output_tokens": 1.5},
        ]
        decoy = [{"created_at": "__TS0__", "model": "wrong-model", "output_tokens": 999, "step_index": 1}]
        self._write(os.path.join(logs, "transcript_full.jsonl"),
                    "\n".join(json.dumps(line) for line in full) + "\n")
        self._write(os.path.join(logs, "transcript.jsonl"),
                    "\n".join(json.dumps(line) for line in decoy) + "\n")
        self._write(os.path.join(root, "history.jsonl"), "\n".join([
            json.dumps({"timestamp": "__OLD__", "conversationId": "conv-full"}),
            json.dumps({"timestamp": "__TS0__", "conversationId": "from-history"}),
        ]) + "\n")
        os.makedirs(os.path.join(root, "conversations"))
        with open(os.path.join(root, "conversations", "conv.db"), "wb") as handle:
            handle.write(b"not-sqlite")
        agents = self._report()["agents"]
        agy = agents["agy"]
        self.assertIsNone(agy["skipped"])
        self.assertEqual(agy["sessions"], 2)
        self.assertAlmostEqual(agy["active_seconds"], 60.0)
        self.assertEqual(agy["models"], {"gemini-test": 1})
        self.assertEqual(agy["output_tokens"], 42)
        self.assertNotIn("models_note", agy)
        self.assertNotIn("note", agy)
        self.assertIn("sqlite store not parsed", agents["antigravity"]["note"])
        text = meter._waste_text(self._report())
        self.assertIn("agy", text)
        self.assertIn("gemini-test 1", text)
        self.assertIn("out 42", text)

    def test_agy_without_a_model_field_says_so_and_a_protobuf_store_is_skipped(self):
        root = os.path.join(self.tmp, "agy-nomodel")
        logs = os.path.join(root, "brain", "conv-a", ".system_generated", "logs")
        lines = [
            {"created_at": "__TS0__", "type": "USER_INPUT", "step_index": 1, "output_tokens": 8},
            {"created_at": "__TS1__", "type": "PLANNER_RESPONSE", "step_index": 1, "output_tokens": 3},
        ]
        self._write(os.path.join(logs, "transcript.jsonl"), "\n".join(json.dumps(line) for line in lines) + "\n")
        mtime_logs = os.path.join(root, "brain", "conv-b", ".system_generated", "logs")
        self._write(os.path.join(mtime_logs, "transcript.jsonl"), json.dumps({"type": "GENERIC"}) + "\n")
        os.makedirs(os.path.join(root, "conversations"))
        with open(os.path.join(root, "conversations", "x.db"), "wb") as handle:
            handle.write(b"pb")
        self.env["TURN_METER_AGY_HOME"] = root
        agy = self._report()["agents"]["agy"]
        self.assertIsNone(agy["skipped"])
        self.assertEqual(agy["sessions"], 2)
        self.assertEqual(agy["models"], {})
        self.assertEqual(agy["output_tokens"], 8)
        self.assertAlmostEqual(agy["active_seconds"], 60.0)
        self.assertIn("no model field in JSONL transcripts", agy["models_note"])
        self.assertIn("protobuf", agy["models_note"])
        text = meter._waste_text(self._report())
        self.assertIn("no model field in JSONL transcripts", text)

        protobuf = os.path.join(self.tmp, "agy-db")
        os.makedirs(os.path.join(protobuf, "conversations"))
        with open(os.path.join(protobuf, "conversations", "only.db"), "wb") as handle:
            handle.write(b"pb")
        self.env["TURN_METER_AGY_HOME"] = protobuf
        agents = self._report()["agents"]
        self.assertNotIn("sessions", agents["agy"])
        self.assertIn("protobuf", agents["agy"]["skipped"])
        self.assertEqual(agents["antigravity"]["status"], "not read")
        self.assertIn("agy: skipped (", meter._waste_text(self._report()))

        self.env["TURN_METER_AGY_HOME"] = os.path.join(self.tmp, "agy-missing")
        self.assertEqual(self._report()["agents"]["agy"], {"skipped": "no Antigravity store"})
        present = os.path.join(self.tmp, "agy-empty")
        os.makedirs(present)
        self.env["TURN_METER_AGY_HOME"] = present
        agy = self._report()["agents"]["agy"]
        self.assertIsNone(agy["skipped"])
        self.assertEqual(agy["sessions"], 0)
        self.assertEqual(agy["models"], {})
        self.assertIsNone(agy["output_tokens"])
        self.assertNotIn("models_note", agy)

    def test_off_report_keeps_the_waste_keys_and_skips_agy(self):
        _code, text = self._command(["waste", "--json"], {"TURN_METER_WASTE": "off"})
        value = json.loads(text)
        self.assertEqual(meter.WASTE_KEYS, (
            "unused", "cache_rehydration", "overpowered_subagents", "old_models", "agents"))
        self.assertEqual(value["agents"]["agy"], {"skipped": "TURN_METER_WASTE=off"})
        self.assertEqual(value["agents"]["amp"]["skipped"], "TURN_METER_WASTE=off")
        self.assertIn("antigravity", value["agents"])


if __name__ == "__main__":
    unittest.main()
