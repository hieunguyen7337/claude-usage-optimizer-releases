"""Tests for the fable advisor lane in bin/lane-stats: pricing, the role field, the advisor subcommand and the
picker never offering a fable arm.

Everything runs on fixtures: a temp state dir and a temp arms catalog. Nothing reads the real ~/.local/state/lanes
or ~/.config/lanes.
"""

import contextlib
import datetime
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import unittest
import uuid
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "bin", "lane-stats")
loader = importlib.machinery.SourceFileLoader("lane_stats_advisor_tested", SCRIPT)
stats = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
loader.exec_module(stats)

ROLES = {"plan": "xhigh", "ladder": "xhigh", "final-review": "high", "tiebreak": "medium"}


def stamp(days_ago, hours=0):
    moment = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_ago, hours=hours)
    return moment.isoformat(timespec="seconds").replace("+00:00", "Z")


class AdvisorTests(unittest.TestCase):
    def setUp(self):
        self.old_env = os.environ.copy()
        self.temp = os.path.join(os.path.dirname(__file__), ".lane-stats-advisor-{}-{}".format(
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
        os.environ["LANES_CONFIG"] = os.path.join(self.temp, "config")
        os.environ.pop("USAGE_OPTIMIZER_MODE", None)
        arm = lambda lane, effort, status, cost, usable: {
            "lane": lane, "model": lane, "effort": effort, "status": status, "classes": ["hard", "mechanical"],
            "weight": 1.0 if status == "active" else 0, "prior_pct": cost, "prior_usable": usable}
        self.catalog = {
            "lanes": {lane: {"model": lane, "provider": "claude"} for lane in ("opus", "sonnet", "fable")},
            "providers": {"claude": {"scarcity": 1.0, "window": {
                "model_weight_week": {"sonnet": 1.0, "opus": 0.67, "fable": 1.69}}}},
            "explore": {"min_runs": 2, "floor": 0.2, "half_life_days": 60, "shrink": 2.0,
                        "review_points": 0.01, "fix_points_per_minute": 0.003,
                        "targets": {"mechanical": 0.8, "hard": 0.5},
                        "pace": {"low_pct": 60, "high_pct": 90, "low_factor": 0.25, "high_factor": 3.0},
                        "exclude_weekly_pct": 95, "exclude_5h_pct": 90, "claude_guard_pct": 85,
                        "lock": {"leaning_p": 0.5, "leaning_runs": 4, "locked_p": 0.8, "locked_runs": 8},
                        "measured_weight": 4, "measured_shrink": 4.0, "measured_min_n": 10,
                        "advisor": {"lane": "fable", "model": "fable", "active": False,
                                    "inactive_reason": "weaker than Opus", "roles": dict(ROLES),
                                    "weekly_list_usd": 60, "budget_basis": "test"}},
            "arms": [arm("opus", "high", "active", 0.3, 0.8), arm("sonnet", "high", "active", 0.1, 0.7),
                     arm("fable", "high", "manual", 1.0, 0.9), arm("fable", "xhigh", "manual", 1.5, 0.9)]}
        self.save_catalog()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old_env)
        shutil.rmtree(self.temp)

    def save_catalog(self):
        with open(self.catalog_path, "w", encoding="utf-8") as stream:
            json.dump(self.catalog, stream)

    def cli(self, *args, code=0):
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(stats, "read_live_usage", return_value={}), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = stats.main(list(args))
        self.assertEqual(result, code, stderr.getvalue())
        return stdout.getvalue()

    def context(self, class_name="hard"):
        args = stats.build_parser().parse_args(["pick", "--class", class_name, "--no-usage"])
        with mock.patch.object(stats, "read_live_usage", return_value={}):
            return stats.model_context(args, class_name)

    def add_run(self, name, lane="opus", effort="high", class_name="hard", started=None, role=None, list_usd=None,
                duration_s=600, usage=None, outcome=None):
        started = started or stamp(1)
        run_dir = os.path.join(self.state, "runs", name)
        os.makedirs(run_dir)
        row = {"run_dir": run_dir, "lane": lane, "provider": None, "model": lane, "effort": effort,
               "class": class_name, "tag": None, "started_at": started, "ended_at": started,
               "duration_s": duration_s, "verdict": "OK", "exit_code": 0,
               "usage": usage if usage is not None else {"list_usd": list_usd}}
        if role is not None:
            row["role"] = role
        with open(os.path.join(run_dir, "meta.json"), "w", encoding="utf-8") as stream:
            json.dump(row, stream)
        with open(os.path.join(self.state, "ledger.jsonl"), "a", encoding="utf-8") as stream:
            stream.write(json.dumps(row) + "\n")
        if outcome:
            with open(os.path.join(run_dir, "review.json"), "w", encoding="utf-8") as stream:
                json.dump({"outcome": outcome, "note": "", "fix_minutes": None,
                           "reviewed_at": stamp(0)}, stream)
        return run_dir

    def metered(self, before, after, list_usd):
        def reading(percent):
            return {"observed_at": "2026-10-17T00:00:00Z", "age_seconds": 1, "status": "ok",
                    "windows": [{"label": "weekly", "used_percent": percent, "resets_at": "2099-01-01T00:00:00Z"}]}
        return {"before": reading(before), "after": reading(after), "list_usd": list_usd}

    def write_calibration(self, rate):
        with open(os.path.join(self.state, "claude-calibration.json"), "w", encoding="utf-8") as stream:
            json.dump({"pct_per_usd": rate}, stream)

    def arm_row(self, lane, effort, class_name="hard"):
        for row in self.context(class_name)["stats"]:
            if row["entry"]["lane"] == lane and row["entry"]["effort"] == effort:
                return row
        self.fail("no arm {}/{}".format(lane, effort))

    # --- pricing ---

    def test_a_fable_run_costs_the_fable_over_opus_weight_times_the_calibrated_rate(self):
        self.write_calibration(0.04)
        self.add_run("opus-1", lane="opus", list_usd=10.0)
        self.add_run("fable-1", lane="fable", role="plan", list_usd=10.0)
        opus, fable = self.arm_row("opus", "high"), self.arm_row("fable", "high")
        self.assertEqual((opus["tier"], fable["tier"]), ("calibrated", "calibrated"))
        self.assertAlmostEqual(opus["cost"], 10.0 * 0.04)
        self.assertAlmostEqual(fable["cost"], 10.0 * 0.04 * 1.69 / 0.67)

    def test_the_fable_factor_is_one_without_two_positive_weights(self):
        self.write_calibration(0.04)
        self.add_run("fable-1", lane="fable", role="plan", list_usd=10.0)
        for weights in ({"opus": 0.67}, {"fable": 1.69}, {"opus": 0, "fable": 1.69}, {"opus": 0.67, "fable": -1},
                        {"opus": "x", "fable": 1.69}, {"opus": True, "fable": 1.69}, None):
            window = {"model_weight_week": weights} if weights is not None else {}
            self.catalog["providers"]["claude"]["window"] = window
            self.save_catalog()
            self.assertAlmostEqual(self.arm_row("fable", "high")["cost"], 0.4, msg=repr(weights))
        del self.catalog["providers"]["claude"]["window"]
        self.save_catalog()
        self.assertAlmostEqual(self.arm_row("fable", "high")["cost"], 0.4)

    def test_a_share_the_meter_measured_is_not_scaled(self):
        self.write_calibration(0.04)
        self.add_run("fable-1", lane="fable", role="plan", started=stamp(2),
                     usage=self.metered(10.0, 12.0, 10.0))
        self.add_run("fable-2", lane="fable", role="plan", started=stamp(1),
                     usage=self.metered(20.0, 24.0, 10.0))
        row = self.arm_row("fable", "high")
        self.assertEqual(row["tier"], "measured")
        self.assertAlmostEqual(row["cost"], 3.0, delta=0.05)

    # --- report ---

    def test_report_groups_by_role_and_shows_a_dash_for_no_role(self):
        self.add_run("opus-1", lane="opus", list_usd=1.0)
        self.add_run("fable-1", lane="fable", role="plan", list_usd=2.0)
        self.add_run("fable-2", lane="fable", role="plan", list_usd=3.0)
        self.add_run("fable-3", lane="fable", role="user", list_usd=4.0)
        rows = {row[0]: row for row in (line.split() for line in self.cli("report", "--by", "role").splitlines()[2:-1])}
        self.assertEqual({key: row[1] for key, row in rows.items()}, {"-": "1", "plan": "2", "user": "1"})
        groups = json.loads(self.cli("report", "--by", "lane,role", "--json"))
        self.assertEqual([(g["lane"], g["role"], g["runs"]) for g in groups],
                         [("fable", "plan", 2), ("fable", "user", 1), ("opus", "-", 1)])
        text = self.cli("report", "--by", "lane,role")
        header = text.splitlines()[0].split()
        self.assertEqual(header[:2], ["lane", "role"])
        for column in ("runs", "ok%", "reviewed", "accepted%", "usable%", "med_min", "min/usable", "wk%/run",
                       "wk%/usable", "$list/usable", "plan$/usable", "pts/usable"):
            self.assertIn(column, header)

    def test_report_keeps_the_existing_by_fields_and_rejects_unknown_ones(self):
        self.add_run("fable-1", lane="fable", role="plan", list_usd=2.0)
        self.assertIn("fable", self.cli("report"))
        for field in ("lane", "model", "effort", "class", "tag", "provider", "place"):
            self.cli("report", "--by", field)
        self.assertEqual(json.loads(self.cli("report", "--by", "provider", "--json"))[0]["provider"], "claude")
        self.cli("report", "--by", "nope", code=2)

    # --- advisor ---

    def fixture_runs(self):
        self.add_run("plan-1", lane="fable", role="plan", effort="xhigh", list_usd=3.0, duration_s=300,
                     outcome="accepted")
        self.add_run("plan-2", lane="fable", role="plan", effort="xhigh", list_usd=2.5, duration_s=900,
                     outcome="fixed")
        self.add_run("final-1", lane="fable", role="final-review", effort="high", list_usd=4.0, duration_s=600,
                     outcome="rejected")
        self.add_run("user-1", lane="fable", role="user", effort="high", list_usd=50.0)
        self.add_run("old-1", lane="fable", role="plan", effort="xhigh", list_usd=20.0, started=stamp(10))
        self.add_run("opus-1", lane="opus", list_usd=99.0)

    def test_advisor_reports_budget_use_and_per_role_outcomes(self):
        self.fixture_runs()
        text = self.cli("advisor")
        self.assertLess(len(text.splitlines()), 25)
        self.assertIn("advisor: lane fable model fable active no", text)
        self.assertIn("inactive: weaker than Opus", text)
        self.assertIn("$9.50 of $60.00", text)
        data = json.loads(self.cli("advisor", "--json"))
        self.assertEqual((data["lane"], data["model"], data["active"], data["budget"]),
                         ("fable", "fable", False, 60))
        self.assertEqual(data["inactive_reason"], "weaker than Opus")
        self.assertAlmostEqual(data["list_usd_7d"], 9.5)
        roles = {row["role"]: row for row in data["roles"]}
        self.assertEqual(list(roles)[:4], list(ROLES))
        plan = roles["plan"]
        self.assertEqual((plan["runs"], plan["reviewed"], plan["accepted"], plan["fixed"], plan["rework"],
                          plan["rejected"]), (3, 2, 1, 1, 0, 0))
        self.assertAlmostEqual(plan["usable_rate"], 1.0)
        # The per-role figures cover every fable run; only the budget is limited to the last 7 days.
        self.assertAlmostEqual(plan["median_minutes"], 10.0)
        self.assertEqual((roles["final-review"]["rejected"], roles["final-review"]["usable_rate"]), (1, 0.0))
        self.assertEqual((roles["ladder"]["runs"], roles["ladder"]["usable_rate"], roles["ladder"]["median_minutes"]),
                         (0, None, None))
        self.assertEqual(roles["user"]["runs"], 1)

    def test_advisor_budget_ignores_other_lanes_and_runs_without_cost_or_time(self):
        self.add_run("plan-1", lane="fable", role="plan", list_usd=None)
        self.add_run("plan-2", lane="fable", role="plan", list_usd=1.25, started="not a time")
        self.add_run("plan-3", lane="fable", role="ladder", list_usd=1.0)
        self.assertAlmostEqual(json.loads(self.cli("advisor", "--json"))["list_usd_7d"], 1.0)

    def test_advisor_without_a_configured_block_says_so(self):
        del self.catalog["explore"]["advisor"]
        self.save_catalog()
        self.assertEqual(self.cli("advisor"), "advisor: not configured\n")
        self.assertEqual(json.loads(self.cli("advisor", "--json")), {"configured": False})

    def test_advisor_on_an_empty_ledger_lists_the_configured_roles(self):
        text = self.cli("advisor")
        self.assertLess(len(text.splitlines()), 25)
        for role in ROLES:
            self.assertIn(role, text)

    # --- the picker never offers a fable arm ---

    def test_pick_recommend_eta_and_main_picks_never_offer_a_fable_arm(self):
        self.write_calibration(0.04)
        for index in range(6):
            effort = ("high", "xhigh")[index % 2]
            self.add_run("fable-{}".format(index), lane="fable", effort=effort, role="plan", list_usd=1.0,
                         started=stamp(1, index), outcome="accepted")
            self.add_run("opus-{}".format(index), lane="opus", list_usd=1.0, started=stamp(1, index),
                         outcome="accepted" if index % 2 else "rework")
        rows, _ = stats.eligible_draw(self.context(), "hard")
        self.assertEqual({row["entry"]["lane"] for row in rows}, {"opus", "sonnet"})
        for seed in range(25):
            for command in ("pick", "explore"):
                picked = json.loads(self.cli(command, "--class", "hard", "--no-usage", "--json", "--seed", str(seed)))
                self.assertNotIn("fable", " ".join(picked["arms"]))
                self.assertFalse(any("fable" in item["arm"] for item in picked["top"]))
        pair = json.loads(self.cli("pick", "--class", "hard", "--no-usage", "--json", "--pair",
                                   "--approved", "test", "--seed", "3"))
        self.assertFalse(any("fable" in arm for arm in pair["arms"]))
        recommended = json.loads(self.cli("recommend", "--no-usage", "--json", "--seed", "1"))
        for block in recommended["classes"].values():
            self.assertNotIn("fable", str(block["leader"]))
            self.assertFalse(any("fable" in item["arm"] for item in block["arms"]))
        listed = json.loads(self.cli("eta", "--class", "hard", "--json"))
        self.assertEqual({item["arm"].split("/")[0] for item in listed["arms"]}, {"opus", "sonnet"})
        picks = json.loads(self.cli("main-picks", "--no-usage"))
        self.assertNotIn("fable", json.dumps(picks))

    def test_the_arms_listing_still_shows_the_manual_fable_arms(self):
        self.add_run("fable-1", lane="fable", role="plan", list_usd=1.0)
        data = json.loads(self.cli("arms", "--json"))
        fable = [row for row in data["arms"] if row["arm"].startswith("fable")]
        self.assertEqual([row["status"] for row in fable], ["manual", "manual"])
        self.assertEqual(data["off_catalog"], [])

    def test_the_shipped_catalog_runs_fable_5_2_with_the_advisor_on(self):
        with open(os.path.join(ROOT, "arms.json"), "r", encoding="utf-8") as stream:
            self.catalog = json.load(stream)
        self.save_catalog()
        data = json.loads(self.cli("arms", "--json"))
        fable = {row["arm"]: row["status"] for row in data["arms"] if row["arm"].startswith("fable/")}
        self.assertEqual(sorted(status for arm, status in fable.items() if "fable-5-2" in arm),
                         ["active", "active", "manual"])
        self.assertEqual([status for arm, status in fable.items() if "fable-5-1" in arm], ["disabled"] * 3)
        advisor = json.loads(self.cli("advisor", "--json"))
        self.assertTrue(advisor["active"])


if __name__ == "__main__":
    unittest.main()
