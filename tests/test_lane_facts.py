"""Repository facts learned from run records and added to later briefs."""

import contextlib
import hashlib
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
import unittest
import uuid


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANE_PATH = os.path.join(ROOT, "bin", "lane")
STATS_PATH = os.path.join(ROOT, "bin", "lane-stats")
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "facts")
SWAP = 'Use "F:/conda/python.exe" instead of "python" in this repository'


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


lane = load("lane_facts_lane", LANE_PATH)
stats = load("lane_facts_stats", STATS_PATH)


def force_rmtree(path):
    def retry(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=retry)
    else:
        shutil.rmtree(path, onerror=retry)


def command(program, args, ok):
    argv = (program,) + tuple(args)
    return {"program": program, "args": tuple(args), "command": " ".join(argv), "ok": ok}


class FactsTests(unittest.TestCase):
    def setUp(self):
        self.old_env = os.environ.copy()
        self.root = os.path.join(os.path.dirname(__file__), ".lane-facts-{}-{}".format(os.getpid(), uuid.uuid4().hex))
        os.makedirs(self.root)
        self.state = os.path.join(self.root, "state")
        self.workspace = os.path.join(self.root, "workspace")
        self.other = os.path.join(self.root, "other")
        os.makedirs(self.workspace)
        os.makedirs(self.other)
        os.environ["LANES_STATE"] = self.state
        os.environ["PYTHONUTF8"] = "1"
        os.environ.pop("LANES_FACTS", None)
        os.environ.pop("LANES_STUCK", None)
        # Keep git from walking out of the temp dir into this checkout.
        os.environ["GIT_CEILING_DIRECTORIES"] = self.root
        self.addCleanup(force_rmtree, self.root)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old_env)

    def run_main(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = stats.main(list(args))
        return code, stdout.getvalue(), stderr.getvalue()

    def make_run(self, name, directory=None):
        run_dir = os.path.join(self.state, "runs", name)
        os.makedirs(run_dir)
        meta = {"dir": directory or self.workspace, "lane": "haiku"}
        with open(os.path.join(run_dir, "meta.json"), "w", encoding="utf-8", newline="\n") as stream:
            json.dump(meta, stream)
        return run_dir

    def init_git(self, path):
        result = subprocess.run(["git", "init", path], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                encoding="utf-8", errors="replace", check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def read_store(self):
        with open(stats.facts_path(), "r", encoding="utf-8") as stream:
            return json.load(stream)

    def test_repo_key_uses_the_git_toplevel_or_the_directory_itself(self):
        self.init_git(self.workspace)
        nested = os.path.join(self.workspace, "nested")
        os.makedirs(nested)
        self.assertEqual(stats.repo_key(nested), stats.repo_key(self.workspace))
        self.assertEqual(stats.repo_key(self.workspace), stats.normalize_repo_path(
            subprocess.run(["git", "-C", self.workspace, "rev-parse", "--show-toplevel"],
                           stdout=subprocess.PIPE, check=True).stdout.decode().strip()))
        self.assertEqual(stats.repo_key(self.other), stats.normalize_repo_path(self.other))
        self.assertNotEqual(stats.repo_key(self.other), stats.repo_key(self.workspace))
        key = stats.normalize_repo_path(self.workspace)
        self.assertNotIn("\\", key)
        if os.name == "nt":
            self.assertEqual(stats.normalize_repo_path("C:/Lane/Repo"), "c:/Lane/Repo")
            self.assertEqual(stats.normalize_repo_path("C:\\Lane\\Repo"), "c:/Lane/Repo")
            self.assertTrue(key[0].islower() and key[1] == ":")

    def test_review_records_a_fact_and_facts_lists_and_drops_it(self):
        run_a = self.make_run("run-a")
        code, out, err = self.run_main("review", run_a, "--outcome", "accepted", "--fact", "  Use conda.  ",
                                        "--fact", "Files in this repository are UTF-8.")
        self.assertEqual(code, 0, err)
        self.assertIn("reviewed run-a: accepted", out)
        rows = stats.list_facts(self.workspace)
        self.assertEqual(sorted(row["text"] for row in rows),
                         ["Files in this repository are UTF-8.", "Use conda."])
        for row in rows:
            self.assertEqual(row["source"], "review")
            self.assertEqual(row["confirmations"], ["run-a"])
            self.assertEqual(row["contradictions"], [])
            self.assertTrue(row["active"])
            self.assertEqual(row["id"], stats.fact_id_for("review", row["text"]))
        stored = self.read_store()["repos"][stats.repo_key(self.workspace)]
        self.assertTrue(all("active" not in fact for fact in stored))
        run_b = self.make_run("run-b")
        code, _, err = self.run_main("review", run_b, "--outcome", "fixed", "--fact", "Use conda.")
        self.assertEqual(code, 0, err)
        again = [row for row in stats.list_facts() if row["text"] == "Use conda."]
        self.assertEqual(len(again), 1)
        self.assertEqual(again[0]["confirmations"], ["run-a", "run-b"])
        code, out, err = self.run_main("facts", "--repo", self.workspace, "--json")
        self.assertEqual(code, 0, err)
        listed = json.loads(out)
        self.assertEqual({row["text"] for row in listed},
                         {"Use conda.", "Files in this repository are UTF-8."})
        self.assertTrue(all(row["repo"] == stats.repo_key(self.workspace) for row in listed))
        code, out, err = self.run_main("facts", "--json", "--repo", self.other)
        self.assertEqual((code, out.strip()), (0, "[]"), err)
        code, out, err = self.run_main("facts")
        self.assertEqual(code, 0, err)
        self.assertIn("active", out)
        self.assertIn("Use conda.", out)
        dropped = again[0]["id"]
        code, out, err = self.run_main("facts", "--drop", dropped, "--json", "--repo", self.other)
        self.assertEqual(code, 0, err)
        self.assertIn("dropped {}".format(dropped), out)
        self.assertFalse(any(row["id"] == dropped for row in stats.list_facts()))
        code, out, err = self.run_main("facts", "--drop", dropped)
        self.assertEqual(code, 2, out)
        self.assertIn("unknown fact", err)

    def test_invalid_fact_is_refused_before_the_review_is_written(self):
        run_dir = self.make_run("run-bad")
        for text in ("", "   ", "a\nb", "x" * 201):
            code, out, err = self.run_main("review", run_dir, "--outcome", "accepted", "--fact", text)
            self.assertEqual(code, 2, text)
            self.assertIn("one line", err)
            self.assertFalse(os.path.exists(os.path.join(run_dir, "review.json")))
            self.assertNotIn("reviewed", out)
        code, _, err = self.run_main("review", run_dir, "--outcome", "accepted", "--fact", "x" * 200)
        self.assertEqual(code, 0, err)
        self.assertTrue(os.path.isfile(os.path.join(run_dir, "review.json")))

    def test_fixtures_find_one_program_substitution(self):
        for name, expected in (
                ("codex.jsonl", [("python", ("-m", "pytest"), False), ("git", ("status",), True),
                                 ("make", ("test",), False), ("F:/conda/python.exe", ("-m", "pytest"), True)]),
                ("claude.jsonl", [("python", ("-m", "pytest"), False),
                                  ("F:/conda/python.exe", ("-m", "pytest"), True)])):
            with open(os.path.join(FIXTURES, name), "r", encoding="utf-8") as stream:
                commands = lane.parse_shell_commands(stream.read())
            self.assertEqual([(item["program"], item["args"], item["ok"]) for item in commands], expected)
            self.assertEqual(stats.substitution_pairs(commands), [("python", "F:/conda/python.exe")])
            shown = " ".join(item["command"] for item in commands)
            self.assertNotIn("do-not-record", shown)
            self.assertNotIn("missing_fact", shown)
            self.assertNotIn("&&", shown)
        self.assertIsNone(lane.parse_command_text("python -m pytest && echo hi"))
        self.assertIsNone(lane.parse_command_text("F:\\conda\\python.exe -m pytest"))
        ambiguous = [command("python", ("-m", "pytest"), False), command("py", ("-m", "pytest"), True),
                     command("python3", ("-m", "pytest"), True)]
        self.assertEqual(stats.substitution_pairs(ambiguous), [])
        split = [command("python", ("-m", "pytest"), False), command("py", ("-m", "pytest"), True),
                 command("python", ("script.py",), False), command("python3", ("script.py",), True)]
        self.assertEqual(stats.substitution_pairs(split), [])

    def test_auto_fact_activates_at_three_runs_and_a_contradiction_retires_it(self):
        commands = [command("python", ("-m", "pytest"), False),
                    command("F:/conda/python.exe", ("-m", "pytest"), True)]
        repo = stats.repo_key(self.workspace)
        self.assertFalse(stats.observe_run(repo, "run-1", ambiguous_commands()))
        self.assertFalse(os.path.exists(stats.facts_path()))
        self.assertTrue(stats.observe_run(repo, "run-1", commands))
        self.assertFalse(stats.observe_run(repo, "run-1", commands))
        row = stats.list_facts(self.workspace)[0]
        self.assertEqual(row["text"], SWAP)
        self.assertEqual(row["source"], "auto")
        self.assertEqual(row["confirmations"], ["run-1"])
        self.assertFalse(row["active"])
        stats.observe_run(repo, "run-2", commands)
        self.assertFalse(stats.list_facts(self.workspace)[0]["active"])
        stats.observe_run(repo, "run-3", commands)
        row = stats.list_facts(self.workspace)[0]
        self.assertTrue(row["active"])
        self.assertEqual(row["confirmations"], ["run-1", "run-2", "run-3"])
        reverse = [command("F:/conda/python.exe", ("-m", "pytest"), False),
                   command("python", ("-m", "pytest"), True)]
        self.assertTrue(stats.observe_run(repo, "run-4", reverse))

        def swapped():
            return next(row for row in stats.list_facts(self.workspace) if row["text"] == SWAP)

        row = swapped()
        self.assertEqual(row["contradictions"], ["run-4"])
        self.assertEqual(row["confirmations"], ["run-1", "run-2", "run-3"])
        self.assertFalse(row["active"])
        disk = self.read_store()["repos"][repo]
        self.assertTrue(any(fact["id"] == row["id"] and "active" not in fact for fact in disk))
        stats.observe_run(repo, "run-5", commands)
        row = swapped()
        self.assertEqual(row["confirmations"], ["run-1", "run-2", "run-3"])
        self.assertFalse(row["active"])

    def test_a_corrupt_store_is_left_untouched(self):
        os.makedirs(self.state)
        with open(stats.facts_path(), "w", encoding="utf-8") as stream:
            stream.write("{")
        commands = [command("python", ("-m", "pytest"), False),
                    command("F:/conda/python.exe", ("-m", "pytest"), True)]
        self.assertFalse(stats.observe_run(stats.repo_key(self.workspace), "run-1", commands))
        with open(stats.facts_path(), "r", encoding="utf-8") as stream:
            self.assertEqual(stream.read(), "{")
        code, out, err = self.run_main("facts")
        self.assertEqual(code, 2, out)
        self.assertIn("unreadable", err)
        with open(stats.facts_path(), "r", encoding="utf-8") as stream:
            self.assertEqual(stream.read(), "{")

    def test_brief_keeps_the_newest_active_facts_inside_the_cap(self):
        repo = stats.repo_key(self.workspace)
        short = []
        for index in range(12):
            text = "short fact {:02d}".format(index)
            short.append({"id": stats.fact_id_for("review", text), "text": text, "source": "review",
                          "confirmations": ["r"], "contradictions": [],
                          "added": "2026-01-{:02d}T00:00:00Z".format(index + 1),
                          "updated": "2026-01-{:02d}T00:00:00Z".format(index + 1)})
        short.append({"id": stats.fact_id_for("auto", "not yet"), "text": "not yet", "source": "auto",
                      "confirmations": ["only"], "contradictions": [],
                      "added": "2026-02-01T00:00:00Z", "updated": "2026-02-01T00:00:00Z"})
        stats.save_facts_store({"repos": {repo: short}})
        block, ids = stats.facts_brief(repo)
        self.assertEqual(len(ids), stats.FACT_LIMIT)
        self.assertLessEqual(len(block.encode("utf-8")), stats.FACT_BYTES)
        lines = block.splitlines()
        self.assertEqual(lines[0], stats.FACT_HEADER)
        self.assertEqual(lines[1], "- short fact 11")
        self.assertEqual(lines[-1], "- short fact 02")
        self.assertNotIn("not yet", block)
        wide = []
        for index in range(12):
            text = "w{:02d} ".format(index) + ("x" * 170)
            wide.append({"id": stats.fact_id_for("review", text), "text": text, "source": "review",
                         "confirmations": ["r"], "contradictions": [],
                         "added": "2026-03-{:02d}T00:00:00Z".format(index + 1),
                         "updated": "2026-03-{:02d}T00:00:00Z".format(index + 1)})
        stats.save_facts_store({"repos": {repo: wide}})
        block, ids = stats.facts_brief(repo)
        ordered = sorted(wide, key=lambda fact: fact["updated"], reverse=True)
        chosen = [fact["text"] for fact in ordered[:len(ids)]]
        self.assertEqual([line[2:] for line in block.splitlines()[1:]], chosen)
        self.assertLess(len(ids), stats.FACT_LIMIT)
        self.assertLessEqual(len(block.encode("utf-8")), stats.FACT_BYTES)
        extra = "\n".join([stats.FACT_HEADER] + ["- " + fact["text"] for fact in ordered[:len(ids) + 1]]) + "\n"
        self.assertGreater(len(extra.encode("utf-8")), stats.FACT_BYTES)
        for name in ("haiku", "luna", "gemini"):
            sent_ids = []
            sent = lane.compose_brief(name, b"Unit brief.\n", False, self.workspace, sent_ids)
            text = sent.decode("utf-8")
            self.assertLess(text.index("Unit brief."), text.index(stats.FACT_HEADER))
            self.assertEqual(sent_ids, ids)
            if name != "haiku":
                self.assertIn(lane.PROCESS_RULE, text)
        untouched = []
        plain = lane.compose_brief("haiku", b"Unit brief.\n", False, None, untouched)
        self.assertEqual(plain, b"Unit brief.\n")
        self.assertEqual(untouched, [])
        os.environ["LANES_FACTS"] = "off"
        sent_ids = []
        sent = lane.compose_brief("haiku", b"Unit brief.\n", False, self.workspace, sent_ids, True)
        self.assertNotIn(stats.FACT_HEADER.encode("utf-8"), sent)
        self.assertEqual(sent_ids, [])
        os.environ.pop("LANES_FACTS")
        sent_ids = []
        sent = lane.compose_brief("luna", b"Unit brief.\n", False, self.workspace, sent_ids, False)
        self.assertNotIn(stats.FACT_HEADER.encode("utf-8"), sent)
        self.assertEqual(sent_ids, [])

    def test_a_lane_run_sends_active_facts_and_mines_unless_disabled(self):
        self.init_git(self.workspace)
        repo = stats.repo_key(os.path.realpath(self.workspace))
        text = "The tests use the conda Python."
        store = stats.load_facts_store()
        fact = stats.upsert_fact(store, repo, "review", text, "seed")
        stats.save_facts_store(store)
        result, capture = self.run_lane(self.claude_body(), dump_fixture=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(stats.FACT_HEADER, capture)
        self.assertIn(text, capture)
        with open(os.path.join(self.outdir, "meta.json"), "r", encoding="utf-8") as stream:
            meta = json.load(stream)
        self.assertEqual(meta["facts_sent"], [fact["id"]])
        record = self.ledger()[-1]
        self.assertNotIn("facts_sent", record)
        self.assertNotIn("stuck", record)
        mined = [row for row in stats.list_facts(self.workspace) if row["source"] == "auto"]
        self.assertEqual(len(mined), 1)
        self.assertEqual(mined[0]["text"], SWAP)
        self.assertEqual(mined[0]["confirmations"], [os.path.basename(self.outdir)])
        self.assertFalse(mined[0]["active"])
        self.outdir = os.path.join(self.root, "no-facts-run")
        result, capture = self.run_lane(self.claude_body(), extra=["--no-facts"], dump_fixture=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn(stats.FACT_HEADER, capture)
        with open(os.path.join(self.outdir, "meta.json"), "r", encoding="utf-8") as stream:
            meta = json.load(stream)
        self.assertEqual(meta["facts_sent"], [])
        self.assertEqual([row["id"] for row in stats.list_facts(self.workspace) if row["source"] == "auto"],
                         [mined[0]["id"]])
        os.environ["LANES_FACTS"] = "off"
        self.outdir = os.path.join(self.root, "env-off-run")
        result, capture = self.run_lane(self.claude_body(), dump_fixture=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn(stats.FACT_HEADER, capture)
        self.assertEqual(len([row for row in stats.list_facts(self.workspace) if row["source"] == "auto"]), 1)

    def claude_body(self):
        return "\n".join((
            "import json",
            "import os",
            "import sys",
            "sys.stdin.read()",
            "open('touched.txt', 'w', encoding='utf-8').write('x\\n')",
            "fixture = os.environ.get('FACTS_FIXTURE')",
            "if fixture:",
            "    sys.stdout.write(open(fixture, encoding='utf-8').read())",
            "print(json.dumps({'session_id': 'sess-test', 'is_error': False, 'result': 'done',",
            "                  'total_cost_usd': 0, 'usage': {'input_tokens': 1, 'output_tokens': 1}}))",
            ""))

    def run_lane(self, body, extra=(), dump_fixture=False):
        bin_dir = os.path.join(self.root, "bin")
        os.makedirs(bin_dir, exist_ok=True)
        script = os.path.join(bin_dir, "fake_claude.py")
        with open(script, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(textwrap.dedent(body))
        if os.name == "nt":
            launcher = os.path.join(bin_dir, "claude.cmd")
            with open(launcher, "w", encoding="utf-8", newline="\n") as stream:
                stream.write('@echo off\n"{}" "{}" %*\n'.format(sys.executable, script))
        else:
            launcher = os.path.join(bin_dir, "claude")
            with open(launcher, "w", encoding="utf-8", newline="\n") as stream:
                stream.write("#!/bin/sh\nexec {} {} \"$@\"\n".format(sys.executable, script))
            os.chmod(launcher, 0o755)
        touched = os.path.join(self.workspace, "touched.txt")
        if os.path.exists(touched):
            os.remove(touched)
        brief = os.path.join(self.root, "brief.md")
        with open(brief, "w", encoding="utf-8", newline="\n") as stream:
            stream.write("Edit nothing.\n")
        self.outdir = getattr(self, "outdir", os.path.join(self.root, "run-out"))
        env = dict(os.environ, LANES_STATE=self.state, LANE_NO_USAGE="1", LANE_NO_ETA="1", LANES_MEM_CHECK="off",
                   PYTHONUTF8="1", LANES_CONFIG=os.path.join(self.root, "config"),
                   LANES_ARMS=os.path.join(ROOT, "arms.json"),
                   LANES_ARMS_LOCAL=os.path.join(self.root, "no-local-arms.json"),
                   LANES_CLAUDE_BIN=launcher, GIT_CEILING_DIRECTORIES=self.root)
        env.pop("USAGE_OPTIMIZER_MODE", None)
        if dump_fixture:
            env["FACTS_FIXTURE"] = os.path.join(FIXTURES, "claude.jsonl")
        result = subprocess.run([sys.executable, LANE_PATH, "haiku", "-C", self.workspace, "-b", brief,
                                 "-e", "xhigh", "--class", "mechanical", "--outdir", self.outdir] + list(extra),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
                                encoding="utf-8", errors="replace", timeout=30, check=False)
        with open(os.path.join(self.outdir, "brief.sent.md"), "r", encoding="utf-8") as stream:
            sent = stream.read()
        return result, sent

    def ledger(self):
        with open(os.path.join(self.state, "ledger.jsonl"), "r", encoding="utf-8") as stream:
            return [json.loads(line) for line in stream]


def ambiguous_commands():
    return [command("python", ("-m", "pytest"), False), command("py", ("-m", "pytest"), True),
            command("python3", ("-m", "pytest"), True)]


class SecretFactTests(unittest.TestCase):
    def test_secret_looking_text_is_refused_and_ordinary_facts_pass(self):
        for text in ('Use curl -H "Authorization: Bearer abc" instead of curl',
                     "Use ghp_abcdefghij instead of the old token",
                     "Set OPENAI_API_KEY first",
                     "Use sk-proj123 instead of sk-old",
                     "Use 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08 as the id",
                     "Mail owner@example.com when it fails",
                     "Clone https://bob:hunter2@host/repo.git"):
            self.assertTrue(stats.looks_secret(text), text)
            with self.assertRaises(ValueError):
                stats.check_fact_text(text)
        for text in (SWAP, 'Use "/home/dev/project/tests/fixtures/facts" for fixtures',
                     "Run the suite with -p test_*.py, not -t ."):
            self.assertFalse(stats.looks_secret(text), text)
            self.assertEqual(stats.check_fact_text(text), text)


class FactIdTests(unittest.TestCase):
    def test_review_and_auto_facts_do_not_share_an_id(self):
        text = "Same words."
        review_id = stats.fact_id_for("review", text)
        auto_id = stats.fact_id_for("auto", text)
        self.assertNotEqual(review_id, auto_id)
        self.assertEqual(review_id, "f-" + hashlib.sha256(("review\0" + text).encode("utf-8")).hexdigest()[:12])


if __name__ == "__main__":
    unittest.main()
