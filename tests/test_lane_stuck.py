"""The stuck-run guard on a process lane. Subagent and cloud runs are not covered."""

import argparse
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import textwrap
import time
import unittest
import uuid


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANE_PATH = os.path.join(ROOT, "bin", "lane")
loader = importlib.machinery.SourceFileLoader("lane_stuck_lane", LANE_PATH)
lane = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
loader.exec_module(lane)


def force_rmtree(path):
    def retry(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=retry)
    else:
        shutil.rmtree(path, onerror=retry)


def failure(command="python -m pytest", args=("-m", "pytest")):
    return {"program": "python", "args": tuple(args), "command": command, "ok": False}


class StuckTests(unittest.TestCase):
    def setUp(self):
        self.old_env = os.environ.copy()
        self.root = os.path.join(os.path.dirname(__file__), ".lane-stuck-{}-{}".format(os.getpid(), uuid.uuid4().hex))
        os.makedirs(self.root)
        self.addCleanup(force_rmtree, self.root)
        os.environ.pop("LANES_STUCK", None)
        os.environ.pop("LANES_STUCK_POLL", None)
        os.environ.pop("LANES_FACTS", None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old_env)

    def test_stuck_needs_both_time_limits_and_three_repeats_in_the_last_ten(self):
        repeated = [failure()] * 3
        self.assertIsNone(lane.run_is_stuck(2.5, 1, 1, repeated))
        self.assertIsNone(lane.run_is_stuck(3, 1, 3, repeated))
        self.assertEqual(lane.run_is_stuck(2.51, 1, 1, repeated), ("python -m pytest", 3))
        self.assertIsNone(lane.stuck_failure(repeated[:2]))
        older = repeated + [{"program": "git", "args": ("status",), "command": "git status", "ok": True}] * 10
        self.assertIsNone(lane.stuck_failure(older))
        spaced = []
        for _ in range(3):
            spaced.append(failure())
            spaced.append({"program": "git", "args": ("status",), "command": "git status", "ok": True})
        self.assertEqual(lane.stuck_failure(spaced), ("python -m pytest", 3))
        mixed = [failure(), failure(), failure(args=("other.py",), command="python other.py")]
        self.assertIsNone(lane.stuck_failure(mixed))
        self.assertIsNone(lane.run_is_stuck(100, None, 1, repeated))
        self.assertIsNone(lane.run_is_stuck(100, 1, None, repeated))

    def test_guard_is_off_without_an_eta_and_off_wins_over_the_kill_flag(self):
        opts = argparse.Namespace(stuck_kill=True, no_facts=False)
        os.environ["LANES_STUCK"] = "off"
        self.assertIsNone(lane.make_stuck_guard(opts, {}, "meta", "log", 10, 12))
        os.environ.pop("LANES_STUCK")
        self.assertIsNone(lane.make_stuck_guard(opts, {}, "meta", "log", None, 12))
        self.assertIsNone(lane.make_stuck_guard(opts, {}, "meta", "log", 10, None))
        guard = lane.make_stuck_guard(opts, {}, "meta", "log", 10, 12)
        self.assertEqual(guard["policy"], "kill")
        guard = lane.make_stuck_guard(argparse.Namespace(stuck_kill=False), {}, "meta", "log", 10, 12)
        self.assertEqual(guard["policy"], "warn")
        os.environ["LANES_STUCK"] = "maybe"
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            guard = lane.make_stuck_guard(argparse.Namespace(stuck_kill=True), {}, "meta", "log", 10, 12)
        self.assertEqual(guard["policy"], "warn")
        self.assertIn("not off or kill", stderr.getvalue())
        os.environ["LANES_STUCK_POLL"] = "nope"
        self.assertEqual(lane.stuck_poll_seconds(), 30.0)
        os.environ["LANES_STUCK_POLL"] = "0.25"
        self.assertEqual(lane.stuck_poll_seconds(), 0.25)

    def write_child(self):
        path = os.path.join(self.root, "child.py")
        with open(path, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(textwrap.dedent('''
                import json
                import sys
                import time
                sleep_s, marker = sys.argv[1], sys.argv[2]
                for index in range(3):
                    print(json.dumps({"type": "assistant", "message": {"content": [
                        {"type": "tool_use", "id": "t{}".format(index), "name": "Bash",
                         "input": {"command": "python -m pytest"}}]}}), flush=True)
                    print(json.dumps({"type": "user", "message": {"content": [
                        {"type": "tool_result", "tool_use_id": "t{}".format(index), "is_error": True,
                         "content": "fail"}]}}), flush=True)
                time.sleep(float(sleep_s))
                with open(marker, "w", encoding="utf-8") as handle:
                    handle.write("finished\\n")
            '''))
        return path

    def run_guard(self, policy, sleep_s):
        os.environ["LANES_STUCK_POLL"] = "0.2"
        script = self.write_child()
        marker = os.path.join(self.root, "finished-{}.txt".format(policy))
        log_path = os.path.join(self.root, "run-{}.log".format(policy))
        meta_path = os.path.join(self.root, "meta-{}.json".format(policy))
        meta = {"lane": "haiku"}
        guard = {"policy": policy, "meta": meta, "meta_path": meta_path, "log_path": log_path,
                 "eta_s": 0.3, "eta_p80_s": 0.3, "warned": False, "killed": False}
        stderr = io.StringIO()
        started = time.monotonic()
        with contextlib.redirect_stderr(stderr):
            code, timed_out, elapsed, _out, _err, _peak = lane.run_process(
                [sys.executable, script, str(sleep_s), marker], self.root, log_path, 30, None, guard=guard)
        return {"code": code, "timed_out": timed_out, "elapsed": elapsed, "wall": time.monotonic() - started,
                "stderr": stderr.getvalue(), "guard": guard, "meta": meta, "meta_path": meta_path,
                "marker": marker}

    def test_warn_once_and_keep_running(self):
        outcome = self.run_guard("warn", 3)
        self.assertEqual(outcome["stderr"].count("warning: stuck:"), 1, outcome["stderr"])
        self.assertIn("python -m pytest failed 3 times; elapsed ", outcome["stderr"])
        self.assertIn(" min against an ETA of ", outcome["stderr"])
        self.assertTrue(outcome["stderr"].rstrip().endswith(" min"))
        self.assertFalse(outcome["guard"]["killed"])
        self.assertFalse(outcome["timed_out"])
        self.assertEqual(outcome["code"], 0)
        self.assertTrue(os.path.isfile(outcome["marker"]))
        stuck = outcome["meta"]["stuck"]
        self.assertEqual(set(stuck), {"at", "command", "failures"})
        self.assertEqual(stuck["command"], "python -m pytest")
        self.assertEqual(stuck["failures"], 3)
        self.assertTrue(str(stuck["at"]).endswith("Z"))
        with open(outcome["meta_path"], "r", encoding="utf-8") as stream:
            self.assertEqual(json.load(stream)["stuck"], stuck)

    def test_kill_stops_the_worker_process_tree(self):
        outcome = self.run_guard("kill", 12)
        self.assertTrue(outcome["guard"]["killed"])
        self.assertFalse(outcome["timed_out"])
        self.assertNotEqual(outcome["code"], 0)
        self.assertNotEqual(outcome["code"], 124)
        self.assertLess(outcome["wall"], 8, outcome["stderr"])
        self.assertFalse(os.path.exists(outcome["marker"]))
        self.assertIn("warning: stuck:", outcome["stderr"])
        self.assertEqual(outcome["meta"]["stuck"]["failures"], 3)

    def test_lane_kill_switch_records_a_stuck_verdict(self):
        bin_dir = os.path.join(self.root, "bin")
        os.makedirs(bin_dir)
        script = os.path.join(bin_dir, "fake_claude.py")
        with open(script, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(textwrap.dedent('''
                import json
                import sys
                import time
                sys.stdin.read()
                for index in range(3):
                    print(json.dumps({"type": "assistant", "message": {"content": [
                        {"type": "tool_use", "id": "t{}".format(index), "name": "Bash",
                         "input": {"command": "python -m pytest"}}]}}), flush=True)
                    print(json.dumps({"type": "user", "message": {"content": [
                        {"type": "tool_result", "tool_use_id": "t{}".format(index), "is_error": True,
                         "content": "fail"}]}}), flush=True)
                time.sleep(15)
                print(json.dumps({"session_id": "sess-test", "is_error": False, "result": "done"}))
            '''))
        if os.name == "nt":
            launcher = os.path.join(bin_dir, "claude.cmd")
            with open(launcher, "w", encoding="utf-8", newline="\n") as stream:
                stream.write('@echo off\n"{}" "{}" %*\n'.format(sys.executable, script))
        else:
            launcher = os.path.join(bin_dir, "claude")
            with open(launcher, "w", encoding="utf-8", newline="\n") as stream:
                stream.write("#!/bin/sh\nexec {} {} \"$@\"\n".format(sys.executable, script))
            os.chmod(launcher, 0o755)
        eta = os.path.join(self.root, "fake-eta.py")
        with open(eta, "w", encoding="utf-8", newline="\n") as stream:
            stream.write('import json\nprint(json.dumps({"minutes": 0.02, "p80_minutes": 0.02, '
                         '"tier": "machine", "runs": {"machine": 1}}))\n')
        workspace = os.path.join(self.root, "workspace")
        os.makedirs(workspace)
        subprocess.run(["git", "init", workspace], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        brief = os.path.join(self.root, "brief.md")
        with open(brief, "w", encoding="utf-8", newline="\n") as stream:
            stream.write("Edit nothing.\n")
        outdir = os.path.join(self.root, "stuck-run")
        state = os.path.join(self.root, "state")
        env = dict(os.environ, LANES_STATE=state, LANE_NO_USAGE="1", LANES_MEM_CHECK="off", PYTHONUTF8="1",
                   PYTHONUNBUFFERED="1", LANES_CONFIG=os.path.join(self.root, "config"),
                   LANES_ARMS=os.path.join(ROOT, "arms.json"),
                   LANES_ARMS_LOCAL=os.path.join(self.root, "no-local-arms.json"),
                   LANES_CLAUDE_BIN=launcher, LANE_STATS=eta, LANES_STUCK="kill", LANES_STUCK_POLL="0.5",
                   GIT_CEILING_DIRECTORIES=self.root)
        env.pop("LANE_NO_ETA", None)
        env.pop("USAGE_OPTIMIZER_MODE", None)
        env.pop("LANES_FACTS", None)
        started = time.monotonic()
        result = subprocess.run([sys.executable, LANE_PATH, "haiku", "-C", workspace, "-b", brief, "-e", "xhigh",
                                 "--class", "mechanical", "--outdir", outdir],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
                                encoding="utf-8", errors="replace", timeout=25, check=False)
        wall = time.monotonic() - started
        self.assertLess(wall, 12, result.stdout + result.stderr)
        self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
        self.assertIn("verdict=STUCK", result.stdout)
        self.assertEqual(result.stderr.count("warning: stuck:"), 1, result.stderr)
        self.assertIn("python -m pytest failed 3 times", result.stderr)
        with open(os.path.join(outdir, "meta.json"), "r", encoding="utf-8") as stream:
            meta = json.load(stream)
        self.assertEqual(meta["verdict"], "STUCK")
        self.assertEqual(meta["exit_code"], 4)
        self.assertEqual(meta["stuck"]["command"], "python -m pytest")
        self.assertEqual(meta["stuck"]["failures"], 3)
        self.assertEqual(meta["facts_sent"], [])
        with open(os.path.join(state, "ledger.jsonl"), "r", encoding="utf-8") as stream:
            record = json.loads(stream.read().splitlines()[-1])
        self.assertEqual(record["verdict"], "STUCK")
        self.assertNotIn("stuck", record)
        self.assertNotIn("facts_sent", record)


if __name__ == "__main__":
    unittest.main()
