import importlib.util
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("publish_public", ROOT / "tools" / "publish-public.py")
publish_public = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publish_public)


class PublishPublicTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.temp.name)
        self.origin = self.base / "claude-usage-optimizer-releases.git"
        subprocess.run(["git", "init", "--bare", "-q", str(self.origin)], check=True)
        seed = self.base / "seed"
        subprocess.run(["git", "init", "-q", str(seed)], check=True)
        (seed / "old.txt").write_text("old\n", encoding="utf-8")
        self.git(seed, "add", ".")
        self.git(seed, "-c", "user.name=Test", "-c", "user.email=test@localhost",
                 "commit", "-qm", "seed")
        self.git(seed, "remote", "add", "origin", str(self.origin))
        self.git(seed, "push", "-q", "origin", "HEAD")
        self.clone = self.base / "clone"
        subprocess.run(["git", "clone", "-q", str(self.origin), str(self.clone)], check=True)

    def tearDown(self):
        self.temp.cleanup()

    def git(self, root, *args):
        return subprocess.run(["git", "-C", str(root), *args], check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def test_dry_run_changes_nothing(self):
        before = self.git(self.clone, "status", "--porcelain=v1").stdout
        result = subprocess.run([sys.executable, "-I", str(ROOT / "tools" / "publish-public.py"),
                                 "--clone", str(self.clone), "--kit", str(ROOT)],
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("DRY RUN", result.stdout)
        self.assertIn("WOULD commit Release", result.stdout)
        self.assertEqual(self.git(self.clone, "status", "--porcelain=v1").stdout, before)
        self.assertTrue((self.clone / "old.txt").exists())

    def test_tree_has_prefaced_readme_and_deletes_old_files(self):
        files = publish_public.public_files(ROOT)
        self.assertNotIn("public-repo/README-public.md", files)
        self.assertTrue(files["README.md"].startswith(
            (ROOT / "public-repo" / "README-public.md").read_bytes().rstrip() + b"\n\n# Claude"))
        publish_public.replace_tree(self.clone, files)
        self.assertFalse((self.clone / "old.txt").exists())
        self.assertEqual((self.clone / "LICENSE").read_bytes(), (ROOT / "LICENSE").read_bytes())

    def test_refuses_non_clone_cleanly(self):
        result = subprocess.run([sys.executable, "-I", str(ROOT / "tools" / "publish-public.py"),
                                 "--clone", str(self.base / "empty")], text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, 2)
        self.assertIn("REFUSED:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_release_check_requires_ok_private(self):
        original = publish_public.run
        try:
            publish_public.run = lambda *args, **kwargs: subprocess.CompletedProcess([], 0, "WARN private: missing\n", "")
            with self.assertRaises(publish_public.PublishError):
                publish_public.check_release(ROOT)
        finally:
            publish_public.run = original


if __name__ == "__main__":
    unittest.main()
