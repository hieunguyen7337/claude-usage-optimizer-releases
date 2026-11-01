"""Black-box tests of `bin/lane main` (mirror cloud sessions), the side refusal and MAIN_BLOCK.

The CLI tests run bin/lane (a copy of it inside a temp kit, so POLICY.md and the sibling lane-stats are fixtures) as a
subprocess with a fake `claude`, a fake lane-term runner, a fake git script on the lane bin folder and a bare local
origin, like tests/test_lane_cloud.py. Nothing touches the network or the real ~/.local/state/lanes.
"""

import contextlib
import importlib.machinery
import importlib.util
import io
import itertools
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
import uuid
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "bin", "lane")
POLICY = os.path.join(ROOT, "POLICY.md")
AGENTS = os.path.join(ROOT, "agents")

KEY = "local/demo-proj"
HOOK_MARK = ".claude/hooks/cloud-notify.py"
MAIN_ID = "20261031-100000-main"
RELEASE = "2099-01-02.3"
IDENT = ["-c", "user.name=Lane Test", "-c", "user.email=lane-test@localhost"]
BRIEF_TEXT = "Build the frobnicator module for the demo project.\nKeep the public API small.\n"
WORKER_SENTENCE = ("Your session is a worker. The kit's policy and tools are held by this project's main session "
                   "(local, or a cloud mirror started by lane main), not by you.")
# The mirror's START step that installs the kit from the project repository (a VM cannot fetch the kit repository).
# The exit is echoed because a pipe to tail would hide a failed install behind tail's own exit 0.
KIT_INSTALL_LINE = ("(git fetch origin lane-main/kit && rm -rf /tmp/uo-kit && mkdir -p /tmp/uo-kit && "
                    "git archive FETCH_HEAD | tar -x -C /tmp/uo-kit && bash /tmp/uo-kit/install.sh --no-view) "
                    "> /tmp/uo-kit.log 2>&1; echo \"kit install exit $?\"; tail -n 5 /tmp/uo-kit.log")

# The marker grammar the main session must be given, one line each (spec section 2 and 3).
MARKER_LINES = (
    "orch: STATUS <n>: <title>",
    "orch: READY <n>: <title>",
    "orch: LOCAL lane <unit> <lane>/<effort> <brief path>",
    "orch: REVIEW <unit> <outcome> arm=<lane>/<effort> class=<class> min=<minutes> tok=<in>/<out> usd=<list usd>",
)

SYNTHETIC_POLICY = """# Claude Usage Optimizer: usage policy

Claude Usage Optimizer version: 2099-01-02.3. Installed at `~/.claude/usage-optimizer/`.

## Principle

PRINCIPLE_SENTINEL stays out of the main prompt. It may hold text the command line cannot carry: → §

## Main cloud sessions (from 2099-01-02.3)

MAIN_SENTINEL: you are the mirror of one project.

- **Review every diff.** Rule one of the section.
- **Report.** Rule two of the section.

## Measure every task

MEASURE_SENTINEL stays out of the main prompt.

## Briefs

BRIEFS_SENTINEL: every brief has four parts.
1. The goal.
2. The files.

## Meters

METERS_SENTINEL stays out of the main prompt.
"""

FAKE_RUNNER = r'''
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
'''

# One fake claude for both kinds of session. A prompt with "CLOUD RUN <id>." is a worker; any other prompt is a
# main session. FAKE_CLAUDE_MODE: ok (default), noop (worker without a change), no-start (nothing is pushed).
FAKE_CLAUDE = r'''
import json
import os
import re
import subprocess
import sys

args = sys.argv[1:]
prompt = args[args.index("--cloud") + 1]
mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
record = os.environ.get("FAKE_CLAUDE_RECORD")
if record:
    with open(record, "w", encoding="utf-8") as stream:
        json.dump({"argv": args, "prompt": prompt}, stream)
branch = os.environ.get("FAKE_SESSION_BRANCH", "claude/test")
session = os.environ.get("FAKE_SESSION", "session_Fake123")
worker = re.search(r"CLOUD RUN (.+?)\.", prompt)
main = re.search(r"main id (\d{8}-\d{6}-main)", prompt)
if mode != "no-start":
    helper = os.path.join(os.environ["FAKE_TMP"], "fake-claude-" + str(os.getpid()))
    try:
        subprocess.run(["git", "-C", os.environ["FAKE_WORKSPACE"], "worktree", "add", "-b",
                        branch, helper, os.environ["FAKE_BRANCH"]],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=True)

        def git(*parts):
            subprocess.run(["git", "-C", helper, "-c", "user.name=Cloud Fake",
                            "-c", "user.email=cloud-fake@localhost"] + list(parts),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=True)

        def push(*parts):
            pushed = subprocess.run([sys.executable, os.environ["FAKE_GIT_SCRIPT"], "-C", helper, "push"]
                                    + list(parts), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    timeout=10, check=False)
            if pushed.returncode:
                raise RuntimeError(pushed.stderr.decode("utf-8", "replace"))

        git("remote", "set-url", "origin", os.environ["FAKE_ORIGIN"])
        if worker:
            run_id = worker.group(1)
            git("commit", "--allow-empty", "-m", "lane: start " + run_id)
            push("-u", "origin", "HEAD")
            if mode == "ok":
                with open(os.path.join(helper, "cloud-result.txt"), "w", encoding="utf-8") as stream:
                    stream.write("returned from cloud\n")
                git("add", "cloud-result.txt")
                git("commit", "-m", "cloud task result")
            git("commit", "--allow-empty", "-m", "lane: done " + run_id)
            push("origin", "HEAD")
        elif main:
            git("commit", "--allow-empty", "-m", "orch: START " + main.group(1))
            push("-u", "origin", "HEAD")
    finally:
        subprocess.run(["git", "-C", os.environ["FAKE_WORKSPACE"], "worktree", "remove",
                        "--force", helper], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       timeout=10, check=False)
        subprocess.run(["git", "-C", os.environ["FAKE_WORKSPACE"], "branch", "-D", branch],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=False)
print("Created cloud session: fake title")
print("View: https://claude.ai/code/" + session + "?from=cli&m=0")
print("Resume with: claude --teleport " + session)
'''

# lane-stats stand-in for `main-picks`: prints (and, with --out, writes) a small valid picks.json.
FAKE_STATS = r'''#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
log = os.environ.get("FAKE_STATS_LOG")
if log:
    with open(log, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(args) + "\n")
if os.environ.get("FAKE_STATS_FAIL") == "1":
    sys.stderr.write("fake lane-stats: failing on purpose\n")
    sys.exit(1)
if args[:1] != ["main-picks"]:
    sys.stderr.write("fake lane-stats: unexpected command\n")
    sys.exit(2)
picks = {"version": 1, "at": os.environ.get("FAKE_STATS_AT", "2026-10-31T00:00:00Z"), "kit": None, "repo": None,
         "plans": {"claude": "max_20x", "codex": "none", "gemini": "none"},
         "modes": {"claude": "utilization", "codex": "default", "gemini": "default"},
         "classes": {"substantive": {"status": "exploring", "arms": [
             {"arm": "sonnet/claude-sonnet-5-5/high", "lane": "sonnet", "where": "subagent", "reviewed": 14,
              "outcomes": {"accepted": 9, "fixed": 3, "rework": 1, "rejected": 1}, "usable": 0.857,
              "points": 1.9, "minutes": 8.2, "p_pick": 1.0, "forced": False}]}}}
text = json.dumps(picks, indent=1) + "\n"
if "--out" in args:
    with open(args[args.index("--out") + 1], "w", encoding="utf-8") as stream:
        stream.write(text)
sys.stdout.write(text)
'''

# The git stand-in of tests/test_lane_cloud.py: ls-remote, push and fetch work against FAKE_ORIGIN by copying objects.
FAKE_GIT = r'''
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
        sha, ref = line.split("\t", 1)
        if fnmatch.fnmatchcase(ref, pattern):
            print(sha + "\t" + ref)
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
    emit(subprocess.run([native, "--git-dir", origin, "update-ref", destination, target_sha],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20, check=False))
if args and args[0] == "fetch":
    refspec = args[-1].lstrip("+")
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
'''


def force_rmtree(path):
    def retry(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=retry)
    else:
        shutil.rmtree(path, onerror=retry)


def load_lane():
    loader = importlib.machinery.SourceFileLoader("lane_main_tested", SCRIPT)
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


def policy_release(text):
    found = re.search(r"^Claude Usage Optimizer version: (\S+?)\.(?:\s|$)", text, re.MULTILINE)
    return found.group(1) if found else None


class LaneMainTests(unittest.TestCase):
    def setUp(self):
        self.root = os.path.join(os.path.dirname(__file__), ".lane-main-{}-{}".format(os.getpid(), uuid.uuid4().hex))
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
        self.origin = os.path.join(self.root, "demo-proj.git")
        self.state = os.path.join(self.root, "state")
        self.config = os.path.join(self.root, "config")
        self.kit = os.path.join(self.root, "kit")
        self.cloud = os.path.join(self.root, "cloud")
        self.brief = os.path.join(self.root, "brief.md")
        self.runner = os.path.join(self.root, "lane-term-fake.py")
        self.record = os.path.join(self.root, "claude-record.json")
        self.lane = os.path.join(self.kit, "bin", "lane")
        os.makedirs(self.bin)
        os.makedirs(self.workspace)
        os.makedirs(os.path.join(self.config, "bin"))
        self.write(self.brief, BRIEF_TEXT)
        self.write(self.runner, FAKE_RUNNER)
        self.install_cli("claude", FAKE_CLAUDE)
        self.install_git_stand_in()
        self.install_kit(SYNTHETIC_POLICY)
        self.git("init", "--bare", self.origin)
        self.git("init", self.workspace)
        self.git("-C", self.workspace, "branch", "-M", "main")
        self.write(os.path.join(self.workspace, "base.txt"), "base\n")
        self.git("-C", self.workspace, "add", "base.txt")
        self.git("-C", self.workspace, *IDENT, "commit", "-m", "base")
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
            "LANES_CLOUD_SKIP_APP_CHECK": "1",
            "LANES_CLOUD_POLL": "0.05",
            "LANES_CLOUD_START_TIMEOUT": "3",
            "LANES_TERM": self.runner,
            "GIT_AUTHOR_NAME": "Lane Test",
            "GIT_AUTHOR_EMAIL": "lane-test@localhost",
            "GIT_COMMITTER_NAME": "Lane Test",
            "GIT_COMMITTER_EMAIL": "lane-test@localhost",
            "FAKE_ORIGIN": self.origin,
            "FAKE_WORKSPACE": self.workspace,
            "FAKE_BRANCH": "main",
            "FAKE_TMP": self.root,
            "FAKE_CLAUDE_RECORD": self.record,
            "FAKE_GIT_SCRIPT": os.path.join(self.config, "fake_git.py"),
            "FAKE_REAL_GIT": shutil.which("git"),
            "PATH": self.bin + os.pathsep + os.environ.get("PATH", ""),
        })
        for name in ("USAGE_OPTIMIZER_MODE", "LANES_CLOUD_KEEP", "LANES_CLOUD_PERMISSION_MODE", "LANE_STATS",
                     "USAGE_OPTIMIZER_PLAN_CODEX", "USAGE_OPTIMIZER_PLAN_GEMINI"):
            self.env.pop(name, None)
        self.assert_stand_ins_win()

    # ----- harness -----

    def write(self, path, text):
        with open(path, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text.lstrip("\n") if text.startswith("\n") else text)

    def read(self, path):
        with open(path, "r", encoding="utf-8") as stream:
            return stream.read()

    def read_json(self, path):
        with open(path, "r", encoding="utf-8") as stream:
            return json.load(stream)

    def git(self, *args):
        return subprocess.run(["git"] + list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=20, check=True)

    def git_text(self, *args):
        return self.git(*args).stdout.decode("utf-8").strip()

    def install_cli(self, name, body):
        script = os.path.join(self.bin, "fake_{}.py".format(name))
        self.write(script, body)
        self.write_launcher(self.bin, name, script)

    def install_git_stand_in(self):
        script = os.path.join(self.config, "fake_git.py")
        self.write(script, FAKE_GIT)
        self.write_launcher(os.path.join(self.config, "bin"), "git", script)

    def write_launcher(self, folder, name, script):
        # Windows finds only PATHEXT names: an extensionless stand-in there is skipped and the real CLI runs.
        if os.name == "nt":
            self.write(os.path.join(folder, name + ".cmd"), '@echo off\n"{}" "{}" %*\n'.format(sys.executable, script))
        else:
            launcher = os.path.join(folder, name)
            self.write(launcher, "#!/bin/sh\nexec {} {} \"$@\"\n".format(shlex.quote(sys.executable),
                                                                         shlex.quote(script)))
            os.chmod(launcher, 0o755)

    def assert_stand_ins_win(self):
        """Every CLI lane resolves here must be this test's stand-in, never a real claude (which could start a
        cloud session on the owner's account) or the real git."""
        root = os.path.normcase(os.path.realpath(self.root)) + os.sep
        for name in ("claude", "git"):
            found = (shutil.which(name, path=os.path.join(self.config, "bin"))
                     or shutil.which(name, path=self.env["PATH"]))
            where = os.path.normcase(os.path.realpath(found)) if found else ""
            if not where.startswith(root):
                raise AssertionError("{} resolves to {} instead of the test's stand-in; stopping before lane runs "
                                     "it".format(name, found))

    def install_kit(self, policy):
        """A temp kit: bin/lane (a copy), a fake sibling lane-stats, POLICY.md and agents/.

        The fake sits where a Windows install keeps the code (bin/lane-stats.py), and bin/lane-stats is a bash
        wrapper as install.sh writes it, which python cannot run: a fake at both names hid that lane ran the
        wrapper (2026-10-31.16)."""
        os.makedirs(os.path.join(self.kit, "bin"), exist_ok=True)
        shutil.copy2(SCRIPT, self.lane)
        stats = os.path.join(self.kit, "bin", "lane-stats.py")
        wrapper = os.path.join(self.kit, "bin", "lane-stats")
        self.write(stats, FAKE_STATS)
        self.write(wrapper, '#!/usr/bin/env bash\nexec {} {} "$@"\n'.format(shlex.quote(sys.executable),
                                                                          shlex.quote(stats)))
        for path in (stats, wrapper):
            os.chmod(path, 0o755)
        self.write_policy(policy)
        if not os.path.isdir(os.path.join(self.kit, "agents")):
            shutil.copytree(AGENTS, os.path.join(self.kit, "agents"))

    def write_policy(self, text):
        self.write(os.path.join(self.kit, "POLICY.md"), text)

    def run_cli(self, argv, env=None, real=False, timeout=45):
        return subprocess.run([sys.executable, SCRIPT if real else self.lane] + list(argv),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False,
                              cwd=self.root, env=dict(self.env, **(env or {})), encoding="utf-8", errors="replace")

    def run_main(self, *argv, **kwargs):
        return self.run_cli(["main"] + list(argv), **kwargs)

    def start(self, *extra, **kwargs):
        return self.run_main("-C", self.workspace, "-b", self.brief, *extra, **kwargs)

    def run_lane(self, lane="sonnet", extra=(), effort="high", env=None):
        argv = [lane, "-C", self.workspace, "-b", self.brief]
        if effort:
            argv.extend(["-e", effort])
        argv.extend(extra)
        return self.run_cli(argv, env=env)

    def out(self, result):
        return "exit {}\nstdout:\n{}\nstderr:\n{}".format(result.returncode, result.stdout, result.stderr)

    def remote_refs(self):
        result = self.git("--git-dir", self.origin, "for-each-ref", "--format=%(objectname)%09%(refname)",
                          "refs/heads")
        return {line.split("\t", 1)[1]: line.split("\t", 1)[0]
                for line in result.stdout.decode("utf-8").splitlines() if "\t" in line}

    def origin_git(self, *args):
        return self.git_text("--git-dir", self.origin, *args)

    # ----- mains.json -----

    @property
    def mains_path(self):
        return os.path.join(self.state, "mains.json")

    def read_mains(self):
        return self.read_json(self.mains_path)

    def write_mains(self, mains):
        os.makedirs(self.state, exist_ok=True)
        with open(self.mains_path, "w", encoding="utf-8") as stream:
            json.dump({"version": 1, "mains": mains}, stream)

    def entry(self, **changes):
        entry = {"main_id": MAIN_ID, "status": "live", "session_id": "session_Reg1",
                 "url": "https://claude.ai/code/session_Reg1", "branch": "claude/test",
                 "checkout": os.path.realpath(self.workspace), "remote": self.origin, "model": "opus",
                 "effort": "xhigh", "started_at": "2026-10-31T10:00:00Z", "last_seen": None, "previous": []}
        entry.update(changes)
        return entry

    def register(self, key=KEY, **changes):
        self.write_mains({key: self.entry(**changes)})

    # ----- the session's side of origin -----

    def open_session(self, branch="claude/test", register=True):
        """Put the workspace's main on origin, start the session branch there with its START marker, register it."""
        self.git("-C", self.workspace, "push", "--quiet", "origin", "main")
        self.git("clone", "--quiet", "-b", "main", self.origin, self.cloud)
        self.session_branch = branch
        self.git("-C", self.cloud, "checkout", "--quiet", "-b", branch)
        start = self.cloud_commit("orch: START " + MAIN_ID)
        if register:
            self.register(branch=branch, last_seen=start)
        return start

    def cloud_commit(self, subject, body=None, files=None):
        # Files enter the index through git plumbing, never the disk: a mirror on Linux can push names Windows cannot
        # create (CON.md; protectNTFS is off here, as on Linux), and --watch on Windows must meet them.
        for rel, text in (files or {}).items():
            content = text.lstrip("\n") if text.startswith("\n") else text
            blob = subprocess.run(["git", "-C", self.cloud, "hash-object", "-w", "--stdin"],
                                  input=content.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  timeout=20, check=True)
            self.git("-C", self.cloud, "-c", "core.protectNTFS=false", "update-index", "--add", "--cacheinfo",
                     "100644,{},{}".format(blob.stdout.decode("ascii").strip(), rel))
        message = os.path.join(self.root, "commit-message.txt")
        self.write(message, subject + ("\n\n" + body if body else "") + "\n")
        self.git("-C", self.cloud, *IDENT, "commit", "--quiet", "--allow-empty", "-F", message)
        sha = self.git_text("-C", self.cloud, "rev-parse", "HEAD")
        self.git("-C", self.cloud, "push", "--quiet", "origin", "HEAD:refs/heads/" + self.session_branch)
        return sha

    # ----- the prompt the main session receives -----

    def claude_record(self):
        return self.read_json(self.record)

    def check_main_prompt(self, prompt, main_id, brief_text=BRIEF_TEXT):
        self.assertTrue(prompt.isascii(), "prompt must be ASCII: " + repr([c for c in prompt if ord(c) > 127][:5]))
        self.assertEqual(prompt.split("\n")[:2], ["Kit mirror - " + KEY, ""], "the typed label is the first line")
        self.assertNotIn("CLOUD RUN", prompt)
        self.assertNotIn("You are a worker dispatched by lane", prompt)
        self.assertIn("(main id {})".format(main_id), prompt)
        self.assertIn('git commit --allow-empty -m "orch: START {}" && git push -u origin HEAD'.format(main_id), prompt)
        self.assertIn("python3 .claude/hooks/cloud-notify.py mark-main", prompt)
        # The kit install is its own START step, after mark-main and before the pick table.
        self.assertIn(KIT_INSTALL_LINE, prompt)
        self.assertLess(prompt.index("cloud-notify.py mark-main"), prompt.index(KIT_INSTALL_LINE))
        self.assertLess(prompt.index(KIT_INSTALL_LINE), prompt.index("4. Read the pick table"))
        self.assertIn("3. If ~/.claude/usage-optimizer is missing, install the kit.", prompt)
        self.assertIn("git fetch origin lane-main/picks", prompt)
        self.assertIn("FETCH_HEAD:picks.json", prompt)
        self.assertIn("before each new unit", prompt)
        self.assertIn("Use modes.claude only while modes_until.claude is in the future", prompt)
        self.assertIn("After it passes, use saving until a", prompt)
        self.assertIn("newer table arrives", prompt)
        for line in MARKER_LINES:
            self.assertIn(line, prompt)
        self.assertIn("lane-main/picks", prompt)
        self.assertIn("lane-result/{}/".format(main_id), prompt)
        self.assertIn("KIT POLICY (from POLICY.md, release {}; it addresses you)".format(RELEASE), prompt)
        self.assertIn("MAIN_SENTINEL", prompt)
        self.assertIn("BRIEFS_SENTINEL", prompt)
        for other in ("PRINCIPLE_SENTINEL", "MEASURE_SENTINEL", "METERS_SENTINEL"):
            self.assertNotIn(other, prompt)
        self.assertIn("PROJECT BRIEF", prompt)
        self.assertGreater(prompt.index("PROJECT BRIEF"), prompt.index("KIT POLICY"))
        self.assertTrue(prompt.rstrip().endswith(brief_text.strip()), prompt[-200:])
        self.assertLess(len(prompt), 30000)

    # ===== 1. start =====

    def test_start_launches_the_main_session_and_registers_it(self):
        result = self.start()
        self.assertEqual(result.returncode, 0, self.out(result))
        entry = self.read_mains()["mains"][KEY]
        self.assertEqual(self.read_mains()["version"], 1)
        self.assertRegex(entry["main_id"], r"^\d{8}-\d{6}-main$")
        self.assertEqual(entry["status"], "live")
        self.assertEqual(entry["session_id"], "session_Fake123")
        self.assertIn("https://claude.ai/code/session_Fake123", entry["url"])
        self.assertEqual(entry["branch"], "claude/test")
        self.assertEqual(os.path.realpath(entry["checkout"]), os.path.realpath(self.workspace))
        self.assertEqual(entry["remote"], self.origin)
        self.assertEqual(entry["model"], "opus")
        self.assertEqual(entry["effort"], "xhigh")
        self.assertTrue(entry["started_at"])
        self.assertEqual(entry["previous"], [])
        refs = self.remote_refs()
        # The session's branch stays; the base branch lane pushed for the session is gone; the picks branch is there.
        self.assertIn("refs/heads/claude/test", refs)
        self.assertNotIn("refs/heads/main", refs)
        self.assertIn("refs/heads/lane-main/picks", refs)
        self.assertEqual(entry["last_seen"], refs["refs/heads/claude/test"])
        self.assertEqual(self.origin_git("log", "-1", "--format=%s", "refs/heads/claude/test"),
                         "orch: START " + entry["main_id"])
        # What the owner is told.
        self.assertIn("https://claude.ai/code/session_Fake123", result.stdout)
        self.assertIn("claude/test", result.stdout)
        self.assertIn("--watch " + KEY, result.stdout)
        # The checkout is as it was.
        self.assertEqual(self.git_text("-C", self.workspace, "status", "--porcelain"), "")
        self.assertEqual(self.git_text("-C", self.workspace, "rev-parse", "HEAD"), self.base_sha)
        leftovers = [name for name in os.listdir(self.state) if name.startswith("mains.json") and name != "mains.json"]
        self.assertEqual(leftovers, [], "the atomic write must not leave its temp file")

    def test_start_prompt_and_arguments_reach_the_cloud_command(self):
        result = self.start()
        self.assertEqual(result.returncode, 0, self.out(result))
        record = self.claude_record()
        main_id = self.read_mains()["mains"][KEY]["main_id"]
        self.check_main_prompt(record["prompt"], main_id)
        argv = record["argv"]
        self.assertIn(argv[argv.index("--model") + 1], ("opus", "claude-opus-5-5"))
        self.assertEqual(argv[argv.index("--effort") + 1], "xhigh")
        self.assertEqual(argv[argv.index("--permission-mode") + 1], "auto")

    def test_start_options_set_model_effort_and_the_permission_mode_env(self):
        result = self.start("--model", "sonnet", "-e", "high", env={"LANES_CLOUD_PERMISSION_MODE": "plan"})
        self.assertEqual(result.returncode, 0, self.out(result))
        entry = self.read_mains()["mains"][KEY]
        self.assertEqual((entry["model"], entry["effort"]), ("sonnet", "high"))
        argv = self.claude_record()["argv"]
        self.assertIn(argv[argv.index("--model") + 1], ("sonnet", "claude-sonnet-5-5"))
        self.assertEqual(argv[argv.index("--effort") + 1], "high")
        self.assertEqual(argv[argv.index("--permission-mode") + 1], "plan")

    def test_start_goes_on_when_the_picks_step_fails(self):
        result = self.start(env={"FAKE_STATS_FAIL": "1"})
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertIn("warn", result.stderr.lower(), self.out(result))
        self.assertIn(KEY, self.read_mains()["mains"])
        self.assertNotIn("refs/heads/lane-main/picks", self.remote_refs())

    def test_start_pushes_the_picks_with_the_kit_and_repo_added(self):
        result = self.start()
        self.assertEqual(result.returncode, 0, self.out(result))
        picks = json.loads(self.origin_git("show", "refs/heads/lane-main/picks:picks.json"))
        self.assertEqual(picks["kit"], RELEASE)
        self.assertEqual(picks["repo"], KEY)

    def test_start_saves_its_exclude_list_and_the_picks_step_passes_it(self):
        log = os.path.join(self.root, "stats-args.log")
        result = self.start("--exclude", "gemini", env={"FAKE_STATS_LOG": log})
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertEqual(self.read_mains()["mains"][KEY]["exclude"], "gemini")
        self.assertEqual(self.stats_calls(log)[-1], ["main-picks", "--exclude", "gemini"])
        picks = json.loads(self.origin_git("show", "refs/heads/lane-main/picks:picks.json"))
        self.assertEqual(picks["repo"], KEY)

    def test_start_without_exclude_saves_an_empty_value_and_passes_none(self):
        log = os.path.join(self.root, "stats-args.log")
        result = self.start(env={"FAKE_STATS_LOG": log})
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertEqual(self.read_mains()["mains"][KEY]["exclude"], "")
        self.assertEqual(self.stats_calls(log)[-1], ["main-picks"])

    def test_start_without_a_work_description_is_a_usage_error(self):
        for argv in ([], ["-C", self.workspace], ["-b", self.brief]):
            result = self.run_main(*argv)
            self.assertEqual(result.returncode, 2, self.out(result))
        self.assertEqual(self.remote_refs(), {})

    def test_start_needs_a_github_origin_unless_the_test_override_is_set(self):
        result = self.start("--dry-run", env={"LANES_CLOUD_ANY_REMOTE": ""})
        self.assertEqual(result.returncode, 8, self.out(result))
        self.assertIn("GitHub", result.stderr)
        self.assertFalse(os.path.exists(self.mains_path))

    def test_start_refuses_a_dirty_tree(self):
        self.write(os.path.join(self.workspace, "untracked.txt"), "dirty\n")
        result = self.start()
        self.assertEqual(result.returncode, 8, self.out(result))
        self.assertIn("clean work tree", result.stderr)
        self.assertEqual(self.remote_refs(), {})
        self.assertFalse(os.path.exists(self.mains_path))

    def test_start_refuses_a_prompt_over_the_size_limit(self):
        self.write(self.brief, ("x" * 99 + "\n") * 310)
        result = self.start()
        self.assertEqual(result.returncode, 8, self.out(result))
        self.assertFalse(os.path.exists(self.record), "no session may be launched")
        self.assertFalse(os.path.exists(self.mains_path))
        self.assertFalse([ref for ref in self.remote_refs() if ref.startswith("refs/heads/claude/")])

    # ===== 2. replace, forget, list =====

    def test_second_start_for_the_same_repository_is_refused_until_replace(self):
        first = self.start()
        self.assertEqual(first.returncode, 0, self.out(first))
        old = self.read_mains()["mains"][KEY]
        before_refs = self.remote_refs()
        before_record = self.read(self.record)
        refused = self.start(env={"FAKE_SESSION_BRANCH": "claude/second", "FAKE_SESSION": "session_Second1"})
        self.assertEqual(refused.returncode, 8, self.out(refused))
        self.assertTrue("--replace" in refused.stderr or old["url"] in refused.stderr, self.out(refused))
        self.assertEqual(self.read_mains()["mains"][KEY], old)
        self.assertEqual(self.remote_refs(), before_refs)
        self.assertEqual(self.read(self.record), before_record, "a refused start must not launch a session")
        time.sleep(1.1)  # main ids count seconds
        replaced = self.start("--replace", env={"FAKE_SESSION_BRANCH": "claude/second",
                                                "FAKE_SESSION": "session_Second1"})
        self.assertEqual(replaced.returncode, 0, self.out(replaced))
        self.assertIn("archive", (replaced.stdout + replaced.stderr).lower(), self.out(replaced))
        entry = self.read_mains()["mains"][KEY]
        self.assertEqual(entry["status"], "live")
        self.assertEqual(entry["session_id"], "session_Second1")
        self.assertEqual(entry["branch"], "claude/second")
        self.assertNotEqual(entry["main_id"], old["main_id"])
        self.assertEqual(len(entry["previous"]), 1)
        previous = entry["previous"][-1]
        self.assertEqual(previous["status"], "replaced")
        self.assertEqual(previous["main_id"], old["main_id"])
        self.assertEqual(previous["session_id"], "session_Fake123")
        self.assertEqual(previous["branch"], "claude/test")

    def test_forget_removes_the_entry_and_later_watch_is_a_usage_error(self):
        self.register()
        result = self.run_main("--forget", KEY)
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertIn("archive", (result.stdout + result.stderr).lower(), self.out(result))
        self.assertEqual(self.read_mains()["mains"], {})
        again = self.run_main("--watch", KEY, "--timeout", "1", "--poll", "0.05")
        self.assertEqual(again.returncode, 2, self.out(again))

    def test_list_prints_a_table_or_says_there_is_none(self):
        empty = self.run_main("--list")
        self.assertEqual(empty.returncode, 0, self.out(empty))
        self.assertIn("no main cloud sessions", empty.stdout)
        self.write_mains({})
        empty = self.run_main("--list")
        self.assertEqual(empty.returncode, 0, self.out(empty))
        self.assertIn("no main cloud sessions", empty.stdout)
        self.register()
        result = self.run_main("--list")
        self.assertEqual(result.returncode, 0, self.out(result))
        row = next((line for line in result.stdout.splitlines() if KEY in line), None)
        self.assertIsNotNone(row, result.stdout)
        for part in ("live", "opus/xhigh", "claude/test", "https://claude.ai/code/session_Reg1"):
            self.assertIn(part, row)
        self.assertNotIn("no main cloud sessions", result.stdout)

    def test_list_json_prints_the_file_and_only_json_shows_replaced_entries(self):
        old = self.entry(status="replaced", main_id="20261030-090000-main", branch="claude/old",
                         url="https://claude.ai/code/session_Old1", session_id="session_Old1")
        self.write_mains({KEY: self.entry(previous=[old])})
        result = self.run_main("--list", "--json")
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertEqual(json.loads(result.stdout), self.read_mains())
        self.assertEqual(json.loads(result.stdout)["mains"][KEY]["previous"][0]["status"], "replaced")
        table = self.run_main("--list")
        self.assertEqual(table.returncode, 0, self.out(table))
        self.assertNotIn("replaced", table.stdout)
        self.assertNotIn("claude/old", table.stdout)

    # ===== 3. no START marker =====

    def test_start_without_a_start_marker_exits_4_and_writes_no_entry(self):
        result = self.start(env={"FAKE_CLAUDE_MODE": "no-start", "LANES_CLOUD_START_TIMEOUT": "0.5"})
        self.assertEqual(result.returncode, 4, self.out(result))
        self.assertIn("https://claude.ai/code/session_Fake123", result.stdout + result.stderr)
        self.assertIn("the session may still be running; stop or archive it in the Claude app: "
                      "https://claude.ai/code/session_Fake123", result.stdout + result.stderr)
        self.assertFalse(os.path.exists(self.mains_path) and self.read_mains()["mains"], self.out(result))
        self.assertFalse([ref for ref in self.remote_refs() if ref.startswith("refs/heads/claude/")])

    def test_start_timeout_bounds_the_whole_start(self):
        result = self.start("--timeout", "1", env={"FAKE_CLAUDE_MODE": "no-start", "LANES_CLOUD_START_TIMEOUT": "60"})
        self.assertEqual(result.returncode, 124, self.out(result))
        self.assertFalse(os.path.exists(self.mains_path) and self.read_mains()["mains"], self.out(result))

    # ===== 3b. a cloud session never starts another session =====

    CLOUD_ENV = {"CLAUDE_CODE_REMOTE": "true"}

    def test_a_real_start_is_refused_in_a_cloud_session_before_any_push_or_launch(self):
        result = self.start(env=self.CLOUD_ENV)
        self.assertEqual(result.returncode, 8, self.out(result))
        self.assertIn("a cloud session never starts another session", result.stderr)
        self.assertIn("USAGE_OPTIMIZER_SESSION_GUARD=off", result.stderr)
        self.assertEqual(self.remote_refs(), {})
        self.assertFalse(os.path.exists(self.record), "no session may be launched")
        self.assertFalse(os.path.exists(self.mains_path))

    def test_a_real_start_in_a_cloud_session_goes_on_with_the_guard_off(self):
        for value in ("off", " OFF "):
            result = self.start("--replace", env=dict(self.CLOUD_ENV, USAGE_OPTIMIZER_SESSION_GUARD=value))
            self.assertEqual(result.returncode, 0, self.out(result))
            self.assertTrue(os.path.exists(self.record), "the guard is off, so the session is launched")
            self.assertNotIn("never starts another session", result.stderr)
            time.sleep(1.1)  # main ids count seconds

    def test_the_read_only_actions_and_the_dry_run_still_work_in_a_cloud_session(self):
        dry = self.start("--dry-run", env=self.CLOUD_ENV)
        self.assertEqual(dry.returncode, 0, self.out(dry))
        self.assertIn("PASS", dry.stdout)
        picks = self.run_main("--picks", KEY, "--dry-run", env=self.CLOUD_ENV)
        self.assertNotIn("never starts another session", picks.stderr)
        listed = self.run_main("--list", env=self.CLOUD_ENV)
        self.assertEqual(listed.returncode, 0, self.out(listed))
        forgotten = self.run_main("--forget", KEY, env=self.CLOUD_ENV)
        self.assertNotIn("never starts another session", forgotten.stderr)
        self.assertFalse(os.path.exists(self.record))
        self.assertEqual(self.remote_refs(), {})

    def test_the_prompt_forbids_starting_other_sessions_and_stays_under_the_limit(self):
        result = self.start("--dry-run")
        self.assertEqual(result.returncode, 0, self.out(result))
        names = [name for name in os.listdir(self.state) if name.startswith("main-prompt-")]
        prompt = self.read(os.path.join(self.state, names[0]))
        self.assertIn("Start no other session", prompt)
        self.assertIn("never call create_session", prompt)
        self.assertLess(len(prompt), load_lane().MAIN_PROMPT_LIMIT)

    # ===== 4. dry run =====

    def test_dry_run_launches_and_pushes_nothing_and_writes_the_prompt_file(self):
        result = self.start("--dry-run")
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertIn("PASS", result.stdout)
        self.assertIn(KEY, result.stdout)
        self.assertIn("mirror", result.stdout.lower())
        self.assertEqual(self.remote_refs(), {})
        self.assertFalse(os.path.exists(self.record), "a dry run must not launch claude")
        self.assertFalse(os.path.exists(self.mains_path))
        names = [name for name in os.listdir(self.state) if name.startswith("main-prompt-")]
        self.assertEqual(len(names), 1, os.listdir(self.state))
        match = re.fullmatch(r"main-prompt-(\d{8}-\d{6}-main)\.md", names[0])
        self.assertIsNotNone(match, names)
        prompt = self.read(os.path.join(self.state, names[0]))
        self.check_main_prompt(prompt, match.group(1))
        lengths = [int(number) for line in result.stdout.splitlines() if "prompt" in line.lower()
                   for number in re.findall(r"\d+", line)]
        self.assertTrue(any(abs(number - len(prompt)) <= 2 for number in lengths),
                        "the prompt length {} is not printed: {}".format(len(prompt), result.stdout))

    def test_dry_run_says_whether_a_live_mirror_exists_and_still_changes_nothing(self):
        none = self.start("--dry-run")
        self.assertEqual(none.returncode, 0, self.out(none))
        line = next(line for line in none.stdout.splitlines() if "mirror" in line.lower())
        self.assertNotIn("yes", line.lower())
        self.register(url="https://claude.ai/code/session_MirrorLive")
        before = self.read(self.mains_path)
        live = self.start("--dry-run")
        self.assertEqual(live.returncode, 0, self.out(live))
        line = next(line for line in live.stdout.splitlines() if "mirror" in line.lower())
        self.assertTrue("yes" in line.lower() or "session_MirrorLive" in line, line)
        self.assertEqual(self.read(self.mains_path), before)
        self.assertEqual(self.remote_refs(), {})
        self.assertFalse(os.path.exists(self.record))

    def test_dry_run_prints_the_exclude_line_and_changes_nothing(self):
        result = self.start("--dry-run", "--exclude", "gemini")
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertIn("exclude: gemini", result.stdout.splitlines())
        plain = self.start("--dry-run")
        self.assertEqual(plain.returncode, 0, self.out(plain))
        self.assertIn("exclude: none", plain.stdout.splitlines())
        self.assertEqual(self.remote_refs(), {})
        self.assertFalse(os.path.exists(self.mains_path))
        self.assertFalse(os.path.exists(self.record))

    def test_an_unknown_lane_in_exclude_stops_start_and_picks_before_anything_runs(self):
        for argv in (("--exclude", "gemni"), ("--dry-run", "--exclude", "gemini, gemni")):
            with self.subTest(argv=argv):
                result = self.start(*argv)
                self.assertEqual(result.returncode, 2, self.out(result))
                self.assertIn("unknown lane in --exclude: gemni", result.stderr)
        picks = self.run_main("--picks", KEY, "--exclude", "gemni")
        self.assertEqual(picks.returncode, 2, self.out(picks))
        self.assertIn("unknown lane in --exclude: gemni", picks.stderr)
        self.assertEqual(self.remote_refs(), {})
        self.assertFalse(os.path.exists(self.mains_path))
        self.assertFalse(os.path.exists(self.record))

    def test_exclude_names_are_trimmed_sorted_and_deduplicated(self):
        result = self.start("--dry-run", "--exclude", " gemini ,haiku,gemini")
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertIn("exclude: gemini,haiku", result.stdout.splitlines())

    # ===== 5. watch =====

    def push_markers(self):
        """STATUS, a non-marker commit, LOCAL with its brief, REVIEW x2, READY; returns {name: sha}."""
        shas = {}
        shas["status"] = self.cloud_commit("orch: STATUS 1: Plan ready",
                                           body="The plan has three units.\nNo action needed.")
        shas["plain"] = self.cloud_commit("cloud task result", files={"result.txt": "work\n"})
        shas["local"] = self.cloud_commit(
            "orch: LOCAL lane unit-a luna/gpt-6-luna/high .lane-main/briefs/unit-a.md",
            files={".lane-main/briefs/unit-a.md": "Goal: write the thing.\nFiles: src/a.py\n"})
        shas["review"] = self.cloud_commit(
            "orch: REVIEW unit-b fixed arm=haiku/claude-haiku-5-5/medium class=mechanical min=3 tok=1000/200 "
            "usd=0.05 fix=2")
        shas["review_unknown"] = self.cloud_commit(
            "orch: REVIEW unit-a accepted arm=luna/gpt-6-luna/high class=substantive min=- tok=- usd=- via=local")
        shas["ready"] = self.cloud_commit("orch: READY 2: Merge unit-b",
                                          body="Merge claude/test into the default branch.")
        return shas

    def watch(self, *extra, key=KEY, **kwargs):
        return self.run_main("--watch", key, "--poll", "0.05", *extra, **kwargs)

    def marker_lines(self, stdout):
        return [line for line in stdout.splitlines() if line.startswith("orch ")]

    def test_watch_prints_one_line_per_marker_and_saves_the_local_brief(self):
        self.open_session()
        shas = self.push_markers()
        result = self.watch("--timeout", "20")
        self.assertEqual(result.returncode, 0, self.out(result))
        lines = self.marker_lines(result.stdout)
        self.assertEqual([line.split()[1] for line in lines], ["STATUS", "LOCAL", "REVIEW", "REVIEW", "READY"],
                         result.stdout)
        by_kind = {}
        for line in lines:
            by_kind.setdefault(line.split()[1], []).append(line)
        status = by_kind["STATUS"][0]
        self.assertTrue(status.startswith("orch STATUS {} n=1 title=".format(shas["status"][:12])), status)
        self.assertIn("Plan ready", status)
        out_lines = result.stdout.splitlines()
        body_at = out_lines.index("  The plan has three units.")
        self.assertEqual(out_lines[body_at + 1], "  No action needed.")
        self.assertGreater(body_at, out_lines.index(status))
        ready = by_kind["READY"][0]
        self.assertTrue(ready.startswith("orch READY {} n=2 title=".format(shas["ready"][:12])), ready)
        self.assertIn("Merge unit-b", ready)
        self.assertIn("  Merge claude/test into the default branch.", out_lines)
        reviews = by_kind["REVIEW"]
        self.assertTrue(reviews[0].startswith("orch REVIEW {} ".format(shas["review"][:12])), reviews[0])
        for part in ("unit-b", "fixed", "arm=haiku/claude-haiku-5-5/medium", "class=mechanical", "min=3",
                     "tok=1000/200", "usd=0.05", "fix=2"):
            self.assertIn(part, reviews[0])
        self.assertTrue(reviews[1].startswith("orch REVIEW {} ".format(shas["review_unknown"][:12])), reviews[1])
        for part in ("unit-a", "accepted", "min=-", "tok=-", "usd=-", "via=local"):
            self.assertIn(part, reviews[1])
        self.assertNotIn("orch BAD", result.stdout)
        # The LOCAL line, the saved brief and the next: commands.
        local = by_kind["LOCAL"][0]
        self.assertTrue(local.startswith("orch LOCAL {} ".format(shas["local"][:12])), local)
        self.assertIn("unit=unit-a", local)
        self.assertIn("arm=luna/gpt-6-luna/high", local)
        saved = re.search(r"brief=(\S+)", local)
        self.assertIsNotNone(saved, local)
        saved_path = saved.group(1)
        self.assertEqual(self.read(saved_path), "Goal: write the thing.\nFiles: src/a.py\n")
        self.assertTrue(os.path.realpath(saved_path).startswith(os.path.realpath(os.path.join(self.state, "mains"))
                                                                + os.sep), saved_path)
        self.assertTrue(saved_path.replace("\\", "/").endswith("briefs/unit-a.md"), saved_path)
        block = out_lines[out_lines.index(local) + 1:]
        next_lines = []
        for line in block:
            if line.startswith("orch "):
                break
            next_lines.append(line)
        self.assertTrue(next_lines and next_lines[0].startswith("  "), result.stdout)
        next_block = "\n".join(next_lines)
        self.assertRegex(next_block, r"(?m)^\s+next:", "the LOCAL block needs an indented next: line")
        # On Windows the next: line prints paths with forward slashes, for Git Bash (2026-10-31.16).
        printed_path = saved_path.replace("\\", "/") if os.name == "nt" else saved_path
        for part in ("lane luna", "--tag orch-{}-unit-a".format(MAIN_ID), printed_path):
            self.assertIn(part, next_block)
        self.assertRegex(next_block, r"git (-C \S+ )?worktree add")
        self.assertRegex(next_block, r"(-e|--effort) high")
        self.assertRegex(next_block, r"lane main --return \S+ unit-a")
        self.assertEqual(self.read_mains()["mains"][KEY]["last_seen"], shas["ready"])

    def test_watch_updates_last_seen_so_a_second_poll_waits(self):
        self.open_session()
        shas = self.push_markers()
        first = self.watch("--timeout", "20")
        self.assertEqual(first.returncode, 0, self.out(first))
        self.assertEqual(self.read_mains()["mains"][KEY]["last_seen"], shas["ready"])
        # A checkout path names the repository too.
        second = self.watch("--timeout", "1", key=self.workspace)
        self.assertEqual(second.returncode, 124, self.out(second))
        self.assertRegex(second.stdout + second.stderr, r"no marker in 1(\.0)? seconds")
        self.assertEqual(self.marker_lines(second.stdout), [])

    def test_watch_keeps_waiting_when_the_new_commit_is_not_a_marker(self):
        start = self.open_session()
        plain = self.cloud_commit("cloud task result", files={"result.txt": "work\n"})
        result = self.watch("--timeout", "1")
        self.assertEqual(result.returncode, 124, self.out(result))
        self.assertRegex(result.stdout + result.stderr, r"no marker in 1(\.0)? seconds")
        self.assertEqual(self.marker_lines(result.stdout), [])
        self.assertNotEqual(start, plain)
        self.assertEqual(self.read_mains()["mains"][KEY]["last_seen"], plain)

    def test_watch_prints_bad_for_a_marker_that_does_not_parse(self):
        self.open_session()
        bad_review = "orch: REVIEW unit-x great arm=sonnet/claude-sonnet-5-5/high class=mechanical min=1 tok=1/1 usd=1"
        bad_status = "orch: STATUS soon: not a number"
        sha_review = self.cloud_commit(bad_review)
        sha_status = self.cloud_commit(bad_status)
        good = self.cloud_commit("orch: STATUS 1: Fine")
        result = self.watch("--timeout", "20")
        self.assertEqual(result.returncode, 0, self.out(result))
        lines = result.stdout.splitlines()
        self.assertIn("orch BAD {} {}".format(sha_review[:12], bad_review), lines)
        self.assertIn("orch BAD {} {}".format(sha_status[:12], bad_status), lines)
        self.assertTrue(any(line.startswith("orch STATUS {} n=1".format(good[:12])) for line in lines), result.stdout)

    def test_watch_does_not_save_a_brief_from_outside_the_briefs_folder(self):
        self.open_session()
        subject = "orch: LOCAL lane unit-z luna/gpt-6-luna/high docs/notes.md"
        sha = self.cloud_commit(subject, files={"docs/notes.md": "not a brief\n"})
        result = self.watch("--timeout", "20")
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertIn("orch BAD {} {}".format(sha[:12], subject), result.stdout.splitlines())
        saved = [name for _, _, names in os.walk(os.path.join(self.state, "mains")) for name in names]
        self.assertEqual(saved, [])

    def test_watch_of_an_unknown_repository_is_a_usage_error(self):
        self.register()
        result = self.watch("--timeout", "1", key="nobody/none")
        self.assertEqual(result.returncode, 2, self.out(result))

    def test_watch_wakes_when_a_marker_arrives_while_it_polls(self):
        self.open_session()
        # No --poll: LANES_CLOUD_POLL=0.05 in the environment sets the default (it would be 60 seconds otherwise).
        process = subprocess.Popen([sys.executable, self.lane, "main", "--watch", KEY, "--timeout", "30"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   cwd=self.root, env=self.env, encoding="utf-8", errors="replace")
        self.addCleanup(lambda: process.poll() is None and process.kill())
        time.sleep(0.6)
        self.assertIsNone(process.poll(), "the poll must wait while nothing happens")
        sha = self.cloud_commit("orch: STATUS 1: Late news")
        stdout, stderr = process.communicate(timeout=20)
        self.assertEqual(process.returncode, 0, stdout + stderr)
        self.assertTrue(any(line.startswith("orch STATUS {} n=1".format(sha[:12])) for line in stdout.splitlines()),
                        stdout)

    # ===== 6. picks =====

    def stats_calls(self, log):
        """The argument lists of the fake lane-stats calls logged in FAKE_STATS_LOG, oldest first."""
        if not os.path.exists(log):
            return []
        with open(log, "r", encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]

    def picks_state(self):
        return {"head": self.git_text("-C", self.workspace, "rev-parse", "HEAD"),
                "status": self.git_text("-C", self.workspace, "status", "--porcelain", "--untracked-files=all"),
                "index": self.git_text("-C", self.workspace, "ls-files", "-s"),
                "heads": self.git_text("-C", self.workspace, "for-each-ref", "refs/heads")}

    def test_picks_pushes_one_commit_with_only_picks_json_then_fast_forwards(self):
        self.register()
        before = self.picks_state()
        first = self.run_main("--picks", KEY, env={"FAKE_STATS_AT": "2026-10-31T01:00:00Z"})
        self.assertEqual(first.returncode, 0, self.out(first))
        tip1 = self.remote_refs()["refs/heads/lane-main/picks"]
        self.assertEqual(self.origin_git("rev-list", "--count", tip1), "1")
        self.assertRegex(self.origin_git("log", "-1", "--format=%s", tip1), r"^lane: picks .*\d{4}")
        self.assertEqual(self.origin_git("ls-tree", "-r", "--name-only", tip1), "picks.json")
        picks = json.loads(self.origin_git("show", tip1 + ":picks.json"))
        self.assertEqual(picks["kit"], RELEASE)
        self.assertEqual(picks["repo"], KEY)
        self.assertEqual(picks["version"], 1)
        self.assertEqual(picks["at"], "2026-10-31T01:00:00Z")
        self.assertEqual(picks["classes"]["substantive"]["arms"][0]["arm"], "sonnet/claude-sonnet-5-5/high")
        self.assertEqual(picks["plans"]["codex"], "none")
        self.assertEqual(self.picks_state(), before, "--picks must not touch the checkout, index or branches")
        second = self.run_main("--picks", KEY, env={"FAKE_STATS_AT": "2026-10-31T02:00:00Z"})
        self.assertEqual(second.returncode, 0, self.out(second))
        tip2 = self.remote_refs()["refs/heads/lane-main/picks"]
        self.assertNotEqual(tip1, tip2)
        self.assertEqual(self.origin_git("rev-parse", tip2 + "^"), tip1)
        self.assertEqual(self.origin_git("rev-list", "--count", tip2), "2")
        self.assertEqual(self.origin_git("ls-tree", "-r", "--name-only", tip2), "picks.json")
        self.assertEqual(json.loads(self.origin_git("show", tip2 + ":picks.json"))["at"], "2026-10-31T02:00:00Z")
        self.assertEqual(self.picks_state(), before)

    def test_picks_dry_run_pushes_nothing(self):
        self.register()
        result = self.run_main("--picks", KEY, "--dry-run")
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertEqual(self.remote_refs(), {})

    def test_picks_runs_the_python_lane_stats_in_both_install_layouts(self):
        # A Windows install: bin/lane-stats.py beside a bash wrapper at bin/lane-stats (the temp kit's layout).
        # A checkout or a Linux install: only bin/lane-stats, which is the Python file.
        self.register()
        with open(os.path.join(self.kit, "bin", "lane-stats"), encoding="utf-8") as stream:
            self.assertTrue(stream.read().startswith("#!/usr/bin/env bash"), "the temp kit must mirror a Windows install")
        windows = self.run_main("--picks", KEY)
        self.assertEqual(windows.returncode, 0, self.out(windows))
        self.assertNotIn("SyntaxError", windows.stderr)
        os.remove(os.path.join(self.kit, "bin", "lane-stats.py"))
        self.write(os.path.join(self.kit, "bin", "lane-stats"), FAKE_STATS)
        plain = self.run_main("--picks", KEY)
        self.assertEqual(plain.returncode, 0, self.out(plain))

    def test_picks_fails_when_lane_stats_fails_and_pushes_nothing(self):
        self.register()
        result = self.run_main("--picks", KEY, env={"FAKE_STATS_FAIL": "1"})
        self.assertNotEqual(result.returncode, 0, self.out(result))
        self.assertEqual(self.remote_refs(), {})

    def test_picks_exclude_is_saved_and_reused_until_changed(self):
        log = os.path.join(self.root, "stats-args.log")
        env = {"FAKE_STATS_LOG": log}
        self.register()  # an entry without an "exclude" key means none
        plain = self.run_main("--picks", KEY, env=env)
        self.assertEqual(plain.returncode, 0, self.out(plain))
        self.assertEqual(self.stats_calls(log)[-1], ["main-picks"])
        self.assertNotIn("exclude", self.read_mains()["mains"][KEY])
        first = self.run_main("--picks", KEY, "--exclude", "gemini", env=env)
        self.assertEqual(first.returncode, 0, self.out(first))
        self.assertEqual(self.stats_calls(log)[-1], ["main-picks", "--exclude", "gemini"])
        self.assertEqual(self.read_mains()["mains"][KEY]["exclude"], "gemini")
        reused = self.run_main("--picks", KEY, env=env)
        self.assertEqual(reused.returncode, 0, self.out(reused))
        self.assertEqual(self.stats_calls(log)[-1], ["main-picks", "--exclude", "gemini"])
        changed = self.run_main("--picks", KEY, "--exclude", "sonnet,haiku", env=env)
        self.assertEqual(changed.returncode, 0, self.out(changed))
        self.assertEqual(self.stats_calls(log)[-1], ["main-picks", "--exclude", "haiku,sonnet"])
        self.assertEqual(self.read_mains()["mains"][KEY]["exclude"], "haiku,sonnet")
        refs_before = self.remote_refs()
        dry = self.run_main("--picks", KEY, "--dry-run", "--exclude", "luna", env=env)
        self.assertEqual(dry.returncode, 0, self.out(dry))
        self.assertIn("exclude: luna", dry.stdout.splitlines())
        self.assertEqual(self.read_mains()["mains"][KEY]["exclude"], "haiku,sonnet", "--dry-run saves nothing")
        self.assertEqual(self.remote_refs(), refs_before, "--dry-run pushes nothing")

    def test_picks_of_an_unknown_repository_fails(self):
        self.register()
        result = self.run_main("--picks", "nobody/none")
        self.assertNotEqual(result.returncode, 0, self.out(result))
        self.assertEqual(self.remote_refs(), {})

    # ===== 6b. the lean kit branch (lane-main/kit) =====

    KIT_REF = "refs/heads/lane-main/kit"

    def installer_inputs(self):
        """The files, folders and copied items install.sh needs, parsed from install.sh so the lists are never copied."""
        text = self.read(os.path.join(ROOT, "install.sh"))
        required = re.search(r"^required_files=\(([^)]*)\)", text, re.MULTILINE)
        folders = re.search(r"^for dir in ([^;]*); do", text, re.MULTILINE)
        items = re.search(r"^KIT_ITEMS=\(([^)]*)\)", text, re.MULTILINE)
        for found in (required, folders, items):
            self.assertIsNotNone(found, "install.sh no longer has the list this test reads")
        return required.group(1).split(), folders.group(1).split(), items.group(1).split()

    def pack_folders(self):
        """Pack folder names in this tree: public packs in skills/, private ones in private/skills/ (2026-11-01.5)."""
        names = set()
        for parts in (("skills",), ("private", "skills")):
            skills = os.path.join(ROOT, *parts)
            if os.path.isdir(skills):
                names.update(name for name in os.listdir(skills) if os.path.isdir(os.path.join(skills, name)))
        return sorted(names)

    def extract_tree(self, tree, folder):
        for relative, (mode, data) in tree.items():
            path = os.path.join(folder, *relative.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as stream:
                stream.write(data)
            os.chmod(path, 0o755 if mode == "100755" else 0o644)

    def small_kit(self, name="small-kit"):
        """A kit root with install.sh and a few items, enough for a push test to be quick."""
        folder = os.path.join(self.root, name)
        os.makedirs(os.path.join(folder, "bin"))
        os.makedirs(os.path.join(folder, "skills", "demo-pack"))
        shutil.copy2(os.path.join(ROOT, "install.sh"), os.path.join(folder, "install.sh"))
        self.write(os.path.join(folder, "POLICY.md"), SYNTHETIC_POLICY)
        self.write(os.path.join(folder, "bin", "tool"), "#!/bin/sh\necho tool\n")
        self.write(os.path.join(folder, "skills", "demo-pack", "SKILL.md"), "a pack\n")
        return folder

    def kit_push_calls(self, module):
        """cloud_git wrapped to record every push's arguments, so a test can show no push forces anything."""
        calls = []
        real = module.cloud_git

        def recording(path, args, timeout=30):
            if args and args[0] == "push":
                calls.append(list(args))
            return real(path, args, timeout=timeout)
        patcher = mock.patch.object(module, "cloud_git", recording)
        patcher.start()
        self.addCleanup(patcher.stop)
        return calls

    def test_the_lean_kit_holds_every_installer_input(self):
        tree = load_lane().main_lean_kit(ROOT)
        required, folders, items = self.installer_inputs()
        for name in required:
            self.assertIn(name, tree, "install.sh requires {}".format(name))
        for name in folders + items:
            self.assertTrue(name in tree or any(path.startswith(name + "/") for path in tree),
                            "install.sh needs {} (a folder or an item it copies)".format(name))
        self.assertIn("install.sh", items, "the installed kit must carry install.sh so the lean copy can install")

    def test_the_lean_kit_leaves_out_the_pack_the_raw_findings_and_crlf(self):
        module = load_lane()
        tree = module.main_lean_kit(ROOT)
        packs = self.pack_folders()  # none in a tree without packs, such as an installed public bundle
        self.assertEqual([path for path in tree if path.startswith("skills/")], ["skills/README.md"])
        for path in tree:
            if path.startswith("findings/"):
                self.assertTrue(path.endswith(".md") or path == "findings/findings.json", path)
            self.assertNotIn("__pycache__", path)
            self.assertFalse(path.endswith(".pyc"), path)
        for path, (mode, data) in tree.items():
            for pack in packs:
                self.assertNotIn(pack.encode("utf-8"), data, "{} names the pack {}".format(path, pack))
            if b"\0" not in data:
                self.assertNotIn(b"\r\n", data, path)
            executable = path == "install.sh" or path.startswith("bin/")
            self.assertEqual(mode, "100755" if executable else "100644", path)
        self.assertNotIn("## Knowledge pack", tree["README.md"][1].decode("utf-8"))
        self.assertIn("~/.claude/agents/", tree["SETUP_PROMPT.md"][1].decode("utf-8"))
        lean = tree["LEAN.md"][1].decode("utf-8")
        self.assertIn(policy_release(self.read(POLICY)), lean)
        self.assertIn("lane main", lean)

    def test_the_lean_kit_dry_run_installs_from_its_own_copy(self):
        bash = shutil.which("bash")
        if bash is None or os.name == "nt":
            self.skipTest("bash is not installed (or this is Windows, where the installer test module covers it)")
        folder = os.path.join(self.root, "lean")
        home = os.path.join(self.root, "lean-home")
        os.makedirs(home)
        self.extract_tree(load_lane().main_lean_kit(ROOT), folder)
        env = dict(os.environ, HOME=home, USERPROFILE=home, USAGE_OPTIMIZER_SKIP_CLI_CHECK="1")
        env.pop("CLAUDE_CONFIG_DIR", None)
        result = subprocess.run([bash, os.path.join(folder, "install.sh"), "--dry-run", "--no-view"], cwd=home,
                                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8",
                                errors="replace", timeout=300, check=False)
        self.assertEqual(result.returncode, 0, self.out(result))

    def test_kit_push_creates_the_branch_skips_an_unchanged_tree_and_builds_on_the_old_tip(self):
        module = self.direct_lane()
        calls = self.kit_push_calls(module)
        kit = self.small_kit()
        before = self.picks_state()
        first, _ = self.stdout_of(module.main_push_kit, self.workspace, kit)
        tip1 = self.remote_refs()[self.KIT_REF]
        self.assertEqual(first, tip1)
        self.assertEqual(self.origin_git("log", "-1", "--format=%s", tip1),
                         "lane: kit 2099-01-02.3 (lean copy for the mirror)")
        names = self.origin_git("ls-tree", "-r", "--name-only", tip1).splitlines()
        self.assertEqual(sorted(names), ["LEAN.md", "POLICY.md", "bin/tool", "install.sh", "skills/README.md"])
        modes = {line.split("\t")[1]: line.split()[0] for line in
                 self.origin_git("ls-tree", "-r", tip1).splitlines()}
        self.assertEqual((modes["bin/tool"], modes["install.sh"], modes["POLICY.md"]), ("100755", "100755", "100644"))
        self.assertEqual(self.picks_state(), before, "the kit push must not touch the checkout, index or branches")
        again, printed = self.stdout_of(module.main_push_kit, self.workspace, kit)
        self.assertIsNone(again)
        self.assertIn("unchanged", printed)
        self.assertEqual(self.remote_refs()[self.KIT_REF], tip1)
        self.write(os.path.join(kit, "bin", "tool"), "#!/bin/sh\necho changed\n")
        changed, _ = self.stdout_of(module.main_push_kit, self.workspace, kit)
        tip2 = self.remote_refs()[self.KIT_REF]
        self.assertEqual(changed, tip2)
        self.assertNotEqual(tip1, tip2)
        self.assertEqual(self.origin_git("rev-parse", tip2 + "^"), tip1)
        self.assertEqual(self.picks_state(), before)
        self.assertEqual(len(calls), 2, calls)
        for args in calls:
            self.assertFalse(any(arg in ("--force", "-f") or arg.startswith(("+", "--force")) for arg in args), args)

    def test_a_kit_without_install_sh_gives_the_warning_and_does_not_raise(self):
        module = self.direct_lane()
        kit = self.small_kit()
        os.remove(os.path.join(kit, "install.sh"))
        captured = io.StringIO()
        with contextlib.redirect_stderr(captured):
            self.assertIsNone(module.main_push_kit(self.workspace, kit))
        self.assertIn("warning: the installed kit has no install.sh (installed before 2026-10-31.18); reinstall the "
                      "kit, then run lane main --picks <repo>", captured.getvalue())
        self.assertNotIn(self.KIT_REF, self.remote_refs())
        # The temp kit of a CLI start has no install.sh either: the start still succeeds.
        result = self.start()
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertIn("no install.sh", result.stderr)
        self.assertNotIn(self.KIT_REF, self.remote_refs())

    def test_start_pushes_the_kit_and_no_kit_turns_it_off_until_a_start_without_it(self):
        shutil.copy2(os.path.join(ROOT, "install.sh"), os.path.join(self.kit, "install.sh"))
        off = self.start("--no-kit")
        self.assertEqual(off.returncode, 0, self.out(off))
        self.assertIs(self.read_mains()["mains"][KEY]["no_kit"], True)
        self.assertNotIn(self.KIT_REF, self.remote_refs())
        picks = self.run_main("--picks", KEY)
        self.assertEqual(picks.returncode, 0, self.out(picks))
        self.assertIn("kit: skipped (--no-kit)", picks.stdout.splitlines())
        self.assertNotIn(self.KIT_REF, self.remote_refs(), "--picks reuses the saved --no-kit")
        dry = self.run_main("--picks", KEY, "--dry-run")
        self.assertIn("kit: skipped (--no-kit)", dry.stdout.splitlines(), self.out(dry))
        time.sleep(1.1)  # main ids count seconds
        on = self.start("--replace", env={"FAKE_SESSION_BRANCH": "claude/second", "FAKE_SESSION": "session_Second1"})
        self.assertEqual(on.returncode, 0, self.out(on))
        self.assertIs(self.read_mains()["mains"][KEY]["no_kit"], False)
        tip = self.remote_refs()[self.KIT_REF]
        self.assertEqual(self.origin_git("ls-tree", "--name-only", tip, "install.sh"), "install.sh")
        later = self.run_main("--picks", KEY)
        self.assertEqual(later.returncode, 0, self.out(later))
        self.assertIn("unchanged", later.stdout)
        self.assertEqual(self.remote_refs()[self.KIT_REF], tip)
        flagged = self.run_main("--picks", KEY, "--no-kit")
        self.assertEqual(flagged.returncode, 0, self.out(flagged))
        self.assertIs(self.read_mains()["mains"][KEY]["no_kit"], True)

    def test_dry_runs_print_the_kit_line(self):
        shutil.copy2(os.path.join(ROOT, "install.sh"), os.path.join(self.kit, "install.sh"))
        result = self.start("--dry-run")
        self.assertEqual(result.returncode, 0, self.out(result))
        line = next(line for line in result.stdout.splitlines() if line.startswith("kit:"))
        self.assertRegex(line, r"^kit: would push lane-main/kit \(\d+ files, \d+ bytes, version 2099-01-02\.3\)$")
        skipped = self.start("--dry-run", "--no-kit")
        self.assertIn("kit: skipped (--no-kit)", skipped.stdout.splitlines(), self.out(skipped))
        self.register()
        picks = self.run_main("--picks", KEY, "--dry-run")
        self.assertIn(line, picks.stdout.splitlines(), self.out(picks))
        self.assertEqual(self.remote_refs(), {})

    def test_no_kit_does_not_go_with_other_modes(self):
        self.register()
        result = self.run_main("--list", "--no-kit")
        self.assertEqual(result.returncode, 2, self.out(result))
        self.assertIn("--no-kit does not go with --list", result.stderr)

    # ===== 7. return =====

    def make_result_tree(self, name="result-tree"):
        path = os.path.join(self.root, name)
        self.git("-C", self.workspace, "worktree", "add", "-q", "-b", name, path, "main")
        return path

    def test_return_pushes_the_result_branch_from_another_work_tree(self):
        self.register()
        tree = self.make_result_tree()
        self.write(os.path.join(tree, "result.txt"), "unit result\n")
        result = self.run_main("--return", KEY, "unit-a", "-C", tree)
        self.assertEqual(result.returncode, 0, self.out(result))
        branch = "refs/heads/lane-result/{}/unit-a".format(MAIN_ID)
        refs = self.remote_refs()
        self.assertIn(branch, refs)
        self.assertEqual(self.origin_git("log", "-1", "--format=%s", branch), "lane: result unit-a verdict=OK")
        self.assertEqual(self.origin_git("show", branch + ":result.txt"), "unit result")
        self.assertEqual(self.origin_git("rev-parse", branch), self.git_text("-C", tree, "rev-parse", "HEAD"))
        self.assertEqual(self.git_text("-C", tree, "status", "--porcelain"), "")
        # A verdict and a clean tree (allow-empty): a second result, same machinery.
        clean = self.make_result_tree("clean-tree")
        partial = self.run_main("--return", KEY, "unit_b.2", "-C", clean, "--verdict", "PARTIAL")
        self.assertEqual(partial.returncode, 0, self.out(partial))
        branch_b = "refs/heads/lane-result/{}/unit_b.2".format(MAIN_ID)
        self.assertIn(branch_b, self.remote_refs())
        self.assertEqual(self.origin_git("log", "-1", "--format=%s", branch_b),
                         "lane: result unit_b.2 verdict=PARTIAL")
        # The registered checkout was never the place to commit.
        self.assertEqual(self.git_text("-C", self.workspace, "rev-parse", "HEAD"), self.base_sha)
        self.assertEqual(self.git_text("-C", self.workspace, "status", "--porcelain"), "")

    def test_return_refuses_the_registered_checkout(self):
        self.register()
        self.write(os.path.join(self.workspace, "result.txt"), "must stay uncommitted\n")
        result = self.run_main("--return", KEY, "unit-a", "-C", self.workspace)
        self.assertEqual(result.returncode, 8, self.out(result))
        self.assertEqual(self.remote_refs(), {})
        self.assertEqual(self.git_text("-C", self.workspace, "rev-parse", "HEAD"), self.base_sha)
        self.assertEqual(self.git_text("-C", self.workspace, "status", "--porcelain"), "?? result.txt")

    def test_return_refuses_a_bad_unit_name_and_an_unregistered_repository(self):
        self.register()
        tree = self.make_result_tree()
        head = self.git_text("-C", tree, "rev-parse", "HEAD")
        for unit in ("bad unit", "a/b", "x" * 49, "has$dollar", "semi;colon"):
            with self.subTest(unit=unit):
                result = self.run_main("--return", KEY, unit, "-C", tree)
                self.assertEqual(result.returncode, 8, self.out(result))
                self.assertEqual(self.git_text("-C", tree, "rev-parse", "HEAD"), head, "a refusal must not commit")
        result = self.run_main("--return", "nobody/none", "unit-a", "-C", tree)
        self.assertEqual(result.returncode, 8, self.out(result))
        self.assertEqual([ref for ref in self.remote_refs() if "lane-result" in ref], [])
        ok = self.run_main("--return", KEY, "x" * 48, "-C", tree)
        self.assertEqual(ok.returncode, 0, "a 48 character unit name is allowed\n" + self.out(ok))

    def test_return_refuses_a_unit_name_git_cannot_use_in_a_branch_name(self):
        # These fit [A-Za-z0-9._-]{1,48} but `refs/heads/lane-result/<id>/<unit>` would not be a valid ref name.
        self.register()
        tree = self.make_result_tree()
        head = self.git_text("-C", tree, "rev-parse", "HEAD")
        self.write(os.path.join(tree, "result.txt"), "unit result\n")
        for unit in ("..", "a..b", ".hidden", "name.lock", "trailing."):
            with self.subTest(unit=unit):
                result = self.run_main("--return", KEY, unit, "-C", tree)
                self.assertEqual(result.returncode, 8, self.out(result))
                self.assertEqual(self.git_text("-C", tree, "rev-parse", "HEAD"), head, "a refusal must not commit")
        self.assertEqual([ref for ref in self.remote_refs() if "lane-result" in ref], [])

    # ===== 8. write-files =====

    def agent_files(self):
        return sorted(name for name in os.listdir(AGENTS)
                      if re.fullmatch(r"lane-(haiku|sonnet|opus)-[a-z]+\.md", name))

    def make_target(self, name="target"):
        target = os.path.join(self.root, name)
        os.makedirs(target)
        self.git("init", "-q", target)
        self.write(os.path.join(target, "CLAUDE.md"), "# Project rules\n\nKeep it small.\n")
        self.git("-C", target, "add", "CLAUDE.md")
        self.git("-C", target, *IDENT, "commit", "-q", "-m", "init")
        return target

    def test_write_files_copies_the_lane_agents_and_commits_nothing(self):
        expected = self.agent_files()
        self.assertGreaterEqual(len(expected), 12)
        target = self.make_target()
        head = self.git_text("-C", target, "rev-parse", "HEAD")
        claude_md = self.read(os.path.join(target, "CLAUDE.md"))
        result = self.run_main("--write-files", target, real=True)
        self.assertEqual(result.returncode, 0, self.out(result))
        folder = os.path.join(target, ".claude", "agents")
        self.assertEqual(sorted(os.listdir(folder)), expected)
        for name in expected:
            self.assertEqual(self.read(os.path.join(folder, name)), self.read(os.path.join(AGENTS, name)), name)
            self.assertIn(name, result.stdout)
        for name in ("researcher.md", "scout.md", "verifier.md", "digest.md"):
            self.assertFalse(os.path.exists(os.path.join(folder, name)), name)
        # Nothing is committed or staged, and CLAUDE.md is the owner's to edit.
        self.assertEqual(self.git_text("-C", target, "rev-parse", "HEAD"), head)
        self.assertEqual(self.git_text("-C", target, "diff", "--cached", "--name-only"), "")
        self.assertEqual(self.git_text("-C", target, "status", "--porcelain"), "?? .claude/")
        self.assertEqual(self.read(os.path.join(target, "CLAUDE.md")), claude_md)
        # The lines the owner adds, and the pointer to cloud-notify.
        self.assertIn("CLAUDE.md, or AGENTS.md if that is the repository's instruction file", result.stdout)
        self.assertIn("orch:", result.stdout)
        self.assertIn("cloud-notify install --repo", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_write_files_second_run_reports_identical_and_a_changed_file_by_name(self):
        expected = self.agent_files()
        target = self.make_target()
        first = self.run_main("--write-files", target, real=True)
        self.assertEqual(first.returncode, 0, self.out(first))
        second = self.run_main("--write-files", target, real=True)
        self.assertEqual(second.returncode, 0, self.out(second))
        self.assertRegex(second.stdout.lower(), r"identical|unchanged")
        self.assertEqual(sorted(os.listdir(os.path.join(target, ".claude", "agents"))), expected)
        changed = os.path.join(target, ".claude", "agents", expected[0])
        self.write(changed, "locally edited\n")
        third = self.run_main("--write-files", target, real=True)
        self.assertEqual(third.returncode, 0, self.out(third))
        self.assertIn(expected[0], third.stdout)
        self.assertRegex(third.stdout.lower(), r"identical|unchanged")
        changed_line = next(line for line in third.stdout.splitlines() if expected[0] in line)
        self.assertNotRegex(changed_line.lower(), r"identical|unchanged")
        self.assertRegex(changed_line.lower(), r"changed|updated|wrote|written|overwr")
        self.assertEqual(self.git_text("-C", target, "diff", "--cached", "--name-only"), "")
        self.assertEqual(self.git_text("-C", target, "log", "--format=%s"), "init")

    def test_write_files_warns_when_git_ignores_the_agents_folder(self):
        target = self.make_target()
        self.write(os.path.join(target, ".gitignore"), ".claude/\n")
        result = self.run_main("--write-files", target, real=True)
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertIn("ignore", (result.stdout + result.stderr).lower())
        quiet = self.run_main("--write-files", self.make_target("target2"), real=True)
        self.assertEqual(quiet.returncode, 0, self.out(quiet))
        self.assertLess((quiet.stdout + quiet.stderr).lower().count("ignor"),
                        (result.stdout + result.stderr).lower().count("ignor"))

    def test_write_files_needs_an_existing_directory(self):
        result = self.run_main("--write-files", os.path.join(self.root, "does-not-exist"), real=True)
        self.assertNotEqual(result.returncode, 0, self.out(result))
        self.assertFalse(os.path.exists(os.path.join(self.root, "does-not-exist")))

    # ===== 8b. warnings about the committed notify and agent files =====

    def commit_files(self, files, message="notify files"):
        """Write `files` ({relative path: text}) into the workspace and commit them on main."""
        for name, text in files.items():
            path = os.path.join(self.workspace, *name.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self.write(path, text)
            self.git("-C", self.workspace, "add", name)
        self.git("-C", self.workspace, *IDENT, "commit", "-m", message)

    def commit_good_notify_files(self):
        self.commit_files({".claude/hooks/cloud-notify.py": "# hook\n",
                           ".claude/settings.json": '{"hooks": "' + HOOK_MARK + '"}\n',
                           ".claude/agents/lane-sonnet.md": "agent\n"})

    def commit_warnings(self, result):
        return [line for line in result.stderr.splitlines()
                if line.startswith("warning:") and ("notify" in line or "lane-*" in line or "committed" in line
                                                    or "git ignores" in line)]

    def test_dry_run_is_quiet_when_notify_and_agent_files_are_committed_and_registered(self):
        self.commit_good_notify_files()
        result = self.start("--dry-run")
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertEqual(self.commit_warnings(result), [], self.out(result))

    def test_dry_run_warns_and_goes_on_when_the_hook_file_is_not_committed(self):
        self.commit_files({".claude/settings.json": '{"hooks": "' + HOOK_MARK + '"}\n',
                           ".claude/agents/lane-sonnet.md": "agent\n"})
        result = self.start("--dry-run")
        self.assertEqual(result.returncode, 0, self.out(result))
        lines = self.commit_warnings(result)
        self.assertEqual(len(lines), 1, self.out(result))
        self.assertIn(HOOK_MARK + " is not committed", lines[0])
        self.assertIn("install --repo", lines[0])
        self.assertIn("then commit and push", lines[0])
        self.assertIn("cloud-notify", lines[0])

    def test_dry_run_warns_when_settings_json_does_not_register_the_hook(self):
        self.commit_files({".claude/hooks/cloud-notify.py": "# hook\n", ".claude/settings.json": "{}\n",
                           ".claude/agents/lane-sonnet.md": "agent\n"})
        result = self.start("--dry-run")
        self.assertEqual(result.returncode, 0, self.out(result))
        lines = self.commit_warnings(result)
        self.assertEqual(len(lines), 1, self.out(result))
        self.assertIn("does not register the hook", lines[0])
        self.assertIn("install --repo", lines[0])

    def test_dry_run_warns_when_settings_json_is_not_committed_at_all(self):
        self.commit_files({".claude/hooks/cloud-notify.py": "# hook\n", ".claude/agents/lane-sonnet.md": "agent\n"})
        result = self.start("--dry-run")
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertIn(".claude/settings.json is not committed", "\n".join(self.commit_warnings(result)))

    def test_dry_run_warns_when_no_agent_files_are_committed(self):
        self.commit_files({".claude/hooks/cloud-notify.py": "# hook\n",
                           ".claude/settings.json": '{"hooks": "' + HOOK_MARK + '"}\n'})
        result = self.start("--dry-run")
        self.assertEqual(result.returncode, 0, self.out(result))
        lines = self.commit_warnings(result)
        self.assertEqual(len(lines), 1, self.out(result))
        self.assertIn("--write-files", lines[0])
        self.assertIn("then commit and push", lines[0])

    def test_dry_run_warns_when_git_ignores_the_hook_or_an_agent_file(self):
        # cloud_preflight refuses a modified or untracked file, but an ignored one keeps the tree clean: the start
        # goes on, and only this warning says the VM will not get the file.
        self.commit_files({".gitignore": ".claude/hooks/\n.claude/agents/lane-new.md\n",
                           ".claude/settings.json": '{"hooks": "' + HOOK_MARK + '"}\n'})
        self.commit_files({".claude/agents/lane-sonnet.md": "agent\n"}, "agent")
        os.makedirs(os.path.join(self.workspace, ".claude", "hooks"), exist_ok=True)
        self.write(os.path.join(self.workspace, ".claude", "hooks", "cloud-notify.py"), "# hook\n")
        self.write(os.path.join(self.workspace, ".claude", "agents", "lane-new.md"), "agent\n")
        result = self.start("--dry-run")
        self.assertEqual(result.returncode, 0, self.out(result))
        text = "\n".join(self.commit_warnings(result))
        self.assertIn(HOOK_MARK + " is not committed", text)
        self.assertIn("git ignores .claude/hooks/cloud-notify.py in the checkout", text)
        self.assertIn("git ignores .claude/agents/lane-new.md in the checkout", text)
        self.assertIn("git check-ignore -v", text)

    def test_commit_warnings_report_a_failing_check_once_and_do_not_raise(self):
        lane = load_lane()
        outside = tempfile.mkdtemp(prefix="lane-not-a-repo-")  # outside every repository, so rev-parse fails
        self.addCleanup(shutil.rmtree, outside, True)
        stderr = io.StringIO()
        ceiling = {"PATH": self.env["PATH"], "GIT_CEILING_DIRECTORIES": os.path.dirname(outside)}
        with mock.patch.dict(os.environ, ceiling), contextlib.redirect_stderr(stderr):
            lane.main_commit_warnings(outside, {"base": "0" * 40})
        lines = stderr.getvalue().strip().splitlines()
        self.assertEqual(len(lines), 1, lines)
        self.assertTrue(lines[0].startswith("warning: could not check the committed notify files ("), lines)

    def test_a_real_start_runs_the_same_check_before_it_pushes(self):
        seen = self.start()
        self.assertEqual(seen.returncode, 0, self.out(seen))
        self.assertIn("will not notify your phone", seen.stderr)
        self.assertIn("--write-files", seen.stderr)
        lane = load_lane()
        order = []
        with mock.patch.object(lane, "main_commit_warnings", side_effect=lambda *a: order.append("check")), \
                mock.patch.object(lane, "cloud_push_branch", side_effect=lambda *a, **k: order.append("push")
                                  or (_ for _ in ()).throw(lane.LaneError("stop here", 8))), \
                mock.patch.object(lane, "cloud_preflight", return_value={
                    "base": "a" * 40, "branch": "main", "remote_url": "https://github.com/acme/shop.git",
                    "remote_existed": True, "env": None}), \
                mock.patch.dict(os.environ, self.env), contextlib.redirect_stderr(io.StringIO()):
            parser = lane.build_main_parser()
            opts = parser.parse_args(["-C", self.workspace, "-b", self.brief])
            with self.assertRaises(lane.LaneError):
                lane.main_start(parser, opts)
        self.assertEqual(order[:2], ["check", "push"], order)

    def test_the_hook_mark_matches_the_one_cloud_notify_uses(self):
        script = os.path.join(ROOT, "bin", "cloud-notify")
        loader = importlib.machinery.SourceFileLoader("cloud_notify_for_mark", script)
        notify = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(notify)
        self.assertEqual(load_lane().MAIN_HOOK_MARK, notify.HOOK_MARK)
        self.assertEqual(HOOK_MARK, notify.HOOK_MARK)

    def test_the_kit_install_step_fits_with_a_long_brief_and_the_real_policy(self):
        # The install step makes the head longer; a 15,000-character brief must still fit the command line.
        lane = load_lane()
        self.assertEqual(lane.MAIN_KIT_BRANCH, "lane-main/kit")
        brief = ("y" * 99 + "\n") * 150
        self.assertEqual(len(brief), 15000)
        prompt = lane.main_prompt(MAIN_ID, RELEASE, SYNTHETIC_POLICY, brief, KEY)
        self.check_main_prompt(prompt, MAIN_ID, brief)
        with open(POLICY, encoding="utf-8") as handle:
            real = handle.read()
        prompt = lane.main_prompt(MAIN_ID, policy_release(real), real, brief, KEY)
        self.assertIn(KIT_INSTALL_LINE, prompt)
        self.assertLess(len(prompt), lane.MAIN_PROMPT_LIMIT)

    # ===== 9. side refusal =====

    def cloud_dry_run(self, *extra, lane="sonnet", effort="high"):
        return self.run_lane(lane, ["--cloud", "--dry-run"] + list(extra), effort=effort)

    def test_a_live_mirror_refuses_a_side_session_unless_a_reason_is_given(self):
        self.register(url="https://claude.ai/code/session_MirrorLive")
        refused = self.cloud_dry_run()
        self.assertEqual(refused.returncode, 8, self.out(refused))
        self.assertIn("https://claude.ai/code/session_MirrorLive", refused.stderr)
        self.assertIn("--side", refused.stderr)
        self.assertIn("subagent", refused.stderr.lower())
        self.assertEqual(self.remote_refs(), {})
        allowed = self.cloud_dry_run("--side", "needs its own VM")
        self.assertEqual(allowed.returncode, 0, self.out(allowed))
        self.assertIn("needs its own VM", allowed.stdout)
        self.assertIn("cloud preflight: PASS", allowed.stdout)
        self.assertEqual(self.remote_refs(), {})
        # Other Claude lanes too.
        for lane, effort in (("haiku", "high"), ("opus", "xhigh")):
            with self.subTest(lane=lane):
                self.assertEqual(self.cloud_dry_run(lane=lane, effort=effort).returncode, 8)

    def test_a_side_session_prompt_starts_with_the_side_label(self):
        self.register()
        result = self.cloud_dry_run("--side", "needs its own VM", "--tag", "docs-pass")
        self.assertEqual(result.returncode, 0, self.out(result))
        launch = json.loads(next(line for line in result.stdout.splitlines() if line.startswith("launch: "))[8:])
        prompt = launch[launch.index("--cloud") + 1]
        self.assertTrue(prompt.startswith("Kit side session - {} - docs-pass\n\n".format(KEY)), prompt[:100])
        # Without a live mirror the same run is a plain worker.
        self.write_mains({})
        plain = self.cloud_dry_run("--tag", "docs-pass")
        self.assertEqual(plain.returncode, 0, self.out(plain))
        launch = json.loads(next(line for line in plain.stdout.splitlines() if line.startswith("launch: "))[8:])
        self.assertTrue(launch[launch.index("--cloud") + 1].startswith("Kit worker - {} - docs-pass\n\n".format(KEY)))

    def test_verify_runs_never_need_the_side_flag(self):
        self.register()
        result = self.cloud_dry_run("--verify")
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertIn("cloud preflight: PASS", result.stdout)

    def test_without_a_live_mirror_no_side_flag_is_needed_and_a_given_one_is_ignored_with_a_note(self):
        plain = self.cloud_dry_run()
        self.assertEqual(plain.returncode, 0, self.out(plain))
        self.assertNotIn("--side", plain.stderr)
        self.register(status="replaced")
        replaced = self.cloud_dry_run()
        self.assertEqual(replaced.returncode, 0, self.out(replaced))
        self.write_mains({})
        noted = self.cloud_dry_run("--side", "no mirror here")
        self.assertEqual(noted.returncode, 0, self.out(noted))
        self.assertIn("side", noted.stderr.lower())
        self.assertTrue(noted.stderr.strip())

    def test_a_mirror_of_another_repository_does_not_block_this_one(self):
        self.write_mains({"other/repo": self.entry()})
        result = self.cloud_dry_run()
        self.assertEqual(result.returncode, 0, self.out(result))

    def test_side_reason_is_stored_in_meta_for_a_real_run(self):
        self.register()
        outdir = os.path.join(self.root, "run output")
        result = self.run_lane("sonnet", ["--cloud", "--side", "needs its own VM", "--outdir", outdir])
        self.assertEqual(result.returncode, 0, self.out(result))
        meta = self.read_json(os.path.join(outdir, "meta.json"))
        self.assertEqual(meta["cloud"]["side_reason"], "needs its own VM")
        self.assertEqual(meta["place"], "cloud")

    def test_side_without_cloud_or_with_a_bad_reason_is_a_usage_error(self):
        result = self.run_lane("sonnet", ["--side", "because", "--dry-run"])
        self.assertEqual(result.returncode, 2, self.out(result))
        self.assertEqual(self.remote_refs(), {})
        for reason in ("", "x" * 201):
            with self.subTest(length=len(reason)):
                bad = self.cloud_dry_run("--side", reason)
                self.assertEqual(bad.returncode, 2, self.out(bad))
        longest = self.cloud_dry_run("--side", "y" * 200)
        self.assertEqual(longest.returncode, 0, self.out(longest))

    # ===== 10. worker prompt =====

    def worker_prompt(self, meta_path):
        cmd = self.read_json(meta_path)["cmd"]
        return cmd[cmd.index("--cloud") + 1]

    def test_worker_prompt_says_the_main_session_holds_the_kit(self):
        outdir = os.path.join(self.root, "worker out")
        result = self.run_lane("sonnet", ["--cloud", "--outdir", outdir], env={"FAKE_CLAUDE_MODE": "noop"})
        self.assertEqual(result.returncode, 3, self.out(result))
        prompt = self.worker_prompt(os.path.join(outdir, "meta.json"))
        self.assertIn(WORKER_SENTENCE, " ".join(prompt.split()))
        self.assertIn("CLOUD RUN", prompt)
        self.assertIn("You are a worker dispatched by lane", prompt)

    def test_verify_prompt_says_the_same(self):
        outdir = os.path.join(self.root, "verify out")
        result = self.run_lane("sonnet", ["--cloud", "--verify", "--outdir", outdir], env={"FAKE_CLAUDE_MODE": "noop"})
        self.assertEqual(result.returncode, 0, self.out(result))
        prompt = self.worker_prompt(os.path.join(outdir, "meta.json"))
        self.assertIn(WORKER_SENTENCE, " ".join(prompt.split()))

    def test_worker_sentence_follows_worker_block_in_both_prompts(self):
        lane = load_lane()
        block = " ".join(lane.WORKER_BLOCK.split())
        for verify in (False, True):
            with self.subTest(verify=verify):
                flat = " ".join(lane.claude_cloud_prompt("Brief.", "run-1", "sonnet", verify, "default").split())
                self.assertIn(block, flat)
                self.assertIn(WORKER_SENTENCE, flat)
                self.assertGreater(flat.index(WORKER_SENTENCE), flat.index(block))
                self.assertEqual(flat.count("Your session is a worker."), 1)

    # ===== 11. CLI: policy problems =====

    def test_a_policy_character_that_cannot_be_folded_stops_lane_main(self):
        self.write_policy(SYNTHETIC_POLICY.replace("BRIEFS_SENTINEL:", "BRIEFS_SENTINEL § 5:"))
        result = self.start("--dry-run")
        self.assertEqual(result.returncode, 8, self.out(result))
        self.assertTrue("§" in result.stderr or "00a7" in result.stderr.lower(), self.out(result))
        self.assertEqual(self.remote_refs(), {})
        self.assertFalse(os.path.exists(self.record))

    def test_non_ascii_in_unused_policy_sections_does_not_matter_and_the_rest_is_folded(self):
        self.write_policy(SYNTHETIC_POLICY.replace("MAIN_SENTINEL:", "MAIN_SENTINEL – it’s “the”"))
        result = self.start("--dry-run")
        self.assertEqual(result.returncode, 0, self.out(result))
        names = [name for name in os.listdir(self.state) if name.startswith("main-prompt-")]
        prompt = self.read(os.path.join(self.state, names[0]))
        self.assertTrue(prompt.isascii())
        self.assertIn("MAIN_SENTINEL - it's \"the\"", prompt)

    # ===== 12. regressions found in review =====

    DEVICE_UNITS = ("CON", "nul", "COM1", "lpt9", "con.txt", "Aux.md", "PRN")
    PLAIN_UNITS = ("con1", "console", "unit-a", "com10", "nullable", "aux-1", "com0")

    def direct_lane(self):
        """bin/lane imported into this process, with this test's environment (state dir, fake git) in os.environ."""
        patcher = mock.patch.dict(os.environ, self.env)
        patcher.start()
        self.addCleanup(patcher.stop)
        return load_lane()

    def mains_litter(self):
        """The temp files and the lock that a mains.json write must not leave in the state folder."""
        return sorted(name for name in os.listdir(self.state)
                      if name == "mains.json.lock" or re.fullmatch(r"mains\.json\..+\.tmp", name))

    def stdout_of(self, function, *args):
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            returned = function(*args)
        return returned, captured.getvalue()

    # --- 12.1 --return and a checkout that is a subdirectory of its work tree ---

    def test_return_refuses_a_registered_checkout_that_is_a_subdirectory_of_the_work_tree(self):
        sub = os.path.join(self.workspace, "sub")
        os.makedirs(sub)
        self.write(os.path.join(sub, "tracked.txt"), "tracked\n")
        self.git("-C", self.workspace, "add", "sub/tracked.txt")
        self.git("-C", self.workspace, *IDENT, "commit", "-q", "-m", "add sub")
        head = self.git_text("-C", self.workspace, "rev-parse", "HEAD")
        self.register(checkout=os.path.realpath(sub))
        self.write(os.path.join(self.workspace, "result.txt"), "must stay uncommitted\n")
        for directory in (self.workspace, sub):
            with self.subTest(dir=os.path.relpath(directory, self.workspace)):
                result = self.run_main("--return", KEY, "unit-a", "-C", directory)
                self.assertEqual(result.returncode, 8, self.out(result))
                self.assertIn("registered checkout", result.stderr)
                self.assertEqual(self.git_text("-C", self.workspace, "rev-parse", "HEAD"), head,
                                 "a refusal must not commit")
                self.assertEqual(self.git_text("-C", self.workspace, "status", "--porcelain"), "?? result.txt",
                                 "a refusal must not stage anything")
                self.assertEqual(self.remote_refs(), {}, "a refusal must not push")

    # --- 12.2 the side refusal fails closed ---

    def test_a_corrupt_mains_file_refuses_a_side_session_unless_a_reason_is_given(self):
        os.makedirs(self.state)
        contents = (('{"version": 1, "mains": {"local/demo-proj": {"main_id": "2026', "truncated JSON"),
                    ("", "empty file"), ("[]", "not an object"), ('{"version": 1}', "no mains"))
        for text, what in contents:
            with self.subTest(file=what):
                self.write(self.mains_path, text)
                refused = self.cloud_dry_run()
                self.assertEqual(refused.returncode, 8, self.out(refused))
                self.assertIn("mains.json", refused.stderr)
                self.assertIn("--side", refused.stderr)
                self.assertEqual(self.remote_refs(), {})
                allowed = self.cloud_dry_run("--side", "worker VM anyway")
                self.assertEqual(allowed.returncode, 0, self.out(allowed))
                self.assertIn("cloud preflight: PASS", allowed.stdout)
                self.assertIn("warning", allowed.stderr.lower())
                self.assertIn("mains.json", allowed.stderr)
                verify = self.cloud_dry_run("--verify")
                self.assertEqual(verify.returncode, 0, self.out(verify))
                self.assertIn("cloud preflight: PASS", verify.stdout)
                self.assertEqual(self.read(self.mains_path), text, "the check must not touch the file")

    # --- 12.3 writes of mains.json ---

    def test_start_and_forget_leave_no_temp_or_lock_file_behind(self):
        started = self.start()
        self.assertEqual(started.returncode, 0, self.out(started))
        self.assertIn(KEY, self.read_mains()["mains"])
        self.assertEqual(self.mains_litter(), [])
        forgot = self.run_main("--forget", KEY)
        self.assertEqual(forgot.returncode, 0, self.out(forgot))
        self.assertEqual(self.read_mains()["mains"], {})
        self.assertEqual(self.mains_litter(), [])

    def test_watch_leaves_no_temp_or_lock_file_behind_when_it_updates_last_seen(self):
        start = self.open_session()
        plain = self.cloud_commit("cloud task result", files={"result.txt": "work\n"})
        self.assertEqual(self.read_mains()["mains"][KEY]["last_seen"], start)
        result = self.watch("--timeout", "1")
        self.assertEqual(result.returncode, 124, self.out(result))
        self.assertEqual(self.read_mains()["mains"][KEY]["last_seen"], plain, "the watch must have written")
        self.assertEqual(self.mains_litter(), [])

    def test_two_concurrent_updaters_do_not_lose_each_others_changes(self):
        lane = self.direct_lane()
        self.write_mains({"owner/one": self.entry(main_id="id-one"), "owner/two": self.entry(main_id="id-two")})
        barrier = threading.Barrier(2)
        errors = []

        def update(key, prefix):
            try:
                barrier.wait(timeout=10)
                for number in range(30):
                    lane.main_update_entry(key, **{"{}_{}".format(prefix, number): number,
                                                   "last_seen": "{}-{}".format(prefix, number)})
            except BaseException as exc:  # reported by the test thread
                errors.append(exc)

        switch = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)
        self.addCleanup(sys.setswitchinterval, switch)
        threads = [threading.Thread(target=update, args=(key, prefix), daemon=True)
                   for key, prefix in (("owner/one", "a"), ("owner/two", "b"))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=120)
        self.assertFalse([thread for thread in threads if thread.is_alive()], "an updater is stuck")
        self.assertEqual(errors, [])
        mains = self.read_mains()["mains"]
        for key, prefix in (("owner/one", "a"), ("owner/two", "b")):
            with self.subTest(key=key):
                self.assertEqual(mains[key]["last_seen"], prefix + "-29")
                self.assertEqual({name: value for name, value in mains[key].items() if name.startswith(prefix + "_")},
                                 {"{}_{}".format(prefix, number): number for number in range(30)})
        self.assertEqual(mains["owner/one"]["main_id"], "id-one")
        self.assertEqual(mains["owner/two"]["main_id"], "id-two")
        self.assertEqual(self.mains_litter(), [])

    def test_a_lock_file_older_than_30_seconds_is_taken_over(self):
        lane = self.direct_lane()
        self.register()
        lock = self.mains_path + ".lock"
        self.write(lock, "")
        old = time.time() - 60
        os.utime(lock, (old, old))
        lane.main_update_entry(KEY, last_seen="after-stale-lock")
        self.assertEqual(self.read_mains()["mains"][KEY]["last_seen"], "after-stale-lock")
        self.assertFalse(os.path.exists(lock), "the lock is released after the write")

    def test_a_stale_lock_file_does_not_stop_a_cli_call(self):
        self.register()
        lock = self.mains_path + ".lock"
        self.write(lock, "")
        old = time.time() - 60
        os.utime(lock, (old, old))
        result = self.run_main("--forget", KEY)
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertEqual(self.read_mains()["mains"], {})
        self.assertEqual(self.mains_litter(), [])

    def test_a_fresh_lock_file_makes_an_update_wait_and_then_fail_without_touching_anything(self):
        lane = self.direct_lane()
        self.register(last_seen="before")
        lock = self.mains_path + ".lock"
        self.write(lock, "")
        ticks = itertools.count(0, 4)  # a clock that jumps 4 s per look, so the 10 s wait ends at once
        clock = types.SimpleNamespace(monotonic=lambda: next(ticks), sleep=lambda seconds: None, time=time.time)
        with mock.patch.object(lane, "time", clock):
            with self.assertRaises(lane.LaneError) as caught:
                lane.main_update_entry(KEY, last_seen="must-not-be-written")
        self.assertEqual(caught.exception.code, 8)
        self.assertIn("locked", str(caught.exception))
        self.assertTrue(os.path.exists(lock), "a lock that is not ours stays")
        self.assertEqual(self.read_mains()["mains"][KEY]["last_seen"], "before")

    # --- 12.4 a replaced session's watch must not write into the new entry ---

    def test_update_entry_changes_only_the_entry_that_still_belongs_to_the_session(self):
        lane = self.direct_lane()
        new_id = "20261031-110000-main"
        self.register(main_id=new_id, last_seen="new-tip")
        lane.main_update_entry(KEY, main_id=MAIN_ID, last_seen="old-tip")
        self.assertEqual(self.read_mains()["mains"][KEY], self.entry(main_id=new_id, last_seen="new-tip"))
        lane.main_update_entry("nobody/none", main_id=new_id, last_seen="x")
        self.assertEqual(list(self.read_mains()["mains"]), [KEY], "an unknown key must not create an entry")
        lane.main_update_entry(KEY, main_id=new_id, last_seen="newer-tip")
        self.assertEqual(self.read_mains()["mains"][KEY], self.entry(main_id=new_id, last_seen="newer-tip"))
        lane.main_update_entry(KEY, last_seen="unconditional")
        self.assertEqual(self.read_mains()["mains"][KEY]["last_seen"], "unconditional")

    def test_a_poll_of_a_replaced_session_does_not_write_into_the_new_entry(self):
        lane = self.direct_lane()
        start = self.open_session()
        old_entry = self.read_mains()["mains"][KEY]
        self.cloud_commit("orch: STATUS 1: Old session news")
        new_id = "20261031-110000-main"
        self.register(branch="claude/second", main_id=new_id, last_seen="new-tip")
        before = self.read_mains()
        (seen, printed), output = self.stdout_of(lane.main_watch_check, KEY, old_entry, start)
        self.assertTrue(printed, "the old session's marker is still reported")
        self.assertIn("orch STATUS", output)
        self.assertEqual(self.read_mains(), before)

    # --- 12.5 --watch remembers the sha it read ---

    def test_watch_remembers_the_fetched_sha_when_ls_remote_was_older_and_prints_the_marker_once(self):
        lane = self.direct_lane()
        start = self.open_session()
        older = self.cloud_commit("orch: STATUS 1: First news")
        newer = self.cloud_commit("orch: STATUS 2: Second news")
        self.assertNotEqual(older, newer)
        entry = self.read_mains()["mains"][KEY]
        # ls-remote answered with `older`; by the time fetch ran the branch was at `newer`.
        with mock.patch.object(lane, "main_remote_tip", return_value=older):
            (seen, printed), output = self.stdout_of(lane.main_watch_check, KEY, entry, start)
        self.assertEqual(seen, newer)
        self.assertTrue(printed)
        self.assertEqual(self.read_mains()["mains"][KEY]["last_seen"], newer)
        shown = [line for line in output.splitlines() if line.startswith("orch ")]
        self.assertEqual([line.split()[1] for line in shown], ["STATUS", "STATUS"], output)
        self.assertEqual([line.split()[2] for line in shown], [older[:12], newer[:12]])
        # The next polls: ls-remote reports the real tip, then a stale answer again. Nothing is shown twice.
        for reported in (newer, older):
            with self.subTest(ls_remote=reported[:12]):
                with mock.patch.object(lane, "main_remote_tip", return_value=reported):
                    (seen_again, printed_again), again = self.stdout_of(
                        lane.main_watch_check, KEY, self.read_mains()["mains"][KEY], seen)
                self.assertEqual((seen_again, printed_again), (newer, False))
                self.assertEqual(again, "")
                self.assertEqual(self.read_mains()["mains"][KEY]["last_seen"], newer)

    # --- 12.6 the LOCAL next: line ---

    def test_the_local_next_line_joins_its_three_commands_with_and_and_never_with_a_semicolon(self):
        self.open_session()
        self.cloud_commit("orch: LOCAL lane unit-a luna/gpt-6-luna/high .lane-main/briefs/unit-a.md",
                          files={".lane-main/briefs/unit-a.md": "Goal: write the thing.\n"})
        result = self.watch("--timeout", "20")
        self.assertEqual(result.returncode, 0, self.out(result))
        next_lines = [line for line in result.stdout.splitlines() if line.startswith("  next: ")]
        self.assertEqual(len(next_lines), 1, result.stdout)
        command = next_lines[0][len("  next: "):]
        self.assertNotIn(" ; ", command)
        # A marker from a mirror started before 2026-10-31.16 names no class: no placeholder, which a shell would
        # read as a redirection, and a note instead.
        self.assertNotIn("<", command)
        self.assertNotIn("--class", command)
        self.assertIn("  note: the marker names no class", result.stdout)
        self.assertNotIn(";", command)
        parts = command.split(" && ")
        self.assertEqual(len(parts), 3, command)
        self.assertRegex(parts[0], r"^git -C .+ worktree add --detach .+ refs/lane-main/{}$".format(MAIN_ID))
        self.assertIn(" luna ", parts[1])
        self.assertIn("--tag orch-{}-unit-a".format(MAIN_ID), parts[1])
        self.assertRegex(parts[2], r" main --return \S+ unit-a -C ")

    def test_main_local_next_builds_one_chain_of_three_commands(self):
        lane = load_lane()
        for checkout in (os.path.join(self.root, "plain"), os.path.join(self.root, "with space & more")):
            with self.subTest(checkout=os.path.basename(checkout)):
                entry = self.entry(checkout=checkout)
                command = lane.main_local_next(KEY, entry, "unit-a", "luna/gpt-6-luna/high",
                                               os.path.join(self.root, "brief one.md"))
                self.assertNotIn(" ; ", command)
                self.assertEqual(len(command.split(" && ")), 3, command)

    # --- 12.7 unit names the platform maps to devices ---

    def test_the_unit_matcher_rejects_device_names_and_accepts_their_lookalikes(self):
        lane = load_lane()
        for name in self.DEVICE_UNITS:
            with self.subTest(refused=name):
                self.assertIsNone(lane.MAIN_UNIT_RE.fullmatch(name))
        for name in self.PLAIN_UNITS:
            with self.subTest(accepted=name):
                self.assertIsNotNone(lane.MAIN_UNIT_RE.fullmatch(name))
        for name in ("", "a/b", "bad unit", "x" * 49):
            with self.subTest(refused=name):
                self.assertIsNone(lane.MAIN_UNIT_RE.fullmatch(name))
        self.assertIsNotNone(lane.MAIN_UNIT_RE.fullmatch("x" * 48))

    def test_return_refuses_a_device_name_before_it_commits_anything(self):
        self.register()
        tree = self.make_result_tree()
        head = self.git_text("-C", tree, "rev-parse", "HEAD")
        self.write(os.path.join(tree, "result.txt"), "unit result\n")
        for unit in self.DEVICE_UNITS:
            with self.subTest(unit=unit):
                result = self.run_main("--return", KEY, unit, "-C", tree)
                self.assertEqual(result.returncode, 8, self.out(result))
                self.assertIn("bad unit name", result.stderr)
                self.assertEqual(self.git_text("-C", tree, "rev-parse", "HEAD"), head, "a refusal must not commit")
                self.assertEqual(self.git_text("-C", tree, "status", "--porcelain"), "?? result.txt")
        self.assertEqual([ref for ref in self.remote_refs() if "lane-result" in ref], [])
        ok = self.run_main("--return", KEY, "con1", "-C", tree)
        self.assertEqual(ok.returncode, 0, "con1 is not a device name\n" + self.out(ok))

    def test_return_refuses_a_unit_git_cannot_name_before_it_adds_or_commits_in_dir(self):
        self.register()
        tree = self.make_result_tree()
        self.write(os.path.join(tree, "result.txt"), "unit result\n")
        log = self.git_text("-C", tree, "log", "--all", "--format=%H")
        refs = self.git_text("-C", tree, "for-each-ref")
        for unit in ("..", ".hidden", "name.lock"):
            with self.subTest(unit=unit):
                result = self.run_main("--return", KEY, unit, "-C", tree)
                self.assertEqual(result.returncode, 8, self.out(result))
                self.assertIn("bad unit name", result.stderr)
                self.assertEqual(self.git_text("-C", tree, "log", "--all", "--format=%H"), log)
                self.assertEqual(self.git_text("-C", tree, "for-each-ref"), refs)
                self.assertEqual(self.git_text("-C", tree, "status", "--porcelain"), "?? result.txt",
                                 "the refusal comes before `git add -A`")
        self.assertEqual(self.remote_refs(), {})

    def test_watch_shows_a_local_marker_with_a_device_unit_as_bad_and_saves_no_brief(self):
        self.open_session()
        subjects = {}
        for unit in self.DEVICE_UNITS + ("con1", "console"):
            subject = "orch: LOCAL lane {} luna/gpt-6-luna/high .lane-main/briefs/{}.md".format(unit, unit)
            subjects[unit] = (self.cloud_commit(subject, files={".lane-main/briefs/{}.md".format(unit): "Goal.\n"}),
                              subject)
        result = self.watch("--timeout", "20")
        self.assertEqual(result.returncode, 0, self.out(result))
        lines = result.stdout.splitlines()
        for unit in self.DEVICE_UNITS:
            with self.subTest(unit=unit):
                sha, subject = subjects[unit]
                self.assertIn("orch BAD {} {}".format(sha[:12], subject), lines)
        self.assertEqual([line.split()[3] for line in lines if line.startswith("orch LOCAL ")],
                         ["unit=con1", "unit=console"], result.stdout)
        saved = sorted(name for _, _, names in os.walk(os.path.join(self.state, "mains")) for name in names)
        self.assertEqual(saved, ["con1.md", "console.md"])


class MainBlockTests(unittest.TestCase):
    """main_block and main_policy_text called directly (no subprocess)."""

    def setUp(self):
        self.lane = load_lane()

    def raw_policy(self):
        with open(POLICY, "r", encoding="utf-8") as stream:
            return stream.read()

    def synthetic(self, **replacements):
        text = SYNTHETIC_POLICY
        for old, new in replacements.items():
            self.assertIn(old, text)
            text = text.replace(old, new)
        return text

    def test_mirror_prompt_with_its_label_still_passes_the_prompt_checks(self):
        prompt = self.lane.main_prompt(MAIN_ID, RELEASE, SYNTHETIC_POLICY, "Brief.\n", "acme/shop")
        self.assertEqual(prompt.split("\n")[:3], ["Kit mirror - acme/shop", "", self.lane.main_block(
            MAIN_ID, RELEASE, SYNTHETIC_POLICY).split("\n")[0]])
        self.lane.main_check_prompt(prompt, "test")
        self.assertTrue(prompt.isascii())
        for phrase in self.lane.MAIN_FORBIDDEN_PHRASES:
            self.assertNotIn(phrase, self.lane.cloud_title("mirror", "acme/shop"))
        # A long repository name keeps the label to 100 characters.
        long_prompt = self.lane.main_prompt(MAIN_ID, RELEASE, SYNTHETIC_POLICY, "Brief.\n", "o/" + "r" * 300)
        self.assertLessEqual(len(long_prompt.split("\n")[0]), 100)

    def test_block_from_the_real_policy(self):
        raw = self.raw_policy()
        if not re.search(r"^## Main cloud sessions", raw, re.MULTILINE):
            self.skipTest("POLICY.md section not written yet")
        release = policy_release(raw)
        self.assertTrue(release, "POLICY.md has no `Claude Usage Optimizer version: X.` line")
        text = self.lane.main_policy_text()
        self.assertIsInstance(text, str)
        self.assertIn("## Briefs", text)
        self.assertIn("## Main cloud sessions", text)
        block = self.lane.main_block(MAIN_ID, release, text)
        self.assertTrue(block.isascii(), [c for c in block if ord(c) > 127][:5])
        self.assertLess(len(block), 30000)
        self.assertIn("## Briefs", block)
        self.assertIn("## Main cloud sessions", block)
        self.assertIn("release {}".format(release), block)
        heading = next(line for line in raw.splitlines() if line.startswith("## Main cloud sessions"))
        if heading.isascii():
            self.assertIn(heading, block)
        after_briefs = raw.split("\n## Briefs", 1)[1].split("\n", 1)[1]
        first_line = next(line for line in after_briefs.splitlines() if line.strip())
        if first_line.isascii():
            self.assertIn(first_line, block)
        self.assertNotIn("CLOUD RUN", block)
        self.assertNotIn("You are a worker dispatched by lane", block)
        self.assertIn("(main id {})".format(MAIN_ID), block)
        self.assertIn("lane-main/picks", block)
        # Sections the main does not get.
        for title in ("## Routing, in order", "## Meters", "## Explore"):
            self.assertNotIn(title, block)

    def test_main_policy_text_reads_the_kits_policy(self):
        raw = self.raw_policy()
        text = self.lane.main_policy_text()
        self.assertIsInstance(text, str)
        self.assertIn("## Briefs", text)
        if re.search(r"^## Main cloud sessions", raw, re.MULTILINE):
            self.assertIn("## Main cloud sessions", text)

    def test_block_takes_the_two_sections_and_the_head_fields(self):
        block = self.lane.main_block(MAIN_ID, RELEASE, SYNTHETIC_POLICY)
        self.assertTrue(block.isascii())
        self.assertIn("(main id {})".format(MAIN_ID), block)
        self.assertIn('git commit --allow-empty -m "orch: START {}" && git push -u origin HEAD'.format(MAIN_ID), block)
        self.assertIn("lane-main/picks", block)
        self.assertIn("lane-result/{}/".format(MAIN_ID), block)
        self.assertIn("KIT POLICY (from POLICY.md, release {}; it addresses you)".format(RELEASE), block)
        for line in MARKER_LINES:
            self.assertIn(line, block)
        main_section = SYNTHETIC_POLICY.split("## Main cloud sessions", 1)[1].split("\n## ", 1)[0]
        briefs_section = SYNTHETIC_POLICY.split("\n## Briefs", 1)[1].split("\n## ", 1)[0]
        self.assertIn("## Main cloud sessions" + main_section.rstrip(), block)
        self.assertIn("## Briefs" + briefs_section.rstrip(), block)
        self.assertLess(block.index("## Main cloud sessions"), block.index("## Briefs"))
        self.assertGreater(block.index("## Main cloud sessions"), block.index("KIT POLICY"))
        for other in ("PRINCIPLE_SENTINEL", "MEASURE_SENTINEL", "METERS_SENTINEL"):
            self.assertNotIn(other, block)
        self.assertNotIn("CLOUD RUN", block)
        self.assertNotIn("You are a worker dispatched by lane", block)

    def test_block_accepts_whatever_follows_the_main_section_name_on_the_heading(self):
        text = self.synthetic(**{"## Main cloud sessions (from 2099-01-02.3)": "## Main cloud sessions"})
        block = self.lane.main_block(MAIN_ID, RELEASE, text)
        self.assertIn("## Main cloud sessions\n", block)
        self.assertIn("MAIN_SENTINEL", block)
        text = self.synthetic(**{"## Main cloud sessions (from 2099-01-02.3)": "## Main cloud sessions, from now on"})
        self.assertIn("## Main cloud sessions, from now on", self.lane.main_block(MAIN_ID, RELEASE, text))

    def test_block_folds_quotes_dashes_dots_and_signs_to_ascii(self):
        text = self.synthetic(**{
            "MAIN_SENTINEL: you are the mirror of one project.":
                "Quotes: “double” and ‘single’ and it’s fine.\n"
                "Dashes: a – b — c.\n"
                "Dots: wait… done.\n"
                "Signs: 2 × 3, n ≥ 1, n ≤ 5.\n"
                "Dot: left · right.\n"
                "MAIN_SENTINEL: end of the folded lines.",
            "BRIEFS_SENTINEL: every brief has four parts.": "BRIEFS_SENTINEL: the brief’s “goal” — one line."})
        block = self.lane.main_block(MAIN_ID, RELEASE, text)
        self.assertTrue(block.isascii(), [c for c in block if ord(c) > 127][:5])
        for line in ("Quotes: \"double\" and 'single' and it's fine.",
                     "Dashes: a - b - c.",
                     "Dots: wait... done.",
                     "Signs: 2 x 3, n >= 1, n <= 5.",
                     "Dot: left - right.",
                     "BRIEFS_SENTINEL: the brief's \"goal\" - one line."):
            self.assertIn(line, block)

    def test_block_folds_the_approximately_sign_to_a_tilde(self):
        text = self.synthetic(**{"Rule one of the section.": "Rule one takes ≈ 5 minutes."})
        self.assertIn("Rule one takes ~ 5 minutes.", self.lane.main_block(MAIN_ID, RELEASE, text))

    def test_block_ignores_non_ascii_outside_the_two_sections(self):
        # The synthetic Principle section holds an arrow and a section sign.
        self.assertIn("→", SYNTHETIC_POLICY)
        block = self.lane.main_block(MAIN_ID, RELEASE, SYNTHETIC_POLICY)
        self.assertTrue(block.isascii())

    def test_block_refuses_a_character_it_cannot_fold_and_names_it(self):
        for where, old in (("main", "Rule one of the section."), ("briefs", "1. The goal.")):
            with self.subTest(section=where):
                text = self.synthetic(**{old: old + " See § 4."})
                with self.assertRaises(self.lane.LaneError) as caught:
                    self.lane.main_block(MAIN_ID, RELEASE, text)
                self.assertEqual(caught.exception.code, 8)
                message = str(caught.exception)
                self.assertTrue("§" in message or "00a7" in message.lower(), message)

    def test_block_text_never_names_a_cloud_worker(self):
        # cloud-notify tells workers from the main by these two phrases.
        block = self.lane.main_block(MAIN_ID, RELEASE, SYNTHETIC_POLICY)
        self.assertNotIn("CLOUD RUN", block)
        self.assertNotIn("You are a worker dispatched by lane", block)
        self.assertIn("MAIN CLOUD SESSION", block)


class MainPrintedCommandTests(unittest.TestCase):
    """Commands lane main prints are pasted into a shell, on Windows Git Bash or cmd.exe (2026-10-31.16)."""

    def test_windows_arguments_print_with_forward_slashes_and_bash_quoting(self):
        lane = load_lane()
        with mock.patch.object(lane, "IS_WINDOWS", True):
            self.assertEqual(lane.main_quote("C:\\Users\\me\\kit\\bin\\lane.py"), "C:/Users/me/kit/bin/lane.py")
            self.assertEqual(lane.main_quote("C:\\with space & more\\x"), '"C:/with space & more/x"')
            self.assertEqual(lane.main_quote("owner/repo"), "owner/repo")
        with mock.patch.object(lane, "IS_WINDOWS", False):
            self.assertEqual(lane.main_quote("/a b/c"), "'/a b/c'")
            self.assertEqual(lane.main_quote("a\\b"), "'a\\b'")

    def test_tool_commands_start_with_this_python_unless_the_script_runs_by_itself(self):
        lane = load_lane()
        python = subprocess.list2cmdline([sys.executable.replace("\\", "/")])
        with mock.patch.object(lane, "IS_WINDOWS", True):
            # A shebang does nothing on Windows, and Git Bash resolves `env python3` to the Store stub.
            self.assertEqual(lane.main_tool_command("C:\\kit\\bin\\cloud-notify"), python + " C:/kit/bin/cloud-notify")
        with mock.patch.object(lane, "IS_WINDOWS", False):
            missing = os.path.join(os.path.dirname(SCRIPT), "no-such-tool")
            self.assertEqual(lane.main_tool_command(missing),
                             shlex.quote(sys.executable) + " " + shlex.quote(missing))
            if os.name != "nt" and os.access(SCRIPT, os.X_OK):
                self.assertEqual(lane.main_tool_command(SCRIPT), shlex.quote(SCRIPT))


class MainLocalClassTests(unittest.TestCase):
    """The LOCAL marker carries the unit's class from 2026-10-31.16."""

    def test_a_local_marker_may_name_a_known_class(self):
        lane = load_lane()
        base = "orch: LOCAL lane unit-a luna/gpt-6-luna/high .lane-main/briefs/unit-a.md"
        kind, fields = lane.main_parse_marker(base + " class=substantive")
        self.assertEqual((kind, fields["class"]), ("LOCAL", "substantive"))
        kind, fields = lane.main_parse_marker(base)
        self.assertEqual((kind, fields["class"]), ("LOCAL", None))
        for bad in (" class=bogus", " class=", " class=substantive extra"):
            with self.subTest(bad=bad):
                self.assertEqual(lane.main_parse_marker(base + bad)[0], "BAD")

    def test_the_next_line_passes_the_class_when_the_marker_names_one(self):
        lane = load_lane()
        entry = {"checkout": os.path.join(os.sep, "work", "shop"), "main_id": "20261031-100000-main"}
        brief = os.path.join(os.sep, "state", "unit-a.md")
        named = lane.main_local_next("acme/shop", entry, "unit-a", "luna/gpt-6-luna/high", brief, "substantive")
        self.assertIn(" --class substantive --tag orch-20261031-100000-main-unit-a", named)
        unnamed = lane.main_local_next("acme/shop", entry, "unit-a", "luna/gpt-6-luna/high", brief)
        self.assertNotIn("--class", unnamed)
        self.assertNotIn("<", unnamed)

    def test_the_mirror_prompt_asks_for_the_class_in_local(self):
        with open(SCRIPT, encoding="utf-8") as stream:
            text = stream.read()
        self.assertIn("orch: LOCAL lane <unit> <lane>/<effort> <brief path> class=<class>", text)
        self.assertIn('.lane-main/briefs/<unit>.md class=<class>" && git push', text)


class MainTwoPartArmTests(unittest.TestCase):
    """LOCAL and REVIEW markers may name the arm as <lane>/<effort>; the catalog supplies the model."""

    ENTRY = {"checkout": os.path.join(os.sep, "work", "shop"), "main_id": "20261101-100000-main"}
    BRIEF = os.path.join(os.sep, "state", "unit-a.md")

    def catalog_lane(self, directory):
        arms = [{"lane": "opus", "model": "claude-opus-5-5", "effort": "medium", "status": "active"},
                {"lane": "gemini", "model": "gemini-3.8-flash-low", "effort": "low", "status": "active"},
                {"lane": "sonnet", "model": "claude-sonnet-5-5", "effort": "high", "status": "active"},
                {"lane": "sonnet", "model": "claude-sonnet-5-6", "effort": "high", "status": "active"}]
        path = os.path.join(directory, "arms.json")
        with open(path, "w", encoding="utf-8") as stream:
            json.dump({"arms": arms}, stream)
        env = {"LANES_ARMS": path, "LANES_ARMS_LOCAL": os.path.join(directory, "none.json")}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        return load_lane()

    def test_the_parser_takes_a_two_part_arm_and_refuses_a_one_part_arm(self):
        lane = load_lane()
        local = "orch: LOCAL lane u1 {} .lane-main/briefs/u1.md class=substantive"
        kind, fields = lane.main_parse_marker(local.format("opus/medium"))
        self.assertEqual((kind, fields["arm"]), ("LOCAL", "opus/medium"))
        self.assertEqual(lane.main_parse_marker(local.format("opus/claude-opus-5-5/medium"))[0], "LOCAL")
        self.assertEqual(lane.main_parse_marker(local.format("opus"))[0], "BAD")
        review = "orch: REVIEW u1 accepted arm={} class=substantive min=3 tok=-/- usd=-"
        self.assertEqual(lane.main_parse_marker(review.format("opus/medium"))[0], "REVIEW")
        self.assertEqual(lane.main_parse_marker(review.format("opus"))[0], "BAD")

    def test_the_parser_reads_arms_as_lane_stats_imports_them(self):
        lane = load_lane()
        review = "orch: REVIEW u1 accepted arm={} class=substantive min=3 tok=-/- usd=-"
        # An arm of - stands only beside via=local, whose run is found by its tag.
        self.assertEqual(lane.main_parse_marker(review.format("-"))[0], "BAD")
        self.assertEqual(lane.main_parse_marker(review.format("-") + " via=subagent")[0], "BAD")
        self.assertEqual(lane.main_parse_marker(review.format("-") + " via=local")[0], "REVIEW")
        # Two or three parts, each at most 64 characters.
        self.assertEqual(lane.main_parse_marker(review.format("sonnet/a/b/high"))[0], "BAD")
        self.assertEqual(lane.main_parse_marker(review.format("sonnet/{}/high".format("m" * 64)))[0], "REVIEW")
        self.assertEqual(lane.main_parse_marker(review.format("sonnet/{}/high".format("m" * 65)))[0], "BAD")
        local = "orch: LOCAL lane u1 {} .lane-main/briefs/u1.md class=substantive"
        self.assertEqual(lane.main_parse_marker(local.format("sonnet/a/b/high"))[0], "BAD")

    def test_local_next_resolves_the_model_from_the_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            lane = self.catalog_lane(directory)
            opus = lane.main_local_next("acme/shop", self.ENTRY, "unit-a", "opus/medium", self.BRIEF)
            self.assertIn(" -e medium", opus)
            self.assertNotIn(" -m ", opus)
            gemini = lane.main_local_next("acme/shop", self.ENTRY, "unit-a", "gemini/low", self.BRIEF)
            self.assertIn(" -m gemini-3.8-flash-low", gemini)
            self.assertNotIn(" -e ", gemini)
            three = lane.main_local_next("acme/shop", self.ENTRY, "unit-a", "opus/claude-opus-5-5/medium", self.BRIEF)
            self.assertEqual(three, opus)

    def test_the_watch_prints_bad_for_a_two_part_arm_the_catalog_cannot_resolve(self):
        with tempfile.TemporaryDirectory() as directory:
            lane = self.catalog_lane(directory)
            state = os.path.join(directory, "state")
            for arm in ("opus/low", "sonnet/high"):
                with self.subTest(arm=arm), mock.patch.object(lane, "main_dir", lambda key: state), \
                        mock.patch.object(lane, "main_save_brief", side_effect=AssertionError("brief saved")):
                    subject = "orch: LOCAL lane unit-a {} .lane-main/briefs/unit-a.md class=substantive".format(arm)
                    out = io.StringIO()
                    with contextlib.redirect_stdout(out):
                        lane.main_watch_report("acme/shop", self.ENTRY, [("a" * 40, subject, "")])
                    self.assertEqual(out.getvalue().splitlines(), [
                        "orch BAD {} {}".format("a" * 12, subject),
                        "  the arm {} names no single catalog arm; ask the mirror for lane/model/effort".format(arm)])

    def test_the_mirror_head_asks_for_lane_and_effort(self):
        with open(SCRIPT, encoding="utf-8") as stream:
            text = stream.read()
        self.assertIn("arm=<lane>/<effort>", text)
        self.assertNotIn("arm=<arm>", text)
        self.assertIn("In LOCAL and REVIEW markers write it as\n  <lane>/<effort>, without the model", text)
        self.assertIn("With via=local, arm may be -.", text)


class MainPublishKitTests(unittest.TestCase):
    """A failed kit push is a warning, never a failed start."""

    def test_an_os_error_from_the_push_is_a_warning(self):
        lane = load_lane()
        for error in (lane.LaneError("push refused"), PermissionError("temp folder not writable")):
            def push(path, error=error):
                raise error
            err = io.StringIO()
            with mock.patch.object(lane, "main_push_kit", push), contextlib.redirect_stderr(err), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertIsNone(lane.main_publish_kit("/nowhere", False))
            self.assertIn("warning: the kit was not published to lane-main/kit", err.getvalue())


class MainTokensGrammarTests(unittest.TestCase):
    """The REVIEW marker's tok field has one grammar in bin/lane and in lane-stats import-orch.

    A marker that lane-stats imports must not show as BAD in `lane main --watch`, and the reverse. Both parsers
    run the same table of subjects, so a change to either grammar fails here.
    """

    CASES = (
        ("12/34", True), ("-/-", True), ("123/-", True), ("-/45", True), ("-", True), ("999999999999/0", True),
        ("12", False), ("/", False), ("a/b", False), ("1/2/3", False), ("", False), ("-/", False),
        ("1234567890123/1", False), ("1/-x", False),
    )

    def test_bin_lane_and_lane_stats_accept_the_same_tok_values(self):
        lane = load_lane()
        loader = importlib.machinery.SourceFileLoader("lane_stats_tok_tested", os.path.join(ROOT, "bin", "lane-stats"))
        stats = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(stats)
        for tok, valid in self.CASES:
            subject = ("orch: REVIEW unit-a accepted arm=luna/gpt-6-luna/high class=mechanical min=3 tok={} usd=0.5"
                       .format(tok))
            with self.subTest(tok=tok):
                lane_kind = lane.main_parse_marker(subject)[0]
                stats_matched = stats.ORCH_REVIEW.fullmatch(subject) is not None
                self.assertEqual(lane_kind == "REVIEW", valid)
                self.assertEqual(stats_matched, valid)


if __name__ == "__main__":
    unittest.main()
