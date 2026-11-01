import datetime as dt
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import time
import unittest
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUSLINE = os.path.join(ROOT, "bin", "claude-statusline")
UTC = dt.timezone.utc


def load_statusline():
    loader = importlib.machinery.SourceFileLoader("claude_statusline_eta_tested", STATUSLINE)
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


statusline = load_statusline()


class TurnEtaTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.state = os.path.join(self._tmp.name, "state")
        os.makedirs(os.path.join(self.state, "turns", "open"))
        self.write_json(os.path.join(self.state, "claude-calibration.json"), {"pct_per_usd": 0.04})
        patcher = mock.patch.dict(os.environ, {"LANES_STATE": self.state, "USAGE_OPTIMIZER_TURNS": "on"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.now = dt.datetime.now(UTC)

    def write_json(self, path, value):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(value, handle)

    def stamp(self, value):
        return value.isoformat().replace("+00:00", "Z")

    def write_turn(self, minutes_ago=12, **fields):
        # The turn opened 12 minutes ago unless told otherwise, so the elapsed time is about 12.0 minutes.
        turn = {"turn_id": "t-current", "session_id": "s1", "cost_start_usd": 1.0,
                "started_at": self.stamp(self.now - dt.timedelta(minutes=minutes_ago))}
        turn.update(fields)
        self.write_json(os.path.join(self.state, "turns", "open", "s1.json"), turn)

    def write_run(self, name, started, **meta):
        folder = os.path.join(self.state, "runs", started.strftime("%Y%m%d-%H%M%S") + "-" + name)
        meta.setdefault("started_at", self.stamp(started))
        self.write_json(os.path.join(folder, "meta.json"), dict(meta, lane="luna"))

    def segment(self):
        return statusline._turn_segment({"session_id": "s1", "cost": {"total_cost_usd": 2.0}})

    def test_estimate_in_the_future_gives_eta_minutes(self):
        self.write_turn(eta={"elapsed_minutes": 10, "remaining_minutes": 10, "factor": 2})
        self.assertEqual(self.segment(), "ETA ~18m ≈0.04% wk")

    def test_missing_factor_uses_time_factor_then_one(self):
        self.write_turn(time_factor=2, eta={"elapsed_minutes": 10, "remaining_minutes": 10})
        self.assertEqual(self.segment(), "ETA ~18m ≈0.04% wk")
        self.write_turn(eta={"elapsed_minutes": 10, "remaining_minutes": 10})
        self.assertEqual(self.segment(), "ETA ~8m ≈0.04% wk")

    def test_overrun_estimate_falls_back_to_history(self):
        self.write_turn(eta={"elapsed_minutes": 10, "remaining_minutes": 1, "factor": 1},
                        history_minutes=[30, 40, 50, 60, 70, 80, 90, 100])
        # Estimate: 10 + 1 - 12 is negative. History: 8 longer turns, median 65, so about 53 minutes to go.
        self.assertEqual(self.segment(), "ETA ~53m ≈0.04% wk")

    def test_eight_longer_turns_give_the_median_rule(self):
        self.write_turn(history_minutes=[5, 20, 25, 30, 35, 40, 45, 50, 60])
        # Longer than 12 minutes: 20 to 60, eight of them, median 37.5, so about 25.5 minutes to go.
        self.assertEqual(self.segment(), "ETA ~26m ≈0.04% wk")

    def test_fewer_longer_turns_or_no_history_give_the_elapsed_time(self):
        self.write_turn()
        self.assertEqual(self.segment(), "ETA ~13m ≈0.04% wk")
        self.write_turn(history_minutes=[20, 20, 20, 20, 20, 20, 20, 5])
        self.assertEqual(self.segment(), "ETA ~13m ≈0.04% wk")
        self.write_turn(minutes_ago=0.3)
        self.assertEqual(self.segment(), "ETA ~1m ≈0.04% wk")

    def test_lane_run_in_flight_with_a_later_eta_raises_the_eta(self):
        self.write_turn()
        self.write_run("a", self.now - dt.timedelta(minutes=1), eta_s=30 * 60)
        # The lane run has 30 minutes to go, more than the turn's 12.
        self.assertEqual(self.segment(), "ETA ~29m ≈0.04% wk")
        # A finished run, and one that started before the session did, count for nothing; they would give 58 and 50.
        self.write_run("done", self.now - dt.timedelta(minutes=2), eta_s=60 * 60, ended_at=self.stamp(self.now))
        self.write_run("early", self.now - dt.timedelta(minutes=10), eta_s=60 * 60)
        self.write_turn(session_started_at=self.stamp(self.now - dt.timedelta(minutes=5)))
        self.assertEqual(self.segment(), "ETA ~29m ≈0.04% wk")

    def test_under_a_minute_reads_less_than_1m(self):
        self.write_turn(eta={"elapsed_minutes": 12, "remaining_minutes": 0.2, "factor": 1})
        self.assertEqual(self.segment(), "ETA <1m ≈0.04% wk")

    def test_hours_read_as_hours_and_minutes(self):
        self.write_turn(eta={"elapsed_minutes": 12, "remaining_minutes": 65, "factor": 1})
        # 77 minutes in all, 12 of them spent: 65 to go.
        self.assertEqual(self.segment(), "ETA ~1h05 ≈0.04% wk")

    def test_old_run_folders_are_never_opened(self):
        self.write_turn()
        runs = os.path.join(self.state, "runs")
        for index in range(3000):
            os.makedirs(os.path.join(runs, "20200101-000000-luna-{:04d}".format(index)))
        self.write_run("recent", self.now - dt.timedelta(minutes=1), eta_s=30 * 60)
        opened = []
        real_open = open

        def counting_open(path, *args, **kwargs):
            opened.append(str(path))
            return real_open(path, *args, **kwargs)

        with mock.patch("builtins.open", side_effect=counting_open):
            self.assertEqual(self.segment(), "ETA ~29m ≈0.04% wk")
        meta_reads = [path for path in opened if path.endswith("meta.json")]
        self.assertEqual(len(meta_reads), 1, meta_reads[:5])
        self.assertIn("recent", meta_reads[0])
        # The statusline runs every 10 s; the turn's own work must stay well inside its budget even with 3,000 folders.
        started = time.perf_counter()
        self.segment()
        self.assertLess(time.perf_counter() - started, 0.15)


if __name__ == "__main__":
    unittest.main()
