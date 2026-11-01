import contextlib
import importlib.machinery
import importlib.util
import io
import json
import math
import os
import shutil
import sys
import tempfile
import threading
import unittest
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "bin", "lane-bench")
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "bench")
loader = importlib.machinery.SourceFileLoader("lane_bench_tested", SCRIPT)
bench = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
loader.exec_module(bench)
fixture_loader = importlib.machinery.SourceFileLoader("bench_rescore_case", os.path.join(FIXTURES, "rescore_case.py"))
rescore_case = importlib.util.module_from_spec(importlib.util.spec_from_loader(fixture_loader.name, fixture_loader))
fixture_loader.exec_module(rescore_case)


class FakeClock:
    """Monotonic time that only moves when something sleeps; sleeps are recorded, not waited."""

    def __init__(self, start=1000.0):
        self.now = start
        self.sleeps = []
        self.on_sleep = None
        self.lock = threading.Lock()

    def monotonic(self):
        with self.lock:
            return self.now

    def sleep(self, seconds):
        with self.lock:
            self.sleeps.append(seconds)
            self.now += seconds
        if self.on_sleep:
            self.on_sleep(seconds)


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(text)


def read_text(path):
    with open(path, encoding="utf-8") as stream:
        return stream.read()


def write_json(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, separators=(",", ":"))
        stream.write("\n")


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_script(path, body):
    write_text(path, "#!/bin/sh\n" + body + "\n")
    os.chmod(path, 0o755)
    return path


def make_cgroup(temp, leaf, levels):
    """levels = [(relative dir under the root, pids.max, pids.current)]; returns (root, proc cgroup file)."""
    root = os.path.join(temp, "cgroup")
    for relative, limit, current in levels:
        directory = os.path.join(root, relative) if relative else root
        write_text(os.path.join(directory, "pids.max"), limit + "\n")
        write_text(os.path.join(directory, "pids.current"), current + "\n")
    proc = os.path.join(temp, "proc-cgroup")
    write_text(proc, "0::" + leaf + "\n")
    return root, proc


DEFAULT_LEVELS = [("", "max", "0"), ("bench", "4096", "10"), ("bench/test.scope", "max", "3")]


class BenchCase(unittest.TestCase):
    """Every external binary is a fake; the clock is fake; the state directory is a temp directory."""

    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix="lane-bench-test-")
        self.addCleanup(shutil.rmtree, self.temp, True)
        self.clock = FakeClock()
        for target, value in (("CLOCK", self.clock.monotonic), ("SLEEP", self.clock.sleep)):
            patcher = mock.patch.object(bench, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.cgroup_root, self.proc_cgroup = make_cgroup(self.temp, "/bench/test.scope", DEFAULT_LEVELS)
        self.usage_file = os.path.join(self.temp, "usage.json")
        shutil.copyfile(os.path.join(FIXTURES, "usage_status.json"), self.usage_file)
        self.claude_calls = os.path.join(self.temp, "claude-calls.txt")
        self.lane_log = os.path.join(self.temp, "lane-calls.jsonl")
        bin_dir = os.path.join(self.temp, "bin")
        env = {
            "HOME": self.temp,
            "LANES_STATE": os.path.join(self.temp, "state"),
            "LANES_PROC_CGROUP": self.proc_cgroup,
            "LANES_CGROUP_ROOT": self.cgroup_root,
            "CODEX_HOME": os.path.join(FIXTURES, "codex_home"),
            "FAKE_LANE_MAP": os.path.join(FIXTURES, "lane_map.json"),
            "FAKE_LANE_LOG": self.lane_log,
            "LANE_BENCH_USAGE_STATUS": write_script(os.path.join(bin_dir, "usage-status"), 'cat "%s"' % self.usage_file),
            "LANE_BENCH_CLAUDE": write_script(os.path.join(bin_dir, "claude"),
                                              'echo call >> "%s"\ncat "%s"' % (
                                                  self.claude_calls, os.path.join(FIXTURES, "claude_stream.jsonl"))),
            "LANE_BENCH_LANE": write_script(os.path.join(bin_dir, "lane"),
                                            'exec "%s" "%s" "$@"' % (sys.executable,
                                                                    os.path.join(FIXTURES, "fake_lane.py"))),
        }
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = bench.main(argv)
        return code, out.getvalue(), err.getvalue()

    def copy_suite(self):
        target = os.path.join(self.temp, "suite")
        shutil.copytree(os.path.join(FIXTURES, "suite"), target)
        return target

    def lane_calls(self):
        if not os.path.exists(self.lane_log):
            return []
        with open(self.lane_log, encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]


class GraderTests(unittest.TestCase):
    def test_unplanted_key_changes_precision_not_recall(self):
        planted = {"id": "D1", "file": "src/x.py", "line": 10, "line_end": 10}
        real = {"id": "U1", "file": "src/x.py", "line": 30, "line_end": 30, "origin": "unplanted"}
        findings = [{"file": "src/x.py", "line": 10}, {"file": "src/x.py", "line": 30}]
        old = bench.score([planted], findings)
        new = bench.score([planted, real], findings)
        self.assertEqual(new["counts"]["defects_found"], old["counts"]["defects_found"])
        self.assertEqual(new["counts"]["unmatched_findings"], 0)
        self.assertEqual(new["real_found"], ["U1"])

    def test_no_unplanted_key_keeps_score_shape(self):
        ds = [{"id": "D1", "file": "src/x.py", "line": 10, "line_end": 10}]
        result = bench.score(ds, [{"file": "src/x.py", "line": 10}])
        self.assertNotIn("real_found", result)
        self.assertNotIn("real_found", result["counts"])

    def test_malformed_findings_are_format_failure_and_leniently_scored(self):
        temp = tempfile.mkdtemp(prefix="lane-bench-malformed-")
        self.addCleanup(shutil.rmtree, temp, True)
        base = os.path.join(FIXTURES, "suite")
        shutil.copytree(base, temp, dirs_exist_ok=True)
        path = os.path.join(temp, "runs", "luna", "001", "findings.jsonl")
        valid = {"file": "src/app.py", "line": 3, "severity": "medium", "description": "synthetic"}
        write_text(path, json.dumps(valid) + "\nnot-json\n")
        items = bench.load_suite(temp).load_items()
        summary = bench.aggregate(items, os.path.join(temp, "runs"), ["luna"])
        row = summary["arms"]["luna"]
        self.assertEqual(row["format_fail_items"], ["001"])
        self.assertEqual(row["items"]["001"]["counts"]["defects_found"], 0)
        self.assertEqual(row["items"]["001"]["lenient"]["counts"]["defects_found"], 1)

    def test_selftest_reproduces_grade_py_expectations(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = bench.selftest()
        text = out.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("SELFTEST-OK", text)
        self.assertIn("SELFTEST item 003: found=1 missed=1 matched=1 unmatched=2", text)
        self.assertIn("7 arms, 21 pairs, 35 triples", text)

    def test_score_window_endpoints_are_inclusive(self):
        ds = [{"id": "D1", "file": "src/x.py", "line": 20, "line_end": 22}]

        def finding(line, file="src/x.py"):
            return {"file": file, "line": line, "severity": "medium", "description": "synthetic"}

        self.assertEqual(bench.score(ds, [finding(15)])["counts"]["defects_found"], 1)
        self.assertEqual(bench.score(ds, [finding(27)])["counts"]["defects_found"], 1)
        self.assertEqual(bench.score(ds, [finding(14), finding(28), finding(20, "src/y.py")])["counts"]["defects_found"], 0)
        self.assertEqual(bench.score(ds, [finding(20), finding(20)])["counts"]["unmatched_findings"], 1)

    def test_window_parameter_changes_the_matching_range(self):
        ds = [{"id": "D1", "file": "src/x.py", "line": 20, "line_end": 20}]
        finding = {"file": "src/x.py", "line": 24, "severity": "low", "description": "synthetic"}
        # The window is [20 - w, 20 + w]: 24 is inside at w = 5 and outside at w = 3.
        self.assertEqual(bench.score(ds, [finding], window=5)["counts"]["defects_found"], 1)
        self.assertEqual(bench.score(ds, [finding], window=3)["counts"]["defects_found"], 0)

    def test_load_findings_rejects_malformed_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "findings.jsonl")
            for text in ("not json\n", '{"file": "src/x.py", "line": true, "severity": "low", "description": "x"}\n',
                         '{"file": "../x.py", "line": 3, "severity": "low", "description": "x"}\n',
                         '{"file": "src/x.py", "line": 3, "severity": "critical", "description": "x"}\n',
                         '{"file": "src/x.py", "line": 3, "severity": "low", "description": "  "}\n'):
                with open(path, "w", encoding="utf-8") as stream:
                    stream.write(text)
                with self.assertRaises(ValueError, msg=text):
                    bench.load_findings(path)

    def test_missing_findings_file_scores_as_no_findings(self):
        self.assertEqual(bench.load_findings("/nonexistent/findings.jsonl"), [])


class ExtendedKeyTests(BenchCase):
    def make_rescore_inputs(self):
        suite = os.path.join(self.temp, "rescore-suite")
        for item, defects in rescore_case.ITEM_DEFECTS.items():
            write_json(os.path.join(suite, "items", item, "defects.json"), defects)
        paths = {
            "suite": suite,
            "findings": os.path.join(self.temp, "findings.jsonl"),
            "assignments": os.path.join(self.temp, "assignments.jsonl"),
            "issues": os.path.join(self.temp, "issues.jsonl"),
            "audit": os.path.join(self.temp, "matched-audit.jsonl"),
            "outcomes": os.path.join(self.temp, "outcomes.jsonl"),
            "out_dir": os.path.join(self.temp, "rescore-out"),
        }
        write_jsonl(paths["findings"], rescore_case.FINDINGS)
        write_jsonl(paths["assignments"], rescore_case.ASSIGNMENTS)
        write_jsonl(paths["issues"], rescore_case.ISSUES)
        write_jsonl(paths["audit"], rescore_case.MATCHED_AUDIT)
        write_jsonl(paths["outcomes"], [rescore_case.OUTCOME_HEADER, *rescore_case.OUTCOMES])
        return paths

    def rescore_args(self, paths, out_dir=None, by_arm=None):
        argv = ["rescore", "--suite", paths["suite"], "--findings", paths["findings"],
                "--assignments", paths["assignments"], "--issues", paths["issues"],
                "--matched-audit", paths["audit"], "--outcomes", paths["outcomes"],
                "--resamples", "20", "--out-dir", out_dir or paths["out_dir"]]
        if by_arm:
            argv += ["--by-arm", by_arm]
        return argv

    def test_rescore_applies_extended_adjudication_and_writes_scored_outcomes(self):
        paths = self.make_rescore_inputs()
        code, _out, err = self.run_main(self.rescore_args(paths))
        self.assertEqual(code, 0, err)
        with open(os.path.join(paths["out_dir"], "per-run.jsonl"), encoding="utf-8") as stream:
            scored = [json.loads(line) for line in stream if line.strip()]
        planted = next(row for row in scored if row["item"] == "001")
        self.assertEqual((planted["tp_planted"], planted["tp_real"], planted["duplicate"], planted["false_alarm"]),
                         (2, 2, 1, 1))
        self.assertEqual(planted["real_found"], 2)
        self.assertTrue(planted["usable_v2"])
        self.assertEqual(scored[1]["item"], "002")
        self.assertTrue(scored[1]["usable_v2"])
        with open(os.path.join(paths["out_dir"], "outcomes-v2.jsonl"), encoding="utf-8") as stream:
            outcomes = [json.loads(line) for line in stream if line.strip()]
        self.assertEqual(outcomes[0]["type"], "header")
        added = ("finding_count", "tp_planted", "tp_real", "duplicate", "false_alarm", "usable_v2", "real_found")
        per_run_by_key = {(row["arm"], row["item"]): row for row in scored}
        for outcome in outcomes[1:]:
            per_run = per_run_by_key[(outcome["arm"], outcome["item"])]
            self.assertEqual({key: outcome[key] for key in added}, {key: per_run[key] for key in added})
        self.assertTrue(os.path.isfile(os.path.join(paths["out_dir"], "by-arm-v2.md")))
        self.assertTrue(os.path.isfile(os.path.join(paths["out_dir"], "cheapest.md")))
        self.assertTrue(os.path.isfile(os.path.join(paths["out_dir"], "key-v2", "001.json")))
        self.assertFalse(os.path.exists(os.path.join(paths["out_dir"], "REPORT.md")))
        self.assertFalse(os.path.exists(os.path.join(paths["out_dir"], "rescore.log")))

    def test_rescore_v1_gate_names_arm_and_metric_on_mismatch(self):
        paths = self.make_rescore_inputs()
        by_arm = os.path.join(self.temp, "wrong-by-arm.json")
        write_json(by_arm, {"rows": [{"arms": ["luna-low"], "lane": "luna", "model": "fixture-model",
                                       "effort": "low", "recall": 0.0, "precision": 1 / 3}]})
        code, _out, err = self.run_main(self.rescore_args(paths, by_arm=by_arm))
        self.assertNotEqual(code, 0)
        self.assertIn("luna-low", err)
        self.assertIn("recall", err)

    def test_export_findings_uses_suite_kind_and_salvages_lenient_format_fail(self):
        suite = os.path.join(self.temp, "export-suite")
        for item, defects in rescore_case.ITEM_DEFECTS.items():
            write_json(os.path.join(suite, "items", item, "defects.json"), defects)
        write_text(os.path.join(suite, "runs", "luna-low", "001", "findings.jsonl"),
                   json.dumps({"file": "src/a.py", "line": 10, "severity": "high", "description": "strict match"}) + "\n")
        write_text(os.path.join(suite, "runs", "luna-low", "002", "findings.jsonl"),
                   json.dumps({"file": "src/a.py", "line": 2, "severity": "low", "description": "salvaged row"}) +
                   "\nnot-json\n")
        items = bench.load_suite(suite).load_items()
        summary = bench.aggregate(items, os.path.join(suite, "runs"), ["luna-low"], 5)
        summary_path = os.path.join(self.temp, "grade-summary.json")
        write_json(summary_path, summary)
        output_path = os.path.join(self.temp, "findings-export.jsonl")
        code, _out, err = self.run_main(["export-findings", "--suite", suite, "--summary", summary_path,
                                         "--arm", "luna-low", "--out", output_path])
        self.assertEqual(code, 0, err)
        with open(output_path, encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream if line.strip()]
        self.assertEqual(len(rows), 2)
        self.assertEqual(set(rows[0]), {"fid", "arm", "lane", "effort", "rep", "item", "kind", "finding_index",
                                        "file", "line", "severity", "description", "matched_defect", "strict"})
        self.assertEqual((rows[0]["fid"], rows[0]["kind"], rows[0]["finding_index"], rows[0]["matched_defect"], rows[0]["strict"]),
                         ("luna-low:001:0", "planted", 0, "001:D1", True))
        self.assertEqual((rows[1]["fid"], rows[1]["kind"], rows[1]["finding_index"], rows[1]["strict"]),
                         ("luna-low:002:0", "control", 0, False))
        self.assertEqual(rows[1]["severity"], "low")
        self.assertEqual(rows[1]["description"], "salvaged row")

    def make_priors_outcomes(self, path, include_v2=True):
        header = dict(rescore_case.OUTCOME_HEADER)
        rows = []
        for item in ("001", "002"):
            planted = item == "001"
            row = {"type": "outcome", "arm": "luna-low", "lane": "luna", "model": "fixture-model",
                   "effort": "low", "rep": 1, "provider": "codex", "item": item,
                   "kind": "planted" if planted else "control",
                   "defects_found": ["001:D1"] if planted else [],
                   "defects_missed": ["001:D2"] if planted else [],
                   "lenient_found": ["001:D1"] if planted else [], "lenient_missed": ["001:D2"] if planted else [],
                   "matched_findings": 1 if planted else 0, "unmatched_findings": 0,
                   "lenient_matched_findings": 1 if planted else 0, "lenient_unmatched_findings": 0,
                   "status": "complete", "lane_exit": "0", "lane_exit_present": True,
                   "findings_present": True, "format_fail": False, "run_present": True,
                   "skipped": False, "infra_failure": False, "tokens": 100, "input_tokens": 50,
                   "cached_tokens": 0, "output_tokens": 50, "cost": 1.0, "cost_unit": "credits",
                   "pct_week": 0.1, "pct_5h": None, "wall_s": 1.0, "verdict": "OK"}
            if include_v2:
                row["usable_v2"] = not planted
            rows.append(row)
        write_jsonl(path, [header, *rows])

    def test_priors_v2_uses_usable_v2_and_rejects_missing_fields(self):
        outcomes = os.path.join(self.temp, "priors-v2.jsonl")
        self.make_priors_outcomes(outcomes)
        code, stdout, err = self.run_main(["priors", "--outcomes", outcomes, "--score", "v2", "--min-items", "1"])
        self.assertEqual(code, 0, err)
        row = json.loads(stdout)["arms"][0]
        self.assertEqual(row["measured"]["review"]["usable"], 0.5)
        code, stdout_v1, err = self.run_main(["priors", "--outcomes", outcomes, "--min-items", "1"])
        self.assertEqual(code, 0, err)
        row_v1 = json.loads(stdout_v1)["arms"][0]
        self.assertEqual(row_v1["measured"]["review"]["usable"], 1.0)
        missing = os.path.join(self.temp, "priors-no-v2.jsonl")
        self.make_priors_outcomes(missing, include_v2=False)
        code, _out, err = self.run_main(["priors", "--outcomes", missing, "--score", "v2", "--min-items", "1"])
        self.assertNotEqual(code, 0)
        self.assertIn("luna-low/001", err)
        self.assertIn("usable_v2", err)
        code, _out, err = self.run_main(["priors", "--suite", os.path.join(self.temp, "suite"), "--score", "v2"])
        self.assertNotEqual(code, 0)
        self.assertIn("requires --outcomes", err)


class StatsMathTests(unittest.TestCase):
    def test_wilson_closed_forms(self):
        # 0 of 10: upper bound is z^2/(n+z^2) = 3.841459/13.841459 = 0.277533; lower bound is 0.
        low, high = bench.wilson(0, 10)
        self.assertAlmostEqual(low, 0.0, places=9)
        self.assertAlmostEqual(high, 0.277533, places=5)
        # 10 of 10 mirrors it: [1 - 0.277533, 1] = [0.722467, 1].
        low, high = bench.wilson(10, 10)
        self.assertAlmostEqual(low, 0.722467, places=5)
        self.assertAlmostEqual(high, 1.0, places=9)
        # 5 of 10: centre 0.5; half-width 1.959964 * sqrt(0.025 + 0.0096037) / 1.3841459 = 0.263407.
        low, high = bench.wilson(5, 10)
        self.assertAlmostEqual(low, 0.236593, places=4)
        self.assertAlmostEqual(high, 0.763407, places=4)
        self.assertEqual(bench.wilson(0, 0), (None, None))

    def test_mcnemar_exact_two_sided(self):
        # 1 vs 6 discordant: n=7, P(X<=1) = (1 + 7) / 128 = 0.0625, doubled = 0.125.
        self.assertAlmostEqual(bench.mcnemar_exact(1, 6), 0.125)
        # 0 vs 5: P(X<=0) = 1/32, doubled = 0.0625.
        self.assertAlmostEqual(bench.mcnemar_exact(0, 5), 0.0625)
        # 3 vs 3: the tail is 0.65625, doubled is above one, so it is capped at 1.
        self.assertEqual(bench.mcnemar_exact(3, 3), 1.0)
        self.assertEqual(bench.mcnemar_exact(0, 0), 1.0)

    def test_ranks_average_ties(self):
        self.assertEqual(bench.ranks([5, 6, 7, 8, 7]), [1.0, 2.0, 3.5, 5.0, 3.5])

    def test_spearman_hand_value_with_ties(self):
        # ranks of y = [1, 2, 3.5, 5, 3.5]; Sxy = 8, Sxx = 10, Syy = 9.5; rho = 8 / sqrt(95) = 0.820783.
        self.assertAlmostEqual(bench.spearman([1, 2, 3, 4, 5], [5, 6, 7, 8, 7]), 8 / (95 ** 0.5))
        self.assertAlmostEqual(bench.spearman([1, 2, 3], [3, 2, 1]), -1.0)
        self.assertIsNone(bench.spearman([1, 2], [1, 2]))
        self.assertIsNone(bench.spearman([1, 2, 3], [4, 4, 4]))

    def test_cohen_kappa_hand_values(self):
        # A=[1,1,0,0], B=[1,0,1,0]: agreement 0.5, chance 0.5, kappa 0.
        self.assertAlmostEqual(bench.cohen_kappa([True, True, False, False], [True, False, True, False]), 0.0)
        self.assertAlmostEqual(bench.cohen_kappa([True, True, False, False], [True, True, False, False]), 1.0)
        # Complementary vectors: agreement 0, chance 0.5, kappa -1.
        self.assertAlmostEqual(bench.cohen_kappa([True, False, True, False], [False, True, False, True]), -1.0)

    def test_percentile_interpolates(self):
        values = list(range(1, 11))
        # position 0.9 * 9 = 8.1: between 9 and 10, so 9.1.
        self.assertAlmostEqual(bench.percentile(values, 0.9), 9.1)
        self.assertAlmostEqual(bench.percentile(values, 0.5), 5.5)
        self.assertIsNone(bench.percentile([], 0.5))

    def test_bootstrap_is_deterministic_and_bounded(self):
        pairs = [(1, 1), (0, 1), (1, 1), (0, 1)]
        first = bench.bootstrap_recall(pairs)
        self.assertEqual(first, bench.bootstrap_recall(pairs))
        self.assertLessEqual(first[0], 0.5)
        self.assertGreaterEqual(first[1], 0.5)
        self.assertEqual(bench.bootstrap_recall([(1, 1), (1, 1)]), (1.0, 1.0))
        self.assertEqual(bench.bootstrap_recall([]), (None, None))


class GateTests(BenchCase):
    def write_pids(self, relative, limit, current):
        directory = os.path.join(self.cgroup_root, relative) if relative else self.cgroup_root
        write_text(os.path.join(directory, "pids.max"), limit + "\n")
        write_text(os.path.join(directory, "pids.current"), current + "\n")

    def set_fake_codex_status(self, readings, after_refresh=None):
        status_bin = os.path.join(self.temp, "bin", "fake-usage-status")
        shutil.copyfile(os.path.join(FIXTURES, "fake_usage_status.sh"), status_bin)
        os.chmod(status_bin, 0o755)
        sequence = os.path.join(self.temp, "codex-status-sequence.jsonl")
        rows = []
        for value in readings:
            rows.append({} if value is None else {"codex": {"seven_day": {"used_percent": value}}})
        write_text(sequence, "".join(json.dumps(row) + "\n" for row in rows))
        index = os.path.join(self.temp, "codex-status-index")
        refresh_log = os.path.join(self.temp, "codex-refresh.log")
        refresh_env_log = os.path.join(self.temp, "codex-refresh-env.log")
        flag = os.path.join(self.temp, "codex-refreshed")
        write_text(index, "0\n")
        write_text(refresh_log, "")
        write_text(refresh_env_log, "")
        env = {
            "LANE_BENCH_USAGE_STATUS": status_bin,
            "LANE_BENCH_FAKE_STATUS_SEQUENCE": sequence,
            "LANE_BENCH_FAKE_STATUS_INDEX": index,
            "LANE_BENCH_FAKE_REFRESH_LOG": refresh_log,
            "LANE_BENCH_FAKE_REFRESH_ENV_LOG": refresh_env_log,
            "LANE_BENCH_FAKE_STATUS_AFTER_REFRESH_FLAG": flag if after_refresh is not None else "",
            "LANE_BENCH_FAKE_STATUS_AFTER_REFRESH_VALUE": json.dumps(
                {} if after_refresh is None else {"codex": {"seven_day": {"used_percent": after_refresh}}}),
        }
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        return refresh_log, refresh_env_log

    def codex_job(self, mode="skip", wait_max_h=0, name="luna-high"):
        suite = bench.load_suite(self.copy_suite(), need_brief=True)
        ctx = {"suite": suite, "meters": bench.Meters(os.environ["LANE_BENCH_USAGE_STATUS"], "claude"),
               "launcher": bench.Launcher(), "ledger": os.path.join(self.temp, "ledger"),
               "lane_bin": os.environ["LANE_BENCH_LANE"], "timeout": 60,
               "claude_5h": 75, "claude_7d": 65, "codex_7d": 96, "codex_at_limit": mode,
               "codex_wait_max_h": wait_max_h, "approved": "unit test"}
        job = bench.Job({"lane": "luna", "effort": "high", "model": None}, name, "001",
                        os.path.join(suite.runs_root, name, "001"))
        return ctx, job

    @staticmethod
    def file_lines(path):
        return read_text(path).splitlines()

    def test_headroom_is_the_smallest_finite_level(self):
        root, proc = make_cgroup(self.temp, "/user.slice/user-1.slice/session-1.scope", [
            ("", "max", "0"), ("user.slice", "1024", "300"), ("user.slice/user-1.slice", "1000", "880"),
            ("user.slice/user-1.slice/session-1.scope", "max", "5")])
        self.assertEqual(bench.task_headroom(proc, root), 120)

    def test_headroom_unknown_without_a_proc_cgroup_file(self):
        self.assertIsNone(bench.task_headroom(os.path.join(self.temp, "missing"), self.cgroup_root))

    def test_reserve_by_lane(self):
        self.assertEqual(bench.reserve_for("luna"), 150)
        self.assertEqual(bench.reserve_for("astra"), 150)
        self.assertEqual(bench.reserve_for("terra"), 150)
        self.assertEqual(bench.reserve_for("gemini"), 40)
        self.assertEqual(bench.reserve_for("haiku"), 40)

    def test_launch_waits_for_reserve_then_launches(self):
        root, proc = make_cgroup(self.temp, "/user.slice/user-1.slice/session-1.scope", [
            ("user.slice/user-1.slice", "1000", "880"), ("user.slice/user-1.slice/session-1.scope", "max", "5")])
        with mock.patch.dict(os.environ, {"LANES_PROC_CGROUP": proc, "LANES_CGROUP_ROOT": root}):
            def freed(_seconds):
                write_text(os.path.join(root, "user.slice/user-1.slice/pids.current"), "100\n")
            self.clock.on_sleep = freed
            started = []
            bench.Launcher().launch("luna", lambda: started.append("luna") or "process")
        self.assertEqual(self.clock.sleeps, [bench.HEADROOM_POLL_S])
        self.assertEqual(started, ["luna"])

    def test_launch_is_spaced_six_seconds_apart(self):
        launcher = bench.Launcher()
        launcher.launch("gemini", lambda: "first")
        launcher.launch("gemini", lambda: "second")
        self.assertEqual(self.clock.sleeps, [bench.LAUNCH_GAP_S])

    def test_claude_gate_waits_for_the_five_hour_ceiling(self):
        write_text(self.usage_file, json.dumps({"claude": {"age_seconds": 30, "reading": {
            "five_hour": {"used_percentage": 80.0}, "seven_day": {"used_percentage": 20.0}}}}))

        def cooled(_seconds):
            write_text(self.usage_file, json.dumps({"claude": {"age_seconds": 30, "reading": {
                "five_hour": {"used_percentage": 40.0}, "seven_day": {"used_percentage": 20.0}}}}))
        self.clock.on_sleep = cooled
        bench.wait_for_claude(bench.Meters(os.environ["LANE_BENCH_USAGE_STATUS"], os.environ["LANE_BENCH_CLAUDE"]),
                              75, 65)
        self.assertEqual(self.clock.sleeps, [bench.CLAUDE_STEP_S])

    def test_claude_reading_uses_fresh_stream_when_status_is_stale(self):
        write_text(self.usage_file, json.dumps({"claude": {"age_seconds": 900, "reading": {}}}))
        meters = bench.Meters(os.environ["LANE_BENCH_USAGE_STATUS"], os.environ["LANE_BENCH_CLAUDE"])
        reading = meters.claude_reading()
        # The last rate_limit_event in the stream wins: 0.42 and 0.10 become percentages.
        self.assertAlmostEqual(reading[0], 42.0)
        self.assertAlmostEqual(reading[1], 10.0)

    def test_claude_reading_is_shared_for_120_seconds(self):
        write_text(self.usage_file, json.dumps({"claude": {"age_seconds": 900, "reading": {}}}))
        meters = bench.Meters(os.environ["LANE_BENCH_USAGE_STATUS"], os.environ["LANE_BENCH_CLAUDE"])
        meters.claude_reading()
        meters.claude_reading()
        with open(self.claude_calls, encoding="utf-8") as stream:
            self.assertEqual(stream.read().count("call"), 1)
        self.clock.now += 121
        meters.claude_reading()
        with open(self.claude_calls, encoding="utf-8") as stream:
            self.assertEqual(stream.read().count("call"), 2)

    def test_codex_weekly_ceiling_skips_the_item_with_exit_75(self):
        write_text(self.usage_file, json.dumps({"codex": {"seven_day": {"used_percent": 97.0}}}))
        suite = bench.load_suite(self.copy_suite(), need_brief=True)
        ctx = {"suite": suite, "meters": bench.Meters(os.environ["LANE_BENCH_USAGE_STATUS"], "claude"),
               "launcher": bench.Launcher(), "ledger": os.path.join(self.temp, "ledger"),
               "lane_bin": os.environ["LANE_BENCH_LANE"], "timeout": 60,
               "claude_5h": 75, "claude_7d": 65, "codex_7d": 96}
        workspace = os.path.join(suite.runs_root, "luna-high", "001")
        job = bench.Job({"lane": "luna", "effort": "high", "model": None}, "luna-high", "001", workspace)
        ok, message = bench.execute(ctx, job)
        self.assertFalse(ok)
        self.assertIn("skipped", message)
        with open(os.path.join(workspace, "lane.exit"), encoding="utf-8") as stream:
            self.assertEqual(stream.read().strip(), "75")
        self.assertEqual(bench.read_json(os.path.join(workspace, "run.json"))["skipped"], "codex weekly")
        self.assertEqual(self.lane_calls(), [])

    def test_codex_skip_refreshes_stale_high_reading_before_running(self):
        refresh_log, refresh_env_log = self.set_fake_codex_status([97, 50])
        ctx, job = self.codex_job()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            ok, _ = bench.execute(ctx, job)
        self.assertTrue(ok)
        self.assertEqual(self.file_lines(refresh_log), ["refresh"])
        self.assertEqual(self.file_lines(refresh_env_log), ["40"])
        self.assertEqual(len(self.lane_calls()), 1)
        self.assertIn("codex gate mode skip", err.getvalue())

    def test_codex_skip_uses_the_refreshed_reading_at_the_ceiling(self):
        refresh_log, _ = self.set_fake_codex_status([97, 96])
        ctx, job = self.codex_job()
        ok, message = bench.execute(ctx, job)
        self.assertFalse(ok)
        self.assertIn("after refresh", message)
        self.assertEqual(self.file_lines(refresh_log), ["refresh"])
        record = bench.read_json(os.path.join(job.workspace, "run.json"))
        self.assertEqual(record["skip_reason"], "codex weekly window at or over 96% after refresh")
        self.assertEqual(self.lane_calls(), [])

    def test_codex_wait_refreshes_two_high_readings_then_runs(self):
        refresh_log, _ = self.set_fake_codex_status([97, 98, 50])
        ctx, job = self.codex_job(mode="wait")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            ok, _ = bench.execute(ctx, job)
        self.assertTrue(ok)
        self.assertEqual(self.clock.sleeps, [bench.CODEX_STEP_S])
        self.assertEqual(self.file_lines(refresh_log), ["refresh", "refresh"])
        self.assertIn("codex gate mode wait", err.getvalue())

    def test_codex_wait_treats_missing_reading_as_at_the_ceiling(self):
        refresh_log, _ = self.set_fake_codex_status([None, None, 50])
        ctx, job = self.codex_job(mode="wait")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            ok, _ = bench.execute(ctx, job)
        self.assertTrue(ok)
        self.assertIn("codex gate: weekly unknown; waiting for the weekly reset or a redeemed reset credit", err.getvalue())
        self.assertEqual(self.clock.sleeps, [bench.CODEX_STEP_S])
        self.assertEqual(self.file_lines(refresh_log), ["refresh", "refresh"])

    def test_codex_wait_max_turns_a_long_wait_into_a_recorded_skip(self):
        refresh_log, _ = self.set_fake_codex_status([98] * 8)
        suite_dir = self.copy_suite()
        code, _, err = self.run_main(["run", "--suite", suite_dir, "--arm", "luna:high", "--items", "001",
                                      "--approved", "unit test", "--no-grade", "--codex-at-limit", "wait",
                                      "--codex-wait-max-h", "0.0001"])
        self.assertEqual(code, 1)
        self.assertIn("codex wait exceeded --codex-wait-max-h", err)
        self.assertEqual(self.clock.sleeps, [bench.CODEX_STEP_S])
        self.assertEqual(self.file_lines(refresh_log), ["refresh"])
        record = bench.read_json(os.path.join(suite_dir, "runs", "luna-high", "001", "run.json"))
        self.assertEqual(record["codex_at_limit"], "wait")
        self.assertIn("codex wait exceeded", record["skip_reason"])
        self.assertEqual(record["codex_wait_max_h"], 0.0001)

    def test_codex_under_ceiling_does_not_refresh(self):
        refresh_log, _ = self.set_fake_codex_status([50])
        ctx, job = self.codex_job()
        ok, _ = bench.execute(ctx, job)
        self.assertTrue(ok)
        self.assertEqual(self.file_lines(refresh_log), [])

    def test_concurrent_codex_waiters_share_one_refresh(self):
        refresh_log, _ = self.set_fake_codex_status([98] * 8, after_refresh=50)
        suite = bench.load_suite(self.copy_suite(), need_brief=True)
        ctx = {"suite": suite, "meters": bench.Meters(os.environ["LANE_BENCH_USAGE_STATUS"], "claude"),
               "launcher": bench.Launcher(), "ledger": os.path.join(self.temp, "ledger"),
               "lane_bin": os.environ["LANE_BENCH_LANE"], "timeout": 60,
               "claude_5h": 75, "claude_7d": 65, "codex_7d": 96, "codex_at_limit": "wait",
               "codex_wait_max_h": 0, "approved": "unit test"}
        jobs = [bench.Job({"lane": "luna", "effort": "high", "model": None}, "luna-high", item,
                          os.path.join(suite.runs_root, "luna-high", item)) for item in ("001", "002")]
        start = threading.Barrier(len(jobs) + 1)
        results = []

        def run(job):
            start.wait()
            results.append(bench.execute(ctx, job))

        threads = [threading.Thread(target=run, args=(job,)) for job in jobs]
        for thread in threads:
            thread.start()
        start.wait()
        for thread in threads:
            thread.join()
        self.assertEqual(len(results), 2)
        self.assertTrue(all(ok for ok, _ in results), repr(results))
        self.assertEqual(self.file_lines(refresh_log), ["refresh"])


class RolloutTests(BenchCase):
    def setUp(self):
        super().setUp()
        self.pricing = bench.load_pricing(os.path.join(FIXTURES, "arms.json"))

    def test_backfill_uses_the_last_token_count_and_rate_card(self):
        rollouts = bench.Rollouts(os.environ["CODEX_HOME"], self.pricing)
        # Last total 1000 input, 600 cached, 200 output: (400 * 2.5 + 600 * 0.25 + 200 * 12.5) / 1e6 = 0.00365.
        self.assertAlmostEqual(rollouts.credits("sid-luna-001", "2026-10-19T10:00:00Z", "luna"), 0.00365, places=9)

    def test_narrow_date_window_falls_back_to_the_full_glob(self):
        rollouts = bench.Rollouts(os.environ["CODEX_HOME"], self.pricing)
        # The file sits in 2026/09/01, outside the run's date folders: 2000 * 2.5 + 100 * 12.5 = 6250 / 1e6.
        self.assertAlmostEqual(rollouts.credits("sid-luna-009", "2026-10-19T10:00:00Z", "luna"), 0.00625, places=9)

    def test_missing_or_unsafe_session_gives_no_credits(self):
        rollouts = bench.Rollouts(os.environ["CODEX_HOME"], self.pricing)
        self.assertIsNone(rollouts.credits("sid-absent", "2026-10-19T10:00:00Z", "luna"))
        self.assertIsNone(rollouts.credits("../escape", "2026-10-19T10:00:00Z", "luna"))
        self.assertIsNone(rollouts.credits(None, "2026-10-19T10:00:00Z", "luna"))

    def test_read_rollout_returns_model_and_totals_only(self):
        usage, model = bench.read_rollout(os.path.join(
            FIXTURES, "codex_home", "sessions", "2026", "10", "19", "rollout-2026-10-19T10-00-00-sid-luna-001.jsonl"))
        self.assertEqual(usage, {"input": 1000, "cached": 600, "output": 200})
        self.assertEqual(model, "gpt-6-luna")


class ArmAndSuiteTests(BenchCase):
    def test_suite_defaults_without_suite_json(self):
        suite_dir = self.copy_suite()
        os.remove(os.path.join(suite_dir, "suite.json"))
        suite = bench.load_suite(suite_dir, need_brief=True)
        self.assertEqual((suite.name, suite.cls, suite.window), ("suite", "review", 5))

    def test_brief_without_placeholder_is_rejected(self):
        suite_dir = self.copy_suite()
        write_text(os.path.join(suite_dir, "review_brief.md"), "no placeholder here\n")
        with self.assertRaises(bench.BenchError):
            bench.load_suite(suite_dir, need_brief=True)

    def test_arm_names_round_trip_with_models_and_reps(self):
        arm = bench.parse_arm_spec("glm:high:z-ai/glm-5.3-flash")
        name = bench.arm_name(arm)
        self.assertEqual(name, "glm-high-z-ai__glm-5.3-flash")
        parsed = bench.parse_arm_name(name)
        self.assertEqual((parsed["lane"], parsed["effort"], parsed["model"], parsed["rep"]),
                         ("glm", "high", "z-ai/glm-5.3-flash", 1))
        self.assertEqual(bench.arm_name(bench.parse_arm_spec("luna:high"), 2), "luna-high-r2")
        self.assertEqual(bench.parse_arm_name("luna-high-r2")["rep"], 2)
        self.assertEqual(bench.parse_arm_name("haiku-low-claude-haiku-5-5")["model"], "claude-haiku-5-5")

    def test_bad_effort_and_duplicate_arms_are_rejected(self):
        with self.assertRaises(bench.BenchError):
            bench.parse_arm_spec("luna:extreme")
        spec = os.path.join(self.temp, "arms.txt")
        write_text(spec, "luna:high\n# a comment line\nluna:high  # duplicate\n")
        with self.assertRaises(bench.BenchError):
            bench.read_arm_specs(None, spec)

    def test_arms_file_strips_comments_and_blank_lines(self):
        spec = os.path.join(self.temp, "arms.txt")
        write_text(spec, "# header\n\nluna:high  # trailing\nhaiku:low:claude-haiku-5-5\n")
        arms = bench.read_arm_specs(None, spec)
        self.assertEqual([bench.arm_name(a) for a in arms], ["luna-high", "haiku-low-claude-haiku-5-5"])

    def test_run_rejects_unknown_items_before_launching(self):
        suite_dir = self.copy_suite()
        code, _, err = self.run_main(["run", "--approved", "test, now", "--suite", suite_dir, "--arm", "luna:high", "--items", "001,999"])
        self.assertEqual(code, 2)
        self.assertIn("unknown item 999", err)
        self.assertEqual(self.lane_calls(), [])

    def test_run_without_approval_exits_2_leaves_nothing_and_never_calls_the_lane(self):
        suite_dir = self.copy_suite()
        before = sorted(os.listdir(suite_dir))
        for approval in ([], ["--approved", ""], ["--approved", "  \t "]):
            code, out, err = self.run_main(["run", "--suite", suite_dir, "--arm", "luna:high"] + approval)
            self.assertEqual(code, 2)
            self.assertEqual(out, "")
            self.assertIn("lane-bench run is a capability test: it spends window on items nobody needs. "
                          "Run it only after the user approves it, and pass --approved \"<who, when>\".", err)
        self.assertEqual(self.lane_calls(), [])
        self.assertEqual(sorted(os.listdir(suite_dir)), before)
        self.assertFalse(os.path.exists(os.path.join(suite_dir, "runs")))
        self.assertFalse(os.path.exists(os.environ["LANES_STATE"]))
        self.assertFalse(os.path.exists(self.claude_calls))

    def test_run_with_approval_records_the_note_but_export_does_not_carry_it(self):
        suite_dir = self.copy_suite()
        note = "the user, 2026-10-20 09:00"
        code, _, err = self.run_main(["run", "--suite", suite_dir, "--arm", "luna:high", "--no-grade",
                                      "--approved", f"  {note}  "])
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.lane_calls()), 3)
        for item in ("001", "002", "003"):
            run = bench.read_json(os.path.join(suite_dir, "runs", "luna-high", item, "run.json"))
            self.assertEqual(run["approved"], note)
        outcomes = os.path.join(self.temp, "outcomes.jsonl")
        code, _, err = self.run_main(["export", "--suite", suite_dir, "--arm", "luna-high",
                                      "--arms-json", os.path.join(FIXTURES, "arms.json"), "--out", outcomes])
        self.assertEqual(code, 0, err)
        self.assertNotIn("approved", read_text(outcomes))
        self.assertNotIn(note, read_text(outcomes))

    def test_priors_write_keeps_other_fields_and_adds_no_prior_keys(self):
        existing = {"arms": [{"lane": "luna", "model": "gpt-6-luna", "effort": "high", "status": "manual",
                              "reason": "keep me", "measured": {"hard": {"n": 4}}}]}
        merged = bench.merge_measured(existing, {("luna", "gpt-6-luna", "high"): {"review": {"n": 9}}})
        arm = merged["arms"][0]
        self.assertEqual(arm["status"], "manual")
        self.assertEqual(arm["reason"], "keep me")
        self.assertEqual(arm["measured"], {"hard": {"n": 4}, "review": {"n": 9}})
        self.assertNotIn("prior_pct", json.dumps(merged))


class CompareTests(unittest.TestCase):
    def test_disagreement_needs_opposite_order_and_disjoint_intervals(self):
        points = [("a", 60, 0.2, (0.1, 0.3), "a"), ("b", 40, 0.9, (0.8, 0.95), "b")]
        flips = bench.disagreements(points, "aa_index")
        self.assertEqual(len(flips), 1)
        self.assertEqual(flips[0]["arms"], ["a", "b"])
        # Overlapping intervals are not a disagreement, even when the orders are opposite.
        overlapping = [("a", 60, 0.2, (0.1, 0.5), "a"), ("b", 40, 0.9, (0.3, 0.95), "b")]
        self.assertEqual(bench.disagreements(overlapping, "aa_index"), [])
        # Agreeing orders are never flagged.
        agreeing = [("a", 60, 0.9, (0.8, 0.95), "a"), ("b", 40, 0.2, (0.1, 0.3), "b")]
        self.assertEqual(bench.disagreements(agreeing, "aa_index"), [])

    def test_public_rows_are_grouped_by_entry(self):
        temp = tempfile.mkdtemp(prefix="lane-bench-public-")
        self.addCleanup(shutil.rmtree, temp, True)
        path = os.path.join(temp, "public.json")
        rows = [{"lane": "sol", "model": "gpt-6.1-sol", "effort": "xhigh", "metric": "aa_index", "value": 63,
                 "source": "fixture", "date": "2026-10-17", "url": None},
                {"lane": "sol", "model": "gpt-6.1-sol", "effort": "xhigh", "metric": "usd_per_task", "value": 1.04,
                 "source": "fixture", "date": "2026-10-17", "url": None}]
        write_text(path, json.dumps(rows))
        entries = bench.load_public(path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["metrics"], {"aa_index": 63.0, "usd_per_task": 1.04})


class PoolingTests(unittest.TestCase):
    def make_row(self, name, lane, effort, rep, recall, cost, provider, partial=False):
        found = round(recall * 3)
        return {"arm": name, "lane": lane, "model": {"luna": "gpt-6-luna", "sol": "gpt-6.1-sol",
                "haiku": "claude-haiku-5-5", "fable": "claude-fable"}[lane], "effort": effort,
                "rep": rep, "provider": provider, "partial": partial, "defects_found": found,
                "defects_total": 3, "recall": found / 3, "recall_wilson": [0.1, 0.9],
                "usable": {"items": 2, "rate": 2 / 3}, "matched_findings": found,
                "unmatched_findings": 1, "format_fail": 0, "cost_per_item": {"mean": cost},
                "pct_week_per_item": {"mean": cost * 2}, "pct_5h_per_item": {"mean": cost * 3},
                "completed": 3, "plan": "plus"}

    def fixture_rows(self):
        return {
            "luna-high": self.make_row("luna-high", "luna", "high", 1, 1 / 3, 0.01, "codex"),
            "luna-high-r2": self.make_row("luna-high-r2", "luna", "high", 2, 2 / 3, 0.02, "codex"),
            "sol-high": self.make_row("sol-high", "sol", "high", 1, 2 / 3, 0.03, "codex"),
            "haiku-low": self.make_row("haiku-low", "haiku", "low", 1, 1, 0.04, "claude"),
            "fable-low": self.make_row("fable-low", "fable", "low", 1, 1, 0.99, "claude", partial=True),
        }

    def test_partial_and_replicates_pool_before_frontiers_and_curves(self):
        rows = self.fixture_rows()
        pooled = bench.pool_rows(rows, 3)
        luna = next(row for row in pooled if row["lane"] == "luna")
        self.assertEqual(luna["arms"], ["luna-high", "luna-high-r2"])
        self.assertEqual(luna["reps"], 2)
        self.assertEqual(luna["items"], 6)
        self.assertEqual(luna["completed"], 6)
        self.assertAlmostEqual(luna["recall"], 0.5)
        self.assertFalse(any(row["lane"] == "fable" for row in pooled))
        pricing = {"providers": {"codex": {"scarcity": 100}, "claude": {"scarcity": 0.01}}}
        frontier = bench.pareto(pooled, pricing)
        self.assertNotIn("fable-low", json.dumps(frontier))
        self.assertEqual(set(frontier["by_provider"]), {"claude", "codex"})
        self.assertEqual(frontier["by_provider"]["claude"], ["haiku-low"])
        self.assertEqual(frontier["by_provider"]["codex"], ["luna-high, luna-high-r2", "sol-high"])
        self.assertEqual(frontier["cost_points"], ["haiku-low"])
        luna_curve = next(curve for curve in bench.effort_curves(pooled) if curve["lane"] == "luna")
        self.assertEqual(luna_curve["efforts"][2]["reps"], 2)
        self.assertTrue(any(pair["replicate"] == "luna-high-r2"
                            for pair in bench.replicate_pairs({"per_defect_hit_matrix": {"d": {
                                "luna-high": True, "luna-high-r2": False}}}, rows)))

    def test_compare_uses_distinct_pooled_points_and_cost_agreement(self):
        rows = self.fixture_rows()
        items = ["001", "002", "003"]
        collected = {"rows": rows, "items": items, "pricing": {
            "windows": {"codex": {"usd_per_credit": 100.0}},
            "providers": {"codex": {"usd_per_credit": 1.0}}}}
        suite = type("Suite", (), {"name": "fixture"})()
        output = tempfile.mkdtemp(prefix="lane-bench-pool-compare-")
        self.addCleanup(shutil.rmtree, output, True)
        args = type("Args", (), {"suite": "fixture", "ledger": None, "arms_json": None,
                                  "codex_home": None, "arm": None,
                                  "public": os.path.join(FIXTURES, "compare_public_cost.json"),
                                  "results_dir": output})()
        with mock.patch.object(bench, "load_suite", return_value=suite), \
                mock.patch.object(bench, "collect", return_value=collected):
            self.assertEqual(bench.cmd_compare(args), 0)
        result = bench.read_json(os.path.join(output, "compare.json"))
        self.assertEqual(result["metrics"]["aa_ii_score"]["spearman_recall"]["n"], 3)
        self.assertEqual(result["metrics"]["aa_cai_index"]["spearman_recall"]["n"], 3)
        self.assertIn("aa_ii_cost_per_task_usd", result["cost_agreement"])
        self.assertEqual(result["cost_agreement"]["aa_ii_cost_per_task_usd"]["spearman_usd_per_item"]["n"], 3)
        self.assertAlmostEqual(result["cost_agreement"]["aa_ii_cost_per_task_usd"]["median_public_to_ours"],
                               20 / 3)
        self.assertNotIn("fable-low", json.dumps(result["metrics"]))
        self.assertFalse(result["public"].startswith("/"))
        markdown = read_text(os.path.join(output, "compare.md"))
        self.assertNotRegex(markdown, r"(?:Public numbers: |\()/(?:home|mnt|tmp)/")
        self.assertIn("fable-low (partial)", markdown)

    def test_model_run_through_another_lane_takes_its_own_5h_weight(self):
        weights = {"haiku": 1.72, "sonnet": 1, "opus": 0.95, "fable": 2.06}
        self.assertEqual(bench.claude_family("opus", "claude-fable-5-1", weights), "fable")
        self.assertEqual(bench.claude_family("opus", None, weights), "opus")
        self.assertEqual(bench.claude_family("sonnet", "claude-sonnet-5-5", weights), "sonnet")

    def test_model_run_through_another_lane_matches_its_own_public_rows(self):
        fable = {"lane": "opus", "model": "claude-fable-5-1", "effort": "high"}
        self.assertTrue(bench.entry_matches({"lane": "fable", "effort": "high"}, fable))
        self.assertFalse(bench.entry_matches({"lane": "opus", "effort": "high"}, fable))
        self.assertTrue(bench.entry_matches({"lane": "sol", "effort": None}, {"lane": "sol", "model": None, "effort": "low"}))

    def test_priors_use_one_complete_pooled_block(self):
        collected = {"rows": self.fixture_rows(), "items": ["001", "002", "003"]}
        suite = type("Suite", (), {"name": "fixture", "cls": "review"})()
        args = type("Args", (), {"suite": "fixture", "ledger": None,
                                  "arms_json": os.path.join(FIXTURES, "arms.json"),
                                  "codex_home": None, "min_items": 1, "write": None})()
        output, error = io.StringIO(), io.StringIO()
        with mock.patch.object(bench, "load_suite", return_value=suite), \
                mock.patch.object(bench, "collect", return_value=collected), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            self.assertEqual(bench.cmd_priors(args), 0)
        arms = json.loads(output.getvalue())["arms"]
        luna = next(row for row in arms if row["lane"] == "luna")
        self.assertEqual(luna["measured"]["review"]["n"], 6)
        self.assertAlmostEqual(luna["measured"]["review"]["recall"], 0.5)
        self.assertNotIn("fable", json.dumps(arms))

    def panel_row(self, name, lane, model, rep, unmatched, pct_week, provider="codex"):
        return {"arm": name, "lane": lane, "model": model, "effort": "high", "rep": rep,
                "provider": provider, "partial": False, "defects_found": 1, "defects_total": 2,
                "recall": 0.5, "recall_wilson": [0.1, 0.9], "usable": {"items": 2, "rate": 1.0},
                "matched_findings": 1, "unmatched_findings": unmatched, "format_fail": 0,
                "cost_per_item": {"mean": pct_week}, "pct_week_per_item": {"mean": pct_week},
                "pct_5h_per_item": None, "completed": 2, "plan": None}

    def test_panels_two_arm_arithmetic(self):
        rows = {"luna-high": self.panel_row("luna-high", "luna", "gpt-6-luna", 1, 1, 2.0),
                "haiku-high": self.panel_row("haiku-high", "haiku", "claude-haiku", 1, 2, 5.0, "claude")}
        collected = {"items": {"001": [{"id": "D1"}, {"id": "D2"}], "002": []},
                     "rows": rows, "pricing": {"providers": {"codex": {"scarcity": 3},
                                                                    "claude": {"scarcity": 2}}},
                     "agg": {"per_defect_hit_matrix": {
                         "001:D1": {"luna-high": True, "haiku-high": False},
                         "001:D2": {"luna-high": False, "haiku-high": True}}}}
        report = bench.build_panels(collected, "fixture")
        pair = next(panel for panel in report["panels"] if panel["size"] == 2)
        # Each arm finds one of two defects, so union recall is 2/2; false alarms are (1+2)/2 items = 1.5;
        # picker costs are (2% * scarcity 3) + (5% * scarcity 2) = 16 cost points per item.
        self.assertEqual(pair["union_recall"], 1.0)
        self.assertEqual(pair["false_alarms_per_item"], 1.5)
        self.assertEqual(pair["cost_points_per_item"], 16.0)
        self.assertEqual(pair["weekly_share_by_provider"], {"claude": 5.0, "codex": 2.0})
        self.assertIn(r"luna\|gpt-6-luna\|high", bench.panels_markdown(report))

    def test_panels_average_every_replicate_combination(self):
        rows = {
            "luna-high": self.panel_row("luna-high", "luna", "gpt-6-luna", 1, 0, 1.0),
            "luna-high-r2": self.panel_row("luna-high-r2", "luna", "gpt-6-luna", 2, 0, 1.0),
            "sol-high": self.panel_row("sol-high", "sol", "gpt-6.1-sol", 1, 0, 1.0),
        }
        collected = {"items": {"001": [{"id": "D1"}], "002": [{"id": "D2"}]},
                     "rows": rows, "pricing": {"providers": {"codex": {"scarcity": 1}}},
                     "agg": {"per_defect_hit_matrix": {
                         "001:D1": {"luna-high": True, "luna-high-r2": False, "sol-high": True},
                         "002:D2": {"luna-high": False, "luna-high-r2": True, "sol-high": False}}}}
        report = bench.build_panels(collected, "fixture")
        pair = next(panel for panel in report["panels"] if panel["size"] == 2 and
                    "luna|gpt-6-luna|high" in panel["members"])
        # The two replicate combinations cover 1/2 and 2/2 defects; their exact mean is 0.75.
        self.assertEqual(pair["union_recall"], 0.75)


class ReplicateTests(BenchCase):
    """A hand-made outcomes file: items 001 (D1 D2), 002 (D3 D4) and a control 003; defects numbered 1-4.

    Found by arm:        luna-high {1,2}   luna-high-r2 {1,2,3}   luna-high-r3 {1,4}   haiku-high {3,4}
    Unmatched findings (001, 002, 003): luna r1 1+0+1, r2 0+1+0, r3 1+1+1; haiku 1+1+1.   %week/item: luna 1.0, haiku 0.5.
    Scarcity: codex 2, claude 1, so cost points are luna 2.0, haiku 0.5.
    """
    FOUND = {"luna-high": {"001:D1", "001:D2"}, "luna-high-r2": {"001:D1", "001:D2", "002:D3"},
             "luna-high-r3": {"001:D1", "002:D4"}, "haiku-high": {"002:D3", "002:D4"}}
    UNMATCHED = {"luna-high": (1, 0, 1), "luna-high-r2": (0, 1, 0), "luna-high-r3": (1, 1, 1), "haiku-high": (1, 1, 1)}
    DEFECTS = {"001": ["001:D1", "001:D2"], "002": ["002:D3", "002:D4"], "003": []}

    def write_fixture(self):
        names = list(self.FOUND)
        header = {"type": "header", "schema_version": 1, "suite": "fixture", "class": "review", "window": 5,
                  "item_count": 3, "total_defects": 4, "planted_items": ["001", "002"], "control_items": ["003"],
                  "item_defect_ids": {item: [defect.split(":")[1] for defect in defects]
                                      for item, defects in self.DEFECTS.items()}, "arms": names}
        lines = [json.dumps(header)]
        for name in names:
            lane = name.split("-")[0]
            rep = int(name.rsplit("-r", 1)[1]) if "-r" in name else 1
            for index, (item, defects) in enumerate(self.DEFECTS.items()):
                found = sorted(self.FOUND[name] & set(defects))
                missed = sorted(set(defects) - set(found))
                unmatched = self.UNMATCHED[name][index]
                lines.append(json.dumps({
                    "type": "outcome", "arm": name, "lane": lane,
                    "model": "gpt-6-luna" if lane == "luna" else "claude-haiku-5-5", "effort": "high", "rep": rep,
                    "provider": "codex" if lane == "luna" else "claude", "plan": None, "stats_plan": None,
                    "item": item, "kind": "planted" if defects else "control",
                    "defects_found": found, "defects_missed": missed, "lenient_found": found, "lenient_missed": missed,
                    "matched_findings": len(found), "unmatched_findings": unmatched,
                    "lenient_matched_findings": len(found), "lenient_unmatched_findings": unmatched,
                    "status": "complete", "lane_exit": "0", "lane_exit_present": True, "findings_present": True,
                    "format_fail": False, "run_present": True, "skipped": False, "infra_failure": False,
                    "input_tokens": 1, "cached_tokens": 0, "output_tokens": 1, "tokens": 2, "cost": 1.0,
                    "cost_unit": "credits", "pct_week": 1.0 if lane == "luna" else 0.5, "pct_5h": None,
                    "wall_s": 10.0, "verdict": "OK"}))
        outcomes = os.path.join(self.temp, "outcomes.jsonl")
        write_text(outcomes, "\n".join(lines) + "\n")
        arms = os.path.join(self.temp, "arms.json")
        write_text(arms, json.dumps({"providers": {"codex": {"scarcity": 2}, "claude": {"scarcity": 1}}}))
        return outcomes, arms

    def collected(self):
        outcomes, arms = self.write_fixture()
        return bench.collected_from_outcomes(outcomes, arms)

    def test_spread_of_a_three_rep_arm(self):
        report = bench.build_replicates(self.collected(), "fixture", 2)
        # Only luna has two or more reps; haiku has one.
        self.assertEqual([row["key"] for row in report["spread"]], ["luna|gpt-6-luna|high"])
        row = report["spread"][0]
        self.assertEqual(row["reps"], [1, 2, 3])
        # Recall by rep is 2/4, 3/4, 2/4, so the mean is 7/12. Deviations are -1/12, +2/12, -1/12, whose squares
        # sum to 6/144; over n-1 = 2 that is 1/48, and the sample SD is sqrt(1/48) = 0.144338.
        self.assertEqual(row["recall_by_rep"], [0.5, 0.75, 0.5])
        self.assertAlmostEqual(row["mean_recall"], 7 / 12)
        self.assertAlmostEqual(row["sd_recall"], math.sqrt(1 / 48))
        self.assertEqual((row["min_recall"], row["max_recall"]), (0.5, 0.75))
        # Unmatched findings are 2 + 1 + 3 = 6 over 3 items x 3 reps = 2/3 per item.
        self.assertAlmostEqual(row["false_alarms_per_item"], 2 / 3)
        # Every rep finds D1 only ({1,2} & {1,2,3} & {1,4}); some rep finds all four: 1/4.
        self.assertEqual((row["found_by_every_rep"], row["found_by_any_rep"]), (1, 4))
        self.assertEqual(row["stable_share"], 0.25)
        # Pair unions: {1,2,3}=3/4, {1,2,4}=3/4, {1,2,3,4}=4/4; their mean is 5/6 and the gain over 7/12 is 1/4.
        self.assertAlmostEqual(row["self_pair_recall"], 5 / 6)
        self.assertAlmostEqual(row["self_pair_gain"], 0.25)
        # With haiku {3,4} the unions are 4/4, 4/4, 3/4, mean 11/12; the gain over 7/12 is 1/3, so a second
        # luna run adds 1/4 - 1/3 = -1/12 relative to the partner.
        self.assertEqual(row["best_partner"]["partner"], "haiku|claude-haiku-5-5|high")
        self.assertAlmostEqual(row["best_partner"]["pair_recall"], 11 / 12)
        self.assertAlmostEqual(row["best_partner"]["pair_gain"], 1 / 3)
        self.assertAlmostEqual(row["self_gain_minus_partner_gain"], -1 / 12)

    def test_holdout_scores_a_member_with_held_out_reps_and_flags_one_without(self):
        collected = self.collected()
        holdout = bench.build_replicates(collected, "fixture", 2)["holdout"]
        self.assertEqual((holdout["training_reps"], holdout["heldout_reps"]), ([1, 2], [3]))
        by_members = {tuple(panel["members"]): panel for panel in holdout["panels"]}
        haiku, luna = "haiku|claude-haiku-5-5|high", "luna|gpt-6-luna|high"
        # Training costs are haiku 0.5, luna 2.0, pair 2.5 and each beats the recall before it, so all three are
        # on the frontier; the pair is also the only panel that reaches 0.95, 0.97 and 1.00 (size 2).
        self.assertEqual(list(by_members), [(haiku,), (luna,), (haiku, luna)])
        self.assertEqual(by_members[(haiku, luna)]["roles"], ["frontier", "target 0.95 size 2",
                                                              "target 0.97 size 2", "target 1.00 size 2"])
        # Haiku has no rep past 2: it keeps its training row, is flagged, and scores identically.
        single = by_members[(haiku,)]
        self.assertFalse(single["has_heldout_member"])
        self.assertEqual((single["in_sample_recall"], single["heldout_recall"], single["difference"]), (0.5, 0.5, 0.0))
        # Luna trains on r1 {1,2} and r2 {1,2,3}: recall (2/4 + 3/4) / 2 = 0.625, 3 unmatched over 6 item-runs = 0.5.
        # Held out it is r3 {1,4} alone: 0.5, with 3 unmatched over 3 items = 1.0.
        solo = by_members[(luna,)]
        self.assertEqual((solo["in_sample_recall"], solo["heldout_recall"], solo["difference"]), (0.625, 0.5, -0.125))
        self.assertEqual((solo["in_sample_false_alarms_per_item"], solo["heldout_false_alarms_per_item"]), (0.5, 1.0))
        # The pair trains at (4/4 + 4/4) / 2 = 1.0 (haiku {3,4} completes r1 and r2) and holds out at
        # {1,4} + {3,4} = 3/4. False alarms: 0.5 + 1.0 = 1.5 in sample, 1.0 + 1.0 = 2.0 held out.
        pair = by_members[(haiku, luna)]
        self.assertEqual([(detail["key"], detail["heldout"], detail["reps_used"]) for detail in pair["member_detail"]],
                         [(haiku, False, [1]), (luna, True, [3])])
        self.assertEqual((pair["in_sample_recall"], pair["heldout_recall"], pair["difference"]), (1.0, 0.75, -0.25))
        self.assertEqual((pair["in_sample_false_alarms_per_item"], pair["heldout_false_alarms_per_item"]), (1.5, 2.0))
        # Two panels have a held-out member, with differences -0.125 and -0.25.
        self.assertEqual(holdout["panels_with_heldout_member"], 2)
        self.assertAlmostEqual(holdout["mean_difference"], -0.1875)
        for target in ("0.95", "0.97", "1.00"):
            block = holdout["targets"][target]
            self.assertEqual([size for size, entry in block["by_size"].items() if entry], ["2"])
            self.assertEqual(block["pick"]["members"], [haiku, luna])
            self.assertTrue(block["pick"]["meets_in_sample"])
            self.assertFalse(block["pick"]["meets_heldout"])
        # With every rep in the training set nothing is held out, so no panel is tested.
        untested = bench.build_replicates(collected, "fixture", 3)["holdout"]
        self.assertEqual((untested["heldout_reps"], untested["panels_with_heldout_member"],
                          untested["mean_difference"]), ([], 0, None))
        self.assertTrue(all(panel["difference"] == 0.0 and not panel["has_heldout_member"]
                            for panel in untested["panels"]))

    def test_command_output_is_deterministic_and_carries_no_paths(self):
        outcomes, arms = self.write_fixture()
        first, second = os.path.join(self.temp, "first"), os.path.join(self.temp, "second")
        for output in (first, second):
            code, out, err = self.run_main(["replicates", "--outcomes", outcomes, "--arms-json", arms,
                                            "--out-dir", output])
            self.assertEqual((code, err), (0, ""))
        self.assertIn("REPLICATES 1 pooled arms with at least 2 reps; 3 hold-out panels", out)
        for name in ("replicates.json", "replicates.md"):
            self.assertEqual(read_text(os.path.join(first, name)), read_text(os.path.join(second, name)))
        text = read_text(os.path.join(first, "replicates.json"))
        self.assertEqual(text, json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n")
        markdown = read_text(os.path.join(first, "replicates.md"))
        self.assertIn(r"luna\|gpt-6-luna\|high", markdown)
        self.assertIn("0.144", markdown)
        self.assertNotIn(self.temp, text + markdown)
        # A later hold-out rep changes the numbers, so the rep split is a real input.
        other = os.path.join(self.temp, "other")
        self.assertEqual(self.run_main(["replicates", "--outcomes", outcomes, "--arms-json", arms,
                                        "--holdout-max-rep", "1", "--out-dir", other])[0], 0)
        self.assertNotEqual(read_text(os.path.join(other, "replicates.json")), text)


class SummaryTests(BenchCase):
    """Items 001 (D1 D2), 002 (D3 D4) and a control 003.

    luna-high x2 (codex, pooled), haiku-high (claude), and opus-max-claude-fable-5-1 (claude, ran item 001 only).
    The catalog also lists a luna fallback with effort "*", a retired sol max and a gemini arm nobody ran.
    """
    FOUND = {"luna-high": {"001:D1", "001:D2"}, "luna-high-r2": {"001:D1", "002:D3"}, "haiku-high": {"002:D3", "002:D4"},
             "opus-max-claude-fable-5-1": {"001:D1"}}
    DEFECTS = {"001": ["001:D1", "001:D2"], "002": ["002:D3", "002:D4"], "003": []}
    IDENTITY = {"luna": ("luna", "gpt-6-luna", "codex", "credits"), "haiku": ("haiku", "claude-haiku-5-5", "claude", "list_usd"),
                "opus": ("opus", "claude-fable-5-1", "claude", "list_usd")}

    def write_fixture(self):
        names = list(self.FOUND)
        header = {"type": "header", "schema_version": 1, "suite": "fixture", "class": "review", "window": 5,
                  "item_count": 3, "total_defects": 4, "planted_items": ["001", "002"], "control_items": ["003"],
                  "item_defect_ids": {item: [defect.split(":")[1] for defect in defects]
                                      for item, defects in self.DEFECTS.items()}, "arms": names}
        lines = [json.dumps(header)]
        for name in names:
            lane, model, provider, unit = self.IDENTITY[name.split("-")[0]]
            rep = int(name.rsplit("-r", 1)[1]) if name.endswith(("-r2", "-r3")) else 1
            effort = name.split("-")[1]
            for item, defects in self.DEFECTS.items():
                ran = not (name.startswith("opus") and item != "001")
                found = sorted(self.FOUND[name] & set(defects)) if ran else []
                missed = sorted(set(defects) - set(found))
                unmatched = 1 if item == "003" and name.startswith("haiku") else 0
                lines.append(json.dumps({
                    "type": "outcome", "arm": name, "lane": lane, "model": model, "effort": effort, "rep": rep,
                    "provider": provider, "plan": None, "stats_plan": None, "item": item,
                    "kind": "planted" if defects else "control",
                    "defects_found": found, "defects_missed": missed, "lenient_found": found, "lenient_missed": missed,
                    "matched_findings": len(found), "unmatched_findings": unmatched,
                    "lenient_matched_findings": len(found), "lenient_unmatched_findings": unmatched,
                    "status": "complete" if ran else "missing", "lane_exit": "0" if ran else None,
                    "lane_exit_present": ran, "findings_present": ran, "format_fail": False, "run_present": ran,
                    "skipped": False, "infra_failure": False, "input_tokens": 1, "cached_tokens": 0,
                    "output_tokens": 1, "tokens": 100 if provider == "claude" else 40, "cost": 2.0 if provider == "claude" else 5.0,
                    "cost_unit": unit, "pct_week": 0.5 if provider == "claude" else 0.25,
                    "pct_5h": 4.0 if provider == "claude" else None, "wall_s": 10.0 + rep, "verdict": "OK"}))
        outcomes = os.path.join(self.temp, "outcomes.jsonl")
        write_text(outcomes, "\n".join(lines) + "\n")
        arms = os.path.join(self.temp, "arms.json")
        write_text(arms, json.dumps({"providers": {"codex": {"scarcity": 2, "usd_per_credit": 0.5}, "claude": {"scarcity": 1}},
                                     "arms": [
            {"lane": "luna", "model": "gpt-6-luna", "effort": "high", "status": "active", "classes": ["review"]},
            {"lane": "haiku", "model": "claude-haiku-5-5", "effort": "high", "status": "active", "classes": ["review"]},
            {"lane": "gemini", "model": "gemini-3.8-flash-low", "effort": "low", "status": "active", "classes": ["mechanical"]},
            {"lane": "sol", "model": "gpt-6.1-sol", "effort": "max", "status": "retired", "classes": [],
             "reason": "no gain over xhigh"},
            {"lane": "luna", "model": "gpt-5.6-luna", "effort": "*", "status": "manual", "classes": [],
             "reason": "fallback"}]}))
        public = os.path.join(self.temp, "public.json")

        def metric(lane, model, effort, name, value):
            return {"lane": lane, "model": model, "effort": effort, "metric": name, "value": value,
                    "source": "AA", "date": "2026-10-20", "url": "https://example.test/" + lane}
        write_text(public, json.dumps([
            metric("luna", "GPT-6 Luna", "high", "aa_ii_score", 40), metric("luna", "GPT-6 Luna", "high", "aa_ii_cost_per_task_usd", 0.9),
            metric("gemini", "Gemini", "low", "aa_ii_score", 12), metric("gemini", "Gemini", "low", "aa_cai_tb4_pct", 7.25),
            metric("fable", "Claude Fable 5.1", "max", "aa_cai_index", 71)]))
        return outcomes, arms, public

    def summarise(self, out_name="out"):
        outcomes, arms, public = self.write_fixture()
        output = os.path.join(self.temp, out_name)
        code, out, err = self.run_main(["summary", "--outcomes", outcomes, "--arms-json", arms, "--public", public,
                                        "--out-dir", output])
        self.assertEqual((code, err), (0, ""), out)
        return output, bench.read_json(os.path.join(output, "by-arm.json")), (outcomes, arms, public)

    def rows(self, report):
        return {(row["lane"], row["model"], row["effort"], row["status"]): row for row in report["rows"]}

    def test_pooled_values_equal_stats_for_every_pooled_arm(self):
        _, report, (outcomes, arms, _) = self.summarise()
        header, _ = bench.read_outcomes(outcomes)
        stats = bench.build_stats_report(bench.outcomes_suite(header, outcomes), bench.collected_from_outcomes(outcomes, arms))
        rows = self.rows(report)
        self.assertEqual(len(stats["pooled"]), 2)
        for pooled in stats["pooled"]:
            row = rows[(pooled["lane"], pooled["model"], pooled["effort"], "measured")]
            self.assertEqual(row["reps"], pooled["reps"])
            for key in ("recall", "usable", "precision", "format_fail", "cost_per_item", "pct_week_per_item",
                        "pct_5h_per_item"):
                self.assertEqual(row[key], pooled[key], key)
            self.assertEqual([row["wilson_lo"], row["wilson_hi"]], pooled["recall_wilson"])
        luna = rows[("luna", "gpt-6-luna", "high", "measured")]
        # Recall by run is 2/4 and 2/4; D1 is found by both and D1, D2, D3 by either: 1/3.
        self.assertEqual((luna["recall_min"], luna["recall_max"], luna["stable_share"]), (0.5, 0.5, 1 / 3))
        self.assertEqual((luna["items_run"], luna["suite_items"], luna["status"]), (6, 3, "measured"))
        self.assertEqual((luna["tokens_per_item"], luna["wall_median_s"], luna["cost_unit"]), (40, 11.5, "credits"))
        # 5.0 credits at the catalog's 0.5 $ per credit; 0.25 %week per item is 400 items a week.
        self.assertEqual((luna["cost_per_item"], luna["api_usd_per_item"], luna["items_per_week"]), (5.0, 2.5, 400))
        self.assertEqual(luna["pct_5h_per_item"], None)
        haiku = rows[("haiku", "claude-haiku-5-5", "high", "measured")]
        self.assertEqual((haiku["stable_share"], haiku["recall_min"], haiku["api_usd_per_item"], haiku["items_per_week"]),
                         (None, 0.5, 2.0, 200))
        self.assertEqual(haiku["fa_per_control_item"], 1.0)
        self.assertEqual(haiku["fa_per_planted_item"], 0.0)
        self.assertEqual((haiku["catalog"], haiku["classes"]), ("active", ["review"]))
        self.assertEqual(luna["public"]["aa_ii_score"], {"value": 40.0, "source": "AA", "date": "2026-10-20",
                                                         "url": "https://example.test/luna"})

    def test_catalog_only_arms_are_not_run_and_keep_their_public_numbers(self):
        _, report, _ = self.summarise()
        rows = self.rows(report)
        gemini = rows[("gemini", "gemini-3.8-flash-low", "low", "not run")]
        self.assertEqual((gemini["reps"], gemini["items_run"], gemini["recall"], gemini["tokens_per_item"]), (0, 0, None, None))
        self.assertEqual(gemini["public"]["aa_ii_score"]["value"], 12.0)
        self.assertEqual(gemini["public"]["aa_cai_tb4_pct"]["value"], 7.25)
        sol = rows[("sol", "gpt-6.1-sol", "max", "not run")]
        self.assertEqual((sol["catalog"], sol["retired_reason"]), ("retired", "no gain over xhigh"))
        self.assertEqual(rows[("luna", "gpt-5.6-luna", "*", "not run")]["catalog"], "manual")
        self.assertEqual(len(report["rows"]), 6)

    def test_partial_arm_is_flagged_and_keeps_its_per_arm_stats(self):
        output, report, (outcomes, arms, _) = self.summarise()
        partial = self.rows(report)[("opus", "claude-fable-5-1", "max", "partial")]
        self.assertEqual((partial["status_note"], partial["reps"], partial["items_run"], partial["catalog"]),
                         ("partial (1 of 3 items)", 1, 1, "absent"))
        header, _ = bench.read_outcomes(outcomes)
        row = bench.build_stats_report(bench.outcomes_suite(header, outcomes),
                                       bench.collected_from_outcomes(outcomes, arms))["arms"]["opus-max-claude-fable-5-1"]
        self.assertTrue(row["partial"])
        self.assertEqual((partial["recall"], partial["precision"], partial["usable"]),
                         (row["recall"], row["precision"], row["usable"]["rate"]))
        self.assertEqual([partial["wilson_lo"], partial["wilson_hi"]], row["recall_wilson"])
        self.assertEqual((partial["cost_per_item"], partial["pct_week_per_item"]),
                         (row["cost_per_item"]["mean"], row["pct_week_per_item"]["mean"]))
        # Public numbers match on the model family, as compare does: fable, not the opus lane.
        self.assertEqual(partial["public"]["aa_cai_index"]["value"], 71.0)
        self.assertIn("partial (1 of 3 items)", read_text(os.path.join(output, "by-arm.md")))
        # No pooled row absorbed it.
        self.assertEqual(sum(1 for r in report["rows"] if r["model"] == "claude-fable-5-1"), 1)

    def test_false_alarm_rates_use_completed_items_only(self):
        output, report, _ = self.summarise()
        rows = self.rows(report)
        partial = rows[("opus", "claude-fable-5-1", "max", "partial")]
        haiku = rows[("haiku", "claude-haiku-5-5", "high", "measured")]
        self.assertIsNone(partial["fa_per_control_item"])
        self.assertEqual(haiku["fa_per_control_item"], 1.0)
        markdown = read_text(os.path.join(output, "by-arm.md"))
        partial_row = next(line for line in markdown.splitlines()
                           if line.startswith("| opus | claude-fable-5-1 | max |"))
        self.assertEqual(partial_row.split("|")[11].strip(), "n/a")
        haiku_row = next(line for line in markdown.splitlines()
                         if line.startswith("| haiku | claude-haiku-5-5 | high |"))
        self.assertEqual(haiku_row.split("|")[11].strip(), "1.00")

    def test_output_is_byte_identical_ordered_and_carries_no_paths(self):
        first, report, _ = self.summarise("first")
        second, _, _ = self.summarise("second")
        for name in ("by-arm.json", "by-arm.md"):
            self.assertEqual(read_text(os.path.join(first, name)), read_text(os.path.join(second, name)))
        text = read_text(os.path.join(first, "by-arm.json")) + read_text(os.path.join(first, "by-arm.md"))
        self.assertNotIn(self.temp, text)
        # Claude, then codex, then gemini; within a provider by model, then effort.
        self.assertEqual([(r["lane"], r["model"], r["effort"]) for r in report["rows"]], [
            ("opus", "claude-fable-5-1", "max"), ("haiku", "claude-haiku-5-5", "high"),
            ("luna", "gpt-5.6-luna", "*"), ("luna", "gpt-6-luna", "high"), ("sol", "gpt-6.1-sol", "max"),
            ("gemini", "gemini-3.8-flash-low", "low")])
        markdown = read_text(os.path.join(first, "by-arm.md"))
        self.assertIn("Capability is this suite's review recall and precision; usage is what one item cost in the "
                      "provider's weekly window. Public columns are Artificial Analysis numbers from `public.json`.", markdown)
        self.assertIn("## Capability", markdown)
        self.assertIn("## Usage", markdown)
        self.assertIn("| gemini | gemini-3.8-flash-low | low | active | not run | n/a |", markdown)
        self.assertIn("| luna | gpt-6-luna | high | active | 2 | 0.50 [", markdown)


class EndToEndTests(BenchCase):
    def test_export_is_deidentified_and_stats_round_trips(self):
        suite_dir = self.copy_suite()
        self.run_main(["run", "--approved", "test, now", "--suite", suite_dir, "--arm", "luna:high", "--no-grade"])
        arms = os.path.join(FIXTURES, "arms.json")
        outcomes = os.path.join(self.temp, "outcomes.jsonl")
        code, _, err = self.run_main(["export", "--suite", suite_dir, "--arm", "luna-high",
                                      "--arms-json", arms, "--out", outcomes])
        self.assertEqual(code, 0, err)
        records = [json.loads(line) for line in read_text(outcomes).splitlines()]
        banned = {"description", "file", "line", "severity"}

        def check_value(value):
            if isinstance(value, dict):
                self.assertFalse(banned.intersection(value))
                for child in value.values():
                    check_value(child)
            elif isinstance(value, list):
                for child in value:
                    check_value(child)
            elif isinstance(value, str):
                self.assertNotIn("/", value, value)

        check_value(records)
        self.assertEqual(records[0]["type"], "header")
        self.assertEqual(len(records), 1 + 3)
        suite_stats, outcomes_stats = os.path.join(self.temp, "suite-stats"), os.path.join(self.temp, "outcomes-stats")
        self.assertEqual(self.run_main(["stats", "--suite", suite_dir, "--arm", "luna-high",
                                       "--arms-json", arms, "--results-dir", suite_stats])[0], 0)
        self.assertEqual(self.run_main(["stats", "--outcomes", outcomes, "--arms-json", arms,
                                       "--results-dir", outcomes_stats])[0], 0)
        self.assertEqual(bench.read_json(os.path.join(suite_stats, "stats.json")),
                         bench.read_json(os.path.join(outcomes_stats, "stats.json")))

    def test_exported_fast_failure_is_counted_once_as_an_infra_failure(self):
        # Item 001 is a fast failure with an exported infra_failure row. It is counted once: the value was 2 before
        # b389c8d, when the verdict check counted the same row a second time.
        defects = {"001": "1", "002": "2"}

        def row(item, **changes):
            missed = [f"{item}:{defects[item]}"]
            outcome = {"type": "outcome", "arm": "luna-high", "lane": "luna", "model": "gpt-6-luna", "effort": "high",
                       "rep": 1, "provider": "codex", "plan": None, "stats_plan": None, "item": item,
                       "kind": "planted", "defects_found": [], "defects_missed": missed, "lenient_found": [],
                       "lenient_missed": missed, "matched_findings": 0, "unmatched_findings": 0,
                       "lenient_matched_findings": 0, "lenient_unmatched_findings": 0, "status": "complete",
                       "lane_exit": "0", "lane_exit_present": True, "findings_present": True, "format_fail": False,
                       "run_present": True, "skipped": False, "infra_failure": False, "input_tokens": 1,
                       "cached_tokens": 0, "output_tokens": 1, "tokens": 2, "cost": 1.0, "cost_unit": "credits",
                       "pct_week": 1.0, "pct_5h": None, "wall_s": 10.0, "verdict": "OK"}
            outcome.update(changes)
            return json.dumps(outcome)

        header = {"type": "header", "schema_version": 1, "suite": "fixture", "class": "review", "window": 5,
                  "item_count": 2, "total_defects": 2, "planted_items": ["001", "002"], "control_items": [],
                  "item_defect_ids": {"001": ["1"], "002": ["2"]}, "arms": ["luna-high"]}
        failed = {"status": "failed", "lane_exit": "4", "lane_exit_present": True, "findings_present": False,
                  "infra_failure": True, "verdict": "FAILED", "wall_s": 5.0, "cost": None, "tokens": None,
                  "pct_week": None}
        outcomes = os.path.join(self.temp, "outcomes.jsonl")
        write_text(outcomes, "\n".join([json.dumps(header), row("001", **failed), row("002")]) + "\n")
        arms = os.path.join(self.temp, "arms.json")
        write_text(arms, json.dumps({"providers": {"codex": {"scarcity": 2}, "claude": {"scarcity": 1}}}))
        results = os.path.join(self.temp, "stats")
        self.assertEqual(self.run_main(["stats", "--outcomes", outcomes, "--arms-json", arms,
                                       "--results-dir", results])[0], 0)
        self.assertEqual(bench.read_json(os.path.join(results, "stats.json"))["arms"]["luna-high"]["infra_failures"], 1)

    def test_run_grade_stats_compare_priors(self):
        suite_dir = self.copy_suite()
        code, _, err = self.run_main(["run", "--approved", "test, now", "--suite", suite_dir, "--arm", "luna:high", "--arm", "haiku:low",
                                      "--par", "2", "--slots", "2"])
        # haiku-low/002 exits 1 in the fixture map, so the run reports failure but still grades.
        self.assertEqual(code, 1)
        self.assertIn("haiku-low 002 failed (exit 1)", err)
        runs = os.path.join(suite_dir, "runs")
        for item in ("001", "002", "003"):
            self.assertEqual(read_text(os.path.join(runs, "luna-high", item, "lane.exit")).strip(), "0")
        self.assertEqual(read_text(os.path.join(runs, "haiku-low", "002", "lane.exit")).strip(), "1")
        run_json = bench.read_json(os.path.join(runs, "luna-high", "001", "run.json"))
        self.assertEqual(set(run_json), {"lane_run_dir", "started_at", "ended_at", "exit", "approved"})
        self.assertEqual(run_json["approved"], "test, now")
        self.assertTrue(os.path.isdir(run_json["lane_run_dir"]))
        self.assertFalse(os.path.exists(os.path.join(runs, "luna-high", "001", "post", "src", "__pycache__")))
        brief = read_text(os.path.join(runs, "luna-high", "001", "review_brief.md"))
        self.assertIn(os.path.join(runs, "luna-high", "001"), brief)
        self.assertNotIn("{{ITEM_PATH}}", brief)
        calls = self.lane_calls()
        self.assertEqual(len(calls), 6)
        for call in calls:
            self.assertTrue(call["brief_rendered"])
            self.assertIn("--off-catalog", call["argv"])
            self.assertEqual(call["argv"][call["argv"].index("--tag") + 1], "bench-fixture")
        luna_call = next(c for c in calls if c["arm"] == "luna-high" and c["item"] == "001")
        self.assertNotIn("-m", luna_call["argv"])
        summary = bench.read_json(os.path.join(suite_dir, "results", "summary.json"))
        self.assertEqual(summary["total_defects"], 3)
        self.assertAlmostEqual(summary["arms"]["luna-high"]["recall"], 1 / 3)
        self.assertAlmostEqual(summary["arms"]["haiku-low"]["recall"], 1 / 3)

        code, _, _ = self.run_main(["stats", "--suite", suite_dir, "--arms-json", os.path.join(FIXTURES, "arms.json")])
        self.assertEqual(code, 0)
        stats = bench.read_json(os.path.join(suite_dir, "results", "stats.json"))
        luna = stats["arms"]["luna-high"]
        self.assertEqual((luna["items_run"], luna["completed"], luna["infra_failures"]), (3, 3, 0))
        self.assertEqual(luna["usable"]["items"], 2)
        self.assertAlmostEqual(luna["usable"]["rate"], 2 / 3)
        self.assertAlmostEqual(luna["precision"], 1 / 3)
        self.assertAlmostEqual(luna["false_alarms"]["planted"]["per_item"], 0.5)
        self.assertAlmostEqual(luna["false_alarms"]["control"]["per_item"], 1.0)
        self.assertEqual(luna["wall_s"]["median"], 42.0)
        self.assertAlmostEqual(luna["wall_s"]["p90"], 52.4)
        self.assertAlmostEqual(luna["tokens_per_item"]["mean"], (16459 + 9000 + 5000) / 3)
        # Two luna items have a rollout (0.00365 credits each); the third has none and is not averaged in.
        self.assertEqual(luna["cost_per_item"]["n"], 2)
        self.assertAlmostEqual(luna["cost_per_item"]["mean"], 0.00365, places=9)
        self.assertEqual(luna["cost_per_item"]["unit"], "credits")
        self.assertAlmostEqual(luna["pct_week_per_item"]["mean"], 0.00365 / 8400 * 100, places=9)
        haiku = stats["arms"]["haiku-low"]
        self.assertEqual((haiku["items_run"], haiku["completed"], haiku["infra_failures"]), (3, 2, 1))
        self.assertAlmostEqual(haiku["usable"]["rate"], 2 / 3)
        self.assertAlmostEqual(haiku["cost_per_item"]["mean"], 0.3)
        self.assertAlmostEqual(haiku["pct_week_per_item"]["mean"], 0.6 / 2 / 1525 * 100)
        self.assertAlmostEqual(haiku["pct_5h_per_item"]["mean"], (0.5 + 0.1) / 2 * 1.72 / 254 * 100)
        self.assertAlmostEqual(haiku["pct_week_per_defect"], (0.5 + 0.1) / 1525 * 100)
        self.assertEqual(haiku["model"], "claude-haiku-5-5")
        # luna is cheaper per week at equal recall (1/3), so haiku is dominated and only luna is on the frontier.
        self.assertEqual(stats["pareto"]["by_provider"], {"claude": ["haiku-low"], "codex": ["luna-high"]})
        self.assertEqual(stats["pareto"]["cost_points"], ["luna-high"])
        self.assertTrue(os.path.exists(os.path.join(suite_dir, "results", "stats.md")))

        public = os.path.join(self.temp, "public.json")
        write_text(public, json.dumps([
            {"lane": "luna", "model": "gpt-6-luna", "effort": "high", "metric": "aa_index", "value": 50,
             "source": "fixture", "date": "2026-10-17", "url": None},
            {"lane": "luna", "model": "gpt-6-luna", "effort": "high", "metric": "usd_per_task", "value": 0.2,
             "source": "fixture", "date": "2026-10-17", "url": None},
            {"lane": "haiku", "model": "claude-haiku-5-5", "effort": "low", "metric": "aa_index", "value": 40,
             "source": "fixture", "date": "2026-10-17", "url": None}]))
        code, _, _ = self.run_main(["compare", "--suite", suite_dir, "--public", public,
                                    "--arms-json", os.path.join(FIXTURES, "arms.json")])
        self.assertEqual(code, 0)
        compare = bench.read_json(os.path.join(suite_dir, "results", "compare.json"))
        matched = {row["arm"]: row["public_entry"] for row in compare["table"]}
        self.assertEqual(matched, {"haiku-low": "haiku low", "luna-high": "luna high"})
        self.assertIn("aa_index", compare["skipped_metrics"])
        self.assertNotIn("aa_index", compare["metrics"])
        self.assertTrue(os.path.exists(os.path.join(suite_dir, "results", "compare.md")))

        code, out, _ = self.run_main(["priors", "--suite", suite_dir, "--min-items", "2",
                                      "--arms-json", os.path.join(FIXTURES, "arms.json")])
        self.assertEqual(code, 0)
        priors = json.loads(out)["arms"]
        by_arm = {(p["lane"], p["effort"]): p for p in priors}
        self.assertEqual(by_arm[("luna", "high")]["measured"]["review"]["n"], 3)
        self.assertEqual(by_arm[("haiku", "low")]["measured"]["review"]["n"], 2)
        self.assertEqual(by_arm[("haiku", "low")]["measured"]["review"]["source"].split()[0], "bench-fixture")
        code, out, _ = self.run_main(["priors", "--suite", suite_dir, "--arms-json", os.path.join(FIXTURES, "arms.json")])
        self.assertEqual(json.loads(out)["arms"], [])

        local = os.path.join(self.temp, "arms.local.json")
        code, _, _ = self.run_main(["priors", "--suite", suite_dir, "--min-items", "2",
                                    "--arms-json", os.path.join(FIXTURES, "arms.json"), "--write", local])
        self.assertEqual(code, 0)
        written = bench.read_json(local)
        self.assertEqual(sorted((a["lane"], a["effort"]) for a in written["arms"]), [("haiku", "low"), ("luna", "high")])
        self.assertNotIn("prior_", read_text(local))

    def test_resume_moves_a_failed_workspace_aside_and_keeps_finished_runs(self):
        suite_dir = self.copy_suite()
        code, _, _ = self.run_main(["run", "--approved", "test, now", "--suite", suite_dir, "--arm", "luna:high", "--arm", "haiku:low",
                                    "--no-grade"])
        self.assertEqual(code, 1)
        code, _, err = self.run_main(["run", "--approved", "test, now", "--suite", suite_dir, "--arm", "luna:high", "--arm", "haiku:low",
                                      "--no-grade"])
        self.assertEqual(code, 2)
        self.assertIn("pass --resume", err)
        code, _, err = self.run_main(["run", "--approved", "test, now", "--suite", suite_dir, "--arm", "luna:high", "--arm", "haiku:low",
                                      "--no-grade", "--resume"])
        self.assertEqual(code, 1)
        failed = os.listdir(os.path.join(suite_dir, "failed_runs"))
        self.assertEqual(len([name for name in failed if name.startswith("haiku-low-002-")]), 1)
        self.assertEqual(read_text(os.path.join(suite_dir, "runs", "haiku-low", "002", "lane.exit")).strip(), "1")
        calls = self.lane_calls()
        self.assertEqual(sum(1 for c in calls if c["arm"] == "luna-high" and c["item"] == "001"), 1)
        self.assertEqual(sum(1 for c in calls if c["arm"] == "haiku-low" and c["item"] == "002"), 2)
        self.assertEqual(sum(1 for c in calls if c["arm"] == "haiku-low" and c["item"] == "001"), 1)

    def test_codex_weekly_ceiling_skips_every_luna_item(self):
        write_text(self.usage_file, json.dumps({"claude": {"age_seconds": 30, "reading": {
            "five_hour": {"used_percentage": 10.0}, "seven_day": {"used_percentage": 20.0}}},
            "codex": {"seven_day": {"used_percent": 99.0}}}))
        suite_dir = self.copy_suite()
        code, _, err = self.run_main(["run", "--approved", "test, now", "--suite", suite_dir, "--arm", "luna:high", "--no-grade"])
        self.assertEqual(code, 1)
        self.assertIn("skipped", err)
        self.assertEqual(self.lane_calls(), [])
        run = bench.read_json(os.path.join(suite_dir, "runs", "luna-high", "001", "run.json"))
        self.assertEqual(run["skipped"], "codex weekly")

    def test_grade_writes_to_results_dir_and_selftest_runs_from_cli(self):
        suite_dir = self.copy_suite()
        self.run_main(["run", "--approved", "test, now", "--suite", suite_dir, "--arm", "luna:high", "--no-grade"])
        other = os.path.join(self.temp, "elsewhere")
        code, out, _ = self.run_main(["grade", "--suite", suite_dir, "--results-dir", other])
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(os.path.join(other, "summary.json")))
        self.assertIn("GRADED 1 arms, 3 items, 3 defects", out)
        code, out, _ = self.run_main(["grade", "--selftest"])
        self.assertEqual(code, 0)
        self.assertIn("SELFTEST-OK", out)

    def test_suite_directory_is_never_written_by_stats_or_compare_outside_results(self):
        suite_dir = self.copy_suite()
        self.run_main(["run", "--approved", "test, now", "--suite", suite_dir, "--arm", "luna:high", "--no-grade"])
        before = sorted(os.listdir(suite_dir))
        smoke = os.path.join(self.temp, "smoke")
        self.run_main(["stats", "--suite", suite_dir, "--results-dir", smoke,
                       "--arms-json", os.path.join(FIXTURES, "arms.json")])
        self.assertTrue(os.path.exists(os.path.join(smoke, "stats.json")))
        self.assertEqual(sorted(os.listdir(suite_dir)), before)
        self.assertFalse(os.path.exists(os.path.join(suite_dir, "results")))

    def test_stats_and_compare_take_an_arm_filter(self):
        suite_dir = self.copy_suite()
        self.run_main(["run", "--approved", "test, now", "--suite", suite_dir, "--arm", "luna:high", "--arm", "haiku:low", "--no-grade"])
        filtered = os.path.join(self.temp, "filtered")
        code, _, _ = self.run_main(["stats", "--suite", suite_dir, "--arm", "luna-high", "--results-dir", filtered,
                                    "--arms-json", os.path.join(FIXTURES, "arms.json")])
        self.assertEqual(code, 0)
        self.assertEqual(list(bench.read_json(os.path.join(filtered, "stats.json"))["arms"]), ["luna-high"])
        code, _, err = self.run_main(["compare", "--suite", suite_dir, "--arm", "sol-high", "--results-dir", filtered])
        self.assertEqual(code, 2)
        self.assertIn("no such arm: sol-high", err)


class WindowsHarnessTests(unittest.TestCase):
    def test_grade_projection_matches_the_jq_query(self):
        data = {"arms": {
            "luna-low": {"items": {"001": {"defects_found": ["D1"], "defects_missed": [], "counts": {"defects_found": 1},
                                           "status": "ok", "lane_exit": 0, "findings_present": True,
                                           "findings": [{"description": "dropped"}]}}},
            "sol-low": {"items": {"002": {"lenient": {"defects_found": ["D2"], "extra": 1}, "status": "ok"}}}}}
        projected = bench.project_grade_summary(data, ["sol-low"])
        self.assertEqual(projected, {"arms": {"sol-low": {"items": {"002": {
            "defects_found": None, "defects_missed": None, "counts": None,
            "lenient": {"defects_found": ["D2"], "defects_missed": None, "counts": None},
            "status": "ok", "lane_exit": None, "findings_present": None}}}}})
        item = bench.project_grade_summary(data)["arms"]["luna-low"]["items"]["001"]
        self.assertNotIn("findings", item)
        self.assertEqual(item["lenient"], {"defects_found": None, "defects_missed": None, "counts": None})

    def test_findings_with_a_byte_order_mark_load(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "findings.jsonl")
            with open(path, "wb") as stream:
                stream.write(b'\xef\xbb\xbf{"file": "src/x.py", "line": 3, "severity": "high", "description": "bug"}\n')
            self.assertEqual(bench.load_findings(path)[0]["line"], 3)

    def test_codex_cost_totals_tokens_from_their_parts(self):
        meta = {"usage": {"credits": 0.5, "tokens": {"input": 95239, "cached_input": 81024, "output": 563,
                                                     "reasoning_output": 47}}}
        rollouts = mock.Mock()
        cost = bench.item_cost(meta, "terra", "codex", {"windows": {"codex": {"weekly_credits": 8400}}}, rollouts)
        self.assertEqual(cost["tokens"], 95802)
        self.assertEqual(cost["cached_tokens"], 81024)

    @unittest.skipUnless(os.name == "nt", "Windows only")
    def test_windows_launches_helpers_through_a_wrapper_or_interpreter(self):
        with tempfile.TemporaryDirectory() as root:
            script = os.path.join(root, "helper")
            write_text(script, "#!/usr/bin/env python3\nprint('hi')\n")
            self.assertEqual(bench.launch_argv([script, "--json"]), [sys.executable, script, "--json"])
            write_text(script + ".cmd", "@echo off\r\n")
            self.assertEqual(bench.launch_argv([script, "--json"]), [script + ".cmd", "--json"])
            self.assertEqual(bench.launch_argv([script + ".cmd"]), [script + ".cmd"])

    @unittest.skipIf(os.name == "nt", "POSIX only")
    def test_posix_launches_helpers_unchanged(self):
        self.assertEqual(bench.launch_argv(["/bin/true", "x"]), ["/bin/true", "x"])


if __name__ == "__main__":
    unittest.main()
