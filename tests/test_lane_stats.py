import contextlib
import datetime
import importlib.machinery
import importlib.util
import io
import json
import math
import os
import random
import shutil
import subprocess
import sys
import unittest
import uuid
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "bin", "lane-stats")
loader = importlib.machinery.SourceFileLoader("lane_stats_tested", SCRIPT)
stats = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
loader.exec_module(stats)


class LaneStatsTests(unittest.TestCase):
    def setUp(self):
        self.old_env = os.environ.copy()
        self.temp = os.path.join(os.path.dirname(__file__), ".lane-stats-{}-{}".format(
            os.getpid(), uuid.uuid4().hex))
        os.mkdir(self.temp)
        self.state = os.path.join(self.temp, "lanes")
        os.makedirs(os.path.join(self.state, "runs"))
        os.environ["LANES_STATE"] = self.state
        os.environ["PYTHONUTF8"] = "1"
        self.catalog_path = os.path.join(self.temp, "arms.json")
        os.environ["LANES_ARMS"] = self.catalog_path
        os.environ["LANES_ARMS_LOCAL"] = os.path.join(self.temp, "arms.local.json")
        os.environ["LANES_MACHINE"] = "this-machine"
        # The usage mode setting: no real ~/.config/lanes/mode, no inherited USAGE_OPTIMIZER_MODE.
        self.config = os.path.join(self.temp, "config")
        os.environ["LANES_CONFIG"] = self.config
        os.environ.pop("USAGE_OPTIMIZER_MODE", None)
        self.catalog = {
            "lanes": {lane: {"model": model, "provider": provider} for lane, model, provider in (
                ("luna", "luna", "codex"), ("sol", "sol", "codex"),
                ("sonnet", "sonnet", "claude"), ("gemini", "gemini-3.8-flash-medium", "gemini"))},
            "providers": {"codex": {"scarcity": 0.3, "prior_plan": "prolite",
                                      "plan_scale": {"prolite": 1.0, "plus": 5.0}},
                          "claude": {"scarcity": 1.0}, "gemini": {"scarcity": 0.2}},
            "explore": {"min_runs": 2, "floor": 0.2, "half_life_days": 60, "shrink": 2.0,
                        "review_points": 0.01, "fix_points_per_minute": 0.003,
                        "targets": {"mechanical": 0.8, "hard": 0.5, "research": 0.7},
                        "pace": {"low_pct": 60, "high_pct": 90, "low_factor": 0.25, "high_factor": 3.0},
                        "exclude_weekly_pct": 95, "exclude_5h_pct": 90, "claude_guard_pct": 85,
                        "lock": {"leaning_p": 0.5, "leaning_runs": 4, "locked_p": 0.8, "locked_runs": 8},
                        "measured_weight": 4, "measured_shrink": 4.0, "measured_min_n": 10},
            "arms": [{"lane": lane, "model": self_model, "effort": effort, "status": "active",
                      "classes": ["mechanical", "hard", "research"], "weight": 1.0,
                      "prior_pct": cost, "prior_usable": usable}
                     for lane, self_model, effort, cost, usable in (
                         ("luna", "luna", "medium", 0.1, 0.7), ("sol", "sol", "xhigh", 0.8, 0.8),
                         ("sonnet", "sonnet", "high", 0.1, 0.8),
                         ("gemini", "gemini-3.8-flash-medium", "medium", 0.6, 0.5))]}
        self.save_catalog()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old_env)
        shutil.rmtree(self.temp)

    def run_cli(self, *args):
        env = os.environ.copy()
        env["LANES_STATE"] = self.state
        env["PYTHONUTF8"] = "1"
        return subprocess.run([sys.executable, SCRIPT] + list(args), cwd=ROOT, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", check=False)

    def save_catalog(self):
        with open(self.catalog_path, "w", encoding="utf-8") as stream:
            json.dump(self.catalog, stream)

    def direct_cli(self, *args, **kwargs):
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(stats, "read_live_usage", return_value=kwargs.get("live", {})), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = stats.main(list(args))
        self.assertEqual(code, 0, stderr.getvalue())
        return stdout.getvalue()

    def context(self, live=None, class_name="hard"):
        args = stats.build_parser().parse_args(["pick", "--class", "hard", "--no-usage"])
        with mock.patch.object(stats, "read_live_usage", return_value=live or {}):
            return stats.model_context(args, class_name)

    def add_run(self, name, lane="luna", model=None, effort="medium", class_name="mechanical",
                started="2026-10-17T00:00:00Z", ended="2026-10-17T00:02:00Z", verdict="OK",
                session_id=None, usage=None, ledger=True, duration_s=120, tag=None, eta_s=None,
                peak_mem_mb=None, verify=False):
        run_dir = os.path.join(self.state, "runs", name)
        os.makedirs(run_dir)
        row = {"run_dir": run_dir, "lane": lane, "provider": None, "model": model or lane,
               "effort": effort, "class": class_name, "tag": tag, "ro": False, "resume": None,
               "started_at": started, "ended_at": ended, "duration_s": duration_s,
               "verdict": verdict, "exit_code": 0, "session_id": session_id,
               "usage": usage, "eta_s": eta_s, "peak_mem_mb": peak_mem_mb}
        if verify:
            row["verify"] = True
        with open(os.path.join(run_dir, "meta.json"), "w", encoding="utf-8") as stream:
            json.dump(row, stream)
        if ledger:
            with open(os.path.join(self.state, "ledger.jsonl"), "a", encoding="utf-8") as stream:
                stream.write(json.dumps(row) + "\n")
        return run_dir

    def usage(self, before, after, tokens=100, cost=None, reset_before="2026-10-23T00:00:00Z",
              reset_after=None, five_hour=None):
        def reading(percent, reset, five):
            windows = [{"label": "weekly", "used_percent": percent, "resets_at": reset}]
            if five is not None:
                windows.append({"label": "5h", "used_percent": five, "resets_at": "2026-10-17T05:00:00Z"})
            return {"observed_at": "2026-10-17T00:00:00Z", "age_seconds": 1, "status": "ok",
                    "windows": windows}
        return {"before": reading(before, reset_before, five_hour),
                "after": reading(after, reset_after or reset_before,
                                 five_hour + 1 if five_hour is not None else None),
                "tokens": {"input": 0, "cached": 0, "output": 0, "total": tokens},
                "list_usd": cost}

    def add_review(self, run_dir, outcome="accepted", reviewed_at="2026-10-17T12:00:00Z", fix_minutes=None):
        review = {"outcome": outcome, "note": "", "fix_minutes": fix_minutes, "reviewed_at": reviewed_at}
        with open(os.path.join(run_dir, "review.json"), "w", encoding="utf-8") as stream:
            json.dump(review, stream)
        return review

    def test_review_accepts_path_name_session_and_last_and_latest_wins(self):
        by_path = self.add_run("run-path")
        by_name = self.add_run("run-name")
        by_session = self.add_run("run-session", session_id="session-123", ledger=False)
        by_ledger_session = self.add_run("run-ledger-session", session_id="ledger-session")
        with open(os.path.join(by_ledger_session, "meta.json"), "r", encoding="utf-8") as stream:
            meta = json.load(stream)
        meta["session_id"] = None
        with open(os.path.join(by_ledger_session, "meta.json"), "w", encoding="utf-8") as stream:
            json.dump(meta, stream)
        by_last = self.add_run("run-last")

        for selector, expected, outcome in (
                (by_path, "run-path", "accepted"),
                ("run-name", "run-name", "fixed"),
                ("session-123", "run-session", "rework"),
                ("ledger-session", "run-ledger-session", "accepted"),
                ("last", "run-last", "rejected")):
            result = self.run_cli("review", selector, "--outcome", outcome,
                                  "--note", "checked", "--fix-minutes", "3")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "reviewed {}: {}".format(expected, outcome))

        result = self.run_cli("review", "run-path", "--outcome", "fixed")
        self.assertEqual(result.returncode, 0, result.stderr)
        with open(os.path.join(by_path, "review.json"), "r", encoding="utf-8") as stream:
            self.assertEqual(json.load(stream)["outcome"], "fixed")
        with open(os.path.join(self.state, "reviews.jsonl"), "r", encoding="utf-8") as stream:
            self.assertEqual(len(stream.readlines()), 6)
        unknown = self.run_cli("review", "missing", "--outcome", "accepted")
        self.assertEqual(unknown.returncode, 2)
        self.assertIn("unknown RUN: missing", unknown.stderr)

    def test_report_groups_percentages_medians_and_malformed_lines(self):
        first = self.add_run("r1", started="2026-10-17T00:00:00Z", ended="2026-10-17T00:02:00Z",
                             usage=self.usage(10, 12, tokens=200, five_hour=4))
        second = self.add_run("r2", started="2026-10-17T01:00:00Z", ended="2026-10-17T01:04:00Z",
                              duration_s=240,
                              verdict="PARTIAL", usage=self.usage(20, 23, tokens=100, cost=0.02,
                                                                  five_hour=10))
        self.add_review(first, "accepted")
        self.add_review(second, "fixed")
        with open(os.path.join(self.state, "reviews.jsonl"), "w", encoding="utf-8") as stream:
            stream.write(json.dumps({"run_dir": first, "outcome": "accepted", "reviewed_at": "2026-10-17T12:00:00Z"}) + "\n")
            stream.write(json.dumps({"run_dir": second, "outcome": "fixed", "reviewed_at": "2026-10-17T12:00:00Z"}) + "\n")
        with open(os.path.join(self.state, "ledger.jsonl"), "a", encoding="utf-8") as stream:
            stream.write("{ malformed line\n")

        result = self.run_cli("report", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        groups = json.loads(result.stdout)
        self.assertEqual(len(groups), 1)
        row = groups[0]
        self.assertEqual(row["runs"], 2)
        self.assertEqual(row["ok%"], 50.0)
        self.assertEqual(row["reviewed"], 2)
        self.assertEqual(row["accepted%"], 50.0)
        self.assertEqual(row["usable%"], 100.0)
        self.assertEqual(row["med_min"], 3.0)
        self.assertEqual(row["med_tokens"], 150.0)
        self.assertAlmostEqual(row["wk%/run"], 2.5)
        self.assertAlmostEqual(row["wk%/usable"], 2.5)
        self.assertAlmostEqual(row["$list/usable"], 0.01)
        self.assertEqual(row["wave_count"], 2)
        self.assertAlmostEqual(row["attributed_percent"]["weekly"], 5)
        self.assertAlmostEqual(row["attributed_percent"]["5h"], 2)
        self.assertIn("malformed lines skipped: 1", result.stderr)

        # The review journal wins when its timestamp is newer than the per-run snapshot.
        with open(os.path.join(self.state, "reviews.jsonl"), "a", encoding="utf-8") as stream:
            stream.write(json.dumps({"run_dir": first, "outcome": "rejected", "reviewed_at": "2026-10-18T00:00:00Z"}) + "\n")
        result = self.run_cli("report", "--json", "--since", "2026-10-17", "--by", "lane")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)[0]["usable%"], 50.0)

    def test_verify_runs_change_no_pick_report_estimate_or_review(self):
        def snapshot():
            report = json.loads(self.run_cli("report", "--json").stdout)
            pick = json.loads(self.run_cli("pick", "--class", "hard", "--no-usage", "--seed", "1", "--json").stdout)
            recommend = json.loads(self.run_cli("recommend", "--class", "hard", "--draws", "100", "--no-usage",
                                                "--seed", "1", "--json").stdout)["classes"]["hard"]
            # Recency weights follow the wall clock, so only the decision is compared.
            recommend = (recommend["status"], recommend["reviewed"], recommend["p_best"], recommend.get("arm"))
            runs = stats.load_runs(self.state)[0]
            eta = stats.estimate_eta(runs, self.catalog, "luna", None, "medium", "hard", None, self.eta_now())
            return report, (pick["arms"], pick["mode"], pick["eta"]), recommend, eta, stats.locate_run("last", self.state)

        for index in range(3):
            run = self.add_run("unit-{}".format(index), class_name="hard", duration_s=600,
                               usage=self.usage(10 + index, 11 + index, cost=0.01))
            self.add_review(run)
        before = snapshot()
        # Same lane, effort and class as the units, in the ledger and as a meta.json alone; neither may count.
        self.add_run("verify-ledger", class_name="hard", duration_s=60, tag="verify", verify=True,
                     started="2026-10-18T00:00:00Z", ended="2026-10-18T00:01:00Z",
                     usage=self.usage(20, 30, cost=1.0))
        self.add_run("verify-meta", class_name=None, duration_s=60, tag="verify", verify=True, ledger=False,
                     verdict="PARTIAL", started="2026-10-18T01:00:00Z", ended="2026-10-18T01:01:00Z")
        self.assertEqual(snapshot(), before)
        # "last" names the newest unit, not the newer verify runs.
        result = self.run_cli("review", "last", "--outcome", "accepted")
        self.assertEqual(result.returncode, 0, result.stderr)
        with open(os.path.join(self.state, "runs", "unit-2", "review.json"), encoding="utf-8") as stream:
            self.assertEqual(json.load(stream)["outcome"], "accepted")
        self.assertFalse(os.path.exists(os.path.join(self.state, "runs", "verify-ledger", "review.json")))

    def test_report_by_place_groups_runs_and_counts_a_missing_place_as_local(self):
        self.add_run("p1", started="2026-10-17T00:00:00Z")
        self.add_run("p2", started="2026-10-17T01:00:00Z")
        for name, place in (("p3", "cloud"), ("p4", "subagent"), ("p5", "cloud")):
            run_dir = self.add_run(name, started="2026-10-17T02:00:00Z", ledger=False)
            with open(os.path.join(run_dir, "meta.json"), encoding="utf-8") as stream:
                row = json.load(stream)
            row["place"] = place
            with open(os.path.join(self.state, "ledger.jsonl"), "a", encoding="utf-8") as stream:
                stream.write(json.dumps(row) + "\n")

        result = self.run_cli("report", "--by", "place", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        counts = {row["place"]: row["runs"] for row in json.loads(result.stdout)}
        self.assertEqual(counts, {"local": 2, "cloud": 2, "subagent": 1})

        result = self.run_cli("report", "--by", "place")
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = {line.split()[0]: line.split() for line in result.stdout.splitlines()
                if line.split() and line.split()[0] in ("local", "cloud", "subagent")}
        self.assertEqual(set(rows), {"local", "cloud", "subagent"})
        self.assertEqual({place: row[1] for place, row in rows.items()},
                         {"local": "2", "cloud": "2", "subagent": "1"})

    def test_report_footer_counts_unfinished_runs(self):
        run_dir = self.add_run("unfinished", ended=None, ledger=False)
        result = self.run_cli("report", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("unfinished runs: 1 (finish with lane --recover)", result.stderr)
        meta_path = os.path.join(run_dir, "meta.json")
        with open(meta_path, "r", encoding="utf-8") as stream:
            meta = json.load(stream)
        meta["recovered"] = True
        with open(meta_path, "w", encoding="utf-8") as stream:
            json.dump(meta, stream)
        result = self.run_cli("report", "--json")
        self.assertNotIn("unfinished runs:", result.stderr)

    def test_legacy_runs_without_ledger_are_included_with_provider_inferred(self):
        run_dir = self.add_run("legacy", lane="luna", model="gpt-6-luna", ledger=False,
                               usage=None, class_name=None)
        result = self.run_cli("report", "--json", "--by", "provider,lane")
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = json.loads(result.stdout)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["provider"], "codex")
        self.assertEqual(rows[0]["runs"], 1)
        self.assertEqual(rows[0]["reviewed"], 0)
        self.assertEqual(rows[0]["ok%"], 100.0)
        self.assertIn("runs without usage: 1", result.stderr)

        result = self.run_cli("review", run_dir, "--outcome", "accepted")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.run_cli("review", "legacy", "--outcome", "fixed")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.run_cli("report", "--json", "--by", "lane")
        self.assertEqual(json.loads(result.stdout)[0]["usable%"], 100.0)

    def test_wave_attribution_splits_by_model_rate_skips_reset_and_counts_solo_run(self):
        def times(start_minute, length=10):
            start = datetime.datetime(2026, 10, 17, 0, 0, tzinfo=datetime.timezone.utc)
            start += datetime.timedelta(minutes=start_minute)
            end = start + datetime.timedelta(minutes=length)
            return start.strftime("%Y-%m-%dT%H:%M:%SZ"), end.strftime("%Y-%m-%dT%H:%M:%SZ")

        def record(name, lane, offset, before, after, reset_after=None):
            start, end = times(offset, 10 if lane == "luna" else 6)
            return self.add_run(name, lane=lane, model="gpt-6.1-sol" if lane == "sol" else "gpt-6-luna",
                                started=start, ended=end,
                                usage=self.usage(before, after, tokens=100, reset_before="reset-a",
                                                 reset_after=reset_after))

        record("wave-a-luna", "luna", 0, 10, 20)
        record("wave-a-sol", "sol", 2, 11, 25)
        record("wave-reset-luna", "luna", 20, 30, 40)
        record("wave-reset-sol", "sol", 22, 31, 42, reset_after="reset-b")
        record("solo-luna", "luna", 40, 40, 45)

        result = self.run_cli("report", "--json", "--by", "lane")
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = {row["lane"]: row for row in json.loads(result.stdout)}
        self.assertAlmostEqual(rows["luna"]["attributed_percent"]["weekly"], 5 + 15 / 21)
        self.assertAlmostEqual(rows["sol"]["attributed_percent"]["weekly"], 15 * 20 / 21)
        self.assertEqual(rows["luna"]["wave_count"], 2)
        self.assertEqual(rows["sol"]["wave_count"], 1)

    def test_reset_time_jitter_is_the_same_window_but_a_moved_reset_is_not(self):
        # Codex reports one reset a second apart between reads (seen 2026-10-17).
        self.add_run("jitter", started="2026-10-17T00:00:00Z", ended="2026-10-17T00:10:00Z",
                     usage=self.usage(0, 1, reset_before="2026-10-23T11:25:25Z", reset_after="2026-10-23T11:25:24Z"))
        self.add_run("moved", started="2026-10-17T01:00:00Z", ended="2026-10-17T01:10:00Z", lane="sol",
                     usage=self.usage(90, 2, reset_before="2026-10-17T01:05:00Z", reset_after="2026-10-24T01:05:00Z"))
        result = self.run_cli("report", "--json", "--by", "lane")
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = {row["lane"]: row for row in json.loads(result.stdout)}
        self.assertAlmostEqual(rows["luna"]["attributed_percent"]["weekly"], 1)
        self.assertNotIn("weekly", rows["sol"]["attributed_percent"])

    def test_explore_alias_ignores_target_and_matches_pick(self):
        for lane, count in (("gemini", 2), ("luna", 1), ("haiku", 1), ("sonnet", 1), ("glm", 1)):
            for index in range(count):
                run_dir = self.add_run("{}-{}".format(lane, index), lane=lane,
                                       class_name="mechanical", started="2026-10-17T00:00:00Z")
                self.add_review(run_dir, "accepted" if index == 0 else "rework")

        result = self.run_cli("explore", "--class", "mechanical", "--target", "2", "--no-usage", "--seed", "1", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        picked = self.run_cli("pick", "--class", "mechanical", "--no-usage", "--seed", "1", "--json")
        self.assertEqual(picked.returncode, 0, picked.stderr)
        other = self.run_cli("explore", "--class", "mechanical", "--target", "999", "--no-usage", "--seed", "1", "--json")
        self.assertEqual(other.returncode, 0, other.stderr)
        for output in (picked.stdout, other.stdout):
            self.assertEqual(json.loads(result.stdout)["arms"], json.loads(output)["arms"])
            self.assertEqual(json.loads(result.stdout)["mode"], json.loads(output)["mode"])

    def test_forced_picks_unexplored_arm_using_reviews_across_classes(self):
        self.catalog["arms"] = self.catalog["arms"][:2]
        self.save_catalog()
        for index in range(2):
            run = self.add_run("measured-{}".format(index), class_name="research")
            self.add_review(run)
        # Unreviewed runs do not satisfy forced exploration.
        self.add_run("not-reviewed", lane="sol", effort="xhigh")
        result = self.run_cli("pick", "--class", "hard", "--no-usage", "--seed", "1", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        row = json.loads(result.stdout)
        self.assertEqual(row["mode"], "forced")
        self.assertEqual(row["arms"], ["sol/sol/xhigh"])
        self.assertRegex(row["pick_id"], r"^p-\d{8}-\d{6}-[0-9a-f]{4}$")
        self.assertIn("-C <DIR> -b <BRIEF> -e xhigh --class hard --pick " + row["pick_id"], row["run_lines"][0])
        with open(os.path.join(self.state, "picks.jsonl"), encoding="utf-8") as stream:
            logged = json.loads(stream.read())
        self.assertNotIn("run_lines", logged)
        self.assertEqual(logged, {key: value for key, value in row.items() if key != "run_lines"})
        self.assertLessEqual(len(row["top"]), 5)

    def test_floor_thompson_and_seeded_choices(self):
        self.catalog["explore"]["min_runs"] = 0
        for floor, expected in ((1.0, "floor"), (0.0, "thompson")):
            self.catalog["explore"]["floor"] = floor
            self.save_catalog()
            outputs = []
            for _ in range(2):
                result = self.run_cli("pick", "--class", "hard", "--no-usage", "--seed", "1", "--json")
                self.assertEqual(result.returncode, 0, result.stderr)
                outputs.append(json.loads(result.stdout))
            self.assertEqual(outputs[0]["mode"], expected)
            self.assertEqual(outputs[0]["arms"], outputs[1]["arms"])
            self.assertEqual(outputs[0]["pick_id"][-4:], outputs[1]["pick_id"][-4:])

    def test_exploration_weights_are_weight_over_sqrt_points(self):
        rows = [{"entry": {"weight": 4}, "points": 4, "reviewed_all": 0},
                {"entry": {"weight": 1}, "points": 1, "reviewed_all": 0}]
        rng = mock.Mock(wraps=random.Random(1))
        chosen, mode = stats.choose_arm(rows, self.catalog["explore"], "hard", rng)
        self.assertEqual(mode, "forced")
        self.assertIn(chosen, rows)
        self.assertEqual(rng.choices.call_args[1]["weights"], [4 / math.sqrt(4), 1 / math.sqrt(1)])
        rng.random.assert_not_called()

    def test_unlabelled_runs_count_on_current_plan_and_new_lanes_are_attributed(self):
        self.catalog["lanes"]["worker"] = {"model": "worker-model", "provider": "codex"}
        self.catalog["arms"].append(dict(self.catalog["arms"][0], lane="worker", model="worker-model"))
        self.save_catalog()
        for index in range(2):
            self.add_run("worker-{}".format(index), lane="worker", model="worker-model",
                         started="2026-10-17T0{}:00:00Z".format(index), ended="2026-10-17T0{}:02:00Z".format(index),
                         usage=self.usage(10, 12))
        row = self.context({"codex": {"plan_type": "plus"}})["stats"][-1]
        self.assertEqual((row["tier"], row["cost"]), ("measured", 2.0))

    def test_pair_uses_other_lane_and_provider_and_quotes_run_arguments(self):
        result = self.run_cli("pick", "--class", "hard", "--pair", "--approved", "test, now", "--no-usage", "--seed", "1",
                              "--dir", "/work/with space", "--brief", "/brief/with space.md", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        record = json.loads(result.stdout)
        self.assertEqual(record["mode"], "pair")
        lanes = [identity.split("/")[0] for identity in record["arms"]]
        self.assertNotEqual(lanes[0], lanes[1])
        self.assertNotEqual(self.catalog["lanes"][lanes[0]]["provider"], self.catalog["lanes"][lanes[1]]["provider"])
        for line in record["run_lines"]:
            self.assertIn("-C '/work/with space' -b '/brief/with space.md'", line)
            self.assertIn("--tag pair-" + record["pick_id"][-4:], line)
        single = self.run_cli("pick", "--class", "hard", "--pair", "--approved", "test, now", "--exclude", "sol,sonnet,gemini", "--no-usage")
        self.assertEqual(single.returncode, 2)

    def test_pair_can_fall_back_to_same_provider_and_excludes_lanes(self):
        result = self.run_cli("pick", "--class", "hard", "--pair", "--approved", "test, now", "--exclude", "sonnet,gemini",
                              "--no-usage", "--seed", "1", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual({arm.split("/")[0] for arm in json.loads(result.stdout)["arms"]}, {"luna", "sol"})

    def test_repeated_exclude_flags_all_apply(self):
        # A second --exclude used to replace the first, so "--exclude gemini --exclude glm" let gemini through.
        result = self.run_cli("pick", "--class", "hard", "--pair", "--approved", "test, now", "--exclude", "sonnet", "--exclude", "gemini",
                              "--no-usage", "--seed", "1", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual({arm.split("/")[0] for arm in json.loads(result.stdout)["arms"]}, {"luna", "sol"})

    def picks(self):
        path = os.path.join(self.state, "picks.jsonl")
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]

    def test_pair_without_approval_exits_2_and_records_no_pick(self):
        for approval in ([], ["--approved", ""], ["--approved", "   "]):
            result = self.run_cli("pick", "--class", "hard", "--pair", "--no-usage", "--seed", "1", *approval)
            self.assertEqual(result.returncode, 2, result.stdout)
            self.assertEqual(result.stdout, "")
            self.assertIn("A pair is a capability test: it runs one unit twice. Run one only after the user approves it, "
                          "and pass --approved \"<who, when>\".", result.stderr)
        self.assertEqual(self.picks(), [])

    def test_pair_with_approval_records_the_note(self):
        result = self.run_cli("pick", "--class", "hard", "--pair", "--approved", "the user, 2026-10-20 09:00",
                              "--no-usage", "--seed", "1", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["approved"], "the user, 2026-10-20 09:00")
        picks = self.picks()
        self.assertEqual(len(picks), 1)
        self.assertEqual(picks[0]["approved"], "the user, 2026-10-20 09:00")

    def test_plain_pick_needs_no_approval_and_records_none(self):
        result = self.run_cli("pick", "--class", "hard", "--no-usage", "--seed", "1", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("approved", self.picks()[0])
        refused = self.run_cli("pick", "--class", "hard", "--approved", "x", "--no-usage", "--seed", "1")
        self.assertEqual(refused.returncode, 2)
        self.assertEqual(len(self.picks()), 1)

    def test_posterior_uses_recency_class_shrink_and_fixed_as_usable(self):
        now = stats.parse_time("2026-10-17T00:00:00Z")
        old = (now - datetime.timedelta(days=60)).isoformat()
        row = {"entry": {"prior_usable": 0.6}, "reviews": [
            ({"ended_at": old, "class": "hard"}, {"outcome": "fixed"}),
            ({"started_at": now.isoformat(), "class": "hard"}, {"outcome": "rejected"}),
            ({"ended_at": now.isoformat(), "class": "research"}, {"outcome": "accepted"})]}
        alpha, beta, reviewed = stats.posterior(row, "hard", self.catalog["explore"], now)
        pooled = (1.5 + 2 * 0.6) / (2.5 + 2)
        self.assertAlmostEqual(alpha, 0.5 + 2 * pooled + 0.5)
        self.assertAlmostEqual(beta, 0.5 + 2 * (1 - pooled) + 1)
        self.assertEqual(reviewed, 2)

    def test_thompson_uses_target_then_cost_per_usable_or_highest_sample(self):
        rows = [{"arm": "cheap", "alpha": 1, "beta": 1, "points": 0.1},
                {"arm": "good", "alpha": 1, "beta": 1, "points": 0.5}]
        rng = mock.Mock()
        rng.betavariate.side_effect = [0.4, 0.7]
        self.assertEqual(stats.thompson_choice(rows, 0.5, rng)["arm"], "good")
        rng.betavariate.side_effect = [0.6, 0.9]
        self.assertEqual(stats.thompson_choice(rows, 0.5, rng)["arm"], "cheap")
        rng.betavariate.side_effect = [0.2, 0.3]
        self.assertEqual(stats.thompson_choice(rows, 0.5, rng)["arm"], "good")

    def test_cost_tier_a_recency_and_plan_change_drops_measurements(self):
        for index, delta in enumerate((1, 3)):
            usage = self.usage(10, 10 + delta)
            usage["after"]["plan"] = "prolite"
            self.add_run("cost-{}".format(index), started="2026-10-17T0{}:00:00Z".format(index),
                         ended="2026-10-17T0{}:02:00Z".format(index), usage=usage)
        context = self.context()
        row = context["stats"][0]
        self.assertEqual(row["tier"], "measured")
        weights = [stats.recency_weight(run, self.catalog["explore"], context["now"]) for _, run in row["history"]]
        self.assertAlmostEqual(row["cost"], (weights[0] + 3 * weights[1]) / sum(weights))
        changed = self.context({"codex": {"plan_type": "plus"}})["stats"][0]
        self.assertEqual(changed["tier"], "prior")
        self.assertAlmostEqual(changed["cost"], 0.5)
        usage = self.usage(20, 21)
        usage["before"]["plan"] = "plus"
        self.add_run("latest-plan", started="2026-10-18T01:00:00Z", ended="2026-10-18T01:02:00Z", usage=usage)
        self.assertEqual(self.context()["stats"][0]["tier"], "prior")

    def test_cost_tier_b_uses_three_provider_waves_and_arm_weight(self):
        for index in range(3):
            usage = self.usage(10, 11, tokens=100)
            usage["after"]["plan"] = "prolite"
            self.add_run("wave-{}".format(index), started="2026-10-17T0{}:00:00Z".format(index),
                         ended="2026-10-17T0{}:02:00Z".format(index), usage=usage)
        # The sol arm has tokens but no meter; the 20x token weight matters.
        self.add_run("weight-only", lane="sol", effort="xhigh", usage={"tokens": {"total": 10}})
        rows = self.context()["stats"]
        self.assertEqual(rows[1]["tier"], "calibrated")
        self.assertAlmostEqual(rows[1]["cost"], 2.0)
        self.assertEqual(rows[2]["tier"], "prior")
        changed = self.context({"codex": {"plan_type": "plus"}})["stats"][1]
        self.assertEqual(changed["tier"], "prior")
        self.assertAlmostEqual(changed["cost"], 4.0)

    def test_gemini_calibration_thresholds_and_claude_calibration(self):
        for index in range(3):
            self.add_run("gem-{}".format(index), lane="gemini", model="outside-catalog", effort="low",
                         started="2026-10-17T0{}:00:00Z".format(index), ended="2026-10-17T0{}:02:00Z".format(index),
                         usage=self.usage(10, 11, tokens=100))
        self.add_run("gem-weight", lane="gemini", model="gemini-3.8-flash-medium", effort=None,
                     usage={"tokens": {"total": 50}})
        self.add_run("claude-weight", lane="sonnet", effort="high", usage={"list_usd": 2})
        self.assertEqual(self.context()["stats"][2]["tier"], "prior")
        path = os.path.join(self.state, "claude-calibration.json")
        with open(path, "w", encoding="utf-8") as stream:
            json.dump({"pct_per_usd": 0.04}, stream)
        rows = self.context()["stats"]
        self.assertEqual(rows[2]["tier"], "calibrated")
        self.assertAlmostEqual(rows[2]["cost"], 0.08)
        self.assertEqual(rows[3]["tier"], "calibrated")
        self.assertAlmostEqual(rows[3]["cost"], 0.5)
        # Fewer than three waves or less than 2% cannot calibrate a provider.
        runs, _, _ = stats.load_runs(self.state)
        self.assertNotIn("gemini", stats.calibrated_rates(self.state, dict(list(runs.items())[:2]), self.catalog,
                                                          {"codex": "prolite", "gemini": None}))
        for run in runs.values():
            if run.get("usage") and "after" in run["usage"]:
                run["usage"]["after"]["windows"][0]["used_percent"] = 10.1
        self.assertNotIn("gemini", stats.calibrated_rates(self.state, runs, self.catalog,
                                                          {"codex": "prolite", "gemini": None}))

    def test_posterior_uses_measured_usable_and_shrink_once_n_reaches_minimum(self):
        now = stats.parse_time("2026-10-17T00:00:00Z")
        old = (now - datetime.timedelta(days=60)).isoformat()
        reviews = [({"ended_at": old, "class": "hard"}, {"outcome": "fixed"}),
                   ({"started_at": now.isoformat(), "class": "hard"}, {"outcome": "rejected"}),
                   ({"ended_at": now.isoformat(), "class": "research"}, {"outcome": "accepted"})]
        # Pooled: success 0.5 (fixed, 60 days old) + 1 (accepted) = 1.5, failure 1. Class hard: 0.5 and 1.
        block = {"usable": 0.9, "pct_week": 0.2, "recall": 0.8, "n": 12}
        row = {"entry": {"prior_usable": 0.6, "measured": {"hard": block}}, "reviews": reviews}
        alpha, beta, reviewed = stats.posterior(row, "hard", self.catalog["explore"], now)
        pooled = (1.5 + 4 * 0.9) / (2.5 + 4)  # measured weight 4 and usable 0.9 replace 2 and 0.6
        self.assertAlmostEqual(alpha, 0.5 + 4.0 * pooled + 0.5)  # measured_shrink 4.0 replaces shrink 2.0
        self.assertAlmostEqual(beta, 0.5 + 4.0 * (1 - pooled) + 1)
        self.assertEqual(reviewed, 2)
        # Below measured_min_n (10) the benchmark prior is used again.
        block["n"] = 9
        alpha, beta, _ = stats.posterior(row, "hard", self.catalog["explore"], now)
        pooled = (1.5 + 2 * 0.6) / (2.5 + 2)
        self.assertAlmostEqual(alpha, 0.5 + 2.0 * pooled + 0.5)
        self.assertAlmostEqual(beta, 0.5 + 2.0 * (1 - pooled) + 1)
        # A block for another class does not touch hard.
        block["n"] = 12
        row["entry"]["measured"] = {"research": block}
        alpha, beta, _ = stats.posterior(row, "hard", self.catalog["explore"], now)
        self.assertAlmostEqual(alpha, 0.5 + 2.0 * pooled + 0.5)
        self.assertAlmostEqual(beta, 0.5 + 2.0 * (1 - pooled) + 1)

    def test_cost_tier_bench_is_per_class_mean_and_scales_by_plan(self):
        now = stats.parse_time("2026-10-17T00:00:00Z")
        plans = {"codex": "prolite", "claude": None, "gemini": None}
        arm = dict(self.catalog["arms"][0], measured={
            "hard": {"usable": 0.9, "pct_week": 0.2, "recall": 0.8, "n": 12, "plan": "prolite"},
            "research": {"usable": 0.7, "pct_week": 0.4, "recall": 0.6, "n": 12, "plan": "prolite"}})
        self.assertEqual(stats.arm_cost(arm, [], {}, self.catalog, plans, {}, now, "hard"), (0.2, "bench"))
        cost, tier = stats.arm_cost(arm, [], {}, self.catalog, plans, {}, now, "mechanical")
        self.assertEqual(tier, "bench")
        self.assertAlmostEqual(cost, (0.2 + 0.4) / 2)
        # prolite block, plus plan: x plan_scale[plus] / plan_scale[prolite] = x 5.8.
        self.catalog["providers"]["codex"]["plan_scale"]["plus"] = 5.8
        plans["codex"] = "plus"
        cost, tier = stats.arm_cost(arm, [], {}, self.catalog, plans, {}, now, "hard")
        self.assertEqual(tier, "bench")
        self.assertAlmostEqual(cost, 0.2 * 5.8)
        cost, _ = stats.arm_cost(arm, [], {}, self.catalog, plans, {}, now, "mechanical")
        self.assertAlmostEqual(cost, (0.2 + 0.4) / 2 * 5.8)
        # A block without a plan is taken as the current plan.
        arm["measured"] = {"hard": {"usable": 0.9, "pct_week": 0.2, "recall": 0.8, "n": 12}}
        self.assertEqual(stats.arm_cost(arm, [], {}, self.catalog, plans, {}, now, "hard"), (0.2, "bench"))

    def test_cost_tier_measured_local_history_beats_bench(self):
        self.catalog["arms"][0]["measured"] = {"hard": {"usable": 0.9, "pct_week": 0.2, "recall": 0.8, "n": 12}}
        self.save_catalog()
        self.assertEqual(self.context()["stats"][0]["tier"], "bench")
        for index, delta in enumerate((2, 4)):
            self.add_run("bench-local-{}".format(index), started="2026-10-17T0{}:00:00Z".format(index),
                         ended="2026-10-17T0{}:02:00Z".format(index), usage=self.usage(10, 10 + delta))
        context = self.context()
        row = context["stats"][0]
        self.assertEqual(row["tier"], "measured")
        weights = [stats.recency_weight(run, self.catalog["explore"], context["now"]) for _, run in row["history"]]
        self.assertAlmostEqual(row["cost"], (2 * weights[0] + 4 * weights[1]) / sum(weights))

    def test_measured_validation_accepts_numbers_and_rejects_bad_blocks(self):
        def with_measured(block, **explore):
            catalog = json.loads(json.dumps(self.catalog))
            catalog["arms"][0]["measured"] = {"hard": block}
            catalog["explore"].update(explore)
            return catalog

        good = {"usable": 0.94, "pct_week": 0.0054, "recall": 0.89, "n": 36,
                "source": "suite-r 2026-10-20", "plan": "prolite"}
        stats.validate_catalog(with_measured(good))
        stats.validate_catalog(with_measured(dict(good, plan=None)))
        stats.validate_catalog(with_measured(dict(good, usable=0, recall=1, pct_week=0)))
        for block in (dict(good, usable=1.2), dict(good, usable=-0.1), dict(good, recall=1.01),
                      dict(good, pct_week=-0.1), dict(good, n=0), dict(good, n=True),
                      dict(good, usable="0.9"), dict(good, plan=3), dict(good, usable=float("nan")),
                      {"usable": 0.9, "pct_week": 0.2, "recall": 0.8}, 3, ["hard"]):
            with self.assertRaises(ValueError, msg=str(block)):
                stats.validate_catalog(with_measured(block))
        for explore in ({"measured_weight": 0}, {"measured_shrink": -1}, {"measured_min_n": "10"}):
            with self.assertRaises(ValueError, msg=str(explore)):
                stats.validate_catalog(with_measured(good, **explore))
        broken = json.loads(json.dumps(self.catalog))
        del broken["explore"]["measured_min_n"]
        with self.assertRaises(ValueError):
            stats.validate_catalog(broken)

    def test_measured_arm_wins_more_seeded_picks_than_its_benchmark_twin(self):
        self.catalog["explore"]["min_runs"] = 0
        self.catalog["explore"]["floor"] = 0.0
        twin = dict(self.catalog["arms"][0], effort="high")
        self.catalog["arms"] = [self.catalog["arms"][0], twin]
        self.catalog["arms"][0]["measured"] = {"hard": {"usable": 0.95, "pct_week": 0.1, "recall": 0.9, "n": 20}}
        self.save_catalog()
        rows = stats.eligible_arms(self.context(), "hard")
        self.assertEqual(len(rows), 2)
        # Measured: Beta(0.5 + 4 * 0.95, 0.5 + 4 * 0.05) = Beta(4.3, 0.7). Twin: Beta(0.5 + 2 * 0.7, 0.5 + 2 * 0.3) = Beta(1.9, 1.1).
        wins = {"medium": 0, "high": 0}
        for seed in range(300):
            chosen, mode = stats.choose_arm(rows, self.catalog["explore"], "hard", random.Random(seed))
            self.assertEqual(mode, "thompson")
            wins[chosen["entry"]["effort"]] += 1
        self.assertGreater(wins["medium"], wins["high"])

    def test_repository_catalog_validates_with_the_measured_constants(self):
        with open(os.path.join(ROOT, "arms.json"), encoding="utf-8") as stream:
            catalog = json.load(stream)
        stats.validate_catalog(catalog)
        self.assertEqual(catalog["providers"]["codex"]["plan_scale"], {"prolite": 1.0, "plus": 5.8})
        self.assertEqual(catalog["providers"]["claude"]["prior_pct_per_usd"], 0.0656)
        self.assertEqual((catalog["explore"]["measured_weight"], catalog["explore"]["measured_shrink"],
                          catalog["explore"]["measured_min_n"]), (4, 4.0, 10))

    def test_points_include_fixed_share_and_fix_time(self):
        for index, outcome in enumerate(("accepted", "fixed", "rejected", "fixed")):
            run = self.add_run("fix-{}".format(index))
            review = self.add_review(run, outcome)
            review["fix_minutes"] = 4 if index == 1 else 8
            with open(os.path.join(run, "review.json"), "w", encoding="utf-8") as stream:
                json.dump(review, stream)
        row = self.context()["stats"][0]
        self.assertAlmostEqual(row["points"], 0.1 * 0.3 + 0.01 + 0.5 * 6 * 0.003)

    def test_pace_projection_and_exclusion_for_all_providers(self):
        now = stats.parse_time("2026-10-17T00:00:00Z")
        reset = (now + datetime.timedelta(days=3.5)).isoformat()
        config = self.catalog["explore"]
        os.environ["USAGE_OPTIMIZER_MODE"] = "auto"
        # Half the week gone: 20% projects to 40 (utilization), 50% to 100 (default), 60% to 120 (saving).
        for used, expected in ((20, 0.25), (50, 1.0), (60, 3.0)):
            live = {"codex": {"windows": [{"label": "weekly", "used_percent": used, "resets_at": reset}]}}
            factor, excluded = stats.provider_pace("codex", live, config, now)
            self.assertEqual((factor, excluded), (expected, False))
        cases = [("codex", {"codex": {"windows": [{"label": "weekly", "used_percent": 95}]}}),
                 ("codex", {"codex": {"windows": [{"label": "5h", "used_percent": 90}]}}),
                 ("claude", {"claude": {"windows": {"seven_day": {"used_percentage": 85}}}}),
                 ("claude", {"claude": {"windows": {"five_hour": {"used_percentage": 90}}}}),
                 ("gemini", {"agy": {"buckets": [{"id": "gemini-weekly", "used_percentage": 95}]}}),
                 ("gemini", {"agy": {"buckets": [{"id": "gemini-5h", "used_percentage": 90}]}})]
        for provider, live in cases:
            self.assertTrue(stats.provider_pace(provider, live, config, now)[1])
            rows = stats.eligible_arms(self.context(live), "hard")
            self.assertFalse(any(row["provider"] == provider for row in rows))
        for provider in ("claude", "gemini"):
            data = ({"windows": {"seven_day": {"used_percentage": 20, "resets_at": reset}}}
                    if provider == "claude" else {"buckets": [{"id": "gemini-weekly", "used_percentage": 20, "reset_time": reset}]})
            self.assertEqual(stats.provider_pace(provider, {"agy" if provider == "gemini" else provider: data}, config, now),
                             (0.25, False))
        self.assertEqual(stats.provider_pace("codex", {}, config, now), (1.0, False))

    def write_mode_file(self, text):
        os.makedirs(self.config, exist_ok=True)
        with open(os.path.join(self.config, "mode"), "w", encoding="utf-8") as stream:
            stream.write(text)

    def test_mode_setting_takes_env_then_file_then_catalog(self):
        explore = dict(self.catalog["explore"], mode="saving")
        self.assertEqual(stats.mode_setting(dict(self.catalog["explore"])), "default")
        self.assertEqual(stats.mode_setting(explore), "saving")
        self.write_mode_file("auto  # chosen 2026-10-31\n")
        self.assertEqual(stats.mode_setting(explore), "auto")
        os.environ["USAGE_OPTIMIZER_MODE"] = "Utilization"
        self.assertEqual(stats.mode_setting(explore), "utilization")

    def test_invalid_mode_setting_warns_once_and_is_default(self):
        os.environ["USAGE_OPTIMIZER_MODE"] = "fast"
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.assertEqual(stats.mode_setting(self.catalog["explore"]), "default")
        self.assertEqual(stderr.getvalue().count("\n"), 1)
        self.assertTrue(stderr.getvalue().startswith("warning: usage mode 'fast'"), stderr.getvalue())

    def test_auto_mode_thresholds(self):
        now = stats.parse_time("2026-10-17T00:00:00Z")
        reset = (now + datetime.timedelta(days=3.5)).isoformat()
        config = dict(self.catalog["explore"], modes={"saving_pct": 110, "utilization_pct": 90})
        for used, expected in ((55.5, "saving"), (50, "default"), (44.5, "utilization")):
            live = {"claude": {"windows": {"seven_day": {"used_percentage": used, "resets_at": reset}}}}
            self.assertEqual(stats.provider_mode("claude", live, config, now, "auto"), expected)
        for projected, expected in ((111, "saving"), (110, "saving"), (100, "default"), (90, "utilization"),
                                    (89, "utilization"), (None, "default")):
            self.assertEqual(stats.projected_mode(projected, config), expected)
        self.assertEqual(stats.provider_mode("claude", {}, config, now, "auto"), "default")
        # A fixed setting applies whatever the week says.
        live = {"claude": {"windows": {"seven_day": {"used_percentage": 55.5, "resets_at": reset}}}}
        self.assertEqual(stats.provider_mode("claude", live, config, now, "utilization"), "utilization")

    def test_main_picks_includes_mode_window_resets(self):
        live = {"claude": {"windows": {"seven_day": {
                    "used_percentage": 20, "resets_at": "2026-11-05T12:34:56+00:00"}}},
                "codex": {"windows": [{"label": "weekly", "used_percent": 30,
                                          "resets_at": "2026-11-06T01:02:03Z"}]}}
        data = json.loads(self.direct_cli("main-picks", "--draws", "5", "--seed", "1", live=live))
        self.assertEqual(data["modes_until"], {"claude": "2026-11-05T12:34:56Z",
                                               "codex": "2026-11-06T01:02:03Z", "gemini": None})

    def test_provider_pace_factor_follows_the_mode(self):
        now = stats.parse_time("2026-10-17T00:00:00Z")
        config = self.catalog["explore"]
        for setting, expected in (("utilization", 0.25), ("saving", 3.0), ("default", 1.0)):
            self.assertEqual(stats.provider_pace("codex", {}, config, now, setting), (expected, False))
        os.environ["USAGE_OPTIMIZER_MODE"] = "saving"
        self.assertEqual(stats.provider_pace("gemini", {}, config, now), (3.0, False))

    def test_mode_command_json_and_text(self):
        reset = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=3.5)).isoformat()
        live = {"claude": {"windows": {"seven_day": {"used_percentage": 20, "resets_at": reset}}},
                "codex": {"windows": [{"label": "weekly", "used_percent": 60, "resets_at": reset}]}}
        data = json.loads(self.direct_cli("mode", "--json", live=live))
        self.assertEqual(data["setting"], "default")
        self.assertEqual(set(data["providers"]), {"claude", "codex", "gemini"})
        self.assertEqual((data["providers"]["claude"]["mode"], data["providers"]["claude"]["used_pct"]), ("default", 20.0))
        os.environ["USAGE_OPTIMIZER_MODE"] = "auto"
        data = json.loads(self.direct_cli("mode", "--json", live=live))
        self.assertEqual(data["setting"], "auto")
        self.assertEqual({name: row["mode"] for name, row in data["providers"].items()},
                         {"claude": "utilization", "codex": "saving", "gemini": "default"})
        self.assertAlmostEqual(data["providers"]["codex"]["projected_pct"], 120.0, delta=0.5)
        self.assertIsNone(data["providers"]["gemini"]["used_pct"])
        lines = self.direct_cli("mode", live=live).splitlines()
        self.assertTrue(lines[0].startswith("claude  utilization  (auto: week 20%, projected 40% at reset)"), lines)
        self.assertEqual(lines[2], "gemini  default      (auto: no reading)")
        os.environ["USAGE_OPTIMIZER_MODE"] = "utilization"
        self.assertEqual(self.direct_cli("mode", live=live).splitlines()[0], "claude  utilization  (setting utilization)")

    def test_mode_places_warnings_preserve_text_and_json_stdout(self):
        os.environ["USAGE_OPTIMIZER_MODE"] = "utilization"
        os.environ["LANES_PLACES"] = "cloud,subagent"
        for lane in ("luna", "sol", "gemini"):
            self.catalog["lanes"][lane]["places"] = ["process"]
        self.save_catalog()
        expected = "".join(
            "warning: no {} arm can run here: the allowed places (subagent, cloud, from LANES_PLACES) "
            "leave out process, while {} is in utilization mode; "
            "add one of them to explore.places or LANES_PLACES\n".format(provider, provider)
            for provider in ("codex", "gemini"))
        for args in ((), ("--json",)):
            with self.subTest(args=args):
                result = self.run_cli("mode", "--no-usage", *args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, expected)
                with mock.patch.object(stats, "warn_unusable_places"):
                    self.assertEqual(result.stdout, self.direct_cli("mode", "--no-usage", *args))
                if args:
                    data = json.loads(result.stdout)
                    self.assertEqual(set(data), {"setting", "providers"})
        for case in ("process", "default", "saving", "absent"):
            with self.subTest(case=case):
                os.environ["LANES_PLACES"] = "process" if case == "process" else "cloud,subagent"
                os.environ["USAGE_OPTIMIZER_MODE"] = case if case in ("default", "saving") else "utilization"
                for provider in ("CODEX", "GEMINI"):
                    os.environ["USAGE_OPTIMIZER_PLAN_" + provider] = "none" if case == "absent" else ""
                result = self.run_cli("mode", "--no-usage", "--json")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "")

    def test_live_usage_command_failure_timeout_and_no_usage(self):
        with mock.patch.object(stats.subprocess, "run") as run:
            self.assertEqual(stats.read_live_usage(True), {})
            run.assert_not_called()
            run.return_value = subprocess.CompletedProcess([], 0, '{"codex":{"plan_type":"plus"}}')
            self.assertEqual(stats.read_live_usage()["codex"]["plan_type"], "plus")
            self.assertEqual(run.call_args[0][0], [sys.executable, os.path.join(ROOT, "bin", "usage-status"), "--json"])
            self.assertEqual(run.call_args[1]["timeout"], 20)
            for failure in (OSError("missing"), subprocess.TimeoutExpired("usage-status", 20)):
                run.side_effect = failure
                self.assertEqual(stats.read_live_usage(), {})
            run.side_effect = None
            for code, stdout in ((0, "invalid"), (0, "[]"), (1, "{}")):
                run.return_value = subprocess.CompletedProcess([], code, stdout)
                self.assertEqual(stats.read_live_usage(), {})

    def test_recommend_statuses_routing_and_since(self):
        self.catalog["arms"] = self.catalog["arms"][:1]
        self.save_catalog()
        for count, expected in ((0, "exploring"), (4, "leaning"), (8, "locked")):
            for index in range(count - 4 if count == 8 else 0, count):
                run = self.add_run("reviewed-{}".format(index), class_name="hard")
                self.add_review(run)
            result = self.run_cli("recommend", "--class", "hard", "--draws", "100", "--no-usage", "--seed", "1", "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            record = json.loads(result.stdout)
            hard = record["classes"]["hard"]
            self.assertEqual((hard["status"], hard["reviewed"], hard["p_best"]), (expected, count, 1.0))
            with open(os.path.join(self.state, "routing.json"), encoding="utf-8") as stream:
                self.assertEqual(json.load(stream), record)
        result = self.run_cli("recommend", "--class", "hard", "--since", "2026-10-18", "--no-usage", "--seed", "1", "--json")
        self.assertEqual(json.loads(result.stdout)["classes"]["hard"]["status"], "exploring")
        text = self.run_cli("recommend", "--no-usage", "--seed", "1")
        self.assertIn("hard: locked luna medium (P(best) 1.00, 8 reviewed)", text.stdout)

    def test_recommend_seed_probability_ranking_and_no_eligible_arms(self):
        outputs = [json.loads(self.direct_cli("recommend", "--class", "hard", "--draws", "100", "--no-usage",
                                             "--seed", "1", "--json")) for _ in range(2)]
        self.assertEqual(outputs[0]["classes"], outputs[1]["classes"])
        rows = outputs[0]["classes"]["hard"]["arms"]
        self.assertAlmostEqual(sum(row["p_best"] for row in rows), 1.0)
        self.assertEqual([row["p_best"] for row in rows], sorted((row["p_best"] for row in rows), reverse=True))
        for arm in self.catalog["arms"]:
            arm["status"] = "manual"
        self.save_catalog()
        result = self.run_cli("recommend", "--no-usage", "--seed", "1", "--json")
        self.assertIsNone(json.loads(result.stdout)["classes"]["hard"]["leader"])
        self.assertEqual(self.run_cli("pick", "--class", "hard", "--no-usage").returncode, 2)

    def test_recommend_status_requires_probability_as_well_as_run_count(self):
        self.catalog["arms"] = self.catalog["arms"][:3]
        self.save_catalog()
        for arm in self.catalog["arms"]:
            for index in range(8):
                run = self.add_run("{}-{}".format(arm["lane"], index), lane=arm["lane"], effort=arm["effort"], class_name="hard")
                self.add_review(run)
        for winner_indices, expected in (([0] * 9 + [1], "locked"), ([0] * 6 + [1] * 4, "leaning"),
                                         ([0] * 4 + [1] * 3 + [2] * 3, "exploring")):
            indices = iter(winner_indices)
            with mock.patch.object(stats, "thompson_choice", side_effect=lambda rows, target, rng: rows[next(indices)]):
                record = json.loads(self.direct_cli("recommend", "--class", "hard", "--draws", "10", "--no-usage", "--json"))
            self.assertEqual(record["classes"]["hard"]["status"], expected)

    def test_export_allowlist_review_plan_and_attribution(self):
        usage = self.usage(10, 12, tokens=200, cost=0.5)
        usage["after"]["plan"] = "plus"
        run = self.add_run("private-run", usage=usage)
        self.add_review(run, "fixed")
        ledger = os.path.join(self.state, "ledger.jsonl")
        with open(ledger, encoding="utf-8") as stream:
            row = json.loads(stream.read())
        row.update({"cmd": ["secret"], "dir": "/private", "log": "/private/log", "mask_paths": ["private"],
                    "executable": "secret", "brief": "private brief", "pick_id": "p-example", "arm": "luna/luna/medium"})
        with open(ledger, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(row) + "\n")
        result = self.run_cli("export")
        self.assertEqual(result.returncode, 0, result.stderr)
        exported = json.loads(result.stdout)
        for key in ("cmd", "dir", "log", "mask_paths", "executable", "brief", "run_dir"):
            self.assertNotIn(key, exported)
        self.assertNotIn("/private", result.stdout)
        self.assertEqual((exported["machine"], exported["run_id"], exported["plan"], exported["attributed_pct"]),
                         ("this-machine", "private-run", "plus", 2.0))
        self.assertEqual(exported["review"]["outcome"], "fixed")
        self.assertEqual(exported["pick_id"], "p-example")
        self.assertEqual(exported["tokens"]["total"], 200)
        out = os.path.join(self.temp, "export.jsonl")
        self.assertEqual(self.run_cli("export", "--out", out).returncode, 0)
        with open(out, encoding="utf-8") as stream:
            self.assertEqual(json.loads(stream.read()), exported)
        self.assertEqual(self.run_cli("export", "--since", "2026-10-18").stdout, "")

    def test_import_refuses_own_machine_and_pools_reviewed_runs_without_waves(self):
        self.catalog["arms"] = self.catalog["arms"][:1]
        self.save_catalog()
        remote = os.path.join(self.temp, "remote.jsonl")
        row = {"machine": "this-machine", "run_id": "foreign", "lane": "luna", "model": "luna", "effort": "medium",
               "class": "hard", "started_at": "2026-10-17T00:00:00Z", "ended_at": "2026-10-17T00:02:00Z",
               "plan": "prolite", "attributed_pct": 2,
               "review": {"outcome": "accepted", "reviewed_at": "2026-10-17T01:00:00Z", "note": "checked", "fix_minutes": None}}
        with open(remote, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(row) + "\n")
        result = self.run_cli("import", remote)
        self.assertEqual(result.returncode, 2)
        self.assertIn("this machine", result.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.state, "imported")))
        row["machine"] = "other-machine"
        with open(remote, "w", encoding="utf-8") as stream:
            for index in range(8):
                stream.write(json.dumps(dict(row, run_id="remote-{}".format(index), cmd="private", dir="private")) + "\n")
            stream.write('{bad\n{"run_id":"no-machine"}\n')
        result = self.run_cli("import", remote)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("imported 8 runs from 1 machines; skipped 2 invalid lines", result.stdout)
        self.assertEqual(self.run_cli("import", remote).returncode, 0)  # replaces, never doubles
        result = self.run_cli("recommend", "--class", "hard", "--no-usage", "--seed", "1", "--json")
        self.assertEqual(json.loads(result.stdout)["classes"]["hard"]["reviewed"], 8)
        self.assertEqual(json.loads(result.stdout)["classes"]["hard"]["status"], "locked")
        self.assertEqual(self.context()["stats"][0]["tier"], "measured")
        report = json.loads(self.run_cli("report", "--json").stdout)[0]
        self.assertEqual(report["reviewed"], 8)
        self.assertEqual(report["wave_count"], 0)
        self.assertEqual(report["wk%/run"], 2.0)
        picked = json.loads(self.run_cli("pick", "--class", "hard", "--no-usage", "--seed", "1", "--json").stdout)
        self.assertNotEqual(picked["mode"], "forced")
        self.assertEqual(json.loads(self.direct_cli("arms", "--json"))["arms"][0]["reviewed"], 8)
        self.assertEqual(self.run_cli("export").stdout, "")
        with open(os.path.join(self.state, "imported", "other-machine.jsonl"), encoding="utf-8") as stream:
            self.assertNotIn("private", stream.read())

    def test_import_validation_skips_bad_shapes_and_cannot_escape_state(self):
        path = os.path.join(self.temp, "bad.jsonl")
        base = {"machine": "remote", "run_id": "r", "lane": "luna"}
        invalid = [dict(base, machine="../escape"), dict(base, lane=[]), dict(base, attributed_pct="nan"),
                   dict(base, review={"outcome": "invalid"}), dict(base, tokens=[]), dict(base, model={}),
                   dict(base, tokens={"input": -1}), dict(base, tokens={"output": "many"})]
        # An unknown count is null, not invalid: Codex runs whose rollout gave no token count export that way.
        unknown = dict(base, run_id="r-unknown-tokens", tokens={"input": None, "cached": None, "output": None, "total": None},
                       review={"outcome": "accepted"})
        with open(path, "w", encoding="utf-8") as stream:
            for row in invalid + [base, unknown]:
                stream.write(json.dumps(row) + "\n")
        result = self.run_cli("import", path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("imported 2 runs from 1 machines; skipped 8 invalid lines", result.stdout)

    def test_catalog_local_merges_and_invalid_catalog_commands_are_isolated(self):
        local = {"providers": {"codex": {"scarcity": 0.6}}, "explore": {"floor": 0.75},
                 "arms": [{"lane": "luna", "model": "luna", "effort": "medium", "weight": 3},
                          dict(self.catalog["arms"][0], model="new-luna", effort="high")]}
        with open(os.environ["LANES_ARMS_LOCAL"], "w", encoding="utf-8") as stream:
            json.dump(local, stream)
        catalog = stats.load_catalog()
        self.assertEqual(catalog["providers"]["codex"]["scarcity"], 0.6)
        self.assertEqual(catalog["providers"]["codex"]["prior_plan"], "prolite")
        self.assertEqual(catalog["explore"]["floor"], 0.75)
        self.assertEqual(catalog["explore"]["min_runs"], 2)
        self.assertEqual(len(catalog["arms"]), 5)
        self.assertEqual(catalog["arms"][0]["weight"], 3)
        self.assertEqual(catalog["arms"][-1]["model"], "new-luna")
        self.add_run("review-without-catalog")
        for content in ("{broken", "{}"):
            with open(self.catalog_path, "w", encoding="utf-8") as stream:
                stream.write(content)
            for args in (("pick", "--class", "hard", "--no-usage"), ("recommend", "--no-usage"), ("arms",)):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(len(result.stderr.splitlines()), 1)
                self.assertEqual(result.stdout, "")
            self.assertEqual(self.run_cli("review", "last", "--outcome", "accepted").returncode, 0)
            self.assertEqual(self.run_cli("report", "--json").returncode, 0)
            # Export needs the window epochs to skip straddling waves, so an invalid catalog stops it.
            self.assertEqual(self.run_cli("export").returncode, 2)
            remote = os.path.join(self.temp, "no-catalog-import.jsonl")
            with open(remote, "w", encoding="utf-8") as stream:
                stream.write(json.dumps({"machine": "remote", "run_id": "r", "lane": "luna"}) + "\n")
            self.assertEqual(self.run_cli("import", remote).returncode, 0)
        os.remove(self.catalog_path)
        self.assertEqual(self.run_cli("pick", "--class", "hard", "--no-usage").returncode, 2)

    def test_off_catalog_wildcard_and_gemini_effort_inference(self):
        self.catalog["arms"].append(dict(self.catalog["arms"][0], model="legacy-luna", effort="*", status="manual", classes=[]))
        self.save_catalog()
        for effort in (None, "max"):
            run = self.add_run("legacy-{}".format(effort), model="legacy-luna", effort=effort)
            self.add_review(run)
        run = self.add_run("inferred", lane="gemini", model="gemini-3.8-flash-medium", effort=None)
        self.add_review(run)
        self.add_run("off-catalog", lane="sol", model="unknown-model", effort="max")
        result = json.loads(self.direct_cli("arms", "--json"))
        self.assertEqual(result["arms"][-1]["reviewed"], 2)
        self.assertEqual(result["arms"][3]["reviewed"], 1)
        self.assertEqual(result["off_catalog"], [{"lane": "sol", "model": "unknown-model", "effort": "max", "count": 1}])
        self.assertIn("off-catalog: sol/unknown-model/max (1 runs)", self.direct_cli("arms"))
        result = self.run_cli("pick", "--class", "hard", "--exclude", "luna,sol,sonnet", "--no-usage", "--seed", "1", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(" -e ", json.loads(result.stdout)["run_lines"][0])
        # A non-default Gemini model needs -m and its name in the display.
        self.catalog["lanes"]["gemini"]["model"] = "gemini-default"
        self.save_catalog()
        result = self.run_cli("pick", "--class", "hard", "--exclude", "luna,sol,sonnet", "--no-usage", "--seed", "1")
        self.assertIn("gemini medium (gemini-3.8-flash-medium)", result.stdout)
        self.assertIn("-m gemini-3.8-flash-medium", result.stdout)

    def test_discovery_reads_cache_and_only_invokes_agy_models(self):
        os.environ["CODEX_HOME"] = self.temp
        with open(os.path.join(self.temp, "models_cache.json"), "w", encoding="utf-8") as stream:
            json.dump({"models": [
                {"slug": "luna"},
                {"slug": "brand-new-sol", "description": "Newer workhorse.",
                 "supported_reasoning_levels": [{"effort": "xhigh"}, {"effort": "max"}]},
                {"slug": "gpt-reserve", "visibility": "hide"},
                {"slug": "gpt-7-nova"}]}, stream)
        self.catalog["providers"]["codex"]["rate_card"] = {
            "sol": {"input": 50, "cached_input": 2.5, "output": 250},
            "brand-new-sol": {"input": 25, "cached_input": 1.25, "output": 125}}
        agy = ("Fetching available models...\ngemini-3.8-flash-medium\tGemini 3.8 Flash (Medium)\n"
               "gemini-new-high\tGemini New (High)\nclaude-sonnet-4-6\tClaude Sonnet 4.6 (Thinking)\n")
        with mock.patch.object(stats.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, agy)) as run:
            found = stats.discover_models(self.catalog)
            self.assertEqual(run.call_args[0][0], ["agy", "models"])
            self.assertEqual(run.call_args[1]["timeout"], 20)
        self.assertEqual([(row["provider"], row["model"], row["lane"]) for row in found],
                         [("codex", "brand-new-sol", "sol"), ("codex", "gpt-7-nova", None),
                          ("gemini", "gemini-new-high", "gemini"), ("gemini", "claude-sonnet-4-6", None)])
        # The predecessor's classes and weight, its cost prior scaled by output price, and only efforts Codex offers.
        self.assertEqual(found[0]["suggested"]["arms"], [{
            "lane": "sol", "model": "brand-new-sol", "effort": "xhigh", "status": "manual",
            "classes": ["mechanical", "hard", "research"], "weight": 1.0, "prior_pct": 0.4, "prior_usable": 0.8}])
        self.assertEqual((found[0]["note"], found[0]["priced"]), ("Newer workhorse.", True))
        self.assertEqual((found[1]["suggested"], found[1]["priced"]), (None, False))
        self.assertEqual([(arm["effort"], arm["prior_pct"]) for arm in found[2]["suggested"]["arms"]], [("high", 0.6)])
        self.assertIsNone(found[3]["suggested"])
        with mock.patch.object(stats.subprocess, "run", side_effect=FileNotFoundError()):
            self.assertEqual(len(stats.discover_models(self.catalog)), 2)
        with mock.patch.object(stats, "discover_models", return_value=found):
            output = self.direct_cli("arms", "--discover")
            self.assertIn("new: codex brand-new-sol (Newer workhorse.)  arms.local.json", output)
            self.assertIn("new: codex gpt-7-nova  no lane serves this family", output)
            self.assertIn("new: gemini claude-sonnet-4-6  no lane serves this family", output)

    def test_codex_run_weight_follows_the_lane_price(self):
        usage = {"tokens": {"total": 100}}
        for run, weight in (({"lane": "terra", "usage": usage}, 1000),
                            ({"lane": "other", "model": "gpt-6.1-terra", "usage": usage}, 1000),
                            ({"lane": "sol", "usage": usage}, 2000), ({"lane": "other", "usage": usage}, 100)):
            with self.subTest(run=run):
                self.assertEqual(stats.weight_for(run, "codex"), weight)

    def eta_now(self):
        return stats.parse_time("2026-10-17T00:02:00Z")

    def test_eta_prior_only_uses_class_effort_and_lane_factors(self):
        self.catalog["lanes"]["terra"] = {"model": "terra", "provider": "codex"}
        now = self.eta_now()
        estimate = stats.estimate_eta({}, self.catalog, "luna", None, "xhigh", "substantive", None, now)
        self.assertEqual((estimate["minutes"], estimate["tier"], estimate["arm"]), (18.0, "prior", "luna/luna/xhigh"))
        self.assertEqual(estimate["p80_minutes"], round(18 * math.exp(0.8416), 2))
        terra = stats.estimate_eta({}, self.catalog, "terra", None, "high", "review", None, now)
        self.assertEqual((terra["minutes"], terra["tier"]), (2.0, "prior"))
        # An unknown class is priced as substantive, and an unknown effort takes a factor of 1.0.
        self.assertEqual(stats.estimate_eta({}, self.catalog, "sol", None, "turbo", "nonsense", None, now)["minutes"], 15.0)
        # A brief twice the 6,000-byte reference scales the prior by 2^0.8; a tiny one is floored at 500 bytes.
        longer = stats.estimate_eta({}, self.catalog, "luna", None, "xhigh", "substantive", None, now, brief_bytes=12000)
        self.assertEqual(longer["minutes"], round(18 * 2 ** 0.8, 2))
        tiny = stats.estimate_eta({}, self.catalog, "luna", None, "xhigh", "substantive", None, now, brief_bytes=10)
        self.assertEqual(tiny["minutes"], round(18 * (500 / 6000) ** 0.8, 2))
        with self.assertRaisesRegex(ValueError, "unknown lane: nobody"):
            stats.estimate_eta({}, self.catalog, "nobody", None, "xhigh", "hard", None, now)

    def test_eta_untagged_runs_move_the_estimate_and_two_make_it_measured(self):
        now = self.eta_now()
        self.add_run("eta-1", lane="luna", effort="xhigh", class_name="substantive", duration_s=2400)
        runs = stats.load_runs(self.state)[0]
        one = stats.estimate_eta(runs, self.catalog, "luna", None, "xhigh", "substantive", None, now)
        # One run: the estimate moves toward 40 minutes, but the tier stays prior.
        self.assertEqual((one["tier"], one["minutes"]), ("prior", 34.16))
        self.assertEqual(one["runs"], {"arm_class": 1, "arm": 1, "class": 1, "machine": 1})
        self.add_run("eta-2", lane="luna", effort="xhigh", class_name="substantive", duration_s=2400)
        runs = stats.load_runs(self.state)[0]
        two = stats.estimate_eta(runs, self.catalog, "luna", None, "xhigh", "substantive", None, now)
        self.assertEqual((two["tier"], two["minutes"]), ("measured", 38.05))
        self.assertEqual(two["runs"], {"arm_class": 2, "arm": 2, "class": 2, "machine": 2})
        self.assertGreater(two["minutes"], one["minutes"])
        self.assertGreater(one["minutes"], 18.0)

    def test_eta_tagged_runs_do_not_change_untagged_estimates(self):
        now = self.eta_now()
        for index in range(2):
            self.add_run("suite-{}".format(index), lane="luna", effort="xhigh", class_name="substantive",
                         duration_s=2400, tag="suite_r")
        runs = stats.load_runs(self.state)[0]
        untagged = stats.estimate_eta(runs, self.catalog, "luna", None, "xhigh", "substantive", None, now)
        self.assertEqual((untagged["tier"], untagged["minutes"]), ("prior", 18.0))
        self.assertEqual(stats.estimate_eta(runs, self.catalog, "luna", None, "xhigh", "substantive", "", now)["minutes"],
                         18.0)
        tagged = stats.estimate_eta(runs, self.catalog, "luna", None, "xhigh", "substantive", "suite_r", now)
        self.assertEqual((tagged["tier"], tagged["minutes"], tagged["tag"]), ("measured", 38.05, "suite_r"))

    def test_eta_ignores_quota_busy_and_runs_without_duration(self):
        now = self.eta_now()
        for verdict in ("QUOTA", "BUSY"):
            self.add_run("ignored-{}".format(verdict), lane="luna", effort="xhigh", class_name="substantive",
                         duration_s=2400, verdict=verdict)
        self.add_run("no-duration", lane="luna", effort="xhigh", class_name="substantive", duration_s=None)
        runs = stats.load_runs(self.state)[0]
        estimate = stats.estimate_eta(runs, self.catalog, "luna", None, "xhigh", "substantive", None, now)
        self.assertEqual((estimate["tier"], estimate["minutes"]), ("prior", 18.0))
        self.assertEqual(estimate["runs"]["machine"], 0)

    def test_eta_learns_only_from_runs_that_did_work(self):
        now = self.eta_now()
        for index in range(2):
            self.add_run("worked-{}".format(index), lane="luna", effort="xhigh", class_name="substantive",
                         duration_s=2400)
        runs = stats.load_runs(self.state)[0]
        before = stats.estimate_eta(runs, self.catalog, "luna", None, "xhigh", "substantive", None, now)
        # The 2026-10-29 case: a max hard unit stopped after 19 s with verdict UNKNOWN and must not move the estimate.
        for verdict in ("UNKNOWN", "NOOP", "FAILED", "SANDBOX", "TIMEOUT", "QUOTA", "BUSY"):
            self.add_run("stopped-{}".format(verdict), lane="luna", effort="xhigh", class_name="substantive",
                         duration_s=19, verdict=verdict)
        runs = stats.load_runs(self.state)[0]
        after = stats.estimate_eta(runs, self.catalog, "luna", None, "xhigh", "substantive", None, now)
        self.assertEqual(after, before)
        # A run that finished with a partial verdict still counts.
        self.add_run("partial", lane="luna", effort="xhigh", class_name="substantive", duration_s=2400,
                     verdict="PARTIAL")
        runs = stats.load_runs(self.state)[0]
        partial = stats.estimate_eta(runs, self.catalog, "luna", None, "xhigh", "substantive", None, now)
        self.assertEqual(partial["runs"]["arm_class"], 3)

    def test_eta_cli_text_and_json_for_one_lane(self):
        prior = self.run_cli("eta", "--lane", "sol", "--effort", "xhigh", "--class", "hard")
        self.assertEqual(prior.stdout.strip(), "eta ~30 min (p80 70) [prior]")
        # The CLI uses the real clock, so these runs end now and their recency weight is about 1.
        for index in range(2):
            self.add_run("cli-{}".format(index), lane="luna", effort="xhigh", class_name="substantive",
                         duration_s=2400, ended=stats.iso_now())
        result = self.run_cli("eta", "--lane", "luna", "--effort", "xhigh", "--class", "substantive")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "eta ~38 min (p80 69) [measured: 2 runs]")
        result = self.run_cli("eta", "--lane", "luna", "--effort", "xhigh", "--class", "substantive", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        estimate = json.loads(result.stdout)
        self.assertEqual((estimate["arm"], estimate["class"], estimate["tag"], estimate["tier"]),
                         ("luna/luna/xhigh", "substantive", None, "measured"))
        self.assertAlmostEqual(estimate["minutes"], 38.05, delta=0.01)
        # Reads the ledger only: no usage call and nothing written.
        before = sorted(os.listdir(self.state))
        with mock.patch.object(stats, "read_live_usage") as live, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(stats.main(["eta", "--lane", "sol", "--effort", "xhigh", "--class", "hard"]), 0)
        live.assert_not_called()
        self.assertEqual(sorted(os.listdir(self.state)), before)
        self.assertFalse(os.path.exists(os.path.join(self.state, "picks.jsonl")))
        # A Claude lane run without -e has no effort: it still gets an estimate, at an effort factor of 1.0.
        no_effort = self.run_cli("eta", "--lane", "sonnet", "--class", "hard", "--json")
        self.assertEqual(no_effort.returncode, 0, no_effort.stderr)
        self.assertEqual(json.loads(no_effort.stdout)["arm"], "sonnet/sonnet")

    def test_eta_cli_lists_arms_sorted_by_minutes_and_refuses_unknown_lane(self):
        result = self.run_cli("eta", "--class", "mechanical")
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[0].split(), ["arm", "eta_min", "p80_min", "tier", "runs"])
        self.assertEqual([line.split()[0] for line in lines[2:]],
                         ["luna/luna/medium", "gemini/gemini-3.8-flash-medium/medium", "sonnet/sonnet/high",
                          "sol/sol/xhigh"])
        self.assertEqual(lines[2].split()[1:4], ["3.6", "8.3", "prior"])
        result = self.run_cli("eta", "--class", "mechanical", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        listed = json.loads(result.stdout)
        self.assertEqual((listed["class"], listed["tag"]), ("mechanical", None))
        self.assertEqual([arm["minutes"] for arm in listed["arms"]], [3.6, 3.6, 4.0, 4.8])
        unknown = self.run_cli("eta", "--lane", "nobody", "--effort", "xhigh", "--class", "hard")
        self.assertEqual(unknown.returncode, 2)
        self.assertIn("lane-stats: unknown lane: nobody", unknown.stderr)
        self.assertEqual(self.run_cli("eta").returncode, 2)
        self.assertEqual(self.run_cli("eta", "--lane", "luna", "--effort", "xhigh", "--model", "x", "--class", "hard",
                                      "--json").returncode, 0)
        self.assertEqual(self.run_cli("eta", "--effort", "xhigh", "--class", "hard").returncode, 2)

    def test_pick_shows_eta_logs_it_and_keeps_the_seeded_choice(self):
        result = self.run_cli("pick", "--class", "hard", "--no-usage", "--seed", "1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("eta ~", result.stdout)
        picked = json.loads(self.run_cli("pick", "--class", "hard", "--no-usage", "--seed", "1", "--json").stdout)
        self.assertEqual([estimate["arm"] for estimate in picked["eta"]], picked["arms"])
        self.assertEqual({tuple(sorted(estimate)) for estimate in picked["eta"]},
                         {("arm", "minutes", "p80_minutes", "tier")})
        self.assertEqual(picked["eta"][0]["tier"], "prior")
        self.assertEqual(self.picks()[-1]["eta"], picked["eta"])
        # The choice is what choose_arm makes from the same seed; the ETA is computed afterwards.
        rows = stats.eligible_arms(self.context(class_name="hard"), "hard")
        chosen, mode = stats.choose_arm(rows, self.catalog["explore"], "hard", random.Random(1))
        self.assertEqual((chosen["arm"], mode), (picked["arms"][0], picked["mode"]))

    def test_report_min_per_usable_and_eta_ratio(self):
        first = self.add_run("eta-r1", lane="luna", duration_s=120, eta_s=60)
        second = self.add_run("eta-r2", lane="luna", duration_s=240, eta_s=80)
        self.add_run("eta-r3", lane="luna", duration_s=60)
        self.add_run("eta-r4", lane="sonnet", duration_s=600)
        self.add_review(first, "accepted")
        self.add_review(second, "fixed", fix_minutes=3)
        result = self.run_cli("report", "--by", "lane")
        self.assertEqual(result.returncode, 0, result.stderr)
        header = result.stdout.splitlines()[0].split()
        self.assertIn("min/usable", header)
        self.assertIn("eta×", header)
        self.assertLess(header.index("med_min"), header.index("min/usable"))
        self.assertEqual(header.index("min/usable") + 1, header.index("eta×"))
        self.assertIn("2.50x", result.stdout)
        rows = {row["lane"]: row for row in json.loads(self.run_cli("report", "--json", "--by", "lane").stdout)}
        # Luna: (2 + 4 + 1 minutes of runs, plus 3 fix minutes) over 2 usable runs; eta ratios 2.0 and 3.0.
        self.assertEqual(rows["luna"]["min/usable"], 5.0)
        self.assertEqual(rows["luna"]["eta_x"], 2.5)
        # Sonnet has no usable run and no eta_s, so both are empty.
        self.assertIsNone(rows["sonnet"]["min/usable"])
        self.assertIsNone(rows["sonnet"]["eta_x"])

    def test_eta_s_survives_export_and_import_and_negative_is_rejected(self):
        self.add_run("eta-export", eta_s=45)
        exported = json.loads(self.run_cli("export").stdout)
        self.assertEqual(exported["eta_s"], 45)
        remote = os.path.join(self.temp, "eta-remote.jsonl")
        row = dict(exported, machine="other-machine")
        with open(remote, "w", encoding="utf-8") as stream:
            for bad in (row, dict(row, run_id="negative", eta_s=-1)):
                stream.write(json.dumps(bad) + "\n")
        result = self.run_cli("import", remote)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("imported 1 runs from 1 machines; skipped 1 invalid lines", result.stdout)
        with open(os.path.join(self.state, "imported", "other-machine.jsonl"), encoding="utf-8") as stream:
            self.assertEqual(json.loads(stream.readline())["eta_s"], 45)

    def test_peak_mem_mb_survives_export_and_import_and_bad_peaks_are_rejected(self):
        self.add_run("peak-export", peak_mem_mb=512)
        exported = json.loads(self.run_cli("export").stdout)
        self.assertEqual(exported["peak_mem_mb"], 512)
        row = dict(exported, machine="other-machine")
        absent = dict(row, run_id="absent")
        del absent["peak_mem_mb"]
        remote = os.path.join(self.temp, "peak-remote.jsonl")
        with open(remote, "w", encoding="utf-8") as stream:
            for item in [row, absent, dict(row, run_id="null", peak_mem_mb=None),
                         dict(row, run_id="negative", peak_mem_mb=-1), dict(row, run_id="text", peak_mem_mb="512"),
                         dict(row, run_id="flag", peak_mem_mb=True)]:
                stream.write(json.dumps(item) + "\n")
        result = self.run_cli("import", remote)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("imported 3 runs from 1 machines; skipped 3 invalid lines", result.stdout)
        with open(os.path.join(self.state, "imported", "other-machine.jsonl"), encoding="utf-8") as stream:
            peaks = {record["run_id"]: record["peak_mem_mb"] for record in map(json.loads, stream)}
        self.assertEqual(peaks, {"peak-export": 512, "absent": None, "null": None})

    def test_report_mem_mb_is_the_median_peak_of_the_runs_that_have_one(self):
        self.add_run("mem-r1", lane="luna", peak_mem_mb=300)
        self.add_run("mem-r2", lane="luna", peak_mem_mb=500)
        self.add_run("mem-r3", lane="luna")
        self.add_run("mem-r4", lane="sonnet")
        rows = {row["lane"]: row for row in json.loads(self.run_cli("report", "--json", "--by", "lane").stdout)}
        self.assertEqual(rows["luna"]["mem_mb"], 400)
        self.assertIsNone(rows["sonnet"]["mem_mb"])
        result = self.run_cli("report", "--by", "lane")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("mem_mb", result.stdout.splitlines()[0].split())
        self.assertIn("400", [line for line in result.stdout.splitlines() if line.startswith("luna")][0].split())

    def test_invalid_explore_time_is_rejected(self):
        def with_time(time):
            catalog = json.loads(json.dumps(self.catalog))
            catalog["explore"]["time"] = time
            return catalog

        stats.validate_catalog(with_time({"class_minutes": {"substantive": 15}, "log_sd": 1.0}))
        bad = [{"effort_factor": {"low": "0.8"}}, {"log_sd": 0}, {"prior_runs": True}, {"lane_factor": {"terra": 0}},
               {"class_minutes": {"hard": 25}}, {"class_minutes": []}, {"class_minutes": {"substantive": float("nan")}},
               "fast", None]
        for time in bad:
            with self.subTest(time=time), self.assertRaisesRegex(ValueError, "invalid explore.time"):
                stats.validate_catalog(with_time(time))
        self.catalog["explore"]["time"] = {"log_sd": 0}
        self.save_catalog()
        self.assertEqual(self.run_cli("eta", "--class", "hard").returncode, 2)

    def test_partial_explore_time_fills_missing_keys_from_defaults(self):
        self.catalog["explore"]["time"] = {"log_sd": 2.0}
        self.save_catalog()
        estimate = stats.estimate_eta({}, self.catalog, "luna", None, "xhigh", "substantive", None, self.eta_now())
        self.assertEqual(estimate["minutes"], 18.0)
        self.assertEqual(estimate["p80_minutes"], round(18 * math.exp(0.8416 * 2.0), 2))
        self.assertEqual(stats.time_config(self.catalog)["class_minutes"], stats.TIME_DEFAULTS["class_minutes"])

    def test_live_usage_runs_the_py_sibling_when_it_exists(self):
        script = os.path.join(self.temp, "usage-status.py")
        with open(script, "w", encoding="utf-8") as stream:
            stream.write('import json\nprint(json.dumps({"claude": {}}))\n')
        with mock.patch.object(stats, "usage_status_script", return_value=script):
            self.assertEqual(stats.read_live_usage(), {"claude": {}})
        with mock.patch.object(stats.os.path, "isfile", return_value=True):
            self.assertTrue(stats.usage_status_script().endswith("usage-status.py"))
        with mock.patch.object(stats.os.path, "isfile", return_value=False):
            self.assertEqual(stats.usage_status_script(), os.path.join(ROOT, "bin", "usage-status"))

    def test_repository_time_block_matches_the_defaults(self):
        with open(os.path.join(ROOT, "arms.json"), encoding="utf-8") as stream:
            catalog = json.load(stream)
        stats.validate_catalog(catalog)
        self.assertEqual(stats.time_config(catalog), stats.TIME_DEFAULTS)

    # Window epochs and plan dollars. EPOCH is the shared schema's Codex Pro Lite doubling.
    EPOCH = {"plan": "prolite", "from": "2026-10-30T00:00:00Z", "scale": 2.0, "source": "limits doubled"}
    CLAUDE_USD_PER_PCT = 200 / 4.345 / 100
    PROLITE_USD_PER_PCT = 100 / 4.345 / 100

    def price_catalog(self, gemini_price=True):
        codex = self.catalog["providers"]["codex"]
        codex["plan_scale"] = {"prolite": 1.0, "plus": 5.8}
        codex["window_epochs"] = [dict(self.EPOCH)]
        codex["plan_prices"] = {"prolite": {"usd_per_month": 100, "source": "test", "checked": "2026-10-31"},
                                "plus": {"usd_per_month": 20}}
        self.catalog["providers"]["claude"].update(prior_plan="max_20x", plan_prices={"max_20x": {"usd_per_month": 200}})
        self.catalog["providers"]["gemini"]["prior_plan"] = "google_ai_pro"
        if gemini_price:
            self.catalog["providers"]["gemini"]["plan_prices"] = {"google_ai_pro": {"usd_per_month": 19.99}}
        self.catalog["providers"]["cline"] = {"scarcity": 0.0}
        self.catalog["lanes"]["glm"] = {"model": "glm", "provider": "cline"}
        self.catalog["arms"].append(dict(self.catalog["arms"][0], lane="glm", model="glm", prior_pct=0.5))
        self.catalog["explore"]["weeks_per_month"] = 4.345
        self.save_catalog()

    def epoch_usage(self, before, after, observed, observed_after=None, plan="prolite", tokens=100):
        usage = self.usage(before, after, tokens=tokens, reset_before="2026-11-04T06:42:00Z")
        usage["before"]["observed_at"] = observed
        usage["after"]["observed_at"] = observed_after or observed
        for side in ("before", "after"):
            usage[side]["plan"] = plan
        return usage

    def test_window_epochs_rescale_runs_read_before_after_and_across_a_plan_switch(self):
        settings = {"plan_scale": {"prolite": 1.0, "plus": 5.8}, "window_epochs": [dict(self.EPOCH)]}
        now = stats.parse_time("2026-10-31T12:00:00Z")
        before, after = stats.parse_time("2026-10-29T04:02:00Z"), stats.parse_time("2026-10-30T00:24:00Z")
        # The meter case: 6% of the window on 10-29 is 3% of today's doubled window; a reading since counts as read.
        self.assertEqual(stats.convert_pct(6, settings, "prolite", before, "prolite", now), 3.0)
        self.assertEqual(stats.convert_pct(3, settings, "prolite", after, "prolite", now), 3.0)
        self.assertEqual(stats.convert_pct(3, settings, "prolite", stats.parse_time(self.EPOCH["from"]),
                                           "prolite", now), 3.0)
        # Asked as of 10-29, today's runs are worth twice the %.
        self.assertEqual(stats.convert_pct(3, settings, "prolite", after, "prolite", before), 6.0)
        # A prolite run today at 1% is 11.6% of a Plus window (5.8 x 2); one from before the epoch is 5.8%.
        self.assertAlmostEqual(stats.convert_pct(1, settings, "prolite", now, "plus", now), 11.6)
        self.assertAlmostEqual(stats.convert_pct(1, settings, "prolite", before, "plus", now), 5.8)
        self.assertAlmostEqual(stats.convert_pct(11.6, settings, "plus", now, "prolite", now), 1.0)
        # None is the base window (bench blocks, priors); an epoch for another plan leaves prolite alone.
        self.assertEqual(stats.convert_pct(0.2, settings, "prolite", None, "prolite", now), 0.1)
        self.assertEqual(stats.convert_pct(5.8, settings, "plus", before, "plus", now), 5.8)
        # Several epochs for one plan multiply; one that starts after `now` does not apply yet.
        settings["window_epochs"].append(dict(self.EPOCH, **{"from": "2026-10-31T06:00:00Z", "scale": 1.5}))
        self.assertAlmostEqual(stats.convert_pct(6, settings, "prolite", before, "prolite", now), 2.0)
        self.assertAlmostEqual(stats.convert_pct(3, settings, "prolite", after, "prolite", now), 2.0)
        self.assertEqual(stats.epoch_product(settings, "prolite", now), 3.0)
        self.assertEqual(stats.epoch_product(settings, "prolite", stats.parse_time("2026-10-31T05:59:00Z")), 2.0)
        # A zero plan_scale has no window to convert from.
        self.assertIsNone(stats.convert_pct(1, {"plan_scale": {"free": 0}}, "free", now, "prolite", now))

    def test_measured_cost_prices_runs_from_before_and_after_an_epoch_in_todays_window(self):
        self.price_catalog()
        # Two runs read before the doubling took 4% each, two since took 2%: all four are 2% of today's window.
        for index, (day, delta) in enumerate((("29", 4), ("29", 4), ("31", 2), ("31", 2))):
            start = "2026-10-{}T0{}:00:00Z".format(day, index)
            self.add_run("epoch-{}".format(index), started=start, ended="2026-10-{}T0{}:02:00Z".format(day, index),
                         usage=self.epoch_usage(10 + index * 5, 10 + index * 5 + delta, start))
        row = self.context()["stats"][0]
        self.assertEqual(row["tier"], "measured")
        self.assertAlmostEqual(row["cost"], 2.0)
        # Without the epoch the same runs are priced as one: between 2% and 4%.
        del self.catalog["providers"]["codex"]["window_epochs"]
        self.save_catalog()
        self.assertGreater(self.context()["stats"][0]["cost"], 2.5)

    def test_a_wave_read_on_both_sides_of_an_epoch_is_skipped_and_calibration_converts(self):
        self.price_catalog()
        # Three solo waves on 10-29 of 2% each: 1% each of today's window.
        for index in range(3):
            start = "2026-10-29T0{}:00:00Z".format(index)
            self.add_run("pre-{}".format(index), started=start, ended="2026-10-29T0{}:02:00Z".format(index),
                         usage=self.epoch_usage(10 + 2 * index, 12 + 2 * index, start))
        # Read at 23:58 and 00:02: its 3% and 4% are of two window sizes.
        self.add_run("straddle", started="2026-10-29T23:58:00Z", ended="2026-10-30T00:02:00Z",
                     usage=self.epoch_usage(3, 4, "2026-10-29T23:58:00Z", "2026-10-30T00:02:00Z"))
        rows = {row["run_id"]: row for row in map(json.loads, self.run_cli("export").stdout.splitlines())}
        self.assertEqual(rows["pre-0"]["attributed_pct"], 2.0)  # exported as the meter read it
        self.assertIsNone(rows["straddle"]["attributed_pct"])
        report = json.loads(self.run_cli("report", "--json").stdout)[0]
        self.assertAlmostEqual(report["attributed_percent"]["weekly"], 6.0)
        self.assertAlmostEqual(report["wk%/run"], 1.0)
        runs = stats.load_data(self.state, self.catalog)[0]
        now = stats.parse_time("2026-10-31T00:00:00Z")
        plans = {"codex": "prolite", "gemini": "google_ai_pro"}
        # 3% of today's window over 300 credit-weighted tokens; the straddling wave adds nothing.
        self.assertAlmostEqual(stats.calibrated_rates(self.state, runs, self.catalog, plans, now)["codex"], 0.01)
        # Without the epochs the straddling wave is pooled raw and the waves count at their old size.
        del self.catalog["providers"]["codex"]["window_epochs"]
        runs = stats.load_data(self.state, self.catalog)[0]
        self.assertAlmostEqual(stats.calibrated_rates(self.state, runs, self.catalog, plans, now)["codex"], 7 / 400)

    def test_bench_blocks_and_priors_are_base_windows_scaled_to_today(self):
        self.price_catalog()
        now = stats.parse_time("2026-10-31T00:00:00Z")
        plans = {"codex": "prolite", "claude": "max_20x", "gemini": "google_ai_pro"}
        arm = dict(self.catalog["arms"][0], measured={
            "hard": {"usable": 0.9, "pct_week": 0.2, "recall": 0.8, "n": 12, "plan": "prolite"}})
        self.assertEqual(stats.arm_cost(arm, [], {}, self.catalog, plans, {}, now, "hard"), (0.1, "bench"))
        early = stats.parse_time("2026-10-29T00:00:00Z")
        self.assertEqual(stats.arm_cost(arm, [], {}, self.catalog, plans, {}, early, "hard"), (0.2, "bench"))
        cost, _ = stats.arm_cost(arm, [], {}, self.catalog, dict(plans, codex="plus"), {}, now, "hard")
        self.assertAlmostEqual(cost, 0.2 * 5.8)
        # The prior (0.1 of Pro Lite's base window) halves too; Claude has no epoch.
        self.assertEqual(stats.arm_cost(self.catalog["arms"][0], [], {}, self.catalog, plans, {}, now), (0.05, "prior"))
        claude = dict(self.catalog["arms"][2], measured={"hard": {"usable": 0.9, "pct_week": 0.3, "recall": 0.8, "n": 12}})
        self.assertEqual(stats.arm_cost(claude, [], {}, self.catalog, plans, {}, now, "hard"), (0.3, "bench"))

    def test_points_are_plan_dollars_with_a_scarcity_fallback_for_unpriced_plans(self):
        self.price_catalog(gemini_price=False)
        review = 0.01 * self.CLAUDE_USD_PER_PCT
        rows = {row["entry"]["lane"]: row for row in self.context()["stats"]}
        # Codex Pro Lite at $100: prior 0.1 of the base window is 0.05% of today's.
        self.assertAlmostEqual(rows["luna"]["points"], 0.05 * self.PROLITE_USD_PER_PCT + review)
        self.assertAlmostEqual(rows["sonnet"]["points"], 0.1 * self.CLAUDE_USD_PER_PCT + review)
        # Gemini has no price here: 0.6% x scarcity 0.2 x Claude's dollars per 1%. Cline stays 0 plus the review.
        self.assertAlmostEqual(rows["gemini"]["points"], 0.6 * 0.2 * self.CLAUDE_USD_PER_PCT + review)
        self.assertAlmostEqual(rows["glm"]["points"], review)
        # With its price, Gemini pays Google AI Pro dollars.
        self.catalog["providers"]["gemini"]["plan_prices"] = {"google_ai_pro": {"usd_per_month": 19.99}}
        self.save_catalog()
        gemini = [row for row in self.context()["stats"] if row["entry"]["lane"] == "gemini"][0]
        self.assertAlmostEqual(gemini["points"], 0.6 * 19.99 / 4.345 / 100 + review)
        # A Codex plan without a price ("pro") falls back to scarcity; utilization pace scales the cost only.
        with mock.patch.dict(os.environ, {"USAGE_OPTIMIZER_MODE": "utilization"}):
            rows = {row["entry"]["lane"]: row for row in self.context({"codex": {"plan_type": "pro"}})["stats"]}
        self.assertAlmostEqual(rows["luna"]["points"], 0.25 * 0.1 * 0.3 * self.CLAUDE_USD_PER_PCT + review)
        self.assertAlmostEqual(rows["sonnet"]["points"], 0.25 * 0.1 * self.CLAUDE_USD_PER_PCT + review)
        # Fix minutes convert at Claude's rate too: half the reviews fixed, 6 minutes on average.
        for index, outcome in enumerate(("accepted", "fixed", "rejected", "fixed")):
            self.add_review(self.add_run("fix-{}".format(index)), outcome, fix_minutes=4 if index == 1 else 8)
        row = self.context()["stats"][0]
        self.assertAlmostEqual(row["points"], 0.05 * self.PROLITE_USD_PER_PCT + review
                               + 0.5 * 6 * 0.003 * self.CLAUDE_USD_PER_PCT)
        # Without a Claude price there is no dollar rate: every term stays in Claude-%, as before plan prices.
        del self.catalog["providers"]["claude"]["plan_prices"]
        self.save_catalog()
        row = self.context()["stats"][0]
        self.assertAlmostEqual(row["points"], 0.05 * 0.3 + 0.01 + 0.5 * 6 * 0.003)

    def test_report_plan_dollars_per_usable_from_the_converted_share(self):
        self.price_catalog()
        first = self.add_run("usd-1", started="2026-10-31T00:00:00Z", ended="2026-10-31T00:02:00Z",
                             usage=self.epoch_usage(10, 12, "2026-10-31T00:00:00Z"))
        # 8% on 10-29 is 4% of today's window.
        second = self.add_run("usd-2", started="2026-10-29T00:00:00Z", ended="2026-10-29T00:02:00Z",
                              usage=self.epoch_usage(20, 28, "2026-10-29T00:00:00Z"))
        self.add_review(first, "accepted")
        self.add_review(second, "fixed")
        row = json.loads(self.run_cli("report", "--json", "--by", "lane").stdout)[0]
        self.assertAlmostEqual(row["attributed_percent"]["weekly"], 10.0)
        self.assertAlmostEqual(row["wk%/run"], 3.0)
        self.assertAlmostEqual(row["wk%/usable"], 3.0)
        self.assertAlmostEqual(row["plan$/usable"], 6.0 * self.PROLITE_USD_PER_PCT / 2)
        result = self.run_cli("report", "--by", "lane")
        self.assertEqual(result.returncode, 0, result.stderr)
        header = result.stdout.splitlines()[0].split()
        self.assertEqual(header.index("$list/usable") + 1, header.index("plan$/usable"))
        self.assertIn("${:0.4f}".format(6.0 * self.PROLITE_USD_PER_PCT / 2), result.stdout.splitlines()[2].split())
        # Without a Claude price points are not dollars, so the column is empty; wk% still converts.
        del self.catalog["providers"]["claude"]["plan_prices"]
        self.save_catalog()
        row = json.loads(self.run_cli("report", "--json", "--by", "lane").stdout)[0]
        self.assertIsNone(row["plan$/usable"])
        self.assertAlmostEqual(row["wk%/usable"], 3.0)

    def test_catalog_validation_of_epochs_prices_prior_plans_and_weeks(self):
        self.price_catalog()
        stats.validate_catalog(self.catalog)

        def changed(change):
            catalog = json.loads(json.dumps(self.catalog))
            change(catalog["providers"]["codex"], catalog)
            return catalog

        good_epoch = dict(self.EPOCH)
        for change, message in (
                (lambda codex, _: codex.update(window_epochs={"plan": "prolite"}), r"window_epochs: needs a list"),
                (lambda codex, _: codex.update(window_epochs=["prolite"]), r"window_epochs\[0\]: needs an object"),
                (lambda codex, _: codex.update(window_epochs=[dict(good_epoch, plan="")]), r"window_epochs\[0\]\.plan"),
                (lambda codex, _: codex.update(window_epochs=[good_epoch, dict(good_epoch, **{"from": "soon"})]),
                 r"window_epochs\[1\]\.from"),
                (lambda codex, _: codex.update(window_epochs=[dict(good_epoch, scale=0)]), r"\.scale: needs a number above 0"),
                (lambda codex, _: codex.update(window_epochs=[dict(good_epoch, scale=-2)]), r"\.scale"),
                (lambda codex, _: codex.update(window_epochs=[dict(good_epoch, scale="2.0")]), r"\.scale"),
                (lambda codex, _: codex.update(window_epochs=[dict(good_epoch, scale=True)]), r"\.scale"),
                (lambda codex, _: codex.update(window_epochs=[dict(good_epoch, source=3)]), r"\.source"),
                (lambda codex, _: codex.update(plan_prices=[100]), r"plan_prices: needs an object"),
                (lambda codex, _: codex.update(plan_prices={"prolite": {"usd_per_month": 0}}),
                 r"plan_prices\.prolite\.usd_per_month"),
                (lambda codex, _: codex.update(plan_prices={"prolite": {"usd_per_month": "100"}}), r"usd_per_month"),
                (lambda codex, _: codex.update(plan_prices={"prolite": 100}), r"usd_per_month"),
                (lambda codex, _: codex.update(plan_prices={"plus": {"usd_per_month": 20, "checked": 20261031}}),
                 r"plan_prices\.plus\.checked"),
                (lambda codex, _: codex.update(prior_plan=3), r"prior_plan"),
                (lambda codex, _: codex.update(prior_plan=""), r"prior_plan"),
                (lambda _, catalog: catalog["explore"].update(weeks_per_month=0), r"weeks_per_month"),
                (lambda _, catalog: catalog["explore"].update(weeks_per_month="4.345"), r"weeks_per_month")):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                stats.validate_catalog(changed(change))
        # The loader shows which key is wrong, so `lane-stats arms` names it in its one line.
        self.catalog["providers"]["codex"]["window_epochs"][0]["scale"] = 0
        self.save_catalog()
        result = self.run_cli("arms")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr.strip(), "lane-stats: invalid arms catalog "
                         "(invalid providers.codex.window_epochs[0].scale: needs a number above 0)")
        # A broken file still shows only its error type: its message could carry a path.
        with open(self.catalog_path, "w", encoding="utf-8") as stream:
            stream.write("{broken")
        self.assertEqual(self.run_cli("arms").stderr.strip(), "lane-stats: invalid arms catalog (JSONDecodeError)")

    def test_catalog_rejects_plans_a_provider_lacks_and_plan_scales_that_are_not_above_zero(self):
        self.price_catalog()
        self.catalog["providers"]["claude"]["plan_scale"] = {"max_20x": 1.0, "max_5x": 4.0}
        self.catalog["providers"]["claude"]["plan_prices"]["max_5x"] = {"usd_per_month": 100}
        stats.validate_catalog(self.catalog)

        def changed(provider, remove=(), **update):
            catalog = json.loads(json.dumps(self.catalog))
            for key in remove:
                del catalog["providers"][provider][key]
            catalog["providers"][provider].update(update)
            return catalog

        for catalog, message in (
                # An epoch names a plan_scale plan; "pro" is not one of codex's.
                (changed("codex", window_epochs=[dict(self.EPOCH, plan="pro")]), r"window_epochs\[0\]\.plan"),
                # A price names a plan the provider has: plan_scale keys, and prior_plan.
                (changed("codex", plan_prices={"pro": {"usd_per_month": 100}}), r"plan_prices\.pro"),
                (changed("claude", plan_prices={"max_5x": {"usd_per_month": 100},
                                                "max_1x": {"usd_per_month": 50}}), r"plan_prices\.max_1x"),
                # Without plan_scale an epoch can only name the prior_plan, max_20x.
                (changed("claude", remove=("plan_scale",), window_epochs=[dict(self.EPOCH, plan="max_5x")]),
                 r"window_epochs\[0\]\.plan"),
                # A plan_scale of 0 would make every run free, so it is rejected like a negative one.
                (changed("codex", plan_scale={"prolite": 0, "plus": 5.8}), r"plan_scale"),
                (changed("codex", plan_scale={"prolite": 1.0, "plus": -5.8}), r"plan_scale"),
                # An epoch scale of 0 is rejected too.
                (changed("codex", window_epochs=[dict(self.EPOCH, scale=0)]), r"\.scale"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                stats.validate_catalog(catalog)

    def test_report_gives_scarcity_priced_values_points_not_plan_dollars(self):
        self.price_catalog(gemini_price=False)
        # Codex at Pro Lite, read after the doubling: its 2% is already a share of today's window.
        luna = self.add_run("pts-luna", lane="luna", started="2026-10-31T00:00:00Z", ended="2026-10-31T00:02:00Z",
                            usage=self.epoch_usage(10, 12, "2026-10-31T00:00:00Z"))
        self.add_review(luna, "accepted")
        # Gemini has no price here: 2% on the scarcity fallback, which is points (Claude-% x scarcity), not plan $.
        gemini = self.add_run("pts-gemini", lane="gemini", started="2026-10-31T00:00:00Z",
                              ended="2026-10-31T00:02:00Z", usage=self.usage(20, 22))
        self.add_review(gemini, "accepted")
        rows = {row["lane"]: row for row in json.loads(self.run_cli("report", "--json", "--by", "lane").stdout)}
        self.assertAlmostEqual(rows["luna"]["plan$/usable"], 2.0 * self.PROLITE_USD_PER_PCT)
        self.assertAlmostEqual(rows["luna"]["pts/usable"], 2.0 * self.PROLITE_USD_PER_PCT)
        self.assertIsNone(rows["gemini"]["plan$/usable"])
        self.assertAlmostEqual(rows["gemini"]["wk%/usable"], 2.0)
        self.assertAlmostEqual(rows["gemini"]["pts/usable"], 2.0 * 0.2 * self.CLAUDE_USD_PER_PCT)
        result = self.run_cli("report", "--by", "lane")
        self.assertEqual(result.returncode, 0, result.stderr)
        header = result.stdout.splitlines()[0].split()
        self.assertEqual(header[-1], "pts/usable")
        gemini_line = [line for line in result.stdout.splitlines() if line.startswith("gemini")][0]
        self.assertNotIn("$", gemini_line)
        self.assertIn("{:0.4f}".format(2.0 * 0.2 * self.CLAUDE_USD_PER_PCT), gemini_line.split())

    def test_export_stops_on_an_invalid_catalog_instead_of_exporting_straddling_waves(self):
        self.price_catalog()
        self.add_run("export-pre", started="2026-10-29T00:00:00Z", ended="2026-10-29T00:02:00Z",
                     usage=self.epoch_usage(10, 12, "2026-10-29T00:00:00Z"))
        self.add_run("export-straddle", started="2026-10-29T23:58:00Z", ended="2026-10-30T00:02:00Z",
                     usage=self.epoch_usage(3, 4, "2026-10-29T23:58:00Z", "2026-10-30T00:02:00Z"))
        self.assertEqual(len(self.run_cli("export").stdout.splitlines()), 2)
        self.catalog["providers"]["codex"]["window_epochs"][0]["scale"] = 0
        self.save_catalog()
        result = self.run_cli("export")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("export stopped, so no wave straddling a window epoch goes out unskipped", result.stderr)
        self.assertIn("invalid arms catalog (invalid providers.codex.window_epochs[0].scale", result.stderr)
        # A missing catalog stops it the same way.
        os.remove(self.catalog_path)
        result = self.run_cli("export")
        self.assertEqual((result.returncode, result.stdout), (2, ""))

    def test_max_5x_takes_four_times_the_percent_of_max_20x_and_costs_half_per_percent(self):
        with open(os.path.join(ROOT, "arms.json"), encoding="utf-8") as stream:
            catalog = json.load(stream)
        settings = catalog["providers"]["claude"]
        now = stats.parse_time("2026-10-31T00:00:00Z")
        # plan_scale is the % one unit takes, so the smaller 5x window takes 4x the % of the 20x window.
        self.assertEqual(stats.convert_pct(1.0, settings, "max_20x", now, "max_5x", now), 4.0)
        self.assertEqual(stats.convert_pct(1.0, settings, "max_5x", now, "max_20x", now), 0.25)
        # An arm with no measurement falls back to its prior, a share of max_20x's window, so 4x on max_5x.
        arm = dict(catalog["arms"][[(a["lane"], a["effort"]) for a in catalog["arms"]].index(("sonnet", "medium"))],
                   measured={})
        cost_5x, tier_5x = stats.arm_cost(arm, [], {}, catalog, {"claude": "max_5x"}, {}, now, "mechanical")
        cost_20x, tier_20x = stats.arm_cost(arm, [], {}, catalog, {"claude": "max_20x"}, {}, now, "mechanical")
        self.assertEqual((tier_5x, tier_20x), ("prior", "prior"))
        self.assertAlmostEqual(cost_5x, 4.0 * cost_20x)
        # Dollars: the 5x plan's price per % is half the 20x one, so the run's plan $ is 4 x 1/2 = 2x.
        self.assertAlmostEqual(stats.usd_per_pct(catalog, "claude", "max_5x") * cost_5x,
                               2.0 * stats.usd_per_pct(catalog, "claude", "max_20x") * cost_20x)

    def test_repository_catalog_has_the_window_epoch_and_plan_prices(self):
        with open(os.path.join(ROOT, "arms.json"), encoding="utf-8") as stream:
            catalog = json.load(stream)
        stats.validate_catalog(catalog)
        providers = catalog["providers"]
        self.assertEqual(providers["codex"]["window_epochs"], [{
            "plan": "prolite", "from": "2026-10-29T16:56:07Z", "scale": 2.0,
            "source": "Tibo (@thsottiaux, OpenAI) on X, 2026-10-29 16:56:07 UTC, "
                      "https://x.com/thsottiaux/status/2115850175868727621: usage limits doubled for the Pro "
                      "100/200/500 tiers and Business Premium, effective that day, no end date given; Plus is not named. "
                      "Meter: 6% -> 3% between 2026-10-29 04:02 and 10-30 00:24 UTC on the window resetting "
                      "2026-11-04T06:42Z with no spend between."}])
        self.assertEqual({name: {plan: price["usd_per_month"] for plan, price in settings.get("plan_prices", {}).items()}
                          for name, settings in providers.items()},
                         {"codex": {"prolite": 100, "plus": 20}, "claude": {"max_20x": 200, "max_5x": 100},
                          "gemini": {"google_ai_pro": 19.99}, "cline": {}, "cursor": {}, "grok": {}, "amp": {}})
        self.assertEqual(providers["claude"]["plan_scale"], {"max_20x": 1.0, "max_5x": 4.0})
        self.assertTrue(all(price["checked"] == "2026-10-31" and price["source"]
                            for settings in providers.values() for price in settings.get("plan_prices", {}).values()))
        self.assertEqual({name: settings.get("prior_plan") for name, settings in providers.items()},
                         {"codex": "prolite", "claude": "max_20x", "gemini": "google_ai_pro", "cline": None,
                          "cursor": None, "grok": None, "amp": None})
        self.assertEqual(catalog["explore"]["weeks_per_month"], 4.345)
        self.assertEqual(catalog["catalog_version"], "2026-11-14.1")
        # The base window stays the measured 8,400: lane-bench divides credits by it, and plan_scale is base too.
        self.assertEqual(providers["codex"]["window"]["weekly_credits"], 8400)
        self.assertEqual(providers["codex"]["plan_scale"], {"prolite": 1.0, "plus": 5.8})
        self.assertEqual((providers["claude"]["scarcity"], providers["codex"]["scarcity"],
                          providers["gemini"]["scarcity"], providers["cline"]["scarcity"]), (1.0, 0.3, 0.2, 0.0))
        self.assertEqual((catalog["explore"]["claude_guard_pct"], catalog["explore"]["exclude_weekly_pct"],
                          catalog["explore"]["exclude_5h_pct"]), (85, 95, 90))

    def place_catalog(self):
        # Codex and gemini lanes run in process only; sonnet (a Claude lane) runs in all three places.
        for lane in ("luna", "sol", "gemini"):
            self.catalog["lanes"][lane]["places"] = ["process"]
        self.catalog["lanes"]["sonnet"]["places"] = ["process", "subagent", "cloud"]
        self.save_catalog()

    def test_places_setting_keeps_codex_and_gemini_out_of_forced_and_floor_draws(self):
        self.place_catalog()
        os.environ["LANES_PLACES"] = "cloud,subagent"
        # Forced: nothing reviewed yet, so every eligible arm is forced. Floor: min_runs 0 and floor 1.
        for min_runs, floor, expected in ((2, 0.2, "forced"), (0, 1.0, "floor")):
            self.catalog["explore"]["min_runs"] = min_runs
            self.catalog["explore"]["floor"] = floor
            self.save_catalog()
            for seed in range(200):
                row = json.loads(self.direct_cli("pick", "--class", "hard", "--no-usage", "--seed", str(seed),
                                                 "--json"))
                self.assertEqual(row["mode"], expected)
                self.assertEqual([arm.split("/")[0] for arm in row["arms"]], ["sonnet"], "seed {}".format(seed))
                self.assertTrue(row["run_lines"][0].startswith("lane sonnet --subagent -C"), row["run_lines"][0])

    def test_place_flag_restricts_one_pick_prints_the_flag_and_names_the_skipped_lanes(self):
        self.place_catalog()
        text = self.run_cli("pick", "--class", "hard", "--place", "cloud", "--no-usage", "--seed", "1")
        self.assertEqual(text.returncode, 0, text.stderr)
        self.assertIn("skipped luna, sol, gemini: they do not run in place cloud (allowed places: process, subagent, cloud)",
                      text.stdout.splitlines())
        runs = [line for line in text.stdout.splitlines() if line.startswith("run  ")]
        self.assertEqual(len(runs), 1)
        self.assertTrue(runs[0].startswith("run  lane sonnet --cloud -C <DIR>"), runs[0])
        result = self.run_cli("pick", "--class", "hard", "--place", "cloud", "--no-usage", "--seed", "1", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["arms"], ["sonnet/sonnet/high"])
        self.assertTrue(payload["run_lines"][0].startswith("lane sonnet --cloud -C"))
        self.assertEqual(payload["skipped_places"], [{"lane": "luna", "places": ["process"]},
                                                     {"lane": "sol", "places": ["process"]},
                                                     {"lane": "gemini", "places": ["process"]}])
        self.assertEqual(self.picks()[-1]["place"], "cloud")
        subagent = json.loads(self.run_cli("pick", "--class", "hard", "--place", "subagent", "--no-usage", "--seed", "1",
                                           "--json").stdout)
        self.assertTrue(subagent["run_lines"][0].startswith("lane sonnet --subagent -C"))
        process = self.run_cli("pick", "--class", "hard", "--place", "process", "--no-usage", "--seed", "1")
        self.assertNotIn("skipped", process.stdout)
        self.assertEqual(self.picks()[-1]["place"], "process")
        unplaced = json.loads(self.run_cli("pick", "--class", "hard", "--no-usage", "--seed", "1", "--json").stdout)
        self.assertNotIn("skipped_places", unplaced)
        self.assertIsNone(self.picks()[-1]["place"])

    def test_places_setting_chooses_a_flag_for_each_lane_it_allows(self):
        self.place_catalog()
        os.environ["LANES_PLACES"] = "cloud,subagent"
        # sonnet runs in process too, but process is not allowed here: the flag is subagent, the first allowed place.
        payload = json.loads(self.run_cli("pick", "--class", "hard", "--no-usage", "--seed", "1", "--json").stdout)
        self.assertEqual(payload["arms"], ["sonnet/sonnet/high"])
        self.assertTrue(payload["run_lines"][0].startswith("lane sonnet --subagent -C"))
        self.assertEqual({entry["lane"] for entry in payload["skipped_places"]}, {"luna", "sol", "gemini"})

    def test_place_errors_name_the_allowed_places(self):
        self.place_catalog()
        os.environ["LANES_PLACES"] = "cloud,bogus"
        unknown_setting = self.run_cli("pick", "--class", "hard", "--no-usage", "--seed", "1")
        self.assertEqual(unknown_setting.returncode, 2)
        self.assertIn("unknown place bogus in LANES_PLACES (places: process, subagent, cloud)", unknown_setting.stderr)
        os.environ.pop("LANES_PLACES")
        unknown_flag = self.run_cli("pick", "--class", "hard", "--place", "bogus", "--no-usage", "--seed", "1")
        self.assertEqual(unknown_flag.returncode, 2)
        self.assertIn("unknown place bogus", unknown_flag.stderr)
        os.environ["LANES_PLACES"] = "cloud"
        refused = self.run_cli("pick", "--class", "hard", "--place", "subagent", "--no-usage", "--seed", "1")
        self.assertEqual(refused.returncode, 2)
        self.assertIn("place subagent is not allowed on this machine (allowed places: cloud)", refused.stderr)
        self.catalog["lanes"]["sonnet"]["places"] = ["process"]
        self.save_catalog()
        empty = self.run_cli("pick", "--class", "hard", "--no-usage", "--seed", "1")
        self.assertEqual(empty.returncode, 2)
        self.assertIn("no eligible arms for hard (allowed places: cloud)", empty.stderr)
        os.environ["LANES_PLACES"] = " , "
        blank = self.run_cli("pick", "--class", "hard", "--no-usage", "--seed", "1")
        self.assertEqual(blank.returncode, 2)
        self.assertIn("LANES_PLACES names no place", blank.stderr)
        os.environ["LANES_PLACES"] = "   "
        self.assertEqual(self.run_cli("pick", "--class", "hard", "--no-usage", "--seed", "1").returncode, 0)

    def test_without_a_places_setting_codex_arms_stay_eligible(self):
        self.place_catalog()
        rows = stats.eligible_arms(self.context(), "hard")
        self.assertEqual({row["entry"]["lane"] for row in rows}, {"luna", "sol", "sonnet", "gemini"})
        payload = json.loads(self.run_cli("pick", "--class", "hard", "--no-usage", "--seed", "1", "--json").stdout)
        self.assertNotIn("skipped_places", payload)
        self.assertIsNone(self.picks()[-1]["place"])
        for line in payload["run_lines"]:
            self.assertNotIn("--cloud", line)
            self.assertNotIn("--subagent", line)

    def test_explore_places_from_the_catalog_is_honoured_and_the_setting_overrides_it(self):
        self.place_catalog()
        self.catalog["explore"]["places"] = ["cloud"]
        self.save_catalog()
        payload = json.loads(self.run_cli("pick", "--class", "hard", "--no-usage", "--seed", "1", "--json").stdout)
        self.assertEqual(payload["arms"], ["sonnet/sonnet/high"])
        self.assertTrue(payload["run_lines"][0].startswith("lane sonnet --cloud -C"))
        os.environ["LANES_PLACES"] = "process"
        process = json.loads(self.run_cli("pick", "--class", "hard", "--no-usage", "--seed", "1", "--json").stdout)
        self.assertNotIn("skipped_places", process)
        self.assertNotIn("--cloud", process["run_lines"][0])
        self.assertNotIn("--subagent", process["run_lines"][0])

    def test_invalid_places_in_the_catalog_are_rejected(self):
        self.place_catalog()
        for section, value in (("explore", ["cloud", "cloud"]), ("explore", ["teleport"]), ("explore", []),
                               ("lanes", []), ("lanes", "process"), ("lanes", ["process", "teleport"])):
            self.place_catalog()
            self.catalog["explore"].pop("places", None)
            if section == "explore":
                self.catalog["explore"]["places"] = value
            else:
                self.catalog["lanes"]["luna"]["places"] = value
            self.save_catalog()
            result = self.run_cli("pick", "--class", "hard", "--no-usage", "--seed", "1")
            self.assertEqual(result.returncode, 2, value)
            self.assertIn("invalid explore.places" if section == "explore" else "invalid lanes.luna.places",
                          result.stderr)

    def test_repository_catalog_says_where_each_lane_runs(self):
        with open(os.path.join(ROOT, "arms.json"), encoding="utf-8") as stream:
            catalog = json.load(stream)
        stats.validate_catalog(catalog)
        places = {lane: settings["places"] for lane, settings in catalog["lanes"].items()}
        self.assertEqual(places, {
            "luna": ["process"], "terra": ["process"], "sol": ["process"], "astra": ["process"],
            "gemini": ["process"], "glm": ["process"], "cursor": ["process"], "grok": ["process"],
            "amp": ["process"], "haiku": ["process", "subagent", "cloud"],
            "sonnet": ["process", "subagent", "cloud"], "opus": ["process", "subagent", "cloud"],
            "fable": ["process", "subagent"], "codex-cloud": ["cloud"]})
        self.assertEqual(catalog["explore"]["places"], ["process", "subagent", "cloud"])


class AmpStatsTests(unittest.TestCase):
    def test_amp_is_a_metered_provider_without_an_account_meter(self):
        self.assertEqual(stats.PROVIDERS["amp"], "amp")
        self.assertEqual(stats.provider_mode("amp", {}, {}, datetime.datetime(2026, 11, 13, tzinfo=datetime.timezone.utc)),
                         "utilization")
        with open(os.path.join(ROOT, "arms.json"), encoding="utf-8") as stream:
            catalog = json.load(stream)
        self.assertEqual(catalog["lanes"]["amp"]["provider"], "amp")
        self.assertIsNone(catalog["providers"]["amp"]["billed_to"])
        self.assertTrue(all(arm["status"] == "manual" for arm in catalog["arms"] if arm["lane"] == "amp"))


class CursorGrokStatsTests(unittest.TestCase):
    def setUp(self):
        self.old_env = os.environ.copy()
        self.temp = os.path.join(os.path.dirname(__file__), ".lane-stats-{}-{}".format(
            os.getpid(), uuid.uuid4().hex))
        os.mkdir(self.temp)
        self.state = os.path.join(self.temp, "lanes")
        os.makedirs(os.path.join(self.state, "runs"))
        os.environ["LANES_STATE"] = self.state
        os.environ["LANES_ARMS"] = os.path.join(ROOT, "arms.json")
        os.environ["LANES_ARMS_LOCAL"] = os.path.join(self.temp, "arms.local.json")
        os.environ["LANES_CONFIG"] = os.path.join(self.temp, "config")
        os.environ["LANES_MACHINE"] = "this-machine"
        os.environ["LANES_PLACES"] = "process"
        os.environ.pop("USAGE_OPTIMIZER_MODE", None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old_env)
        shutil.rmtree(self.temp)

    def run_cli(self, *args):
        env = os.environ.copy()
        return subprocess.run([sys.executable, SCRIPT] + list(args), cwd=ROOT, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", check=False)

    def add_run(self, name, **kwargs):
        run_dir = os.path.join(self.state, "runs", name)
        os.makedirs(run_dir)
        row = {"run_dir": run_dir, "lane": kwargs.get("lane", "cursor"), "provider": kwargs.get("provider"),
               "model": kwargs.get("model", "composer-2.5"), "effort": kwargs.get("effort", "medium"),
               "class": kwargs.get("class_name", "substantive"), "tag": None, "ro": False, "resume": None,
               "started_at": "2026-10-17T00:00:00Z", "ended_at": "2026-10-17T00:02:00Z", "duration_s": 120,
               "verdict": "OK", "exit_code": 0, "session_id": "s1",
               "usage": kwargs.get("usage", {"before": None, "after": None, "tokens": {"total": 112},
                                            "list_usd": None})}
        with open(os.path.join(run_dir, "meta.json"), "w", encoding="utf-8") as stream:
            json.dump(row, stream)
        with open(os.path.join(self.state, "ledger.jsonl"), "a", encoding="utf-8") as stream:
            stream.write(json.dumps(row) + "\n")
        return run_dir

    def test_pick_substantive_can_return_cursor_or_grok_when_every_other_lane_is_excluded(self):
        excluded = ("luna", "terra", "sol", "astra", "haiku", "sonnet", "opus", "fable", "gemini", "glm",
                    "codex-cloud")
        result = self.run_cli("pick", "--class", "substantive", "--no-usage", "--seed", "1",
                              "--exclude", ",".join(excluded), "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        lanes = {line.split()[1] for line in payload["run_lines"]}
        self.assertTrue(lanes <= {"cursor", "grok"}, payload)
        self.assertTrue(lanes & {"cursor", "grok"})
        self.assertFalse(any("composer" in arm for arm in payload["arms"]), payload)

    def test_mode_lists_cursor_and_grok_as_utilization_after_the_metered_providers(self):
        os.environ["USAGE_OPTIMIZER_MODE"] = "default"
        result = self.run_cli("mode", "--no-usage", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["providers"]["cursor"]["mode"], "utilization")
        self.assertEqual(data["providers"]["grok"]["mode"], "utilization")
        self.assertEqual(data["providers"]["cline"]["mode"], "default")
        lines = self.run_cli("mode", "--no-usage").stdout.splitlines()
        self.assertEqual([line.split()[0] for line in lines[:3]], ["claude", "codex", "gemini"])
        self.assertIn(["cursor", "utilization"], [line.split()[:2] for line in lines])
        self.assertIn(["grok", "utilization"], [line.split()[:2] for line in lines])

    def test_report_does_not_crash_on_a_cursor_run_in_the_ledger(self):
        self.add_run("cursor-substantive", lane="cursor", model="composer-2.5", effort="medium",
                     class_name="substantive")
        result = self.run_cli("report", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout))



LANE_SCRIPT = os.path.join(ROOT, "bin", "lane")
lane_loader = importlib.machinery.SourceFileLoader("lane_for_platform_agreement", LANE_SCRIPT)
lane = importlib.util.module_from_spec(importlib.util.spec_from_loader(lane_loader.name, lane_loader))
lane_loader.exec_module(lane)


class PlatformPlacesTests(unittest.TestCase):
    def shipped_catalog(self):
        with open(os.path.join(ROOT, "arms.json"), encoding="utf-8") as stream:
            return json.load(stream)

    def allowed(self, env, catalog=None):
        with mock.patch.dict(os.environ, env, clear=True):
            return stats.allowed_places_with_source(catalog or self.shipped_catalog())

    def test_codex_never_offers_the_subagent_place_and_amp_does(self):
        names, source = self.allowed({"KIT_PLATFORM": "codex"})
        self.assertEqual(names, ["process", "cloud"])
        self.assertIn("narrowed to platform codex", source)
        self.assertEqual(self.allowed({"KIT_PLATFORM": "amp"})[0], ["process", "subagent", "cloud"])

    def test_lanes_places_cannot_add_a_place_the_platform_lacks(self):
        self.assertEqual(self.allowed({"KIT_PLATFORM": "codex", "LANES_PLACES": "process,subagent"})[0], ["process"])
        with self.assertRaises(ValueError) as caught:
            self.allowed({"KIT_PLATFORM": "codex", "LANES_PLACES": "subagent"})
        self.assertIn("no allowed place", str(caught.exception))

    def test_amp_runs_only_its_agent_lanes_as_subagents(self):
        catalog = self.shipped_catalog()
        with mock.patch.dict(os.environ, {"KIT_PLATFORM": "amp"}, clear=True):
            self.assertEqual(stats.lane_places(catalog, "sonnet"), ["process", "subagent", "cloud"])
            self.assertEqual(stats.lane_places(catalog, "fable"), ["process", "subagent"])
            for name in ("luna", "sol", "gemini", "cursor", "grok", "glm"):
                self.assertNotIn("subagent", stats.lane_places(catalog, name))
        catalog["lanes"]["luna"]["places"] = ["process", "subagent"]
        with mock.patch.dict(os.environ, {"KIT_PLATFORM": "amp"}, clear=True):
            self.assertEqual(stats.lane_places(catalog, "luna"), ["process"])
        with mock.patch.dict(os.environ, {"KIT_PLATFORM": "claude-code"}, clear=True):
            self.assertEqual(stats.lane_places(catalog, "luna"), ["process", "subagent"])

    def test_pick_on_amp_prints_subagent_only_for_agent_lanes(self):
        catalog = self.shipped_catalog()
        with mock.patch.dict(os.environ, {"KIT_PLATFORM": "amp", "LANES_PLACES": "subagent,cloud"}, clear=True):
            allowed = stats.allowed_places(catalog)
            self.assertEqual(stats.run_place("haiku", catalog, allowed, None), "subagent")
            self.assertEqual(stats.run_place("opus", catalog, allowed, None), "subagent")
        with mock.patch.dict(os.environ, {"KIT_PLATFORM": "amp"}, clear=True):
            self.assertEqual(stats.run_place("sonnet", catalog, stats.allowed_places(catalog), None), "process")

    def test_subagent_lanes_and_agent_providers_agree_with_lanes_copy(self):
        for key in ("subagent_lanes", "agent_providers"):
            self.assertEqual(self.shipped_catalog()["explore"]["platforms"]["amp"][key], stats.PLATFORM_DEFAULTS["amp"][key])
            self.assertEqual(stats.PLATFORM_DEFAULTS["amp"][key], lane.PLATFORM_DEFAULTS["amp"][key])

    def test_claude_code_keeps_all_three_places(self):
        self.assertEqual(self.allowed({"CLAUDECODE": "1"})[0], ["process", "subagent", "cloud"])
        self.assertEqual(self.allowed({"KIT_PLATFORM": "claude-code"})[0], ["process", "subagent", "cloud"])
        self.assertEqual(self.allowed({})[0], ["process", "subagent", "cloud"])

    def test_kit_platform_copies_in_lane_and_lane_stats_agree(self):
        custom = {"explore": {"places": ["process", "subagent", "cloud"], "platforms": {
            "amp": {"places": ["process", "cloud"], "env_markers": ["KIT_AGREE_MARKER"]},
            "claude-code": {"places": ["process", "subagent", "cloud"], "env_markers": ["CLAUDECODE"]}}}}
        cases = [
            ({}, self.shipped_catalog()), ({"CLAUDECODE": "1"}, self.shipped_catalog()),
            ({"KIT_PLATFORM": "amp"}, self.shipped_catalog()), ({"KIT_PLATFORM": "codex"}, self.shipped_catalog()),
            ({"KIT_PLATFORM": " amp "}, self.shipped_catalog()), ({"KIT_PLATFORM": "nope"}, self.shipped_catalog()),
            ({}, custom), ({"KIT_AGREE_MARKER": "1"}, custom), ({"KIT_AGREE_MARKER": "1", "CLAUDECODE": "1"}, custom),
            ({"CLAUDECODE": "1"}, None),
        ]
        for env, catalog in cases:
            with mock.patch.dict(os.environ, env, clear=True):
                try:
                    lane_answer = lane.kit_platform(catalog)
                except ValueError:
                    lane_answer = "ValueError"
                try:
                    stats_answer = stats.kit_platform(catalog)
                except ValueError:
                    stats_answer = "ValueError"
                self.assertEqual(lane_answer, stats_answer, (env, catalog is None))
                if lane_answer != "ValueError":
                    for platform in (catalog or self.shipped_catalog())["explore"].get("platforms", {"claude-code": {}}):
                        self.assertEqual(lane.platform_places(catalog, platform), stats.platform_places(catalog, platform))

    def test_catalog_rejects_a_platform_with_a_place_it_cannot_name(self):
        catalog = self.shipped_catalog()
        catalog["explore"]["platforms"]["amp"]["places"] = ["process", "bogus"]
        with self.assertRaises(stats.CatalogError):
            stats.validate_catalog(catalog)
        catalog = self.shipped_catalog()
        stats.validate_catalog(catalog)


if __name__ == "__main__":
    unittest.main()
