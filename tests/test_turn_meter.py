import datetime as dt
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
METER = os.path.join(ROOT, "bin", "turn-meter")
STATUSLINE = os.path.join(ROOT, "bin", "claude-statusline")
UTC = dt.timezone.utc
_statusline_loader = importlib.machinery.SourceFileLoader("turn_meter_statusline_test", STATUSLINE)
_statusline_spec = importlib.util.spec_from_loader(_statusline_loader.name, _statusline_loader)
statusline = importlib.util.module_from_spec(_statusline_spec)
_statusline_loader.exec_module(statusline)
_meter_loader = importlib.machinery.SourceFileLoader("turn_meter_module_test", METER)
_meter_spec = importlib.util.spec_from_loader(_meter_loader.name, _meter_loader)
meter = importlib.util.module_from_spec(_meter_spec)
_meter_loader.exec_module(meter)


class TurnMeterTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="turn-meter-test-")
        self.state = os.path.join(self.root, "state")
        self.usage = os.path.join(self.root, "usage")
        self.cwd = os.path.join(self.root, "work")
        os.makedirs(self.cwd)
        os.makedirs(self.usage)
        os.makedirs(self.state)
        self.config = os.path.join(self.root, "config")
        os.makedirs(self.config)
        self.env = dict(os.environ)
        self.env.update({"LANES_STATE": self.state, "CLAUDE_USAGE_DIR": self.usage, "LANES_CONFIG": self.config,
                         "LANES_ARMS": os.path.join(ROOT, "arms.json"), "HOME": self.root,
                         "USERPROFILE": self.root, "NO_COLOR": "1", "USAGE_OPTIMIZER_CODEX": "off",
                         "USAGE_OPTIMIZER_KIT_LABEL": "off", "USAGE_OPTIMIZER_MODE_NOTICE": "off"})
        self.env.pop("CLAUDE_CONFIG_DIR", None)
        self.env.pop("USAGE_OPTIMIZER_MODE", None)
        self.env.pop("LANES_ARMS_LOCAL", None)
        # A cloud VM sets CLAUDE_CODE_REMOTE=true, which turns on cloud-only probes and defaults the tests do not expect.
        self.env.pop("CLAUDE_CODE_REMOTE", None)

    def tearDown(self):
        shutil.rmtree(self.root)

    def write_json(self, path, value):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(value, handle)

    def read_json(self, path):
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)

    def write_cost(self, session, cost):
        self.write_json(os.path.join(self.usage, "sessions", session + ".json"),
                        {"session_id": session, "total_cost_usd": cost, "observed_at": "2026-10-17T01:00:00Z",
                         "model": "sonnet"})

    def hook(self, event, session="session-1", **extra):
        value = {"hook_event_name": event, "session_id": session, "cwd": self.cwd}
        value.update(extra)
        result = subprocess.run([sys.executable, METER, "hook"], input=json.dumps(value), text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env,
                                cwd=self.cwd, timeout=10, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        return result

    def command(self, *args):
        return subprocess.run([sys.executable, METER, *args], text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, env=self.env, cwd=self.cwd, timeout=15, check=False)

    def ledger(self):
        path = os.path.join(self.state, "turns.jsonl")
        with open(path, encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def write_eta_history(self, count=3, ratio=1.3, session="history-session"):
        now = dt.datetime.now(UTC)
        rows = []
        for index in range(count):
            at = now - dt.timedelta(hours=index + 2)
            ended = at + dt.timedelta(minutes=10 * ratio)
            turn_id = "estimate-{}".format(index)
            rows.append({"type": "turn", "turn_id": turn_id, "session_id": session,
                         "started_at": self.stamp(ended - dt.timedelta(minutes=25)),
                         "ended_at": self.stamp(ended), "interrupted": False,
                         "cost_start_usd": 0, "cost_end_usd": 1})
            rows.append({"type": "eta", "turn_id": turn_id, "session_id": session,
                         "at": self.stamp(at), "elapsed_minutes": 10,
                         "remaining_minutes": 10, "note": "history"})
        with open(os.path.join(self.state, "turns.jsonl"), "w", encoding="utf-8") as handle:
            handle.write("".join(json.dumps(row) + "\n" for row in rows))

    def test_begin_and_stop_round_trip(self):
        self.write_cost("session-1", 1.0)
        self.write_json(os.path.join(self.usage, "claude-latest.json"), {
            "observed_at": "2026-10-17T01:00:00Z", "plan": "max",
            "five_hour": {"used_percentage": 12, "resets_at": "2026-10-17T05:00:00Z"},
            "seven_day": {"used_percentage": 20, "resets_at": "2026-10-20T00:00:00Z"}})
        self.write_json(os.path.join(self.usage, "codex-latest.json"), {
            "observed_at": "2026-10-17T01:00:00Z", "plan_type": "plus",
            "windows": [{"label": "5h", "used_percent": 5}, {"label": "weekly", "used_percent": 30,
                         "resets_at": "2026-10-20T00:00:00Z"}]})
        self.hook("UserPromptSubmit", prompt="hello   there\nfriend")
        opened = self.read_json(os.path.join(self.state, "turns", "open", "session-1.json"))
        self.assertEqual(opened["prompt_preview"], "hello there friend")
        self.assertEqual(opened["meters_start"]["claude"]["weekly_pct"], 20)
        self.assertEqual(opened["meters_start"]["codex"]["plan"], "plus")
        self.write_json(os.path.join(self.usage, "claude-latest.json"), {
            "observed_at": "2026-10-17T01:01:00Z", "plan": "max",
            "five_hour": {"used_percentage": 13, "resets_at": "2026-10-17T05:00:00Z"},
            "seven_day": {"used_percentage": 21, "resets_at": "2026-10-20T00:00:00Z"}})
        self.write_cost("session-1", 1.25)
        self.hook("Stop")
        turn = self.ledger()[0]
        self.assertEqual(turn["type"], "turn")
        self.assertEqual(turn["cost_start_usd"], 1.0)
        self.assertEqual(turn["cost_end_usd"], 1.25)
        self.assertFalse(turn["interrupted"])
        self.assertFalse(os.path.exists(os.path.join(self.state, "turns", "open", "session-1.json")))
        self.assertEqual(turn["meters"]["claude"]["before"]["weekly_pct"], 20)
        self.assertEqual(turn["meters"]["claude"]["after"]["weekly_pct"], 21)
        self.assertEqual(turn["meters"]["gemini"]["before"], None)
        self.assertEqual(set(turn["meters"]), {"claude", "codex", "gemini"})

    def test_new_prompt_closes_previous_turn_as_interrupted(self):
        self.write_cost("session-1", 0.4)
        self.hook("UserPromptSubmit", prompt="first prompt")
        self.write_cost("session-1", 0.6)
        self.hook("UserPromptSubmit", prompt="second prompt")
        rows = self.ledger()
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["interrupted"])
        self.assertEqual(rows[0]["prompt_preview"], "first prompt")
        opened = self.read_json(os.path.join(self.state, "turns", "open", "session-1.json"))
        self.assertEqual(opened["cost_start_usd"], 0.6)
        self.assertEqual(opened["prompt_preview"], "second prompt")

    def test_eta_records_ledger_and_merges_open_turn(self):
        started = dt.datetime.now(UTC) - dt.timedelta(minutes=1)
        self.write_json(os.path.join(self.state, "turns", "open", "session-1.json"), {
            "turn_id": "t-open", "session_id": "session-1", "started_at": self.stamp(started),
            "cwd": self.cwd, "prompt_preview": "keep me", "other": 7})
        text = self.command("eta", "25", "--note", "still working  on  it", "--session", "session-1")
        self.assertEqual(text.returncode, 0, text.stderr)
        self.assertEqual(text.stdout.strip(),
                         "eta recorded: ~25 min left (no calibration yet: fewer than 3 finished estimates)")
        result = self.command("eta", "25", "--note", "still working  on  it", "--session", "session-1", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        record = json.loads(result.stdout)
        self.assertEqual(record["type"], "eta")
        self.assertEqual(record["turn_id"], "t-open")
        self.assertEqual(record["remaining_minutes"], 25)
        self.assertEqual(record["note"], "still working on it")
        self.assertEqual(record["calibrated_minutes"], 25)
        self.assertAlmostEqual(record["elapsed_minutes"], round((dt.datetime.now(UTC) - started).total_seconds() / 60, 2), places=1)
        entries = self.ledger()
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[1], {key: value for key, value in record.items() if key != "calibrated_minutes"})
        opened = self.read_json(os.path.join(self.state, "turns", "open", "session-1.json"))
        self.assertEqual(opened["other"], 7)
        self.assertEqual(opened["prompt_preview"], "keep me")
        self.assertEqual(opened["eta"]["remaining_minutes"], 25)
        self.assertEqual(opened["eta"]["factor"], 1.0)

    def test_eta_without_open_turn_and_bad_minutes_exit_two(self):
        result = self.command("eta", "10")
        self.assertEqual(result.returncode, 2)
        self.assertIn("turn-meter: no open turn", result.stderr)
        self.assertEqual(self.command("eta", "-1").returncode, 2)
        self.assertEqual(self.command("eta", "not-a-number").returncode, 2)

    def test_time_calibration_needs_three_finished_estimates(self):
        self.write_eta_history(3, 1.3)
        calibrated = json.loads(self.command("calibrate", "--json").stdout)["time"]
        self.assertEqual(calibrated["source"], "calibrated")
        self.assertEqual(calibrated["n"], 3)
        self.assertAlmostEqual(calibrated["factor"], 1.3)
        self.assertAlmostEqual(calibrated["median_ratio"], 1.3)
        self.write_json(os.path.join(self.state, "turns", "open", "session-1.json"), {
            "turn_id": "t-calibrated", "session_id": "session-1",
            "started_at": self.stamp(dt.datetime.now(UTC) - dt.timedelta(minutes=2)), "cwd": self.cwd})
        eta_text = self.command("eta", "25", "--session", "session-1")
        self.assertIn("past estimates ran ×1.30 (n=3) → ~33 min", eta_text.stdout)

        self.write_eta_history(2, 1.3)
        uncalibrated = json.loads(self.command("calibrate", "--json").stdout)["time"]
        self.assertEqual(uncalibrated["source"], "none")
        self.assertEqual(uncalibrated["n"], 2)
        self.assertEqual(uncalibrated["factor"], 1.0)

    def test_time_calibration_skips_turns_that_handed_back_mid_task(self):
        # Turns that ended after a tenth of their estimate were split, not finished: they do not pull the factor down.
        self.write_eta_history(5, 0.1)
        split = json.loads(self.command("calibrate", "--json").stdout)["time"]
        self.assertEqual((split["source"], split["n"], split["factor"]), ("none", 0, 1.0))

    def test_current_uses_history_default_when_eight_turns_are_longer(self):
        now = dt.datetime.now(UTC)
        turns = []
        for index in range(8):
            end = now - dt.timedelta(hours=index + 1)
            duration = 10 + index
            turns.append({"type": "turn", "turn_id": "long-{}".format(index), "session_id": "old",
                          "started_at": self.stamp(end - dt.timedelta(minutes=duration)),
                          "ended_at": self.stamp(end), "interrupted": False})
        with open(os.path.join(self.state, "turns.jsonl"), "w", encoding="utf-8") as handle:
            handle.write("".join(json.dumps(turn) + "\n" for turn in turns))
        opened_at = now - dt.timedelta(minutes=3)
        self.write_json(os.path.join(self.state, "turns", "open", "session-1.json"), {
            "turn_id": "t-current", "session_id": "session-1", "started_at": self.stamp(opened_at),
            "cwd": self.cwd})
        result = self.command("current", "--session", "session-1", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)["turn"]["time"]
        self.assertEqual(value["remaining_source"], "history")
        self.assertEqual(set(value), {"turn_minutes", "session_minutes", "session_turns", "session_started_at",
                                      "remaining_minutes", "remaining_source", "estimate", "calibration",
                                      "lanes_in_flight"})
        self.assertAlmostEqual(value["remaining_minutes"], 10.5, delta=0.1)

    def test_current_time_text_estimate_overdue_and_lane_eta(self):
        now = dt.datetime.now(UTC)
        opened_at = now - dt.timedelta(minutes=30)
        closed = []
        for index in range(8):
            end = now - dt.timedelta(hours=index + 1)
            duration = 35 + index * 2
            closed.append({"type": "turn", "turn_id": "old-{}".format(index), "session_id": "session-1",
                           "started_at": self.stamp(end - dt.timedelta(minutes=duration)),
                           "ended_at": self.stamp(end), "interrupted": False})
        eta_at = now - dt.timedelta(minutes=10)
        rows = closed + [{"type": "eta", "turn_id": "t-current", "session_id": "session-1",
                          "at": self.stamp(eta_at), "elapsed_minutes": 20,
                          "remaining_minutes": 2, "note": "wrap up"}]
        with open(os.path.join(self.state, "turns.jsonl"), "w", encoding="utf-8") as handle:
            handle.write("".join(json.dumps(row) + "\n" for row in rows))
        self.write_json(os.path.join(self.state, "turns", "open", "session-1.json"), {
            "turn_id": "t-current", "session_id": "session-1", "started_at": self.stamp(opened_at),
            "cwd": self.cwd})
        text = self.command("current", "--session", "session-1").stdout
        self.assertIn("time: turn ", text)
        self.assertIn("history, n=8;", text)
        self.assertIn("past the estimate)", text)
        data = json.loads(self.command("current", "--session", "session-1", "--json").stdout)["turn"]["time"]
        self.assertEqual(data["remaining_source"], "history")
        self.assertAlmostEqual(data["estimate"]["over_minutes"], 8, delta=0.1)
        self.assertGreater(data["remaining_minutes"], 0)

        lane_started = now - dt.timedelta(minutes=1)
        self.write_json(os.path.join(self.state, "runs", "run-1", "meta.json"), {
            "lane": "luna", "effort": "xhigh", "class": "routine",
            "started_at": self.stamp(lane_started), "eta_s": 20 * 60})
        lane_value = json.loads(self.command("current", "--session", "session-1", "--json").stdout)["turn"]["time"]
        self.assertEqual(len(lane_value["lanes_in_flight"]), 1)
        self.assertAlmostEqual(lane_value["lanes_in_flight"][0]["eta_minutes"], 20)
        lane_text = self.command("current", "--session", "session-1").stdout
        self.assertIn("lanes in flight: luna xhigh 1.0/~20 min", lane_text)

    def test_current_uses_rule_default_when_history_is_too_short(self):
        started = dt.datetime.now(UTC) - dt.timedelta(minutes=4)
        self.write_json(os.path.join(self.state, "turns", "open", "session-1.json"), {
            "turn_id": "t-rule", "session_id": "session-1", "started_at": self.stamp(started),
            "cwd": self.cwd})
        value = json.loads(self.command("current", "--session", "session-1", "--json").stdout)["turn"]["time"]
        self.assertEqual(value["remaining_source"], "rule")
        self.assertAlmostEqual(value["remaining_minutes"], value["turn_minutes"], delta=0.01)

    def test_report_estimate_column_totals_and_session_grouping(self):
        self.write_eta_history(3, 1.3, session="session-a")
        result = self.command("report", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertAlmostEqual(value["turns"][0]["estimate_minutes"], 20)
        self.assertEqual(value["totals"]["estimates"], {"n": 3, "factor": 1.3})
        text = self.command("report").stdout
        self.assertIn("min    est", text)
        self.assertIn("estimates: n=3, actual/est ×1.30", text)

        sessions = self.command("report", "--by", "session", "--json")
        self.assertEqual(sessions.returncode, 0, sessions.stderr)
        grouped = json.loads(sessions.stdout)
        self.assertEqual(set(grouped), {"sessions", "totals", "calibration"})
        self.assertEqual(set(grouped["sessions"][0]), {
            "session_id", "started_local", "turns", "active_minutes", "span_hours", "list_usd",
            "estimated_claude_weekly_pct", "estimates"})
        self.assertEqual(grouped["sessions"][0]["turns"], 3)
        self.assertEqual(grouped["sessions"][0]["estimates"], 3)
        self.assertIn("session-a", self.command("report", "--by", "session").stdout)

    def test_calibrate_text_reports_time_accuracy(self):
        self.write_eta_history(3, 1.3)
        result = self.command("calibrate")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("time: Claude's estimates ran ×1.30 from 3 (median actual/estimate 1.30); current applies the factor",
                      result.stdout)
        self.write_eta_history(2, 1.3)
        result = self.command("calibrate")
        self.assertIn("time: fewer than 3 finished estimates", result.stdout)

    def test_stop_without_prompt_continues_last_turn(self):
        last = {"type": "turn", "turn_id": "t-old", "session_id": "session-1",
                "started_at": "2026-10-17T00:00:00Z", "ended_at": "2026-10-17T00:05:00Z",
                "cost_start_usd": 2.0, "cost_end_usd": 2.4,
                "meters": {provider: {"before": None, "after": None} for provider in ("claude", "codex", "gemini")}}
        self.write_json(os.path.join(self.state, "turns", "last", "session-1.json"), last)
        self.write_cost("session-1", 2.7)
        self.hook("Stop")
        turn = self.ledger()[0]
        self.assertEqual(turn["prompt_preview"], "(continued)")
        self.assertEqual(turn["started_at"], last["ended_at"])
        self.assertEqual(turn["cost_start_usd"], 2.4)
        self.assertEqual(turn["cost_end_usd"], 2.7)

    def test_prompt_settles_last_closed_turn(self):
        last = {"type": "turn", "turn_id": "t-last", "session_id": "session-1",
                "started_at": "2026-10-17T00:00:00Z", "ended_at": "2026-10-17T00:05:00Z",
                "cost_start_usd": 1.0, "cost_end_usd": 2.0}
        self.write_json(os.path.join(self.state, "turns", "last", "session-1.json"), last)
        self.write_cost("session-1", 2.5)
        with open(os.path.join(self.state, "turns.jsonl"), "w", encoding="utf-8") as handle:
            handle.write(json.dumps(last) + "\n")
        self.hook("UserPromptSubmit", prompt="next")
        rows = self.ledger()
        entry = rows[1]
        self.assertEqual(entry, {"type": "settle", "turn_id": "t-last", "cost_end_usd": 2.5,
                                 "settled_at": entry["settled_at"]})
        self.assertEqual(self.read_json(os.path.join(self.state, "turns", "last", "session-1.json"))["cost_end_usd"], 2.5)
        report = self.command("report", "--json")
        self.assertEqual(json.loads(report.stdout)["turns"][0]["list_usd"], 1.5)

    def test_malformed_hook_logs_and_off_switch_is_noop(self):
        result = subprocess.run([sys.executable, METER, "hook"], input="{bad", text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env, timeout=10)
        self.assertEqual((result.returncode, result.stdout), (0, ""))
        error_path = os.path.join(self.state, "turn-meter.err")
        with open(error_path, encoding="utf-8") as handle:
            self.assertIn("JSONDecodeError", handle.read())
        off_env = dict(self.env, USAGE_OPTIMIZER_TURNS="off")
        result = subprocess.run([sys.executable, METER, "hook"], input="{bad", text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=off_env, timeout=10)
        self.assertEqual((result.returncode, result.stdout), (0, ""))
        with open(error_path, encoding="utf-8") as handle:
            self.assertEqual(len(handle.readlines()), 1)

    def test_a_new_turn_records_sorted_history_without_interrupted_or_old_turns(self):
        now = dt.datetime.now(UTC)
        rows = [{"type": "turn", "turn_id": "h-day", "session_id": "history", "started_at": self.stamp(now - dt.timedelta(days=1, minutes=10)),
                 "ended_at": self.stamp(now - dt.timedelta(days=1)), "interrupted": False},
                {"type": "turn", "turn_id": "h-cut", "session_id": "history", "started_at": self.stamp(now - dt.timedelta(hours=1, minutes=99)),
                 "ended_at": self.stamp(now - dt.timedelta(hours=1)), "interrupted": True},
                {"type": "turn", "turn_id": "h-old", "session_id": "history", "started_at": self.stamp(now - dt.timedelta(days=70, minutes=88)),
                 "ended_at": self.stamp(now - dt.timedelta(days=70)), "interrupted": False}]
        with open(os.path.join(self.state, "turns.jsonl"), "w", encoding="utf-8") as handle:
            handle.write("".join(json.dumps(row) + "\n" for row in rows))
        self.hook("UserPromptSubmit", prompt="go")
        self.assertEqual(self.read_json(os.path.join(self.state, "turns", "open", "session-1.json"))["history_minutes"], [10.0])

    def test_history_keeps_the_500_most_recent_turns_sorted(self):
        now = dt.datetime.now(UTC)
        rows = []
        for index in range(510):
            # Turn index lasts index + 1 minutes; later index ended later.
            ended = now - dt.timedelta(minutes=510 - index)
            rows.append({"type": "turn", "turn_id": "h-{}".format(index), "session_id": "history",
                         "started_at": self.stamp(ended - dt.timedelta(minutes=index + 1)),
                         "ended_at": self.stamp(ended), "interrupted": False})
        with open(os.path.join(self.state, "turns.jsonl"), "w", encoding="utf-8") as handle:
            handle.write("".join(json.dumps(row) + "\n" for row in rows))
        self.hook("UserPromptSubmit", prompt="go")
        opened = self.read_json(os.path.join(self.state, "turns", "open", "session-1.json"))
        self.assertEqual(opened["history_minutes"], [float(minutes) for minutes in range(11, 511)])

    def test_a_broken_ledger_line_does_not_stop_the_hook(self):
        now = dt.datetime.now(UTC)
        good = {"type": "turn", "turn_id": "h-good", "session_id": "history", "started_at": self.stamp(now - dt.timedelta(days=1, minutes=10)),
                "ended_at": self.stamp(now - dt.timedelta(days=1)), "interrupted": False}
        with open(os.path.join(self.state, "turns.jsonl"), "w", encoding="utf-8") as handle:
            handle.write("{bad json\n[1, 2]\n" + json.dumps(good) + "\n" +
                         json.dumps({"type": "turn", "turn_id": "h-bad", "started_at": "nope", "ended_at": "nope"}) + "\n")
        self.hook("UserPromptSubmit", prompt="go")
        opened = self.read_json(os.path.join(self.state, "turns", "open", "session-1.json"))
        self.assertEqual(opened["history_minutes"], [10.0])
        self.assertFalse(os.path.exists(os.path.join(self.state, "turn-meter.err")))

    def test_a_new_turn_records_session_start_and_time_factor(self):
        now = dt.datetime.now(UTC)
        self.write_eta_history(3, 1.3)
        earlier = now - dt.timedelta(hours=3)
        row = {"type": "turn", "turn_id": "t-earlier", "session_id": "session-1", "started_at": self.stamp(earlier),
               "ended_at": self.stamp(earlier + dt.timedelta(minutes=7)), "interrupted": False}
        with open(os.path.join(self.state, "turns.jsonl"), "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")
        self.hook("UserPromptSubmit", prompt="next")
        opened = self.read_json(os.path.join(self.state, "turns", "open", "session-1.json"))
        self.assertEqual(opened["session_started_at"], earlier.replace(microsecond=0).isoformat().replace("+00:00", "Z"))
        self.assertAlmostEqual(opened["time_factor"], 1.3)
        self.assertEqual(opened["history_minutes"], [7.0, 25.0, 25.0, 25.0])

    def test_statusline_reads_the_eta_text_from_a_turn_the_hook_opened(self):
        self.write_cost("session-1", 1.0)
        rows = [{"type": "turn", "turn_id": "h-{}".format(index), "session_id": "history",
                 "started_at": self.stamp(dt.datetime.now(UTC) - dt.timedelta(days=1, minutes=index + 1)),
                 "ended_at": self.stamp(dt.datetime.now(UTC) - dt.timedelta(days=1)), "interrupted": False}
                for index in range(10, 510)]
        with open(os.path.join(self.state, "turns.jsonl"), "w", encoding="utf-8") as handle:
            handle.write("".join(json.dumps(row) + "\n" for row in rows))
        self.hook("UserPromptSubmit", prompt="go")
        with mock.patch.dict(os.environ, self.env, clear=True):
            text = statusline._turn_segment({"session_id": "session-1", "cost": {"total_cost_usd": 1.0}})
        # The history durations run 11 to 510 minutes; their median is 260.5, so the turn has about 261 minutes to go.
        self.assertRegex(text, r"^ETA ~4h21 ≈0\.00% wk$")

    def test_current_includes_lane_run_cost_and_weekly_delta(self):
        self.write_cost("session-1", 1.0)
        self.hook("UserPromptSubmit", prompt="inspect lane runs")
        self.write_cost("session-1", 1.5)
        runs_dir = os.path.join(self.state, "runs")
        started = dt.datetime.now(UTC).isoformat().replace("+00:00", "Z")
        for name, before, after, cost in (("a", 10, 12, 3.0), ("b", 11, 15, 2.0)):
            self.write_json(os.path.join(runs_dir, name, "meta.json"), {
                "lane": "sonnet", "provider": "claude", "started_at": started, "ended_at": started,
                "usage": {"list_usd": cost,
                          "before": {"windows": [{"label": "weekly", "used_percent": before}]},
                          "after": {"windows": [{"label": "weekly", "used_percent": after}]}}})
        result = self.command("current", "--session", "session-1", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)["turn"]
        self.assertAlmostEqual(value["cost_so_far_usd"], 0.5)
        self.assertEqual(value["lane_runs"]["claude"]["count"], 2)
        self.assertEqual(value["lane_runs"]["claude"]["list_usd"], 5.0)
        self.assertEqual(value["lane_runs"]["claude"]["weekly_delta_pct"], 5)

    def plan_catalog(self, prices=True, **claude):
        # A catalog of the test's own: 0.05% of Claude's week per $1, and, with prices, Max 20x at $200 a month.
        settings = {"prior_pct_per_usd": 0.05, "prior_plan": "max_20x"}
        if prices:
            settings["plan_prices"] = {"max_20x": {"usd_per_month": 200, "source": "test", "checked": "2026-10-31"},
                                       "max_5x": {"usd_per_month": 100, "source": "test", "checked": "2026-10-31"}}
        settings.update(claude)
        path = os.path.join(self.root, "arms.json")
        self.write_json(path, {"providers": {"claude": settings}, "explore": {"weeks_per_month": 4.345}})
        self.env["LANES_ARMS"] = path

    def test_current_shows_plan_dollars_only_with_a_plan_price(self):
        self.write_cost("session-1", 1.0)
        self.hook("UserPromptSubmit", prompt="price this turn")
        self.write_cost("session-1", 3.0)
        self.plan_catalog()
        value = json.loads(self.command("current", "--session", "session-1", "--json").stdout)["turn"]
        self.assertAlmostEqual(value["estimated_claude_weekly_pct"], 0.1)
        # 0.1% of the week x $200 a month / 4.345 weeks a month.
        self.assertAlmostEqual(value["estimated_plan_usd"], 0.001 * 200 / 4.345)
        self.assertEqual(value["plan_price"]["plan"], "max_20x")
        first = self.command("current", "--session", "session-1").stdout.splitlines()[0]
        self.assertRegex(first, r" min \| list \$2\.00 \| est Claude wk ≈0\.10% \| ≈\$0\.05 of plan \(max_20x, \$200/mo\)$")

        # arms.local.json names the plan this machine is on, as lane-stats reads it.
        self.write_json(os.path.join(self.root, ".config", "lanes", "arms.local.json"),
                        {"providers": {"claude": {"prior_plan": "max_5x"}}})
        value = json.loads(self.command("current", "--session", "session-1", "--json").stdout)["turn"]
        self.assertAlmostEqual(value["estimated_plan_usd"], 0.001 * 100 / 4.345)
        os.remove(os.path.join(self.root, ".config", "lanes", "arms.local.json"))

        self.hook("Stop")
        report = json.loads(self.command("report", "--json").stdout)["totals"]
        self.assertAlmostEqual(report["estimated_plan_usd"], 0.001 * 200 / 4.345)
        self.assertTrue(self.command("report").stdout.rstrip().endswith("| ≈$0.05 of plan (max_20x, $200/mo)"))

        for catalog in ({"prices": False}, {"prior_plan": "pro"}):
            self.plan_catalog(**catalog)
            self.assertNotIn("estimated_plan_usd", json.loads(self.command("report", "--json").stdout)["totals"])
            self.assertNotIn("of plan", self.command("report").stdout)
        self.write_cost("session-1", 3.0)
        self.hook("UserPromptSubmit", prompt="no price")
        self.write_cost("session-1", 4.0)
        value = json.loads(self.command("current", "--session", "session-1", "--json").stdout)["turn"]
        self.assertNotIn("estimated_plan_usd", value)
        self.assertNotIn("plan_price", value)
        self.assertNotIn("of plan", self.command("current", "--session", "session-1").stdout)

    def subagent_run(self, name, parent, cost):
        when = dt.datetime.now(UTC).isoformat().replace("+00:00", "Z")
        self.write_json(os.path.join(self.state, "runs", name, "meta.json"), {
            "lane": "sonnet", "provider": "claude", "place": "subagent", "started_at": when, "ended_at": when,
            "subagent": {"parent_session_id": parent}, "usage": {"list_usd": cost}})

    def test_subagent_spend_is_separated_from_the_turn_cost(self):
        self.write_cost("session-1", 0.25)
        self.hook("UserPromptSubmit", prompt="use a worker")
        self.subagent_run("sub-a", "session-1", 0.40)
        self.subagent_run("sub-b", "other-session", 0.30)
        self.write_cost("session-1", 1.0)
        current = json.loads(self.command("current", "--session", "session-1", "--json").stdout)["turn"]
        self.assertAlmostEqual(current["cost_so_far_usd"], 0.35)
        self.assertEqual(current["subagents"], {"count": 1, "list_usd": 0.40})
        self.assertIn("claude subagents 1 runs $0.40", self.command("current", "--session", "session-1").stdout)
        self.hook("Stop")
        report = json.loads(self.command("report", "--json").stdout)
        self.assertAlmostEqual(report["turns"][0]["list_usd"], 0.35)
        self.assertEqual(report["turns"][0]["lane_runs"], {})
        self.assertIn("claude subagents 1 runs $0.40", self.command("report").stdout)

    def test_subagent_run_spanning_two_turns_is_split_by_time(self):
        # A background run launched at 10:05 that ends at 10:25 spends a quarter of its time in each turn.
        base = dt.datetime(2026, 10, 20, 10, 0, tzinfo=UTC)
        minutes = lambda value: base + dt.timedelta(minutes=value)
        self.write_turns((minutes(0), minutes(10), 1.0), (minutes(20), minutes(30), 1.0))
        self.write_json(os.path.join(self.state, "runs", "sub-span", "meta.json"), {
            "lane": "haiku", "provider": "claude", "place": "subagent",
            "started_at": self.stamp(minutes(5)), "ended_at": self.stamp(minutes(25)),
            "subagent": {"parent_session_id": "s"}, "usage": {"list_usd": 0.8}})
        rows = json.loads(self.command("report", "--json").stdout)["turns"]
        self.assertEqual([row["subagents"] for row in rows], [{"count": 1, "list_usd": 0.2}] * 2)
        self.assertEqual([round(row["list_usd"], 6) for row in rows], [0.8, 0.8])

    def test_subagent_run_of_another_session_changes_nothing(self):
        self.write_cost("session-1", 0.25)
        self.hook("UserPromptSubmit", prompt="no worker")
        self.subagent_run("sub-b", "other-session", 0.30)
        self.write_cost("session-1", 1.0)
        self.hook("Stop")
        row = json.loads(self.command("report", "--json").stdout)["turns"][0]
        self.assertEqual(row["list_usd"], 0.75)
        self.assertNotIn("subagents", row)

    def test_report_rows_include_turn_cost_and_lane_runs(self):
        self.write_cost("session-1", 0.25)
        self.hook("UserPromptSubmit", prompt="report this test turn with some details")
        self.write_cost("session-1", 1.0)
        self.hook("Stop")
        result = self.command("report", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(len(value["turns"]), 1)
        self.assertEqual(value["turns"][0]["list_usd"], 0.75)
        self.assertEqual(value["turns"][0]["prompt_preview"], "report this test turn with some details")
        self.assertEqual(value["totals"]["turns"], 1)

    def test_calibrate_uses_window_rise_over_turn_spend(self):
        now = dt.datetime.now(UTC)
        first = now - dt.timedelta(hours=20)
        second = now - dt.timedelta(hours=10)
        reset = (now + dt.timedelta(days=5)).isoformat().replace("+00:00", "Z")
        rate_path = os.path.join(self.usage, "claude-rate.jsonl")
        with open(rate_path, "w", encoding="utf-8") as handle:
            # The reading before the first recorded turn has no matching spend and must not count.
            for stamp, percent in ((now - dt.timedelta(hours=30), 2), (first, 10), (second, 16)):
                handle.write(json.dumps({"observed_at": stamp.isoformat().replace("+00:00", "Z"),
                                         "seven_day": {"used_percentage": percent, "resets_at": reset}}) + "\n")
        started = (now - dt.timedelta(hours=21)).isoformat().replace("+00:00", "Z")
        ended = (now - dt.timedelta(hours=15)).isoformat().replace("+00:00", "Z")
        turn = {"type": "turn", "turn_id": "t-spend", "session_id": "s", "started_at": started,
                "ended_at": ended, "cost_start_usd": 0, "cost_end_usd": 150}
        with open(os.path.join(self.state, "turns.jsonl"), "w", encoding="utf-8") as handle:
            handle.write(json.dumps(turn) + "\n")
        result = self.command("calibrate", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertAlmostEqual(value["pct_per_usd"], 0.04)
        self.assertEqual(value["windows"], 1)
        self.assertEqual(value["spend_usd"], 150)
        self.assertEqual(value["rise_pct"], 6)
        self.assertAlmostEqual(self.read_json(os.path.join(self.state, "claude-calibration.json"))["pct_per_usd"], 0.04)

    def stamp(self, value):
        return value.isoformat().replace("+00:00", "Z")

    def write_readings(self, reset, readings):
        with open(os.path.join(self.usage, "claude-rate.jsonl"), "w", encoding="utf-8") as handle:
            for observed, percent in readings:
                handle.write(json.dumps({"observed_at": self.stamp(observed),
                                         "seven_day": {"used_percentage": percent, "resets_at": self.stamp(reset)}}) + "\n")

    def write_turns(self, *spans):
        with open(os.path.join(self.state, "turns.jsonl"), "w", encoding="utf-8") as handle:
            for index, (started, ended, cost) in enumerate(spans):
                handle.write(json.dumps({"type": "turn", "turn_id": "t-{}".format(index), "session_id": "s",
                                         "started_at": self.stamp(started), "ended_at": self.stamp(ended),
                                         "cost_start_usd": 0, "cost_end_usd": cost}) + "\n")

    def calibrate(self):
        result = self.command("calibrate", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_calibrate_starts_each_week_at_its_own_first_turn(self):
        # 2026-10-22: a turn the week before made the whole of this week's rise count against one day's spend.
        now = dt.datetime.now(UTC)
        hours = lambda value: now - dt.timedelta(hours=value)
        self.write_readings(now + dt.timedelta(days=3), ((hours(95), 0), (hours(10), 40), (hours(8.5), 42), (hours(7), 45)))
        self.write_turns((hours(216), hours(215), 10), (hours(9), hours(7.5), 50))
        value = self.calibrate()
        self.assertEqual(value["source"], "calibrated")
        self.assertEqual(value["rise_pct"], 3)
        self.assertEqual(value["spend_usd"], 50)
        self.assertAlmostEqual(value["pct_per_usd"], 0.06)

    def test_calibrate_skips_rise_between_readings_with_no_recorded_activity(self):
        now = dt.datetime.now(UTC)
        hours = lambda value: now - dt.timedelta(hours=value)
        # 12 → 35 happened while no turn here was running (another device, or a session without the hooks).
        self.write_readings(now + dt.timedelta(days=5), ((hours(29.9), 10), (hours(29), 12), (hours(20), 30),
                                                         (hours(12), 35), (hours(4.9), 36), (hours(4), 38)))
        self.write_turns((hours(30), hours(29), 40), (hours(5), hours(4), 40))
        value = self.calibrate()
        self.assertEqual(value["rise_pct"], 5)
        self.assertEqual(value["spend_usd"], 80)
        self.assertAlmostEqual(value["pct_per_usd"], 0.0625)

    def test_calibrate_rejects_implausible_rate_and_removes_stale_file(self):
        now = dt.datetime.now(UTC)
        hours = lambda value: now - dt.timedelta(hours=value)
        path = os.path.join(self.state, "claude-calibration.json")
        self.write_json(path, {"pct_per_usd": 0.95, "windows": 1, "updated_at": "2026-10-22T14:07:28Z"})
        self.write_readings(now + dt.timedelta(days=5), ((hours(10), 10), (hours(9), 40)))
        self.write_turns((hours(10.5), hours(9.5), 10))
        value = self.calibrate()
        self.assertEqual(value["source"], "prior")
        self.assertAlmostEqual(value["pct_per_usd"], self.read_json(os.path.join(ROOT, "arms.json"))
                               ["providers"]["claude"]["prior_pct_per_usd"])
        self.assertAlmostEqual(value["rejected_pct_per_usd"], 3.0)
        self.assertFalse(os.path.exists(path))
        text = self.command("calibrate").stdout
        self.assertIn("rejected 3.000000% per $1", text)

    def test_calibrate_falls_back_to_catalog_prior_without_writing(self):
        catalog = os.path.join(self.root, "arms.json")
        self.write_json(catalog, {"providers": {"claude": {"prior_pct_per_usd": 0.031}}})
        self.env["LANES_ARMS"] = catalog
        result = self.command("calibrate", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value["source"], "prior")
        self.assertEqual(value["pct_per_usd"], 0.031)
        self.assertFalse(os.path.exists(os.path.join(self.state, "claude-calibration.json")))

    def test_statusline_writes_session_cost_only_when_changed_and_shows_turn(self):
        self.write_json(os.path.join(self.state, "turns", "open", "session-1.json"),
                        {"session_id": "session-1", "cost_start_usd": 1.0})
        self.write_json(os.path.join(self.state, "claude-calibration.json"), {"pct_per_usd": 0.04})
        os.makedirs(os.path.join(self.usage, "sessions"), exist_ok=True)
        incoming = {"session_id": "session-1", "model": "claude-sonnet", "cost": {"total_cost_usd": 2.0}}
        def run_statusline(data, env=None):
            output = io.StringIO()
            with mock.patch.dict(os.environ, env or self.env, clear=True):
                with mock.patch("sys.stdin", io.StringIO(json.dumps(data))), contextlib.redirect_stdout(output):
                    statusline.main()
            return output.getvalue()
        first = run_statusline(incoming)
        self.assertIn("0.04% wk", first.splitlines()[0])
        narrow_env = dict(self.env, COLUMNS="14")
        narrow = run_statusline(incoming, narrow_env)
        self.assertNotIn("turn", narrow.splitlines()[0])
        off_env = dict(self.env, USAGE_OPTIMIZER_TURNS="off")
        hidden = run_statusline(incoming, off_env)
        self.assertNotIn("turn", hidden.splitlines()[0])
        path = os.path.join(self.usage, "sessions", "session-1.json")
        saved = self.read_json(path)
        self.assertEqual(saved["total_cost_usd"], 2.0)
        with open(path, encoding="utf-8") as handle:
            same_cost_content = handle.read()
        changed_model = dict(incoming, model="claude-opus")
        second = run_statusline(changed_model)
        with open(path, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), same_cost_content)
        incoming["cost"]["total_cost_usd"] = 2.1
        third = run_statusline(incoming)
        self.assertEqual(self.read_json(path)["total_cost_usd"], 2.1)


class TranscriptCostTests(unittest.TestCase):
    # A cloud session has no statusline, so its cost is priced from its transcripts at the catalog's prices.
    # The prices are the test's own, in dollars per million tokens, so every expected cost is worked out by hand.
    PRICES = {"claude-test-1": {"input": 1, "output": 5, "cache_read": 0.5, "cache_write_5m": 2, "cache_write_1h": 4,
                                "long_context": {"above_prompt_tokens": 100000, "input": 2, "output": 10,
                                                 "cache_read": 1, "cache_write_5m": 4, "cache_write_1h": 8}}}

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="turn-meter-transcript-test-")
        self.state = os.path.join(self.root, "state")
        self.usage = os.path.join(self.root, "usage")
        self.cwd = os.path.join(self.root, "work")
        self.config = os.path.join(self.root, "claude-config")
        self.projects = os.path.join(self.config, "projects")
        for path in (self.state, self.usage, self.cwd, self.projects):
            os.makedirs(path)
        self.arms = os.path.join(self.root, "arms.json")
        self.write_json(self.arms, {"providers": {"claude": {"prices": self.PRICES}}})
        self.env = dict(os.environ)
        self.env.update({"LANES_STATE": self.state, "CLAUDE_USAGE_DIR": self.usage, "CLAUDE_CONFIG_DIR": self.config,
                         "LANES_ARMS": self.arms, "LANES_CONFIG": os.path.join(self.root, "config"),
                         "HOME": self.root, "USERPROFILE": self.root, "NO_COLOR": "1",
                         "USAGE_OPTIMIZER_CODEX": "off", "USAGE_OPTIMIZER_KIT_LABEL": "off",
                         "USAGE_OPTIMIZER_MODE_NOTICE": "off"})
        for name in ("CLAUDE_CODE_REMOTE", "USAGE_OPTIMIZER_MODE", "LANES_ARMS_LOCAL"):
            self.env.pop(name, None)

    def tearDown(self):
        shutil.rmtree(self.root)

    def write_json(self, path, value):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(value, handle)

    def read_json(self, path):
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)

    def write_cost(self, session, cost):
        self.write_json(os.path.join(self.usage, "sessions", session + ".json"),
                        {"session_id": session, "total_cost_usd": cost, "observed_at": "2026-10-17T01:00:00Z"})

    def transcript(self, *parts):
        return os.path.join(self.projects, *parts)

    def write_lines(self, path, entries, append=False):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a" if append else "w", encoding="utf-8") as handle:
            handle.write("".join(json.dumps(entry) + "\n" for entry in entries))

    def response(self, identity, model, **usage):
        # One assistant entry as Claude Code writes it; the usage keys are the API's.
        return {"type": "assistant", "message": {"id": identity, "model": model, "usage": usage}}

    def hook(self, event, session="session-1", **extra):
        value = {"hook_event_name": event, "session_id": session, "cwd": self.cwd}
        value.update(extra)
        result = subprocess.run([sys.executable, METER, "hook"], input=json.dumps(value), text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env,
                                cwd=self.cwd, timeout=10, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def command(self, *args):
        return subprocess.run([sys.executable, METER, *args], text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, env=self.env, cwd=self.cwd, timeout=15, check=False)

    def ledger(self):
        with open(os.path.join(self.state, "turns.jsonl"), encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def session_cost(self, session="session-1"):
        with mock.patch.dict(os.environ, self.env, clear=True):
            return meter._session_cost_info(session)

    def test_fallback_prices_main_and_subagent_transcripts_once_per_message_id(self):
        cache_creation = {"ephemeral_5m_input_tokens": 500, "ephemeral_1h_input_tokens": 200}
        self.write_lines(self.transcript("-work", "session-1.jsonl"), [
            {"type": "user", "message": {"role": "user", "content": "hello"}},
            # One API response written as two entries: the later entry carries the final output count.
            self.response("msg-1", "claude-test-1", input_tokens=1000, output_tokens=1, cache_read_input_tokens=2000,
                          cache_creation=cache_creation),
            self.response("msg-1", "claude-test-1", input_tokens=1000, output_tokens=300,
                          cache_read_input_tokens=2000, cache_creation=cache_creation),
            # A dated id takes its family's price; without a cache_creation object its writes are 5m.
            self.response("msg-2", "claude-test-1-20261001", input_tokens=200, output_tokens=50,
                          cache_creation_input_tokens=400),
        ])
        self.write_lines(self.transcript("-work", "session-1", "subagents", "agent-a1.jsonl"),
                         [self.response("msg-3", "claude-test-1", input_tokens=3000, output_tokens=1000)])
        # Neither of these counts: not an agent-*.jsonl of this session, and a session of another root.
        self.write_lines(self.transcript("-work", "session-1", "subagents", "notes.jsonl"),
                         [self.response("msg-7", "claude-test-1", output_tokens=10 ** 6)])
        self.write_lines(os.path.join(self.root, ".claude", "projects", "-work", "session-1.jsonl"),
                         [self.response("msg-8", "claude-test-1", output_tokens=10 ** 6)])
        # By hand, in dollars per million tokens. msg-1: 1000x1 + 300x5 + 2000x0.5 + 500x2 + 200x4 = 5300, which is
        # $0.0053. msg-2: 200x1 + 50x5 + 400x2 = 1250, which is $0.00125. msg-3: 3000x1 + 1000x5 = 8000, $0.008.
        cost, source = self.session_cost()
        self.assertEqual(source, "transcript")
        self.assertAlmostEqual(cost, 0.0053 + 0.00125 + 0.008)

    def test_statusline_cost_is_used_unchanged_and_transcripts_are_not_read(self):
        self.write_lines(self.transcript("-work", "session-1.jsonl"),
                         [self.response("msg-1", "claude-test-1", output_tokens=1000)])
        self.write_cost("session-1", 2.5)
        self.assertEqual(self.session_cost(), (2.5, "statusline"))
        self.hook("UserPromptSubmit", prompt="statusline turn")
        self.hook("Stop")
        turn = self.ledger()[0]
        self.assertEqual((turn["cost_start_usd"], turn["cost_end_usd"]), (2.5, 2.5))
        self.assertNotIn("cost_source", turn)
        self.assertFalse(os.path.exists(os.path.join(self.state, meter.TRANSCRIPT_COST_DIR)))

    def test_a_model_without_a_price_makes_the_session_unknown_not_partial(self):
        self.write_lines(self.transcript("-work", "session-1.jsonl"), [
            self.response("msg-1", "claude-test-1", output_tokens=250),
            self.response("msg-2", "claude-mystery-9", output_tokens=250)])
        self.assertEqual(self.session_cost(), (None, None))
        self.hook("UserPromptSubmit", prompt="unpriced model")
        first = self.command("current", "--session", "session-1").stdout.splitlines()[0]
        self.assertIn("list unknown", first)

    def test_synthetic_entries_are_skipped(self):
        # The <synthetic> entry has no price and far more tokens than the priced response: counting it would fail.
        self.write_lines(self.transcript("-work", "session-1.jsonl"), [
            self.response("msg-1", "<synthetic>", input_tokens=999999, output_tokens=999999),
            self.response("msg-2", "claude-test-1", output_tokens=50000)])
        self.assertEqual(self.session_cost(), (0.25, "transcript"))

    def test_current_and_the_turn_record_show_a_transcript_priced_turn(self):
        main = self.transcript("-work", "session-1.jsonl")
        # $0.00125 is the session's cost when the prompt is submitted; the turn then adds $0.25.
        self.write_lines(main, [self.response("msg-1", "claude-test-1", output_tokens=250)])
        self.hook("UserPromptSubmit", prompt="priced from transcripts")
        self.write_lines(main, [self.response("msg-2", "claude-test-1", output_tokens=50000)], append=True)
        first = self.command("current", "--session", "session-1").stdout.splitlines()[0]
        self.assertRegex(first, r" min \| list \$0\.25 \(transcript\) \| est Claude wk ")
        value = json.loads(self.command("current", "--session", "session-1", "--json").stdout)["turn"]
        self.assertEqual(value["cost_source"], "transcript")
        self.assertAlmostEqual(value["cost_so_far_usd"], 0.25)
        self.hook("Stop")
        turn = self.ledger()[0]
        self.assertEqual(turn["cost_source"], "transcript")
        self.assertAlmostEqual(turn["cost_start_usd"], 0.00125)
        self.assertAlmostEqual(turn["cost_end_usd"], 0.25125)
        self.assertEqual(turn["session_id"], "session-1")

    def test_transcript_costs_are_cached_until_the_file_changes(self):
        main = self.transcript("-work", "session-1.jsonl")
        self.write_lines(main, [self.response("msg-1", "claude-test-1", output_tokens=250)])
        self.write_lines(self.transcript("-work", "session-1", "subagents", "agent-a1.jsonl"),
                         [self.response("msg-2", "claude-test-1", output_tokens=1000)])
        self.assertAlmostEqual(self.session_cost()[0], 0.00125 + 0.005)
        cache_dir = os.path.join(self.state, meter.TRANSCRIPT_COST_DIR)
        caches = [os.path.join(cache_dir, name) for name in os.listdir(cache_dir)]
        self.assertEqual(len(caches), 2)
        # The size and mtime are unchanged, so the cached records are used: emptying the main file's cache takes
        # its $0.00125 out of the cost.
        for path in caches:
            value = self.read_json(path)
            if value["path"] == main:
                value["records"] = []
            self.write_json(path, value)
        self.assertAlmostEqual(self.session_cost()[0], 0.005)
        # A transcript that grew has a new size, so it is read again: msg-3 adds 100 output tokens, $0.0005.
        self.write_lines(main, [self.response("msg-3", "claude-test-1", output_tokens=100)], append=True)
        self.assertAlmostEqual(self.session_cost()[0], 0.00125 + 0.0005 + 0.005)
        # An unreadable cache is a miss: the transcripts are priced again, and the cache is written again.
        for path in caches:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{not json")
        self.assertAlmostEqual(self.session_cost()[0], 0.00125 + 0.0005 + 0.005)
        rewritten = [self.read_json(path) for path in caches]
        main_cache = next(value for value in rewritten if value["path"] == main)
        self.assertEqual(main_cache["size"], os.path.getsize(main))
        self.assertEqual(len(main_cache["records"]), 2)

    def test_projects_root_is_claude_config_dir_or_home_claude(self):
        self.write_lines(self.transcript("-work", "session-1.jsonl"),
                         [self.response("msg-1", "claude-test-1", output_tokens=1000)])
        self.write_lines(os.path.join(self.root, ".claude", "projects", "-work", "session-1.jsonl"),
                         [self.response("msg-1", "claude-test-1", output_tokens=20000)])
        self.assertAlmostEqual(self.session_cost()[0], 0.005)
        self.env.pop("CLAUDE_CONFIG_DIR")
        self.assertAlmostEqual(self.session_cost()[0], 0.1)

    def test_long_context_rates_apply_above_the_prompt_threshold(self):
        price = self.PRICES["claude-test-1"]
        # 200,000 prompt tokens are above 100,000, so the long-context rates: 200,000x2 + 10x10 = 400,100, $0.4001.
        self.assertAlmostEqual(meter._message_usd(price, (200000, 10, 0, 0, 0)), 0.4001)
        # 50,000 prompt tokens are not: 50,000x1 + 100x5 = 50,500, $0.0505.
        self.assertAlmostEqual(meter._message_usd(price, (50000, 100, 0, 0, 0)), 0.0505)

    def test_a_local_price_override_is_merged_over_the_catalog(self):
        # arms.local.json prices override the catalog's, as in lane and lane-stats.
        local = os.path.join(self.root, "arms.local.json")
        self.write_json(local, {"providers": {"claude": {"prices": {"claude-test-1": dict(
            self.PRICES["claude-test-1"], output=50)}}}})
        self.env["LANES_ARMS_LOCAL"] = local
        self.write_lines(self.transcript("-work", "session-1.jsonl"),
                         [self.response("msg-1", "claude-test-1", output_tokens=1000)])
        cost, source = self.session_cost()
        self.assertEqual(source, "transcript")
        self.assertAlmostEqual(cost, 0.05)

    def test_a_transcript_that_cannot_be_priced_leaves_the_cost_unknown_and_keeps_the_turn(self):
        # An absurd token count overflows the float sum; the hook must still open and close its turn.
        self.write_lines(self.transcript("-work", "session-1.jsonl"),
                         [self.response("msg-1", "claude-test-1", output_tokens=10 ** 400)])
        self.assertEqual(self.session_cost(), (None, None))
        self.hook("UserPromptSubmit", prompt="bad transcript")
        self.hook("Stop")
        turn = self.ledger()[0]
        self.assertIsNone(turn["cost_end_usd"])
        self.assertNotIn("cost_source", turn)


class CompactionTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="turn-meter-compaction-test-")
        self.state = os.path.join(self.root, "state")
        self.usage = os.path.join(self.root, "usage")
        self.cwd = os.path.join(self.root, "work")
        os.makedirs(self.state)
        os.makedirs(self.usage)
        os.makedirs(self.cwd)
        self.config = os.path.join(self.root, "config")
        os.makedirs(self.config)
        self.env = dict(os.environ, LANES_STATE=self.state, CLAUDE_USAGE_DIR=self.usage, LANES_CONFIG=self.config,
                        HOME=self.root, USERPROFILE=self.root, NO_COLOR="1", USAGE_OPTIMIZER_MODE_NOTICE="off")
        self.env.pop("USAGE_OPTIMIZER_MODE", None)
        self.env.pop("CLAUDE_CODE_REMOTE", None)

    def tearDown(self):
        shutil.rmtree(self.root)

    def command(self, *args, input_text=None, env=None):
        return subprocess.run([sys.executable, METER, *args], input=input_text, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=env or self.env, cwd=self.cwd, timeout=15, check=False)

    def write_json(self, path, value):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(value, handle)

    def transcript(self, name, usage=100, ending="assistant"):
        path = os.path.join(self.root, name + ".jsonl")
        prompt = {"type": "user", "message": {"content": [{"type": "text", "text": "do this"}]}}
        assistant = {"type": "assistant", "message": {
            "usage": {"input_tokens": usage, "cache_read_input_tokens": 0,
                      "cache_creation_input_tokens": 0, "output_tokens": 0}, "content": []}}
        entries = [prompt, assistant]
        if ending == "prompt":
            entries.append({"type": "user", "message": {"content": "next turn prompt"}})
        elif ending == "tool":
            entries.append({"type": "user", "message": {"content": [
                {"type": "tool_result", "content": "x" * 1200000}]}})
        with open(path, "w", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(json.dumps(entry) + "\n")
        return path

    def gate(self, path=None, session="session-1", trigger="auto", env=None, raw=None):
        event = {"session_id": session, "trigger": trigger}
        if path is not None:
            event["transcript_path"] = path
        payload = raw if raw is not None else json.dumps(event)
        return self.command("compact-gate", input_text=payload, env=env)

    def compaction_rows(self):
        path = os.path.join(self.state, "compactions.jsonl")
        with open(path, encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def test_gate_blocks_mid_turn_below_ceiling_and_logs_decision(self):
        result = self.gate(self.transcript("below", usage=100))
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value["decision"], "block")
        self.assertIn("context ~0.1k of the 350k ceiling", value["reason"])
        row = self.compaction_rows()[0]
        self.assertEqual((row["type"], row["mid_turn"], row["decision"]), ("gate", True, "block"))
        self.assertEqual(row["session_id"], "session-1")

    def test_gate_allows_at_or_above_ceiling_and_at_turn_start(self):
        above = self.gate(self.transcript("above", usage=350000), session="above")
        self.assertEqual((above.returncode, above.stdout), (0, ""))
        start = self.gate(self.transcript("start", usage=100, ending="prompt"), session="start")
        self.assertEqual((start.returncode, start.stdout), (0, ""))
        rows = self.compaction_rows()
        self.assertEqual([row["decision"] for row in rows], ["allow", "allow"])
        self.assertEqual([row["mid_turn"] for row in rows], [True, False])

    def test_gate_counts_pending_tool_results_in_estimate(self):
        path = self.transcript("pending-tools", usage=100, ending="tool")
        env = dict(self.env, USAGE_OPTIMIZER_COMPACT_HARD="250000")
        result = self.gate(path, env=env)
        self.assertEqual((result.returncode, result.stdout), (0, ""))
        row = self.compaction_rows()[0]
        self.assertGreaterEqual(row["estimate"], 250000)
        self.assertEqual(row["decision"], "allow")

    def test_gate_allows_manual_trigger_and_gate_off_without_reading_transcript(self):
        manual = self.gate(trigger="manual", session="manual")
        off = self.gate(trigger="auto", session="off", env=dict(self.env, USAGE_OPTIMIZER_COMPACT_GATE="off"))
        self.assertEqual((manual.returncode, manual.stdout), (0, ""))
        self.assertEqual((off.returncode, off.stdout), (0, ""))
        self.assertEqual([row["decision"] for row in self.compaction_rows()], ["allow", "allow"])

    def test_cloud_default_allows_but_explicit_on_keeps_gate(self):
        remote = dict(self.env, CLAUDE_CODE_REMOTE="true")
        allowed = self.gate(session="cloud-default", env=remote)
        self.assertEqual((allowed.returncode, allowed.stdout), (0, ""))
        row = self.compaction_rows()[0]
        self.assertEqual((row["decision"], row["cloud"], row["estimate"]), ("allow", True, None))
        gated = self.gate(self.transcript("cloud-on", usage=100), session="cloud-on",
                          env=dict(remote, USAGE_OPTIMIZER_COMPACT_GATE="on"))
        self.assertEqual(json.loads(gated.stdout)["decision"], "block")
        self.assertTrue(self.compaction_rows()[1]["cloud"])

    def test_local_default_still_keeps_gate(self):
        result = self.gate(self.transcript("local-default", usage=100))
        self.assertEqual(json.loads(result.stdout)["decision"], "block")
        self.assertFalse(self.compaction_rows()[0]["cloud"])

    def test_gate_garbage_fails_open_without_output(self):
        result = self.gate(raw="not json")
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))
        with open(os.path.join(self.state, "turn-meter.err"), encoding="utf-8") as handle:
            self.assertIn("JSONDecodeError", handle.read())

    def test_resume_context_lists_in_flight_pending_review_and_eta_but_not_reviewed(self):
        now = dt.datetime.now(UTC)
        stamp = lambda value: value.isoformat().replace("+00:00", "Z")
        runs = os.path.join(self.state, "runs")
        self.write_json(os.path.join(runs, "run-live", "meta.json"), {
            "lane": "sonnet", "effort": "high", "class": "design",
            "launched_at": stamp(now - dt.timedelta(minutes=10)), "eta_s": 1500})
        self.write_json(os.path.join(runs, "run-pending", "meta.json"), {
            "lane": "haiku", "effort": "medium", "verdict": "ok",
            "started_at": stamp(now - dt.timedelta(hours=2)), "ended_at": stamp(now - dt.timedelta(hours=1))})
        self.write_json(os.path.join(runs, "run-reviewed", "meta.json"), {
            "lane": "opus", "effort": "low", "verdict": "ok",
            "started_at": stamp(now - dt.timedelta(hours=2)), "ended_at": stamp(now - dt.timedelta(hours=1))})
        self.write_json(os.path.join(runs, "run-reviewed", "review.json"), {"outcome": "accepted"})
        # A verify run is not a unit and is never reviewed.
        self.write_json(os.path.join(runs, "run-verify", "meta.json"), {
            "lane": "sonnet", "effort": "medium", "verdict": "OK", "verify": True, "tag": "verify",
            "started_at": stamp(now - dt.timedelta(hours=2)), "ended_at": stamp(now - dt.timedelta(minutes=30))})
        opened = os.path.join(self.state, "turns", "open", "session-1.json")
        self.write_json(opened, {"session_id": "session-1", "turn_id": "turn-1",
                                 "started_at": stamp(now - dt.timedelta(minutes=15))})
        with open(os.path.join(self.state, "turns.jsonl"), "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"type": "eta", "turn_id": "turn-1", "session_id": "session-1",
                                     "at": stamp(now), "elapsed_minutes": 10,
                                     "remaining_minutes": 20, "note": "check output"}) + "\n")
        result = self.command("resume-context", input_text=json.dumps({"session_id": "session-1"}))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Lanes in flight:\n- run-live sonnet high design local started", result.stdout)
        self.assertIn("eta ~25 min", result.stdout)
        self.assertIn("Finished, not reviewed (48 h):\n- run-pending haiku medium ok ended", result.stdout)
        self.assertNotIn("run-reviewed", result.stdout)
        self.assertNotIn("run-verify", result.stdout)
        self.assertIn("This turn: ", result.stdout)
        self.assertIn("of ~30 min; note: check output", result.stdout)
        self.assertEqual(result.stdout.splitlines()[-1], "Check these runs and the task list before acting on the summary.")
        self.assertLessEqual(len(result.stdout.splitlines()), 50)

    def test_resume_context_empty_state(self):
        result = self.command("resume-context", input_text="{}")
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("Kit state after compaction (turn-meter, "))
        self.assertEqual(lines[1], "No lane runs in flight or awaiting review.")

    def test_post_compact_logs_summary_and_does_not_change_turn_ledger(self):
        self.gate(self.transcript("compact", usage=1234), session="compact-session")
        ledger_path = os.path.join(self.state, "turns.jsonl")
        with open(ledger_path, "w", encoding="utf-8") as handle:
            handle.write("existing turn ledger\n")
        with open(ledger_path, encoding="utf-8") as handle:
            before = handle.read()
        event = {"hook_event_name": "PostCompact", "session_id": "compact-session",
                 "trigger": "auto", "compact_summary": "a summary"}
        result = self.command("hook", input_text=json.dumps(event))
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))
        with open(ledger_path, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), before)
        row = self.compaction_rows()[-1]
        self.assertEqual(row["type"], "compaction")
        self.assertEqual(row["summary_chars"], len("a summary"))
        self.assertEqual(row["estimate"], 1234)

    def test_compactions_report_counts_triggers_gate_results_and_medians(self):
        start = self.transcript("report-start", usage=100, ending="prompt")
        self.gate(start, session="start")
        self.gate(self.transcript("report-block", usage=100), session="block")
        self.gate(self.transcript("report-over", usage=360000), session="over")
        for session, trigger, summary in (("start", "auto", "abc"), ("over", "auto", "abcdefghij"),
                                          ("manual", "manual", "abcdef")):
            event = {"hook_event_name": "PostCompact", "session_id": session,
                     "trigger": trigger, "compact_summary": summary}
            self.command("hook", input_text=json.dumps(event))
        result = self.command("compactions", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value["compactions"], 3)
        self.assertEqual(value["by_trigger"], {"auto": 2, "manual": 1})
        self.assertEqual(value["allowed_at_turn_start"], 1)
        self.assertEqual(value["allowed_mid_turn_past_ceiling"], 1)
        self.assertEqual(value["blocks"], 1)
        self.assertEqual(value["median_summary_chars"], 6)
        self.assertGreater(value["median_estimate_tokens"], 100000)


class CensusTests(unittest.TestCase):
    SECRET = "SECRET-PROMPT-TEXT"

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="census-test-")
        self.claude = os.path.join(self.root, "claude")
        self.codex = os.path.join(self.root, "codex")
        self.usage = os.path.join(self.root, "usage")
        os.makedirs(self.usage)
        self.config = os.path.join(self.root, "config")
        os.makedirs(self.config)
        self.env = dict(os.environ, CLAUDE_CONFIG_DIR=self.claude, CODEX_HOME=self.codex,
                        CLAUDE_USAGE_DIR=self.usage, LANES_CONFIG=self.config, HOME=self.root, USERPROFILE=self.root)
        self.env.pop("USAGE_OPTIMIZER_MODE", None)
        base = dt.datetime(2026, 10, 29, 10, 0, 0, tzinfo=UTC)
        self.base = base
        project = os.path.join(self.claude, "projects", "proj-a")
        # cli: 4 events 1 min apart, a 1 h gap, 2 more events 1 min apart -> 4 active minutes
        offsets = [0, 60, 120, 180, 180 + 3600, 180 + 3660]
        self.cli = self.write_lines(os.path.join(project, "s1.jsonl"), [
            self.claude_event(base, offsets[i], "assistant" if i % 2 else "user", "cli", i) for i in range(6)])
        self.sub = self.write_lines(os.path.join(project, "s1", "subagents", "agent-1.jsonl"), [
            self.claude_event(base, 0, "assistant", None, 0), self.claude_event(base, 120, "assistant", None, 1)])
        self.sdk = self.write_lines(os.path.join(project, "s2.jsonl"), [
            self.claude_event(base, 0, "assistant", "sdk-cli", 0), self.claude_event(base, 30, "assistant", "sdk-cli", 1)])
        stamp = lambda s: (base + dt.timedelta(seconds=s)).isoformat().replace("+00:00", "Z")
        self.rollout = self.write_lines(os.path.join(self.codex, "sessions", "2026", "10", "29", "rollout-x.jsonl"), [
            {"timestamp": stamp(0), "type": "session_meta", "payload": {"originator": "codex-tui", "text": self.SECRET}},
            {"timestamp": stamp(60), "type": "turn_context", "payload": {"model": "gpt-x"}},
            {"timestamp": stamp(120), "type": "turn_context", "payload": {"model": "gpt-x"}},
            {"timestamp": stamp(4000), "type": "event_msg", "payload": {"message": self.SECRET}}])

    def tearDown(self):
        shutil.rmtree(self.root)

    def claude_event(self, base, offset, kind, entrypoint, index):
        event = {"timestamp": (base + dt.timedelta(seconds=offset)).isoformat().replace("+00:00", "Z"), "type": kind,
                 "message": {"content": self.SECRET}}
        if entrypoint:
            event["entrypoint"] = entrypoint
        if kind == "assistant":
            event["message"] = {"model": "claude-test", "usage": {"output_tokens": 10}, "content": self.SECRET}
        return event

    def write_lines(self, path, events):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event) + "\n")
            handle.write("not json " + self.SECRET + "\n")
        return path

    def run_census(self, *args):
        result = subprocess.run([sys.executable, METER, "census", *args], text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, env=self.env, timeout=15, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(self.SECRET, result.stdout)
        return result.stdout

    def test_counts_and_json_shape(self):
        value = json.loads(self.run_census("--since", "2026-10-29T00:00:00Z", "--json"))
        self.assertEqual(set(value), {"since", "claude", "codex", "claude_wall_hours", "skipped_files"})
        self.assertEqual(value["since"], "2026-10-29T00:00:00Z")
        self.assertEqual(set(value["claude"]), {"cli", "sdk-cli", "subagent"})
        cli = value["claude"]["cli"]
        self.assertEqual(cli["sessions"], 1)
        self.assertEqual(cli["active_seconds"], 240)
        self.assertEqual(cli["output_tokens"], 30)
        self.assertEqual(cli["models"], {"claude-test": 3})
        self.assertEqual(value["claude"]["sdk-cli"]["sessions"], 1)
        self.assertEqual(value["claude"]["sdk-cli"]["active_seconds"], 30)
        self.assertEqual(value["claude"]["subagent"]["sessions"], 1)
        self.assertEqual(value["claude"]["subagent"]["active_seconds"], 120)
        self.assertEqual(value["claude"]["subagent"]["output_tokens"], 20)
        self.assertAlmostEqual(value["claude_wall_hours"], 240 / 3600)
        codex = value["codex"]["codex-tui"]
        self.assertEqual((codex["sessions"], codex["active_seconds"], codex["turns"]), (1, 120, 2))
        self.assertEqual(codex["models"], {"gpt-x": 2})
        self.assertEqual(value["skipped_files"], 0)
        self.assertNotIn("proj-a", json.dumps(value))

    def test_text_output(self):
        text = self.run_census("--since", "2026-10-29")
        self.assertIn("cli", text)
        self.assertIn("codex-tui", text)
        self.assertIn("proj-a", text)

    def test_since_by_mtime_and_timestamp(self):
        old = (self.base - dt.timedelta(days=30)).timestamp()
        os.utime(self.sdk, (old, old))
        os.utime(self.rollout, (old, old))
        value = json.loads(self.run_census("--since", "2026-10-29T00:00:00Z", "--json"))
        self.assertNotIn("sdk-cli", value["claude"])
        self.assertEqual(value["codex"], {})
        # by timestamp: start after the first three cli events keeps only the last gaps
        cut = (self.base + dt.timedelta(seconds=150)).isoformat()
        value = json.loads(self.run_census("--since", cut, "--json"))
        self.assertEqual(value["claude"]["cli"]["active_seconds"], 60)

    def test_week_uses_rate_limit_record_or_falls_back(self):
        text = json.loads(self.run_census("--json"))
        self.assertIn("7 days", text["since_note"])
        reset = dt.datetime.now(UTC) + dt.timedelta(days=2)
        with open(os.path.join(self.usage, "claude-latest.json"), "w", encoding="utf-8") as handle:
            json.dump({"seven_day": {"used_percentage": 5, "resets_at": reset.isoformat()}}, handle)
        value = json.loads(self.run_census("--json"))
        self.assertNotIn("since_note", value)
        start = dt.datetime.fromisoformat(value["since"].replace("Z", "+00:00"))
        self.assertLess(abs((start - (reset - dt.timedelta(days=7))).total_seconds()), 2)


class PromptHookCase(unittest.TestCase):
    """What the UserPromptSubmit hook prints into Claude's context."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="mode-notice-test-")
        self.state = os.path.join(self.root, "state")
        self.usage = os.path.join(self.root, "usage")
        self.config = os.path.join(self.root, "config")
        self.cwd = os.path.join(self.root, "work")
        for folder in (self.state, self.usage, self.config, self.cwd):
            os.makedirs(folder)
        self.env = dict(os.environ)
        self.env.update({"LANES_STATE": self.state, "CLAUDE_USAGE_DIR": self.usage, "LANES_CONFIG": self.config,
                         "HOME": self.root, "USERPROFILE": self.root, "NO_COLOR": "1",
                         "USAGE_OPTIMIZER_CODEX": "off", "USAGE_OPTIMIZER_KIT_LABEL": "off"})
        for name in ("CLAUDE_CONFIG_DIR", "CLAUDE_CODE_REMOTE", "USAGE_OPTIMIZER_MODE", "USAGE_OPTIMIZER_MODE_NOTICE",
                     "USAGE_OPTIMIZER_NOTICES", "USAGE_OPTIMIZER_UPDATE_CHECK", "LANES_ARMS_LOCAL"):
            self.env.pop(name, None)

    def tearDown(self):
        shutil.rmtree(self.root)

    def stamp(self, value):
        return value.isoformat().replace("+00:00", "Z")

    def hook_output(self, event, session="session-1"):
        value = {"hook_event_name": event, "session_id": session, "cwd": self.cwd}
        return subprocess.run([sys.executable, METER, "hook"], input=json.dumps(value), text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env,
                              cwd=self.cwd, timeout=10, check=False)

    def prompt_notice(self, session="session-1"):
        result = self.hook_output("UserPromptSubmit", session)
        self.assertEqual(result.returncode, 0, result.stderr)
        if not result.stdout:
            return ""
        self.assertEqual(len(result.stdout.splitlines()), 1)
        output = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "UserPromptSubmit")
        return output["additionalContext"]

    def write_claude_week(self, used, reset):
        self.write_json(os.path.join(self.usage, "claude-latest.json"), {
            "observed_at": self.stamp(dt.datetime.now(UTC)), "plan": "max",
            "seven_day": {"used_percentage": used, "resets_at": self.stamp(reset)}})

    def write_json(self, path, value):
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(value, handle)

    def read_json(self, path):
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)


class ModeNoticeTests(PromptHookCase):
    def test_first_prompt_announces_mode_once_per_session(self):
        self.env["USAGE_OPTIMIZER_MODE"] = "utilization"
        self.assertTrue(self.prompt_notice().startswith("Usage Optimizer mode: utilization"))
        self.assertEqual(self.prompt_notice(), "")

    def test_cloud_session_notice_fans_out_to_subagents_not_sessions(self):
        self.env["USAGE_OPTIMIZER_MODE"] = "utilization"
        self.env["CLAUDE_CODE_REMOTE"] = "true"
        notice = self.prompt_notice()
        self.assertIn("this session's units run as its own subagents", notice)
        self.assertNotIn("Put them in a few cloud sessions", notice)
        self.env["USAGE_OPTIMIZER_MODE"] = "saving"
        self.assertIn("all as this session's own", self.prompt_notice())

    def test_local_session_notice_names_lane_cloud_sessions(self):
        self.env["USAGE_OPTIMIZER_MODE"] = "utilization"
        self.env.pop("CLAUDE_CODE_REMOTE", None)
        notice = self.prompt_notice()
        self.assertIn("started through lane --cloud", notice)
        self.assertNotIn("run as its own subagents", notice)

    def test_changed_mode_is_announced_once_more(self):
        self.env["USAGE_OPTIMIZER_MODE"] = "utilization"
        self.prompt_notice()
        self.env["USAGE_OPTIMIZER_MODE"] = "saving"
        self.assertTrue(self.prompt_notice().startswith("Usage Optimizer mode: saving"))
        self.assertEqual(self.prompt_notice(), "")

    def test_stop_and_invalid_session_print_nothing(self):
        self.env["USAGE_OPTIMIZER_MODE"] = "utilization"
        stop = self.hook_output("Stop")
        self.assertEqual(stop.returncode, 0, stop.stderr)
        self.assertEqual(stop.stdout, "")
        self.assertEqual(self.prompt_notice(session="bad id/with spaces"), "")

    def test_mode_setting_order_is_env_then_file_then_catalog(self):
        with open(os.path.join(self.config, "mode"), "w", encoding="utf-8") as handle:
            handle.write("saving\n")
        self.env["USAGE_OPTIMIZER_MODE"] = "utilization"
        self.assertTrue(self.prompt_notice("env-session").startswith("Usage Optimizer mode: utilization"))
        del self.env["USAGE_OPTIMIZER_MODE"]
        self.assertTrue(self.prompt_notice("file-session").startswith("Usage Optimizer mode: saving"))
        os.remove(os.path.join(self.config, "mode"))
        # A catalog of the test's own (LANES_ARMS), so the shipped explore.mode, now auto, does not decide the result.
        catalog = os.path.join(self.root, "arms.json")
        self.write_json(catalog, {"explore": {"mode": "utilization"}})
        self.env["LANES_ARMS"] = catalog
        self.assertTrue(self.prompt_notice("catalog-session").startswith("Usage Optimizer mode: utilization"))

    def test_unknown_mode_counts_as_default(self):
        self.env["USAGE_OPTIMIZER_MODE"] = "bogus"
        self.assertTrue(self.prompt_notice().startswith("Usage Optimizer mode: default"))

    def test_auto_mode_follows_claude_week_projection(self):
        self.env["USAGE_OPTIMIZER_MODE"] = "auto"
        now = dt.datetime.now(UTC)
        self.write_claude_week(33, now + dt.timedelta(days=1))
        calm = self.prompt_notice("calm-session")
        self.assertTrue(calm.startswith("Usage Optimizer mode: utilization"))
        self.assertIn("projected", calm)
        self.write_claude_week(99, now + dt.timedelta(days=6))
        self.assertTrue(self.prompt_notice("hot-session").startswith("Usage Optimizer mode: saving"))

    def test_auto_cloud_mode_uses_only_a_current_pick_table(self):
        self.env.update({"USAGE_OPTIMIZER_MODE": "auto", "CLAUDE_CODE_REMOTE": "true"})
        picks = os.path.join(self.root, "picks.json")
        self.env["USAGE_OPTIMIZER_PICKS"] = picks
        now = dt.datetime.now(UTC)
        self.write_json(picks, {"at": "2026-11-01T10:00:00Z", "modes": {"claude": "utilization"},
                                "modes_until": {"claude": self.stamp(now + dt.timedelta(days=2))}})
        notice = self.prompt_notice("current")
        self.assertTrue(notice.startswith("Usage Optimizer mode: utilization"))
        self.assertIn("pick table of 2026-11-01T10:00:00Z", notice)
        self.write_json(picks, {"at": "old", "modes": {"claude": "utilization"},
                                "modes_until": {"claude": self.stamp(now - dt.timedelta(seconds=1))}})
        self.assertTrue(self.prompt_notice("expired").startswith("Usage Optimizer mode: saving"))
        os.remove(picks)
        self.assertTrue(self.prompt_notice("missing").startswith("Usage Optimizer mode: saving"))

    def test_auto_without_meter_stays_default_locally(self):
        self.env["USAGE_OPTIMIZER_MODE"] = "auto"
        self.assertIn("default (auto, no meter reading", self.prompt_notice("local-no-meter"))

    def test_local_mode_change_mentions_live_mirrors_only(self):
        self.env["USAGE_OPTIMIZER_MODE"] = "utilization"
        self.assertNotIn("Cloud mirrors keep", self.prompt_notice("without"))
        self.write_json(os.path.join(self.state, "mains.json"),
                        {"version": 1, "mains": {"owner/repo": {"status": "live"}}})
        with_mirror = self.prompt_notice("with")
        self.assertIn("Cloud mirrors keep the mode they were handed", with_mirror)
        self.assertIn("lane main --picks <repo>", with_mirror)

    def test_notice_off_switch_prints_nothing_on_first_prompt(self):
        self.env["USAGE_OPTIMIZER_MODE"] = "utilization"
        self.env["USAGE_OPTIMIZER_MODE_NOTICE"] = "off"
        self.assertEqual(self.prompt_notice(), "")


class KitNoticeTests(PromptHookCase):
    def setUp(self):
        super().setUp()
        self.env["USAGE_OPTIMIZER_MODE_NOTICE"] = "off"  # these tests read the kit notices alone
        self.notices = os.path.join(self.state, "notices")
        os.makedirs(self.notices)

    def notice(self, notice_id, text, kind="window_change", created=None, expires=None, **extra):
        created = created or dt.datetime.now(UTC) - dt.timedelta(hours=1)
        value = {"id": notice_id, "kind": kind, "created_at": self.stamp(created), "text": text,
                 "expires_at": self.stamp(expires) if expires else None}
        value.update(extra)
        self.write_json(os.path.join(self.notices, notice_id + ".json"), value)
        return value

    def test_a_notice_is_told_once_per_session_and_again_for_a_new_created_at(self):
        first = dt.datetime.now(UTC) - dt.timedelta(hours=2)
        self.notice("window-1", "Claude's weekly window moved.", created=first)
        self.assertEqual(self.prompt_notice(), "Usage Optimizer notice: Claude's weekly window moved.")
        self.assertEqual(self.prompt_notice(), "")
        self.notice("window-1", "Claude's weekly window moved again.", created=first + dt.timedelta(hours=1))
        self.assertEqual(self.prompt_notice(), "Usage Optimizer notice: Claude's weekly window moved again.")
        self.assertEqual(self.prompt_notice(), "")
        told = self.read_json(os.path.join(self.state, "turns", "notices", "session-1"))["told"]
        self.assertEqual(len(told), 2)  # one content id per notice text, not per notice id

    def test_two_sessions_are_each_told_once(self):
        self.notice("kit-2.0", "Usage Optimizer 2.0 is out.", kind="kit_update")
        self.assertEqual(self.prompt_notice("session-a"), "Usage Optimizer 2.0 is out.")
        self.assertEqual(self.prompt_notice("session-b"), "Usage Optimizer 2.0 is out.")
        self.assertEqual(self.prompt_notice("session-a"), "")
        self.assertEqual(self.prompt_notice("session-b"), "")

    def test_expired_malformed_and_mismatched_notices_are_ignored(self):
        now = dt.datetime.now(UTC)
        self.notice("good", "Still current.", expires=now + dt.timedelta(days=1))
        self.notice("expired", "Too late.", expires=now - dt.timedelta(minutes=1))
        self.notice("bad-expiry", "Unreadable expiry.", expires_at="soon")
        self.notice("bad-created", "Unreadable start.", created_at="yesterday")
        self.notice("no-text", "")
        self.notice("no-kind", "No kind.", kind=None)
        self.notice("renamed", "Wrong id.", id="other")
        self.notice("bad id", "Not an id.")
        self.write_json(os.path.join(self.notices, "a-list.json"), ["not", "a", "notice"])
        with open(os.path.join(self.notices, "broken.json"), "w", encoding="utf-8") as handle:
            handle.write("{not json")
        with open(os.path.join(self.notices, "huge.json"), "w", encoding="utf-8") as handle:
            json.dump({"id": "huge", "kind": "window_change", "created_at": self.stamp(now), "text": "x" * 70000,
                       "expires_at": None}, handle)
        self.assertEqual(self.prompt_notice(), "Usage Optimizer notice: Still current.")
        self.assertFalse(os.path.exists(os.path.join(self.state, "turn-meter.err")))

    def test_at_most_five_notices_newest_first_each_capped(self):
        now = dt.datetime.now(UTC)
        for index in range(7):
            self.notice("n-{}".format(index), "Notice {}.".format(index), created=now - dt.timedelta(hours=10 - index))
        self.notice("long", "y" * 3000, created=now)
        text = self.prompt_notice()
        parts = text.split("\n\n")
        self.assertEqual(len(parts), 6)
        self.assertEqual(parts[:4], ["Usage Optimizer notice: Notice {}.".format(index) for index in range(3, 7)])
        self.assertEqual(len(parts[4]), len("Usage Optimizer notice: ") + 1500)
        self.assertTrue(parts[4].endswith("…"))
        self.assertEqual(parts[5], "Usage Optimizer: 3 more notices not shown here; run `turn-meter notices` to list them.")

    def test_mode_and_notices_come_out_as_one_json_object(self):
        self.env["USAGE_OPTIMIZER_MODE_NOTICE"] = ""
        self.env["USAGE_OPTIMIZER_MODE"] = "utilization"
        now = dt.datetime.now(UTC)
        self.notice("window", "Claude's window moved.", created=now - dt.timedelta(hours=2))
        self.notice("kit", "Usage Optimizer 2.0 is out.", kind="kit_update", created=now - dt.timedelta(hours=1))
        result = self.hook_output("UserPromptSubmit")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 1)
        context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        mode, window, kit = context.split("\n\n")
        self.assertTrue(mode.startswith("Usage Optimizer mode: utilization"))
        self.assertEqual((window, kit), ("Usage Optimizer notice: Claude's window moved.",
                                         "Usage Optimizer 2.0 is out."))
        self.assertEqual(self.prompt_notice(), "")

    def test_off_switches(self):
        self.notice("window", "Claude's window moved.", created=dt.datetime.now(UTC) - dt.timedelta(hours=2))
        self.notice("kit", "Usage Optimizer 2.0 is out.", kind="kit_update")
        self.env["USAGE_OPTIMIZER_NOTICES"] = "off"
        self.assertEqual(self.prompt_notice(), "")
        del self.env["USAGE_OPTIMIZER_NOTICES"]
        self.env["USAGE_OPTIMIZER_UPDATE_CHECK"] = "off"
        self.assertEqual(self.prompt_notice(), "Usage Optimizer notice: Claude's window moved.")
        del self.env["USAGE_OPTIMIZER_UPDATE_CHECK"]
        self.assertEqual(self.prompt_notice(), "Usage Optimizer 2.0 is out.")
        # The mode notice's own off switch (set in setUp) leaves the kit notices on.
        self.assertEqual(self.prompt_notice("session-2"),
                         "Usage Optimizer notice: Claude's window moved.\n\nUsage Optimizer 2.0 is out.")

    def test_an_unreadable_notices_folder_prints_nothing_and_the_turn_still_opens(self):
        shutil.rmtree(self.notices)
        with open(self.notices, "w", encoding="utf-8") as handle:
            handle.write("not a folder")
        self.env["USAGE_OPTIMIZER_MODE_NOTICE"] = ""
        self.env["USAGE_OPTIMIZER_MODE"] = "saving"
        self.assertTrue(self.prompt_notice().startswith("Usage Optimizer mode: saving"))
        self.assertTrue(os.path.exists(os.path.join(self.state, "turns", "open", "session-1.json")))

    def test_seven_waiting_notices_print_five_and_count_the_rest(self):
        now = dt.datetime.now(UTC)
        for index in range(7):
            self.notice("n-{}".format(index), "Notice {}.".format(index), created=now - dt.timedelta(hours=10 - index))
        parts = self.prompt_notice().split("\n\n")
        self.assertEqual(parts[:5], ["Usage Optimizer notice: Notice {}.".format(index) for index in range(2, 7)])
        self.assertEqual(parts[5], "Usage Optimizer: 2 more notices not shown here; run `turn-meter notices` to list them.")
        self.assertEqual(self.prompt_notice(), "")  # all seven are told, the two counted ones included
        listing = subprocess.run([sys.executable, METER, "notices", "--json"], env=self.env, cwd=self.cwd,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10, check=True)
        rows = json.loads(listing.stdout)["notices"]
        self.assertEqual([row["id"] for row in rows], ["n-{}".format(index) for index in range(6, -1, -1)])
        text = subprocess.run([sys.executable, METER, "notices"], env=self.env, cwd=self.cwd,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10, check=True)
        self.assertIn("Notice 0.", text.stdout)

    def test_a_notice_whose_print_fails_is_not_marked_told(self):
        self.env["USAGE_OPTIMIZER_MODE_NOTICE"] = ""
        self.env["USAGE_OPTIMIZER_MODE"] = "utilization"
        self.notice("window-1", "Claude's weekly window moved.", created=dt.datetime.now(UTC) - dt.timedelta(hours=2))
        raw = json.dumps({"hook_event_name": "UserPromptSubmit", "session_id": "session-1"})
        with mock.patch.dict(os.environ, self.env, clear=True), \
                mock.patch("builtins.print", side_effect=OSError("stdout closed")):
            meter._announce(self.state, raw)
        self.assertFalse(os.path.exists(os.path.join(self.state, "turns", "notices", "session-1")))
        self.assertFalse(os.path.exists(os.path.join(self.state, "turns", "mode", "session-1")))
        with open(os.path.join(self.state, "turn-meter.err"), encoding="utf-8") as handle:
            self.assertIn("OSError", handle.read())
        told_again = self.prompt_notice().split("\n\n")
        self.assertTrue(told_again[0].startswith("Usage Optimizer mode: utilization"))
        self.assertEqual(told_again[1:], ["Usage Optimizer notice: Claude's weekly window moved."])
        self.assertEqual(self.prompt_notice(), "")

    def test_session_ids_that_name_a_folder_are_refused(self):
        for bad in (".", "..", "", "a/b", "a\\b"):
            with self.subTest(session_id=bad):
                self.assertFalse(meter._session_id_ok(bad))
                with self.assertRaises(ValueError):
                    meter._session_path(self.state, bad)
                result = self.hook_output("UserPromptSubmit", bad)
                self.assertEqual((result.returncode, result.stdout), (0, ""))
                self.assertFalse(os.path.exists(os.path.join(self.state, "turns")))
        self.assertTrue(meter._session_id_ok("session-1.2_x"))

    def test_the_same_notice_in_a_recreated_file_is_not_told_again(self):
        created = dt.datetime.now(UTC) - dt.timedelta(hours=2)
        path = os.path.join(self.notices, "window-1.json")
        self.notice("window-1", "Claude's weekly window moved.", created=created)
        self.assertEqual(self.prompt_notice(), "Usage Optimizer notice: Claude's weekly window moved.")
        os.remove(path)
        self.notice("kit-2", "Usage Optimizer 2.0 is out.", kind="kit_update")
        self.assertEqual(self.prompt_notice(), "Usage Optimizer 2.0 is out.")
        self.notice("window-1", "Claude's weekly window moved.", created=created)  # the same content, a new file
        self.assertEqual(self.prompt_notice(), "")

    def test_only_files_newer_than_the_last_scan_are_read(self):
        now = dt.datetime.now(UTC)
        self.notice("fresh", "Fresh notice.", created=now - dt.timedelta(hours=1))
        self.assertEqual(self.prompt_notice(), "Usage Optimizer notice: Fresh notice.")
        self.notice("old", "Old notice.", created=now - dt.timedelta(hours=5))
        mark = os.path.getmtime(os.path.join(self.notices, "fresh.json"))
        os.utime(os.path.join(self.notices, "old.json"), (mark - 3600, mark - 3600))  # older than the last scan
        self.assertEqual(self.prompt_notice(), "")
        # A session that has never scanned reads the old file too.
        self.assertEqual(self.prompt_notice("session-2"),
                         "Usage Optimizer notice: Old notice.\n\nUsage Optimizer notice: Fresh notice.")

    def test_at_most_fifty_notice_files_are_read_per_scan(self):
        base = time.time() - 100000
        for index in range(60):
            self.notice("m-{:02d}".format(index), "Notice {:02d}.".format(index),
                        created=dt.datetime.now(UTC) - dt.timedelta(hours=60 - index))
            path = os.path.join(self.notices, "m-{:02d}.json".format(index))
            os.utime(path, (base + index, base + index))
        with mock.patch.dict(os.environ, self.env, clear=True), \
                mock.patch.object(meter, "_read_notice", wraps=meter._read_notice) as reader:
            texts, commit = meter._kit_notices(self.state, "session-3", dt.datetime.now(UTC))
            commit()
            self.assertEqual(reader.call_count, 50)
            reader.reset_mock()
            texts_again, _ = meter._kit_notices(self.state, "session-3", dt.datetime.now(UTC))
            self.assertLessEqual(reader.call_count, 1)  # only the newest file, at the mark, and it is told already
        self.assertEqual(texts_again, [])
        self.assertEqual(texts[-1], "Usage Optimizer: 45 more notices not shown here; run `turn-meter notices` to list them.")


if __name__ == "__main__":
    unittest.main()
