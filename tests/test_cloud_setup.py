import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "bin", "cloud-setup")
WINDOWS = os.name == "nt"


def find_bash():
    # On Windows `bash` on PATH may be WSL's, which cannot see this checkout's Windows paths.
    if WINDOWS:
        for candidate in (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files (x86)\Git\bin\bash.exe"):
            if os.path.exists(candidate):
                return candidate
        return None
    return shutil.which("bash")


BASH = find_bash()
GIT = shutil.which("git")
PREFIX = "usage-optimizer setup: "
GIT_IDENTITY = ["-c", "user.name=t", "-c", "user.email=t@localhost"]


def kit_version():
    with open(os.path.join(ROOT, "POLICY.md"), encoding="utf-8") as stream:
        match = re.search(r"^Claude Usage Optimizer version: (\d{4}-\d{2}-\d{2}\.\d+)\.", stream.read(4096), re.M)
    return match.group(1)


@unittest.skipIf(WINDOWS, "cloud-setup targets the Linux cloud VM")
@unittest.skipIf(BASH is None or GIT is None, "bash or git is not installed")
class CloudSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = self.temp.name
        self.home = os.path.join(root, "home")
        self.setup_dir = os.path.join(root, "opt", "kit")
        self.log = os.path.join(root, "log", "setup.log")
        self.repos = os.path.join(root, "repos")
        os.makedirs(self.home)
        os.makedirs(self.repos)
        self.prefix = os.path.join(self.home, ".claude", "usage-optimizer")

    def tearDown(self):
        self.temp.cleanup()

    def env(self, extra=None):
        # Only the variables the tests set: the owner's own USAGE_OPTIMIZER_* settings must not leak in.
        env = {key: value for key, value in os.environ.items() if not key.startswith("USAGE_OPTIMIZER_")}
        env.pop("CLAUDE_CONFIG_DIR", None)
        env.update({"HOME": self.home, "USERPROFILE": self.home, "USAGE_OPTIMIZER_SKIP_CLI_CHECK": "1",
                    "USAGE_OPTIMIZER_SETUP_DIR": self.setup_dir, "USAGE_OPTIMIZER_SETUP_LOG": self.log,
                    "USAGE_OPTIMIZER_SETUP_REPOS": self.repos,
                    "USAGE_OPTIMIZER_KIT_PUBLIC_REPO": "off"})
        env.update(extra or {})
        return env

    def git(self, *args, cwd):
        return subprocess.run([GIT, *GIT_IDENTITY, *args], cwd=cwd, env=self.env(), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, encoding="utf-8", errors="replace", timeout=120,
                              check=True).stdout

    def make_kit(self, folder):
        """A git repository holding the kit's tracked files, copied from the working tree, plus bin/cloud-setup
        (new files are untracked until committed, so it is listed by name)."""
        listed = subprocess.run([GIT, "-C", ROOT, "ls-files", "-z"], stdout=subprocess.PIPE, check=True,
                                timeout=120).stdout.decode("utf-8").split("\0")
        for name in sorted(set(filter(None, listed)) | {"bin/cloud-setup"}):
            source = os.path.join(ROOT, *name.split("/"))
            if not os.path.isfile(source):
                continue
            target = os.path.join(folder, *name.split("/"))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(source, target)
        self.git("-c", "init.defaultBranch=main", "init", "-q", cwd=folder)
        self.git("add", "-A", cwd=folder)
        self.git("commit", "-q", "-m", "Kit", cwd=folder)
        return folder

    def run_script(self, args=(), env_extra=None, path=None):
        env = self.env(env_extra)
        if path is not None:
            env["PATH"] = path
        return subprocess.run([BASH, SCRIPT, *args], cwd=self.home, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, encoding="utf-8", errors="replace", timeout=400, check=False)

    def run_script_at(self, script, args=()):
        return subprocess.run([BASH, script, *args], cwd=self.home, env=self.env(), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, encoding="utf-8", errors="replace", timeout=120, check=False)

    def installed_policy(self):
        return os.path.join(self.prefix, "POLICY.md")

    def assert_setup_lines(self, result):
        lines = [line for line in result.stdout.splitlines() if line]
        self.assertTrue(lines, result.stdout)
        for line in lines:
            self.assertTrue(line.startswith(PREFIX), line)
        return lines

    def android_env(self, kit, command_log, fakebin):
        sdk = os.path.join(self.temp.name, "android-sdk")
        profile = os.path.join(self.temp.name, "profile.d")
        links = os.path.join(self.temp.name, "local-bin")
        os.makedirs(fakebin, exist_ok=True)

        def command(name, body):
            path = os.path.join(fakebin, name)
            with open(path, "w", encoding="utf-8", newline="\n") as stream:
                stream.write("#!/bin/sh\n" + body)
            os.chmod(path, 0o755)

        command("java", 'echo java "$@" >>"$COMMAND_LOG"\n'
                'case "$*" in *XshowSettings*) echo "    java.home = /fake/jdk" >&2;; '
                '*) echo \'openjdk version "17.0.1"\' >&2;; esac\n')
        command("apt-get", 'echo apt-get "$@" >>"$COMMAND_LOG"\n')
        command("curl", 'echo curl "$@" >>"$COMMAND_LOG"\n'
                'while [ "$1" ]; do [ "$1" = --output ] && { shift; : >"$1"; }; shift; done\n')
        command("sha256sum", 'echo sha256sum "$@" >>"$COMMAND_LOG"\ncat >/dev/null\n')
        command("unzip", 'echo unzip "$@" >>"$COMMAND_LOG"\n'
                'while [ "$1" ]; do [ "$1" = -d ] && { shift; out=$1; }; shift; done\n'
                'mkdir -p "$out/cmdline-tools/bin"\n'
                'cat >"$out/cmdline-tools/bin/sdkmanager" <<\'EOF\'\n#!/bin/sh\necho sdkmanager "$@" >>"$COMMAND_LOG"\nEOF\n'
                'chmod +x "$out/cmdline-tools/bin/sdkmanager"\n'
                'cp "$out/cmdline-tools/bin/sdkmanager" "$out/cmdline-tools/bin/avdmanager"\n')
        return {"USAGE_OPTIMIZER_KIT_URL": kit, "USAGE_OPTIMIZER_ANDROID": "1",
                "USAGE_OPTIMIZER_ANDROID_SDK": sdk,
                "USAGE_OPTIMIZER_ANDROID_PROFILE_DIR": profile,
                "USAGE_OPTIMIZER_ANDROID_BIN_DIR": links, "COMMAND_LOG": command_log,
                "PATH": fakebin + os.pathsep + os.environ["PATH"]}, sdk, profile, links

    # (a) the file itself
    def test_script_is_executable_ascii_small_and_parses(self):
        with open(SCRIPT, "rb") as stream:
            data = stream.read()
        self.assertLess(len(data), 65536)
        data.decode("ascii")
        self.assertNotIn(b"\r", data)
        if not WINDOWS:
            self.assertTrue(os.access(SCRIPT, os.X_OK))
        result = subprocess.run([BASH, "-n", SCRIPT], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                encoding="utf-8", timeout=60, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    # (b) --print fills both config lines and changes nothing else
    def test_print_fills_both_lines_and_keeps_the_rest(self):
        result = self.run_script(["--print", "--repo", "owner/name", "--ref", "main"])
        self.assertEqual(result.returncode, 0, result.stderr)
        with open(SCRIPT, encoding="utf-8", newline="") as stream:
            original = stream.read().split("\n")
        printed = result.stdout.split("\n")
        self.assertEqual(len(printed), len(original))
        changed = [(old, new) for old, new in zip(original, printed) if old != new]
        self.assertEqual(changed, [('KIT_REPO_DEFAULT=""', 'KIT_REPO_DEFAULT="owner/name"'),
                                   ('KIT_REF_DEFAULT=""', 'KIT_REF_DEFAULT="main"')])
        output = os.path.join(self.home, "printed.sh")
        with open(output, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(result.stdout)
        check = subprocess.run([BASH, "-n", output], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               encoding="utf-8", timeout=60, check=False)
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertLess(len(result.stdout.encode("utf-8")), 65536)

    # (c) a bad repository is refused before anything is printed
    def test_print_refuses_a_bad_repo(self):
        result = self.run_script(["--print", "--repo", "bad;repo"])
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("--repo", result.stderr)

    def test_print_android_options_and_refuses_bad_package(self):
        result = self.run_script(["--print", "--repo", "owner/name", "--android",
                                  "--android-packages", "platform-tools platforms;android-35"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('ANDROID_DEFAULT="1"', result.stdout.splitlines())
        self.assertIn('ANDROID_PACKAGES_DEFAULT="platform-tools platforms;android-35"', result.stdout.splitlines())
        bad = self.run_script(["--print", "--repo", "owner/name", "--android-packages", "ok bad/package"])
        self.assertEqual((bad.returncode, bad.stdout), (2, ""))
        self.assertIn("--android-packages", bad.stderr)

        implied = self.run_script(["--print", "--repo", "owner/name", "--android-packages", "platform-tools"])
        self.assertEqual(implied.returncode, 0, implied.stderr)
        self.assertIn('ANDROID_DEFAULT="1"', implied.stdout.splitlines())
        wildcard = self.run_script(["--print", "--repo", "owner/name", "--android-packages", "*"])
        self.assertEqual((wildcard.returncode, wildcard.stdout), (2, ""))

    def test_print_refuses_a_bad_ref_and_unknown_options(self):
        bad_ref = self.run_script(["--print", "--repo", "owner/name", "--ref", "bad ref"])
        self.assertEqual((bad_ref.returncode, bad_ref.stdout), (2, ""))
        self.assertIn("--ref", bad_ref.stderr)
        unknown = self.run_script(["--frobnicate"])
        self.assertEqual((unknown.returncode, unknown.stdout), (2, ""))
        self.assertIn("unknown option", unknown.stderr)

    # (d) the repository comes from source.json's checkout, else from the script's own checkout
    def test_print_takes_the_repo_from_source_json_then_from_the_script_checkout(self):
        kit = self.make_kit(os.path.join(self.home, "kit"))
        self.git("remote", "add", "origin", "https://github.com/other/kit.git", cwd=kit)
        checkout = os.path.join(self.home, "checkout")
        os.makedirs(checkout)
        self.git("init", "-q", cwd=checkout)
        self.git("remote", "add", "origin", "git@github.com:owner/name.git", cwd=checkout)
        with open(os.path.join(kit, "source.json"), "w", encoding="utf-8") as stream:
            json.dump({"checkout": checkout, "installed_at": "2026-10-31T00:00:00Z"}, stream)
        result = self.run_script_at(os.path.join(kit, "bin", "cloud-setup"), ["--print", "--ref", "main"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('KIT_REPO_DEFAULT="owner/name"', result.stdout.splitlines())

        os.remove(os.path.join(kit, "source.json"))
        result = self.run_script_at(os.path.join(kit, "bin", "cloud-setup"), ["--print"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('KIT_REPO_DEFAULT="other/kit"', result.stdout.splitlines())

    # (e) setup from the local kit repository installs the kit; a second run keeps it installed
    def test_setup_installs_the_kit_from_a_local_repository_and_reruns(self):
        kit = self.make_kit(os.path.join(self.temp.name, "kit"))
        extra = {"USAGE_OPTIMIZER_KIT_URL": kit}
        first = self.run_script(env_extra=extra)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertTrue(os.path.isfile(self.installed_policy()))
        lines = self.assert_setup_lines(first)
        summary = [line for line in lines if "install.sh exit 0" in line]
        self.assertEqual(len(summary), 1, lines)
        self.assertIn(kit_version(), summary[0])
        with open(self.log, encoding="utf-8") as stream:
            self.assertIn(summary[0], stream.read().splitlines())

        second = self.run_script(env_extra=extra)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertTrue(os.path.isfile(self.installed_policy()))
        self.assertTrue(any("install.sh exit 0" in line for line in self.assert_setup_lines(second)))

    # (f) nothing reachable and no project clones: exit 0, not installed
    def test_unreachable_url_and_no_project_clones_leave_the_kit_out(self):
        result = self.run_script(env_extra={"USAGE_OPTIMIZER_KIT_URL": os.path.join(self.temp.name, "missing.git")})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_setup_lines(result)
        self.assertIn("not installed", result.stdout)
        self.assertFalse(os.path.exists(self.installed_policy()))
        self.assertFalse(os.path.exists(self.setup_dir))
        self.assertFalse(os.path.exists(self.setup_dir + ".new"))

    # (g) source 2: the lane-main/kit branch of a project clone
    def test_lane_main_kit_branch_of_a_project_clone_is_the_fallback(self):
        work = self.make_kit(os.path.join(self.temp.name, "work"))
        self.git("branch", "lane-main/kit", cwd=work)
        bare = os.path.join(self.temp.name, "origin.git")
        self.git("clone", "-q", "--bare", work, bare, cwd=self.temp.name)
        project = os.path.join(self.repos, "project-a")
        self.git("clone", "-q", "file://" + bare, project, cwd=self.temp.name)
        result = self.run_script(env_extra={"USAGE_OPTIMIZER_KIT_URL": os.path.join(self.temp.name, "missing.git")})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(os.path.isfile(self.installed_policy()))
        self.assertIn("lane-main/kit of project-a", result.stdout)

    def matching_project(self, ref=None):
        work = self.make_kit(os.path.join(self.temp.name, "matching-work"))
        if ref:
            self.git("branch", ref, cwd=work)
        owner = os.path.join(self.temp.name, "OWNER")
        os.makedirs(owner, exist_ok=True)
        bare = os.path.join(owner, "NAME.git")
        self.git("clone", "-q", "--bare", work, bare, cwd=self.temp.name)
        project = os.path.join(self.repos, "matching-project")
        self.git("clone", "-q", bare, project, cwd=self.temp.name)
        return bare, project

    def test_matching_origin_installs_its_default_branch(self):
        self.matching_project()
        result = self.run_script(env_extra={"USAGE_OPTIMIZER_KIT_REPO": "owner/name",
                                            "USAGE_OPTIMIZER_KIT_URL": os.path.join(self.temp.name, "missing")})
        self.assertTrue(os.path.isfile(self.installed_policy()), result.stdout + result.stderr)
        self.assertIn("origin is the kit repository", result.stdout)

    def test_matching_origin_installs_the_requested_branch(self):
        self.matching_project("release-test")
        result = self.run_script(env_extra={"USAGE_OPTIMIZER_KIT_REPO": "OWNER/NAME",
                                            "USAGE_OPTIMIZER_KIT_REF": "release-test",
                                            "USAGE_OPTIMIZER_KIT_URL": os.path.join(self.temp.name, "missing")})
        self.assertTrue(os.path.isfile(self.installed_policy()), result.stdout + result.stderr)
        self.assertIn("origin is the kit repository", result.stdout)

    def test_matching_origin_uses_allowed_local_ref_when_fetch_fails(self):
        bare, project = self.matching_project()
        shutil.rmtree(bare)
        result = self.run_script(env_extra={"USAGE_OPTIMIZER_KIT_REPO": "owner/name",
                                            "USAGE_OPTIMIZER_KIT_URL": os.path.join(self.temp.name, "missing")})
        self.assertTrue(os.path.isfile(self.installed_policy()), result.stdout + result.stderr)
        self.assertIn("fetch from", result.stdout)
        self.assertIn("local copy refs/remotes/origin/HEAD used", result.stdout)

    def test_matching_origin_does_not_use_an_arbitrary_remote_ref(self):
        bare, project = self.matching_project("topic")
        self.git("remote", "set-head", "origin", "-d", cwd=project)
        for ref in ("master", "main"):
            self.git("update-ref", "-d", "refs/remotes/origin/" + ref, cwd=project)
        self.git("fetch", "origin", "topic:refs/remotes/origin/topic", cwd=project)
        shutil.rmtree(bare)
        result = self.run_script(env_extra={"USAGE_OPTIMIZER_KIT_REPO": "owner/name",
                                            "USAGE_OPTIMIZER_KIT_URL": os.path.join(self.temp.name, "missing")})
        self.assertFalse(os.path.exists(self.installed_policy()), result.stdout)
        self.assertIn("no allowed local remote-tracking ref", result.stdout)

    def test_nonmatching_origin_is_not_used_as_a_default_branch(self):
        self.matching_project()
        result = self.run_script(env_extra={"USAGE_OPTIMIZER_KIT_REPO": "different/repository",
                                            "USAGE_OPTIMIZER_KIT_URL": os.path.join(self.temp.name, "missing")})
        self.assertFalse(os.path.exists(self.installed_policy()), result.stdout)

    def test_public_releases_repository_is_the_last_source(self):
        public = self.make_kit(os.path.join(self.temp.name, "public"))
        result = self.run_script(env_extra={"USAGE_OPTIMIZER_KIT_URL": os.path.join(self.temp.name, "missing"),
                                            "USAGE_OPTIMIZER_KIT_PUBLIC_REPO": "public/releases",
                                            "USAGE_OPTIMIZER_KIT_PUBLIC_URL": public})
        self.assertTrue(os.path.isfile(self.installed_policy()), result.stdout + result.stderr)
        self.assertIn("public releases repository public/releases", result.stdout)

    def test_public_source_can_be_disabled(self):
        result = self.run_script(env_extra={"USAGE_OPTIMIZER_KIT_URL": os.path.join(self.temp.name, "missing"),
                                            "USAGE_OPTIMIZER_KIT_PUBLIC_REPO": "off"})
        self.assertEqual(result.returncode, 0)
        self.assertFalse(os.path.exists(self.installed_policy()))

    def test_public_url_credentials_are_redacted(self):
        url = "https://user:PUBLICSECRET@127.0.0.1:9/releases.git"
        result = self.run_script(env_extra={"USAGE_OPTIMIZER_KIT_URL": os.path.join(self.temp.name, "missing"),
                                            "USAGE_OPTIMIZER_KIT_PUBLIC_REPO": "public/releases",
                                            "USAGE_OPTIMIZER_KIT_PUBLIC_URL": url})
        with open(self.log, encoding="utf-8") as stream:
            text = result.stdout + result.stderr + stream.read()
        self.assertNotIn("PUBLICSECRET", text)

    # (h) PATH without git: exit 0 and the line says git is missing
    def test_setup_without_git_says_so_and_exits_zero(self):
        bindir = os.path.join(self.temp.name, "nogit-bin")
        os.makedirs(bindir)
        for directory in ("/usr/local/bin", "/usr/bin", "/bin"):
            if not os.path.isdir(directory):
                continue
            for name in os.listdir(directory):
                target = os.path.join(bindir, name)
                if name == "git" or os.path.lexists(target):
                    continue
                os.symlink(os.path.join(directory, name), target)
        if shutil.which("git", path=bindir) is not None:
            self.skipTest("git is installed in a folder that cannot be left off PATH")
        result = self.run_script(path=bindir)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("git is missing", result.stdout)
        self.assertFalse(os.path.exists(self.installed_policy()))

    # Found by the second reader: credentials, a .git suffix, a symlink, loose host matching, an unwritable folder.
    def script_checkout(self, name, origin):
        """A folder holding only bin/cloud-setup, as a git checkout whose origin is `origin`."""
        folder = os.path.join(self.temp.name, name)
        os.makedirs(os.path.join(folder, "bin"))
        shutil.copy2(SCRIPT, os.path.join(folder, "bin", "cloud-setup"))
        self.git("init", "-q", cwd=folder)
        self.git("remote", "add", "origin", origin, cwd=folder)
        return os.path.join(folder, "bin", "cloud-setup")

    def test_credentials_in_a_url_reach_neither_the_output_nor_the_log(self):
        offline = {key: "" for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY")}
        for url in ("https://x:SECRETPART@127.0.0.1:9/k.git", "https://x:SECRETPART/tail@127.0.0.1:9/k.git"):
            result = self.run_script(env_extra=dict(offline, USAGE_OPTIMIZER_KIT_URL=url))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("not installed", result.stdout)
            with open(self.log, encoding="utf-8") as stream:
                logged = stream.read()
            for text in (result.stdout, result.stderr, logged):
                self.assertNotIn("SECRETPART", text)

    def test_print_drops_a_dot_git_suffix(self):
        result = self.run_script(["--print", "--repo", "owner/name.git"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('KIT_REPO_DEFAULT="owner/name"', result.stdout.splitlines())

    def test_print_through_a_symlink_reads_the_real_checkout(self):
        script = self.script_checkout("linked", "https://github.com/owner/name.git")
        link_dir = os.path.join(self.temp.name, "links")
        os.makedirs(link_dir)
        link = os.path.join(link_dir, "cloud-setup")
        os.symlink(script, link)
        result = self.run_script_at(link, ["--print"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('KIT_REPO_DEFAULT="owner/name"', result.stdout.splitlines())

    def test_print_reads_only_github_hosts(self):
        cases = {"https://evil.example/github.com/x/y.git": None,
                 "https://github.com.evil.example/x/y.git": None,
                 "ssh://git@github.com:22/owner/name.git": "owner/name",
                 "https://token@github.com/owner/name": "owner/name"}
        for number, (origin, expected) in enumerate(sorted(cases.items())):
            result = self.run_script_at(self.script_checkout("host-%d" % number, origin), ["--print"])
            if expected is None:
                self.assertEqual((result.returncode, result.stdout), (2, ""), origin)
            else:
                self.assertEqual(result.returncode, 0, origin + result.stderr)
                self.assertIn('KIT_REPO_DEFAULT="%s"' % expected, result.stdout.splitlines(), origin)

    def test_an_unwritable_kit_folder_is_named_and_exits_zero(self):
        blocker = os.path.join(self.temp.name, "a-file")
        with open(blocker, "w", encoding="utf-8") as stream:
            stream.write("not a folder\n")
        result = self.run_script(env_extra={"USAGE_OPTIMIZER_SETUP_DIR": os.path.join(blocker, "kit"),
                                            "USAGE_OPTIMIZER_KIT_URL": os.path.join(self.temp.name, "missing.git")})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("cannot write", result.stdout)
        self.assertFalse(os.path.exists(self.installed_policy()))

    def test_android_setup_writes_environment_merges_settings_and_prefetches_gradle(self):
        kit = self.make_kit(os.path.join(self.temp.name, "android-kit"))
        commands = os.path.join(self.temp.name, "commands")
        extra, sdk, profile, links = self.android_env(kit, commands, os.path.join(self.temp.name, "fakebin"))
        settings = os.path.join(self.home, ".claude", "settings.json")
        os.makedirs(os.path.dirname(settings))
        with open(settings, "w", encoding="utf-8") as stream:
            json.dump({"keep": True, "env": {"OLD": "yes"}}, stream)
        gradle = os.path.join(self.repos, "app", "android", "gradlew")
        os.makedirs(os.path.dirname(gradle))
        with open(gradle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write('#!/bin/sh\necho gradlew "$@" >>"$COMMAND_LOG"\n')
        os.chmod(gradle, 0o755)
        result = self.run_script(env_extra=extra)
        self.assertEqual(result.returncode, 0, result.stderr)
        with open(commands, encoding="utf-8") as stream:
            recorded = stream.read()
        self.assertLess(recorded.index("curl "), recorded.index("unzip "))
        self.assertIn("sdkmanager --sdk_root=%s --install platform-tools platforms;android-35 build-tools;35.0.0" % sdk,
                      recorded)
        self.assertIn("gradlew --version --no-daemon", recorded)
        with open(os.path.join(profile, "android-sdk.sh"), encoding="utf-8") as stream:
            self.assertIn('export ANDROID_HOME="%s"' % sdk, stream.read())
        with open(settings, encoding="utf-8") as stream:
            data = json.load(stream)
        self.assertTrue(data["keep"])
        self.assertEqual(data["env"]["OLD"], "yes")
        self.assertEqual(data["env"]["ANDROID_SDK_ROOT"], sdk)
        self.assertTrue(os.path.islink(os.path.join(links, "sdkmanager")))

        before = recorded.count("curl ")
        rerun = self.run_script(env_extra=extra)
        self.assertEqual(rerun.returncode, 0, rerun.stderr)
        with open(commands, encoding="utf-8") as stream:
            self.assertEqual(stream.read().count("curl "), before)

    def test_android_checksum_or_download_failure_is_nonfatal_and_does_not_unzip(self):
        kit = self.make_kit(os.path.join(self.temp.name, "failure-kit"))
        for failure in ("checksum", "download"):
            commands = os.path.join(self.temp.name, failure + "-commands")
            fakebin = os.path.join(self.temp.name, failure + "-bin")
            extra, _, _, _ = self.android_env(kit, commands, fakebin)
            target = "sha256sum" if failure == "checksum" else "curl"
            with open(os.path.join(fakebin, target), "a", encoding="utf-8") as stream:
                stream.write("exit 1\n")
            result = self.run_script(env_extra=extra)
            self.assertEqual(result.returncode, 0, result.stderr)
            with open(commands, encoding="utf-8") as stream:
                self.assertNotIn("unzip ", stream.read())
            if failure == "download":
                self.assertIn("dl.google.com", result.stdout)
                self.assertIn("network access to Custom", result.stdout)

    def test_android_budget_writes_environment_before_skipping_download(self):
        commands = os.path.join(self.temp.name, "budget-commands")
        missing = os.path.join(self.temp.name, "missing-kit")
        extra, _, profile, _ = self.android_env(missing, commands, os.path.join(self.temp.name, "budget-bin"))
        extra["USAGE_OPTIMIZER_SETUP_BUDGET"] = "1"
        result = self.run_script(env_extra=extra)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("near the five-minute cache limit", result.stdout)
        self.assertTrue(os.path.isfile(os.path.join(profile, "android-sdk.sh")))
        with open(os.path.join(self.home, ".claude", "settings.json"), encoding="utf-8") as stream:
            self.assertIn("ANDROID_SDK_ROOT", json.load(stream)["env"])
        with open(commands, encoding="utf-8") as stream:
            self.assertNotIn("curl ", stream.read())

    def test_android_leaves_invalid_settings_unchanged_and_omits_empty_java_home(self):
        kit = self.make_kit(os.path.join(self.temp.name, "settings-kit"))
        commands = os.path.join(self.temp.name, "settings-commands")
        fakebin = os.path.join(self.temp.name, "settings-bin")
        extra, _, profile, _ = self.android_env(kit, commands, fakebin)
        java = os.path.join(fakebin, "java")
        with open(java, "w", encoding="utf-8", newline="\n") as stream:
            stream.write("#!/bin/sh\ncase \"$*\" in *XshowSettings*) :;; *) echo 'openjdk version \"17\"' >&2;; esac\n")
        os.chmod(java, 0o755)
        settings = os.path.join(self.home, ".claude", "settings.json")
        os.makedirs(os.path.dirname(settings))
        original = b"{not json\n"
        with open(settings, "wb") as stream:
            stream.write(original)
        result = self.run_script(env_extra=extra)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("does not parse", result.stdout)
        with open(settings, "rb") as stream:
            self.assertEqual(stream.read(), original)
        with open(os.path.join(profile, "android-sdk.sh"), encoding="utf-8") as stream:
            self.assertNotIn("JAVA_HOME", stream.read())


if __name__ == "__main__":
    unittest.main()
