import contextlib
import datetime
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import shlex
import shutil
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
import uuid
from unittest import mock


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


class LaneCloudTests(unittest.TestCase):
    def setUp(self):
        self.root = os.path.join(os.path.dirname(__file__), ".lane-cloud-{}-{}".format(os.getpid(), uuid.uuid4().hex))
        os.makedirs(self.root)
        self.addCleanup(force_rmtree, self.root)
        # The suite runs on a PC and in cloud VMs (CLAUDE_CODE_REMOTE=true), where a cloud launch is refused.
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("CLAUDE_CODE_REMOTE", None)
        os.environ.pop("USAGE_OPTIMIZER_SESSION_GUARD", None)
        self.bin = os.path.join(self.root, "bin")
        self.workspace = os.path.join(self.root, "workspace")
        self.origin = os.path.join(self.root, "origin.git")
        self.state = os.path.join(self.root, "state")
        self.config = os.path.join(self.root, "config")
        self.outdir = os.path.join(self.root, "run output")
        self.brief = os.path.join(self.root, "brief.md")
        self.runner = os.path.join(self.root, "lane-term-fake.py")
        os.makedirs(self.bin)
        os.makedirs(self.workspace)
        os.makedirs(os.path.join(self.config, "bin"))
        self.write(self.brief, "Create a small cloud result file.\n")
        self.write(self.runner, textwrap.dedent('''
            import json
            import os
            import subprocess
            import sys
            import time

            args = sys.argv[1:]
            out = args[args.index("--out") + 1]
            cwd = args[args.index("--cwd") + 1]
            command = args[args.index("--") + 1:]
            started = time.monotonic()
            result = subprocess.run(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    timeout=20, check=False)
            with open(out + ".txt", "wb") as stream:
                stream.write(result.stdout)
            print(json.dumps({"exit_code": result.returncode, "stopped": False,
                              "seconds": round(time.monotonic() - started, 3), "answered": 1,
                              "until_seen": True, "bytes": len(result.stdout)}))
        '''))
        self.install_cli("claude", '''
            import os
            import re
            import subprocess
            import sys

            args = sys.argv[1:]
            prompt = args[args.index("--cloud") + 1]
            mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
            run_id = re.search(r"CLOUD RUN (.+?)\\.", prompt).group(1)
            session = "session_Fake123"
            if mode != "no-start":
                helper = os.path.join(os.environ["FAKE_TMP"], "fake-claude-" + str(os.getpid()))
                try:
                    subprocess.run(["git", "-C", os.environ["FAKE_WORKSPACE"], "worktree", "add", "-b",
                                    "claude/test", helper, os.environ["FAKE_BRANCH"]],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=True)
                    def git(*parts):
                        subprocess.run(["git", "-C", helper, "-c", "user.name=Cloud Fake",
                                        "-c", "user.email=cloud-fake@localhost"] + list(parts),
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=True)
                    git("remote", "set-url", "origin", os.environ["FAKE_ORIGIN"])
                    git("commit", "--allow-empty", "-m", "lane: start " + run_id)
                    if mode != "single-push":
                        pushed = subprocess.run([sys.executable, os.environ["FAKE_GIT_SCRIPT"], "-C", helper,
                                                 "push", "-u", "origin", "HEAD"], stdout=subprocess.PIPE,
                                                stderr=subprocess.PIPE, timeout=10, check=False)
                        if pushed.returncode:
                            raise RuntimeError(pushed.stderr.decode("utf-8", "replace"))
                    if mode in ("ok", "partial", "report", "subagents", "verify-change", "new-branch",
                                "single-push"):
                        with open(os.path.join(helper, "cloud-result.txt"), "w", encoding="utf-8") as stream:
                            stream.write("returned from cloud\\n")
                        git("add", "cloud-result.txt")
                        git("commit", "-m", "cloud task result")
                    done = "lane: done " + run_id
                    if mode == "partial":
                        done += " PARTIAL: fake partial result"
                    if mode == "verify-partial":
                        done += " PARTIAL: 1 of 2 commands failed"
                    if mode in ("report", "subagents") or mode.startswith("verify"):
                        body = "Fake report line\\n# Kept heading\\n"
                        if mode == "subagents":
                            body = "Fake report line\\nSubagents: 3\\n- read files\\n"
                        report = os.path.join(os.environ["FAKE_TMP"], "report-" + run_id + ".md")
                        with open(report, "w", encoding="utf-8") as stream:
                            stream.write(done + "\\n\\n" + body)
                        git("commit", "--allow-empty", "-F", report)
                    else:
                        git("commit", "--allow-empty", "-m", done)
                    destination = "HEAD:refs/heads/claude/done" if mode == "new-branch" else "HEAD"
                    pushed = subprocess.run([sys.executable, os.environ["FAKE_GIT_SCRIPT"], "-C", helper,
                                             "push", "origin", destination], stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE, timeout=10, check=False)
                    if pushed.returncode:
                        raise RuntimeError(pushed.stderr.decode("utf-8", "replace"))
                    if mode == "verify-after-done":
                        git("commit", "--allow-empty", "-m", "Stop-hook commit your changes")
                        pushed = subprocess.run([sys.executable, os.environ["FAKE_GIT_SCRIPT"], "-C", helper,
                                                 "push", "origin", "HEAD"], stdout=subprocess.PIPE,
                                                stderr=subprocess.PIPE, timeout=10, check=False)
                        if pushed.returncode:
                            raise RuntimeError(pushed.stderr.decode("utf-8", "replace"))
                finally:
                    subprocess.run(["git", "-C", os.environ["FAKE_WORKSPACE"], "worktree", "remove",
                                    "--force", helper], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   timeout=10, check=False)
                    subprocess.run(["git", "-C", os.environ["FAKE_WORKSPACE"], "branch", "-D", "claude/test"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=False)
            print("Created cloud session: fake title")
            print("View: https://claude.ai/code/" + session + "?from=cli&m=0")
            print("Resume with: claude --teleport " + session)
        ''')
        self.install_cli("codex", '''
            import os
            import sys

            args = sys.argv[1:]
            if args[:2] == ["cloud", "exec"]:
                env = args[args.index("--env") + 1]
                if env == os.environ.get("FAKE_CODEX_MISSING_ENV"):
                    print("Error: environment '" + env + "' not found; run `codex cloud` to list available "
                          "environments", file=sys.stderr)
                    sys.exit(1)
                prompt = sys.stdin.read()
                with open(os.environ["FAKE_CODEX_PROMPT"], "w", encoding="utf-8") as stream:
                    stream.write(prompt)
                if os.environ.get("FAKE_CODEX_ERROR_LOG"):
                    with open("error.log", "w", encoding="utf-8") as stream:
                        stream.write("ChatGPT account id: fake\\n")
                print("Task: https://chatgpt.com/codex/tasks/fake-task-123")
            elif args[:2] == ["cloud", "status"]:
                with open(os.environ["FAKE_CODEX_CWDS"], "a", encoding="utf-8") as stream:
                    stream.write("status " + os.getcwd() + "\\n")
                path = os.environ["FAKE_CODEX_STATUS"]
                try:
                    with open(path, "r", encoding="ascii") as stream:
                        count = int(stream.read())
                except OSError:
                    count = 0
                count += 1
                with open(path, "w", encoding="ascii") as stream:
                    stream.write(str(count))
                print(os.environ.get("FAKE_CODEX_RUNNING", "running") if count == 1 else "ready")
                sys.exit(1 if count == 1 else 0)
            elif args[:2] == ["cloud", "diff"]:
                with open(os.environ["FAKE_CODEX_CWDS"], "a", encoding="utf-8") as stream:
                    stream.write("diff " + os.getcwd() + "\\n")
                print("diff --git a/codex-result.txt b/codex-result.txt")
                print("new file mode 100644")
                print("--- /dev/null")
                print("+++ b/codex-result.txt")
                print("@@ -0,0 +1 @@")
                print("+returned from Codex Cloud")
            else:
                sys.exit(2)
        ''')
        self.git("init", "--bare", self.origin)
        self.git("init", self.workspace)
        self.git("-C", self.workspace, "branch", "-M", "main")
        self.write(os.path.join(self.workspace, "base.txt"), "base\n")
        self.git("-C", self.workspace, "add", "base.txt")
        self.git("-C", self.workspace, "-c", "user.name=Lane Test", "-c", "user.email=lane-test@localhost",
                 "commit", "-m", "base")
        self.base_sha = self.git("-C", self.workspace, "rev-parse", "HEAD").stdout.decode("ascii").strip()
        self.git("-C", self.workspace, "remote", "add", "origin", self.origin)
        self.env = os.environ.copy()
        self.env.update({
            "LANES_STATE": self.state,
            "LANES_CONFIG": self.config,
            "LANES_ARMS": os.path.join(ROOT, "arms.json"),
            "LANES_ARMS_LOCAL": os.path.join(self.root, "no-local-arms.json"),
            "LANE_NO_USAGE": "1",
            "LANE_NO_ETA": "1",
            "LANES_MEM_CHECK": "off",
            "LANES_CLOUD_ANY_REMOTE": "1",
            "LANES_CLOUD_POLL": "0.05",
            "LANES_CLOUD_START_TIMEOUT": "2",
            "LANES_TERM": self.runner,
            "FAKE_ORIGIN": self.origin,
            "FAKE_WORKSPACE": self.workspace,
            "FAKE_BRANCH": "main",
            "FAKE_TMP": self.root,
            "FAKE_CODEX_PROMPT": os.path.join(self.root, "codex-prompt.txt"),
            "FAKE_CODEX_STATUS": os.path.join(self.root, "codex-status.txt"),
            "FAKE_CODEX_CWDS": os.path.join(self.root, "codex-cwds.txt"),
            "FAKE_GIT_SCRIPT": os.path.join(self.config, "fake_git.py"),
            "FAKE_REAL_GIT": shutil.which("git"),
            "PATH": self.bin + os.pathsep + os.environ.get("PATH", ""),
        })
        self.env.pop("USAGE_OPTIMIZER_MODE", None)
        self.env.pop("LANES_CLOUD_KEEP", None)
        self.env.pop("LANES_CODEX_CLOUD_ENV", None)
        self.install_cloud_git()

    def write(self, path, text):
        with open(path, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(textwrap.dedent(text))

    def git(self, *args):
        return subprocess.run(["git"] + list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=10, check=True)

    def install_cli(self, name, body):
        script = os.path.join(self.bin, "fake_{}.py".format(name))
        self.write(script, body)
        if os.name == "nt":
            launcher = os.path.join(self.bin, name + ".cmd")
            self.write(launcher, '@echo off\n"{}" "{}" %*\n'.format(sys.executable, script))
        else:
            launcher = os.path.join(self.bin, name)
            self.write(launcher, "#!/bin/sh\nexec {} {} \"$@\"\n".format(shlex.quote(sys.executable),
                                                                               shlex.quote(script)))
            os.chmod(launcher, 0o755)

    def install_cloud_git(self):
        script = os.path.join(self.config, "fake_git.py")
        self.write(script, '''
            import fnmatch
            import os
            import shutil
            import subprocess
            import sys

            native = os.environ["FAKE_REAL_GIT"]
            origin = os.environ["FAKE_ORIGIN"]
            args = sys.argv[1:]
            cwd = None
            if len(args) >= 2 and args[0] == "-C":
                cwd, args = args[1], args[2:]

            def run(command):
                return subprocess.run([native] + command, cwd=cwd, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, timeout=20, check=False)

            def emit(result):
                sys.stdout.buffer.write(result.stdout)
                sys.stderr.buffer.write(result.stderr)
                sys.exit(result.returncode)

            def git_objects(path, bare=False):
                command = ["--git-dir", path, "rev-parse", "--path-format=absolute", "--git-common-dir"] if bare else \
                          ["-C", path, "rev-parse", "--path-format=absolute", "--git-common-dir"]
                result = subprocess.run([native] + command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        timeout=20, check=True)
                value = result.stdout.decode("utf-8").strip()
                return os.path.join(value, "objects")

            def copy_objects(source, destination):
                os.makedirs(destination, exist_ok=True)
                for current, dirs, files in os.walk(source):
                    rel = os.path.relpath(current, source)
                    target = destination if rel == "." else os.path.join(destination, rel)
                    os.makedirs(target, exist_ok=True)
                    for name in files:
                        src = os.path.join(current, name)
                        dst = os.path.join(target, name)
                        if not os.path.exists(dst):
                            shutil.copy2(src, dst)

            if args and args[0] == "ls-remote":
                pattern = args[2] if len(args) > 2 else "refs/*"
                result = subprocess.run([native, "--git-dir", origin, "for-each-ref",
                                         "--format=%(objectname)%09%(refname)", "refs/heads"],
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20, check=False)
                if result.returncode:
                    emit(result)
                for line in result.stdout.decode("utf-8").splitlines():
                    sha, ref = line.split("\\t", 1)
                    if fnmatch.fnmatchcase(ref, pattern):
                        print(sha + "\\t" + ref)
                sys.exit(0)
            if args and args[0] == "push":
                if "--delete" in args:
                    branch = args[args.index("--delete") + 1]
                    emit(subprocess.run([native, "--git-dir", origin, "update-ref", "-d",
                                         "refs/heads/" + branch], stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, timeout=20, check=False))
                refspec = next((part for part in reversed(args) if part == "HEAD" or ":" in part), None)
                if refspec is None:
                    sys.exit(2)
                source, separator, destination = refspec.partition(":")
                if not separator:
                    name = run(["symbolic-ref", "--quiet", "--short", "HEAD"])
                    if name.returncode:
                        emit(name)
                    destination = "refs/heads/" + name.stdout.decode("utf-8").strip()
                sha = run(["rev-parse", source])
                if sha.returncode:
                    emit(sha)
                source_objects = git_objects(cwd)
                remote_objects = git_objects(origin, bare=True)
                copy_objects(source_objects, remote_objects)
                target_sha = sha.stdout.decode("ascii").strip()
                updated = subprocess.run([native, "--git-dir", origin, "update-ref", destination, target_sha],
                                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20, check=False)
                if updated.returncode:
                    sys.stderr.write("source_objects={} remote_objects={} source_has={} remote_has={}\\n".format(
                        source_objects, remote_objects,
                        os.path.exists(os.path.join(source_objects, target_sha[:2], target_sha[2:])),
                        os.path.exists(os.path.join(remote_objects, target_sha[:2], target_sha[2:]))))
                emit(updated)
            if args and args[0] == "fetch":
                refspec = args[-1].lstrip("+")
                fail_marker = os.environ.get("FAKE_FAIL_FETCH_ONCE")
                if fail_marker and "refs/heads/claude/test:" in refspec and not os.path.exists(fail_marker):
                    with open(fail_marker, "w", encoding="ascii") as stream:
                        stream.write("failed once")
                    sys.exit(1)
                source, separator, destination = refspec.partition(":")
                if not separator:
                    sys.exit(2)
                sha = subprocess.run([native, "--git-dir", origin, "rev-parse", source],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20, check=False)
                if sha.returncode:
                    emit(sha)
                copy_objects(git_objects(origin, bare=True), git_objects(cwd))
                emit(run(["update-ref", destination, sha.stdout.decode("ascii").strip()]))
            emit(run(args))
        ''')
        lane_bin = os.path.join(self.config, "bin")
        if os.name == "nt":
            self.write(os.path.join(lane_bin, "git.cmd"), '@echo off\n"{}" "{}" %*\n'.format(
                sys.executable, script))
        else:
            launcher = os.path.join(lane_bin, "git")
            self.write(launcher, "#!/bin/sh\nexec {} {} \"$@\"\n".format(shlex.quote(sys.executable),
                                                                                shlex.quote(script)))
            os.chmod(launcher, 0o755)

    def run_lane(self, lane="haiku", extra=(), effort="high", env=None, dir_path=None):
        argv = [sys.executable, SCRIPT, lane, "-C", dir_path or self.workspace, "-b", self.brief]
        if effort:
            argv.extend(["-e", effort])
        argv.extend(extra)
        return subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20, check=False,
                              env=dict(self.env, **(env or {})), encoding="utf-8", errors="replace")

    def remote_refs(self):
        result = self.git("--git-dir", self.origin, "for-each-ref", "--format=%(objectname)%09%(refname)",
                          "refs/heads")
        return {line.split("\t", 1)[1]: line.split("\t", 1)[0]
                for line in result.stdout.decode("utf-8").splitlines() if "\t" in line}

    def read_json(self, path):
        with open(path, "r", encoding="utf-8") as stream:
            return json.load(stream)

    def test_claude_cloud_ok_applies_uncommitted_diff_and_cleans_branches(self):
        result = self.run_lane(extra=["--cloud", "--outdir", self.outdir])
        screen_path = os.path.join(self.outdir, "cloud-screen.txt")
        if os.path.isfile(screen_path):
            with open(screen_path, encoding="utf-8") as stream:
                screen = stream.read()
        else:
            screen = ""
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout + screen)
        self.assertIn("verdict=OK", result.stdout)
        with open(os.path.join(self.workspace, "cloud-result.txt"), "r", encoding="utf-8") as stream:
            self.assertEqual(stream.read(), "returned from cloud\n")
        self.assertTrue(self.git("-C", self.workspace, "status", "--porcelain").stdout)
        self.assertEqual(self.git("-C", self.workspace, "rev-parse", "HEAD").stdout.decode().strip(), self.base_sha)
        self.assertEqual(self.remote_refs(), {})
        meta = self.read_json(os.path.join(self.outdir, "meta.json"))
        self.assertEqual(meta["place"], "cloud")
        self.assertEqual(meta["cloud"]["kind"], "claude")
        self.assertEqual(meta["cloud"]["session_id"], "session_Fake123")
        self.assertIn("https://claude.ai/code/session_Fake123", meta["cloud"]["url"])
        self.assertEqual(meta["cloud"]["result_branch"], "claude/test")
        self.assertTrue(meta["cloud"]["result_sha"])
        # The done commit has no body here, so there is no report.
        self.assertFalse(os.path.exists(os.path.join(self.outdir, "report.md")))
        self.assertNotIn("report", meta["cloud"])
        self.assertIsNone(meta["usage"]["tokens"])
        self.assertIsNone(meta["usage"]["list_usd"])
        with open(os.path.join(self.state, "ledger.jsonl"), "r", encoding="utf-8") as stream:
            ledger = [json.loads(line) for line in stream]
        self.assertEqual(ledger[0]["place"], "cloud")
        self.assertEqual(self.git("-C", self.workspace, "for-each-ref", "--format=%(refname)",
                                  "refs/lane-cloud").stdout.strip(), b"")

    def refused_in_a_cloud_session(self, result):
        self.assertEqual(result.returncode, 8, result.stderr + result.stdout)
        self.assertIn("a cloud session never starts another session", result.stderr)
        self.assertIn("USAGE_OPTIMIZER_SESSION_GUARD=off", result.stderr)
        self.assertEqual(self.remote_refs(), {})
        self.assertFalse(os.path.exists(os.path.join(self.state, "runs")), "no run directory may be reserved")
        self.assertFalse(os.path.exists(self.outdir))
        self.assertFalse(os.path.exists(os.path.join(self.workspace, "cloud-result.txt")))
        self.assertFalse(os.path.exists(os.path.join(self.root, "codex-prompt.txt")))

    def test_cloud_runs_are_refused_inside_a_cloud_session_and_launch_nothing(self):
        cloud = {"CLAUDE_CODE_REMOTE": "true", "LANES_CODEX_CLOUD_ENV": "test-env"}
        for extra in (["--cloud"], ["--cloud", "--verify"], ["--cloud", "--side", "needs its own VM"],
                      ["--cloud", "--outdir", self.outdir]):
            self.refused_in_a_cloud_session(self.run_lane(extra=extra, env=cloud))
        self.refused_in_a_cloud_session(self.run_lane("codex-cloud", effort=None, env=cloud))
        self.refused_in_a_cloud_session(self.run_lane("codex-cloud", extra=["--outdir", self.outdir], effort=None,
                                                      env=cloud))

    def test_a_claude_cloud_run_goes_on_inside_a_cloud_session_with_the_guard_off(self):
        result = self.run_lane(extra=["--cloud", "--outdir", self.outdir],
                               env={"CLAUDE_CODE_REMOTE": "true", "USAGE_OPTIMIZER_SESSION_GUARD": " Off "})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("verdict=OK", result.stdout)

    def test_a_codex_cloud_run_goes_on_inside_a_cloud_session_with_the_guard_off(self):
        result = self.run_lane("codex-cloud", extra=["--outdir", self.outdir], effort=None,
                               env={"CLAUDE_CODE_REMOTE": "true", "USAGE_OPTIMIZER_SESSION_GUARD": "off",
                                    "LANES_CODEX_CLOUD_ENV": "test-env"})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("verdict=OK", result.stdout)

    def test_a_cloud_dry_run_and_a_local_run_are_allowed_inside_a_cloud_session(self):
        result = self.run_lane(extra=["--cloud", "--dry-run"], env={"CLAUDE_CODE_REMOTE": "true"})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("cloud preflight: PASS", result.stdout)
        self.assertEqual(self.remote_refs(), {})
        result = self.run_lane("codex-cloud", extra=["--dry-run"], effort=None,
                               env={"CLAUDE_CODE_REMOTE": "true", "LANES_CODEX_CLOUD_ENV": "test-env"})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        result = self.run_lane(extra=["--dry-run"], env={"CLAUDE_CODE_REMOTE": "true"})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_claude_cloud_noop(self):
        result = self.run_lane(extra=["--cloud", "--outdir", self.outdir], env={"FAKE_CLAUDE_MODE": "noop"})
        self.assertEqual(result.returncode, 3, result.stderr + result.stdout)
        self.assertIn("verdict=NOOP", result.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.workspace, "cloud-result.txt")))
        self.assertEqual(self.remote_refs(), {})
        # The default brief names no ignored path, so there is no warning and no key.
        self.assertNotIn("git ignores", result.stderr)
        self.assertNotIn("ignored_paths", self.read_json(os.path.join(self.outdir, "meta.json"))["cloud"])

    def test_claude_cloud_noop_names_the_ignored_paths_the_brief_asks_for(self):
        self.write(os.path.join(self.workspace, ".gitignore"), "out/\n")
        self.git("-C", self.workspace, "add", ".gitignore")
        self.git("-C", self.workspace, "-c", "user.name=Lane Test", "-c", "user.email=lane-test@localhost",
                 "commit", "-m", "ignore out")
        self.write(self.brief, "Write the summary to `out/summary.json` and update base.txt.\n")
        result = self.run_lane(extra=["--cloud", "--outdir", self.outdir], env={"FAKE_CLAUDE_MODE": "noop"})
        self.assertEqual(result.returncode, 3, result.stderr + result.stdout)
        self.assertIn("verdict=NOOP", result.stdout)
        self.assertIn("warning: NOOP: the diff is empty and the brief names paths git ignores (out/summary.json)",
                      result.stderr)
        self.assertIn("git add -f", result.stderr)
        meta = self.read_json(os.path.join(self.outdir, "meta.json"))
        self.assertEqual(meta["cloud"]["ignored_paths"], ["out/summary.json"])
        self.assertEqual(meta["verdict"], "NOOP")

    def test_brief_ignored_paths_finds_only_ignored_paths_in_a_real_repository(self):
        lane = self.lane_module()
        repo = self.git_repo({".gitignore": "out/\n*.log\n"}, commit=False)
        brief = ("Write `out/report.json` and notes/plan.md (keep build.log), see https://example.com/out/x.txt,\n"
                 "/home/user/out/abs.txt, ../out/up.txt and `git add -f <path>`.\n")
        self.assertEqual(lane.brief_ignored_paths(repo, brief), ["out/report.json", "build.log"])
        self.assertEqual(lane.brief_ignored_paths(repo, "Only notes/plan.md here."), [])
        outside = tempfile.mkdtemp(prefix="lane-no-repo-")
        self.addCleanup(force_rmtree, outside)
        self.assertEqual(lane.brief_ignored_paths(outside, "Write `out/report.json`."), [])

    def test_brief_ignored_paths_survives_a_bad_name_quoted_names_and_keeps_the_brief_order(self):
        lane = self.lane_module()
        repo = self.git_repo({".gitignore": "out/\n", "real/keep.txt": "x"}, commit=False)
        # Non-ASCII and backslash names are quoted by git without -z, and would then never match.
        brief = "Write out/y.json, then `out/résumé.json` and out/a\\b.json."
        self.assertEqual(lane.brief_ignored_paths(repo, brief),
                         ["out/y.json", "out/résumé.json", "out/a\\b.json"])
        try:
            os.symlink(os.path.join(repo, "real"), os.path.join(repo, "linkdir"))
        except (OSError, NotImplementedError):
            self.skipTest("this system cannot make a symbolic link")
        # A path behind a symlink makes git check-ignore exit 128 for the whole batch; the real hit must survive.
        self.assertEqual(lane.brief_ignored_paths(repo, "Write linkdir/x.txt and out/a.json."), ["out/a.json"])

    def test_a_noop_warning_that_cannot_write_meta_does_not_raise(self):
        lane = self.lane_module()
        repo = self.git_repo({".gitignore": "out/\n"}, commit=False)
        stderr = io.StringIO()
        with mock.patch.object(lane, "cloud_update_meta", side_effect=OSError("disk full")), \
                contextlib.redirect_stderr(stderr):
            lane.cloud_noop_ignored_warning(repo, "Write out/a.json.", {}, os.path.join(repo, "meta.json"), {})
        self.assertIn("names paths git ignores (out/a.json)", stderr.getvalue())
        self.assertIn("could not record ignored_paths", stderr.getvalue())

    def test_only_the_work_steps_ask_for_git_add_f(self):
        lane = self.lane_module()
        sentence = "add it with git add -f <path> and name it in"
        for step in (lane.SUBAGENT_STEP, lane.UTILIZATION_STEP, lane.SAVING_STEP):
            self.assertIn("Commit all your changes; leave nothing uncommitted.\n   A file the brief asks for counts "
                          "even when git ignores it: " + sentence, step)
        for step in (lane.VERIFY_STEP, lane.PARALLEL_VERIFY_STEP):
            self.assertNotIn("git add -f", step)

    def test_claude_cloud_done_commit_body_is_saved_as_report(self):
        result = self.run_lane(extra=["--cloud", "--outdir", self.outdir], env={"FAKE_CLAUDE_MODE": "report"})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("verdict=OK", result.stdout)
        report_path = os.path.join(self.outdir, "report.md")
        self.assertIn("lane: cloud report saved to " + report_path, result.stdout)
        with open(report_path, "r", encoding="utf-8") as stream:
            self.assertEqual(stream.read(), "Fake report line\n# Kept heading\n")
        meta = self.read_json(os.path.join(self.outdir, "meta.json"))
        self.assertEqual(meta["cloud"]["report"], report_path)
        with open(os.path.join(self.workspace, "cloud-result.txt"), "r", encoding="utf-8") as stream:
            self.assertEqual(stream.read(), "returned from cloud\n")

    def test_claude_cloud_uses_done_marker_before_a_followup_commit(self):
        result = self.run_verify("verify-after-done")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("verdict=OK", result.stdout)
        report_path = os.path.join(self.outdir, "report.md")
        with open(report_path, "r", encoding="utf-8") as stream:
            self.assertEqual(stream.read(), "Fake report line\n# Kept heading\n")
        warnings = [line for line in result.stderr.splitlines() if line.startswith("warning:")]
        self.assertEqual(len(warnings), 1, result.stderr)
        self.assertIn("1 commit followed lane: done", warnings[0])
        meta = self.read_json(os.path.join(self.outdir, "meta.json"))
        done_subject = self.git("-C", self.workspace, "show", "-s", "--format=%s",
                                meta["cloud"]["result_sha"]).stdout.decode("utf-8").strip()
        self.assertEqual(done_subject, "lane: done " + os.path.basename(self.outdir))

    def test_claude_cloud_finds_done_marker_on_a_new_branch(self):
        result = self.run_lane(extra=["--cloud", "--outdir", self.outdir], env={"FAKE_CLAUDE_MODE": "new-branch"})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("verdict=OK", result.stdout)
        with open(os.path.join(self.workspace, "cloud-result.txt"), "r", encoding="utf-8") as stream:
            self.assertEqual(stream.read(), "returned from cloud\n")
        meta = self.read_json(os.path.join(self.outdir, "meta.json"))
        self.assertEqual(meta["cloud"]["result_branch"], "claude/done")
        done_subject = self.git("-C", self.workspace, "show", "-s", "--format=%s",
                                meta["cloud"]["result_sha"]).stdout.decode("utf-8").strip()
        self.assertEqual(done_subject, "lane: done " + os.path.basename(self.outdir))

    def test_claude_cloud_retries_a_failed_fetch_for_a_single_push(self):
        fail_marker = os.path.join(self.root, "failed-fetch-once")
        result = self.run_lane(extra=["--cloud", "--outdir", self.outdir],
                               env={"FAKE_CLAUDE_MODE": "single-push", "FAKE_FAIL_FETCH_ONCE": fail_marker})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("verdict=OK", result.stdout)
        self.assertTrue(os.path.isfile(fail_marker))
        with open(os.path.join(self.workspace, "cloud-result.txt"), "r", encoding="utf-8") as stream:
            self.assertEqual(stream.read(), "returned from cloud\n")

    def install_fake_eta(self):
        script = os.path.join(self.root, "fake-lane-stats.py")
        self.write(script, '''
            import json
            import os
            import sys

            marker = os.environ.get("FAKE_ETA_MARKER")
            if marker:
                with open(marker, "w", encoding="utf-8") as stream:
                    stream.write(json.dumps(sys.argv[1:]))
            print(json.dumps({"arm": "fake", "class": None, "tag": None, "minutes": 14.2, "p80_minutes": 25.0,
                              "tier": "measured", "runs": {"arm_class": 9}}))
        ''')
        return script

    def test_claude_cloud_run_records_an_eta(self):
        script = self.install_fake_eta()
        marker = os.path.join(self.root, "eta-argv.json")
        result = self.run_lane(extra=["--cloud", "--outdir", self.outdir],
                               env={"LANE_STATS": script, "LANE_NO_ETA": "0", "FAKE_ETA_MARKER": marker})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("verdict=OK", result.stdout)
        self.assertIn("lane: eta ~14 min (p80 25; measured, 9 runs)", result.stderr)
        self.assertTrue(os.path.exists(marker))
        meta = self.read_json(os.path.join(self.outdir, "meta.json"))
        self.assertEqual(meta["place"], "cloud")
        self.assertEqual(meta["eta_s"], 852.0)
        self.assertEqual(meta["eta_p80_s"], 1500.0)
        self.assertEqual(meta["eta_tier"], "measured")
        with open(os.path.join(self.state, "ledger.jsonl"), "r", encoding="utf-8") as stream:
            ledger = [json.loads(line) for line in stream]
        self.assertEqual(ledger[0]["eta_s"], 852.0)

    def test_claude_cloud_verify_makes_no_eta_call(self):
        script = self.install_fake_eta()
        marker = os.path.join(self.root, "eta-called")
        result = self.run_lane(extra=["--cloud", "--verify", "--outdir", self.outdir],
                               env={"FAKE_CLAUDE_MODE": "verify", "LANE_STATS": script, "LANE_NO_ETA": "0",
                                    "FAKE_ETA_MARKER": marker})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("verdict=OK", result.stdout)
        self.assertFalse(os.path.exists(marker))
        self.assertNotIn("lane: eta", result.stderr)
        meta = self.read_json(os.path.join(self.outdir, "meta.json"))
        self.assertIsNone(meta["eta_s"])
        self.assertIsNone(meta["eta_p80_s"])
        self.assertIsNone(meta["eta_tier"])

    def test_codex_cloud_run_does_not_fail_in_the_eta_step(self):
        script = self.install_fake_eta()
        result = self.run_lane("codex-cloud", extra=["--outdir", self.outdir], effort=None,
                               env={"LANES_CODEX_CLOUD_ENV": "test-env", "LANE_STATS": script, "LANE_NO_ETA": "0"})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("verdict=OK", result.stdout)
        self.assertNotIn("Traceback", result.stderr)
        meta = self.read_json(os.path.join(self.outdir, "meta.json"))
        self.assertEqual(meta["place"], "cloud")
        self.assertTrue(meta["eta_s"] is None or isinstance(meta["eta_s"], float))

    def cloud_prompt(self, meta):
        return meta["cmd"][meta["cmd"].index("--cloud") + 1]

    def test_claude_cloud_prompt_asks_for_subagents_on_the_lane_model(self):
        for lane in ("sonnet", "haiku"):
            outdir = os.path.join(self.root, "out-" + lane)
            # noop leaves the work tree clean, so both lanes can run in turn.
            result = self.run_lane(lane=lane, extra=["--cloud", "--outdir", outdir],
                                   env={"FAKE_CLAUDE_MODE": "noop"})
            self.assertEqual(result.returncode, 3, result.stderr + result.stdout)
            prompt = self.cloud_prompt(self.read_json(os.path.join(outdir, "meta.json")))
            self.assertIn("Agent tool", prompt)
            self.assertIn('model "{}"'.format(lane), prompt)
            self.assertIn("Subagents:", prompt)
            for other in {"sonnet", "haiku"} - {lane}:
                self.assertNotIn('model "{}"'.format(other), prompt)

    def test_claude_cloud_verify_prompt_has_no_subagent_text(self):
        result = self.run_verify("verify")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        prompt = self.cloud_prompt(self.read_json(os.path.join(self.outdir, "meta.json")))
        self.assertNotIn("Agent tool", prompt)
        self.assertNotIn("Subagents:", prompt)

    # ----- the typed label on the first line of every cloud prompt -----

    def test_cloud_title_has_one_first_line_per_kind(self):
        lane = self.lane_module()
        self.assertEqual([kind for kind, _ in lane.CLOUD_TITLE_KINDS], ["mirror", "side", "verify", "worker"])
        expected = {"mirror": "Kit mirror - acme/shop", "side": "Kit side session - acme/shop - unit-1",
                    "verify": "Kit verify - acme/shop - unit-1", "worker": "Kit worker - acme/shop - unit-1"}
        for kind, _ in lane.CLOUD_TITLE_KINDS:
            with self.subTest(kind=kind):
                title = lane.cloud_title(kind, "acme/shop", None if kind == "mirror" else "unit-1")
                self.assertEqual(title, expected[kind])

    def test_cloud_title_is_one_ascii_line_of_at_most_100_characters(self):
        lane = self.lane_module()
        for kind, _ in lane.CLOUD_TITLE_KINDS:
            for name in ("x" * 400, "caf\u00e9\nsecond line\r\n\u2014 dash", "", None):
                with self.subTest(kind=kind, name=name):
                    title = lane.cloud_title(kind, "acme/shop", name)
                    self.assertTrue(title.isascii())
                    self.assertNotIn("\n", title)
                    self.assertNotIn("\r", title)
                    self.assertLessEqual(len(title), 100)
                    self.assertTrue(title.startswith(dict(lane.CLOUD_TITLE_KINDS)[kind] + " - acme/shop"))
        self.assertEqual(len(lane.cloud_title("worker", "acme/shop", "x" * 400)), 100)
        self.assertEqual(lane.cloud_title("worker", "acme/shop", "caf\u00e9\nsecond"),
                         "Kit worker - acme/shop - caf second")
        # A repository name that alone is too long is cut too: the line never exceeds the limit.
        self.assertLessEqual(len(lane.cloud_title("side", "o/" + "r" * 300, "unit")), 100)

    def test_claude_cloud_prompt_puts_the_label_first_and_changes_nothing_else(self):
        lane = self.lane_module()
        plain = lane.claude_cloud_prompt("Brief.", "run-1", "sonnet")
        self.assertEqual(plain.splitlines()[0], "Brief.")
        for title in (lane.cloud_title("worker", "acme/shop", "unit-1"),
                      lane.cloud_title("side", "acme/shop", "unit-1"),
                      lane.cloud_title("verify", "acme/shop", "run-1")):
            prompt = lane.claude_cloud_prompt("Brief.", "run-1", "sonnet", title=title)
            self.assertEqual(prompt.split("\n")[:3], [title, "", "Brief."])
            self.assertEqual(prompt, title + "\n\n" + plain)
        verify = lane.claude_cloud_prompt("Brief.", "run-1", "sonnet", True, "default",
                                          title="Kit verify - acme/shop - run-1")
        self.assertTrue(verify.startswith("Kit verify - acme/shop - run-1\n\nBrief.\n"))
        # `lane main` passes its own prompt, so a title is ignored there.
        command = lane.claude_cloud_command("claude", "lane-term", self.workspace, "p", "", "main-1", "opus", "xhigh",
                                            prompt="OWN PROMPT", title="Kit mirror - acme/shop")
        self.assertEqual(command[command.index("--cloud") + 1], "OWN PROMPT")

    def first_cloud_lines(self):
        """The first two lines of the prompt a real (stand-in) run launched, from its meta.json."""
        meta = self.read_json(os.path.join(self.outdir, "meta.json"))
        return self.cloud_prompt(meta).split("\n")[:3]

    def test_claude_cloud_worker_prompt_starts_with_the_worker_label(self):
        lane = self.lane_module()
        repo = lane.main_repo_key(self.origin)
        result = self.run_lane(extra=["--cloud", "--tag", "label-unit", "--outdir", self.outdir])
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        first = self.first_cloud_lines()
        self.assertEqual(first[:2], ["Kit worker - {} - label-unit".format(repo), ""])
        self.assertTrue(first[2])

    def test_claude_cloud_worker_without_a_tag_is_named_by_its_run_id(self):
        lane = self.lane_module()
        repo = lane.main_repo_key(self.origin)
        result = self.run_lane(extra=["--cloud", "--outdir", self.outdir])
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(self.first_cloud_lines()[0],
                         "Kit worker - {} - {}".format(repo, os.path.basename(self.outdir)))

    def test_claude_cloud_verify_prompt_starts_with_the_verify_label_and_the_run_id(self):
        lane = self.lane_module()
        repo = lane.main_repo_key(self.origin)
        result = self.run_lane(extra=["--cloud", "--verify", "--outdir", self.outdir])
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(self.first_cloud_lines()[0],
                         "Kit verify - {} - {}".format(repo, os.path.basename(self.outdir)))

    def test_cloud_dry_run_launch_shows_the_label(self):
        lane = self.lane_module()
        repo = lane.main_repo_key(self.origin)
        result = self.run_lane(extra=["--cloud", "--tag", "dry-unit", "--dry-run"])
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        launch = json.loads(next(line for line in result.stdout.splitlines() if line.startswith("launch: "))[8:])
        self.assertTrue(launch[launch.index("--cloud") + 1].startswith(
            "Kit worker - {} - dry-unit\n\n".format(repo)))
        result = self.run_lane("codex-cloud", extra=["--tag", "dry-unit", "--dry-run"], effort=None,
                               env={"LANES_CODEX_CLOUD_ENV": "test-env"})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        stdin = json.loads(next(line for line in result.stdout.splitlines() if line.startswith("stdin: "))[7:])
        self.assertTrue(stdin.startswith("Kit worker - {} - dry-unit\n\n".format(repo)), stdin[:80])

    def test_codex_cloud_stdin_starts_with_the_worker_label(self):
        lane = self.lane_module()
        repo = lane.main_repo_key(self.origin)
        result = self.run_lane("codex-cloud", extra=["--tag", "codex-unit", "--outdir", self.outdir], effort=None,
                               env={"LANES_CODEX_CLOUD_ENV": "test-env"})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        with open(os.path.join(self.root, "codex-prompt.txt"), "r", encoding="utf-8") as stream:
            lines = stream.read().split("\n")
        self.assertEqual(lines[:2], ["Kit worker - {} - codex-unit".format(repo), ""])
        self.assertEqual(lines[2], "Create a small cloud result file.")

    def test_claude_cloud_step2_follows_the_mode(self):
        lane = self.lane_module()
        phrases = {"default": "for as much of the work as splits off",
                   "utilization": "usage is not the limit",
                   "saving": 'Use subagents only for reading and searching, with model "haiku"'}
        for mode, phrase in phrases.items():
            prompt = lane.claude_cloud_prompt("Brief.", "run-1", "sonnet", False, mode)
            self.assertIn(phrase, prompt)
            self.assertIn("Subagents:", prompt)
            self.assertIn("replaces the worker rule against starting agents", prompt)
            for other in set(phrases.values()) - {phrase}:
                self.assertNotIn(other, prompt)
        self.assertIn('Pass model "sonnet"', lane.claude_cloud_prompt("Brief.", "run-1", "sonnet", False, "utilization"))
        self.assertIn(lane.SUBAGENT_STEP.format("sonnet"), lane.claude_cloud_prompt("Brief.", "run-1", "sonnet"))

    def test_claude_cloud_verify_step_follows_the_mode(self):
        lane = self.lane_module()
        parallel = lane.claude_cloud_prompt("Brief.", "run-1", "sonnet", True, "utilization")
        self.assertIn("up to 4 parallel shards by test module", parallel)
        self.assertIn("run instead of the whole command, never beside it", parallel)
        self.assertIn("background processes", parallel)
        self.assertIn("shard counts as a command", parallel)
        self.assertIn("lane: done run-1 PARTIAL: <k> of <n> commands failed", parallel)
        self.assertNotIn("Subagents:", parallel)
        # The shard rules may wrap across lines in the prompt, so they are checked on the joined text.
        flat = " ".join(parallel.split())
        self.assertIn("Lane lists the test files of the committed tree", flat)
        self.assertIn("each file is in exactly one shard, with no overlapping patterns", flat)
        self.assertIn("Run the script and do not write a launch line of your own", flat)
        self.assertIn("their test counts add up to the whole suite", flat)
        self.assertIn("for each shard the list of files it ran", flat)
        for mode in ("default", "saving"):
            prompt = lane.claude_cloud_prompt("Brief.", "run-1", "sonnet", True, mode)
            self.assertIn(lane.VERIFY_STEP.format("run-1", "run-1"), prompt)
            self.assertNotIn("shard", prompt)

    def git_repo(self, files, commit=True):
        """Make a temporary git repository with the files (path to text) and commit them unless commit is False."""
        path = tempfile.mkdtemp(prefix="lane-shards-")
        self.addCleanup(force_rmtree, path)
        subprocess.run(["git", "-C", path, "init", "-q"], check=True, timeout=30)
        for name, text in files.items():
            os.makedirs(os.path.dirname(os.path.join(path, name)), exist_ok=True)
            with open(os.path.join(path, name), "w", encoding="utf-8", newline="\n") as stream:
                stream.write(text)
        if commit:
            identity = ["git", "-C", path, "-c", "user.name=kit", "-c", "user.email=kit@localhost"]
            subprocess.run(identity + ["add", "-A"], check=True, timeout=30)
            subprocess.run(identity + ["commit", "-q", "-m", "test shards"], check=True, timeout=30)
        return path

    def test_verify_shards_gives_each_committed_test_module_to_exactly_one_shard(self):
        lane = self.lane_module()
        sizes = {"test_a": 900, "test_b": 700, "test_c": 500, "test_d": 300, "test_e": 200, "test_f": 100}
        files = {"tests/{}.py".format(name): "x" * size for name, size in sizes.items()}
        files["tests/sub/test_nested.py"] = "x" * 5000  # in a subdirectory, so not a module directly in tests/
        files["tests/helper.py"] = "x" * 4000  # not a test_*.py file
        path = self.git_repo(files)
        self.write(os.path.join(path, "tests", "test_late.py"), "x")  # not committed, so the VM never sees it
        # Largest first, each file to the shard with the smallest total: sizes 900,700 | 500 | 300+200 | 100 on c.
        self.assertEqual(lane.verify_shards(path), [
            ["tests.test_a"], ["tests.test_b"], ["tests.test_c", "tests.test_f"], ["tests.test_d", "tests.test_e"]])
        shards = lane.verify_shards(path, count=2)
        self.assertEqual(len(shards), 2)
        self.assertEqual(sorted(sum(shards, [])), sorted("tests.{}".format(name) for name in sizes))

    def test_verify_shards_keeps_a_non_ascii_name_and_gives_up_on_a_name_that_is_no_module(self):
        lane = self.lane_module()
        # Without ls-tree -z, git quotes the non-ASCII path and the module would run in no shard at all.
        path = self.git_repo({"tests/test_a.py": "x" * 20, "tests/test_café.py": "x" * 10})
        self.assertEqual(lane.verify_shards(path), [["tests.test_a"], ["tests.test_café"]])
        # A space would split the name in two in the script; lane hands the session the placeholder script instead.
        for odd in ("tests/test_my x.py", "tests/test_a.b.py"):
            self.assertEqual(lane.verify_shards(self.git_repo({"tests/test_a.py": "x", odd: "x"})), [], odd)

    def test_verify_shard_script_keeps_shell_syntax_out_of_the_run_id(self):
        lane = self.lane_module()
        script = lane.verify_shard_script('run "$(x)" 1', [["tests.test_a"]])
        self.assertIn("lane-verify-run----x---1.XXXXXX", script)
        self.assertNotIn("$(x)", script)

    def test_verify_shards_is_empty_outside_a_repository_or_without_a_commit(self):
        lane = self.lane_module()
        plain = tempfile.mkdtemp(prefix="lane-plain-")
        self.addCleanup(force_rmtree, plain)
        self.assertEqual(lane.verify_shards(plain), [])
        self.assertEqual(lane.verify_shards(os.path.join(plain, "missing")), [])
        self.assertEqual(lane.verify_shards(self.git_repo({"tests/test_a.py": "x"}, commit=False)), [])

    def test_utilization_verify_prompt_carries_the_shard_script(self):
        lane = self.lane_module()
        shards = [["tests.test_a"], ["tests.test_b"], ["tests.test_c"]]
        prompt = lane.claude_cloud_prompt("Brief.", "run-1", "sonnet", True, "utilization", shards=shards)
        self.assertIn("\nBEGIN\n", prompt)
        script = prompt.split("\nBEGIN\n", 1)[1].split("\nEND\n", 1)[0] + "\n"
        # The prompt is formatted twice, so the script must come out of it exactly as the function wrote it.
        self.assertEqual(script, lane.verify_shard_script("run-1", shards))
        self.assertIn("${TMPDIR:-/tmp}", script)
        lines = script.splitlines()
        groups = [line for line in lines if line.endswith(") &")]
        self.assertEqual(len(groups), 3)
        first_group = lines.index(groups[0])
        for name in ("ROOT=", "LOG_DIR="):
            self.assertLess(next(i for i, line in enumerate(lines) if line.startswith(name)), first_group)
        for line in groups:
            self.assertTrue(line.startswith('( cd "$ROOT" && $RUN $SHARD_'), line)
            # Only the shard's own command sits inside the group: no NAME= assignment, which a shell would
            # scope to that group alone.
            self.assertIsNone(re.search(r"(^|[\s;(])[A-Za-z_]\w*=", line), line)
        self.assertEqual(lines.count("wait"), 1)
        self.assertIn('case "$LOG_DIR" in /*)', script)
        self.assertIn('case "$LOG_DIR" in "$ROOT"/*)', script)
        self.assertNotIn("%", script)
        self.assertNotIn("`", script)
        # With no list (lane could not read the commit), the four SHARD values are placeholders to fill in.
        empty = lane.claude_cloud_prompt("Brief.", "run-1", "sonnet", True, "utilization")
        self.assertIn('SHARD_4="<fill>"', empty)
        self.assertNotIn("SHARD_5", empty)
        self.assertIn("placeholders", empty)
        for mode in ("default", "saving"):
            self.assertEqual(lane.claude_cloud_prompt("Brief.", "run-1", "sonnet", True, mode, shards=shards),
                             lane.claude_cloud_prompt("Brief.", "run-1", "sonnet", True, mode))

    def test_verify_shards_is_listed_only_for_utilization_verify_runs(self):
        lane = self.lane_module()
        path = self.git_repo({"tests/test_a.py": "x"})
        calls = []

        def listing(folder, count=4):
            calls.append(folder)
            return [["tests.test_a"]]

        with mock.patch.object(lane, "verify_shards", side_effect=listing):
            for verify, mode in ((True, "utilization"), (True, "default"), (False, "utilization")):
                lane.claude_cloud_command("claude", "term.py", path, os.path.join(path, "out"), "Brief.", "run-1",
                                          "claude-haiku-5-5", "high", verify=verify, mode=mode)
        self.assertEqual(calls, [path])

    @unittest.skipUnless(shutil.which("sh"), "the shard script runs under a POSIX sh")
    @unittest.skipIf(os.name == "nt", "the shard script runs in the Linux VM; Git for Windows prints C:/ paths,"
                     " which its absolute-path check refuses")
    def test_shard_script_runs_each_module_once_and_reports_each_return_code(self):
        lane = self.lane_module()
        work = tempfile.mkdtemp(prefix="lane-run-")
        self.addCleanup(force_rmtree, work)
        mark = os.path.join(work, "ran.txt")
        # Each module appends its name to mark when it is imported, so a module that ran twice shows twice.
        template = textwrap.dedent("""\
            import unittest

            with open({mark!r}, "a", encoding="utf-8") as stream:
                stream.write({name!r} + "\\n")


            class Check(unittest.TestCase):
                def test_runs(self):
                    self.assertTrue({passes})
            """)
        files = {"tests/test_{}.py".format(name): template.format(mark=mark, name="test_" + name,
                                                                    passes=name != "b")
                 for name in ("a", "b", "c")}
        repo = self.git_repo(files)
        shards = lane.verify_shards(repo, count=3)
        self.assertEqual(sorted(sum(shards, [])), ["tests.test_a", "tests.test_b", "tests.test_c"])
        script = lane.verify_shard_script("run-1", shards)
        runner = 'RUN="python3 -m unittest"'
        self.assertEqual(script.count(runner), 1)
        script = script.replace(runner, 'RUN="{} -m unittest"'.format(sys.executable))
        script_path = os.path.join(work, "verify.sh")
        with open(script_path, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(script)
        logs = os.path.join(work, "logs")
        os.makedirs(logs)
        result = subprocess.run(["sh", script_path], cwd=repo, env=dict(os.environ, TMPDIR=logs),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
        output = result.stdout.decode("utf-8", "replace")
        self.assertEqual(result.returncode, 0, output + result.stderr.decode("utf-8", "replace"))
        reports = re.findall(r"^shard \d+ rc=(\S+) files: (\S+)$", output, re.M)
        self.assertEqual(dict((module, rc) for rc, module in reports),
                         {"tests.test_a": "0", "tests.test_b": "1", "tests.test_c": "0"}, output)
        with open(mark, encoding="utf-8") as stream:
            ran = stream.read().split()
        self.assertEqual(sorted(ran), ["test_a", "test_b", "test_c"])

    def test_mode_setting_takes_env_then_file_then_catalog(self):
        lane = self.lane_module()
        explore = {"mode": "saving"}
        with mock.patch.dict(os.environ, {"LANES_CONFIG": self.config}):
            os.environ.pop("USAGE_OPTIMIZER_MODE", None)
            self.assertEqual(lane.mode_setting(None), "default")
            self.assertEqual(lane.mode_setting(explore), "saving")
            self.write(os.path.join(self.config, "mode"), "auto\n")
            self.assertEqual(lane.mode_setting(explore), "auto")
            os.environ["USAGE_OPTIMIZER_MODE"] = "utilization"
            self.assertEqual(lane.mode_setting(explore), "utilization")
            os.environ["USAGE_OPTIMIZER_MODE"] = "turbo"
            with mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
                self.assertEqual(lane.mode_setting(explore), "default")
            self.assertTrue(stderr.getvalue().startswith("warning: usage mode 'turbo'"), stderr.getvalue())
            self.assertEqual(stderr.getvalue().count("\n"), 1)
        with open(os.path.join(ROOT, "arms.json"), "r", encoding="utf-8") as stream:
            self.assertEqual(json.load(stream)["explore"]["mode"], "auto")

    def test_auto_mode_reads_the_weekly_window_of_the_meter_reading(self):
        lane = self.lane_module()
        explore = {"modes": {"saving_pct": 110, "utilization_pct": 90}}
        reset = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=3.5)).isoformat()
        # Half the week gone: used x 2 is the projection.
        for used, expected in ((55.5, "saving"), (50, "default"), (44.5, "utilization")):
            snapshot = {"windows": [{"label": "5h", "used_percent": 99, "resets_at": reset},
                                    {"label": "weekly", "used_percent": used, "resets_at": reset}]}
            self.assertEqual(lane.run_mode("auto", snapshot, explore), expected)
            self.assertEqual(lane.run_mode("saving", snapshot, explore), "saving")
        self.assertEqual(lane.run_mode("auto", None, explore), "default")
        for projected, expected in ((111, "saving"), (100, "default"), (89, "utilization")):
            self.assertEqual(lane.projected_mode(projected, explore), expected)

    def test_claude_cloud_mode_is_printed_and_recorded_in_meta_and_ledger(self):
        result = self.run_lane(extra=["--cloud", "--outdir", self.outdir],
                               env={"FAKE_CLAUDE_MODE": "noop", "USAGE_OPTIMIZER_MODE": "saving"})
        self.assertEqual(result.returncode, 3, result.stderr + result.stdout)
        self.assertIn("lane: mode saving (setting saving)", result.stderr)
        meta = self.read_json(os.path.join(self.outdir, "meta.json"))
        self.assertEqual(meta["mode"], "saving")
        self.assertIn("make the edits yourself", self.cloud_prompt(meta))
        with open(os.path.join(self.state, "ledger.jsonl"), "r", encoding="utf-8") as stream:
            ledger = [json.loads(line) for line in stream]
        self.assertEqual(ledger[0]["mode"], "saving")

    def test_claude_cloud_auto_without_a_reading_is_default(self):
        result = self.run_lane(extra=["--cloud", "--outdir", self.outdir],
                               env={"FAKE_CLAUDE_MODE": "noop", "USAGE_OPTIMIZER_MODE": "auto"})
        self.assertEqual(result.returncode, 3, result.stderr + result.stdout)
        self.assertIn("lane: mode default (auto)", result.stderr)
        meta = self.read_json(os.path.join(self.outdir, "meta.json"))
        self.assertEqual(meta["mode"], "default")
        self.assertIn("for as much of the work as splits off", self.cloud_prompt(meta))

    def test_claude_cloud_subagents_count_is_saved_in_meta_and_ledger(self):
        result = self.run_lane(extra=["--cloud", "--outdir", self.outdir], env={"FAKE_CLAUDE_MODE": "subagents"})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("verdict=OK", result.stdout)
        meta = self.read_json(os.path.join(self.outdir, "meta.json"))
        self.assertEqual(meta["cloud"]["subagents"], 3)
        self.assertEqual(meta["cloud"]["report"], os.path.join(self.outdir, "report.md"))
        with open(os.path.join(self.state, "ledger.jsonl"), "r", encoding="utf-8") as stream:
            ledger = [json.loads(line) for line in stream]
        self.assertEqual(ledger[0]["subagents"], 3)

    def test_claude_cloud_report_without_subagents_line_has_no_subagents_key(self):
        result = self.run_lane(extra=["--cloud", "--outdir", self.outdir], env={"FAKE_CLAUDE_MODE": "report"})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        meta = self.read_json(os.path.join(self.outdir, "meta.json"))
        self.assertIn("report", meta["cloud"])
        self.assertNotIn("subagents", meta["cloud"])
        with open(os.path.join(self.state, "ledger.jsonl"), "r", encoding="utf-8") as stream:
            ledger = [json.loads(line) for line in stream]
        self.assertNotIn("subagents", ledger[0])

    def test_claude_cloud_partial(self):
        result = self.run_lane(extra=["--cloud", "--outdir", self.outdir], env={"FAKE_CLAUDE_MODE": "partial"})
        self.assertEqual(result.returncode, 6, result.stderr + result.stdout)
        self.assertIn("verdict=PARTIAL", result.stdout)
        self.assertTrue(os.path.isfile(os.path.join(self.workspace, "cloud-result.txt")))

    def run_verify(self, mode):
        return self.run_lane(extra=["--cloud", "--verify", "--outdir", self.outdir],
                             env={"FAKE_CLAUDE_MODE": mode})

    def test_claude_cloud_verify_returns_report_and_changes_nothing(self):
        result = self.run_verify("verify")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("verdict=OK", result.stdout)
        report_path = os.path.join(self.outdir, "report.md")
        with open(report_path, "r", encoding="utf-8") as stream:
            self.assertEqual(stream.read(), "Fake report line\n# Kept heading\n")
        # The report follows the saved line on stdout, so the caller's log holds it.
        self.assertIn("lane: cloud report saved to " + report_path + "\nFake report line\n# Kept heading\n",
                      result.stdout)
        self.assertNotIn("pass --class", result.stderr)
        self.assertEqual(self.git("-C", self.workspace, "status", "--porcelain").stdout, b"")
        self.assertEqual(self.git("-C", self.workspace, "rev-parse", "HEAD").stdout.decode().strip(), self.base_sha)
        self.assertEqual(self.remote_refs(), {})
        meta = self.read_json(os.path.join(self.outdir, "meta.json"))
        self.assertIs(meta["verify"], True)
        self.assertEqual(meta["tag"], "verify")
        self.assertEqual(meta["verdict"], "OK")
        prompt = meta["cmd"][meta["cmd"].index("--cloud") + 1]
        self.assertIn("Run each command the brief lists, from the repository root", prompt)
        self.assertNotIn("Do the task.", prompt)
        self.assertIn('git commit --allow-empty -m "lane: start ', prompt)
        self.assertIn("git commit --allow-empty -F <that file> && git push origin HEAD", prompt)
        with open(os.path.join(self.state, "ledger.jsonl"), "r", encoding="utf-8") as stream:
            ledger = [json.loads(line) for line in stream]
        self.assertIs(ledger[0]["verify"], True)

    def test_claude_cloud_verify_keeps_tag(self):
        result = self.run_lane(extra=["--cloud", "--verify", "--tag", "suite", "--outdir", self.outdir],
                               env={"FAKE_CLAUDE_MODE": "verify"})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(self.read_json(os.path.join(self.outdir, "meta.json"))["tag"], "suite")

    def test_claude_cloud_verify_partial_marker(self):
        result = self.run_verify("verify-partial")
        self.assertEqual(result.returncode, 6, result.stderr + result.stdout)
        self.assertIn("verdict=PARTIAL", result.stdout)
        self.assertIn("Fake report line", result.stdout)
        self.assertEqual(self.git("-C", self.workspace, "status", "--porcelain").stdout, b"")

    def test_claude_cloud_verify_change_is_kept_not_applied(self):
        result = self.run_verify("verify-change")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("verdict=OK", result.stdout)
        self.assertIn("warning: verify run changed files; cloud.diff kept, not applied", result.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.workspace, "cloud-result.txt")))
        self.assertEqual(self.git("-C", self.workspace, "status", "--porcelain").stdout, b"")
        with open(os.path.join(self.outdir, "cloud.diff"), "r", encoding="utf-8") as stream:
            self.assertIn("returned from cloud", stream.read())

    def test_verify_requires_cloud_and_claude_lane(self):
        result = self.run_lane(extra=["--verify", "--dry-run"])
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("--verify needs --cloud", result.stderr)
        result = self.run_lane(lane="luna", effort="medium", extra=["--cloud", "--verify", "--dry-run"])
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("haiku, sonnet, or opus", result.stderr)
        result = self.run_lane(lane="codex-cloud", effort=None, extra=["--verify", "--dry-run"])
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("--verify needs --cloud", result.stderr)
        self.assertEqual(self.remote_refs(), {})

    def test_claude_missing_start_marker_fails_and_cleans_up(self):
        result = self.run_lane(extra=["--cloud", "--outdir", self.outdir], env={"FAKE_CLAUDE_MODE": "no-start"})
        self.assertEqual(result.returncode, 4, result.stderr + result.stdout)
        self.assertIn("GitHub App may be missing", result.stderr)
        self.assertIn("session_Fake123", result.stderr)
        self.assertEqual(self.remote_refs(), {})
        self.assertIn("the session may still be running; stop or archive it in the Claude app: "
                      "https://claude.ai/code/session_Fake123", result.stderr)
        cloud = self.read_json(os.path.join(self.outdir, "meta.json"))["cloud"]
        self.assertIs(cloud["left_running"], True)
        self.assertEqual(cloud["session_id"], "session_Fake123")
        self.assertIn("https://claude.ai/code/session_Fake123", cloud["url"])

    def test_cloud_preflight_rejects_dirty_tree(self):
        self.write(os.path.join(self.workspace, "untracked.txt"), "dirty\n")
        result = self.run_lane(extra=["--cloud", "--dry-run"])
        self.assertEqual(result.returncode, 8)
        self.assertIn("clean work tree", result.stderr)
        self.assertEqual(self.remote_refs(), {})

    def test_cloud_preflight_accepts_subdirectory_and_checks_whole_tree(self):
        subdir = os.path.join(self.workspace, "nested")
        os.makedirs(subdir)
        result = self.run_lane(extra=["--cloud", "--dry-run"], dir_path=subdir)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.write(os.path.join(self.workspace, "outside-subdir.txt"), "dirty\n")
        result = self.run_lane(extra=["--cloud", "--dry-run"], dir_path=subdir)
        self.assertEqual(result.returncode, 8)
        self.assertIn("clean work tree", result.stderr)
        self.assertEqual(self.remote_refs(), {})

    def test_claude_requires_github_without_override(self):
        result = self.run_lane(extra=["--cloud", "--dry-run"], env={"LANES_CLOUD_ANY_REMOTE": ""})
        self.assertEqual(result.returncode, 8)
        self.assertIn("Claude cloud runs need the repository on GitHub with the Claude GitHub App installed", result.stderr)

    def test_cloud_switch_rejected_on_non_claude_lane(self):
        result = self.run_lane("luna", extra=["--cloud", "--dry-run"], effort="medium")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--cloud is only available", result.stderr)

    def test_codex_cloud_ok(self):
        result = self.run_lane("codex-cloud", extra=["--outdir", self.outdir], effort=None,
                               env={"LANES_CODEX_CLOUD_ENV": "test-env"})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("verdict=OK", result.stdout)
        with open(os.path.join(self.workspace, "codex-result.txt"), "r", encoding="utf-8") as stream:
            self.assertEqual(stream.read(), "returned from Codex Cloud\n")
        self.assertTrue(self.git("-C", self.workspace, "status", "--porcelain").stdout)
        self.assertEqual(self.remote_refs(), {})
        meta = self.read_json(os.path.join(self.outdir, "meta.json"))
        self.assertEqual(meta["place"], "cloud")
        self.assertEqual(meta["effort"], "default")
        self.assertEqual(meta["cloud"]["kind"], "codex")
        self.assertEqual(meta["cloud"]["task_id"], "fake-task-123")
        self.assertEqual(meta["cloud"]["url"], "https://chatgpt.com/codex/tasks/fake-task-123")
        self.assertEqual(meta["cloud"]["env"], "test-env")
        self.assertEqual(meta["cloud"]["branch"], "main")
        self.assertEqual(meta["cloud"]["base"], meta["cloud"]["result_sha"])
        with open(os.path.join(self.root, "codex-prompt.txt"), "r", encoding="utf-8") as stream:
            self.assertIn("Create a small cloud result file.", stream.read())

    def test_codex_cloud_title_with_error_word_is_not_a_failure(self):
        result = self.run_lane("codex-cloud", extra=["--outdir", self.outdir], effort=None,
                               env={"LANES_CODEX_CLOUD_ENV": "test-env",
                                    "FAKE_CODEX_RUNNING": "[RUNNING] Fix error handling in the parser"})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("verdict=OK", result.stdout)

    def test_codex_cloud_failed_status_tag_fails(self):
        result = self.run_lane("codex-cloud", extra=["--outdir", self.outdir], effort=None,
                               env={"LANES_CODEX_CLOUD_ENV": "test-env",
                                    "FAKE_CODEX_RUNNING": "[FAILED] Fix error handling in the parser"})
        self.assertEqual(result.returncode, 4, result.stderr + result.stdout)
        self.assertIn("Codex Cloud task failed", result.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.workspace, "codex-result.txt")))

    def test_codex_cloud_error_log_is_moved_out_of_the_workspace(self):
        result = self.run_lane("codex-cloud", extra=["--outdir", self.outdir], effort=None,
                               env={"LANES_CODEX_CLOUD_ENV": "test-env", "FAKE_CODEX_ERROR_LOG": "1"})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.workspace, "error.log")))
        moved = os.path.join(self.outdir, "codex-error.log")
        with open(moved, "r", encoding="utf-8") as stream:
            self.assertEqual(stream.read(), "ChatGPT account id: fake\n")
        self.assertIn("warning: codex cloud wrote error.log in the workspace (it holds the ChatGPT account id); "
                      "moved to " + moved, result.stderr)
        meta = self.read_json(os.path.join(self.outdir, "meta.json"))
        self.assertIs(meta["cloud"]["error_log_moved"], True)

    def test_codex_cloud_status_and_diff_run_in_the_run_directory(self):
        result = self.run_lane("codex-cloud", extra=["--outdir", self.outdir], effort=None,
                               env={"LANES_CODEX_CLOUD_ENV": "test-env"})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        with open(os.path.join(self.root, "codex-cwds.txt"), "r", encoding="utf-8") as stream:
            calls = [line.split(" ", 1) for line in stream.read().splitlines()]
        self.assertEqual([call[0] for call in calls], ["status", "status", "diff"])
        for _, cwd in calls:
            self.assertEqual(os.path.realpath(cwd), os.path.realpath(self.outdir))

    def test_codex_cloud_preexisting_error_log_is_left_alone(self):
        os.makedirs(os.path.join(self.workspace, ".git", "info"), exist_ok=True)
        with open(os.path.join(self.workspace, ".git", "info", "exclude"), "a", encoding="utf-8") as stream:
            stream.write("error.log\n")
        self.write(os.path.join(self.workspace, "error.log"), "user notes\n")
        result = self.run_lane("codex-cloud", extra=["--outdir", self.outdir], effort=None,
                               env={"LANES_CODEX_CLOUD_ENV": "test-env"})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        with open(os.path.join(self.workspace, "error.log"), "r", encoding="utf-8") as stream:
            self.assertEqual(stream.read(), "user notes\n")
        self.assertFalse(os.path.exists(os.path.join(self.outdir, "codex-error.log")))
        self.assertNotIn("warning: codex cloud wrote error.log", result.stderr)
        meta = self.read_json(os.path.join(self.outdir, "meta.json"))
        self.assertNotIn("error_log_moved", meta["cloud"])

    def test_claude_cloud_started_elsewhere_returns_only_its_own_work(self):
        self.write(os.path.join(self.workspace, "branch-only.txt"), "kept\n")
        self.git("-C", self.workspace, "add", "branch-only.txt")
        self.git("-C", self.workspace, "-c", "user.name=Lane Test", "-c", "user.email=lane-test@localhost",
                 "commit", "-m", "branch work")
        result = self.run_lane(extra=["--cloud", "--outdir", self.outdir], env={"FAKE_BRANCH": "main~1"})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("not the pushed base", result.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.workspace, "branch-only.txt")))
        self.assertTrue(os.path.isfile(os.path.join(self.workspace, "cloud-result.txt")))
        meta = self.read_json(os.path.join(self.outdir, "meta.json"))
        self.assertEqual(meta["cloud"]["started_from"], self.base_sha)
        self.assertNotEqual(meta["cloud"]["base"], self.base_sha)

    def test_codex_cloud_refuses_missing_environment(self):
        result = self.run_lane("codex-cloud", extra=["--dry-run"], effort=None)
        self.assertEqual(result.returncode, 8)
        self.assertIn("create a Codex environment at chatgpt.com/codex", result.stderr)
        self.assertEqual(self.remote_refs(), {})

    def test_cloud_dry_run_prints_plan_without_pushing(self):
        result = self.run_lane(extra=["--cloud", "--dry-run"])
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        for label in ("cloud preflight: PASS", "push:", "launch:", "poll:", "apply:",
                      "dry-run: no push or cloud launch performed"):
            self.assertIn(label, result.stdout)
        self.assertEqual(self.remote_refs(), {})
        self.assertFalse(os.path.exists(os.path.join(self.root, "run output")))

    def lane_module(self):
        loader = importlib.machinery.SourceFileLoader("lane_cloud_tested", SCRIPT)
        module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(module)
        return module

    def base_plan(self, **changes):
        plan = {"remote_url": self.origin, "branch": "main", "base": self.base_sha, "remote_existed": False}
        plan.update(changes)
        return plan

    def test_runs_sharing_a_base_branch_keep_it_until_the_last_one_ends(self):
        lane = self.lane_module()
        with mock.patch.dict(os.environ, {"LANES_STATE": self.state}):
            lane.cloud_push_branch(self.workspace, self.base_plan(), None, "run-a")
            lane.cloud_push_branch(self.workspace, self.base_plan(remote_existed=True), None, "run-b")
            self.assertIn("refs/heads/main", self.remote_refs())
            self.assertFalse(lane.cloud_release_base(self.workspace, self.base_plan(base_pushed=True), "run-a"))
            self.assertTrue(lane.cloud_release_base(
                self.workspace, self.base_plan(remote_existed=True, base_pushed=True), "run-b"))

    def test_base_branch_that_was_on_origin_first_is_never_deleted(self):
        lane = self.lane_module()
        self.git("-C", self.workspace, "push", "origin", "HEAD:refs/heads/main")
        plan = self.base_plan(remote_existed=True)
        with mock.patch.dict(os.environ, {"LANES_STATE": self.state}):
            lane.cloud_push_branch(self.workspace, plan, None, "run-a")
            self.assertFalse(lane.cloud_release_base(self.workspace, dict(plan, base_pushed=True), "run-a"))

    def test_failed_push_counts_when_origin_has_the_commit_and_else_names_gits_reason(self):
        lane = self.lane_module()
        self.git("-C", self.workspace, "push", "origin", "HEAD:refs/heads/main")
        real = lane.cloud_git

        def locked(path, args, timeout=30):
            if args and args[0] == "push":
                return subprocess.CompletedProcess(args, 1, b"", b"error: cannot lock ref 'refs/heads/main'\n")
            return real(path, args, timeout)

        with mock.patch.dict(os.environ, {"LANES_STATE": self.state}), \
                mock.patch.object(lane, "cloud_git", locked), mock.patch.object(lane.time, "sleep"):
            lane.cloud_push_branch(self.workspace, self.base_plan(remote_existed=True), None, "run-a")
            with self.assertRaises(lane.LaneError) as caught:
                lane.cloud_push_branch(self.workspace, self.base_plan(base="0" * 40), None, "run-b")
        self.assertIn("cannot lock ref", str(caught.exception))

    def test_done_marker_and_result_commit_come_from_the_same_read(self):
        lane = self.lane_module()
        self.git("-C", self.workspace, "-c", "user.name=Lane Test", "-c", "user.email=lane-test@localhost",
                 "commit", "--allow-empty", "-m", "lane: done run-x")
        done = self.git("-C", self.workspace, "rev-parse", "HEAD").stdout.decode("ascii").strip()
        self.git("-C", self.workspace, "update-ref", "refs/lane-cloud/run-x/main", done)
        self.assertEqual(lane.cloud_ref_head(self.workspace, "refs/lane-cloud/run-x/main"), (done, "lane: done run-x"))
        self.assertIsNone(lane.cloud_ref_head(self.workspace, "refs/lane-cloud/run-x/missing"))

    def test_claude_app_check_refuses_only_when_github_lists_apps_without_claude(self):
        lane = self.lane_module()

        def listing(code, apps):
            return mock.patch.object(lane, "cloud_process",
                                     return_value=subprocess.CompletedProcess([], code, apps, b""))

        with mock.patch.object(lane.shutil, "which", return_value="gh"), \
                mock.patch.dict(os.environ, {"LANES_CLOUD_SKIP_APP_CHECK": ""}):
            with listing(0, b"cursor\n"):
                self.assertTrue(lane.claude_app_missing("https://github.com/some-org/repo.git"))
            with listing(0, b"cursor\nclaude\n"):
                self.assertFalse(lane.claude_app_missing("https://github.com/some-org/repo.git"))
            with listing(1, b""):
                self.assertFalse(lane.claude_app_missing("https://github.com/some-user/repo.git"))
            self.assertFalse(lane.claude_app_missing(self.origin))

    def test_claude_app_check_prints_one_note_when_it_cannot_know(self):
        """Each path that passes without knowing prints one note with its reason; a found app prints nothing."""
        lane = self.lane_module()
        url = "https://github.com/some-org/repo.git"
        note = ("note: the Claude GitHub App on some-org is unknown ({}); "
                "check https://github.com/apps/claude/installations/select_target")

        def check(patches, remote=url):
            with contextlib.ExitStack() as stack:
                for patch in patches:
                    stack.enter_context(patch)
                with contextlib.redirect_stderr(io.StringIO()) as err:
                    result = lane.claude_app_missing(remote)
            return result, err.getvalue()

        def gh(code=0, out=b""):
            return [mock.patch.object(lane.shutil, "which", return_value="gh"),
                    mock.patch.dict(os.environ, {"LANES_CLOUD_SKIP_APP_CHECK": ""}),
                    mock.patch.object(lane, "cloud_process",
                                      return_value=subprocess.CompletedProcess([], code, out, b""))]

        cases = (
            ([mock.patch.object(lane.shutil, "which", return_value=None),
              mock.patch.dict(os.environ, {"LANES_CLOUD_SKIP_APP_CHECK": ""})], "gh is not on PATH"),
            ([mock.patch.object(lane.shutil, "which", return_value="gh"),
              mock.patch.dict(os.environ, {"LANES_CLOUD_SKIP_APP_CHECK": "1"})], "LANES_CLOUD_SKIP_APP_CHECK=1"),
            (gh(code=1), "gh api exit 1: a user-owned repository, or an account that cannot list the owner's apps"),
            ([mock.patch.object(lane.shutil, "which", return_value="gh"),
              mock.patch.dict(os.environ, {"LANES_CLOUD_SKIP_APP_CHECK": ""}),
              mock.patch.object(lane, "cloud_process", side_effect=lane.LaneError("boom", 4))],
             "the API call failed"),
        )
        for patches, reason in cases:
            with self.subTest(reason=reason):
                result, stderr = check(patches)
                self.assertFalse(result)
                self.assertEqual(stderr, note.format(reason) + "\n")

        self.assertEqual(check(gh(out=b"cursor\nclaude\n")), (False, ""))
        self.assertEqual(check(gh(out=b"cursor\n")), (True, ""))
        self.assertEqual(check(gh(), remote=self.origin), (False, ""))

    def test_codex_environment_is_looked_up_per_github_repository(self):
        lane = self.lane_module()
        os.makedirs(self.config, exist_ok=True)
        self.write(os.path.join(self.config, "cloud.json"),
                   '{"codex_env": "single", "codex_envs": {"Owner/Repo": "env-repo"}}\n')
        with mock.patch.dict(os.environ, {"LANES_CONFIG": self.config}):
            os.environ.pop("LANES_CODEX_CLOUD_ENV", None)
            self.assertEqual(lane.codex_cloud_env("https://github.com/owner/repo.git"), "env-repo")
            self.assertEqual(lane.codex_cloud_env("git@github.com:owner/repo.git"), "env-repo")
            # Without an entry a GitHub remote passes its own name, as written, for Codex to resolve.
            self.assertEqual(lane.codex_cloud_env("https://github.com/Owner/Other.git"), "Owner/Other")
            self.assertEqual(lane.codex_cloud_env(self.origin), "single")
            self.write(os.path.join(self.config, "cloud.json"), '{"codex_envs": {}}\n')
            with self.assertRaises(lane.LaneError) as caught:
                lane.codex_cloud_env(self.origin)
            self.assertIn("not on GitHub", str(caught.exception))
            self.assertIn("chatgpt.com/codex/settings/environments", str(caught.exception))

    def test_codex_cloud_missing_environment_names_codex_reason_and_where_to_create_it(self):
        result = self.run_lane("codex-cloud", extra=["--outdir", self.outdir], effort=None,
                               env={"LANES_CODEX_CLOUD_ENV": "owner/none", "FAKE_CODEX_MISSING_ENV": "owner/none"})
        self.assertEqual(result.returncode, 4, result.stderr + result.stdout)
        self.assertIn("environment 'owner/none' not found", result.stderr)
        self.assertIn("chatgpt.com/codex/settings/environments", result.stderr)
        with open(os.path.join(self.outdir, "meta.json"), "r", encoding="utf-8") as stream:
            self.assertIn("not found", json.load(stream)["error"])

    def test_codex_cloud_can_read_environment_from_config(self):
        os.makedirs(self.config, exist_ok=True)
        self.write(os.path.join(self.config, "cloud.json"), '{"codex_env":"saved-label"}\n')
        result = self.run_lane("codex-cloud", extra=["--dry-run"], effort=None)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("saved-label", result.stdout)
        self.assertEqual(self.remote_refs(), {})


if __name__ == "__main__":
    unittest.main()
