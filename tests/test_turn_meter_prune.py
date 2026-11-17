"""Tests for `turn-meter prune`, in a temporary HOME / state dir with fake agents, skills and turns.jsonl.

Reuses the isolation and fixtures of tests/test_turn_meter_waste.py; nothing under the real home is read or moved.
"""
import datetime as dt
import json
import os
import unittest

from tests import test_turn_meter_waste as waste_tests

UTC = dt.timezone.utc


class PruneTest(unittest.TestCase):
    def setUp(self):
        # A helper instance supplies the temp HOME, env, fixture copies and the _main runner.
        self.h = waste_tests.WasteTest("test_json_prints_one_object_with_a_key_per_section")
        self.h.setUp()
        self.addCleanup(self.h.tearDown)
        self.h._inventory()
        self.h._sessions()
        self.config = self.h.config
        self.state = self.h.env["LANES_STATE"]
        # A user agent the kit installs, a kit-named copy, a lane- skill and a non-kit unused agent outside the dirs.
        self._text(os.path.join(self.config, "agents", "lane-foo.md"), "---\nname: lane-foo\ndescription: x\n---\n")
        self._text(os.path.join(self.config, "agents", "digest.md"), "---\nname: digest\ndescription: x\n---\n")
        self._text(os.path.join(self.config, "skills", "lane-skill", "SKILL.md"), "---\nname: lane-skill\n---\n")

    def _text(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)

    def _turn(self, minutes_ago):
        ended = dt.datetime.now(UTC) - dt.timedelta(minutes=minutes_ago)
        stamp = ended.isoformat(timespec="seconds").replace("+00:00", "Z")
        self._text(os.path.join(self.state, "turns.jsonl"), json.dumps(
            {"type": "turn", "turn_id": "t-1", "session_id": "s", "started_at": stamp, "ended_at": stamp}) + "\n")

    def _run(self, *argv):
        code, out = self.h._command(["prune"] + list(argv))
        return code, out

    def _json(self, *argv):
        code, out = self._run(*(list(argv) + ["--json"]))
        return code, json.loads(out)

    def _agent(self, name):
        return os.path.join(self.config, "agents", name + ".md")

    def _skill(self, name):
        return os.path.join(self.config, "skills", name)

    def test_dry_run_lists_candidates_and_excludes_kit_and_project_items(self):
        code, out = self._run()
        self.assertEqual(code, 0)
        self.assertIn("agent unused-agent (user) ~2 tok/request -> would move " + self._agent("unused-agent"), out)
        self.assertIn("skill unused-skill (user)", out)
        self.assertIn("excluded agent lane-foo (user): installed by the kit", out)
        self.assertIn("excluded agent digest (user): installed by the kit", out)
        self.assertIn("excluded skill lane-skill (user): installed by the kit", out)
        self.assertIn("excluded agent proj-agent (project)", out)
        self.assertNotIn("would move " + self._agent("lane-foo"), out)
        self.assertTrue(os.path.exists(self._agent("unused-agent")))
        self.assertFalse(os.path.exists(os.path.join(self.state, "pruned")))

    def test_dry_run_json_shape(self):
        code, value = self._json()
        self.assertEqual(code, 0)
        self.assertEqual(value["mode"], "dry-run")
        names = {(c["kind"], c["name"]): c for c in value["candidates"]}
        self.assertEqual(names[("agent", "unused-agent")]["action"], "move")
        self.assertEqual(names[("mcp", "ghost-server")]["action"], "manual")
        self.assertEqual(names[("mcp", "ghost-server")]["command"], "claude mcp remove ghost-server -s user")
        self.assertNotIn(("agent", "lane-foo"), names)
        reasons = {(e["kind"], e["name"]): e["reason"] for e in value["excluded"]}
        self.assertIn(("agent", "lane-foo"), reasons)
        self.assertIn("project scope", reasons[("agent", "proj-agent")])

    def test_outside_path_is_excluded(self):
        item = {"kind": "agent", "name": "x", "scope": "user", "path": os.path.join(self.h.tmp, "elsewhere", "x.md")}
        self.assertIn("outside", self.h_meter()._prune_exclusion(item, self.config, set()))

    def test_skill_folder_without_skill_md_is_excluded(self):
        # ~/.claude/skills/synced holds Claude Code's synced skills one level down; moving it would drop them all.
        self._text(os.path.join(self._skill("synced"), "abc_def", "chrome-browser", "SKILL.md"), "---\nname: c\n---\n")
        item = {"kind": "skill", "name": "synced", "scope": "user", "path": self._skill("synced")}
        self.assertIn("no SKILL.md", self.h_meter()._prune_exclusion(item, self.config, set()))
        item = {"kind": "skill", "name": "unused-skill", "scope": "user", "path": self._skill("unused-skill")}
        self.assertIsNone(self.h_meter()._prune_exclusion(item, self.config, set()))

    def h_meter(self):
        return waste_tests.meter

    def test_apply_moves_and_writes_manifest(self):
        self._turn(120)
        code, value = self._json("--apply", "unused-agent", "unused-skill")
        self.assertEqual(code, 0, value)
        self.assertFalse(os.path.exists(self._agent("unused-agent")))
        self.assertFalse(os.path.exists(self._skill("unused-skill")))
        stamp = value["stamp"]
        folder = os.path.join(self.state, "pruned", stamp)
        self.assertTrue(os.path.isfile(os.path.join(folder, "agent", "unused-agent.md")))
        self.assertTrue(os.path.isfile(os.path.join(folder, "skill", "unused-skill", "SKILL.md")))
        with open(os.path.join(folder, "manifest.json"), encoding="utf-8") as handle:
            manifest = json.load(handle)
        by_name = {i["name"]: i for i in manifest["items"]}
        self.assertEqual(set(by_name), {"unused-agent", "unused-skill"})
        agent = by_name["unused-agent"]
        self.assertEqual(agent["kind"], "agent")
        self.assertEqual(agent["original_path"], self._agent("unused-agent"))
        self.assertTrue(agent["new_path"].startswith(folder))
        self.assertEqual(agent["tokens"], 2)
        self.assertTrue(agent["time"].endswith("Z"))

    def test_apply_refuses_kit_items_and_unknown_names(self):
        self._turn(120)
        code, value = self._json("--apply", "lane-foo", "digest", "no-such-thing")
        self.assertEqual(code, 1)
        self.assertTrue(os.path.exists(self._agent("lane-foo")))
        self.assertTrue(os.path.exists(self._agent("digest")))
        self.assertEqual(value["applied"], [])
        self.assertEqual(value["not_found"], ["no-such-thing"])
        self.assertEqual(sorted(e["name"] for e in value["excluded"]), ["digest", "lane-foo"])
        self.assertIsNone(value["manifest"])

    def test_idle_gate_refuses_and_now_overrides(self):
        self._turn(5)
        code, out = self._run("--apply", "unused-agent")
        self.assertEqual(code, 3)
        self.assertEqual(len(out.strip().splitlines()), 1)
        self.assertIn("5 min ago", out)
        self.assertIn("--now", out)
        self.assertTrue(os.path.exists(self._agent("unused-agent")))
        code, value = self._json("--apply", "unused-agent")
        self.assertEqual(code, 3)
        self.assertIn("refused", value)
        code, value = self._json("--apply", "unused-agent", "--now")
        self.assertEqual(code, 0, value)
        self.assertFalse(os.path.exists(self._agent("unused-agent")))

    def test_lane_run_in_flight_refuses(self):
        started = (dt.datetime.now(UTC) - dt.timedelta(minutes=3)).isoformat(timespec="seconds").replace("+00:00", "Z")
        self._text(os.path.join(self.state, "runs", "r1", "meta.json"),
                   json.dumps({"lane": "x", "started_at": started, "ended_at": None}))
        code, out = self._run("--apply-all")
        self.assertEqual(code, 3)
        self.assertIn("in flight", out)
        self.assertTrue(os.path.exists(self._agent("unused-agent")))

    def test_mcp_is_manual_only_and_never_edits_config(self):
        self._turn(120)
        claude_json = os.path.join(self.h.home, ".claude.json")
        with open(claude_json, "rb") as handle:
            before = handle.read()
        settings = os.path.join(self.config, "settings.json")
        with open(settings, "rb") as handle:
            settings_before = handle.read()
        code, out = self._run("--apply", "ghost-server")
        self.assertEqual(code, 0, out)
        self.assertIn("claude mcp remove ghost-server -s user", out)
        with open(claude_json, "rb") as handle:
            self.assertEqual(handle.read(), before)
        with open(settings, "rb") as handle:
            self.assertEqual(handle.read(), settings_before)
        code, value = self._json("--apply", "ghost-server")
        self.assertEqual(value["applied"], [])
        self.assertEqual(value["manual"][0]["status"], "manual")
        with open(value["manifest"], encoding="utf-8") as handle:
            manifest = json.load(handle)
        self.assertEqual(manifest["items"][0]["status"], "manual")
        self.assertIsNone(manifest["items"][0]["new_path"])

    def test_apply_all_then_restore_round_trip(self):
        self._turn(120)
        with open(self._agent("unused-agent"), "rb") as handle:
            original = handle.read()
        code, value = self._json("--apply-all")
        self.assertEqual(code, 0, value)
        moved = {i["name"] for i in value["applied"]}
        self.assertIn("unused-agent", moved)
        self.assertNotIn("lane-foo", moved)
        self.assertFalse(os.path.exists(self._agent("unused-agent")))
        code, listed = self._json("--list")
        self.assertEqual(listed["manifests"][0]["stamp"], value["stamp"])
        self.assertIsNone(listed["manifests"][0]["restored_at"])
        code, out = self._run("--restore", "last")
        self.assertEqual(code, 0, out)
        with open(self._agent("unused-agent"), "rb") as handle:
            self.assertEqual(handle.read(), original)
        self.assertTrue(os.path.isfile(os.path.join(self._skill("unused-skill"), "SKILL.md")))
        code, listed = self._json("--list")
        self.assertIsNotNone(listed["manifests"][0]["restored_at"])
        code, value = self._json("--restore", value["stamp"])
        self.assertEqual(value["restored"], [])
        self.assertEqual(code, 0)

    def test_restore_refuses_to_overwrite_an_existing_path(self):
        self._turn(120)
        code, value = self._json("--apply", "unused-agent", "unused-skill")
        self.assertEqual(code, 0, value)
        self._text(self._agent("unused-agent"), "replacement\n")
        code, value = self._json("--restore")
        self.assertEqual(code, 1)
        self.assertEqual([c["name"] for c in value["conflicts"]], ["unused-agent"])
        self.assertEqual([r["name"] for r in value["restored"]], ["unused-skill"])
        with open(self._agent("unused-agent"), encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "replacement\n")
        stamp = value["stamp"]
        self.assertTrue(os.path.isfile(os.path.join(self.state, "pruned", stamp, "agent", "unused-agent.md")))
        self.assertFalse(value["fully_restored"])
        code, listed = self._json("--list")
        self.assertIsNone(listed["manifests"][0]["restored_at"])

    def test_restore_without_manifest_and_json_shapes(self):
        code, value = self._json("--restore")
        self.assertEqual(code, 1)
        self.assertEqual(value["mode"], "restore")
        code, value = self._json("--list")
        self.assertEqual(value, {"mode": "list", "manifests": []})


if __name__ == "__main__":
    unittest.main()
