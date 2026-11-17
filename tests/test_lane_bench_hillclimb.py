"""Tests for `lane-bench hillclimb`: blind reviewer rounds over labelled screens. Every lane is faked."""

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
import unittest
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "bin", "lane-bench")
loader = importlib.machinery.SourceFileLoader("lane_bench_hill_tested", SCRIPT)
bench = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
loader.exec_module(bench)

FEEDBACK = "The hero screen feels crowded; say less above the fold."
APPROVED = "the user, 2026-11-17 09:00"

# The reviewer stand-in. It reads the first line of each staged screen (ROLE:<role>), scores the screens from
# FAKE_LANE_SPEC, and writes a run directory the way lane does: meta.json with list dollars, final.md with the answer,
# then the summary line with out=<dir> and a warning after it (lane prints warnings after the summary).
FAKE_LANE = r'''#!/usr/bin/env python3
import json
import os
import sys
import time


def main(argv):
    lane = argv[0]
    workspace = os.getcwd()
    brief = argv[argv.index("-b") + 1]
    with open(os.environ["FAKE_LANE_SPEC"], encoding="utf-8") as stream:
        spec = json.load(stream)
    roles = {}
    for folder in sorted(os.listdir(workspace)):
        if folder.startswith("screen-"):
            first = sorted(os.listdir(os.path.join(workspace, folder)))[0]
            with open(os.path.join(workspace, folder, first), encoding="utf-8") as stream:
                roles[folder[len("screen-"):]] = stream.readline().strip()[len("ROLE:"):]
    with open(brief, encoding="utf-8") as stream:
        brief_text = stream.read()
    with open(os.environ["FAKE_LANE_LOG"], "a", encoding="utf-8") as stream:
        stream.write(json.dumps({"argv": argv, "cwd_files": sorted(os.listdir(workspace)),
                                 "brief": brief_text, "roles": roles}) + "\n")
    if spec.get("sleep"):
        time.sleep(spec["sleep"])
    runs = os.environ["FAKE_LANE_RUNS"]
    os.makedirs(runs, exist_ok=True)
    run_dir = os.path.join(runs, "run-%03d" % len(os.listdir(runs)))
    os.makedirs(run_dir)
    with open(os.path.join(run_dir, "meta.json"), "w", encoding="utf-8") as stream:
        json.dump({"lane": lane, "usage": {"list_usd": spec.get("usd")}}, stream)
    if spec.get("write_final", True):
        text = spec.get("final_text")
        if text is None:
            answer = {"scores": {letter: spec["scores"][role] for letter, role in roles.items()},
                      "fixes": spec.get("fixes", []), "regressions": spec.get("regressions", []),
                      "checklist": spec.get("checklist", [])}
            text = "Notes first.\n\n```json\n" + json.dumps(answer) + "\n```\n"
        with open(os.path.join(run_dir, "final.md"), "w", encoding="utf-8") as stream:
            stream.write(text)
    code = spec.get("exit", 0)
    print("lane={} verdict=OK exit={} session=- secs=1 out={} class=review".format(lane, code, run_dir))
    print("warning: a line that lane prints after the summary")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
'''


def score_set(layout, copy, before=(4, 5), ref_a=(8, 8), ref_b=(8, 8)):
    """Scores per role as (layout, copy) pairs; the candidate's pair comes first."""
    return {"candidate": {"layout": layout, "copy": copy},
            "before": {"layout": before[0], "copy": before[1]},
            "ref:ref-a.png": {"layout": ref_a[0], "copy": ref_a[1]},
            "ref:ref-b.png": {"layout": ref_b[0], "copy": ref_b[1]}}


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(text)


def read_text(path):
    with open(path, encoding="utf-8") as stream:
        return stream.read()


class HillCase(unittest.TestCase):
    """A temp directory for every test, a fake lane on LANE_BENCH_LANE, and the artifacts: the artifact as it was,
    two references and a candidate. Each screen file says its role on its first line; the fake reads it."""

    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix="lane-bench-hill-")
        self.addCleanup(shutil.rmtree, self.temp, True)
        bin_dir = os.path.join(self.temp, "bin")
        os.makedirs(bin_dir)
        self.fake = os.path.join(bin_dir, "lane")
        with open(self.fake, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(FAKE_LANE)
        os.chmod(self.fake, 0o755)
        self.spec_path = os.path.join(self.temp, "spec.json")
        self.lane_log = os.path.join(self.temp, "lane-calls.jsonl")
        env = {"LANE_BENCH_LANE": self.fake, "FAKE_LANE_SPEC": self.spec_path, "FAKE_LANE_LOG": self.lane_log,
               "FAKE_LANE_RUNS": os.path.join(self.temp, "runs"),
               "LANES_PROC_CGROUP": os.path.join(self.temp, "no-such-cgroup"),
               "LANES_STATE": os.path.join(self.temp, "state")}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.set_spec()
        self.before_file = os.path.join(self.temp, "src", "before", "home.png")
        write_text(self.before_file, "ROLE:before\nlayout v1\n")
        self.ref_a = os.path.join(self.temp, "src", "refs", "ref-a.png")
        write_text(self.ref_a, "ROLE:ref:ref-a.png\nlayout reference a\n")
        self.ref_b = os.path.join(self.temp, "src", "refs", "ref-b.png")
        write_text(self.ref_b, "ROLE:ref:ref-b.png\ncopy reference b\n")
        self.candidate_file = os.path.join(self.temp, "src", "next", "home.png")
        write_text(self.candidate_file, "ROLE:candidate\nlayout v2\n")
        self.workdir = os.path.join(self.temp, "hill")

    def set_spec(self, **changes):
        spec = {"scores": score_set(9, 9), "usd": 0.4, "fixes": ["tighten the headline"], "regressions": [],
                "checklist": []}
        spec.update(changes)
        with open(self.spec_path, "w", encoding="utf-8") as stream:
            json.dump(spec, stream)

    def run_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = bench.main(argv)
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def init(self, *extra):
        return self.run_main(["hillclimb", "init", self.workdir, "--feedback", FEEDBACK,
                              "--dimension", "layout", "--dimension", "copy", "--before", self.before_file,
                              "--ref", self.ref_a, "--ref", self.ref_b, "--approved", APPROVED] + list(extra))

    def snapshot(self):
        return self.run_main(["hillclimb", "snapshot", self.workdir, self.candidate_file])

    def review(self, lane, *extra):
        return self.run_main(["hillclimb", "review", self.workdir, "--lane", lane, "-e", "high"] + list(extra))

    def state(self):
        return bench.read_json(os.path.join(self.workdir, "state.json"))

    def status_json(self):
        code, out, err = self.run_main(["hillclimb", "status", self.workdir, "--json"])
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def lane_calls(self):
        if not os.path.exists(self.lane_log):
            return []
        with open(self.lane_log, encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]


class InitTests(HillCase):
    def test_init_refuses_without_approval_and_creates_nothing(self):
        argv = ["hillclimb", "init", self.workdir, "--feedback", FEEDBACK, "--dimension", "layout",
                "--dimension", "copy", "--before", self.before_file]
        for approval in ([], ["--approved", ""], ["--approved", "  \t "]):
            code, out, err = self.run_main(argv + approval)
            self.assertEqual(code, 2)
            self.assertEqual(out, "")
            self.assertEqual(err.strip(), bench.HILL_APPROVAL_REFUSAL)
        self.assertIn("lane-bench hillclimb is a capability test", bench.HILL_APPROVAL_REFUSAL)
        self.assertFalse(os.path.exists(self.workdir))
        self.assertEqual(self.lane_calls(), [])

    def test_init_writes_state_plan_rounds_and_copies(self):
        code, _, err = self.init()
        self.assertEqual(code, 0, err)
        state = self.state()
        self.assertEqual(state["dimensions"], ["layout", "copy"])
        self.assertEqual(state["bar"], 9.0)
        self.assertEqual(state["rounds_cap"], 4)
        self.assertEqual(state["budget_usd"], 5.0)
        self.assertEqual(state["builder_family"], "claude")
        self.assertEqual(state["before"], ["home.png"])
        self.assertEqual(state["refs"], ["ref-a.png", "ref-b.png"])
        self.assertEqual(state["rounds"], [])
        self.assertTrue(os.path.isfile(os.path.join(self.workdir, "before", "home.png")))
        self.assertTrue(os.path.isfile(os.path.join(self.workdir, "refs", "ref-a.png")))
        self.assertTrue(os.path.isfile(os.path.join(self.workdir, "refs", "ref-b.png")))
        plan = read_text(os.path.join(self.workdir, "PLAN.md"))
        self.assertIn("> The hero screen feels crowded", plan)
        self.assertIn("Bar: 9 on every dimension", plan)
        self.assertIn("Round cap: 4 rounds", plan)
        self.assertIn(APPROVED, plan)
        self.assertTrue(read_text(os.path.join(self.workdir, "ROUNDS.md")).startswith("# Hill-climb rounds"))

    def test_init_checks_dimensions_before_and_names(self):
        base = ["hillclimb", "init", self.workdir, "--feedback", FEEDBACK, "--approved", APPROVED]
        other = os.path.join(self.temp, "other", "home.png")
        write_text(other, "ROLE:before\n")
        cases = {
            "one dimension": ["--dimension", "layout", "--before", self.before_file],
            "six dimensions": ["--dimension", "a", "--dimension", "b", "--dimension", "c", "--dimension", "d",
                               "--dimension", "e", "--dimension", "f", "--before", self.before_file],
            "no before": ["--dimension", "layout", "--dimension", "copy"],
            "bar above ten": ["--dimension", "layout", "--dimension", "copy", "--before", self.before_file,
                              "--bar", "11"],
            "two befores with one name": ["--dimension", "layout", "--dimension", "copy",
                                          "--before", self.before_file, "--before", other],
        }
        for label, extra in cases.items():
            code, _, err = self.run_main(base + extra)
            self.assertEqual(code, 2, label)
            self.assertIn("lane-bench:", err, label)
            self.assertFalse(os.path.exists(self.workdir), label)

    def test_snapshot_refuses_a_missing_file_and_past_the_round_cap(self):
        self.assertEqual(self.init("--rounds", "1")[0], 0)
        code, _, err = self.run_main(["hillclimb", "snapshot", self.workdir, os.path.join(self.temp, "nope.png")])
        self.assertEqual(code, 2)
        self.assertIn("snapshot file not found", err)
        code, _, err = self.snapshot()
        self.assertEqual(code, 0, err)
        self.assertTrue(os.path.isfile(os.path.join(self.workdir, "round-1", "home.png")))
        code, _, err = self.snapshot()
        self.assertEqual(code, 2)
        self.assertIn("round cap reached (1)", err)
        self.assertEqual(len(self.state()["rounds"]), 1)

    def test_review_needs_a_round_and_a_known_family(self):
        self.init()
        code, _, err = self.review("gemini")
        self.assertEqual(code, 2)
        self.assertIn("run hillclimb snapshot first", err)
        self.snapshot()
        code, _, err = self.review("amp")
        self.assertEqual(code, 2)
        self.assertIn("no known model family", err)
        code, _, err = self.review("haiku", "--family", "openai")
        self.assertEqual(code, 2)
        self.assertIn("contradicts", err)
        self.assertEqual(self.lane_calls(), [])


class ReviewTests(HillCase):
    def test_labels_are_a_permutation_and_the_brief_is_blind(self):
        self.init()
        self.snapshot()
        code, _, err = self.review("sol")
        self.assertEqual(code, 0, err)
        review = self.state()["rounds"][0]["reviews"][0]
        self.assertEqual(sorted(review["labels"]), ["A", "B", "C", "D"])
        self.assertEqual(sorted(review["labels"].values()),
                         sorted(["candidate", "before", "ref:ref-a.png", "ref:ref-b.png"]))
        candidate = [letter for letter, role in review["labels"].items() if role == "candidate"][0]
        brief = self.lane_calls()[0]["brief"]
        lines = brief.splitlines()
        screen_paths = [line[2:] for line in lines if line.startswith("- ") and os.path.isabs(line[2:])]
        instructions = "\n".join(line for line in lines if not (line.startswith("- ") and os.path.isabs(line[2:])))
        lowered = instructions.lower()
        for word in ("round", "bar", "candidate", "before", "reference", "refs", "earlier", "9"):
            self.assertNotIn(word, lowered)
        self.assertIn("fixes for screen " + candidate, brief)
        self.assertEqual(len(screen_paths), 4)
        for path in screen_paths:
            self.assertTrue(os.path.isabs(path))
            self.assertNotIn("round", path.lower())
            self.assertNotIn(os.sep + "refs" + os.sep, path)
            self.assertNotIn(os.sep + "before" + os.sep, path)

    def test_reviewer_runs_in_a_folder_with_no_state_and_gets_the_lane_args(self):
        self.init()
        self.snapshot()
        code, _, err = self.review("gemini", "--lane-arg=-m", "--lane-arg=gemini-x")
        self.assertEqual(code, 0, err)
        call = self.lane_calls()[0]
        self.assertEqual(call["argv"][0], "gemini")
        self.assertEqual(call["argv"][call["argv"].index("--class") + 1], "review")
        self.assertEqual(call["argv"][call["argv"].index("-e") + 1], "high")
        self.assertIn("-C", call["argv"])
        self.assertEqual(call["argv"][-2:], ["-m", "gemini-x"])
        for name in ("state.json", "PLAN.md", "ROUNDS.md", "before", "refs", "round-1"):
            self.assertNotIn(name, call["cwd_files"])
        self.assertEqual(sorted(call["cwd_files"]), ["screen-A", "screen-B", "screen-C", "screen-D"])
        self.assertEqual(self.state()["rounds"][0]["reviews"][0]["lane_args"], ["-m", "gemini-x"])

    def test_parse_and_unblind_scores_by_role(self):
        self.init()
        self.snapshot()
        self.set_spec(scores=score_set(9, 8, before=(4, 5), ref_a=(8, 7), ref_b=(6, 9)), usd=0.42,
                      fixes=["tighten the headline"], regressions=["the footer wrapped"])
        code, _, err = self.review("gemini")
        self.assertEqual(code, 0, err)
        state = self.state()
        review = state["rounds"][0]["reviews"][0]
        self.assertEqual(review["status"], "ok")
        self.assertTrue(review["gating"])
        self.assertEqual(review["usd"], 0.42)
        self.assertEqual(review["scores"]["candidate"], {"layout": 9.0, "copy": 8.0})
        self.assertEqual(review["scores"]["before"], {"layout": 4.0, "copy": 5.0})
        self.assertEqual(review["scores"]["ref:ref-b.png"], {"layout": 6.0, "copy": 9.0})
        self.assertEqual(review["fixes"], ["tighten the headline"])
        self.assertEqual(review["regressions"], ["the footer wrapped"])
        self.assertTrue(os.path.isdir(review["run_dir"]))
        self.assertAlmostEqual(state["spend_usd"], 0.42)
        rounds = read_text(os.path.join(self.workdir, "ROUNDS.md"))
        self.assertIn("## Round 1, review 1: gemini effort high, gating, ok", rounds)
        self.assertIn("| layout | 9 | 4 | 8 | 6 |", rounds)
        self.assertIn("| copy | 8 | 5 | 7 | 9 |", rounds)

    def test_same_family_is_refused_then_runs_as_non_gating(self):
        self.init()
        self.snapshot()
        code, _, err = self.review("opus")
        self.assertEqual(code, 2)
        self.assertIn("the builder's family", err)
        self.assertEqual(self.lane_calls(), [])
        code, _, err = self.review("opus", "--allow-same-family")
        self.assertEqual(code, 0, err)
        review = self.state()["rounds"][0]["reviews"][0]
        self.assertFalse(review["gating"])
        self.assertEqual(review["family"], "claude")
        self.assertEqual(self.status_json()["verdict"], "continue")

    def test_amp_takes_its_model_family_from_the_flag_and_is_gating(self):
        self.init()
        self.snapshot()
        code, _, err = self.review("amp", "--family", "xai")
        self.assertEqual(code, 0, err)
        review = self.state()["rounds"][0]["reviews"][0]
        self.assertEqual(review["family"], "xai")
        self.assertTrue(review["gating"])

    def test_malformed_answers_fail_and_count_for_nothing(self):
        self.init()
        self.snapshot()
        self.set_spec(final_text="Notes.\n\n```json\n{\"scores\": \n```\n")
        code, _, _ = self.review("gemini")
        self.assertEqual(code, 1)
        self.set_spec(scores=score_set(11, 9))
        code, _, _ = self.review("gemini")
        self.assertEqual(code, 1)
        reviews = self.state()["rounds"][0]["reviews"]
        self.assertEqual([review["status"] for review in reviews], ["failed", "failed"])
        self.assertTrue(reviews[0]["reason"].startswith("the last json block does not parse"))
        self.assertIn("is not a number from 0 to 10", reviews[1]["reason"])
        self.assertIsNone(reviews[1]["scores"])
        status = self.status_json()
        self.assertEqual(status["verdict"], "continue")
        self.assertIn("no gating review has come back", " ".join(status["reasons"]))
        self.assertIn("2 failed review(s) not counted", " ".join(status["reasons"]))
        self.assertIn("Not counted:", read_text(os.path.join(self.workdir, "ROUNDS.md")))

    def test_lane_exit_and_missing_final_fail_but_still_cost(self):
        self.init()
        self.snapshot()
        self.set_spec(exit=3, usd=0.25)
        self.assertEqual(self.review("gemini")[0], 1)
        self.set_spec(write_final=False, usd=0.1)
        self.assertEqual(self.review("gemini")[0], 1)
        reviews = self.state()["rounds"][0]["reviews"]
        self.assertEqual(reviews[0]["reason"], "lane exited 3")
        self.assertEqual(reviews[1]["reason"], "the run wrote no final.md")
        self.assertAlmostEqual(self.state()["spend_usd"], 0.35)

    def test_timeout_is_recorded_as_failed(self):
        self.init()
        self.snapshot()
        self.set_spec(sleep=30)
        with mock.patch.object(bench, "TIMEOUT_GRACE_S", 0):
            code, _, _ = self.review("gemini", "--timeout", "1")
        self.assertEqual(code, 1)
        review = self.state()["rounds"][0]["reviews"][0]
        self.assertEqual(review["status"], "failed")
        self.assertEqual(review["reason"], "timed out after 1 s")

    def test_budget_refuses_the_next_review(self):
        self.init("--budget-usd", "0.5")
        self.snapshot()
        self.set_spec(scores=score_set(8, 9), usd=0.6)
        self.assertEqual(self.review("gemini")[0], 0)
        code, _, err = self.review("gemini")
        self.assertEqual(code, 2)
        self.assertIn("at or over the budget $0.5", err)
        self.assertEqual(len(self.lane_calls()), 1)
        status = self.status_json()
        self.assertEqual(status["verdict"], "stop")
        self.assertIn("budget reached", " ".join(status["reasons"]))


class StatusTests(HillCase):
    def test_stop_rule_met_only_when_every_gating_review_agrees(self):
        self.init()
        self.snapshot()
        self.set_spec(scores=score_set(9, 9))
        self.assertEqual(self.review("gemini")[0], 0)
        status = self.status_json()
        self.assertEqual((status["verdict"], status["reasons"]), ("met", []))
        self.set_spec(scores=score_set(9, 9, ref_b=(8, 10)))
        self.assertEqual(self.review("sol")[0], 0)
        status = self.status_json()
        self.assertEqual(status["verdict"], "continue")
        self.assertIn("review 2 (sol) scores the candidate 9 on copy, under ref:ref-b.png at 10",
                      status["reasons"])

    def test_candidate_under_the_bar_is_not_met(self):
        self.init()
        self.snapshot()
        self.set_spec(scores=score_set(8, 9))
        self.review("gemini")
        status = self.status_json()
        self.assertEqual(status["verdict"], "continue")
        self.assertIn("review 1 (gemini) scores the candidate 8 on layout, under the bar 9", status["reasons"])

    def test_status_json_round_trips_the_state_and_the_text_matches(self):
        self.init()
        self.snapshot()
        self.set_spec(scores=score_set(9, 9))
        self.review("gemini")
        state = self.state()
        data = self.status_json()
        self.assertEqual(data["verdict"], bench.hill_verdict(state)["verdict"])
        self.assertEqual(data["rounds"][0]["reviews"][0]["scores"], state["rounds"][0]["reviews"][0]["scores"])
        self.assertEqual(data["bar"], 9.0)
        self.assertEqual(data["rounds_used"], 1)
        self.assertEqual(data["spend_usd"], state["spend_usd"])
        code, text, err = self.run_main(["hillclimb", "status", self.workdir])
        self.assertEqual(code, 0, err)
        self.assertIn("verdict: met", text)
        self.assertIn("    candidate: layout 9, copy 9", text)

    def test_help_runs_for_the_group_and_the_review(self):
        for argv in (["hillclimb", "--help"], ["hillclimb", "review", "--help"]):
            result = subprocess.run([sys.executable, SCRIPT] + argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    timeout=60, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(b"usage: lane-bench hillclimb", result.stdout)


if __name__ == "__main__":
    unittest.main()
