import datetime as dt
import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUSLINE = os.path.join(ROOT, "bin", "claude-statusline")
UTC = dt.timezone.utc
WEEK_MINUTES = 7 * 24 * 60
YELLOW = "\x1b[33m"
RED = "\x1b[31m"
DIM = "\x1b[2m"
RESET = "\x1b[0m"


def load_statusline():
    loader = importlib.machinery.SourceFileLoader("claude_statusline_pace_tested", STATUSLINE)
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


statusline = load_statusline()


def resets_for_pace(now, length_minutes, pace):
    # Remaining share is (100 − pace) percent of the window, in whole seconds, so the
    # elapsed share rounds to `pace` at `now`.
    length_seconds = int(length_minutes * 60)
    remaining = length_seconds * (100 - pace) // 100
    return now + dt.timedelta(seconds=remaining)


def iso(when):
    return when.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class StatuslinePaceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self.usage = os.path.join(self.root, "usage")
        os.makedirs(self.usage)
        os.makedirs(os.path.join(self.root, ".claude"))
        self.env = dict(os.environ)
        self.env.update({
            "HOME": self.root,
            "USERPROFILE": self.root,
            "TMPDIR": self.root,
            "CLAUDE_USAGE_DIR": self.usage,
            "CLAUDE_CONFIG_DIR": os.path.join(self.root, ".claude"),
            "CODEX_HOME": os.path.join(self.root, "codex"),
            "LANES_STATE": os.path.join(self.root, "state"),
            "USAGE_OPTIMIZER_CODEX": "off",
            "USAGE_OPTIMIZER_CODEX_BIN": os.path.join(self.root, "missing-codex"),
            "USAGE_OPTIMIZER_CLAUDE_JSON": "off",
            "USAGE_OPTIMIZER_KIT_LABEL": "off",
            "USAGE_OPTIMIZER_TURNS": "off",
            "USAGE_OPTIMIZER_UPDATE_CHECK": "off",
            "USAGE_OPTIMIZER_TZ": "UTC",
            "NO_COLOR": "1",
        })
        for key in ("COLUMNS", "USAGE_OPTIMIZER_PACE", "USAGE_OPTIMIZER_COLOR",
                    "USAGE_OPTIMIZER_POLICY"):
            self.env.pop(key, None)
        self.now = dt.datetime.now(UTC).replace(microsecond=0)

    def shown_reset(self, when, weekly):
        # Format with the same zone the status line uses (UTC here), not the machine's zone.
        previous = os.environ.get("USAGE_OPTIMIZER_TZ")
        os.environ["USAGE_OPTIMIZER_TZ"] = "UTC"
        try:
            return statusline._format_reset(iso(when), weekly)
        finally:
            if previous is None:
                os.environ.pop("USAGE_OPTIMIZER_TZ", None)
            else:
                os.environ["USAGE_OPTIMIZER_TZ"] = previous

    def run_statusline(self, data, **env):
        run_env = dict(self.env, **env)
        if env.get("NO_COLOR") == "":
            run_env.pop("NO_COLOR")
        result = subprocess.run(
            [sys.executable, "-X", "utf8", STATUSLINE], input=json.dumps(data), text=True,
            encoding="utf-8", stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=run_env, timeout=15, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.splitlines()

    def claude_data(self, five=9, week=23, five_at=None, week_at=None, scoped=None):
        five_at = five_at or (self.now + dt.timedelta(hours=3))
        week_at = week_at or resets_for_pace(self.now, WEEK_MINUTES, 31)
        limits = {
            "five_hour": {"used_percentage": five, "resets_at": iso(five_at)},
            "seven_day": {"used_percentage": week, "resets_at": iso(week_at)},
        }
        if scoped is not None:
            limits["limits"] = scoped
        return {"session_id": "s1", "model": {"display_name": "Opus 5.5"},
                "effort": {"level": "xhigh"}, "rate_limits": limits,
                "cost": {"total_cost_usd": 1.0}}

    def write_codex(self, windows, **extra):
        stamp = iso(self.now)
        cache = {"observed_at": stamp, "reading_at": stamp, "status": "ok", "windows": windows,
                 "reached": None, "ordinary_usage_allowed": True}
        cache.update(extra)
        with open(os.path.join(self.usage, "codex-latest.json"), "w", encoding="utf-8") as handle:
            json.dump(cache, handle)

    def test_pace_percent_is_the_elapsed_share_as_a_whole_percent(self):
        now = dt.datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
        self.assertEqual(statusline._pace_percent(resets_for_pace(now, WEEK_MINUTES, 31), WEEK_MINUTES, now), 31)
        self.assertEqual(statusline._pace_percent(resets_for_pace(now, WEEK_MINUTES, 52), WEEK_MINUTES, now), 52)
        self.assertEqual(statusline._pace_percent(resets_for_pace(now, 1440, 50), 1440, now), 50)
        # Same rounding as the used percent: int(round), half to even.
        self.assertEqual(statusline._pace_percent(resets_for_pace(now, WEEK_MINUTES, 30) - dt.timedelta(
            seconds=WEEK_MINUTES * 60 // 200), WEEK_MINUTES, now), 30)
        self.assertEqual(statusline._pace_percent(now + dt.timedelta(minutes=WEEK_MINUTES), WEEK_MINUTES, now), 0)
        self.assertEqual(statusline._pace_percent(now + dt.timedelta(minutes=WEEK_MINUTES + 90), WEEK_MINUTES, now), 0)
        self.assertIsNone(statusline._pace_percent(now, WEEK_MINUTES, now))
        self.assertIsNone(statusline._pace_percent(now - dt.timedelta(minutes=1), WEEK_MINUTES, now))
        self.assertIsNone(statusline._pace_percent("not-a-date", WEEK_MINUTES, now))
        self.assertIsNone(statusline._pace_percent(resets_for_pace(now, WEEK_MINUTES, 31), None, now))
        self.assertIsNone(statusline._pace_percent(resets_for_pace(now, WEEK_MINUTES, 31), 0, now))
        self.assertEqual(statusline._pace_marker(40, 31), " (pace 31%)")
        self.assertEqual(statusline._pace_marker(40.4, 31), " (pace 31%)")
        self.assertEqual(statusline._pace_marker(41, 31), " (pace 31%, hot)")
        self.assertEqual(statusline._pace_marker(40.6, 31), " (pace 31%, hot)")
        self.assertEqual(statusline._pace_marker(10, 0), " (pace 0%, hot)")
        self.assertEqual(statusline._pace_marker(9, 0), " (pace 0%)")
        self.assertEqual(statusline._pace_marker("nope", 31), "")
        self.assertEqual(statusline._pace_marker(23, None), "")

    def test_weekly_windows_show_the_marker_and_five_hour_windows_do_not(self):
        week_at = resets_for_pace(self.now, WEEK_MINUTES, 31)
        five_at = self.now + dt.timedelta(hours=3)
        fable_at = resets_for_pace(self.now, WEEK_MINUTES, 31)
        scoped = [{"kind": "weekly_scoped", "name": "Fable", "used_percentage": 7,
                   "resets_at": iso(fable_at)}]
        lines = self.run_statusline(self.claude_data(five_at=five_at, week_at=week_at, scoped=scoped))
        self.assertEqual(lines[1], "Claude 5h 9% resets {} · wk 23% (pace 31%) resets {} · "
                         "Fable 7% (pace 31%) resets {}".format(
                             self.shown_reset(five_at, False), self.shown_reset(week_at, True),
                             self.shown_reset(fable_at, True)))
        self.assertNotRegex(lines[1], r"5h \d+% \(pace")

        day_at = resets_for_pace(self.now, 1440, 50)
        codex_week = resets_for_pace(self.now, WEEK_MINUTES, 52)
        codex_five = self.now + dt.timedelta(hours=4)
        self.write_codex([
            {"label": "5h", "window_minutes": 300, "used_percent": 3, "resets_at": iso(codex_five)},
            {"label": "weekly", "window_minutes": WEEK_MINUTES, "used_percent": 37,
             "resets_at": iso(codex_week)},
            {"label": "daily", "window_minutes": 1440, "used_percent": 10, "resets_at": iso(day_at)},
        ])
        codex = self.run_statusline(self.claude_data(), USAGE_OPTIMIZER_CODEX="auto")[1]
        codex_part = codex.split(" │ ", 1)[1]
        self.assertEqual(codex_part, "Codex 5h 3% resets {} · wk 37% (pace 52%) resets {} · "
                         "1d 10% (pace 50%) resets {}".format(
                             self.shown_reset(codex_five, False), self.shown_reset(codex_week, True),
                             self.shown_reset(day_at, True)))
        self.assertNotRegex(codex_part, r"5h \d+% \(pace")

        self.write_codex([{"label": "weekly", "used_percent": 36, "resets_at": iso(codex_week)}])
        missing = self.run_statusline(self.claude_data(), USAGE_OPTIMIZER_CODEX="auto")[1]
        self.assertTrue(missing.endswith("Codex wk 36% resets {}".format(self.shown_reset(codex_week, True))),
                        missing)
        self.assertNotIn("(pace", missing.split(" │ ", 1)[1])

    def test_hot_when_used_leads_pace_by_ten_points(self):
        week_at = resets_for_pace(self.now, WEEK_MINUTES, 31)
        cool = self.run_statusline(self.claude_data(week=40, week_at=week_at))[1]
        self.assertIn("wk 40% (pace 31%) resets {}".format(self.shown_reset(week_at, True)), cool)
        self.assertNotIn("hot", cool)
        hot = self.run_statusline(self.claude_data(week=41, week_at=week_at))[1]
        self.assertIn("wk 41% (pace 31%, hot) resets {}".format(self.shown_reset(week_at, True)), hot)

    def test_pace_text_stays_plain_when_the_used_percent_is_coloured(self):
        week_at = resets_for_pace(self.now, WEEK_MINUTES, 80)
        codex_at = resets_for_pace(self.now, WEEK_MINUTES, 31)
        self.write_codex([{"label": "weekly", "window_minutes": WEEK_MINUTES, "used_percent": 96,
                           "resets_at": iso(codex_at)}])
        line = self.run_statusline(self.claude_data(week=85, week_at=week_at),
                                   USAGE_OPTIMIZER_CODEX="auto", NO_COLOR="", USAGE_OPTIMIZER_COLOR="on")[1]
        self.assertIn(YELLOW + "85%" + RESET + " (pace 80%) " + DIM + "resets ", line)
        self.assertIn(RED + "96%" + RESET + " (pace 31%, hot)", line)
        self.assertNotIn("hot", line.split(" │ ", 1)[0])
        for marker in re.findall(r"\(pace [^)]*\)", line):
            self.assertNotIn("\x1b", marker)
        plain = self.run_statusline(self.claude_data(week=85, week_at=week_at),
                                    USAGE_OPTIMIZER_COLOR="off")[1]
        self.assertNotIn("\x1b", plain)
        self.assertIn("wk 85% (pace 80%)", plain)

    def test_narrow_line_drops_pace_before_resets(self):
        five_at = self.now + dt.timedelta(hours=3)
        week_at = resets_for_pace(self.now, WEEK_MINUTES, 31)
        codex_five = self.now + dt.timedelta(hours=4)
        codex_week = resets_for_pace(self.now, WEEK_MINUTES, 52)
        self.write_codex([
            {"label": "5h", "window_minutes": 300, "used_percent": 3, "resets_at": iso(codex_five)},
            {"label": "weekly", "window_minutes": WEEK_MINUTES, "used_percent": 37,
             "resets_at": iso(codex_week)},
        ])
        data = self.claude_data(five_at=five_at, week_at=week_at)
        with_pace = ("Claude 5h 9% resets {five} · wk 23% (pace 31%) resets {week} │ "
                     "Codex 5h 3% resets {c5} · wk 37% (pace 52%) resets {cweek}").format(
            five=self.shown_reset(five_at, False), week=self.shown_reset(week_at, True),
            c5=self.shown_reset(codex_five, False), cweek=self.shown_reset(codex_week, True))
        no_pace = ("Claude 5h 9% resets {five} · wk 23% resets {week} │ "
                   "Codex 5h 3% resets {c5} · wk 37% resets {cweek}").format(
            five=self.shown_reset(five_at, False), week=self.shown_reset(week_at, True),
            c5=self.shown_reset(codex_five, False), cweek=self.shown_reset(codex_week, True))
        no_reset = "Claude 5h 9% · wk 23% │ Codex 5h 3% · wk 37%"
        self.assertEqual(self.run_statusline(data, USAGE_OPTIMIZER_CODEX="auto",
                                             COLUMNS=str(len(with_pace) + 2))[1], with_pace)
        dropped = self.run_statusline(data, USAGE_OPTIMIZER_CODEX="auto",
                                      COLUMNS=str(len(with_pace) + 1))[1]
        self.assertEqual(dropped, no_pace)
        self.assertNotIn("(pace", dropped)
        self.assertIn("resets ", dropped)
        self.assertEqual(self.run_statusline(data, USAGE_OPTIMIZER_CODEX="auto",
                                             COLUMNS=str(len(no_reset) + 2))[1], no_reset)

    def test_off_switch_hides_the_marker(self):
        week_at = resets_for_pace(self.now, WEEK_MINUTES, 31)
        codex_week = resets_for_pace(self.now, WEEK_MINUTES, 52)
        self.write_codex([{"label": "weekly", "window_minutes": WEEK_MINUTES, "used_percent": 80,
                           "resets_at": iso(codex_week)}])
        data = self.claude_data(week=41, week_at=week_at)
        shown = self.run_statusline(data, USAGE_OPTIMIZER_CODEX="auto")[1]
        self.assertIn("(pace 31%, hot)", shown)
        self.assertIn("(pace 52%, hot)", shown)
        for value in ("off", "OFF", " off "):
            hidden = self.run_statusline(data, USAGE_OPTIMIZER_CODEX="auto", USAGE_OPTIMIZER_PACE=value)[1]
            self.assertNotIn("pace", hidden)
            self.assertIn("wk 41% resets {}".format(self.shown_reset(week_at, True)), hidden)
            self.assertIn("Codex wk 80% resets {}".format(self.shown_reset(codex_week, True)), hidden)

    def test_a_bad_window_keeps_the_old_line(self):
        data = self.claude_data()
        data["rate_limits"]["seven_day"]["resets_at"] = "not-a-time"
        lines = self.run_statusline(data)
        self.assertEqual(lines[1], "Claude 5h 9% resets {} · wk 23%".format(
            self.shown_reset(self.now + dt.timedelta(hours=3), False)))
        self.assertNotIn("pace", lines[1])

        self.write_codex([
            {"label": "weekly", "window_minutes": "nope", "used_percent": 36,
             "resets_at": iso(resets_for_pace(self.now, WEEK_MINUTES, 40))},
            {"label": "weekly", "window_minutes": WEEK_MINUTES, "used_percent": 12,
             "resets_at": "not-a-time"},
        ])
        codex = self.run_statusline({"model": {"display_name": "Opus 5.5"}},
                                    USAGE_OPTIMIZER_CODEX="auto")[1]
        self.assertEqual(codex, "Codex wk 36% resets {} · wk 12%".format(
            self.shown_reset(resets_for_pace(self.now, WEEK_MINUTES, 40), True)))
        self.assertNotIn("pace", codex)

        expired = statusline._claude_text(
            None, None, [{"name": "Fable", "expired": True}], False,
            now=self.now, include_pace=True)
        self.assertEqual(expired, "Claude Fable ? /usage")
        self.assertNotIn("pace", expired)

    def test_rate_log_does_not_gain_a_pace_field(self):
        week_at = resets_for_pace(self.now, WEEK_MINUTES, 31)
        five_at = self.now + dt.timedelta(hours=3)
        scoped = [{"kind": "weekly_scoped", "name": "Fable", "used_percentage": 7,
                   "resets_at": iso(week_at)}]
        data = self.claude_data(five_at=five_at, week_at=week_at, scoped=scoped)

        def fields(pace):
            directory = os.path.join(self.root, "log-" + pace)
            os.makedirs(directory)
            self.run_statusline(data, CLAUDE_USAGE_DIR=directory, USAGE_OPTIMIZER_PACE=pace)
            with open(os.path.join(directory, "claude-latest.json"), encoding="utf-8") as handle:
                latest = json.load(handle)
            with open(os.path.join(directory, "claude-rate.jsonl"), encoding="utf-8") as handle:
                history = handle.read()
            self.assertNotIn("pace", history)
            self.assertEqual(json.loads(history), latest)
            return {key: latest[key] for key in ("five_hour", "seven_day", "scoped", "model", "session_id")}

        on = fields("on")
        off = fields("off")
        self.assertEqual(on, off)
        self.assertEqual(on["five_hour"], {"used_percentage": 9, "resets_at": iso(five_at)})
        self.assertEqual(on["seven_day"], {"used_percentage": 23, "resets_at": iso(week_at)})
        self.assertEqual(on["scoped"], [{"kind": "weekly_scoped", "name": "Fable",
                                         "used_percentage": 7, "resets_at": iso(week_at)}])
        self.assertEqual(set(on["five_hour"]), {"used_percentage", "resets_at"})


if __name__ == "__main__":
    unittest.main()
