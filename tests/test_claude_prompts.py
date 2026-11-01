import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "bin", "claude-prompts")


def load_script(name, filename):
    loader = importlib.machinery.SourceFileLoader(name, os.path.join(ROOT, "bin", filename))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    loader.exec_module(module)
    return module


prompts = load_script("claude_prompts_tested", "claude-prompts")


def user(uuid, parent, text, **extra):
    row = {"type": "user", "uuid": uuid, "parentUuid": parent, "isSidechain": False,
           "timestamp": "2026-10-13T02:%02d:00.000Z" % (len(uuid) % 60),
           "message": {"role": "user", "content": text}, "origin": {"kind": "human"},
           "promptSource": "typed"}
    row.update(extra)
    return row


def assistant(uuid, parent, text="ok"):
    return {"type": "assistant", "uuid": uuid, "parentUuid": parent, "isSidechain": False,
            "timestamp": "2026-10-13T02:00:00.000Z",
            "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


def tool_result(uuid, parent):
    return {"type": "user", "uuid": uuid, "parentUuid": parent, "isSidechain": False,
            "timestamp": "2026-10-13T02:00:00.000Z", "toolUseResult": {"stdout": "x"},
            "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "x"}]}}


class ClaudePromptsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def write(self, rows, tail=""):
        path = os.path.join(self.temp.name, "session.jsonl")
        with open(path, "w", encoding="utf-8", newline="\n") as stream:
            for row in rows:
                stream.write((row if isinstance(row, str) else json.dumps(row, ensure_ascii=False)) + "\n")
            stream.write(tail)
        return path

    def titles(self, rows, tail=""):
        return [item["title"] for item in prompts.prompts_of(self.write(rows, tail))["prompts"]]

    def test_straight_chain_skips_tool_results_and_numbers_prompts(self):
        rows = [user("u1", None, "first question"), assistant("a1", "u1"), tool_result("r1", "a1"),
                assistant("a2", "r1"), user("u2", "a2", "second question"), assistant("a3", "u2")]
        result = prompts.prompts_of(self.write(rows))
        self.assertEqual([p["title"] for p in result["prompts"]], ["first question", "second question"])
        self.assertEqual([p["n"] for p in result["prompts"]], [1, 2])
        self.assertEqual([p["uuid"] for p in result["prompts"]], ["u1", "u2"])

    def test_rewound_branch_is_left_out(self):
        rows = [user("u1", None, "A"), assistant("a1", "u1"),
                user("u2", "a1", "B abandoned"), assistant("a2", "u2"),
                user("u3", "a1", "C after rewind"), assistant("a3", "u3")]
        self.assertEqual(self.titles(rows), ["A", "C after rewind"])

    def test_compaction_boundary_follows_its_logical_parent(self):
        boundary = {"type": "system", "subtype": "compact_boundary", "uuid": "c1", "parentUuid": None,
                    "logicalParentUuid": "a2", "isSidechain": False, "timestamp": "2026-10-13T02:00:00.000Z"}
        summary = user("s1", "c1", "This session is being continued from a previous conversation", isCompactSummary=True)
        rows = [user("u1", None, "before one"), assistant("a1", "u1"), user("u2", "a1", "before two"),
                assistant("a2", "u2"), boundary, summary, user("u3", "s1", "after"), assistant("a3", "u3")]
        result = prompts.prompts_of(self.write(rows))
        self.assertEqual([p["title"] for p in result["prompts"]], ["before one", "before two", "after"])
        self.assertEqual([p["isBeforeCompact"] for p in result["prompts"]], [True, True, False])

    def test_forward_logical_parent_and_cycles_do_not_hang(self):
        boundary = {"type": "system", "subtype": "compact_boundary", "uuid": "c1", "parentUuid": None,
                    "logicalParentUuid": "u3", "isSidechain": False, "timestamp": "2026-10-13T02:00:00.000Z"}
        rows = [user("u1", None, "one"), assistant("a1", "u1"), boundary, user("u3", "c1", "three"),
                assistant("a3", "u3")]
        self.assertEqual(self.titles(rows), ["one", "three"])
        started = time.time()
        cycle = [user("loop1", "loop2", "x"), user("loop2", "loop1", "y")]
        self.assertEqual(sorted(self.titles(cycle)), ["x", "y"])
        self.assertLess(time.time() - started, 2)

    def test_injected_rows_and_other_senders_are_left_out(self):
        rows = [
            user("u1", None, "real one"),
            user("m1", "u1", "reminder", isMeta=True),
            user("c1", "m1", "<command-name>/effort</command-name>"),
            user("l1", "c1", "<local-command-stdout>done</local-command-stdout>"),
            user("i1", "l1", "[Request interrupted by user]"),
            user("t1", "i1", "task done", origin={"kind": "task-notification"}),
            user("p1", "t1", "hello from a peer", origin={"kind": "peer", "from": "x"}),
            user("s1", "p1", "system text", origin=None, promptSource="system"),
            dict(user("side", "s1", "sidechain prompt"), isSidechain=True),
            user("u2", "s1", "real two"),
        ]
        self.assertEqual(self.titles(rows), ["real one", "real two"])

    def test_rows_from_before_origin_stamps_still_count(self):
        old = user("u1", None, "old style prompt")
        del old["origin"]
        del old["promptSource"]
        self.assertEqual(self.titles([old, assistant("a1", "u1")]), ["old style prompt"])

    def test_message_sent_mid_turn_is_a_prompt(self):
        queued = {"type": "attachment", "uuid": "q1", "parentUuid": "a1", "isSidechain": False,
                  "timestamp": "2026-10-13T02:00:00.000Z",
                  "attachment": {"type": "queued_command", "prompt": "also do this", "commandMode": "prompt",
                                 "origin": {"kind": "human"}, "humanTurn": True}}
        rows = [user("u1", None, "first"), assistant("a1", "u1"), queued, assistant("a2", "q1")]
        result = prompts.prompts_of(self.write(rows))
        self.assertEqual([(p["title"], p["uuid"]) for p in result["prompts"]], [("first", "u1"), ("also do this", "q1")])

    def test_titles_show_pastes_and_images(self):
        pasted = user("u1", None, "<pasted_content id=\"ab\">\nlong log\nmore\n</pasted_content id=\"ab\">\n\ninstead of this, show the answer")
        image = user("u2", "u1", [{"type": "image", "source": {}}, {"type": "text", "text": "what is this?"}])
        long_text = user("u3", "u2", "x" * 400)
        titles = self.titles([pasted, image, long_text])
        self.assertEqual(titles[0], "[pasted] instead of this, show the answer")
        self.assertEqual(titles[1], "[image] what is this?")
        self.assertEqual(len(titles[2]), prompts.TITLE_CELLS)
        self.assertTrue(titles[2].endswith("…"))

    def test_half_written_last_line_is_ignored(self):
        self.assertEqual(self.titles([user("u1", None, "complete")], tail='{"type":"user","uuid":"u2","mess'), ["complete"])

    def test_unicode_survives_a_pipe(self):
        path = self.write([user("u1", None, "日本語の質問 🚀 and more")])
        env = {k: v for k, v in os.environ.items() if k != "PYTHONIOENCODING"}
        result = subprocess.run([sys.executable, "-I", SCRIPT, "--transcript", path],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout.decode("utf-8"))
        self.assertEqual(data["prompts"][0]["title"], "日本語の質問 🚀 and more")

    def test_session_id_is_found_under_the_config_dir(self):
        config = os.path.join(self.temp.name, "config")
        folder = os.path.join(config, "projects", "C--work")
        os.makedirs(folder)
        with open(os.path.join(folder, "abc-123.jsonl"), "w", encoding="utf-8") as stream:
            stream.write(json.dumps(user("u1", None, "found me")) + "\n")
        env = dict(os.environ, CLAUDE_CONFIG_DIR=config)
        result = subprocess.run([sys.executable, "-I", SCRIPT, "--session-id", "abc-123", "--text"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("found me", result.stdout.decode("utf-8"))

    def test_missing_transcript_exits_2_with_json(self):
        result = subprocess.run([sys.executable, "-I", SCRIPT, "--transcript", os.path.join(self.temp.name, "nope.jsonl")],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("error", json.loads(result.stdout.decode("utf-8")))

    @unittest.skipUnless(os.environ.get("CLAUDE_PROMPTS_BIG"), "set CLAUDE_PROMPTS_BIG to a large transcript")
    def test_large_transcript_is_quick(self):
        started = time.time()
        prompts.prompts_of(os.environ["CLAUDE_PROMPTS_BIG"])
        self.assertLess(time.time() - started, 3)


if __name__ == "__main__":
    unittest.main()
