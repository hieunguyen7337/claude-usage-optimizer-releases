import contextlib
import datetime as dt
import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USAGE = os.path.join(ROOT, "bin", "usage-status")
FAKE = os.path.join(os.path.dirname(__file__), "fake_codex.py")


def load_script(name, filename):
    loader = importlib.machinery.SourceFileLoader(name, os.path.join(ROOT, "bin", filename))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    loader.exec_module(module)
    return module


usage = load_script("usage_status_local", "usage-status")

MEMORY = {"lane_mb": {"luna": 400, "terra": 400, "sol": 400, "astra": 400, "haiku": 900, "sonnet": 900,
                      "opus": 900, "gemini": 600, "glm": 500},
          "default_mb": 700, "reserve_mb": 1536, "reserve_fraction": 0.1, "recent_runs": 20, "min_runs": 3,
          "young_run_seconds": 120}
# 6451 MB available of 16300 MB: the reserve is 10% of the total (1630 MB), so 4821 MB is free for workers.
FAKE_RAM = "6451:16300"


def iso(moment):
    return moment.isoformat(timespec="seconds").replace("+00:00", "Z")


class UsageLocalTests(unittest.TestCase):
    def setUp(self):
        self.old_env = os.environ.copy()
        self.temp = tempfile.TemporaryDirectory()
        self.root = self.temp.name
        self.state = os.path.join(self.root, "lanes")
        self.codex_home = os.path.join(self.root, "codex")
        self.config = os.path.join(self.root, "claude-config")
        self.usage_dir = os.path.join(self.root, "usage")
        for path in (os.path.join(self.state, "runs"), self.codex_home, self.config, self.usage_dir):
            os.makedirs(path)
        self.catalog_path = os.path.join(self.root, "arms.json")
        self.write_catalog({"explore": {"memory": MEMORY}})
        self.fake_bin = FAKE
        if os.name == "nt":
            self.fake_bin = os.path.join(self.root, "fake-codex.cmd")
            with open(self.fake_bin, "w", encoding="utf-8") as handle:
                handle.write('@echo off\r\n"{}" "{}" %*\r\n'.format(sys.executable, FAKE))
        os.environ.update({
            "HOME": self.root,
            "TMPDIR": self.root,
            "CLAUDE_USAGE_DIR": self.usage_dir,
            "CODEX_HOME": self.codex_home,
            "CLAUDE_CONFIG_DIR": self.config,
            "LANES_STATE": self.state,
            "LANES_ARMS": self.catalog_path,
            "USAGE_OPTIMIZER_CLOUD_PROBE_MIN": "off",
            "USAGE_OPTIMIZER_CODEX_BIN": self.fake_bin,
            "USAGE_OPTIMIZER_CODEX_TIMEOUT": "2",
            "USAGE_OPTIMIZER_CODEX_TTL": "300",
            "USAGE_OPTIMIZER_CODEX_LIVE": "1",
            "NO_COLOR": "1",
            "FAKE_CODEX_MODE": "pro",
            "FAKE_CODEX_LOG": os.path.join(self.root, "methods.log"),
            "LANES_MEM_FAKE": FAKE_RAM,
        })
        for name in ("COLUMNS", "LANES_MEM_NEED_MB", "LANES_MEM_RESERVE_MB", "LANES_MEMINFO",
                     "LANES_PROC_CGROUP", "LANES_CGROUP_ROOT"):
            os.environ.pop(name, None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old_env)
        self.temp.cleanup()

    def write_catalog(self, catalog):
        with open(self.catalog_path, "w", encoding="utf-8") as handle:
            json.dump(catalog, handle)

    def write_ledger(self, lines):
        with open(os.path.join(self.state, "ledger.jsonl"), "w", encoding="utf-8") as handle:
            for line in lines:
                handle.write((line if isinstance(line, str) else json.dumps(line)) + "\n")

    def peaks(self, lane, values):
        return [{"run_dir": os.path.join("runs", "{}-{}".format(lane, index)), "lane": lane,
                 "peak_mem_mb": value} for index, value in enumerate(values)]

    def add_run(self, name, stamp_age, lane, started_age, ended=False, launched="absent"):
        now = dt.datetime.now(dt.timezone.utc)
        stamp = (now - dt.timedelta(seconds=stamp_age)).strftime("%Y%m%d-%H%M%S")
        run_dir = os.path.join(self.state, "runs", "{}-{}-{}".format(stamp, lane, name))
        os.makedirs(run_dir)
        meta = {"lane": lane, "started_at": iso(now - dt.timedelta(seconds=started_age)),
                "ended_at": iso(now - dt.timedelta(seconds=10)) if ended else None}
        if launched != "absent":
            meta["launched_at"] = None if launched is None else iso(now - dt.timedelta(seconds=launched))
        with open(os.path.join(run_dir, "meta.json"), "w", encoding="utf-8") as handle:
            json.dump(meta, handle)

    def run_usage(self, *flags, env=None):
        return subprocess.run([sys.executable, USAGE, "--no-agy", "--no-codex-live"] + list(flags),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                              env=env or os.environ.copy(), timeout=20, check=False)

    def run_json(self, *flags, env=None):
        result = self.run_usage("--json", *flags, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_json_shape_and_prior_needs_with_no_ledger(self):
        data = self.run_json()
        self.assertEqual(set(data), {"claude", "codex", "agy", "local", "hint"})
        local = data["local"]
        self.assertEqual(set(local), {"available_mb", "total_mb", "reserve_mb", "young_mb", "source",
                                      "lanes", "fits"})
        self.assertEqual((local["available_mb"], local["total_mb"], local["reserve_mb"], local["young_mb"],
                          local["source"]), (6451, 16300, 1630, 0, "fake"))
        self.assertEqual(set(local["lanes"]), set(MEMORY["lane_mb"]))
        self.assertEqual(local["lanes"]["luna"], {"need_mb": 400, "basis": "prior", "n": 0, "fits": 12})
        self.assertEqual(local["lanes"]["haiku"], {"need_mb": 900, "basis": "prior", "n": 0, "fits": 5})
        self.assertEqual(local["fits"], {"codex": 12, "claude": 5, "gemini": 8})
        self.assertNotIn("glm", local["fits"])

    def test_measured_needs_replace_priors_only_from_positive_numeric_peaks(self):
        self.write_ledger(
            [json.dumps({"lane": "luna"}), "{ not json", "[1, 2]", ""]
            + [json.dumps(row) for row in self.peaks("luna", [480] * 12)]
            + [json.dumps(row) for row in self.peaks("terra", [999, 999])]
            + [json.dumps(row) for row in self.peaks("sol", [0, "512", True, None, -5])]
            + [json.dumps(row) for row in self.peaks("sonnet", [700, 800, 900])]
            + [json.dumps(row) for row in self.peaks("astra", [100] * 5 + [480] * 20)])
        lanes = self.run_json()["local"]["lanes"]
        self.assertEqual(lanes["luna"], {"need_mb": 480, "basis": "measured", "n": 12, "fits": 10})
        # Two measured runs are below min_runs, so terra keeps its prior; sol has no positive numeric peak.
        self.assertEqual(lanes["terra"], {"need_mb": 400, "basis": "prior", "n": 2, "fits": 12})
        self.assertEqual(lanes["sol"], {"need_mb": 400, "basis": "prior", "n": 0, "fits": 12})
        self.assertEqual(lanes["sonnet"], {"need_mb": 800, "basis": "measured", "n": 3, "fits": 6})
        # Only the last recent_runs (20) of astra's 25 count, so the five 100 MB runs drop out.
        self.assertEqual(lanes["astra"], {"need_mb": 480, "basis": "measured", "n": 20, "fits": 10})

    def test_provider_fit_is_the_minimum_over_its_lanes(self):
        self.write_ledger(self.peaks("astra", [2000] * 3))
        local = self.run_json()["local"]
        codex = [local["lanes"][lane]["fits"] for lane in ("luna", "terra", "sol", "astra")]
        claude = [local["lanes"][lane]["fits"] for lane in ("haiku", "sonnet", "opus")]
        self.assertEqual(local["lanes"]["astra"]["fits"], 2)
        self.assertEqual(local["fits"]["codex"], min(codex))
        self.assertEqual(local["fits"]["claude"], min(claude))
        self.assertEqual(local["fits"]["gemini"], local["lanes"]["gemini"]["fits"])

    def test_young_runs_are_held_back_by_their_need(self):
        # Young: started 30 s ago, not ended, stamped within ten minutes (sol 400 + haiku 900).
        self.add_run("work-a", 60, "sol", 30)
        self.add_run("work-b", 60, "haiku", 30)
        # Not young: ended, started too long ago for young_run_seconds, or stamped more than ten minutes back.
        self.add_run("work-c", 60, "luna", 30, ended=True)
        self.add_run("work-d", 60, "terra", 300)
        self.add_run("work-e", 1200, "astra", 30)
        local = self.run_json()["local"]
        self.assertEqual(local["young_mb"], 1300)
        # (6451 - 1630 - 1300) = 3521 MB left for new runs.
        self.assertEqual(local["fits"], {"codex": 8, "claude": 3, "gemini": 5})

    def test_young_runs_count_from_launch_and_skip_waiting_runs(self):
        # Launched 10 s ago after a long wait for memory: young (sol 400). Still waiting, or launched long ago: not.
        self.add_run("work-a", 300, "sol", 300, launched=10)
        self.add_run("work-b", 60, "haiku", 30, launched=None)
        self.add_run("work-c", 300, "haiku", 300, launched=200)
        self.assertEqual(self.run_json()["local"]["young_mb"], 400)

    def test_reserve_floor_and_environment_overrides(self):
        local = self.run_json(env=dict(os.environ, LANES_MEM_FAKE="3000:4000"))["local"]
        self.assertEqual(local["reserve_mb"], 1536)
        env = dict(os.environ, LANES_MEM_NEED_MB="1000", LANES_MEM_RESERVE_MB="0")
        local = self.run_json(env=env)["local"]
        self.assertEqual(local["reserve_mb"], 0)
        self.assertEqual(local["lanes"]["haiku"], {"need_mb": 1000, "basis": "env", "n": 0, "fits": 6})
        self.assertEqual(local["fits"], {"codex": 6, "claude": 6, "gemini": 6})

    def test_catalog_block_is_read_key_by_key_with_defaults_for_bad_ones(self):
        self.write_catalog({"explore": {"memory": {"default_mb": "big", "reserve_mb": 2000, "min_runs": 0,
                                                   "lane_mb": {"haiku": 1200}}}})
        config = usage.memory_config()
        self.assertEqual((config["default_mb"], config["reserve_mb"], config["min_runs"]), (700, 2000, 3))
        self.assertEqual(config["lane_mb"], {"haiku": 1200})
        self.assertEqual(config["recent_runs"], 20)
        self.write_catalog({"explore": "not a block"})
        self.assertEqual(usage.memory_config()["lane_mb"], usage.MEMORY_DEFAULTS["lane_mb"])
        with open(self.catalog_path, "w", encoding="utf-8") as handle:
            handle.write("{ not json")
        self.assertEqual(usage.memory_config(), usage.MEMORY_DEFAULTS)
        os.environ["LANES_ARMS"] = os.path.join(self.root, "missing.json")
        self.assertEqual(usage.memory_config(), usage.MEMORY_DEFAULTS)
        local = self.run_json()["local"]
        self.assertEqual(local["lanes"]["luna"]["need_mb"], 400)

    def test_no_local_flag_drops_the_object_and_the_line(self):
        data = self.run_json("--no-local")
        self.assertIsNone(data["local"])
        result = self.run_usage("--no-local")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Local:", result.stdout)
        self.assertTrue(result.stdout.splitlines()[-1].startswith("Hint: "))

    def test_text_line_is_exact_and_brief_keeps_the_hint(self):
        self.write_ledger(self.peaks("luna", [480] * 12))
        result = self.run_usage()
        self.assertEqual(result.returncode, 0, result.stderr)
        local_lines = [line for line in result.stdout.splitlines() if line.startswith("Local: ")]
        self.assertEqual(local_lines, [
            "Local: RAM 6.3 of 15.9 GB available, reserve 1.6 GB | fits Codex ~10, Claude ~5, gemini ~8 | "
            "needs measured for luna (n=12), prior for the rest"])
        self.assertTrue(result.stdout.splitlines()[-1].startswith("Hint: "))
        brief = self.run_usage("--brief")
        self.assertIn("Local: RAM 6.3", brief.stdout)
        self.assertTrue(brief.stdout.splitlines()[-1].startswith("Hint: "))

    def test_text_needs_from_priors_and_starting_runs(self):
        self.add_run("work-a", 60, "sol", 30)
        result = self.run_usage()
        # 4821 MB free less the young sol run's 400 MB prior leaves 4421 MB.
        self.assertIn("Local: RAM 6.3 of 15.9 GB available, reserve 1.6 GB, starting runs 0.4 GB | "
                      "fits Codex ~11, Claude ~4, gemini ~7 | needs from priors", result.stdout)

    def test_memory_full_hint_when_no_worker_fits(self):
        env = dict(os.environ, LANES_MEM_FAKE="1000:16300")
        data = self.run_json(env=env)
        self.assertEqual(data["local"]["fits"], {"codex": 0, "claude": 0, "gemini": 0})
        self.assertEqual(data["hint"], "PC memory full: wait for running lanes before starting more")
        result = self.run_usage(env=env)
        self.assertEqual(result.stdout.splitlines()[-1],
                         "Hint: PC memory full: wait for running lanes before starting more")

    def test_unknown_memory_gives_null_and_the_unknown_line(self):
        args = mock.Mock(json=False, brief=False, no_agy=True, no_codex_live=True, no_local=False)
        stdout = io.StringIO()
        with mock.patch.object(usage, "memory_snapshot", return_value=None), \
                contextlib.redirect_stdout(stdout):
            usage.usage_status(args)
        self.assertIn("Local: RAM unknown on this OS", stdout.getvalue().splitlines())
        self.assertTrue(stdout.getvalue().splitlines()[-1].startswith("Hint: "))
        args.json = True
        stdout = io.StringIO()
        with mock.patch.object(usage, "memory_snapshot", return_value=None), \
                contextlib.redirect_stdout(stdout):
            usage.usage_status(args)
        data = json.loads(stdout.getvalue())
        self.assertIsNone(data["local"])
        self.assertNotIn("PC memory full", data["hint"])

    def test_linux_snapshot_takes_the_tightest_cgroup_limit(self):
        meminfo = os.path.join(self.root, "meminfo")
        with open(meminfo, "w", encoding="utf-8") as handle:
            handle.write("MemTotal:       16000000 kB\nMemFree:  1 kB\nMemAvailable:    8000000 kB\n")
        proc = os.path.join(self.root, "cgroup")
        with open(proc, "w", encoding="utf-8") as handle:
            handle.write("0::/app/worker\n")
        cgroup_root = os.path.join(self.root, "cgroup-root")
        worker = os.path.join(cgroup_root, "app", "worker")
        os.makedirs(worker)
        with open(os.path.join(worker, "memory.max"), "w", encoding="ascii") as handle:
            handle.write("2000000000\n")
        with open(os.path.join(worker, "memory.current"), "w", encoding="ascii") as handle:
            handle.write("1000000000\n")
        with open(os.path.join(cgroup_root, "app", "memory.max"), "w", encoding="ascii") as handle:
            handle.write("max\n")
        os.environ.update({"LANES_MEMINFO": meminfo, "LANES_PROC_CGROUP": proc, "LANES_CGROUP_ROOT": cgroup_root})
        self.assertEqual(usage.linux_memory(),
                         {"available_mb": 953, "total_mb": 1907, "source": "cgroup"})
        # A root cgroup with no memory.max (as on a real host) sets no limit: MemAvailable and MemTotal stand.
        with open(proc, "w", encoding="utf-8") as handle:
            handle.write("0::/\n")
        self.assertEqual(usage.linux_memory(),
                         {"available_mb": 7812, "total_mb": 15625, "source": "meminfo"})


if __name__ == "__main__":
    unittest.main()
