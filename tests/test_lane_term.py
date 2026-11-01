import argparse
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "bin", "lane-term")
loader = importlib.machinery.SourceFileLoader("lane_term_tested", SCRIPT)
lane_term = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
loader.exec_module(lane_term)

# Shows whether it has a terminal, asks a question, echoes the answer, then waits far longer than any test.
CHILD = """\
import sys, time
print("tty", sys.stdin.isatty(), sys.stdout.isatty(), flush=True)
print("Continue? Yes, go on", flush=True)
print("GOT:" + sys.stdin.readline().strip(), flush=True)
print("FINISHED", flush=True)
time.sleep(30)
"""


def squashed(text):
    return "".join(text.split())


class LaneTermTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.prefix = os.path.join(self.temp.name, "run")
        self.child = os.path.join(self.temp.name, "child.py")
        with open(self.child, "w", encoding="utf-8") as handle:
            handle.write(CHILD)

    def tearDown(self):
        self.temp.cleanup()

    def term(self, options, command):
        return subprocess.run([sys.executable, SCRIPT, "--out", self.prefix] + options + ["--"] + command,
                              capture_output=True, text=True, timeout=60)

    def run_term(self, options, command):
        process = self.term(options, command)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(len(process.stdout.splitlines()), 1, process.stdout)
        with open(self.prefix + ".txt", encoding="utf-8") as handle:
            return json.loads(process.stdout), handle.read()

    def test_child_gets_a_terminal(self):
        summary, text = self.run_term(["--answer", "Yes, go on=text:ok,enter", "--until", "FINISHED",
                                       "--grace", "0.5"], [sys.executable, self.child])
        self.assertIn("ttyTrueTrue", squashed(text))
        self.assertTrue(summary["until_seen"])

    def test_answer_is_typed_then_until_stops_the_child(self):
        summary, text = self.run_term(["--answer", "Yes, go on=text:ok,enter", "--until", "FINISHED",
                                       "--grace", "0.5"], [sys.executable, self.child])
        self.assertIn("GOT:ok", squashed(text))
        self.assertEqual(summary["answered"], ["Yes, go on"])
        self.assertTrue(summary["stopped"])
        self.assertIsNone(summary["exit_code"])
        self.assertTrue(summary["until_seen"])
        self.assertLess(summary["seconds"], 15)

    def test_max_stops_a_child_that_never_finishes(self):
        summary, _ = self.run_term(["--max", "2"], [sys.executable, "-c", "import time; time.sleep(30)"])
        self.assertTrue(summary["stopped"])
        self.assertIsNone(summary["exit_code"])
        self.assertFalse(summary["until_seen"])
        self.assertLess(summary["seconds"], 10)

    def test_child_exit_code_is_reported(self):
        summary, text = self.run_term([], [sys.executable, "-c", "import sys; print('bye'); sys.exit(3)"])
        self.assertEqual(summary["exit_code"], 3)
        self.assertFalse(summary["stopped"])
        self.assertIn("bye", text)

    def test_bad_answer_is_a_usage_error(self):
        process = self.term(["--answer", "no equals sign"], [sys.executable, "-c", "pass"])
        self.assertEqual(process.returncode, 2)

    def test_missing_command_exits_1(self):
        process = self.term([], ["lane-term-no-such-command"])
        self.assertEqual(process.returncode, 1)
        self.assertIn("lane-term-no-such-command", process.stderr)

    def test_answer_keys_map_to_bytes(self):
        self.assertEqual(lane_term.answer_arg("Yes, go on=text:ok,enter"), ("Yes, go on", [b"ok", b"\r"]))
        self.assertEqual(lane_term.answer_arg("Pick=down,space"), ("Pick", [b"\x1b[B", b" "]))
        with self.assertRaises(argparse.ArgumentTypeError):
            lane_term.answer_arg("Pick=bogus")

    def test_matching_ignores_escape_codes_and_whitespace(self):
        self.assertEqual(lane_term.squash(b"\x1b[31mGOT:\x1b[0m  ok\r\n"), "GOT:ok")
