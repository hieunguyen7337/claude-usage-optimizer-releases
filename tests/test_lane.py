import datetime
import glob
import importlib.machinery
import importlib.util
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
import uuid
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "bin", "lane")
loader = importlib.machinery.SourceFileLoader("lane_tested", SCRIPT)
lane = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
loader.exec_module(lane)


def without_mode_line(text):
    # Every run prints its usage mode on stderr (tests/test_lane_cloud.py covers the line).
    return "".join(line for line in text.splitlines(True) if not line.startswith("lane: mode "))


def force_rmtree(path):
    """rmtree that clears read-only bits first: git marks its object files read-only on Windows."""
    def retry(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=retry)
    else:
        shutil.rmtree(path, onerror=retry)


class LaneTests(unittest.TestCase):
    def setUp(self):
        self.root = os.path.join(os.path.dirname(__file__), ".lane-stats-{}-{}".format(os.getpid(), uuid.uuid4().hex))
        os.makedirs(self.root)
        self.addCleanup(force_rmtree, self.root)
        self.workspace = os.path.join(self.root, "workspace with spaces")
        self.bin = os.path.join(self.root, "bin")
        self.state = os.path.join(self.root, "state")
        self.outdir = os.path.join(self.root, "explicit run")
        self.brief = os.path.join(self.root, "brief.md")
        self.capture = os.path.join(self.root, "capture.json")
        for directory in (self.workspace, self.bin):
            os.makedirs(directory)
        self.write(self.brief, "Edit worker.txt and return the verifier output.\n")
        self.env = dict(os.environ, LANES_STATE=self.state, LANE_NO_USAGE="1", LANE_NO_ETA="1", LANES_MEM_CHECK="off",
                        PYTHONUTF8="1",
                        LANES_CONFIG=os.path.join(self.root, "config"), FAKE_CAPTURE=self.capture,
                        LANES_ARMS=os.path.join(ROOT, "arms.json"),
                        LANES_ARMS_LOCAL=os.path.join(self.root, "no-local-arms.json"),
                        CODEX_HOME=os.path.join(self.root, "codex-home"),
                        LANES_PROC_CGROUP=os.path.join(self.root, "no-proc-cgroup"),
                        LANES_CGROUP_ROOT=os.path.join(self.root, "cgroup"),
                        PATH=self.bin + os.pathsep + os.environ.get("PATH", ""), FAKE_MODE="edit",
                        CLAUDECODE="nested", CLAUDE_CODE_ENTRYPOINT="nested", CLAUDE_CODE_TEST="nested",
                        CLAUDE_KEEP="preserved")
        self.install_cli("claude", '''
            import json
            import os
            import subprocess
            import sys
            import time

            brief = sys.stdin.read()
            with open(os.environ["FAKE_CAPTURE"], "w", encoding="utf-8") as stream:
                json.dump({"argv": sys.argv[1:], "brief": brief,
                           "nested_env": sorted(key for key in os.environ
                                                if key == "CLAUDECODE" or key.startswith("CLAUDE_CODE_")),
                           "keep": os.environ.get("CLAUDE_KEEP")}, stream)
            mode = os.environ.get("FAKE_MODE", "edit")
            if mode == "timeout":
                time.sleep(2)
                sys.exit(0)
            if mode == "edit":
                with open("worker.txt", "w", encoding="utf-8") as stream:
                    stream.write("edited by fake claude\\n")
            if mode == "commit":
                with open("committed.txt", "w", encoding="utf-8") as stream:
                    stream.write("committed by fake claude\\n")
                subprocess.run(["git", "add", "committed.txt"], check=True)
                subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@localhost",
                                "commit", "-m", "worker commit"], check=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(json.dumps({"type": "init", "session_id": "earlier-session"}))
            print(json.dumps({"session_id": "claude-test-session",
                              "is_error": mode in ("quota", "failed", "failed-429"),
                              "result": "You hit your limit: usage limit reached" if mode == "quota" else
                                        "tool failed: request id abc429def" if mode == "failed-429" else
                                        "tool failed" if mode == "failed" else "done edit",
                              "total_cost_usd": 0.125,
                              "usage": {"input_tokens": 11, "cache_creation_input_tokens": 7,
                                        "cache_read_input_tokens": 100, "output_tokens": 5}}))
            print('{"session_id":"stderr-is-not-the-result"}', file=sys.stderr)
            if mode == "quota-fail":
                print("rate limit 429", file=sys.stderr)
                sys.exit(1)
        ''')

    def write(self, path, content):
        with open(path, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)

    def read_json(self, path):
        with open(path, "r", encoding="utf-8") as stream:
            return json.load(stream)

    def install_cli(self, name, body):
        script = os.path.join(self.bin, "fake_{}.py".format(name))
        self.write(script, textwrap.dedent(body))
        if os.name == "nt":
            launcher = os.path.join(self.bin, name + ".cmd")
            self.write(launcher, '@echo off\n"{}" "{}" %*\n'.format(sys.executable, script))
        else:
            launcher = os.path.join(self.bin, name)
            self.write(launcher, '#!/bin/sh\nexec {} {} "$@"\n'.format(shlex.quote(sys.executable), shlex.quote(script)))
            os.chmod(launcher, 0o755)

    def install_fake_eta(self):
        script = os.path.join(self.root, "fake-lane-stats.py")
        self.write(script, textwrap.dedent('''
            import json
            import os
            import sys

            marker = os.environ.get("FAKE_ETA_MARKER")
            if marker:
                with open(marker, "w", encoding="utf-8") as stream:
                    stream.write(json.dumps(sys.argv[1:]))
            mode = os.environ.get("FAKE_ETA_MODE", "estimate")
            if mode == "exit":
                sys.exit(1)
            if mode == "invalid":
                print("not json")
                sys.exit(0)
            print(json.dumps({"arm": "luna/gpt-6-luna/xhigh", "class": "substantive", "tag": None,
                              "minutes": 14.2, "p80_minutes": 25.0, "tier": "measured",
                              "runs": {"arm_class": 9, "arm": 12, "class": 40, "machine": 88}}))
        '''))
        return script

    def fake_cgroup(self, leaf_max=200, leaf_current=30):
        root = os.path.join(self.root, "cgroup")
        proc_cgroup = os.path.join(self.root, "proc-cgroup")
        self.write(proc_cgroup, "0::/fake/job\n")
        levels = (root, os.path.join(root, "fake"), os.path.join(root, "fake", "job"))
        for directory, maximum, current in zip(levels, (2000, 1000, leaf_max), (10, 20, leaf_current)):
            os.makedirs(directory, exist_ok=True)
            self.write(os.path.join(directory, "pids.max"), str(maximum) + "\n")
            self.write(os.path.join(directory, "pids.current"), str(current) + "\n")
        return {"LANES_PROC_CGROUP": proc_cgroup, "LANES_CGROUP_ROOT": root}

    def write_codex_rollout(self, model, usage, session="12345678-1234-1234-1234-123456789abc", error=None):
        day = datetime.datetime.now().astimezone().strftime("%Y/%m/%d")
        home = os.path.join(self.root, "codex-home")
        folder = os.path.join(home, "sessions", day)
        os.makedirs(folder, exist_ok=True)
        earlier = dict(usage, input_tokens=1, cached_input_tokens=0, output_tokens=1,
                       reasoning_output_tokens=0, total_tokens=2)
        events = [
            {"type": "turn_context", "payload": {"model": model}},
            {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": earlier}}},
            {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": usage}}},
        ]
        if error is not None:
            events.append({"type": "event_msg", "payload": {"type": "task_complete", "error": error}})
        path = os.path.join(folder, "rollout-test-{}.jsonl".format(session))
        self.write(path, "".join(json.dumps(event) + "\n" for event in events))
        return home

    def init_git(self):
        result = subprocess.run(["git", "init", self.workspace], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                encoding="utf-8", errors="replace", check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def run_lane(self, name="haiku", extra=(), env=None, script=SCRIPT, effort="xhigh"):
        command = [sys.executable, script, name, "-C", self.workspace, "-b", self.brief]
        if effort:
            command += ["-e", effort]
        return subprocess.run(command + list(extra), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=dict(self.env, **(env or {})), encoding="utf-8", errors="replace",
                              timeout=20, check=False)

    def preview(self, name="haiku", extra=(), effort="xhigh"):
        result = self.run_lane(name, list(extra) + ["--dry-run"], effort=effort)
        self.assertEqual(result.returncode, 0, result.stderr)
        command = json.loads(result.stdout.splitlines()[0].split("argv: ", 1)[1])
        self.assertFalse(os.path.exists(self.state), result.stdout)
        self.assertNotIn("note:", result.stderr)
        return command

    def ledger(self):
        with open(os.path.join(self.state, "ledger.jsonl"), "r", encoding="utf-8") as stream:
            return [json.loads(line) for line in stream]

    def make_unfinished(self, name, lane_name, log_text, final_text=None):
        run_dir = os.path.join(self.state, "runs", name)
        os.makedirs(run_dir)
        started = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=10)).isoformat().replace(
            "+00:00", "Z")
        meta = {"lane": lane_name, "provider": lane.PROVIDERS[lane_name], "model": lane.DEFAULT_MODELS[lane_name],
                "effort": "medium", "class": "mechanical", "tag": None, "pick_id": None, "arm": None,
                "off_catalog": False, "ro": False, "resume": None, "started_at": started, "ended_at": None,
                "duration_s": None, "verdict": None, "exit_code": None, "session_id": None,
                "usage": {"before": None, "after": None, "tokens": None, "list_usd": None}}
        self.write(os.path.join(run_dir, "meta.json"), json.dumps(meta))
        self.write(os.path.join(run_dir, "run.log"), log_text)
        if final_text is not None:
            self.write(os.path.join(run_dir, "final.md"), final_text)
        old = datetime.datetime.now().timestamp() - 300
        for path in (os.path.join(run_dir, "run.log"), os.path.join(run_dir, "final.md")):
            if os.path.exists(path):
                os.utime(path, (old, old))
        return run_dir

    def recover_cli(self, run, *extra):
        return subprocess.run([sys.executable, SCRIPT, "--recover", run] + list(extra), env=self.env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)

    def test_write_meta_waits_out_a_reader_holding_the_file(self):
        path = os.path.join(self.root, "held-meta.json")
        real_replace = os.replace
        calls = []

        def held_twice(source, target):
            calls.append(target)
            if len(calls) <= 2:
                raise PermissionError(5, "Access is denied")
            real_replace(source, target)

        with mock.patch.object(lane.os, "replace", side_effect=held_twice), \
                mock.patch.object(lane.time, "sleep") as sleep:
            lane.write_meta(path, {"verdict": "OK"})
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleep.call_count, 2)
        self.assertEqual(self.read_json(path), {"verdict": "OK"})
        with mock.patch.object(lane.os, "replace", side_effect=PermissionError(5, "Access is denied")), \
                mock.patch.object(lane.time, "sleep"):
            with self.assertRaises(PermissionError):
                lane.write_meta(path, {"verdict": "OK"})

    def test_recover_codex_by_basename_and_append_ledger(self):
        run_dir = self.make_unfinished("recover-codex", "luna",
                                       "session id: 123e4567-e89b-12d3-a456-426614174000\n"
                                       "tokens used\n1,234\n", "Recovered answer\n")
        meta_path = os.path.join(run_dir, "meta.json")
        meta = self.read_json(meta_path)
        meta.update({"eta_s": 852.0, "eta_p80_s": 1500.0, "eta_tier": "measured"})
        self.write(meta_path, json.dumps(meta))
        result = self.recover_cli("recover-codex")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("verdict=OK", result.stdout)
        self.assertIn("recovered=1", result.stdout)
        meta = self.read_json(os.path.join(run_dir, "meta.json"))
        self.assertIsNone(meta["usage"]["tokens"])
        self.assertEqual(meta["usage"]["tokens_error"], "rollout not found")
        self.assertEqual(meta["session_id"], "123e4567-e89b-12d3-a456-426614174000")
        self.assertEqual(meta["usage"]["error"], "recovered: no after-reading")
        self.assertTrue(meta["recovered"])
        self.assertEqual(len(self.ledger()), 1)
        record = self.ledger()[0]
        self.assertEqual(record["eta_s"], 852.0)
        self.assertEqual(record["eta_p80_s"], 1500.0)
        self.assertEqual(record["eta_tier"], "measured")

    def test_recover_claude_json_cost_and_refusals(self):
        run_dir = self.make_unfinished("recover-claude", "sonnet",
                                       json.dumps({"type": "result", "subtype": "success", "session_id": "s-1",
                                                   "result": "done", "total_cost_usd": 0.125,
                                                   "usage": {"input_tokens": 10, "cache_read_input_tokens": 0,
                                                             "output_tokens": 4}}))
        result = self.recover_cli(run_dir)
        self.assertEqual(result.returncode, 0, result.stderr)
        meta = self.read_json(os.path.join(run_dir, "meta.json"))
        self.assertEqual(meta["verdict"], "OK")
        self.assertEqual(meta["usage"]["list_usd"], 0.125)
        self.assertEqual(meta["usage"]["tokens"]["total"], 14)
        self.assertEqual(self.recover_cli(run_dir).returncode, 2)
        self.assertEqual(len(self.ledger()), 1)

        fresh = self.make_unfinished("fresh", "luna", "tokens used\n10\n", "answer")
        path = os.path.join(fresh, "run.log")
        os.utime(path, None)
        refused = self.recover_cli("fresh")
        self.assertEqual(refused.returncode, 2)
        self.assertEqual(len(refused.stderr.splitlines()), 1)
        self.assertIn("--force", refused.stderr)

    def test_retired_names_have_one_line_diagnostic(self):
        for name in ("muse", "prep-muse"):
            for extra in ([], ["--help"], ["unused", "arguments"]):
                with self.subTest(name=name, extra=extra):
                    result = subprocess.run([sys.executable, SCRIPT, name] + extra, env=self.env,
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            encoding="utf-8", check=False)
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stdout, "")
                    self.assertEqual(result.stderr, "lane: {} was retired on 2026-10-17 (see POLICY.md)\n".format(name))

    def test_astra_dry_run_uses_codex_contract(self):
        command = self.preview("astra", ["-e", "max", "--resume", "session-1", "--ro"])
        start = command.index("exec")
        self.assertEqual(command[start:start + 4], ["exec", "--skip-git-repo-check", "-m", "gpt-6-astra"])
        self.assertEqual(command[command.index("-s") + 1], "read-only")
        self.assertIn('approval_policy="never"', command)
        self.assertIn('model_reasoning_effort="max"', command)
        self.assertEqual(command[-3:], ["resume", "session-1", "-"])

    def test_terra_dry_run_uses_codex_contract(self):
        command = self.preview("terra", ["-e", "medium"])
        start = command.index("exec")
        self.assertEqual(command[start:start + 4], ["exec", "--skip-git-repo-check", "-m", "gpt-6.1-terra"])
        self.assertIn('model_reasoning_effort="medium"', command)
        self.assertEqual(lane.PROVIDERS["terra"], "codex")

    def test_claude_dry_runs_use_exact_flags_and_abbreviate_worker_block(self):
        for name, model, effort in (("haiku", "claude-haiku-5-5", "xhigh"),
                                    ("sonnet", "claude-sonnet-5-5", "max"),
                                    ("opus", "claude-opus-5-5", "medium")):
            with self.subTest(name=name):
                command = self.preview(name, ["-e", effort, "--resume", "resume-1"])
                start = command.index("-p")
                self.assertEqual(command[start:], [
                    "-p", "--model", model, "--effort", effort, "--output-format", "stream-json", "--verbose",
                    "--setting-sources", "project,local", "--strict-mcp-config", "--permission-mode", "acceptEdits",
                    "--allowedTools", "Bash", "Read", "Edit", "Write", "Glob", "Grep",
                    "--disallowedTools", "Agent", "Workflow", "WebSearch", "WebFetch",
                    "--append-system-prompt", lane.WORKER_BLOCK[:40] + "...", "--resume", "resume-1"])
                self.assertNotIn("--bare", command)

    def test_haiku_read_only_dry_run(self):
        command = self.preview(extra=["--ro"])
        allowed = command.index("--allowedTools")
        disallowed = command.index("--disallowedTools")
        self.assertEqual(command[allowed + 1:disallowed], ["Read", "Glob", "Grep", "Bash"])
        self.assertEqual(command[disallowed + 1:command.index("--append-system-prompt")],
                         ["Agent", "Workflow", "WebSearch", "WebFetch", "Edit", "Write"])

    def test_claude_web_flag_moves_web_tools_between_allowed_and_disallowed(self):
        for extra, allowed, disallowed in (
                ([], ["Bash", "Read", "Edit", "Write", "Glob", "Grep"], ["Agent", "Workflow", "WebSearch", "WebFetch"]),
                (["--web"], ["Bash", "Read", "Edit", "Write", "Glob", "Grep", "WebSearch", "WebFetch"],
                 ["Agent", "Workflow"]),
                (["--ro", "--web"], ["Read", "Glob", "Grep", "Bash", "WebSearch", "WebFetch"],
                 ["Agent", "Workflow", "Edit", "Write"])):
            for name in ("haiku", "sonnet", "opus"):
                with self.subTest(name=name, extra=extra):
                    command = self.preview(name, extra)
                    self.assertEqual(command[command.index("--allowedTools") + 1:command.index("--disallowedTools")],
                                     allowed)
                    self.assertEqual(command[command.index("--disallowedTools") + 1:command.index("--append-system-prompt")],
                                     disallowed)

    def test_codex_web_flag_adds_only_the_search_config_before_the_subcommand(self):
        for name in lane.CODEX_LANES:
            with self.subTest(name=name):
                effort = "high" if name == "terra" else "xhigh"  # terra xhigh is retired (2026-10-28)
                plain = self.preview(name, ["--outdir", self.outdir], effort)
                web = self.preview(name, ["--web", "--outdir", self.outdir], effort)
                self.assertEqual(web, plain[:-1] + ["-c", 'web_search="live"'] + plain[-1:])
                resumed = self.preview(name, ["--web", "--resume", "session-1"], effort)
                self.assertEqual(resumed[-5:], ["-c", 'web_search="live"', "resume", "session-1", "-"])

    def test_web_is_refused_for_gemini_and_glm_while_their_plain_argv_stays(self):
        for name in ("gemini", "glm"):
            with self.subTest(name=name):
                for extra in (["--web", "--dry-run"], ["--web", "--class", "mechanical"]):
                    result = self.run_lane(name, extra, effort=None)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertEqual(result.stdout, "")
                    self.assertIn("{} cannot take --web".format(name), result.stderr)
                self.assertEqual(self.run_lane(name, ["--dry-run"], effort=None).returncode, 0)
        self.assertFalse(os.path.exists(self.state))

    def test_claude_web_run_records_the_flag_in_meta_and_summary_line(self):
        self.init_git()
        result = self.run_lane(extra=["--web", "--class", "mechanical", "--outdir", self.outdir])
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue(result.stdout.splitlines()[0].endswith(" class=mechanical web"), result.stdout)
        meta = self.read_json(os.path.join(self.outdir, "meta.json"))
        self.assertIs(meta["web"], True)
        command = meta["cmd"]
        allowed = command[command.index("--allowedTools"):command.index("--disallowedTools")]
        self.assertIn("WebSearch", allowed)
        self.assertIn("WebFetch", allowed)

    def test_claude_plain_run_records_web_false_and_no_web_suffix(self):
        self.init_git()
        result = self.run_lane(extra=["--class", "mechanical", "--outdir", self.outdir])
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue(result.stdout.splitlines()[0].endswith(" class=mechanical"), result.stdout)
        meta = self.read_json(os.path.join(self.outdir, "meta.json"))
        self.assertIs(meta["web"], False)
        command = meta["cmd"]
        self.assertIn("WebSearch", command[command.index("--disallowedTools"):])

    def test_codex_web_run_records_the_flag_in_meta_and_summary_line(self):
        self.install_fake_codex()
        result = self.run_lane("luna", ["--web", "--class", "mechanical", "--outdir", self.outdir])
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue(result.stdout.splitlines()[0].endswith(" class=mechanical web"), result.stdout)
        meta = self.read_json(os.path.join(self.outdir, "meta.json"))
        self.assertIs(meta["web"], True)
        self.assertIn('web_search="live"', meta["cmd"])

    def test_retired_arms_are_refused_with_their_reason(self):
        for name, model, reason in (
                ("haiku", "claude-haiku-5-5", "Artificial Analysis v1.5: 36 at $2.58 a task, below xhigh's 41 at $0.61; "
                                              "Suite R 2026-10-20 agrees: no recall gain over xhigh at a higher price"),
                ("sol", "gpt-6.1-sol", "Artificial Analysis v1.5: 60 at $1.55 a task, below xhigh's 63 at $1.04; "
                                       "Suite R 2026-10-20 agrees: no recall gain over xhigh at a higher price")):
            with self.subTest(name=name):
                result = self.run_lane(name, ["-e", "max", "--dry-run"])
                self.assertEqual(result.returncode, 8, result.stderr)
                self.assertEqual(result.stderr, "lane: {} max ({}) is retired: {}; pass --off-catalog to run it anyway\n".format(
                    name, model, reason))
        self.assertFalse(os.path.exists(self.state))

    def test_absent_arm_is_refused_until_off_catalog(self):
        self.init_git()
        result = self.run_lane("sonnet", ["-e", "low", "--dry-run"])
        self.assertEqual(result.returncode, 8, result.stderr)
        self.assertEqual(result.stderr, "lane: sonnet low (claude-sonnet-5-5) is not in the arms catalog; "
                                        "add it to ~/.config/lanes/arms.local.json or pass --off-catalog\n")
        result = self.run_lane("sonnet", ["-e", "low", "--class", "mechanical", "--off-catalog", "--outdir", self.outdir])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        record = self.ledger()[-1]
        self.assertIs(record["off_catalog"], True)
        self.assertIsNone(record["arm"])

    def test_off_catalog_runs_a_retired_arm_and_records_the_arm(self):
        self.init_git()
        result = self.run_lane(extra=["-e", "max", "--off-catalog", "--outdir", self.outdir])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("lane=haiku verdict=OK", result.stdout)
        record = self.ledger()[-1]
        self.assertIs(record["off_catalog"], True)
        self.assertEqual(record["arm"], "haiku/claude-haiku-5-5/max")

    def test_manual_wildcard_arm_allows_any_luna_effort(self):
        for effort in ("low", "medium", "high", "xhigh", "max"):
            with self.subTest(effort=effort):
                command = self.preview("luna", ["--model", "gpt-5.6-luna", "-e", effort])
                self.assertEqual(command[command.index("-m") + 1], "gpt-5.6-luna")
        result = self.run_lane("luna", ["--model", "gpt-9", "--dry-run"])
        self.assertEqual(result.returncode, 8)
        self.assertIn("lane: luna xhigh (gpt-9) is not in the arms catalog", result.stderr)

    def test_gemini_effort_is_inferred_from_the_model_suffix(self):
        for model, code in (("gemini-3.8-flash-high", 0), ("gemini-3.8-flash-medium", 0), ("gemini-3.8-flash-xhigh", 8)):
            with self.subTest(model=model):
                result = self.run_lane("gemini", ["--model", model, "--dry-run"], effort=None)
                self.assertEqual(result.returncode, code, result.stderr)
                if code:
                    self.assertIn("lane: gemini xhigh ({}) is not in the arms catalog".format(model), result.stderr)

    def test_missing_catalog_warns_and_keeps_built_in_refusals(self):
        missing = os.path.join(self.root, "missing-arms.json")
        result = self.run_lane(extra=["-e", "max", "--dry-run"], env={"LANES_ARMS": missing})
        self.assertEqual(result.returncode, 2, result.stderr)
        first = result.stderr.splitlines()[0]
        self.assertTrue(first.startswith("lane: arms catalog unavailable (cannot read {}: ".format(missing)), first)
        self.assertTrue(first.endswith("); using built-in defaults"), first)
        self.assertIn("haiku effort must be low, medium, high, or xhigh", result.stderr)
        result = self.run_lane("haiku", ["--model", "wrong-model", "--dry-run"], env={"LANES_ARMS": missing})
        self.assertEqual(result.returncode, 8, result.stderr)
        self.assertIn("haiku model must be claude-haiku-5-5", result.stderr)
        without_arms = os.path.join(self.root, "without-arms.json")
        self.write(without_arms, '{"lanes": {}}\n')
        result = self.run_lane("haiku", ["--dry-run"], env={"LANES_ARMS": without_arms})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr.splitlines()[0], "lane: arms catalog unavailable ({} has no arms list); "
                                                        "using built-in defaults".format(without_arms))

    def test_local_catalog_overrides_matching_arms_and_appends_new_ones(self):
        local = os.path.join(self.root, "local-arms.json")
        self.write(local, json.dumps({"arms": [
            {"lane": "haiku", "model": "claude-haiku-5-5", "effort": "xhigh", "status": "retired", "reason": "local retirement"},
            {"lane": "haiku", "model": "claude-haiku-5-5", "effort": "max", "status": "active"},
            {"lane": "sonnet", "model": "claude-sonnet-5-5", "effort": "low", "status": "active"}]}))
        env = {"LANES_ARMS_LOCAL": local}
        result = self.run_lane("haiku", ["--dry-run"], env=env)
        self.assertEqual(result.returncode, 8, result.stderr)
        self.assertIn("lane: haiku xhigh (claude-haiku-5-5) is retired: local retirement; ", result.stderr)
        result = self.run_lane("haiku", ["--dry-run"], env=env, effort="max")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.run_lane("sonnet", ["--dry-run"], env=env, effort="low")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_pick_is_recorded_in_meta_and_ledger(self):
        self.init_git()
        result = self.run_lane(extra=["--pick", "p-test", "--outdir", self.outdir])
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        meta = self.read_json(os.path.join(self.outdir, "meta.json"))
        self.assertEqual(meta["pick_id"], "p-test")
        self.assertEqual(meta["arm"], "haiku/claude-haiku-5-5/xhigh")
        self.assertIs(meta["off_catalog"], False)
        self.assertEqual(self.ledger()[-1]["pick_id"], "p-test")

    def test_pick_must_be_a_short_identifier(self):
        for value in ("", "has space", "slash/id", "x" * 65):
            with self.subTest(value=value):
                result = self.run_lane(extra=["--pick", value, "--dry-run"])
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("argument --pick", result.stderr)
        self.preview(extra=["--pick", "x" * 64])

    def test_new_lanes_only_accept_their_pinned_model(self):
        for name in ("terra", "astra", "haiku", "sonnet", "opus"):
            with self.subTest(name=name):
                result = self.run_lane(name, ["--model", "wrong-model", "--dry-run"])
                self.assertEqual(result.returncode, 8)
                self.assertIn("lane: {} xhigh (wrong-model) is not in the arms catalog".format(name), result.stderr)
                self.preview(name, ["--model", lane.DEFAULT_MODELS[name]], "high" if name == "terra" else "xhigh")

    def test_real_claude_edit_records_meta_and_one_ledger_line(self):
        self.init_git()
        result = self.run_lane(extra=["--class", "mechanical", "--tag", "pair-1", "--outdir", self.outdir,
                                      "--resume", "resume-1"])
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("lane=haiku verdict=OK", result.stdout)
        self.assertIn("class=mechanical", result.stdout)
        self.assertIn("done edit", result.stdout)
        self.assertEqual(without_mode_line(result.stderr), "")
        with open(os.path.join(self.outdir, "final.md"), "r", encoding="utf-8") as stream:
            self.assertEqual(stream.read(), "done edit\n")
        meta = self.read_json(os.path.join(self.outdir, "meta.json"))
        self.assertEqual(meta["provider"], "claude")
        self.assertEqual(meta["session_id"], "claude-test-session")
        self.assertEqual(meta["resume"], "resume-1")
        self.assertEqual(meta["usage"], {"before": None, "after": None, "error": "disabled", "list_usd": 0.125,
                                        "tokens": {"input": 18, "cached": 100, "output": 5, "total": 123}})
        self.assertIn(lane.WORKER_BLOCK, meta["cmd"])
        capture = self.read_json(self.capture)
        # The parent session's CLAUDE_CODE_* variables are dropped; only the auto-memory switch is set.
        self.assertEqual(capture["nested_env"], ["CLAUDE_CODE_DISABLE_AUTO_MEMORY"])
        self.assertEqual(capture["keep"], "preserved")
        with open(self.brief, "r", encoding="utf-8") as stream:
            self.assertEqual(capture["brief"], stream.read())
        records = self.ledger()
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["run_dir"], self.outdir)
        self.assertEqual(record["class"], "mechanical")
        self.assertEqual(record["tag"], "pair-1")
        self.assertEqual(set(record), {"run_dir", "lane", "provider", "model", "effort", "class", "tag", "pick_id",
                                       "arm", "off_catalog", "ro", "resume", "started_at", "ended_at", "duration_s",
                                       "verdict", "exit_code", "session_id", "usage", "eta_s", "eta_p80_s", "eta_tier",
                                       "place", "brief_bytes", "peak_mem_mb", "mode", "platform"})
        for key in record:
            if key != "run_dir":
                self.assertEqual(record[key], meta[key])
        self.assertTrue(record["started_at"].endswith("Z"))
        self.assertTrue(record["ended_at"].endswith("Z"))

    def test_claude_commit_is_not_noop(self):
        self.init_git()
        self.write(os.path.join(self.workspace, "base.txt"), "base\n")
        subprocess.run(["git", "-C", self.workspace, "add", "base.txt"], check=True)
        subprocess.run(["git", "-C", self.workspace, "-c", "user.name=test", "-c", "user.email=test@localhost",
                        "commit", "-m", "base"], check=True, stdout=subprocess.PIPE)
        result = self.run_lane(env={"FAKE_MODE": "commit"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("verdict=OK", result.stdout)
        self.assertEqual(self.ledger()[-1]["verdict"], "OK")

    def test_new_file_in_untracked_workspace_is_not_noop(self):
        subprocess.run(["git", "init", self.root], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(["git", "-C", self.root, "-c", "user.name=test", "-c", "user.email=test@localhost",
                        "commit", "--allow-empty", "-m", "base"], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        result = self.run_lane()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("verdict=OK", result.stdout)
        self.assertEqual(self.ledger()[-1]["verdict"], "OK")

    def test_quota_and_failed_runs_are_also_in_the_ledger(self):
        for mode, verdict, code in (("quota", "QUOTA", 75), ("quota-fail", "QUOTA", 75), ("failed", "FAILED", 4)):
            with self.subTest(mode=mode):
                result = self.run_lane(extra=["--outdir", os.path.join(self.root, mode)], env={"FAKE_MODE": mode})
                self.assertEqual(result.returncode, code, result.stderr + result.stdout)
                record = self.ledger()[-1]
                self.assertEqual(record["verdict"], verdict)
                self.assertEqual(record["class"], None)
                self.assertIn("class=-", result.stdout)
                self.assertEqual(without_mode_line(result.stderr), "note: pass --class so lane-stats can compare lanes\n")
        self.assertEqual(len(self.ledger()), 3)

    def test_claude_error_result_with_429_inside_request_id_is_failed(self):
        result = self.run_lane(env={"FAKE_MODE": "failed-429"})
        self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
        self.assertIn("verdict=FAILED", result.stdout)
        self.assertEqual(self.ledger()[-1]["verdict"], "FAILED")

    def test_noop_compares_initial_status_and_read_only_briefs_go_on_stdin(self):
        self.init_git()
        self.write(os.path.join(self.workspace, "already-dirty.txt"), "existing change\n")
        result = self.run_lane(env={"FAKE_MODE": "noop"})
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertEqual(self.ledger()[-1]["verdict"], "NOOP")
        long_brief = "Unicode \u03bb, quote \" and percent % & backslash \\ end.\n" * 2000
        self.write(self.brief, long_brief)
        result = self.run_lane("sonnet", ["--ro", "--class", "review"], env={"FAKE_MODE": "noop"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        capture = self.read_json(self.capture)
        self.assertEqual(capture["brief"], "READ-ONLY UNIT: do not modify any file.\n" + long_brief)
        self.assertLess(lane.windows_command_line_length(capture["argv"]), lane.WINDOWS_COMMAND_LINE_LIMIT)
        record = self.ledger()[-1]
        self.assertTrue(record["ro"])
        self.assertEqual(record["verdict"], "OK")
        self.assertTrue(record["run_dir"].startswith(os.path.join(self.state, "runs") + os.sep))

    def test_timeout_records_final_meta_and_ledger(self):
        result = self.run_lane(extra=["--timeout", "1"], env={"FAKE_MODE": "timeout"})
        self.assertEqual(result.returncode, 124, result.stdout + result.stderr)
        record = self.ledger()[0]
        self.assertEqual(record["verdict"], "TIMEOUT")
        self.assertIsNone(record["usage"]["tokens"])

    def test_real_run_reads_both_usage_snapshots_from_preferred_sibling(self):
        self.init_git()
        copied = os.path.join(self.bin, "lane")
        shutil.copyfile(SCRIPT, copied)
        self.write(os.path.join(self.bin, "usage-status"), "raise RuntimeError('wrong sibling')\n")
        self.write(os.path.join(self.bin, "usage-status.py"), textwrap.dedent('''
            import json
            import os
            import sys
            path = os.path.join(os.environ["LANES_STATE"], "usage-calls.jsonl")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as stream:
                stream.write(json.dumps(sys.argv[1:]) + "\\n")
            with open(path, encoding="utf-8") as stream:
                count = len(stream.readlines())
            print(json.dumps({"claude": {"reading": {"observed_at": "2026-10-17T01:02:03Z"},
                "age_seconds": 2, "stale": False, "windows": {
                    "five_hour": {"used_percentage": count, "resets_at": "2026-10-17T05:00:00Z"},
                    "seven_day": {"used_percentage": count + 10, "resets_at": "2026-10-23T05:00:00Z"}}}}))
        '''))
        result = self.run_lane(script=copied, env={"LANE_NO_USAGE": "0"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        usage = self.ledger()[0]["usage"]
        self.assertNotIn("error", usage)
        self.assertEqual(usage["before"]["windows"][0]["used_percent"], 1.0)
        self.assertEqual(usage["after"]["windows"][0]["used_percent"], 2.0)
        self.assertEqual([item["label"] for item in usage["after"]["windows"]], ["5h", "weekly"])
        self.assertEqual(usage["before"]["observed_at"], "2026-10-17T01:02:03Z")
        self.assertEqual(usage["after"]["age_seconds"], 2)
        with open(os.path.join(self.state, "usage-calls.jsonl"), encoding="utf-8") as stream:
            self.assertEqual([json.loads(line) for line in stream], [["--json", "--no-agy"]] * 2)

    def test_meter_failures_do_not_change_real_worker_verdict_or_exit_code(self):
        self.init_git()
        copied = os.path.join(self.bin, "lane")
        shutil.copyfile(SCRIPT, copied)
        self.write(os.path.join(self.bin, "usage-status"), textwrap.dedent('''
            import os
            import sys
            with open(os.path.join(os.environ["LANES_STATE"], "meter-calls"), "a") as stream:
                stream.write("called\\n")
            sys.exit(7)
        '''))
        result = self.run_lane(script=copied, env={"LANE_NO_USAGE": "0"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        record = self.ledger()[0]
        self.assertEqual(record["verdict"], "OK")
        self.assertEqual(record["usage"]["error"], "usage-status exited 7")
        self.assertIsNone(record["usage"]["before"])
        self.assertIsNone(record["usage"]["after"])
        self.assertEqual(record["usage"]["tokens"]["total"], 123)
        with open(os.path.join(self.state, "meter-calls")) as stream:
            self.assertEqual(stream.read(), "called\ncalled\n")

    def install_fake_codex(self):
        self.install_cli("codex", '''
            import os
            import sys
            if "--version" in sys.argv:
                print("codex-cli 0.159.1")
                sys.exit(0)
            mode = os.environ.get("FAKE_MODE")
            brief = sys.stdin.read()
            session = "12345678-1234-4290-1234-123456789abc" if mode == "session-429" else \
                      "12345678-1234-1234-1234-123456789abc"
            print("session id: " + session, file=sys.stderr)
            print("tokens used\\n12,345", file=sys.stderr)
            if mode == "quota":
                print("ERROR: You've hit your usage limit ... try again at 6:53 PM", file=sys.stderr)
            else:
                final_message = ("ERROR: You've hit your usage limit ... try again at 6:53 PM"
                                 if mode == "mentions-limit" else "completed")
                with open(sys.argv[sys.argv.index("-o") + 1], "w", encoding="utf-8") as stream:
                    stream.write(final_message + "\\n")
                if mode == "mentions-limit":
                    print(final_message, file=sys.stderr)
                if mode == "echoed-tool-output":
                    print('print("usage limit reached", file=sys.stderr)', file=sys.stderr)
                    print('+    final_message = "the usage limit is 95%" if mode == "mentions-limit" else "completed"',
                          file=sys.stderr)
        ''')

    def test_codex_plan_is_recorded_in_both_usage_snapshots(self):
        self.init_git()
        self.install_fake_codex()
        copied = os.path.join(self.bin, "lane")
        shutil.copyfile(SCRIPT, copied)
        self.write(os.path.join(self.bin, "usage-status.py"), textwrap.dedent('''
            import json
            print(json.dumps({"codex": {"status": "ok", "age_seconds": 2, "plan_type": "prolite",
                "reading": {"timestamp": "2026-10-17T01:02:03Z"},
                "windows": [{"label": "weekly", "used_percent": 12, "resets_at": "2026-10-23T11:25:25Z"}]}}))
        '''))
        result = self.run_lane("luna", ["--outdir", self.outdir], script=copied, env={"LANE_NO_USAGE": "0"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        usage = self.ledger()[0]["usage"]
        for snapshot in (usage["before"], usage["after"]):
            self.assertEqual(snapshot["plan"], "prolite")
            self.assertEqual(snapshot["windows"][0]["used_percent"], 12.0)

    def test_astra_real_run_reuses_codex_session_quota_and_token_rules(self):
        self.install_fake_codex()
        for mode, code, verdict in (("edit", 0, "OK"), ("quota", 75, "QUOTA")):
            result = self.run_lane("astra", ["--outdir", os.path.join(self.root, mode)], env={"FAKE_MODE": mode})
            self.assertEqual(result.returncode, code, result.stdout + result.stderr)
            self.assertEqual(result.stderr.count("note: astra draws about 5x sol per token from the Codex weekly window\n"), 1)
            record = self.ledger()[-1]
            self.assertEqual(record["verdict"], verdict)
            self.assertEqual(record["provider"], "codex")
            self.assertEqual(record["session_id"], "12345678-1234-1234-1234-123456789abc")
            self.assertIsNone(record["usage"]["tokens"])
            self.assertEqual(record["usage"]["tokens_error"], "rollout not found")

    def test_codex_final_message_quoting_error_line_is_not_quota(self):
        self.install_fake_codex()
        result = self.run_lane("luna", ["--outdir", self.outdir], env={"FAKE_MODE": "mentions-limit"})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("verdict=OK", result.stdout)
        self.assertEqual(self.ledger()[-1]["verdict"], "OK")

    def test_codex_rollout_usage_limit_error_is_quota(self):
        self.install_fake_codex()
        usage = {"input_tokens": 10, "cached_input_tokens": 2, "output_tokens": 3,
                 "reasoning_output_tokens": 1, "total_tokens": 13}
        code_home = self.write_codex_rollout(
            "gpt-6.1-sol", usage,
            error={"message": "provider quota stop", "codex_error_info": "usage_limit_exceeded"})
        result = self.run_lane("luna", ["--outdir", self.outdir],
                               env={"CODEX_HOME": code_home, "FAKE_MODE": "edit"})
        self.assertEqual(result.returncode, 75, result.stdout + result.stderr)
        self.assertIn("verdict=QUOTA", result.stdout)
        self.assertEqual(self.ledger()[-1]["verdict"], "QUOTA")

    def test_codex_error_line_without_rollout_is_quota(self):
        self.install_fake_codex()
        result = self.run_lane("luna", ["--outdir", self.outdir], env={"FAKE_MODE": "quota"})
        self.assertEqual(result.returncode, 75, result.stdout + result.stderr)
        self.assertIn("verdict=QUOTA", result.stdout)
        self.assertEqual(self.ledger()[-1]["verdict"], "QUOTA")

    def test_codex_echoed_tool_output_with_normal_rollout_is_ok(self):
        self.install_fake_codex()
        usage = {"input_tokens": 10, "cached_input_tokens": 2, "output_tokens": 3,
                 "reasoning_output_tokens": 1, "total_tokens": 13}
        code_home = self.write_codex_rollout("gpt-6.1-sol", usage)
        result = self.run_lane("luna", ["--outdir", self.outdir],
                               env={"CODEX_HOME": code_home, "FAKE_MODE": "echoed-tool-output"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("verdict=OK", result.stdout)
        self.assertEqual(self.ledger()[-1]["verdict"], "OK")
        with open(os.path.join(self.outdir, "run.log"), "r", encoding="utf-8") as stream:
            log_text = stream.read()
        self.assertIn('print("usage limit reached", file=sys.stderr)', log_text)
        self.assertIn('+    final_message = "the usage limit is 95%"', log_text)

    def test_codex_session_id_containing_429_is_not_quota(self):
        self.install_fake_codex()
        result = self.run_lane("luna", ["--outdir", self.outdir], env={"FAKE_MODE": "session-429"})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        record = self.ledger()[-1]
        self.assertEqual(record["verdict"], "OK")
        self.assertEqual(record["session_id"], "12345678-1234-4290-1234-123456789abc")

    def test_gemini_stderr_quota_phrases_are_anchored(self):
        success = json.dumps({"status": "SUCCESS", "response": "done"})
        for stderr in ("Generating response…", "rate of change"):
            with self.subTest(stderr=stderr):
                verdict, code, _ = lane.decide_verdict(
                    "gemini", 0, False, "", self.outdir, self.workspace,
                    stdout_text=success, stderr_text=stderr)
                self.assertEqual((verdict, code), ("OK", 0))

        verdict, code, _ = lane.decide_verdict(
            "gemini", 0, False, "", self.outdir, self.workspace,
            stdout_text=success, stderr_text="429 Too Many Requests")
        self.assertEqual((verdict, code), ("QUOTA", 75))

    def test_gemini_structured_quota_keeps_specific_strings_and_numeric_code(self):
        self.assertTrue(lane.gemini_structured_quota({"status": "RESOURCE_EXHAUSTED"}))
        self.assertTrue(lane.gemini_structured_quota({"error": {"code": 429}}))
        self.assertFalse(lane.gemini_structured_quota({"error": {"message": "rate of change"}}))

    def test_codex_rollout_records_tokens_model_and_hand_calculated_credits(self):
        self.install_fake_codex()
        usage = {"input_tokens": 237096, "cached_input_tokens": 198272, "cache_write_input_tokens": 0,
                 "output_tokens": 1481, "reasoning_output_tokens": 507, "total_tokens": 238577}
        code_home = self.write_codex_rollout("gpt-6.1-sol", usage)
        result = self.run_lane("sol", ["--class", "hard", "--outdir", self.outdir], env={"CODEX_HOME": code_home})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        recorded = self.read_json(os.path.join(self.outdir, "meta.json"))["usage"]
        self.assertEqual(recorded["tokens"], {"input": 237096, "cached_input": 198272,
                                               "output": 1481, "reasoning_output": 507})
        self.assertEqual(recorded["model_observed"], "gpt-6.1-sol")
        # Fresh input is 38,824; 38,824*50 + 198,272*2.5 + 1,481*250 = 2,807,130 credits.
        # Divide by 1,000,000 for 2.80713 credits, then multiply by $0.04 for $0.1122852 list cost.
        self.assertEqual(recorded["credits"], 2.80713)
        self.assertEqual(recorded["list_usd"], 0.1122852)
        self.assertNotIn("tokens_error", recorded)

    def test_codex_missing_rollout_records_tokens_error(self):
        self.install_fake_codex()
        result = self.run_lane("sol", ["--class", "hard", "--outdir", self.outdir])
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        recorded = self.read_json(os.path.join(self.outdir, "meta.json"))["usage"]
        self.assertIsNone(recorded["tokens"])
        self.assertIsNone(recorded["credits"])
        self.assertIsNone(recorded["list_usd"])
        self.assertEqual(recorded["tokens_error"], "rollout not found")

    def test_codex_unknown_rollout_model_records_tokens_error(self):
        self.install_fake_codex()
        usage = {"input_tokens": 10, "cached_input_tokens": 2, "output_tokens": 3,
                 "reasoning_output_tokens": 1, "total_tokens": 13}
        code_home = self.write_codex_rollout("gpt-unlisted", usage)
        result = self.run_lane("sol", ["--class", "hard", "--outdir", self.outdir], env={"CODEX_HOME": code_home})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        recorded = self.read_json(os.path.join(self.outdir, "meta.json"))["usage"]
        self.assertIsNone(recorded["tokens"])
        self.assertIsNone(recorded["credits"])
        self.assertEqual(recorded["model_observed"], "gpt-unlisted")
        self.assertEqual(recorded["tokens_error"], "model absent from rate card")

    def test_cgroup_headroom_allows_worker_launch(self):
        env = self.fake_cgroup(leaf_max=200, leaf_current=30)
        result = self.run_lane("haiku", ["--class", "mechanical", "--outdir", self.outdir], env=env)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue(os.path.isfile(self.capture))
        self.assertIn("lane=haiku verdict=OK", result.stdout)

    def test_cgroup_shortage_returns_busy_and_writes_meta(self):
        env = dict(self.fake_cgroup(leaf_max=50, leaf_current=20), LANES_PIDS_WAIT="0")
        result = self.run_lane("haiku", ["--class", "mechanical", "--outdir", self.outdir], env=env)
        self.assertEqual(result.returncode, 70, result.stderr + result.stdout)
        self.assertIn("lane=haiku verdict=BUSY exit=70", result.stdout)
        self.assertEqual(len(without_mode_line(result.stderr).splitlines()), 1)
        meta = self.read_json(os.path.join(self.outdir, "meta.json"))
        self.assertEqual(meta["verdict"], "BUSY")
        self.assertEqual(meta["exit_code"], 70)
        self.assertEqual(self.ledger()[0]["verdict"], "BUSY")
        self.assertFalse(os.path.exists(self.capture))

    def test_dry_run_prints_headroom_without_waiting(self):
        env = dict(self.fake_cgroup(leaf_max=25, leaf_current=20), LANES_PIDS_WAIT="0")
        result = self.run_lane("haiku", ["--dry-run"], env=env)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("task headroom: 5; reserve: 40", result.stdout)
        self.assertEqual(result.stderr, "")

    def memory_env(self, **values):
        return mock.patch.dict(os.environ, dict({"LANES_STATE": self.state, "LANES_MEM_CHECK": "on"}, **values))

    def peak_rows(self, lane_name, peaks):
        return [{"lane": lane_name, "peak_mem_mb": peak} for peak in peaks]

    def test_memory_need_from_measured_prior_default_and_env(self):
        config = lane.memory_config(None)
        records = (self.peak_rows("luna", [300, 500, 410]) + self.peak_rows("sol", [9000, 9000, 9000]) +
                   self.peak_rows("luna", [None, 0, True, "800"]))
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LANES_MEM_NEED_MB", None)
            self.assertEqual(lane.memory_need("luna", records, config), (410, "measured", 3))
            self.assertEqual(lane.memory_need("luna", records, dict(config, recent_runs=2)), (400, "prior", 2))
            self.assertEqual(lane.memory_need("haiku", records, config), (700, "prior", 0))
            self.assertEqual(lane.memory_need("unlisted", records, config), (700, "default", 0))
            os.environ["LANES_MEM_NEED_MB"] = "900"
            self.assertEqual(lane.memory_need("luna", records, config), (900, "env", 0))
            os.environ["LANES_MEM_NEED_MB"] = "0"
            with self.assertRaises(lane.LaneError) as caught:
                lane.memory_need("luna", records, config)
            self.assertEqual(caught.exception.code, 8)

    def test_ledger_records_skip_lines_that_are_not_json_objects(self):
        os.makedirs(self.state)
        self.write(os.path.join(self.state, "ledger.jsonl"),
                   'not json\n[1]\n{"lane": "luna", "peak_mem_mb": 300}\n')
        with self.memory_env():
            self.assertEqual(lane.ledger_records(), [{"lane": "luna", "peak_mem_mb": 300}])

    def test_memory_reserve_from_catalog_and_env(self):
        with mock.patch.dict(os.environ, {"LANES_ARMS": os.path.join(ROOT, "arms.json"),
                                          "LANES_ARMS_LOCAL": os.path.join(self.root, "no-local-arms.json")}):
            os.environ.pop("LANES_MEM_RESERVE_MB", None)
            config = lane.memory_config(lane.load_catalog())
            self.assertEqual(lane.memory_reserve(16264, config), 1626)
            self.assertEqual(lane.memory_reserve(8000, config), 1536)
            custom = lane.memory_config({"explore": {"memory": {"reserve_mb": 2048, "lane_mb": {"luna": 300}}}})
            self.assertEqual(lane.memory_reserve(8000, custom), 2048)
            self.assertEqual(custom["lane_mb"]["luna"], 300)
            self.assertEqual(custom["lane_mb"]["haiku"], 700)
            os.environ["LANES_MEM_RESERVE_MB"] = "0"
            self.assertEqual(lane.memory_reserve(16264, config), 0)
            os.environ["LANES_MEM_RESERVE_MB"] = "-1"
            with self.assertRaises(lane.LaneError):
                lane.memory_reserve(16264, config)

    def make_run(self, age_seconds, lane_name="luna", ended=False, stamp_age=None, launched="absent"):
        now = datetime.datetime.now(datetime.timezone.utc)
        stamp = now - datetime.timedelta(seconds=age_seconds if stamp_age is None else stamp_age)
        run_dir = os.path.join(self.state, "runs", "{}-{}-ws-{}".format(
            stamp.strftime("%Y%m%d-%H%M%S"), lane_name, uuid.uuid4().hex[:6]))
        os.makedirs(run_dir)
        started = (now - datetime.timedelta(seconds=age_seconds)).isoformat(timespec="seconds").replace("+00:00", "Z")
        meta = {"lane": lane_name, "started_at": started, "ended_at": started if ended else None}
        if launched != "absent":
            meta["launched_at"] = None if launched is None else (now - datetime.timedelta(seconds=launched)).isoformat(
                timespec="seconds").replace("+00:00", "Z")
        self.write(os.path.join(run_dir, "meta.json"), json.dumps(meta))
        return run_dir

    def test_young_runs_count_from_launch_and_skip_waiting_runs(self):
        config = lane.memory_config(None)
        self.make_run(200, "luna", launched=10)
        self.make_run(20, "haiku", launched=None)
        self.make_run(20, "haiku", launched=200)
        with self.memory_env():
            os.environ.pop("LANES_MEM_NEED_MB", None)
            self.assertEqual(lane.young_runs_mb([], config), 400)

    def test_young_runs_count_only_recent_unfinished_runs_of_others(self):
        config = lane.memory_config(None)
        own = self.make_run(5, "haiku")
        self.make_run(10, "luna")
        self.make_run(30, "haiku")
        self.make_run(300, "luna")
        self.make_run(10, "luna", ended=True)
        self.make_run(10, "luna", stamp_age=900)
        os.makedirs(os.path.join(self.state, "runs", "not-a-run"))
        with self.memory_env():
            os.environ.pop("LANES_MEM_NEED_MB", None)
            self.assertEqual(lane.young_runs_mb([], config, own), 400 + 700)
            self.assertEqual(lane.young_runs_mb([], config), 400 + 700 + 700)

    def test_memory_line_and_busy_message(self):
        own = self.make_run(1, "haiku")
        self.make_run(5, "luna")
        with self.memory_env(LANES_MEM_FAKE="2500:16264", LANES_MEM_WAIT="0"):
            for name in ("LANES_MEM_NEED_MB", "LANES_MEM_RESERVE_MB"):
                os.environ.pop(name, None)
            fit = lane.memory_fit("haiku", None, own)
            self.assertEqual(lane.memory_line(fit), "lane: memory 2,500 MB available of 16,264 (reserve 1,626, "
                                                    "starting runs 400) | needs ~700 MB (prior, n=0) | fits 0")
            with self.assertRaises(lane.LaneError) as caught:
                lane.wait_for_memory("haiku", None, own)
            self.assertEqual((caught.exception.code, caught.exception.verdict), (70, "BUSY"))
            self.assertEqual(str(caught.exception), "memory: 2,500 MB available, 1,626 reserved, 400 held for starting "
                                                    "runs; this run needs ~700 MB (prior); wait for running lanes or "
                                                    "lower LANES_MEM_RESERVE_MB")
            os.environ["LANES_MEM_WAIT"] = "soon"
            with self.assertRaises(lane.LaneError) as caught:
                lane.wait_for_memory("haiku", None, own)
            self.assertEqual(caught.exception.code, 8)
            os.environ["LANES_MEM_CHECK"] = "off"
            self.assertIsNone(lane.wait_for_memory("haiku", None, own))
        with self.memory_env(LANES_MEM_FAKE="unknown"):
            self.assertIsNone(lane.memory_snapshot())
            self.assertIsNone(lane.wait_for_memory("haiku", None, own))
            self.assertEqual(lane.memory_line(None), "lane: memory unknown on this OS")

    def test_memory_shortage_returns_busy_and_writes_meta(self):
        env = {"LANES_MEM_CHECK": "on", "LANES_MEM_FAKE": "100:16000", "LANES_MEM_WAIT": "0"}
        result = self.run_lane("haiku", ["--class", "mechanical", "--outdir", self.outdir], env=env)
        self.assertEqual(result.returncode, 70, result.stderr + result.stdout)
        self.assertIn("lane=haiku verdict=BUSY exit=70", result.stdout)
        self.assertIn("lane: memory 100 MB available of 16,000", result.stderr)
        meta = self.read_json(os.path.join(self.outdir, "meta.json"))
        self.assertEqual((meta["verdict"], meta["exit_code"], meta["peak_mem_mb"]), ("BUSY", 70, None))
        self.assertEqual(self.ledger()[0]["verdict"], "BUSY")
        self.assertFalse(os.path.exists(self.capture))

    def test_enough_memory_or_check_off_starts_the_worker(self):
        for env in ({"LANES_MEM_CHECK": "on", "LANES_MEM_FAKE": "60000:64000", "LANES_MEM_WAIT": "0"},
                    {"LANES_MEM_CHECK": "off", "LANES_MEM_FAKE": "100:16000", "LANES_MEM_WAIT": "0"}):
            with self.subTest(env=env):
                for path in (self.capture, os.path.join(self.workspace, "worker.txt")):
                    if os.path.exists(path):
                        os.remove(path)
                result = self.run_lane("haiku", ["--class", "mechanical"], env=env)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                self.assertTrue(os.path.isfile(self.capture))
                self.assertNotIn("lane: memory", result.stderr)
                newest = max(glob.glob(os.path.join(self.state, "runs", "*", "meta.json")), key=os.path.getmtime)
                self.assertTrue(self.read_json(newest)["launched_at"])

    def test_dry_run_prints_the_memory_line(self):
        result = self.run_lane("haiku", ["--dry-run"], env={"LANES_MEM_FAKE": "6312:16264"})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("lane: memory 6,312 MB available of 16,264 (reserve 1,626, starting runs 0) | "
                      "needs ~700 MB (prior, n=0) | fits 6", result.stdout)
        result = self.run_lane("haiku", ["--dry-run"], env={"LANES_MEM_FAKE": "bad"})
        self.assertIn("lane: memory unknown on this OS", result.stdout)

    def fake_memory_tree(self, leaf_max, leaf_current):
        root = os.path.join(self.root, "cgroup")
        proc_cgroup = os.path.join(self.root, "proc-cgroup")
        self.write(proc_cgroup, "0::/fake/job\n")
        leaf = os.path.join(root, "fake", "job")
        os.makedirs(leaf)
        self.write(os.path.join(root, "memory.max"), "max\n")
        self.write(os.path.join(root, "memory.current"), "1\n")
        # The middle level has no memory files, like a cgroup without the memory controller enabled.
        self.write(os.path.join(leaf, "memory.max"), str(leaf_max) + "\n")
        self.write(os.path.join(leaf, "memory.current"), str(leaf_current) + "\n")
        meminfo = os.path.join(self.root, "meminfo")
        self.write(meminfo, "MemTotal:       16000000 kB\nMemFree:         1000000 kB\n"
                            "MemAvailable:    8000000 kB\nBuffers:          100000 kB\n")
        return {"LANES_PROC_CGROUP": proc_cgroup, "LANES_CGROUP_ROOT": root, "LANES_MEMINFO": meminfo}

    def test_meminfo_and_a_smaller_cgroup_memory_max(self):
        mib = 1024 * 1024
        env = self.fake_memory_tree(2048 * mib, 512 * mib)
        with mock.patch.dict(os.environ, env):
            self.assertEqual(lane.linux_memory_snapshot(), {"available_mb": 1536, "total_mb": 2048, "source": "cgroup"})
        with mock.patch.dict(os.environ, dict(env, LANES_PROC_CGROUP=os.path.join(self.root, "absent"))):
            self.assertEqual(lane.linux_memory_snapshot(), {"available_mb": 7812, "total_mb": 15625, "source": "meminfo"})

    @unittest.skipUnless(os.name == "nt" or sys.platform.startswith("linux"), "peak memory is measured on Windows and Linux")
    def test_worker_peak_memory_is_recorded(self):
        self.install_cli("claude", '''
            import json
            import sys
            import time

            sys.stdin.read()
            held = b"\\x01" * (64 * 1024 * 1024)
            time.sleep(1)
            with open("worker.txt", "w", encoding="utf-8") as stream:
                stream.write("edited by a worker that held 64 MB\\n")
            print(json.dumps({"session_id": "memory-session", "is_error": False, "result": "done " + str(len(held))}))
        ''')
        result = self.run_lane("haiku", ["--class", "mechanical", "--outdir", self.outdir],
                               env={"LANES_MEM_SAMPLE_SECONDS": "0.1"})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        meta = self.read_json(os.path.join(self.outdir, "meta.json"))
        self.assertIsInstance(meta["peak_mem_mb"], int)
        self.assertGreaterEqual(meta["peak_mem_mb"], 32)
        self.assertEqual(self.ledger()[0]["peak_mem_mb"], meta["peak_mem_mb"])

    def test_eta_is_saved_reported_and_added_to_the_ledger(self):
        script = self.install_fake_eta()
        marker = os.path.join(self.root, "eta-argv.json")
        result = self.run_lane(extra=["--class", "substantive", "--tag", "pair-1", "--outdir", self.outdir],
                               env={"LANE_STATS": script, "LANE_NO_ETA": "0", "FAKE_ETA_MARKER": marker})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("lane: eta ~14 min (p80 25; measured, 9 runs)", result.stderr)
        self.assertIn("eta 14", result.stdout)
        brief_bytes = os.path.getsize(self.brief)
        argv = self.read_json(marker)
        self.assertEqual(argv[argv.index("--brief-bytes") + 1], str(brief_bytes))
        meta = self.read_json(os.path.join(self.outdir, "meta.json"))
        self.assertEqual(meta["eta_s"], 852.0)
        self.assertEqual(meta["eta_p80_s"], 1500.0)
        self.assertEqual(meta["eta_tier"], "measured")
        self.assertEqual(meta["brief_bytes"], brief_bytes)
        record = self.ledger()[0]
        self.assertEqual(record["eta_s"], 852.0)
        self.assertEqual(record["eta_tier"], "measured")
        self.assertEqual(record["brief_bytes"], brief_bytes)

    def test_eta_failures_leave_eta_empty_and_run_finishes(self):
        script = self.install_fake_eta()
        for mode in ("exit", "invalid"):
            with self.subTest(mode=mode):
                worker_file = os.path.join(self.workspace, "worker.txt")
                if os.path.exists(worker_file):
                    os.unlink(worker_file)
                outdir = os.path.join(self.root, mode)
                result = self.run_lane(extra=["--class", "mechanical", "--outdir", outdir],
                                       env={"LANE_STATS": script, "LANE_NO_ETA": "0", "FAKE_ETA_MODE": mode})
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                self.assertIn("verdict=OK", result.stdout)
                self.assertNotIn("lane: eta", result.stderr)
                meta = self.read_json(os.path.join(outdir, "meta.json"))
                self.assertIsNone(meta["eta_s"])
                self.assertIsNone(meta["eta_p80_s"])
                self.assertIsNone(meta["eta_tier"])
                self.assertIsNone(self.ledger()[-1]["eta_s"])

    def test_no_eta_skips_the_fake(self):
        script = self.install_fake_eta()
        marker = os.path.join(self.root, "eta-called")
        result = self.run_lane(extra=["--class", "mechanical", "--outdir", self.outdir],
                               env={"LANE_STATS": script, "LANE_NO_ETA": "1", "FAKE_ETA_MARKER": marker})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertFalse(os.path.exists(marker))

    def test_dry_run_prints_eta_without_writing(self):
        script = self.install_fake_eta()
        result = self.run_lane(extra=["--dry-run"], env={"LANE_STATS": script, "LANE_NO_ETA": "0"})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("lane: eta ~14 min (p80 25; measured, 9 runs)", result.stderr)
        self.assertFalse(os.path.exists(self.state))

    def test_reserve_run_dir_allocates_unique_directory(self):
        target = os.path.join(self.root, "runs", "20261019-120000-haiku-test")
        first = lane.reserve_run_dir(target)
        self.assertEqual(first, target)
        self.assertTrue(os.path.isdir(first))

        second = lane.reserve_run_dir(target)
        self.assertEqual(second, target + "-2")
        self.assertTrue(os.path.isdir(second))

        third = lane.reserve_run_dir(target)
        self.assertEqual(third, target + "-3")
        self.assertTrue(os.path.isdir(third))

    def test_dry_run_without_outdir_leaves_no_runs_folder(self):
        self.preview("haiku")
        runs_dir = os.path.join(self.state, "runs")
        self.assertFalse(os.path.exists(runs_dir))


class UsageTests(unittest.TestCase):
    def meter(self, provider, data):
        completed = subprocess.CompletedProcess([], 0, json.dumps(data).encode("utf-8"), b"")
        with mock.patch.dict(os.environ, {"LANE_NO_USAGE": "0"}), \
                mock.patch.object(lane, "run_quiet", return_value=None) as refresh, \
                mock.patch.object(lane.subprocess, "run", return_value=completed) as command:
            reading, error = lane.read_usage(provider)
        return reading, error, refresh, command

    def test_codex_refresh_failure_is_ignored_and_windows_are_mapped(self):
        reading, error, refresh, command = self.meter("codex", {"codex": {
            "status": "ok", "age_seconds": 2, "reading": {"timestamp": "2026-10-17T01:02:03Z"},
            "windows": [{"label": "weekly", "used_percent": 12, "resets_at": "2026-10-23T11:25:25Z"}]}})
        self.assertIsNone(error)
        self.assertEqual(reading, {"observed_at": "2026-10-17T01:02:03Z", "age_seconds": 2, "status": "ok",
                                   "windows": [{"label": "weekly", "used_percent": 12.0, "resets_at": "2026-10-23T11:25:25Z"}]})
        self.assertEqual(refresh.call_args[0][0][-1], "--codex-refresh")
        self.assertEqual(refresh.call_args[1]["timeout"], 45)
        self.assertEqual(command.call_args[0][0][0], sys.executable)
        self.assertEqual(command.call_args[0][0][-2:], ["--json", "--no-agy"])
        self.assertEqual(command.call_args[1]["timeout"], 45)

    def test_live_codex_observed_time_is_derived_from_age(self):
        reading, error, _, _ = self.meter("codex", {"codex": {"status": "ok", "age_seconds": 0,
            "reading": None, "windows": [{"label": "5h", "used_percent": 0, "resets_at": None}]}})
        self.assertIsNone(error)
        self.assertTrue(reading["observed_at"].endswith("Z"))

    def test_agy_bucket_shape_and_labels(self):
        reading, error, refresh, command = self.meter("gemini", {"agy": {"exit_code": 0, "error": None,
            "buckets": [{"id": "Gemini Pro", "window": "weekly", "used_percentage": 37.5, "reset_time": "2026-10-23T00:00:00Z"},
                        {"window": "5h", "used_percentage": 10, "reset_time": None}]}})
        self.assertIsNone(error)
        self.assertEqual(reading["windows"], [
            {"label": "Gemini Pro weekly", "used_percent": 37.5, "resets_at": "2026-10-23T00:00:00Z"},
            {"label": "5h", "used_percent": 10.0, "resets_at": None}])
        self.assertEqual(command.call_args[0][0][-1], "--json")
        self.assertNotIn("--no-agy", command.call_args[0][0])
        refresh.assert_not_called()

    def test_disabled_and_cline_do_not_invoke_a_meter(self):
        with mock.patch.object(lane.subprocess, "run") as command:
            with mock.patch.dict(os.environ, {"LANE_NO_USAGE": "1"}):
                self.assertEqual(lane.read_usage("claude"), (None, "disabled"))
            with mock.patch.dict(os.environ, {"LANE_NO_USAGE": "0"}):
                self.assertEqual(lane.read_usage("cline"), (None, "no meter"))
        command.assert_not_called()

    def test_meter_failures_are_short_errors(self):
        cases = [(subprocess.CompletedProcess([], 7, b"", b"private"), "usage-status exited 7"),
                 (subprocess.CompletedProcess([], 0, b"not JSON", b""), "invalid usage-status JSON"),
                 (subprocess.CompletedProcess([], 0, b"{}", b""), "no claude reading")]
        with mock.patch.dict(os.environ, {"LANE_NO_USAGE": "0"}):
            for result, message in cases:
                with self.subTest(message=message), mock.patch.object(lane.subprocess, "run", return_value=result):
                    self.assertEqual(lane.read_usage("claude"), (None, message))
            for exc, message in ((OSError("private"), "usage-status unavailable"),
                                 (subprocess.TimeoutExpired([], 45), "usage-status timed out")):
                with mock.patch.object(lane.subprocess, "run", side_effect=exc):
                    self.assertEqual(lane.read_usage("claude"), (None, message))

    def test_gemini_tokens_are_optional_and_support_json_stats(self):
        self.assertIsNone(lane.run_tokens("gemini", "", '{"status":"SUCCESS"}'))
        self.assertEqual(lane.run_tokens("gemini", "", json.dumps({"usage": {
            "input_tokens": 10, "cached_tokens": 20, "output_tokens": 3, "total_tokens": 33}})),
            {"input": 10, "cached": 20, "output": 3, "total": 33})

    def test_astra_minimum_version(self):
        for version, accepted in (("0.159.0", False), ("0.159.1", True)):
            result = subprocess.CompletedProcess([], 0, ("codex-cli " + version).encode("ascii"), b"")
            with mock.patch.object(lane, "run_quiet", return_value=result):
                check = lane.version_check("astra", sys.executable)
            self.assertEqual("accepted" in check, accepted, check)

    def test_terra_minimum_version(self):
        for version, accepted in (("0.158.9", False), ("0.159.0", True)):
            result = subprocess.CompletedProcess([], 0, ("codex-cli " + version).encode("ascii"), b"")
            with mock.patch.object(lane, "run_quiet", return_value=result):
                check = lane.version_check("terra", sys.executable)
            self.assertEqual("accepted" in check, accepted, check)


class CursorGrokLaneTests(LaneTests):
    CURSOR_OK = json.dumps({"type": "result", "subtype": "success", "is_error": False, "duration_ms": 10,
                            "result": "OK", "session_id": "s1", "request_id": "r1",
                            "usage": {"inputTokens": 100, "outputTokens": 5, "cacheReadTokens": 7,
                                      "cacheWriteTokens": 0}})
    GROK_OK = json.dumps({"text": "OK", "stopReason": "end_turn", "sessionId": "g1", "requestId": "r1", "cwd": "x",
                          "thought": "secret thought",
                          "usage": {"input_tokens": 100, "cache_read_input_tokens": 7,
                                    "cache_creation_input_tokens": 0, "output_tokens": 5, "reasoning_tokens": 4,
                                    "total_tokens": 112}, "num_turns": 1, "total_cost_usd": 0.0123})

    def setUp(self):
        super().setUp()
        self.install_fake_cursor_agent()
        self.install_fake_grok()
        self.cursor_bin = os.path.join(self.bin, "cursor-agent.cmd" if os.name == "nt" else "cursor-agent")
        self.grok_bin = os.path.join(self.bin, "grok.cmd" if os.name == "nt" else "grok")
        self.bin_env = {"LANES_CURSOR_AGENT_BIN": self.cursor_bin, "LANES_GROK_BIN": self.grok_bin}

    def read_capture(self):
        self.assertTrue(os.path.isfile(self.capture))
        return self.read_json(self.capture)

    def dry_preview(self, name, extra=()):
        result = self.run_lane(name, list(extra) + ["--dry-run"], effort=None, env=self.bin_env)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout.splitlines()[0].split("argv: ", 1)[1])

    def install_fake_cursor_agent(self):
        self.install_cli("cursor-agent", '''
            import json
            import os
            import sys

            brief = sys.stdin.read()
            with open(os.environ["FAKE_CAPTURE"], "w", encoding="utf-8") as stream:
                json.dump({"argv": sys.argv[1:], "brief": brief}, stream)
            mode = os.environ.get("FAKE_MODE", "ok")
            payload = ''' + repr(self.CURSOR_OK) + '''
            data = json.loads(payload)
            if mode == "mentions-limit":
                data["result"] = "The rate limit resets soon; please login again to continue."
            elif mode == "quota":
                print("Error: you have hit your usage limit", file=sys.stderr)
                sys.exit(1)
            elif mode == "auth":
                print("You are not authenticated", file=sys.stderr)
                sys.exit(1)
            elif mode == "ok":
                with open("worker.txt", "w", encoding="utf-8") as stream:
                    stream.write("edited by fake cursor\\n")
            if mode != "quota" and mode != "auth":
                print(json.dumps(data))
        ''')

    def install_fake_grok(self):
        self.install_cli("grok", '''
            import json
            import os
            import sys

            prompt_path = None
            if "--prompt-file" in sys.argv:
                prompt_path = sys.argv[sys.argv.index("--prompt-file") + 1]
            brief = ""
            if prompt_path:
                with open(prompt_path, "r", encoding="utf-8") as stream:
                    brief = stream.read()
            with open(os.environ["FAKE_CAPTURE"], "w", encoding="utf-8") as stream:
                json.dump({"argv": sys.argv[1:], "brief": brief}, stream)
            mode = os.environ.get("FAKE_MODE", "ok")
            payload = ''' + repr(self.GROK_OK) + '''
            data = json.loads(payload)
            if mode == "mentions-limit":
                data["text"] = "The rate limit resets soon; please login again to continue."
            elif mode == "quota":
                print("Error: you have hit your usage limit", file=sys.stderr)
                sys.exit(1)
            elif mode == "auth":
                print("You are not authenticated", file=sys.stderr)
                sys.exit(1)
            elif mode == "ok":
                with open("worker.txt", "w", encoding="utf-8") as stream:
                    stream.write("edited by fake grok\\n")
            if mode != "quota" and mode != "auth":
                print(json.dumps(data))
        ''')

    def test_resolve_binary_uses_lane_bin_overrides(self):
        with mock.patch.dict(os.environ, self.bin_env, clear=False):
            self.assertEqual(lane.resolve_binary("cursor-agent")[0], os.path.expanduser(self.cursor_bin))
            self.assertEqual(lane.resolve_binary("grok")[0], os.path.expanduser(self.grok_bin))

    def test_cursor_dry_run_argv_and_brief_contract(self):
        command = self.dry_preview("cursor", ["-e", "medium"])
        # On Windows lane unwraps the fake's .cmd launcher, so the argv starts with the interpreter and its script.
        if os.name != "nt":
            self.assertEqual(os.path.normcase(command[0]), os.path.normcase(self.cursor_bin))
        start = command.index("-p")
        self.assertEqual(command[start:start + 7], ["-p", "--output-format", "json", "--model", "grok-4.7-medium",
                                                    "--trust", "--workspace"])
        self.assertEqual(command[start + 7], self.workspace)
        self.assertEqual(command[start + 8:], ["--force"])
        command = self.dry_preview("cursor", ["-e", "medium", "--ro"])
        self.assertEqual(command[-2:], ["--mode", "ask"])
        self.assertNotIn("--force", command)

    def test_grok_dry_run_argv_and_prompt_file_contract(self):
        os.makedirs(self.outdir, exist_ok=True)
        command = self.dry_preview("grok", ["-e", "medium", "--outdir", self.outdir])
        model_index = command.index("-m")
        self.assertEqual(command[model_index + 1], "grok-4.7")
        self.assertIn("--prompt-file", command)
        self.assertEqual(command[command.index("--prompt-file") + 1], os.path.join(self.outdir, "brief.sent.md"))
        self.assertEqual(command[command.index("--cwd") + 1], self.workspace)
        self.assertIn("--always-approve", command)
        self.assertEqual(command[command.index("--reasoning-effort") + 1], "medium")
        fast = self.dry_preview("grok", ["--model", "grok-4.7-build-fast", "-e", "low", "--outdir", self.outdir])
        self.assertNotIn("--reasoning-effort", fast)
        self.assertIn("--always-approve", fast)
        read_only = self.dry_preview("grok", ["-e", "high", "--ro", "--outdir", self.outdir])
        self.assertEqual(read_only[read_only.index("--permission-mode") + 1], "plan")
        self.assertNotIn("--always-approve", read_only)

    def test_web_is_refused_for_cursor_and_grok(self):
        for name in ("cursor", "grok"):
            with self.subTest(name=name):
                for extra in (["--web", "--dry-run"], ["--web", "--class", "mechanical"]):
                    result = self.run_lane(name, extra, effort=None, env=self.bin_env)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertIn("{} cannot take --web".format(name), result.stderr)
                effort = ["-e", "medium"] if name == "cursor" else ["-e", "medium"]
                self.assertEqual(self.run_lane(name, ["--dry-run"] + effort, effort=None,
                                               env=self.bin_env).returncode, 0)

    def test_catalog_accepts_every_cursor_and_grok_arm(self):
        catalog = lane.load_catalog()
        for arm in catalog["arms"]:
            if arm["lane"] not in ("cursor", "grok") or arm["status"] != "active":
                continue
            with self.subTest(arm=lane.arm_key(arm)):
                result = self.run_lane(arm["lane"], ["--model", arm["model"], "-e", arm["effort"], "--dry-run"],
                                       effort=None, env=self.bin_env)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_cursor_success_records_tokens_session_and_final_without_thought(self):
        self.init_git()
        os.makedirs(self.outdir, exist_ok=True)
        result = self.run_lane("cursor", ["-e", "medium", "--class", "substantive", "--outdir", self.outdir],
                               effort=None, env=dict(self.bin_env, FAKE_MODE="ok"))
        self.assertEqual(result.returncode, 0, result.stdout + without_mode_line(result.stderr))
        self.assertIn("verdict=OK", result.stdout)
        captured = self.read_capture()
        self.assertNotIn(self.brief, captured["argv"])
        self.assertIn("Edit worker.txt", captured["brief"])
        self.assertEqual(captured["argv"], ["-p", "--output-format", "json", "--model", "grok-4.7-medium", "--trust",
                                            "--workspace", self.workspace, "--force"])
        meta = self.read_json(os.path.join(self.outdir, "meta.json"))
        self.assertEqual(meta["session_id"], "s1")
        self.assertEqual(meta["usage"]["tokens"], {"input": 100, "cached": 7, "output": 5, "total": 112})
        self.assertIsNone(meta["usage"].get("list_usd"))
        meta_text = json.dumps(meta)
        final = open(os.path.join(self.outdir, "final.md"), encoding="utf-8").read()
        self.assertEqual(final.strip(), "OK")
        self.assertNotIn("secret thought", meta_text + final)
        self.assertNotIn("login", result.stderr.lower())

    def test_grok_success_records_tokens_cost_and_omits_thought(self):
        self.init_git()
        os.makedirs(self.outdir, exist_ok=True)
        result = self.run_lane("grok", ["-e", "medium", "--class", "substantive", "--outdir", self.outdir],
                               effort=None, env=dict(self.bin_env, FAKE_MODE="ok"))
        self.assertEqual(result.returncode, 0, result.stdout + without_mode_line(result.stderr))
        captured = self.read_capture()
        self.assertEqual(captured["argv"][captured["argv"].index("--prompt-file") + 1],
                         os.path.join(self.outdir, "brief.sent.md"))
        self.assertNotIn(self.brief, captured["argv"])
        meta = self.read_json(os.path.join(self.outdir, "meta.json"))
        self.assertEqual(meta["session_id"], "g1")
        self.assertEqual(meta["usage"]["list_usd"], 0.0123)
        self.assertEqual(meta["usage"]["tokens"]["total"], 112)
        # run.log keeps the CLI's raw output, as every lane's does; the record and final.md leave the thought out.
        self.assertNotIn("secret thought", json.dumps(meta) + open(
            os.path.join(self.outdir, "final.md"), encoding="utf-8").read())

    def test_cursor_and_grok_quota_failed_and_limit_mentions(self):
        cases = (
            ("cursor", "quota", 75, "QUOTA"),
            ("grok", "quota", 75, "QUOTA"),
            ("cursor", "auth", 4, "FAILED"),
            ("grok", "auth", 4, "FAILED"),
            ("cursor", "mentions-limit", 0, "OK"),
            ("grok", "mentions-limit", 0, "OK"),
        )
        for lane_name, mode, code, verdict in cases:
            with self.subTest(lane=lane_name, mode=mode):
                self.init_git()
                outdir = os.path.join(self.root, lane_name + "-" + mode)
                os.makedirs(outdir, exist_ok=True)
                # The limit-mentioning answer edits nothing, so it runs read-only (a writing run would be NOOP).
                effort = ["-e", "medium"] + (["--ro"] if mode == "mentions-limit" else [])
                result = self.run_lane(lane_name, effort + ["--outdir", outdir], effort=None,
                                       env=dict(self.bin_env, FAKE_MODE=mode))
                self.assertEqual(result.returncode, code, result.stdout + result.stderr)
                self.assertIn("verdict={}".format(verdict), result.stdout)
                if mode == "auth":
                    self.assertIn("warning: run the {} CLI's login command before retrying".format(lane_name),
                                  result.stderr)
                if mode == "mentions-limit":
                    self.assertNotIn("warning: run the", result.stderr)

    def test_writing_run_without_git_change_is_noop(self):
        self.init_git()
        os.makedirs(self.outdir, exist_ok=True)
        for lane_name in ("cursor", "grok"):
            with self.subTest(lane=lane_name):
                outdir = os.path.join(self.root, lane_name + "-noop")
                os.makedirs(outdir, exist_ok=True)
                effort = ["-e", "medium"]
                result = self.run_lane(lane_name, effort + ["--outdir", outdir], effort=None,
                                       env=dict(self.bin_env, FAKE_MODE="noop"))
                self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
                self.assertIn("verdict=NOOP", result.stdout)


class PlatformIdentityTests(unittest.TestCase):
    CATALOG = {"explore": {"platforms": {
        "claude-code": {"places": ["process", "subagent", "cloud"], "env_markers": ["CLAUDECODE"]},
        "amp": {"places": ["process", "cloud"], "env_markers": ["AMP_TEST_MARKER"]}}}}

    def test_kit_platform_order_and_override(self):
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1", "AMP_TEST_MARKER": "1"}, clear=True):
            self.assertEqual(lane.kit_platform(self.CATALOG), "claude-code")
        with mock.patch.dict(os.environ, {"AMP_TEST_MARKER": "1"}, clear=True):
            self.assertEqual(lane.kit_platform(self.CATALOG), "amp")
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(lane.kit_platform(self.CATALOG), "claude-code")
            self.assertEqual(lane.kit_platform(None), "claude-code")
        with mock.patch.dict(os.environ, {"KIT_PLATFORM": "amp", "CLAUDECODE": "1"}, clear=True):
            self.assertEqual(lane.kit_platform(self.CATALOG), "amp")
        with mock.patch.dict(os.environ, {"KIT_PLATFORM": "nope"}, clear=True):
            with self.assertRaises(ValueError):
                lane.kit_platform(self.CATALOG)

    def test_platform_places_default_when_the_catalog_has_none(self):
        self.assertEqual(lane.platform_places(None, "amp"), ["process", "cloud"])
        self.assertEqual(lane.platform_places({}, "claude-code"), ["process", "subagent", "cloud"])
        self.assertEqual(lane.platform_places(self.CATALOG, "amp"), ["process", "cloud"])


# CursorGrokLaneTests borrows LaneTests' fixtures; without this, unittest would run every LaneTests test twice.
for _name in dir(LaneTests):
    if _name.startswith("test_") and _name not in CursorGrokLaneTests.__dict__:
        setattr(CursorGrokLaneTests, _name, None)


# AmpLaneTests borrows LaneTests' fixtures; without this, unittest would run every LaneTests test twice.
class AmpLaneTests(LaneTests):
    AMP_FIXTURES = os.path.join(ROOT, "tests", "fixtures", "amp")
    THREAD = "T-7c1e2a40-5b1d-4e8f-9a3c-2f6d8e1b0a57"

    def setUp(self):
        super().setUp()
        self.install_fake_amp()
        self.amp_bin = os.path.join(self.bin, "amp.cmd" if os.name == "nt" else "amp")
        self.usage_capture = os.path.join(self.root, "usage-capture.json")
        # The amp settings file is read from ~/.config/amp: a home of its own keeps the user's real settings out of tests.
        self.home = os.path.join(self.root, "home")
        os.makedirs(self.home)
        self.amp_env = {"LANES_AMP_BIN": self.amp_bin, "FAKE_AMP_FIXTURES": self.AMP_FIXTURES,
                        "FAKE_USAGE_CAPTURE": self.usage_capture, "FAKE_USAGE": "ok",
                        "HOME": self.home, "USERPROFILE": self.home}

    def install_fake_amp(self):
        self.install_cli("amp", '''
            import json
            import os
            import sys

            fixtures = os.environ["FAKE_AMP_FIXTURES"]
            lane_env = {key: os.environ.get(key) for key in ("KIT_LANE_RUN", "USAGE_OPTIMIZER_TURNS")}
            if sys.argv[1:3] == ["threads", "usage"]:
                with open(os.environ["FAKE_USAGE_CAPTURE"], "w", encoding="utf-8") as stream:
                    json.dump({"argv": sys.argv[1:], "env": lane_env}, stream)
                if os.environ.get("FAKE_USAGE") == "fail":
                    print("cannot read thread usage", file=sys.stderr)
                    sys.exit(1)
                name = "threads-usage-subscription.txt" if os.environ.get("FAKE_USAGE") == "subscription" else "threads-usage.txt"
                with open(os.path.join(fixtures, name), encoding="utf-8") as stream:
                    sys.stdout.write(stream.read())
                sys.exit(0)
            brief = sys.stdin.read()
            settings = None
            if "--settings-file" in sys.argv:
                with open(sys.argv[sys.argv.index("--settings-file") + 1], encoding="utf-8") as stream:
                    settings = json.load(stream)
            with open(os.environ["FAKE_CAPTURE"], "w", encoding="utf-8") as stream:
                json.dump({"argv": sys.argv[1:], "brief": brief, "env": lane_env, "settings": settings}, stream)
            mode = os.environ.get("FAKE_MODE", "ok")
            name = {"cut": "stream-cut.jsonl", "error": "stream-error.jsonl"}.get(mode, "stream-ok.jsonl")
            with open(os.path.join(fixtures, name), encoding="utf-8") as stream:
                events = [json.loads(line) for line in stream if line.strip()]
            if mode == "error":
                events[-1]["result"] = os.environ.get("FAKE_ERROR_TEXT", events[-1]["result"])
            if mode == "sandbox":
                events[-1]["permission_denials"] = [{"tool_name": "shell_command", "tool_use_id": "toolu_02",
                                                     "tool_input": {"cmd": "git status"}}]
            if mode in ("ok", "sandbox"):
                with open("worker.txt", "w", encoding="utf-8") as stream:
                    stream.write("edited by fake amp\\n")
            for event in events:
                print(json.dumps(event))
            if mode == "error":
                sys.exit(1)
        ''')

    def fresh_workspace(self, name):
        # A workspace of its own per case: an edit left by one case would make the next one a NOOP.
        self.workspace = os.path.join(self.root, "ws-" + name)
        os.makedirs(self.workspace)
        self.init_git()

    def read_capture(self):
        self.assertTrue(os.path.isfile(self.capture))
        return self.read_json(self.capture)

    def read_text(self, path):
        with open(path, "r", encoding="utf-8") as stream:
            return stream.read()

    def dry_lines(self, extra):
        result = self.run_lane("amp", list(extra) + ["--dry-run"], effort=None, env=self.amp_env)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.splitlines()

    def expected_claude_usd(self, model):
        # Amp's input_tokens is uncached input: the 2600 input, 1900 cache reads, 300 cache writes and 57 output.
        price = lane.price_for(lane.load_catalog()["providers"]["claude"]["prices"], model)
        return lane.message_list_usd(price, {"input": 2600, "cache_read": 1900, "cache_write_5m": 300,
                                             "cache_write_1h": 0, "output": 57})

    def test_amp_dry_run_argv_and_run_environment(self):
        lines = self.dry_lines(["-e", "medium", "--outdir", os.path.join(self.root, "dry-run")])
        argv = json.loads(lines[0].split("argv: ", 1)[1])
        self.assertEqual(argv[-6:], ["-x", "--stream-json", "--model", "anthropic/claude-opus-5-5", "--effort",
                                     "medium"])
        self.assertIn('env: {"KIT_LANE_RUN": "dry-run", "USAGE_OPTIMIZER_TURNS": "off"}', lines)
        lines = self.dry_lines(["-m", "gpt-6.1-sol", "-e", "high", "--outdir", os.path.join(self.root, "dry-sol")])
        argv = json.loads(lines[0].split("argv: ", 1)[1])
        self.assertEqual(argv[-6:], ["-x", "--stream-json", "--model", "openai/gpt-6.1-sol", "--effort", "high"])
        resumed = self.dry_lines(["--resume", self.THREAD, "-e", "medium"])
        argv = json.loads(resumed[0].split("argv: ", 1)[1])
        self.assertEqual(argv[-5:], ["threads", "continue", self.THREAD, "-x", "--stream-json"])
        self.assertNotIn("--model", argv)

    def test_catalog_accepts_every_amp_arm(self):
        catalog = lane.load_catalog()
        amp_arms = [arm for arm in catalog["arms"] if arm["lane"] == "amp"]
        self.assertEqual(len(amp_arms), 7)
        for arm in amp_arms:
            with self.subTest(arm=lane.arm_key(arm)):
                self.assertEqual(arm["status"], "manual")
                result = self.run_lane("amp", ["-m", arm["model"], "-e", arm["effort"], "--dry-run"],
                                       effort=None, env=self.amp_env)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                argv = json.loads(result.stdout.splitlines()[0].split("argv: ", 1)[1])
                self.assertEqual(argv[argv.index("--model") + 1], arm["cli_model"])

    def test_amp_refuses_ro_web_and_a_resume_id_that_is_not_a_thread(self):
        for extra, message in ((["--ro"], "amp cannot take --ro"), (["--web"], "amp cannot take --web"),
                               (["--resume", "abc"], "amp --resume needs an amp thread id")):
            with self.subTest(extra=extra):
                result = self.run_lane("amp", ["-e", "medium", "--dry-run"] + extra, effort=None, env=self.amp_env)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(message, result.stderr)

    def test_amp_success_records_thread_tokens_and_threads_usage_cost(self):
        self.fresh_workspace("success")
        outdir = os.path.join(self.root, "success-run")
        result = self.run_lane("amp", ["-e", "medium", "--class", "substantive", "--outdir", outdir], effort=None,
                               env=dict(self.amp_env, FAKE_MODE="ok", FAKE_CAPTURE=self.capture))
        self.assertEqual(result.returncode, 0, result.stdout + without_mode_line(result.stderr))
        self.assertIn("verdict=OK", result.stdout)
        captured = self.read_capture()
        self.assertEqual(captured["argv"][:2], ["--settings-file", os.path.join(outdir, "amp-settings.json")])
        self.assertEqual(captured["argv"][2:], ["-x", "--stream-json", "--model", "anthropic/claude-opus-5-5",
                                                "--effort", "medium"])
        self.assertIn("Edit worker.txt", captured["brief"])
        self.assertNotIn(self.brief, captured["argv"])
        self.assertEqual(captured["env"], {"KIT_LANE_RUN": "success-run", "USAGE_OPTIMIZER_TURNS": "off"})
        usage_call = self.read_json(self.usage_capture)
        self.assertEqual(usage_call["argv"], ["threads", "usage", self.THREAD, "--details"])
        self.assertEqual(usage_call["env"], {"KIT_LANE_RUN": "success-run", "USAGE_OPTIMIZER_TURNS": "off"})
        meta = self.read_json(os.path.join(outdir, "meta.json"))
        self.assertEqual(meta["session_id"], self.THREAD)
        self.assertEqual(meta["model"], "claude-opus-5-5")
        self.assertEqual(meta["usage"]["list_usd"], 0.13)
        self.assertEqual(meta["usage"]["cost_source"], "amp-threads-usage")
        self.assertEqual(meta["usage"]["tokens"], {"input": 2900, "cached": 1900, "output": 57, "total": 4857})
        self.assertEqual(self.read_text(os.path.join(outdir, "final.md")).strip(), "Created worker.txt.")

    def test_amp_subscription_thread_is_priced_at_list_and_billed_to_the_claude_plan(self):
        self.fresh_workspace("subscription")
        outdir = os.path.join(self.root, "subscription-run")
        result = self.run_lane("amp", ["-e", "medium", "--outdir", outdir], effort=None,
                               env=dict(self.amp_env, FAKE_MODE="ok", FAKE_USAGE="subscription", FAKE_CAPTURE=self.capture))
        self.assertEqual(result.returncode, 0, result.stdout + without_mode_line(result.stderr))
        self.assertIn("verdict=OK", result.stdout)
        usage = self.read_json(os.path.join(outdir, "meta.json"))["usage"]
        # Amp's Cost is $0.00 (credits only); the $0.66 list price is what the Claude subscription served, so the plan paid.
        self.assertEqual((usage["list_usd"], usage["amp_usd"], usage["billed"]), (0.66, 0.0, "claude"))
        self.assertEqual(usage["cost_source"], "amp-threads-usage")

    def test_amp_billed_to_in_the_arms_catalog_names_the_payer(self):
        self.fresh_workspace("billed-to")
        outdir = os.path.join(self.root, "billed-to-run")
        local = os.path.join(self.root, "arms.local.json")
        self.write(local, json.dumps({"providers": {"amp": {"billed_to": "codex"}}}))
        result = self.run_lane("amp", ["-e", "medium", "--outdir", outdir], effort=None,
                               env=dict(self.amp_env, FAKE_MODE="ok", FAKE_USAGE="subscription", LANES_ARMS_LOCAL=local,
                                        FAKE_CAPTURE=self.capture))
        self.assertEqual(result.returncode, 0, result.stdout + without_mode_line(result.stderr))
        usage = self.read_json(os.path.join(outdir, "meta.json"))["usage"]
        self.assertEqual((usage["list_usd"], usage["billed"]), (0.66, "codex"))

    def test_amp_report_rule_reads_both_fixtures_and_refuses_a_windowed_or_doubled_report(self):
        def fixture(name):
            with open(os.path.join(self.AMP_FIXTURES, name), encoding="utf-8") as stream:
                return stream.read()

        subscription = fixture("threads-usage-subscription.txt")
        details = fixture("threads-usage-details.txt")
        # The same literal values as turn-meter's test of its copy of this rule (PlatformTests).
        self.assertEqual(lane.amp_report_usage(subscription),
                         {"amp_usd": 0.0, "list_usd": 0.66, "routed": ["claude"], "billed": "claude"})
        self.assertEqual(lane.amp_report_usage(details),
                         {"amp_usd": 0.13, "list_usd": 0.13, "routed": ["amp"], "billed": "amp"})
        # An unparseable Est. list price cell falls back to Amp's cost; so does a windowed scope or a second Cost line.
        self.assertEqual(lane.amp_report_usage(subscription.replace("| $0.00 | $0.66 |", "| $0.00 | n/a |"))["list_usd"], 0.0)
        self.assertIsNone(lane.amp_report_usage(subscription.replace("Scope: Entire lifetime of this thread.", "Scope: Last 7 days.")))
        self.assertIsNone(lane.amp_report_usage(details + "\nCost: $0.20\n"))
        self.assertIsNone(lane.amp_report_usage(""))

    def test_amp_cost_falls_back_to_priced_tokens_or_null(self):
        cases = (
            ("claude", [], "claude-opus-5-5"),
            ("gpt", ["-m", "gpt-6.1-sol"], "gpt-6.1-sol"),
            ("glm", ["-m", "glm-5.3-flash", "-e", "low"], "glm-5.3-flash"),
        )
        for name, extra, model in cases:
            with self.subTest(model=model):
                self.fresh_workspace(name)
                outdir = os.path.join(self.root, name + "-run")
                effort = ["-e", "medium"] if name != "glm" else []
                result = self.run_lane("amp", extra + effort + ["--outdir", outdir], effort=None,
                                       env=dict(self.amp_env, FAKE_MODE="ok", FAKE_USAGE="fail"))
                self.assertEqual(result.returncode, 0, result.stdout + without_mode_line(result.stderr))
                usage = self.read_json(os.path.join(outdir, "meta.json"))["usage"]
                self.assertEqual(usage["tokens"]["total"], 4857)
                if name == "claude":
                    self.assertEqual(usage["cost_source"], "tokens")
                    self.assertAlmostEqual(usage["list_usd"], self.expected_claude_usd("claude-opus-5-5"), places=9)
                elif name == "gpt":
                    # Codex rate card: 2900 input at 50, 1900 cached at 2.5 and 57 output at 250, per million credits.
                    self.assertEqual(usage["cost_source"], "tokens")
                    credits = (2900 * 50 + 1900 * 2.5 + 57 * 250) / 1e6
                    self.assertAlmostEqual(usage["list_usd"], credits * 0.04, places=9)
                else:
                    self.assertIsNone(usage["list_usd"])
                    self.assertIsNone(usage.get("cost_source"))
                    self.assertEqual(usage["tokens_error"], "no list price for model glm-5.3-flash")

    def test_amp_verdict_rows(self):
        cases = (
            # mode, error text, exit code, verdict, exit code
            ("ok", None, 0, "OK", 0),
            ("noop", None, 0, "NOOP", 3),
            ("sandbox", None, 0, "SANDBOX", 7),
            ("error", "Error: request failed (HTTP 500)", 1, "FAILED", 4),
            ("error", "402 insufficient credits: add credits at ampcode.com", 1, "QUOTA", 75),
            ("error", "You are out of credits.", 1, "QUOTA", 75),
            ("error", "You have hit your usage limit for this thread.", 1, "QUOTA", 75),
            ("error", "HTTP 429 too many requests", 1, "QUOTA", 75),
            ("cut", None, 0, "PARTIAL", 6),
        )
        for index, (mode, error_text, code, verdict, exit_code) in enumerate(cases):
            with self.subTest(mode=mode, text=error_text):
                self.fresh_workspace("case-{}".format(index))
                outdir = os.path.join(self.root, "verdict-{}".format(index))
                env = dict(self.amp_env, FAKE_MODE=mode, FAKE_CAPTURE=self.capture)
                if error_text:
                    env["FAKE_ERROR_TEXT"] = error_text
                result = self.run_lane("amp", ["-e", "medium", "--outdir", outdir], effort=None, env=env)
                self.assertEqual(result.returncode, exit_code, result.stdout + result.stderr)
                self.assertIn("verdict={}".format(verdict), result.stdout)
                self.assertEqual(self.read_json(os.path.join(outdir, "meta.json"))["session_id"], self.THREAD)

    def settings_path(self, outdir):
        return os.path.join(outdir, "amp-settings.json")

    def user_settings_path(self):
        return os.path.join(self.home, ".config", "amp", "settings.json")

    def write_user_settings(self, text):
        os.makedirs(os.path.dirname(self.user_settings_path()), exist_ok=True)
        self.write(self.user_settings_path(), text)

    def test_amp_dry_run_names_the_settings_file_for_new_and_resumed_threads(self):
        outdir = os.path.join(self.root, "dry-settings")
        lines = self.dry_lines(["-e", "medium", "--outdir", outdir])
        argv = json.loads(lines[0].split("argv: ", 1)[1])
        flag = argv.index("--settings-file")  # 1, or later on Windows, where a launcher runs the fake amp
        self.assertEqual(argv[flag + 1], self.settings_path(outdir))
        self.assertEqual(argv[flag + 2:], ["-x", "--stream-json", "--model", "anthropic/claude-opus-5-5", "--effort",
                                           "medium"])
        self.assertIn("amp settings: would write {} with amp.dangerouslyAllowAll true, deleted when the run ends".format(
            self.settings_path(outdir)), lines)
        self.assertFalse(os.path.exists(self.settings_path(outdir)))
        resumed = self.dry_lines(["--resume", self.THREAD, "-e", "medium"])
        argv = json.loads(resumed[0].split("argv: ", 1)[1])
        self.assertIn("--settings-file", argv)
        self.assertEqual(argv[-5:], ["threads", "continue", self.THREAD, "-x", "--stream-json"])

    def test_amp_run_passes_the_settings_file_and_deletes_it_after_the_run(self):
        self.write_user_settings(json.dumps({"amp.experimental.modes": ["x"], "amp.dangerouslyAllowAll": False}))
        before = self.read_text(self.user_settings_path())
        self.fresh_workspace("settings")
        outdir = os.path.join(self.root, "settings-run")
        result = self.run_lane("amp", ["-e", "medium", "--outdir", outdir], effort=None,
                               env=dict(self.amp_env, FAKE_MODE="ok", FAKE_CAPTURE=self.capture))
        self.assertEqual(result.returncode, 0, result.stdout + without_mode_line(result.stderr))
        captured = self.read_capture()
        self.assertEqual(captured["argv"][:2], ["--settings-file", self.settings_path(outdir)])
        self.assertEqual(captured["settings"], {"amp.experimental.modes": ["x"], "amp.dangerouslyAllowAll": True})
        self.assertFalse(os.path.exists(self.settings_path(outdir)))
        self.assertEqual(self.read_text(self.user_settings_path()), before)

    def test_amp_settings_from_unparseable_user_settings_hold_only_the_key(self):
        self.write_user_settings("{not json")
        self.fresh_workspace("bad-settings")
        outdir = os.path.join(self.root, "bad-settings-run")
        result = self.run_lane("amp", ["-e", "medium", "--outdir", outdir], effort=None,
                               env=dict(self.amp_env, FAKE_MODE="ok", FAKE_CAPTURE=self.capture))
        self.assertEqual(result.returncode, 0, result.stdout + without_mode_line(result.stderr))
        self.assertEqual(self.read_capture()["settings"], {"amp.dangerouslyAllowAll": True})
        self.assertFalse(os.path.exists(self.settings_path(outdir)))

    def test_amp_allow_all_false_in_arms_local_passes_no_settings_file(self):
        local = os.path.join(self.root, "arms-amp-optout.json")
        self.write(local, json.dumps({"providers": {"amp": {"allow_all": False}}}))
        env = dict(self.amp_env, LANES_ARMS_LOCAL=local)
        outdir = os.path.join(self.root, "optout-dry")
        result = self.run_lane("amp", ["-e", "medium", "--outdir", outdir, "--dry-run"], effort=None, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("amp settings: none (providers.amp.allow_all is false)", result.stdout.splitlines())
        argv = json.loads(result.stdout.splitlines()[0].split("argv: ", 1)[1])
        self.assertNotIn("--settings-file", argv)
        self.fresh_workspace("optout")
        outdir = os.path.join(self.root, "optout-run")
        result = self.run_lane("amp", ["-e", "medium", "--outdir", outdir], effort=None,
                               env=dict(env, FAKE_MODE="ok", FAKE_CAPTURE=self.capture))
        self.assertEqual(result.returncode, 0, result.stdout + without_mode_line(result.stderr))
        captured = self.read_capture()
        self.assertNotIn("--settings-file", captured["argv"])
        self.assertIsNone(captured["settings"])

    @unittest.skipIf(os.name == "nt", "the hanging amp here is a POSIX shell script; Windows is covered by taskkill /T")
    def test_amp_threads_cost_returns_within_its_limit_when_amp_hangs(self):
        hang = os.path.join(self.root, "hang-amp")
        self.write(hang, "#!/bin/sh\nexec sleep 30\n")
        os.chmod(hang, 0o755)
        started = time.monotonic()
        usage = lane.amp_threads_usage(hang, self.THREAD, dict(os.environ), timeout=1)
        elapsed = time.monotonic() - started
        self.assertIsNone(usage)
        self.assertLess(elapsed, 10)

    def test_amp_run_meta_and_ledger_carry_the_platform(self):
        self.fresh_workspace("platform-amp")
        outdir = os.path.join(self.root, "platform-amp-run")
        result = self.run_lane("amp", ["-e", "medium", "--outdir", outdir], effort=None,
                               env=dict(self.amp_env, FAKE_MODE="ok", FAKE_CAPTURE=self.capture, KIT_PLATFORM="amp"))
        self.assertEqual(result.returncode, 0, result.stdout + without_mode_line(result.stderr))
        self.assertEqual(self.read_json(os.path.join(outdir, "meta.json"))["platform"], "amp")
        self.assertEqual(self.ledger()[-1]["platform"], "amp")
        self.fresh_workspace("platform-default")
        outdir = os.path.join(self.root, "platform-default-run")
        result = self.run_lane("amp", ["-e", "medium", "--outdir", outdir], effort=None,
                               env=dict(self.amp_env, FAKE_MODE="ok", FAKE_CAPTURE=self.capture))
        self.assertEqual(result.returncode, 0, result.stdout + without_mode_line(result.stderr))
        self.assertEqual(self.read_json(os.path.join(outdir, "meta.json"))["platform"], "claude-code")
        self.assertEqual(self.ledger()[-1]["platform"], "claude-code")

    def test_amp_usage_fallback_counts_each_message_once(self):
        events = [
            {"type": "system", "session_id": self.THREAD},
            {"type": "assistant", "message": {"id": "m1", "usage": {"input_tokens": 10, "output_tokens": 2}}},
            {"type": "assistant", "message": {"id": "m1", "usage": {"input_tokens": 10, "output_tokens": 2}}},
            {"type": "assistant", "message": {"id": "m2", "usage": {"input_tokens": 5, "cache_read_input_tokens": 7,
                                                                  "output_tokens": 1}}},
        ]
        self.assertEqual(lane.amp_usage_source(events, None),
                         {"input_tokens": 15, "output_tokens": 3, "cache_read_input_tokens": 7})
        self.assertEqual(lane.claude_style_counts(lane.amp_usage_source(events, None)),
                         {"input": 15, "cached": 7, "output": 3, "total": 25})
        self.assertEqual(lane.amp_session(events, None), self.THREAD)


for _name in dir(LaneTests):
    if _name.startswith("test_") and _name not in AmpLaneTests.__dict__:
        setattr(AmpLaneTests, _name, None)


class CursorLauncherTests(unittest.TestCase):
    """Cursor's Windows launcher chains cmd.exe, PowerShell and node; lane starts node and index.js directly."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        self.shim = os.path.join(self.root, "cursor-agent.cmd")
        with open(self.shim, "w", encoding="utf-8") as stream:
            stream.write('@echo off\r\n%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe -NoProfile '
                         '-ExecutionPolicy Bypass -File "%SCRIPT_DIR%\\cursor-agent.ps1" %*\r\n')

    def version(self, name, complete=True):
        folder = os.path.join(self.root, "versions", name)
        os.makedirs(folder)
        for file_name in ("node.exe", "index.js") if complete else ("index.js",):
            open(os.path.join(folder, file_name), "w").close()
        return folder

    def test_the_newest_complete_dated_version_is_started(self):
        self.version("2026.9.28-64d2043")
        newest = self.version("2026.10.22-27dcf5f")
        self.version("2026.11.05-86047df", complete=False)
        self.version("not-a-version")
        self.assertEqual(lane.windows_shim_target(self.shim),
                         [os.path.join(newest, "node.exe"), os.path.join(newest, "index.js")])

    def test_a_node_beside_the_launcher_wins(self):
        self.version("2026.10.22-27dcf5f")
        for file_name in ("node.exe", "index.js"):
            open(os.path.join(self.root, file_name), "w").close()
        self.assertEqual(lane.windows_shim_target(self.shim),
                         [os.path.join(self.root, "node.exe"), os.path.join(self.root, "index.js")])

    def test_no_version_folder_means_no_target(self):
        self.assertIsNone(lane.windows_shim_target(self.shim))


class BriefAndTextCheckTests(unittest.TestCase):
    def test_codex_brief_on_windows_carries_the_windows_rule(self):
        for windows in (True, False):
            with mock.patch.object(lane, "IS_WINDOWS", windows):
                for name in ("luna", "terra", "sol", "astra"):
                    sent = lane.compose_brief(name, b"Do the unit.\n", False).decode("utf-8")
                    self.assertIn(lane.PROCESS_RULE, sent)
                    self.assertEqual(lane.WINDOWS_CODEX_RULE in sent, windows, name)
                for name in ("haiku", "gemini"):
                    sent = lane.compose_brief(name, b"Do the unit.\n", False).decode("utf-8")
                    self.assertNotIn(lane.WINDOWS_CODEX_RULE, sent, name)

    def test_cloud_command_starts_claude_in_auto_mode_unless_overridden(self):
        args = ("claude", "lane-term", "/work", "/out/cloud-screen", "Do the unit.", "run1", "claude-haiku-5-5", "low")
        with mock.patch.dict(os.environ):
            os.environ.pop("LANES_CLOUD_PERMISSION_MODE", None)
            cmd = lane.claude_cloud_command(*args)
        self.assertEqual(cmd[cmd.index("--permission-mode") + 1], "auto")
        self.assertLess(cmd.index("--cloud"), cmd.index("--permission-mode"))
        with mock.patch.dict(os.environ, {"LANES_CLOUD_PERMISSION_MODE": "acceptEdits"}):
            cmd = lane.claude_cloud_command(*args)
        self.assertEqual(cmd[cmd.index("--permission-mode") + 1], "acceptEdits")

    def write(self, root, name, data):
        with open(os.path.join(root, name), "wb") as stream:
            stream.write(data)

    def test_encoding_warnings_flag_new_bom_utf16_and_garbled_text_in_git(self):
        with tempfile.TemporaryDirectory() as root:
            subprocess.run(["git", "init", root], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.write(root, "names.txt", "café Â· kept\n".encode("utf-8"))
            self.write(root, "clean.txt", b"plain\n")
            subprocess.run(["git", "-C", root, "add", "."], check=True, stdout=subprocess.PIPE)
            subprocess.run(["git", "-C", root, "-c", "user.name=t", "-c", "user.email=t@localhost", "commit", "-m", "base"],
                           check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.write(root, "names.txt", "café Â· kept\nfoo Â· bar â€“ baz\n".encode("utf-8"))
            self.write(root, "clean.txt", b"plain\nmore\n")
            self.write(root, "findings.jsonl", b"\xef\xbb\xbf{\"a\": 1}\n")
            self.write(root, "notes.txt", "hello\n".encode("utf-16"))
            warnings = lane.encoding_warnings(root, 0)
        joined = "\n".join(warnings)
        self.assertIn("names.txt: 2 new garbled characters", joined)
        self.assertIn("findings.jsonl: starts with a UTF-8 byte-order mark", joined)
        self.assertIn("notes.txt: written as UTF-16", joined)
        self.assertNotIn("clean.txt", joined)
        self.assertEqual(len(warnings), 3, warnings)

    def test_encoding_warnings_flag_files_saved_with_crlf_unless_git_checks_out_crlf(self):
        with tempfile.TemporaryDirectory() as root:
            subprocess.run(["git", "init", root], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(["git", "-C", root, "config", "core.autocrlf", "false"], check=True)
            self.write(root, "tool.py", b"a = 1\nb = 2\n")
            self.write(root, "kept.py", b"x = 1\n")
            subprocess.run(["git", "-C", root, "add", "."], check=True, stdout=subprocess.PIPE)
            subprocess.run(["git", "-C", root, "-c", "user.name=t", "-c", "user.email=t@localhost", "commit", "-m", "base"],
                           check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.write(root, "tool.py", b"a = 1\r\nb = 3\r\n")
            self.write(root, "kept.py", b"x = 2\n")
            self.write(root, "test_new.py", b"import os\r\n")
            warnings = lane.encoding_warnings(root, 0)
            self.assertEqual(sorted(warnings), [
                "test_new.py: new file with CRLF line endings (a Windows editor or tool saved it); the repository uses LF",
                "tool.py: changed to CRLF line endings (a Windows editor or tool saved it); the repository uses LF"])
            subprocess.run(["git", "-C", root, "config", "core.autocrlf", "true"], check=True)
            self.assertEqual(lane.encoding_warnings(root, 0), [])

    def test_encoding_warnings_outside_git_check_only_files_newer_than_the_run(self):
        with tempfile.TemporaryDirectory() as root:
            self.write(root, "old.jsonl", b"\xef\xbb\xbf{}\n")
            os.utime(os.path.join(root, "old.jsonl"), (1000, 1000))
            os.makedirs(os.path.join(root, "node_modules"))
            self.write(os.path.join(root, "node_modules"), "dep.json", b"\xef\xbb\xbf{}\n")
            self.write(root, "findings.jsonl", b"\xef\xbb\xbf{}\n")
            warnings = lane.encoding_warnings(root, 2000)
        self.assertEqual(warnings, ["findings.jsonl: starts with a UTF-8 byte-order mark (Set-Content -Encoding UTF8); "
                                    "JSON readers reject it"])


if __name__ == "__main__":
    unittest.main()
