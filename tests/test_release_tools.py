import hashlib
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from test_install_view import find_bash


ROOT = pathlib.Path(__file__).resolve().parents[1]
BASH = find_bash()


@unittest.skipIf(BASH is None, "Git Bash (or bash) is not installed")
class ReleaseToolsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.temp.name)
        self.home = self.base / "home"
        self.home.mkdir()
        self.kit = self.base / "kit"
        self.kit.mkdir()
        (self.kit / "tools").mkdir()
        for name in ("make-bundle.sh", "knowledge_scan.py", "knowledge-scan.allow",
                     "release_bundle.py", "diff-bundle.py", "check-release.py"):
            shutil.copy2(ROOT / "tools" / name, self.kit / "tools" / name)
        (self.kit / "skills").mkdir()
        (self.kit / "POLICY.md").write_text("Claude Usage Optimizer version: 9.8.7\n",
                                              encoding="utf-8")
        (self.kit / "arms.json").write_text('{"catalog_version": 1, "arms": []}\n',
                                             encoding="utf-8")
        (self.kit / "install.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.git("init", "-q")
        # A machine with core.autocrlf on would store these files with LF and check them out with CRLF.
        self.git("config", "core.autocrlf", "false")
        self.git("config", "user.email", "release-test@example.invalid")
        self.git("config", "user.name", "Release Test")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        self.build()
        self.bundle = self.kit / "dist" / "claude-usage-optimizer-bundle.sh"
        self.page = self.base / "page.html"
        self.page.write_text("<p>Claude Usage Optimizer version: 9.8.7</p>\n", encoding="utf-8")
        self.patterns = self.base / "patterns-empty"
        self.patterns.write_text("", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def env(self):
        value = os.environ.copy()
        value["HOME"] = str(self.home)
        return value

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.kit), *args], check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def command(self, script, *args):
        return subprocess.run([sys.executable, "-I", str(self.kit / "tools" / script), *map(str, args)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, env=self.env())

    def build(self):
        subprocess.run([BASH, str(self.kit / "tools" / "make-bundle.sh")], cwd=self.kit,
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env())

    def check(self, *extra):
        return self.command("check-release.py", "--kit", self.kit, "--bundle", self.bundle,
                            "--page", self.page, "--patterns", self.patterns, *extra)

    def test_identical(self):
        diff = self.command("diff-bundle.py", self.bundle, "--kit", self.kit)
        self.assertEqual(diff.returncode, 0, diff.stdout + diff.stderr)
        check = self.check()
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        self.assertNotIn("FAIL ", check.stdout)

    def test_added_removed_changed_and_final_newline(self):
        added = self.kit / "extra.txt"
        added.write_text("extra\n", encoding="utf-8")
        self.git("rm", "-q", "arms.json")
        changed = self.kit / "install.sh"
        changed.write_bytes(b"#!/bin/sh\necho changed")
        diff = self.command("diff-bundle.py", self.bundle, "--kit", self.kit)
        self.assertEqual(diff.returncode, 1)
        self.assertIn("added (1):\n  arms.json", diff.stdout)
        self.assertIn("removed (1):\n  extra.txt", diff.stdout)
        self.assertIn("changed (1):\n  install.sh", diff.stdout)
        self.assertNotEqual(hashlib.sha256(changed.read_bytes()).hexdigest(), "")

    def test_tampered_block_is_rejected(self):
        # Bytes, not text: on Windows write_text would also turn every LF into CRLF.
        content = self.bundle.read_bytes()
        content = content.replace(b'"catalog_version": 1', b'"catalog_version": 2', 1)
        self.bundle.write_bytes(content)
        result = self.command("diff-bundle.py", self.bundle, "--kit", self.kit)
        self.assertEqual(result.returncode, 2)
        self.assertIn("SHA-256 mismatch", result.stderr)

    def test_missing_final_newline_matches_builder_rule(self):
        (self.kit / "no-newline.txt").write_bytes(b"the builder adds one")
        (self.kit / "crlf.txt").write_bytes(b"first\r\nsecond\r\n")
        self.build()
        result = self.command("diff-bundle.py", self.bundle, "--kit", self.kit)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_crlf_working_copy_of_an_lf_file_fails(self):
        (self.kit / "lf.sh").write_bytes(b"#!/bin/sh\nexit 0\n")
        (self.kit / "stored-crlf.csv").write_bytes(b"a,b\r\n1,2\r\n")
        self.git("add", "lf.sh", "stored-crlf.csv")
        self.git("commit", "-qm", "line endings")
        (self.kit / "lf.sh").write_bytes(b"#!/bin/sh\r\nexit 0\r\n")
        self.build()
        result = self.check()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("FAIL eol:", result.stdout)
        self.assertIn("lf.sh", result.stdout)
        self.assertNotIn("stored-crlf.csv", result.stdout)
        (self.kit / "lf.sh").write_bytes(b"#!/bin/sh\nexit 0\n")
        self.build()
        result = self.check()
        self.assertIn("OK eol:", result.stdout)

    def test_replacement_character_fails(self):
        self.assertIn("OK replacement:", self.check().stdout)
        (self.kit / "notes.md").write_bytes("escape it (`\"\ufffd\"`)\n".encode("utf-8"))
        self.build()
        self.page.write_text("<p>Claude Usage Optimizer version: 9.8.7 \ufffd</p>\n", encoding="utf-8")
        result = self.check()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("FAIL replacement: U+FFFD (write it as an escape) in: page, notes.md", result.stdout)

    def test_untracked_shipped_file_fails_until_ignored(self):
        (self.kit / "error.log").write_text("auth: account_id=placeholder\n", encoding="utf-8")
        self.build()
        result = self.check()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("FAIL untracked: shipped but not tracked (commit or git-ignore): error.log", result.stdout)
        (self.kit / ".gitignore").write_text("error.log\n", encoding="utf-8")
        self.git("add", ".gitignore")
        self.git("commit", "-qm", "ignore logs")
        self.build()
        self.assertIn("OK untracked:", self.check().stdout)

    def test_extract_modes_and_guards(self):
        destination = self.base / "extracted"
        result = self.command("diff-bundle.py", self.bundle, "--kit", self.kit,
                              "--extract", destination)
        self.assertEqual(result.returncode, 0, result.stderr)
        if os.name != "nt":  # Windows keeps no executable bit.
            self.assertEqual((destination / "install.sh").stat().st_mode & 0o777, 0o755)
            self.assertEqual((destination / "POLICY.md").stat().st_mode & 0o777, 0o644)
        occupied = self.base / "occupied"
        occupied.mkdir()
        (occupied / "keep").touch()
        refused = self.command("diff-bundle.py", self.bundle, "--kit", self.kit,
                               "--extract", occupied)
        self.assertEqual(refused.returncode, 2)
        checkout = self.command("diff-bundle.py", self.bundle, "--kit", self.kit,
                                "--extract", self.kit / "newdir")
        self.assertEqual(checkout.returncode, 2)

    def test_catalog_stale_patterns_size_and_version(self):
        (self.kit / "arms.json").write_text(
            '{"catalog_version": 1, "nested": {"measured": null}}\n', encoding="utf-8")
        self.git("add", "arms.json")
        self.git("commit", "-qm", "bad catalog")
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL catalog:", result.stdout)
        self.assertIn("FAIL fresh:", result.stdout)
        patterns = self.base / "patterns"
        patterns.write_text("forbidden-secret\n", encoding="utf-8")
        (self.kit / "leak.txt").write_text("here forbidden-secret\n", encoding="utf-8")
        self.git("add", "leak.txt")
        self.git("commit", "-qm", "pattern hit")
        result = self.check("--patterns", patterns)
        self.assertIn("FAIL patterns: leak.txt:1 pattern#1", result.stdout)
        self.assertNotIn("forbidden-secret", result.stdout + result.stderr)
        result = self.check("--max-bytes", "10")
        self.assertIn("FAIL bundle:", result.stdout)
        self.page.write_text("wrong version", encoding="utf-8")
        result = self.check()
        self.assertIn("FAIL version:", result.stdout)

    def test_private_patterns_match_missing_and_invalid(self):
        missing = self.check()
        expected = self.home / ".config" / "lanes" / "private-patterns.txt"
        self.assertIn("WARN private: no private pattern list at {}; the release is not checked for "
                      "private text".format(expected), missing.stdout)

        expected.parent.mkdir(parents=True)
        expected.write_text("private-value\n", encoding="utf-8")
        (self.kit / "leak.txt").write_text("the private-value is here\n", encoding="utf-8")
        self.build()
        matched = self.check()
        self.assertEqual(matched.returncode, 1, matched.stdout + matched.stderr)
        self.assertIn("FAIL private: leak.txt:1 pattern#1", matched.stdout)
        self.assertNotIn("private-value", matched.stdout + matched.stderr)

        expected.write_text("[unterminated\n", encoding="utf-8")
        invalid = self.check()
        self.assertEqual(invalid.returncode, 1, invalid.stdout + invalid.stderr)
        self.assertIn("FAIL private: bad regular expression at pattern line 1", invalid.stdout)
        self.assertNotIn("unterminated", invalid.stdout + invalid.stderr)

    def test_exclusions_and_the_evidence_file(self):
        # findings/bundle-size-plan.md steps 1 and 2: .claude/ and a mod's tests stay out of the bundle, and the
        # Suite R rescore evidence goes to its own file; the builder and check-release read one list.
        # No __pycache__ in the fixture kit: it has no .gitignore, and the builder ships untracked files.
        writes_bytecode, sys.dont_write_bytecode = sys.dont_write_bytecode, True
        sys.path.insert(0, str(self.kit / "tools"))
        try:
            import release_bundle
        finally:
            sys.path.pop(0)
            sys.dont_write_bytecode = writes_bytecode
        self.assertEqual(self.check().returncode, 0)  # no evidence files and no evidence file: fine
        sources = {".claude/settings.json": "{}\n", "mods/demo/tests/a.test.ts": "test\n",
                   "private/notes.md": "private\n",
                   "public-repo/README-public.md": "preface\n",
                   "private/skills/example-pack/SKILL.md": "private\n",
                   "skills/example-pack/SKILL.md": "public\n",
                   "mods/demo/hooks/register.tsx": "hook\n"}
        for relative in release_bundle.EVIDENCE_FILES:
            sources[relative] = '{"row": 1}\n'
        for relative, text in sources.items():
            path = self.kit / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            # LF bytes, as the kit's .gitattributes keeps them: Git Bash drops a CR when it replays a heredoc.
            path.write_bytes(text.encode("utf-8"))
        self.git("add", ".")
        self.git("commit", "-qm", "excluded and evidence files")
        self.build()
        bundled = set(release_bundle.parse_bundle(str(self.bundle))["files"])
        self.assertIn("mods/demo/hooks/register.tsx", bundled)
        self.assertIn("skills/example-pack/SKILL.md", bundled)
        for relative in (".claude/settings.json", "mods/demo/tests/a.test.ts", "private/notes.md",
                         "private/skills/example-pack/SKILL.md", "public-repo/README-public.md") + release_bundle.EVIDENCE_FILES:
            self.assertNotIn(relative, bundled)
        evidence = self.kit / "dist" / release_bundle.EVIDENCE_NAME
        self.assertEqual(set(release_bundle.parse_bundle(str(evidence))["files"]),
                         set(release_bundle.EVIDENCE_FILES))
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OK evidence: ", result.stdout)
        diff = self.command("diff-bundle.py", evidence, "--kit", self.kit)
        self.assertEqual(diff.returncode, 0, diff.stdout + diff.stderr)
        # It extracts and verifies only: the destination has no install.sh, so an exec of it would fail.
        destination = self.base / "evidence-extract"
        env = self.env()
        # Forward slashes: GNU sha256sum escapes a path holding a backslash, which the check would read as a mismatch.
        env["USAGE_OPTIMIZER_DIR"] = destination.as_posix()
        run = subprocess.run([BASH, str(evidence)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, env=env)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertTrue((destination / release_bundle.EVIDENCE_FILES[0]).is_file())
        self.assertFalse((destination / "install.sh").exists())
        # A changed evidence file without a rebuild fails, while the main bundle stays fresh.
        (self.kit / release_bundle.EVIDENCE_FILES[1]).write_bytes(b'{"row": 2}\n')
        self.git("commit", "-qam", "changed evidence")
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL evidence: differing files: " + release_bundle.EVIDENCE_FILES[1], result.stdout)
        self.assertIn("OK fresh:", result.stdout)

    def test_installer_accepts_source_without_skill_folders(self):
        source = self.base / "source-without-skills"
        shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(".git", "dist"))
        shutil.rmtree(source / "private" / "skills")
        if (source / "skills").exists():
            shutil.rmtree(source / "skills")
        env = self.env()
        env["USAGE_OPTIMIZER_SKIP_CLI_CHECK"] = "1"
        result = subprocess.run([BASH, str(source / "install.sh"), "--dry-run"], cwd=self.home,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
