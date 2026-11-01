"""Black-box tests of `lane fable --role`, the advisor gate and budget, and `lane main`'s defaults from arms.json.

bin/lane runs as a subprocess against a temp catalog (LANES_ARMS), a temp state (LANES_STATE) and a fake `claude`.
Nothing touches ~/.claude, ~/.local/state or the network.
"""

import datetime
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import unittest
import uuid


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "bin", "lane")

FAKE_CLAUDE = '''
import json
import os
import sys

sys.stdin.read()
with open(os.environ["FAKE_CAPTURE"], "w", encoding="utf-8") as stream:
    json.dump({"argv": sys.argv[1:]}, stream)
with open("worker.txt", "w", encoding="utf-8") as stream:
    stream.write("edited\\n")
print(json.dumps({"session_id": "fake-session", "is_error": False, "result": "done", "total_cost_usd": 0.5,
                  "usage": {"input_tokens": 1, "cache_creation_input_tokens": 1, "cache_read_input_tokens": 1,
                            "output_tokens": 1}}))
'''


def force_rmtree(path):
    def retry(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=retry)
    else:
        shutil.rmtree(path, onerror=retry)


def days_ago(days):
    moment = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    return moment.isoformat(timespec="seconds").replace("+00:00", "Z")


class LaneAdvisorTests(unittest.TestCase):
    def setUp(self):
        self.root = os.path.join(os.path.dirname(__file__), ".lane-advisor-{}-{}".format(os.getpid(), uuid.uuid4().hex))
        os.makedirs(self.root)
        self.addCleanup(force_rmtree, self.root)
        self.workspace = os.path.join(self.root, "workspace")
        self.bin = os.path.join(self.root, "bin")
        self.state = os.path.join(self.root, "state")
        self.brief = os.path.join(self.root, "brief.md")
        self.capture = os.path.join(self.root, "capture.json")
        self.arms = os.path.join(self.root, "arms.json")
        for directory in (self.workspace, self.bin, self.state):
            os.makedirs(directory)
        self.write(self.brief, "Create worker.txt.\n")
        self.install_claude()
        self.catalog = self.shipped_catalog()
        # Most tests cover the lane as the switch rule leaves it, its arms manual; the shipped catalog disables
        # them (the tests under "the shipped catalog").
        for arm in self.catalog["arms"]:
            if arm["lane"] == "fable" and arm["status"] == "disabled":
                arm["status"] = "manual"
        self.save_catalog()
        self.env = dict(os.environ, LANES_STATE=self.state, LANE_NO_USAGE="1", LANE_NO_ETA="1", LANES_MEM_CHECK="off",
                        PYTHONUTF8="1", LANES_CONFIG=os.path.join(self.root, "config"), FAKE_CAPTURE=self.capture,
                        LANES_ARMS=self.arms, LANES_ARMS_LOCAL=os.path.join(self.root, "no-local-arms.json"),
                        LANES_PROC_CGROUP=os.path.join(self.root, "no-proc-cgroup"),
                        LANES_CGROUP_ROOT=os.path.join(self.root, "cgroup"),
                        PATH=self.bin + os.pathsep + os.environ.get("PATH", ""))
        for name in ("CLAUDE_CODE_REMOTE", "USAGE_OPTIMIZER_SESSION_GUARD"):
            self.env.pop(name, None)

    # ----- harness -----

    def write(self, path, text):
        with open(path, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)

    def shipped_catalog(self):
        with open(os.path.join(ROOT, "arms.json"), "r", encoding="utf-8") as stream:
            return json.load(stream)

    def save_catalog(self):
        self.write(self.arms, json.dumps(self.catalog))

    def install_claude(self):
        script = os.path.join(self.bin, "fake_claude.py")
        self.write(script, FAKE_CLAUDE)
        if os.name == "nt":
            self.write(os.path.join(self.bin, "claude.cmd"), '@echo off\n"{}" "{}" %*\n'.format(sys.executable, script))
        else:
            launcher = os.path.join(self.bin, "claude")
            self.write(launcher, '#!/bin/sh\nexec {} {} "$@"\n'.format(shlex.quote(sys.executable), shlex.quote(script)))
            os.chmod(launcher, 0o755)

    def activate(self, budget=10):
        self.catalog["explore"]["advisor"]["active"] = True
        self.catalog["explore"]["advisor"]["weekly_list_usd"] = budget
        self.save_catalog()

    def ledger_row(self, **fields):
        row = {"lane": "fable", "role": "plan", "started_at": days_ago(1), "usage": {"list_usd": 1.0}}
        row.update(fields)
        with open(os.path.join(self.state, "ledger.jsonl"), "a", encoding="utf-8") as stream:
            stream.write(json.dumps(row) + "\n")

    def lane(self, lane, *extra, env=None):
        argv = [sys.executable, SCRIPT, lane, "-C", self.workspace, "-b", self.brief, "--class", "hard",
                "--no-mask"] + list(extra)
        return subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False,
                              env=dict(self.env, **(env or {})), encoding="utf-8", errors="replace")

    def out(self, result):
        return "exit {}\nstdout:\n{}\nstderr:\n{}".format(result.returncode, result.stdout, result.stderr)

    def meta(self, result):
        folder = next(line.split("out=", 1)[1].split()[0] for line in result.stdout.splitlines() if "out=" in line)
        with open(os.path.join(folder, "meta.json"), "r", encoding="utf-8") as stream:
            return json.load(stream)

    def launched(self):
        return os.path.exists(self.capture)

    # ----- the shipped catalog -----

    def test_the_shipped_catalog_disables_every_fable_arm(self):
        self.catalog = self.shipped_catalog()
        self.save_catalog()
        fable = [arm for arm in self.catalog["arms"] if arm["lane"] == "fable"]
        self.assertEqual(sorted(arm["effort"] for arm in fable), ["high", "medium", "xhigh"])
        self.assertEqual({arm["status"] for arm in fable}, {"disabled"})
        for extra in (["--role", "plan"], ["-e", "high", "--role", "user"],
                      ["-e", "high", "--role", "user", "--subagent"]):
            result = self.lane("fable", *extra)
            self.assertEqual(result.returncode, 8, self.out(result))
            self.assertIn("disabled", result.stderr)
            self.assertFalse(self.launched())
        # An active advisor still runs nothing while the arms are disabled.
        self.activate()
        result = self.lane("fable", "--role", "plan")
        self.assertEqual(result.returncode, 8, self.out(result))
        self.assertIn("is disabled: only Fable 5.1 is accessible", result.stderr)
        self.assertFalse(self.launched())

    def test_the_shipped_catalog_runs_fable_only_with_role_user_and_off_catalog(self):
        self.catalog = self.shipped_catalog()
        self.save_catalog()
        result = self.lane("fable", "-e", "high", "--role", "user", "--off-catalog")
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertTrue(self.launched())

    # ----- the role option -----

    def test_fable_without_a_role_is_a_usage_error(self):
        result = self.lane("fable", "-e", "high")
        self.assertEqual(result.returncode, 2, self.out(result))
        self.assertIn("--role", result.stderr)
        self.assertFalse(self.launched())

    def test_role_on_another_lane_is_a_usage_error(self):
        result = self.lane("sonnet", "-e", "high", "--role", "plan")
        self.assertEqual(result.returncode, 2, self.out(result))
        self.assertIn("--role is only for the fable lane", result.stderr)
        self.assertFalse(self.launched())

    def test_an_unknown_role_is_a_usage_error(self):
        result = self.lane("fable", "--role", "chat")
        self.assertEqual(result.returncode, 2, self.out(result))

    def test_other_lanes_record_no_role(self):
        result = self.lane("sonnet", "-e", "high")
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertNotIn("role", self.meta(result))
        self.assertNotIn("advisor", result.stderr)

    # ----- the gate -----

    def test_an_inactive_advisor_refuses_a_role_run_and_launches_nothing(self):
        result = self.lane("fable", "--role", "plan")
        self.assertEqual(result.returncode, 8, self.out(result))
        self.assertIn(self.catalog["explore"]["advisor"]["inactive_reason"], result.stderr)
        self.assertIn("--role user", result.stderr)
        self.assertFalse(self.launched())
        self.assertEqual(os.listdir(self.state), [])

    def test_a_catalog_without_an_advisor_counts_as_off(self):
        del self.catalog["explore"]["advisor"]
        self.save_catalog()
        result = self.lane("fable", "-e", "high", "--role", "tiebreak")
        self.assertEqual(result.returncode, 8, self.out(result))
        self.assertFalse(self.launched())

    def test_role_user_runs_while_the_advisor_is_off_and_records_the_role(self):
        result = self.lane("fable", "-e", "high", "--role", "user")
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertIn("lane: advisor budget $0.00 of $60 used in the last 7 days", result.stderr)
        self.assertIn("role=user", result.stdout)
        meta = self.meta(result)
        self.assertEqual((meta["role"], meta["lane"], meta["model"]), ("user", "fable", "claude-fable-5-1"))
        with open(self.capture, "r", encoding="utf-8") as stream:
            argv = json.load(stream)["argv"]
        self.assertEqual(argv[argv.index("--model") + 1], "claude-fable-5-1")
        self.assertEqual(argv[argv.index("--effort") + 1], "high")
        with open(os.path.join(self.state, "ledger.jsonl"), "r", encoding="utf-8") as stream:
            self.assertEqual(json.loads(stream.readline())["role"], "user")

    def test_a_role_missing_from_a_local_advisor_block_names_the_roles_map(self):
        # A local explore.advisor replaces the whole shipped block, roles included.
        self.catalog["explore"]["advisor"] = {"active": True, "weekly_list_usd": 10}
        self.save_catalog()
        result = self.lane("fable", "--role", "plan")
        self.assertEqual(result.returncode, 2, self.out(result))
        self.assertIn("explore.advisor.roles has no default for role plan", result.stderr)
        self.assertFalse(self.launched())

    def test_role_user_needs_an_effort(self):
        result = self.lane("fable", "--role", "user")
        self.assertEqual(result.returncode, 2, self.out(result))
        self.assertIn("-e is required", result.stderr)

    def test_an_active_advisor_under_budget_runs_and_prints_the_spend(self):
        self.activate(budget=10)
        self.ledger_row(usage={"list_usd": 2.5})
        result = self.lane("fable", "-e", "high", "--role", "plan")
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertIn("lane: advisor budget $2.50 of $10 used in the last 7 days", result.stderr)
        self.assertEqual(self.meta(result)["role"], "plan")

    def test_spend_at_the_budget_refuses(self):
        self.activate(budget=3)
        self.ledger_row(usage={"list_usd": 1.5})
        self.ledger_row(usage={"list_usd": 1.5}, role="final-review")
        result = self.lane("fable", "-e", "high", "--role", "plan")
        self.assertEqual(result.returncode, 8, self.out(result))
        self.assertIn("$3.00", result.stderr)
        self.assertFalse(self.launched())

    def test_old_user_other_lane_and_unpriced_runs_are_not_counted(self):
        self.activate(budget=3)
        self.ledger_row(usage={"list_usd": 50}, started_at=days_ago(8))
        self.ledger_row(usage={"list_usd": 50}, role="user")
        self.ledger_row(usage={"list_usd": 50}, lane="opus")
        self.ledger_row(usage={"list_usd": None})
        self.ledger_row(usage={})
        result = self.lane("fable", "-e", "high", "--role", "ladder")
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertIn("$0.00 of $3", result.stderr)

    def test_role_user_ignores_the_budget(self):
        self.activate(budget=1)
        self.ledger_row(usage={"list_usd": 5})
        result = self.lane("fable", "-e", "xhigh", "--role", "user")
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertIn("$5.00 of $1", result.stderr)

    def test_the_effort_defaults_from_the_role(self):
        self.activate()
        for role, effort in (("plan", "xhigh"), ("final-review", "high"), ("tiebreak", "medium")):
            result = self.lane("fable", "--role", role, "--dry-run")
            self.assertEqual(result.returncode, 0, self.out(result))
            argv = json.loads(next(line for line in result.stdout.splitlines() if line.startswith("argv: "))[6:])
            self.assertEqual(argv[argv.index("--effort") + 1], effort, role)
            self.assertIn("--model", argv)
            self.assertEqual(argv[argv.index("--model") + 1], "claude-fable-5-1")

    def test_an_explicit_effort_wins_over_the_role_default(self):
        self.activate()
        result = self.lane("fable", "--role", "plan", "-e", "medium")
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertEqual(self.meta(result)["effort"], "medium")

    def test_the_gate_applies_to_a_subagent_run_and_names_the_agent(self):
        refused = self.lane("fable", "--role", "plan", "--subagent")
        self.assertEqual(refused.returncode, 8, self.out(refused))
        self.activate()
        result = self.lane("fable", "--role", "plan", "--subagent")
        self.assertEqual(result.returncode, 0, self.out(result))
        launch = json.loads(result.stdout.splitlines()[1])
        self.assertEqual(launch["subagent_type"], "lane-fable-xhigh")
        run_dir = os.path.join(self.state, "runs", result.stdout.splitlines()[0].split()[3])
        with open(os.path.join(run_dir, "meta.json"), "r", encoding="utf-8") as stream:
            self.assertEqual(json.load(stream)["role"], "plan")

    def test_fable_refuses_cloud_and_verify(self):
        for flag in ("--cloud", "--verify"):
            result = self.lane("fable", "-e", "high", "--role", "user", flag)
            self.assertEqual(result.returncode, 2, self.out(result))
            self.assertIn("process and subagent", result.stderr)
        self.assertFalse(self.launched())


class LaneMainDefaultsTests(unittest.TestCase):
    """`lane main start` takes its model and effort from explore.main_session (the dry run prints them)."""

    def setUp(self):
        self.root = os.path.join(os.path.dirname(__file__), ".lane-advisor-main-{}-{}".format(os.getpid(), uuid.uuid4().hex))
        os.makedirs(self.root)
        self.addCleanup(force_rmtree, self.root)
        self.workspace = os.path.join(self.root, "workspace")
        origin = os.path.join(self.root, "demo-proj.git")
        self.brief = os.path.join(self.root, "brief.md")
        self.arms = os.path.join(self.root, "arms.json")
        os.makedirs(self.workspace)
        with open(self.brief, "w", encoding="utf-8") as stream:
            stream.write("Build the demo.\n")
        ident = ["-c", "user.name=Lane Test", "-c", "user.email=lane-test@localhost"]
        for args in (["init", "--bare", origin], ["init", self.workspace],
                     ["-C", self.workspace, "branch", "-M", "main"]):
            subprocess.run(["git"] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=20)
        with open(os.path.join(self.workspace, "base.txt"), "w", encoding="utf-8") as stream:
            stream.write("base\n")
        for args in (["add", "base.txt"], ident + ["commit", "-m", "base"], ["remote", "add", "origin", origin]):
            subprocess.run(["git", "-C", self.workspace] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           check=True, timeout=20)
        with open(os.path.join(ROOT, "arms.json"), "r", encoding="utf-8") as stream:
            self.catalog = json.load(stream)
        self.env = dict(os.environ, LANES_STATE=os.path.join(self.root, "state"), LANE_NO_USAGE="1",
                        LANE_NO_ETA="1", LANES_MEM_CHECK="off", LANES_ARMS=self.arms,
                        LANES_ARMS_LOCAL=os.path.join(self.root, "no-local-arms.json"),
                        LANES_CONFIG=os.path.join(self.root, "config"), LANES_CLOUD_ANY_REMOTE="1",
                        LANES_CLOUD_SKIP_APP_CHECK="1")
        for name in ("CLAUDE_CODE_REMOTE", "USAGE_OPTIMIZER_SESSION_GUARD"):
            self.env.pop(name, None)

    def start(self, *extra):
        with open(self.arms, "w", encoding="utf-8") as stream:
            json.dump(self.catalog, stream)
        result = subprocess.run([sys.executable, SCRIPT, "main", "-C", self.workspace, "-b", self.brief,
                                 "--dry-run"] + list(extra), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=45, check=False, env=self.env, encoding="utf-8", errors="replace")
        self.assertEqual(result.returncode, 0, "{}\n{}".format(result.stdout, result.stderr))
        line = next(line for line in result.stdout.splitlines() if line.startswith("model: "))
        return line, result.stderr

    def test_the_catalog_sets_the_model_and_effort_and_the_suffix_is_dropped(self):
        self.catalog["explore"]["main_session"].update({"model": "sonnet[1m]", "effort": "high"})
        self.assertEqual(self.start()[0], "model: sonnet effort: high")

    def test_the_shipped_catalog_gives_opus_xhigh(self):
        self.assertEqual(self.start()[0], "model: opus effort: xhigh")

    def test_flags_win_over_the_catalog(self):
        self.catalog["explore"]["main_session"].update({"model": "sonnet[1m]", "effort": "high"})
        self.assertEqual(self.start("-m", "haiku", "-e", "low")[0], "model: haiku effort: low")

    def test_without_the_block_it_falls_back_to_opus_xhigh(self):
        del self.catalog["explore"]["main_session"]
        self.assertEqual(self.start()[0], "model: opus effort: xhigh")

    def test_an_unknown_effort_falls_back_to_xhigh_with_a_warning(self):
        self.catalog["explore"]["main_session"]["effort"] = "turbo"
        line, stderr = self.start()
        self.assertEqual(line, "model: opus effort: xhigh")
        self.assertIn("turbo", stderr)

    def out(self, result):
        return "exit {}\nstdout:\n{}\nstderr:\n{}".format(result.returncode, result.stdout, result.stderr)

    def test_a_mirror_gets_no_fable_agent_file(self):
        kit = os.path.join(self.root, "kit")
        os.makedirs(os.path.join(kit, "bin"))
        os.makedirs(os.path.join(kit, "agents"))
        shutil.copy2(SCRIPT, os.path.join(kit, "bin", "lane"))
        for name in ("lane-haiku-high.md", "lane-fable-xhigh.md", "lane-fable-high.md"):
            with open(os.path.join(kit, "agents", name), "w", encoding="utf-8") as stream:
                stream.write("---\nname: x\n---\n")
        target = os.path.join(self.root, "target")
        os.makedirs(target)
        result = subprocess.run([sys.executable, os.path.join(kit, "bin", "lane"), "main", "--write-files", target],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False,
                                env=self.env, encoding="utf-8", errors="replace")
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertEqual(os.listdir(os.path.join(target, ".claude", "agents")), ["lane-haiku-high.md"])
        self.assertNotIn("fable", result.stdout)
        # Only fable files: the "no lane agent files" check still fires.
        os.remove(os.path.join(kit, "agents", "lane-haiku-high.md"))
        result = subprocess.run([sys.executable, os.path.join(kit, "bin", "lane"), "main", "--write-files", target],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False,
                                env=self.env, encoding="utf-8", errors="replace")
        self.assertEqual(result.returncode, 8, self.out(result))


if __name__ == "__main__":
    unittest.main()
