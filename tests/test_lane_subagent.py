import json
import os
import shutil
import stat
import subprocess
import sys
import time
import unittest
import uuid


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "bin", "lane")


def force_rmtree(path):
    def retry(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=retry)
    else:
        shutil.rmtree(path, onerror=retry)


def usage(input_tokens, output, cache_read, write_5m=None, write_1h=None, creation=None):
    value = {"input_tokens": input_tokens, "output_tokens": output, "cache_read_input_tokens": cache_read}
    if creation is not None:
        value["cache_creation_input_tokens"] = creation
    else:
        value["cache_creation_input_tokens"] = write_5m + write_1h
        value["cache_creation"] = {"ephemeral_5m_input_tokens": write_5m, "ephemeral_1h_input_tokens": write_1h}
    return value


def assistant(message_id, tokens, text=None, model="claude-haiku-5-5", effort="high"):
    content = [{"type": "text", "text": text}] if text is not None else [{"type": "tool_use", "id": "t", "name": "Bash"}]
    return {"type": "assistant", "effort": effort,
            "message": {"id": message_id, "model": model, "role": "assistant", "content": content, "usage": tokens}}


class LaneSubagentBase(unittest.TestCase):
    def setUp(self):
        self.root = os.path.join(os.path.dirname(__file__), ".lane-subagent-{}-{}".format(os.getpid(), uuid.uuid4().hex))
        os.makedirs(self.root)
        self.addCleanup(force_rmtree, self.root)
        self.workspace = os.path.join(self.root, "workspace")
        self.state = os.path.join(self.root, "state")
        self.config = os.path.join(self.root, "config")
        self.projects = os.path.join(self.root, "projects")
        self.brief = os.path.join(self.root, "brief.md")
        os.makedirs(self.workspace)
        os.makedirs(os.path.join(self.config, "bin"))
        self.write(self.brief, "Create a small result file.\n")
        self.git("init", self.workspace)
        self.write(os.path.join(self.workspace, "base.txt"), "base\n")
        self.git("-C", self.workspace, "add", "base.txt")
        self.git("-C", self.workspace, "-c", "user.name=Lane Test", "-c", "user.email=lane-test@localhost",
                 "commit", "-m", "base")
        self.env = os.environ.copy()
        self.env.update({
            "LANES_STATE": self.state,
            "LANES_CONFIG": self.config,
            "LANES_ARMS": os.path.join(ROOT, "arms.json"),
            "LANES_ARMS_LOCAL": os.path.join(self.root, "no-local-arms.json"),
            "LANES_CLAUDE_PROJECTS": self.projects,
            "LANE_NO_USAGE": "1",
            "LANE_NO_ETA": "1",
            "LANES_MEM_CHECK": "off",
        })

    def write(self, path, text):
        with open(path, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)

    def git(self, *args):
        return subprocess.run(["git"] + list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=10, check=True)

    def run_lane(self, extra=(), lane="haiku", effort="high"):
        argv = [sys.executable, SCRIPT, lane, "-C", self.workspace, "-b", self.brief, "-e", effort,
                "--class", "mechanical"] + list(extra)
        return subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False,
                              env=self.env, encoding="utf-8", errors="replace")

    def prepare(self, extra=()):
        result = self.run_lane(("--subagent",) + tuple(extra))
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertRegex(lines[0], r"^lane: subagent run \S+ prepared; launch it with the Agent tool:$")
        launch = json.loads(lines[1])
        run_id = lines[0].split()[3]
        self.last_launch_line = lines[1]
        return run_id, os.path.join(self.state, "runs", run_id), launch

    def transcript(self, run_id, entries, path=None, first_as_blocks=False):
        path = path or os.path.join(self.root, "agent-{}.jsonl".format(uuid.uuid4().hex[:8]))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        text = "lane-run: {}\nYour brief is in somewhere. Read it in full first and follow it exactly.".format(run_id)
        content = [{"type": "text", "text": text}] if first_as_blocks else text
        rows = [{"type": "user", "agentId": "a1", "sessionId": "parent-1",
                 "message": {"role": "user", "content": content}}] + list(entries)
        with open(path, "w", encoding="utf-8", newline="\n") as stream:
            for row in rows:
                stream.write(json.dumps(row) + "\n")
        return path

    def hook(self, payload):
        data = payload if isinstance(payload, str) else json.dumps(payload)
        return subprocess.run([sys.executable, SCRIPT, "hook", "subagent-stop"], input=data, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=30, check=False, env=self.env, encoding="utf-8")

    def stop(self, transcript, last="Done; wrote result.txt.", agent_type="lane-haiku-high", agent_id="a1"):
        result = self.hook({"session_id": "parent-1", "agent_id": agent_id, "agent_type": agent_type,
                            "agent_transcript_path": transcript, "last_assistant_message": last,
                            "cwd": self.workspace, "hook_event_name": "SubagentStop"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        return result

    def meta(self, run_dir):
        with open(os.path.join(run_dir, "meta.json"), "r", encoding="utf-8") as stream:
            return json.load(stream)

    def ledger(self):
        path = os.path.join(self.state, "ledger.jsonl")
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]

    def standard_entries(self, last="Done; wrote result.txt.", effort="high"):
        first = usage(10, 5, 1000, 2000, 400)
        final = usage(10, 50, 1000, 2000, 400)
        return [assistant("msg_A", first, effort=effort), assistant("msg_A", final, text="working", effort=effort),
                assistant("msg_B", usage(3, 7, 3000, creation=500), text=last, effort=effort)]



class LaneSubagentTests(LaneSubagentBase):
    def test_prepare_writes_prompt_and_launch_line_without_ledger(self):
        run_id, run_dir, launch = self.prepare()
        prompt_path = os.path.join(run_dir, "prompt.md")
        with open(prompt_path, "r", encoding="utf-8") as stream:
            prompt = stream.read()
        lines = prompt.splitlines()
        self.assertEqual(lines[0], "lane-run: " + run_id)
        self.assertEqual(lines[1], "Work only in this directory: " + os.path.realpath(self.workspace))
        self.assertEqual(lines[2], "")
        self.assertIn("Create a small result file.", prompt)
        self.assertIn("You are a worker dispatched by lane.", prompt)
        self.assertIn("PARTIAL: <one-line reason>", prompt)
        self.assertEqual(launch["subagent_type"], "lane-haiku-high")
        self.assertEqual(launch["description"], "haiku high mechanical")
        self.assertEqual(launch["prompt"], "lane-run: {}\nYour brief is in {}. Read it in full first and follow it "
                                           "exactly.".format(run_id, prompt_path))
        meta = self.meta(run_dir)
        self.assertEqual(meta["place"], "subagent")
        self.assertIsNone(meta["verdict"])
        self.assertIsNone(meta["peak_mem_mb"])
        self.assertTrue(meta["launched_at"])
        self.assertEqual(meta["git_before"]["status"], [])
        self.assertEqual(self.ledger(), [])

    def test_prepare_read_only_adds_line(self):
        run_id, run_dir, _ = self.prepare(("--ro",))
        with open(os.path.join(run_dir, "prompt.md"), "r", encoding="utf-8") as stream:
            lines = stream.read().splitlines()
        self.assertEqual(lines[2], "Read-only run: do not create, modify or delete any file.")
        self.assertEqual(lines[3], "")

    def test_dry_run_writes_nothing(self):
        result = self.run_lane(("--subagent", "--dry-run"))
        self.assertEqual(result.returncode, 0, result.stderr)
        launch = json.loads(next(line for line in result.stdout.splitlines() if line.startswith("{")))
        self.assertEqual(launch["subagent_type"], "lane-haiku-high")
        self.assertFalse(os.path.exists(os.path.join(self.state, "runs")))

    def test_flag_refusals(self):
        for extra in (("--cloud",), ("--web",), ("--mask",), ("--resume", "abc")):
            result = self.run_lane(("--subagent",) + extra)
            self.assertEqual(result.returncode, 2, extra)
            self.assertIn("--subagent cannot be combined", result.stderr)
        result = self.run_lane(("--subagent",), lane="luna", effort="medium")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--subagent is only available", result.stderr)

    def test_changed_workspace_ok_with_deduplicated_tokens(self):
        run_id, run_dir, _ = self.prepare()
        self.write(os.path.join(self.workspace, "result.txt"), "result\n")
        self.stop(self.transcript(run_id, self.standard_entries()))
        meta = self.meta(run_dir)
        self.assertEqual(meta["verdict"], "OK")
        self.assertEqual(meta["exit_code"], 0)
        self.assertEqual(meta["usage"]["tokens"], {"input": 13, "output": 57, "cache_read": 4000,
                                                   "cache_write_5m": 2500, "cache_write_1h": 400})
        expected = (10 * 0.1 + 50 * 0.5 + 1000 * 0.01 + 2000 * 0.125 + 400 * 0.2
                    + 3 * 0.1 + 7 * 0.5 + 3000 * 0.01 + 500 * 0.125) / 1e6
        self.assertEqual(meta["usage"]["list_usd"], round(expected, 6))
        self.assertEqual(meta["subagent"]["parent_session_id"], "parent-1")
        self.assertEqual(meta["subagent"]["agent_id"], "a1")
        self.assertEqual(meta["subagent"]["models_seen"], ["claude-haiku-5-5"])
        self.assertEqual(meta["subagent"]["efforts_seen"], ["high"])
        self.assertEqual(meta["subagent"]["later_stops"], [])
        self.assertNotIn("warnings", meta)
        with open(os.path.join(run_dir, "final.md"), "r", encoding="utf-8") as stream:
            self.assertEqual(stream.read(), "Done; wrote result.txt.\n")
        records = self.ledger()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["place"], "subagent")
        self.assertEqual(records[0]["verdict"], "OK")
        self.assertEqual(records[0]["run_dir"], os.path.abspath(run_dir))

    def test_unchanged_workspace_is_noop(self):
        run_id, run_dir, _ = self.prepare()
        self.stop(self.transcript(run_id, self.standard_entries()))
        self.assertEqual(self.meta(run_dir)["verdict"], "NOOP")
        self.assertEqual(self.ledger()[0]["exit_code"], 3)

    def test_partial_marker_is_partial(self):
        run_id, run_dir, _ = self.prepare()
        self.write(os.path.join(self.workspace, "result.txt"), "half\n")
        last = "Summary\n\nPARTIAL: ran out of turns before the tests"
        self.stop(self.transcript(run_id, self.standard_entries(last)), last=last)
        self.assertEqual(self.meta(run_dir)["verdict"], "PARTIAL")

    def test_read_only_empty_answer_is_noop(self):
        run_id, run_dir, _ = self.prepare(("--ro",))
        self.stop(self.transcript(run_id, self.standard_entries("")), last="")
        self.assertEqual(self.meta(run_dir)["verdict"], "NOOP")

    def test_second_stop_records_later_stop_only(self):
        run_id, run_dir, _ = self.prepare()
        transcript = self.transcript(run_id, self.standard_entries())
        self.stop(transcript)
        self.stop(transcript, agent_id="a2")
        meta = self.meta(run_dir)
        self.assertEqual(len(self.ledger()), 1)
        self.assertEqual(len(meta["subagent"]["later_stops"]), 1)
        self.assertEqual(meta["subagent"]["later_stops"][0]["agent_id"], "a2")
        self.assertEqual(meta["subagent"]["agent_id"], "a1")

    def test_other_agent_type_writes_nothing(self):
        run_id, run_dir, _ = self.prepare()
        self.stop(self.transcript(run_id, self.standard_entries()), agent_type="general-purpose")
        self.assertIsNone(self.meta(run_dir)["verdict"])
        self.assertEqual(self.ledger(), [])
        self.assertFalse(os.path.exists(os.path.join(self.state, "hook-errors.log")))

    def test_transcript_without_run_header_writes_nothing(self):
        run_id, run_dir, _ = self.prepare()
        path = os.path.join(self.root, "other.jsonl")
        self.write(path, json.dumps({"type": "user", "message": {"content": "hello"}}) + "\n")
        self.stop(path)
        self.assertIsNone(self.meta(run_dir)["verdict"])
        self.assertEqual(self.ledger(), [])

    def test_garbage_stdin_logs_and_exits_zero(self):
        result = self.hook("this is not json {")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        with open(os.path.join(self.state, "hook-errors.log"), "r", encoding="utf-8") as stream:
            self.assertIn("Traceback", stream.read())
        self.assertEqual(self.ledger(), [])

    def test_recover_finds_transcript_under_projects_root(self):
        run_id, run_dir, _ = self.prepare()
        self.write(os.path.join(self.workspace, "result.txt"), "result\n")
        decoy = self.transcript("20000101-000000-haiku-other", self.standard_entries(),
                                path=os.path.join(self.projects, "proj", "sess-0", "subagents", "agent-zzz.jsonl"))
        path = self.transcript(run_id, self.standard_entries("Recovered answer."), first_as_blocks=True,
                               path=os.path.join(self.projects, "proj", "sess-9", "subagents", "agent-abc.jsonl"))
        old = time.time() - 600
        for item in (decoy, path):
            os.utime(item, (old, old))
        result = subprocess.run([sys.executable, SCRIPT, "--recover", run_id], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=30, check=False, env=self.env, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("recovered=1", result.stdout)
        meta = self.meta(run_dir)
        self.assertEqual(meta["verdict"], "OK")
        self.assertTrue(meta["recovered"])
        self.assertEqual(meta["subagent"]["transcript"], path)
        self.assertEqual(meta["subagent"]["parent_session_id"], "parent-1")
        with open(os.path.join(run_dir, "final.md"), "r", encoding="utf-8") as stream:
            self.assertEqual(stream.read(), "Recovered answer.\n")
        self.assertEqual(len(self.ledger()), 1)

    def test_recover_without_transcript_is_lost_run(self):
        run_id, run_dir, _ = self.prepare()
        result = subprocess.run([sys.executable, SCRIPT, "--recover", run_id], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=30, check=False, env=self.env, encoding="utf-8")
        self.assertEqual(result.returncode, 2)
        self.assertIn("run.log is missing", result.stderr)
        self.assertEqual(self.ledger(), [])

    def test_haiku_long_context_prices(self):
        run_id, run_dir, _ = self.prepare()
        entries = [assistant("msg_L", usage(1000, 100, 99500, 0, 0), text="long"),
                   assistant("msg_S", usage(1000, 100, 9500, 0, 0), text="short")]
        self.stop(self.transcript(run_id, entries))
        expected = (1000 * 0.5 + 100 * 2.5 + 99500 * 0.05) / 1e6 + (1000 * 0.1 + 100 * 0.5 + 9500 * 0.01) / 1e6
        self.assertEqual(self.meta(run_dir)["usage"]["list_usd"], round(expected, 6))

    def test_unknown_model_nulls_price_with_warning(self):
        run_id, run_dir, _ = self.prepare()
        entries = [assistant("msg_X", usage(1, 1, 1, 0, 0), text="x", model="claude-mystery-1")]
        self.stop(self.transcript(run_id, entries))
        meta = self.meta(run_dir)
        self.assertIsNone(meta["usage"]["list_usd"])
        self.assertTrue(any("claude-mystery-1" in item for item in meta["warnings"]))

    def test_effort_mismatch_warning(self):
        run_id, run_dir, _ = self.prepare()
        self.stop(self.transcript(run_id, self.standard_entries(effort="low")))
        meta = self.meta(run_dir)
        self.assertIn("subagent ran at effort low; the arm is high", meta["warnings"])
        self.assertEqual(meta["subagent"]["efforts_seen"], ["low"])


    def test_subagent_refused_where_the_platform_has_no_subagent_place(self):
        env = dict(self.env, KIT_PLATFORM="codex")
        argv = [sys.executable, SCRIPT, "haiku", "-C", self.workspace, "-b", self.brief, "-e", "high",
                "--class", "mechanical", "--subagent"]
        result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False,
                                env=env, encoding="utf-8", errors="replace")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("--subagent is not available on codex", result.stderr)
        self.assertIn("process form", result.stderr)


FAKE_AMP = os.path.join(ROOT, "tests", "fake_amp.py")


class AmpAgentRunTests(LaneSubagentBase):
    """A4: on platform amp, --subagent prepares a run the plugin's kit_lane_run tool starts as an agent thread."""

    def setUp(self):
        super().setUp()
        # LANES_AMP_BIN names a wrapper that runs tests/fake_amp.py with this interpreter, as test_turn_meter does.
        if os.name == "nt":
            wrapper = os.path.join(self.root, "amp.cmd")
            body = '@echo off\r\n"{}" "{}" %*\r\n'.format(sys.executable, FAKE_AMP)
        else:
            wrapper = os.path.join(self.root, "amp")
            body = '#!/bin/sh\nexec "{}" "{}" "$@"\n'.format(sys.executable, FAKE_AMP)
        self.write(wrapper, body)
        os.chmod(wrapper, 0o700)
        self.amp_log = os.path.join(self.root, "amp-calls.log")
        self.env.update({"KIT_PLATFORM": "amp", "LANES_AMP_BIN": wrapper, "FAKE_AMP_LOG": self.amp_log,
                         "FAKE_AMP_MODE": "ok"})

    def amp_calls(self):
        if not os.path.exists(self.amp_log):
            return []
        with open(self.amp_log, "r", encoding="utf-8") as stream:
            return [line.strip() for line in stream if line.strip()]

    def prepare_amp(self, extra=(), lane="sonnet", effort="high"):
        result = self.run_lane(("--subagent",) + tuple(extra), lane=lane, effort=effort)
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertRegex(lines[0], r"^lane: amp agent run \S+ prepared; call the kit_lane_run tool with this input:$")
        run_id = lines[0].split()[4]
        self.assertEqual(json.loads(lines[1]), {"tool": "kit_lane_run", "run_id": run_id})
        return run_id, os.path.join(self.state, "runs", run_id)

    def amp_hook(self, name, payload, as_argument=False):
        data = json.dumps(payload)
        argv = [sys.executable, SCRIPT, "hook", name] + (["--json", data] if as_argument else ["--json", "-"])
        result = subprocess.run(argv, input=None if as_argument else data, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=60, check=False, env=self.env, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 1, result.stdout)
        return json.loads(lines[0])

    def end(self, run_id, **fields):
        payload = {"run_id": run_id, "thread_id": "T-child-0001", "text": "Done; wrote result.txt.", "status": "done",
                   "parent_thread_id": "T-parent-0001"}
        payload.update(fields)
        return self.amp_hook("amp-run-end", payload)

    def test_prepare_prints_the_tool_call_and_writes_an_amp_record(self):
        run_id, run_dir = self.prepare_amp()
        meta = self.meta(run_dir)
        self.assertEqual((meta["place"], meta["platform"], meta["provider"]), ("subagent", "amp", "amp"))
        self.assertEqual(meta["subagent"]["agent_type"], "amp-agent")
        self.assertEqual(meta["subagent"]["agent_model"], "anthropic/claude-sonnet-5-5")
        self.assertEqual(meta["subagent"]["timeout_s"], 3600)
        self.assertIsNone(meta["verdict"])
        with open(os.path.join(run_dir, "prompt.md"), "r", encoding="utf-8") as stream:
            self.assertEqual(stream.readline(), "lane-run: {}\n".format(run_id))
        self.assertEqual(self.ledger(), [])
        self.assertEqual(self.amp_calls(), [])

    def test_amp_lane_arm_uses_its_cli_model_and_dry_run_writes_nothing(self):
        result = self.run_lane(("--subagent", "--dry-run", "-m", "gpt-6.1-sol"), lane="amp", effort="medium")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("as an Amp agent on openai/gpt-6.1-sol", result.stdout)
        self.assertIn('{"tool": "kit_lane_run", "run_id": ', result.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.state, "runs")))

    def test_arms_amp_cannot_serve_are_refused_before_any_run_dir(self):
        result = self.run_lane(("--subagent", "-m", "glm-5.3-flash"), lane="amp", effort="low")
        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot run as an Amp agent", result.stderr)
        result = self.run_lane(("--subagent",), lane="luna", effort="medium")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--subagent is only available for haiku, sonnet, opus, fable, amp on amp", result.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.state, "runs")))

    def test_spec_gives_model_effort_prompt_timeout_and_excluded_tools(self):
        run_id, run_dir = self.prepare_amp(("--ro", "--timeout", "900"), lane="opus", effort="xhigh")
        spec = self.amp_hook("amp-run-spec", {"run_id": run_id, "parent_thread_id": "T-parent-0001"})
        self.assertTrue(spec["ok"], spec)
        self.assertEqual(spec["model"], "anthropic/claude-opus-5-5")
        self.assertEqual(spec["reasoningEffort"], "xhigh")
        self.assertEqual(spec["timeoutMs"], 900000)
        with open(os.path.join(run_dir, "prompt.md"), "r", encoding="utf-8") as stream:
            self.assertEqual(spec["instructions"], stream.read())
        self.assertTrue(spec["message"].startswith("lane-run: " + run_id + "\n"))
        for name in ("kit_lane_run", "Task", "create_thread", "edit_file", "apply_patch"):
            self.assertIn(name, spec["tools"]["exclude"])
        meta = self.meta(run_dir)
        self.assertEqual(meta["subagent"]["parent_thread_id"], "T-parent-0001")
        self.assertTrue(meta["subagent"]["tool_started_at"])

    def test_spec_refuses_paths_unknown_runs_and_claude_code_runs(self):
        for run_id in ("../x", "a/b", "", 5):
            self.assertFalse(self.amp_hook("amp-run-spec", {"run_id": run_id})["ok"])
        self.assertIn("no lane run", self.amp_hook("amp-run-spec", {"run_id": "20000101-000000-x"})["error"])
        self.env["KIT_PLATFORM"] = "claude-code"
        run_id, _, _ = self.prepare()
        self.assertIn("not prepared as an Amp agent run", self.amp_hook("amp-run-spec", {"run_id": run_id})["error"])

    def test_end_records_verdict_final_tokens_and_dollars_with_one_usage_call(self):
        run_id, run_dir = self.prepare_amp()
        self.write(os.path.join(self.workspace, "result.txt"), "result\n")
        result = self.end(run_id)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["verdict"], "OK")
        self.assertRegex(result["summary"], r"^lane=sonnet verdict=OK exit=0 session=T-child-0001 secs=\d+ out=")
        meta = self.meta(run_dir)
        self.assertEqual((meta["verdict"], meta["exit_code"], meta["session_id"]), ("OK", 0, "T-child-0001"))
        self.assertEqual((meta["place"], meta["platform"]), ("subagent", "amp"))
        usage = meta["usage"]
        self.assertEqual(usage["tokens"], {"input": 186663, "cached": 1075868, "output": 10931, "total": 1273462})
        self.assertEqual((usage["list_usd"], usage["amp_usd"], usage["billed"], usage["cost_source"]),
                         (0.13, 0.13, "amp", "amp-threads-usage"))
        self.assertEqual(meta["subagent"]["child_thread_id"], "T-child-0001")
        self.assertEqual(meta["subagent"]["status"], "done")
        with open(os.path.join(run_dir, "final.md"), "r", encoding="utf-8") as stream:
            self.assertEqual(stream.read(), "Done; wrote result.txt.\n")
        self.assertEqual(self.amp_calls(), ["threads usage T-child-0001 --details"])
        ledger = self.ledger()
        self.assertEqual(len(ledger), 1)
        self.assertEqual(ledger[0]["verdict"], "OK")

    def test_end_accepts_the_json_as_an_argument_and_a_second_end_is_only_noted(self):
        run_id, run_dir = self.prepare_amp()
        payload = {"run_id": run_id, "thread_id": "T-child-0002", "text": "Nothing to change.", "status": "done"}
        self.assertEqual(self.amp_hook("amp-run-end", payload, as_argument=True)["verdict"], "NOOP")
        again = self.end(run_id)
        self.assertIn("already recorded (NOOP)", again["summary"])
        meta = self.meta(run_dir)
        self.assertEqual(len(meta["subagent"]["later_ends"]), 1)
        self.assertEqual(len(self.ledger()), 1)
        self.assertEqual(len(self.amp_calls()), 1)

    def test_rejected_runs_are_timeout_quota_or_failed_without_a_usage_call(self):
        cases = [({"status": "timeout", "error": "Agent run timed out"}, "TIMEOUT", 124),
                 ({"status": "error", "error": "Error: insufficient credits"}, "QUOTA", 75),
                 ({"status": "error", "error": "Error: model unavailable"}, "FAILED", 4),
                 ({"status": "cancelled", "error": "AbortError"}, "FAILED", 4)]
        for fields, verdict, code in cases:
            run_id, run_dir = self.prepare_amp()
            result = self.end(run_id, thread_id=None, text="", **fields)
            self.assertEqual((result["verdict"], result["exit_code"]), (verdict, code), fields)
            meta = self.meta(run_dir)
            self.assertIsNone(meta["usage"]["tokens"])
            self.assertIsNone(meta["usage"]["list_usd"])
            self.assertIn("no child thread id", meta["usage"]["tokens_error"])
            self.assertTrue(any(item.startswith("Agent.run ") for item in meta["warnings"]))
            self.assertFalse(os.path.exists(os.path.join(run_dir, "final.md")))
        self.assertEqual(self.amp_calls(), [])

    def test_partial_marker_and_unreadable_usage(self):
        self.env["FAKE_AMP_MODE"] = "fail"
        run_id, run_dir = self.prepare_amp()
        result = self.end(run_id, text="PARTIAL: tests would not run")
        self.assertEqual(result["verdict"], "PARTIAL")
        usage = self.meta(run_dir)["usage"]
        self.assertIsNone(usage["tokens"])
        self.assertIsNone(usage["list_usd"])
        self.assertEqual(usage["tokens_error"], "amp threads usage unavailable")
        self.assertEqual(len(self.amp_calls()), 1)

    def test_recover_waits_for_the_timeout_then_marks_from_git_state(self):
        run_id, run_dir = self.prepare_amp(("--timeout", "600"))
        recover = [sys.executable, SCRIPT, "--recover", run_id]
        result = subprocess.run(recover, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False,
                                env=self.env, encoding="utf-8")
        self.assertEqual(result.returncode, 2)
        self.assertIn("may still be running", result.stderr)
        self.write(os.path.join(self.workspace, "result.txt"), "result\n")
        result = subprocess.run(recover + ["--force"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
                                check=False, env=self.env, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("recovered=1", result.stdout)
        meta = self.meta(run_dir)
        # A lost run never counts as OK: changed files without an answer are unfinished work.
        self.assertEqual(meta["verdict"], "PARTIAL")
        self.assertTrue(meta["recovered"])
        self.assertEqual(meta["subagent"]["status"], "lost")
        self.assertIsNone(meta["usage"]["tokens"])
        self.assertEqual(len(self.ledger()), 1)
        self.assertEqual(self.amp_calls(), [])

    def test_recover_of_an_unchanged_workspace_is_failed(self):
        run_id, run_dir = self.prepare_amp(("--timeout", "1"))
        meta = self.meta(run_dir)
        meta["launched_at"] = "2000-01-01T00:00:00Z"
        with open(os.path.join(run_dir, "meta.json"), "w", encoding="utf-8") as stream:
            json.dump(meta, stream)
        result = subprocess.run([sys.executable, SCRIPT, "--recover", run_id], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=30, check=False, env=self.env, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.meta(run_dir)["verdict"], "FAILED")

    def test_amp_mode_reads_main_session(self):
        mode = self.amp_hook("amp-mode", {})
        self.assertTrue(mode["ok"])
        self.assertEqual((mode["key"], mode["model"], mode["reasoningEffort"], mode["compactionThresholdTokens"]),
                         ("kit", "anthropic/claude-opus-5-5", "xhigh", 250000))
        self.assertEqual(mode["subagentModel"], "anthropic/claude-sonnet-5-5")
        local = os.path.join(self.root, "arms.local.json")
        self.write(local, json.dumps({"explore": {"main_session": {"model": "sonnet", "effort": "high"}}}))
        self.env["LANES_ARMS_LOCAL"] = local
        mode = self.amp_hook("amp-mode", {})
        self.assertEqual((mode["model"], mode["reasoningEffort"]), ("anthropic/claude-sonnet-5-5", "high"))

    def test_bad_hook_input_answers_ok_false(self):
        self.assertFalse(self.amp_hook("amp-run-end", [1])["ok"])
        result = subprocess.run([sys.executable, SCRIPT, "hook", "amp-run-end", "--bogus"], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=30, check=False, env=self.env, encoding="utf-8")
        self.assertEqual(result.returncode, 0)
        self.assertFalse(json.loads(result.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()
