import datetime as dt
import importlib.machinery
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KIT_UPDATE = os.path.join(ROOT, "bin", "kit-update")
STATUSLINE = os.path.join(ROOT, "bin", "claude-statusline")
GIT = shutil.which("git")
POLICY = ("# Claude Usage Optimizer: usage policy\n\n"
          "Claude Usage Optimizer version: {}. Installed at `~/.claude/usage-optimizer/`.\n")
FAKE_NOTIFY = ("import json, os, sys\n"
               "with open(os.environ['FAKE_NOTIFY_LOG'], 'a', encoding='utf-8') as handle:\n"
               "    handle.write(json.dumps(sys.argv[1:]) + '\\n')\n")
STAMP = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"


def load(path, name):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def iso(moment):
    return moment.replace(microsecond=0).isoformat().replace("+00:00", "Z")


class ReleaseOrderTests(unittest.TestCase):
    def test_releases_order_by_date_then_number(self):
        kit_update = load(KIT_UPDATE, "kit_update_order_tested")
        statusline = load(STATUSLINE, "statusline_order_tested")
        ordered = ["2026-10-31.9", "2026-10-31.10", "2026-10-31.13", "2026-10-31.14", "2026-11-01.1",
                   "2027-01-01.0"]
        for module in (kit_update, statusline):
            key = getattr(module, "release_key", None) or module._release_key
            self.assertEqual(sorted(reversed(ordered), key=key), ordered)
        self.assertTrue(kit_update.is_newer("2026-10-31.14", "2026-10-31.13"))
        self.assertTrue(kit_update.is_newer("2026-11-01.1", "2026-10-31.14"))
        self.assertFalse(kit_update.is_newer("2026-10-31.13", "2026-10-31.13"))
        self.assertFalse(kit_update.is_newer("2026-10-31.13", "2026-11-01.1"))
        for bad in (None, "", "2026-10-31", "v2026-10-31.1", "2026-10-31.1x", 20261031):
            self.assertIsNone(kit_update.release_key(bad))
            self.assertFalse(kit_update.is_newer(bad, "2026-10-31.1"))
            self.assertFalse(kit_update.is_newer("2026-10-31.1", bad))


class ReplaceFileTests(unittest.TestCase):
    """os.replace on Windows can be refused while a reader holds the file; the write is retried, then skipped."""

    def setUp(self):
        self.kit_update = load(KIT_UPDATE, "kit_update_replace_tested")
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = self._tmp.name
        patcher = mock.patch.object(self.kit_update.time, "sleep")
        self.sleep = patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_file_refused_twice_then_lands(self):
        calls = []

        def replace(source, target):
            calls.append((source, target))
            if len(calls) <= 2:
                raise PermissionError(13, "held open by a reader")

        with mock.patch.object(os, "replace", side_effect=replace):
            self.assertTrue(self.kit_update.replace_file("new.tmp", "kit-update.json"))
        self.assertEqual(calls, [("new.tmp", "kit-update.json")] * 3)
        self.assertEqual(self.sleep.call_count, 2)

    def test_a_file_refused_throughout_is_skipped_without_raising(self):
        with mock.patch.object(os, "replace", side_effect=PermissionError(13, "held open by a reader")) as replace:
            self.assertFalse(self.kit_update.replace_file("new.tmp", "kit-update.json"))
        self.assertEqual(replace.call_count, 4)  # the first try and three retries
        self.assertAlmostEqual(sum(call.args[0] for call in self.sleep.call_args_list), 1.0)

    def test_write_json_skips_a_held_file_and_leaves_no_temporary(self):
        target = os.path.join(self.folder, "kit-update.json")
        write(target, "old\n")
        with mock.patch.object(os, "replace", side_effect=PermissionError(13, "held open by a reader")):
            self.assertFalse(self.kit_update.write_json(self.folder, "kit-update.json", {"latest": "2026-11-01.1"}))
        self.assertEqual(os.listdir(self.folder), ["kit-update.json"])
        with open(target, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "old\n")

    def test_write_json_lands_a_file_on_the_first_try(self):
        self.assertTrue(self.kit_update.write_json(self.folder, "kit-update.json", {"latest": "2026-11-01.1"}))
        self.sleep.assert_not_called()
        with open(os.path.join(self.folder, "kit-update.json"), encoding="utf-8") as handle:
            self.assertEqual(json.load(handle), {"latest": "2026-11-01.1"})


@unittest.skipIf(GIT is None, "git is not installed")
class KitUpdateCheckTests(unittest.TestCase):
    """A bare "origin", a publisher clone that releases to it, and an install whose source.json names a checkout."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self.home = os.path.join(self.root, "home")
        self.state = os.path.join(self.root, "state")
        self.prefix = os.path.join(self.root, "prefix")
        self.origin = os.path.join(self.root, "origin.git")
        self.publisher = os.path.join(self.root, "publisher")
        # install.sh records a checkout with forward slashes on Windows too (cygpath -m).
        self.checkout = os.path.join(self.home, "claude-usage-optimizer").replace("\\", "/")
        self.push_log = os.path.join(self.root, "push.log")
        os.makedirs(self.home)
        self.env = dict(os.environ)
        for key in ("USAGE_OPTIMIZER_UPDATE_CHECK", "USAGE_OPTIMIZER_POLICY", "GIT_DIR", "GIT_WORK_TREE"):
            self.env.pop(key, None)
        self.env.update({"HOME": self.home, "USERPROFILE": self.home,
                         "XDG_CONFIG_HOME": os.path.join(self.home, ".config"), "GIT_CONFIG_NOSYSTEM": "1",
                         "LANES_STATE": self.state, "FAKE_NOTIFY_LOG": self.push_log})

        self.git("init", "-q", "--bare", self.origin)
        self.git("-C", self.origin, "symbolic-ref", "HEAD", "refs/heads/main")
        self.git("init", "-q", self.publisher)
        self.git("-C", self.publisher, "remote", "add", "origin", self.origin)
        self.publish("2026-11-01.1")
        self.git("clone", "-q", self.origin, self.checkout)

        self.bin = os.path.join(self.prefix, "bin")
        os.makedirs(self.bin)
        shutil.copy2(KIT_UPDATE, os.path.join(self.bin, "kit-update"))
        write(os.path.join(self.bin, "cloud-notify"), FAKE_NOTIFY)
        self.install("2026-10-31.13")
        self.record_checkout(self.checkout)

    def git(self, *args):
        return subprocess.run([GIT, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                               "-c", "init.defaultBranch=main", *args], env=self.env, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, encoding="utf-8", timeout=60, check=True).stdout

    def publish(self, version, branch="main"):
        write(os.path.join(self.publisher, "POLICY.md"), POLICY.format(version))
        self.git("-C", self.publisher, "add", "POLICY.md")
        self.git("-C", self.publisher, "commit", "-q", "-m", "Release " + version)
        self.git("-C", self.publisher, "push", "-q", "origin", "HEAD:" + branch)

    def install(self, version):
        write(os.path.join(self.prefix, "POLICY.md"), POLICY.format(version))

    def record_checkout(self, path):
        write(os.path.join(self.prefix, "source.json"),
              json.dumps({"checkout": path, "installed_at": "2026-10-31T00:00:00Z"}))

    def check(self, **env):
        result = subprocess.run([sys.executable, "-X", "utf8", os.path.join(self.bin, "kit-update"), "check"],
                                env=dict(self.env, **env), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                encoding="utf-8", timeout=120, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(len(result.stdout.splitlines()), 1, result.stdout)
        return result.stdout.strip()

    def cache(self):
        with open(os.path.join(self.state, "kit-update.json"), encoding="utf-8") as handle:
            return json.load(handle)

    def notices(self):
        try:
            return sorted(os.listdir(os.path.join(self.state, "notices")))
        except FileNotFoundError:
            return []

    def notice(self, version):
        with open(os.path.join(self.state, "notices", "kit-update-%s.json" % version), encoding="utf-8") as handle:
            return json.load(handle)

    def pushes(self):
        try:
            with open(self.push_log, encoding="utf-8") as handle:
                return [json.loads(line) for line in handle]
        except FileNotFoundError:
            return []

    def test_a_newer_release_is_cached_noticed_and_pushed_once(self):
        line = self.check()
        self.assertIn("2026-11-01.1 is published; this machine runs 2026-10-31.13", line)
        cache = self.cache()
        self.assertRegex(cache.pop("checked_at"), STAMP)
        self.assertEqual(cache, {"installed": "2026-10-31.13", "latest": "2026-11-01.1", "checkout": self.checkout,
                                 "error": None, "announced": "2026-11-01.1"})

        self.assertEqual(self.notices(), ["kit-update-2026-11-01.1.json"])
        notice = self.notice("2026-11-01.1")
        self.assertEqual(set(notice), {"id", "kind", "created_at", "text", "expires_at"})
        self.assertEqual(notice["id"], "kit-update-2026-11-01.1")
        self.assertEqual(notice["kind"], "kit_update")
        self.assertRegex(notice["created_at"], STAMP)
        self.assertIsNone(notice["expires_at"])
        text = notice["text"]
        self.assertIn("2026-11-01.1, is published (installed: 2026-10-31.13)", text)
        self.assertIn("`git -C %s pull --ff-only`, then `bash %s/install.sh`" % (self.checkout, self.checkout), text)
        self.assertIn("restart or /compact", text)
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.state, "notices")).st_mode), 0o700)

        # The push leaves the machine, so it names the checkout from ~.
        self.assertEqual(self.pushes(), [["push", "--title", "Usage Optimizer 2026-11-01.1", "--message",
                                          "Installed 2026-10-31.13. Update: git -C ~/claude-usage-optimizer pull "
                                          "--ff-only && bash ~/claude-usage-optimizer/install.sh"]])

        self.check()
        self.assertEqual(len(self.pushes()), 1)
        self.assertEqual(self.notice("2026-11-01.1"), notice)
        # A notice that was read and removed is not written again for the same release.
        os.unlink(os.path.join(self.state, "notices", "kit-update-2026-11-01.1.json"))
        self.check()
        self.assertEqual(self.notices(), [])
        self.assertEqual(len(self.pushes()), 1)

    def test_a_later_release_replaces_the_notice_and_is_pushed(self):
        self.check()
        self.publish("2026-11-01.2")
        self.check()
        self.assertEqual(self.cache()["latest"], "2026-11-01.2")
        self.assertEqual(self.notices(), ["kit-update-2026-11-01.2.json"])
        self.assertEqual([push[2] for push in self.pushes()],
                         ["Usage Optimizer 2026-11-01.1", "Usage Optimizer 2026-11-01.2"])

    def test_catching_up_removes_the_notice(self):
        self.check()
        self.install("2026-11-01.1")
        line = self.check()
        self.assertEqual(line, "Claude Usage Optimizer 2026-11-01.1 is the newest published release.")
        self.assertEqual(self.notices(), [])
        cache = self.cache()
        self.assertEqual((cache["installed"], cache["latest"], cache["error"]), ("2026-11-01.1", "2026-11-01.1", None))
        self.install("2026-11-02.1")  # ahead of origin, as in the source checkout before a release is pushed
        self.assertIn("runs 2026-11-02.1; the newest published release is 2026-11-01.1", self.check())
        self.assertEqual(self.notices(), [])
        self.assertEqual(len(self.pushes()), 1)

    def test_the_default_branch_comes_from_origin_when_origin_head_is_unset(self):
        self.git("-C", self.checkout, "remote", "set-head", "origin", "-d")
        self.publish("2026-11-03.4")
        self.check()
        self.assertEqual((self.cache()["latest"], self.cache()["error"]), ("2026-11-03.4", None))

    def test_a_renamed_default_branch_on_origin_beats_a_stale_origin_head(self):
        # The clone recorded origin/HEAD -> main; origin has since made trunk its default branch.
        self.assertEqual(self.git("-C", self.checkout, "symbolic-ref", "refs/remotes/origin/HEAD").strip(),
                         "refs/remotes/origin/main")
        self.publish("2026-11-05.1", branch="trunk")
        self.git("-C", self.origin, "symbolic-ref", "HEAD", "refs/heads/trunk")
        self.check()
        self.assertEqual((self.cache()["latest"], self.cache()["error"]), ("2026-11-05.1", None))

    def test_the_check_leaves_origin_refs_and_fetch_head_as_the_user_left_them(self):
        self.git("-C", self.checkout, "fetch", "-q", "origin")  # the user's own fetch writes FETCH_HEAD
        fetch_head = os.path.join(self.checkout, ".git", "FETCH_HEAD")
        with open(fetch_head, "rb") as handle:
            before_head = handle.read()
        tracking = self.git("-C", self.checkout, "rev-parse", "refs/remotes/origin/main").strip()
        self.publish("2026-11-06.1")
        self.check()
        self.assertEqual(self.cache()["latest"], "2026-11-06.1")
        self.assertEqual(self.git("-C", self.checkout, "rev-parse", "refs/remotes/origin/main").strip(), tracking)
        with open(fetch_head, "rb") as handle:
            self.assertEqual(handle.read(), before_head)
        origin_main = self.git("-C", self.origin, "rev-parse", "refs/heads/main").strip()
        self.assertEqual(self.git("-C", self.checkout, "rev-parse", "refs/usage-optimizer/update/main").strip(),
                         origin_main)

    def test_without_a_recorded_checkout_the_error_is_recorded_quietly(self):
        os.unlink(os.path.join(self.prefix, "source.json"))
        line = self.check()
        self.assertTrue(line.startswith("Update check failed: no source checkout is recorded"), line)
        cache = self.cache()
        self.assertIn("no source checkout", cache["error"])
        self.assertEqual((cache["installed"], cache["latest"], cache["checkout"]), ("2026-10-31.13", None, None))
        self.assertEqual(self.notices(), [])
        self.assertEqual(self.pushes(), [])

    def test_without_git_the_error_is_recorded(self):
        empty = os.path.join(self.root, "no-tools")
        os.makedirs(empty)
        self.check(PATH=empty)
        self.assertEqual((self.cache()["error"], self.cache()["latest"]), ("git is not installed", None))
        self.assertEqual(self.pushes(), [])

    def test_an_unreachable_origin_keeps_the_release_found_before(self):
        missing = os.path.join(self.root, "gone.git")
        self.git("-C", self.checkout, "remote", "set-url", "origin", missing)
        line = self.check()
        self.assertTrue(line.startswith("Update check failed: git fetch origin main failed"), line)
        self.assertEqual((self.cache()["latest"], self.notices(), self.pushes()), (None, [], []))

        self.git("-C", self.checkout, "remote", "set-url", "origin", self.origin)
        self.check()
        self.git("-C", self.checkout, "remote", "set-url", "origin", missing)
        line = self.check()
        self.assertIn("An earlier check found: Claude Usage Optimizer 2026-11-01.1 is published", line)
        cache = self.cache()
        self.assertIn("failed", cache["error"])
        self.assertEqual((cache["latest"], cache["announced"]), ("2026-11-01.1", "2026-11-01.1"))
        self.assertEqual(self.notices(), ["kit-update-2026-11-01.1.json"])
        self.assertEqual(len(self.pushes()), 1)

    def test_a_folder_inside_another_repository_is_never_fetched(self):
        plain = os.path.join(self.root, "outer", "kit")
        os.makedirs(plain)
        self.git("init", "-q", os.path.join(self.root, "outer"))
        self.record_checkout(plain)
        self.check()
        self.assertEqual(self.cache()["error"], "the recorded checkout is not a git checkout")

    def test_the_off_switch_checks_nothing_and_removes_the_notice(self):
        line = self.check(USAGE_OPTIMIZER_UPDATE_CHECK="off")
        self.assertIn("off", line)
        self.assertFalse(os.path.exists(self.state))

        self.check()
        with open(os.path.join(self.state, "kit-update.json"), "rb") as handle:
            before = handle.read()
        self.publish("2026-11-01.2")
        self.check(USAGE_OPTIMIZER_UPDATE_CHECK="OFF")
        with open(os.path.join(self.state, "kit-update.json"), "rb") as handle:
            self.assertEqual(handle.read(), before)
        self.assertEqual(self.notices(), [])
        self.assertEqual(len(self.pushes()), 1)

    def test_a_running_check_is_not_doubled_and_a_stale_lock_is_cleared(self):
        os.makedirs(self.state)
        lock = os.path.join(self.state, "kit-update.lock")
        write(lock, "")
        self.assertEqual(self.check(), "Another update check is running.")
        self.assertFalse(os.path.exists(os.path.join(self.state, "kit-update.json")))
        old = time.time() - 600
        os.utime(lock, (old, old))
        self.check()
        self.assertEqual(self.cache()["latest"], "2026-11-01.1")
        self.assertFalse(os.path.exists(lock))

    def test_the_statusline_runs_the_check_in_the_background_and_shows_it(self):
        statusline = os.path.join(self.bin, "claude-statusline")
        shutil.copy2(STATUSLINE, statusline)
        env = dict(self.env, CLAUDE_USAGE_DIR=os.path.join(self.root, "usage"), USAGE_OPTIMIZER_CODEX="off",
                   NO_COLOR="1")
        env.pop("COLUMNS", None)
        data = json.dumps({"session_id": "s1", "model": {"display_name": "Opus 5.5"}})

        def row():
            result = subprocess.run([sys.executable, "-X", "utf8", statusline], input=data, env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8",
                                    timeout=30, check=True)
            return result.stdout.splitlines()[0]

        self.assertEqual(row(), "Opus 5.5 · Usage Optimizer 2026-10-31.13")
        deadline = time.monotonic() + 60
        while not os.path.exists(os.path.join(self.state, "kit-update.json")) and time.monotonic() < deadline:
            time.sleep(0.05)
        while os.path.exists(os.path.join(self.state, "kit-update.lock")) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertEqual(self.cache()["latest"], "2026-11-01.1")
        self.assertEqual(row(), "Opus 5.5 · Usage Optimizer 2026-10-31.13 ⇡ 2026-11-01.1")
        deadline = time.monotonic() + 20
        while not self.pushes() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertEqual(len(self.pushes()), 1)


class StatuslineSpawnTests(unittest.TestCase):
    """The statusline's 6-hour throttle, lock and off switch, with the spawn itself mocked."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self.state = os.path.join(self.root, "state")
        self.bin = os.path.join(self.root, "prefix", "bin")
        os.makedirs(self.bin)
        shutil.copy2(STATUSLINE, os.path.join(self.bin, "claude-statusline"))
        write(os.path.join(self.bin, "kit-update"), "")
        write(os.path.join(self.root, "prefix", "source.json"), json.dumps({"checkout": self.root}))
        self.module = load(os.path.join(self.bin, "claude-statusline"), "statusline_spawn_tested_%d" % id(self))
        patcher = mock.patch.dict(os.environ, {"LANES_STATE": self.state})
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("USAGE_OPTIMIZER_UPDATE_CHECK", None)
        self.now = dt.datetime.now(dt.timezone.utc)

    def latest(self, installed="2026-10-31.13"):
        with mock.patch.object(self.module.subprocess, "Popen") as popen:
            latest = self.module._kit_update_latest(installed, self.now)
        return latest, [call.args[0] for call in popen.call_args_list]

    def write_cache(self, hours_ago, installed="2026-10-31.13", latest="2026-11-01.1"):
        write(os.path.join(self.state, "kit-update.json"), json.dumps({
            "checked_at": iso(self.now - dt.timedelta(hours=hours_ago)), "installed": installed, "latest": latest,
            "checkout": self.root, "error": None, "announced": latest}))

    def age(self, name, hours):
        moment = time.time() - hours * 3600
        os.utime(os.path.join(self.state, name), (moment, moment))

    def test_no_cache_spawns_once_then_waits_six_hours(self):
        latest, spawns = self.latest()
        self.assertIsNone(latest)
        self.assertEqual(spawns, [[sys.executable, os.path.join(os.path.realpath(self.bin), "kit-update"), "check"]])
        with open(os.path.join(self.state, "kit-update.spawned"), encoding="utf-8") as handle:
            self.assertEqual(handle.read().strip(), "2026-10-31.13")
        self.assertEqual(self.latest()[1], [])
        self.age("kit-update.spawned", 5.9)
        self.assertEqual(self.latest()[1], [])
        self.age("kit-update.spawned", 6.1)
        self.assertEqual(len(self.latest()[1]), 1)

    def test_a_cache_younger_than_six_hours_is_only_read(self):
        self.write_cache(hours_ago=5.9)
        self.assertEqual(self.latest(), ("2026-11-01.1", []))
        self.write_cache(hours_ago=6.1)
        latest, spawns = self.latest()
        self.assertEqual((latest, len(spawns)), ("2026-11-01.1", 1))

    def test_a_new_install_is_checked_at_once_then_throttled(self):
        self.write_cache(hours_ago=1, installed="2026-10-31.13")
        self.latest("2026-10-31.13")
        write(os.path.join(self.state, "kit-update.spawned"), "2026-10-31.13\n")
        latest, spawns = self.latest("2026-10-31.14")
        self.assertEqual((latest, len(spawns)), ("2026-11-01.1", 1))
        self.assertEqual(self.latest("2026-10-31.14")[1], [])
        self.assertEqual(self.latest("2026-11-01.1"), (None, [[sys.executable, mock.ANY, "check"]]))

    def test_a_running_check_blocks_the_spawn(self):
        write(os.path.join(self.state, "kit-update.lock"), "")
        self.assertEqual(self.latest()[1], [])
        self.age("kit-update.lock", 1)
        self.assertEqual(len(self.latest()[1]), 1)

    def test_an_install_without_a_recorded_checkout_never_spawns(self):
        os.unlink(os.path.join(self.root, "prefix", "source.json"))
        self.assertEqual(self.latest(), (None, []))
        self.write_cache(hours_ago=7)
        self.assertEqual(self.latest(), ("2026-11-01.1", []))

    def test_the_off_switch_neither_spawns_nor_shows(self):
        self.write_cache(hours_ago=7)
        os.environ["USAGE_OPTIMIZER_UPDATE_CHECK"] = "off"
        self.assertEqual(self.latest(), (None, []))
        self.assertFalse(os.path.exists(os.path.join(self.state, "kit-update.spawned")))

    def test_only_a_newer_release_is_shown(self):
        for cached, shown in (("2026-11-01.1", "2026-11-01.1"), ("2026-10-31.14", "2026-10-31.14"),
                              ("2026-10-31.13", None), ("2026-10-30.20", None), (None, None), ("junk", None)):
            with self.subTest(cached=cached):
                self.write_cache(hours_ago=1, latest=cached)
                self.assertEqual(self.latest(), (shown, []))
        write(os.path.join(self.state, "kit-update.json"), "not json")
        write(os.path.join(self.state, "kit-update.spawned"), "2026-10-31.13\n")
        self.assertEqual(self.latest(), (None, []))


if __name__ == "__main__":
    unittest.main()
