import datetime as dt
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAKE = os.path.join(os.path.dirname(__file__), "fake_codex.py")


def load_script(name, filename):
    loader = importlib.machinery.SourceFileLoader(name, os.path.join(ROOT, "bin", filename))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    loader.exec_module(module)
    return module


usage = load_script("usage_status_tested", "usage-status")
statusline = load_script("claude_statusline_tested", "claude-statusline")


def _strip_sgr(value):
    return re.sub(r"\x1b\[[0-9;]*m", "", value)


class CodexMeterTests(unittest.TestCase):
    def setUp(self):
        self.old_env = os.environ.copy()
        self.temp = tempfile.TemporaryDirectory()
        self.root = self.temp.name
        self.state = os.path.join(self.root, "usage")
        self.codex_home = os.path.join(self.root, "codex")
        self.config = os.path.join(self.root, "claude-config")
        self.lanes = os.path.join(self.root, "lanes")
        for path in (self.state, self.codex_home, self.config, self.lanes):
            os.makedirs(path)
        self.log = os.path.join(self.root, "methods.log")
        self.fake_bin = FAKE
        if os.name == "nt":
            self.fake_bin = os.path.join(self.root, "fake-codex.cmd")
            with open(self.fake_bin, "w", encoding="utf-8") as handle:
                handle.write('@echo off\r\n"{}" "{}" %*\r\n'.format(sys.executable, FAKE))
        os.environ.update({
            "HOME": self.root,
            "TMPDIR": self.root,
            "CLAUDE_USAGE_DIR": self.state,
            "CODEX_HOME": self.codex_home,
            "CLAUDE_CONFIG_DIR": self.config,
            "LANES_STATE": self.lanes,
            "USAGE_OPTIMIZER_CODEX_BIN": self.fake_bin,
            "USAGE_OPTIMIZER_CODEX_TIMEOUT": "2",
            "USAGE_OPTIMIZER_CODEX_TTL": "300",
            "USAGE_OPTIMIZER_CODEX_LIVE": "1",
            "USAGE_OPTIMIZER_CODEX": "auto",
            "NO_COLOR": "1",
            "USAGE_OPTIMIZER_KIT_LABEL": "off",
            "FAKE_CODEX_MODE": "pro",
            "FAKE_CODEX_LOG": self.log,
        })
        os.environ.pop("COLUMNS", None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old_env)
        self.temp.cleanup()

    def env(self, **overrides):
        result = os.environ.copy()
        result.update({key: str(value) for key, value in overrides.items()})
        return result

    def cache_path(self, directory=None):
        return os.path.join(directory or self.state, "codex-latest.json")

    def read_cache(self, directory=None):
        with open(self.cache_path(directory), "r", encoding="utf-8") as handle:
            return json.load(handle)

    def write_cache(self, cache, directory=None):
        folder = directory or self.state
        os.makedirs(folder, exist_ok=True)
        with open(self.cache_path(folder), "w", encoding="utf-8") as handle:
            json.dump(cache, handle)

    def sample_statusline(self, env=None, script=None, data=None):
        data = data or {
            "model": {"display_name": "Claude Test"},
            "effort": {"level": "high"},
            "context_window": {"used_percentage": 12},
            "rate_limits": {
                "five_hour": {"used_percentage": 8, "resets_at": "2099-01-01T12:00:00Z"},
                "seven_day": {"used_percentage": 25, "resets_at": "2099-01-03T12:00:00Z"},
                "limits": [{"kind": "weekly_scoped", "name": "work", "used_percentage": 4,
                            "resets_at": "2099-01-03T12:00:00Z"}],
            },
        }
        return subprocess.run([sys.executable, script or os.path.join(ROOT, "bin", "claude-statusline")],
                              input=json.dumps(data), text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, env=env or os.environ.copy(),
                              timeout=10, check=False)

    def test_statusline_turn_segment_shows_elapsed_eta_and_bad_start_fallback(self):
        opened = os.path.join(self.lanes, "turns", "open", "segment-session.json")
        os.makedirs(os.path.dirname(opened), exist_ok=True)
        started = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=12)).isoformat().replace("+00:00", "Z")
        with open(os.path.join(self.lanes, "claude-calibration.json"), "w", encoding="utf-8") as handle:
            json.dump({"pct_per_usd": 0.04}, handle)
        turn = {"session_id": "segment-session", "started_at": started, "cost_start_usd": 1.0}
        with open(opened, "w", encoding="utf-8") as handle:
            json.dump(turn, handle)
        data = {"session_id": "segment-session", "cost": {"total_cost_usd": 2.0}}
        no_eta = statusline._turn_segment(data)
        self.assertRegex(no_eta, r"^ETA ~13m ≈0\.04% wk$")

        turn["eta"] = {"elapsed_minutes": 10, "remaining_minutes": 10, "factor": 2}
        with open(opened, "w", encoding="utf-8") as handle:
            json.dump(turn, handle)
        with_eta = statusline._turn_segment(data)
        self.assertRegex(with_eta, r"^ETA ~18m ≈0\.04% wk$")
        turn["eta"]["remaining_minutes"] = 33.5
        with open(opened, "w", encoding="utf-8") as handle:
            json.dump(turn, handle)
        self.assertRegex(statusline._turn_segment(data), r"^ETA ~1h05 ≈0\.04% wk$")

        turn["started_at"] = "not-a-timestamp"
        with open(opened, "w", encoding="utf-8") as handle:
            json.dump(turn, handle)
        self.assertEqual(statusline._turn_segment(data), "turn ≈0.04% wk")

    def run_usage_json(self, env=None):
        return subprocess.run([sys.executable, os.path.join(ROOT, "bin", "usage-status"),
                               "--json", "--no-agy"], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True, env=env or os.environ.copy(),
                              timeout=12, check=False)

    def test_each_fake_mode_populates_expected_cache_fields(self):
        expected = {
            "pro": ("ok", "live", "prolite", ["weekly"], 2),
            "plus": ("ok", "live", "plus", ["5h", "weekly"], 0),
            "reached": ("ok", "live", "prolite", ["weekly"], 2),
            "noise": ("ok", "live", "prolite", ["weekly"], 2),
            "logged_out": ("logged_out", "none", None, [], None),
            "api_key": ("api_key", "none", None, [], None),
            "unsupported": ("unsupported", "none", None, [], None),
        }
        for mode, values in expected.items():
            with self.subTest(mode=mode):
                os.environ["FAKE_CODEX_MODE"] = mode
                folder = os.path.join(self.root, mode)
                os.makedirs(folder)
                cache = usage.codex_refresh(self.codex_home, folder, live_enabled=True)
                self.assertEqual((cache["status"], cache["source"], cache["plan_type"],
                                  [window["label"] for window in cache["windows"]],
                                  cache["reset_credits"]), values)
                self.assertIn("observed_at", cache)
                self.assertIn("reading_at", cache)
                self.assertIn("ordinary_usage_allowed", cache)
                self.assertIn("reached", cache)
                self.assertIn("error_code", cache)
                self.assertIn("kit_version", cache)
                self.assertNotIn("accountId", json.dumps(cache))
                if cache["status"] == "ok":
                    self.assertEqual(cache["reading_at"], cache["observed_at"])
                    self.assertIsNone(cache["error_code"])
                    if mode == "reached":
                        self.assertEqual(cache["reached"], "weekly")
                        self.assertIs(cache["ordinary_usage_allowed"], False)
                    else:
                        self.assertIsNone(cache["reached"])
                        self.assertIs(cache["ordinary_usage_allowed"], True)
                else:
                    self.assertIsNone(cache["reading_at"])
                    self.assertIsNone(cache["ordinary_usage_allowed"])
                if mode == "logged_out":
                    self.assertEqual(cache["error_code"], 401)
                if mode == "api_key":
                    self.assertEqual(cache["error_code"], 401)
                if mode == "unsupported":
                    self.assertEqual(cache["error_code"], -32601)

    def test_hang_is_timeout_within_deadline(self):
        os.environ["FAKE_CODEX_MODE"] = "hang"
        started = time.monotonic()
        cache = usage.codex_refresh(self.codex_home, self.state, timeout=0.2, live_enabled=True)
        self.assertEqual(cache["status"], "timeout")
        self.assertLess(time.monotonic() - started, 4.5)
        self.assertFalse(os.path.exists(os.path.join(self.state, "codex-refresh.lock")))

    def test_server_exit_before_response_is_exited(self):
        for initialized in (False, True):
            with self.subTest(initialized=initialized):
                script = os.path.join(self.root, "exit-server.py")
                with open(script, "w", encoding="utf-8") as handle:
                    handle.write("#!{}\nimport sys\n".format(sys.executable))
                    if initialized:
                        handle.write('sys.stdin.readline()\n'
                                     'print(\'{"id":1,"result":{}}\', flush=True)\n')
                os.chmod(script, 0o700)
                executable = script
                if os.name == "nt":
                    executable = os.path.join(self.root, "exit-server.cmd")
                    with open(executable, "w", encoding="utf-8") as handle:
                        handle.write('@echo off\r\n"{}" "{}" %*\r\n'.format(sys.executable, script))
                os.environ["USAGE_OPTIMIZER_CODEX_BIN"] = executable
                cache = usage.codex_refresh(self.codex_home, self.state, timeout=2, live_enabled=True)
                self.assertEqual(cache["status"], "exited")
                section = usage.codex_section(self.codex_home, dt.datetime.now(usage.UTC), self.state)
                self.assertIn("live read failed (exited)", str(section))

    def test_refresh_path_timeout_defaults_and_environment_override(self):
        for override, background, synchronous in ((None, 30, 15), ("4", 4, 4)):
            with self.subTest(override=override):
                os.environ.pop("USAGE_OPTIMIZER_CODEX_TIMEOUT", None)
                if override is not None:
                    os.environ["USAGE_OPTIMIZER_CODEX_TIMEOUT"] = override
                with mock.patch.object(usage, "codex_live_read", return_value={"status": "error"}) as live:
                    with mock.patch.object(sys, "argv", ["usage-status", "--codex-refresh"]):
                        self.assertEqual(usage.main(), 0)
                    self.assertEqual(usage.codex_timeout(live.call_args.args[0]), background)
                    os.unlink(self.cache_path())
                    usage.codex_section(self.codex_home, dt.datetime.now(usage.UTC), self.state)
                    self.assertEqual(usage.codex_timeout(live.call_args.args[0]), synchronous)
                    usage.codex_refresh(self.codex_home, self.state, timeout=0.3)
                    self.assertEqual(live.call_args.args[0], 0.3)
                    self.assertEqual(usage.codex_timeout(0.3), 0.3)

    def test_only_safe_rpc_methods_are_sent(self):
        usage.codex_refresh(self.codex_home, self.state, live_enabled=True)
        with open(self.log, "r", encoding="utf-8") as handle:
            methods = handle.read().splitlines()
        self.assertEqual(methods, ["initialize", "initialized", "account/rateLimits/read"])
        self.assertNotIn("account/rateLimitResetCredit/consume", methods)
        self.assertNotIn("account/read", methods)

    def test_no_codex_live_flag_skips_the_app_server(self):
        result = subprocess.run([sys.executable, os.path.join(ROOT, "bin", "usage-status"),
                                 "--json", "--no-agy", "--no-codex-live"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                env=os.environ.copy(), timeout=10, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["codex"]["status"], "live_off")
        self.assertFalse(os.path.exists(self.log))

    def test_usage_json_omits_retired_lanes(self):
        result = self.run_usage_json()
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertNotIn("muse", data)
        self.assertNotIn("cursor", data)
        self.assertNotIn("Muse", result.stdout)
        self.assertNotIn("cursor-agent", result.stdout)

    def test_missing_codex_binary_is_no_cli(self):
        os.environ["USAGE_OPTIMIZER_CODEX_BIN"] = os.path.join(self.root, "missing-codex")
        cache = usage.codex_refresh(self.codex_home, self.state, live_enabled=True)
        self.assertEqual(cache["status"], "no_cli")
        self.assertEqual(cache["source"], "none")
        self.assertFalse(os.path.exists(self.log))

    def test_live_failure_uses_newest_rollout_and_keeps_failure_status(self):
        today = dt.datetime.now(dt.timezone.utc).date()
        folder = os.path.join(self.codex_home, "sessions", today.strftime("%Y"),
                              today.strftime("%m"), today.strftime("%d"))
        os.makedirs(folder)
        event = {"type": "event_msg", "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
                 "payload": {"type": "token_count", "rate_limits": {
                     "plan_type": "prolite", "primary": {"used_percent": 44,
                     "window_minutes": 10080, "resets_at": "2099-01-03T12:00:00Z"}}}}
        with open(os.path.join(folder, "rollout-test.jsonl"), "w", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")
        os.environ["FAKE_CODEX_MODE"] = "logged_out"
        cache = usage.codex_refresh(self.codex_home, self.state, live_enabled=True)
        self.assertEqual(cache["source"], "rollout")
        self.assertEqual(cache["status"], "logged_out")
        self.assertEqual(cache["plan_type"], "prolite")
        self.assertEqual(cache["windows"][0]["used_percent"], 44)
        self.assertEqual(cache["windows"][0]["label"], "weekly")

    def test_account_id_never_reaches_cache_or_usage_json(self):
        usage.codex_refresh(self.codex_home, self.state, live_enabled=True)
        with open(self.cache_path(), "r", encoding="utf-8") as handle:
            cache_text = handle.read()
        self.assertNotIn("accountId", cache_text)
        result = self.run_usage_json()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("must-never-be-stored-or-printed", result.stdout)
        self.assertNotIn("accountId", result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["codex"]["source"], "live")
        for key in ("reading", "five_hour", "seven_day", "age_seconds", "plan_type"):
            self.assertIn(key, payload["codex"])

    def test_hint_texts_for_out_tight_and_logged_out(self):
        os.environ["FAKE_CODEX_MODE"] = "reached"
        result = self.run_usage_json()
        self.assertIn("Codex is out with 2 reset credits available", json.loads(result.stdout)["hint"])

        now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        base = {"observed_at": now, "source": "live", "status": "ok", "reading_at": now,
                "plan_type": "prolite", "reached": "weekly", "ordinary_usage_allowed": False,
                "reset_credits": 0, "error_code": None, "kit_version": None, "reading": None,
                "windows": [{"label": "weekly", "window_minutes": 10080,
                             "used_percent": 97, "resets_at": "2099-01-03T12:00:00Z"}]}
        self.write_cache(base)
        result = self.run_usage_json()
        self.assertIn("Codex weekly ≥95%: Codex is out", json.loads(result.stdout)["hint"])

        base["reached"] = None
        base["ordinary_usage_allowed"] = True
        base["reset_credits"] = 1
        base["windows"] = [{"label": "5h", "window_minutes": 300,
                            "used_percent": 85, "resets_at": "2099-01-01T12:00:00Z"}]
        self.write_cache(base)
        result = self.run_usage_json()
        self.assertIn("1 reset credit available (the user applies them)",
                      json.loads(result.stdout)["hint"])

        base.update({"source": "none", "status": "logged_out", "reading_at": None,
                     "windows": [], "reset_credits": None})
        self.write_cache(base)
        result = self.run_usage_json()
        self.assertEqual(json.loads(result.stdout)["hint"],
                         "Codex logged out: route Codex units to gemini until codex login")

    def test_statusline_auth_status_hides_rollout_windows(self):
        future = "2099-01-05T12:00:00Z"
        for status, expected in (("logged_out", "Codex logged out"), ("api_key", "Codex api key")):
            with self.subTest(status=status):
                cache = self.status_cache(status, [{"label": "weekly", "window_minutes": 10080,
                                                   "used_percent": 85, "resets_at": future}])
                cache["reading_at"] = (dt.datetime.now(dt.timezone.utc) -
                                        dt.timedelta(hours=2)).isoformat().replace("+00:00", "Z")
                self.write_cache(cache)
                result = self.sample_statusline()
                self.assertTrue(result.stdout.rstrip("\n").endswith("│ " + expected),
                                result.stdout)

    def test_statusline_uses_cached_weekly_label_when_length_is_missing(self):
        cache = self.status_cache(windows=[{"label": "weekly", "used_percent": 36,
                                           "resets_at": "2099-01-05T12:00:00Z"}])
        self.write_cache(cache)
        result = self.sample_statusline(self.env(USAGE_OPTIMIZER_TZ="UTC"))
        self.assertTrue(result.stdout.rstrip("\n").endswith("Codex wk 36% resets Mon 12:00"))

    def test_stale_cache_spawn_marker_throttles_failed_refreshes(self):
        bin_dir = os.path.join(self.root, "copied-bin")
        os.makedirs(bin_dir)
        statusline_copy = os.path.join(bin_dir, "claude-statusline")
        shutil.copyfile(os.path.join(ROOT, "bin", "claude-statusline"), statusline_copy)
        counter = os.path.join(self.root, "refresh-count.txt")
        fake_usage_status = os.path.join(bin_dir, "usage-status")
        with open(fake_usage_status, "w", encoding="utf-8") as handle:
            handle.write("\n".join(("import os",
                                     "with open(os.environ['FAKE_USAGE_STATUS_COUNT'], 'a') as f:",
                                     "    f.write('refresh' + chr(10))")) + "\n")

        old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        cache = self.status_cache(windows=[{"label": "weekly", "window_minutes": 10080,
                                           "used_percent": 36, "resets_at": "2099-01-05T12:00:00Z"}])
        cache["observed_at"] = old
        self.write_cache(cache)
        env = self.env(FAKE_USAGE_STATUS_COUNT=counter)

        first = self.sample_statusline(env, statusline_copy)
        self.assertEqual(first.returncode, 0, first.stderr)
        deadline = time.monotonic() + 5
        while not os.path.exists(counter) and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue(os.path.exists(counter))
        marker = os.path.join(self.state, "codex-refresh.spawned")
        first_marker_mtime = os.path.getmtime(marker)
        self.assertEqual(self.read_cache()["observed_at"], old)

        second = self.sample_statusline(env, statusline_copy)
        self.assertEqual(second.returncode, 0, second.stderr)
        time.sleep(0.2)
        self.assertEqual(os.path.getmtime(marker), first_marker_mtime)
        with open(counter, "r", encoding="utf-8") as handle:
            self.assertEqual(handle.read().splitlines(), ["refresh"])

    def test_logged_out_hint_precedes_tight_weekly_rollout(self):
        stamp = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        cache = self.status_cache("logged_out", [{"label": "weekly", "window_minutes": 10080,
                                                   "used_percent": 85,
                                                   "resets_at": "2099-01-05T12:00:00Z"}],
                                  source="rollout", reading_at=stamp)
        self.write_cache(cache)
        result = self.run_usage_json()
        self.assertEqual(json.loads(result.stdout)["hint"],
                         "Codex logged out: route Codex units to gemini until codex login")

        cache["status"] = "api_key"
        self.write_cache(cache)
        result = self.run_usage_json()
        self.assertEqual(json.loads(result.stdout)["hint"],
                         "Codex is on an API key here, no plan meter: route by its billing, not by this meter")

    def test_plus_weekly_tight_hint_even_with_five_hour_window(self):
        stamp = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        cache = self.status_cache("ok", [
            {"label": "5h", "window_minutes": 300, "used_percent": 30,
             "resets_at": "2099-01-01T12:00:00Z"},
            {"label": "weekly", "window_minutes": 10080, "used_percent": 85,
             "resets_at": "2099-01-05T12:00:00Z"}],
            plan_type="plus", reading_at=stamp, reset_credits=2)
        self.write_cache(cache)
        result = self.run_usage_json()
        hint = json.loads(result.stdout)["hint"]
        self.assertTrue(hint.startswith("Codex weekly window tight:"), hint)
        self.assertIn("2 reset credits available (the user applies them)", hint)

    def test_codex_refresh_flag_is_silent_and_lock_prevents_second_refresh(self):
        env = self.env(USAGE_OPTIMIZER_CODEX_TIMEOUT="0.2", FAKE_CODEX_MODE="hang")
        result = subprocess.run([sys.executable, os.path.join(ROOT, "bin", "usage-status"),
                                 "--codex-refresh"], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, env=env,
                                timeout=7, check=False)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.read_cache()["status"], "timeout")

        os.unlink(self.log)
        with open(os.path.join(self.state, "codex-refresh.lock"), "w", encoding="utf-8") as handle:
            handle.write("locked")
        result = subprocess.run([sys.executable, os.path.join(ROOT, "bin", "usage-status"),
                                 "--codex-refresh"], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, env=env,
                                timeout=5, check=False)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertFalse(os.path.exists(self.log))

    def status_cache(self, status="ok", windows=None, **extra):
        now = dt.datetime.now(dt.timezone.utc)
        stamp = now.isoformat().replace("+00:00", "Z")
        cache = {"observed_at": stamp, "source": "live", "status": status,
                 "reading_at": stamp, "plan_type": "prolite", "windows": windows or [],
                 "reached": None, "ordinary_usage_allowed": True, "reset_credits": 2,
                 "error_code": None, "kit_version": None, "reading": None}
        cache.update(extra)
        return cache

    def test_statusline_pro_plus_logged_out_out_stale_off_and_missing_cli(self):
        future = "2099-01-03T12:00:00Z"
        self.write_cache(self.status_cache(windows=[{"label": "weekly", "window_minutes": 10080,
                                                     "used_percent": 36, "resets_at": future}]))
        result = self.sample_statusline()
        self.assertIn("Codex wk 36% resets ", result.stdout)
        codex_part = result.stdout.split(" │ Codex ", 1)[1]
        self.assertNotIn("5h", codex_part)

        self.write_cache(self.status_cache("ok", [
            {"label": "5h", "window_minutes": 300, "used_percent": 3, "resets_at": future},
            {"label": "weekly", "window_minutes": 10080, "used_percent": 0, "resets_at": future}]))
        result = self.sample_statusline()
        self.assertIn("Codex 5h 3% resets ", result.stdout)
        self.assertIn(" · wk 0% resets ", result.stdout)

        self.write_cache(self.status_cache("logged_out", []))
        self.assertIn("Codex logged out", self.sample_statusline().stdout)

        self.write_cache(self.status_cache("ok", [{"label": "weekly", "window_minutes": 10080,
                                                     "used_percent": 36, "resets_at": future}],
                                           ordinary_usage_allowed=False))
        self.assertIn("Codex OUT wk 36% resets ", self.sample_statusline().stdout)

        old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=20)).isoformat().replace("+00:00", "Z")
        cache = self.status_cache(windows=[{"label": "weekly", "window_minutes": 10080,
                                           "used_percent": 36, "resets_at": future}])
        cache["reading_at"] = old
        self.write_cache(cache)
        self.assertIn("(20m old)", self.sample_statusline().stdout)

        self.write_cache(self.status_cache(windows=[{"label": "weekly", "window_minutes": 10080,
                                                     "used_percent": 36, "resets_at": future}]))
        result = self.sample_statusline(self.env(USAGE_OPTIMIZER_CODEX="off"))
        self.assertNotIn("codex", result.stdout.lower())

        os.unlink(self.cache_path())
        missing_home = os.path.join(self.root, "no-codex-home")
        missing_bin = os.path.join(self.root, "missing-codex")
        env = self.env(CODEX_HOME=missing_home, USAGE_OPTIMIZER_CODEX_BIN=missing_bin)
        result = self.sample_statusline(env)
        self.assertNotIn("codex", result.stdout.lower())
        self.assertFalse(os.path.exists(os.path.join(self.state, "codex-refresh.lock")))

    def test_statusline_pro_plus_labels(self):
        future = "2099-01-03T12:00:00Z"
        self.write_cache(self.status_cache(windows=[{"label": "weekly", "window_minutes": 10080,
                                                     "used_percent": 36, "resets_at": future}]))
        result = self.sample_statusline()
        self.assertIn("Codex wk 36% resets ", result.stdout)
        codex_part = result.stdout.split(" │ Codex ", 1)[1]
        self.assertNotIn("5h", codex_part)
        self.write_cache(self.status_cache("ok", [
            {"label": "5h", "window_minutes": 300, "used_percent": 3, "resets_at": future},
            {"label": "weekly", "window_minutes": 10080, "used_percent": 0, "resets_at": future}]))
        result = self.sample_statusline()
        self.assertIn("Codex 5h 3% resets ", result.stdout)
        self.assertIn(" · wk 0% resets ", result.stdout)

    def test_statusline_end_to_end_detached_refresh_updates_stale_cache(self):
        old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        cache = self.status_cache(windows=[{"label": "weekly", "window_minutes": 10080,
                                           "used_percent": 1, "resets_at": "2099-01-03T12:00:00Z"}])
        cache["observed_at"] = old
        self.write_cache(cache)
        result = self.sample_statusline()
        self.assertEqual(result.returncode, 0, result.stderr)
        before = usage.parse_time(old)
        deadline = time.monotonic() + 10
        refreshed = None
        while time.monotonic() < deadline:
            try:
                refreshed = self.read_cache()
            except (OSError, ValueError):
                refreshed = None
            stamp = usage.parse_time(refreshed.get("observed_at")) if isinstance(refreshed, dict) else None
            if stamp and stamp > before and refreshed.get("source") == "live":
                break
            time.sleep(0.1)
        self.assertIsNotNone(stamp)
        self.assertGreater(stamp, before)
        self.assertEqual(refreshed["source"], "live")

    def test_existing_statusline_segments_are_unchanged(self):
        off_env = self.env(USAGE_OPTIMIZER_CODEX="off")
        baseline = self.sample_statusline(off_env).stdout
        self.write_cache(self.status_cache(windows=[{"label": "weekly", "window_minutes": 10080,
                                                     "used_percent": 36, "resets_at": "2099-01-03T12:00:00Z"}]))
        full = self.sample_statusline(self.env(USAGE_OPTIMIZER_CODEX="auto")).stdout
        self.assertEqual(full.splitlines()[0], baseline.splitlines()[0])
        self.assertEqual(full.splitlines()[1].split(" │ ")[0], baseline.splitlines()[1])
        self.assertTrue(full.rstrip("\n").split(" │ ")[-1].startswith("Codex wk 36% resets "))

    def layout_data(self, codex=False, scoped=False, plus=False, context=True):
        data = {"model": {"display_name": "Opus 5.5 (1M context)"},
                "effort": {"level": "xhigh"}, "rate_limits": {}}
        if context:
            data["context_window"] = {
                "current_usage": {"input_tokens": 321000, "cache_creation_input_tokens": 0,
                                  "cache_read_input_tokens": 0},
                "context_window_size": 450000, "used_percentage": 71}
        if codex or scoped:
            data["rate_limits"].update({
                "five_hour": {"used_percentage": 9, "resets_at": "2099-01-05T10:40:00Z"},
                "seven_day": {"used_percentage": 23, "resets_at": "2099-01-11T12:00:00Z"}})
        if scoped:
            data["rate_limits"]["limits"] = [
                {"kind": "weekly_scoped", "name": "Fable", "used_percentage": 7,
                 "resets_at": "2099-01-11T02:00:00Z"}]
        if plus:
            data["rate_limits"]["five_hour"] = {
                "used_percentage": 9, "resets_at": "2099-01-05T10:40:00Z"}
        return data

    def layout_env(self, **overrides):
        env = self.env(USAGE_OPTIMIZER_TZ="UTC", NO_COLOR="1", **overrides)
        if "COLUMNS" not in overrides:
            env.pop("COLUMNS", None)
        return env

    def test_layout_pro_example_is_exactly_two_lines(self):
        cache = self.status_cache(windows=[{"label": "weekly", "window_minutes": 10080,
                                           "used_percent": 37, "resets_at": "2099-01-05T21:51:00Z"}])
        self.write_cache(cache)
        result = self.sample_statusline(self.layout_env(), data=self.layout_data(codex=True))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, (
            "Opus 5.5 · xhigh · ctx 321k/450k (71%)\n"
            "Claude 5h 9% resets 10:40 · wk 23% resets Sun 12:00 │ Codex wk 37% resets Mon 21:51\n"))

    def test_layout_plus_and_scoped_claude_window(self):
        cache = self.status_cache("ok", [
            {"label": "5h", "window_minutes": 300, "used_percent": 3,
             "resets_at": "2099-01-05T14:03:00Z"},
            {"label": "weekly", "window_minutes": 10080, "used_percent": 41,
             "resets_at": "2099-01-05T21:51:00Z"}], plan_type="plus")
        self.write_cache(cache)
        result = self.sample_statusline(self.layout_env(), data=self.layout_data(scoped=True, plus=True))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Fable 7% resets Sun 02:00", result.stdout)
        self.assertIn("Codex 5h 3% resets 14:03 · wk 41% resets Mon 21:51", result.stdout)

    def test_layout_omits_second_line_when_no_quotas_are_available(self):
        env = self.layout_env(USAGE_OPTIMIZER_CODEX_BIN=os.path.join(self.root, "missing-codex"),
                              CODEX_HOME=os.path.join(self.root, "missing-codex-home"),
                              USAGE_OPTIMIZER_CODEX="auto")
        result = self.sample_statusline(env, data={
            "model": {"display_name": "Opus 5.5 (1M context)"},
            "effort": {"level": "xhigh"}, "context_window": {"used_percentage": 71}})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "Opus 5.5 · xhigh · ctx 71%\n")
        self.assertFalse(os.path.exists(os.path.join(self.state, "codex-refresh.lock")))

    def test_layout_colors_percentages_out_and_color_disabling(self):
        self.write_cache(self.status_cache(windows=[{"label": "weekly", "window_minutes": 10080,
                                                     "used_percent": 96,
                                                     "resets_at": "2099-01-05T21:51:00Z"}],
                                           reached="weekly"))
        data = self.layout_data(codex=True)
        data["context_window"] = {"current_usage": {
            "input_tokens": 85000, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
            "context_window_size": 100000, "used_percentage": 85}
        color_env = self.env(USAGE_OPTIMIZER_TZ="UTC")
        color_env.pop("NO_COLOR", None)
        result = self.sample_statusline(color_env, data=data)
        self.assertIn("\x1b[33m85%\x1b[0m", result.stdout)
        self.assertIn("\x1b[31m96%\x1b[0m", result.stdout)
        self.assertIn("\x1b[31mOUT\x1b[0m", result.stdout)

        for overrides in ({"NO_COLOR": ""}, {"USAGE_OPTIMIZER_COLOR": "off"}):
            env = self.env(USAGE_OPTIMIZER_TZ="UTC", **overrides)
            if "USAGE_OPTIMIZER_COLOR" in overrides:
                env.pop("NO_COLOR", None)
            result = self.sample_statusline(env, data=data)
            self.assertNotIn("\x1b", result.stdout)

    def test_layout_width_degrades_resets_then_truncates_safely(self):
        windows = [
            {"label": "5h", "window_minutes": 300, "used_percent": 23,
             "resets_at": "2099-01-05T14:03:00Z"},
            {"label": "weekly", "window_minutes": 10080, "used_percent": 23,
             "resets_at": "2099-01-05T21:51:00Z"}]
        self.write_cache(self.status_cache("ok", windows))
        data = self.layout_data(codex=True)
        data["rate_limits"]["five_hour"]["used_percentage"] = 85

        at_64 = self.sample_statusline(self.layout_env(COLUMNS="64"), data=data).stdout
        self.assertIn("5h 85% resets 10:40", at_64)
        self.assertNotIn("wk 23% resets ", at_64)
        self.assertNotIn("Codex 5h 23% resets ", at_64)

        at_40 = self.sample_statusline(self.layout_env(COLUMNS="40"), data=data).stdout
        self.assertNotIn("resets ", at_40)

        narrow_env = self.env(COLUMNS="20", USAGE_OPTIMIZER_TZ="UTC")
        narrow_env.pop("NO_COLOR", None)
        at_20 = self.sample_statusline(narrow_env, data=data).stdout
        for line in at_20.splitlines():
            self.assertLessEqual(len(_strip_sgr(line)), 20)
            self.assertTrue(_strip_sgr(line).endswith("…"), line)
            self.assertIsNone(re.search(r"\x1b\[(?![0-9;]*m)", line), line)
            active = False
            for sgr in re.findall(r"\x1b\[([0-9;]*)m", line):
                active = sgr not in ("0", ";0")
            self.assertFalse(active, line)

    def test_layout_strips_model_parenthetical_and_effort_prefix(self):
        result = self.sample_statusline(self.layout_env(USAGE_OPTIMIZER_CODEX="off"),
                                        data=self.layout_data(context=False))
        self.assertEqual(result.stdout, "Opus 5.5 · xhigh\n")

    def test_layout_does_not_change_claude_usage_logging(self):
        directory = os.path.join(self.root, "layout-log")
        data = self.layout_data(scoped=True)
        data["session_id"] = "layout-session"
        env = self.layout_env(CLAUDE_USAGE_DIR=directory, USAGE_OPTIMIZER_CODEX="off")
        result = self.sample_statusline(env, data=data)
        self.assertEqual(result.returncode, 0, result.stderr)
        with open(os.path.join(directory, "claude-latest.json"), "r", encoding="utf-8") as handle:
            latest = json.load(handle)
        self.assertEqual(latest["model"], "Opus 5.5 (1M context)")
        self.assertEqual(latest["session_id"], "layout-session")
        self.assertEqual(latest["five_hour"], {"used_percentage": 9,
                                                "resets_at": "2099-01-05T10:40:00Z"})
        self.assertEqual(latest["seven_day"], {"used_percentage": 23,
                                                "resets_at": "2099-01-11T12:00:00Z"})
        self.assertEqual(latest["scoped"], [{"kind": "weekly_scoped", "name": "Fable",
                                             "used_percentage": 7,
                                             "resets_at": "2099-01-11T02:00:00Z"}])
        with open(os.path.join(directory, "claude-rate.jsonl"), "r", encoding="utf-8") as handle:
            history = [json.loads(line) for line in handle]
        self.assertEqual(history, [latest])

    def test_idle_sessions_do_not_replace_fresh_claude_readings(self):
        directory = os.path.join(self.root, "fresh-log")
        env = self.env(CLAUDE_USAGE_DIR=directory, USAGE_OPTIMIZER_CODEX="off")

        def sample(session, cost, pct):
            data = self.layout_data(codex=True)
            data.update({"session_id": session, "cost": {"total_cost_usd": cost}})
            data["rate_limits"]["seven_day"]["used_percentage"] = pct
            result = self.sample_statusline(env, data=data)
            self.assertEqual(result.returncode, 0, result.stderr)

        sample("moving", 1, 5)  # A session's first reading is fresh.
        sample("idle", 1, 4)
        sample("moving", 2, 6)
        sample("idle", 1, 4)  # Its unchanged cost must not restore 4%.
        with open(os.path.join(directory, "claude-latest.json"), "r", encoding="utf-8") as handle:
            self.assertEqual(json.load(handle)["seven_day"]["used_percentage"], 6)
        with open(os.path.join(directory, "claude-rate.jsonl"), "r", encoding="utf-8") as handle:
            self.assertEqual([json.loads(line)["seven_day"]["used_percentage"] for line in handle], [5, 4, 6])

        data = self.layout_data(codex=True)
        data.update({"session_id": "idle"})  # A missing cost keeps the previous write behaviour.
        data["rate_limits"]["seven_day"]["used_percentage"] = 7
        self.assertEqual(self.sample_statusline(env, data=data).returncode, 0)
        with open(os.path.join(directory, "claude-latest.json"), "r", encoding="utf-8") as handle:
            self.assertEqual(json.load(handle)["seven_day"]["used_percentage"], 7)

    def test_live_read_resolves_codex_from_lane_bin_folder(self):
        config_dir = os.path.join(self.root, "lane_config")
        bin_dir = os.path.join(config_dir, "bin")
        os.makedirs(bin_dir)
        fake_lane_log = os.path.join(self.root, "lane_codex.log")
        if os.name == "nt":
            fake_bin = os.path.join(bin_dir, "codex.cmd")
            with open(fake_bin, "w", encoding="utf-8") as handle:
                handle.write('@echo off\r\nset "FAKE_CODEX_LOG={}"\r\n"{}" "{}" %*\r\n'.format(
                    fake_lane_log, sys.executable, FAKE))
        else:
            fake_bin = os.path.join(bin_dir, "codex")
            with open(fake_bin, "w", encoding="utf-8") as handle:
                handle.write('#!/bin/sh\nexport FAKE_CODEX_LOG="{}"\nexec "{}" "{}" "$@"\n'.format(
                    fake_lane_log, sys.executable, FAKE))
            os.chmod(fake_bin, 0o755)

        os.environ.pop("USAGE_OPTIMIZER_CODEX_BIN", None)
        os.environ["LANES_CONFIG"] = config_dir
        os.environ["PATH"] = self.root

        read = usage.codex_live_read()
        self.assertEqual(read.get("status"), "ok")
        self.assertTrue(os.path.exists(fake_lane_log))

    def test_live_read_prefers_env_var_over_lane_bin_folder(self):
        config_dir = os.path.join(self.root, "lane_config_env")
        bin_dir = os.path.join(config_dir, "bin")
        os.makedirs(bin_dir)
        fake_lane_log = os.path.join(self.root, "lane_unused.log")
        fake_env_log = os.path.join(self.root, "env_used.log")

        if os.name == "nt":
            lane_bin = os.path.join(bin_dir, "codex.cmd")
            with open(lane_bin, "w", encoding="utf-8") as handle:
                handle.write('@echo off\r\nset "FAKE_CODEX_LOG={}"\r\n"{}" "{}" %*\r\n'.format(
                    fake_lane_log, sys.executable, FAKE))
            env_bin = os.path.join(self.root, "env_codex.cmd")
            with open(env_bin, "w", encoding="utf-8") as handle:
                handle.write('@echo off\r\nset "FAKE_CODEX_LOG={}"\r\n"{}" "{}" %*\r\n'.format(
                    fake_env_log, sys.executable, FAKE))
        else:
            lane_bin = os.path.join(bin_dir, "codex")
            with open(lane_bin, "w", encoding="utf-8") as handle:
                handle.write('#!/bin/sh\nexport FAKE_CODEX_LOG="{}"\nexec "{}" "{}" "$@"\n'.format(
                    fake_lane_log, sys.executable, FAKE))
            os.chmod(lane_bin, 0o755)
            env_bin = os.path.join(self.root, "env_codex")
            with open(env_bin, "w", encoding="utf-8") as handle:
                handle.write('#!/bin/sh\nexport FAKE_CODEX_LOG="{}"\nexec "{}" "{}" "$@"\n'.format(
                    fake_env_log, sys.executable, FAKE))
            os.chmod(env_bin, 0o755)

        os.environ["LANES_CONFIG"] = config_dir
        os.environ["USAGE_OPTIMIZER_CODEX_BIN"] = env_bin

        read = usage.codex_live_read()
        self.assertEqual(read.get("status"), "ok")
        self.assertTrue(os.path.exists(fake_env_log))
        self.assertFalse(os.path.exists(fake_lane_log))


if __name__ == "__main__":
    unittest.main()
