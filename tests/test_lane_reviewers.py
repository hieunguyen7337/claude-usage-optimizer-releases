import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import unittest
import uuid


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "bin", "lane-stats")
loader = importlib.machinery.SourceFileLoader("lane_stats_reviewers", SCRIPT)
stats = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
loader.exec_module(stats)

HIGHER = ("apply a verified finding by default; decline only for explicit direction, repo convention "
          "or a pattern it did not see")
LOWER = ("start sceptical: act only on a concrete correctness, contract or security flaw with a "
         "path that fires")
UNKNOWN = "no data: treat as lower-signal; record --findings on its reviews"


class ReviewerStatsTests(unittest.TestCase):
    def setUp(self):
        self.old_env = os.environ.copy()
        self.temp = os.path.join(os.path.dirname(__file__), ".lane-reviewers-{}-{}".format(
            os.getpid(), uuid.uuid4().hex))
        os.mkdir(self.temp)
        self.state = os.path.join(self.temp, "lanes")
        os.makedirs(os.path.join(self.state, "runs"))
        os.environ["LANES_STATE"] = self.state
        os.environ["PYTHONUTF8"] = "1"
        os.environ["LANES_ARMS"] = os.path.join(self.temp, "arms.json")
        os.environ["LANES_ARMS_LOCAL"] = os.path.join(self.temp, "arms.local.json")
        os.environ["LANES_MACHINE"] = "this-machine"

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old_env)
        shutil.rmtree(self.temp)

    def cli(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = stats.main(list(args))
        return code, stdout.getvalue(), stderr.getvalue()

    def add_run(self, name, lane="luna", effort="medium", class_name="mechanical"):
        run_dir = os.path.join(self.state, "runs", name)
        os.makedirs(run_dir)
        row = {"run_dir": run_dir, "lane": lane, "model": lane, "effort": effort, "class": class_name,
               "started_at": "2026-10-17T00:00:00Z", "ended_at": "2026-10-17T00:02:00Z",
               "verdict": "OK", "exit_code": 0}
        with open(os.path.join(run_dir, "meta.json"), "w", encoding="utf-8") as stream:
            json.dump(row, stream)
        with open(os.path.join(self.state, "ledger.jsonl"), "a", encoding="utf-8") as stream:
            stream.write(json.dumps(row) + "\n")
        return run_dir

    def suite_row(self, arm, precision=1.0, planted=True, recall_planted=1.0, real_total=0, recall_real=None,
                  infra=False, skipped=False, present=True):
        lane, effort = arm.rsplit("-", 1)
        return {"arm": arm, "lane": lane, "effort": effort, "infra_failure": infra, "skipped": skipped,
                "run_present": present, "is_planted_item": planted, "precision_v2_nodup_item": precision,
                "recall_planted_v1_item": recall_planted, "real_issue_total": real_total,
                "recall_real_item": recall_real}

    def write_suite(self, rows, bad_line=False):
        directory = os.path.join(self.temp, "findings", "suite-r")
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, "rescore-per-run.jsonl")
        with open(path, "w", encoding="utf-8") as stream:
            if bad_line:
                stream.write("{not json\n")
            for row in rows:
                stream.write(json.dumps(row) + "\n")
        return path

    def review(self, name, outcome="accepted", findings=None):
        args = ["review", name, "--outcome", outcome]
        # Equals form so a negative count is an argument, not another flag.
        if findings is not None:
            args.append("--findings=" + findings)
        return self.cli(*args)

    def arms(self, *args):
        code, out, err = self.cli("reviewers", "--json", *args)
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        again = json.loads(json.dumps(payload, allow_nan=False))
        self.assertEqual(payload, again)
        self.assertEqual(out, json.dumps(payload, ensure_ascii=False, allow_nan=False) + "\n")
        return payload, err

    def test_findings_flag_stores_integers_and_rejects_bad_values(self):
        counted = self.add_run("counted", lane="astra", effort="high")
        code, out, err = self.review("counted", findings="3/5")
        self.assertEqual((code, out.strip(), err), (0, "reviewed counted: accepted", ""))
        with open(os.path.join(counted, "review.json"), encoding="utf-8") as stream:
            review = json.load(stream)
        self.assertEqual(list(review)[:3], ["outcome", "findings_applied", "findings_total"])
        self.assertIs(type(review["findings_applied"]), int)
        self.assertIs(type(review["findings_total"]), int)
        self.assertEqual((review["findings_applied"], review["findings_total"], review["outcome"]), (3, 5, "accepted"))
        with open(os.path.join(self.state, "reviews.jsonl"), encoding="utf-8") as stream:
            line = json.loads(stream.readline())
        self.assertEqual((line["findings_applied"], line["findings_total"], line["run_dir"]), (3, 5, counted))
        exported = stats.export_record({"lane": "astra", "run_dir": counted, "usage": {}}, review, {})
        self.assertEqual((exported["review"]["findings_applied"], exported["review"]["findings_total"]), (3, 5))

        zero = self.add_run("zero")
        self.assertEqual(self.review("zero", findings="0/0")[0], 0)
        with open(os.path.join(zero, "review.json"), encoding="utf-8") as stream:
            zero_review = json.load(stream)
        self.assertEqual((zero_review["findings_applied"], zero_review["findings_total"]), (0, 0))
        self.assertIs(type(zero_review["findings_applied"]), int)

        padded = self.add_run("padded")
        self.assertEqual(self.review("padded", findings=" 03/05 ")[0], 0)
        with open(os.path.join(padded, "review.json"), encoding="utf-8") as stream:
            padded_review = json.load(stream)
        self.assertEqual((padded_review["findings_applied"], padded_review["findings_total"]), (3, 5))

        plain = self.add_run("plain")
        self.assertEqual(self.review("plain")[0], 0)
        with open(os.path.join(plain, "review.json"), encoding="utf-8") as stream:
            plain_review = json.load(stream)
        self.assertEqual(list(plain_review), ["outcome", "note", "fix_minutes", "reviewed_at"])
        plain_export = stats.export_record({"lane": "luna", "run_dir": plain, "usage": {}}, plain_review, {})
        self.assertNotIn("findings_applied", plain_export["review"])
        self.assertNotIn("findings_total", plain_export["review"])

        self.assertFalse(stats.valid_import({"machine": "other", "run_id": "r", "lane": "luna",
                                             "review": {"outcome": "accepted", "findings_applied": 2,
                                                        "findings_total": 1}}))
        self.assertFalse(stats.valid_import({"machine": "other", "run_id": "r", "lane": "luna",
                                             "review": {"outcome": "accepted", "findings_applied": True,
                                                        "findings_total": 1}}))
        self.assertTrue(stats.valid_import({"machine": "other", "run_id": "r", "lane": "luna",
                                            "review": {"outcome": "accepted", "findings_applied": 0,
                                                       "findings_total": 0}}))

        for value in ("nope", "3", "6/5", "-1/2", "1/-1", "1/2/3", "1.5/2", "", "1 / 2", "+1/2"):
            name = "bad-" + uuid.uuid4().hex[:8]
            self.add_run(name)
            code, out, err = self.review(name, findings=value)
            self.assertEqual(code, 2, value)
            self.assertEqual(out, "", value)
            self.assertEqual([line for line in err.splitlines() if line.strip()], [err.strip()], value)
            self.assertTrue(err.startswith("lane-stats: "), value)
            self.assertIn("APPLIED", err)
            self.assertFalse(os.path.exists(os.path.join(self.state, "runs", name, "review.json")))

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as caught:
                stats.main(["reviewers", "--min-findings", "-1"])
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("min-findings", stderr.getvalue())

    def test_reviewers_tier_uses_live_only_past_min_findings(self):
        rows = [
            self.suite_row("astra-high", precision=1.0, planted=True, recall_planted=1.0, real_total=2, recall_real=0.5),
            self.suite_row("astra-high", precision=0.8, planted=False, recall_planted=0.0, real_total=0, recall_real=1.0),
            self.suite_row("astra-high", precision=None, planted=True, recall_planted=None, real_total=4, recall_real=1.0),
            self.suite_row("astra-high", precision=0.0, infra=True, real_total=9, recall_real=0.0),
            self.suite_row("astra-high", precision=0.0, skipped=True),
            self.suite_row("astra-high", precision=0.0, present=False),
            self.suite_row("sonnet-high", precision=0.5, planted=True, recall_planted=0.5, real_total=1, recall_real=0.0),
            self.suite_row("haiku-low", precision=None, planted=True, recall_planted=None),
            self.suite_row("haiku-low", precision=None, planted=False, recall_planted=0.2, real_total=0, recall_real=1.0),
            self.suite_row("sol-low", precision=0.85),
            self.suite_row("sol-medium", precision=0.84),
            self.suite_row("amp-high", precision=1.0),
            self.suite_row("cursor-high", precision=1.0),
            self.suite_row("terra-high", precision=1.0, infra=True),
            self.suite_row("terra-high", precision=1.0, skipped=True),
            self.suite_row("terra-high", precision=1.0, present=False),
        ]
        self.write_suite(rows, bad_line=True)
        self.add_run("astra-a", lane="astra", effort="high", class_name="mechanical")
        self.add_run("astra-b", lane="astra", effort="high", class_name="hard")
        self.review("astra-a", findings="4/5")
        self.review("astra-b", findings="4/5")
        self.add_run("sonnet-a", lane="sonnet", effort="high")
        self.review("sonnet-a", findings="2/2")
        self.add_run("opus-a", lane="opus", effort="xhigh")
        self.review("opus-a", findings="9/10")
        self.add_run("gemini-a", lane="gemini", effort="medium")
        self.review("gemini-a", findings="0/0")
        self.add_run("bare", lane="luna", effort="medium")
        self.review("bare")
        imported = os.path.join(self.state, "imported")
        os.makedirs(imported)
        good = {"machine": "other-machine", "run_id": "remote-grok", "lane": "grok", "effort": "high",
                "review": {"outcome": "accepted", "note": "", "reviewed_at": "2026-10-17T01:00:00Z",
                           "fix_minutes": None, "findings_applied": 1, "findings_total": 1}}
        bad = {"machine": "other-machine", "run_id": "remote-bad", "lane": "grok", "effort": "low",
               "review": {"outcome": "accepted", "findings_applied": 3, "findings_total": 1}}
        with open(os.path.join(imported, "other-machine.jsonl"), "w", encoding="utf-8") as stream:
            stream.write(json.dumps(good) + "\n")
            stream.write(json.dumps(bad) + "\n")

        payload, err = self.arms()
        self.assertEqual(err, "")
        self.assertEqual(payload["schema"], 1)
        self.assertEqual(payload["min_findings"], 10)
        by_arm = {row["arm"]: row for row in payload["arms"]}
        self.assertNotIn("terra-high", by_arm)
        self.assertNotIn("luna-medium", by_arm)
        self.assertNotIn("grok-low", by_arm)

        astra = by_arm["astra-high"]
        self.assertEqual(astra["suite_n"], 3)
        self.assertAlmostEqual(astra["precision_v2_nodup_item"], 0.9)
        self.assertAlmostEqual(astra["recall_planted_v1_item"], 1.0)
        self.assertAlmostEqual(astra["recall_real_item"], 0.75)
        self.assertEqual((astra["findings_applied"], astra["findings_total"]), (8, 10))
        self.assertAlmostEqual(astra["live_precision"], 0.8)
        self.assertEqual(astra["precision_source"], "live")
        self.assertEqual(astra["tier"], "lower-signal")
        self.assertAlmostEqual(astra["precision"], 0.8)
        self.assertEqual((astra["lane"], astra["effort"]), ("astra", "high"))

        sonnet = by_arm["sonnet-high"]
        self.assertEqual(sonnet["precision_source"], "suite-r")
        self.assertAlmostEqual(sonnet["precision"], 0.5)
        self.assertEqual(sonnet["tier"], "lower-signal")
        self.assertEqual((sonnet["findings_applied"], sonnet["findings_total"]), (2, 2))

        haiku = by_arm["haiku-low"]
        self.assertEqual(haiku["suite_n"], 2)
        self.assertIsNone(haiku["precision_v2_nodup_item"])
        self.assertIsNone(haiku["recall_planted_v1_item"])
        self.assertIsNone(haiku["recall_real_item"])
        self.assertEqual(haiku["tier"], "unknown")
        self.assertEqual(haiku["precision_source"], "suite-r")
        self.assertIsNone(haiku["findings_total"])

        self.assertEqual(by_arm["sol-low"]["tier"], "higher-signal")
        self.assertEqual(by_arm["sol-medium"]["tier"], "lower-signal")
        opus = by_arm["opus-xhigh"]
        self.assertIsNone(opus["suite_n"])
        self.assertIsNone(opus["precision_v2_nodup_item"])
        self.assertEqual(opus["precision_source"], "live")
        self.assertEqual(opus["tier"], "higher-signal")
        self.assertEqual((opus["findings_applied"], opus["findings_total"]), (9, 10))
        gemini = by_arm["gemini-medium"]
        self.assertEqual((gemini["findings_applied"], gemini["findings_total"]), (0, 0))
        self.assertEqual(gemini["precision_source"], "suite-r")
        self.assertEqual(gemini["tier"], "unknown")
        self.assertIsNone(gemini["precision"])
        grok = by_arm["grok-high"]
        self.assertEqual((grok["findings_applied"], grok["findings_total"]), (1, 1))
        self.assertEqual(grok["tier"], "unknown")

        self.assertEqual([row["arm"] for row in payload["arms"]], [
            "amp-high", "cursor-high", "opus-xhigh", "sol-low",
            "sol-medium", "astra-high", "sonnet-high",
            "gemini-medium", "grok-high", "haiku-low"])
        self.assertEqual([row["tier"] for row in payload["arms"]], [
            "higher-signal", "higher-signal", "higher-signal", "higher-signal",
            "lower-signal", "lower-signal", "lower-signal",
            "unknown", "unknown", "unknown"])
        for row in payload["arms"]:
            self.assertEqual(row["stance"], stats.REVIEWER_STANCE[row["tier"]])

        switched, _ = self.arms("--min-findings", "11")
        switched_by = {row["arm"]: row for row in switched["arms"]}
        self.assertEqual(switched["min_findings"], 11)
        self.assertEqual(switched_by["astra-high"]["precision_source"], "suite-r")
        self.assertEqual(switched_by["astra-high"]["tier"], "higher-signal")
        self.assertAlmostEqual(switched_by["astra-high"]["precision"], 0.9)
        self.assertEqual(switched_by["opus-xhigh"]["precision_source"], "suite-r")
        self.assertEqual(switched_by["opus-xhigh"]["tier"], "unknown")
        self.assertIsNone(switched_by["opus-xhigh"]["precision"])
        self.assertEqual(switched_by["sonnet-high"]["precision_source"], "suite-r")

        low_bar, _ = self.arms("--min-findings", "2")
        low_by = {row["arm"]: row for row in low_bar["arms"]}
        self.assertEqual(low_by["sonnet-high"]["precision_source"], "live")
        self.assertEqual(low_by["sonnet-high"]["tier"], "higher-signal")
        self.assertAlmostEqual(low_by["sonnet-high"]["precision"], 1.0)
        self.assertEqual(low_by["haiku-low"]["precision_source"], "suite-r")

        zero_bar, _ = self.arms("--min-findings", "0")
        zero_by = {row["arm"]: row for row in zero_bar["arms"]}
        self.assertEqual(zero_by["gemini-medium"]["precision_source"], "live")
        self.assertEqual(zero_by["gemini-medium"]["tier"], "unknown")
        self.assertIsNone(zero_by["gemini-medium"]["precision"])
        self.assertEqual(zero_by["haiku-low"]["precision_source"], "suite-r")
        self.assertEqual(zero_by["sol-low"]["precision_source"], "suite-r")

        code, text, err = self.cli("reviewers")
        self.assertEqual((code, err), (0, ""))
        lines = text.splitlines()
        self.assertEqual(len(lines[0]), len(lines[1]))
        self.assertIn("precision_v2", lines[0])
        self.assertEqual(lines[1].strip("- "), "")
        blank = lines.index("")
        shown = [line.split()[0] for line in lines[2:blank]]
        self.assertEqual(shown, [row["arm"] for row in payload["arms"]])
        astra_line = next(line for line in lines if line.startswith("astra-high"))
        self.assertIn("8/10", astra_line)
        self.assertIn("lower-signal", astra_line)
        self.assertEqual(text.split("\n\n", 1)[1],
                         "higher-signal: {}\nlower-signal: {}\nunknown: {}\n".format(HIGHER, LOWER, UNKNOWN))

    def test_rereview_counts_once_and_classes_share_an_arm(self):
        self.write_suite([])
        self.add_run("once", lane="luna", effort="low", class_name="mechanical")
        self.review("once", findings="9/10")
        self.review("once", outcome="fixed", findings="1/4")
        with open(os.path.join(self.state, "reviews.jsonl"), encoding="utf-8") as stream:
            self.assertEqual(len(stream.readlines()), 2)
        payload, _ = self.arms("--min-findings", "1")
        self.assertEqual(len(payload["arms"]), 1)
        arm = payload["arms"][0]
        self.assertEqual(arm["arm"], "luna-low")
        self.assertEqual((arm["findings_applied"], arm["findings_total"]), (1, 4))
        self.assertEqual(arm["precision_source"], "live")
        self.assertAlmostEqual(arm["precision"], 0.25)
        self.assertEqual(arm["tier"], "lower-signal")

    def test_missing_suite_file_leaves_nulls_and_a_note(self):
        self.add_run("only", lane="astra", effort="high")
        self.review("only", findings="9/10")
        payload, err = self.arms()
        self.assertIn("no Suite R file", err)
        self.assertIn("Suite R columns are empty", err)
        self.assertEqual(len([line for line in err.splitlines() if line.strip()]), 1)
        self.assertNotIn("no Suite R file", json.dumps(payload))
        self.assertEqual(len(payload["arms"]), 1)
        arm = payload["arms"][0]
        self.assertEqual(arm["arm"], "astra-high")
        self.assertIsNone(arm["suite_n"])
        self.assertIsNone(arm["precision_v2_nodup_item"])
        self.assertIsNone(arm["recall_planted_v1_item"])
        self.assertIsNone(arm["recall_real_item"])
        self.assertEqual(arm["precision_source"], "live")
        self.assertEqual((arm["findings_applied"], arm["findings_total"]), (9, 10))
        self.assertEqual(arm["tier"], "higher-signal")
        code, text, err = self.cli("reviewers")
        self.assertEqual(code, 0)
        self.assertIn("astra-high", text)
        self.assertIn("9/10", text)
        self.assertIn("no Suite R file", err)
        self.assertNotIn("no Suite R file", text)

    def test_stance_constants_match_the_reviewer_policy(self):
        self.assertEqual(stats.REVIEWER_STANCE["higher-signal"], HIGHER)
        self.assertEqual(stats.REVIEWER_STANCE["lower-signal"], LOWER)
        self.assertEqual(stats.REVIEWER_STANCE["unknown"], UNKNOWN)
        self.assertEqual(stats.REVIEWER_PRECISION_BAR, 0.85)
        self.assertEqual(stats.REVIEWER_MIN_FINDINGS, 10)

    def test_replicates_join_their_arm_and_fable_rows_take_the_model_name(self):
        rows = [
            {"arm": "astra-high", "lane": "astra", "effort": "high", "precision_v2_nodup_item": 1.0},
            {"arm": "astra-high-r2", "lane": "astra", "effort": "high", "precision_v2_nodup_item": 0.5},
            {"arm": "opus-max-claude-fable-5-1", "lane": "opus", "effort": "max", "precision_v2_nodup_item": 0.9},
        ]
        by_arm = stats.suite_r_by_arm(rows)
        self.assertEqual(sorted(by_arm), ["astra-high", "fable-5.1-max"])
        self.assertEqual(by_arm["astra-high"]["suite_n"], 2)
        self.assertAlmostEqual(by_arm["astra-high"]["precision_v2_nodup_item"], 0.75)


if __name__ == "__main__":
    unittest.main()
