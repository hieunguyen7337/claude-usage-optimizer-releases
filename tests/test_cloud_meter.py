import datetime as dt
import importlib.machinery
import importlib.util
import json
import os
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATUS = ROOT / "bin" / "usage-status"


def load(name):
    module_name = name.replace('-', '_')
    loader = importlib.machinery.SourceFileLoader(module_name, str(ROOT / "bin" / name))
    spec = importlib.util.spec_from_loader(module_name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class CloudMeterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.usage = pathlib.Path(self.temp.name) / "usage"
        self.fake = pathlib.Path(self.temp.name) / "claude"
        self.calls = pathlib.Path(self.temp.name) / "calls"
        self.fake.write_text("#!/usr/bin/env python3\nimport json,os\nopen(os.environ['CALLS'],'a').write('x')\nprint(json.dumps({'type':'rate_limit_event','rate_limit_info':{'unifiedWindows':{'five_hour':{'utilization':.25,'resetsAt':1893456000},'seven_day':{'utilization':.75,'resetsAt':1893542400}}}}))\n", encoding="utf-8")
        self.fake.chmod(0o755)
        self.env = dict(os.environ, CLAUDE_USAGE_DIR=str(self.usage),
                        USAGE_OPTIMIZER_CLAUDE_BIN=str(self.fake), CALLS=str(self.calls))

    def tearDown(self):
        self.temp.cleanup()

    def run_status(self, *args, env=None):
        return subprocess.run([str(STATUS), *args], env=env or self.env, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

    @unittest.skipIf(os.name == "nt", "the fake claude is a POSIX script")
    def test_probe_writes_percent_resets_source_and_history(self):
        self.run_status("--probe-claude", "--quiet")
        value = json.loads((self.usage / "claude-latest.json").read_text(encoding="utf-8"))
        self.assertEqual(value["five_hour"]["used_percentage"], 25)
        self.assertEqual(value["seven_day"]["used_percentage"], 75)
        self.assertEqual(value["five_hour"]["resets_at"], "2030-01-01T00:00:00Z")
        self.assertEqual(value["source"], "probe")
        self.assertEqual(len((self.usage / "claude-rate.jsonl").read_text().splitlines()), 1)

    @unittest.skipIf(os.name == "nt", "the fake claude is a POSIX script")
    def test_fresh_skips_and_off_disables_cloud_probe(self):
        self.run_status("--probe-claude", "--quiet")
        self.run_status("--probe-claude", "--quiet")
        self.assertEqual(self.calls.read_text(), "x")
        env = dict(self.env, CLAUDE_CODE_REMOTE="true", USAGE_OPTIMIZER_CLOUD_PROBE_MIN="off")
        (self.usage / "claude-latest.json").unlink()
        self.run_status("--no-local", "--no-agy", "--no-codex-live", env=env)
        self.assertEqual(self.calls.read_text(), "x")

    @unittest.skipIf(os.name == "nt", "the fake claude is a POSIX script")
    def test_failure_and_lock_leave_old_reading(self):
        self.usage.mkdir()
        old = '{"observed_at":"2000-01-01T00:00:00Z"}\n'
        latest = self.usage / "claude-latest.json"
        latest.write_text(old)
        bad = dict(self.env, USAGE_OPTIMIZER_CLAUDE_BIN=str(self.usage / "missing"))
        self.run_status("--probe-claude", "--quiet", env=bad)
        self.assertEqual(latest.read_text(), old)
        (self.usage / ".claude-probe.lock").write_text("")
        self.run_status("--probe-claude", "--quiet")
        self.assertEqual(latest.read_text(), old)

    def probe_with_event(self, info):
        status = load("usage-status")
        line = json.dumps({"type": "rate_limit_event", "rate_limit_info": info})
        done = subprocess.CompletedProcess([], 0, stdout=line + "\n")
        with mock.patch.object(status.subprocess, "run", return_value=done):
            return status.probe_claude(str(self.usage), None, quiet=True)

    def test_probe_keeps_a_weekly_only_event(self):
        # The shape a cloud VM returned on 2026-11-02: no five_hour window at all.
        ok = self.probe_with_event({"status": "allowed_warning", "resetsAt": 1893542400,
                                    "rateLimitType": "seven_day", "utilization": 0.26,
                                    "unifiedWindows": {"seven_day": {"utilization": 0.26, "resetsAt": 1893542400,
                                                                     "status": "allowed"}}})
        self.assertTrue(ok)
        value = json.loads((self.usage / "claude-latest.json").read_text(encoding="utf-8"))
        self.assertEqual(value["seven_day"]["used_percentage"], 26)
        self.assertEqual(value["seven_day"]["resets_at"], "2030-01-02T00:00:00Z")
        self.assertNotIn("five_hour", value)
        status = load("usage-status")
        _, line = status.claude_section(str(self.usage), dt.datetime.now(dt.timezone.utc))
        self.assertIn("weekly 26%", line)

    def test_probe_uses_top_level_window_and_rejects_an_empty_event(self):
        self.assertTrue(self.probe_with_event({"rateLimitType": "five_hour", "utilization": 0.4,
                                               "resetsAt": 1893456000}))
        value = json.loads((self.usage / "claude-latest.json").read_text(encoding="utf-8"))
        self.assertEqual(value["five_hour"]["used_percentage"], 40)
        (self.usage / "claude-latest.json").unlink()
        self.assertFalse(self.probe_with_event({"status": "allowed"}))
        self.assertFalse((self.usage / "claude-latest.json").exists())

    def test_cloud_hook_detaches_but_local_does_not_and_mode_names_probe(self):
        meter = load("turn-meter")
        now = dt.datetime.now(dt.timezone.utc)
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_REMOTE": "true"}, clear=False), \
             mock.patch.object(meter.subprocess, "Popen") as popen:
            self.assertTrue(meter._start_cloud_probe(str(self.usage), now))
            self.assertTrue(popen.call_args.kwargs["start_new_session"])
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_REMOTE": "false"}, clear=False), \
             mock.patch.object(meter.subprocess, "Popen") as popen:
            self.assertFalse(meter._start_cloud_probe(str(self.usage), now))
            popen.assert_not_called()
        self.usage.mkdir(exist_ok=True)
        (self.usage / "claude-latest.json").write_text(json.dumps({
            "observed_at": now.isoformat().replace("+00:00", "Z"),
            "seven_day": {"used_percentage": 50, "resets_at": (now + dt.timedelta(days=3)).isoformat()}
        }))
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_REMOTE": "true", "USAGE_OPTIMIZER_MODE": "auto"}, clear=False):
            mode, reason = meter._kit_mode(str(self.usage), now)
        self.assertIn(mode, meter.MODES)
        self.assertIn("auto, cloud probe reading", reason)


if __name__ == "__main__":
    unittest.main()
