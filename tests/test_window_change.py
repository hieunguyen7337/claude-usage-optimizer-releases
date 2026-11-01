"""Plan-window change watch in bin/usage-status, and the warning bin/lane prints for it. No network."""

import datetime as dt
import importlib.machinery
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USAGE = os.path.join(ROOT, "bin", "usage-status")
LANE = os.path.join(ROOT, "bin", "lane")
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "window_change")
UTC = dt.timezone.utc
RESET = "2026-11-04T06:42:00Z"
NOTICE_KEYS = {"id", "kind", "created_at", "text", "expires_at"}


def load_script(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    loader.exec_module(module)
    return module


usage = load_script("usage_status_window", USAGE)
lane = load_script("lane_window", LANE)


def fixture(name):
    with open(os.path.join(FIXTURES, name), "r", encoding="utf-8") as handle:
        return json.load(handle)


def at(text):
    return usage.parse_time(text)


def iso(moment):
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class WindowWatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = os.path.join(self.temp.name, "state")

    def codex(self, pct, reading_at, reset=RESET, **extra):
        cache = fixture("codex-before.json")
        cache.update({"reading_at": reading_at, "observed_at": reading_at})
        cache["windows"][0].update({"used_percent": pct, "resets_at": reset})
        cache.update(extra)
        return cache

    def watch(self, cache, now, claude=None, agy=None):
        now = at(now)
        return usage.watch_windows(usage.weekly_readings(claude, cache, agy, now), now, self.state)

    def changes(self):
        path = os.path.join(self.state, "window-changes.jsonl")
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle]

    def notices(self):
        directory = os.path.join(self.state, "notices")
        if not os.path.isdir(directory):
            return {}
        result = {}
        for name in sorted(os.listdir(directory)):
            with open(os.path.join(directory, name), "r", encoding="utf-8") as handle:
                result[name] = json.load(handle)
        return result

    def stored(self, provider="codex", window="weekly"):
        with open(os.path.join(self.state, "window-readings.json"), "r", encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertEqual(data["version"], 1)
        return data["readings"][provider][window]

    def write_fall_and_history(self, provider="claude", reading_at=None, reading_pct=6):
        os.makedirs(self.state, exist_ok=True)
        event = {"at": "2026-10-30T12:01:00Z", "provider": provider, "window": "weekly", "kind": "fell",
                 "before": {"pct": 6.0, "resets_at": RESET, "at": "2026-10-30T08:00:00Z"},
                 "after": {"pct": 4.0, "resets_at": RESET, "at": "2026-10-30T12:00:00Z"}}
        usage.append_window_change(os.path.join(self.state, "window-changes.jsonl"), event)
        usage_dir = os.path.join(self.temp.name, "usage")
        os.makedirs(usage_dir)
        if reading_at:
            with open(os.path.join(usage_dir, "claude-rate.jsonl"), "w", encoding="utf-8") as handle:
                handle.write(json.dumps({"observed_at": reading_at,
                                         "seven_day": {"used_percentage": reading_pct,
                                                       "resets_at": RESET}}) + "\n")
        return usage_dir

    def test_claude_fall_contradicted_within_thirty_minutes_is_hidden(self):
        usage_dir = self.write_fall_and_history(reading_at="2026-10-30T12:20:00Z")
        with mock.patch.dict(os.environ, {"CLAUDE_USAGE_DIR": usage_dir}):
            self.assertEqual(usage.watch_windows([], at("2026-10-30T13:00:00Z"), self.state), [])

    def test_uncontradicted_claude_fall_is_shown(self):
        usage_dir = self.write_fall_and_history()
        with mock.patch.dict(os.environ, {"CLAUDE_USAGE_DIR": usage_dir}):
            self.assertEqual(len(usage.watch_windows([], at("2026-10-30T13:00:00Z"), self.state)), 1)

    def test_claude_fall_contradicted_more_than_thirty_minutes_later_is_shown(self):
        usage_dir = self.write_fall_and_history(reading_at="2026-10-30T12:31:00Z")
        with mock.patch.dict(os.environ, {"CLAUDE_USAGE_DIR": usage_dir}):
            self.assertEqual(len(usage.watch_windows([], at("2026-10-30T13:00:00Z"), self.state)), 1)

    def test_codex_fall_is_not_filtered_by_claude_history(self):
        usage_dir = self.write_fall_and_history(provider="codex", reading_at="2026-10-30T12:20:00Z")
        with mock.patch.dict(os.environ, {"CLAUDE_USAGE_DIR": usage_dir}):
            [shown] = usage.watch_windows([], at("2026-10-30T13:00:00Z"), self.state)
        self.assertEqual(shown["provider"], "codex")

    def test_fall_with_the_same_reset_is_an_event(self):
        # The 2026-10-30 case: Codex weekly 6% then 3%, the reset unchanged (30 s of jitter), no spend between.
        self.assertEqual(self.watch(fixture("codex-before.json"), "2026-10-30T08:01:00Z"), [])
        self.assertEqual(self.stored()["pct"], 6.0)
        shown = self.watch(fixture("codex-after.json"), "2026-10-30T12:01:00Z")
        [event] = self.changes()
        self.assertEqual(set(event), {"at", "provider", "window", "kind", "before", "after", "implied_scale"})
        self.assertEqual((event["provider"], event["window"], event["kind"]), ("codex", "weekly", "fell"))
        self.assertEqual(event["at"], "2026-10-30T12:01:00Z")
        self.assertEqual(event["before"], {"pct": 6.0, "resets_at": RESET, "at": "2026-10-30T08:00:00Z",
                                           "plan": "prolite"})
        self.assertEqual(event["after"]["pct"], 3.0)
        self.assertEqual(event["after"]["resets_at"], "2026-11-04T06:42:30Z")
        self.assertEqual(event["implied_scale"], 2.0)
        self.assertEqual([item["kind"] for item in shown], ["fell"])
        self.assertEqual(shown[0]["text"],
                         "plan window change: Codex weekly fell from 6% to 3% with the same reset "
                         "(2026-11-04T06:42:30Z), seen 2026-10-30: the window looks 2.0x larger; arms.json needs a "
                         "dated providers.codex.window_epochs entry")
        self.assertEqual(self.stored()["pct"], 3.0)
        self.assertEqual(self.stored()["at"], "2026-10-30T12:00:00Z")

    def test_notice_file_follows_the_shared_schema(self):
        self.watch(fixture("codex-before.json"), "2026-10-30T08:01:00Z")
        self.watch(fixture("codex-after.json"), "2026-10-30T12:01:00Z")
        [(name, notice)] = self.notices().items()
        self.assertEqual(set(notice), NOTICE_KEYS)
        self.assertTrue(re.fullmatch(r"[A-Za-z0-9_.-]+", notice["id"]))
        self.assertEqual(name, notice["id"] + ".json")
        self.assertEqual(notice["kind"], "window_change")
        self.assertEqual(notice["created_at"], "2026-10-30T12:01:00Z")
        self.assertEqual(notice["expires_at"], "2026-11-06T12:01:00Z")
        text = notice["text"]
        self.assertNotIn("\n", text)
        for piece in ("Codex weekly plan window looks about 2.0x larger", "from 6%", "to 3%",
                      "2026-11-04T06:42:30Z", "not a reset", "providers.codex.window_epochs",
                      "next kit release", "FINDINGS needs the measurement"):
            self.assertIn(piece, text)
        directory = os.path.join(self.state, "notices")
        self.assertEqual([entry for entry in os.listdir(directory) if not entry.endswith(".json")], [])
        if os.name != "nt":
            self.assertEqual(os.stat(directory).st_mode & 0o777, 0o700)

    def test_fall_across_a_reset_is_not_an_event(self):
        self.watch(fixture("codex-before.json"), "2026-10-30T08:01:00Z")
        self.assertEqual(self.watch(fixture("codex-after-reset.json"), "2026-11-04T08:01:00Z"), [])
        self.assertEqual(self.changes(), [])
        self.assertEqual(self.notices(), {})
        stored = self.stored()
        self.assertEqual((stored["pct"], stored["resets_at"]), (1.0, "2026-11-11T06:42:00Z"))

    def test_fall_of_one_point_is_rounding_but_one_and_a_half_is_an_event(self):
        self.watch(self.codex(6, "2026-10-30T08:00:00Z"), "2026-10-30T08:01:00Z")
        self.watch(self.codex(5, "2026-10-30T09:00:00Z"), "2026-10-30T09:01:00Z")
        self.assertEqual(self.changes(), [])
        self.watch(self.codex(3.5, "2026-10-30T10:00:00Z"), "2026-10-30T10:01:00Z")
        self.assertEqual([(row["kind"], row["before"]["pct"], row["after"]["pct"]) for row in self.changes()],
                         [("fell", 5.0, 3.5)])

    def test_a_reset_credit_the_user_applied_is_not_an_event(self):
        self.watch(self.codex(40, "2026-10-30T08:00:00Z", reset_credits=2), "2026-10-30T08:01:00Z")
        self.watch(self.codex(0, "2026-10-30T09:00:00Z", reset_credits=1), "2026-10-30T09:01:00Z")
        self.assertEqual(self.changes(), [])

    def test_fall_to_zero_has_no_implied_scale(self):
        self.watch(self.codex(4, "2026-10-30T08:00:00Z"), "2026-10-30T08:01:00Z")
        [shown] = self.watch(self.codex(0, "2026-10-30T09:00:00Z"), "2026-10-30T09:01:00Z")
        self.assertNotIn("implied_scale", self.changes()[0])
        self.assertIn("an early reset or a larger window", shown["text"])

    def test_a_rise_is_never_an_event_and_stores_no_anchor(self):
        # A rise has no event: interactive sessions, other machines and other meter readers raise it too.
        self.watch(self.codex(10, "2026-10-30T08:00:00Z"), "2026-10-30T08:01:00Z")
        self.assertEqual(self.watch(self.codex(22, "2026-10-30T12:00:00Z"), "2026-10-30T12:01:00Z"), [])
        self.assertEqual(self.changes(), [])
        self.assertEqual(self.notices(), {})
        self.assertEqual((self.stored()["pct"], self.stored()["at"]), (22.0, "2026-10-30T12:00:00Z"))
        self.assertNotIn("anchor", self.stored())
        claude = {"observed_at": "2026-10-30T12:00:00Z", "seven_day": {"used_percentage": 40, "resets_at": RESET}}
        self.assertEqual(self.watch(None, "2026-10-30T12:01:00Z", claude=claude), [])
        self.assertEqual(self.stored("claude")["pct"], 40.0)

    def test_old_rise_rows_in_the_log_are_not_shown(self):
        # A log written by an earlier version may hold rise events; they are not warnings any more.
        os.makedirs(self.state, exist_ok=True)
        old = {"at": "2026-10-30T12:01:00Z", "provider": "codex", "window": "weekly", "kind": "rose_fast",
               "before": {"pct": 10.0, "resets_at": RESET, "at": "2026-10-30T08:00:00Z"},
               "after": {"pct": 22.0, "resets_at": RESET, "at": "2026-10-30T12:00:00Z"}, "explained_pct": 0.0}
        with open(os.path.join(self.state, "window-changes.jsonl"), "w", encoding="utf-8") as handle:
            handle.write(json.dumps(old) + "\n")
        self.assertEqual(usage.watch_windows([], at("2026-10-30T13:00:00Z"), self.state), [])

    def test_the_same_event_is_recorded_and_noticed_once(self):
        self.watch(fixture("codex-before.json"), "2026-10-30T08:01:00Z")
        self.watch(fixture("codex-after.json"), "2026-10-30T12:01:00Z")
        first = self.notices()
        self.watch(fixture("codex-after.json"), "2026-10-30T12:30:00Z")
        # A second fall in the same window is the same event for this window.
        shown = self.watch(self.codex(1, "2026-10-30T13:00:00Z"), "2026-10-30T13:01:00Z")
        self.assertEqual(len(self.changes()), 1)
        self.assertEqual(len(shown), 1)
        self.assertEqual(self.notices(), first)
        self.assertEqual(self.stored()["pct"], 1.0)

    def test_only_the_last_seven_days_are_listed(self):
        self.watch(fixture("codex-before.json"), "2026-10-30T08:01:00Z")
        self.watch(fixture("codex-after.json"), "2026-10-30T12:01:00Z")
        self.assertEqual(len(usage.watch_windows([], at("2026-11-06T12:00:00Z"), self.state)), 1)
        self.assertEqual(usage.watch_windows([], at("2026-11-06T12:02:00Z"), self.state), [])

    def test_readings_with_a_non_finite_percentage_are_skipped(self):
        now = at("2026-10-30T12:00:00Z")
        for pct in (float("nan"), float("inf"), float("-inf")):
            self.assertEqual(usage.weekly_readings(None, self.codex(pct, "2026-10-30T11:59:00Z"), None, now), [])
            self.assertEqual(self.watch(self.codex(pct, "2026-10-30T11:59:00Z"), "2026-10-30T12:00:00Z"), [])
        self.assertFalse(os.path.exists(os.path.join(self.state, "window-readings.json")))
        # The same reading with a finite percentage is kept.
        self.assertEqual([item["pct"] for item in usage.weekly_readings(None, self.codex(7, "2026-10-30T11:59:00Z"),
                                                                       None, now)], [7.0])

    def test_readings_stamped_more_than_five_minutes_ahead_are_skipped(self):
        now = at("2026-10-30T12:00:00Z")
        self.assertEqual(usage.weekly_readings(None, self.codex(10, "2026-10-30T12:06:00Z"), None, now), [])
        claude = {"observed_at": "2026-10-30T12:10:00Z", "seven_day": {"used_percentage": 10, "resets_at": RESET}}
        self.assertEqual(usage.weekly_readings(claude, None, None, now), [])
        # Up to five minutes ahead is clock jitter: kept, and stamped with now.
        [item] = usage.weekly_readings(None, self.codex(10, "2026-10-30T12:04:00Z"), None, now)
        self.assertEqual(item["at"], "2026-10-30T12:00:00Z")

    def test_a_future_reading_stores_nothing(self):
        self.watch(self.codex(10, "2026-10-30T08:00:00Z"), "2026-10-30T08:01:00Z")
        self.assertEqual(self.watch(self.codex(3, "2026-10-30T13:00:00Z"), "2026-10-30T12:01:00Z"), [])
        self.assertEqual(self.changes(), [])
        self.assertEqual((self.stored()["pct"], self.stored()["at"]), (10.0, "2026-10-30T08:00:00Z"))

    def test_readings_skip_ended_windows_and_name_gemini_buckets(self):
        now = at("2026-10-30T12:00:00Z")
        ended = self.codex(0, "2026-10-28T08:00:00Z", reset="2026-10-29T00:00:00Z")
        self.assertEqual(usage.weekly_readings(None, ended, None, now), [])
        agy = {"exit_code": 0, "error": None, "buckets": [
            {"id": "gemini-weekly", "window": "weekly", "used_percentage": 30.0, "reset_time": RESET},
            {"id": "Gemini Pro", "window": "weekly", "used_percentage": 12.5, "reset_time": RESET},
            {"id": "gemini-5h", "window": "5h", "used_percentage": 50.0, "reset_time": "2026-10-30T15:00:00Z"}]}
        readings = usage.weekly_readings(None, None, agy, now)
        self.assertEqual([(item["provider"], item["window"], item["pct"], item["at"]) for item in readings],
                         [("gemini", "weekly", 30.0, "2026-10-30T12:00:00Z"),
                          ("gemini", "Gemini Pro weekly", 12.5, "2026-10-30T12:00:00Z")])
        self.assertEqual(usage.weekly_readings(None, None, dict(agy, exit_code=1), now), [])


WRITER = '''
import importlib.machinery
import importlib.util
import sys

usage_path, log_path, tag, count = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
loader = importlib.machinery.SourceFileLoader("usage_writer", usage_path)
module = importlib.util.module_from_spec(importlib.util.spec_from_loader("usage_writer", loader))
loader.exec_module(module)
for index in range(count):
    module.append_window_change(log_path, {
        "at": "2026-10-30T12:00:00Z", "provider": "codex", "window": "%s-%d" % (tag, index), "kind": "fell",
        "before": {"pct": 6.0, "resets_at": "2026-11-04T06:42:00Z", "at": "2026-10-30T08:00:00Z"},
        "after": {"pct": 3.0, "resets_at": "2026-11-04T06:42:00Z", "at": "2026-10-30T12:00:00Z"}})
'''


class EventLogTests(unittest.TestCase):
    """The event log takes no lock: writers append one line each, and reads dedupe the copies."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.log = os.path.join(self.temp.name, "window-changes.jsonl")

    def test_two_writers_appending_at_once_lose_no_event(self):
        script = os.path.join(self.temp.name, "writer.py")
        with open(script, "w", encoding="utf-8") as handle:
            handle.write(WRITER)
        writers = [subprocess.Popen([sys.executable, script, USAGE, self.log, tag, "150"], stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True, encoding="utf-8")
                   for tag in ("a", "b")]
        for writer in writers:
            _, stderr = writer.communicate(timeout=120)
            self.assertEqual(writer.returncode, 0, stderr)
        with open(self.log, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        self.assertEqual(len(lines), 300)
        for line in lines:
            self.assertIsInstance(json.loads(line), dict)  # each line is one whole event
        rows = usage.read_window_changes(self.log)
        self.assertEqual(sorted(row["window"] for row in rows),
                         sorted("%s-%d" % (tag, index) for tag in ("a", "b") for index in range(150)))

    def test_a_second_writers_copy_of_the_same_fall_is_read_once(self):
        event = {"at": "2026-10-30T12:01:00Z", "provider": "codex", "window": "weekly", "kind": "fell",
                 "before": {"pct": 6.0, "resets_at": RESET, "at": "2026-10-30T08:00:00Z"},
                 "after": {"pct": 3.0, "resets_at": "2026-11-04T06:42:30Z", "at": "2026-10-30T12:01:00Z"}}
        usage.append_window_change(self.log, event)
        usage.append_window_change(self.log, dict(event, at="2026-10-30T12:01:05Z"))  # the other writer's copy
        usage.append_window_change(self.log, dict(event, window="other"))  # a different window is kept
        with open(self.log, "r", encoding="utf-8") as handle:
            self.assertEqual(len(handle.read().splitlines()), 3)
        rows = usage.read_window_changes(self.log)
        self.assertEqual([(row["window"], row["at"]) for row in rows],
                         [("weekly", "2026-10-30T12:01:00Z"), ("other", "2026-10-30T12:01:00Z")])
        shown = usage.watch_windows([], at("2026-10-30T13:00:00Z"), os.path.dirname(self.log))
        self.assertEqual([row["window"] for row in shown], ["weekly", "other"])


class UsageStatusWindowTests(unittest.TestCase):
    """The --json field, the text warning and the background refresh, through the real script."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = self.temp.name
        self.state = os.path.join(root, "state")
        self.usage_dir = os.path.join(root, "usage")
        for path in (self.state, self.usage_dir, os.path.join(root, "codex")):
            os.makedirs(path)
        self.env = dict(os.environ, HOME=root, TMPDIR=root, CLAUDE_USAGE_DIR=self.usage_dir,
                        CODEX_HOME=os.path.join(root, "codex"), LANES_STATE=self.state,
                        LANES_ARMS=os.path.join(FIXTURES, "arms.json"), USAGE_OPTIMIZER_CODEX_LIVE="0",
                        USAGE_OPTIMIZER_CODEX_BIN=os.path.join(root, "no-codex"), NO_COLOR="1",
                        LANES_MEM_FAKE="6451:16300", PYTHONUTF8="1")
        now = dt.datetime.now(UTC)
        self.reset = iso(now + dt.timedelta(days=3))
        self.write(os.path.join(self.usage_dir, "claude-latest.json"), {
            "observed_at": iso(now - dt.timedelta(minutes=1)),
            "five_hour": {"used_percentage": 5, "resets_at": iso(now + dt.timedelta(hours=2))},
            "seven_day": {"used_percentage": 20, "resets_at": self.reset}})
        self.earlier = {"pct": 40.0, "resets_at": self.reset, "at": iso(now - dt.timedelta(hours=2))}

    def write(self, path, value):
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(value, handle)

    def seed(self):
        self.write(os.path.join(self.state, "window-readings.json"), {"version": 1, "readings": {
            "claude": {"weekly": dict(self.earlier)}}})

    def run_usage(self, *flags):
        result = subprocess.run([sys.executable, USAGE] + list(flags), stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, encoding="utf-8", env=self.env, timeout=30,
                                check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def change_rows(self):
        with open(os.path.join(self.state, "window-changes.jsonl"), "r", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle]

    def test_json_and_text_carry_the_window_change(self):
        self.seed()
        data = json.loads(self.run_usage("--json", "--no-agy", "--no-local"))
        [change] = data["window_changes"]
        self.assertEqual((change["provider"], change["window"], change["kind"], change["implied_scale"]),
                         ("claude", "weekly", "fell", 2.0))
        self.assertEqual(change["before"], self.earlier)
        self.assertTrue(change["text"].startswith("plan window change: Claude weekly fell from 40% to 20%"))
        lines = self.run_usage("--no-agy", "--no-local").splitlines()
        warnings = [line for line in lines if line.startswith("warning: ")]
        self.assertEqual(warnings, ["warning: " + change["text"]])
        self.assertTrue(lines[-1].startswith("Hint: "))
        self.assertEqual(len(self.change_rows()), 1)
        self.assertEqual(len(os.listdir(os.path.join(self.state, "notices"))), 1)

    def test_no_event_leaves_the_json_without_the_field(self):
        data = json.loads(self.run_usage("--json", "--no-agy", "--no-local"))
        self.assertNotIn("window_changes", data)
        with open(os.path.join(self.state, "window-readings.json"), "r", encoding="utf-8") as handle:
            stored = json.load(handle)["readings"]["claude"]["weekly"]
        self.assertEqual((stored["pct"], stored["resets_at"]), (20.0, self.reset))

    def test_background_refresh_runs_the_watch_and_prints_nothing(self):
        self.seed()
        self.assertEqual(self.run_usage("--codex-refresh"), "")
        self.assertEqual([row["kind"] for row in self.change_rows()], ["fell"])


class LaneWindowWarningTests(unittest.TestCase):
    TEXT = ("plan window change: Codex weekly fell from 6% to 3% with the same reset (2026-11-04T06:42:30Z), "
            "seen 2026-10-30: the window looks 2.0x larger; arms.json needs a dated providers.codex.window_epochs "
            "entry")

    def setUp(self):
        lane.WINDOW_CHANGES.clear()
        self.addCleanup(lane.WINDOW_CHANGES.clear)

    def meter(self, data):
        completed = subprocess.CompletedProcess([], 0, json.dumps(data).encode("utf-8"), b"")
        with mock.patch.dict(os.environ, {"LANE_NO_USAGE": "0"}), \
                mock.patch.object(lane, "run_quiet", return_value=None), \
                mock.patch.object(lane.subprocess, "run", return_value=completed):
            return lane.read_usage("codex")

    def test_before_and_after_readings_give_one_warning(self):
        section = {"status": "ok", "age_seconds": 2, "reading": None,
                   "windows": [{"label": "weekly", "used_percent": 3, "resets_at": "2026-11-04T06:42:30Z"}]}
        self.meter({"codex": section})
        self.assertIsNone(lane.window_change_warning())
        change = {"provider": "codex", "window": "weekly", "kind": "fell", "text": self.TEXT}
        for _ in range(2):
            reading, error = self.meter({"codex": section, "window_changes": [change, {"text": None}, "bad"]})
            self.assertIsNone(error)
            self.assertNotIn("window_changes", reading)
        self.assertEqual(lane.window_change_warning(), self.TEXT)

    def test_lane_run_prints_the_warning_line(self):
        root = tempfile.mkdtemp(prefix="lane-window-")
        self.addCleanup(shutil.rmtree, root, True)
        bin_dir, workspace, state = (os.path.join(root, name) for name in ("bin", "workspace", "state"))
        for path in (bin_dir, workspace):
            os.makedirs(path)
        subprocess.run(["git", "init", workspace], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        brief = os.path.join(root, "brief.md")
        with open(brief, "w", encoding="utf-8") as handle:
            handle.write("Say done.\n")
        copied = os.path.join(bin_dir, "lane")
        shutil.copyfile(LANE, copied)
        with open(os.path.join(bin_dir, "usage-status.py"), "w", encoding="utf-8") as handle:
            handle.write(textwrap.dedent('''
                import json
                print(json.dumps({"claude": {"reading": {"observed_at": "2026-10-30T12:00:00Z"}, "age_seconds": 2,
                    "stale": False, "windows": {"seven_day": {"used_percentage": 20,
                    "resets_at": "2026-11-04T06:42:00Z"}}},
                    "window_changes": [{"provider": "codex", "window": "weekly", "kind": "fell",
                                        "text": %r}]}))
            ''' % self.TEXT))
        fake = os.path.join(bin_dir, "fake_claude.py")
        with open(fake, "w", encoding="utf-8") as handle:
            handle.write(textwrap.dedent('''
                import json
                import sys
                sys.stdin.read()
                with open("worker.txt", "w", encoding="utf-8") as stream:
                    stream.write("done\\n")
                print(json.dumps({"session_id": "window-test", "is_error": False, "result": "done",
                                  "total_cost_usd": 0.01, "usage": {"input_tokens": 1, "output_tokens": 1}}))
            '''))
        if os.name == "nt":
            with open(os.path.join(bin_dir, "claude.cmd"), "w", encoding="utf-8") as handle:
                handle.write('@echo off\n"{}" "{}" %*\n'.format(sys.executable, fake))
        else:
            launcher = os.path.join(bin_dir, "claude")
            with open(launcher, "w", encoding="utf-8") as handle:
                handle.write('#!/bin/sh\nexec {} {} "$@"\n'.format(shlex.quote(sys.executable), shlex.quote(fake)))
            os.chmod(launcher, 0o755)
        env = dict(os.environ, LANES_STATE=state, LANE_NO_USAGE="0", LANE_NO_ETA="1", LANES_MEM_CHECK="off",
                   PYTHONUTF8="1", LANES_CONFIG=os.path.join(root, "config"),
                   LANES_ARMS=os.path.join(ROOT, "arms.json"), LANES_ARMS_LOCAL=os.path.join(root, "none.json"),
                   CODEX_HOME=os.path.join(root, "codex-home"), LANES_PROC_CGROUP=os.path.join(root, "none"),
                   LANES_CGROUP_ROOT=os.path.join(root, "cgroup"),
                   PATH=bin_dir + os.pathsep + os.environ.get("PATH", ""))
        result = subprocess.run([sys.executable, copied, "haiku", "-C", workspace, "-b", brief, "-e", "low",
                                 "--class", "mechanical"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, encoding="utf-8",
                                errors="replace", timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        warnings = [line for line in result.stdout.splitlines() if line.startswith("warning: ")]
        self.assertEqual(warnings, ["warning: " + self.TEXT])


if __name__ == "__main__":
    unittest.main()
