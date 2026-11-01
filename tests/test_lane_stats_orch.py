"""Tests for the mirror features of bin/lane-stats: main-picks, absent providers and import-orch.

Everything runs on fixtures: a temp state dir, a temp arms catalog, temp git repositories with a bare origin as the
network. Nothing reads the real ~/.local/state/lanes or ~/.config/lanes.
"""

import contextlib
import datetime
import importlib.machinery
import importlib.util
import io
import json
import os
import random
import re
import shutil
import stat
import subprocess
import sys
import unittest
import uuid
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "bin", "lane-stats")
loader = importlib.machinery.SourceFileLoader("lane_stats_orch_tested", SCRIPT)
stats = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
loader.exec_module(stats)

CLASSES = ("mechanical", "substantive", "hard", "design", "review", "research")
OUTCOMES = ("accepted", "fixed", "rework", "rejected")
ARM_KEYS = {"arm", "lane", "where", "reviewed", "outcomes", "usable", "points", "minutes", "p_pick", "forced"}
TOP_KEYS = {"version", "at", "kit", "repo", "plans", "modes", "modes_until", "excluded", "classes"}
PROVIDER_OF = {"luna": "codex", "sol": "codex", "sonnet": "claude", "haiku": "claude", "gemini": "gemini"}
UTC = datetime.timezone.utc


def force_rmtree(path):
    def retry(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=retry)
    else:
        shutil.rmtree(path, onerror=retry)


class OrchTestCase(unittest.TestCase):
    """A temp state dir, config dir and arms catalog, like tests/test_lane_stats.py, plus CLI helpers."""

    # lane, model, effort, status, classes, prior_pct, prior_usable
    ARMS = (
        ("luna", "gpt-6-luna", "medium", "active", ("mechanical", "research"), 1.0, 0.7),
        ("sol", "gpt-6.1-sol", "xhigh", "active", ("hard", "design", "review"), 4.0, 0.85),
        ("sonnet", "claude-sonnet-5-5", "high", "active", ("substantive", "hard", "research", "review"), 3.0, 0.8),
        ("sonnet", "claude-sonnet-5-5", "medium", "active", ("mechanical", "substantive"), 1.5, 0.75),
        ("haiku", "claude-haiku-5-5", "medium", "active", ("mechanical", "research", "review"), 0.5, 0.6),
        ("gemini", "gemini-3.8-flash-medium", "medium", "active", ("mechanical", "substantive", "research"), 1.2, 0.5),
        ("sonnet", "claude-sonnet-5-5", "max", "manual", ("hard", "design"), 6.0, 0.9),
        ("haiku", "claude-haiku-5-5", "xhigh", "retired", CLASSES, 2.0, 0.7),
    )
    SONNET_HIGH = "sonnet/claude-sonnet-5-5/high"
    HAIKU_MEDIUM = "haiku/claude-haiku-5-5/medium"
    LUNA_MEDIUM = "luna/gpt-6-luna/medium"

    def setUp(self):
        old_env = os.environ.copy()
        self.addCleanup(self.restore_env, old_env)
        self.temp = os.path.join(os.path.dirname(__file__), ".lane-stats-orch-{}-{}".format(
            os.getpid(), uuid.uuid4().hex))
        os.mkdir(self.temp)
        self.addCleanup(force_rmtree, self.temp)
        self.state = os.path.join(self.temp, "lanes")
        os.makedirs(os.path.join(self.state, "runs"))
        self.config = os.path.join(self.temp, "config")
        self.catalog_path = os.path.join(self.temp, "arms.json")
        os.environ["LANES_STATE"] = self.state
        os.environ["LANES_CONFIG"] = self.config
        os.environ["LANES_ARMS"] = self.catalog_path
        os.environ["LANES_ARMS_LOCAL"] = os.path.join(self.temp, "arms.local.json")
        os.environ["LANES_MACHINE"] = "this-machine"
        os.environ["PYTHONUTF8"] = "1"
        for name in list(os.environ):
            if name.startswith("USAGE_OPTIMIZER_"):
                del os.environ[name]
        self.counter = 0
        self.catalog = {
            "lanes": {"luna": {"model": "gpt-6-luna", "provider": "codex"},
                      "sol": {"model": "gpt-6.1-sol", "provider": "codex"},
                      "sonnet": {"model": "claude-sonnet-5-5", "provider": "claude"},
                      "haiku": {"model": "claude-haiku-5-5", "provider": "claude"},
                      "gemini": {"model": "gemini-3.8-flash-medium", "provider": "gemini"}},
            "providers": {
                "codex": {"scarcity": 0.3, "prior_plan": "prolite", "plan_scale": {"prolite": 1.0, "plus": 5.0},
                          "plan_prices": {"prolite": {"usd_per_month": 100}}},
                "claude": {"scarcity": 1.0, "prior_plan": "max_20x",
                           "plan_prices": {"max_20x": {"usd_per_month": 200}}},
                "gemini": {"scarcity": 0.2, "prior_plan": "google_ai_pro",
                           "plan_prices": {"google_ai_pro": {"usd_per_month": 19.99}}}},
            "explore": {"min_runs": 2, "floor": 0.2, "half_life_days": 60, "shrink": 2.0,
                        "review_points": 0.01, "fix_points_per_minute": 0.003, "weeks_per_month": 4.345,
                        "targets": {"mechanical": 0.8, "substantive": 0.7, "hard": 0.5, "design": 0.5,
                                    "review": 0.7, "research": 0.7},
                        "pace": {"low_pct": 60, "high_pct": 90, "low_factor": 0.25, "high_factor": 3.0},
                        "exclude_weekly_pct": 95, "exclude_5h_pct": 90, "claude_guard_pct": 85,
                        "lock": {"leaning_p": 0.5, "leaning_runs": 4, "locked_p": 0.8, "locked_runs": 8},
                        "measured_weight": 4, "measured_shrink": 4.0, "measured_min_n": 10},
            "arms": [{"lane": lane, "model": model, "effort": effort, "status": status, "classes": list(classes),
                      "weight": 1.0, "prior_pct": cost, "prior_usable": usable}
                     for lane, model, effort, status, classes, cost, usable in self.ARMS]}
        self.save_catalog()

    @staticmethod
    def restore_env(old_env):
        os.environ.clear()
        os.environ.update(old_env)

    def save_catalog(self):
        with open(self.catalog_path, "w", encoding="utf-8") as stream:
            json.dump(self.catalog, stream)

    def run_cli(self, *args):
        env = os.environ.copy()
        env["LANES_STATE"] = self.state
        env["PYTHONUTF8"] = "1"
        return subprocess.run([sys.executable, SCRIPT] + list(args), cwd=ROOT, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", check=False)

    def direct_cli(self, *args, **kwargs):
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(stats, "read_live_usage", return_value=kwargs.get("live", {})), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = stats.main(list(args))
        self.assertEqual(code, 0, stderr.getvalue())
        return stdout.getvalue()

    def main_picks(self, *args, seed=1):
        argv = ["main-picks", "--no-usage"] + (["--seed", str(seed)] if seed is not None else []) + list(args)
        result = self.run_cli(*argv)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout), result.stdout

    def add_run(self, name, lane="sonnet", model="claude-sonnet-5-5", effort="high", class_name="substantive",
                started="2026-10-30T00:00:00Z", ended="2026-10-30T00:02:00Z", verdict="OK", tag=None,
                session_id=None, extra=None, ledger=True, duration_s=120):
        run_dir = os.path.join(self.state, "runs", name)
        os.makedirs(run_dir)
        row = {"run_dir": run_dir, "lane": lane, "provider": None, "model": model, "effort": effort,
               "class": class_name, "tag": tag, "ro": False, "resume": None, "started_at": started,
               "ended_at": ended, "duration_s": duration_s, "verdict": verdict, "exit_code": 0,
               "session_id": session_id, "usage": None}
        row.update(extra or {})
        with open(os.path.join(run_dir, "meta.json"), "w", encoding="utf-8") as stream:
            json.dump(row, stream)
        if ledger:
            with open(os.path.join(self.state, "ledger.jsonl"), "a", encoding="utf-8") as stream:
                stream.write(json.dumps(row) + "\n")
        return run_dir

    def add_review(self, run_dir, outcome="accepted", reviewed_at="2026-10-30T12:00:00Z", fix_minutes=None,
                   note=""):
        review = {"outcome": outcome, "note": note, "fix_minutes": fix_minutes, "reviewed_at": reviewed_at}
        with open(os.path.join(run_dir, "review.json"), "w", encoding="utf-8") as stream:
            json.dump(review, stream)
        return review

    def review_runs(self, arm, count, class_name, outcome="accepted"):
        lane, model, effort = arm.split("/")
        for _ in range(count):
            self.counter += 1
            run_dir = self.add_run("r{}".format(self.counter), lane=lane, model=model, effort=effort,
                                   class_name=class_name)
            self.add_review(run_dir, outcome)

    def model_context(self, class_name):
        args = stats.build_parser().parse_args(["pick", "--class", class_name, "--no-usage"])
        with mock.patch.object(stats, "read_live_usage", return_value={}):
            return stats.model_context(args, class_name)

    def eligible(self, class_name):
        return {row["arm"]: row for row in stats.eligible_arms(self.model_context(class_name), class_name)}

    def expected_arms(self, class_name, absent=()):
        return {"/".join((arm["lane"], arm["model"], arm["effort"])) for arm in self.catalog["arms"]
                if arm["status"] == "active" and class_name in arm["classes"]
                and self.catalog["lanes"][arm["lane"]]["provider"] not in absent}

    @staticmethod
    def arms_of(data, class_name):
        block = data["classes"].get(class_name)
        return block["arms"] if block else []

    @staticmethod
    def lanes(data):
        return {row["lane"] for block in data["classes"].values() for row in block["arms"]}

    @staticmethod
    def p_total(rows):
        return sum(row["p_pick"] for row in rows)


class MainPicksTests(OrchTestCase):
    def test_output_schema_plans_modes_classes_and_arm_fields(self):
        data, _ = self.main_picks(seed=1)
        self.assertEqual(set(data), TOP_KEYS)
        self.assertEqual(data["version"], 1)
        self.assertIsNotNone(stats.parse_time(data["at"]))
        for key in ("kit", "repo"):
            self.assertTrue(data[key] is None or isinstance(data[key], str), key)
        self.assertEqual(data["plans"], {"claude": "max_20x", "codex": "prolite", "gemini": "google_ai_pro"})
        self.assertEqual(data["modes"], {"claude": "default", "codex": "default", "gemini": "default"})
        self.assertEqual(set(data["modes_until"]), set(data["modes"]))
        for provider, until in data["modes_until"].items():
            self.assertTrue(until is None or stats.parse_time(until) is not None, provider)
        self.assertEqual(set(data["classes"]), set(CLASSES))
        for class_name, block in data["classes"].items():
            self.assertEqual(set(block), {"status", "arms"}, class_name)
            self.assertIn(block["status"], ("exploring", "leaning", "locked"))
            self.assertEqual({row["arm"] for row in block["arms"]}, self.expected_arms(class_name), class_name)
            for row in block["arms"]:
                self.assertEqual(set(row), ARM_KEYS, row["arm"])
                self.assertEqual(row["lane"], row["arm"].split("/")[0])
                self.assertIsInstance(row["reviewed"], int)
                self.assertIsInstance(row["forced"], bool)
                self.assertTrue(set(row["outcomes"]) <= set(OUTCOMES), row["outcomes"])
                self.assertEqual(sum(row["outcomes"].values()), row["reviewed"])
                self.assertTrue(0 <= row["usable"] <= 1, row)
                self.assertTrue(0 <= row["p_pick"] <= 1, row)
                self.assertGreaterEqual(row["points"], 0)
                self.assertGreater(row["minutes"], 0)

    def tree(self):
        return sorted((os.path.relpath(os.path.join(folder, name), self.state),
                       os.path.getsize(os.path.join(folder, name)))
                      for folder, _, names in os.walk(self.state) for name in names)

    def test_main_picks_changes_nothing_in_the_state_dir_and_needs_no_seed(self):
        self.review_runs(self.SONNET_HIGH, 2, "hard")
        before = self.tree()
        data, _ = self.main_picks(seed=None)
        self.assertEqual(self.tree(), before)
        self.assertFalse(os.path.exists(os.path.join(self.state, "picks.jsonl")))  # a simulated draw is not a pick
        self.assertEqual(set(data), TOP_KEYS)
        for class_name, block in data["classes"].items():
            self.assertAlmostEqual(self.p_total(block["arms"]), 1.0, delta=0.006 * len(block["arms"]), msg=class_name)

    def test_usage_mode_setting_shows_in_modes(self):
        os.environ["USAGE_OPTIMIZER_MODE"] = "saving"
        data, _ = self.main_picks()
        self.assertEqual(data["modes"], {"claude": "saving", "codex": "saving", "gemini": "saving"})

    def test_p_pick_sums_to_one_per_class_and_is_deterministic_for_a_seed(self):
        self.review_runs(self.SONNET_HIGH, 5, "hard")
        self.review_runs(self.HAIKU_MEDIUM, 3, "mechanical", "rework")
        outputs = []
        for _ in range(2):
            data, _ = self.main_picks(seed=7)
            data.pop("at")
            outputs.append(data)
        self.assertEqual(outputs[0], outputs[1])
        for class_name, block in outputs[0]["classes"].items():
            # p_pick is rounded for the wire, so the sum is exact only to the rounding of each arm.
            self.assertAlmostEqual(self.p_total(block["arms"]), 1.0, delta=0.006 * len(block["arms"]), msg=class_name)

    def test_seed_changes_the_draws_and_draws_sets_the_resolution(self):
        first, _ = self.main_picks("--draws", "300", seed=1)
        second, _ = self.main_picks("--draws", "300", seed=2)
        self.assertNotEqual(first["classes"], second["classes"])
        coarse, _ = self.main_picks("--draws", "10", seed=1)
        for block in coarse["classes"].values():
            for row in block["arms"]:
                self.assertAlmostEqual(row["p_pick"] * 10, round(row["p_pick"] * 10), delta=0.06, msg=row)
        bad = self.run_cli("main-picks", "--no-usage", "--draws", "0")
        self.assertEqual(bad.returncode, 2)

    def test_p_pick_is_the_share_of_simulated_picker_calls(self):
        # Enough reviews that no arm is forced, so floor and thompson both play.
        for arm in self.catalog["arms"]:
            if arm["status"] == "active":
                lane_arm = "/".join((arm["lane"], arm["model"], arm["effort"]))
                self.review_runs(lane_arm, 4, arm["classes"][0], "accepted")
        self.review_runs(self.SONNET_HIGH, 3, "substantive", "rejected")
        data, _ = self.main_picks(seed=1)
        for class_name in ("mechanical", "substantive", "research"):
            expected = self.simulate(class_name)
            rows = data["classes"][class_name]["arms"]
            self.assertEqual({row["arm"] for row in rows}, set(expected))
            for row in rows:
                self.assertFalse(row["forced"], row)
                self.assertAlmostEqual(row["p_pick"], expected[row["arm"]], delta=0.07,
                                       msg="{} {}".format(class_name, row["arm"]))

    def simulate(self, class_name, draws=4000, seed=12345):
        context = self.model_context(class_name)
        rows = stats.eligible_arms(context, class_name)
        config = context["catalog"]["explore"]
        rng = random.Random(seed)
        wins = {row["arm"]: 0 for row in rows}
        for _ in range(draws):
            wins[stats.choose_arm(rows, config, class_name, rng)[0]["arm"]] += 1
        return {arm: count / draws for arm, count in wins.items()}

    def test_where_is_subagent_for_claude_and_local_for_codex_and_gemini(self):
        data, _ = self.main_picks()
        seen = set()
        for block in data["classes"].values():
            for row in block["arms"]:
                seen.add(row["lane"])
                expected = "subagent" if PROVIDER_OF[row["lane"]] == "claude" else "local"
                self.assertEqual(row["where"], expected, row["arm"])
        self.assertEqual(seen, set(PROVIDER_OF))

    def test_arm_with_fewer_than_min_runs_reviews_is_forced_and_dominates(self):
        # Every active arm has min_runs (2) reviews except gemini (1). Reviews count across classes.
        for arm in self.catalog["arms"]:
            if arm["status"] == "active":
                lane_arm = "/".join((arm["lane"], arm["model"], arm["effort"]))
                self.review_runs(lane_arm, 1 if arm["lane"] == "gemini" else 2, arm["classes"][-1])
        data, _ = self.main_picks(seed=1)
        for class_name in ("mechanical", "substantive", "research"):
            rows = {row["arm"]: row for row in data["classes"][class_name]["arms"]}
            gemini = rows["gemini/gemini-3.8-flash-medium/medium"]
            self.assertTrue(gemini["forced"], class_name)
            self.assertAlmostEqual(gemini["p_pick"], 1.0, places=2)
            for arm, row in rows.items():
                if row is not gemini:
                    self.assertFalse(row["forced"], arm)
                    self.assertEqual(row["p_pick"], 0, arm)
        for class_name in ("hard", "design", "review"):
            rows = data["classes"][class_name]["arms"]
            self.assertFalse(any(row["forced"] for row in rows), class_name)
            self.assertAlmostEqual(self.p_total(rows), 1.0, delta=0.006 * len(rows))

    def test_two_forced_arms_share_the_draws_and_the_rest_get_none(self):
        for arm in self.catalog["arms"]:
            if arm["status"] == "active":
                lane_arm = "/".join((arm["lane"], arm["model"], arm["effort"]))
                short = {"gemini": 0, "haiku": 1}.get(arm["lane"], 2)
                self.review_runs(lane_arm, short, arm["classes"][0])
        data, _ = self.main_picks(seed=1)
        rows = {row["arm"]: row for row in data["classes"]["mechanical"]["arms"]}
        forced = {arm for arm, row in rows.items() if row["forced"]}
        self.assertEqual(forced, {"gemini/gemini-3.8-flash-medium/medium", self.HAIKU_MEDIUM})
        for arm, row in rows.items():
            if arm in forced:
                self.assertGreater(row["p_pick"], 0, arm)
            else:
                self.assertEqual(row["p_pick"], 0, arm)
        self.assertAlmostEqual(sum(rows[arm]["p_pick"] for arm in forced), 1.0, delta=0.012)

    def test_no_reviews_at_all_makes_every_arm_forced(self):
        data, _ = self.main_picks()
        for class_name, block in data["classes"].items():
            self.assertEqual(block["status"], "exploring")
            for row in block["arms"]:
                self.assertTrue(row["forced"], row["arm"])
                self.assertEqual(row["reviewed"], 0)
                self.assertTrue(all(count == 0 for count in row["outcomes"].values()), row["outcomes"])
            self.assertAlmostEqual(self.p_total(block["arms"]), 1.0, delta=0.006 * len(block["arms"]))

    def test_works_when_the_state_dir_does_not_exist(self):
        shutil.rmtree(self.state)
        data, _ = self.main_picks()
        self.assertEqual({row["arm"] for row in data["classes"]["hard"]["arms"]}, self.expected_arms("hard"))

    def test_inactive_manual_and_wrong_class_arms_are_absent(self):
        data, text = self.main_picks()
        self.assertNotIn("claude-sonnet-5-5/max", text)  # manual
        self.assertNotIn("claude-haiku-5-5/xhigh", text)  # retired
        for class_name in CLASSES:
            arms = {row["arm"] for row in self.arms_of(data, class_name)}
            for arm in self.catalog["arms"]:
                identity = "/".join((arm["lane"], arm["model"], arm["effort"]))
                if arm["status"] != "active" or class_name not in arm["classes"]:
                    self.assertNotIn(identity, arms, "{} in {}".format(identity, class_name))
        # Reviews of an arm in a class it does not serve do not put it there.
        self.review_runs(self.LUNA_MEDIUM, 3, "design")
        data, _ = self.main_picks()
        self.assertNotIn(self.LUNA_MEDIUM, {row["arm"] for row in self.arms_of(data, "design")})

    def test_reviewed_outcomes_usable_points_and_minutes_per_class(self):
        sonnet = self.SONNET_HIGH
        self.review_runs(sonnet, 1, "substantive", "accepted")
        fixed = self.add_run("fixed-one", class_name="substantive")
        self.add_review(fixed, "fixed", fix_minutes=5)
        self.review_runs(sonnet, 1, "substantive", "rework")
        self.review_runs(sonnet, 1, "hard", "rejected")
        self.add_run("unreviewed", class_name="substantive")
        # A reviewed run of another machine (lane-stats import) counts like a local one.
        os.makedirs(os.path.join(self.state, "imported"))
        row = {"machine": "other-machine", "run_id": "other-1", "lane": "sonnet", "model": "claude-sonnet-5-5",
               "effort": "high", "class": "substantive", "started_at": "2026-10-30T00:00:00Z",
               "ended_at": "2026-10-30T00:02:00Z", "duration_s": 120, "verdict": "OK", "tokens": None,
               "list_usd": None, "review": {"outcome": "accepted", "note": "", "fix_minutes": None,
                                            "reviewed_at": "2026-10-30T12:00:00Z"}}
        with open(os.path.join(self.state, "imported", "other-machine.jsonl"), "w", encoding="utf-8") as stream:
            stream.write(json.dumps(row) + "\n")

        data, _ = self.main_picks()
        by_class = {name: {row["arm"]: row for row in self.arms_of(data, name)} for name in ("substantive", "hard", "research")}
        counts = by_class["substantive"][sonnet]
        self.assertEqual(counts["reviewed"], 4)
        self.assertEqual({key: counts["outcomes"].get(key, 0) for key in OUTCOMES},
                         {"accepted": 2, "fixed": 1, "rework": 1, "rejected": 0})
        hard = by_class["hard"][sonnet]
        self.assertEqual(hard["reviewed"], 1)
        self.assertEqual({key: hard["outcomes"].get(key, 0) for key in OUTCOMES},
                         {"accepted": 0, "fixed": 0, "rework": 0, "rejected": 1})
        self.assertEqual(by_class["research"][sonnet]["reviewed"], 0)
        # The wire numbers are the picker's own: mean_usable, cost points and the ETA estimate, rounded.
        runs = stats.load_data(self.state, stats.load_catalog())[0]
        now = stats.parse_time(data["at"])
        for class_name in ("substantive", "hard", "research"):
            expected = self.eligible(class_name)
            for arm, row in by_class[class_name].items():
                lane, model, effort = arm.split("/")
                self.assertAlmostEqual(row["usable"], expected[arm]["mean_usable"], delta=0.006, msg=arm)
                self.assertAlmostEqual(row["points"], expected[arm]["points"], delta=0.051, msg=arm)
                eta = stats.estimate_eta(runs, self.catalog, lane, model, effort, class_name, None, now)["minutes"]
                self.assertAlmostEqual(row["minutes"], eta, delta=max(0.1, 0.01 * eta), msg=arm)

    def test_class_status_follows_the_lock_rule(self):
        self.review_runs(self.SONNET_HIGH, 9, "hard", "accepted")
        self.review_runs("sol/gpt-6.1-sol/xhigh", 9, "hard", "rejected")
        data, _ = self.main_picks(seed=1)
        self.assertEqual(data["classes"]["hard"]["status"], "locked")
        self.assertEqual(data["classes"]["mechanical"]["status"], "exploring")
        rows = {row["arm"]: row for row in data["classes"]["hard"]["arms"]}
        # The exploration floor keeps the loser alive; the leader takes most draws.
        self.assertGreater(rows[self.SONNET_HIGH]["p_pick"], 0.7)
        self.assertTrue(0.01 < rows["sol/gpt-6.1-sol/xhigh"]["p_pick"] < 0.25, rows)
        self.assertFalse(rows[self.SONNET_HIGH]["forced"])

    def test_meter_guards_drop_the_arms_the_picker_would_not_choose(self):
        live = {"claude": {"windows": {"seven_day": {"used_percentage": 90}}}}
        data = json.loads(self.direct_cli("main-picks", "--seed", "1", live=live))
        self.assertEqual(self.lanes(data), {"luna", "sol", "gemini"})
        self.assertEqual({row["where"] for block in data["classes"].values() for row in block["arms"]}, {"local"})
        live = {"codex": {"windows": [{"label": "weekly", "used_percent": 96}]}}
        data = json.loads(self.direct_cli("main-picks", "--seed", "1", live=live))
        self.assertEqual(self.lanes(data), {"sonnet", "haiku", "gemini"})
        self.assertEqual(self.arms_of(data, "design"), [])
        # Without --no-usage and without a reading nothing is dropped.
        data = json.loads(self.direct_cli("main-picks", "--seed", "1", live={}))
        self.assertEqual(self.lanes(data), set(PROVIDER_OF))

    def test_out_writes_the_same_json_as_stdout(self):
        printed, _ = self.main_picks(seed=3)
        target = os.path.join(self.temp, "out", "picks.json")
        os.makedirs(os.path.dirname(target))
        result = self.run_cli("main-picks", "--no-usage", "--seed", "3", "--out", target)
        self.assertEqual(result.returncode, 0, result.stderr)
        with open(target, encoding="utf-8") as stream:
            written = json.load(stream)
        printed.pop("at")
        written.pop("at")
        self.assertEqual(written, printed)

    def test_exclude_leaves_the_lane_out_of_every_class_and_is_recorded(self):
        data, _ = self.main_picks("--exclude", "gemini", seed=1)
        self.assertEqual(data["excluded"], ["gemini"])
        self.assertEqual(self.lanes(data), {"luna", "sol", "sonnet", "haiku"})
        for class_name, block in data["classes"].items():
            self.assertNotIn("gemini", {row["lane"] for row in block["arms"]}, class_name)
            self.assertAlmostEqual(self.p_total(block["arms"]), 1.0, delta=0.006 * len(block["arms"]), msg=class_name)

    def test_exclude_takes_comma_lists_and_repeated_flags_and_matches_pick(self):
        data, _ = self.main_picks("--exclude", "gemini,haiku", seed=1)
        self.assertEqual(data["excluded"], ["gemini", "haiku"])
        self.assertEqual(self.lanes(data), {"luna", "sol", "sonnet"})
        repeated, _ = self.main_picks("--exclude", "haiku", "--exclude", " gemini ,gemini", seed=1)
        self.assertEqual(repeated["excluded"], ["gemini", "haiku"])
        self.assertEqual(repeated["classes"], data["classes"])
        for class_name in CLASSES:
            # The same arms as `pick --exclude` gets from eligible_arms.
            expected = {row["arm"] for row in stats.eligible_arms(self.model_context(class_name), class_name,
                                                                  "gemini,haiku")}
            self.assertEqual({row["arm"] for row in self.arms_of(data, class_name)}, expected, class_name)

    def test_an_unknown_lane_in_exclude_fails_for_main_picks_and_pick(self):
        target = os.path.join(self.temp, "typo-picks.json")
        for argv in (["main-picks", "--no-usage", "--seed", "1", "--exclude", "gemni", "--out", target],
                     ["pick", "--class", "review", "--no-usage", "--exclude", "gemini,gemni"]):
            with self.subTest(command=argv[0]):
                result = self.run_cli(*argv)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("unknown lane in --exclude: gemni", result.stderr)
        self.assertFalse(os.path.exists(target))

    def test_without_exclude_no_lane_is_left_out_and_excluded_is_empty(self):
        data, _ = self.main_picks(seed=1)
        self.assertEqual(data["excluded"], [])
        self.assertEqual(self.lanes(data), set(PROVIDER_OF))

    def test_nothing_identifying_leaves_the_machine(self):
        leak = "LEAK" + uuid.uuid4().hex[:10]
        os.environ["LANES_MACHINE"] = "machine-" + leak
        for index in range(3):
            run_dir = self.add_run("run-{}-{}".format(leak, index), tag="tag-" + leak, session_id="session-" + leak,
                                   extra={"pick_id": "p-" + leak, "brief_bytes": 87654321, "arm": "arm-" + leak})
            self.add_review(run_dir, "accepted" if index else "fixed", note="note-" + leak, fix_minutes=3)
        os.makedirs(os.path.join(self.state, "imported"))
        row = {"machine": "other-" + leak, "run_id": "runid-" + leak, "lane": "sonnet", "model": "claude-sonnet-5-5",
               "effort": "high", "class": "substantive", "tag": "imptag-" + leak, "started_at": "2026-10-30T00:00:00Z",
               "ended_at": "2026-10-30T00:02:00Z", "duration_s": 60, "verdict": "OK", "tokens": None, "list_usd": None,
               "review": {"outcome": "accepted", "note": "impnote-" + leak, "fix_minutes": None,
                          "reviewed_at": "2026-10-30T12:00:00Z"}}
        with open(os.path.join(self.state, "imported", "other.jsonl"), "w", encoding="utf-8") as stream:
            stream.write(json.dumps(row) + "\n")
        with open(os.path.join(self.state, "picks.jsonl"), "w", encoding="utf-8") as stream:
            stream.write(json.dumps({"pick_id": "pickrow-" + leak, "class": "hard", "arms": []}) + "\n")
        target = os.path.join(self.temp, "wire.json")
        _, text = self.main_picks()
        result = self.run_cli("main-picks", "--no-usage", "--out", target)
        self.assertEqual(result.returncode, 0, result.stderr)
        with open(target, encoding="utf-8") as stream:
            texts = {"stdout": text, "--out file": stream.read()}
        needles = [leak, "run-", "87654321", self.temp, self.state, self.catalog_path, os.path.basename(self.temp),
                   "this-machine", "tag-", "session-", "pick_id", "run_dir", "run_id", "machine", "brief_bytes", "note"]
        for where, body in texts.items():
            for needle in needles:
                self.assertNotIn(needle, body, "{} has {!r}".format(where, needle))
        # The imported and local reviews still count: only their identity stays home.
        data = json.loads(texts["stdout"])
        counts = {row["arm"]: row for row in data["classes"]["substantive"]["arms"]}[self.SONNET_HIGH]
        self.assertEqual(counts["reviewed"], 4)


class AbsentProviderTests(OrchTestCase):
    CODEX_LANES = {"luna", "sol"}

    def lanes_in_pick(self, seed):
        record = json.loads(self.direct_cli("pick", "--class", "mechanical", "--no-usage", "--seed", str(seed), "--json"))
        return {arm.split("/")[0] for arm in record["arms"]} | {row["arm"].split("/")[0] for row in record["top"]}

    def test_a_provider_is_present_by_default_and_with_an_empty_value(self):
        os.environ["USAGE_OPTIMIZER_PLAN_CODEX"] = ""
        data, _ = self.main_picks()
        self.assertEqual(data["plans"]["codex"], "prolite")
        self.assertTrue(self.CODEX_LANES <= self.lanes(data))
        # The control for the pick loop below: with codex present, codex arms do get picked.
        picked = set().union(*(self.lanes_in_pick(seed) for seed in range(1, 31)))
        self.assertTrue(self.CODEX_LANES & picked, picked)

    def test_env_none_removes_the_providers_arms_everywhere(self):
        os.environ["USAGE_OPTIMIZER_PLAN_CODEX"] = "none"
        data, text = self.main_picks()
        self.assertEqual(data["plans"]["codex"], "none")
        self.assertEqual(data["plans"]["claude"], "max_20x")
        self.assertEqual(data["plans"]["gemini"], "google_ai_pro")
        self.assertEqual(self.lanes(data), {"sonnet", "haiku", "gemini"})
        for class_name in CLASSES:
            self.assertEqual({row["arm"] for row in self.arms_of(data, class_name)},
                             self.expected_arms(class_name, absent=("codex",)), class_name)
        # The arms that stay are all there is: gemini hands off to the local session, claude runs as subagent.
        self.assertEqual({row["where"] for block in data["classes"].values() for row in block["arms"]},
                         {"local", "subagent"})
        self.assertNotIn("gpt-6", text)

        for seed in range(1, 31):
            self.assertFalse(self.CODEX_LANES & self.lanes_in_pick(seed), seed)
        record = json.loads(self.direct_cli("recommend", "--no-usage", "--seed", "1", "--draws", "50", "--json"))
        for class_name, block in record["classes"].items():
            self.assertFalse(any(row["arm"].split("/")[0] in self.CODEX_LANES for row in block["arms"]), class_name)
        self.assertEqual(record["classes"]["design"]["arms"], [])
        self.assertIsNone(record["classes"]["design"]["leader"])
        listing = json.loads(self.direct_cli("eta", "--class", "mechanical", "--json"))
        self.assertEqual({row["arm"].split("/")[0] for row in listing["arms"]}, {"sonnet", "haiku", "gemini"})

    def test_a_class_whose_only_arms_are_absent_has_nothing_to_pick(self):
        os.environ["USAGE_OPTIMIZER_PLAN_CODEX"] = "none"
        result = self.run_cli("pick", "--class", "design", "--no-usage", "--seed", "1")
        self.assertEqual(result.returncode, 2)
        self.assertIn("no eligible arms", result.stderr)
        data, _ = self.main_picks()
        self.assertEqual(self.arms_of(data, "design"), [])

    def test_casing_and_whitespace_of_the_value_do_not_matter(self):
        for value in ("none", "None", "NONE", " none ", "\tnone\n", "nOnE  "):
            with self.subTest(value=value):
                os.environ["USAGE_OPTIMIZER_PLAN_CODEX"] = value
                data, _ = self.main_picks()
                self.assertEqual(data["plans"]["codex"], "none")
                self.assertEqual(self.lanes(data), {"sonnet", "haiku", "gemini"})
                self.assertFalse(self.CODEX_LANES & self.lanes_in_pick(1))

    def test_plans_json_in_the_config_dir_marks_a_provider_absent(self):
        os.makedirs(self.config)
        for value in ("None", " NONE "):
            with open(os.path.join(self.config, "plans.json"), "w", encoding="utf-8") as stream:
                json.dump({"codex": value}, stream)
            data, _ = self.main_picks()
            self.assertEqual(data["plans"]["codex"], "none", value)
            self.assertEqual(self.lanes(data), {"sonnet", "haiku", "gemini"}, value)
        with open(os.path.join(self.config, "plans.json"), "w", encoding="utf-8") as stream:
            json.dump({"codex": "none"}, stream)
        data, _ = self.main_picks()
        self.assertEqual(data["plans"]["codex"], "none")
        self.assertEqual(self.lanes(data), {"sonnet", "haiku", "gemini"})
        for seed in range(1, 11):
            self.assertFalse(self.CODEX_LANES & self.lanes_in_pick(seed), seed)
        record = json.loads(self.direct_cli("recommend", "--class", "hard", "--no-usage", "--seed", "1",
                                            "--draws", "50", "--json"))
        self.assertEqual({row["arm"] for row in record["classes"]["hard"]["arms"]}, {self.SONNET_HIGH})
        listing = json.loads(self.direct_cli("eta", "--class", "hard", "--json"))
        self.assertEqual({row["arm"] for row in listing["arms"]}, {self.SONNET_HIGH})

    def test_with_every_local_provider_absent_no_arm_is_local(self):
        os.environ["USAGE_OPTIMIZER_PLAN_CODEX"] = "none"
        os.environ["USAGE_OPTIMIZER_PLAN_GEMINI"] = "None"
        data, _ = self.main_picks()
        self.assertEqual((data["plans"]["codex"], data["plans"]["gemini"]), ("none", "none"))
        self.assertEqual(self.lanes(data), {"sonnet", "haiku"})
        wheres = {row["where"] for block in data["classes"].values() for row in block["arms"]}
        self.assertEqual(wheres, {"subagent"})
        self.assertEqual(self.arms_of(data, "design"), [])

    def test_a_present_provider_keeps_its_arms_when_another_is_absent(self):
        os.environ["USAGE_OPTIMIZER_PLAN_GEMINI"] = "none"
        data, _ = self.main_picks()
        self.assertEqual(data["plans"]["gemini"], "none")
        self.assertEqual(self.lanes(data), {"luna", "sol", "sonnet", "haiku"})
        self.assertEqual({row["arm"] for row in self.arms_of(data, "substantive")},
                         self.expected_arms("substantive", absent=("gemini",)))

    def test_claude_can_be_absent_too(self):
        os.environ["USAGE_OPTIMIZER_PLAN_CLAUDE"] = "none"
        data, _ = self.main_picks()
        self.assertEqual(data["plans"]["claude"], "none")
        self.assertEqual(self.lanes(data), {"luna", "sol", "gemini"})
        self.assertEqual({row["where"] for block in data["classes"].values() for row in block["arms"]}, {"local"})


class ImportOrchTests(OrchTestCase):
    MAIN_ID = "20261031-080000-main"
    BRANCH = "claude/main-session-test"
    LONG_UNIT = "long-" + "x" * 43

    def setUp(self):
        super().setUp()
        os.environ.update({"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
                           "GIT_AUTHOR_NAME": "Orch Test", "GIT_AUTHOR_EMAIL": "orch-test@localhost",
                           "GIT_COMMITTER_NAME": "Orch Test", "GIT_COMMITTER_EMAIL": "orch-test@localhost"})
        self.hex = uuid.uuid4().hex[:10]
        self.noise = {"status": "STATUSBODY-" + self.hex, "ready": "READYBODY-" + self.hex,
                      "brief": "BRIEFSECRET-" + self.hex, "plain": "NONORCHMSG-" + self.hex}
        self.origin = os.path.join(self.temp, "origin.git")
        self.checkout = os.path.join(self.temp, "checkout")
        self.cloud = os.path.join(self.temp, "cloud")
        self.branch = self.BRANCH
        self.sha, self.times = {}, {}
        self.clock = datetime.datetime(2026, 10, 31, 8, 0, tzinfo=UTC)
        self.git("init", "--bare", self.origin)
        self.git("symbolic-ref", "HEAD", "refs/heads/main", cwd=self.origin)
        self.git("init", self.checkout)
        self.git("symbolic-ref", "HEAD", "refs/heads/main", cwd=self.checkout)
        with open(os.path.join(self.checkout, "base.txt"), "w", encoding="utf-8") as stream:
            stream.write("base\n")
        self.git("add", "base.txt", cwd=self.checkout)
        self.git("commit", "-m", "base", cwd=self.checkout, when="2026-10-31T07:00:00+00:00")
        self.git("remote", "add", "origin", self.origin, cwd=self.checkout)
        self.git("push", "origin", "main", cwd=self.checkout)
        self.git("clone", self.origin, self.cloud)
        self.git("checkout", "-b", self.branch, cwd=self.cloud)
        self.build_branch()
        self.git("push", "origin", self.branch, cwd=self.cloud)
        # Two local runs of unit-f, the second the later one: a via=local review lands on the later.
        tag = self.tag("unit-f")
        for name, start, end in (("unit-f-early", "07:00:00", "07:02:00"), ("unit-f-late", "07:30:00", "07:32:00")):
            self.add_run(name, lane="luna", model="gpt-6-luna", effort="medium", class_name="mechanical", tag=tag,
                         started="2026-10-31T" + start + "Z", ended="2026-10-31T" + end + "Z")

    # --- git fixtures -------------------------------------------------------------------------------------------

    def git(self, *args, cwd=None, when=None):
        env = os.environ.copy()
        if when:
            env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = when
        result = subprocess.run(["git"] + list(args), cwd=cwd, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, encoding="utf-8", timeout=60, check=False)
        if result.returncode != 0:
            self.fail("git {} failed: {}".format(" ".join(args), result.stderr))
        return result.stdout.strip()

    def commit(self, label, subject, body=None, files=None, offset=0, repo=None):
        repo = repo or self.cloud
        self.clock += datetime.timedelta(minutes=5)
        when = self.clock.astimezone(datetime.timezone(datetime.timedelta(hours=offset))).isoformat()
        for path, text in (files or {}).items():
            full = os.path.join(repo, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(text)
            self.git("add", path, cwd=repo)
        message = ["-m", subject] + (["-m", body] if body else [])
        self.git("commit", "--allow-empty", *message, cwd=repo, when=when)
        self.sha[label] = self.git("rev-parse", "HEAD", cwd=repo)
        self.times[label] = self.clock
        return self.sha[label]

    def tag(self, unit):
        return "orch-{}-{}".format(self.MAIN_ID, unit)

    @staticmethod
    def marker(unit, outcome, arm, class_name, minutes, tokens, usd, extra=""):
        return "orch: REVIEW {} {} arm={} class={} min={} tok={} usd={}{}".format(
            unit, outcome, arm, class_name, minutes, tokens, usd, extra)

    def build_branch(self):
        sonnet, haiku, luna = self.SONNET_HIGH, self.HAIKU_MEDIUM, self.LUNA_MEDIUM
        self.commit("start", "orch: START " + self.MAIN_ID)
        # A line in a body is not a marker: only the subject line is.
        self.commit("status", "orch: STATUS 1: plan ready", body="{} a plain message\n{}".format(
            self.noise["status"], self.marker("body-fake", "accepted", sonnet, "substantive", "1", "1/1", "0.01")))
        # Commit times can carry any offset; this one is two hours east.
        self.commit("unit-a", self.marker("unit-a", "accepted", sonnet, "substantive", "12.5", "120000/8000", "1.25"),
                    offset=2)
        self.commit("unit-b", self.marker("unit-b", "fixed", haiku, "mechanical", "3", "40000/2000", "0.10", " fix=4"))
        self.commit("unit-c", self.marker("unit-c", "rework", sonnet, "hard", "20", "200000/15000", "2.50"))
        self.commit("unit-d", self.marker("unit-d", "rejected", haiku, "mechanical", "0.5", "30000/1000", "0.05"))
        self.commit("unit-e", self.marker("unit-e", "accepted", sonnet, "research", "-", "-", "-"))
        self.commit("long", self.marker(self.LONG_UNIT, "accepted", haiku, "mechanical", "1", "1/2", "0.01", " fix=-"))
        self.commit("local-handoff", "orch: LOCAL lane unit-f {} .lane-main/briefs/unit-f.md".format(luna),
                    files={".lane-main/briefs/unit-f.md": self.noise["brief"] + "\nDo the thing.\n"})
        self.commit("unit-f", self.marker("unit-f", "accepted", luna, "mechanical", "7", "-", "-", " via=local"))
        self.commit("ready", "orch: READY 2: first batch done", body=self.noise["ready"] + " merge branch")
        bad = (
            ("bad-outcome", "bad-outcome", "maybe", sonnet, "substantive", "1", "1/1", "0.01", ""),
            ("bad-class", "bad-class", "accepted", sonnet, "bogus", "1", "1/1", "0.01", ""),
            ("neg-min", "neg-min", "accepted", sonnet, "substantive", "-5", "1/1", "0.01", ""),
            ("bad-arm-a", "bad-arm-a", "accepted", "sonnet/claude-sonnet-5-5", "substantive", "1", "1/1", "0.01", ""),
            ("bad-arm-b", "bad-arm-b", "accepted", "sonnet", "substantive", "1", "1/1", "0.01", ""),
            ("bad-unit-a", "bad/unit", "accepted", sonnet, "substantive", "1", "1/1", "0.01", ""),
            ("bad-unit-b", self.LONG_UNIT + "x", "accepted", sonnet, "substantive", "1", "1/1", "0.01", ""),
            ("bad-tok", "bad-tok", "accepted", sonnet, "substantive", "1", "abc/2", "0.01", ""),
            ("bad-usd", "bad-usd", "accepted", sonnet, "substantive", "1", "1/1", "abc", ""),
            ("bad-fix", "bad-fix", "fixed", sonnet, "substantive", "1", "1/1", "0.01", " fix=abc"),
        )
        for label, unit, outcome, arm, class_name, minutes, tokens, usd, extra in bad:
            self.commit(label, self.marker(unit, outcome, arm, class_name, minutes, tokens, usd, extra))
        self.commit("unit-h", self.marker("unit-h", "accepted", luna, "mechanical", "5", "-", "-", " via=local"))
        self.commit("plain", "tidy readme " + self.noise["plain"], files={"README.md": self.noise["plain"] + "\n"})
        self.commit("quoted", 'Revert "{}"'.format(self.marker("unit-r", "accepted", sonnet, "substantive", "1", "1/1", "0.01")))

    GOOD_UNITS = ("unit-a", "unit-b", "unit-c", "unit-d", "unit-e", LONG_UNIT)
    MALFORMED = 10

    # --- helpers ------------------------------------------------------------------------------------------------

    def import_orch(self, *extra, repo=None, branch=None):
        return self.run_cli("import-orch", repo or self.checkout, branch or self.branch, *extra)

    def imported(self):
        result = self.import_orch()
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def orch_runs(self):
        """{run dir name: meta} for every imported run."""
        found = {}
        root = os.path.join(self.state, "runs")
        for name in sorted(os.listdir(root)):
            if name.startswith("orch-"):
                with open(os.path.join(root, name, "meta.json"), encoding="utf-8") as stream:
                    found[name] = json.load(stream)
        return found

    def run_of(self, unit):
        runs = {meta.get("unit"): (name, meta) for name, meta in self.orch_runs().items()}
        self.assertIn(unit, runs, sorted(runs))
        return runs[unit]

    def reviews_by_name(self):
        runs, _, _ = stats.load_runs(self.state)
        reviews, bad = stats.latest_reviews(self.state, runs)
        self.assertEqual(bad, 0)
        return {os.path.basename(runs[key]["run_dir"]): review for key, review in reviews.items()}

    def line_count(self, name):
        path = os.path.join(self.state, name)
        if not os.path.exists(path):
            return 0
        with open(path, encoding="utf-8") as stream:
            return len(stream.readlines())

    def state_summary(self):
        names = sorted(os.listdir(os.path.join(self.state, "runs")))
        metas = {}
        for name in names:
            if name.startswith("orch-"):
                with open(os.path.join(self.state, "runs", name, "meta.json"), "rb") as stream:
                    metas[name] = stream.read()
        reviews = {name: (review["outcome"], stats.number(review.get("fix_minutes")), review.get("reviewed_at"))
                   for name, review in self.reviews_by_name().items()}
        return names, metas, reviews, self.line_count("ledger.jsonl"), self.line_count("reviews.jsonl")

    # --- tests --------------------------------------------------------------------------------------------------

    def test_subagent_reviews_become_runs_with_the_marker_fields(self):
        self.imported()
        runs = self.orch_runs()
        self.assertEqual(len(runs), 6)
        self.assertEqual(set(runs), {"orch-" + self.sha[label][:12] for label in
                                     ("unit-a", "unit-b", "unit-c", "unit-d", "unit-e", "long")})
        table = (
            ("unit-a", "sonnet", "claude-sonnet-5-5", "high", "substantive", 12.5, 120000, 8000, 1.25),
            ("unit-b", "haiku", "claude-haiku-5-5", "medium", "mechanical", 3, 40000, 2000, 0.10),
            ("unit-c", "sonnet", "claude-sonnet-5-5", "high", "hard", 20, 200000, 15000, 2.50),
            ("unit-d", "haiku", "claude-haiku-5-5", "medium", "mechanical", 0.5, 30000, 1000, 0.05),
        )
        for unit, lane, model, effort, class_name, minutes, tokens_in, tokens_out, usd in table:
            with self.subTest(unit=unit):
                name, meta = self.run_of(unit)
                self.assertEqual(name, "orch-" + self.sha[unit][:12])
                for key, value in (("lane", lane), ("model", model), ("effort", effort), ("class", class_name),
                                   ("provider", "claude"), ("place", "cloud-main"), ("tag", self.tag(unit)),
                                   ("arm", "{}/{}/{}".format(lane, model, effort)), ("verdict", "OK"),
                                   ("exit_code", 0), ("main_id", self.MAIN_ID), ("unit", unit)):
                    self.assertEqual(meta.get(key), value, key)
                self.assertAlmostEqual(meta["duration_s"], minutes * 60)
                commit_time = self.times[unit]
                self.assertEqual(stats.parse_time(meta["ended_at"]), commit_time)
                self.assertEqual(stats.parse_time(meta["started_at"]), commit_time - datetime.timedelta(minutes=minutes))
                self.assertEqual(meta["usage"]["tokens"]["input"], tokens_in)
                self.assertEqual(meta["usage"]["tokens"]["output"], tokens_out)
                self.assertAlmostEqual(meta["usage"]["list_usd"], usd)

    def test_dash_values_are_unknown_not_guessed(self):
        self.imported()
        name, meta = self.run_of("unit-e")
        self.assertEqual((meta["lane"], meta["class"], meta["place"]), ("sonnet", "research", "cloud-main"))
        self.assertIn(meta.get("duration_s"), (None, 0, 0.0))
        usage = meta.get("usage") or {}
        tokens = usage.get("tokens") or {}
        self.assertIsNone(tokens.get("input"))
        self.assertIsNone(tokens.get("output"))
        self.assertIsNone(usage.get("list_usd"))
        self.assertEqual(stats.parse_time(meta["ended_at"]), self.times["unit-e"])
        self.assertEqual(self.reviews_by_name()[name]["outcome"], "accepted")
        # The longest legal unit (48 characters) and an unknown fix time import too.
        long_name, long_meta = self.run_of(self.LONG_UNIT)
        self.assertEqual(len(self.LONG_UNIT), 48)
        self.assertEqual(long_meta["tag"], self.tag(self.LONG_UNIT))
        self.assertIsNone(self.reviews_by_name()[long_name].get("fix_minutes"))

    def test_reviews_are_stored_where_load_data_and_latest_reviews_read_them(self):
        self.imported()
        by_name = self.reviews_by_name()
        expected = (("unit-a", "accepted", None), ("unit-b", "fixed", 4), ("unit-c", "rework", None),
                    ("unit-d", "rejected", None), ("unit-e", "accepted", None))
        for unit, outcome, fix in expected:
            with self.subTest(unit=unit):
                review = by_name["orch-" + self.sha[unit][:12]]
                self.assertEqual(review["outcome"], outcome)
                self.assertEqual(stats.number(review.get("fix_minutes")), fix)
                self.assertEqual(stats.parse_time(review["reviewed_at"]), self.times[unit])
        # The same two places `lane-stats review` writes: review.json beside the run, and a reviews.jsonl line.
        with open(os.path.join(self.state, "runs", "orch-" + self.sha["unit-b"][:12], "review.json"), encoding="utf-8") as stream:
            stored = json.load(stream)
        self.assertEqual((stored["outcome"], stored["fix_minutes"]), ("fixed", 4))
        self.assertEqual(stats.parse_time(stored["reviewed_at"]), self.times["unit-b"])
        with open(os.path.join(self.state, "reviews.jsonl"), encoding="utf-8") as stream:
            lines = [json.loads(line) for line in stream if line.strip()]
        self.assertIn("orch-" + self.sha["unit-b"][:12], {os.path.basename(row["run_dir"]) for row in lines})
        runs, reviews, _, _, malformed = stats.load_data(self.state, stats.load_catalog())
        self.assertEqual(malformed, 0)
        orch = {key for key, run in runs.items() if run.get("place") == "cloud-main"}
        self.assertEqual(len(orch), 6)
        self.assertTrue(orch <= set(reviews))
        # Six imported runs plus the one via=local review on a local run.
        self.assertEqual(len(reviews), 7)

    def test_importing_twice_adds_nothing(self):
        self.imported()
        before = self.state_summary()
        second = self.imported()
        self.assertEqual(self.state_summary(), before)
        match = re.search(r"imported (\d+) runs?", second.stdout)
        self.assertIsNotNone(match, second.stdout)
        self.assertEqual(match.group(1), "0")

    def test_a_later_marker_is_imported_alone_on_the_next_run(self):
        self.imported()
        before = set(self.orch_runs())
        self.commit("unit-g", self.marker("unit-g", "accepted", self.HAIKU_MEDIUM, "mechanical", "2", "10/20", "0.02"))
        self.git("push", "origin", self.branch, cwd=self.cloud)
        second = self.imported()
        added = set(self.orch_runs()) - before
        self.assertEqual(added, {"orch-" + self.sha["unit-g"][:12]})
        self.assertEqual(len(self.orch_runs()), 7)
        self.assertEqual(re.search(r"imported (\d+) runs?", second.stdout).group(1), "1")

    def test_via_local_attaches_to_the_latest_local_run_and_creates_no_run(self):
        self.imported()
        self.assertFalse(os.path.exists(os.path.join(self.state, "runs", "orch-" + self.sha["unit-f"][:12])))
        self.assertEqual(sorted(meta["unit"] for meta in self.orch_runs().values()), sorted(self.GOOD_UNITS))
        by_name = self.reviews_by_name()
        self.assertEqual(by_name["unit-f-late"]["outcome"], "accepted")
        self.assertEqual(stats.parse_time(by_name["unit-f-late"]["reviewed_at"]), self.times["unit-f"])
        self.assertNotIn("unit-f-early", by_name)
        # The local run stays a local run.
        with open(os.path.join(self.state, "runs", "unit-f-late", "meta.json"), encoding="utf-8") as stream:
            meta = json.load(stream)
        self.assertEqual(meta["tag"], self.tag("unit-f"))
        self.assertNotEqual(meta.get("place"), "cloud-main")
        runs, _, _ = stats.load_runs(self.state)
        self.assertEqual(sum(1 for run in runs.values() if run.get("tag") == self.tag("unit-f")), 2)

    def test_via_local_without_a_local_run_is_skipped_with_a_warning(self):
        result = self.imported()
        # A line says which marker was skipped (the spec asks for "a warning line", not for a word in it).
        shown = (result.stdout + result.stderr).splitlines()
        marker = (self.sha["unit-h"][:12], "unit-h", self.tag("unit-h"))
        self.assertTrue(any(name in line for line in shown for name in marker), shown)
        self.assertNotIn("unit-h", {meta.get("unit") for meta in self.orch_runs().values()})
        self.assertFalse(os.path.exists(os.path.join(self.state, "runs", "orch-" + self.sha["unit-h"][:12])))
        runs, _, _ = stats.load_runs(self.state)
        self.assertFalse(any(run.get("tag") == self.tag("unit-h") for run in runs.values()))

    def test_malformed_markers_are_skipped_and_never_guessed(self):
        self.imported()
        tags = {meta["tag"] for meta in self.orch_runs().values()}
        self.assertEqual(tags, {self.tag(unit) for unit in self.GOOD_UNITS})
        for label in ("bad-outcome", "bad-class", "neg-min", "bad-arm-a", "bad-arm-b", "bad-unit-a", "bad-unit-b",
                      "bad-tok", "bad-usd", "bad-fix"):
            self.assertFalse(os.path.exists(os.path.join(self.state, "runs", "orch-" + self.sha[label][:12])), label)
        # No review was written for them on a local run either (a bad marker is not a via=local one).
        self.assertEqual(sorted(self.reviews_by_name()), sorted(
            ["orch-" + self.sha[label][:12] for label in ("unit-a", "unit-b", "unit-c", "unit-d", "unit-e", "long")]
            + ["unit-f-late"]))

    def test_summary_line_counts_runs_reviews_and_skipped_markers(self):
        result = self.imported()
        match = re.search(r"imported (\d+) runs?, (\d+) reviews? attached, (\d+) skipped", result.stdout)
        self.assertIsNotNone(match, result.stdout)
        self.assertEqual(match.group(1), "6")
        self.assertEqual(match.group(2), "7")
        # Ten malformed markers and the via=local marker that has no local run; STATUS, READY, LOCAL and the
        # non-orch commit are not markers to import, so they are not skipped.
        self.assertEqual(match.group(3), str(self.MALFORMED + 1))

    def test_nothing_else_from_the_branch_is_stored(self):
        self.imported()
        needles = list(self.noise.values()) + [self.origin, self.cloud, "tidy readme"]
        found = []
        for folder, _, names in os.walk(self.state):
            for name in names:
                with open(os.path.join(folder, name), "rb") as stream:
                    body = stream.read().decode("utf-8", "replace")
                found.extend((os.path.relpath(os.path.join(folder, name), self.state), needle)
                             for needle in needles if needle in body)
        self.assertEqual(found, [])

    def test_a_branch_without_a_start_marker_exits_2(self):
        before = self.state_summary()
        for branch, start in (("claude/no-start", None), ("claude/bad-start", "orch: START my-session")):
            with self.subTest(branch=branch):
                self.git("checkout", "-b", branch, "main", cwd=self.cloud)
                if start:
                    self.commit("bad-start", start)
                self.commit("lonely", self.marker("unit-z", "accepted", self.SONNET_HIGH, "substantive", "1", "1/1", "0.01"))
                self.commit("status-only", "orch: STATUS 1: nothing started")
                self.git("push", "origin", branch, cwd=self.cloud)
                result = self.import_orch(branch=branch)
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertTrue(result.stderr.strip())
                self.assertEqual(self.state_summary(), before)
                self.assertEqual(self.orch_runs(), {})

    def test_an_unknown_branch_or_repo_fails_and_imports_nothing(self):
        for repo, branch in ((self.checkout, "claude/does-not-exist"), (os.path.join(self.temp, "nowhere"), self.branch)):
            with self.subTest(branch=branch):
                result = self.import_orch(repo=repo, branch=branch)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.orch_runs(), {})

    def test_default_fetches_the_branch_from_the_bare_origin(self):
        ref = "refs/remotes/origin/" + self.branch
        probe = subprocess.run(["git", "rev-parse", "--verify", "--quiet", ref], cwd=self.checkout,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        self.assertNotEqual(probe.returncode, 0)
        self.imported()
        self.assertEqual(len(self.orch_runs()), 6)

    def test_no_fetch_reads_the_remote_tracking_ref_and_never_touches_the_origin(self):
        # Nothing fetched yet: there is nothing to read.
        refused = self.import_orch("--no-fetch")
        self.assertNotEqual(refused.returncode, 0)
        self.assertEqual(self.orch_runs(), {})
        self.git("fetch", "origin", cwd=self.checkout)
        self.git("rev-parse", "--verify", "refs/remotes/origin/" + self.branch, cwd=self.checkout)
        # A marker pushed after that fetch is not in the local copy.
        self.commit("unit-g", self.marker("unit-g", "accepted", self.HAIKU_MEDIUM, "mechanical", "2", "10/20", "0.02"))
        self.git("push", "origin", self.branch, cwd=self.cloud)
        away = self.origin + ".away"
        os.rename(self.origin, away)
        try:
            offline = self.import_orch("--no-fetch")
        finally:
            os.rename(away, self.origin)
        self.assertEqual(offline.returncode, 0, offline.stderr)
        self.assertEqual(sorted(meta["unit"] for meta in self.orch_runs().values()), sorted(self.GOOD_UNITS))
        # The default run fetches and sees it.
        self.imported()
        self.assertEqual(sorted(meta["unit"] for meta in self.orch_runs().values()),
                         sorted(self.GOOD_UNITS + ("unit-g",)))
        self.assertEqual(len(self.orch_runs()), 7)

    def test_zero_is_a_value_and_fix_may_be_decimal(self):
        self.commit("zero", self.marker("unit-zero", "fixed", self.HAIKU_MEDIUM, "mechanical", "0", "0/0", "0", " fix=2.5"))
        self.git("push", "origin", self.branch, cwd=self.cloud)
        self.imported()
        name, meta = self.run_of("unit-zero")
        self.assertIsNotNone(meta["duration_s"])
        self.assertEqual(meta["duration_s"], 0)
        self.assertEqual(meta["usage"]["tokens"]["input"], 0)
        self.assertEqual(meta["usage"]["tokens"]["output"], 0)
        self.assertEqual(meta["usage"]["list_usd"], 0)
        self.assertEqual(stats.parse_time(meta["started_at"]), stats.parse_time(meta["ended_at"]))
        self.assertEqual(stats.number(self.reviews_by_name()[name]["fix_minutes"]), 2.5)

    def test_two_reviews_of_one_unit_are_two_records(self):
        # The record's key is the commit, not the unit: a later REVIEW of the same unit is its own run and review.
        self.imported()
        self.commit("unit-a-again", self.marker("unit-a", "rework", self.SONNET_HIGH, "substantive", "4", "10/10", "0.1"))
        self.git("push", "origin", self.branch, cwd=self.cloud)
        self.imported()
        again = [name for name, meta in self.orch_runs().items() if meta["unit"] == "unit-a"]
        self.assertEqual(sorted(again), sorted("orch-" + self.sha[label][:12] for label in ("unit-a", "unit-a-again")))
        self.assertEqual(sorted(self.reviews_by_name()[name]["outcome"] for name in again), ["accepted", "rework"])

    def test_an_arm_of_a_lane_nobody_knows_gets_no_guessed_provider(self):
        self.commit("ghost", self.marker("unit-ghost", "accepted", "ghost/ghost-model/high", "mechanical", "1", "1/1", "0.01"))
        self.git("push", "origin", self.branch, cwd=self.cloud)
        result = self.imported()
        match = re.search(r"imported (\d+) runs?, (\d+) reviews? attached, (\d+) skipped", result.stdout)
        ghost = [meta for meta in self.orch_runs().values() if meta["unit"] == "unit-ghost"]
        if ghost:
            self.assertIsNone(ghost[0].get("provider"))
            self.assertEqual((match.group(1), match.group(3)), ("7", str(self.MALFORMED + 1)))
        else:
            self.assertEqual((match.group(1), match.group(3)), ("6", str(self.MALFORMED + 2)))

    def skipped_as(self, result, label):
        """The reason stderr gives for skipping the marker committed as `label`, or None."""
        match = re.search(r"skipped {}: (.+)".format(self.sha[label][:12]), result.stderr)
        return match.group(1).strip() if match else None

    def test_a_lane_effort_arm_takes_the_catalog_model_for_that_lane_and_effort(self):
        self.commit("short", self.marker("unit-short", "rework", "sonnet/high", "substantive", "13.9",
                                         "3201958/53894", "2.42", " fix=8"))
        self.git("push", "origin", self.branch, cwd=self.cloud)
        result = self.imported()
        self.assertIsNone(self.skipped_as(result, "short"), result.stderr)
        name, meta = self.run_of("unit-short")
        self.assertEqual(name, "orch-" + self.sha["short"][:12])
        for key, value in (("lane", "sonnet"), ("model", "claude-sonnet-5-5"), ("effort", "high"),
                           ("arm", self.SONNET_HIGH), ("provider", "claude"), ("class", "substantive"),
                           ("place", "cloud-main"), ("tag", self.tag("unit-short"))):
            self.assertEqual(meta.get(key), value, key)
        self.assertAlmostEqual(meta["duration_s"], 13.9 * 60)
        self.assertEqual(meta["usage"]["tokens"], {"input": 3201958, "output": 53894})
        review = self.reviews_by_name()[name]
        self.assertEqual(review["outcome"], "rework")
        self.assertEqual(stats.number(review.get("fix_minutes")), 8)

    def test_a_lane_effort_arm_with_no_catalog_arm_is_skipped_as_unknown_arm(self):
        self.imported()
        before = self.state_summary()
        self.commit("nomatch", self.marker("unit-nomatch", "accepted", "sonnet/low", "substantive", "1", "1/1", "0.01"))
        self.git("push", "origin", self.branch, cwd=self.cloud)
        result = self.imported()
        self.assertEqual(self.skipped_as(result, "nomatch"), "unknown arm")
        self.assertFalse(os.path.exists(os.path.join(self.state, "runs", "orch-" + self.sha["nomatch"][:12])))
        self.assertEqual(self.state_summary(), before)

    def test_a_lane_effort_arm_matching_two_models_is_skipped_as_unknown_arm(self):
        self.catalog["arms"].append({"lane": "sonnet", "model": "claude-sonnet-6", "effort": "high", "status": "active",
                                     "classes": ["substantive"], "weight": 1.0, "prior_pct": 3.0, "prior_usable": 0.8})
        self.save_catalog()
        self.imported()
        before = self.state_summary()
        self.commit("twin", self.marker("unit-twin", "accepted", "sonnet/high", "substantive", "1", "1/1", "0.01"))
        self.git("push", "origin", self.branch, cwd=self.cloud)
        result = self.imported()
        self.assertEqual(self.skipped_as(result, "twin"), "unknown arm")
        self.assertFalse(os.path.exists(os.path.join(self.state, "runs", "orch-" + self.sha["twin"][:12])))
        self.assertEqual(self.state_summary(), before)

    def test_a_dash_arm_is_accepted_only_with_via_local(self):
        tag = self.tag("unit-g")
        self.add_run("unit-g-run", lane="luna", model="gpt-6-luna", effort="medium", class_name="mechanical", tag=tag,
                     started="2026-10-31T07:10:00Z", ended="2026-10-31T07:12:00Z")
        self.commit("dash-local", self.marker("unit-g", "fixed", "-", "mechanical", "2", "-", "-", " fix=3 via=local"))
        self.commit("dash-bare", self.marker("unit-dash", "accepted", "-", "mechanical", "1", "1/1", "0.01"))
        self.git("push", "origin", self.branch, cwd=self.cloud)
        result = self.imported()
        self.assertIsNone(self.skipped_as(result, "dash-local"), result.stderr)
        review = self.reviews_by_name()["unit-g-run"]
        self.assertEqual(review["outcome"], "fixed")
        self.assertEqual(stats.number(review.get("fix_minutes")), 3)
        self.assertEqual(self.skipped_as(result, "dash-bare"), "malformed")
        self.assertNotIn("unit-dash", {meta.get("unit") for meta in self.orch_runs().values()})
        self.assertIsNone(stats.parse_orch_review(self.marker("u", "accepted", "-", "mechanical", "1", "-", "-")))
        self.assertIsNone(stats.parse_orch_review(self.marker("u", "accepted", "sonnet/x/y/z", "mechanical", "1", "-", "-")))
        short = stats.parse_orch_review(self.marker("u", "accepted", "sonnet/high", "mechanical", "1", "-", "-"))
        self.assertEqual((short["lane"], short["model"], short["effort"]), ("sonnet", None, "high"))

    def test_a_via_local_review_replaces_an_older_review_of_the_local_run(self):
        self.add_review(os.path.join(self.state, "runs", "unit-f-late"), "rejected", reviewed_at="2026-10-31T07:40:00Z")
        self.assertEqual(self.reviews_by_name()["unit-f-late"]["outcome"], "rejected")
        self.imported()
        self.assertEqual(self.reviews_by_name()["unit-f-late"]["outcome"], "accepted")
        before = self.state_summary()
        self.imported()
        self.assertEqual(self.state_summary(), before)

    def test_report_by_place_lists_cloud_main(self):
        self.imported()
        result = self.run_cli("report", "--by", "place", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = {row["place"]: row for row in json.loads(result.stdout)}
        self.assertEqual({place: row["runs"] for place, row in rows.items()}, {"local": 2, "cloud-main": 6})
        self.assertEqual(rows["cloud-main"]["reviewed"], 6)
        text = self.run_cli("report", "--by", "place")
        self.assertEqual(text.returncode, 0, text.stderr)
        lines = {line.split()[0]: line.split() for line in text.stdout.splitlines()
                 if line.split() and line.split()[0] in ("local", "cloud-main")}
        self.assertEqual(lines["cloud-main"][1], "6")

    def test_imported_reviews_change_the_picker_posterior_and_main_picks_counts(self):
        config = self.catalog["explore"]
        before = {class_name: self.eligible(class_name) for class_name in ("substantive", "hard", "mechanical")}
        for rows in before.values():
            for row in rows.values():
                self.assertEqual((row["reviewed"], row["reviewed_all"]), (0, 0))
        self.imported()
        after = {class_name: self.eligible(class_name) for class_name in ("substantive", "hard", "mechanical")}
        sonnet, haiku, luna = self.SONNET_HIGH, self.HAIKU_MEDIUM, self.LUNA_MEDIUM
        # unit-a (substantive), unit-c (hard) and unit-e (research) all reviewed sonnet high.
        self.assertEqual((after["substantive"][sonnet]["reviewed"], after["substantive"][sonnet]["reviewed_all"]), (1, 3))
        self.assertEqual(after["hard"][sonnet]["reviewed"], 1)
        # unit-b fixed, unit-d rejected and the 48-character unit accepted, all haiku medium mechanical.
        self.assertEqual((after["mechanical"][haiku]["reviewed"], after["mechanical"][haiku]["reviewed_all"]), (3, 3))
        # The via=local review counts for the local run's arm.
        self.assertEqual(after["mechanical"][luna]["reviewed"], 1)
        now = datetime.datetime.now(UTC)
        alpha_before, beta_before, _ = stats.posterior(before["hard"][sonnet], "hard", config, now)
        alpha_after, beta_after, count = stats.posterior(after["hard"][sonnet], "hard", config, now)
        self.assertEqual(count, 1)
        self.assertGreater(beta_after, beta_before)  # the rework is a failure in the class
        alpha_before, beta_before, _ = stats.posterior(before["substantive"][sonnet], "substantive", config, now)
        alpha_after, beta_after, _ = stats.posterior(after["substantive"][sonnet], "substantive", config, now)
        self.assertGreater(alpha_after, alpha_before)  # the accepted unit is a success in the class
        # The same counts reach the table the main reads.
        data, _ = self.main_picks()
        row = {row["arm"]: row for row in data["classes"]["substantive"]["arms"]}[sonnet]
        self.assertEqual(row["reviewed"], 1)
        self.assertEqual(row["outcomes"].get("accepted"), 1)
        row = {row["arm"]: row for row in data["classes"]["mechanical"]["arms"]}[haiku]
        self.assertEqual({key: row["outcomes"].get(key, 0) for key in OUTCOMES},
                         {"accepted": 1, "fixed": 1, "rework": 0, "rejected": 1})
        self.assertFalse(row["forced"])


class CommandLineTests(OrchTestCase):
    def test_help_exits_zero_for_both_commands(self):
        for command, option in (("main-picks", "--seed"), ("import-orch", "--no-fetch")):
            with self.subTest(command=command):
                result = self.run_cli(command, "--help")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("usage:", result.stdout)
                self.assertIn(option, result.stdout)
        main_help = self.run_cli("main-picks", "--help").stdout
        for option in ("--out", "--draws", "--no-usage", "--exclude"):
            self.assertIn(option, main_help)

    def test_import_orch_needs_a_repo_and_a_branch(self):
        for args in ((), ("only-one",)):
            with self.subTest(args=args):
                self.assertEqual(self.run_cli("import-orch", *args).returncode, 2)

    def test_commands_are_registered_in_the_parser(self):
        parser = stats.build_parser()
        self.assertEqual(parser.parse_args(["main-picks", "--seed", "1"]).command, "main-picks")
        args = parser.parse_args(["import-orch", "repo", "branch", "--no-fetch"])
        self.assertEqual(args.command, "import-orch")
        self.assertTrue(args.no_fetch)


if __name__ == "__main__":
    unittest.main()
