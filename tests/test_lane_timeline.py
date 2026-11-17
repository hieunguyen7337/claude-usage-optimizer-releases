"""lane-stats note and timeline. Everything runs on a temp state dir and a temp git repository; no network."""

import contextlib
import datetime
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import unittest
import uuid


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "bin", "lane-stats")
loader = importlib.machinery.SourceFileLoader("lane_timeline_stats", SCRIPT)
stats = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
loader.exec_module(stats)
UTC = datetime.timezone.utc


def force_rmtree(path):
    def retry(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=retry)
    else:
        shutil.rmtree(path, onerror=retry)


def stamp(delta_minutes):
    when = datetime.datetime.now(UTC).replace(microsecond=0) + datetime.timedelta(minutes=delta_minutes)
    return when.isoformat().replace("+00:00", "Z")


class TimelineTests(unittest.TestCase):
    def setUp(self):
        self.old_env = os.environ.copy()
        self.addCleanup(self.restore)
        self.root = os.path.join(os.path.dirname(__file__), ".lane-timeline-{}-{}".format(os.getpid(), uuid.uuid4().hex))
        os.makedirs(os.path.join(self.root, "state", "runs"))
        self.addCleanup(force_rmtree, self.root)
        self.state = os.path.join(self.root, "state")
        os.environ["LANES_STATE"] = self.state
        os.environ["PYTHONUTF8"] = "1"

    def restore(self):
        os.environ.clear()
        os.environ.update(self.old_env)

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = stats.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def events(self, *argv):
        code, out, err = self.run_cli("timeline", "--json", *argv)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def add_run(self, name, **fields):
        run_dir = os.path.join(self.state, "runs", name)
        os.makedirs(run_dir)
        meta = {"lane": "sonnet", "effort": "high", "class": "substantive", "verdict": "OK",
                "started_at": stamp(-30), "ended_at": stamp(-20), "duration_s": 600.0, "eta_s": 480.0,
                "usage": {"list_usd": 0.25}}
        meta.update(fields)
        with open(os.path.join(run_dir, "meta.json"), "w", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(meta))
        return run_dir

    def test_note_writes_a_line(self):
        code, _, err = self.run_cli("note", "[decision] use sqlite", "--lane", "w1", "--at", "2026-11-16T09:05:00")
        self.assertEqual((code, err), (0, ""))
        with open(os.path.join(self.state, "lead-log.md"), encoding="utf-8") as stream:
            self.assertEqual(stream.read(), "- 2026-11-16 09:05 (w1) [decision] use sqlite\n")
        self.run_cli("note", "plain")
        with open(os.path.join(self.state, "lead-log.md"), encoding="utf-8") as stream:
            self.assertIn(") plain\n", stream.read().splitlines(True)[1])

    def test_note_default_lane_is_main(self):
        self.run_cli("note", "hello")
        with open(os.path.join(self.state, "lead-log.md"), encoding="utf-8") as stream:
            self.assertIn(" (main) hello", stream.read())

    def test_note_refusals(self):
        for text in ("two\nlines", "x" * 301, "token sk-abcdefghijklmnop", "mail me@example.com", ""):
            code, out, err = self.run_cli("note", text)
            self.assertEqual(code, 2, text)
            self.assertTrue(err.startswith("lane-stats:"))
        self.assertFalse(os.path.exists(os.path.join(self.state, "lead-log.md")))
        self.assertEqual(self.run_cli("note", "x" * 300)[0], 0)

    def test_tags_kinds_and_importance(self):
        cases = [("[start] go", "start", 2), ("[result] ok", "success", 2), ("[fail] no", "fail", 3),
                 ("[breakthrough] hmm", "breakthrough", 3), ("[blocked: approve deploy]", "blocked", 3),
                 ("[cleared] fine", "cleared", 1), ("[done: Ship it]", "done", 2),
                 ("[metric: Speed = 3 s]", "metric", 1), ("[status: warn slow]", "status", 1),
                 ("[progress: 3/6 files]", "progress", 1), ("[end]", "end", 1), ("[review] ok", "review", 2),
                 ("untagged text", "update", 1), ("[weird] thing [decision]", "decision", 2)]
        for text, _, _ in cases:
            self.assertEqual(self.run_cli("note", text)[0], 0)
        got = {event["id"]: event for event in self.events("--since", "1h")["events"]}
        self.assertEqual(len(got), len(cases))
        by_title = {}
        for event in got.values():
            self.assertEqual(event["source"], "log")
            by_title[event["title"]] = event
        for text, kind, importance in cases:
            matches = [event for event in got.values() if event["kind"] == kind and event["importance"] == importance]
            self.assertTrue(matches, text)
        self.assertEqual(by_title["approve deploy"]["tags"], ["blocked: approve deploy"])
        self.assertEqual(by_title["Ship it"]["kind"], "done")
        weird = [event for event in got.values() if "weird" in event["tags"]]
        self.assertEqual(weird[0]["kind"], "decision")

    def test_title_is_cut_at_80(self):
        self.run_cli("note", "word " * 40)
        title = self.events("--since", "1h")["events"][0]["title"]
        self.assertEqual(len(title), 80)
        self.assertTrue(title.endswith("…"))

    def test_runs_and_reviews(self):
        self.add_run("run-a")
        self.add_run("run-b", verdict="TIMEOUT", started_at=stamp(-15), ended_at=stamp(-5))
        self.add_run("run-old", started_at=stamp(-60 * 24 * 3), ended_at=stamp(-60 * 24 * 3 + 5))
        self.assertEqual(self.run_cli("review", "run-a", "--outcome", "accepted")[0], 0)
        got = self.events("--since", "24h")["events"]
        ids = [event["id"] for event in got]
        self.assertEqual(len(set(ids)), len(ids))
        self.assertNotIn("run:run-old:end", ids)
        end = next(event for event in got if event["id"] == "run:run-a:end")
        self.assertEqual((end["kind"], end["importance"], end["source"], end["run"]), ("success", 2, "run", "run-a"))
        self.assertEqual((end["minutes"], end["eta_minutes"], end["list_usd"]), (10.0, 8.0, 0.25))
        self.assertIn("sonnet/high substantive OK", end["title"])
        fail = next(event for event in got if event["id"] == "run:run-b:end")
        self.assertEqual((fail["kind"], fail["importance"]), ("fail", 3))
        review = next(event for event in got if event["source"] == "review")
        self.assertEqual((review["kind"], review["run"], review["tags"]), ("review", "run-a", ["review: accepted"]))
        self.assertEqual([event["at"] for event in got], sorted(event["at"] for event in got))
        wide = self.events("--since", "7d")["events"]
        self.assertIn("run:run-old:end", [event["id"] for event in wide])

    def test_limit_and_text_mode(self):
        self.add_run("run-a")
        self.run_cli("note", "[blocked: approve deploy]", "--lane", "w1")
        code, out, _ = self.run_cli("timeline", "--since", "24h")
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertRegex(lines[0], r"^\d{4}-\d{2}-\d{2}$")
        self.assertTrue(any(line[2] == ":" and "  blocked  w1  approve deploy" in line for line in lines))
        self.assertEqual(len(self.events("--limit", "2")["events"]), 2)

    def test_duplicate_log_lines_collapse(self):
        path = os.path.join(self.state, "lead-log.md")
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        with open(path, "w", encoding="utf-8", newline="\n") as stream:
            stream.write("- {0} (main) same\n- {0} (main) same\nnot a log line\n".format(now))
        self.assertEqual(len(self.events("--since", "1h")["events"]), 1)

    def test_bad_since(self):
        code, _, err = self.run_cli("timeline", "--since", "soon")
        self.assertEqual(code, 2)
        self.assertIn("--since", err)

    def git(self, repo, *argv):
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
        subprocess.run(["git", "-c", "commit.gpgsign=false", "-C", repo] + list(argv), env=env, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_mirror_markers(self):
        repo = os.path.join(self.root, "repo")
        os.makedirs(repo)
        self.git(repo, "init", "-q", "-b", "work")
        subjects = ["orch: START 20261117-050000-main", "orch: STATUS 1: [blocked: approve deploy] waiting",
                    "orch: STATUS 2: plain progress", "orch: LOCAL lane u1 sonnet/high .lane-main/briefs/u1.md class=hard",
                    "orch: REVIEW u1 accepted arm=sonnet/high class=hard min=3 tok=-/- usd=0.1",
                    "orch: READY 3: all merged", "unrelated commit"]
        for subject in subjects:
            self.git(repo, "commit", "-q", "--allow-empty", "-m", subject)
        self.git(repo, "update-ref", "refs/remotes/origin/work", "HEAD")
        got = self.events("--since", "1h", "--repo", repo)["events"]
        self.assertEqual([event["kind"] for event in got], ["start", "blocked", "status", "update", "review", "done"])
        self.assertTrue(all(event["source"] == "mirror" and event["lane"] == "main" for event in got))
        self.assertEqual(got[1]["tags"], ["blocked: approve deploy"])
        self.assertEqual(got[1]["importance"], 3)
        self.assertEqual(got[1]["title"], "approve deploy - waiting")
        again = self.events("--since", "1h", "--repo", repo, "--branch", "work")["events"]
        self.assertEqual([event["id"] for event in again], [event["id"] for event in got])
        code, _, err = self.run_cli("timeline", "--repo", repo, "--branch", "missing")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
